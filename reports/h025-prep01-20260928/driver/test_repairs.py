"""Focused H025 repairs; real guard/anchor, offline native adapter seams only."""
import contextlib,copy,json,os,sys,tempfile,types,unittest
from pathlib import Path
from unittest.mock import MagicMock,patch
from test_driver import manifest,go,proof,sample,Clock,Phase
from contract import LANES,Refusal,text_body,validate_go
from native import NativeAdapter
from primitives import Journal
REPO=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(REPO/'tests/install'))
from test_storage_io_paths import SyntheticMountPathTests
from install.storage_io import AnchoredRoot,StorageIOError

class Repairs(unittest.TestCase):
 def phase(self):
  c=Clock();m=manifest();t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup)
  p=Phase(m,go(m,c),'B','f'*64,Path(t.name)/'phase',c)
  p.observe(sample(m,c));p.release_barrier({l:proof(m,c,l) for l in LANES});return p,m,c
 def test_real_mounted_guard_on_every_write_append_and_atomic_replace(self):
  f=SyntheticMountPathTests();f.setUp();self.addCleanup(f.doCleanups)
  root=lambda p,g:AnchoredRoot(p,g,uid=os.geteuid())
  j=Journal(f.data/'phase',{'owned':True},storage_guard=f.guard,anchored_root=root)
  j.write('STATUS',{'first':True});j.append('TELEMETRY',{'sample':1})
  original={p.name:p.read_bytes() for p in j.path.iterdir()}
  # Same-device mount replacement after successful preflight must block all modes.
  f._mount('phase')
  for operation in [lambda:j.write('STATUS',{'second':True}),lambda:j.append('TELEMETRY',{'sample':2}),lambda:j.write('NATIVE-STOP-qwen1',{},exclusive=True)]:
   with self.assertRaises(StorageIOError):operation()
  self.assertEqual({p.name:p.read_bytes() for p in j.path.iterdir()},original)
 def test_real_native_preflight_shape_accepted_without_generic_lease(self):
  p,m,c=self.phase();a=NativeAdapter.__new__(NativeAdapter)
  a.m=m;a.go=go(m,c);a.owner_id='exact-task-owner';a.spool_baseline=None
  a.o=types.SimpleNamespace(BASE=Path('/fixture'),read=lambda _:dict(active_requests=0,quarantined=False))
  a.image=types.SimpleNamespace(tmp_snapshot=lambda _:dict(entries=[]))
  for lane in LANES:
   # Fixture values preserve actual per-lane keys; no invented lease/supervisor.
   if lane=='image':m['lanes'][lane]['identity']={'container':'fixture','run_id':'a'*32}
   m['lanes'][lane].setdefault('capacity_readback',{'context_length':480000})
  p.m=copy.deepcopy(m);a.m=m;p.go=go(m,c);p.claims={}
  a.go=p.go;a.identity=lambda lane:m['lanes'][lane]['identity']
  def rpc(lane,path):
   return {'/slots':[dict(is_processing=False,n_ctx=1048576)],'/props':dict(default_generation_settings=dict(n_ctx=1048576)),
     '/v1/readiness':dict(ready=True,model_alias='glm-5.3-flash'),'/get_server_info':dict(context_length=480000),'/health/ready':dict(ready=True,busy=False,admitting=True)}[path]
  a.rpc=rpc
  with patch('native.clock',c):
   for lane in LANES:
    row=a.preflight(lane);self.assertNotIn('lease_id',row);p.owner_proof(lane,row)
 def test_healthy_flash_remains_owned_at_899_seconds_and_admission_closed(self):
  p,m,c=self.phase();r,raw=p.prepare('flash',text_body(m,'flash','fresh','corpus'),'fresh',proof(m,c,'flash'))
  p.active['flash'].update(state='POSSIBLY_SUBMITTED',send_started=c())
  c.advance(899);p.observe(sample(m,c));p.monitoring_tick()
  self.assertTrue(p.admission_closed);self.assertIn('flash',p.active);self.assertFalse(p.stop_intents)
  c.advance(1);p.observe(sample(m,c));p.monitoring_tick();self.assertIn('flash',p.stop_intents)
 def test_undersized_settlement_reserve_refused(self):
  p,m,c=self.phase();g=go(m,c);g['settlement_deadline_utc']=g['admission_deadline_utc']
  with self.assertRaises(Refusal):validate_go(g,m,'B','f'*64,c()['utc'])
 def test_memory_max_pressure_is_recorded_but_oom_still_cuts_lane(self):
  p,m,c=self.phase();r=sample(m,c);r['cgroups']['flash']['events']['max']=99
  _,faults=p.observe(r);self.assertFalse(faults);self.assertEqual(p.latest_sample['cgroups']['flash']['events']['max'],99)
  r['cgroups']['flash']['events']['oom']=1
  _,faults=p.observe(r);self.assertIn({'reason':'cgroup_OOM_or_limit','lane':'flash','stop_exact':True},faults)
 def test_single_guest_swap_bump_does_not_persist_against_baseline(self):
  p,m,c=self.phase()
  for index in range(8):
   c.advance();r=sample(m,c);r['guest']['swap_out']=261
   d,faults=p.observe(r)
   self.assertFalse(faults);self.assertEqual(d['guest_swap_consecutive_intervals'],1 if index==0 else 0)
  self.assertEqual(p.baseline['guest']['swap_out'],0)
  self.assertFalse(p.first_failure);self.assertFalse(p.admission_closed)
 def test_five_consecutive_guest_swap_intervals_close_only_admission(self):
  for counter in ('swap_in','swap_out','alternating'):
   with self.subTest(counter=counter):
    p,m,c=self.phase();values={'swap_in':0,'swap_out':0}
    for index in range(1,6):
     c.advance();r=sample(m,c)
     values[('swap_in' if index%2 else 'swap_out') if counter=='alternating' else counter]+=1
     r['guest'].update(values);d,faults=p.observe(r)
     self.assertEqual(d['guest_swap_consecutive_intervals'],index)
     self.assertEqual(bool(faults),index==5)
    self.assertEqual(faults,[{'reason':'sustained_swap_io_5_intervals','lane':None,'stop_exact':False}])
    self.assertTrue(p.admission_closed);self.assertFalse(p.stop_intents)
 def test_quiet_interval_resets_guest_swap_streak_owned_swap_still_immediate(self):
  p,m,c=self.phase()
  for value,streak in ((1,1),(2,2),(3,3),(4,4),(4,0),(5,1)):
   c.advance();r=sample(m,c);r['guest']['swap_out']=value
   d,faults=p.observe(r);self.assertFalse(faults)
   self.assertEqual(d['guest_swap_consecutive_intervals'],streak)
  c.advance();r=sample(m,c);r['guest']['swap_out']=5;r['cgroups']['qwen1']['swap_current']=1
  _,faults=p.observe(r)
  self.assertIn({'reason':'owned_swap','lane':'qwen1','stop_exact':True},faults)
  self.assertIn('qwen1',p.stop_intents)
 def test_top_error_preserves_exact_owned_receipts(self):
  from driver import failure_receipt
  p,m,c=self.phase();p.prepare('flash',text_body(m,'flash','fresh','x'),'fresh',proof(m,c,'flash'))
  p.active['flash']['state']='POSSIBLY_SUBMITTED';receipt=failure_receipt(OSError('fixture'),p,True)
  self.assertEqual(receipt['status'],'POSSIBLY_SUBMITTED_UNKNOWN_OWNED');self.assertEqual(receipt['active']['flash']['request_id'],p.active['flash']['request_id'])
  self.assertFalse(receipt['automatic_retry'])
 def test_stopping_identity_accepts_exact_dead_container_without_release_claim(self):
  a=NativeAdapter.__new__(NativeAdapter);m=manifest();expected={'Id':'a'*64,'Image':'sha256:'+'b'*64,'Pid':987654321,'StartedAt':'fixture','cgroup':'/fixture','pid_start_ticks':'123'}
  m['lanes']['qwen1']['identity']={'container':expected,'generation':35,'runtime_profile':{'id':expected['Id']}}
  a.m=m;a.stopping={'qwen1':{'stage':'PHYSICAL_STOPPING'}};a.physically_stopped=set()
  a.manager=types.SimpleNamespace(trusted_container=lambda _:dict(Id=expected['Id'],Image=expected['Image'],State=dict(Running=False,Pid=0,Restarting=False)))
  self.assertEqual(a.stopping_identity('qwen1'),m['lanes']['qwen1']['identity']);self.assertFalse(a.physically_stopped)
 def test_glm_native_count_revision_is_pinned_without_qwen_token_array(self):
  from contract import canonical
  a=NativeAdapter.__new__(NativeAdapter);a.m=manifest();a.owner_id='owned';raw=canonical(text_body(a.m,'flash','prefix','corpus'))
  row={'identity':a.m['lanes']['flash']['identity']}
  native={'count':16257,'tokenizer_revision':'eb9eb208eb0d988989d07a6a12d0fdeb5f52574a','template_revision':'eb9eb208eb0d988989d07a6a12d0fdeb5f52574a','context_limit':1048576}
  a.rpc=lambda *args:dict(native)
  self.assertEqual(a.count('flash',raw,row)['response']['count'],16257)
  native['template_revision']='changed'
  with self.assertRaises(Refusal):a.count('flash',raw,row)
 def test_qwen_physical_wait_outside_lease_bookkeeping_inside(self):
  a=NativeAdapter.__new__(NativeAdapter);m=manifest();m['lanes']['qwen1']['identity']={'container':dict(Id='a'*64,Image='b',Pid=987654321),'generation':35,'runtime_profile':{'id':'a'*64}}
  a.m=m;a.stopping={};a.physically_stopped=set();a.cg={'qwen1':Path('/nonexistent-fixture-cgroup')};a.journal=MagicMock();a.identity=lambda _:None
  slot={'generation':35,'container':{'id':'a'*64},'selected':'qwen','desired':'running','boot_policy':'resume','failure':None};held=[False];events=[]
  @contextlib.contextmanager
  def boundary():
   held[0]=True;yield 'fixture-lease';held[0]=False
  a.boundary=boundary
  def dispatch(*args,**kw):self.assertTrue(held[0]);events.append('bookkeeping');slot['generation']+=1
  a.manager=types.SimpleNamespace(read_state=lambda **_:dict(slots={'qwen':copy.deepcopy(slot)}),dispatch=dispatch)
  stopped={'Id':'a'*64,'Image':'b','State':{'Running':False,'Pid':0,'Restarting':False}}
  def run(argv,timeout=5):
   if argv[1]=='stop':self.assertFalse(held[0]);events.append('physical')
   return json.dumps([stopped])
  with patch('native.run',run),patch('native.container_identity',return_value=m['lanes']['qwen1']['identity']['container']):
   result=a.stop_exact('qwen1',{'owned':'fixture'})
  self.assertEqual(events,['physical','bookkeeping']);self.assertTrue(result['physical_stop_proven']);self.assertIn('qwen1',a.physically_stopped)
