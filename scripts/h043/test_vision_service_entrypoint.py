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

import copy,dataclasses,hashlib,importlib.util,json,os,stat,sys,tempfile,time,unittest
from pathlib import Path
import vision_service_entrypoint as e
ROOT=Path(__file__).resolve().parents[2]
class EntryTests(unittest.TestCase):
 def config(self):return json.loads((ROOT/'configs/vision/h043-candidate.json').read_text())
 def test_disabled_entry_and_profile(self):
  self.assertFalse(e.EXECUTION_ENABLED);self.assertEqual(e.Profile().check().maxImagePixels,2097152)
  for kwargs in ({'maxImagePixels':2097153},{'concurrencyPerService':True},{'qwenTotalTokens':8192},{'cropsPerRequest':9}):
   with self.assertRaises(e.Refused):e.Profile(**kwargs).check()
 def test_exact_identity_and_ports(self):
  c=self.config();self.assertEqual(e.validate_config(c)['generation'],1)
  for key,value in [('enabled',True),('qwenOrigin','http://127.0.0.1:1'),('generation',True),('jobDeadlineSeconds',121)]:
   changed=copy.deepcopy(c);changed['service'][key]=value
   with self.assertRaises(e.Refused):e.validate_config(changed)
 def test_library_bindings_and_no_model_contact(self):
  service,backend=e.load_libraries(ROOT/'scripts/vision');self.assertEqual(backend.QWEN_REV,e.REV_QWEN)
  bad=copy.deepcopy(e.LIBRARY_HASHES);bad['service.py']='0'*64
  original=e.LIBRARY_HASHES;e.LIBRARY_HASHES=bad
  try:
   with self.assertRaises(e.Refused):e.load_libraries(ROOT/'scripts/vision')
  finally:e.LIBRARY_HASHES=original
 def test_actual_private_reader_and_unsafe_files(self):
  # Exact private test TMPDIR is root-sticky ancestry; this strict production reader
  # refuses it. Positive reader fixtures use protected phase path, no new credentials.
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'key';p.write_text('EXPLICIT-FAKE-TEST-KEY-0001');os.chmod(p,0o600)
   with self.assertRaises(e.Refused):e.protected_read(p)
   with self.assertRaises(e.Refused):e.protected_read(p,uid=os.geteuid()+1)
 def test_positive_actual_uid_private_reader(self):
  p=ROOT.parent/'output'/'FAKE-key-fixture'
  try:
   p.write_text('EXPLICIT-FAKE-TEST-KEY-0001');os.chmod(p,0o600)
   self.assertEqual(e.protected_read(p),'EXPLICIT-FAKE-TEST-KEY-0001')
   os.chmod(p,0o644)
   with self.assertRaises(e.Refused):e.protected_read(p)
  finally:p.unlink(missing_ok=True)
 def test_saved_credential_single_terminal_lf_without_rewriting(self):
  p=ROOT.parent/'output'/'FAKE-key-LF-fixture'
  try:
   token='EXPLICIT-FAKE-TEST-KEY-0001';p.write_text(token+'\n');os.chmod(p,0o600)
   before=p.read_bytes();inode=p.stat().st_ino
   self.assertEqual(e.protected_read(p),token)
   self.assertEqual(p.read_bytes(),before);self.assertEqual(p.stat().st_ino,inode)
   for bad in (token+'\n\n',token+'\r\n',' '+token,token+' ',token[:8]+'\n'+token[8:]):
    p.write_text(bad)
    with self.assertRaises(e.Refused):e.protected_read(p)
  finally:p.unlink(missing_ok=True)
 def test_concrete_disabled_construct_and_close(self):
  # Use fixed private phase directory rather than weakening ancestor requirements.
  p=ROOT.parent/'output'/'test-ledger';p.mkdir(mode=0o700)
  try:
   runtime=e.ServiceRuntime(self.config(),ROOT/'scripts/vision',p,lambda role:'EXPLICIT-FAKE-TEST-KEY-0001')
   self.assertFalse(runtime.service.capabilities()['admitting'])
   with self.assertRaises(e.Refused):runtime.bind()
   result=runtime.close();self.assertTrue(result['workerDrained']);self.assertEqual(result['nativeEngineSettlement'],'NOT_PROVEN')
  finally:
   for f in p.iterdir():f.unlink()
   p.rmdir()

