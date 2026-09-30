"""Focused local flock and final-proxy-disposition tests; no host contacts."""
import contextlib
import copy
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from common import lifecycle_lease as canonical
spec = importlib.util.spec_from_file_location('owner_settlement_test', ROOT / 'scripts/runtime/mimo/owner.py')
o = importlib.util.module_from_spec(spec)
spec.loader.exec_module(o)


class CanonicalSettlementTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.uid = os.getuid()
        self.acquire = lambda **kw: canonical.acquire_lease(system_root=self.root, trusted_uid=self.uid, **kw)
        with self.acquire(blocking=False):
            pass
        self.path = self.root / 'run/llmctl/lifecycle.lock'
        self.h = SimpleNamespace(acquire_lease=self.acquire, LeaseBusy=canonical.LeaseBusy)
        self.addCleanup(patch.stopall)
        patch.object(o, 'LEASE_PATH', self.path).start()

    def test_real_flock_wait_succeeds_on_same_inode(self):
        acquired, release = threading.Event(), threading.Event()
        def holder():
            with self.acquire(blocking=False):
                acquired.set()
                release.wait(1)
        worker = threading.Thread(target=holder)
        worker.start();self.assertTrue(acquired.wait(1))
        timer = threading.Timer(.03, release.set)
        timer.start()
        before = self.path.stat().st_ino
        try:
            with o.settlement_lease(self.h, deadline=time.monotonic()+.8) as lease:
                lease.validate()
                self.assertEqual(self.path.stat().st_ino, before)
        finally:
            release.set();timer.join();worker.join(1)
        self.assertFalse(worker.is_alive())

    def test_real_flock_contention_stops_at_deadline_without_mutation(self):
        before = self.path.stat().st_ino
        with self.acquire(blocking=False):
            started = time.monotonic()
            with self.assertRaisesRegex(o.OwnerRefusal, 'settlement_lease_deadline'):
                with o.settlement_lease(self.h, deadline=started+.03):
                    self.fail('contended lease admitted')
        self.assertLess(time.monotonic()-started,.2)
        self.assertEqual(self.path.stat().st_ino,before)

    def test_inode_replacement_between_attempts_refuses(self):
        # Deliberate fixture corruption only; production never renames/deletes a lock.
        original_sleep = time.sleep
        def replace(_):
            self.path.rename(self.path.with_suffix('.old'))
            self.path.touch(mode=0o600)
            original_sleep(.001)
        with self.acquire(blocking=False),patch.object(o.time,'sleep',side_effect=replace):
            with self.assertRaisesRegex(o.OwnerRefusal,'settlement_lock_changed'):
                with o.settlement_lease(self.h,deadline=time.monotonic()+.3):
                    self.fail('replacement admitted')

    def test_nested_borrow_uses_existing_scope_validation_and_no_reacquire(self):
        validate = canonical._validate_borrowed_lease
        def scoped(lease):
            return validate(lease,system_root=self.root,trusted_uid=self.uid)
        with self.acquire(blocking=False) as outer,patch.object(canonical,'_validate_borrowed_lease',side_effect=scoped) as check:
            h=SimpleNamespace(acquire_lease=Mock(side_effect=AssertionError('reacquired')))
            with o.settlement_lease(h,lease=outer) as inner:
                self.assertIs(inner,outer)
            self.assertEqual(check.call_count,2)
            h.acquire_lease.assert_not_called()
        with patch.object(canonical,'_validate_borrowed_lease',side_effect=scoped):
            with self.assertRaisesRegex(canonical.LeaseError,'lease_not_active'):
                with o.settlement_lease(h,lease=outer):pass

    def test_untrusted_lock_fails_immediately_without_retry(self):
        self.path.chmod(0o644)
        with patch.object(o.time,'sleep') as sleep:
            with self.assertRaisesRegex(canonical.LeaseError,'untrusted_lock_file'):
                with o.settlement_lease(self.h):pass
            sleep.assert_not_called()


    def test_actual_busy_expiry_preserves_prior_no_proxy_proof_but_not_fresh_success(self):
        proof=dict(pid_released=True,cgroup_empty=True,gpu_compute_empty=True)
        prior=dict(schema_version=2,status='SETTLED',launch_id='same-protected-launch',manifest_sha256=o.digest({}),
                   supervisor={'invocation_id':'same-invocation'},proxy_started=False,
                   request_hold=False,settlement=proof)
        state=copy.deepcopy(prior);writes=[]
        with self.acquire(blocking=False),patch.object(o,'read',side_effect=FileNotFoundError),patch.object(o,'stop_proxy'),patch.object(o,'write',side_effect=lambda h,n,v:writes.append(copy.deepcopy(v))),patch('builtins.print'),patch.object(o,'run') as run:
            with self.assertRaisesRegex(o.OwnerRefusal,'settlement_lease_deadline'):
                o.settle_state(self.h,{},state,deadline=time.monotonic()+.025)
            run.assert_not_called()  # No fresh container/GPU evidence was gathered.
        self.assertEqual(state['status'],'SETTLED');self.assertEqual(state['settlement'],proof)
        self.assertEqual(state['launch_id'],prior['launch_id']);self.assertEqual(state['supervisor'],prior['supervisor'])
        self.assertFalse(state['request_hold'])
        self.assertEqual(state['settlement_recheck_failure']['code'],'settlement_lease_deadline')
        self.assertNotIn('settlement_failure',state);self.assertEqual(writes[-1],state)
        for change in ({'status':'LOADING'},{'request_hold':True},{'proxy_started':True},{'manifest_sha256':'changed-owner-manifest'}):
            state={**copy.deepcopy(prior),**change}
            with self.acquire(blocking=False),patch.object(o,'read',side_effect=FileNotFoundError),patch.object(o,'stop_proxy'),patch.object(o,'write'),patch('builtins.print'):
                with self.assertRaises(o.OwnerRefusal):o.settle_state(self.h,{},state,deadline=time.monotonic()+.005)
            self.assertEqual(state['status'],'HELD');self.assertIsNone(state['settlement'])
            if change.get('request_hold') or change.get('proxy_started'):self.assertTrue(state['request_hold'])
        state=copy.deepcopy(prior)
        with patch.object(o,'read',side_effect=FileNotFoundError),patch.object(o,'stop_proxy'),patch.object(o,'stop_exact',side_effect=o.OwnerRefusal('exact_owned_container_required')),patch.object(o,'write'),patch('builtins.print'):
            with self.assertRaises(o.OwnerRefusal):o.settle_state(self.h,{},state)
        self.assertEqual(state['status'],'HELD');self.assertIsNone(state['settlement'])

    def test_body_busy_is_not_retried(self):
        entered=[]
        with self.assertRaises(canonical.LeaseBusy):
            with o.settlement_lease(self.h):
                entered.append(True)
                raise canonical.LeaseBusy()
        self.assertEqual(entered,[True])


