"""Focused offline H023 fixtures. No sockets, subprocess dispatch or credential reads."""
import base64
import copy
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import zlib
from contract import *
from controller import Phase
from primitives import Journal, capture_text, capture_image, decode_png, interval_report
from telemetry import validate_sample

HERE = Path(__file__).resolve().parent

class Clock:
    def __init__(self):
        self.t = 10.
    def __call__(self):
        return {'monotonic': self.t, 'utc': (datetime(2026, 9, 28, 15, 0, tzinfo=timezone.utc)+timedelta(seconds=self.t)).isoformat()}
    def advance(self, seconds=1):
        self.t += seconds
        return self()

def manifest():
    m = json.loads((HERE/'deployment.example.json').read_text())
    m.update(task_id='H023-FIXTURE', review_state='REVIEWED_CURRENT', boot_id='fixture-current-boot',
             deployment_id='fixture-current-deployment', captured_utc=Clock()()['utc'],
             deployment_manifest_sha256='a'*64, owner_adapter_sha256='b'*64, source_sha256={'/fixture/current/owner.py':'c'*64})
    for i, lane in enumerate(LANES):
        s = m['lanes'][lane]
        s.update(gpu_uuid='GPU-'+f'{i+1:08x}'+'-0000-0000-0000-000000000000', gpu_type=lane+' fixture type',
                 model='mimo-v2.6-pro-rl' if lane=='mimo' else lane+'-fixture-model', runtime='fixture-runtime',
                 endpoint='http://10.156.100.60:30012' if lane=='mimo' else 'http://fixture.invalid:39999',
                 auth_ref='fixture-private-reference-never-opened', identity={k:lane+'-current-'+k for k in s['identity']},
                 power_limit_w=300 if lane=='image' else 600,reserve_mib=1000,critical_c=90,
                 ecc_current='Disabled',ecc_pending='Disabled')
        s['owner_contract'].update({k:lane+'-source-ref-'+k for k in ('claim','preflight','settlement','stop_exact')})
        s['owner_contract']['source_sha256']='c'*64
        if lane=='image':s['owner_contract']['spool_cleanup']='fixture-approved-owned-cleanup'
        if lane.startswith('qwen'):s.update(output_ceiling=4096,template_sha256='d'*64)
        else:s.update(count_path='/v1/chat/completions/input_tokens',count_field='input_tokens')
        if lane.startswith('qwen'):s.update(count_path='/v1/tokenize',count_field='count')
    validate_manifest(m)
    return m

def go(m, clock, phase='B'):
    return dict(action='ROOT GO H023 PHASE '+phase,phase=phase,task_id=m['task_id'],go_id='fixture-go-'+phase,
                boot_id=m['boot_id'],deployment_sha256=digest(m),package_sha256='f'*64,
                quiet_confirmed=True,global_admission_receipt='fixture-current-global-receipt',
                not_before_utc=clock()['utc'],admission_deadline_utc=(datetime.fromisoformat(clock()['utc'])+timedelta(seconds=300)).isoformat(),
                settlement_deadline_utc=(datetime.fromisoformat(clock()['utc'])+timedelta(seconds=720)).isoformat())

def proof(m, clock, lane):
    r = dict(lane=lane,owner_id=lane+'-owner',lease_id=lane+'-lease',boot_id=m['boot_id'],deployment_sha256=digest(m),
             identity=copy.deepcopy(m['lanes'][lane]['identity']),gpu_uuid=m['lanes'][lane]['gpu_uuid'],observed=clock(),
             ready=True,guard_ok=True,global_admission_receipt='fixture-current-global-receipt',native_idle=True,
             authenticated=True,evidence_ref='fixture-native-authenticated-readback')
    if lane.startswith('qwen'):r['request_disposition']='EXCLUSIVE_QUIET_PREFLIGHT'
    if lane=='mimo':r.update(proxy_active_requests=0,proxy_quarantined=False,native_slots=[{'is_processing':False,'n_ctx':950000}])
    if lane=='image':r.update(owned_job_idle=True,spool_ready=True)
    return r

