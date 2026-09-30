"""Deterministic command/deadline fixtures. No wall-clock sleeps or Docker."""
import contextlib
import copy
import importlib.util
from pathlib import Path
import subprocess
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

spec=importlib.util.spec_from_file_location('stop_deadline_owner',Path(__file__).resolve().parents[1]/'scripts/runtime/mimo/owner.py')
o=importlib.util.module_from_spec(spec);spec.loader.exec_module(o)


class StopDeadlineTests(unittest.TestCase):
    def fixture(self, *, duration=11.6, contention=0, deadline=None, running=True):
        now=[100.0];calls=[];held=[False]
        before={'Id':'c'*64,'State':{'Running':running,'Pid':0}}
        after={'Id':'c'*64,'State':{'Running':False,'Pid':0}}
        h=SimpleNamespace(s=SimpleNamespace(root_payload_guard=Mock()),
                          MountedStorageGuard=lambda _:contextlib.nullcontext())
        @contextlib.contextmanager
        def lease(*a,**kw):
            now[0]+=contention
            if now[0]>=kw['deadline']:raise o.OwnerRefusal('settlement_lease_deadline')
            held[0]=True
            try:yield None
            finally:held[0]=False
        def run(argv,timeout):
            self.assertTrue(held[0]);calls.append((copy.deepcopy(argv),timeout))
            if argv[:2]==['docker','ps']:return 'c'*64
            if argv[:2]==['docker','stop']:
                now[0]+=min(timeout,duration)
                if duration>timeout:raise subprocess.TimeoutExpired(argv,timeout)
            return ''
        stack=contextlib.ExitStack();self.addCleanup(stack.close)
        for name,value in [('settlement_lease',lease),('storage_paths',Mock()),('run',run),
                           ('inspect',Mock(side_effect=[before,after])),('exact_container',lambda c,*a,**k:c)]:
            stack.enter_context(patch.object(o,name,value))
        stack.enter_context(patch.object(o.time,'monotonic',side_effect=lambda:now[0]))
        return lambda:o.stop_exact(h,{'container_name':'exact'}, {},deadline=deadline),calls,held

    def test_retained_release_duration_fits_one_stop_and_no_retry(self):
        invoke,calls,held=self.fixture()
        self.assertEqual(invoke(),{'pid_released':True,'cgroup_empty':True,'gpu_compute_empty':True})
        stops=[c for c in calls if c[0][:2]==['docker','stop']]
        self.assertEqual(stops,[(['docker','stop','--time','3','c'*64],20)])
        self.assertFalse(held[0])

    def test_client_expiry_remains_command_timeout_and_skips_success_checks(self):
        invoke,calls,held=self.fixture(duration=21)
        with self.assertRaises(subprocess.TimeoutExpired) as caught:invoke()
        self.assertEqual(o.failure(caught.exception,'SETTLING','settlement')['code'],'command_timeout')
        self.assertEqual(sum(a[:2]==['docker','stop'] for a,t in calls),1)
        self.assertFalse(any(a[0]=='nvidia-smi' for a,t in calls));self.assertFalse(held[0])

    def test_contention_and_caller_deadline_clip_the_same_budget(self):
        invoke,calls,_=self.fixture(contention=9,duration=11.6)
        invoke();self.assertEqual(calls[1][1],17)

    def test_short_caller_deadline_is_not_extended(self):
        invoke,calls,_=self.fixture(deadline=110,duration=11.6)
        with self.assertRaises(subprocess.TimeoutExpired):invoke()
        self.assertEqual(calls[1][1],6)
        self.assertEqual(sum(a[:2]==['docker','stop'] for a,t in calls),1)

    def test_expired_deadline_and_stopped_container_never_dispatch_stop(self):
        invoke,calls,_=self.fixture(deadline=100)
        with self.assertRaises(o.OwnerRefusal):invoke()
        self.assertEqual(calls,[])

    def test_already_stopped_does_not_repeat_command(self):
        invoke,calls,_=self.fixture(running=False)
        invoke();self.assertFalse(any(a[:2]==['docker','stop'] for a,t in calls))


if __name__=='__main__':unittest.main()