class SignedTicketTests(unittest.TestCase):
 def setUp(self):
  import control
  from test_trusted_imports import recorded_command
  self.run=recorded_command;self.control=control;self.d=tempfile.TemporaryDirectory(dir=ROOT.parent/'output');self.path=Path(self.d.name);self.openssl='/opt/homebrew/opt/openssl@3/bin/openssl'
  # Ephemeral explicit fake fixture key; never an existing user/service credential.
  self.key=self.path/'EXPLICIT-FAKE.private';self.pub=self.path/'EXPLICIT-FAKE.pub'
  self.assertEqual(self.run([self.openssl,'genpkey','-algorithm','ED25519','-out',str(self.key)]).returncode,0)
  self.assertEqual(self.run([self.openssl,'pkey','-in',str(self.key),'-pubout','-out',str(self.pub)]).returncode,0)
  self.anchor=hashlib.sha256(self.pub.read_bytes()).hexdigest();self.now=time.time();self.graph=json.loads((ROOT.parent/'output/RUNTIME-GRAPH.json').read_text());self.graph['gates']={k:'PASS' for k in self.graph['gates']}
  self.go={'schema':'h044-finite-root-go-v1','nonce':'d'*64,'notBefore':self.iso(-1),'expires':self.iso(100),'bootId':'EXPLICIT_FAKE_BOOT','graphSHA256':control.sha(control.canonical(self.graph)),'ownedTupleSHA256':control.sha(control.canonical(self.graph['rootOwnerEvidence'])),'actions':['load','inference','stop'],'actionDeadlines':{k:self.iso(n) for k,n in [('load',20),('inference',60),('stop',90)]},'counts':{'load':1,'inference':1,'stop':1},'issuer':'ROOT_AUTHENTIC_SIGNER','rootCarrierSHA256':self.anchor}
 def tearDown(self):self.d.cleanup()
 def iso(self,n):return __import__('datetime').datetime.fromtimestamp(self.now+n,__import__('datetime').timezone.utc).isoformat()
 def ticket(self,go=None):
  go=go or self.go;raw=self.control.canonical(go);f=self.path/'go';f.write_bytes(raw);signed=self.run([self.openssl,'pkeyutl','-sign','-rawin','-inkey',str(self.key),'-in',str(f)]);self.assertEqual(signed.returncode,0)
  return {'graph':copy.deepcopy(self.graph),'goRawHex':raw.hex(),'signatureHex':signed.stdout.hex()}
 def verify(self,raw,sig):
  f=self.path/'verify-go';s=self.path/'verify-sig';f.write_bytes(raw);s.write_bytes(sig)
  return self.run([self.openssl,'pkeyutl','-verify','-pubin','-inkey',str(self.pub),'-rawin','-in',str(f),'-sigfile',str(s)]).returncode==0
 def proof(self,ticket=None,**changes):
  kwargs=dict(uid=1000,now=self.now,boot='EXPLICIT_FAKE_BOOT',anchor_sha=self.anchor,signature_verifier=self.verify);kwargs.update(changes)
  return e.verify_signed_ticket(ticket or self.ticket(),'serve',**kwargs)
 def test_signed_positive_and_root_uid_denial(self):
  p=self.proof();self.assertEqual(p['identityOrigin'],'REVIEWED_SIGNED_ROOT_PROOF');self.assertEqual(p['actualUid'],1000)
  with self.assertRaises(e.Refused):self.proof(uid=0)
 def test_expiry_currentboot_signature_malformed_and_source_binding(self):
  t=self.ticket()
  for changed in (dict(t,signatureHex='00'*64),dict(t,signatureHex='bad'),dict(t,goRawHex='bad'),dict(t,unexpected=True)):
   with self.assertRaises(e.Refused):self.proof(changed)
  with self.assertRaises(e.Refused):self.proof(t,now=self.now+101)
  with self.assertRaises(e.Refused):self.proof(t,boot='different-current-boot')
  changed=copy.deepcopy(t);changed['graph']['sourceManifest']['scripts/h043/vision_service_entrypoint.py']='0'*64
  with self.assertRaises(e.Refused):self.proof(changed)
  for k,value in [('counts',{'load':True,'inference':1,'stop':1}),('nonce','old-nonce'),('issuer','WORKER_PRODUCER')]:
   g=copy.deepcopy(self.go);g[k]=value
   with self.assertRaises(e.Refused):self.proof(self.ticket(g))
 def test_durable_signed_ticket_replay_denied(self):
  from unittest import mock
  p=self.proof();claim=self.path/('ticket-'+p['go']['nonce']+'-serve.json');self.control.exclusive(claim,{'proofSHA256':p['proofSHA256']})
  with self.assertRaises(FileExistsError):self.control.exclusive(claim,{'proofSHA256':p['proofSHA256']})
 def test_actual_serve_cli_positive_with_native_boundaries_explicitly_mocked(self):
  import io
  from unittest import mock
  self.graph['rootCarrier']['publicKeyPath']=str(self.pub);self.go['graphSHA256']=self.control.sha(self.control.canonical(self.graph))
  t=self.ticket();cfg=json.loads((ROOT/'configs/vision/h043-candidate.json').read_text());original_read=Path.read_text;written=[]
  def read(path,*a,**k):return 'EXPLICIT_FAKE_BOOT' if str(path)=='/proc/sys/kernel/random/boot_id' else original_read(path,*a,**k)
  # This genuine -I test process invokes the real --serve parser/signature path.
  # Only inaccessible Linux UID/filesystem/native server boundaries are fixtures.
  fake=type('Runtime',(),{'backend':type('Backend',(),{})(),'service':type('Service',(),{})()})()
  td=tempfile.TemporaryDirectory
  def verifier_dir(*a,**k):return td(dir=self.path)
  import trusted_imports
  with mock.patch.object(e.sys,'argv',['entry','--serve']),mock.patch.object(e.sys,'stdin',type('Input',(),{'buffer':io.BytesIO(self.control.canonical(t))})()),mock.patch.object(e.os,'geteuid',return_value=1000),mock.patch.object(e,'private_directory'),mock.patch.object(self.control,'TRUST_ANCHOR',str(self.pub)),mock.patch.object(self.control,'trusted_anchor',return_value=self.anchor),mock.patch.object(e.tempfile,'TemporaryDirectory',side_effect=verifier_dir),mock.patch.object(e.subprocess,'run',side_effect=lambda argv,**kwargs:self.run([self.openssl,*argv[1:]])),mock.patch.object(Path,'read_text',read),mock.patch.object(self.control,'verify_source'),mock.patch.object(self.control,'exclusive',side_effect=lambda p,v:written.append((str(p),v))),mock.patch.object(trusted_imports,'protected_bytes',return_value=self.control.canonical(cfg)),mock.patch.object(e,'ServiceRuntime',return_value=fake),mock.patch.object(e,'serve',return_value={'workerDrained':True,'ledgerUnsettled':False}):
   self.assertEqual(e.main(),0)
  self.assertEqual(len(written),2);self.assertIn('ticket-',written[0][0]);self.assertEqual(written[0][1]['uid'],1000)


