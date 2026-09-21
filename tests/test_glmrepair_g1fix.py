import json
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from benchmark import glmrepair as g, profiles, fixtures
from benchmark.host import LinuxHost

class G1Fix(unittest.TestCase):
    def test_profile_clock_and_one_case(self):
        prior=profiles.glmrepair_manifest(g.CAMPAIGN)
        actual=profiles.glmrepair_manifest(g.G1FIX_CAMPAIGN)
        self.assertEqual(actual,json.loads(json.dumps(prior).replace(g.CAMPAIGN,g.G1FIX_CAMPAIGN)))
        arm={'campaign':g.G1FIX_CAMPAIGN,'scope':'glmrepair','manifests':[actual],
             'trial_plan':profiles.trial_order('glmrepair',campaign=g.G1FIX_CAMPAIGN),
             'runtime':{'start_epoch':100.,'deadline_epoch':1300.,'budget_seconds':1200}}
        self.assertEqual(profiles.validate_arm_scope(arm),'glmrepair')
        self.assertEqual(LinuxHost.glmrepair_clock(arm),(100.,1300.))
        self.assertEqual([r['case'] for r in arm['trial_plan']['trials']],['load_warmup','native-schema'])
        arm['runtime']['deadline_epoch']+=1
        with self.assertRaises(Exception):LinuxHost.glmrepair_clock(arm)

    def test_saved_schema_alias_only_and_real_boundary_seam(self):
        temporary=tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        task=Path(temporary.name);(task/'private').mkdir()
        old={'model':'glm-5.3','messages':[{'role':'user','content':'fixed fixture'}],
             'temperature':1.0,'seed':1729,'max_tokens':256,'stream':True,
             'response_format':{'type':'json_schema','json_schema':{'strict':True,'schema':{
                 'type':'object','required':['START','MIDDLE','END'],'additionalProperties':False,
                 'properties':{k:{'type':'string'} for k in ('START','MIDDLE','END')}}}}}
        saved=fixtures.canonical(old);(task/'private/D-native-schema.request.json').write_bytes(saved)
        digest_patch=patch.object(g,'SCHEMA_SHA256',fixtures.digest(saved))
        digest_patch.start();self.addCleanup(digest_patch.stop)
        raw=g.schema_body(task)
        new=json.loads(raw)
        self.assertEqual({k for k in set(old)|set(new) if old.get(k)!=new.get(k)},{'model'})
        self.assertEqual(new['model'],g.MODEL)
        class ReachedIdle(Exception):pass
        def idle():raise ReachedIdle()
        host=SimpleNamespace(scope='glmrepair',owner=SimpleNamespace(phase='ACTIVE'),assert_idle=idle)
        points=[];requests=[];counts=[]
        def boundary(cid,point):
            with self.assertRaises(ReachedIdle):LinuxHost.diagnostic_snapshot(host,cid,point)
            points.append(point)
        def counter(body):counts.append(body);return {'input_tokens':3546}
        def request(cid,body,name):
            requests.append((body,name));return {'parsed':{'message':{}},'summary':{'counters':{'cached_tokens':0}}}
        fake=SimpleNamespace(host=SimpleNamespace(call=lambda *a,**kw:None),armed={'manifests':[{}]},
            loaded=lambda manifest:'cid',fixture_cache={g.FIXTURE_KEY:{}},state=task,
            counter=lambda cid:counter,boundary=boundary,progress={'completed':{},'inflight':{}},
            record=lambda *a:None,request=request,telemetry_window=lambda *a:{},emit=lambda row:None)
        with patch.object(g,'exact_body',return_value=(b'{}',{})), \
             patch.object(fixtures,'validate_count',return_value={'input_tokens':3546}), \
             patch.object(g,'format_outcome',return_value={'status':'PASS'}),patch.object(g.runner,'save'):
            g.Diagnostic.schema_sequence(fake)
        self.assertEqual(points,['before_stream','after_stream'])
        self.assertEqual(requests,[(raw,'native-schema')]);self.assertEqual(counts,[raw])
        self.assertEqual(set(fake.progress['completed']),{'native-schema'})
