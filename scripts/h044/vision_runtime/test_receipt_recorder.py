"""Actual local child fault tests. Fixtures never qualify native/runtime ownership."""
import json,os,signal,sys,tempfile,time,unittest
from pathlib import Path
from unittest import mock
import receipt_recorder as r
OUT=Path(__file__).absolute().parents[3].parent/'output'
class ReceiptTests(unittest.TestCase):
 def run_record(self,code,**kw):
  env={k:os.environ[k] for k in ('PATH','TMPDIR','LANG') if k in os.environ}
  return r.record([sys.executable,'-I','-c',code],OUT/'recorder-fault-tests',environment=env,timeout=2,label='source-fixture',evidence='SOURCE_ONLY_FIXTURE_INJECTED_BOUNDARIES',**kw)
 def assert_wait(self,result):
  self.assertTrue(result['waited']);self.assertIs(type(result['actualExitCode']),int)
  self.assertIsNone(r.birth(result['pid']))
 def test_original_nonzero_bytes_and_birth(self):
  x=self.run_record("import sys;sys.stdout.buffer.write(b'original\\x00out');sys.stderr.write('err');sys.exit(7)")
  self.assertEqual(x['status'],'COMPLETE');self.assertEqual(x['actualExitCode'],7);self.assert_wait(x)
  self.assertEqual(Path(x['stdout']['path']).read_bytes(),b'original\x00out');self.assertTrue(x['absence']['recordedGroupAbsent']);self.assertTrue(x['birth'])
 def test_every_failure_after_popen_settles_known_direct_child(self):
  for point in ('after_popen','before_birth','after_birth','metadata_write','before_log_write','log_write','final_write'):
   with self.subTest(point=point):
    def fault(p):
     if p==point:raise OSError('INJECTED_SOURCE_ONLY_'+p)
    x=self.run_record("import time;print('captured',flush=True);time.sleep(10)",fault=fault)
    self.assert_wait(x);self.assertEqual(x['status'],'PARTIAL');self.assertTrue(x['errors'])
    if point=='after_popen':self.assertIn('birth',x['missing'])
    if point=='final_write':
     self.assertTrue(x['settlementFallbackPath']);saved=json.loads(Path(x['settlementFallbackPath']).read_text());self.assertTrue(saved['waited']);self.assertIs(type(saved['actualExitCode']),int);self.assertEqual(saved['status'],'PARTIAL')
    if point=='before_log_write':self.assertIn(b'captured',bytes.fromhex(x['pendingOutput']['originalBytesHex']))
 def test_prefork_failure_never_invents_wait(self):
  for point in ('before_logs','before_popen'):
   def fault(p):
    if p==point:raise OSError('INJECTED_SOURCE_ONLY')
   x=self.run_record('pass',fault=fault);self.assertIsNone(x['pid']);self.assertFalse(x['waited']);self.assertIsNone(x['actualExitCode']);self.assertIn('directChildWait',x['missing'])
 def test_closed_output_pipes_still_wait_and_timeout(self):
  x=self.run_record("import os,time;os.close(1);os.close(2);time.sleep(10)")
  self.assert_wait(x);self.assertEqual(x['status'],'PARTIAL');self.assertLess(x['actualExitCode'],0)
 def test_output_cap_keeps_original_crossing_chunk(self):
  x=self.run_record("import sys,time;sys.stdout.write('x'*20000);sys.stdout.flush();time.sleep(10)",output_cap=32)
  self.assert_wait(x);self.assertGreater(Path(x['stdout']['path']).stat().st_size,32);self.assertEqual(x['status'],'PARTIAL')
 def test_birth_capture_failure_and_reuse_never_signal_guessed_group(self):
  original=r.birth;calls=[]
  def inconsistent(pid):
   b=original(pid)
   if b is not None:
    calls.append(pid)
    if len(calls)>1:return {'kind':'INJECTED_SOURCE_ONLY_REUSED'}
   return b
  with mock.patch.object(r,'birth',side_effect=inconsistent),mock.patch.object(r.os,'killpg',side_effect=AssertionError('guessed group signalled')):
   x=self.run_record("import time;time.sleep(10)")
  self.assert_wait(x);self.assertTrue(x['waited']);self.assertLess(x['actualExitCode'],0)
 def test_unrelated_pid_survives_fault(self):
  # Another recorder has sole ownership of this independent child; no guessed
  # external pid/group is accepted by record(). Actual separate receipt retained.
  import threading
  holder={};started=threading.Event()
  def other():
   def fault(point):
    if point=='after_birth':started.set()
   holder['r']=self.run_record('import time;time.sleep(.8)',fault=fault)
  t=threading.Thread(target=other);t.start();self.assertTrue(started.wait(2))
  x=self.run_record('pass',fault=lambda p:(_ for _ in ()).throw(OSError('fixture')) if p=='before_birth' else None)
  t.join(3);self.assertFalse(t.is_alive());self.assertEqual(holder['r']['actualExitCode'],0);self.assert_wait(x)
 def test_stdin_original_hash_and_large_payload(self):
  payload=b'k'*200000
  x=self.run_record('import sys;print(len(sys.stdin.buffer.read()))',stdin_data=payload)
  self.assertEqual(x['status'],'COMPLETE');self.assertEqual(Path(x['stdout']['path']).read_bytes(),b'200000\n');self.assertEqual(x['stdin']['bytes'],len(payload))
if __name__=='__main__':unittest.main()
