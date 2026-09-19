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
    def test_only_selected_production_profile_has_native_low_default(self):
        from lifecycle.manager import Manager
        root=Path(__file__).resolve().parents[1]
        name='glm-5.3-ud-q4-k-xl-n76-native1m'
        d=json.loads((root/'configs/deployments'/ (name+'.json')).read_text())
        d['_model']=json.loads((root/'configs/models'/ (d['model']+'.json')).read_text())
        d['_runtime']=json.loads((root/'configs/runtimes'/ (d['runtime']+'.json')).read_text())
        command=Manager.launch_command(d, {'image_id': d['_runtime']['validation']['image_id'], 'load_mode':'none'})
        kwargs=json.loads(command[command.index('--chat-template-kwargs')+1])
        self.assertEqual(kwargs, {'clear_thinking':True,'reasoning_effort':'low'})
        for other in root.joinpath('configs/deployments').glob('glm*.json'):
            if other.stem != name:
                self.assertEqual(json.loads(other.read_text())['launch']['chat_template_kwargs'],{'clear_thinking':True})
        client=Client('http://127.0.0.1:30002/v1','glm-5.3')
        with patch.object(client,'_request',return_value={}) as request:
            client.chat([{'role':'user','content':'hi'}])
            self.assertNotIn('reasoning_effort',request.call_args.args[1])
        client=Client('http://127.0.0.1:30002/v1','glm-5.3',reasoning_effort='high')
        with patch.object(client,'_request',return_value={}) as request:
            client.chat([{'role':'user','content':'hi'}])
            self.assertEqual(request.call_args.args[1]['reasoning_effort'],'high')

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
