#!/usr/bin/env python3
"""Private H041 fan-only recovery. Import inert; executable requires root GO.
No native/model/service other than ONE existing fan unit is in this interface.
SOURCE test backends are explicitly independent of live Linux qualification.
"""
import base64, copy, fcntl, hashlib, json, math, os, re, stat, subprocess, sys, time, types
from datetime import datetime, timezone
from pathlib import Path
OLD='77a451e94ea50534bcd3cb9c012bca54752f1e38f1fc5961c2b48c7003870aa3'
NEW='85b39446d385975cc9b368dc082986bf8cf783c208a47be4a00cb789ea49297f'
UNIT_SHA='04f861f9c59caee51b6fc4f1e48b58cd5516c5705afd1dd230a1d5b788114a3b'
UNIT='sova-cha-fan3.service';SOURCE='/usr/local/lib/sova-cha-fan3/cha_fan3.py';UNIT_PATH='/etc/systemd/system/'+UNIT;STATE='/var/lib/sova-cha-fan3'
GPU='GPU-93dbfca8-ef3a-9628-a798-6a4afd0af528'
PROPS=['Id','LoadState','ActiveState','SubState','Result','MainPID','ExecMainPID','ExecMainStatus','InvocationID','NRestarts','ControlGroup','FragmentPath','User','Group','Restart','RestartUSec']
META=['st_dev','st_ino','st_uid','st_gid','st_mode','st_nlink','st_size','st_mtime_ns','st_ctime_ns']
class Fault(RuntimeError):pass
def need(condition,reason):
 if not condition:raise Fault(reason)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def encode(v):return (json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()
def decode(raw):
 def pairs(xs):
  d={}
  for k,v in xs:need(k not in d,'duplicate_json_key');d[k]=v
  return d
 def nonfinite(x):raise Fault('nonfinite_json')
 return json.loads(raw,object_pairs_hook=pairs,parse_constant=nonfinite)
def stamp(value):
 need(isinstance(value,str),'invalid_timestamp')
 try:d=datetime.fromisoformat(value.replace('Z','+00:00'))
 except ValueError:raise Fault('invalid_timestamp') from None
 need(d.tzinfo is not None,'timestamp_zone_required');n=d.timestamp();need(math.isfinite(n),'invalid_timestamp');return n
def utc():return datetime.now(timezone.utc).isoformat()
def metadata(s):return {k:getattr(s,k) for k in META}
def parents_protected(path,owners):
 for parent in Path(path).parents:
  s=parent.lstat();need(stat.S_ISDIR(s.st_mode) and s.st_uid in owners and not s.st_mode&0o022,'unprotected_parent')
def read_original(path,maximum=4*1024*1024):
 p=Path(path);s=p.lstat();need(p.resolve()==p and stat.S_ISREG(s.st_mode) and s.st_nlink==1 and s.st_size<=maximum,'unsafe_original')
 fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
 try:
  chunks=[];left=s.st_size+1
  while left:
   b=os.read(fd,min(left,65536))
   if not b:break
   chunks.append(b);left-=len(b)
  raw=b''.join(chunks);need(len(raw)==s.st_size and metadata(s)==metadata(os.fstat(fd))==metadata(p.lstat()),'original_changed');return raw,metadata(s)
 finally:os.close(fd)
def check_meta(actual,expected):
 need(isinstance(expected,dict) and all(k in expected for k in ('st_uid','st_gid','st_mode')),'frozen_metadata_required')
 need(all(actual.get(k)==v for k,v in expected.items()),'frozen_metadata_changed')
def syncdir(p):
 fd=os.open(p,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
 try:os.fsync(fd)
 finally:os.close(fd)
def durable(p,raw,mode=0o600,owner=None):
 p=Path(p);fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,mode)
 try:
  with os.fdopen(fd,'wb',closefd=False) as f:f.write(raw);f.flush();os.fsync(fd)
  if owner is not None:os.fchown(fd,*owner)
  os.fchmod(fd,mode);os.fsync(fd)
 finally:os.close(fd)
 syncdir(p.parent)
def directory(p,expected):
 s=Path(p).lstat();need(Path(p).resolve()==Path(p) and stat.S_ISDIR(s.st_mode),'unsafe_directory');check_meta(metadata(s),expected);return metadata(s)
def file_proof(p,expected=None):
 raw,m=read_original(p)
 if expected:check_meta(m,expected)
 return {'sha256':sha(raw),'bytes':len(raw),'metadata':m,'bytesBase64':base64.b64encode(raw).decode()}
def verify_tree(plan,installed=False,archived=False,phase=None):
 phase=phase or {}
 paths={'source':plan['sourcePath'],'unit':plan['unitPath'],'replacement':plan['replacementPath']}
 for name,p in paths.items():parents_protected(p,{0,plan['stateOwnerUid']})
 for name in ['state','backupParent','sourceParent','unitParent']:
  directory(plan[name+'Path'],phase.get(name,plan['metadata'][name]))
 out={k:file_proof(v,phase.get(k,plan['metadata'][k])) for k,v in paths.items()}
 need(out['source']['sha256']==(NEW if installed else OLD) and out['unit']['sha256']==UNIT_SHA and out['replacement']['sha256']==NEW,'fixed_source_unit_CAS_failed')
 state=Path(plan['statePath']);expected=set(plan['stateFiles'])-({'blocked.json'} if archived else set());need(set(p.name for p in state.iterdir())==expected,'state_inventory_changed')
 for name in expected:
  need(Path(name).name==name and name not in ('.','..') and re.fullmatch(r'[A-Za-z0-9._-]{1,120}',name),'unsafe_state_name')
  row=plan['stateFiles'][name];proof=file_proof(state/name,row['metadata']);need(proof['sha256']==row['sha256'] and proof['bytes']==row['bytes'],'state_CAS_failed');out['state/'+name]=proof
 need(decode(base64.b64decode(out['state/pending-write.json']['bytesBase64'])).get('state')=='verified','uncertain_pending_write')
 need('state/uncertain-write.json' not in out,'retained_uncertain_write_requires_separate_review')
 return out
class Window:
 def __init__(self,go,now=time.time):self.go=go;self.now=now;self.issued=stamp(go['issuedUtc']);self.cap=stamp(go['capUtc']);need(0<self.cap-self.issued<=300 and go['settlementReserveMs']==120000,'fixed_finite_fan_window_required')
 def check(self,cleanup=False):
  n=self.now();need(math.isfinite(n) and self.issued<=n<self.cap-(0 if cleanup else 120),'fan_GO_expired_or_reserve')
 def fresh(self,receipt):
  n=self.now();a=stamp(receipt['startedUtc']);b=stamp(receipt['finishedUtc']);need(math.isfinite(n) and a<=b<=n and n-b<=60 and receipt['exitCode']==0,'fresh_ordered_successful_original_required');self.check()
def parse_unit(raw):
 out={}
 for line in raw.splitlines():
  k,sep,v=line.partition('=');need(sep and k in PROPS and k not in out,'invalid_unit_observation');out[k]=v
 need(set(out)==set(PROPS),'incomplete_unit_observation')
 for k in ['MainPID','ExecMainPID','ExecMainStatus','NRestarts']:need(re.fullmatch(r'[0-9]+',out[k]) is not None,'invalid_unit_integer')
 need(out['Id']==UNIT and out['LoadState']=='loaded' and out['FragmentPath']==UNIT_PATH and out['User']=='user' and out['Group']=='user' and out['Restart']=='on-failure' and out['RestartUSec']=='30s','unit_scope_changed')
 return out
def no_owner(obs,plan=None):
 u=parse_unit(obs['unitUtf8']);need(u['ActiveState']=='failed' and u['SubState']=='failed' and u['MainPID']=='0' and u['Result']=='exit-code' and u['ExecMainStatus']=='78','exact_failed_no_owner_required')
 need(obs['cgroupProcsUtf8'] in (None,'') and obs['process'] is None,'fan_owner_or_cgroup_remaining');need(re.fullmatch(r'[a-f0-9-]{36}',obs['bootIdUtf8'].strip()) is not None,'actual_host_boot_required');
 if plan is not None:need(sha(obs['unitUtf8'].encode())==plan['failedUnitUtf8Sha256'] and obs['bootIdUtf8'].strip()==plan['hostBootId'],'frozen_failed_owner_changed')
 return u
class LinuxBackend:
 def __init__(self,plan):
  raw,_=read_original(plan['replacementPath']);need(sha(raw)==NEW,'reviewed_reader_source_required');self.reader=types.ModuleType('h041_fixed_fan_source');self.reader.__file__=plan['replacementPath'];exec(compile(raw,plan['replacementPath'],'exec'),self.reader.__dict__) # Execute exactly verified bytes, no reopen/pycache.
  self.bmc=self.reader.BMC(self.reader.BMC_FILE);self.node=self.reader.Node(self.reader.NODE_FILE);self.logged=False
 def command(self,args):
  result=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=5,check=False);need(result.returncode==0 and not result.stderr,'bounded_system_command_failed');return result.stdout.decode('utf8')
 def physical(self):
  raw=self.command(['/usr/bin/systemctl','show',UNIT,'--property='+','.join(PROPS)]);u=parse_unit(raw);boot=Path('/proc/sys/kernel/random/boot_id').read_text();cg=u['ControlGroup'];need(cg in ('','/system.slice/'+UNIT),'foreign_fan_cgroup')
  try:procs=Path('/sys/fs/cgroup'+cg+'/cgroup.procs').read_text() if cg else None
  except FileNotFoundError:procs=None
  pid=int(u['MainPID']);process=None
  if pid:
   statraw=Path('/proc/'+str(pid)+'/stat').read_text();fields=statraw[statraw.rfind(')')+2:].split();status=Path('/proc/'+str(pid)+'/status').read_text();cmdline=Path('/proc/'+str(pid)+'/cmdline').read_bytes();exe=os.readlink('/proc/'+str(pid)+'/exe')
   process={'pid':pid,'startTicks':fields[19],'procStatUtf8':statraw,'procStatusUtf8':status,'cmdlineBase64':base64.b64encode(cmdline).decode(),'exe':exe,'bootId':boot.strip()}
  return {'unitUtf8':raw,'bootIdUtf8':boot,'cgroupProcsUtf8':procs,'process':process}
 def readings(self):
  if not self.logged:self.bmc.login();self.logged=True
  return {'snapshot':self.bmc.snapshot(),'tach':self.bmc.tach(),'node':self.node.read(),'readerSourceSha256':NEW}
 def start(self):return self.command(['/usr/bin/systemctl','start','--no-block',UNIT])
 def stop(self):return self.command(['/usr/bin/systemctl','stop','--no-block',UNIT])
 def close(self):self.bmc.logout()
