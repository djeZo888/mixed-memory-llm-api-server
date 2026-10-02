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
"""Exact ID resource journal and complete failure settlement, never name cleanup."""
import json,os,re,time
from pathlib import Path
import control,observer
from executor import run
OWNER='H044-VISION-V03'
NETWORK_INSPECT='{"id":{{json .Id}},"owner":{{json (index .Labels "io.h044.vision.owner")}},"nonce":{{json (index .Labels "io.h044.vision.nonce")}},"containers":{{json .Containers}}}'
def exact_devices(devices):
 return isinstance(devices,list) and len(devices)==1 and devices[0].get('DeviceIDs')==[observer.GPU] and devices[0].get('Count')==0 and devices[0].get('Driver') in ('','nvidia')

def check_enabled(action):return control.current_authority(action)
def docker(argv,deadline,label):
 r=run(['/usr/bin/docker',*argv],deadline,control.PHASE_ROOT,label);raw=(Path(control.PHASE_ROOT)/(label+'.raw')).read_bytes()
 if len(raw)>65536:raise control.Refused('lifecycle_output_cap')
 if r['exitCode']!=0 or r['state']!='EXITED':raise control.Refused('lifecycle_failed_quarantine')
 return r,raw

def record_created(kind,role,argv,nonce,deadline,expected_image=None):
 control.exclusive(Path(control.PHASE_ROOT)/('create-intent-'+nonce+'-'+role+'.json'),{'kind':kind,'role':role,'nonce':nonce,'argvSHA256':control.sha(control.canonical(argv))})
 label=nonce+'-'+role+'-create';r=run(['/usr/bin/docker',*argv],deadline,control.PHASE_ROOT,label);raw=(Path(control.PHASE_ROOT)/(label+'.raw')).read_bytes();cid=raw.decode().strip()
 if not re.fullmatch('[a-f0-9]{64}',cid):raise control.Refused('CREATE_ID_UNKNOWN_QUARANTINE_NO_NAME_CLEANUP')
 value={'id':cid,'role':role,'nonce':nonce,'receipt':r,'bootId':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'createArgvSHA256':control.sha(control.canonical(argv)),'createdIDOrigin':'ORIGINAL_CREATE_OUTPUT','startAttempted':False,'expectedImageId':expected_image}
 control.exclusive(Path(control.PHASE_ROOT)/(kind+'-'+nonce+('-'+role if kind=='container' else '')+'.json'),value)
 if r['exitCode']!=0 or r['state']!='EXITED':raise control.Refused('created_with_failed_receipt_requires_settlement')
 return value

def start_created(created,nonce,deadline,manager=None):
 role=created['role'];cid=created['id'];control.exclusive(Path(control.PHASE_ROOT)/('start-intent-'+nonce+'-'+role+'.json'),{'id':cid,'nonce':nonce,'bootId':created['bootId']})
 if manager is None:docker(['start',cid],deadline,nonce+'-'+role+'-start')
 else:
  manager.launch_attach(created)
  while time.time()<deadline:
   if manager.children['attach-'+role]['p'].poll() is not None:raise control.Refused('ORIGINAL_ATTACH_EXITED_DURING_START')
   q=observer.exact_container(cid)
   if q.get('value',{}).get('running') and q.get('birth'):break
   time.sleep(.05)
  else:raise TimeoutError('original_attach_start_deadline')
 q=observer.exact_container(cid);v=q.get('value',{})
 if v.get('image')!=created['expectedImageId'] or not exact_devices(v.get('devices')):raise control.Refused('EXACT_OCI_GPU_READBACK_MISMATCH')
 if v.get('owner')!=OWNER or v.get('nonce')!=nonce or not v.get('running') or not q.get('birth'):raise control.Refused('START_BIRTH_UNKNOWN_QUARANTINE')
 owned=dict(created,birth=q['birth'],image=v['image'],devices=v['devices'],startedAt=v['started'])
 control.exclusive(Path(control.PHASE_ROOT)/('birth-'+nonce+'-'+role+'.json'),owned);return owned

def load(graph,nonce,deadline,manager=None):
 check_enabled('load')
 if not re.fullmatch('[a-f0-9]{64}',nonce):raise control.Refused('current_nonce')
 network_argv=[v.replace('ROOT_FINITE_NONCE',nonce) for v in graph['runtime']['network']['createArgv']]
 n=record_created('network','network',network_argv,nonce,deadline);owners=[]
 for spec in graph['runtime']['containers']:
  argv=[n['id'] if v=='ACTUAL_NEW_NETWORK_ID' else v.replace('ROOT_FINITE_NONCE',nonce) for v in spec['createArgv']]
  if '--pull=never' not in argv or graph['image'] not in argv or spec['dtype']!='BF16' or spec['gpuUuid']!=observer.GPU:raise control.Refused('exact_BF16_image_gpu')
  created=record_created('container',spec['role'],argv,nonce,deadline,graph['rootOwnerEvidence']['imageId']);owners.append(start_created(created,nonce,deadline) if manager is None else start_created(created,nonce,deadline,manager=manager))
 control.exclusive(Path(control.PHASE_ROOT)/('owned-'+nonce+'.json'),owners);return owners

