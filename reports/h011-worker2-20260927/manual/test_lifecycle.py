#!/usr/bin/env python3
"""Offline real owner-method failure tests with subprocess/storage seams mocked."""
import contextlib
import copy
from pathlib import Path
import sys
import types
import unittest
from unittest import mock
sys.path.insert(0,str(Path(__file__).resolve().parent))
import manual as m

class Lifecycle(unittest.TestCase):
    def valid(self):
        return {'status':'TRANSPORT_PASS','semantic_status':'PASS','sse_done':True,'body_drained':True,
                'finish_reason':'stop','usage':{'prompt_tokens':1000000,'completion_tokens':150,'total_tokens':1000150}}

    def test_retention_needs_every_terminal_gate(self):
        value=self.valid();self.assertTrue(m.retainable(value,None,True))
        for key,bad in [('status','PARTIAL_OR_FAIL'),('semantic_status','FAIL_COMPLETED_ANSWER'),
                        ('sse_done',False),('body_drained',False),('finish_reason','length')]:
            self.assertFalse(m.retainable(value|{key:bad},None,True))
        for key,bad in [('prompt_tokens',999999),('completion_tokens',1025),('completion_tokens',0),('total_tokens',1000000)]:
            changed=copy.deepcopy(value);changed['usage'][key]=bad
            self.assertFalse(m.retainable(changed,None,True))
        self.assertFalse(m.retainable(value,'gpu_reserve_below_7pct',True))
        self.assertFalse(m.retainable(value,None,False))

    def ops(self):
        ops=object.__new__(m.Ops)
        ops.transaction=lambda:contextlib.nullcontext((object(),object()))
        ops.validate_candidate=mock.Mock()
        ops.save=mock.Mock()
        return ops

    def test_only_exact_owned_id_stopped_and_confirmation_durable(self):
        ops=self.ops();job={'candidate_id':'exact-owned-id'}
        running={'State':{'Running':True,'Pid':99}}
        stopped={'State':{'Running':False,'Pid':0,'Paused':False,'Restarting':False}}
        with mock.patch.object(m,'inspect',side_effect=[running,stopped]) as inspect, mock.patch.object(m,'run') as run:
            ops.stop_candidate(job)
        run.assert_called_once_with(['docker','stop','--time','30','exact-owned-id'],45)
        self.assertEqual([c.args for c in inspect.call_args_list],[('exact-owned-id',),('exact-owned-id',)])
        self.assertEqual(job['status'],'CANDIDATE_STOP_CONFIRMED')
        self.assertEqual(ops.validate_candidate.call_count,2)
        ops.save.assert_called_once()

    def test_unknown_create_or_changed_identity_never_stopped(self):
        ops=self.ops()
        with mock.patch.object(m,'run',return_value='unexpected-container') as run:
            with self.assertRaisesRegex(ValueError,'unknown_created_candidate'):ops.stop_candidate({'candidate_id':None})
            self.assertFalse(any(c.args[0][1]=='stop' for c in run.call_args_list))
        ops.validate_candidate.side_effect=ValueError('candidate_identity_changed')
        with mock.patch.object(m,'inspect',return_value={}), mock.patch.object(m,'run') as run:
            with self.assertRaisesRegex(ValueError,'candidate_identity_changed'):ops.stop_candidate({'candidate_id':'id'})
            run.assert_not_called()

    def test_running_after_stop_never_authorizes_restore(self):
        ops=self.ops();job={'candidate_id':'id'}
        running={'State':{'Running':True,'Pid':99}}
        with mock.patch.object(m,'inspect',return_value=running),mock.patch.object(m,'run'):
            with self.assertRaisesRegex(ValueError,'candidate_stop_unconfirmed'):ops.stop_candidate(job)
        ops.save.assert_not_called()
        self.assertEqual(m.cleanup_decision(True,True,False),'QUARANTINE')
        self.assertEqual(m.cleanup_decision(True,False,True),'QUARANTINE')
        self.assertEqual(m.cleanup_decision(True,True,True),'RESTORE_ORIGINAL')

    def test_restore_invokes_original_owner_only_after_confirmed_candidate_stop(self):
        ops=self.ops();events=[];before={'container_id':'original','state_sha256':m.sha(b'original-state'),'other_three':{'same':True}}
        ops.stop_candidate=lambda job:events.append('confirmed-stop')
        ops.original=lambda:({}, {}, {'Id':'original'})
        ops.owner=types.SimpleNamespace(operate=lambda action,**kw:events.append(action))
        ops.call=lambda *a,**kw:{'ready':True}
        ops.verify_capacity=lambda port,context:(events.append((port,context)) or {'context':context})
        ops.others=lambda:{'same':True};ops.ecc=lambda:None
        with mock.patch.object(m,'protected',return_value=b'original-state'):
            job={};ops.restore(job,before,m.time.monotonic()+30)
        self.assertEqual(events,['confirmed-stop','resume',(30010,480000)])
        self.assertEqual(job['status'],'FAILED_CANDIDATE_STOPPED_480K_RESTORED')
        ops.stop_candidate=mock.Mock(side_effect=ValueError('unsettled'))
        with mock.patch.object(ops.owner,'operate') as resume:
            with self.assertRaises(ValueError):ops.restore({},before,m.time.monotonic()+30)
            resume.assert_not_called()

    def test_start_refuses_stale_owner_without_systemd_or_mutation(self):
        ops=self.ops()
        with mock.patch.object(m,'Ops',return_value=ops),mock.patch.object(Path,'exists',return_value=True),mock.patch.object(m,'run') as run:
            with self.assertRaisesRegex(ValueError,'duplicate_or_stale_job_no_replay'):m.start(True)
            run.assert_not_called();ops.save.assert_not_called()

    def test_unit_has_no_destructive_execstop_and_source_uses_distinct_candidate(self):
        source=Path(m.__file__).read_text()
        self.assertNotIn("'--property=ExecStop",source)
        self.assertNotIn("['docker','rm'",source)
        self.assertNotIn("['docker','stop','--time','30',self.owner.NAME]",source)
        self.assertEqual(m.NAME,'llm-frontier-flash-h011-manual1m')
        self.assertEqual(m.BUDGET['main'],7200)
        self.assertIn('if success_decided:',source)
        self.assertIn('if not claimed:raise',source)


    def test_exact_candidate_projection_keeps_all_original_containment_gates(self):
        runtime=Path(__file__).resolve().parents[3]/'scripts/runtime/flash'
        owner=m.load_module('offline_h011_owner',runtime/'owner.py')
        import json
        config={'owner':owner.OWNER,'image_id':owner.IMAGE,'image_env':[],
                'numa_seccomp_sha256':owner.NUMA_SECCOMP_SHA256}
        seccomp=json.loads((runtime/'numa-seccomp.json').read_text())
        c={'Id':'candidate','Image':owner.IMAGE,'Name':'/'+m.NAME,
           'HostConfig':{'DeviceRequests':[{'DeviceIDs':[owner.GPU],'Capabilities':[['gpu']],'Count':0}],
                         'ReadonlyRootfs':True,'NetworkMode':'host','RestartPolicy':{'Name':'no','MaximumRetryCount':0},
                         'Memory':owner.MEMORY,'MemorySwap':owner.MEMORY,'CpusetCpus':'0-71','CapDrop':['ALL'],
                         'SecurityOpt':['no-new-privileges','seccomp='+json.dumps(seccomp)],'LogConfig':{'Type':'local'}},
           'Mounts':[{'Type':'bind','Source':m.STAGE if target=='/runtime' else source,'Destination':target,'RW':writable}
                     for target,(source,writable) in owner.mounts().items()],
           'Config':{'Entrypoint':['/opt/conda/bin/python'],'Cmd':['-I','-B','/runtime/file_auth.py','--profile','manual1m'],
                     'Labels':{'io.llm-frontier.owner':m.OWNER,'io.llm-frontier.gpu':owner.GPU,'io.h011.job':'nonce'},
                     'Env':[k+'='+v for k,v in owner.environment().items()]}}
        ops=self.ops();ops.owner=owner;ops.verify_sources=lambda:({},config)
        # Use the real validator, not the generic mock in ops().
        del ops.validate_candidate
        job={'candidate_id':'candidate','nonce':'nonce'}
        ops.validate_candidate(c,job)
        variants=[]
        for key,value in [('Memory',owner.MEMORY+1),('CpusetCpus','0-63'),('NetworkMode','bridge'),('RestartPolicy',{'Name':'always','MaximumRetryCount':0})]:
            bad=copy.deepcopy(c);bad['HostConfig'][key]=value;variants.append(bad)
        bad=copy.deepcopy(c);bad['Config']['Cmd'][-1]='production480k';variants.append(bad)
        bad=copy.deepcopy(c);bad['Config']['Labels']['io.h011.job']='another';variants.append(bad)
        bad=copy.deepcopy(c);bad['Mounts'][1]['RW']=True;variants.append(bad)
        for bad in variants:
            with self.assertRaises(ValueError):ops.validate_candidate(bad,job)

if __name__=='__main__':unittest.main(verbosity=2)
