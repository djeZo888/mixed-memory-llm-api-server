# Explicit protected import bootstrap for genuine Python -I entrypoints.
if __name__ == '__main__':
 import hashlib as _h, importlib.util as _iu, json as _j, os as _o, stat as _s
 from pathlib import Path as _P
 _root = _P(__file__).absolute().parents[3]
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

"""Steady lease reader/owner. Disabled until signed current real-receipt adoption.

Normal authority governs availability, renewal and shutdown independently of an
expired finite test. Root ledger is public metadata, never credential contents.
Original Popen parent remains alive to reap its service/ingress children.
"""
import json,os,time
from pathlib import Path
import control,normal_handoff as handoff
STATUS=handoff.STATUS

def public_read(path):
 from trusted_imports import protected_bytes
 return protected_bytes(Path(path),0)

class ActiveLease:
 def __init__(self,graph,component,finite_end,*,read=public_read,clock=time.time,verify=handoff.verify_signature,birth=None,ack=None):
  self.graph=graph;self.component=component;self.finite_end=finite_end
  self.read=read;self.clock=clock;self.verify=verify;self.birth=birth;self.ack=ack
  self.adopted=False;self.lastState=None;self.failure=None;self.acknowledged=set();self.signatureCache={}
 def verify_cached(self,raw,signature):
  anchor=control.trusted_anchor() if self.verify is handoff.verify_signature else 'SOURCE_FIXTURE_VERIFIER'
  key=(control.sha(raw),control.sha(signature),anchor)
  if key not in self.signatureCache:
   self.signatureCache={key:self.verify(raw,signature)}
  return self.signatureCache[key]
 def deadline(self):
  """Return authenticated current authority deadline, never a lifetime flag."""
  descriptor=self.graph['runtime'].get('normalHandoff',{})
  if descriptor.get('status')!=STATUS or not descriptor.get('statePath'):return self.finite_end
  try:
   state=control.parse_proof(self.read(descriptor['statePath']))
   self.lastState=state
   if state['state'] not in ('PREPARED','COMMIT_PENDING_ACK','ACK_PENDING_RELINQUISH','NORMAL'):return self.finite_end if not self.adopted else 0
   signed=state.get('signedCapability')
   if signed:
    capraw=bytes.fromhex(signed['rawHex']);sig=bytes.fromhex(signed['signatureHex'])
   else:capraw=self.read(descriptor['capabilityPath']);sig=self.read(descriptor['signaturePath'])
   cap=control.parse_proof(capraw)
   if state.get('capabilitySHA256')!=control.sha(control.canonical(cap)) or state['bootId']!=Path('/proc/sys/kernel/random/boot_id').read_text().strip():raise control.Refused('normal_descriptor_cap_boot')
   # current resource graph is immutable in the protected ledger, and each leaf
   # verifies its own authentic birth before acknowledgement or continuing.
   if not self.birth:raise control.Refused('normal_actual_component_birth_required')
   cap=handoff.component_capability(capraw,sig,self.graph,state,self.component,self.birth(),now=self.clock(),verify=self.verify_cached,boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip())
   phase=state['state']
   if phase!='NORMAL':
    token=(cap['nonce'],phase)
    if token not in self.acknowledged:
     if not self.ack:raise control.Refused('normal_component_ack_channel_missing')
     self.ack({'nonce':cap['nonce'],'phase':phase,'role':self.component,'birth':self.birth(),'capabilitySHA256':control.sha(control.canonical(cap)),'bootId':cap['bootId'],'actualUtc':control.utc(),'actualUid':os.geteuid(),'descriptorReadable':True})
     self.acknowledged.add(token)
    return self.finite_end
   if state['owner']!=cap['newOwner'] or not state.get('newOwnerAck') or not state.get('oldOwnerRelinquish'):raise control.Refused('normal_handshake_not_committed')
   self.adopted=True
   return handoff.timestamp(cap['normalLeaseExpires'])
  except (OSError,ValueError,KeyError,TypeError) as exc:
   self.failure=str(exc)
   # No accepted normal ownership yet: finite safety deadline stays in force.
   # After takeover, normal lease failure closes admission truthfully.
   return 0 if self.adopted else self.finite_end
 def available(self):return self.clock()<self.deadline()


def component_lease(graph,component,finite_end):
 import observer
 def acknowledge(value):
  d=graph['runtime']['normalHandoff']['componentAckRoot']+'/'+component
  control.exclusive(Path(d)/(value['nonce']+'-'+component+'-'+value['phase']+'.json'),value)
 return ActiveLease(graph,component,finite_end,birth=lambda:observer.birth(os.getpid()),ack=acknowledge)

class NormalOwner:
 """Original supervisor adopts a distinct root-signed steady admission lease."""
 def __init__(self,graph,ledger,cap,manager,resources,*,inspect,callbacks,capability_raw,signature,current_tuple,clock=time.time):
  self.graph=graph;self.ledger=ledger;self.cap=cap;self.manager=manager
  self.resources=resources;self.inspect=inspect;self.callbacks=callbacks;self.clock=clock
  self.capability_raw=capability_raw;self.signature=signature;self.current_tuple=current_tuple
 def adopt(self):
  # Callers must validate signed capability first against genuine current graph,
  # original receipt bytes and current boot/owner tuple. Recheck actual root and
  # original supervisor here; mock fixtures are explicitly source-only.
  import observer
  if os.geteuid()!=0 or observer.birth(os.getpid())!=self.cap['newOwner']['supervisorBirth']:raise control.Refused('normal_original_root_wait_parent')
  if self.cap['oldOwner'].get('supervisorDomain')!='ROOT_STEADY_LAUNCHER_SEPARATE_FROM_FINITE_EXECUTOR' or self.cap['newOwner'].get('supervisorDomain')!=self.cap['oldOwner'].get('supervisorDomain'):raise control.Refused('finite_executor_parent_cannot_become_steady_owner')
  adapter=self.graph['runtime']['normalHandoff']['adapter']
  if not isinstance(adapter,dict) or set(adapter)!={'path','sha256','contract'} or adapter['contract']!='h044-root-steady-owner-adapter-v1' or self.graph['sourceManifest'].get(adapter['path'])!=adapter['sha256']:raise control.Refused('root_R_current_source_bound_steady_adapter_required')
  control.validate_graph(self.graph);control.verify_source(self.graph,control.SOURCE_ROOT,control.SOURCE_ROOT+'/scripts/h044/vision_runtime')
  validated=handoff.validate(self.capability_raw,self.signature,self.graph,self.current_tuple(),now=self.clock())
  if validated!=self.cap:raise control.Refused('normal_capability_object_not_signed_bytes')
  state=handoff.transition(self.ledger,self.cap,observe=self.inspect,now=self.clock,**{k:self.callbacks[k] for k in ('prepare','commit','ack','relinquish')})
  return self.ledger.cas(state['version'],state['owner'],'NORMAL',{'signedCapability':{'rawHex':self.capability_raw.hex(),'signatureHex':self.signature.hex()}})
 def govern(self,*,stop_requested,renew=None,pause=time.sleep):
  """Steady owner retains direct waits; finite expiry is irrelevant after NORMAL.

  stop_requested must be a signed current normal-owner shutdown request, not an
  old finite GO. Renewal is another reviewed signed capability with exact same
  resources and original parent. No automatic renewable/unlimited authority.
  """
  while True:
   state=self.ledger.read()
   if handoff.cleanup_policy(state,self.cap['oldOwner'],self.resources)!='NORMAL_OWNER_ONLY_NO_FINITE_STOP':raise control.Refused('steady_owner_ledger_changed_quarantine')
   if self.inspect()!=self.resources:raise control.Refused('steady_actual_identity_changed_quarantine')
   request=stop_requested(state)
   if request:
    if not isinstance(request,tuple) or len(request)!=2:raise control.Refused('normal_shutdown_requires_signed_original_bytes')
    approved=handoff.validate_normal_control(*request,state,self.graph,now=self.clock())
    control.exclusive(self.ledger.path/('shutdown-spent-'+approved['nonce']+'.json'),{'requestSHA256':control.sha(request[0]),'originalOwner':state['owner'],'approvedUtc':control.utc()})
    return 'NORMAL_OWNER_SIGNED_SHUTDOWN'
   if self.clock()>=handoff.timestamp(state['normalLeaseExpires']):return 'NORMAL_LEASE_EXPIRED_OWNED_SHUTDOWN'
   if renew:
    renewal=renew(state)
    if renewal:self.renew(*renewal)
   pause(.2)

 def renew(self,raw,signature):
  state=self.ledger.read()
  if state['state']!='NORMAL' or state['owner']!=self.cap['newOwner']:raise control.Refused('normal_renewal_current_owner')
  cap=handoff.validate(raw,signature,self.graph,self.current_tuple(),now=self.clock(),preparing=False)
  for field in ('nonce','bootId','sourceGraphSHA256','ociImageId','oldOwner','newOwner','resources','admissionLease','hostContract','credentials','evidence'):
   if cap[field]!=self.cap[field]:raise control.Refused('normal_renewal_changed_original_tuple')
  if handoff.timestamp(cap['normalLeaseExpires'])<=handoff.timestamp(state['normalLeaseExpires']):raise control.Refused('normal_renewal_not_newer')
  state=self.ledger.cas(state['version'],state['owner'],'NORMAL',{'capability':cap,'capabilitySHA256':control.sha(control.canonical(cap)),'normalLeaseExpires':cap['normalLeaseExpires'],'signedCapability':{'rawHex':raw.hex(),'signatureHex':signature.hex()}})
  self.cap=cap;self.capability_raw=raw;self.signature=signature
  return state


