"""Synthetic offline carrier/real helper ledger tests; never Linux qualification."""
import unittest,tempfile,sys,json,copy,os
from pathlib import Path
from unittest import mock
from contextlib import contextmanager
sys.path.insert(0,str(Path(__file__).parent))
import local_helper as helper
from qualification_carrier import CarrierPlan,QualificationCarrier,preserve_stopped_roots,tree_manifest,CarrierError
class Lease:
 def __init__(self):self.active=True
 def validate(self):
  if not self.active:raise Exception('inactive')
class Fixtures(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name).resolve();self.calls=[];self.lease=Lease();self.active={'load':'loaded','active':'active','sub':'running','invocation':'a'*32,'main_pid':123,'control_pid':0,'job_pending':False};self.state=copy.deepcopy(self.active);self.boot='00000000-0000-0000-0000-000000000001';self.acquires=0
  @contextmanager
  def acquire():
   self.acquires+=1
   try:yield self.lease
   finally:self.lease.active=False
  def execute(r):
   self.calls.append(r['action']);self.lease.validate();self.state.update(active='inactive',sub='dead',main_pid=0) if r['action']=='service.stop' else self.state.update(active='active',sub='running',main_pid=124,invocation='b'*32)
  self.ops=helper.Operations(self.root/'ops.sqlite',lambda:self.boot,lambda s:copy.deepcopy(self.state),execute,freeze=lambda r:{'app_state':'acknowledged'},lease=acquire);self.ops.refresh('harness');self.patch=mock.patch.object(helper,'validate_borrowed_canonical_lease',side_effect=lambda l:self.assertIs(l,self.lease));self.patch.start()
 def tearDown(self):self.patch.stop();self.ops.db.close();self.temp.cleanup()
 def request(self,verb,key):return {'schema_version':1,'node_id':'ai-harness','action':'service.'+verb,'service_id':'harness','idempotency_key':key,'expected_boot_id':self.boot,'expected_generation':self.ops.observations['harness']['generation'],'allow_interrupt':True}
 def test_actual_helper_borrows_without_reacquire_and_retains_once_only_audit(self):
  r=self.request('stop','fixture-stop01');a=self.ops.submit_under_lease(r,self.lease);self.assertEqual(a['status'],'succeeded');self.assertEqual(self.acquires,0);self.assertEqual(self.ops.submit_under_lease(r,self.lease),a);self.assertEqual(self.calls,['service.stop']);self.assertEqual(self.ops.db.execute('SELECT COUNT(*) FROM dispatches').fetchone()[0],1)
 def test_private_seam_rejects_reboot_restart_and_search(self):
  for action,service in [('service.restart','harness'),('service.stop','search'),('node.reboot',None)]:
   r=self.request('stop','fixture-stop02');r['action']=action
   if service:r['service_id']=service
   else:r.pop('service_id')
   with self.assertRaises(helper.Rejected):self.ops.submit_under_lease(r,self.lease)
  self.assertEqual(self.calls,[])
 def test_invalid_borrowed_object_never_reaches_execute(self):
  self.patch.stop()
  with self.assertRaises(helper.Rejected):self.ops.submit_under_lease(self.request('stop','fixture-stop03'),object())
  self.patch.start();self.assertEqual(self.calls,[])
 def test_stopped_full_tree_preserves_sqlite_and_all_sidecars_native_originals(self):
  source=self.root/'source';source.mkdir(mode=0o700);(source/'profile').mkdir(mode=0o700)
  for n in ['harness.sqlite','harness.sqlite-wal','harness.sqlite-shm','harness.sqlite-journal','owner.sqlite','profile/rollout.jsonl']:(source/n).write_bytes(n.encode())
  before=tree_manifest(source);receipt=preserve_stopped_roots((source,),self.root/'backup');self.assertEqual(tree_manifest(source),before);self.assertEqual(set(receipt[0]['manifest']),set(before));self.assertEqual((self.root/'backup/0/profile/rollout.jsonl').read_bytes(),b'profile/rollout.jsonl')
 def test_preservation_denies_symlink_and_hardlink_alias(self):
  source=self.root/'source';source.mkdir();(source/'original').write_text('retained');(source/'link').symlink_to(source/'original')
  with self.assertRaises(CarrierError):tree_manifest(source)
  (source/'link').unlink();os.link(source/'original',source/'link')
  with self.assertRaises(CarrierError):tree_manifest(source)
 def test_preservation_never_overwrites_old_evidence_or_copies_inside_original(self):
  source=self.root/'source';source.mkdir();dest=self.root/'existing';dest.mkdir()
  with self.assertRaises(CarrierError):preserve_stopped_roots((source,),dest)
  with self.assertRaises(CarrierError):preserve_stopped_roots((source,),source/'nested')
 def plan(self):
  source=self.root/'data';source.mkdir(mode=0o700);(source/'history').write_text('retained')
  stop=self.request('stop','fixture-carrier-stop');start=self.request('start','fixture-carrier-start');start['expected_generation']+=1
  return CarrierPlan('fixture-transaction',self.boot,stop,start,100,1000,800,120,(source,),self.root/'backup',self.root/'journal')
 def host(self,mode='pass'):
  fixture=self
  class Host:
   def assert_current(self,p,l,stage):fixture.assertIs(l,fixture.lease);l.validate();fixture.calls.append(stage)
   def assert_stopped_writers(self,p,l):fixture.assertEqual(fixture.state['active'],'inactive');l.validate()
   def run_owned_task(self,p,l):fixture.calls.append('task');l.validate();
   def settle_owned_task(self,p,l):fixture.calls.append('cleanup');l.validate();
   def assert_task_closed(self,p,l):
    if mode=='uncertain':raise Exception('unknown settlement')
   def assert_restored(self,p,l,b):fixture.assertEqual(fixture.state['active'],'active');return {'actualRecoveryDelta':'synthetic'}
   def retain_restore_needed(self,p,reason):fixture.calls.append('restore-needed')
  host=Host()
  if mode=='failed':host.run_owned_task=lambda p,l:(_ for _ in ()).throw(Exception('workload failed'))
  return host
 def test_one_lease_spans_real_stop_backup_task_cleanup_actual_restore(self):
  plan=self.plan();r=QualificationCarrier(self.ops,self.host(),clock=lambda:200).run(plan);self.assertEqual(r['status'],'settled');self.assertEqual(self.acquires,1);self.assertEqual(self.calls,['before-stop','service.stop','before-task','task','cleanup','before-restore','service.start']);self.assertTrue(plan.backup_root.exists())
 def test_failed_workload_restores_only_after_proved_cleanup_and_never_replays(self):
  plan=self.plan()
  with self.assertRaisesRegex(Exception,'workload failed'):QualificationCarrier(self.ops,self.host('failed'),clock=lambda:200).run(plan)
  self.assertIn('cleanup',self.calls);self.assertIn('service.start',self.calls);self.assertNotIn('restore-needed',self.calls)
  with self.assertRaises(FileExistsError):QualificationCarrier(self.ops,self.host(),clock=lambda:200).run(plan)
  self.assertEqual(self.calls.count('service.stop'),1)
 def test_unknown_task_close_does_not_race_normal_restore(self):
  plan=self.plan();carrier=QualificationCarrier(self.ops,self.host('uncertain'),clock=lambda:200)
  with self.assertRaisesRegex(Exception,'unknown settlement'):carrier.run(plan)
  self.assertNotIn('service.start',self.calls);self.assertIn('restore-needed',self.calls);self.assertTrue(plan.backup_root.exists());self.assertTrue(carrier.pending(plan.transaction_id));self.assertTrue(self.lease.active);carrier.host=self.host();restored=carrier.settle_pending(plan.transaction_id);self.assertEqual(restored['status'],'restored_no_replay');self.assertFalse(self.lease.active);self.assertFalse(carrier.pending(plan.transaction_id));self.assertEqual(self.calls.count('task'),1)
 def test_expiry_before_dispatch_cannot_stop_normal_unit(self):
  plan=self.plan()
  with self.assertRaises(CarrierError):QualificationCarrier(self.ops,self.host(),clock=lambda:900).run(plan)
  self.assertNotIn('service.stop',self.calls)
if __name__=='__main__':unittest.main()