def measured_readings(readings,reader,plan,now):
 need(readings['readerSourceSha256']==NEW,'independent_reader_source_changed');s=readings['snapshot'];duty=reader.shape(s);inv=reader.digest(reader.invariant(s));others=reader.digest(reader.non_target(s))
 need(inv==plan['invariantSha256'] and others==plan['nonTargetSha256'],'BMC_invariant_or_other_zone_changed')
 tach=readings['tach'];node=readings['node'];need(tach['name']=='CHA_FAN3' and isinstance(tach['value'],(int,float)) and math.isfinite(tach['value']) and tach['value']>0,'actual_tach_unavailable')
 for at in [tach['at'],node['sampled_at']]:need(0<=now-stamp(at)<=15,'current_tach_or_GPU_required')
 temp=node['temperature_c'];age=node['telemetry_age_seconds'];need(type(temp) in (int,float) and math.isfinite(temp) and 0<=temp<=120 and type(age) in (int,float) and math.isfinite(age) and 0<=age<=15,'fresh_exact_GPU_measurement_required')
 need(node['node_boot_id']==plan['nodeBootId'],'current_GPU_boot_changed');return {'duty':duty,'invariantSha256':inv,'nonTargetSha256':others,'temperatureC':temp,'tach':tach['value'],'nodeSampledAt':stamp(node['sampled_at'])}