def contract(graph):
 return {'schema':'h044-normal-host-contract-v1','status':STATUS,
  'normalHost':'10.156.100.60:18193','serviceUid':1000,
  'credentialLeaf':graph['runtime']['service']['credentialPaths']['service'],
  'credentialContents':'NEVER_EXPORTED','sourceRoot':graph['sourceRoot'],
  'sourceGraphSHA256':control.sha(control.canonical(graph)),
  'endpoints':['/v1/technical-vision/capabilities','/v1/technical-vision/jobs','/v1/technical-vision/requests/{requestId}/status','/v1/technical-vision/jobs/{jobId}/status','/v1/technical-vision/jobs/{jobId}/cancel'],
  'rawBackendBypass':False,'nativeFactoryOwner':'R_EXCLUSIVE',
  'requiredRouting':'normal Sova owned job journal -> authenticated normal host -> service -> both model services',
  'ownerPolicy':'original supervising PID remains direct Popen parent under new signed steady owner/lease; explicit normal shutdown/renewal',
  'integrationBlockers':['Root authentic current adoption capability and evidence receipt wrappers','Root/R normal native factory source tuple and signed normal-host admission descriptor','Current systemd original-parent/domain + UID1000 actual public descriptor/channel access must be operationally verified; source fixtures do not qualify availability']}

# Concrete original supervisor and independent finite monitor protocol.
# Production launch is a foreground systemd Type=exec service, NEVER a fork out
# of executor cleanup. Local fixture launch uses independently supervised siblings.
DOMAIN='ROOT_STEADY_LAUNCHER_SEPARATE_FROM_FINITE_EXECUTOR'

def process_identity(pid):
 import receipt_recorder,observer
 if __import__('sys').platform.startswith('linux'):return observer.birth(pid)
 import ctypes,struct
 lib=ctypes.CDLL('/usr/lib/libproc.dylib');buf=ctypes.create_string_buffer(136)
 if lib.proc_pidinfo(int(pid),3,0,buf,136)!=136:raise control.Refused('actual_birth_or_parent_missing')
 observed_pid,ppid,uid=struct.unpack_from('III',buf.raw,12);pgid=struct.unpack_from('I',buf.raw,100)[0];seconds,micros=struct.unpack_from('QQ',buf.raw,120)
 if observed_pid!=pid:raise control.Refused('actual_kernel_pid_mismatch')
 return {'pid':pid,'kernelBirth':{'kind':'darwin-proc-bsdinfo','seconds':seconds,'microseconds':micros},'ppid':ppid,'pgid':pgid,'uid':uid,'domain':'LOCAL_SOURCE_FIXTURE_SESSION'}


def publish(path,value,*,public=False):
 control.exclusive(path,value)
 if public:os.chmod(path,0o444)

def channels(graph):return Path(graph['runtime']['normalHandoff']['statePath']).parent

def install_channels(graph,*,uid=0,component_uid=1000):
 """Public signed metadata, root-only command/monitor writes, UID leaf ACKs.

 No credential or job-journal copy, chown or replacement is ever performed here.
 Refuse existing paths so a prior owner's channel cannot be silently reused.
 """
 import stat
 root=channels(graph)
 if os.geteuid()!=uid or str(root)!=os.path.realpath(root):raise control.Refused('original_channel_writer_canonical_root')
 # Check ancestors BEFORE creating even the channel root. A signed path string
 # does not qualify access or permit writing through an unsafe live ancestor.
 for ancestor in root.parents:
  s=ancestor.lstat()
  if ancestor.is_symlink() or not stat.S_ISDIR(s.st_mode) or s.st_uid not in (0,uid) or s.st_mode&0o022:raise control.Refused('protected_channel_ancestor_required')
 root.mkdir(mode=0o755);os.chmod(root,0o755)
 for name,owner,mode in [('monitor',uid,0o700),('components',uid,0o755),('components/service',component_uid,0o700),('components/ingress',component_uid,0o700),('logs',uid,0o700)]:
  p=root/name;p.mkdir(mode=mode);os.chmod(p,mode)
  if owner!=os.geteuid():os.chown(p,owner,owner)
  s=p.lstat()
  if not stat.S_ISDIR(s.st_mode) or p.is_symlink() or s.st_uid!=owner or stat.S_IMODE(s.st_mode)!=mode:raise control.Refused('actual_channel_leaf_owner_mode')
 return root

def read_channel(path,uid=0):
 from trusted_imports import protected_bytes
 return control.parse_proof(protected_bytes(Path(path),uid))

def wait_channel(path,deadline,*,uid=0,check=lambda:None):
 while time.time()<deadline:
  check()
  try:return read_channel(path,uid)
  except FileNotFoundError:time.sleep(.025)
 raise TimeoutError('protected_channel_ack_timeout:'+str(path))

def exact_owner(owner,resources,*,finite=None,production=True):
 """Independent fresh original parent/group/domain + original resource check."""
 b=process_identity(owner['supervisorBirth']['pid'])
 if b!=owner['supervisorBirth'] or b['pgid']!=b['pid'] or owner['supervisorDomain']!=DOMAIN:raise control.Refused('independent_supervisor_original_identity')
 if finite and (b['pgid']==finite['pgid'] or b.get('cgroup')==finite.get('cgroup') and production):raise control.Refused('supervisor_in_finite_kill_domain')
 if production and (b['ppid']!=1 or '/'+owner['unit'] not in b['cgroup']):raise control.Refused('systemd_original_parent_domain')
 for resource in resources:
  role=resource['role']
  if role in ('service','ingress') or not production and role in ('interpretation','ocr'):
   child=process_identity(resource['birth']['pid'])
   if child!=resource['birth'] or child['ppid']!=b['pid']:raise control.Refused('original_direct_wait_parent_changed')
  elif role in ('interpretation','ocr'):
   import observer
   q=observer.exact_container(resource['id'])
   if q.get('birth')!=resource['birth'] or not q.get('value',{}).get('running') or q['value']['image']!=resource['image']:raise control.Refused('original_model_identity_changed')
   for gpu_birth in resource.get('gpuProcessBirths',[]):
    current_gpu=process_identity(gpu_birth['pid'])
    if current_gpu!=gpu_birth or current_gpu['cgroup']!=resource['birth']['cgroup']:raise control.Refused('original_model_GPU_process_birth_changed')
   if not resource.get('gpuProcessBirths'):raise control.Refused('original_model_GPU_process_birth_missing')
   attach=process_identity(resource['attachBirth']['pid'])
   if attach!=resource['attachBirth'] or attach['ppid']!=b['pid']:raise control.Refused('original_attach_wait_parent_changed')
 return {'owner':owner,'resources':resources,'supervisorObserved':b,'actualUtc':control.utc(),'verification':'ACTUAL_ORIGINAL_PARENT_GROUP_DOMAIN_READ'}