class RawCaptureTests(unittest.TestCase):
 def test_actual_loopback_raw_bytes_and_failure_checkpoint(self):
  import http.server,threading
  cfg=json.loads((ROOT/'configs/vision/h043-candidate.json').read_text());identity=e.validate_config(cfg);_,backend=e.load_libraries(ROOT/'scripts/vision')
  for malformed in (False,True):
   literal=json.dumps({'description':'EXPLICIT_SOURCE_FIXTURE','uncertainties':['Unqualified source fixture'],'derivedConclusions':[]})
   raw=b'{ malformed source fixture' if malformed else json.dumps({'model':backend.QWEN,'choices':[{'index':0,'message':{'role':'assistant','content':literal},'finish_reason':'stop'}]},indent=2).encode()
   class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self,*_):pass
    def do_POST(self):
     self.rfile.read(int(self.headers['Content-Length']));self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
   server=http.server.HTTPServer(('127.0.0.1',0),Handler);port=server.server_address[1];thread=threading.Thread(target=server.handle_request);thread.start();events=[]
   audit=e.audited_backend(backend,identity,lambda _:'EXPLICIT-FAKE-KEY-0001',cfg);audit.endpoints['interpretation']=port
   self.control=__import__('control');self.control.exclusive(ROOT.parent/'output'/('raw-socket-'+__import__('secrets').token_hex(8)+'.json'),{'kind':'TCP_LOOPBACK_SOURCE_FIXTURE','address':'127.0.0.1','port':port,'unixSocketPaths':[],'TMPDIR':os.environ.get('TMPDIR')})
   try:
    if malformed:
     with self.assertRaises(backend.BackendFailure):audit._call('interpretation',backend.QWEN,b'fake-source-pixels','fixture',time.monotonic()+2,events.append,{'sourceSha256':'f'*64})
    else:audit._call('interpretation',backend.QWEN,b'fake-source-pixels','fixture',time.monotonic()+2,events.append,{'sourceSha256':'f'*64})
    observed=next(x for x in events if x['kind']==('model_response_failure' if malformed else 'model_response'));self.assertEqual(bytes.fromhex(observed['rawResponseHex']),raw);self.assertEqual(observed['responseSha256'],hashlib.sha256(raw).hexdigest())
   finally:thread.join(timeout=2);server.server_close()
   self.assertFalse(thread.is_alive())

if __name__=='__main__':unittest.main()
