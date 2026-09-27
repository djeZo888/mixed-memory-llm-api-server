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
        with self.assertRaises(TimeoutError):
            with o.bounded(.02):
                time.sleep(.2)
        self.assertLess(time.monotonic()-start,.1)
        source=PATH.read_text()
        self.assertNotIn('numa_maps',source);self.assertNotIn('/smaps',source)
        self.assertNotIn('placement(',source)

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
        state=dict(launch_id='a',proxy_started=True)
        calls=[]
        with patch.object(o,'read',return_value={'launch_id':'a','active_requests':0,'quarantined':False}),patch.object(o,'stop_proxy',side_effect=lambda *_:calls.append('proxy')),patch.object(o,'stop_exact',side_effect=lambda *_:calls.append('native') or {'pid_released':True}),patch.object(o,'write',side_effect=lambda *_:calls.append('write')):
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
            self.assertTrue(state['request_hold']);self.assertIsNone(state['settlement'])
            self.assertEqual(write.call_args.args[2]['status'],'HELD')

if __name__ == '__main__':unittest.main()