class ChannelHandshake:
 """Supervisor writes ledger; monitor/component processes open their own leaves."""
 def __init__(self,graph,ledger,cap,observe,*,verify=handoff.verify_signature,component_uid=1000,fixture=False):
  self.graph,self.ledger,self.cap,self.observe=graph,ledger,cap,observe
  self.root=ledger.path;self.verify=verify;self.component_uid=component_uid;self.fixture=fixture
 def healthy(self):
  if self.observe()!=self.cap['resources']:raise control.Refused('handoff_original_observation_changed')
  if (self.root/'monitor/cancel.json').exists():raise control.Refused('finite_monitor_cancelled')
 def prepare(self,cap):
  return {'normalAdmission':cap['admissionLease'],'originalOwner':cap['oldOwner'],'preparedUtc':control.utc()}
 def commit(self,cap,prepared):
  end=handoff.timestamp(cap['prepareExpires'])
  for role in ('service','ingress'):
   prepared=wait_channel(self.root/'components'/role/(cap['nonce']+'-'+role+'-PREPARED.json'),end,uid=self.component_uid,check=self.healthy)
   expected=next(x for x in cap['resources'] if x['role']==role)
   if prepared.get('birth')!=expected['birth'] or prepared.get('actualUid')!=self.component_uid or prepared.get('descriptorReadable') is not True or prepared.get('capabilitySHA256')!=control.sha(control.canonical(cap)):raise control.Refused('prepared_original_admission_component_ack')
  wait_channel(self.root/'commit.json',end,uid=self.ledger.uid,check=self.healthy)
  from trusted_imports import protected_bytes
  raw=protected_bytes(self.root/'commit.json',self.ledger.uid);sig=protected_bytes(self.root/'commit.sig',self.ledger.uid)
  value=handoff.validate_commit(raw,sig,cap,self.graph,verify=self.verify)
  publish(self.root/('commit-spent-'+value['nonce']+'.json'),{'rawSHA256':control.sha(raw),'actualUtc':control.utc()})
  return {'rootSignedCommit':value,'rawSHA256':control.sha(raw),'originalSignatureHex':sig.hex()}
 def ack(self,cap,committed):
  end=handoff.timestamp(cap['prepareExpires']);acks={}
  for role in ('service','ingress'):
   p=self.root/'components'/role/(cap['nonce']+'-'+role+'-COMMIT_PENDING_ACK.json')
   value=wait_channel(p,end,uid=self.component_uid,check=self.healthy)
   resource=next(x for x in cap['resources'] if x['role']==role)
   if value.get('birth')!=resource['birth'] or value.get('actualUid')!=self.component_uid or value.get('descriptorReadable') is not True or value.get('phase')!='COMMIT_PENDING_ACK' or value.get('capabilitySHA256')!=control.sha(control.canonical(cap)) or value.get('bootId')!=cap['bootId']:raise control.Refused('authentic_component_ack_tuple')
   acks[role]=value
  # Models do not emit invented callbacks. Reobserve original Docker native and
  # attach identities after component ACKs, then publish this actual observation.
  self.healthy();publish(self.root/'supervisor-ready.json',{'owner':cap['newOwner'],'resources':self.observe(),'bootId':cap['bootId'],'capabilitySHA256':control.sha(control.canonical(cap))},public=True)
  checked=wait_channel(self.root/'monitor/verified.json',end,uid=self.ledger.uid,check=self.healthy)
  initial=read_channel(self.root/'monitor/startup-ack.json',self.ledger.uid)
  if checked.get('monitorBirth')!=initial.get('monitorBirth') or process_identity(checked['monitorBirth']['pid'])!=checked['monitorBirth']:raise control.Refused('independent_monitor_original_birth_not_current')
  if checked.get('owner')!=cap['newOwner'] or checked.get('resources')!=cap['resources'] or checked.get('capabilitySHA256')!=control.sha(control.canonical(cap)) or not checked.get('monitorBirth'):raise control.Refused('independent_new_owner_ack_required')
  return {'owner':cap['newOwner'],'resources':cap['resources'],'bootId':cap['bootId'],'componentAcks':acks,'independentMonitor':checked,'modelAcknowledgment':'GENUINE_ORIGINAL_RESOURCE_OBSERVATION_NO_CONTAINER_CALLBACK'}
 def relinquish(self,cap,ack):
  value=wait_channel(self.root/'monitor/relinquish.json',handoff.timestamp(cap['prepareExpires']),uid=self.ledger.uid,check=self.healthy)
  if value.get('monitorBirth')!=ack['independentMonitor']['monitorBirth'] or process_identity(value['monitorBirth']['pid'])!=value['monitorBirth']:raise control.Refused('original_finite_monitor_relinquish_birth')
  if value.get('owner')!=cap['oldOwner'] or value.get('capabilitySHA256')!=control.sha(control.canonical(cap)) or value.get('verifiedSHA256')!=control.sha(control.canonical(ack['independentMonitor'])):raise control.Refused('finite_relinquishment_before_verified_owner')
  return value
 def transact(self,raw,signature):
  cap=self.cap;state=self.ledger.read()
  # Public signature/evidence references have no credential contents. UID1000
  # never needs permission to read private original root qualification logs.
  state=self.ledger.cas(state['version'],state['owner'],'FINITE',{'signedCapability':{'rawHex':raw.hex(),'signatureHex':signature.hex()}})
  return handoff.transition(self.ledger,cap,prepare=self.prepare,commit=self.commit,ack=self.ack,relinquish=self.relinquish,observe=self.observe)


def finite_monitor(graph,go,*,uid=0,production=True,timeout=None):
 """Never owns persistent Popen handles or signals guessed supervisor PIDs.

 Monitor independently observes genuine topology before old finite release. A
 failed monitor writes only its exact cancel channel; original supervisor closes
 its own resources under the initial signed finite deadline.
 """
 import service_supervisor
 root=channels(graph);self_birth=process_identity(os.getpid());deadline=service_supervisor.epoch(go,'inference') if timeout is None else timeout
 verified=False;relinquished=False
 try:
  startup=wait_channel(root/'startup.json',deadline,uid=uid)
  exact_owner(startup['owner'],startup['resources'],finite=self_birth,production=production)
  publish(root/'monitor/startup-ack.json',{'monitorBirth':self_birth,'owner':startup['owner'],'resources':startup['resources'],'bootId':go['bootId'],'actualUtc':control.utc()})
  while time.time()<deadline:
   state=read_channel(root/'state.json',uid)
   if state['state']=='QUARANTINE':raise control.Refused('supervisor_quarantined')
   if state['state']=='COMMIT_PENDING_ACK' and (root/'supervisor-ready.json').exists() and not verified:
    ready=read_channel(root/'supervisor-ready.json',uid);cap=state['capability'] if 'capability' in state else control.parse_proof(bytes.fromhex(state['signedCapability']['rawHex']))
    if ready['owner']!=cap['newOwner'] or ready['resources']!=state['resources'] or ready['bootId']!=go['bootId'] or ready['capabilitySHA256']!=state['capabilitySHA256']:raise control.Refused('supervisor_ready_current_signed_tuple')
    if production:
     signed=state['signedCapability'];raw=bytes.fromhex(signed['rawHex']);signature=bytes.fromhex(signed['signatureHex'])
     old=startup['owner'];current={'bootId':go['bootId'],'ociImageId':graph['rootOwnerEvidence']['imageId'],'oldOwner':old,'newOwner':dict(old,nonce=cap['nonce']),'resources':state['resources'],'admissionLease':{'state':'NORMAL_PREPARED_EXCLUSIVE'},'hostContract':contract(graph),'credentials':credential_identities(graph)}
     cap=handoff.validate(raw,signature,graph,current)
    value=exact_owner(ready['owner'],ready['resources'],finite=self_birth,production=production)
    value.update(monitorBirth=self_birth,bootId=go['bootId'],capabilitySHA256=state['capabilitySHA256'])
    publish(root/'monitor/verified.json',value);verified=True
   if state['state']=='ACK_PENDING_RELINQUISH' and verified and not relinquished:
    cap=control.parse_proof(bytes.fromhex(state['signedCapability']['rawHex']))
    value=read_channel(root/'monitor/verified.json',uid)
    exact_owner(cap['newOwner'],state['resources'],finite=self_birth,production=production)
    publish(root/'monitor/relinquish.json',{'owner':cap['oldOwner'],'capabilitySHA256':state['capabilitySHA256'],'verifiedSHA256':control.sha(control.canonical(value)),'monitorBirth':self_birth,'actualUtc':control.utc()});relinquished=True
   if state['state']=='NORMAL':
    if not verified or not relinquished or not state.get('oldOwnerRelinquish'):raise control.Refused('normal_without_original_monitor_handshake')
    exact_owner(state['owner'],state['resources'],finite=self_birth,production=production)
    publish(root/'monitor/normal-observed.json',{'owner':state['owner'],'version':state['version'],'monitorBirth':self_birth,'resources':state['resources'],'actualUtc':control.utc()})
    return {'state':'INDEPENDENT_NORMAL_OWNER_VERIFIED_FINITE_MONITOR_RELINQUISHED','originalMonitorBirth':self_birth}
   time.sleep(.025)
  raise TimeoutError('finite_monitor_entire_wall_deadline')
 except BaseException as exc:
  # Atomic NORMAL wins over late finite cancellation; state alone is insufficient
  # to invent proof. Original supervisor checks ownership before handling cancel.
  try:publish(root/'monitor/cancel.json',{'monitorBirth':self_birth,'failure':str(exc),'actualUtc':control.utc()})
  except OSError:pass
  raise

