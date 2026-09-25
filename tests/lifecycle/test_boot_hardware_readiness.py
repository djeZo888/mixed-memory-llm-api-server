"""First-boot exact hardware admission, without live hardware or model work.

The recorded failure was an unknown Q1 exact probe before any native start,
followed by successful Q0 restoration and later current-boot Q1 proof. The
original NVML error subtype was not retained; these fixtures inject a generic
unknown and do not claim that the historical call timed out.

Real policy, latch state machine and canonical lease run against explicit
clock/NVML seams. The manager integration uses its real slot dispatcher and
registered anchored latch writer, with synthetic Docker/profile/mount discovery.
"""
from __future__ import annotations

import copy
import datetime
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))

from common.lifecycle_lease import acquire_lease
from control.hardware_latch import HardwareLatch, LatchStorageUnavailable
from lifecycle.hardware_policy import (GPU_UUIDS, HardwarePolicy,
    RegisteredLatchStore, STATE_SUFFIX, read_latch_status)
from lifecycle.runtime_io import LifecycleError
from tests.test_hardware_latch import BOOT, NEXT_BOOT, MemoryProtectedStore, inventory

Q0, Q1, ADA = GPU_UUIDS
EPOCH = 1790337600.0
PRIVATE = 'fixture_private_probe_output_must_not_escape'


class Clock:
    def __init__(self):
        self.elapsed = 0.0
        self.sleeps = []

    def monotonic(self):
        return self.elapsed

    def wall(self):
        return EPOCH + self.elapsed

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.elapsed += seconds


def prior_proofs():
    stamp = datetime.datetime.fromtimestamp(EPOCH - 60, datetime.timezone.utc).isoformat()
    return {'schema_version': 1, 'targets': {}, 'validated': {
        gpu: {'boot_id': BOOT, 'observed_at': stamp, 'observation_id': 'prior-' + str(index)}
        for index, gpu in enumerate(GPU_UUIDS)}}


class BootHardwarePolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        owner = acquire_lease(system_root=self.root, trusted_uid=os.geteuid())
        self.lease = owner.__enter__()
        self.addCleanup(owner.__exit__, None, None, None)
        self.clock = Clock()
        self.boot_id = NEXT_BOOT
        self.store = MemoryProtectedStore()
        self.store.state = prior_proofs()
        self.commands, self.diagnostics = [], []
        self.probe = lambda gpu, timeout: gpu + '\n'
        self.policy = HardwarePolicy(self.store, lease=self.lease,
            system_root=self.root, trusted_uid=os.geteuid(), run=self.command,
            boot=self.boot, wall=self.clock.wall, monotonic=self.clock.monotonic,
            sleep=self.clock.sleep)

    def boot(self):
        return {'boot_id': self.boot_id, 'uptime_seconds': 150 + self.clock.elapsed}

    def command(self, argv, *, timeout):
        self.commands.append((copy.deepcopy(argv), timeout, self.clock.elapsed))
        self.assertGreater(timeout, 0)
        self.assertLessEqual(timeout, 2)
        if argv[1] == '--query-gpu=uuid':
            raise LifecycleError('hardware_inventory_unknown')
        self.assertTrue(argv[1].startswith('--id='))
        return self.probe(argv[1][len('--id='):], timeout)

    def require(self, *, boot_restore=True):
        return self.policy.require_start([Q1], boot_restore=boot_restore,
                                         diagnostic=self.diagnostics.append)

    def targets(self):
        return [item for item in self.commands if item[0][1].startswith('--id=')]

    def status(self):
        class Binding:
            def path(_self, *args):
                return 'fixture-protected-state'

            def read_json(_self, *args, **kwargs):
                return self.store.read()
        return read_latch_status(Binding(), [Q1], current_boot_id=self.boot_id,
                                 wall=self.clock.wall)

    def test_boot_transient_unknown_requires_new_exact_current_boot_proof(self):
        prior = copy.deepcopy(self.store.state['validated'][Q1])
        def probe(gpu, timeout):
            if len(self.targets()) == 1:
                self.clock.elapsed += min(timeout, .1)
                self.assertEqual(self.store.state['validated'][Q1], prior)
                self.assertIsNone(self.status()['hardware_latched'])
                raise RuntimeError(PRIVATE)
            self.clock.elapsed += .01
            return gpu + '\n'
        self.probe = probe
        self.assertTrue(self.require())
        self.assertEqual(len(self.targets()), 2)
        # One absence fallback is retained; no repeated global queries.
        self.assertEqual(sum(cmd[0][1] == '--query-gpu=uuid' for cmd in self.commands), 1)
        self.assertTrue(self.clock.sleeps)
        self.assertLessEqual(self.clock.elapsed, 10)
        self.assertFalse(self.status()['hardware_latched'])

        self.assertEqual(self.store.state['validated'][Q1]['boot_id'], NEXT_BOOT)
        self.assertEqual(self.store.state['validated'][Q0], prior_proofs()['validated'][Q0])
        self.assertTrue(self.diagnostics)
        self.assertNotIn(PRIVATE, json.dumps(self.diagnostics))

    def test_persistent_unknown_exhausts_hard_budget_without_fabricating_health(self):
        before = copy.deepcopy(self.store.state)
        def probe(_gpu, timeout):
            self.clock.elapsed += timeout
            raise RuntimeError(PRIVATE)
        self.probe = probe
        with self.assertRaisesRegex(LifecycleError, '^hardware_target_unknown$'):
            self.require()
        self.assertGreater(len(self.targets()), 1)
        self.assertLessEqual(self.clock.elapsed, 10.000001)
        for _argv, timeout, started in self.targets():
            self.assertLessEqual(timeout, 10 - started + .000001)
        self.assertLessEqual(sum(cmd[0][1] == '--query-gpu=uuid' for cmd in self.commands), 1)
        self.assertEqual(self.store.state, before)
        self.assertIsNone(self.status()['hardware_latched'])
        self.assertNotIn(PRIVATE, json.dumps(self.diagnostics))

    def test_manual_unknown_has_one_exact_attempt_and_no_backoff(self):
        self.probe = lambda *_: (_ for _ in ()).throw(RuntimeError(PRIVATE))
        with self.assertRaisesRegex(LifecycleError, '^hardware_target_unknown$'):
            self.require(boot_restore=False)
        self.assertEqual(len(self.targets()), 1)
        self.assertEqual(self.clock.sleeps, [])
        self.assertIsNone(self.status()['hardware_latched'])

    def test_same_boot_confirmed_missing_or_fault_never_probes_or_retries(self):
        for fault in (None, 'gpu_fallen_off_bus'):
            with self.subTest(fault=fault):
                latch = HardwareLatch()
                for second in (0, 5):
                    latch.observe(Q1, inventory(second, boot=NEXT_BOOT,
                        uuids=[Q0, ADA], hardware_faults={} if fault is None else {Q1: fault}),
                        current_boot_id=NEXT_BOOT, boot_age_seconds=150)
                self.store.state = latch.export_state()
                before = copy.deepcopy(self.store.state)
                with self.assertRaisesRegex(LifecycleError, '^hardware_' + ('missing' if fault is None else 'fault') + '$'):
                    self.require()
                self.assertEqual(self.commands, [])
                self.assertEqual(self.clock.sleeps, [])
                self.assertEqual(self.store.state, before)

    def test_boot_change_during_exact_probe_is_not_retried_or_validated(self):
        before = copy.deepcopy(self.store.state)
        def probe(gpu, _timeout):
            self.boot_id = BOOT
            return gpu + '\n'
        self.probe = probe
        with self.assertRaisesRegex(LifecycleError, '^hardware_target_unknown$'):
            self.require()
        self.assertEqual(len(self.targets()), 1)
        self.assertEqual(self.clock.sleeps, [])
        self.assertEqual(self.store.state, before)

    def test_unreadable_latch_refuses_before_probe_without_retry(self):
        with patch.object(self.store, 'read', side_effect=OSError('protected-state-unavailable')):
            with self.assertRaises(LatchStorageUnavailable):
                self.require()
        self.assertEqual(self.commands, [])
        self.assertEqual(self.clock.sleeps, [])

    def test_delayed_diagnostic_does_not_refresh_exact_probe_timestamp(self):
        before = copy.deepcopy(self.store.state)
        def delayed(_receipt):
            self.clock.elapsed += 16
        with self.assertRaisesRegex(LifecycleError, '^hardware_validation_stale$'):
            self.policy.require_start([Q1], boot_restore=True, diagnostic=delayed)
        self.assertEqual(len(self.targets()), 1)
        self.assertEqual(self.store.state, before)
        self.assertIsNone(self.status()['hardware_latched'])

    def test_new_boot_exact_positive_clears_only_inherited_target_protection(self):
        latch = HardwareLatch()
        for gpu in (Q0, Q1):
            for second in (0, 5):
                latch.observe(gpu, inventory(second, boot=BOOT, uuids=[ADA]),
                              current_boot_id=BOOT, boot_age_seconds=150)
        self.store.state = latch.export_state()
        self.assertTrue(self.require())
        self.assertNotIn(Q1, self.store.state['targets'])
        self.assertTrue(self.store.state['targets'][Q0]['hardware_latched'])
        self.assertEqual(len(self.targets()), 1)
        self.assertFalse(self.status()['hardware_latched'])

    def test_second_target_unknown_inventory_cannot_erase_first_exact_proof(self):
        calls = {Q0: 0, Q1: 0}
        def command(argv, *, timeout):
            self.commands.append((list(argv), timeout, self.clock.elapsed))
            self.clock.elapsed += .01
            if argv[1] == '--query-gpu=uuid':
                return ''  # Successful complete empty inventory, after Q0 proof.
            gpu = argv[1].removeprefix('--id=')
            calls[gpu] += 1
            if gpu == Q1 and calls[gpu] == 1:
                raise LifecycleError('command_failed')
            return gpu + '\n'
        self.policy.run = command
        self.assertTrue(self.policy.require_start([Q0, Q1], boot_restore=True))
        self.assertEqual(calls, {Q0: 1, Q1: 2})
        self.assertEqual(self.store.state['targets'], {})
        for gpu in (Q0, Q1):
            self.assertEqual(self.store.state['validated'][gpu]['boot_id'], NEXT_BOOT)


