"""Bounded adapter HTTP/policy and native scheduler-wait tests; no GPU claims."""
from pathlib import Path
import sys
import types
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/runtime/flash'))
from tokenize_adapter import MODEL, normalized_text_request
from file_auth import ContractMiddleware, install_readiness
from idle import FlashIdle

class SharedHttpPolicy(unittest.TestCase):
    def setUp(self):
        from fastapi import FastAPI, Request
        from fastapi.testclient import TestClient
        from tokenize_adapter import install_tokenize_route
        self.seen=[]
        class Serving:
            def _process_messages(inner, request, *, is_multimodal):
                self.seen.append(request.__dict__)
                # Fake IDs are transport-policy fixture only, never model counts.
                content=request.messages[0]['content']
                text=content if isinstance(content,str) else ''.join(p['text'] for p in content or [])
                return types.SimpleNamespace(prompt_ids=list(range(len(text))))
        app=FastAPI();server=types.SimpleNamespace(app=app)
        app.state.openai_serving_chat=Serving()
        install_tokenize_route(server,types.SimpleNamespace)
        @app.post('/v1/chat/completions')
        async def chat(request:Request):
            return await request.json()
        @app.get('/v1/models')
        async def models():return {'data':[]}
        app.add_middleware(ContractMiddleware,key=b'fixture-key',server=server,request_type=types.SimpleNamespace)
        self.client=TestClient(app);self.headers={'Authorization':'Bearer fixture-key'}

    def payload(self, content='Helloworld',role='user'):
        return {'model':MODEL,'messages':[{'role':role,'content':content}],'max_tokens':8}

    def test_auth_and_closed_native_routes(self):
        for headers in [{},{'Authorization':'Bearer wrong'}]:
            self.assertEqual(self.client.get('/v1/models',headers=headers).status_code,401)
        self.assertEqual(self.client.get('/v1/models',headers=self.headers).status_code,200)
        self.assertEqual(self.client.post('/generate',json={},headers=self.headers).status_code,404)

    def test_both_routes_share_text_array_policy_and_concat_count(self):
        array=[{'type':'text','text':'Hello'},{'type':'text','text':'world'}]
        counts=[]
        for content in ['Helloworld',array]:
            response=self.client.post('/v1/tokenize',json=self.payload(content),headers=self.headers)
            self.assertEqual(response.status_code,200);counts.append(response.json()['count'])
            response=self.client.post('/v1/chat/completions',json=self.payload(content),headers=self.headers)
            self.assertEqual(response.status_code,200);self.assertEqual(response.json()['messages'][0]['content'],content)
            self.assertEqual(response.json()['reasoning_effort'],'high')
        self.assertEqual(counts,[10,10])

    def test_developer_normalizes_to_system_without_reordering_both_routes(self):
        for route in ['/v1/tokenize','/v1/chat/completions']:
            self.seen.clear()
            response=self.client.post(route,json=self.payload(role='developer'),headers=self.headers)
            self.assertEqual(response.status_code,200)
            self.assertTrue(all(row['messages'][0]['role']=='system' for row in self.seen))
        self.assertEqual(normalized_text_request(self.payload(role='developer')), normalized_text_request(self.payload(role='system')))

    def test_multimodal_unknown_and_effort_rejected_both_routes(self):
        bad=[self.payload([{'type':'image_url','image_url':{'url':'x'}}]),self.payload([{'type':'unknown','text':'x'}]),self.payload()|{'reasoning_effort':'low'}]
        for route in ['/v1/tokenize','/v1/chat/completions']:
            for payload in bad:self.assertEqual(self.client.post(route,json=payload,headers=self.headers).status_code,400)

    def test_native_input_and_sum_bounds(self):
        for n,max_tokens,code in [(479993,5,200),(479994,1,400),(479993,6,400)]:
            r=self.client.post('/v1/tokenize',json=self.payload('x'*n)|{'max_tokens':max_tokens},headers=self.headers)
            self.assertEqual(r.status_code,code)

class IdleWait(unittest.TestCase):
    def test_grace_block_wake_and_async_grammar(self):
        now=[0];calls=[]
        scheduler=types.SimpleNamespace(chunked_req=None,running_batch=types.SimpleNamespace(is_empty=lambda:True),waiting_queue=[],grammar_manager=[])
        idle=FlashIdle(scheduler,clock=lambda:now[0],poller=types.SimpleNamespace(poll=lambda timeout:calls.append(timeout)))
        idle.wait();now[0]=600;idle.wait();idle.work();idle.wait()
        self.assertEqual(calls,[1,None,1])
        now[0]=1201;scheduler.grammar_manager.append(object());idle.wait()
        self.assertEqual(calls[-1],1)

if __name__=='__main__':unittest.main()
