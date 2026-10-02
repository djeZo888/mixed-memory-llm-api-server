"""SOURCE_ONLY mock evidence, signatures and identities: never live qualification."""
import copy,datetime,json,os,tempfile,time,unittest
from pathlib import Path
from unittest import mock
import control,normal_handoff as h,normal_service as n
OUT=Path(__file__).absolute().parents[3].parent/'output'
class NormalTests(unittest.TestCase):
 def fixture(self):
  now=time.time();iso=lambda t:datetime.datetime.fromtimestamp(t,datetime.timezone.utc).isoformat()
  birth={'pid':123,'startTicks':456,'uid':0};old={'nonce':'a'*64,'supervisorBirth':birth};new={'nonce':'b'*64,'supervisorBirth':birth}
  resources=[{'role':role,'id':role,'birth':{'pid':42}} for role in sorted(h.ROLES)]
  cap={'schema':'h044-normal-adoption-v1','nonce':'b'*64,'issuer':'ROOT_AUTHENTIC_SIGNER','notBefore':iso(now-1),'prepareExpires':iso(now+20),'normalLeaseExpires':iso(now+100),'bootId':'boot','sourceGraphSHA256':control.sha(control.canonical({})),'ociImageId':'sha256:'+'c'*64,'oldOwner':old,'newOwner':new,'resources':resources,'admissionLease':{'state':'NORMAL_PREPARED_EXCLUSIVE'},'hostContract':{'normalHost':'10.156.100.60:18193','rawBackendBypass':False},'credentials':{'leaf':'existing-preserved'},'evidence':{}}
  terminal=control.canonical({'state':'completed','settled':True})
  records={'startup':{'actualBothModelServiceIngressHealthy':True},'workload':{'status':'RESPONSE_ASSERTIONS_PASS','accuracyPassed':True,'timingPassed':True,'rawServiceResponseHex':terminal.hex(),'rawServiceResponseSHA256':control.sha(terminal)},'credentials':{'leavesPreserved':True},'uidDescriptor':{'actualUid':1000,'readableDescriptor':True},'sixResident':{'instances':list(range(6)),'concurrentOperation':True},'sourceGraph':{'graphSHA256':cap['sourceGraphSHA256']},'oci':{'imageId':cap['ociImageId']}}
  records['ocr']=copy.deepcopy(records['workload']);raws={}
  for key,v in records.items():
   b=control.canonical(v);raws[key]=b;cap['evidence'][key]={'path':key,'sha256':control.sha(b),'bytes':len(b)}
  current={k:cap[k] for k in ('bootId','ociImageId','oldOwner','newOwner','resources','admissionLease','hostContract','credentials')}
  return cap,current,raws,now
 def ledger(self,cap):
  d=tempfile.TemporaryDirectory(dir=OUT);self.addCleanup(d.cleanup);p=Path(d.name);os.chmod(p,0o700)
  l=h.Ledger(p,uid=os.geteuid());l.initialize(cap['oldOwner'],cap['resources'],cap['bootId']);return l
 def callbacks(self,cap):
  return dict(prepare=lambda c:{'resources':c['resources']},commit=lambda c,p:{'resources':c['resources']},ack=lambda c,p:{'owner':c['newOwner'],'resources':c['resources'],'bootId':c['bootId']},relinquish=lambda c,a:{'owner':c['oldOwner'],'capabilitySHA256':control.sha(control.canonical(c))},observe=lambda:cap['resources'])
 def validate(self,cap,current,raws,now,**kw):
  return h.validate(control.canonical(cap),b'not-a-real-signature',{},current,now=now,verify=lambda *_:True,read=lambda p:raws[p],**kw)
 def test_exact_bindings_and_original_terminal_hash(self):
  cap,current,raws,now=self.fixture();self.assertEqual(self.validate(cap,current,raws,now)['nonce'],cap['nonce'])
  for key in ('bootId','ociImageId','oldOwner','newOwner','resources','admissionLease','hostContract','credentials'):
   c=copy.deepcopy(current);c[key]=None
   with self.subTest(binding=key),self.assertRaises(control.Refused):self.validate(cap,c,raws,now)
  bad=copy.deepcopy(cap);b=control.canonical(dict(control.parse_proof(raws['workload']),rawServiceResponseSHA256='0'*64));raws['workload']=b;bad['evidence']['workload'].update(sha256=control.sha(b),bytes=len(b))
  with self.assertRaises(control.Refused):self.validate(bad,current,raws,now)
 def test_signature_fixture_missing_evidence_and_expiry_fail_closed(self):
  c,current,raws,now=self.fixture()
  with self.assertRaises(control.Refused):h.validate(control.canonical(c),b'bad',{},current,now=now,verify=lambda *_:False)
  for change in ('fixture','missing','expiry','six','UID','source'):
   cap,cur,raw,at=self.fixture()
   if change=='fixture':raw['startup']=control.canonical({'fixture':True});cap['evidence']['startup'].update(sha256=control.sha(raw['startup']),bytes=len(raw['startup']))
   if change=='missing':del cap['evidence']['ocr']
   if change=='expiry':at+=21
   if change=='six':raw['sixResident']=control.canonical({'instances':[1],'concurrentOperation':True});cap['evidence']['sixResident'].update(sha256=control.sha(raw['sixResident']),bytes=len(raw['sixResident']))
   if change=='UID':raw['uidDescriptor']=control.canonical({'actualUid':0,'readableDescriptor':True});cap['evidence']['uidDescriptor'].update(sha256=control.sha(raw['uidDescriptor']),bytes=len(raw['uidDescriptor']))
   if change=='source':cap['sourceGraphSHA256']='0'*64
   with self.subTest(change=change),self.assertRaises(control.Refused):self.validate(cap,cur,raw,at)
 def test_explicit_all_handshakes_and_old_test_expiry_no_stop(self):
  cap,_,_,now=self.fixture();l=self.ledger(cap);state=h.transition(l,cap,**self.callbacks(cap))
  self.assertEqual(state['state'],'NORMAL');self.assertEqual(state['owner'],cap['newOwner']);self.assertTrue(state['newOwnerAck']);self.assertTrue(state['oldOwnerRelinquish'])
  self.assertEqual(h.cleanup_policy(state,cap['oldOwner'],cap['resources']),'NORMAL_OWNER_ONLY_NO_FINITE_STOP')
  self.assertEqual([json.loads(p.read_text())['phase'] for p in sorted(l.path.glob('event*'))],['PREPARED','COMMIT_PENDING_ACK','ACK_PENDING_RELINQUISH','NORMAL'])
 def test_each_failure_preserves_truthful_owner_and_never_grants_normal(self):
  for point in ('preparation','commit','ack','CAS','oldowner_relinquishment'):
   cap,_,_,_=self.fixture();l=self.ledger(cap)
   def fault(p):
    if p==point:raise OSError('INJECTED_SOURCE_ONLY_'+p)
   with self.subTest(point=point),self.assertRaises(OSError):h.transition(l,cap,failpoint=fault,**self.callbacks(cap))
   s=l.read();self.assertEqual(s['owner'],cap['oldOwner']);self.assertEqual(s['state'],'QUARANTINE');self.assertFalse(s['normalOwnershipGranted'])
   policy=h.cleanup_policy(s,cap['oldOwner'],cap['resources']);self.assertIn(policy,('CLOSE_EXACT_FINITE_OWNED_RESOURCES','QUARANTINE_UNKNOWN_HANDOFF_NO_SIGNAL'))
 def test_collision_expiry_resource_change_and_ack_failure(self):
  for kind in ('collision','expiry','resource','ack'):
   cap,_,_,now=self.fixture();l=self.ledger(cap);kw=self.callbacks(cap)
   if kind=='collision':l.cas(0,cap['oldOwner'],'FINITE',{'state':'PREPARED'})
   if kind=='expiry':kw['now']=lambda:now+22
   if kind=='resource':kw['observe']=lambda:[]
   if kind=='ack':kw['ack']=lambda *_:None
   with self.subTest(kind=kind),self.assertRaises(control.Refused):h.transition(l,cap,**kw)
   self.assertNotEqual(l.read()['state'],'NORMAL')
 def test_atomic_CAS_one_owner_and_owned_cleanup_failure(self):
  cap,_,_,_=self.fixture();l=self.ledger(cap);l.cas(0,cap['oldOwner'],'FINITE',{'state':'PREPARED'})
  with self.assertRaises(control.Refused):l.cas(0,cap['oldOwner'],'FINITE',{'state':'NORMAL'})
  self.assertEqual(h.cleanup_policy(dict(l.read(),resources=[]),cap['oldOwner'],cap['resources']),'QUARANTINE_UNKNOWN_RESOURCES')
 def test_active_steady_lease_survives_test_deadline_then_normal_lease_expires(self):
  cap,current,raws,now=self.fixture();graph={'runtime':{'normalHandoff':{'status':n.STATUS,'statePath':'state','capabilityPath':'cap','signaturePath':'sig'}}};cap['sourceGraphSHA256']=control.sha(control.canonical(graph));raws['sourceGraph']=control.canonical({'graphSHA256':cap['sourceGraphSHA256']});cap['evidence']['sourceGraph'].update(sha256=control.sha(raws['sourceGraph']),bytes=len(raws['sourceGraph']));l=self.ledger(cap);state=h.transition(l,cap,**self.callbacks(cap))
  data=dict(raws,state=control.canonical(state),cap=control.canonical(cap),sig=b'not-real-signature');clock=[now+25]
  lease=n.ActiveLease(graph,'service',now+10,read=lambda p:data[p],clock=lambda:clock[0],verify=lambda *_:True,birth=lambda:{'pid':42})
  original=Path.read_text
  with mock.patch.object(Path,'read_text',side_effect=lambda *a,**k:'boot'):
   self.assertTrue(lease.available());self.assertTrue(lease.adopted);self.assertEqual(lease.deadline(),h.timestamp(cap['normalLeaseExpires']))
   clock[0]=now+101;self.assertFalse(lease.available())
 def test_unsigned_or_prepared_state_does_not_extend_finite_lease(self):
  cap,_,_,now=self.fixture();graph={'runtime':{'normalHandoff':{'status':n.STATUS,'statePath':'state','capabilityPath':'cap','signaturePath':'sig'}}};cap['sourceGraphSHA256']=control.sha(control.canonical(graph));l=self.ledger(cap);l.cas(0,cap['oldOwner'],'FINITE',{'state':'PREPARED','capabilitySHA256':control.sha(control.canonical(cap))})
  data={'state':control.canonical(l.read()),'cap':control.canonical(cap),'sig':b'bad'}
  lease=n.ActiveLease(graph,'service',now+10,read=lambda p:data[p],clock=lambda:now+11,verify=lambda *_:False,birth=lambda:{'pid':42})
  with mock.patch.object(Path,'read_text',return_value='boot'):self.assertFalse(lease.available());self.assertFalse(lease.adopted)
 def test_normal_shutdown_rejects_old_finite_or_unsigned_owner_control(self):
  cap,_,_,now=self.fixture();l=self.ledger(cap);state=h.transition(l,cap,**self.callbacks(cap));iso=lambda t:datetime.datetime.fromtimestamp(t,datetime.timezone.utc).isoformat()
  req={'schema':'h044-normal-owner-control-v1','issuer':'ROOT_AUTHENTIC_SIGNER','nonce':'e'*64,'action':'shutdown','count':1,'notBefore':iso(now-1),'expires':iso(now+20),'bootId':state['bootId'],'owner':state['owner'],'resourcesSHA256':control.sha(control.canonical(state['resources'])),'graphSHA256':control.sha(control.canonical({})),'capabilitySHA256':state['capabilitySHA256']}
  self.assertEqual(h.validate_normal_control(control.canonical(req),b'mocked',state,{},now=now,verify=lambda *_:True)['action'],'shutdown')
  for key,value in [('schema','h044-finite-root-go-v1'),('count',True),('owner',cap['oldOwner']),('bootId','other'),('capabilitySHA256','0'*64),('expires',iso(now-1))]:
   changed=dict(req,**{key:value})
   with self.subTest(field=key),self.assertRaises(control.Refused):h.validate_normal_control(control.canonical(changed),b'mocked',state,{},now=now,verify=lambda *_:True)
 def test_renewal_requires_fresh_signature_and_same_original_tuple(self):
  cap,current,raws,now=self.fixture();l=self.ledger(cap);h.transition(l,cap,**self.callbacks(cap))
  owner=n.NormalOwner({},l,cap,None,cap['resources'],inspect=lambda:cap['resources'],callbacks={},capability_raw=control.canonical(cap),signature=b'mocked',current_tuple=lambda:current,clock=lambda:now)
  renewed=copy.deepcopy(cap);renewed['normalLeaseExpires']=datetime.datetime.fromtimestamp(now+200,datetime.timezone.utc).isoformat()
  # Mock ONLY the root signature/protected evidence boundary. This is source-only.
  def validated(raw,sig,graph,cur,**kw):return h.validate(raw,sig,graph,cur,verify=lambda *_:sig==b'mocked',read=lambda p:raws[p],**kw)
  original=h.validate
  with mock.patch.object(n.handoff,'validate',side_effect=lambda raw,sig,g,c,**kw:original(raw,sig,g,c,verify=lambda *_:sig==b'mocked',read=lambda p:raws[p],**kw)):
   with self.assertRaises(control.Refused):owner.renew(control.canonical(renewed),b'bad')
   result=owner.renew(control.canonical(renewed),b'mocked');self.assertEqual(result['normalLeaseExpires'],renewed['normalLeaseExpires']);self.assertTrue(result['signedCapability'])
   with self.assertRaises(control.Refused):owner.renew(control.canonical(renewed),b'mocked')
