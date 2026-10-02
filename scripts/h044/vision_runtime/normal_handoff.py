"""Root-signed finite -> steady ownership protocol, disabled without real receipts.

The normal owner remains the ORIGINAL supervising process (and direct Popen
parent). A new authority/lease is adopted; Popen wait ownership is never falsely
transferred to another process. No lifetime flag extends a finite GO.
"""
import contextlib,datetime,fcntl,json,os,re,time
from pathlib import Path
import control
STATUS='DISABLED_UNTIL_ROOT_SIGNED_REAL_RECEIPTS'
ROLES={'interpretation','ocr','service','ingress','network'}
EVIDENCE={'startup','workload','ocr','sixResident','credentials','uidDescriptor','sourceGraph','oci'}

def required_evidence(graph):
 return (EVIDENCE-{'sixResident'})|{'enabledResident'} if control.enabled_roster(graph) else EVIDENCE

def validate_enabled_residency(record,graph,resources):
 roster=control.enabled_roster(graph);protected=control.protected_roster(graph)
 if control.enabled_roster({'runtime':{'enabledServices':record.get('enabledServices')}})!=roster:raise control.Refused('enabled_resident_roster')
 expected=[{k:r.get(k) for k in ('role','id','birth','image','devices')} for r in sorted(resources,key=lambda x:x['role']) if r['role'] in roster['vision']]
 if len(expected)!=len(roster['vision']) or any(not r[k] for r in expected for k in ('id','birth','image','devices')):raise control.Refused('enabled_vision_identity_required')
 if record.get('enabledServices')!=roster or record.get('protectedInstances')!=protected or record.get('visionInstances')!=expected:raise control.Refused('enabled_resident_identity_bindings')
 fraction=record.get('minimumFreeFraction')
 if type(record.get('instanceCount')) is not int or record.get('instanceCount')!=len(protected)+len(expected) or record.get('concurrentOperation') is not True or type(fraction) not in (int,float) or not .07<=fraction<=1:raise control.Refused('enabled_resident_operation_capacity')

def timestamp(s):
 try:
  d=datetime.datetime.fromisoformat(s)
  if d.tzinfo is None:raise ValueError('timezone')
  return d.timestamp()
 except (ValueError,TypeError):raise control.Refused('handoff_timestamp')

def no_fixture(v):
 if isinstance(v,dict):
  for k,x in v.items():
   if k.lower() in ('fixture','injectedfault','synthetic','fixtureonly') and x:raise control.Refused('fixture_cannot_qualify_normal')
   no_fixture(x)
 elif isinstance(v,list):
  for x in v:no_fixture(x)
 elif isinstance(v,str) and any(x in v.upper() for x in ('SOURCE_ONLY','INJECTED','FAKE','NOT_TESTED')):raise control.Refused('unqualified_evidence')

def verify_signature(raw,signature):
 """Pre-existing root anchor only; no key installation or credential changes."""
 import tempfile,receipt_recorder
 control.trusted_anchor()
 if len(signature)!=64:raise control.Refused('normal_signature_size')
 d=tempfile.mkdtemp(dir=control.PHASE_ROOT if os.geteuid()==0 else '/data/services/h044-vision-v03/control-ledger',prefix='normal-signature-original-')
 p=Path(d);(p/'raw').write_bytes(raw);(p/'sig').write_bytes(signature)
 r=receipt_recorder.record(['/usr/bin/openssl','pkeyutl','-verify','-pubin','-inkey',control.TRUST_ANCHOR,'-rawin','-in',str(p/'raw'),'-sigfile',str(p/'sig')],p,environment={'PATH':'/usr/bin:/bin','LC_ALL':'C'},timeout=5,label='normal-root-signature')
 return r['status']=='COMPLETE' and r['actualExitCode']==0

