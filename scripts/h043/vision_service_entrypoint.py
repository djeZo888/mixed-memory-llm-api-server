# Explicit protected import bootstrap for genuine Python -I entrypoints.
if __name__ == '__main__':
 import hashlib as _h, importlib.util as _iu, json as _j, os as _o, stat as _s
 from pathlib import Path as _P
 _root = _P(__file__).absolute().parents[2]
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
"""Real H043 service construction; deployment remains disabled in this revision.

No engine lifecycle, alternate profile, credentials in arguments, or implicit GO.
A root-reviewed successor must enable the sealed control graph, not this CLI.
"""
import argparse,dataclasses,hashlib,importlib.util,json,os,re,signal,stat,sys,threading,time,subprocess,tempfile
from pathlib import Path
LIBRARY_HASHES={
 'service.py':'3887854b2e7c29173baa63480cebeead44c3054c8b67caae280fa37bb292c4d0',
 'backend.py':'5ca264c574dc714aaae1a1cdfe51776a2d19ee28a47f2b67509152e3b6e31b39'}
REV_QWEN='c202236235762e1c871ad0ccb60c8ee5ba337b9a'
REV_OCR='c5630abae1d940eafe0697512a0325494b02ab42'
SECRET_PATHS={'service':'/run/secrets/vision-service.key','interpretation':'/run/secrets/vision-interpretation.key','ocr':'/run/secrets/vision-ocr.key'}
EXECUTION_ENABLED=False
class Refused(ValueError):pass
@dataclasses.dataclass(frozen=True)
class Profile:
 qwenTotalTokens:int=16384
 ocrTotalTokens:int=8192
 maxOutputTokens:int=4096
 concurrencyPerService:int=1
 pagesPerRequest:int=1
 cropsPerInference:int=1
 cropsPerRequest:int=8
 maxImagePixels:int=2097152
 maxImageEdge:int=4096
 def check(self):
  if dataclasses.asdict(self)!=dataclasses.asdict(Profile()):raise Refused('exact_profile_required')
  if any(type(x) is not int for x in dataclasses.asdict(self).values()):raise Refused('typed_profile_required')
  return self

def private_directory(path,uid):
 p=Path(path)
 if str(p)!=os.path.realpath(p):raise Refused('symlink_path')
 for parent in [p,*p.parents]:
  s=os.lstat(parent)
  if not stat.S_ISDIR(s.st_mode) or s.st_uid not in (0,uid) or s.st_mode&0o022:raise Refused('unsafe_directory')
 s=os.lstat(p)
 if s.st_uid!=uid or stat.S_IMODE(s.st_mode)!=0o700:raise Refused('private_directory_required')

def protected_read(path,*,uid=None,limit=4096,secret=True):
 """Actual effective UID; open every ancestor via held no-follow directory FD."""
 uid=os.geteuid() if uid is None else uid
 if uid!=os.geteuid():raise Refused('actual_uid_required')
 p=Path(path)
 if not p.is_absolute() or '..' in p.parts or str(p)!=os.path.realpath(p):raise Refused('canonical_absolute_required')
 directories=[];fd=None
 try:
  d=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW);directories.append(d)
  for part in p.parts[1:-1]:
   d=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=d);directories.append(d);s=os.fstat(d)
   if s.st_uid not in (0,uid) or s.st_mode&0o022:raise Refused('unsafe_credential_parent')
  fd=os.open(p.name,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=d);a=os.fstat(fd)
  if not stat.S_ISREG(a.st_mode) or a.st_nlink!=1 or a.st_uid!=uid or stat.S_IMODE(a.st_mode) not in (0o400,0o600) or a.st_size>limit:raise Refused('protected_credential_required')
  raw=os.read(fd,limit+1);z=os.fstat(fd);lookup=os.stat(p.name,dir_fd=d,follow_symlinks=False)
  original=(a.st_dev,a.st_ino,a.st_size,a.st_mtime_ns,a.st_ctime_ns)
  if original!=(z.st_dev,z.st_ino,z.st_size,z.st_mtime_ns,z.st_ctime_ns) or (lookup.st_dev,lookup.st_ino)!=(a.st_dev,a.st_ino):raise Refused('credential_changed')
 finally:
  if fd is not None:os.close(fd)
  for d in reversed(directories):os.close(d)
 if len(raw)>limit:raise Refused('credential_cap')
 if not secret:return raw
 try:value=raw.decode('ascii')
 except UnicodeError:raise Refused('credential_encoding')
 # Existing openssl-generated protected leaves have one terminal LF. Preserve
 # the file/descriptor identity and normalize only this storage delimiter.
 if value.endswith('\n'):value=value[:-1]
 if not re.fullmatch(r'[\x21-\x7e]{16,256}',value):raise Refused('credential_format')
 return value