if __name__=='__main__':unittest.main()

class ExecutableTopologyTests(unittest.TestCase):
 """Actual protected -I launcher/monitor/supervisor/channel/child executions."""
 def scenario(self,case):
  import sys,uuid,receipt_recorder
  directory=OUT/('actual-topology-'+case+'-'+uuid.uuid4().hex);directory.mkdir(mode=0o700)
  now=time.time();spec={'evidence':'SOURCE_ONLY_SYNTHETIC_EXECUTABLE_TOPOLOGY','case':case,'artifactRoot':str(directory),'channels':str(directory/'channels'),'fixtureAnchorHex':os.urandom(32).hex(),'finiteEnd':now+3,'normalEnd':now+5}
  p=directory/'fixture.json';p.write_bytes(control.canonical(spec));os.chmod(p,0o600)
  env={'PATH':'/usr/bin:/bin','LC_ALL':'C','PYTHONDONTWRITEBYTECODE':'1','TMPDIR':os.environ['TMPDIR']}
  result=receipt_recorder.record([sys.executable,'-I','-B',str(Path(n.__file__).resolve()),'--source-fixture-launch',str(p)],directory/'original-command',environment=env,timeout=12,label='actual-'+case,evidence=spec['evidence'],input_bindings=receipt_recorder.digest(p))
  self.assertEqual(result['status'],'COMPLETE',result['errors']);self.assertIs(type(result['actualExitCode']),int);self.assertTrue(result['waited']);self.assertTrue(result['absence']['recordedBirthAbsent']);self.assertTrue(result['absence']['recordedGroupAbsent'])
  terminal=json.loads((directory/'launcher-terminal.json').read_text());self.assertIsNone(terminal['failure'],terminal['failure'])
  for child in terminal['children']:
   self.assertTrue(child['directPopenWait']);self.assertIs(type(child['actualExitCode']),int);self.assertTrue(child['originalBirthAbsent']);self.assertTrue(child['originalGroupAbsent'])
  supervisor=json.loads((directory/'channels/supervisor-terminal.json').read_text())
  for child in supervisor['children']:
   self.assertTrue(child['directPopenWait']);self.assertIs(type(child['actualExitCode']),int);self.assertTrue(child['originalGroupAbsent']) if child['birth'] else self.assertTrue(child['knownDirectPidAbsent'])
  return directory,terminal,supervisor
 def test_executable_same_original_owner_takeover_and_usable_after_finite_expiry(self):
  directory,terminal,supervisor=self.scenario('success');self.assertTrue(supervisor['adopted']);self.assertIsNone(supervisor['failure']);self.assertTrue(json.loads((directory/'after-finite-expiry.json').read_text())['childrenUsableBeyondFiniteExpiry'])
  state=json.loads((directory/'channels/state.json').read_text());self.assertEqual(state['state'],'NORMAL');self.assertEqual(state['owner']['supervisorBirth'],supervisor['originalBirth']);self.assertTrue(state['newOwnerAck']['componentAcks']);self.assertTrue(state['newOwnerAck']['independentMonitor']);self.assertTrue(state['oldOwnerRelinquish'])
 def test_executable_rejection_faults_expiry_close_exact_children(self):
  for case in ('cas-collision','post-popen-birth','bad-signature','expired-capability','identity-collision','wrong-ack','missing-ack','partial-launch','metadata-write','timeout','output-cap','expiry'):
   with self.subTest(case=case):
    directory,_,supervisor=self.scenario(case);self.assertFalse(supervisor['adopted']);self.assertFalse((directory/'after-finite-expiry.json').exists())
    if (directory/'channels/state.json').exists():self.assertNotEqual(json.loads((directory/'channels/state.json').read_text())['state'],'NORMAL')

 def test_executable_finite_group_kill_leaves_original_normal_children_usable(self):
  directory,terminal,supervisor=self.scenario('finite-group-timeout');self.assertTrue(supervisor['adopted']);self.assertIsNone(supervisor['failure']);self.assertTrue(json.loads((directory/'after-finite-expiry.json').read_text())['childrenUsableBeyondFiniteExpiry'])

 def test_executable_admitted_normal_fault_TERM_metadata_retains_originals_until_authority(self):
  for case in ('normal-term-shutdown','normal-fault-expiry','normal-metadata-shutdown'):
   with self.subTest(case=case):
    directory,terminal,supervisor=self.scenario(case)
    before=json.loads((directory/'normal-fault-before-authority.json').read_text())
    self.assertTrue(supervisor['adopted']);self.assertTrue(supervisor['failure'])
    self.assertTrue(before['unexpiredNormalLease']);self.assertTrue(before['oldFiniteDeadlineExpired'])
    self.assertTrue(before['noChildTerminalBeforeAuthority']);self.assertTrue(before['shutdownNotPresent'])
    self.assertEqual(before['sameOriginalSupervisorAndChildren']['supervisorObserved'],supervisor['originalBirth'])
    self.assertTrue(all(before['rawPulseSizesAfter'][role]>size for role,size in before['rawPulseSizesBefore'].items()))
    expected='NORMAL_LEASE_EXPIRED_OWNED_SHUTDOWN' if case=='normal-fault-expiry' else 'NORMAL_OWNER_SIGNED_SHUTDOWN'
    self.assertEqual(supervisor['reason'],expected)
    self.assertEqual(supervisor['cleanupDecision']['reason'],expected)
    original=next(x for x in terminal['children'] if x['pid']==supervisor['originalBirth']['pid'])
    self.assertEqual(original['actualExitCode'],75) # original fault retained after authorized closure
    for child in supervisor['children']:
     self.assertTrue(child['directPopenWait']);self.assertTrue(child['originalBirthAbsent']);self.assertTrue(child['originalGroupAbsent'])
