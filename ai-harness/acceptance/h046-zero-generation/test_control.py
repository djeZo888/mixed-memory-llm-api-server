"""Finite HMAC/source/claim SOURCE fixtures; no native or remote operation."""
import hashlib,hmac,importlib.util,json,os,sys,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
s=importlib.util.spec_from_file_location('h046control',Path(__file__).with_name('control.py'));c=importlib.util.module_from_spec(s);s.loader.exec_module(c)
class Controls(unittest.TestCase):
 def setUp(self):
  self.key=bytes(range(32));self.raw=b'{"SOURCE":"fixture"}';self.now=c.timestamp('2026-10-02T13:00:00Z')
  self.body=dict(schema='h046-zero-generation-go-v1',status='APPROVED',approvedBy='root',authority='H046',approvalId='a'*64,issuedAt='2026-10-02T12:59:59Z',notBefore='2026-10-02T13:00:00Z',dispatchCutoff='2026-10-02T13:01:00Z',expiresAt='2026-10-02T13:05:00Z',inputSha256=c.sha(self.raw),invocations={'nativeStart':1,'ownedShutdown':1,'initialize':1,'threadStart':1,'turnStart':0,'turnResume':0,'compact':0,'providerDispatch':0,'generation':0},cleanupReserveSeconds=130)
 def envelope(self,b=None):
  b=b or self.body;return c.canonical({'body':b,'seal':hmac.new(self.key,c.canonical(b).encode(),hashlib.sha256).hexdigest()}).encode()
 def test_exact_hmac_and_body_join(self):
  self.assertEqual(c.check_go(self.envelope(),self.key,self.raw,self.now)['approvalId'],'a'*64)
  for raw,key in [(b'changed',self.key),(self.raw,b'x'*32)]:
   with self.assertRaises(c.Denied):c.check_go(self.envelope(),key,raw,self.now)
 def test_stale_expired_not_before_reserve_window_and_generation(self):
  for delta in [-1,61,301]:
   with self.assertRaises(c.Denied):c.check_go(self.envelope(),self.key,self.raw,self.now+delta)
  for change in [{'cleanupReserveSeconds':0},{'invocations':dict(self.body['invocations'],nativeStart=True)},{'expiresAt':'2026-10-02T13:11:00Z'},{'status':'UNAPPROVED'},{'approvedBy':'worker1'},{'authority':'H044'},{'extra':True},{'invocations':dict(self.body['invocations'],generation=1)}]:
   with self.assertRaises(c.Denied):c.check_go(self.envelope(dict(self.body,**change)),self.key,self.raw,self.now)
 def test_duplicate_json_and_unsafe_numbers(self):
  with self.assertRaises(c.Denied):c.load(b'{"x":1,"x":2}')
  with self.assertRaises(c.Denied):c.canonical({'float':1.1})
 def test_once_only_claim_is_spent_even_failure(self):
  with tempfile.TemporaryDirectory() as td:
   path=Path(td)/'claim';c.write_once(path,{'status':'SPENT_BEFORE_START'})
   self.assertEqual(path.stat().st_mode&0o777,0o600)
   with self.assertRaises(FileExistsError):c.write_once(path,{'status':'retry'})
 def test_caller_owner_cannot_be_accepted(self):
  with patch.object(c,'birth',return_value={'pid':1,'uid':1000,'bootId':'new','startTicks':'22'}):
   self.assertFalse(c.present({'pid':1,'uid':1000,'bootId':'old','startTicks':'22'}))
   self.assertFalse(c.present({'pid':1,'uid':1000,'bootId':'new','startTicks':'11'}))
 def test_actual_integer_parent_wait_source_fixture(self):
  import subprocess
  p=subprocess.Popen([sys.executable,'-c','raise SystemExit(7)']);actual=p.wait(timeout=3)
  self.assertIs(type(actual),int);self.assertEqual(actual,7)
 def test_stale_source_rejected(self):
  with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as td:
   files={}
   for n in range(8):
    p=Path(td)/('source'+str(n));p.write_bytes(b'original');files[str(p.resolve())]=c.sha(b'original')
   p.write_bytes(b'changed')
   with self.assertRaisesRegex(c.Denied,'source/build/helper changed'):
    c.source_graph({'fileGraph':files,'fileGraphSha256':c.sha(c.canonical(files).encode())})
if __name__=='__main__':unittest.main()