def acquire(plan):
 p=Path(plan['statePath'])/'controller.lock';fd=os.open(p,os.O_RDWR|os.O_NOFOLLOW)
 try:
  fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);held=metadata(os.fstat(fd));named=metadata(p.lstat());need(held==named,'held_lock_inode_changed');check_meta(held,plan['stateFiles']['controller.lock']['metadata']);need(sha(read_original(p)[0])==plan['stateFiles']['controller.lock']['sha256'],'lock_original_changed');return fd
 except BaseException:os.close(fd);raise
def held_original(fd,plan):
 need(metadata(os.fstat(fd))==metadata((Path(plan['statePath'])/'controller.lock').lstat()),'held_lock_replaced');check_meta(metadata(os.fstat(fd)),plan['stateFiles']['controller.lock']['metadata'])
def preflight(plan,backend,window):
 window.check();a=utc();fd=acquire(plan)
 try:
  tree=verify_tree(plan);physical=backend.physical();no_owner(physical,plan);readings=backend.readings();m=measured_readings(readings,backend.reader,plan,window.now());need(m['duty']==100,'safe_initial_100_required');held_original(fd,plan);verify_tree(plan);window.check()
 finally:os.close(fd)
 return {'schema':'h041-fan-preflight-v2','startedUtc':a,'finishedUtc':utc(),'exitCode':0,'producerSourceSha256':sha(Path(__file__).read_bytes()),'readerSourceSha256':NEW,'tree':tree,'physical':physical,'readings':readings,'lockReleasedAfterActualClose':True}
