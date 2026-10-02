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

#!/usr/bin/env python3
"""Fixed authenticated private-link + bearer ingress; disabled source. No general proxy/logging."""
import hmac,http.client,json,re,socket,ssl,threading,time
from http.server import BaseHTTPRequestHandler,HTTPServer
from socketserver import ThreadingMixIn
import control
BIND=('10.156.100.60',18193);TARGET=('127.0.0.1',18193)
ROUTES=re.compile(r'/v1/technical-vision/(?:capabilities|jobs|requests/[A-Za-z0-9_-]{1,80}/status|jobs/[A-Za-z0-9_-]{1,80}/(?:status|cancel))\Z')
class Handler(BaseHTTPRequestHandler):
 protocol_version='HTTP/1.1'
 def log_message(self,*_):pass
 def setup(self):
  super().setup();self.connection.settimeout(10);self.timer=threading.Timer(10,self.expire);self.timer.daemon=True;self.timer.start()
 def expire(self):
  try:self.connection.shutdown(socket.SHUT_RDWR)
  except OSError:pass
 def finish(self):
  try:super().finish()
  finally:self.timer.cancel()
 def do_GET(self):self.forward()
 def do_POST(self):self.forward()
 def forward(self):
  self.close_connection=True
  if time.monotonic()>=self.server.deadline:return self.send_error(503)
  with self.server.count_lock:
   if self.server.request_count>=64:return self.send_error(503)
   self.server.request_count+=1
  if len(self.headers.get_all('Authorization',[]))!=1 or self.headers.get('Host')!='10.156.100.60:18193':return self.send_error(401)
  if self.client_address[0] not in (self.server.client_ip,self.server.health_client_ip) or not hmac.compare_digest(self.headers.get('Authorization',''),'Bearer '+self.server.bearer):return self.send_error(401)
  if not ROUTES.fullmatch(self.path) or (self.command=='GET')!=(self.path.endswith('/capabilities')):return self.send_error(404)
  if self.headers.get('Transfer-Encoding') or len(self.headers.get_all('Content-Length',[]))>1:return self.send_error(400)
  n=self.headers.get('Content-Length','0')
  if not n.isdigit() or int(n)>51*1024*1024:return self.send_error(413)
  body=self.rfile.read(int(n))
  if len(body)!=int(n):return self.send_error(400)
  headers={'Authorization':'Bearer '+self.server.bearer,'Content-Length':str(len(body)),'Content-Type':self.headers.get('Content-Type','application/json'),'Connection':'close','Accept':'application/json'}
  if 'Idempotency-Key' in self.headers:headers['Idempotency-Key']=self.headers['Idempotency-Key']
  c=http.client.HTTPConnection(*TARGET,timeout=10)
  try:
   c.request(self.command,self.path,body,headers);r=c.getresponse();b=r.read(1048577)
   if len(b)>1048576 or r.getheader('Content-Type','')!='application/json':return self.send_error(502)
   self.send_response(r.status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(b)));self.send_header('Connection','close');self.end_headers();self.wfile.write(b)
  except (OSError,http.client.HTTPException):self.send_error(502)
  finally:c.close() # observation only: never cancel/resubmit or certify backend drain
class Server(ThreadingMixIn,HTTPServer):
 daemon_threads=True
 def process_request(self,request,address):
  if not self.slots.acquire(False):request.close();return
  try:super().process_request(request,address)
  except BaseException:self.slots.release();raise
 def process_request_thread(self,request,address):
  try:super().process_request_thread(request,address)
  finally:self.slots.release()
 def handle_error(self,*_):pass
 def __init__(self,bearer,client_ip,protected_link_attestation,deadline,*,proof=None):
  if not proof or proof.get('identityOrigin')!='REVIEWED_SIGNED_ROOT_PROOF' or proof.get('component')!='ingress' or proof.get('actualUid')!=1000:raise control.Refused('signed_ingress_proof_required')
  if not re.fullmatch(r'10\.156\.100\.[0-9]{1,3}',client_ip):raise control.Refused('root_exact_client_ip_required')
  if protected_link_attestation!='PASS_ROOT_REVIEWED_AUTHENTICATED_PRIVATE_LINK':raise control.Refused('protected_transport_required_for_existing_http_client')
  if not isinstance(bearer,str) or not re.fullmatch(r'[\x21-\x7e]{16,256}',bearer):raise control.Refused('private_bearer_required')
  if not 0<deadline-time.monotonic()<=600:raise control.Refused('finite_ingress_window')
  self.bearer=bearer;self.client_ip=client_ip;self.health_client_ip=proof['graph']['runtime']['ingress']['healthClientIp'];self.deadline=deadline;self.slots=threading.BoundedSemaphore(8);self.count_lock=threading.Lock();self.request_count=0;super().__init__(BIND,Handler)
if __name__=='__main__':raise SystemExit('DISABLED: private ingress needs authentic root carrier, exact client IP, protected private-link attestation and bearer references')
