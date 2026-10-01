import base64
import copy
import http.client
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import threading
import time
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from service import *
from backend import Outcome

SERVICE=dict(serviceId='fixture-vision',generation=0,mode='mock',interpreter=dict(model='Qwen/Qwen3.5-9B',revision='generation0-not-loaded',precision='BF16'),parser=dict(model='PaddlePaddle/PaddleOCR-VL-1.6',revision='generation0-not-loaded'))
OWNER=dict(sessionId='session1',workspaceId='workspace1',runId='run1')
KEY='fixture-private-bearer-0001'

def fixture(request='request1'):
    png=encode_png(4,3,2,[b'\xff\xff\xff'*4 for _ in range(3)])
    source=dict(reference=dict(fileId='source1'),sha256=digest(png),mediaType='image/png',coordinateSpace='oriented_page_pixels',pages=[dict(page=1,width=4,height=3,originalWidth=4,originalHeight=3,orientation=1)],crops=[dict(id='label',page=1,x=1,y=1,width=2,height=1)])
    meta=dict(schemaVersion=1,owner=copy.deepcopy(OWNER),requestId=request,service=copy.deepcopy(SERVICE),source=source,question='Transcribe exact labels.',pageImages=[dict(page=1,sha256=digest(png),part='page-1')])
    return meta,{'page-1':('image/png',png)}

def minimal_result(meta):
    return dict(schemaVersion=1,service=meta['service'],source=meta['source'],description='Explicit fake backend fixture; no model prediction.',evidence=[],extraction=dict(text=[],tables=[],formulas=[],layout=[]),observations=dict(components=[],relationships=[]),uncertainties=[],derivedConclusions=[],electricalNetReconstruction='not_qualified')

class ControlledBackend:
    ready=True
    def __init__(self):self.started=threading.Event();self.drain=threading.Event();self.calls=0;self.metadata=None;self.images=None;self.unknown=False
    def execute(self,m,images,cancel,deadline,checkpoint):
        self.calls+=1;self.metadata=m;self.images=images;self.started.set()
        checkpoint(dict(kind='fake_fixture_not_inference',pageSha256=digest(images[1])))
        if not self.drain.wait(max(0,deadline-time.monotonic())):raise BackendFailure(False)
        if self.unknown:raise BackendFailure(False)
        return Outcome(minimal_result(m),True)