def load_libraries(directory):
 from trusted_imports import protected_bytes,install
 p=Path(directory);uid=0 if str(p).startswith('/opt/') else os.geteuid();sources={}
 for name,digest in LIBRARY_HASHES.items():
  try:raw=protected_bytes(p/name,uid,131072)
  except (ValueError,OSError) as e:raise Refused('protected_library_graph') from e
  if hashlib.sha256(raw).hexdigest()!=digest:raise Refused('library_hash_mismatch')
  sources[name[:-3]]={'path':name,'sha256':digest,'bytes':len(raw)}
 try:install(p,{'schema':'h044-protected-imports-v1','modules':sources},uid)
 except ValueError as e:raise Refused('foreign_library_graph') from e
 import service,backend
 return service,backend

def validate_config(c):
 if c['activation']!='DISABLED_SOURCE_PREPARATION' or c['service']['enabled'] is not False:raise Refused('disabled_candidate_required')
 Profile(**c['profiles']['16k']).check()
 if set(c['profiles'])!={'16k'}:raise Refused('profile_set')
 s=c['service']
 expected={'serviceId':'h043-technical-vision-candidate','generation':1,'mode':'live','interpreter':{'model':'Qwen/Qwen3.5-9B','revision':REV_QWEN,'precision':'BF16'},'parser':{'model':'PaddlePaddle/PaddleOCR-VL-1.6','revision':REV_OCR}}
 if {k:s[k] for k in expected}!=expected:raise Refused('service_identity_mismatch')
 if (s['listenOrigin'],s['qwenOrigin'],s['ocrOrigin'])!=('http://127.0.0.1:18193','http://127.0.0.1:18191','http://127.0.0.1:18192'):raise Refused('fixed_origin_required')
 if any(type(s[k]) is not int for k in ('generation','requestDeadlineSeconds','jobDeadlineSeconds','queueCap','jobHistoryCap','privateLedgerBytes')):raise Refused('typed_service_limits')
 if (s['requestDeadlineSeconds'],s['jobDeadlineSeconds'],s['queueCap'],s['jobHistoryCap'],s['privateLedgerBytes'])!=(10,120,4,128,268435456):raise Refused('service_bounds')
 return expected

