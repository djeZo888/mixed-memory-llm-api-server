"""Closed dual-Qwen control contracts; synthetic local HTTP, never ai-vm."""
from copy import deepcopy
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from lifecycle import slot_state
from lifecycle.runtime_io import LifecycleError
from test_control_fixtures import HTTPHarness, model_record
from test_control_slots import PairBackend
from control.catalog import GLM_PROFILE, QWEN0_PROFILE, QWEN1_PROFILE
from control.private_network import EXPECTED


class DualQwenTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        os.chmod(self.root, 0o700)
        self.backend = PairBackend(self.root)
        self.backend.records = []
        for identifier, model, port, alias in (
                (GLM_PROFILE, 'unsloth/GLM-5.3-GGUF', 30002, 'glm-5.3'),
                (QWEN0_PROFILE, 'Qwen/Qwen3.8-27B-FP8', 30002, 'qwen3.8-27b-gpu0'),
                (QWEN1_PROFILE, 'Qwen/Qwen3.8-27B-FP8', 30004, 'qwen3.8-27b')):
            record = model_record(identifier, port)
            record.update(model_id=model, context_limit=480000)
            record['endpoint']['served_model'] = alias
            self.backend.records.append(record)
        self.http = HTTPHarness(self.root, backend=self.backend)
        self.http.app.advertised_policy = deepcopy(EXPECTED)
        self.addCleanup(self.http.close)

    def payload(self, slot, identifier, *, interrupt=False):
        state = self.http.status()['slots'][slot]
        return {'target': slot, 'deployment_id': identifier,
                'expected_active': state['active_identity'],
                'expected_generation': state['generation'], 'allow_interrupt': interrupt}

    def switch(self, slot, identifier, key, *, interrupt=False):
        code, receipt = self.http.request('POST', '/control/v1/switch',
                                         self.payload(slot, identifier, interrupt=interrupt), key)
        self.assertEqual(code, 202, receipt)
        result = self.http.finish(receipt)
        self.assertEqual(result['status'], 'succeeded', result)
        return result

    def dual(self):
        self.switch('glm', QWEN0_PROFILE, 'q0')
        self.switch('qwen', QWEN1_PROFILE, 'q1')

    def test_qwen0_recovery_placement_is_exact_and_wrong_slot_refuses(self):
        self.assertEqual(slot_state.deployment_slot(QWEN0_PROFILE), 'glm')
        self.assertEqual(slot_state.deployment_slot(QWEN1_PROFILE), 'qwen')
        self.assertEqual(slot_state.deployment_slot('qwen38-27b-128k'), 'qwen')
        item = slot_state.empty_slot()
        item['selected'] = QWEN0_PROFILE
        slot_state.validate_slot(item, 'glm', lambda _: None)
        with self.assertRaisesRegex(LifecycleError, 'slot_deployment_mismatch'):
            slot_state.validate_slot(item, 'qwen', lambda _: None)

    def test_two_instances_of_same_logical_model_keep_distinct_routes_and_capacity(self):
        self.dual()
        code, catalog = self.http.request(path='/control/v1/catalog')
        self.assertEqual(code, 200)
        self.assertEqual(catalog['current_mode'], 'dual-qwen')
        self.assertEqual(catalog['readiness'], 'ready')
        self.assertFalse(catalog['degraded'])
        entries = {e['deployment_id']: e for e in catalog['entries']}
        q0, q1 = entries[QWEN0_PROFILE], entries[QWEN1_PROFILE]
        self.assertEqual(q0['model_id'], q1['model_id'])
        self.assertNotEqual(q0['instance_id'], q1['instance_id'])
        self.assertEqual((q0['placement'], q1['placement']), ('gpu0', 'gpu1'))
        self.assertEqual(q0['endpoint']['base_url'], 'http://10.156.100.60:30002/v1')
        self.assertEqual(q1['endpoint']['base_url'], 'http://10.156.100.60:30004/v1')
        self.assertEqual(q0['endpoint']['served_model'], 'qwen3.8-27b-gpu0')
        self.assertEqual(q1['endpoint']['served_model'], 'qwen3.8-27b')
        for entry in (q0, q1):
            self.assertEqual(entry['context']['configured_tokens'], 480000)
            self.assertIsNone(entry['context']['accepted_configured_tokens'])
            self.assertIsNone(entry['context']['verified_occupied_tokens'])
            self.assertEqual(entry['inference_busy']['status'], 'unknown')
        self.assertEqual(entries[GLM_PROFILE]['state'], 'available')
        self.assertTrue(all(mode['installed'] for mode in catalog['available_modes']))
        modes = {mode['id']: mode for mode in catalog['available_modes']}
        self.assertEqual(modes['dual-qwen']['qwen_capacity'], 2)
        self.assertEqual(modes['glm-qwen']['qwen_capacity'], 1)
        self.assertEqual(modes['glm-qwen']['performance_class'], 'slow_fallback')
        self.assertEqual(modes['glm-qwen']['intended_use'], 'last_resort')
        self.assertIsNone(modes['glm-qwen']['switch_cost']['seconds'])

    def test_running_replacement_needs_ack_and_preserves_peer_on_roundtrip(self):
        self.dual()
        peer = deepcopy(self.backend.state['slots']['qwen'])
        calls = len(self.backend.calls)
        self.assertEqual(self.http.request('POST', '/control/v1/switch',
            self.payload('glm', GLM_PROFILE), 'no-ack'),
            (409, {'error': {'code': 'interruption_ack_required'}}))
        self.assertFalse(any(call[0] in {'stop', 'select', 'start'} for call in self.backend.calls[calls:]))
        self.backend.state['slots']['glm']['observed'] = 'unhealthy'
        self.assertEqual(self.http.request('POST', '/control/v1/switch',
            self.payload('glm', GLM_PROFILE), 'unhealthy-no-ack'),
            (409, {'error': {'code': 'interruption_ack_required'}}))
        self.switch('glm', GLM_PROFILE, 'to-glm', interrupt=True)
        mixed = self.http.status()
        self.assertEqual(mixed['current_mode'], 'glm-qwen')
        self.assertEqual(self.backend.state['slots']['qwen'], peer)
        self.switch('glm', QWEN0_PROFILE, 'return-q0', interrupt=True)
        self.assertEqual(self.http.status()['current_mode'], 'dual-qwen')
        self.assertEqual(self.backend.state['slots']['qwen'], peer)

    def test_ready_is_not_idle_and_degraded_peer_does_not_hide_capacity(self):
        self.dual()
        state = self.http.status()
        self.assertFalse(state['mutation_busy'])
        self.assertEqual(state['external_backlog']['status'], 'unknown')
        self.assertIsNone(state['switch_cost']['seconds'])
        self.assertFalse(state['switch_cost']['atomic_drain_guarantee'])
        for item in state['slots'].values():
            self.assertEqual(item['configured_context'], {'tokens': 480000, 'provenance': 'declared'})
            self.assertEqual(item['inference_busy']['status'], 'unknown')
            self.assertIsNone(item['inference_busy']['observed_at'])
            self.assertIsNone(item['inference_busy']['freshness'])
            self.assertIsNone(item['inference_busy']['running_requests'])
        self.backend.state['slots']['glm'].update(observed='failed', container_running=False)
        degraded = self.http.status()
        self.assertEqual(degraded['current_mode'], 'dual-qwen')
        self.assertEqual(degraded['readiness'], 'degraded')
        self.assertTrue(degraded['degraded'])
        self.assertEqual(degraded['slots']['qwen']['readiness'], 'ready')

    def test_mutation_busy_is_separate_from_unknown_inference_busy(self):
        self.dual()
        self.backend.release_start.clear()
        self.backend.start_entered.clear()
        code, receipt = self.http.request('POST', '/control/v1/switch',
            self.payload('glm', GLM_PROFILE, interrupt=True), 'loading')
        self.assertEqual(code, 202)
        self.assertTrue(self.backend.start_entered.wait(1))
        state = self.http.status()
        self.assertTrue(state['mutation_busy'])
        self.assertTrue(state['slots']['glm']['mutation_busy'])
        self.assertFalse(state['slots']['qwen']['mutation_busy'])
        self.assertEqual(state['slots']['glm']['inference_busy']['status'], 'unknown')
        self.assertEqual(state['slots']['qwen']['readiness'], 'ready')
        self.backend.release_start.set()
        self.assertEqual(self.http.finish(receipt)['status'], 'succeeded')

    def test_historical_dual_gpu_profiles_do_not_advertise_single_gpu_placement(self):
        historical = {'glm': 'glm-5.3-ud-q4-k-xl-n76-native1m',
                      'qwen': 'qwen38-27b-1000000-yarn4-tp2-bf16kv'}
        for slot, identifier in historical.items():
            original = self.backend.records[0 if slot == 'glm' else 2]
            record = deepcopy(original)
            record.update(deployment_id=identifier, context_limit=1000000)
            self.backend.records.append(record)
            self.backend.state['slots'][slot]['selected'] = identifier
        code, catalog = self.http.request(path='/control/v1/catalog')
        self.assertEqual(code, 200)
        entries = {entry['deployment_id']: entry for entry in catalog['entries']}
        for slot, identifier in historical.items():
            self.assertIsNone(entries[identifier]['placement'])
            self.assertIsNone(catalog['slots'][slot]['placement'])
            self.assertIsNone(catalog['slots'][slot]['configured_context']['tokens'])


if __name__ == '__main__':
    unittest.main()
