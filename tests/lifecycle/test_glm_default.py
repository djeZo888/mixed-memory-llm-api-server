import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"scripts"))
from agent.protocol import Client

class Default(unittest.TestCase):
    def test_only_selected_production_profile_has_native_low_default(self):
        from lifecycle.manager import Manager
        root=Path(__file__).resolve().parents[2]
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