def audited_backend(module,identity,reader,config):
 """Extend reviewed backend transport with exact raw-byte checkpoints, no backend bypass."""
 import http.client,types
 local=threading.local();original=http.client.HTTPConnection
 class CapturedResponse:
  def __init__(self,response):self.response=response;self.chunks=[];self.eofObserved=False;self.originalLength=response.length
  def read1(self,n):
   b=self.response.read1(n);self.chunks.append(b);self.eofObserved=self.eofObserved or b==b'';return b
  def complete_body(self):
   # Content-length framing can be drained while HTTPResponse.fp remains open
   # on Python3.9. isclosed is a transport property, not body-byte evidence.
   return self.eofObserved and (self.originalLength is None or sum(map(len,self.chunks))==self.originalLength)
  def __getattr__(self,k):return getattr(self.response,k)
 class CapturedConnection(original):
  def getresponse(self):
   r=CapturedResponse(super().getresponse());local.response=r;return r
 # Only this verified backend module's private http reference changes. Global HTTP
 # modules and ingress/workload processes retain their own reviewed transports.
 module.http=types.SimpleNamespace(client=types.SimpleNamespace(HTTPConnection=CapturedConnection))
 class AuditedBackend(module.LocalVisionBackend):
  def _call(self,role,model,png,prompt,deadline,checkpoint,context):
   local.response=None;complete=[False]
   def evidence(value):
    if value.get('kind')=='model_response':
     r=local.response
     if r is None or not r.complete_body():raise module.BackendFailure(False)
     raw=b''.join(r.chunks)
     if hashlib.sha256(raw).hexdigest()!=value['responseSha256']:raise module.BackendFailure(False)
     complete[0]=True
     value=dict(value,rawResponseHex=raw.hex(),inputPngSHA256=hashlib.sha256(png).hexdigest())
    checkpoint(value)
   try:return super()._call(role,model,png,prompt,deadline,evidence,context)
   finally:
    if not complete[0] and local.response is not None:
     r=local.response;raw=b''.join(r.chunks)
     checkpoint(dict(kind='model_response_failure',role=role,model=model,revision=self.service['interpreter' if role=='interpretation' else 'parser']['revision'],rawResponseHex=raw.hex(),responseSha256=hashlib.sha256(raw).hexdigest(),completeBodyObserved=r.complete_body(),nativeSettlement='UNKNOWN',inputPngSHA256=hashlib.sha256(png).hexdigest(),**context))
 return AuditedBackend(identity,reader,qwen_origin=config['service']['qwenOrigin'],ocr_origin=config['service']['ocrOrigin'],enabled=False)

class ServiceRuntime:
 def __init__(self,config,library_directory,ledger_directory,credential_reader=None):
  # Construction itself is inert with respect to model calls, while binding real APIs.
  self.identity=validate_config(config);self.uid=os.geteuid();private_directory(ledger_directory,self.uid)
  service,backend=load_libraries(library_directory);self.reader=credential_reader or (lambda role:protected_read(SECRET_PATHS[role]))
  self.ledger=service.PrivateLedger(ledger_directory,max_jobs=128,max_bytes=268435456)
  self.backend=audited_backend(backend,self.identity,self.reader,config)
  self.service=service.VisionService(self.ledger,self.identity,self.backend,enabled=False,queue_cap=4,job_timeout=120)
  self.http=None;self.closed=False;self.authorized=False
 def bind(self):
  # Binding fixed authenticated loopback remains a live action; never implicit in construct.
  if not self.authorized:raise Refused('authentic_current_root_ticket_required')
  module=sys.modules['service'];self.http=module.BoundedHTTPServer(('127.0.0.1',18193),self.service,self.reader('service'),request_seconds=10)
  return self.http
 def close(self,timeout=5):
  self.service.enabled=False;self.backend.ready=False
  if self.http:self.http.server_close()
  drained=self.service.close(timeout)
  unsettled=self.service.blocked()
  result={'serviceUid':self.uid,'workerDrained':drained,'ledgerUnsettled':unsettled,'nativeEngineSettlement':'NOT_PROVEN','admission':'CLOSED','state':'QUARANTINE' if unsettled or not drained else 'LOCAL_WORKER_CLOSED'}
  if drained and not self.closed:self.ledger.close();self.closed=True
  # Never clear/reconcile interrupted/cancelling records or infer native engine drain.
  return result

