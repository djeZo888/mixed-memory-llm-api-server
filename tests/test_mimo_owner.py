"""Offline fixtures only. No Docker, HTTP, GPU or live storage contacts."""
import contextlib
import copy
import importlib.util
import hashlib
import json
from pathlib import Path
import sys
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch, Mock

PATH = Path(__file__).resolve().parents[1] / 'scripts/runtime/mimo/owner.py'
spec = importlib.util.spec_from_file_location('mimo_owner_test', PATH)
o = importlib.util.module_from_spec(spec)
spec.loader.exec_module(o)


class OwnerTests(unittest.TestCase):
    def setUp(self):
        self.m = {'memory': {'limit_bytes':800}, 'native_argv':['--load-mode','none'], 'container_name':'llm-frontier-mimo-production'}
        self.baseline = dict(MemTotal=1000,MemAvailable=900,SwapTotal=100,SwapFree=100)
        self.sample = dict(gpus=[dict(uuid=o.GPU,total_mib=100,free_mib=7,temp_c=69)],host=dict(self.baseline),
            cgroup={'memory.max':'800','memory.current':'790','memory.swap.current':'0','memory.swap.max':'0',
                    'memory.events':{'oom':'0','oom_kill':'0'}})

    def test_only_owned_gpu_is_required(self):
        o.validate_sample(self.m,self.sample,self.baseline,85)
        self.sample['gpus'].append(dict(uuid='unrelated',total_mib=1,free_mib=0,temp_c=100))
        o.validate_sample(self.m,self.sample,self.baseline,85)
        self.sample['gpus'] = self.sample['gpus'][1:]
        with self.assertRaisesRegex(RuntimeError,'owned_gpu_missing'):
            o.validate_sample(self.m,self.sample,self.baseline,85)

    def test_creation_pins_spin_policy_without_changing_native_configuration(self):
        native = json.loads(PATH.with_name('launch.json').read_text())['native_argv'] + ['--no-host']
        manifest = {**self.m, 'native_argv': native,
                    'source_sha256': {str(o.BASE / 'source/owner.py'): hashlib.sha256(PATH.read_bytes()).hexdigest()}}
        with patch.object(o, 'launch_args', return_value=native):
            argv = o.create_argv(SimpleNamespace(MODEL='/fixture/models'), manifest, 'fixture-launch')
        values = lambda flag: [argv[i + 1] for i, value in enumerate(argv[:-1]) if value == flag]
        self.assertEqual(values('--env'), ['CUDA_CACHE_DISABLE=1', 'OMP_NUM_THREADS=1', 'GOMP_SPINCOUNT=0'])
        self.assertEqual(values('--cpuset-cpus'), ['0-7,16-71'])
        self.assertEqual(values('--cpuset-mems'), ['0-7'])
        self.assertEqual(values('--gpus'), ['device=' + o.GPU])
        self.assertEqual(argv[argv.index(o.IMAGE) + 1:], ['--interleave=0-7', '/opt/llama/llama-server'] + native)
        self.assertEqual(values('--memory'), values('--memory-swap'))
        self.assertEqual(values('--restart'), ['no'])
        self.assertIn('io.h016.manifest=' + o.digest(manifest), values('--label'))
        changed = copy.deepcopy(manifest)
        changed['source_sha256'][str(o.BASE / 'source/owner.py')] = '0' * 64
        self.assertNotEqual(o.digest(changed), o.digest(manifest))
        container = {'Config': {'Labels': {'io.h016.owner': o.OWNER,
                     'io.h016.manifest': o.digest(manifest), 'io.h016.launch': 'fixture-launch'}},
                     'Name': '/' + manifest['container_name'], 'Image': o.IMAGE}
        self.assertIs(o.exact_container(container, manifest, {'launch_id': 'fixture-launch'}, configuration=False), container)
        with self.assertRaisesRegex(RuntimeError, 'exact_owned_container_required'):
            o.exact_container(container, changed, {'launch_id': 'fixture-launch'}, configuration=False)

    def test_fatal_own_temperature_reserve_host_swap_oom_and_ceiling(self):
        for target,key,value in [('gpu','temp_c',85),('gpu','free_mib',6.99),('host','MemAvailable',149),
                                 ('host','SwapFree',99),('cgroup','memory.swap.current','1'),
                                 ('cgroup','memory.max','704'),('events','oom_kill','1')]:
            sample=copy.deepcopy(self.sample)
            mapping={'gpu':sample['gpus'][0],'host':sample['host'],'cgroup':sample['cgroup'],'events':sample['cgroup']['memory.events']}
            mapping[target][key]=value
            with self.assertRaises(RuntimeError,msg=(target,key)):
                o.validate_sample(self.m,sample,self.baseline,85)

    def test_mandatory_timeout_not_optional_mapping_wait(self):
        start=time.monotonic()
        with self.assertRaises(o.MandatoryGuardTimeout) as raised:
            with o.bounded(.02):
                time.sleep(.2)
        self.assertIsInstance(raised.exception, TimeoutError)
        self.assertEqual(str(raised.exception), 'mandatory_guard_timeout')
        self.assertLess(time.monotonic()-start,.1)
        source=PATH.read_text()
        self.assertNotIn('numa_maps',source);self.assertNotIn('/smaps',source)
        self.assertNotIn('placement(',source)

    def _supervise_loading_fixture(self, readiness_error, *, sample_error=None, settlement_error=None, receipt_error=None):
        """Run the actual owner loop, mocking every host/network boundary."""
        class LoopObserved(Exception):
            pass
        manifest=copy.deepcopy(self.m)
        selected=dict(selected_frontier=o.MODEL,manifest_sha256=o.digest(manifest),generation=1)
        native=dict(container_id='a'*64,pid=123)
        helper=SimpleNamespace(acquire_lease=lambda **_:contextlib.nullcontext(),
            MountedStorageGuard=lambda _:contextlib.nullcontext(),
            s=SimpleNamespace(root_payload_guard=lambda:None))
        writes=[]
        def read(path):
            if path == o.BASE / 'manifest.json':return manifest
            raise FileNotFoundError(path)
        def run(argv,*_):
            if argv[:2] == ['systemctl','show']:return 'MainPID=0\nActiveState=inactive\n'
            if argv == ['fixture-create']:return 'a'*64
            return ''
        with contextlib.ExitStack() as stack:
            replacements=dict(setup=Mock(return_value=helper),source_preflight=Mock(),
                read=Mock(side_effect=read),require_selected=Mock(return_value=selected),
                unit_identity=Mock(return_value={'pid':1,'invocation_id':'fixture'}),
                BOOT=SimpleNamespace(read_text=lambda:'fixture-boot'),storage_paths=Mock(),
                memory=Mock(return_value={**self.baseline,'MemAvailable':1000}),
                temperature_limit=Mock(return_value=85),run=Mock(side_effect=run),
                sample_guard=Mock(side_effect=[self.sample,sample_error or self.sample]),
                latch=Mock(return_value={'hardware_latched':False}),
                create_argv=Mock(return_value=['fixture-create']),inspect=Mock(return_value={'State':{'Pid':123}}),
                exact_container=Mock(side_effect=lambda c,*_:c),native_identity=Mock(return_value=native),
                cgpath=Mock(return_value=Path('/fixture/cgroup')),read_key=Mock(return_value=b'fixture'),
                native_ready=Mock(side_effect=readiness_error),
                write=Mock(side_effect=lambda h,name,value: (_ for _ in ()).throw(receipt_error)
                    if receipt_error is not None and 'primary_failure' in value
                    else writes.append((name,copy.deepcopy(value)))),
                settle_state=Mock(side_effect=settlement_error))
            for name,value in replacements.items():stack.enter_context(patch.object(o,name,value))
            sleep=stack.enter_context(patch.object(o.time,'sleep',side_effect=LoopObserved('loop reached sleep')))
            with self.assertRaises(Exception) as caught:o.supervise()
        return caught.exception,LoopObserved,writes,replacements,sleep

    def test_loading_readiness_socket_timeout_remains_pending(self):
        error,marker,writes,mocks,sleep=self._supervise_loading_fixture(TimeoutError('socket timed out'))
        self.assertIsInstance(error,marker)
        guards=[value for name,value in writes if name == 'guard.json']
        self.assertEqual(len(guards),1)
        self.assertEqual(guards[0]['status'],'ok')
        self.assertIsNone(guards[0]['proxy'])
        sleep.assert_called_once()
        mocks['settle_state'].assert_called_once()
        self.assertEqual(mocks['settle_state'].call_args.args[2]['status'],'LOADING')

    def test_mandatory_deadline_inside_readiness_is_fatal_and_settles(self):
        deadline=o.MandatoryGuardTimeout('mandatory_guard_timeout')
        error,_,writes,mocks,sleep=self._supervise_loading_fixture(deadline)
        self.assertIs(error,deadline)
        self.assertNotIn('guard.json',[name for name,_ in writes])
        sleep.assert_not_called()
        mocks['settle_state'].assert_called_once()

    def test_guard_timeout_outside_readiness_is_fatal_and_settles(self):
        for deadline in (TimeoutError('nvml timeout'),o.MandatoryGuardTimeout('mandatory_guard_timeout')):
            with self.subTest(error=type(deadline).__name__):
                error,_,writes,mocks,sleep=self._supervise_loading_fixture(None,sample_error=deadline)
                self.assertIs(error,deadline)
                self.assertNotIn('guard.json',[name for name,_ in writes])
                mocks['native_ready'].assert_not_called()
                sleep.assert_not_called()
                mocks['settle_state'].assert_called_once()

    def test_no_double_launch_and_ambiguity_no_replay(self):
        selected=dict(selected_frontier=o.MODEL,manifest_sha256=o.digest(self.m))
        o.assert_launch_admission(self.m,selected,None)
        proof=dict(schema_version=2,status='SETTLED',request_hold=False,
                   settlement=dict(pid_released=True,cgroup_empty=True,gpu_compute_empty=True))
        o.assert_launch_admission(self.m,selected,proof)
        for change in ({'status':'RUNNING'},{'request_hold':True},{'settlement':{'pid_released':True}}):
            with self.assertRaises(RuntimeError):
                o.assert_launch_admission(self.m,selected,{**proof,**change})

    def test_proxy_death_is_fatal(self):
        with self.assertRaisesRegex(RuntimeError,'proxy_child_died'):
            o.proxy_snapshot({},SimpleNamespace(poll=lambda:1))

    def test_settlement_runs_despite_proxy_stop_error(self):
        state=dict(launch_id='a',proxy_started=True)
        with patch.object(o,'read',side_effect=FileNotFoundError),patch.object(o,'stop_proxy',side_effect=TimeoutError),patch.object(o,'stop_exact',return_value={}) as stop,patch.object(o,'write'):
            with self.assertRaises(TimeoutError):
                o.settle_state(None,{},state,Mock())
            stop.assert_called_once()
            self.assertTrue(state['request_hold'])

    def test_clean_finally_settles_native_before_publishing(self):
        state=dict(launch_id='a',proxy_started=False)
        calls=[]
        with patch.object(o,'read',side_effect=FileNotFoundError),patch.object(o,'stop_proxy',side_effect=lambda *_:calls.append('proxy')),patch.object(o,'stop_exact',side_effect=lambda *_:calls.append('native') or {'pid_released':True}),patch.object(o,'write',side_effect=lambda *_:calls.append('write')):
            result=o.settle_state(None,{},state,Mock())
        self.assertEqual(calls,['proxy','native','write']);self.assertEqual(result['status'],'SETTLED')
        self.assertFalse(result['request_hold'])

    def test_selected_generation_change_is_fatal(self):
        m={};selected=dict(schema_version=1,selected_frontier=o.MODEL,generation=1,manifest_sha256=o.digest(m))
        with patch.object(o,'selection',return_value={**selected,'generation':2}):
            with self.assertRaises(RuntimeError):o.require_selected(m,selected)

    def test_manifest_context_and_reviewed_no_host_only(self):
        base=json.loads(PATH.with_name('launch.json').read_text())
        argv=base['native_argv']
        m=dict(context=262144,no_host=True,source_sha256={str(o.BASE / 'source/launch.json'):hashlib.sha256(json.dumps(base).encode()).hexdigest()})
        expected=list(argv)
        for flag in ('--ctx-size','--kv-unified-per-slot'):expected[expected.index(flag)+1]='262144'
        m['native_argv']=expected+['--no-host']
        with patch.object(o,'protected',return_value=json.dumps(base).encode()):
            self.assertEqual(o.launch_args(m),m['native_argv'])
            m['native_argv'].append('--arbitrary')
            with self.assertRaises(RuntimeError):o.launch_args(m)

    def test_reviewed_1m_request_preserved_for_actual_allocator_rounding(self):
        base=json.loads(PATH.with_name('launch.json').read_text())
        for flag in ('--ctx-size','--kv-unified-per-slot'):
            base['native_argv'][base['native_argv'].index(flag)+1]='1000000'
        raw=json.dumps(base).encode()
        for actual in (1000000,1000192):
            m=dict(context=actual,no_host=True,
                   source_sha256={str(o.BASE / 'source/launch.json'):hashlib.sha256(raw).hexdigest()},
                   native_argv=base['native_argv']+['--no-host'])
            with patch.object(o,'protected',return_value=raw):
                self.assertEqual(o.launch_args(m),m['native_argv'])
                self.assertEqual(m['context'],actual)
                m['native_argv'][m['native_argv'].index('--ctx-size')+1]='1000192'
                with self.assertRaisesRegex(RuntimeError,'reviewed_native_argv_changed'):
                    o.launch_args(m)

    def test_reviewed_1m_capacity_rejects_stale_or_mixed_source_request(self):
        for requested in (('131072','131072'),('1000000','1000192'),('1000192','1000000')):
            base=json.loads(PATH.with_name('launch.json').read_text())
            for flag,value in zip(('--ctx-size','--kv-unified-per-slot'),requested):
                base['native_argv'][base['native_argv'].index(flag)+1]=value
            raw=json.dumps(base).encode()
            for actual in (1000000,1000192):
                m=dict(context=actual,no_host=True,
                       source_sha256={str(o.BASE / 'source/launch.json'):hashlib.sha256(raw).hexdigest()},
                       native_argv=base['native_argv']+['--no-host'])
                with patch.object(o,'protected',return_value=raw),self.assertRaisesRegex(RuntimeError,'reviewed_1m_request_required'):
                    o.launch_args(m)

    def test_memory_peak_includes_cache_only_incremental_startup_added(self):
        m=json.loads((PATH.parents[3] / 'reports/h016-production-owner-20260927/REVIEW-MANIFEST.template.json').read_text())
        m.update(qualified=True,no_host=True,native_argv=['--no-host'],qualification_sha256={'fixture':'0'*64})
        m['artifact']['files']=[{} for _ in range(13)]
        m['memory']=dict(limit_bytes=704,qualified_peak_bytes=704,startup_cache_bytes=0)
        o.validate_manifest(m)  # Cgroup peak already contains its charged file cache.
        m['memory']=dict(limit_bytes=704,qualified_peak_bytes=700,startup_cache_bytes=4)
        o.validate_manifest(m)  # Separately justified incremental allowance.
        for budget in (dict(limit_bytes=704,qualified_peak_bytes=704,startup_cache_bytes=-1),
                       dict(limit_bytes=704,qualified_peak_bytes=704,startup_cache_bytes=1),
                       dict(limit_bytes=704,qualified_peak_bytes=700,startup_cache_bytes=5),
                       dict(limit_bytes=704,qualified_peak_bytes=0,startup_cache_bytes=0),
                       dict(limit_bytes=704,qualified_peak_bytes=700,startup_cache_bytes=False)):
            m['memory']=budget
            with self.assertRaisesRegex(RuntimeError,'reviewed_memory_peak_and_cache_required'):
                o.validate_manifest(m)

    def test_explicit_glm_rollback_publishes_valid_selection_before_start(self):
        selected=dict(schema_version=1,selected_frontier=o.MODEL,generation=4)
        state=dict(status='SETTLED',request_hold=False,native={'container_id':'a'},native_cgroup='/fixture/absent',
                   settlement=dict(pid_released=True,cgroup_empty=True,gpu_compute_empty=True))
        h=SimpleNamespace(acquire_lease=lambda **_:contextlib.nullcontext(),MountedStorageGuard=lambda _:contextlib.nullcontext(None),s=SimpleNamespace(root_payload_guard=lambda:None))
        calls=[]
        with patch.object(o,'storage_paths'),patch.object(o,'selection',return_value=selected),patch.object(o,'read',return_value=state),patch.object(o,'inspect',return_value={'State':{'Running':False,'Pid':0}}),patch.object(o,'exact_container',side_effect=lambda c,*_:c),patch.object(o,'run',side_effect=lambda argv,*_:calls.append(argv) or ''),patch.object(o,'write',side_effect=lambda h,n,v:calls.append(v)):
            result=o.rollback_glm(h,{'glm_preserved_sha256':{}},selected)
        self.assertEqual(result,dict(schema_version=1,selected_frontier=o.GLM,generation=5))
        self.assertEqual(calls[-2],result);self.assertEqual(calls[-1],['systemctl','start',o.GLM_UNIT])

    def test_loading_503_is_pending_but_success_identity_mismatch_fatal(self):
        with patch.object(o,'get',side_effect=[(503,{}),(200,[])]):
            self.assertIs(o.native_ready({},b'fixture'),False)
        with patch.object(o,'get',side_effect=[(200,{'model_alias':'wrong'}),(200,[])]):
            with self.assertRaises(RuntimeError):
                o.native_ready({},b'fixture')

    def test_stop_or_nvml_timeout_publishes_held_never_settled(self):
        for error in (TimeoutError('stop'),TimeoutError('nvml')):
            state=dict(launch_id='a',proxy_started=False)
            with patch.object(o,'read',side_effect=FileNotFoundError),patch.object(o,'stop_proxy'),patch.object(o,'stop_exact',side_effect=error),patch.object(o,'write') as write:
                with self.assertRaises(TimeoutError):o.settle_state(None,{},state)
            self.assertEqual(state['status'],'HELD')
            self.assertFalse(state['request_hold']);self.assertIsNone(state['settlement'])
            self.assertEqual(state['settlement_failure']['code'],'timeout')
            self.assertEqual(write.call_args.args[2]['status'],'HELD')


    def test_primary_survives_settlement_and_receipt_double_failure(self):
        primary=o.OwnerRefusal('native_identity_or_capacity_changed')
        for receipt_error in (None, OSError('private-file-detail')):
            with self.subTest(receipt_failure=receipt_error is not None),patch('builtins.print') as journal:
                error,_,writes,mocks,sleep=self._supervise_loading_fixture(primary,
                    settlement_error=TimeoutError('private-cleanup-detail'),receipt_error=receipt_error)
            self.assertIs(error,primary)
            mocks['settle_state'].assert_called_once()
            state=mocks['settle_state'].call_args.args[2]
            self.assertEqual(state['primary_failure']['phase'],'LOADING')
            self.assertEqual(state['primary_failure']['code'],'native_identity_or_capacity_changed')
            self.assertEqual(state['primary_failure']['operation'],'native_readiness')
            self.assertGreaterEqual(state['primary_failure']['cycle_elapsed_s'],0)
            self.assertEqual(state['settlement_failure']['phase'],'SETTLING')
            self.assertEqual(state['settlement_failure']['code'],'timeout')
            if receipt_error is not None:self.assertEqual(state['receipt_failure']['code'],'os_error')
            emitted=' '.join(call.args[0] for call in journal.call_args_list)
            self.assertIn('primary_failure',emitted);self.assertIn('settlement_failure',emitted)
            self.assertNotIn('private-',emitted)
            sleep.assert_not_called()

    def test_physical_failure_does_not_create_request_hold_but_ambiguity_does(self):
        cases=[(False,False,None,False), (False,True,None,True),
               (True,False,None,True), (True,False,{'launch_id':'old'},True),
               (True,False,{'launch_id':'a','active_requests':1,'quarantined':False},True),
               (True,False,{'launch_id':'a','active_requests':0,'quarantined':True},True),
               (False,False,{'launch_id':'a','active_requests':1,'quarantined':False},True)]
        for started,held,receipt,expected in cases:
            with self.subTest(started=started,held=held,receipt=receipt):
                state=dict(launch_id='a',proxy_started=started,request_hold=held)
                with patch.object(o,'read',side_effect=FileNotFoundError if receipt is None else None,return_value=receipt),patch.object(o,'stop_proxy'),patch.object(o,'stop_exact',side_effect=TimeoutError),patch.object(o,'write'),patch('builtins.print'):
                    with self.assertRaises(TimeoutError):o.settle_state(None,{},state)
                self.assertEqual(state['status'],'HELD');self.assertEqual(state['request_hold'],expected)
                with patch.object(o,'read',side_effect=FileNotFoundError),patch.object(o,'stop_proxy'),patch.object(o,'stop_exact',return_value={'pid_released':True,'cgroup_empty':True,'gpu_compute_empty':True}),patch.object(o,'write'):
                    o.settle_state(None,{},state)
                self.assertEqual(state['status'],'SETTLED');self.assertEqual(state['request_hold'],expected)
                self.assertIn('settlement_failure',state)  # Previous fault evidence retained.


    def test_loop_failure_records_specific_operation_and_cycle_elapsed(self):
        def deadline(m,key,*,progress):
            progress('http_slots')
            raise o.MandatoryGuardTimeout('mandatory_guard_timeout')
        with patch('builtins.print'):
            error,_,writes,mocks,sleep=self._supervise_loading_fixture(deadline)
        self.assertIsInstance(error,o.MandatoryGuardTimeout)
        diagnostic=mocks['settle_state'].call_args.args[2]['primary_failure']
        self.assertEqual(diagnostic['operation'],'http_slots')
        self.assertEqual(diagnostic['code'],'mandatory_guard_timeout')
        self.assertGreaterEqual(diagnostic['cycle_elapsed_s'],0)
        sleep.assert_not_called()
        self.assertEqual(o.failure(o.OwnerRefusal('private_token'),'LOADING')['code'],'unexpected_error')

    def test_proxy_creation_failure_cannot_claim_no_proxy_admission(self):
        with patch.object(o.subprocess,'Popen',side_effect=OSError('private-child-detail')),patch('builtins.print'):
            error,_,writes,mocks,sleep=self._supervise_loading_fixture(lambda *a,**kw:True)
        self.assertIsInstance(error,OSError)
        state=mocks['settle_state'].call_args.args[2]
        self.assertTrue(state['proxy_started'])
        starting=[v for n,v in writes if n=='state.json' and v['status']=='STARTING_PROXY']
        self.assertTrue(starting[0]['proxy_started'])
        self.assertEqual(state['primary_failure']['operation'],'proxy_start')

    def test_arbitrary_exception_text_is_never_a_diagnostic(self):
        for exc in (RuntimeError('private-token'),ValueError('private-prompt'),OSError('private-path')):
            self.assertNotIn('private-',json.dumps(o.failure(exc,'LOADING')))

if __name__ == '__main__':unittest.main()
