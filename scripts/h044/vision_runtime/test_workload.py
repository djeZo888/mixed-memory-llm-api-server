# Explicit protected import bootstrap for genuine Python -I entrypoints.
if __name__ == '__main__':
 import hashlib as _h, importlib.util as _iu, json as _j, os as _o, stat as _s
 from pathlib import Path as _P
 _root = _P(__file__).absolute().parents[3]
 _loader = _root/'scripts/h044/vision_runtime/trusted_imports.py'
 _manifest = (_root/'SOURCE-MANIFEST.json') if str(_root).startswith('/opt/') else (_root.parent/'output/SOURCE-MANIFEST.json')
 _uid = 0 if str(_root).startswith('/opt/') else _o.geteuid()
 def _protected(p):
  if str(p)!=_o.path.realpath(p):raise ValueError('bootstrap_symlink')
  for a in [p,*p.parents]:
   z=a.lstat()
   if z.st_uid not in (0,_uid) or z.st_mode&0o022:raise ValueError('bootstrap_owner_mode')
  fd=_o.open(p,_o.O_RDONLY|_o.O_NOFOLLOW)
  try:
   z=_o.fstat(fd)
   if not _s.S_ISREG(z.st_mode) or z.st_uid!=_uid or z.st_nlink!=1 or z.st_size>1048576:raise ValueError('bootstrap_source')
   raw=_o.read(fd,1048577);q=_o.fstat(fd)
   if (z.st_dev,z.st_ino,z.st_size,z.st_mtime_ns,z.st_ctime_ns)!=(q.st_dev,q.st_ino,q.st_size,q.st_mtime_ns,q.st_ctime_ns):raise ValueError('bootstrap_changed')
   return raw
  finally:_o.close(fd)
 _m=_j.loads(_protected(_manifest));_b=_protected(_loader);_record=_m['modules']['trusted_imports']
 if _record['path']!='scripts/h044/vision_runtime/trusted_imports.py' or _h.sha256(_b).hexdigest()!=_record['sha256'] or len(_b)!=_record['bytes']:raise ValueError('bootstrap_hash')
 _spec=_iu.spec_from_file_location('trusted_imports',_loader);_module=_iu.module_from_spec(_spec)
 import sys as _sys
 _sys.modules['trusted_imports']=_module;exec(compile(_b,str(_loader),'exec'),_module.__dict__)
 _module.install(_root,_m,_uid)

import copy,json,time,unittest
import control,workload
class WorkloadTests(unittest.TestCase):
 def case(self):
  _,corpus=workload.fixture();identity={'interpreter':{'model':'Qwen/Qwen3.5-9B','revision':'q'},'parser':{'model':'PaddlePaddle/PaddleOCR-VL-1.6','revision':'p'}};source={'sha256':corpus['pngSha256']};responses=[]
  for role,k in [('interpretation','interpreter'),('ocr','parser')]:
   raw=control.canonical({'model':identity[k]['model'],'choices':[]});responses.append({'kind':'model_response','role':role,'model':identity[k]['model'],'revision':identity[k]['revision'],'sourceSha256':source['sha256'],'response':json.loads(raw),'responseSha256':control.sha(raw),'rawResponseHex':raw.hex(),'viewSha256':source['sha256'],'inputPngSHA256':source['sha256']})
  current={'state':'completed','settled':True,'result':{'service':identity,'source':source,'description':'R1 10K 5V labels','extraction':{'text':[{'exactText':'R1 10K 5V'}]},'uncertainties':[{'id':'qwen-uncertainty-1','description':'unqualified interpretation'}],'electricalNetReconstruction':'not_qualified'}}
  return current,corpus,identity,source,{'backendEvidence':responses}
 def test_expected_response_and_ocr_failure_are_distinct(self):
  c=self.case();r=workload.assess_response(*c,1,120);self.assertEqual(r['status'],'RESPONSE_ASSERTIONS_PASS');self.assertIn('SOURCE_ONLY',r['fixtureQualification'])
  c[0]['result']['extraction']['text'][0]['exactText']='R1 100K 5V';r=workload.assess_response(*c,1,120);self.assertIn('EXPECTED_OCR_LITERAL_MISMATCH',r['failures'])
 def test_timing_raw_revision_input_uncertainty_fail(self):
  c=self.case();r=workload.assess_response(*c,121,120);self.assertIn('TIMING_OVERRUN',r['failures'])
  c[-1]['backendEvidence'][0]['rawResponseHex']='00';c[-1]['backendEvidence'][1]['revision']='wrong';c[0]['result']['uncertainties']=[]
  r=workload.assess_response(*c,1,120);self.assertIn('RAW_BYTE_HASH_PROVENANCE',r['failures']);self.assertIn('MODEL_REVISION_RAW_INPUT_PROVENANCE',r['failures']);self.assertIn('INTERPRETATION_UNCERTAINTY_MISSING',r['failures'])
 def test_more_than_twelve_polls_and_full_deadline(self):
  now=[0];seen=[]
  def call(*_):return 200,b'{}',{'state':'completed' if len(seen)>=16 else 'running','settled':True}
  def record(n,*_):seen.append(n)
  def pause(t):now[0]+=t
  current,polls=workload.poll_job(call,{},'owned',10,record,clock=lambda:now[0],pause=pause);self.assertEqual(polls,17);self.assertEqual(current['state'],'completed')
  now[0]=0
  with self.assertRaises(TimeoutError):workload.poll_job(lambda *_:(200,b'{}',{'state':'running'}),{},'owned',1,lambda *_:None,clock=lambda:now[0],pause=pause)
 def test_root_cannot_read_service_uid_bearer_or_dispatch(self):
  # No leaf is opened before authentic UID and signed-workload proof.
  with self.assertRaises(control.Refused):workload.service_job({}, {'component':'workload','actualUid':1000},time.monotonic()+1,'EXPLICIT-FAKE-KEY-0001')