class OriginalChildren:
 """Bounded local/launcher Popen ownership with original gates, waits and logs.

 This owns from the instant Popen returns, including post-Popen birth failures.
 It never adopts another PID's wait handle. Used by executable topology fixtures
 and the launcher for its SHORT systemd-run helper, never its persistent service.
 """
 def __init__(self,path,*,fault=None):self.path=Path(path);self.items={};self.fault=fault
 def launch(self,name,argv,*,env=None):
  import subprocess,receipt_recorder as r
  readfd,writefd=os.pipe();p=None;log=None;err=None
  item={'argv':argv,'cwd':str(Path.cwd()),'environment':dict(env or {'PATH':'/usr/bin:/bin','LC_ALL':'C','PYTHONDONTWRITEBYTECODE':'1'}),'startUtc':control.utc(),'birth':None,'identity':None,'pgid':None,'waited':False}
  try:
   log=(self.path/(name+'.stdout')).open('xb');err=(self.path/(name+'.stderr')).open('xb')
   for f in (log,err):os.chmod(f.name,0o600)
   p=subprocess.Popen([__import__('sys').executable,'-I','-c',r._GATE,str(readfd),*argv],cwd=item['cwd'],env=item['environment'],stdout=log,stderr=err,pass_fds=(readfd,),start_new_session=True,stdin=subprocess.DEVNULL)
   item.update(p=p,log=log,err=err,pid=p.pid);self.items[name]=item
   if self.fault:self.fault('after_popen',name)
   item['pgid']=os.getpgid(p.pid);item['birth']=r.birth(p.pid)
   if item['birth'] is None:raise control.Refused('original_birth_missing')
   item['identity']=process_identity(p.pid);item['initialInventory']=r.inventory(item['pgid'])
   if self.fault:self.fault('metadata_write',name)
   publish(self.path/(name+'.identity.json'),{k:v for k,v in item.items() if k not in ('p','log','err')})
   os.write(writefd,b'G')
   return item
  except BaseException:
   if p is not None:self.close_one(name)
   else:
    if log:log.close()
    if err:err.close()
   raise
  finally:os.close(readfd);os.close(writefd)
 def check(self,*,cap=1048576):
  for name,x in self.items.items():
   if x.get('waited'):continue
   if x['p'].poll() is not None:raise control.Refused('original_child_early_exit:'+name)
   if Path(x['log'].name).stat().st_size+Path(x['err'].name).stat().st_size>cap:raise control.Refused('original_child_output_cap:'+name)
 def close_one(self,name,*,deadline=None):
  import signal,subprocess,receipt_recorder as r
  x=self.items[name];p=x['p']
  if x['waited']:return x['terminal']
  errors=[];code=None
  try:
   if p.poll() is None:
    same=x['birth'] is not None and r.birth(p.pid)==x['birth'] and x['pgid']==p.pid and os.getpgid(p.pid)==p.pid
    if same:os.killpg(p.pid,signal.SIGTERM)
    else:p.terminate() # still-owned original direct child, no external identity
    try:p.wait(timeout=1)
    except subprocess.TimeoutExpired:
     if same and r.birth(p.pid)==x['birth']:os.killpg(p.pid,signal.SIGKILL)
     else:p.kill()
   code=p.wait(timeout=2)
  except BaseException as exc:errors.append({'stage':'bounded_close','type':type(exc).__name__,'message':str(exc)})
  finally:
   if p.returncode is None:
    try:p.kill()
    except ProcessLookupError:pass
   code=p.wait();x['waited']=True
  value={k:v for k,v in x.items() if k not in ('p','log','err','terminal')}
  value.update(actualExitCode=code,endUtc=control.utc(),directPopenWait=True,finalInventory=None,knownDirectPidAbsent=None,originalBirthAbsent=None,originalGroupAbsent=None,stdout=None,stderr=None,errors=errors,status='QUARANTINE_PARTIAL_EVIDENCE')
  x['terminal']=value
  def attempt(stage,operation):
   try:return operation()
   except BaseException as exc:errors.append({'stage':stage,'type':type(exc).__name__,'message':str(exc)});return None
  attempt('durable_original_wait',lambda:publish(self.path/(name+'.wait.json'),dict(value)))
  if errors:attempt('wait_fallback',lambda:publish(self.path/(name+'.wait-fallback.json'),dict(value)))
  for stream in ('log','err'):
   f=x[stream];attempt(stream+'_flush',f.flush);attempt(stream+'_fsync',lambda:os.fsync(f.fileno()));attempt(stream+'_close',f.close)
  if x['pgid'] is not None:
   inventory=attempt('final_inventory',lambda:r.inventory(x['pgid']));value['finalInventory']=inventory
   if inventory is not None:value['originalGroupAbsent']=not inventory['rows']
  born=attempt('direct_birth_absence',lambda:r.birth(p.pid));value['knownDirectPidAbsent']=born is None and not any(e['stage']=='direct_birth_absence' for e in errors)
  if x['birth'] is not None:value['originalBirthAbsent']=born!=x['birth'] if not any(e['stage']=='direct_birth_absence' for e in errors) else None
  for label,key in [('stdout','log'),('stderr','err')]:
   digest=attempt(label+'_digest',lambda:r.digest(x[key].name))
   if digest is not None:value[label]={'path':x[key].name,**digest}
  if not errors and value['originalBirthAbsent'] is True and value['originalGroupAbsent'] is True:value['status']='WAITED_ABSENT'
  attempt('terminal_publication',lambda:publish(self.path/(name+'.terminal.json'),dict(value)))
  if errors:
   value['status']='QUARANTINE_PARTIAL_EVIDENCE';attempt('terminal_fallback',lambda:publish(self.path/(name+'.terminal-fallback.json'),dict(value)))
  return value
 def wait_one(self,name,deadline):
  import subprocess
  try:self.items[name]['p'].wait(timeout=max(.001,deadline-time.time()))
  except subprocess.TimeoutExpired:raise TimeoutError('original_child_whole_wall_timeout:'+name)
  return self.close_one(name)
 def close(self):
  results=[]
  for name in reversed(list(self.items)):
   try:results.append(self.close_one(name))
   except BaseException as exc:results.append({'name':name,'failure':str(exc),'status':'QUARANTINE_UNREAPED_OR_UNKNOWN'})
  return results


def startup_argv(graph,nonce):
 """Exact root-signed launch argv; systemd creates original separate parent."""
 import re
 if not re.fullmatch('[a-f0-9]{64}',nonce):raise control.Refused('startup_nonce')
 unit='h044-vision-'+nonce+'.service';entry=graph['sourceRoot']+'/scripts/h044/vision_runtime/normal_service.py'
 return ['/usr/bin/systemd-run','--unit='+unit,'--service-type=exec','--property=Restart=no','--property=KillMode=control-group','--property=TimeoutStopSec=15s','--property=User=root','--property=Group=root','--property=UMask=0077','--property=StandardOutput=journal','--property=StandardError=journal','/usr/bin/python3','-I','-B',entry,'--supervise']


def launcher():
 import service_supervisor,receipt_recorder
 graph,go=control.current_authority('load')
 expected=graph['runtime']['normalHandoff']['launcher']
 if expected!={'mode':'SYSTEMD_TYPE_EXEC_ORIGINAL_SUPERVISOR','argvTemplate':startup_argv(graph,'a'*64),'nonceTemplate':'a'*64,'finiteKillParent':False}:raise control.Refused('signed_concrete_launcher_descriptor')
 # Initial exclusive authorization is spent by outer executor BEFORE launch.
 for action in ('load','inference','stop'):
  claim=read_channel(Path(control.PHASE_ROOT)/('spent-'+go['nonce']+'-'+action+'.json'))
  if claim.get('carrierSHA256')!=control.sha(control.read_private(control.PHASE_ROOT+'/CURRENT-GO.json',0)) or claim.get('count')!=1 or claim.get('scheduleEntry')!='load':raise control.Refused('root_finite_initial_start_claim')
 argv=startup_argv(graph,go['nonce']);r=receipt_recorder.record(argv,control.PHASE_ROOT,environment={'PATH':'/usr/bin:/bin','LC_ALL':'C'},timeout=max(.01,service_supervisor.epoch(go,'load')-time.time()),label=go['nonce']+'-separate-systemd-launch')
 if r['status']!='COMPLETE' or r['actualExitCode']!=0:raise control.Refused('separate_service_launch_unknown_finite_supervisor_must_self_settle')
 # This finite process never has a Popen object for supervisor or its children.
 return finite_monitor(graph,go)


