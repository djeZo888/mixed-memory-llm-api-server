"""Actual ManagerSession/Manager calls over root's synthetic slot fixture.

Only host/storage/artifact/profile resources are synthetic. These tests do not
establish deployed pair admission, actual inference streams or live acceptance.
"""
from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent / 'lifecycle'))
import lifecycle
import test_slots as slot_fixture
from test_slots import GLM, QWEN
from control.adapter import ManagerSession
from control.protocol import ControlError, Deadline
from lifecycle.runtime_io import LifecycleError
from common.lifecycle_lease import acquire_lease


class ManagerSlotTests(unittest.TestCase):
    compatible = slot_fixture.SlotTests.compatible
    migrate = slot_fixture.SlotTests.migrate
    pair = slot_fixture.SlotTests.pair

    def setUp(self):
        slot_fixture.SlotTests.setUp(self)
        original_deployment = self.manager.deployment
        def deployment(identifier):
            value = original_deployment(identifier)
            if identifier == QWEN:
                value['_model']['repo_id'] = 'Qwen/Qwen3.8-27B-FP8'
            return value
        patch.object(self.manager, 'deployment', side_effect=deployment).start()
        original_start = self.docker.start
        self.serial = 0
        def start(identity):
            original_start(identity)
            self.serial += 1
            records = self.docker._read()
            next(item for item in records if item['Id'] == identity)['State']['StartedAt'] = f'fixture-start-{self.serial}'
            self.docker._write(records)
        patch.object(self.docker, 'start', side_effect=start).start()
        self.pair()
        self.session = ManagerSession(self.manager, lambda *_: [])

    def lease(self):
        return acquire_lease(system_root=self.root, trusted_uid=self.manager.trusted_uid)

    def test_observe_stop_preflight_select_start_scopes_real_dispatch_and_boot_intent(self):
        observed = self.session.observe(Deadline.after(5))
        self.assertEqual({slot['observed'] for slot in observed['slots'].values()}, {'ready'})
        peer = deepcopy(self.manager.read_state()['slots']['qwen'])
        self.docker.calls.clear()
        with self.lease() as lease:
            self.session.preflight(GLM, lease, Deadline.after(5), slot='glm')
            self.session.stop(lease, Deadline.after(5), slot='glm')
            self.session.observe(Deadline.after(5))
            self.session.select(GLM, lease, Deadline.after(5), slot='glm')
            self.session.start(lease, Deadline.after(5), slot='glm')
        state = self.manager.read_state()
        self.assertEqual(state['slots']['glm']['boot_policy'], 'resume')
        self.assertEqual(state['slots']['qwen'], peer)
        self.assertEqual(self.session.observe(Deadline.after(5))['slots']['glm']['observed'], 'ready')
        self.assertTrue(self.manager.running(self.docker.inspect(peer['container']['id'])))
        self.assertTrue(all(call[1] != peer['container']['id'] for call in self.docker.calls if call[0] in {'stop', 'remove', 'start_enter'}))

    def test_manager_generation_cas_and_preflight_peer_conflict_before_stop(self):
        self.session.observe(Deadline.after(5))
        self.manager.dispatch('stop', target='glm')
        self.docker.calls.clear()
        with self.lease() as lease:
            with self.assertRaisesRegex(LifecycleError, 'stale_slot_generation'):
                self.session.start(lease, Deadline.after(5), slot='glm')
        self.assertEqual(self.docker.calls, [])
        self.session.observe(Deadline.after(5))
        with patch('lifecycle.concurrent_profiles.validate_pair', side_effect=LifecycleError('incompatible_pair_profiles')):
            with self.lease() as lease, self.assertRaisesRegex(ControlError, 'preflight_failed'):
                self.session.preflight(GLM, lease, Deadline.after(5), slot='glm')
        self.assertFalse(any(call[0] in {'stop', 'remove', 'create'} for call in self.docker.calls))

    def test_pending_create_recovers_exact_stopped_identity_without_peer_change(self):
        from lifecycle.manager import Manager
        from control.core import observation, trusted_recovery
        saved = self.manager.read_state()
        original = saved['slots']['glm']['container']
        peer = deepcopy(saved['slots']['qwen'])
        self.docker.stop(original['id'])
        saved['slots']['glm'].update(container=None, container_running=None,
            pending_create={key: original[key] for key in ('image_id', 'name', 'owner', 'instance', 'deployment')})
        with self.lease():
            self.manager.state = saved
            self.manager.save()
        recovery = Manager(self.root / 'absent-config', {'schema_version': 1, 'id': self.instance['id']},
                           recovery_only=True, test_paths=True, lease_system_root=self.root, docker=self.docker)
        session = ManagerSession(recovery, lambda *_: self.fail('recovery catalog access'))
        raw = session.observe(Deadline.after(5))
        public, _ = observation(raw)
        self.assertIsNone(public['slots']['glm']['active_identity'])
        self.assertTrue(trusted_recovery(public, raw, 'glm'))
        self.assertEqual(raw['slots']['glm']['container']['id'], original['id'])
        with self.lease() as lease:
            session.stop(lease, Deadline.after(5), slot='glm')
        result = recovery.read_state(recovery=True)
        self.assertIsNone(result['slots']['glm']['pending_create'])
        self.assertEqual(result['slots']['glm']['container'], original)
        self.assertEqual(result['slots']['qwen'], peer)
        self.assertFalse(result['state_persisted'])

    def test_failed_observation_is_scoped_and_never_saved_ready(self):
        state = self.manager.read_state()
        target_id = state['slots']['glm']['container']['id']
        original = self.manager.trusted_container
        def inspect(identity):
            if identity and identity['id'] == target_id:
                raise LifecycleError('fixture_identity_mismatch')
            return original(identity)
        with patch.object(self.manager, 'trusted_container', side_effect=inspect):
            raw = self.session.observe(Deadline.after(5))
        self.assertFalse(raw['slots']['glm']['observation_available'])
        self.assertIsNone(raw['slots']['glm']['container_running'])
        self.assertEqual(raw['slots']['qwen']['observed'], 'ready')


if __name__ == '__main__':
    unittest.main()