def sample(m, clock):
    row=dict(boot_id=m['boot_id'],deployment_sha256=digest(m),identities={l:copy.deepcopy(m['lanes'][l]['identity']) for l in LANES},
             guard_ok=True,utc=clock()['utc'],start_monotonic=clock.t-.1,end_monotonic=clock.t,due_monotonic=clock.t-.2,
             gpu={},cgroups={},guest={'ram_total_bytes':1000,'ram_available_bytes':500,'swap_in':0,'swap_out':0,'cpu_ticks':[1,1,1,10,1,1,1,1,0,0]},
             kernel={'read_ok':True,'events':[]},external_fan={'header':'CHA_FAN3','configured_curve':[75,75,75,75,100],
                 'source_readback':'CPU Package Temp value0 mask1 LastSource0','evidence_ref':'fixture-approved-external-owner',
                 'tach_units':'unknown','raw_tach':5040})
    for lane in LANES:
        spec=m['lanes'][lane]
        row['gpu'][spec['gpu_uuid']]=dict(type=spec['gpu_type'],family=spec['gpu_family'],temperature_c=40,
            power_draw_w=100 if lane!='image' else 20,power_limit_w=spec['power_limit_w'],utilization_pct=10,
            memory_total_mib=10000,memory_free_mib=2000,memory_used_mib=8000,clocks={'graphics':100,'sm':100,'memory':100},
            throttle={k:False for k in ('hw_thermal_slowdown','sw_thermal_slowdown','hw_power_brake_slowdown','sw_power_cap','hw_slowdown')},
            power_brake=False,ecc_current='Disabled',ecc_pending='Disabled',ecc_uncorrected=0,pcie_replay=0,
            integrated_fan={'target_pct':None,'current_pct':None,'rpm':None,'unavailable_reason':'fixture not exposed'})
        row['cgroups'][lane]={'memory_current':1,'swap_current':0,'events':{'oom':0,'oom_kill':0,'max':0},'cpu':{'usage_usec':1}}
    return row

class Response(io.BytesIO):
    status=200

def sse(count=16384, tail=b'', done=True, usage=True):
    rows=[{'id':'fixture-native-id','choices':[{'index':0,'delta':{'content':'x'},'finish_reason':None}]},
          {'choices':[{'index':0,'delta':{},'finish_reason':'stop'}],'timings':{'predicted_ms':1}}]
    if usage:rows.append({'choices':[],'usage':{'prompt_tokens':count,'completion_tokens':1,'total_tokens':count+1}})
    return b''.join(b'data: '+canonical(r)+b'\n\n' for r in rows)+(b'data: [DONE]\n\n' if done else b'')+tail

def png(w=1920,h=1080):
    def chunk(k,v):return struct.pack('>I',len(v))+k+v+struct.pack('>I',zlib.crc32(k+v)&0xffffffff)
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',w,h,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(b'\0'*(h*(1+w*3))))+chunk(b'IEND',b'')