def credential_identities(graph):
 import stat
 result={}
 for role,path in graph['runtime']['service']['credentialPaths'].items():
  p=Path(path)
  if str(p)!=os.path.realpath(p):raise control.Refused('credential_original_canonical_path')
  for ancestor in p.parents:
   a=ancestor.lstat()
   if not ancestor.is_dir() or ancestor.is_symlink() or a.st_uid not in (0,1000) or a.st_mode&0o022:raise control.Refused('credential_original_protected_ancestor')
  s=p.lstat()
  if p.is_symlink() or not stat.S_ISREG(s.st_mode) or s.st_uid!=1000 or s.st_nlink!=1 or stat.S_IMODE(s.st_mode) not in (0o400,0o600):raise control.Refused('actual_UID1000_original_credential_descriptor')
  result[role]={'path':path,'dev':s.st_dev,'inode':s.st_ino,'uid':s.st_uid,'gid':s.st_gid,'mode':stat.S_IMODE(s.st_mode),'bytes':s.st_size,'mtimeNs':s.st_mtime_ns,'ctimeNs':s.st_ctime_ns}
 return result


def normal_cleanup_decision(graph,ledger,cap,resources,raw,signature,requested,*,clock=time.time,verify=handoff.verify_signature):
 """Read-only authority check BEFORE any original child/resource settlement.

 cap/raw/signature are the last authentically admitted (or renewed) capability,
 not a reconstructed history. Faults, signals and finite expiry grant nothing.
 Unknown current ownership keeps the original wait parent in quarantine.
 """
 state=ledger.read()
 if (state['state']!='NORMAL' or state['owner']!=cap['newOwner'] or
     state['resources']!=resources or resources!=cap['resources'] or
     state['bootId']!=cap['bootId'] or not state.get('newOwnerAck') or
     not state.get('oldOwnerRelinquish') or
     state.get('capabilitySHA256')!=control.sha(control.canonical(cap)) or
     state.get('normalLeaseExpires')!=cap['normalLeaseExpires'] or
     state.get('signedCapability')!={'rawHex':raw.hex(),'signatureHex':signature.hex()} or
     control.parse_proof(raw)!=cap or
     cap['sourceGraphSHA256']!=control.sha(control.canonical(graph)) or
     cap['newOwner']['supervisorBirth']!=process_identity(os.getpid()) or
     cap['newOwner'].get('supervisorDomain')!=DOMAIN):
  raise control.Refused('normal_cleanup_exact_admitted_owner_quarantine')
 now=clock()
 request=requested(state)
 if request:
  try:approved=handoff.validate_normal_control(*request,state,graph,now=now,verify=verify)
  except (OSError,ValueError,KeyError,TypeError):
   if now<handoff.timestamp(cap['normalLeaseExpires']):raise
  else:return {'reason':'NORMAL_OWNER_SIGNED_SHUTDOWN','state':state,'request':approved,'rawSHA256':control.sha(request[0])}
 if now>=handoff.timestamp(cap['normalLeaseExpires']):
  return {'reason':'NORMAL_LEASE_EXPIRED_OWNED_SHUTDOWN','state':state}
 return None


def await_normal_cleanup(graph,ledger,capability,resources,requested,*,clock=time.time,verify=handoff.verify_signature,pause=time.sleep,on_deferred=lambda value:None):
 """Keep ORIGINAL parent/handles alive until current normal authority permits.

 No close, signal, resource stop or finite-deadline fallback on refusal. Missing
 ledger/metadata is truthful quarantine, including after nominal lease expiry.
 """
 previous=None
 while True:
  try:
   cap,raw,signature=capability()
   decision=normal_cleanup_decision(graph,ledger,cap,resources,raw,signature,requested,clock=clock,verify=verify)
   if decision:return decision
   why='NORMAL_UNEXPIRED_NO_SIGNED_SHUTDOWN'
  except (OSError,ValueError,KeyError,TypeError) as exc:why='QUARANTINE_NO_NORMAL_CLEANUP_AUTHORITY:'+str(exc)
  if why!=previous:on_deferred(why);previous=why
  pause(.025)


def settle_normal_owned(graph,ledger,capability,resources,requested,close,stop,**options):
 """One authority gate shared by the real supervisor and executable fixture.

 Serialize the exact decision through child settlement against normal renew/CAS.
 A changed state restarts admission without closing any original child handle.
 """
 while True:
  decision=await_normal_cleanup(graph,ledger,capability,resources,requested,**options)
  with ledger.lock():
   if ledger.read()!=decision['state']:continue
   def authorize():
    if ledger.read()!=decision['state']:raise control.Refused('normal_cleanup_state_changed_quarantine')
    return graph,capability()[0]
   authorize()
   children=close()
   try:cleanup=stop(authorize)
   except BaseException as exc:cleanup={'state':'QUARANTINE','failure':str(exc)}
   return decision,children,cleanup