def serve(runtime,deadline_monotonic,normal_lease=None):
 if not runtime.authorized:raise Refused('execution_disabled_without_authentic_root_ticket')
 if not 0<deadline_monotonic-time.monotonic()<=600:raise Refused('finite_service_window_required')
 stop=threading.Event();previous={}
 def interrupt(*_):runtime.service.enabled=False;stop.set()
 for sig in (signal.SIGTERM,signal.SIGINT):previous[sig]=signal.signal(sig,interrupt)
 try:
  http=runtime.bind();http.timeout=.2
  while not stop.is_set() and (normal_lease.available() if normal_lease else time.monotonic()<deadline_monotonic):http.handle_request()
 finally:
  result=runtime.close()
  for sig,handler in previous.items():signal.signal(sig,handler)
 return result

def description():
 return {'executionEnabled':False,'sourceBindings':LIBRARY_HASHES,'serviceBind':'127.0.0.1:18193','models':['127.0.0.1:18191','127.0.0.1:18192'],'profile':dataclasses.asdict(Profile()),'credentialContext':'actual effective UID; 0400/0600 single-link no-follow stable FD; protected ancestors','credentialPaths':SECRET_PATHS,'nativeSettlement':'NO_PROOF_FROM_HTTP_CLOSE','remoteIngress':'separate protected private-link+bearer fixed 10.156.100.60:18193 bridge required'}
def verify_signed_ticket(ticket,component,*,uid,now,boot,anchor_sha,signature_verifier):
 """Identity follows the reviewed signed proof only; producer/root euid is insufficient."""
 import control,datetime
 if not isinstance(ticket,dict) or set(ticket)!={'graph','goRawHex','signatureHex'}:raise Refused('ticket_fields')
 try:raw=bytes.fromhex(ticket['goRawHex']);signature=bytes.fromhex(ticket['signatureHex'])
 except (ValueError,TypeError):raise Refused('ticket_encoding')
 if len(raw)>1048576 or len(signature)!=64 or not signature_verifier(raw,signature):raise Refused('root_ticket_signature')
 graph=ticket['graph']
 try:control.validate_graph(graph);go=control.validate_carrier(raw,graph,anchor_sha,now,boot)
 except (control.Refused,KeyError,TypeError) as e:raise Refused('ticket_current_bindings') from e
 if uid!=1000 or graph['runtime']['service']['uid']!=1000 or graph['rootOwnerEvidence']['serviceUid']!=1000:raise Refused('exact_service_uid')
 action='inference' if component=='workload' else 'load'
 if component not in ('serve','ingress','health','workload') or action not in go['actions']:raise Refused('ticket_component_action')
 end=datetime.datetime.fromisoformat(go['actionDeadlines'][action]).timestamp()
 residence_end=datetime.datetime.fromisoformat(go['actionDeadlines']['inference']).timestamp() if component in ('serve','ingress') else end
 if not now<end or not 0<residence_end-now<=600:raise Refused('finite_service_ticket')
 if any(graph['gates'].get(x)!='PASS' for x in control.GATES):raise Refused('current_runtime_gates')
 exact={k:'/data/services/h044-vision-v03/credentials/vision-'+k+'.key' for k in ('service','interpretation','ocr')}
 if graph['runtime']['service']['credentialPaths']!=exact:raise Refused('exact_native_credential_mapping')
 return {'graph':graph,'go':go,'end':residence_end,'proofSHA256':hashlib.sha256(raw).hexdigest(),'component':component,'actualUid':uid,'identityOrigin':'REVIEWED_SIGNED_ROOT_PROOF'}