class Contracts(unittest.TestCase):
    def test_placeholder_reject(self):
        with self.assertRaises(Refusal):validate_manifest(json.loads((HERE/'deployment.example.json').read_text()))
    def test_mandatory_identity_owner_endpoints(self):
        m=manifest()
        for key in ('native','launch','proxy','supervisor','container','policy'):
            x=copy.deepcopy(m);x['lanes']['mimo']['identity'][key]=None
            with self.subTest(key=key),self.assertRaises(Refusal):validate_manifest(x)
        for endpoint in ('http://127.0.0.1:30012','http://10.156.100.60:30010','http://user:secret@10.156.100.60:30012'):
            x=copy.deepcopy(m);x['lanes']['mimo']['endpoint']=endpoint
            with self.assertRaises(Refusal):validate_manifest(x)
        x=copy.deepcopy(m);x['lanes']['qwen1']['owner_contract']={}
        with self.assertRaises(Refusal):validate_manifest(x)
    def test_context_bounds_and_no_shell(self):
        for lane,key,value in [('mimo','context_tokens',4096),('mimo','output_ceiling',128),('qwen1','context_tokens',262144),('image','shell','rm -rf /')]:
            m=manifest();m['lanes'][lane][key]=value
            with self.assertRaises(Refusal):validate_manifest(m)
    def test_exact_go_deadline_phase_batch_reject(self):
        m=manifest();c=Clock();g=go(m,c)
        validate_go(g,m,'B','f'*64,c()['utc'])
        for key,value in [('package_sha256','e'*64),('boot_id','old'),('action','ROOT GO H019'),('phase','A'),('phases',['A','B'])]:
            bad={**g,key:value}
            with self.assertRaises(Refusal):validate_go(bad,m,'B','f'*64,c()['utc'])
        c.advance(300)
        with self.assertRaises(Refusal):validate_go(g,m,'B','f'*64,c()['utc'])
    def test_mimo_canonical_matches_retained_proxy_normalizer(self):
        # Execute ONLY the pure normalize function, not proxy imports or startup.
        import ast
        path=HERE.parents[2]/'scripts/runtime/mimo/private_proxy.py'
        tree=ast.parse(path.read_text());nodes=[]
        for node in tree.body:
            if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id in ('FIELDS','MODEL') for t in node.targets):nodes.append(node)
            if isinstance(node,ast.FunctionDef) and node.name=='normalize':nodes.append(node)
        ns={};exec(compile(ast.Module(body=nodes,type_ignores=[]),'retained-proxy-pure-normalize','exec'),ns)
        body=text_body(manifest(),'mimo','prefix-1','fresh native counted data')
        self.assertEqual(ns['normalize'](body),body)
        self.assertEqual(body['max_tokens'],128)
    def test_count_16k_no_estimate_no_body_mutation(self):
        m=manifest();body=text_body(m,'mimo','prefix','data');h=digest(body)
        r={'body_sha256':h,'native':True,'http_status':200,'endpoint':m['lanes']['mimo']['count_path'],'response':{'input_tokens':16384}}
        self.assertEqual(validate_count(m,'mimo',h,r),16384)
        for n in (4096,15999,16385,950000,True,'16384'):
            with self.assertRaises(Refusal):validate_count(m,'mimo',h,{**r,'response':{'input_tokens':n}})
        with self.assertRaises(Refusal):validate_count(m,'mimo','a'*64,r)

class Drain(unittest.TestCase):
    def test_done_then_actual_eof_and_native_timings(self):
        c=Clock();row={};r=Response(sse(tail=b': trailing comment\n\n'))
        capture_text(r,row,16384,128,c)
        self.assertTrue(row['http_drained']);self.assertEqual(r.tell(),len(r.getvalue()))
        self.assertTrue(row['done']);self.assertEqual(row['native_timings'],[{'predicted_ms':1}])
        self.assertIn('eof',row)
    def test_missing_eof_done_finish_usage_and_errors(self):
        for data in (sse(done=False),sse(usage=False),sse(count=4096),sse(tail=b'data: {}\n\n'),b'data: {"error":{"message":"private"}}\n\n',sse().replace(b'"stop"',b'null')):
            row={}
            with self.subTest(data=data[-30:]),self.assertRaises((Refusal,ValueError)):capture_text(Response(data),row,16384,128,Clock())
            self.assertFalse(row['response_complete']);self.assertIn('first_failure',row)
    def test_disconnect_after_done_is_not_eof(self):
        class Broken(Response):
            def readline(self,*args):
                value=super().readline(*args)
                if not value:raise TimeoutError('simulated disconnect')
                return value
        row={}
        with self.assertRaises(TimeoutError):capture_text(Broken(sse()),row,16384,128,Clock())
        self.assertTrue(row['done']);self.assertFalse(row['http_drained']);self.assertNotIn('eof',row)
    def test_png_full_decode_crc_dimensions_and_hash(self):
        raw=png();got=decode_png(raw);self.assertTrue(got['decoded']);self.assertEqual(got['png_sha256'],hashlib.sha256(raw).hexdigest())
        for bad in (raw[:-1],raw+b'x',raw[:40]+b'x'+raw[41:],png(1920,1079)):
            with self.assertRaises(Refusal):decode_png(bad)
        row={};capture_image(Response(canonical({'data':[{'b64_json':base64.b64encode(raw).decode()}]})),row,Clock())
        self.assertTrue(row['http_drained']);self.assertTrue(row['image']['decoded'])