def supervise():
 """Original steady PID creates and waits every attach/service/ingress child."""
 import service_supervisor as ss,lifecycle,observer,signal
 graph,go=control.current_authority('load')
 if os.getpgrp()!=os.getpid():os.setsid() # foreground original process, no fork
 b=process_identity(os.getpid());unit='h044-vision-'+go['nonce']+'.service'
 if b['ppid']!=1 or '/'+unit not in b['cgroup']:raise control.Refused('initial_separate_systemd_topology_required')
 root=install_channels(graph);ledger=handoff.Ledger(root);manager=ss.SteadyChildren(graph,go)
 finite=ss.epoch(go,'inference');stop_end=ss.epoch(go,'stop');owners=[];resources=[];normal=None;failure=None;reason=None;cap=None;raw=None;sig=None
 old={'nonce':go['nonce'],'supervisorBirth':b,'supervisorDomain':DOMAIN,'unit':unit}
 credentials=credential_identities(graph);protected=observer.protected_instances(graph,observer.snapshot());closing=[]
 signal.signal(signal.SIGTERM,lambda *_:closing.append('TERM'));signal.signal(signal.SIGINT,lambda *_:closing.append('INT'))
 def requested(state):
  if (root/'shutdown.json').exists() and (root/'shutdown.sig').exists():return public_read(root/'shutdown.json'),public_read(root/'shutdown.sig')
 def healthy():
  if closing:raise control.Refused('original_supervisor_stop_signal')
  manager.check_output_and_liveness()
  if credential_identities(graph)!=credentials:raise control.Refused('original_credential_identity_changed')
  observer.residency_sample(graph,owners)
 def observe():
  import json
  value=[]
  sample=observer.residency_sample(graph,owners)
  for model in owners:
   q=observer.exact_container(model['id'])
   if q.get('birth')!=model['birth'] or not q.get('value',{}).get('running'):raise control.Refused('original_container_birth_changed')
   attach=manager.children['attach-'+model['role']]['birth']
   if observer.birth(attach['pid'])!=attach:raise control.Refused('original_docker_attach_birth_changed')
   value.append({'role':model['role'],'id':model['id'],'birth':model['birth'],'image':model['image'],'devices':model['devices'],'startedAt':model['startedAt'],'attachBirth':attach,'gpuProcessBirths':sorted([x['birth'] for x in next(x for x in sample['snapshot']['containers'] if x.get('value',{}).get('id')==model['id'])['ownedGpuProcessBirths']],key=lambda x:x['pid'])})
  for role in ('service','ingress'):
   x=manager.children[role];birth=observer.birth(x['p'].pid)
   if birth!=x['birth'] or birth['ppid']!=os.getpid():raise control.Refused('original_service_direct_parent_changed')
   value.append({'role':role,'birth':birth,'id':str(x['p'].pid)})
  n=read_channel(Path(control.PHASE_ROOT)/('network-'+go['nonce']+'.json'))
  _,raw=lifecycle.docker(['network','inspect','--format',lifecycle.NETWORK_INSPECT,n['id']],time.time()+5,go['nonce']+'-normal-network-'+str(time.monotonic_ns()))
  actual=json.loads(raw)
  if (actual['id'],actual['owner'],actual['nonce'])!=(n['id'],lifecycle.OWNER,go['nonce']):raise control.Refused('original_network_identity_changed')
  value.append({'role':'network','id':n['id'],'bootId':n['bootId']})
  return sorted(value,key=lambda x:x['role'])
 try:
  owners=lifecycle.load(graph,go['nonce'],ss.epoch(go,'load'),manager=manager)
  manager.launch('service');manager.launch('ingress');manager.launch('health')
  health=manager.wait('health',ss.epoch(go,'load'))
  if health['actualExitCode']!=0 or health['state']!='WAITED_ABSENT':raise control.Refused('actual_authenticated_startup_health')
  resources=observe();ledger.initialize(old,resources,go['bootId'])
  publish(root/'startup.json',{'owner':old,'resources':resources,'bootId':go['bootId'],'credentials':credentials,'graphSHA256':control.sha(control.canonical(graph))},public=True)
  monitor=wait_channel(root/'monitor/startup-ack.json',ss.epoch(go,'load'),check=healthy)
  if monitor.get('owner')!=old or monitor.get('resources')!=resources:raise control.Refused('initial_independent_monitor_identity_ack')
  if monitor['monitorBirth']['cgroup']==b['cgroup'] or monitor['monitorBirth']['pgid']==b['pgid']:raise control.Refused('finite_monitor_not_separate')
  manager.launch('workload');workload=manager.wait('workload',finite)
  if workload['actualExitCode']!=0 or workload['state']!='WAITED_ABSENT':raise control.Refused('actual_concurrent_workload_failed')
  publish(root/'workload-ready.json',{'originalWorkload':workload,'resources':observe(),'sixResident':observer.residency_sample(graph,owners),'credentials':credentials,'status':'ROOT_ACCURACY_TIMING_ORIGINAL_RECEIPT_REVIEW_REQUIRED'},public=True)
  while time.time()<finite:
   healthy()
   if (root/'monitor/cancel.json').exists():raise control.Refused('unadopted_finite_monitor_cancel')
   if (root/'adoption.json').exists() and (root/'adoption.sig').exists():
    from trusted_imports import protected_bytes
    raw=protected_bytes(root/'adoption.json',0);sig=protected_bytes(root/'adoption.sig',0)
    proposed=control.parse_proof(raw);current={'bootId':go['bootId'],'ociImageId':graph['rootOwnerEvidence']['imageId'],'oldOwner':old,'newOwner':dict(old,nonce=proposed['nonce']),'resources':observe(),'admissionLease':{'state':'NORMAL_PREPARED_EXCLUSIVE'},'hostContract':contract(graph),'credentials':credentials}
    control.verify_source(graph,control.SOURCE_ROOT,control.SOURCE_ROOT+'/scripts/h044/vision_runtime')
    cap=handoff.validate(raw,sig,graph,current)
    if cap['newOwner']['supervisorBirth']!=b or cap['newOwner']['supervisorDomain']!=DOMAIN:raise control.Refused('actual_original_supervisor_authority_adoption_only')
    transaction=ChannelHandshake(graph,ledger,cap,observe);transaction.transact(raw,sig)
    normal=NormalOwner(graph,ledger,cap,manager,resources,inspect=observe,callbacks={},capability_raw=raw,signature=sig,current_tuple=lambda:current)
    try:publish(root/'normal-owner.json',{'originalSupervisorBirth':b,'owner':cap['newOwner'],'resources':observe(),'directWaitHandlesRemainOriginal':True},public=True)
    except OSError as metadata_error:
     # NORMAL atomic state+verified ACKs are already durable. A supplementary
     # report failure cannot resurrect expired finite cleanup authority.
     print('NORMAL supplementary metadata failure; original steady ownership retained:'+str(metadata_error),file=__import__('sys').stderr,flush=True)
    renewal_sequence=[1]
    def renewed(state):
     prefix='renewal-%06d'%renewal_sequence[0];body=root/(prefix+'.json');signature=root/(prefix+'.sig')
     if body.exists() and signature.exists():
      pair=(protected_bytes(body,0),protected_bytes(signature,0));publish(root/(prefix+'-consumed.json'),{'rawSHA256':control.sha(pair[0]),'originalOwner':state['owner']});renewal_sequence[0]+=1;return pair
    reason=normal.govern(stop_requested=requested,renew=renewed,pause=lambda t:(healthy(),time.sleep(t)))
    break
   time.sleep(.05)
  else:reason='FINITE_AUTHORITY_EXPIRED_NO_ADOPTION'
 except BaseException as exc:failure=str(exc)
 finally:
  # Determine current cleanup authority before manager.close() can signal ANY
  # attach/service/ingress child. The original supervisor cannot exit and leave
  # admitted normal children without their direct Popen wait parent.
  normal_required=normal is not None
  if not normal_required and (root/'state.json').exists():
   while True:
    try:
     state=ledger.read()
     if handoff.cleanup_policy(state,old,resources)=='CLOSE_EXACT_FINITE_OWNED_RESOURCES':break
     if cap is None:raise control.Refused('unknown_handoff_without_admitted_capability')
    except (OSError,ValueError,KeyError,TypeError) as exc:
     print('QUARANTINE original handles retained:'+str(exc),file=__import__('sys').stderr,flush=True);time.sleep(.2);continue
    # A post-CAS exception must not silently restore finite cleanup. Keep the
    # original admitted capability; do not fabricate a successor owner/handle.
    normal_required=True
    break
  if normal_required:
   decision,child_receipts,cleanup=settle_normal_owned(graph,ledger,
    lambda:(normal.cap,normal.capability_raw,normal.signature) if normal else (cap,raw,sig),resources,requested,
    lambda:manager.close(time.time()+15),lambda authorize:lifecycle.stop(graph,go['nonce'],time.time()+30,authorize=authorize),
    on_deferred=lambda why:print(why+'; original parent and handles retained',file=__import__('sys').stderr,flush=True))
   reason=decision['reason']
  else:
   child_receipts=manager.close(stop_end)
   try:cleanup=lifecycle.stop(graph,go['nonce'],stop_end)
   except BaseException as exc:cleanup={'state':'QUARANTINE','failure':str(exc)}
  try:
   if observer.protected_instances(graph,observer.snapshot())!=protected:raise control.Refused('other_four_original_instances_changed')
  except BaseException as exc:failure=(failure or '')+';'+str(exc)
  publish(root/'supervisor-terminal.json',{'originalSupervisorBirth':b,'reason':reason,'failure':failure,'children':child_receipts,'cleanup':cleanup,'qualification':'NOT_TESTED_UNTIL_GENUINE_ROOT_REVIEW'})
 if failure:raise control.Refused(failure)
 return reason

# Executable source fixtures use a separate LOCAL HMAC fixture anchor. This path
# is unavailable in root /opt deployment and never accepts/produces live evidence.
def fixture_spec(path):
 import sys
 from trusted_imports import protected_bytes
 if os.geteuid()==0 or str(Path(__file__).resolve()).startswith('/opt/') or sys.platform!='darwin':raise control.Refused('LOCAL_SOURCE_FIXTURE_ONLY_NOT_OPERATIONAL_AUTHORITY')
 spec=control.parse_proof(protected_bytes(Path(path),os.geteuid()))
 if spec.get('evidence')!='SOURCE_ONLY_SYNTHETIC_EXECUTABLE_TOPOLOGY':raise control.Refused('explicit_local_source_fixture_required')
 return spec

def fixture_sign(spec,raw):
 import hmac,hashlib
 return hmac.new(bytes.fromhex(spec['fixtureAnchorHex']),raw,hashlib.sha256).digest()

def fixture_verify(spec,raw,sig):
 import hmac
 return hmac.compare_digest(fixture_sign(spec,raw),sig)

def fixture_graph(spec):
 root=Path(spec['channels'])
 return {'sourceRoot':str(Path(__file__).absolute().parents[3]),'runtime':{'normalHandoff':{'status':STATUS,'statePath':str(root/'state.json'),'capabilityPath':str(root/'adoption.json'),'signaturePath':str(root/'adoption.sig'),'componentAckRoot':str(root/'components')}}}

def fixture_go(spec):
 import datetime
 iso=lambda t:datetime.datetime.fromtimestamp(t,datetime.timezone.utc).isoformat()
 return {'bootId':'LOCAL_SOURCE_FIXTURE_BOOT','nonce':'a'*64,'actionDeadlines':{'load':iso(spec['finiteEnd']),'inference':iso(spec['finiteEnd']),'stop':iso(spec['finiteEnd']+2)}}

def fixture_member(spec,role):
 import sys
 root=Path(spec['channels']);graph=fixture_graph(spec);me=process_identity(os.getpid());uid=os.geteuid();last=set();deadline=spec['finiteEnd']
 while time.time()<deadline:
  if (root/'state.json').exists():
   state=read_channel(root/'state.json',uid)
   if state['state'] in ('PREPARED','COMMIT_PENDING_ACK','ACK_PENDING_RELINQUISH','NORMAL'):
    signed=state['signedCapability'];raw=bytes.fromhex(signed['rawHex']);sig=bytes.fromhex(signed['signatureHex']);cap=control.parse_proof(raw)
    if not fixture_verify(spec,raw,sig):raise control.Refused('source_fixture_signature_rejected')
    if role in ('service','ingress') and state['state']!='NORMAL' and state['state'] not in last and spec['case']!='missing-ack':
     phase=state['state'];value={'nonce':cap['nonce'],'role':role,'phase':phase,'birth':me,'actualUid':uid,'descriptorReadable':True,'capabilitySHA256':control.sha(control.canonical(cap)),'bootId':cap['bootId'],'actualUtc':control.utc()}
     if spec['case']=='wrong-ack':value['birth']={'pid':1,'evidence':'SOURCE_ONLY_BAD_IDENTITY'}
     publish(root/'components'/role/(cap['nonce']+'-'+role+'-'+phase+'.json'),value);last.add(phase)
    if state['state']=='NORMAL':
     match=next(x for x in cap['resources'] if x['role']==role)
     if match['birth']!=me:raise control.Refused('source_fixture_original_birth_changed')
     deadline=handoff.timestamp(cap['normalLeaseExpires'])
  if spec['case']=='output-cap' and role=='ocr':sys.stdout.write('x'*70000)
  else:print('usable-original-child',role,time.time(),flush=True)
  sys.stdout.flush();time.sleep(.025)
 return 0

