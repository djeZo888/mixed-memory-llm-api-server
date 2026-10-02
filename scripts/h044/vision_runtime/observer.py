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

#!/usr/bin/env python3
"""Exact selected owned observations; PID/container/name guesses never qualify."""
import json,os,re,subprocess,time
from pathlib import Path
from control import Refused,sha,utc
INSPECT='{"id":{{json .Id}},"image":{{json .Image}},"pid":{{json .State.Pid}},"running":{{json .State.Running}},"exit":{{json .State.ExitCode}},"started":{{json .State.StartedAt}},"finished":{{json .State.FinishedAt}},"owner":{{json (index .Config.Labels "io.h044.vision.owner")}},"nonce":{{json (index .Config.Labels "io.h044.vision.nonce")}},"devices":{{json .HostConfig.DeviceRequests}},"networks":{{json .NetworkSettings.Networks}},"networkMode":{{json .HostConfig.NetworkMode}},"portBindings":{{json .HostConfig.PortBindings}}}'
GPU='GPU-14c23cbc-12f0-9c61-0fda-7aaf80fbd1bf'
def selected(argv,timeout=5):
 import receipt_recorder
 result=receipt_recorder.record(argv,__import__('control').PHASE_ROOT,environment={'PATH':'/usr/bin:/bin','LC_ALL':'C'},timeout=timeout,output_cap=1048576,label='original-selected-observation')
 out=Path(result['stdout']['path']).read_bytes() if result.get('stdout') else b'';err=Path(result['stderr']['path']).read_bytes() if result.get('stderr') else b''
 if result['status']!='COMPLETE' or len(out)>65536 or len(err)>4096:raise Refused('observer_original_receipt_or_output_cap')
 return {'argv':argv,'exitCode':result['actualExitCode'],'observedUtc':utc(),'stdoutSHA256':sha(out),'stderrSHA256':sha(err),'originalReceipt':result['receiptPath'],'originalDirectWait':result['waited'],'originalAbsence':result['absence']},out


def birth(pid):
 raw=Path(f'/proc/{pid}/stat').read_text();tail=raw[raw.rfind(')')+2:].split()
 return {'pid':pid,'startTicks':int(tail[19]),'ppid':int(tail[1]),'pgid':int(tail[2]),'cgroup':Path(f'/proc/{pid}/cgroup').read_text(),'exe':os.readlink(f'/proc/{pid}/exe'),'uid':int(re.search(r'^Uid:\s+(\d+)',Path(f'/proc/{pid}/status').read_text(),re.M).group(1))}

def pid_presence(original):
 # Only /proc/PID/stat (not a missing exe/cgroup) determines original birth absence.
 path=Path('/proc')/str(original['pid'])/'stat'
 try:
  raw=path.read_text();tail=raw[raw.rfind(')')+2:].split();ticks=int(tail[19])
  return {'state':'ORIGINAL_PRESENT' if ticks==original['startTicks'] else 'ORIGINAL_ABSENT_PID_REUSED','currentStartTicks':ticks}
 except FileNotFoundError:
  try:os.stat(path.parent)
  except FileNotFoundError:return {'state':'ORIGINAL_ABSENT_PROC_ROOT'}
  except OSError:return {'state':'UNKNOWN'}
  return {'state':'UNKNOWN_PROC_ROOT_STILL_PRESENT'}
 except (OSError,ValueError,IndexError):return {'state':'UNKNOWN'}

def exact_container(cid):
 if not re.fullmatch('[a-f0-9]{64}',cid):raise Refused('actual_container_id_required')
 r,b=selected(['/usr/bin/docker','container','inspect','--format',INSPECT,cid])
 if r['exitCode']!=0:
  # Successful daemon-wide exact ID inventory independently distinguishes denial from absence.
  listing,raw=selected(['/usr/bin/docker','ps','-a','--no-trunc','--format','{{.ID}}'])
  ids=raw.decode().splitlines()
  if listing['exitCode']==0 and len(ids)<=64 and all(re.fullmatch('[a-f0-9]{64}',x) for x in ids) and cid not in ids:return {'receipt':r,'absenceInventoryReceipt':listing,'state':'ABSENT_PROVEN','id':cid}
  return {'receipt':r,'absenceInventoryReceipt':listing,'state':'UNKNOWN','id':cid}
 v=json.loads(b)
 if v['id']!=cid:raise Refused('container_identity')
 result={'receipt':r,'state':'READBACK','value':v,'birth':None}
 if v['running'] and v['pid']>0:
  try:result['birth']=birth(v['pid'])
  except OSError:result['birthState']='UNKNOWN'
 return result