class FinalDispositionTests(unittest.TestCase):
    def fixture(self):
        state=dict(launch_id='a',proxy_started=True,request_hold=False,boot_id='boot',
                   supervisor={'pid':1},native={'container_id':'native'},
                   proxy={'pid':99999999,'pid_start_ticks':'10','parent_pid':1})
        receipt=dict(schema_version=2,launch_id='a',boot_id='boot',native=state['native'],
                     **state['proxy'],active_requests=0,quarantined=False)
        return state,receipt

    def test_admission_between_pre_stop_idle_and_termination_remains_held(self):
        state,receipt=self.fixture();calls=[]
        proxy=SimpleNamespace(pid=state['proxy']['pid'],poll=lambda:0)
        def stopped(_):
            calls.append('stop')
            receipt['active_requests']=1  # begin persisted before SIGTERM, no finish.
        def read(_):
            calls.append('read_final');return copy.deepcopy(receipt)
        with patch.object(o,'BOOT',SimpleNamespace(read_text=lambda:'boot')),patch.object(o,'stop_proxy',side_effect=stopped),patch.object(o,'read',side_effect=read),patch.object(o,'stop_exact',return_value={}) as physical,patch.object(o,'write'):
            o.settle_state(None,{},state,proxy)
        self.assertTrue(state['request_hold'])
        self.assertEqual(calls,['stop','read_final']);physical.assert_called_once()

    def test_exact_closed_child_terminal_receipt_and_repeat_keep_release(self):
        state,receipt=self.fixture();proxy=SimpleNamespace(pid=state['proxy']['pid'],poll=lambda:0)
        physical=dict(pid_released=True,cgroup_empty=True,gpu_compute_empty=True)
        with patch.object(o,'BOOT',SimpleNamespace(read_text=lambda:'boot')),patch.object(o,'stop_proxy'),patch.object(o,'read',return_value=receipt),patch.object(o,'stop_exact',return_value=physical) as stop,patch.object(o,'write'):
            o.settle_state(None,{},state,proxy)
            self.assertFalse(state['request_hold'])
            o.settle_state(None,{},state)  # ExecStopPost: fresh absence + receipt + native proof.
            self.assertEqual(stop.call_count,2)
        self.assertEqual(state['status'],'SETTLED');self.assertFalse(state['request_hold'])

    def test_wrong_or_malformed_final_receipts_and_unproven_child_remain_held(self):
        for change in ({'launch_id':'old'},{'pid_start_ticks':'other'},{'boot_id':'old'},
                       {'active_requests':False},{'quarantined':None},{'native':{}},
                       {'parent_pid':2},{'schema_version':1}):
            state,receipt=self.fixture();receipt.update(change)
            with self.subTest(change=change),patch.object(o,'BOOT',SimpleNamespace(read_text=lambda:'boot')),patch.object(o,'read',return_value=receipt):
                self.assertFalse(o.proxy_released(state,SimpleNamespace(pid=state['proxy']['pid'],poll=lambda:0)))
        state,receipt=self.fixture()
        with patch.object(o,'read',return_value=receipt) as read,patch.object(o,'BOOT',SimpleNamespace(read_text=lambda:'boot')):
            self.assertFalse(o.proxy_released(state,SimpleNamespace(pid=state['proxy']['pid'],poll=lambda:None)))
            read.assert_not_called()  # Child must be closed before even reading final receipt.

    def test_repeated_no_proxy_settlement_reproves_physical_state(self):
        state=dict(status='SETTLED',launch_id='a',proxy_started=False,request_hold=False,
                   settlement=dict(pid_released=True,cgroup_empty=True,gpu_compute_empty=True))
        with patch.object(o,'read',side_effect=FileNotFoundError),patch.object(o,'stop_proxy'),patch.object(o,'stop_exact',return_value=copy.deepcopy(state['settlement'])) as physical,patch.object(o,'write'):
            o.settle_state(None,{},state);o.settle_state(None,{},state)
            self.assertEqual(physical.call_count,2)
        self.assertEqual(state['status'],'SETTLED');self.assertFalse(state['request_hold'])
        with patch.object(o,'read',side_effect=FileNotFoundError),patch.object(o,'stop_proxy'),patch.object(o,'stop_exact',side_effect=o.OwnerRefusal('settlement_lease_deadline')),patch.object(o,'write'),patch('builtins.print'):
            with self.assertRaises(o.OwnerRefusal):o.settle_state(None,{},state)
        self.assertFalse(state['request_hold'])  # Physical uncertainty never fabricates request ambiguity.
        self.assertIsNone(state['settlement'])  # No stale physical proof authorizes rollback.

if __name__=='__main__':unittest.main()