class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();os.chmod(self.tmp.name,0o700);self.ledger=PrivateLedger(self.tmp.name);self.backend=ControlledBackend();self.service=VisionService(self.ledger,SERVICE,self.backend,enabled=True,job_timeout=2)
    def tearDown(self):
        self.backend.drain.set();self.assertTrue(self.service.close());self.ledger.close();self.tmp.cleanup()
    def admit(self,request='request1'):
        m,p=fixture(request);return self.service.submit(m,p,request)[1]
    def wait_state(self,job,state):
        end=time.monotonic()+3
        while time.monotonic()<end:
            j=self.service.get(OWNER,job_id=job['jobId'])
            if j['state']==state:return j
            time.sleep(.01)
        self.fail(f'expected {state}, got {j}')
    def test_atomic_duplicates_frozen_and_conflicts(self):
        m,p=fixture();status,job=self.service.submit(m,p,'request1');self.assertEqual(status,202);self.assertTrue(self.backend.started.wait(1))
        results=[]
        ts=[threading.Thread(target=lambda:results.append(self.service.submit(m,p,'request1'))) for _ in range(8)]
        for t in ts:t.start()
        for t in ts:t.join()
        self.assertEqual({j['jobId'] for _,j in results},{job['jobId']});self.assertEqual(self.backend.calls,1)
        changed=copy.deepcopy(m);changed['question']='different'
        with self.assertRaises(Reject) as e:self.service.submit(changed,p,'request1')
        self.assertEqual(e.exception.status,409)
        changed=copy.deepcopy(m);changed['source']['reference']={'workspacePath':'later.png'}
        with self.assertRaises(Reject):self.service.submit(changed,p,'request1')
        newpng=encode_png(4,3,2,[b'\0\0\0'*4 for _ in range(3)]);changed=copy.deepcopy(m);changed['pageImages'][0]['sha256']=digest(newpng)
        with self.assertRaises(Reject) as e:self.service.submit(changed,{'page-1':('image/png',newpng)},'request1')
        self.assertEqual(e.exception.status,409)
        m['question']='caller mutation';self.assertEqual(self.backend.metadata['question'],'Transcribe exact labels.');self.assertEqual(digest(self.backend.images[1]),fixture()[0]['pageImages'][0]['sha256'])
        self.backend.drain.set();j=self.wait_state(job,'completed');self.assertTrue(j['settled']);self.assertEqual(self.service.submit(*fixture(),'request1')[0],200)
    def test_owner_isolation_caps_and_queued_cancel(self):
        first=self.admit();self.assertTrue(self.backend.started.wait(1));second=self.admit('request2')
        who={**OWNER,'runId':'newrun'}
        with self.assertRaises(Reject) as e:self.service.get(who,job_id=first['jobId'])
        self.assertEqual(e.exception.status,404)
        cancelled=self.service.get(OWNER,job_id=second['jobId'],cancel=True);self.assertEqual(cancelled['state'],'cancelled');self.assertTrue(cancelled['settled']);self.assertEqual(self.backend.calls,1)
        self.admit('request3');self.admit('request4');self.admit('request5')
        with self.assertRaises(Reject) as e:self.admit('request6')
        self.assertEqual(e.exception.status,429)
    def test_cancel_observation_never_claims_native_settlement(self):
        job=self.admit();self.assertTrue(self.backend.started.wait(1));j=self.service.get(OWNER,job_id=job['jobId'],cancel=True)
        self.assertEqual(j['state'],'cancelling');self.assertFalse(j['settled']);self.backend.drain.set();self.assertTrue(self.wait_state(job,'cancelled')['settled'])
    def test_unknown_cancel_blocks_inference_and_readiness(self):
        job=self.admit();self.assertTrue(self.backend.started.wait(1));self.backend.unknown=True;self.service.get(OWNER,job_id=job['jobId'],cancel=True);self.backend.drain.set();time.sleep(.1)
        j=self.service.get(OWNER,job_id=job['jobId']);self.assertEqual(j['state'],'cancelling');self.assertFalse(j['settled']);self.assertFalse(self.service.capabilities()['admitting'])
        with self.assertRaises(Reject) as e:self.admit('next')
        self.assertEqual(e.exception.status,503)
    def test_durable_terminal_reopen_and_no_repeat(self):
        job=self.admit();self.backend.drain.set();original=self.wait_state(job,'completed');self.assertTrue(self.service.close());self.ledger.close()
        self.ledger=PrivateLedger(self.tmp.name);self.backend=ControlledBackend();self.service=VisionService(self.ledger,SERVICE,self.backend,enabled=True)
        self.assertEqual(self.service.get(OWNER,request_id='request1'),original);self.assertEqual(self.service.submit(*fixture(),'request1')[0],200);self.assertEqual(self.backend.calls,0)
    def test_restart_interrupts_original_owner_without_dispatch(self):
        # Simulate persisted running record without replaying a live process.
        self.assertTrue(self.service.close());m,p=fixture();key=PrivateLedger.scope(m);j=dict(schemaVersion=1,jobId='job-old',requestId=m['requestId'],owner=m['owner'],service=m['service'],source=m['source'],state='running',settled=False,cancelRequested=False)
        self.ledger.save(key,dict(metadata=m,fingerprint=digest(canonical(m)),images={'1':base64.b64encode(p['page-1'][1]).decode()},job=j,backendEvidence=[]));self.ledger.close()
        self.ledger=PrivateLedger(self.tmp.name);self.backend=ControlledBackend();newidentity={**SERVICE,'serviceId':'new-service'};self.service=VisionService(self.ledger,newidentity,self.backend,enabled=True)
        j=self.service.get(OWNER,request_id='request1');self.assertEqual(j['service'],SERVICE);self.assertEqual(j['owner'],OWNER);self.assertEqual(j['state'],'interrupted');self.assertFalse(j['settled']);self.assertFalse(self.service.capabilities()['ready']);self.assertEqual(self.backend.calls,0)
    def test_private_files_and_single_writer(self):
        with self.assertRaises(BlockingIOError):PrivateLedger(self.tmp.name)
        self.admit();self.backend.drain.set();time.sleep(.05)
        for f in Path(self.tmp.name).iterdir():self.assertEqual(stat.S_IMODE(f.stat().st_mode),0o600)
        with tempfile.TemporaryDirectory() as t:
            os.chmod(t,0o755)
            with self.assertRaises(ValueError):PrivateLedger(t)
    def test_png_caps_hashes_and_path_rejection(self):
        m,p=fixture();broken=bytearray(p['page-1'][1]);broken[-1]^=1
        with self.assertRaises(Reject):decode_png(bytes(broken))
        for ref in [{'workspacePath':'../secret'},{'workspacePath':'https://x'},{'argv':['x']},{'fileId':'source1','url':'http://x'}]:
            bad=copy.deepcopy(m);bad['source']['reference']=ref
            with self.assertRaises(Reject):self.service.submit(bad,p,'request1')
        bad=copy.deepcopy(m);bad['source']['pages'][0]['width']=5
        with self.assertRaises(Reject):self.service.submit(bad,p,'request1')
        self.assertEqual(decode_png(crop_png(p['page-1'][1],dict(x=1,y=1,width=2,height=1)))[:2],(2,1))
    def test_invalid_graph_rejected(self):
        m,_=fixture();r=minimal_result(m);r['evidence']=[dict(id='e',page=1,box=dict(x=0,y=0,width=100,height=1))]
        with self.assertRaises(Reject):validate_result(r,m['source'],SERVICE)
        r=minimal_result(m);r['derivedConclusions']=[dict(id='d',description='circular',basisIds=['d'],evidenceIds=[],uncertaintyIds=[])]
        with self.assertRaises(Reject):validate_result(r,m['source'],SERVICE)

    def test_profile_exact_pixel_boundary_and_just_over_before_decode(self):
        m,_=fixture();p=m['source']['pages'][0];p.update(width=2048,height=1024,originalWidth=2048,originalHeight=1024)
        runtime_profile(m)
        png=encode_png(2048,1024,2,[b'\xff\xff\xff'*2048 for _ in range(1024)]);m['source']['sha256']=digest(png);m['source']['crops']=[];m['pageImages'][0]['sha256']=digest(png)
        self.assertEqual(len(admission(m,{'page-1':('image/png',png)},SERVICE,'request1')),1)
        p.update(height=1025,originalHeight=1025)
        with self.assertRaises(Reject) as e:runtime_profile(m)
        self.assertEqual(e.exception.status,413)
        m,_=fixture();m['source']['mediaType']='application/pdf';p=m['source']['pages'][0];p['pdf']=dict(widthPoints=10,heightPoints=10,rotation=0);m['source']['pages'].append({**p,'page':2})
        with self.assertRaises(Reject):runtime_profile(m)
        m,_=fixture();m['source']['crops']=[{**m['source']['crops'][0],'id':f'crop-{n}'} for n in range(8)];runtime_profile(m);m['source']['crops'].append({**m['source']['crops'][0],'id':'crop-9'})
        with self.assertRaises(Reject):runtime_profile(m)
    def test_unexpected_worker_death_closes_admission(self):
        def die(*args):raise SystemExit('injected unexpected worker death')
        self.backend.execute=die;job=self.admit('worker-death');end=time.monotonic()+1
        while self.service.worker.is_alive() and time.monotonic()<end:time.sleep(.01)
        self.assertFalse(self.service.worker.is_alive());self.assertTrue(self.service.faulted);self.assertFalse(self.service.capabilities()['admitting']);self.assertFalse(self.service.get(OWNER,job_id=job['jobId'])['settled'])
    def test_store_running_checkpoint_final_and_cap_failures_close_admission(self):
        original=self.ledger.save
        for phase in ('running','checkpoint','final','admission'):
            def failing(key,r,phase=phase):
                if ((phase=='running' and r['job']['state']=='running' and not r['backendEvidence']) or (phase=='checkpoint' and r['backendEvidence']) or (phase=='final' and r['job']['state']=='completed') or phase=='admission'):
                    raise OSError('injected fsync/store failure')
                return original(key,r)
            self.ledger.save=failing;self.backend.drain.set()
            if phase=='admission':
                with self.assertRaises(OSError):self.admit(phase)
            else:
                job=self.admit(phase);end=time.monotonic()+1
                while not self.service.faulted and time.monotonic()<end:time.sleep(.01)
                self.assertTrue(self.service.faulted);durable=self.service.get(OWNER,job_id=job['jobId']);self.assertFalse(durable['settled']);self.assertIn(durable['state'],('queued','running'))
            self.assertFalse(self.service.capabilities()['admitting'])
            self.assertTrue(self.service.close());self.ledger.save=original;self.service=VisionService(self.ledger,SERVICE,self.backend,enabled=True);self.assertFalse(self.service.capabilities()['ready']) if phase!='admission' else None
            # Clear fixtures only after this owned service is closed; no production recovery API.
            self.assertTrue(self.service.close());self.ledger.records={}
            for f in Path(self.tmp.name).glob('*.json'):f.unlink()
            self.backend=ControlledBackend();self.service=VisionService(self.ledger,SERVICE,self.backend,enabled=True,job_timeout=2)
        self.ledger.max_bytes=1
        with self.assertRaises(Reject):self.admit('storage-cap')
        self.assertFalse(self.service.capabilities()['admitting'])

