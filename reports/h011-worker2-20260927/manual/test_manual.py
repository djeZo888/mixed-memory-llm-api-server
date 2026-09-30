#!/usr/bin/env python3
"""Offline candidate policy/count/fixture checks. No native/GPU acceptance."""
import asyncio
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import prepare
import context_profile as profiles
import manual

class Preparation(unittest.TestCase):
    def test_exact_baseline_and_production_unchanged(self):
        before = prepare.sources()
        generated = prepare.candidate(before)
        self.assertEqual(prepare.sources(), before)
        for name in ('owner.py','tool_runtime.py','native-source-pins.json','numa-seccomp.json','fixture_native.py'):
            self.assertEqual(generated[name], before[name])
        self.assertIn(b"'--host','127.0.0.1'", generated['file_auth.py'])
        self.assertIn(b"choices=('production480k','manual1m'), default='production480k'", generated['file_auth.py'])
        self.assertNotIn(b'--context-length', generated['context_profile.py'])

    def test_materialization_refuses_duplicate_without_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp)/'candidate'
            result = prepare.prepare(target)
            self.assertTrue(result['runnable_source_candidate']);self.assertFalse(result['live_verified'])
            hashes = {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in target.iterdir()}
            with self.assertRaises(FileExistsError):
                prepare.prepare(target)
            self.assertEqual(hashes, {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in target.iterdir()})

    def test_edit_requires_exact_single_site(self):
        for bad in ('missing','old old'):
            with self.assertRaises(ValueError): prepare.once(bad, 'old', 'new')

    def test_start_always_fails_closed_without_maintenance_bypass(self):
        response = subprocess.run([sys.executable, '-B', str(HERE/'manual.py'), 'start'], capture_output=True, text=True)
        self.assertEqual(response.returncode, 2)
        value = json.loads(response.stdout)
        self.assertEqual(value['code'],'fresh_harness_stopped_and_all_clients_settled_ack_required')
        self.assertEqual(value['status'], 'REFUSED_OR_BLOCKED')
        denied = subprocess.run([sys.executable, '-B', str(HERE/'manual.py'), 'start', '--force'], capture_output=True)
        self.assertEqual(denied.returncode, 2)

class Profiles(unittest.TestCase):
    def test_allowlist_default_and_capacity(self):
        self.assertEqual(profiles.select().context, 480000)
        self.assertEqual(profiles.select().port, 30010)
        self.assertEqual(profiles.select('manual1m').port, 30011)
        for value in (None, True, 480000, '1048576', 'manual', '--context-length=1048576'):
            with self.assertRaises(ValueError): profiles.select(value)
        for value in (True, 1048576.0, '1048576', 1000000, 480001):
            with self.assertRaises(ValueError): profiles.from_context(value)

    def test_native_margins_and_mismatched_allocation_refused(self):
        for p in profiles.PROFILES.values():
            profiles.verify_allocation(p.allocation, p)
            profiles.require_budget(p.context-7, 5, p)
            for count, output in ((p.context-6,1),(p.context-7,6),(100,65537),(0,1)):
                with self.assertRaises(ValueError): profiles.require_budget(count, output, p)
            bad = p.allocation | {'pool':480000 if p.context != 480000 else 479999}
            with self.assertRaises(ValueError): profiles.verify_allocation(bad, p)
        profiles.require_budget(1000000,1024,profiles.select('manual1m'))
        with self.assertRaises(ValueError): profiles.require_budget(1000000,1024,profiles.select())

    def test_exact_native_count_and_pins_and_output_reserve(self):
        good = {'count':1000000,'tokenizer_revision':profiles.REVISION,
                'template_revision':profiles.REVISION,'context_limit':1048576}
        profiles.verify_count(good)
        for key, value in (('count',999999),('count',1048576),('context_limit',480000),
                           ('tokenizer_revision','other'),('template_revision','other')):
            with self.assertRaises(ValueError): profiles.verify_count(good | {key:value})
        with self.assertRaises(ValueError): profiles.verify_count(good, output=65536)

