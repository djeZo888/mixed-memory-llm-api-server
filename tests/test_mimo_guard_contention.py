"""Narrow real canonical-lease fixtures; no native runtime or VM work."""
import contextlib
import copy
import os
import threading
import time
from unittest.mock import patch
from tests.test_mimo_owner import LatchRefreshTests, o
from common.lifecycle_lease import LeaseBusy


class GuardContentionTests(LatchRefreshTests):
    def setUp(self):
        super().setUp()
        self.lock_path = self.root / 'run/llmctl/lifecycle.lock'
        with self.h.acquire_lease(blocking=False):
            pass
        p = patch.object(o, 'LEASE_PATH', self.lock_path)
        p.start(); self.addCleanup(p.stop)

    def holder(self, seconds):
        entered = threading.Event()
        def hold():
            with self.h.acquire_lease(blocking=False):
                entered.set()
                time.sleep(seconds)
        thread = threading.Thread(target=hold)
        thread.start(); self.addCleanup(thread.join)
        self.assertTrue(entered.wait(1))
        return thread

    def test_transient_contention_refreshes_under_same_canonical_inode(self):
        before = self.lock_path.stat().st_ino
        self.holder(.10)
        with patch.object(o, 'run', side_effect=AssertionError('no new sample')):
            result = o.latch(self.h, self.boot, evidence=self.evidence, deadline=time.monotonic()+.6)
        self.assertFalse(result['hardware_latched'])
        self.assertGreaterEqual(result['owner_refresh']['lease_contentions'], 1)
        self.assertEqual(self.lock_path.stat().st_ino, before)
        self.assertEqual(self.store.writes, 1)

    def test_continuous_contention_expires_original_cycle_without_write(self):
        before = copy.deepcopy(self.store.state)
        self.holder(.2)
        start = time.monotonic()
        with self.assertRaises(o.MandatoryGuardTimeout):
            o.latch(self.h, self.boot, evidence=self.evidence, deadline=start+.08)
        self.assertLess(time.monotonic()-start, .18)
        self.assertEqual(self.store.state, before)
        self.assertEqual(self.store.writes, 0)

    def test_positive_latch_missing_identity_and_stale_sample_never_wait(self):
        from control import hardware_latch as hl
        from tests.test_hardware_latch import inventory
        for case in ('positive','identity','stale','boot'):
            with self.subTest(case=case):
                original = copy.deepcopy(self.store.state)
                evidence = dict(self.evidence)
                if case == 'positive':
                    self.store.state['validated'] = {}
                    latch = hl.HardwareLatch(self.store.state)
                    for sec in (0,5): latch.observe(o.GPU, inventory(sec,uuids=[]), current_boot_id=self.boot,boot_age_seconds=100)
                    self.store.state = latch.export_state()
                if case == 'identity': self.store.state['validated'] = {}
                if case == 'stale': evidence['observed_at'] = self.stamp(-30)
                if case == 'boot': evidence['boot_id'] = '0'*36
                with patch.object(self.h, 'acquire_lease', side_effect=AssertionError('must fail before lock')):
                    with self.assertRaises(o.OwnerRefusal):
                        o.latch(self.h,self.boot,evidence=evidence,deadline=time.monotonic()+.2)
                self.assertEqual(self.store.writes,0)
                self.store.state = original

    def test_canonical_inode_replacement_during_contention_fails_closed(self):
        original = self.h.acquire_lease
        attempts = 0
        @contextlib.contextmanager
        def replaced(**kw):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                os.rename(self.lock_path, self.lock_path.with_suffix('.preserved'))
                with original(blocking=False): pass
                raise LeaseBusy()
            with original(**kw) as lease: yield lease
        with patch.object(self.h,'acquire_lease',replaced):
            with self.assertRaisesRegex(o.OwnerRefusal,'guard_lock_changed'):
                o.latch(self.h,self.boot,evidence=self.evidence,deadline=time.monotonic()+.3)
        self.assertEqual(self.store.writes,0)

    def test_fault_appearing_during_contention_is_not_cleared(self):
        from control.hardware_latch import HardwareLatch
        from tests.test_hardware_latch import inventory
        @contextlib.contextmanager
        def fault(**kw):
            self.store.state['validated'] = {}
            latch = HardwareLatch(self.store.state)
            for sec in (0,5): latch.observe(o.GPU,inventory(sec,uuids=[]),current_boot_id=self.boot,boot_age_seconds=100)
            self.store.state = latch.export_state()
            raise LeaseBusy()
            yield
        with patch.object(self.h,'acquire_lease',fault):
            with self.assertRaises(o.OwnerRefusal):
                o.latch(self.h,self.boot,evidence=self.evidence,deadline=time.monotonic()+.3)
        self.assertEqual(self.store.writes,0)