def approved_component(component):
 import control,trusted_imports
 raw=sys.stdin.buffer.read(1048577)
 if len(raw)>1048576:raise Refused('ticket_cap')
 try:ticket=control.parse_proof(raw)
 except control.Refused as e:raise Refused('ticket_json') from e
 base=control.SOURCE_ROOT;private='/data/services/h044-vision-v03';ledger_path=private+'/control-ledger'
 if os.geteuid()!=1000:raise Refused('exact_service_uid_roots')
 anchor=Path(control.TRUST_ANCHOR);anchor_sha=control.trusted_anchor();private_directory(ledger_path,1000)
 def verify(go_raw,signature):
  with tempfile.TemporaryDirectory(prefix='.verify-',dir=ledger_path) as d:
   os.chmod(d,0o700);g=Path(d)/'carrier';sig=Path(d)/'signature';g.write_bytes(go_raw);sig.write_bytes(signature);os.chmod(g,0o600);os.chmod(sig,0o600)
   c=subprocess.run(['/usr/bin/openssl','pkeyutl','-verify','-pubin','-inkey',str(anchor),'-rawin','-in',str(g),'-sigfile',str(sig)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=5)
   return c.returncode==0
 proof=verify_signed_ticket(ticket,component,uid=os.geteuid(),now=time.time(),boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),anchor_sha=anchor_sha,signature_verifier=verify)
 graph=proof['graph'];control.verify_source(graph,base,base+'/scripts/h044/vision_runtime')
 # Distinct durable claims permit the concurrent components; each may execute once.
 claim=Path(ledger_path)/('ticket-'+proof['go']['nonce']+'-'+component+'.json')
 try:control.exclusive(claim,{'component':component,'proofSHA256':proof['proofSHA256'],'uid':os.geteuid(),'bootId':proof['go']['bootId']})
 except FileExistsError:raise Refused('ticket_replay')
 credentials=graph['runtime']['service']['credentialPaths'];end=time.monotonic()+proof['end']-time.time()
 if component in ('health','workload'):
  import workload
  key=protected_read(credentials['service'])
  result=workload.health(graph,proof,end,lambda role:protected_read(credentials[role])) if component=='health' else workload.service_job(graph,proof,end,key)
  output=Path(ledger_path)/('component-'+proof['go']['nonce']+'-'+component+'.json');control.exclusive(output,result)
  return 0 if result.get('status') in ('HEALTHY','RESPONSE_ASSERTIONS_PASS') else 75
 if component=='ingress':
  import ingress
  import normal_service
  lease=normal_service.component_lease(graph,'ingress',proof['end'])
  s=graph['runtime']['ingress'];server=ingress.Server(protected_read(credentials['service']),s['clientIp'],s['protectedLinkAttestation'],end,proof=proof);server.timeout=.2
  closing=threading.Event();old={}
  def close_ingress(*_):closing.set()
  for sig in (signal.SIGTERM,signal.SIGINT):old[sig]=signal.signal(sig,close_ingress)
  try:
   while not closing.is_set() and lease.available():
    # Request admission follows authenticated steady lease after adoption.
    server.deadline=time.monotonic()+max(0,lease.deadline()-time.time());server.handle_request()
  finally:
   server.server_close()
   for sig,handler in old.items():signal.signal(sig,handler)
  return 0
 config=json.loads(trusted_imports.protected_bytes(Path(base)/'configs/vision/h043-candidate.json',0))
 runtime=ServiceRuntime(config,Path(base)/'scripts/vision',private+'/job-ledger',lambda role:protected_read(credentials[role]));runtime.authorized=True;runtime.backend.ready=True;runtime.service.enabled=True
 import normal_service
 lease=normal_service.component_lease(graph,'service',proof['end'])
 result=serve(runtime,end,lease);control.exclusive(Path(ledger_path)/('component-'+proof['go']['nonce']+'-serve.json'),result)
 return 0 if result['workerDrained'] and not result['ledgerUnsettled'] else 75


def approved_serve():return approved_component('serve')

def main():
 p=argparse.ArgumentParser();p.add_argument('--describe',action='store_true');group=p.add_mutually_exclusive_group()
 for name in ('serve','ingress','health','workload'):group.add_argument('--'+name,action='store_true')
 a=p.parse_args()
 for name in ('serve','ingress','health','workload'):
  if getattr(a,name):return approved_component(name)
 print(json.dumps(description(),indent=2));return 0

if __name__=='__main__':
 try:raise SystemExit(main())
 except Refused as e:print(str(e),file=sys.stderr);raise SystemExit(78)