def snapshot(containers=()):
 r,b=selected(['/usr/bin/nvidia-smi','--query-compute-apps=gpu_uuid,pid,used_memory','--format=csv,noheader,nounits'])
 gp=[list(map(str.strip,x.split(','))) for x in b.decode().splitlines()] if r['exitCode']==0 else None
 gr,gb=selected(['/usr/bin/nvidia-smi','--query-gpu=uuid,memory.total,memory.used,memory.free,temperature.gpu','--format=csv,noheader,nounits'])
 g=[list(map(str.strip,x.split(','))) for x in gb.decode().splitlines()] if gr['exitCode']==0 else None
 sr,sb=selected(['/usr/bin/ss','-H','-ltn','sport = :18191 or sport = :18192 or sport = :18193'])
 return {'bootId':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'gpuProcesses':gp,'gpuProcessReceipt':r,'gpus':g,'gpuReceipt':gr,'ports':sb.decode().splitlines() if sr['exitCode']==0 else None,'socketReceipt':sr,'containers':[exact_container(c) for c in containers]}

def cleanup_proof(before,after,owned,exits,protected_before,protected_after):
 unknown=[]
 if not owned:unknown.append('original_owned_identity_missing')
 if before['bootId']!=after['bootId']:unknown.append('boot_changed')
 if any(after[k] is None for k in ('gpuProcesses','gpus','ports')):unknown.append('selected_observations_unknown')
 if after['ports']:unknown.append('sockets_remain')
 # Exit receipts must come from original wait, not daemon/child absence inference.
 for o in owned:
  x=exits.get(o['id'])
  if not x or type(x.get('exitCode')) is not int or x.get('containerId')!=o['id']:unknown.append('authentic_exit_missing')
  if not o.get('birth'):unknown.append('original_birth_missing')
  elif pid_presence(o['birth'])['state'] not in ('ORIGINAL_ABSENT_PROC_ROOT','ORIGINAL_ABSENT_PID_REUSED'):unknown.append('original_pid_not_proven_absent')
  if o.get('birth'):
   cg=o['birth'].get('cgroup','')
   paths=[x.split(':',2)[-1] for x in cg.splitlines() if x.startswith('0::')]
   if len(paths)!=1 or paths[0]=='/':unknown.append('original_scope_not_exact')
   else:
    scope=Path('/sys/fs/cgroup')/paths[0].lstrip('/')
    try:
     processes=(scope/'cgroup.procs').read_text().splitlines()
     if processes:unknown.append('original_cgroup_processes_remain')
    except FileNotFoundError:
     try:os.stat(scope)
     except FileNotFoundError:pass
     except OSError:unknown.append('original_scope_absence_unknown')
     else:unknown.append('original_scope_still_present_without_procs')
    except OSError:unknown.append('original_scope_absence_unknown')
  q=next((q for q in after['containers'] if q.get('value',{}).get('id',q.get('id'))==o['id']),None)
  # Absence must be an explicit reviewed not-found result; permission failures UNKNOWN.
  if q is None or q.get('state')!='ABSENT_PROVEN':unknown.append('exact_container_absence_unknown')
 owned_pids={str(x['birth']['pid']) for x in owned if x.get('birth')}
 if after['gpuProcesses'] and any(x[1] in owned_pids for x in after['gpuProcesses']):unknown.append('owned_gpu_process_present')
 original=sorted(x for x in (before['gpuProcesses'] or []) if x[1] not in owned_pids)
 final=sorted(x for x in (after['gpuProcesses'] or []) if x[1] not in owned_pids)
 if original!=final:unknown.append('unrelated_gpu_control_changed')
 if protected_before!=protected_after:unknown.append('unrelated_protected_control_changed')
 return {'state':'QUARANTINE' if unknown else 'OWNED_CLEANUP_PROVEN','failures':unknown,'admission':'CLOSED','authenticSettlement':not unknown}