def validate_original_preflight(raw,plan,go,window):
 need(sha(raw)==go['preflightSha256'],'exact_original_preflight_required');p=decode(raw);need(p.get('schema')=='h041-fan-preflight-v2' and p.get('producerSourceSha256')==go['helperSha256'] and p.get('readerSourceSha256')==NEW and p.get('lockReleasedAfterActualClose') is True,'source_bound_actual_preflight_required');window.fresh(p);no_owner(p['physical'],plan);need(p['tree']['source']['sha256']==OLD and p['tree']['unit']['sha256']==UNIT_SHA,'original_preflight_source_unit');return p
class Journal:
 def __init__(self,root):self.root=Path(root);self.index=0
 def put(self,event):self.index+=1;raw=encode(event);name=f'{self.index:04d}-event.json';durable(self.root/name,raw);return {'file':name,'sha256':sha(raw),'bytes':len(raw)}
def admit_directory_mutation(plan,phase,name,inputs):
 before=phase.get(name,plan['metadata'][name]);after=metadata(Path(plan[name+'Path']).lstat());need(all(before[k]==after[k] for k in ('st_dev','st_ino','st_uid','st_gid','st_mode')),'unowned_directory_identity_changed');phase[name]=after

def install(plan,backend,window,journal,fd):
 window.check();held_original(fd,plan);phase={};inputs=verify_tree(plan,phase=phase);no_owner(backend.physical(),plan);need(measured_readings(backend.readings(),backend.reader,plan,window.now())['duty']==100,'exact_initial_curve_100_required');window.check()
 backup=Path(plan['backupPath']);need(not backup.exists(),'new_backup_only');backup.mkdir(mode=0o700);os.chown(backup,0,0);syncdir(backup.parent);admit_directory_mutation(plan,phase,'backupParent',inputs)
 for name,proof in inputs.items():
  m=proof['metadata'];durable(backup/name.replace('/','--'),base64.b64decode(proof['bytesBase64']),stat.S_IMODE(m['st_mode']),(m['st_uid'],m['st_gid']))
 durable(backup/'metadata.json',encode(inputs));journal.put({'event':'whole_original_backup_fsynced','backup':str(backup),'inputs':inputs});held_original(fd,plan);verify_tree(plan,phase=phase);no_owner(backend.physical(),plan);window.check()
 state=Path(plan['statePath']);archive=backup/'original-blocker.archived';source=Path(plan['sourcePath']);temporary=source.with_name('.cha_fan3.h041-'+plan['transactionId']+'.py');archived=False
 try:
  need(measured_readings(backend.readings(),backend.reader,plan,window.now())['duty']==100,'exact_curve_100_before_clear_required');window.check();journal.put({'event':'archive_intent','originalBlockerSha256':plan['stateFiles']['blocked.json']['sha256']});os.rename(state/'blocked.json',archive);archived=True;syncdir(state);syncdir(backup);admit_directory_mutation(plan,phase,'state',inputs)
  need(sha(read_original(archive)[0])==plan['stateFiles']['blocked.json']['sha256'],'archive_changed');verify_tree(plan,archived=True,phase=phase);held_original(fd,plan);window.check()
  m=inputs['source']['metadata'];durable(temporary,base64.b64decode(inputs['replacement']['bytesBase64']),stat.S_IMODE(m['st_mode']),(m['st_uid'],m['st_gid']));created=read_original(temporary)[1];admit_directory_mutation(plan,phase,'sourceParent',inputs);verify_tree(plan,archived=True,phase=phase);held_original(fd,plan);no_owner(backend.physical(),plan);window.check();journal.put({'event':'source_replace_intent','oldSha256':OLD,'newSha256':NEW})
  os.replace(temporary,source);syncdir(source.parent);current=read_original(source)[1];need(all(current[k]==created[k] for k in META if k!='st_ctime_ns'),'installed_inode_not_own_temporary');phase['source']=current;admit_directory_mutation(plan,phase,'sourceParent',inputs);verify_tree(plan,installed=True,archived=True,phase=phase);held_original(fd,plan);no_owner(backend.physical(),plan);window.check();journal.put({'event':'source_installed_full_remaining_CAS','sourceSha256':NEW,'unitSha256':UNIT_SHA,'explicitServiceStarts':0,'postMutationMetadata':phase});return {'inputs':inputs,'phase':phase}
 except BaseException as error:
  disposition='not_archived'
  if archived:
   try:
    held_original(fd,plan);need(not (state/'blocked.json').exists(),'new_blocker_or_writer');no_owner(backend.physical(),plan);verify_tree(plan,installed=sha(read_original(source)[0])==NEW,archived=True,phase=phase);need(sha(read_original(archive)[0])==plan['stateFiles']['blocked.json']['sha256'],'archive_changed');p=inputs['state/blocked.json'];m=p['metadata'];durable(state/'blocked.json',base64.b64decode(p['bytesBase64']),stat.S_IMODE(m['st_mode']),(m['st_uid'],m['st_gid']));disposition='original_blocker_restored_by_no_writer_CAS_source_not_rolled_back'
   except BaseException:disposition='quarantined_partial_no_authority_to_restore'
  journal.put({'event':'installer_failed','reason':str(error) if isinstance(error,Fault) else 'installer_failed_'+type(error).__name__,'disposition':disposition,'explicitServiceStarts':0,'noAtomicRollbackClaim':True});raise
