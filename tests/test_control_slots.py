"""Two fixed slots through real local HTTP/journal/lease; no live acceptance."""
from copy import deepcopy
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_control_fixtures import HTTPHarness, SyntheticBackend, SyntheticSession, model_record
from control.core import observation
from control.protocol import ControlError, StorageUnavailable


class PairBackend(SyntheticBackend):
    def __init__(self, root):
        super().__init__(root)
        empty = deepcopy(self.state)
        empty.update(generation=0, boot_policy='resume')
        self.state = {'schema_version': 3, 'slots': {name: deepcopy(empty) for name in ('glm', 'qwen')}}
        self.records = []
        for slot, model, port in [('glm', 'unsloth/GLM-5.3-GGUF', 30002), ('qwen', 'Qwen/Qwen3.8-27B-FP8', 30004)]:
            record = model_record(slot + '-review', port)
            record['model_id'] = model
            record['context_limit'] = 480000 if slot == 'glm' else 700160
            self.records.append(record)

    def open(self, *, recovery=False):
        if not self.storage_available and not recovery:
            raise StorageUnavailable()
        return PairSession(self, recovery)


class PairSession(SyntheticSession):
    def __init__(self, backend, recovery=False):
        super().__init__(backend)
        self.recovery = recovery

    def observe(self, deadline):
        deadline.remaining()
        if getattr(self.backend, 'fail_observe', False):
            raise ControlError('observation_unavailable')
        raw = deepcopy(self.backend.state)
        raw['recovery_trusted'] = self.recovery
        for value in raw['slots'].values():
            value.update(observation_available=True, storage_available=self.backend.storage_available,
                         state_persisted=self.backend.storage_available,
                         ready_proof={name: value['observed'] == 'ready' for name in
                                      ('trusted_identity', 'safe_network', 'authenticated_model', 'runtime_health')})
        return raw

    def preflight(self, target, lease, deadline, *, slot=None):
        self._borrow('preflight', lease, deadline, slot)
        if self.backend.fail_preflight:
            raise ControlError('preflight_failed')

    def stop(self, lease, deadline, *, slot=None):
        self._borrow('stop', lease, deadline, slot)
        value = self.backend.state['slots'][slot]
        if not self.backend.fail_stop:
            value.update(desired='stopped', observed='stopped', container_running=False,
                         generation=value['generation'] + 1)

    def select(self, target, lease, deadline, *, slot=None):
        self._borrow('select', lease, deadline, slot)
        value = self.backend.state['slots'][slot]
        value.update(selected=target, desired='stopped', generation=value['generation'] + 1)

    def start(self, lease, deadline, *, slot=None):
        self._borrow('start', lease, deadline, slot)
        value = self.backend.state['slots'][slot]
        self.backend.serial += 1
        value.update(desired='running', observed='ready', container_running=True,
                     generation=value['generation'] + 1,
                     container={'instance': 'fixture', 'deployment': value['selected'],
                                'id': str(self.backend.serial), 'generation': str(self.backend.serial)})
        self.backend.fail_observe = getattr(self.backend, 'observe_fail_on_start', False)
        self.backend.start_entered.set()
        if not self.backend.release_start.wait(min(deadline.remaining(), 3)):
            raise ControlError('deadline_exceeded')
        if self.backend.fail_start:
            value.update(observed='failed', failure='start_failed', container_running=False)
            raise ControlError('start_failed')


class SlotTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        os.chmod(self.root, 0o700)
        self.backend = PairBackend(self.root)
        self.http = HTTPHarness(self.root, backend=self.backend)
        self.addCleanup(self.http.close)

    def payload(self, slot, kind, interrupt=True):
        state = self.http.status()['slots'][slot]
        value = {'target': slot, 'expected_active': state['active_identity'], 'expected_generation': state['generation']}
        if kind in {'start', 'switch'}:
            value['deployment_id'] = slot + '-review'
        if kind in {'switch', 'restart'}:
            value['allow_interrupt'] = interrupt
        return value

    def mutate(self, slot, kind, key):
        code, receipt = self.http.request('POST', '/control/v1/' + kind, self.payload(slot, kind), key)
        self.assertEqual(code, 202, receipt)
        return self.http.finish(receipt)

    def test_peer_transition_preserves_identity_generation_and_stale_checks(self):
        self.assertEqual(self.mutate('glm', 'start', 'g')['status'], 'succeeded')
        before = self.http.status()['slots']['glm']
        pending = self.payload('glm', 'stop')
        self.assertEqual(self.mutate('qwen', 'start', 'q')['status'], 'succeeded')
        after = self.http.status()['slots']['glm']
        self.assertEqual((before['generation'], before['active_identity']), (after['generation'], after['active_identity']))
        qwen = deepcopy(self.backend.state['slots']['qwen'])
        code, receipt = self.http.request('POST', '/control/v1/stop', pending, 'g-stop')
        self.assertEqual(code, 202)
        self.assertEqual(self.http.finish(receipt)['status'], 'succeeded')
        self.assertEqual(qwen, self.backend.state['slots']['qwen'])
        self.assertEqual(self.http.request('POST', '/control/v1/stop', pending, 'g-stale')[0], 409)
        replay = self.http.request('POST', '/control/v1/stop', pending, 'g-stop')
        self.assertTrue(replay[1]['replayed'])
        pending['target'] = 'qwen'
        self.assertEqual(self.http.request('POST', '/control/v1/stop', pending, 'g-stop')[1]['error']['code'], 'idempotency_conflict')

    def test_ambiguous_legacy_target_and_mismatch_rejected(self):
        self.mutate('glm', 'start', 'g')
        self.mutate('qwen', 'start', 'q')
        payload = self.payload('glm', 'stop')
        del payload['target']
        self.assertEqual(self.http.request('POST', '/control/v1/stop', payload, 'ambiguous'), (409, {'error': {'code': 'target_required'}}))
        payload = self.payload('glm', 'switch')
        payload['deployment_id'] = 'qwen-review'
        self.assertEqual(self.http.request('POST', '/control/v1/switch', payload, 'mismatch'), (409, {'error': {'code': 'target_mismatch'}}))
        payload['target'] = []
        self.assertEqual(self.http.request('POST', '/control/v1/switch', payload, 'bad')[0], 400)

    def test_independent_failure_stop_and_restart(self):
        self.mutate('glm', 'start', 'g')
        glm = deepcopy(self.backend.state['slots']['glm'])
        self.backend.fail_start = True
        self.assertEqual(self.mutate('qwen', 'start', 'q-fail')['status'], 'failed')
        self.assertEqual(glm, self.backend.state['slots']['glm'])
        self.backend.fail_start = False
        self.mutate('qwen', 'restart', 'q-recover')
        qwen = deepcopy(self.backend.state['slots']['qwen'])
        self.backend.fail_stop = True
        self.assertEqual(self.mutate('glm', 'stop', 'g-fail')['failure_code'], 'stop_not_proven')
        self.assertEqual(qwen, self.backend.state['slots']['qwen'])
        self.backend.fail_stop = False
        self.assertEqual(self.mutate('glm', 'restart', 'g-restart')['status'], 'succeeded')
        self.assertEqual(qwen, self.backend.state['slots']['qwen'])

    def test_catalog_status_and_capacity_not_accepted_from_readiness(self):
        self.mutate('glm', 'start', 'g')
        self.mutate('qwen', 'start', 'q')
        code, catalog = self.http.request(path='/control/v1/catalog')
        self.assertEqual(code, 200)
        self.assertNotIn('selected', catalog)
        self.assertEqual({entry['slot'] for entry in catalog['entries']}, {'glm', 'qwen'})
        self.assertEqual([entry['state'] for entry in catalog['entries']], ['ready', 'ready'])
        self.assertEqual([entry['context']['accepted_configured_tokens'] for entry in catalog['entries']], [None, None])
        self.assertEqual([entry['context']['acceptance_status'] for entry in catalog['entries']], ['unvalidated', 'unvalidated'])
        code, status = self.http.request(path='/control/v1/status/qwen')
        self.assertEqual((code, status['slot'], status['observed']), (200, 'qwen', 'ready'))

    def test_single_selected_legacy_stop_and_journal_restart_replay(self):
        self.mutate('glm', 'start', 'g')
        payload = self.payload('glm', 'stop')
        del payload['target']
        code, receipt = self.http.request('POST', '/control/v1/stop', payload, 'legacy')
        self.assertEqual(code, 202)
        self.http.finish(receipt)
        self.assertEqual(self.http.journal.read()['schema'], 2)
        self.http.close()
        self.http = HTTPHarness(self.root, backend=self.backend)
        self.addCleanup(self.http.close)
        self.assertTrue(self.http.request('POST', '/control/v1/stop', payload, 'legacy')[1]['replayed'])

    def test_storage_loss_targeted_stop_retains_peer(self):
        self.mutate('glm', 'start', 'g')
        self.mutate('qwen', 'start', 'q')
        self.backend.storage_available = False
        peer = deepcopy(self.backend.state['slots']['qwen'])
        outcome = self.mutate('glm', 'stop', 'recovery')
        self.assertEqual(outcome['status'], 'succeeded')
        self.assertFalse(outcome['state_persisted'])
        self.assertEqual(peer, self.backend.state['slots']['qwen'])

    def test_loading_and_interrupt_ack_are_target_scoped(self):
        self.mutate('glm', 'start', 'g')
        before = self.http.status()['slots']['glm']
        self.backend.release_start.clear()
        code, receipt = self.http.request('POST', '/control/v1/start', self.payload('qwen', 'start'), 'q')
        self.assertEqual(code, 202)
        self.assertTrue(self.backend.start_entered.wait(1))
        status = self.http.status()
        self.assertEqual(status['slots']['glm']['observed'], 'ready')
        self.assertEqual(status['slots']['glm']['active_identity'], before['active_identity'])
        self.assertEqual(status['slots']['qwen']['observed'], 'loading')
        self.assertEqual(self.http.request('POST', '/control/v1/stop', self.payload('glm', 'stop'), 'busy')[0], 409)
        self.backend.release_start.set()
        self.assertEqual(self.http.finish(receipt)['status'], 'succeeded')
        self.assertEqual(self.http.request('POST', '/control/v1/restart', self.payload('glm', 'restart', False), 'no-ack')[1]['error']['code'], 'interruption_ack_required')
        self.assertEqual(self.http.request('POST', '/control/v1/start', self.payload('glm', 'start'), 'already')[1]['error']['code'], 'already_running')

    def test_interrupted_receipt_reconciles_its_slot_without_replay(self):
        self.mutate('glm', 'start', 'g')
        self.mutate('qwen', 'start', 'q')
        journal = self.http.journal.read()
        operation = next(op for op in journal['entries'].values() if op.get('slot') == 'qwen')
        operation.update(status='running', completed_at=None)
        self.assertTrue(self.http.journal.save(journal))
        self.http.close()
        before = len(self.backend.calls)
        self.http = HTTPHarness(self.root, backend=self.backend)
        self.addCleanup(self.http.close)
        code, outcome = self.http.request(path=operation['poll_url'])
        self.assertEqual((code, outcome['status'], outcome['slot']), (200, 'interrupted', 'qwen'))
        self.assertEqual(outcome['observed']['selected'], 'qwen-review')
        self.assertEqual(before, len(self.backend.calls))

    def test_failed_final_observation_keeps_target_generation(self):
        self.mutate('glm', 'start', 'g')
        payload = self.payload('qwen', 'start')
        self.backend.observe_fail_on_start = True
        self.backend.fail_start = True
        code, receipt = self.http.request('POST', '/control/v1/start', payload, 'q-fail-observe')
        self.assertEqual(code, 202)
        outcome = self.http.finish(receipt)
        self.assertEqual(outcome['status'], 'failed')
        self.assertEqual(outcome['generation'], payload['expected_generation'])
        self.assertFalse(outcome['state_persisted'])
        self.backend.fail_observe = False

    def test_malformed_slot_state_fails_closed(self):
        for slots in ({}, {'glm': {}}, {'glm': {}, 'qwen': {}}, {'glm': [], 'qwen': []}):
            with self.assertRaises(ControlError):
                observation({'schema_version': 3, 'slots': slots})


if __name__ == '__main__':
    unittest.main()
