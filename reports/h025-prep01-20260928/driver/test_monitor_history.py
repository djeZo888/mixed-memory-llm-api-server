"""Real confined journals, complete request lifecycles and failed monitoring."""
import json,os,threading,types,unittest
from pathlib import Path
from unittest.mock import patch
import controller
from test_driver import Clock,manifest,go,proof,sample,Response,sse
from test_repairs import SyntheticMountPathTests,AnchoredRoot,StorageIOError
from primitives import Journal,capture_text
from contract import LANES,text_body,canonical,Refusal
from runner import Runner

class MonitorHistory(unittest.TestCase):
 def phase(self):
  f=SyntheticMountPathTests();f.setUp();self.addCleanup(f.doCleanups)
  self.c=Clock();self.m=manifest();self.m['bounds']['max_requests_per_lane']=1000
  with patch.object(controller,'Journal',Journal):
   self.p=controller.Phase(self.m,go(self.m,self.c),'B','f'*64,f.data/'phase',self.c,
        storage_guard=f.guard,anchored_root=lambda p,g:AnchoredRoot(p,g,uid=os.geteuid()))
  self.p.observe(sample(self.m,self.c));self.p.release_barrier({l:proof(self.m,self.c,l) for l in LANES})
  return f
 def start(self,lane,prefix):
  p,m,c=self.p,self.m,self.c
  row,raw=p.prepare(lane,text_body(m,lane,prefix,'fixture corpus'),prefix,proof(m,c,lane))
  count=16384 if lane=='flash' else 4096
  p.counted(lane,dict(owner_id=row['owner_id'],identity=row['identity'],observed=c(),body_sha256=row['body_sha256'],count_body_sha256=row['count_body_sha256'],native=True,http_status=200,endpoint=m['lanes'][lane]['count_path'],response={m['lanes'][lane]['count_field']:count}))
  p.begin_send(lane,raw,proof(m,c,lane));return p.body_sent(lane),count
 def test_long_history_exceeds_old_cap_but_compact_status_and_recoverable_chunks(self):
  self.phase();p,m,c=self.p,self.m,self.c
  for n in range(420):
   row,count=self.start('qwen0','fresh-'+str(n));c.advance(.01)
   capture_text(Response(sse(count)),row,count,128,c);p.http_finished('qwen0',row)
   receipt=proof(m,c,'qwen0');receipt.update(request_id=row['request_id'],ownership_released=True,resident=True,disposition='COMPLETED')
   p.settled('qwen0',receipt);p.observe(sample(m,c))
   self.assertLess((p.journal.path/'STATUS.json').stat().st_size,16384)
  self.assertGreater(len(canonical(p.requests)),1024*1024) # Old STATUS demonstrably fails.
  histories=sorted(p.journal.path.glob('REQUESTS-*.jsonl'))
  self.assertGreater(len(histories),1)
  records=[json.loads(line) for path in histories for line in path.read_text().splitlines()]
  self.assertEqual(len(records),420);self.assertTrue(all(r['state']=='SETTLED' for r in records))
  self.assertTrue(all(path.stat().st_size<=512*1024 for path in histories))
  self.assertFalse(p.first_failure);self.assertFalse(p.active)
 def test_actual_guard_rejects_old_oversized_status_without_widening(self):
  self.phase()
  with self.assertRaises(StorageIOError):self.p.journal.write('OLD-STATUS',{'history':'x'*(1024*1024)})
 def monitor_failure(self,kind):
  f=self.phase();p=self.p
  self.start('qwen0','owned-q0');self.start('qwen1','owned-q1')
  calls=[];done=threading.Event()
  def stop(lane,intent):
   calls.append((lane,intent['request_id']));return dict(intent=intent,physical_stop_proven=True,observed=self.c())
  def failed_sample(due):
   if kind=='read':raise TimeoutError('fixture transport failure')
   return sample(self.m,self.c)
  a=types.SimpleNamespace(sample=failed_sample,stop_exact=stop);r=Runner(p,a)
  # For mount loss every subsequent append/status/stop-receipt persist fails.
  if kind=='mount':f._mount('phase')
  t=threading.Thread(target=r.monitor);t.start()
  for _ in range(100):
   if len(calls)==2 and not p.active:break
   done.wait(.01)
  r.finished.set();t.join(2)
  for stop_thread in r.stop_threads:stop_thread.join(2)
  self.assertFalse(t.is_alive());self.assertTrue(p.admission_closed)
  self.assertEqual(sorted(l for l,_ in calls),['qwen0','qwen1']);self.assertFalse(p.active)
  first=dict(p.first_failure);r.dispatch_stops();p.fail('later_failure')
  self.assertEqual(first,p.first_failure);self.assertEqual(len(calls),2)
  self.assertNotIn('flash',p.stop_intents);self.assertNotIn('image',p.stop_intents)
  with self.assertRaises((Refusal,StorageIOError)):p.admission('qwen0')
 def test_monitor_read_failure_stops_and_settles_accepted_work(self):self.monitor_failure('read')
 def test_mount_loss_cannot_kill_monitor_before_owned_settlement(self):self.monitor_failure('mount')
 def test_five_global_swap_growth_intervals_stop_accepted_work(self):
  self.phase();self.start('qwen0','accepted')
  for n in range(1,6):
   self.c.advance(.1);s=sample(self.m,self.c);s['guest']['swap_out']=n;self.p.observe(s)
   self.assertEqual(bool(self.p.stop_intents),n==5)
  self.assertEqual(set(self.p.stop_intents),{'qwen0'})
 def test_failed_ambiguous_receipt_still_dispatches_exact_stop_once(self):
  self.phase();row,_=self.start('qwen0','accepted-write-failure');p=self.p
  original=p.journal.write
  def fail_request(name,value,**kw):
   if name==row['request_id']:raise OSError('fixture request receipt unavailable')
   return original(name,value,**kw)
  calls=[]
  def stop(lane,intent):
   calls.append(lane);return {'intent':intent,'physical_stop_proven':True,'observed':self.c()}
  with patch.object(p.journal,'write',fail_request):
   p.ambiguous('qwen0','original_transport_failure',{'done':True,'http_drained':False})
   r=Runner(p,types.SimpleNamespace(stop_exact=stop));r.dispatch_stops()
   for t in r.stop_threads:t.join(2)
  self.assertEqual(calls,['qwen0']);self.assertFalse(p.active)
  self.assertEqual(p.first_failure['reason'],'original_transport_failure')
  self.assertTrue(p.requests['qwen0'][0]['partial_capture']['done'])
 def test_history_record_and_total_bounds_fail_closed(self):
  self.phase();j=self.p.journal
  with self.assertRaises(Refusal):j.append('TELEMETRY',{'oversize':'x'*(256*1024)})
  j.history['TELEMETRY']=(5000,1,0,0)
  with self.assertRaises(Refusal):self.p.observe(sample(self.m,self.c))

if __name__=='__main__':unittest.main()