def owned_process(obs,plan):
 u=parse_unit(obs['unitUtf8']);p=obs['process'];need(p and int(u['MainPID'])==p['pid'] and p['pid']>1 and u['ExecMainPID']==str(p['pid']),'current_owned_fan_process_required')
 need(p['bootId']==plan['hostBootId'] and obs['bootIdUtf8'].strip()==plan['hostBootId'] and re.fullmatch(r'[0-9]+',p['startTicks']) is not None,'current_owned_process_birth_required')
 need(base64.b64decode(p['cmdlineBase64'])==b'/usr/bin/python3\0'+SOURCE.encode()+b'\0run\0','fan_cmdline_changed')
 need(re.search(r'^Uid:\s+'+str(plan['stateOwnerUid'])+r'\s+'+str(plan['stateOwnerUid'])+r'\s',p['procStatusUtf8'],re.M) is not None,'fan_process_uid_changed')
 need(obs['cgroupProcsUtf8'] is not None and obs['cgroupProcsUtf8'].split()==[str(p['pid'])],'unexpected_cgroup_writer');need(re.fullmatch(r'[0-9a-f]{32}',u['InvocationID']) is not None,'actual_invocation_required')
 return {'pid':p['pid'],'startTicks':p['startTicks'],'bootId':p['bootId'],'invocationId':u['InvocationID'],'NRestarts':int(u['NRestarts'])}
class Observation:
 """Independent sampled thermal/owner verifier; flags from UI are not evidence."""
 def __init__(self,plan,reader,old_unit):self.plan=plan;self.reader=reader;self.old=old_unit;self.owner=None;self.cool_at=None;self.last_at=None;self.last_puts=None;self.first=True;self.saw_low=False
 def accept(self,physical,readings,state,now):
  u=parse_unit(physical['unitUtf8']);owner=owned_process(physical,self.plan);need(int(u['NRestarts'])==int(self.old['NRestarts']),'automatic_restart_observed')
  need(u['ActiveState'] in ('activating','active') and u['SubState'] in ('start','running'),'fan_not_running')
  if self.owner is None:need(u['InvocationID']!=self.old['InvocationID'],'old_unit_invocation_reused');self.owner=owner
  else:need(owner==self.owner,'owned_process_replaced_or_restart')
  m=measured_readings(readings,self.reader,self.plan,now);s=decode(state['status.json']['raw']);pending=decode(state['pending-write.json']['raw']);baseline=decode(state['baseline.json']['raw'])
  need('blocked.json' not in state and pending.get('state')=='verified','new_latch_or_uncertain_write')
  need(s.get('source_sha256')==NEW and s.get('gpu_uuid')==GPU and s.get('host_boot_id')==owner['bootId'] and s.get('pid')==owner['pid'] and s.get('state')=='healthy' and s.get('errors')==[],'actual_healthy_status_scope_required')
  for key in ['updated_at','readback_at','tach_at','sampled_at']:need(0<=now-stamp(s[key])<=15,'stale_status_or_sample')
  need(s.get('node_boot_id')==self.plan['nodeBootId'] and s.get('invariant_sha256')==self.plan['invariantSha256']==self.reader.digest(baseline),'status_baseline_changed')
  need(s.get('confirmed_expected_duty')==s.get('readback_duty')==m['duty'] and s.get('desired_duty')==m['duty'] and s.get('mode')==4 and s.get('source_bits')==[0,0,0] and s.get('channel')=='Zone4(CHA_FAN3)/PWMNum3','readback_status_disagrees')
  puts=s.get('bmc_put_attempts');need(type(puts) is int and 0<=puts<=1,'unexpected_PUT_count_or_cycling')
  if self.last_puts is not None:need(puts>=self.last_puts,'PUT_counter_regressed')
  self.last_puts=puts
  sampled=stamp(s['sampled_at']);temp=s['temperature_c'];need(type(temp) in (int,float) and math.isfinite(temp) and 0<=temp<=120,'status_temperature_unavailable')
  if self.last_at is not None:need(sampled>=self.last_at and sampled-self.last_at<=15,'cool_sample_gap_or_regression')
  if temp>65 or m['temperatureC']>65:self.cool_at=None
  elif self.cool_at is None:self.cool_at=sampled
  if self.first:need(m['duty']==100,'initial_actual_100_not_observed');self.first=False
  if m['duty']==40:
   need(self.cool_at is not None and sampled-self.cool_at>=30,'cool_dwell_not_independently_observed');self.saw_low=True
  else:need(m['duty']==100,'unexpected_recovery_curve_duty')
  if self.saw_low:need(m['duty']==40 and temp<=65 and m['temperatureC']<=65,'cool_recovery_not_stable')
  self.last_at=sampled;return {'owner':owner,'measurement':m,'statusSampledAt':sampled,'coolObservedSeconds':0 if self.cool_at is None else sampled-self.cool_at,'putAttempts':puts,'sawLow':self.saw_low}
