"""Owner policy integration, real canonical leases; GPU/storage I/O explicit fixtures."""
import copy
import contextlib
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from tests.test_hardware_latch import MemoryProtectedStore, inventory, BOOT, NEXT_BOOT
from tests.image_runtime.test_service import service, owned_container, owned_state, completed, CID, RUN_ID
from common.lifecycle_lease import acquire_lease, LeaseError
from control.hardware_latch import HardwareLatch, LatchStorageUnavailable
from lifecycle.hardware_policy import (GPU_UUIDS, HardwarePolicy, RegisteredLatchStore,
                                        STATE_SUFFIX, read_latch_status)
from lifecycle.manager import Manager
from lifecycle.runtime_io import LifecycleError
from tests.lifecycle.test_concurrent_profiles import bound, pair

GPU, PEER, IMAGE_GPU = GPU_UUIDS


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.owner = acquire_lease(system_root=self.root, trusted_uid=os.geteuid())
        self.lease = self.owner.__enter__()
        self.addCleanup(self.owner.__exit__, None, None, None)
        self.store = MemoryProtectedStore()
        self.boot = {'boot_id': BOOT, 'uptime_seconds': 150}
        self.calls = []
        self.outputs = {}
        self.policy = HardwarePolicy(self.store, lease=self.lease, system_root=self.root,
                                     trusted_uid=os.geteuid(), run=self.command, boot=lambda: self.boot)

    def command(self, argv, *, timeout):
        self.calls.append(argv)
        self.assertLessEqual(timeout, 2)
        key = argv[1]
        value = self.outputs.get(key, GPU + '\n')
        if isinstance(value, Exception):
            raise value
        return value

    def missing(self, boot=BOOT):
        for second in (0, 5):
            self.policy.observe_inventory(inventory(second, boot=boot, uuids=[]), boot_age_seconds=150)

    def test_absence_empty_two_proofs_survive_app_restart_and_target_probe_reset(self):
        self.missing()
        self.assertTrue(self.store.state['targets'][GPU]['hardware_latched'])
        for _ in range(2):
            with self.assertRaisesRegex(LifecycleError, '^hardware_missing$'):
                self.policy.require_start([GPU])
        self.assertEqual(self.calls, [])
        self.assertEqual(read_latch_status(self.binding(), [GPU])['hardware_latched_boot_id'], BOOT)

    def binding(self):
        binding = Mock()
        binding.read_json.side_effect = lambda *args, **kwargs: self.store.read()
        return binding

    def test_inherited_latch_keeps_new_boot_pending_then_becomes_sticky_new_boot(self):
        self.missing()
        self.boot['boot_id'] = NEXT_BOOT
        self.policy.observe_inventory(inventory(10, boot=NEXT_BOOT, uuids=[]), boot_age_seconds=150)
        self.assertEqual(self.store.state['targets'][GPU]['boot_id'], BOOT)
        # Restore validates persisted nested pending evidence.
        HardwareLatch(self.store.read())
        self.policy.observe_inventory(inventory(15, boot=NEXT_BOOT, uuids=[]), boot_age_seconds=155)
        self.assertEqual(self.store.state['targets'][GPU]['boot_id'], NEXT_BOOT)
        with self.assertRaisesRegex(LifecycleError, 'hardware_missing'):
            self.policy.require_start([GPU])
        self.assertEqual(self.calls, [])

    def test_new_boot_exact_target_validation_clears_only_required_latch_without_global_query(self):
        self.missing()
        self.boot['boot_id'] = NEXT_BOOT
        self.outputs['--query-gpu=uuid'] = RuntimeError('NVML initialization failed')
        self.assertTrue(self.policy.require_start([GPU]))
        self.assertNotIn(GPU, self.store.state['targets'])
        self.assertTrue(self.store.state['targets'][PEER]['hardware_latched'])
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.calls[0][1], '--id=' + GPU)

    def test_unknown_inventory_and_target_failure_cannot_latch(self):
        for bad in ('NVIDIA-SMI failed', GPU + '\n' + GPU, 'bad-uuid',
                    subprocess.TimeoutExpired('nvidia-smi', 2), RuntimeError('init_failure')):
            with self.subTest(bad=bad):
                self.outputs = {'--id=' + GPU: RuntimeError('target_unavailable'), '--query-gpu=uuid': bad}
                for _ in range(2):
                    with self.assertRaisesRegex(LifecycleError, 'hardware_target_unknown'):
                        self.policy.require_start([GPU])
                self.assertEqual(self.store.state['targets'], {})

    def test_successful_empty_inventory_on_failed_start_persists_missing_evidence(self):
        self.outputs = {'--id=' + GPU: RuntimeError('target_unknown'), '--query-gpu=uuid': ''}
        with self.assertRaisesRegex(LifecycleError, 'hardware_target_unknown'):
            self.policy.require_start([GPU])
        with self.assertRaisesRegex(LifecycleError, 'hardware_missing'):
            self.policy.require_start([GPU])
        self.assertEqual(self.store.state['targets'][GPU]['boot_id'], BOOT)

    def test_typed_fault_immediate_during_grace_only_target(self):
        self.boot['uptime_seconds'] = 5
        value = inventory(0, uuids=list(GPU_UUIDS), hardware_faults={GPU: 'gpu_fallen_off_bus'})
        result = self.policy.observe_inventory(value, boot_age_seconds=5)
        self.assertTrue(result[GPU]['hardware_latched'])
        self.assertFalse(result[PEER]['hardware_latched'])
        self.outputs['--id=' + PEER] = PEER
        self.assertTrue(self.policy.require_start([PEER]))

    def test_partial_stale_or_duplicate_fault_metadata_never_proves_missing(self):
        for change in ({'complete': False}, {'age_ms': 15001}, {'gpu_uuids': [GPU, GPU]},
                       {'hardware_faults': {GPU: 'driver_init_failed'}}):
            value = inventory(0, uuids=[], **change) if 'gpu_uuids' not in change else inventory(0, **change)
            self.policy.observe_inventory(value, boot_age_seconds=150)
        self.assertEqual(self.store.state['targets'], {})

    def test_negative_latch_requires_fresh_exact_current_boot_validation(self):
        import datetime
        wall = 1790347200.0
        stamp = datetime.datetime.fromtimestamp(wall, datetime.timezone.utc).isoformat()
        self.policy.wall = lambda: wall
        query = lambda **kwargs: read_latch_status(self.binding(), [GPU], current_boot_id=BOOT,
                                                  wall=lambda: wall, **kwargs)
        self.assertIsNone(query()['hardware_latched'])  # empty state != validated healthy
        self.policy.observe_inventory(inventory(0, uuids=list(GPU_UUIDS)), boot_age_seconds=150)
        self.assertIsNone(query()['hardware_latched'])  # inventory presence is not exact healthy probe
        self.policy.validate_required(GPU, current_boot_id=BOOT, observed_at=stamp, observation_id='exact-proof')
        self.assertFalse(query()['hardware_latched'])
        self.assertEqual(query()['hardware_validation_age_ms'], 0)
        self.assertEqual(query()['hardware_validated_gpu_uuids'], [GPU])
        self.assertIsNone(read_latch_status(self.binding(), [PEER], current_boot_id=BOOT,
                                          wall=lambda: wall)['hardware_latched'])
        self.assertIsNone(read_latch_status(self.binding(), [GPU], current_boot_id=NEXT_BOOT,
                                          wall=lambda: wall)['hardware_latched'])
        self.assertIsNone(read_latch_status(self.binding(), [GPU], current_boot_id=BOOT,
                                          wall=lambda: wall+15.001)['hardware_latched'])
        self.assertIsNone(read_latch_status(self.binding(), [GPU], current_boot_id=BOOT,
                                          wall=lambda: wall-1)['hardware_latched'])
        self.assertTrue(HardwareLatch(self.store.read()).export_state()['validated'][GPU])
        self.assertEqual(query()['identity'], read_latch_status(self.binding(), [GPU], current_boot_id=BOOT,
                                                              wall=lambda: wall+1000)['identity'])

    def test_exact_validation_sticky_same_boot_and_new_boot_clear_without_global_query(self):
        import datetime
        wall = 1790347200.0
        self.policy.wall = lambda: wall
        stamp = datetime.datetime.fromtimestamp(wall, datetime.timezone.utc).isoformat()
        self.missing()
        result = self.policy.validate_required(GPU, current_boot_id=BOOT, observed_at=stamp, observation_id='exact-proof-a')
        self.assertTrue(result['hardware_latched'])
        self.boot['boot_id'] = NEXT_BOOT
        result = self.policy.validate_required(GPU, current_boot_id=NEXT_BOOT, observed_at=stamp, observation_id='exact-proof-b')
        self.assertFalse(result['hardware_latched'])
        self.assertFalse(read_latch_status(self.binding(), [GPU], current_boot_id=NEXT_BOOT,
                                         wall=lambda: wall)['hardware_latched'])
        self.assertEqual(self.calls, [])
        with self.assertRaisesRegex(LifecycleError, 'hardware_validation_stale'):
            self.policy.validate_required(PEER, current_boot_id=BOOT, observed_at=stamp, observation_id='old-boot')

    def test_storage_delay_does_not_refresh_absence_evidence(self):
        ticks = iter([0, 16, 16, 16])
        self.policy.monotonic = lambda: next(ticks)
        self.policy.observe_inventory(inventory(0, uuids=[]), boot_age_seconds=150)
        self.assertEqual(self.store.state['targets'], {})

    def test_missing_or_unreadable_store_denies_without_target_query(self):
        self.store.read = Mock(side_effect=OSError('missing'))
        with self.assertRaises(LatchStorageUnavailable):
            self.policy.require_start([GPU])
        self.assertEqual(self.calls, [])
        self.assertIsNone(read_latch_status(self.binding(), [GPU])['hardware_latched'])

    def test_boot_change_during_probe_and_noncanonical_lease_refused(self):
        values = iter([self.boot, {'boot_id': NEXT_BOOT, 'uptime_seconds': 150}])
        self.policy.boot = lambda: next(values, {"boot_id": NEXT_BOOT, "uptime_seconds": 150})
        with self.assertRaisesRegex(LifecycleError, 'hardware_target_unknown'):
            self.policy.require_start([GPU])
        self.policy.lease = object()
        with self.assertRaises(LeaseError):
            self.policy.require_start([GPU])

    def test_manager_real_start_gate_uses_same_borrowed_lease_before_artifacts(self):
        manager = object.__new__(Manager)
        manager.binding = self.binding()
        manager._hardware_lease = self.lease
        manager.lease_system_root, manager.trusted_uid = self.root, os.geteuid()
        manager.run = self.command
        manager.persistent_writer = Mock(return_value=object())
        manager.check_sources = Mock()
        manager.host_guards = Mock()
        manager.check_artifacts = Mock()
        d = bound(pair.QWEN0_PROFILE)
        self.missing()
        with patch('lifecycle.hardware_policy.boot_identity', return_value=self.boot):
            # Default function object uses OS reads; override only constructor boot seam.
            original = HardwarePolicy.__init__
            def init(policy, *args, **kwargs):
                original(policy, *args, boot=lambda: self.boot, **kwargs)
            with patch.object(HardwarePolicy, '__init__', init):
                with self.assertRaisesRegex(LifecycleError, 'hardware_missing'):
                    manager.prepare_start(d)
        manager.check_artifacts.assert_not_called()
        self.assertEqual(self.calls, [])

    def test_control_preflight_binds_existing_lease_before_dispatch_and_restores_it(self):
        from control.adapter import ManagerSession
        from control.protocol import ControlError, Deadline
        manager = object.__new__(Manager)
        manager.binding = self.binding()
        manager.lease_system_root, manager.trusted_uid = self.root, os.geteuid()
        manager.recovery_only = False
        manager.run = self.command
        manager.persistent_writer = Mock(return_value=object())
        for name in ('check_sources', 'host_guards', 'check_artifacts', 'check_package_admission',
                     'preflight_slot_admission', 'create_args'):
            setattr(manager, name, Mock())
        d = bound(pair.QWEN0_PROFILE)
        manager.deployment = Mock(return_value=d)
        session = ManagerSession(manager, lambda *_: [])
        self.missing()
        original = HardwarePolicy.__init__
        def init(policy, *args, **kwargs):
            original(policy, *args, boot=lambda: self.boot, **kwargs)
        with patch.object(session, '_bounded', return_value=contextlib.nullcontext()), \
                patch.object(HardwarePolicy, '__init__', init):
            with self.assertRaisesRegex(ControlError, 'hardware_missing|preflight_failed'):
                session.preflight(d['id'], self.lease, Deadline.after(2), slot='glm')
        self.assertNotIn('_hardware_lease', manager.__dict__)
        manager.create_args.assert_not_called()
        manager.check_artifacts.assert_not_called()



