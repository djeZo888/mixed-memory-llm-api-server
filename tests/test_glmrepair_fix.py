import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from agent.protocol import Client
from benchmark import glmrepair as g, profiles, fixtures
from benchmark.host import LinuxHost

class Fix(unittest.TestCase):
    def test_repair_sequence_uses_actual_host_allowed_boundary_names(self):
        from types import SimpleNamespace
        class ReachedIdle(Exception): pass
        def idle(): raise ReachedIdle()
        host = SimpleNamespace(scope='glmrepair', owner=SimpleNamespace(phase='ACTIVE'), assert_idle=idle)
        points=[]
        def boundary(cid, point):
            with self.assertRaises(ReachedIdle):
                LinuxHost.diagnostic_snapshot(host,cid,point)
            points.append(point)
        fake=SimpleNamespace(host=SimpleNamespace(call=lambda *a,**kw:None),
            armed={'manifests':[{}]},loaded=lambda manifest:'cid',
            fixture_cache={g.FIXTURE_KEY:{}},state=Path('/unused'),
            counter=lambda cid:lambda raw:{'input_tokens':3546},boundary=boundary,
            progress={'completed':{},'inflight':{}},record=lambda *a:None,
            request=lambda *a:{'parsed':{'message':{}},'summary':{'counters':{'cached_tokens':0}}},
            telemetry_window=lambda *a:{},emit=lambda row:None)
        with patch.object(g,'exact_body',return_value=(b'{}',{})), \
             patch.object(g,'sampling_body',return_value=b'{}'), \
             patch.object(fixtures,'validate_count',return_value={'input_tokens':3546}), \
             patch.object(g,'format_outcome',return_value={'status':'PASS'}), \
             patch.object(g.runner,'save'):
            g.Diagnostic.repair_sequence(fake)
        self.assertEqual(points,['before_stream','after_stream','before_nonstream','after_nonstream'])
        self.assertEqual(set(fake.progress['completed']),{'sampling1729','sampling2718'})

    def test_fixed_profile_and_clock(self):
        actual = profiles.glmrepair_manifest(g.FIX_CAMPAIGN)
        prior = profiles.glmrepair_manifest(g.CAMPAIGN)
        self.assertEqual(actual,json.loads(json.dumps(prior).replace(g.CAMPAIGN,g.FIX_CAMPAIGN)))
        arm = {'campaign':g.FIX_CAMPAIGN,'scope':'glmrepair','manifests':[actual],'trial_plan':profiles.trial_order('glmrepair',campaign=g.FIX_CAMPAIGN),'runtime':{'start_epoch':100.,'deadline_epoch':2800.,'budget_seconds':2700}}
        self.assertEqual(profiles.validate_arm_scope(arm),'glmrepair')
        self.assertEqual(LinuxHost.glmrepair_clock(arm),(100.,2800.))
        arm['runtime']['deadline_epoch'] += 1
        with self.assertRaises(Exception): LinuxHost.glmrepair_clock(arm)

    def test_only_sampling_fields_changed(self):
        raw = fixtures.canonical({'model':'bench-glm-5.3','temperature':0,'reasoning_effort':'low','messages':[{'role':'user','content':'unchanged'}],'max_tokens':256,'stream':True})
        for seed in (1729,2718):
            with patch.object(g, "BODY_SHA256", fixtures.digest(raw)):
                value=json.loads(g.sampling_body(raw,seed))
            old=json.loads(raw)
            self.assertEqual({k for k in set(value)|set(old) if value.get(k)!=old.get(k)}, {'temperature','seed'})
            self.assertEqual(value['temperature'],1.0); self.assertEqual(value['seed'],seed)