def state_observation(plan):
 p=Path(plan['statePath']);out={}
 for name in ['status.json','pending-write.json','baseline.json','blocked.json']:
  try:raw,m=read_original(p/name,65536)
  except FileNotFoundError:
   need(name=='blocked.json','required_current_state_missing');continue
  need(m['st_uid']==plan['stateOwnerUid'] and m['st_gid']==plan['stateOwnerGid'] and stat.S_IMODE(m['st_mode'])==0o600,'current_state_protection_changed');out[name]={'raw':raw,'metadata':m,'sha256':sha(raw)}
 return out
def state_packet(state):return {k:{'bytesBase64':base64.b64encode(v['raw']).decode(),'bytes':len(v['raw']),'sha256':v['sha256'],'metadata':v['metadata']} for k,v in state.items()}
def cleanup_owned(plan,backend,verifier,journal,window):
 """Stop only the newly observed invocation; a foreign/ambiguous owner denies."""
 window.check(cleanup=True);current=backend.physical();u=parse_unit(current['unitUtf8']);known=verifier.owner;need(known is not None,'cleanup_owner_never_observed')
 if current['process'] is not None:need(owned_process(current,plan)==known,'cleanup_foreign_owner')
 else:need(u['MainPID']=='0' and u['ExecMainPID']==str(known['pid']) and u['InvocationID']==known['invocationId'] and int(u['NRestarts'])==known['NRestarts'],'cleanup_ambiguous_restart_or_foreign_invocation')
 need(sha(read_original(plan['sourcePath'])[0])==NEW and sha(read_original(plan['unitPath'])[0])==UNIT_SHA,'cleanup_source_or_unit_changed')
 journal.put({'event':'owned_stop_intent','owner':known,'currentPhysical':current});window.check(cleanup=True);reply=backend.stop();journal.put({'event':'owned_stop_command_returned','stdoutUtf8':reply});end=time.monotonic()+50
 while time.monotonic()<end:
  window.check(cleanup=True);p=backend.physical();u=parse_unit(p['unitUtf8']);journal.put({'event':'owned_stop_observation','physical':p})
  if u['MainPID']=='0' and p['process'] is None and p['cgroupProcsUtf8'] in (None,'') and u['ActiveState'] in ('inactive','failed') and u['SubState'] not in ('auto-restart','start','running'):
   fd=acquire_after_stop(plan)
   try:need(sha(read_original(plan['unitPath'])[0])==UNIT_SHA,'cleanup_unit_changed')
   finally:os.close(fd)
   return {'released':True,'physical':p,'observedLockAcquiredAndClosed':True}
  time.sleep(.5)
 raise Fault('owned_stop_exit_unconfirmed')
def acquire_after_stop(plan):
 p=Path(plan['statePath'])/'controller.lock';fd=os.open(p,os.O_RDWR|os.O_NOFOLLOW)
 try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);need(metadata(os.fstat(fd))==metadata(p.lstat()),'post_stop_lock_replaced');check_meta(metadata(os.fstat(fd)),plan['stateFiles']['controller.lock']['metadata']);return fd
 except BaseException:os.close(fd);raise