def fixture_supervisor(spec,path):
 import sys,signal
 graph=fixture_graph(spec);root=install_channels(graph,uid=os.geteuid(),component_uid=os.geteuid());b=process_identity(os.getpid());go=fixture_go(spec);uid=os.geteuid();manager=OriginalChildren(root/'logs',fault=lambda point,name:(_ for _ in ()).throw(OSError('SOURCE_ONLY_INJECTED_METADATA_WRITE')) if spec['case'] in ('metadata-write','post-popen-birth') and point==('metadata_write' if spec['case']=='metadata-write' else 'after_popen') and name=='service' else None)
 old={'nonce':go['nonce'],'supervisorBirth':b,'supervisorDomain':DOMAIN,'unit':'LOCAL_SOURCE_FIXTURE_SESSION'};resources=[];ledger=handoff.Ledger(root,uid=uid);normal=False;failure=None;reason=None;cancel=[]
 signal.signal(signal.SIGTERM,lambda *_:cancel.append('TERM'))
 def observe():
  values=[]
  for role in ('interpretation','ocr','service','ingress'):
   x=manager.items[role];birth=process_identity(x['p'].pid)
   if birth!=x['identity']:raise control.Refused('actual_source_fixture_birth_changed')
   values.append({'role':role,'id':str(x['p'].pid),'birth':birth})
  values.append({'role':'network','id':'LOCAL_SOURCE_FIXTURE_NO_NETWORK'})
  return sorted(values,key=lambda x:x['role'])
 try:
  for role in ('interpretation','ocr','service','ingress'):
   if spec['case']=='partial-launch' and role=='ingress':raise OSError('SOURCE_ONLY_INJECTED_PARTIAL_LAUNCH')
   manager.launch(role,[sys.executable,'-I','-B',__file__,'--source-fixture-member',path,role])
  resources=observe();ledger.initialize(old,resources,go['bootId']);publish(root/'startup.json',{'owner':old,'resources':resources,'bootId':go['bootId']},public=True)
  wait_channel(root/'monitor/startup-ack.json',spec['finiteEnd'],uid=uid,check=manager.check)
  while time.time()<spec['finiteEnd']:
   manager.check(cap=65536 if spec['case']=='output-cap' else 1048576)
   if cancel or (root/'monitor/cancel.json').exists():raise control.Refused('SOURCE_ONLY_FINITE_CANCEL')
   if (root/'adoption.json').exists():
    from trusted_imports import protected_bytes
    raw=protected_bytes(root/'adoption.json',uid);sig=protected_bytes(root/'adoption.sig',uid)
    if not fixture_verify(spec,raw,sig):raise control.Refused('SOURCE_ONLY_SIGNATURE_FAILURE')
    cap=control.parse_proof(raw)
    if cap['resources']!=observe() or cap['oldOwner']!=old or cap['newOwner']['supervisorBirth']!=b or time.time()>=handoff.timestamp(cap['prepareExpires']):raise control.Refused('SOURCE_ONLY_EXACT_OWNER_OR_EXPIRY_REJECTED')
    ChannelHandshake(graph,ledger,cap,observe,verify=lambda a,s:fixture_verify(spec,a,s),component_uid=uid,fixture=True).transact(raw,sig)
    normal=True
    if spec['case']=='normal-metadata-shutdown':raise OSError('SOURCE_ONLY_SUPPLEMENTARY_METADATA_FAILURE_AFTER_NORMAL')
    while time.time()<handoff.timestamp(ledger.read()['normalLeaseExpires']):
     if cancel:raise control.Refused('SOURCE_ONLY_NORMAL_TERM_WITHOUT_SIGNED_SHUTDOWN')
     if (root/'normal-fault.json').exists():raise OSError('SOURCE_ONLY_NORMAL_FAULT_WITHOUT_SIGNED_SHUTDOWN')
     manager.check()
     state=ledger.read()
     if state['state']!='NORMAL' or state['owner']!=cap['newOwner']:raise control.Refused('SOURCE_ONLY_COLLISION_QUARANTINE')
     if (root/'shutdown.json').exists():
      request=protected_bytes(root/'shutdown.json',uid);signature=protected_bytes(root/'shutdown.sig',uid)
      handoff.validate_normal_control(request,signature,state,graph,verify=lambda a,s:fixture_verify(spec,a,s));reason='SIGNED_LOCAL_SOURCE_FIXTURE_SHUTDOWN';break
     time.sleep(.025)
    else:reason='SIGNED_LOCAL_SOURCE_FIXTURE_LEASE_EXPIRED'
    break
   time.sleep(.025)
  else:reason='SOURCE_ONLY_FINITE_EXPIRED_UNADOPTED'
 except BaseException as exc:
  failure=str(exc)
  if (root/'state.json').exists():
   state=ledger.read()
   if state['state']!='NORMAL':
    try:ledger.cas(state['version'],state['owner'],state['state'],{'state':'QUARANTINE','normalOwnershipGranted':False,'failure':failure})
    except (ValueError,OSError):pass
 finally:
  decision=None
  if normal:
   def requested(state):
    from trusted_imports import protected_bytes
    if (root/'shutdown.json').exists() and (root/'shutdown.sig').exists():return protected_bytes(root/'shutdown.json',uid),protected_bytes(root/'shutdown.sig',uid)
   def deferred(why):
    p=root/'normal-cleanup-deferred.json'
    if not p.exists():publish(p,{'evidence':spec['evidence'],'why':why,'failure':failure,'actualUtc':control.utc(),'originalBirth':process_identity(os.getpid()),'resources':observe(),'finiteExpired':time.time()>=spec['finiteEnd'],'childrenNotClosed':all(not x['waited'] for x in manager.items.values())},public=True)
   decision,receipts,cleanup=settle_normal_owned(graph,ledger,lambda:(cap,raw,sig),resources,requested,manager.close,
    lambda authorize:{'state':'SOURCE_ONLY_NO_LINUX_RESOURCE_STOP','authority':authorize()[1]['nonce']},verify=lambda a,s:fixture_verify(spec,a,s),on_deferred=deferred)
   reason=decision['reason']
  else:receipts=manager.close()
  publish(root/'supervisor-terminal.json',{'evidence':spec['evidence'],'failure':failure,'reason':reason,'adopted':normal,'originalBirth':b,'cleanupDecision':decision,'children':receipts})
 return 75 if failure else 0


