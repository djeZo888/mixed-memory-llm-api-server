import copy
import http.server
import json
from pathlib import Path
import sys
import threading
import time
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_service import SERVICE,fixture
from service import BackendFailure,decode_png,canonical,parse_json,digest,validate_result
from backend import LocalVisionBackend,QWEN,PADDLE,QWEN_REV,PADDLE_REV

class BackendTests(unittest.TestCase):
    def setUp(self):
        self.requests=[];self.mode='valid'
        outer=self
        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self,*a):pass
            def do_POST(self):
                outer.assertEqual(self.path,'/v1/chat/completions');outer.assertEqual(self.headers['Authorization'],'Bearer fixture-backend-key-0001')
                body=parse_json(self.rfile.read(int(self.headers['Content-Length'])),60*1024*1024);outer.requests.append(body)
                model=body['model'];literal='R1  10 kΩ\n  Vcc\n' if model==PADDLE else json.dumps(dict(description='Fixture Qwen response',uncertainties=['Unclear crossing'],derivedConclusions=['Possible resistor']))
                if outer.mode=='bad-json' and model==QWEN:literal='```not json```'
                payload=dict(model=model,choices=[dict(index=0,message=dict(role='assistant',content=literal),finish_reason='stop')])
                if outer.mode=='wrong-model':payload['model']='other'
                if outer.mode=='length':payload['choices'][0]['finish_reason']='length'
                if outer.mode=='delay':time.sleep(.15)
                raw=canonical(payload)
                if outer.mode=='header-drip':
                    try:
                        self.connection.sendall(b'HTTP/1.1 200 OK\r\nX-Drip: ')
                        for _ in range(40):self.connection.sendall(b'x');time.sleep(.02)
                    except OSError:pass
                    return
                self.send_response(302 if outer.mode=='redirect' else 200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.send_header('Connection','close');self.end_headers()
                if outer.mode=='body-drip':
                    try:
                        for b in raw:self.wfile.write(bytes([b]));self.wfile.flush();time.sleep(.02)
                    except OSError:pass
                    return
                try:self.wfile.write(raw)
                except (BrokenPipeError,ConnectionResetError):pass
        self.server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler);self.thread=threading.Thread(target=self.server.serve_forever);self.thread.start();origin=f'http://127.0.0.1:{self.server.server_port}'
        self.backend=LocalVisionBackend(SERVICE,lambda role:'fixture-backend-key-0001',fixture=True,enabled=True,qwen_origin=origin,ocr_origin=origin);self.evidence=[]
    def tearDown(self):self.server.shutdown();self.server.server_close();self.thread.join()
    def run_backend(self,cancel=None,timeout=2):
        m,p=fixture();return self.backend.execute(m,{1:p['page-1'][1]},cancel or threading.Event(),time.monotonic()+timeout,self.evidence.append)
    def test_real_requests_preserve_literal_crop_provenance(self):
        outcome=self.run_backend();r=outcome.result;self.assertTrue(outcome.settled);self.assertEqual(r['extraction']['text'][0]['exactText'],'R1  10 kΩ\n  Vcc\n');self.assertEqual(r['observations'],dict(components=[],relationships=[]));self.assertEqual(r['electricalNetReconstruction'],'not_qualified');self.assertTrue(r['derivedConclusions']);self.assertTrue(r['uncertainties'])
        self.assertEqual([r['model'] for r in self.requests],[QWEN,PADDLE]);self.assertTrue(all(r['max_tokens']==4096 and not r['stream'] for r in self.requests));self.assertEqual(len(self.evidence),4)
        ocr=self.evidence[-1];self.assertEqual(ocr['cropId'],'label');self.assertEqual(ocr['literalText'],'R1  10 kΩ\n  Vcc\n');self.assertEqual(ocr['inputRegion'],dict(x=1,y=1,width=2,height=1));self.assertNotEqual(ocr['cropSha256'],ocr['pageSha256']);self.assertEqual(ocr['sourceSha256'],fixture()[0]['source']['sha256'])
        import base64
        png=base64.b64decode(self.requests[1]['messages'][1]['content'][0]['image_url']['url'].split(',')[1]);self.assertEqual(decode_png(png)[:2],(2,1))
        validate_result(r,fixture()[0]['source'],SERVICE)
    def test_malformed_qwen_content_is_settled_failure_no_ocr(self):
        self.mode='bad-json'
        with self.assertRaises(BackendFailure) as e:self.run_backend()
        self.assertTrue(e.exception.settled);self.assertEqual(len(self.requests),1)
    def test_ambiguous_timeout_and_no_retry(self):
        self.mode='delay'
        with self.assertRaises(BackendFailure) as e:self.run_backend(timeout=.04)
        self.assertFalse(e.exception.settled);self.assertEqual(len(self.requests),1)
    def test_redirect_mismatch_and_truncation_fail_closed(self):
        for mode in ['redirect','wrong-model','length']:
            self.mode=mode
            with self.assertRaises(BackendFailure) as e:self.run_backend()
            self.assertFalse(e.exception.settled)
        self.assertEqual(len(self.requests),3)
    def test_cancel_before_dispatch_and_after_drained_response(self):
        cancel=threading.Event();cancel.set();self.assertTrue(self.run_backend(cancel).settled);self.assertEqual(self.requests,[])
        def checkpoint(v):
            self.evidence.append(v)
            if v['kind']=='model_response':cancel.set()
        cancel.clear();self.backend.key=lambda _: 'fixture-backend-key-0001';m,p=fixture();out=self.backend.execute(m,{1:p['page-1'][1]},cancel,time.monotonic()+2,checkpoint);self.assertTrue(out.settled);self.assertIsNone(out.result);self.assertEqual(len(self.requests),1)
    def test_absolute_backend_header_and_body_drip_deadlines(self):
        for mode in ('header-drip','body-drip'):
            self.mode=mode;start=time.monotonic()
            with self.assertRaises(BackendFailure) as e:self.run_backend(timeout=.12)
            self.assertFalse(e.exception.settled);self.assertLess(time.monotonic()-start,.5)
        self.assertEqual(len(self.requests),2)
    def test_profile_rejection_before_dispatch(self):
        m,p=fixture();page=m['source']['pages'][0];page.update(width=2048,height=1025,originalWidth=2048,originalHeight=1025)
        with self.assertRaises(BackendFailure) as e:self.backend.execute(m,{1:p['page-1'][1]},threading.Event(),time.monotonic()+2,self.evidence.append)
        self.assertTrue(e.exception.settled);self.assertEqual(self.requests,[])

    def test_backend_rejects_changed_page_bytes_before_any_dispatch(self):
        m,p=fixture()
        with self.assertRaises(BackendFailure) as e:self.backend.execute(m,{1:p['page-1'][1]+b'changed'},threading.Event(),time.monotonic()+2,self.evidence.append)
        self.assertTrue(e.exception.settled);self.assertEqual(self.requests,[])
    def test_endpoint_and_exact_live_revision_policy(self):
        live=copy.deepcopy(SERVICE);live.update(mode='live',generation=1);live['interpreter']['revision']=QWEN_REV;live['parser']['revision']=PADDLE_REV
        backend=LocalVisionBackend(live,lambda _:'protected-key-reference-only');self.assertFalse(backend.ready)
        for origin in ['http://example.com:18191','http://127.0.0.1:18191/secret','http://127.0.0.1:18191?x=1','http://user:pass@127.0.0.1:18191','http://127.0.0.1:18192','https://127.0.0.1:18191']:
            with self.assertRaises(ValueError):LocalVisionBackend(live,lambda _:'not-used',qwen_origin=origin)
        live['parser']['revision']='0'*40
        with self.assertRaises(ValueError):LocalVisionBackend(live,lambda _:'not-used')

if __name__=='__main__':unittest.main()