def validate(raw,signature,graph,current,*,now=None,verify=verify_signature,read=None,preparing=True):
 """All current inputs are exact signed tuples and protected ORIGINAL bytes.

    Injected verify/read seams are only for explicitly labelled source fixtures;
    production caller uses root signature and protected reads. Root qualification
    is the signature over genuine evidence, never assertions in a fixture.
 """
 now=time.time() if now is None else now
 if not verify(raw,signature):raise control.Refused('normal_root_signature')
 cap=control.parse_proof(raw)
 required={'schema','nonce','issuer','notBefore','prepareExpires','normalLeaseExpires','bootId','sourceGraphSHA256','ociImageId','oldOwner','newOwner','resources','admissionLease','hostContract','credentials','evidence'}
 if not isinstance(cap,dict) or set(cap)!=required:raise control.Refused('normal_capability_fields')
 if cap['schema']!='h044-normal-adoption-v1' or cap['issuer']!='ROOT_AUTHENTIC_SIGNER' or not re.fullmatch('[a-f0-9]{64}',cap['nonce']):raise control.Refused('normal_issuer_nonce')
 start=timestamp(cap['notBefore']);end=timestamp(cap['prepareExpires']);lease=timestamp(cap['normalLeaseExpires'])
 if not start<=now<lease or not 0<end-start<=1200 or lease<=end:raise control.Refused('normal_lease_window')
 if preparing and now>=end:raise control.Refused('normal_preparation_expired')
 if cap['sourceGraphSHA256']!=control.sha(control.canonical(graph)):raise control.Refused('normal_source_graph')
 bindings=('bootId','ociImageId','oldOwner','newOwner','resources','admissionLease','hostContract','credentials')
 if any(cap[k]!=current.get(k) for k in bindings):raise control.Refused('normal_current_identity_bindings')
 if {x.get('role') for x in cap['resources']}!=ROLES or len(cap['resources'])!=5:raise control.Refused('both_models_service_ingress_network_required')
 if not cap['oldOwner'] or cap['oldOwner']==cap['newOwner'] or not cap['newOwner'].get('supervisorBirth') or cap['newOwner'].get('supervisorBirth')!=cap['oldOwner'].get('supervisorBirth'):raise control.Refused('original_supervisor_wait_parent_required')
 if cap['admissionLease'].get('state')!='NORMAL_PREPARED_EXCLUSIVE' or cap['hostContract'].get('normalHost')!='10.156.100.60:18193' or cap['hostContract'].get('rawBackendBypass') is not False:raise control.Refused('normal_host_admission_contract')
 if set(cap['evidence'])!=required_evidence(graph):raise control.Refused('normal_evidence_complete_required')
 read=read or (lambda p:control.read_private(p,0))
 records={}
 for name,ref in cap['evidence'].items():
  if set(ref)!={'path','sha256','bytes'} or not re.fullmatch('[a-f0-9]{64}',ref['sha256']):raise control.Refused('normal_evidence_reference')
  b=read(ref['path'])
  if control.sha(b)!=ref['sha256'] or len(b)!=ref['bytes']:raise control.Refused('normal_original_evidence_bytes')
  value=control.parse_proof(b);no_fixture(value);records[name]=value
 if records['sourceGraph'].get('graphSHA256')!=cap['sourceGraphSHA256'] or records['oci'].get('imageId')!=cap['ociImageId']:raise control.Refused('normal_actual_source_oci_receipts')
 if records['startup'].get('actualBothModelServiceIngressHealthy') is not True or records['credentials'].get('leavesPreserved') is not True or records['uidDescriptor'].get('actualUid')!=1000 or records['uidDescriptor'].get('readableDescriptor') is not True:raise control.Refused('normal_actual_startup_uid_credentials')
 if control.enabled_roster(graph):validate_enabled_residency(records['enabledResident'],graph,cap['resources'])
 elif len(records['sixResident'].get('instances',[]))!=6 or records['sixResident'].get('concurrentOperation') is not True:raise control.Refused('normal_six_resident_original_receipts')
 for name in ('workload','ocr'):
  x=records[name]
  if x.get('status')!='RESPONSE_ASSERTIONS_PASS' or x.get('accuracyPassed') is not True or x.get('timingPassed') is not True:raise control.Refused('normal_accuracy_timing')
  try:terminal=bytes.fromhex(x['rawServiceResponseHex'])
  except (ValueError,KeyError,TypeError):raise control.Refused('normal_terminal_raw_required')
  if control.sha(terminal)!=x.get('rawServiceResponseSHA256') or control.parse_proof(terminal).get('state')!='completed':raise control.Refused('normal_terminal_raw_hash')
 return cap