class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='h023-private-fixture-')
        self.addCleanup(self.tmp.cleanup)
        self.c=Clock();self.m=manifest()
        self.p=self.make('B')
    def make(self,phase):
        p=Phase(self.m,go(self.m,self.c,phase),phase,'f'*64,Path(self.tmp.name)/phase,self.c)
        p.observe(sample(self.m,self.c));p.release_barrier({l:proof(self.m,self.c,l) for l in p.lanes})
        return p
    def started(self,lane='mimo',prefix='random-prefix-a',p=None):
        p=p or self.p
        b=text_body(self.m,lane,prefix,'varied corpus') if lane in TEXT else image_body(self.m,prefix)
        row,raw=p.prepare(lane,b,prefix,proof(self.m,self.c,lane))
        on_disk=json.loads((p.journal.path/(row['request_id']+'.json')).read_text());self.assertEqual(on_disk['state'],'OWNED_BEFORE_COUNT')
        if lane in TEXT:
            p.counted(lane,{'owner_id':row['owner_id'],'identity':row['identity'],'observed':self.c(),'body_sha256':row['body_sha256'],'count_body_sha256':row['count_body_sha256'],
                           'native':True,'http_status':200,'endpoint':self.m['lanes'][lane]['count_path'],'response':{self.m['lanes'][lane]['count_field']:16384 if lane=='mimo' else 4096}})
        p.begin_send(lane,raw,proof(self.m,self.c,lane));return p.body_sent(lane)
    def finish(self,lane,row,p=None):
        p=p or self.p
        self.c.advance(1)
        if lane in TEXT:capture_text(Response(sse(16384 if lane=='mimo' else 4096)),row,16384 if lane=='mimo' else 4096,128,self.c)
        else:capture_image(Response(canonical({'data':[{'b64_json':base64.b64encode(png()).decode()}]})),row,self.c)
        p.http_finished(lane,row)
        pr=proof(self.m,self.c,lane);pr.update(request_id=row['request_id'],ownership_released=True,resident=True,disposition='COMPLETED')
        if lane=='image':pr.update(job_released=True,spool_cleanup='APPROVED_OWNED_CLEANUP',cleanup_receipt='fixture-cleanup',native_owner_run_id='fixture-run')
        p.settled(lane,pr)
    def test_one_inflight_then_native_settlement_required(self):
        row=self.started()
        with self.assertRaises(Refusal):self.p.prepare('mimo',text_body(self.m,'mimo','b','x'),'b',proof(self.m,self.c,'mimo'))
        self.finish('mimo',row)
        self.assertNotIn('mimo',self.p.active)
        with self.assertRaisesRegex(Refusal,'MiMo never repeats'):self.p.prepare('mimo',text_body(self.m,'mimo','c','x'),'c',proof(self.m,self.c,'mimo'))
    def test_server_hot_keeps_mimo_owned_draining(self):
        mimo=self.started();self.started('qwen1','server-prefix')
        hot=sample(self.m,self.c);hot['gpu'][self.m['lanes']['qwen1']['gpu_uuid']]['temperature_c']=85
        self.p.observe(hot)
        self.assertEqual(set(self.p.stop_intents),{'qwen1'})
        self.assertEqual(self.p.active['mimo']['state'],'POSSIBLY_SUBMITTED')
        self.finish('mimo',mimo)
        self.assertTrue(self.p.requests['mimo'][0]['settlement']['resident'])
        self.assertEqual(self.p.requests['mimo'][0]['state'],'SETTLED')
        with self.assertRaises(Refusal):self.started('qwen0','later')
    def test_ambiguous_work_owned_no_retry_and_first_failure_preserved(self):
        self.started();self.p.ambiguous('mimo','first_timeout');self.p.fail('second_telemetry_error')
        self.assertEqual(self.p.first_failure['reason'],'first_timeout')
        self.assertEqual(self.p.active['mimo']['state'],'UNKNOWN_OWNED')
        with self.assertRaises(Refusal):self.started('mimo','retry')
        self.assertIn('mimo',self.p.report()['unknown_or_owned'])
    def test_expired_phase_stops_admission_not_healthy_draining(self):
        row=self.started();self.c.advance(300);self.p.observe(sample(self.m,self.c));self.p.monitoring_tick()
        self.assertTrue(self.p.admission_closed);self.assertFalse(self.p.stop_intents)
        self.finish('mimo',row);self.assertNotIn('mimo',self.p.active)
    def test_phase_A_only_qwen1_and_target_and_bounded(self):
        p=self.make('A')
        with self.assertRaises(Refusal):self.started('mimo',p=p)
        row=self.started('qwen1','A-prefix',p)
        self.c.advance(179);p.observe(sample(self.m,self.c));self.finish('qwen1',row,p)
        with self.assertRaisesRegex(Refusal,'target reached'):p.prepare('qwen1',text_body(self.m,'qwen1','next','x'),'next',proof(self.m,self.c,'qwen1'))
        self.assertEqual(p.report()['status'],'PASS')
    def test_fresh_prefix_reused_rejects(self):
        row=self.started('qwen0');self.finish('qwen0',row)
        with self.assertRaisesRegex(Refusal,'fresh leading prefix'):self.started('qwen0')
        self.assertTrue(self.p.admission_closed)
    def test_count_failure_stops_all_admission(self):
        row,raw=self.p.prepare('mimo',text_body(self.m,'mimo','a','x'),'a',proof(self.m,self.c,'mimo'))
        bad={'owner_id':row['owner_id'],'identity':row['identity'],'observed':self.c(),'body_sha256':row['body_sha256'],'count_body_sha256':row['count_body_sha256'],'native':True,
             'http_status':200,'endpoint':self.m['lanes']['mimo']['count_path'],'response':{'input_tokens':4096}}
        with self.assertRaises(Refusal):self.p.counted('mimo',bad)
        self.assertTrue(self.p.admission_closed);self.assertIn('mimo',self.p.active)
        with self.assertRaises(Refusal):self.p.begin_send('mimo',raw,proof(self.m,self.c,'mimo'))
    def test_preflight_all_four_actual_owners_required(self):
        p=Phase(self.m,go(self.m,self.c),'B','f'*64,Path(self.tmp.name)/'partial',self.c);p.observe(sample(self.m,self.c))
        with self.assertRaises(Refusal):p.release_barrier({'mimo':proof(self.m,self.c,'mimo')})
        self.assertIsNone(p.barrier)
    def test_owner_drift_and_queue_zero_not_native_proof(self):
        r=self.started();pr=proof(self.m,self.c,'mimo');pr.update(request_id=r['request_id'],ownership_released=True,resident=True,disposition='COMPLETED')
        del pr['native_slots'];pr.update(queue=0,util=0,client_exit=0)
        with self.assertRaises(Refusal):self.p.settled('mimo',pr)
        self.assertIn('mimo',self.p.active)
    def test_stale_telemetry_global_stop_without_broad_cancel(self):
        self.started();self.c.advance(4);self.p.monitoring_tick()
        self.assertTrue(self.p.admission_closed);self.assertFalse(self.p.stop_intents)
        self.assertIn('mimo',self.p.active);self.assertTrue(self.p.escalations)
    def test_exclusive_journal_prevents_replay_and_permissions(self):
        with self.assertRaises(FileExistsError):self.make('B')
        self.assertEqual(self.p.journal.path.stat().st_mode & 0o777,0o700)
        self.assertEqual((self.p.journal.path/'INTENT.json').stat().st_mode & 0o777,0o600)
    def test_send_exact_hash_and_possible_submission_before_IO(self):
        lane='qwen0';b=text_body(self.m,lane,'p','x');row,raw=self.p.prepare(lane,b,'p',proof(self.m,self.c,lane))
        self.p.counted(lane,{'owner_id':row['owner_id'],'identity':row['identity'],'observed':self.c(),'body_sha256':row['body_sha256'],'count_body_sha256':row['count_body_sha256'],
             'native':True,'http_status':200,'endpoint':self.m['lanes'][lane]['count_path'],'response':{'count':4096}})
        with self.assertRaisesRegex(Refusal,'bytes changed'):self.p.begin_send(lane,raw+b' ',proof(self.m,self.c,lane))
        self.assertNotIn('send_started',self.p.active[lane])
    def test_image_repeat_waits_owned_spool_cleanup(self):
        row=self.started('image')
        self.c.advance();capture_image(Response(canonical({'data':[{'b64_json':base64.b64encode(png()).decode()}]})),row,self.c)
        self.p.http_finished('image',row)
        with self.assertRaises(Refusal):self.started('image','second')
        pr=proof(self.m,self.c,'image');pr.update(request_id=row['request_id'],ownership_released=True,resident=True,disposition='COMPLETED',job_released=True)
        with self.assertRaisesRegex(Refusal,'cleanup'):self.p.settled('image',pr)
        self.assertIn('image',self.p.active)