def recover(plan,go,preflight_raw,backend,window):
 original=validate_original_preflight(preflight_raw,plan,go,window);fresh=preflight(plan,backend,window);need(fresh['physical']['bootIdUtf8']==original['physical']['bootIdUtf8'],'preflight_host_changed');old=no_owner(fresh['physical'],plan);journal=Journal(plan['journalPath']);journal.put({'event':'current_independent_preflight','originalSha256':sha(preflight_raw),'observed':fresh})
 fd=acquire(plan);started=False;verifier=Observation(plan,backend.reader,old)
 try:
  installed=install(plan,backend,window,journal,fd);window.check();need(window.now()+140<window.cap,'observation_and_cleanup_reserve_unavailable');verify_tree(plan,installed=True,archived=True,phase=installed['phase']);held_original(fd,plan);no_owner(backend.physical(),plan);need(measured_readings(backend.readings(),backend.reader,plan,window.now())['duty']==100,'exact_curve_100_before_start_required');window.check();os.close(fd);fd=None
  # O_EXCL is the durable spent-start marker. A crash after it is ambiguous;
  # never retry a start or repeat blocker clearing from the same transaction.
  durable(Path(plan['journalPath'])/'start-spent.json',encode({'schema':'fan-start-spent-v1','transactionId':plan['transactionId'],'argv':['/usr/bin/systemctl','start','--no-block',UNIT],'at':utc()}));window.check();started=True
  reply=backend.start();journal.put({'event':'explicit_start_returned','stdoutUtf8':reply,'explicitServiceStarts':1});begin=time.monotonic();last_read=-float('inf');samples=0
  while time.monotonic()-begin<90:
   window.check(cleanup=True);physical=backend.physical();u=parse_unit(physical['unitUtf8']);journal.put({'event':'physical_poll','physical':physical})
   need(int(u['NRestarts'])==int(old['NRestarts']),'automatic_restart_detected')
   if physical['process'] is None:
    need(time.monotonic()-begin<10 and u['ActiveState']=='activating' and u['SubState']=='start','new_start_failed_or_owner_absent');time.sleep(.5);continue
   identity=owned_process(physical,plan)
   if verifier.owner is None:need(u['InvocationID']!=old['InvocationID'],'old_invocation_reused');verifier.owner=identity
   else:need(identity==verifier.owner,'new_fan_owner_replaced')
   need(u['ActiveState'] in ('activating','active') and u['SubState'] in ('start','running'),'owned_unit_failed_or_restart_pending')
   if time.monotonic()-last_read>=5:
    readings=backend.readings();state=state_observation(plan);journal.put({'event':'original_observation','physical':physical,'readings':readings,'state':state_packet(state)});window.check(cleanup=True);check=verifier.accept(physical,readings,state,window.now());journal.put({'event':'independent_observation_verified','verified':check});last_read=time.monotonic();samples+=1
   time.sleep(.5)
  need(samples>=12 and verifier.saw_low,'ninety_second_cool_recovery_not_qualified');journal.put({'event':'observed_recovery_PASS','actualObservationSeconds':time.monotonic()-begin,'samples':samples,'ownedProcess':verifier.owner,'explicitServiceStarts':1,'nativeAcceptance':'NOT_TESTED','noAtomicRollbackClaim':True});return {'fanObservation':'PASS','owner':verifier.owner,'samples':samples,'explicitServiceStarts':1}
 except BaseException as error:
  work_reason=str(error) if isinstance(error,Fault) else 'recovery_'+type(error).__name__;cleanup=None;cleanup_reason=None
  if started:
   try:cleanup=cleanup_owned(plan,backend,verifier,journal,window)
   except BaseException as e:cleanup_reason=str(e) if isinstance(e,Fault) else 'cleanup_'+type(e).__name__
  journal.put({'event':'recovery_FAILED','reason':work_reason,'explicitServiceStarts':1 if started else 0,'cleanup':cleanup,'cleanupFailure':cleanup_reason,'quarantine':cleanup_reason is not None,'noRetry':True})
  if cleanup_reason:raise Fault(work_reason+';cleanup_failed:'+cleanup_reason) from error
  raise
 finally:
  if fd is not None:os.close(fd)
