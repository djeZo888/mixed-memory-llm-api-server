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
        self.sample = dict(memory_policy={'memory.max':'800','memory.swap.max':'0','memory.swap.current':'0'},gpus=[dict(uuid=o.GPU,total_mib=100,free_mib=7,temp_c=69)],host=dict(self.baseline),
            cgroup={'memory.max':'800','memory.current':'790','memory.swap.current':'0','memory.swap.max':'0',
                    'memory.events':{'oom':'0','oom_kill':'0'}})

    def test_swap_limit_classes_and_parent_enforcement(self):
        for raw, kind in [('0', 'zero'), ('max', 'max'), ('', 'empty'), ('oops', 'invalid'),
                          ('1', 'finite'), ('-1', 'invalid'), ('1' * 33, 'invalid')]:
            self.assertEqual(o.limit_value(raw)['class'], kind)
            sample = copy.deepcopy(self.sample)
            sample['cgroup']['memory.swap.max'] = raw
            if raw in ('0', 'max'):
                o.validate_sample(self.m, sample, self.baseline, 85)
            else:
                with self.assertRaisesRegex(o.OwnerRefusal, 'native_memory_oom_or_swap'):
                    o.validate_sample(self.m, sample, self.baseline, 85)
        for key, value in [('memory.swap.max', 'max'), ('memory.swap.current', '1'), ('memory.max', 'max')]:
            sample = copy.deepcopy(self.sample)
            sample['memory_policy'][key] = value
            with self.assertRaisesRegex(o.OwnerRefusal, 'native_memory_oom_or_swap'):
                o.validate_sample(self.m, sample, self.baseline, 85)
        sample = copy.deepcopy(self.sample)
        del sample['memory_policy']
        with self.assertRaises(o.OwnerRefusal):
            o.validate_sample(self.m, sample, self.baseline, 85)

    def test_parent_limit_refusal_retains_safe_diagnostics(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            parent = Path(td)
            (parent / 'cgroup.procs').write_text('')
            values = {'memory.max': '800', 'memory.swap.max': '0', 'memory.swap.current': '0'}
            unit = b'[Unit]\nDescription=MiMo dedicated zero-swap boundary\n[Slice]\nMemoryAccounting=yes\nMemoryMax=800\nMemorySwapMax=0\n'
            for field in ('memory.max', 'memory.swap.max', 'memory.swap.current'):
                for raw, kind in [('max', 'max'), ('', 'empty'), ('19', 'finite'), ('PRIVATE_INVALID', 'invalid')]:
                    for name, value in {**values, field: raw}.items():
                        (parent / name).write_text(value)
                    with patch.object(o, 'MEMORY_SLICE_PATH', parent), patch.object(o, 'protected', return_value=unit):
                        with self.assertRaises(o.OwnerRefusal) as caught:
                            o.memory_policy(self.m)
                    receipt = o.failure(caught.exception, 'RUNNING', 'cgroup_memory')
                    self.assertEqual(receipt['code'], 'native_memory_policy_changed')
                    detail = receipt['resource_memory']['memory_policy'][field]
                    self.assertEqual(detail['class'], kind)
                    if kind == 'invalid':
                        self.assertEqual(detail, {'class': 'invalid'})
                        self.assertNotIn(raw, json.dumps(receipt))
                    else:
                        self.assertEqual(detail['raw'], raw)

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
                                 ('host','SwapTotal',101),('cgroup','memory.swap.current','1'),
                                 ('cgroup','memory.swap.max','1'),('cgroup','memory.max','704'),
                                 ('events','oom','1'),('events','oom_kill','1')]:
            sample=copy.deepcopy(self.sample)
            mapping={'gpu':sample['gpus'][0],'host':sample['host'],'cgroup':sample['cgroup'],'events':sample['cgroup']['memory.events']}
            mapping[target][key]=value
            with self.assertRaises(RuntimeError,msg=(target,key)):
                o.validate_sample(self.m,sample,self.baseline,85)

    def test_background_host_swap_is_diagnostic_with_zero_owned_swap(self):
        self.sample['host']['SwapFree'] = 90
        o.validate_sample(self.m, self.sample, self.baseline, 85)
        self.assertEqual(self.sample['host_swap_diagnostic'],
                         {'baseline_used_bytes': 0, 'used_bytes': 10, 'delta_bytes': 10})
        for target, key, value, code in (
                ('cgroup', 'memory.swap.current', '1', 'native_memory_oom_or_swap'),
                ('cgroup', 'memory.swap.max', '1', 'native_memory_oom_or_swap'),
                ('host', 'MemAvailable', 149, 'host_reserve'),
                ('host', 'SwapTotal', 101, 'host_swap_configuration_changed')):
            sample = copy.deepcopy(self.sample)
            sample[target][key] = value
            with self.assertRaisesRegex(o.OwnerRefusal, code):
                o.validate_sample(self.m, sample, self.baseline, 85)

    def test_failing_numeric_sample_survives_in_failure_receipt(self):
        host = {**self.baseline, 'MemAvailable': 149, 'SwapFree': 90}
        with patch.object(o, 'run', return_value=o.GPU + ', 100, 7, 69'), \
                patch.object(o, 'memory', return_value=host):
            with self.assertRaises(o.OwnerRefusal) as caught:
                o.sample_guard(self.m, self.baseline, 85)
        receipt = o.failure(caught.exception, 'LOADING', 'resource_validate')
        self.assertEqual(receipt['code'], 'host_reserve')
        self.assertEqual(receipt['resource_memory'],
                         {'host': host, 'baseline': self.baseline, 'cgroup': None})

    def test_unexpected_validation_retains_safe_metadata_and_fails_closed(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            cg = Path(td) / 'docker-fixture.scope'
            cg.mkdir()
            for name, value in self.sample['cgroup'].items():
                (cg / name).write_text('\n'.join(k + ' ' + v for k, v in value.items())
                                      if isinstance(value, dict) else value)
            for kind in (KeyError, ValueError, RuntimeError):
                original = kind('PRIVATE_EXCEPTION_MESSAGE')
                with self.subTest(kind=kind.__name__), \
                        patch.object(o, 'run', return_value=o.GPU + ', 100, 7, 69'), \
                        patch.object(o, 'memory', return_value=dict(self.baseline)), \
                        patch.object(o, 'cgpath', return_value=cg), \
                        patch.object(o, 'MEMORY_SLICE_PATH', cg.parent), \
                        patch.object(o, 'memory_policy', return_value=self.sample['memory_policy']), \
                        patch.object(o, 'validate_sample', side_effect=original):
                    try:
                        o.sample_guard(self.m, self.baseline, 85, {'pid': 123, 'container_id': 'fixture'})
                    except Exception as caught:
                        self.assertIs(caught, original)
                        receipt = o.failure(caught, 'RUNNING', 'resource_validate')
                    else:
                        self.fail('validation exception must fail closed')
                self.assertEqual(receipt['code'], 'unexpected_error')
                self.assertEqual(receipt['exception_class'], kind.__name__)
                self.assertIsInstance(receipt['owner_source_line'], int)
                self.assertIn('validate_sample(m, sample, baseline, limit)',
                              PATH.read_text().splitlines()[receipt['owner_source_line'] - 1])
                self.assertEqual(receipt['resource_memory'],
                                 {'host': self.baseline, 'baseline': self.baseline,
                                  'cgroup': {**self.sample['cgroup'], 'limit_classification': {
                                      'memory.max': {'class': 'finite', 'raw': '800'},
                                      'memory.swap.max': {'class': 'zero', 'raw': '0'}}}})
                self.assertNotIn('PRIVATE_EXCEPTION_MESSAGE', json.dumps(receipt))

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
        helper=SimpleNamespace(acquire_lease=lambda **_:contextlib.nullcontext('held-lease-fixture'),
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
                startup_lease=lambda h, boot: h.acquire_lease(blocking=False),
                read=Mock(side_effect=read),require_selected=Mock(return_value=selected),
                unit_identity=Mock(return_value={'pid':1,'invocation_id':'fixture'}),
                BOOT=SimpleNamespace(read_text=lambda:'fixture-boot'),storage_paths=Mock(),
                memory=Mock(return_value={**self.baseline,'MemAvailable':1000}),
                temperature_limit=Mock(return_value=85),run=Mock(side_effect=run),
                memory_policy=Mock(return_value={}),
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

    def test_launch_borrows_held_lease_and_passes_same_boot_sample(self):
        self.sample['hardware_validation'] = {'observation_id': 'fresh-fixture'}
        _, _, _, mocks, _ = self._supervise_loading_fixture(ConnectionError('loading'))
        call = mocks['latch'].call_args_list[0]
        self.assertEqual(call.kwargs['lease'], 'held-lease-fixture')
        self.assertIs(call.kwargs['evidence'], self.sample['hardware_validation'])
        self.assertEqual(mocks['sample_guard'].call_args_list[0].kwargs['proof_boot'], 'fixture-boot')
        self.assertIsInstance(call.kwargs['deadline'], float)

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

class LatchRefreshTests(unittest.TestCase):
    """Real existing policy/latch semantics and canonical lease; no VM I/O."""
    def setUp(self):
        import datetime, os, tempfile
        from common.lifecycle_lease import acquire_lease
        from lifecycle import hardware_policy as hp
        from tests.test_hardware_latch import MemoryProtectedStore, BOOT
        self.boot = BOOT
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.store = MemoryProtectedStore()
        self.stamp = lambda seconds=0: datetime.datetime.fromtimestamp(time.time()+seconds, datetime.timezone.utc).isoformat()
        self.store.state['validated'] = {o.GPU: {'boot_id': BOOT, 'observed_at': self.stamp(-20), 'observation_id': 'a'*32}}
        self.evidence = dict(gpu_uuid=o.GPU, boot_id=BOOT, observed_at=self.stamp(), observation_id='b'*32)
        self.h = SimpleNamespace(acquire_lease=lambda **kw: acquire_lease(system_root=self.root, trusted_uid=os.geteuid(), **kw))
        policy = hp.HardwarePolicy
        patches = [patch.object(o, 'BOOT', SimpleNamespace(read_text=lambda:BOOT)),
            patch.object(hp, 'RegisteredLatchStore', side_effect=lambda *a, **kw:self.store),
            patch.object(hp, 'HardwarePolicy', side_effect=lambda store, lease:policy(store, lease=lease,
                system_root=self.root, trusted_uid=os.geteuid(), boot=lambda:dict(boot_id=BOOT,uptime_seconds=100))),
            patch('lifecycle.storage_binding.RegisteredStorageBinding.read_registered', return_value=object())]
        for item in patches: item.start(); self.addCleanup(item.stop)

    def test_stale_proof_refresh_uses_existing_policy_and_real_lease(self):
        with patch.object(o, 'run', side_effect=AssertionError('no extra GPU query')):
            result = o.latch(self.h, self.boot, evidence=self.evidence)
        self.assertFalse(result['hardware_latched'])
        self.assertTrue(result['owner_refresh']['refresh_attempted'])
        self.assertEqual(self.store.writes, 1)
        self.assertEqual(self.store.state['validated'][o.GPU]['observed_at'], self.evidence['observed_at'])

    def borrowed_scope(self):
        import os
        from common.lifecycle_lease import _validate_borrowed_lease
        return patch('common.lifecycle_lease._validate_borrowed_lease',
            side_effect=lambda lease: _validate_borrowed_lease(lease,
                system_root=self.root, trusted_uid=os.geteuid()))

    def test_borrowed_lease_refresh_never_reacquires_or_releases_parent(self):
        with self.h.acquire_lease(blocking=False) as lease, self.borrowed_scope():
            with patch.object(self.h, 'acquire_lease', side_effect=AssertionError('nested acquisition')), patch.object(o, 'run', side_effect=AssertionError('extra sample')):
                result = o.latch(self.h, self.boot, evidence=self.evidence, lease=lease)
            lease.validate()
        self.assertFalse(result['hardware_latched'])
        self.assertEqual(self.store.writes, 1)
        self.assertEqual(self.store.state['validated'][o.GPU]['observation_id'], self.evidence['observation_id'])

    def test_invalid_expired_or_wrong_scope_borrow_refused_even_with_fresh_proof(self):
        from common.lifecycle_lease import LeaseError
        self.store.state['validated'][o.GPU]['observed_at'] = self.stamp()
        with self.h.acquire_lease(blocking=False) as lease:
            # A valid capability for the fixture is not a production-root lease.
            with self.assertRaisesRegex(LeaseError, 'borrowed_lease_scope_mismatch'):
                o.latch(self.h, self.boot, lease=lease)
        for bad in (lease, object()):
            with self.borrowed_scope(), self.assertRaises(LeaseError):
                o.latch(self.h, self.boot, lease=bad)
        self.assertEqual(self.store.writes, 0)

    def test_borrowed_lease_requires_fresh_same_boot_evidence(self):
        before = copy.deepcopy(self.store.state)
        with self.h.acquire_lease(blocking=False) as lease, self.borrowed_scope():
            for evidence in (None, {**self.evidence, 'observed_at': self.stamp(-30)},
                             {**self.evidence, 'boot_id': 'different'}):
                with self.assertRaises(Exception):
                    o.latch(self.h, self.boot, evidence=evidence, lease=lease)
                lease.validate()
        self.assertEqual(self.store.state, before)
        self.assertEqual(self.store.writes, 0)

    def test_fresh_proof_never_acquires_lease(self):
        self.store.state['validated'][o.GPU]['observed_at'] = self.stamp()
        self.h.acquire_lease = Mock(side_effect=AssertionError('unexpected lease'))
        self.assertFalse(o.latch(self.h, self.boot)['hardware_latched'])
        self.assertEqual(self.store.writes, 0)

    def test_producer_refresh_before_lease_entry_succeeds_without_validation_write(self):
        original=self.h.acquire_lease
        @contextlib.contextmanager
        def refreshed(**kwargs):
            with original(**kwargs) as lease:
                self.store.state['validated'][o.GPU]['observed_at']=self.stamp()
                yield lease
        self.h.acquire_lease=refreshed
        result=o.latch(self.h,self.boot,evidence=self.evidence)
        self.assertFalse(result['hardware_latched'])
        self.assertEqual(self.store.writes,0)

    def test_positive_latch_cannot_refresh(self):
        from control.hardware_latch import HardwareLatch
        from tests.test_hardware_latch import inventory
        self.store.state['validated'] = {}
        latch = HardwareLatch(self.store.state)
        for second in (0,5): latch.observe(o.GPU, inventory(second, uuids=[]), current_boot_id=self.boot, boot_age_seconds=100)
        self.store.state = latch.export_state(); before = copy.deepcopy(self.store.state)
        with self.assertRaises(o.OwnerRefusal): o.latch(self.h,self.boot,evidence=self.evidence)
        self.assertEqual(self.store.state,before); self.assertEqual(self.store.writes,0)

    def test_missing_corrupt_storage_stale_sample_other_boot_and_busy_fail_closed(self):
        from common.lifecycle_lease import LeaseBusy
        cases = ['missing','corrupt','write_failure','stale_sample','other_boot','busy','deadline']
        for case in cases:
            with self.subTest(case=case):
                before = copy.deepcopy(self.store.state); evidence = dict(self.evidence)
                with contextlib.ExitStack() as stack:
                    if case=='missing': self.store.state['validated']={}
                    if case=='corrupt': self.store.state={'schema_version':99}
                    if case=='write_failure': self.store.fail=True
                    if case=='stale_sample': evidence['observed_at']=self.stamp(-30)
                    if case=='other_boot': evidence['boot_id']='00000000-0000-0000-0000-000000000000'
                    if case in ('busy','deadline'):
                        error = LeaseBusy() if case=='busy' else o.MandatoryGuardTimeout('mandatory_guard_timeout')
                        stack.enter_context(patch.object(self.h,'acquire_lease',side_effect=error))
                    with self.assertRaises(Exception) as caught: o.latch(self.h,self.boot,evidence=evidence)
                    receipt=o.failure(caught.exception,'RUNNING','hardware_latch')
                    self.assertIn('hardware_evidence',receipt)
                    self.assertNotIn('private storage detail',json.dumps(receipt))
                    self.assertEqual(self.store.writes,0)
                self.store.state=before; self.store.fail=False

    def test_strict_owner_storage_failure_preserves_passive_unknown_contract(self):
        from lifecycle.hardware_policy import read_latch_status
        with patch.object(self.store,'read',side_effect=OSError('private read detail')):
            self.assertIsNone(read_latch_status(object(),[o.GPU],current_boot_id=self.boot)['hardware_latched'])
            with self.assertRaises(OSError) as caught: o.latch(self.h,self.boot,evidence=self.evidence)
        receipt=o.failure(caught.exception,'RUNNING','hardware_latch')
        self.assertFalse(receipt['hardware_evidence']['refresh_attempted'])
        self.assertNotIn('private read detail',json.dumps(receipt))
        self.assertEqual(self.store.writes,0)

    def test_outer_alarm_cannot_allow_refresh_after_deadline(self):
        # The passive projection swallows read exceptions; elapsed total remains fatal.
        def delayed_read():
            time.sleep(.04)
            return copy.deepcopy(self.store.state)
        with patch.object(self.store, 'read', side_effect=delayed_read), o.bounded(.01):
            with self.assertRaises(o.MandatoryGuardTimeout):
                o.latch(self.h,self.boot,evidence=self.evidence,deadline=time.monotonic()+.01)
        self.assertEqual(self.store.writes,0)

    def test_sample_proof_brackets_boot_and_preserves_probe_capture_time(self):
        baseline=dict(MemTotal=1000,MemAvailable=900,SwapTotal=100,SwapFree=100)
        with patch.object(o,'run',return_value=o.GPU+', 100, 8, 40'), patch.object(o,'memory',return_value=baseline):
            result=o.sample_guard({'memory':{'limit_bytes':800}},baseline,85,proof_boot=self.boot)
            self.assertEqual(result['hardware_validation']['boot_id'],self.boot)
            with patch.object(o,'BOOT',SimpleNamespace(read_text=Mock(side_effect=[self.boot,'changed']))):
                with self.assertRaisesRegex(o.OwnerRefusal,'boot_changed'):
                    o.sample_guard({'memory':{'limit_bytes':800}},baseline,85,proof_boot=self.boot)

if __name__ == '__main__':unittest.main()