class CandidateRuntime(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.path = Path(cls.temp.name)/'runtime'
        prepare.prepare(cls.path)
        sys.path.insert(0,str(cls.path))
        def load(name):
            spec=importlib.util.spec_from_file_location(name,cls.path/(name+'.py'))
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
        cls.adapter=load('tokenize_adapter');sys.modules['tokenize_adapter']=cls.adapter
        cls.auth=load('file_auth');cls.fixture=load('fixture_1m')
    @classmethod
    def tearDownClass(cls):
        sys.path.remove(str(cls.path));cls.temp.cleanup()

    def payload(self,n,output):
        return {'model':self.adapter.MODEL,'messages':[{'role':'user','content':n}], 'max_tokens':output}

    def test_same_native_processing_and_selected_context(self):
        seen=[]
        server=types.SimpleNamespace(_process_messages=lambda request,**kw:(seen.append((request,kw)) or types.SimpleNamespace(prompt_ids=[1,2,3])))
        for context in (480000,1048576):
            count=self.adapter.count_native(self.payload('abc',1024), request_type=types.SimpleNamespace,serving_chat=server,context_limit=context)
            self.assertEqual(count['context_limit'],context);self.assertEqual(count['count'],3)
        self.assertEqual(seen[0][0].reasoning_effort,'high')
        self.assertEqual(seen[0][1],{'is_multimodal':False})
        with self.assertRaises(ValueError):self.adapter.count_native(self.payload('abc',1),request_type=types.SimpleNamespace,serving_chat=server,context_limit=1000000)

    def test_middleware_rejects_stale_480k_and_accepts_candidate_count(self):
        class Response:
            def __init__(self,body,status_code):self.body,self.code=body,status_code
            async def __call__(self,scope,receive,send):await send({'status':self.code,'body':self.body})
        async def case(profile,n,output):
            sent=[]
            async def app(scope,receive,send):await send({'status':200})
            async def receive():return {'type':'http.request','body':json.dumps(self.payload('fixture',output)).encode()}
            async def send(value):sent.append(value)
            server=types.SimpleNamespace(app=types.SimpleNamespace(state=types.SimpleNamespace(openai_serving_chat=None)))
            middleware=self.auth.ContractMiddleware(app,key=b'fixture-only',server=server,request_type=object,profile=profile)
            with mock.patch.object(self.auth,'count_native',return_value={'count':n}), mock.patch.dict(sys.modules,{'starlette.responses':types.SimpleNamespace(JSONResponse=Response)}):
                await middleware({'type':'http','headers':[(b'authorization',b'Bearer fixture-only')],'path':'/v1/chat/completions','method':'POST'},receive,send)
            return sent[0]['status']
        self.assertEqual(asyncio.run(case(profiles.select(),1000000,1024)),400)
        self.assertEqual(asyncio.run(case(profiles.select('manual1m'),1000000,1024)),200)
        self.assertEqual(asyncio.run(case(profiles.select('manual1m'),1048570,1)),400)

    def test_full_target_fixture_with_character_mock_only(self):
        base=self.fixture.fixture_module()
        value=self.fixture.build(base._CharacterTokenizer(),'offline-full-target')
        self.assertEqual(value['rendered_tokens'],1000000)
        self.assertEqual(value['payload']['max_tokens'],1024)
        self.assertLess(value['serialized_request_bytes'],16*1024*1024)
        self.assertEqual(value['native_tokenize_parity'],'REQUIRED_BEFORE_INFERENCE')
        self.assertEqual(len(set(value['expected_result'][k] for k in ('early','middle','end'))),3)
        for key,fraction in (('early',.02),('middle',.5),('end',.98)):
            self.assertLess(abs(value['code_locations'][key]['token_fraction']-fraction),.002)
        self.__class__.fixture_bytes=value['serialized_request_bytes']

if __name__=='__main__':
    unittest.main(verbosity=2)