def fixture_launcher(spec,path):
 """Actual original guardian creates supervisor and finite monitor as siblings.

 Neither daemon forks nor transfers wait handles. Guardian directly waits both;
 finite monitor can expire/exit while the independently grouped supervisor keeps
 its original children usable. This is LOCAL SOURCE evidence only.
 """
 import datetime,sys
 directory=Path(spec['artifactRoot']);root=Path(spec['channels']);uid=os.geteuid();owned=OriginalChildren(directory);failure=None;survived=None
 iso=lambda t:datetime.datetime.fromtimestamp(t,datetime.timezone.utc).isoformat()
 try:
  owned.launch('unrelated',[sys.executable,'-I','-c','import time;time.sleep(12)'])
  supervisor=owned.launch('supervisor',[sys.executable,'-I','-B',__file__,'--source-fixture-supervisor',path])
  finite=owned.launch('finite-monitor',[sys.executable,'-I','-B',__file__,'--source-fixture-monitor',path])
  if spec['case'] not in ('partial-launch','metadata-write','post-popen-birth'):
   startup=wait_channel(root/'startup.json',spec['finiteEnd'],uid=uid)
   if spec['case'] not in ('expiry','timeout','output-cap'):
    old=startup['owner'];new=dict(old,nonce='b'*64);cap={'schema':'h044-normal-adoption-v1','nonce':'b'*64,'issuer':'ROOT_AUTHENTIC_SIGNER','notBefore':iso(time.time()-.1),'prepareExpires':iso(spec['finiteEnd']),'normalLeaseExpires':iso(spec['normalEnd']),'bootId':'LOCAL_SOURCE_FIXTURE_BOOT','sourceGraphSHA256':control.sha(control.canonical(fixture_graph(spec))),'ociImageId':'LOCAL_SOURCE_FIXTURE_NO_OCI','oldOwner':old,'newOwner':new,'resources':startup['resources'],'admissionLease':{'state':'NORMAL_PREPARED_EXCLUSIVE'},'hostContract':{'normalHost':'LOCAL_SOURCE_FIXTURE_NO_NETWORK'},'credentials':{'fixture':'LOCAL_NO_CREDENTIAL_ACCESS'},'evidence':{'fixture':spec['evidence']}}
    if spec['case']=='identity-collision':cap['newOwner']['supervisorBirth']={'pid':1,'evidence':'SOURCE_ONLY_COLLISION'}
    if spec['case']=='expired-capability':cap['prepareExpires']=iso(time.time()-1)
    raw=control.canonical(cap);(root/'adoption.sig').write_bytes(fixture_sign(spec,raw) if spec['case']!='bad-signature' else b'bad');os.chmod(root/'adoption.sig',0o600);publish(root/'adoption.json',cap,public=True)
    if spec['case'] in ('success','finite-group-timeout','cas-collision','normal-term-shutdown','normal-fault-expiry','normal-metadata-shutdown'):
     state=None
     while time.time()<spec['finiteEnd']:
      state=read_channel(root/'state.json',uid)
      if state['state']=='PREPARED':break
      if state['state']=='QUARANTINE':raise control.Refused('unexpected_quarantine')
      time.sleep(.025)
    if spec['case']=='cas-collision':
     other=handoff.Ledger(root,uid=uid);state=other.read();other.cas(state['version'],state['owner'],state['state'],{'state':'QUARANTINE','failure':'SOURCE_ONLY_SEPARATE_WRITER_CAS_COLLISION'})
    commit={'schema':'h044-normal-commit-v1','issuer':'ROOT_AUTHENTIC_SIGNER','nonce':'c'*64,'action':'commit','count':1,'notBefore':iso(time.time()-.1),'expires':iso(min(spec['finiteEnd'],time.time()+2)),'bootId':cap['bootId'],'owner':new,'resourcesSHA256':control.sha(control.canonical(cap['resources'])),'graphSHA256':cap['sourceGraphSHA256'],'capabilitySHA256':control.sha(raw)}
    commitraw=control.canonical(commit);(root/'commit.sig').write_bytes(fixture_sign(spec,commitraw));os.chmod(root/'commit.sig',0o600);publish(root/'commit.json',commit,public=True)
  if spec['case']=='finite-group-timeout':
   import signal,receipt_recorder
   wait_channel(root/'monitor/normal-observed.json',spec['finiteEnd'],uid=uid)
   if receipt_recorder.birth(finite['pid'])!=finite['birth'] or os.getpgid(finite['pid'])!=finite['pid']:raise control.Refused('actual_finite_group_identity_before_signal')
   os.killpg(finite['pid'],signal.SIGTERM)
  monitor_result=owned.wait_one('finite-monitor',spec['finiteEnd']+.5)
  if spec['case'] in ('success','finite-group-timeout','normal-term-shutdown','normal-fault-expiry','normal-metadata-shutdown'):
   if monitor_result['actualExitCode']!=(-15 if spec['case']=='finite-group-timeout' else 0):raise control.Refused('actual_finite_monitor_failed')
   if spec['case']=='normal-term-shutdown':
    import signal,receipt_recorder
    if receipt_recorder.birth(supervisor['pid'])!=supervisor['birth'] or os.getpgid(supervisor['pid'])!=supervisor['pid']:raise control.Refused('original_supervisor_identity_before_TERM')
    os.killpg(supervisor['pid'],signal.SIGTERM)
   if spec['case']=='normal-fault-expiry':publish(root/'normal-fault.json',{'evidence':spec['evidence'],'actualUtc':control.utc()})
   if spec['case'].startswith('normal-'):wait_channel(root/'normal-cleanup-deferred.json',spec['finiteEnd'],uid=uid)
   while time.time()<spec['finiteEnd']+.15:time.sleep(.025)
   state=read_channel(root/'state.json',uid)
   survived=exact_owner(state['owner'],state['resources'],finite=finite['identity'],production=False)
   pulses={role:Path(root/'logs'/(role+'.stdout')).stat().st_size for role in ('service','ingress','interpretation','ocr')}
   time.sleep(.1)
   if any(Path(root/'logs'/(role+'.stdout')).stat().st_size<=size for role,size in pulses.items()):raise control.Refused('children_not_usable_after_finite_expiry')
   publish(directory/'after-finite-expiry.json',{'evidence':spec['evidence'],'actualOriginalOwner':survived,'finiteOriginalWait':monitor_result,'childrenUsableBeyondFiniteExpiry':True,'unrelatedOriginalStillPresent':process_identity(owned.items['unrelated']['p'].pid)})
   if spec['case'].startswith('normal-'):
    if any((root/'logs'/(role+'.terminal.json')).exists() for role in ('interpretation','ocr','service','ingress')):raise control.Refused('normal_children_closed_before_authority')
    publish(directory/'normal-fault-before-authority.json',{'evidence':spec['evidence'],'case':spec['case'],'observedUtc':control.utc(),'unexpiredNormalLease':time.time()<spec['normalEnd'],'oldFiniteDeadlineExpired':time.time()>spec['finiteEnd'],'sameOriginalSupervisorAndChildren':survived,'rawPulseSizesBefore':pulses,'rawPulseSizesAfter':{role:Path(root/'logs'/(role+'.stdout')).stat().st_size for role in pulses},'noChildTerminalBeforeAuthority':True,'shutdownNotPresent':not (root/'shutdown.json').exists()})
   req={'schema':'h044-normal-owner-control-v1','issuer':'ROOT_AUTHENTIC_SIGNER','nonce':'d'*64,'action':'shutdown','count':1,'notBefore':iso(time.time()-.1),'expires':iso(time.time()+2),'bootId':state['bootId'],'owner':state['owner'],'resourcesSHA256':control.sha(control.canonical(state['resources'])),'graphSHA256':control.sha(control.canonical(fixture_graph(spec))),'capabilitySHA256':state['capabilitySHA256']}
   if spec['case']!='normal-fault-expiry':
    raw=control.canonical(req);(root/'shutdown.sig').write_bytes(fixture_sign(spec,raw));os.chmod(root/'shutdown.sig',0o600);publish(root/'shutdown.json',req,public=True)
  owned.wait_one('supervisor',spec['normalEnd']+2)
  if owned.items['unrelated']['p'].poll() is not None:raise control.Refused('unrelated_original_touched')
 except BaseException as exc:failure=str(exc)
 finally:
  settled=owned.close();publish(directory/'launcher-terminal.json',{'evidence':spec['evidence'],'failure':failure,'children':settled,'afterFiniteExpiry':survived})
 return 75 if failure else 0


def main():
 import argparse,sys
 p=argparse.ArgumentParser();p.add_argument('mode',choices=('--launch','--supervise','--source-fixture-launch','--source-fixture-supervisor','--source-fixture-monitor','--source-fixture-member'));p.add_argument('inputs',nargs='*')
 # argparse treats --foo as options; exact positional mode is consumed separately.
 if len(sys.argv)<2:raise control.Refused('fixed_launcher_mode')
 mode=sys.argv[1]
 if mode in ('--launch','--supervise'):
  if len(sys.argv)!=2:raise control.Refused('no_unsigned_live_overrides')
  print(control.canonical(launcher() if mode=='--launch' else supervise()).decode());return 0
 if mode.startswith('--source-fixture-') and len(sys.argv) in (3,4):
  path=sys.argv[2];spec=fixture_spec(path)
  if mode=='--source-fixture-launch':return fixture_launcher(spec,path)
  if mode=='--source-fixture-supervisor':return fixture_supervisor(spec,path)
  if mode=='--source-fixture-monitor':
   finite_monitor(fixture_graph(spec),fixture_go(spec),uid=os.geteuid(),production=False)
   if spec['case']=='finite-group-timeout':time.sleep(12)
   return 0
  if mode=='--source-fixture-member' and len(sys.argv)==4 and sys.argv[3] in ('service','ingress','interpretation','ocr'):return fixture_member(spec,sys.argv[3])
 raise control.Refused('fixed_launcher_mode')

if __name__=='__main__':
 try:raise SystemExit(main())
 except BaseException as exc:
  if isinstance(exc,SystemExit):raise
  print(str(exc),file=__import__('sys').stderr);raise SystemExit(75)