def group_absent(pgid):
 # Original process-group scope only; no name matching, signalling or daemon inference.
 try:
  for p in Path('/proc').iterdir():
   if not p.name.isdigit():continue
   try:
    raw=(p/'stat').read_text();tail=raw[raw.rfind(')')+2:].split()
    if int(tail[2])==pgid:return False
   except FileNotFoundError:continue
   except (OSError,ValueError,IndexError):return False
  return True
 except OSError:return False


def protected_instances(graph,snapshot):
 expected=__import__('control').protected_roster(graph)
 result=[]
 for owner in expected:
  q=exact_container(owner['id'])
  if not q.get('birth') or q['birth']!=owner.get('birth') or q.get('value',{}).get('image')!=owner.get('image') or q.get('value',{}).get('devices')!=owner.get('devices') or not q.get('value',{}).get('running'):raise Refused('protected_instance_identity_changed')
  result.append(owner)
 return result


def residency_sample(graph,owners):
 s=snapshot([o['id'] for o in owners]);protected=protected_instances(graph,s)
 # Reuse the same current exact-container reads; one bounded network inspect
 # binds normal as well as finite operation to the original owned bridge.
 if len(owners)!=2 or len({o.get('nonce') for o in owners})!=1:raise Refused('network_original_owners_required')
 containers={}
 for o in owners:
  v=next((q.get('value',{}) for q in s['containers'] if q.get('value',{}).get('id')==o['id']),{})
  containers[o['role']]={'Id':v.get('id'),'State':{'Running':v.get('running')},'Config':{'Labels':{'io.h044.vision.owner':v.get('owner'),'io.h044.vision.nonce':v.get('nonce')}},'HostConfig':{'NetworkMode':v.get('networkMode'),'PortBindings':v.get('portBindings')},'NetworkSettings':{'Networks':v.get('networks',{})}}
 network=__import__('control').verify_current_network(graph,owners[0]['nonce'],containers=containers)
 if s['gpuProcesses'] is None or s['gpus'] is None:raise Refused('gpu_telemetry_unknown')
 for o in owners:
  q=next(x for x in s['containers'] if x.get('value',{}).get('id')==o['id'])
  if q.get('birth')!=o['birth'] or not q['value']['running'] or q['value']['devices']!=o['devices']:raise Refused('both_BF16_residence_changed')
  joined=[]
  for x in s['gpuProcesses']:
   if x[0]!=GPU:continue
   b=birth(int(x[1]))
   if b['cgroup']==o['birth']['cgroup']:joined.append({'gpuProcess':x,'birth':b})
  if not joined:raise Refused('model_GPU_residency_missing_exact_cgroup_join')
  q['ownedGpuProcessBirths']=joined
 g=next((x for x in s['gpus'] if x[0]==GPU),None)
 if g is None or float(g[3])/float(g[1])<.07:raise Refused('peak_free_below_seven_percent')
 roster=__import__('control').enabled_roster(graph)
 result={'snapshot':s,'network':network,'minimumFreeFraction':float(g[3])/float(g[1]),'bothResident':True,'qualification':'LIVE_RECEIPTS_ONLY_NOT_SOURCE_FIXTURE'}
 result['protectedInstances' if roster else 'otherFourInstances']=protected
 if roster:
  if sorted(o['role'] for o in owners)!=sorted(roster['vision']):raise Refused('enabled_vision_roles')
  result.update(enabledServices=roster,instanceCount=len(protected)+len(owners),visionInstances=[{k:o[k] for k in ('role','id','birth','image','devices')} for o in sorted(owners,key=lambda x:x['role'])])
 return result
if __name__=='__main__':raise SystemExit('DISABLED: only source-bound exact executor may call observer after current root GO')