class TelemetryAndOverlap(unittest.TestCase):
    def test_UUID_join_and_same_sample_power(self):
        m=manifest();c=Clock();s=sample(m,c);d,f=validate_sample(m,s,c.t)
        self.assertEqual(f,[]);self.assertEqual(d['three_blackwell_draw_w'],300);self.assertEqual(d['ada_draw_w'],20)
        self.assertAlmostEqual(d['sampling_delay_seconds'],.2)
        s['gpu']['wrong-uuid']=s['gpu'].pop(m['lanes']['image']['gpu_uuid'])
        self.assertTrue(validate_sample(m,s,c.t)[1])
    def test_each_cutoff_fault_scope_and_lower_native_critical(self):
        for lane in LANES:
            m=manifest();m['lanes'][lane]['critical_c']=82;c=Clock();s=sample(m,c);s['gpu'][m['lanes'][lane]['gpu_uuid']]['temperature_c']=82
            f=validate_sample(m,s,c.t)[1];self.assertEqual(f,[{'reason':'thermal_limit','lane':lane,'stop_exact':True}])
    def test_oom_xid_swap_reserve_delay_guard(self):
        m=manifest();c=Clock();base=sample(m,c)
        variants=[]
        s=copy.deepcopy(base);s['cgroups']['qwen1']['swap_current']=1;variants.append((s,'qwen1'))
        s=copy.deepcopy(base);s['cgroups']['qwen1']['events']['oom']=1;variants.append((s,'qwen1'))
        s=copy.deepcopy(base);s['kernel']['events']=[{'kind':'Xid','lane':'qwen1'}];variants.append((s,'qwen1'))
        s=copy.deepcopy(base);s['gpu'][m['lanes']['qwen1']['gpu_uuid']]['memory_free_mib']=0;variants.append((s,'qwen1'))
        for s,lane in variants:
            self.assertTrue(any(f['lane']==lane and f['stop_exact'] for f in validate_sample(m,s,c.t,base)[1]))
        for key,value in [('guard_ok',False),('end_monotonic',c.t-10),('boot_id','old')]:
            s=copy.deepcopy(base);s[key]=value
            self.assertTrue(any(f['lane'] is None and not f['stop_exact'] for f in validate_sample(m,s,c.t,base)[1]))
    def test_overlap_union_intersection_and_idle_gaps(self):
        by={'mimo':[[0,10],[8,12]],'qwen0':[[2,4],[7,11]],'qwen1':[[3,9]],'image':[[1,5],[8,10]]}
        report=interval_report(by,0,15)
        self.assertEqual(report['intersection_intervals'],[[3,4],[8,9]])
        self.assertEqual(report['intersection_seconds'],2)
        self.assertEqual(report['lanes']['mimo']['active_seconds'],12)
        self.assertEqual(report['lanes']['qwen1']['largest_idle_gap_seconds'],6)
        self.assertEqual(interval_report({l:[] for l in LANES},0,300)['intersection_seconds'],0)

