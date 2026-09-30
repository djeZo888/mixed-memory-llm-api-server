"""SOURCE04 admission diagnosis, not a replay of either historical failure.

Actual supervise/sample/latch and temporary canonical flock; all installed
storage, systemd, GPU and Docker I/O are replaced by explicit fixture boundaries.
The source-only bounded admission correction never replays acquired work.
"""
import contextlib
import copy
import os
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from common.lifecycle_lease import LeaseBusy
from tests import test_mimo_owner as owner_tests

o = owner_tests.o


class BeforeOwnership(Exception):
    pass


class StartupAdmissionTests(unittest.TestCase):
    setUp = owner_tests.LatchRefreshTests.setUp
    borrowed_scope = owner_tests.LatchRefreshTests.borrowed_scope

    def fixture(self, initialize_lock=True):
        manifest = {'memory': {'limit_bytes': 800}, 'container_name': 'fixture'}
        old = dict(manifest, predecessor=True)
        selected = {'selected_frontier': o.MODEL, 'manifest_sha256': o.digest(manifest)}
        previous = {'schema_version': 2, 'status': 'SETTLED', 'request_hold': False,
                    'manifest_sha256': o.digest(old), 'launch_id': 'preserved',
                    'settlement': {'pid_released': True, 'cgroup_empty': True,
                                   'gpu_compute_empty': True}}
        recovery = {'status': 'SETTLED_SOURCE_RECONCILED',
                    'transition': o.STOP_TIMEOUT_TRANSITION,
                    'prior_state_digest': o.digest(previous),
                    'manifest_sha256': o.digest(manifest), 'selection': selected}
        before = copy.deepcopy(previous)
        self.h.MountedStorageGuard = Mock(side_effect=lambda _: contextlib.nullcontext())
        self.h.s = SimpleNamespace(root_payload_guard=Mock())
        acquire = self.h.acquire_lease
        self.h.acquire_lease = Mock(side_effect=acquire)
        def read(path):
            if path == o.BASE / 'manifest.json':
                return copy.deepcopy(manifest)
            if path == o.BASE / 'state.json':
                return copy.deepcopy(previous)
            raise AssertionError('unexpected fixture read')
        def run(argv, *_):
            if argv[:2] == ['systemctl', 'show']:
                return 'MainPID=0\nActiveState=inactive\n'
            if argv[:2] == ['nvidia-smi', '--id=' + o.GPU]:
                if '--query-gpu=uuid,memory.total,memory.free,temperature.gpu' in argv:
                    return o.GPU + ', 100, 8, 40'
                return ''
            if argv[:2] == ['docker', 'ps']:
                return 'a' * 64
            raise AssertionError('unexpected native operation')
        self.boundaries = dict(
            setup=Mock(return_value=self.h), source_preflight=Mock(),
            read=Mock(side_effect=read), require_selected=Mock(return_value=selected),
            settled_source_for_start=Mock(return_value=(recovery, old)),
            timeout_physical=Mock(), unit_identity=Mock(return_value={'pid': 1}),
            storage_paths=Mock(), run=Mock(side_effect=run),
            memory=Mock(return_value=dict(MemTotal=1000, MemAvailable=1000,
                                         SwapTotal=100, SwapFree=100)),
            temperature_limit=Mock(return_value=85), memory_policy=Mock(),
            inspect=Mock(return_value={'State': {'Running': False, 'Pid': 0}}),
            exact_container=Mock(side_effect=lambda c, *_: c),
            write=Mock(side_effect=BeforeOwnership),
            exclusive_recovery_write=Mock(), settle_state=Mock(), record_failure=Mock())
        if initialize_lock:
            with acquire(blocking=False):
                pass
        stack = contextlib.ExitStack()
        stack.enter_context(patch.object(o, "LEASE_PATH", self.root / "run/llmctl/lifecycle.lock"))
        stack.enter_context(patch.object(o, "STARTUP_LEASE_SECONDS", .15, create=True))
        for name, value in self.boundaries.items():
            stack.enter_context(patch.object(o, name, value))
        stack.enter_context(self.borrowed_scope())
        self.addCleanup(stack.close)
        return previous, before, acquire

    def assert_unconsumed(self, previous, before):
        self.assertEqual(previous, before)
        self.boundaries['exclusive_recovery_write'].assert_not_called()
        self.boundaries['settle_state'].assert_not_called()
        self.boundaries['record_failure'].assert_not_called()
        self.assertEqual(self.store.writes, 0)

    def test_sustained_entry_contention_times_out_before_guard_or_ownership(self):
        previous, before, acquire = self.fixture()
        with acquire(blocking=False):
            started = time.monotonic()
            with self.assertRaisesRegex(o.OwnerRefusal, 'startup_lease_deadline'):
                o.supervise()
        self.assertLess(time.monotonic() - started, .5)
        self.assertGreater(self.h.acquire_lease.call_count, 1)
        self.h.MountedStorageGuard.assert_not_called()
        self.boundaries['timeout_physical'].assert_not_called()
        self.boundaries['run'].assert_not_called()
        self.boundaries['write'].assert_not_called()
        self.assert_unconsumed(previous, before)

    def test_transient_real_holder_release_reaches_body_once(self):
        previous, before, acquire = self.fixture()
        self.store.state['validated'][o.GPU]['observed_at'] = self.stamp()
        ready, release = threading.Event(), threading.Event()
        def holder():
            with acquire(blocking=False):
                ready.set()
                release.wait(.5)
        thread = threading.Thread(target=holder)
        thread.start()
        self.assertTrue(ready.wait(.5))
        original_sleep = time.sleep
        def release_on_wait(seconds):
            release.set()
            thread.join(.5)
            original_sleep(seconds)
        try:
            with patch.object(o.time, 'sleep', side_effect=release_on_wait):
                with self.assertRaises(BeforeOwnership):
                    o.supervise()
        finally:
            release.set()
            thread.join(.5)
        self.assertGreater(self.h.acquire_lease.call_count, 1)
        self.boundaries['source_preflight'].assert_has_calls([
            unittest.mock.call(self.h, unittest.mock.ANY),
            unittest.mock.call(self.h, unittest.mock.ANY)])
        self.boundaries['timeout_physical'].assert_called_once()
        self.boundaries['write'].assert_called_once()
        self.assert_unconsumed(previous, before)

    def test_waiting_replaced_inode_refuses_before_body(self):
        previous, before, acquire = self.fixture()
        def replace(_):
            o.LEASE_PATH.unlink()
            fd = os.open(o.LEASE_PATH, os.O_CREAT | os.O_WRONLY | os.O_EXCL, 0o600)
            os.close(fd)
        with acquire(blocking=False), patch.object(o.time, 'sleep', side_effect=replace):
            with self.assertRaisesRegex(o.OwnerRefusal, 'startup_lock_changed'):
                o.supervise()
        self.boundaries['write'].assert_not_called()
        self.boundaries['run'].assert_not_called()
        self.assert_unconsumed(previous, before)

    def test_waiting_boot_change_refuses_before_body(self):
        previous, before, acquire = self.fixture()
        boot = [self.boot]
        with patch.object(o, 'BOOT', SimpleNamespace(read_text=lambda: boot[0])):
            with acquire(blocking=False), patch.object(o.time, 'sleep', side_effect=lambda _: boot.__setitem__(0, 'changed')):
                with self.assertRaisesRegex(o.OwnerRefusal, 'boot_changed'):
                    o.supervise()
        self.boundaries['write'].assert_not_called()
        self.boundaries['run'].assert_not_called()
        self.assert_unconsumed(previous, before)

    def test_prior_state_drift_under_lease_refuses_before_body(self):
        previous, before, _ = self.fixture()
        original = self.boundaries['read'].side_effect
        reads = [0]
        def changed(path):
            value = original(path)
            if path == o.BASE / 'state.json':
                reads[0] += 1
                if reads[0] > 1:
                    value['status'] = 'HELD'
            return value
        self.boundaries['read'].side_effect = changed
        with self.assertRaisesRegex(o.OwnerRefusal, 'startup_state_changed'):
            o.supervise()
        self.boundaries['write'].assert_not_called()
        self.boundaries['run'].assert_not_called()
        self.assert_unconsumed(previous, before)

    def test_manifest_drift_under_lease_refuses_before_body(self):
        previous, before, _ = self.fixture()
        original = self.boundaries['read'].side_effect
        reads = [0]
        def changed(path):
            value = original(path)
            if path == o.BASE / 'manifest.json':
                reads[0] += 1
                if reads[0] > 1:
                    value['changed'] = True
            return value
        self.boundaries['read'].side_effect = changed
        with self.assertRaisesRegex(o.OwnerRefusal, 'launch_source_changed'):
            o.supervise()
        self.boundaries['write'].assert_not_called()
        self.boundaries['run'].assert_not_called()
        self.assert_unconsumed(previous, before)

    def test_source_preflight_drift_under_lease_refuses_before_body(self):
        previous, before, _ = self.fixture()
        self.boundaries['source_preflight'].side_effect = [None, o.OwnerRefusal('reviewed_file_changed')]
        with self.assertRaisesRegex(o.OwnerRefusal, 'reviewed_file_changed'):
            o.supervise()
        self.boundaries['write'].assert_not_called()
        self.boundaries['run'].assert_not_called()
        self.assert_unconsumed(previous, before)

    def test_acquired_body_lease_busy_never_reenters(self):
        previous, before, _ = self.fixture()
        self.boundaries['source_preflight'].side_effect = [None, LeaseBusy()]
        with self.assertRaises(LeaseBusy):
            o.supervise()
        self.h.acquire_lease.assert_called_once_with(blocking=False)
        self.boundaries['source_preflight'].assert_called()
        self.assertEqual(self.boundaries['source_preflight'].call_count, 2)
        self.boundaries['write'].assert_not_called()
        self.assert_unconsumed(previous, before)

    def test_uncontended_start_borrows_real_lease_through_strict_hardware_guard(self):
        previous, before, _ = self.fixture()
        self.store.state['validated'][o.GPU]['observed_at'] = self.stamp()
        with self.assertRaises(BeforeOwnership):
            o.supervise()
        self.h.acquire_lease.assert_called_once_with(blocking=False)
        self.boundaries['timeout_physical'].assert_called_once()
        self.boundaries['write'].assert_called_once()
        self.assert_unconsumed(previous, before)

    def test_initially_absent_lock_is_created_by_canonical_acquire_once(self):
        previous, before, _ = self.fixture(initialize_lock=False)
        self.assertFalse(o.LEASE_PATH.exists())
        self.store.state['validated'][o.GPU]['observed_at'] = self.stamp()
        with self.assertRaises(BeforeOwnership):
            o.supervise()
        self.assertTrue(o.LEASE_PATH.is_file())
        self.h.acquire_lease.assert_called_once_with(blocking=False)
        self.boundaries['timeout_physical'].assert_called_once()
        self.boundaries['write'].assert_called_once()
        self.assert_unconsumed(previous, before)

    def test_stop_timeout_start_cannot_refresh_stale_proof_with_its_new_sample(self):
        previous, before, _ = self.fixture()
        with self.assertRaisesRegex(o.OwnerRefusal, 'owned_gpu_latch_unproven'):
            o.supervise()
        self.h.acquire_lease.assert_called_once_with(blocking=False)
        self.boundaries['timeout_physical'].assert_called_once()
        self.boundaries['write'].assert_not_called()
        self.assert_unconsumed(previous, before)