class ImageOwnerIntegration(unittest.TestCase):
    def tearDown(self):
        service.OPERATION_DEADLINE = None

    def test_manual_and_systemd_image_start_gate_precedes_owned_mutation(self):
        runtime = object.__new__(service.Runtime)
        runtime.guards = Mock()
        runtime.require_hardware = Mock(side_effect=LifecycleError('hardware_missing'))
        runtime.state = Mock()
        with patch.dict(service.os.environ, {'INVOCATION_ID': RUN_ID}), \
                patch.object(service, 'OPERATION_DEADLINE', 900):
            with self.assertRaisesRegex(LifecycleError, 'hardware_missing'):
                runtime.start()
        runtime.state.assert_not_called()

    def test_explicit_image_recovery_latch_refusal_does_not_reset_or_stop(self):
        runtime = Mock()
        runtime.require_hardware.side_effect = LifecycleError('hardware_fault')
        with patch.object(service, 'Runtime', return_value=runtime), \
                patch.object(service, 'acquire_lease', return_value=contextlib.nullcontext('borrowed')), \
                patch.object(service, 'run') as run:
            with self.assertRaisesRegex(LifecycleError, 'hardware_fault'):
                service.recover()
        runtime.reset_owned.assert_not_called()
        run.assert_not_called()
        self.assertIsNone(service.OPERATION_DEADLINE)

    def test_resident_process_proof_does_not_query_peer_or_spare(self):
        runtime = object.__new__(service.Runtime)
        value = owned_container()
        value['State'].update(OOMKilled=False, StartedAt='fixture')
        value['NetworkSettings']['Networks'] = {service.NETWORK: {'NetworkID': 'network'}}
        runtime.config = {'network_id': 'network'}
        runtime.inspect_owned = Mock(return_value=value)
        runtime.check_network = Mock()
        runtime.native_health = Mock(return_value=True)
        runtime.current_device = Mock(return_value={'total_bytes': 100, 'free_bytes': 10})
        runtime.host_headroom = Mock(return_value={})
        expected = ['nvidia-smi', '--id=' + IMAGE_GPU, '--query-compute-apps=gpu_uuid,pid,used_memory',
                    '--format=csv,noheader,nounits']
        def run(argv, **kwargs):
            if argv[:2] == ['docker', 'top']:
                return completed(argv, 'PID\n77\n')
            if argv == expected:
                return completed(argv, IMAGE_GPU + ', 77, 1024\n')
            raise AssertionError('unexpected global/peer query')
        with patch.object(service, 'run', side_effect=run):
            self.assertEqual(runtime.verify_resident(owned_state())['gpu_processes'][0][1], '77')
        with patch.object(service, 'run', side_effect=lambda argv, **kw: completed(argv, 'PID\n88\n')
                          if argv[:2] == ['docker', 'top'] else completed(argv, IMAGE_GPU + ', 77, 1024\n')):
            with self.assertRaisesRegex(RuntimeError, 'ada_process_ownership_mismatch'):
                runtime.verify_resident(owned_state())