if __name__=='__main__':unittest.main()

class ConcreteRunner(unittest.TestCase):
    def test_real_runner_flow_fake_transport_full_drain(self):
        from runner import Runner
        c=Clock();m=manifest()
        with tempfile.TemporaryDirectory(prefix='h023-private-runner-') as tmp:
            p=Phase(m,go(m,c),'B','f'*64,Path(tmp)/'run',c)
            p.observe(sample(m,c));p.release_barrier({l:proof(m,c,l) for l in LANES})
            sent=[]
            class Connection:
                def send(self,raw,rid):
                    current=p.active['mimo'];saved=json.loads((p.journal.path/(rid+'.json')).read_text())
                    require(saved['state']=='POSSIBLY_SUBMITTED','must persist before fake wire')
                    sent.append(raw)
                def response(self):c.advance();return Response(sse())
                def close(self):pass
            class Fake:
                def preflight(self,lane):return proof(m,c,lane)
                def count(self,lane,raw,row):return {'native':True,'http_status':200,'body_sha256':hashlib.sha256(raw).hexdigest(),
                    'count_body_sha256':hashlib.sha256(raw).hexdigest(),'endpoint':m['lanes'][lane]['count_path'],
                    'response':{'input_tokens':16384},'observed':c(),'owner_id':row['owner_id'],'identity':row['identity']}
                def connect(self,lane):return Connection()
                def settlement(self,lane,row):
                    r=proof(m,c,lane);r.update(request_id=row['request_id'],ownership_released=True,resident=True,disposition='COMPLETED');return r
            self.assertTrue(Runner(p,Fake()).once('mimo','native counted fixture corpus'))
            self.assertEqual(len(sent),1);self.assertEqual(p.requests['mimo'][0]['state'],'SETTLED')
            self.assertTrue(p.requests['mimo'][0]['http_drained']);self.assertIn('eof',p.requests['mimo'][0])
    def test_fixed_wire_no_retry_and_endpoint_from_manifest(self):
        from native import Wire
        from unittest.mock import MagicMock
        m=manifest();conn=MagicMock()
        with patch('native.http.client.HTTPConnection',return_value=conn) as create:
            wire=Wire(m['lanes']['mimo'],'fake-not-a-credential',2)
            conn.request.side_effect=TimeoutError('mock')
            with self.assertRaises(TimeoutError):wire.send(b'{}','owned-fixture')
            self.assertEqual(conn.request.call_count,1);self.assertEqual(conn.auto_open,0)
            create.assert_called_once_with('10.156.100.60',30012,timeout=2)
    def test_qwen_config_ceiling_and_phase_fan100(self):
        m=manifest();m['lanes']['qwen1']['output_ceiling']=32768
        m['external_fan']['configured_curve']=[100]*5;validate_manifest(m)