class HTTPTests(unittest.TestCase):
    def test_real_http_auth_multipart_duplicate_disconnect_and_lookup(self):
        with tempfile.TemporaryDirectory() as t:
            os.chmod(t,0o700);ledger=PrivateLedger(t);backend=ControlledBackend();svc=VisionService(ledger,SERVICE,backend,enabled=True);server=BoundedHTTPServer(('127.0.0.1',0),svc,KEY);thread=threading.Thread(target=server.serve_forever);thread.start();port=server.server_port
            def call(route,body=None,headers=None):
                c=http.client.HTTPConnection('127.0.0.1',port);c.request('POST' if body else 'GET',route,body,headers or {});r=c.getresponse();data=r.read();status=r.status;c.close();return status,parse_json(data)
            try:
                self.assertEqual(call('/v1/technical-vision/capabilities')[0],401)
                self.assertTrue(call('/v1/technical-vision/capabilities',headers={'Authorization':'Bearer '+KEY})[1]['ready'])
                m,parts=fixture();b='technical-vision-fixture';body=b'--'+b.encode()+b'\r\nContent-Disposition: form-data; name="metadata"\r\nContent-Type: application/json\r\n\r\n'+canonical(m)+b'\r\n--'+b.encode()+b'\r\nContent-Disposition: form-data; name="page-1"; filename="page-1.png"\r\nContent-Type: image/png\r\n\r\n'+parts['page-1'][1]+b'\r\n--'+b.encode()+b'--\r\n'
                headers={'Authorization':'Bearer '+KEY,'Content-Type':'multipart/form-data; boundary='+b,'Idempotency-Key':'request1'}
                status,j=call('/v1/technical-vision/jobs',body,headers);self.assertEqual(status,202)
                self.assertEqual(call('/v1/technical-vision/jobs',body,headers)[1]['jobId'],j['jobId'])
                # Observer disconnect after durable admission has no cancellation authority.
                c=http.client.HTTPConnection('127.0.0.1',port);c.request('POST','/v1/technical-vision/jobs',body,headers);c.close()
                status,found=call('/v1/technical-vision/requests/request1/status',canonical(dict(schemaVersion=1,owner=OWNER)),{'Authorization':'Bearer '+KEY,'Content-Type':'application/json'});self.assertEqual(status,200);self.assertEqual(found['jobId'],j['jobId']);self.assertFalse(found['cancelRequested']);self.assertEqual(backend.calls,1)
            finally:
                backend.drain.set();server.shutdown();server.server_close();thread.join();self.assertTrue(svc.close());ledger.close()

    def test_absolute_http_header_and_body_drip_deadline(self):
        import socket
        with tempfile.TemporaryDirectory() as t:
            os.chmod(t,0o700);ledger=PrivateLedger(t);backend=ControlledBackend();svc=VisionService(ledger,SERVICE,backend,enabled=True);server=BoundedHTTPServer(('127.0.0.1',0),svc,KEY,request_seconds=.18);thread=threading.Thread(target=server.serve_forever);thread.start()
            try:
                for header_drip in (True,False):
                    sock=socket.create_connection(('127.0.0.1',server.server_port));start=time.monotonic()
                    if header_drip:prefix=b'POST /v1/technical-vision/jobs HTTP/1.1\r\nX-Drip: '
                    else:prefix=('POST /v1/technical-vision/jobs HTTP/1.1\r\nHost: localhost\r\nAuthorization: Bearer '+KEY+'\r\nContent-Type: multipart/form-data; boundary=b\r\nContent-Length: 100000\r\n\r\n').encode()
                    sock.sendall(prefix)
                    for _ in range(30):
                        try:sock.sendall(b'x')
                        except OSError:break
                        time.sleep(.02)
                    sock.settimeout(.5)
                    try:data=sock.recv(4096)
                    except (ConnectionResetError,OSError):data=b''
                    elapsed=time.monotonic()-start;sock.close();self.assertLess(elapsed,.8);self.assertFalse(ledger.records);self.assertEqual(backend.calls,0)
            finally:backend.drain.set();server.shutdown();server.server_close();thread.join();svc.close();ledger.close()