def settle_container(created,birth,nonce,deadline):
 cid=created['id'];role=created['role'];q=observer.exact_container(cid);v=q.get('value',{})
 if q.get('state')=='ABSENT_PROVEN':raise control.Refused('ORIGINAL_REMOVE_WAIT_RECEIPT_MISSING')
 if v.get('image')!=created['expectedImageId'] or not exact_devices(v.get('devices')):raise control.Refused('UNEXPECTED_IMAGE_GPU_UNTOUCHED')
 if v.get('id')!=cid or v.get('nonce')!=nonce or v.get('owner')!=OWNER or created['bootId']!=Path('/proc/sys/kernel/random/boot_id').read_text().strip():raise control.Refused('OWNER_BOOT_CHANGED_UNTOUCHED')
 never_started=not v.get('running') and v.get('pid')==0 and str(v.get('started','')).startswith('0001-01-01')
 if birth is None:
  if not never_started:raise control.Refused('STARTED_WITHOUT_ORIGINAL_BIRTH_UNTOUCHED')
  # Exact created ID + daemon never-started state has no native producer to wait.
  result={'id':cid,'role':role,'createdNeverStarted':True,'createdReceipt':created['receipt'],'nativeWait':'NOT_APPLICABLE_NO_START','birth':None}
 else:
  if (birth['id'],birth['nonce'])!=(cid,nonce) or v.get('image')!=birth['image'] or v.get('devices')!=birth['devices'] or v.get('started')!=birth['startedAt']:raise control.Refused('EXACT_STARTED_OWNER_CHANGED_UNTOUCHED')
  if v.get('running') and q.get('birth')!=birth['birth']:raise control.Refused('EXACT_BIRTH_CHANGED_UNTOUCHED')
  if v.get('running'):docker(['stop','--time','5',cid],deadline,nonce+'-'+role+'-stop')
  receipt,raw=docker(['wait',cid],deadline,nonce+'-'+role+'-wait');value=raw.decode().strip()
  if not re.fullmatch('[0-9]{1,3}',value):raise control.Refused('ORIGINAL_NATIVE_WAIT_UNKNOWN')
  after=observer.exact_container(cid)
  if after.get('value',{}).get('running') or after.get('value',{}).get('exit')!=int(value):raise control.Refused('WAIT_INSPECT_MISMATCH')
  result={'id':cid,'role':role,'createdNeverStarted':False,'exitCode':int(value),'waitReceipt':receipt,'birth':birth['birth']}
 docker(['rm',cid],deadline,nonce+'-'+role+'-remove')
 absent=observer.exact_container(cid)
 if absent.get('state')!='ABSENT_PROVEN':raise control.Refused('EXACT_CONTAINER_ABSENCE_UNKNOWN')
 result['absence']=absent
 if birth and observer.pid_presence(birth['birth'])['state'] not in ('ORIGINAL_ABSENT_PROC_ROOT','ORIGINAL_ABSENT_PID_REUSED'):raise control.Refused('ORIGINAL_PID_REMAINS_OR_UNKNOWN')
 if birth and not observer.group_absent(birth['birth']['pgid']):raise control.Refused('ORIGINAL_GROUP_REMAINS_OR_UNKNOWN')
 control.exclusive(Path(control.PHASE_ROOT)/('settled-'+nonce+'-'+role+'.json'),result);return result

