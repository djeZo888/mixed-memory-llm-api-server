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
from control.catalog import Catalog
from test_control_catalog import record

class Fix(unittest.TestCase):
    def test_glm_default_on_initial_and_tool_continuation_override_untouched(self):
        messages = [{'role': 'user', 'content': 'hello'}]
        continued = messages + [{'role':'assistant', 'content':None, 'tool_calls':[{'id':'call1','type':'function','function':{'name':'check','arguments':'{}'}}]}, {'role':'tool','tool_call_id':'call1','content':'ok'}]
        for model, effort, expected in [('glm-5.3', None, 'low'), ('glm-5.3','high','high'), ('qwen3.8-27b',None,None)]:
            client = Client('http://127.0.0.1:30002/v1', model, reasoning_effort=effort)
            for stream in (False, True):
                for history in (messages, continued):
                    with patch.object(client, '_request', return_value={}) as request:
                        client.chat(history, stream=stream)
                        body = request.call_args.args[1]
                        self.assertEqual(body.get('reasoning_effort'), expected)
                        self.assertNotIn('temperature', body)
        client = Client('http://127.0.0.1:30002/v1', 'glm-5.3')
        with patch.object(client, '_request', return_value={}) as request:
            client.chat(messages, model='unrelated')
            self.assertNotIn('reasoning_effort', request.call_args.args[1])

    def test_catalog_only_glm_has_default(self):
        for model in ('unsloth/GLM-5.3-GGUF', 'Qwen/Qwen3.8-27B-FP8'):
            value = Catalog([record(model_id=model)]).target('model-a')
            self.assertEqual(value.get('request_defaults'), {'reasoning_effort':'low'} if model.startswith('unsloth/') else None)

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