class ReadOnlyGuardRegression(unittest.TestCase):
    def test_request_read_guard_has_no_lease_or_full_scan(self):
        from native import NativeAdapter
        from unittest.mock import MagicMock
        a=NativeAdapter.__new__(NativeAdapter);a.storage=MagicMock();a.acquire=MagicMock(side_effect=AssertionError('lease forbidden'))
        a.guard_cls=MagicMock();a.journal_path=Path('/data/logs/H023-fixture/run')
        with a.read_boundary():pass
        a.acquire.assert_not_called();a.storage.root_payload_guard.assert_not_called()
        a.guard_cls.return_value.__enter__.return_value.check_path.assert_called_once()
    def test_exact_stop_receipt_releases_only_hot_owned_lane(self):
        c=Clock();m=manifest()
        with tempfile.TemporaryDirectory(prefix='h023-private-stop-') as tmp:
            p=Phase(m,go(m,c),'B','f'*64,Path(tmp)/'run',c);p.observe(sample(m,c));p.release_barrier({l:proof(m,c,l) for l in LANES})
            for lane in ('mimo','qwen1'):
                row,_=p.prepare(lane,text_body(m,lane,lane+'-prefix','x'),lane+'-prefix',proof(m,c,lane))
            p.fail('hot','qwen1',True);intent=copy.deepcopy(p.stop_intents['qwen1'])
            p.physical_stopped('qwen1',{'intent':intent,'physical_stop_proven':True,'observed':c()})
            self.assertIn('mimo',p.active);self.assertNotIn('qwen1',p.active)
            self.assertEqual(p.stop_intents['qwen1']['status'],'PHYSICALLY_SETTLED')