class TerminalRawTests(unittest.TestCase):
 def test_service_job_returns_terminal_poll_bytes_never_admission_bytes(self):
  from unittest import mock
  import vision_service_entrypoint as entry
  root=__import__('pathlib').Path(__file__).absolute().parents[3];config=__import__('json').loads((root/'configs/vision/h043-candidate.json').read_text())
  writes=[];terminal={'jobId':'owned-job','state':'completed','settled':True,'result':{}}
  admission=b'{"jobId":"owned-job","state":"running"}'
  terminal_raw=__import__('json').dumps(terminal,indent=3).encode();count=[0]
  def bounded(method,host,port,path,payload,typ,key,deadline,rid=None):
   count[0]+=1
   return (202 if count[0]==1 else 200,admission,{'jobId':'owned-job','state':'running'}) if count[0]<=2 else (200,terminal_raw,terminal)
  def read_record(*_,**kw):
   metadata=next(v['metadata'] for p,v in writes if 'request-' in str(p))
   return control.canonical({'metadata':metadata,'job':terminal})
  graph={'runtime':{'service':{'ledger':str(root.parent/'output/terminal-source-fixture')}}}
  proof={'component':'workload','actualUid':1000,'identityOrigin':'REVIEWED_SIGNED_ROOT_PROOF','proofSHA256':'SOURCE_ONLY_FIXTURE'}
  with mock.patch.object(workload.os,'geteuid',return_value=1000),mock.patch.object(workload,'graph_service',return_value=config['service']),mock.patch.object(workload,'bounded_call',side_effect=bounded),mock.patch.object(workload.control,'exclusive',side_effect=lambda p,v:writes.append((p,v))),mock.patch.object(entry,'protected_read',side_effect=read_record),mock.patch.object(workload,'assess_response',return_value={'status':'SOURCE_ONLY_FIXTURE'}):
   result=workload.service_job(graph,proof,time.monotonic()+5,'EXPLICIT_FAKE_KEY')
  self.assertEqual(bytes.fromhex(result['rawServiceResponseHex']),terminal_raw);self.assertNotEqual(bytes.fromhex(result['rawServiceResponseHex']),admission);self.assertEqual(result['rawServiceResponseSHA256'],control.sha(terminal_raw));self.assertEqual(result['polls'],1)

class WallTimerTests(unittest.TestCase):
 def test_slow_body_entire_wall_timer_and_actual_socket(self):
  import http.client,os,threading
  from http.server import BaseHTTPRequestHandler,HTTPServer
  from pathlib import Path
  class Slow(BaseHTTPRequestHandler):
   def log_message(self,*_):pass
   def do_GET(self):
    self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length','21');self.end_headers()
    try:
     for b in b'{"slow":"test_body"}  ':self.wfile.write(bytes([b]));self.wfile.flush();time.sleep(.02)
    except OSError:pass
  server=HTTPServer(('127.0.0.1',0),Slow);port=server.server_address[1];thread=threading.Thread(target=server.handle_request);thread.start();start=time.monotonic()
  root=Path(__file__).absolute().parents[3];control.exclusive(root.parent/'output'/('socket-test-'+__import__('secrets').token_hex(8)+'.json'),{'address':'127.0.0.1','port':port,'kind':'TCP_LOOPBACK_SOURCE_FIXTURE','unixSocketPaths':[],'TMPDIR':os.environ.get('TMPDIR')})
  try:
   with self.assertRaises((TimeoutError,OSError,http.client.HTTPException)):workload.bounded_call('GET','127.0.0.1',port,'/source-fixture',b'','application/json','EXPLICIT-FAKE-KEY-0001',start+.08)
   self.assertLess(time.monotonic()-start,.4)
  finally:thread.join(timeout=2);server.server_close()
  self.assertFalse(thread.is_alive())
if __name__=='__main__':unittest.main()