def plan_layout(plan):
 need(plan.get('schema')=='h041-fan-recovery-plan-v2' and plan.get('enabled') is False and plan.get('liveGo') is None,'disabled_root_template_required')
 need(plan['sourcePath']==SOURCE and plan['unitPath']==UNIT_PATH and plan['statePath']==STATE and plan['sourceParentPath']==str(Path(SOURCE).parent) and plan['unitParentPath']==str(Path(UNIT_PATH).parent),'fixed_existing_fan_layout_required')
 need(plan['oldSourceSha256']==OLD and plan['newSourceSha256']==NEW and plan['unitSha256']==UNIT_SHA and plan['gpuUuid']==GPU,'exact_fixed_source_and_thermal_scope')
 need(re.fullmatch(r'[a-z0-9-]{8,80}',plan['transactionId']) is not None,'invalid_transaction')
 private='/run/sova-fan-recovery/'+plan['transactionId'];need(plan['backupParentPath']==private and plan['backupPath']==private+'/originals' and plan['journalPath']==private+'/journal' and plan['replacementPath']==private+'/cha_fan3.reviewed.py','fixed_root_private_layout_required')
 need(type(plan['stateOwnerUid']) is int and plan['stateOwnerUid']>0 and type(plan['stateOwnerGid']) is int and plan['stateOwnerGid']>0,'actual_state_user_identity_required')
 need({'blocked.json','status.json','baseline.json','pending-write.json','controller.lock'}<=set(plan['stateFiles']) and 5<=len(plan['stateFiles'])<=64,'whole_original_state_manifest_required')
 need(plan['observationSeconds']==90 and plan['serviceStarts']==1 and plan['cleanupStopsMaximum']==1 and plan['settlementReserveMs']==120000,'fixed_one_start_observation_budget')
 for name in ['source','unit','replacement']:
  m=plan['metadata'][name];need(m['st_uid']==0 and not m['st_mode']&0o022,'protected_fixed_inputs_required')
 for name in ['sourceParent','unitParent','backupParent']:
  m=plan['metadata'][name];need(m['st_uid']==0 and not m['st_mode']&0o022,'protected_fixed_parent_required')
 need(plan['metadata']['state']['st_uid']==plan['stateOwnerUid'] and stat.S_IMODE(plan['metadata']['state']['st_mode'])==0o700,'protected_state_directory_required')
def main():
 need(sys.platform=='linux' and os.geteuid()==0 and len(sys.argv)==4,'root_worker1_separate_exact_GO_only');mode,config_path,go_path=sys.argv[1:];need(mode in ('preflight','recover'),'fixed_recovery_mode_required')
 for p in [config_path,go_path]:parents_protected(p,{0})
 raw,cm=read_original(config_path);auth,gm=read_original(go_path)
 for m in [cm,gm]:need(m['st_uid']==0 and stat.S_IMODE(m['st_mode'])==0o600,'root_owned_exact_packet_required')
 plan=decode(raw);plan_layout(plan);go=decode(auth);need(go.get('schema')=='h041-root-fan-recovery-GO-v2' and go.get('actor')=='worker1' and go.get('phase')==mode and go.get('planSha256')==sha(raw) and go.get('helperSha256')==sha(Path(__file__).read_bytes()) and go.get('sourceSha256')==NEW and go.get('unitSha256')==UNIT_SHA and go.get('transactionId')==plan['transactionId'] and go.get('serviceStarts')==(1 if mode=='recover' else 0),'exact_phase_source_config_GO_required')
 window=Window(go);window.check();directory(plan['journalPath'],{'st_uid':0,'st_gid':0,'st_mode':stat.S_IFDIR|0o700});directory(plan['backupParentPath'],plan['metadata']['backupParent']);parents_protected(plan['journalPath'],{0});backend=LinuxBackend(plan)
 try:
  if mode=='preflight':result=preflight(plan,backend,window);durable(Path(plan['journalPath'])/'preflight-original.json',encode(result));print(json.dumps({'preflight':'READ_ONLY','receiptSha256':sha(encode(result))}))
  else:
   prior,pm=read_original(plan['journalPath']+'/preflight-original.json');need(pm['st_uid']==0 and stat.S_IMODE(pm['st_mode'])==0o600,'protected_original_preflight_required');result=recover(plan,go,prior,backend,window);durable(Path(plan['journalPath'])/'RESULTS.json',encode(result));print(json.dumps(result))
 finally:backend.close()
if __name__=='__main__':
 try:main()
 except Fault as e:print(json.dumps({'status':'FAILED','reason':str(e),'nativeAcceptance':'NOT_TESTED'}));raise SystemExit(1)