class BootHardwareManagerTests(unittest.TestCase):
    def setUp(self):
        from tests.lifecycle.test_slots import SlotTests, GLM, QWEN
        from tests.lifecycle.test_real_storage_io import LocalStorageFixture
        self.fixture = SlotTests('test_boot_order_explicit_intents_and_partial_stop_failure')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.manager, self.docker = self.fixture.manager, self.fixture.docker
        self.profile_gpu = {GLM: Q0, QWEN: Q1}
        self.fixture.pair()
        self.manager.dispatch('boot-stop')
        self.saved = self.manager.read_state()
        self.docker.calls.clear()

        self.storage = LocalStorageFixture()
        self.addCleanup(self.storage.close)
        original_verify = self.storage.storage.verify
        self.verify = patch.object(self.storage.storage, 'verify',
            side_effect=lambda registration=None, **kwargs: original_verify(registration))
        self.verify.start()
        self.addCleanup(self.verify.stop)
        self.path = self.storage.binding.path('services', STATE_SUFFIX)
        self.storage.jsonfile(self.path, prior_proofs())
        self.clock = Clock()
        self.mode = 'transient'
        self.commands, self.events, self.gates = [], [], []
        self.target_counts = {Q0: 0, Q1: 0}
        self.gate_patch = patch.object(self.manager, 'require_hardware', side_effect=self.gate)
        self.gate_patch.start()
        self.addCleanup(self.gate_patch.stop)
        original_start = self.docker.start
        def native_start(identity):
            slot = next(name for name, value in self.saved['slots'].items()
                        if value['container']['id'] == identity)
            gpu = Q0 if slot == 'glm' else Q1
            proof = self.latch()['validated'][gpu]
            self.assertEqual(proof['boot_id'], NEXT_BOOT)
            self.events.append(('native_start', gpu))
            return original_start(identity)
        self.start_patch = patch.object(self.docker, 'start', side_effect=native_start)
        self.start_patch.start()
        self.addCleanup(self.start_patch.stop)

    def latch(self):
        return self.storage.binding.read_json('services', self.path)

    def gate(self, deployment):
        gpu = self.profile_gpu[deployment['id']]
        boot_restore = getattr(self.manager, '_boot_restore_hardware', False)
        self.gates.append((gpu, boot_restore))
        lease = self.manager._hardware_lease
        store = RegisteredLatchStore(self.storage.binding, lease=lease,
            storage_io=self.storage.api, system_root=self.fixture.root,
            trusted_uid=os.geteuid())
        policy = HardwarePolicy(store, lease=lease, run=self.command,
            boot=lambda: {'boot_id': NEXT_BOOT, 'uptime_seconds': 150 + self.clock.elapsed},
            system_root=self.fixture.root, trusted_uid=os.geteuid(),
            wall=self.clock.wall, monotonic=self.clock.monotonic, sleep=self.clock.sleep)
        return policy.require_start([gpu], boot_restore=boot_restore)

    def command(self, argv, *, timeout):
        self.commands.append((list(argv), timeout, self.clock.elapsed))
        if argv[1] == '--query-gpu=uuid':
            raise LifecycleError('hardware_inventory_unknown')
        gpu = argv[1].removeprefix('--id=')
        self.assertIn(gpu, (Q0, Q1))
        self.target_counts[gpu] += 1
        self.events.append(('exact_probe', gpu))
        if gpu == Q1 and (self.mode == 'persistent' or self.target_counts[gpu] == 1):
            self.assertFalse(any(item == ('native_start', Q1) for item in self.events))
            self.assertEqual(self.latch()['validated'][Q1]['boot_id'], BOOT)
            self.clock.elapsed += timeout
            raise LifecycleError('command_failed')
        self.clock.elapsed += .01
        return gpu + '\n'

    def assert_saved_intent(self, state):
        for name in ('qwen', 'glm'):
            self.assertEqual(state['slots'][name]['desired'], 'running')
            self.assertEqual(state['slots'][name]['boot_policy'], 'resume')
            self.assertEqual(state['slots'][name]['container'], self.saved['slots'][name]['container'])
            self.assertIsNone(state['slots'][name]['pending_create'])
        self.assertFalse(any(call[0] in {'create', 'stop', 'remove'} for call in self.docker.calls))

    def test_real_boot_gate_transient_unknown_starts_each_native_once(self):
        state = self.manager.dispatch('boot-start')
        self.assertEqual(self.target_counts, {Q0: 1, Q1: 2})
        self.assertEqual([item for item in self.events if item[0] == 'native_start'],
                         [('native_start', Q1), ('native_start', Q0)])
        self.assertEqual(self.gates, [(Q1, True), (Q0, True)])
        self.assertTrue(all(row['observed'] == 'ready' for row in state['slots'].values()))
        self.assert_saved_intent(state)
        self.assertFalse(self.manager._boot_restore_hardware)
        self.assertGreater(len(self.storage.anchors), 0)

    def test_real_boot_gate_exhaustion_preserves_unknown_and_starts_healthy_peer_once(self):
        self.mode = 'persistent'
        with self.assertRaisesRegex(LifecycleError, '^partial_slot_transition_failed_use_status$'):
            self.manager.dispatch('boot-start')
        state = self.manager.read_state()
        self.assertGreater(self.target_counts[Q1], 1)
        self.assertEqual(self.target_counts[Q0], 1)
        self.assertLessEqual(self.clock.elapsed, 10.010001)
        self.assertEqual([item for item in self.events if item[0] == 'native_start'], [('native_start', Q0)])
        self.assertEqual(state['slots']['qwen']['failure'], 'hardware_target_unknown')
        self.assertEqual(state['slots']['glm']['observed'], 'ready')
        self.assertEqual(self.latch()['validated'][Q1]['boot_id'], BOOT)
        self.assertEqual(self.latch()['targets'], {})
        self.assert_saved_intent(state)
        self.assertFalse(self.manager._boot_restore_hardware)

    def test_manual_target_does_not_inherit_boot_probe_retry(self):
        peer = copy.deepcopy(self.saved['slots']['glm'])
        with self.assertRaisesRegex(LifecycleError, '^hardware_target_unknown$'):
            self.manager.dispatch('start', target='qwen')
        state = self.manager.read_state()
        self.assertEqual(self.target_counts, {Q0: 0, Q1: 1})
        self.assertEqual(self.gates, [(Q1, False)])
        self.assertEqual(self.clock.sleeps, [])
        self.assertEqual(state['slots']['glm'], peer)
        self.assertFalse(any(item[0] == 'native_start' for item in self.events))
        self.assert_saved_intent(state)
        self.assertFalse(self.manager._boot_restore_hardware)

    def test_actual_manager_diagnostic_storage_guard_failure_denies_before_validation(self):
        from lifecycle import concurrent_profiles as pair
        from lifecycle.storage_binding import BindingError
        from install.storage import StorageError
        manager = self.storage.manager
        before = Path(self.path).read_bytes()
        constructor = HardwarePolicy.__init__
        def init(policy, *args, **kwargs):
            constructor(policy, *args, **dict(kwargs,
                boot=lambda: {'boot_id': NEXT_BOOT, 'uptime_seconds': 150},
                wall=self.clock.wall, monotonic=self.clock.monotonic, sleep=self.clock.sleep))
        def probe(_argv, **_kwargs):
            self.storage.lost = True  # Detach discovered at diagnostic writer's guard.
            return Q1 + '\n'
        manager.run = probe
        manager._boot_restore_hardware = True
        with self.storage.lease() as lease:
            manager._hardware_lease = lease
            with patch.object(HardwarePolicy, '__init__', init):
                with self.assertRaises((LifecycleError, BindingError, StorageError)):
                    manager.require_hardware({'id': pair.QWEN_PROFILE, 'launch': {'gpus': [Q1]}})
        self.storage.lost = False
        self.assertEqual(Path(self.path).read_bytes(), before)
        evidence = Path(self.storage.binding.path('services', 'llm-manager/evidence'))
        self.assertEqual(list(evidence.glob('boot-hardware-*.json')), [])
        self.assertEqual(self.storage.docker.calls, [])