class Ledger:
 """Protected atomic CAS + immutable event receipts, one resource owner."""
 def __init__(self,path,*,uid=0):self.path=Path(path);self.uid=uid
 def checked(self):
  from trusted_imports import protected_bytes
  if os.geteuid()!=self.uid:raise control.Refused('normal_root_ledger_writer')
  for p in (self.path,*self.path.parents):
   s=p.lstat()
   if not p.is_dir() or p.is_symlink() or s.st_uid not in (0,self.uid) or s.st_mode&0o022:raise control.Refused('normal_protected_ledger')
 @contextlib.contextmanager
 def lock(self):
  self.checked();fd=os.open(self.path/'lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
  try:
   s=os.fstat(fd)
   if s.st_uid!=self.uid or s.st_nlink!=1:raise control.Refused('normal_lock_owner')
   fcntl.flock(fd,fcntl.LOCK_EX);yield
  finally:fcntl.flock(fd,fcntl.LOCK_UN);os.close(fd)
 def read(self):
  from trusted_imports import protected_bytes
  return control.parse_proof(protected_bytes(self.path/'state.json',self.uid))
 def initialize(self,old,resources,boot):
  with self.lock():
   control.exclusive(self.path/'state.json',{'version':0,'state':'FINITE','owner':old,'resources':resources,'bootId':boot,'events':[]});os.chmod(self.path/'state.json',0o444)
 def cas(self,version,owner,phase,update):
  with self.lock():
   old=self.read()
   if old['version']!=version or old['owner']!=owner or old['state']!=phase:raise control.Refused('normal_CAS_collision')
   new=dict(old,**update,version=version+1)
   event={'version':new['version'],'beforeSHA256':control.sha(control.canonical(old)),'afterSHA256':control.sha(control.canonical(new)),'utc':control.utc(),'phase':new['state']}
   control.exclusive(self.path/('event-%06d.json'%new['version']),event)
   # A crash before atomic state replacement leaves the old owner authoritative
   # with a visible unacknowledged event. No broad retry or silent takeover.
   temp=self.path/('state-%06d.new'%new['version']);control.exclusive(temp,new);os.chmod(temp,0o444);os.replace(temp,self.path/'state.json')
   d=os.open(self.path,os.O_RDONLY|os.O_DIRECTORY);os.fsync(d);os.close(d)
   return new

def transition(ledger,cap,*,prepare,commit,ack,relinquish,observe,now=time.time,failpoint=None):
 """Explicit handshake. Before NORMAL, finite owner remains authoritative.

    Callbacks must be authentic original-process acknowledgement endpoints;
    they cannot be populated by invented receipts. Default schedule does not
    construct them. Any ambiguous failure quarantines, preserving truthful owner.
 """
 def fault(name):
  if failpoint:failpoint(name)
 def fresh():
  if now()>=timestamp(cap['prepareExpires']):raise control.Refused('handoff_window_deadline')
  if observe()!=cap['resources']:raise control.Refused('handoff_actual_resource_identity_changed')
 old=cap['oldOwner'];state=ledger.read()
 if state['owner']!=old or state['state']!='FINITE' or state['resources']!=cap['resources'] or state['bootId']!=cap['bootId']:raise control.Refused('handoff_current_old_owner')
 fresh()
 try:
  fault('preparation');prepared=prepare(cap);fresh()
  state=ledger.cas(state['version'],old,'FINITE',{'state':'PREPARED','capabilitySHA256':control.sha(control.canonical(cap)),'transitionIntent':{'oldOwner':old,'newOwner':cap['newOwner']},'preparation':prepared})
  fault('commit');committed=commit(cap,prepared);fresh()
  state=ledger.cas(state['version'],old,'PREPARED',{'state':'COMMIT_PENDING_ACK','commit':committed})
  fault('ack');acknowledgement=ack(cap,committed);fresh()
  if not acknowledgement or acknowledgement.get('owner')!=cap['newOwner'] or acknowledgement.get('resources')!=cap['resources'] or acknowledgement.get('bootId')!=cap['bootId']:raise control.Refused('normal_new_owner_ack_required')
  state=ledger.cas(state['version'],old,'COMMIT_PENDING_ACK',{'state':'ACK_PENDING_RELINQUISH','newOwnerAck':acknowledgement})
  fault('oldowner_relinquishment');released=relinquish(cap,acknowledgement);fresh()
  if not released or released.get('owner')!=old or released.get('capabilitySHA256')!=control.sha(control.canonical(cap)):raise control.Refused('normal_old_owner_relinquish_required')
  fault('CAS')
  state=ledger.cas(state['version'],old,'ACK_PENDING_RELINQUISH',{'state':'NORMAL','owner':cap['newOwner'],'oldOwnerRelinquish':released,'normalLeaseExpires':cap['normalLeaseExpires'],'capability':cap})
  return state
 except BaseException as exc:
  # A competing completed NORMAL owner is never changed or stopped by old test.
  current=ledger.read()
  if current['owner']==old and current['state']!='NORMAL':
   try:ledger.cas(current['version'],old,current['state'],{'state':'QUARANTINE','failure':str(exc),'normalOwnershipGranted':False})
   except (OSError,ValueError):pass
  raise

def cleanup_policy(state,old_owner,resources):
 if state['resources']!=resources:return 'QUARANTINE_UNKNOWN_RESOURCES'
 if state['state']=='NORMAL' and state['owner']!=old_owner and state.get('newOwnerAck') and state.get('oldOwnerRelinquish'):return 'NORMAL_OWNER_ONLY_NO_FINITE_STOP'
 if state['owner']==old_owner and not state.get('newOwnerAck'):return 'CLOSE_EXACT_FINITE_OWNED_RESOURCES'
 return 'QUARANTINE_UNKNOWN_HANDOFF_NO_SIGNAL'

def validate_normal_control(raw,signature,state,graph,*,now=None,verify=verify_signature):
 """Fresh one-shot steady owner shutdown; finite test GO cannot substitute."""
 now=time.time() if now is None else now
 if not verify(raw,signature):raise control.Refused('normal_control_signature')
 request=control.parse_proof(raw)
 fields={'schema','issuer','nonce','action','count','notBefore','expires','bootId','owner','resourcesSHA256','graphSHA256','capabilitySHA256'}
 if set(request)!=fields or request['schema']!='h044-normal-owner-control-v1' or request['issuer']!='ROOT_AUTHENTIC_SIGNER' or request['action']!='shutdown' or type(request['count']) is not int or request['count']!=1 or not re.fullmatch('[a-f0-9]{64}',request['nonce']):raise control.Refused('normal_control_fields')
 start=timestamp(request['notBefore']);end=timestamp(request['expires'])
 if not start<=now<end or not 0<end-start<=120:raise control.Refused('normal_control_current_window')
 if state['state']!='NORMAL' or request['owner']!=state['owner'] or request['bootId']!=state['bootId'] or request['resourcesSHA256']!=control.sha(control.canonical(state['resources'])) or request['graphSHA256']!=control.sha(control.canonical(graph)) or request['capabilitySHA256']!=state['capabilitySHA256']:raise control.Refused('normal_control_current_owner_tuple')
 return request


def validate_commit(raw,signature,cap,graph,*,now=None,verify=verify_signature):
 """Separate authentic ROOT commit after prepared admission, one finite use."""
 now=time.time() if now is None else now
 if not verify(raw,signature):raise control.Refused('normal_commit_signature')
 value=control.parse_proof(raw)
 fields={'schema','issuer','nonce','action','count','notBefore','expires','bootId','owner','resourcesSHA256','graphSHA256','capabilitySHA256'}
 if set(value)!=fields or value['schema']!='h044-normal-commit-v1' or value['issuer']!='ROOT_AUTHENTIC_SIGNER' or value['action']!='commit' or type(value['count']) is not int or value['count']!=1:raise control.Refused('normal_commit_fields')
 if not re.fullmatch('[a-f0-9]{64}',value['nonce']):raise control.Refused('normal_commit_nonce')
 start=timestamp(value['notBefore']);end=timestamp(value['expires'])
 if not start<=now<end or not 0<end-start<=120 or now>=timestamp(cap['prepareExpires']):raise control.Refused('normal_commit_window')
 if value['bootId']!=cap['bootId'] or value['owner']!=cap['newOwner'] or value['resourcesSHA256']!=control.sha(control.canonical(cap['resources'])) or value['graphSHA256']!=control.sha(control.canonical(graph)) or value['capabilitySHA256']!=control.sha(control.canonical(cap)):raise control.Refused('normal_commit_current_tuple')
 return value

def component_capability(raw,signature,graph,state,role,birth,*,now,verify=verify_signature,boot=None):
 """UID1000 verifies signed PUBLIC metadata without opening root evidence logs.

 Root alone validates original private qualification files before PREPARED.
 Component attests only its own actual birth and access, never GPU/model facts.
 """
 if not verify(raw,signature):raise control.Refused('component_root_signature')
 cap=control.parse_proof(raw)
 if cap.get('schema')!='h044-normal-adoption-v1' or cap.get('issuer')!='ROOT_AUTHENTIC_SIGNER' or cap.get('sourceGraphSHA256')!=control.sha(control.canonical(graph)):raise control.Refused('component_source_bound_capability')
 if cap['bootId']!=boot or state['bootId']!=boot or state['resources']!=cap['resources'] or state['capabilitySHA256']!=control.sha(control.canonical(cap)):raise control.Refused('component_current_public_tuple')
 if not timestamp(cap['notBefore'])<=now<timestamp(cap['normalLeaseExpires']):raise control.Refused('component_lease_window')
 if state['state']!='NORMAL' and now>=timestamp(cap['prepareExpires']):raise control.Refused('component_preparation_expired')
 matches=[x for x in cap['resources'] if x['role']==role]
 if len(matches)!=1 or matches[0]['birth']!=birth:raise control.Refused('component_actual_original_birth')
 return cap
