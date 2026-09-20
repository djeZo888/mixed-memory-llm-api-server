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

    def test_absent_pending_storage_loss_stop_is_proven_and_peer_unchanged(self):
        from lifecycle.manager import Manager
        from control.core import observation, trusted_recovery
        saved = self.manager.read_state()
        identity = saved['slots']['glm']['container']
        peer = deepcopy(saved['slots']['qwen'])
        self.docker.stop(identity['id'])
        self.docker.remove(identity['id'])
        pending = {key: identity[key] for key in ('image_id', 'name', 'owner', 'instance', 'deployment')}
        saved['slots']['glm'].update(container=None, container_running=None, pending_create=pending)
        with self.lease():
            self.manager.state = saved
            self.manager.save()
        recovery = Manager(self.root / 'absent-config', {'schema_version': 1, 'id': self.instance['id']},
                           recovery_only=True, test_paths=True, lease_system_root=self.root, docker=self.docker)
        session = ManagerSession(recovery, lambda *_: self.fail('recovery catalog access'))
        raw = session.observe(Deadline.after(5))
        public, fingerprint = observation(raw)
        self.assertTrue(raw['slots']['glm']['pending_absence_verified'])
        self.assertIsNone(public['slots']['glm']['active_identity'])
        self.assertFalse(public['slots']['glm']['container_running'])
        self.assertTrue(trusted_recovery(public, raw, 'glm'))
        without_marker = deepcopy(raw)
        without_marker['slots']['glm'].pop('pending_absence_verified')
        self.assertFalse(trusted_recovery(public, without_marker, 'glm'))
        self.docker.calls.clear()
        with self.lease() as lease:
            session.stop(lease, Deadline.after(5), slot='glm')
        result = recovery.read_state(recovery=True)
        self.assertIsNone(result['slots']['glm']['pending_create'])
        self.assertIsNone(result['slots']['glm']['container'])
        self.assertEqual(result['slots']['qwen'], peer)
        self.assertFalse(result['state_persisted'])
        self.assertFalse(any(event[0] in {'stop', 'remove', 'create', 'start_enter'} for event in self.docker.calls))
        self.assertNotEqual(fingerprint['glm'], observation(session.observe(Deadline.after(5)))[1]['glm'])

    def test_uncertain_pending_inspection_refuses_recovery_and_keeps_ownership(self):
        from lifecycle.manager import Manager
        from control.core import observation, trusted_recovery
        saved = self.manager.read_state()
        identity = saved['slots']['glm']['container']
        pending = {key: identity[key] for key in ('image_id', 'name', 'owner', 'instance', 'deployment')}
        saved['slots']['glm'].update(container=None, container_running=None, pending_create=pending)
        with self.lease():
            self.manager.state = saved
            self.manager.save()
        recovery = Manager(self.root / 'absent-config', {'schema_version': 1, 'id': self.instance['id']},
                           recovery_only=True, test_paths=True, lease_system_root=self.root, docker=self.docker)
        session = ManagerSession(recovery, lambda *_: self.fail('recovery catalog access'))
        original = self.docker.inspect
        def inspect(name):
            if name == pending['name']:
                raise LifecycleError('command_failed')
            return original(name)
        with patch.object(self.docker, 'inspect', side_effect=inspect):
            raw = session.observe(Deadline.after(5))
            public, _ = observation(raw)
            self.assertNotIn('pending_absence_verified', raw['slots']['glm'])
            self.assertFalse(trusted_recovery(public, raw, 'glm'))
            self.assertFalse(public['slots']['glm']['observation_available'])
            with self.lease() as lease, self.assertRaises(LifecycleError):
                session.stop(lease, Deadline.after(5), slot='glm')
        result = recovery.read_state(recovery=True)
        self.assertEqual(result['slots']['glm']['pending_create'], pending)
        self.assertEqual(result['slots']['qwen'], saved['slots']['qwen'])

    def test_native_capacity_failure_is_precise_and_healthy_peer_stays_ready(self):
        from control.core import observation, safe_error
        original = self.manager.probe_deployment
        def probe(deployment, timeout):
            if deployment['id'] == QWEN:
                raise LifecycleError('concurrent_native_capacity_mismatch')
            return original(deployment, timeout)
        with patch.object(self.manager, 'probe_deployment', side_effect=probe):
            public, _ = observation(self.session.observe(Deadline.after(5)))
        self.assertEqual(public['slots']['qwen']['observed'], 'failed')
        self.assertEqual(public['slots']['qwen']['failure_code'], 'concurrent_native_capacity_mismatch')
        self.assertEqual(public['slots']['glm']['observed'], 'ready')
        self.assertFalse(any(public['slots']['qwen']['ready_proof'].values()))
        self.assertEqual(safe_error(LifecycleError('concurrent_native_metadata_auth_failed')),
                         'concurrent_native_metadata_auth_failed')
        self.assertEqual(safe_error(LifecycleError('private_unknown_failure')), 'transition_failed')
        with patch.object(self.manager, 'prepare_start', side_effect=LifecycleError('concurrent_current_host_memory_insufficient')):
            with self.lease() as lease, self.assertRaises(ControlError) as raised:
                self.session.preflight(QWEN, lease, Deadline.after(5), slot='qwen')
        self.assertEqual(raised.exception.code, 'concurrent_current_host_memory_insufficient')

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