# TS cross-language fixture exercises this real HTTP service, with an explicit fake
# backend. It never opens model endpoints and is not a service deployment launcher.
if __name__=='__main__' and '--fixture-server' in sys.argv:
    directory=sys.argv[sys.argv.index('--fixture-server')+1];ledger=PrivateLedger(directory)
    # Owned fake local model HTTP server: exercises the actual bounded backend.
    from backend import LocalVisionBackend,QWEN,PADDLE
    class FixtureModels(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_POST(self):
            payload=parse_json(self.rfile.read(int(self.headers['Content-Length'])),60*1024*1024)
            if self.path!='/v1/chat/completions' or self.headers.get('Authorization')!='Bearer fixture-backend-key-0001':self.send_error(401);return
            literal='R1  10 kΩ\n  Vcc\n' if payload['model']==PADDLE else json.dumps(dict(description='Explicit fake local model HTTP response; no accuracy claim.',uncertainties=['Fixture only'],derivedConclusions=[]))
            data=canonical(dict(model=payload['model'],choices=[dict(index=0,message=dict(role='assistant',content=literal),finish_reason='stop')]))
            self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(data)));self.send_header('Connection','close');self.end_headers();self.wfile.write(data)
    models=HTTPServer(('127.0.0.1',0),FixtureModels);modelthread=threading.Thread(target=models.serve_forever);modelthread.start();origin=f'http://127.0.0.1:{models.server_port}'
    backend=LocalVisionBackend(SERVICE,lambda role:'fixture-backend-key-0001',fixture=True,enabled=True,qwen_origin=origin,ocr_origin=origin)
    svc=VisionService(ledger,SERVICE,backend,enabled=True);bearer=sys.stdin.readline().rstrip('\n');server=BoundedHTTPServer(('127.0.0.1',0),svc,bearer)
    print(json.dumps(dict(port=server.server_port,service=SERVICE)),flush=True)
    def shutdown():
        for line in sys.stdin:
            if line.strip()=='stop':server.shutdown();return
    thread=threading.Thread(target=shutdown,daemon=True);thread.start()
    try:server.serve_forever()
    finally:server.server_close();svc.close();ledger.close();models.shutdown();models.server_close();modelthread.join()
elif __name__=='__main__':unittest.main()