def stop(graph,nonce,deadline,authorize=None):
 (authorize() if authorize else check_enabled('stop'));results=[];failures=[]
 roles=[s['role'] for s in graph['runtime']['containers']]+['preflight']
 for role in ['network',*roles]:
  intent=Path(control.PHASE_ROOT)/('create-intent-'+nonce+'-'+role+'.json')
  resource=Path(control.PHASE_ROOT)/(('network-'+nonce+'.json') if role=='network' else ('container-'+nonce+'-'+role+'.json'))
  if intent.exists() and not resource.exists():failures.append({'role':role,'failure':'CREATE_OUTPUT_ID_UNKNOWN_NO_NAME_CLEANUP','state':'QUARANTINE'})
 for role in reversed(roles):
  p=Path(control.PHASE_ROOT)/('container-'+nonce+'-'+role+'.json')
  if not p.exists():continue
  try:
   created=json.loads(control.read_private(p,0));bp=Path(control.PHASE_ROOT)/('birth-'+nonce+'-'+role+'.json');birth=json.loads(control.read_private(bp,0)) if bp.exists() else None
   results.append(settle_container(created,birth,nonce,deadline))
  except (ValueError,OSError,TimeoutError) as e:failures.append({'role':role,'failure':str(e),'state':'QUARANTINE_EXACT_OWNER_UNTOUCHED'})
 np=Path(control.PHASE_ROOT)/('network-'+nonce+'.json');network_absence=None
 if np.exists():
  try:
   n=json.loads(control.read_private(np,0));r,raw=docker(['network','inspect','--format',NETWORK_INSPECT,n['id']],deadline,nonce+'-network-inspect');v=json.loads(raw)
   if (v['id'],v['owner'],v['nonce'])!=(n['id'],OWNER,nonce) or v['containers'] or n['bootId']!=Path('/proc/sys/kernel/random/boot_id').read_text().strip():raise control.Refused('EXACT_NETWORK_OWNER_CHANGED_UNTOUCHED')
   docker(['network','rm',n['id']],deadline,nonce+'-network-remove');r,raw=docker(['network','ls','--no-trunc','--format','{{.ID}}'],deadline,nonce+'-network-absence');ids=raw.decode().splitlines()
   if not all(re.fullmatch('[a-f0-9]{64}',x) for x in ids) or n['id'] in ids:raise control.Refused('EXACT_NETWORK_ABSENCE_UNKNOWN')
   network_absence={'id':n['id'],'inventoryReceipt':r,'absent':True}
  except (ValueError,OSError,TimeoutError) as e:failures.append({'role':'network','failure':str(e),'state':'QUARANTINE'})
 snapshot=observer.snapshot([x['id'] for x in results]);owned_pids={str(x['birth']['pid']) for x in results if x['birth']}
 if snapshot['ports'] is None or snapshot['ports']:failures.append({'role':'socket','failure':'OWNED_PORT_ABSENCE_NOT_PROVEN'})
 if snapshot['gpuProcesses'] is None or any(x[1] in owned_pids for x in snapshot['gpuProcesses']):failures.append({'role':'GPU','failure':'OWNED_GPU_ABSENCE_NOT_PROVEN'})
 result={'state':'QUARANTINE' if failures else 'OWNED_RESOURCE_SETTLEMENT_PROVEN','containers':results,'networkAbsence':network_absence,'failures':failures,'after':snapshot,'admission':'CLOSED','serviceWait':'SCHEDULE_ORIGINAL_POPEN_RECEIPTS_REQUIRED'}
 control.exclusive(Path(control.PHASE_ROOT)/('cleanup-'+nonce+'.json'),result);return result


def preflight(graph,nonce,deadline):
 check_enabled('preflight');created=None;result={};failure=None
 argv=['create','--pull=never','--network=none','--label','io.h044.vision.owner='+OWNER,'--label','io.h044.vision.nonce='+nonce,'--read-only','--user=1000:1000','--cap-drop=ALL','--security-opt=no-new-privileges','--memory=4g','--memory-swap=4g','--cpuset-cpus=0-15','--pids-limit=128','--gpus','device='+observer.GPU,'--mount','type=bind,src='+control.SOURCE_ROOT+',dst=/opt/vision,readonly','--entrypoint','/usr/bin/python3',graph['image'],'-I','-B','/opt/vision/scripts/h044/vision_runtime/preflight.py']
 try:
  created=record_created('container','preflight',argv,nonce,deadline,graph['rootOwnerEvidence']['imageId']);birth=start_created(created,nonce,deadline)
  r,raw=docker(['wait',created['id']],deadline,nonce+'-preflight-native-wait')
  if not re.fullmatch('[0-9]{1,3}',raw.decode().strip()):raise control.Refused('PREFLIGHT_NATIVE_WAIT_UNKNOWN')
  result={'containerId':created['id'],'nativeExitCode':int(raw.decode().strip()),'waitReceipt':r,'candidateCompatibility':'ACTUAL_OUTPUT_REVIEW_REQUIRED'}
 except BaseException as e:failure=str(e)
 finally:
  # Uses the separately signed stop deadline, including every post-create exception.
  _,go=check_enabled('stop');import datetime
  cleanup=stop(graph,nonce,datetime.datetime.fromisoformat(go['actionDeadlines']['stop']).timestamp())
 result.update(failure=failure,cleanup=cleanup)
 return result
if __name__=='__main__':raise SystemExit('DISABLED_NO_CURRENT_FINITE_ROOT_CAPABILITY')
