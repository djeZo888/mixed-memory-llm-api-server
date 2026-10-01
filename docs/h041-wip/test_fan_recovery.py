"""SOURCE synthetic/fresh-files tests only. No Linux, BMC, fan or unit action."""
import base64, copy, importlib.util, json, os, pathlib, stat, subprocess, tempfile, time, types, unittest
from unittest.mock import patch
p=pathlib.Path(__file__).resolve().parent;repo=p.parent/'repo';spec=importlib.util.spec_from_file_location('recovery',p/'fan_recovery.py');r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
reader=types.ModuleType('fixed_reader');reader.__file__=str(p/'fan-source.py');exec(compile((p/'fan-source.py').read_bytes(),reader.__file__,'exec'),reader.__dict__)
BOOT='17ac5d50-a6a4-4df1-8f9e-7bfc3db5f125';NOW=1790872800
iso=lambda n:r.datetime.fromtimestamp(n,r.timezone.utc).isoformat()
def snapshot(duty=100):
 pwm=[{'PWMName':'other'+str(i),'PWMNum':i,'PWMSrc':0,'CurrentPWMdata':[{'Temp':t,'Duty':100,'index':j} for j,t in enumerate((20,45,65,90,100))]} for i in range(8)];pwm[3]['PWMName']='Zone4(CHA_FAN3)'
 for x in pwm[3]['CurrentPWMdata'][:4]:x['Duty']=duty
 return dict(zip(reader.PATHS,({'FanMode':4},pwm,{'PWM4_1':0,'PWM4_2':0,'PWM4_3':0,'FanSourceList':[{'PWM':'PWM4','Name':'CHA_FAN3','Current':0}]},{'PWM4_LastSource':0,'PWM4_LastTemp':40})))
def physical(running=False,pid=123,inv='a'*32,uid=None):
 u={'Id':r.UNIT,'LoadState':'loaded','ActiveState':'active' if running else 'failed','SubState':'running' if running else 'failed','Result':'success' if running else 'exit-code','MainPID':str(pid) if running else '0','ExecMainPID':str(pid),'ExecMainStatus':'0' if running else '78','InvocationID':inv,'NRestarts':'0','ControlGroup':'/system.slice/'+r.UNIT if running else '', 'FragmentPath':r.UNIT_PATH,'User':'user','Group':'user','Restart':'on-failure','RestartUSec':'30s'}
 p={'pid':pid,'startTicks':'555','procStatUtf8':'SOURCE-only stat','procStatusUtf8':'Uid:\t%d\t%d\t%d\t%d\n'%((os.getuid() if uid is None else uid,)*4),'cmdlineBase64':base64.b64encode(b'/usr/bin/python3\0'+r.SOURCE.encode()+b'\0run\0').decode(),'exe':'/usr/bin/python3.12','bootId':BOOT} if running else None
 return {'unitUtf8':''.join(k+'='+u[k]+'\n' for k in r.PROPS),'bootIdUtf8':BOOT+'\n','cgroupProcsUtf8':str(pid)+'\n' if running else None,'process':p}
def readings(now=NOW,duty=100,temp=34):return {'readerSourceSha256':r.NEW,'snapshot':snapshot(duty),'tach':{'name':'CHA_FAN3','value':3360,'units':None,'at':iso(now)},'node':{'node_boot_id':BOOT,'temperature_c':temp,'telemetry_age_seconds':0,'sampled_at':iso(now)}}
class SOURCEBackend:
 reader=reader
 def __init__(self):self.p=physical();self.duty=100;self.events=[];self.on_physical=None
 def physical(self):
  if self.on_physical:self.on_physical()
  self.events.append('physical');return copy.deepcopy(self.p)
 def readings(self):self.events.append('readings');return readings(duty=self.duty)
 def start(self):self.events.append('start');raise AssertionError('SOURCE installer never starts')
 def stop(self):self.events.append('stop');raise AssertionError('SOURCE installer never stops')
class RecoveryTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.temp.name).resolve();self.parent_patch=patch.object(r,'parents_protected',lambda *a:None);self.parent_patch.start();self.chown_patch=patch.object(r.os,'chown',lambda *a:None);self.chown_patch.start()
  self.addCleanup(self.temp.cleanup);self.addCleanup(self.parent_patch.stop);self.addCleanup(self.chown_patch.stop)
 def fixture(self):
  d=self.root;state=d/'state';state.mkdir(mode=0o700);sp=d/'source-parent';sp.mkdir(mode=0o700);up=d/'unit-parent';up.mkdir(mode=0o700);bp=d/'private';bp.mkdir(mode=0o700);journal=bp/'journal';journal.mkdir(mode=0o700)
  old=subprocess.check_output(['git','show','ac46fb0^:scripts/thermal/cha_fan3.py'],cwd=repo);(sp/'source').write_bytes(old);(up/'unit').write_bytes((repo/'scripts/thermal/sova-cha-fan3.service').read_bytes());(bp/'new').write_bytes((p/'fan-source.py').read_bytes())
  for f in [sp/'source',up/'unit',bp/'new']:f.chmod(0o600)
  values={'blocked.json':{'reason':'SOURCE-original-retained'},'status.json':{'readback_duty':100},'pending-write.json':{'state':'verified'},'baseline.json':reader.invariant(snapshot())}
  for i in range(20):values['historical-%02d.json'%i]={'SOURCE-retained-history':i}
  for name,v in values.items():(state/name).write_bytes(r.encode(v));(state/name).chmod(0o600)
  (state/'controller.lock').write_bytes(b'');(state/'controller.lock').chmod(0o600)
  plan={'sourcePath':str(sp/'source'),'sourceParentPath':str(sp),'unitPath':str(up/'unit'),'unitParentPath':str(up),'statePath':str(state),'replacementPath':str(bp/'new'),'backupParentPath':str(bp),'backupPath':str(bp/'originals'),'journalPath':str(journal),'transactionId':'source-fixture-01','stateOwnerUid':os.getuid(),'stateOwnerGid':os.getgid(),'hostBootId':BOOT,'nodeBootId':BOOT,'invariantSha256':reader.digest(reader.invariant(snapshot())),'nonTargetSha256':reader.digest(reader.non_target(snapshot())),'failedUnitUtf8Sha256':r.sha(physical()['unitUtf8'].encode()),'stateFiles':{f.name:{'sha256':r.sha(f.read_bytes()),'bytes':len(f.read_bytes()),'metadata':r.metadata(f.stat())} for f in state.iterdir()}}
  plan['metadata']={k:r.metadata(pathlib.Path(plan[k+'Path']).stat()) for k in ['source','unit','replacement','state','sourceParent','unitParent','backupParent']};return plan
 def window(self):return r.Window({'issuedUtc':iso(NOW-1),'capUtc':iso(NOW+299),'settlementReserveMs':120000},now=lambda:NOW)
 def install(self,plan,backend=None):
  backend=backend or SOURCEBackend();fd=r.acquire(plan)
  try:return r.install(plan,backend,self.window(),r.Journal(plan['journalPath']),fd)
  finally:os.close(fd)
 def test_full25_original_CAS_and_own_phase_metadata_succeed_without_lifecycle(self):
  plan=self.fixture();backend=SOURCEBackend();result=self.install(plan,backend);self.assertEqual(len(plan['stateFiles']),25);self.assertEqual(r.sha(pathlib.Path(plan['sourcePath']).read_bytes()),r.NEW);self.assertEqual(r.sha(pathlib.Path(plan['unitPath']).read_bytes()),r.UNIT_SHA);self.assertEqual(len(list(pathlib.Path(plan['statePath']).iterdir())),24);self.assertEqual(pathlib.Path(plan['backupPath'],'original-blocker.archived').read_bytes(),r.encode({'reason':'SOURCE-original-retained'}));self.assertNotIn('start',backend.events);r.verify_tree(plan,installed=True,archived=True,phase=result['phase']);self.assertNotEqual(result['phase']['source']['st_ino'],plan['metadata']['source']['st_ino'])
 def test_changed_arbitrary_historical_original_denies_and_retains_old_source_latch(self):
  plan=self.fixture();pathlib.Path(plan['statePath'],'historical-13.json').write_bytes(b'foreign')
  with self.assertRaisesRegex(r.Fault,'state_CAS|metadata_changed'):self.install(plan)
  self.assertEqual(r.sha(pathlib.Path(plan['sourcePath']).read_bytes()),r.OLD);self.assertTrue(pathlib.Path(plan['statePath'],'blocked.json').exists())
 def test_duty_drift100_to40_or80_masks_no_invariant_and_must_deny(self):
  plan=self.fixture()
  for duty in (40,80,0):
   backend=SOURCEBackend();backend.duty=duty
   with self.subTest(duty=duty),self.assertRaisesRegex(r.Fault,'initial_curve_100'):self.install(plan,backend)
  self.assertTrue(pathlib.Path(plan['statePath'],'blocked.json').exists())
 def test_failed_owner_boot_or_invocation_restart_transplant_denies(self):
  plan=self.fixture()
  for kind in ['boot','invocation','restart']:
   backend=SOURCEBackend()
   if kind=='boot':backend.p['bootIdUtf8']='00000000-0000-0000-0000-000000000000\n'
   elif kind=='invocation':backend.p['unitUtf8']=backend.p['unitUtf8'].replace('InvocationID='+'a'*32,'InvocationID='+'b'*32)
   else:backend.p['unitUtf8']=backend.p['unitUtf8'].replace('NRestarts=0','NRestarts=1')
   with self.subTest(kind=kind),self.assertRaisesRegex(r.Fault,'frozen_failed_owner_changed'):self.install(plan,backend)
 def test_held_lock_must_match_original_inode_even_if_named_identity_agrees(self):
  plan=self.fixture();lock=pathlib.Path(plan['statePath'],'controller.lock');lock.unlink();lock.write_bytes(b'');lock.chmod(0o600)
  with self.assertRaisesRegex(r.Fault,'metadata_changed'):r.acquire(plan)
 def test_partial_after_archive_source_fault_restores_original_safe_latch_without_rollback_claim(self):
  plan=self.fixture();real=r.os.replace
  with patch.object(r.os,'replace',side_effect=OSError('SOURCE-before-replace')):
   with self.assertRaises(OSError):self.install(plan)
  self.assertEqual(r.sha(pathlib.Path(plan['sourcePath']).read_bytes()),r.OLD);self.assertTrue(pathlib.Path(plan['statePath'],'blocked.json').exists());events=[r.decode(f.read_bytes()) for f in sorted(pathlib.Path(plan['journalPath']).glob('*event.json'))];self.assertEqual(events[-1]['disposition'],'original_blocker_restored_by_no_writer_CAS_source_not_rolled_back')
 def test_foreign_state_after_archive_quarantines_not_overwrites(self):
  plan=self.fixture()
  def changed(*a):pathlib.Path(plan['statePath'],'historical-02.json').write_bytes(b'FOREIGN-after-archive');raise OSError('SOURCE-fault')
  with patch.object(r.os,'replace',side_effect=changed),self.assertRaises(OSError):self.install(plan)
  events=[r.decode(f.read_bytes()) for f in sorted(pathlib.Path(plan['journalPath']).glob('*event.json'))];self.assertEqual(events[-1]['disposition'],'quarantined_partial_no_authority_to_restore');self.assertEqual(pathlib.Path(plan['statePath'],'historical-02.json').read_bytes(),b'FOREIGN-after-archive')
 def test_own_mutations_do_not_allow_later_source_or_directory_identity_changes(self):
  plan=self.fixture();result=self.install(plan);pathlib.Path(plan['sourcePath']).chmod(0o640)
  with self.assertRaisesRegex(r.Fault,'metadata_changed'):r.verify_tree(plan,installed=True,archived=True,phase=result['phase'])
 def test_production_parent_protection_denies_world_writable_ancestor(self):
  self.parent_patch.stop();unsafe=self.root/'SOURCE-world-writable';unsafe.mkdir();unsafe.chmod(0o777)
  with self.assertRaisesRegex(r.Fault,'unprotected_parent'):r.parents_protected(unsafe/'nonexistent',{0,os.getuid()})
  self.parent_patch.start()
 def test_clock_order_nonfinite_and_cutoff_deny_before_mutation(self):
  w=self.window()
  for a,b in [(None,iso(NOW)),('bogus',iso(NOW)),(iso(NOW+1),iso(NOW)),(iso(NOW-100),iso(NOW-61))]:
   with self.subTest(a=a),self.assertRaises((r.Fault,KeyError,ValueError)):w.fresh({'startedUtc':a,'finishedUtc':b,'exitCode':0})
  w.now=lambda:NOW+179
  with self.assertRaisesRegex(r.Fault,'reserve'):w.check()
  w.now=lambda:float('nan')
  with self.assertRaises(r.Fault):w.check()
 def test_reader_executes_pinned_bytes_without_loader_reopen_or_pycache(self):
  plan=self.fixture()
  with patch.object(reader.BMC,'__init__') as b:backend=r.LinuxBackend(plan)
  self.assertEqual(backend.reader.GPU,r.GPU);self.assertEqual(list(self.root.rglob('__pycache__')),[])
 def state(self,now,duty=100,puts=0):
  s={'source_sha256':r.NEW,'gpu_uuid':r.GPU,'host_boot_id':BOOT,'pid':123,'state':'healthy','errors':[],'updated_at':iso(now),'readback_at':iso(now),'tach_at':iso(now),'sampled_at':iso(now),'node_boot_id':BOOT,'invariant_sha256':reader.digest(reader.invariant(snapshot())),'confirmed_expected_duty':duty,'readback_duty':duty,'desired_duty':duty,'mode':4,'source_bits':[0,0,0],'channel':'Zone4(CHA_FAN3)/PWMNum3','bmc_put_attempts':puts,'temperature_c':34}
  return {k:{'raw':r.encode(v)} for k,v in {'status.json':s,'pending-write.json':{'state':'verified'},'baseline.json':reader.invariant(snapshot())}.items()}
 def observer(self):
  return r.Observation({'hostBootId':BOOT,'stateOwnerUid':os.getuid(),'nodeBootId':BOOT,'invariantSha256':reader.digest(reader.invariant(snapshot())),'nonTargetSha256':reader.digest(reader.non_target(snapshot()))},reader,r.parse_unit(physical()['unitUtf8']))
 def test_ninety_seconds_actual_sampled_cool_dwell_and_counter_one(self):
  o=self.observer()
  for sec in range(0,91,5):
   duty=40 if sec>=30 else 100;o.accept(physical(True,inv='b'*32),readings(NOW+sec,duty),self.state(NOW+sec,duty,1 if sec>=30 else 0),NOW+sec)
  self.assertTrue(o.saw_low);self.assertEqual(o.last_puts,1)
 def test_early_low_stale_tach_or_gap_fail(self):
  for kind in ['low','tach','gap','counter','foreign','restart']:
   o=self.observer();o.accept(physical(True,inv='b'*32),readings(),self.state(NOW),NOW);t=NOW+5;ph=physical(True,inv='b'*32);rd=readings(t);st=self.state(t)
   if kind=='low':rd=readings(t,40);st=self.state(t,40,1)
   if kind=='tach':rd['tach']['at']=iso(t-16)
   if kind=='gap':t=NOW+20;rd=readings(t);st=self.state(t)
   if kind=='counter':st=self.state(t,100,2)
   if kind=='foreign':ph['process']['startTicks']='FOREIGN'
   if kind=='restart':ph['unitUtf8']=ph['unitUtf8'].replace('NRestarts=0','NRestarts=1')
   with self.subTest(kind=kind),self.assertRaises(r.Fault):o.accept(ph,rd,st,t)
 def test_non_target_GenericPWMdata_and_mode_source_mask_unchanged(self):
  plan=self.fixture()
  for kind in ['generic','mode','mask']:
   rd=readings()
   if kind=='generic':rd['snapshot'][reader.PATHS[1]][0]['GenericPWMdata']='FOREIGN'
   if kind=='mode':rd['snapshot'][reader.PATHS[0]]['FanMode']=0
   if kind=='mask':rd['snapshot'][reader.PATHS[2]]['PWM4_1']=1
   with self.subTest(kind=kind),self.assertRaises((r.Fault,reader.Fault)):r.measured_readings(rd,reader,plan,NOW)
if __name__=='__main__':unittest.main(verbosity=2)