class DurableOwnerIntegration(unittest.TestCase):
    def test_real_registered_writer_persists_latch_and_refuses_lost_mount_or_lease(self):
        from tests.lifecycle.test_real_storage_io import LocalStorageFixture
        from control.hardware_latch import empty_state, ProtectedHardwareLatch
        fixture = LocalStorageFixture()
        self.addCleanup(fixture.close)
        # Older fixture injects full mount discovery only; preserve the real
        # root-payload scanner while adapting its verify roles call explicitly.
        original_verify = fixture.storage.verify
        verify = patch.object(fixture.storage, 'verify', side_effect=lambda registration=None, **kwargs: original_verify(registration))
        verify.start()
        self.addCleanup(verify.stop)
        path = fixture.binding.path('services', STATE_SUFFIX)
        fixture.jsonfile(path, empty_state())  # reviewed first activation fixture only
        with fixture.lease() as lease:
            store = RegisteredLatchStore(fixture.binding, lease=lease, storage_io=fixture.api,
                                         system_root=fixture.base, trusted_uid=os.geteuid())
            policy = HardwarePolicy(store, lease=lease, system_root=fixture.base, trusted_uid=os.geteuid(),
                                    boot=lambda: {'boot_id': BOOT, 'uptime_seconds': 150})
            for second in (0, 5):
                policy.observe_inventory(inventory(second, uuids=[]), boot_age_seconds=150)
            self.assertTrue(ProtectedHardwareLatch(store).export_state()['targets'][GPU]['hardware_latched'])
            before = Path(path).read_bytes()
            root_payload = fixture.base / 'var/lib/docker/fixture-layer'
            root_payload.parent.mkdir(parents=True)
            root_payload.write_text('synthetic-root-payload')
            with self.assertRaisesRegex(Exception, 'existing container payload remains on root'):
                store.write(empty_state())
            self.assertEqual(Path(path).read_bytes(), before)
            root_payload.unlink()
            fixture.lost = True
            with self.assertRaises(Exception):
                store.write(empty_state())
            self.assertEqual(Path(path).read_bytes(), before)
        fixture.lost = False
        with self.assertRaises(LeaseError):
            store.write(empty_state())
        self.assertEqual(Path(path).read_bytes(), before)

    def test_real_slot_boot_continues_healthy_peer_and_manual_restart_does_not_stop_latched_target(self):
        from tests.lifecycle.test_slots import SlotTests, GLM, QWEN
        fixture = SlotTests('test_migration_backup_precedes_state_and_keeps_intent_not_readiness')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.migrate()
        for name, profile in [('glm', GLM), ('qwen', QWEN)]:
            fixture.manager.dispatch('select', profile, boot_policy='resume', target=name)
        saved = fixture.manager.read_state()
        for item in saved['slots'].values():
            item['desired'] = 'running'
        fixture.manager.state = saved
        fixture.manager.save()
        store = MemoryProtectedStore()
        latch = HardwareLatch()
        for second in (0, 5):
            latch.observe(GPU, inventory(second, uuids=[PEER, IMAGE_GPU]), current_boot_id=BOOT, boot_age_seconds=150)
        store.state = latch.export_state()
        def gate(deployment):
            gpu = GPU if deployment['id'] == GLM else PEER
            HardwarePolicy(store, lease=fixture.manager._hardware_lease,
                           system_root=fixture.root, trusted_uid=os.geteuid(),
                           run=lambda *args, **kwargs: gpu,
                           boot=lambda: {'boot_id': BOOT, 'uptime_seconds': 150}).require_start([gpu])
        with patch.object(fixture.manager, 'require_hardware', side_effect=gate):
            with self.assertRaisesRegex(LifecycleError, 'partial_slot_transition_failed'):
                fixture.manager.dispatch('boot-start')
            result = fixture.manager.read_state()
            self.assertEqual(result['slots']['qwen']['observed'], 'ready')
            self.assertEqual(result['slots']['glm']['failure'], 'hardware_missing')
            with patch.object(fixture.manager, '_stop') as stop:
                with self.assertRaisesRegex(LifecycleError, 'hardware_missing'):
                    fixture.manager.dispatch('restart', target='glm')
                stop.assert_not_called()
