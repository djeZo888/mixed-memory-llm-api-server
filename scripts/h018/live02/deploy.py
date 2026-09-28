#!/usr/bin/env python3
"""H018 LIVE02 exact reviewed deployment; payload globals supplied by local launcher.
Single dispatch. Staging lease is released before normal systemd owner start.
"""
import base64, datetime, hashlib, importlib.util, json, os, stat, time
from pathlib import Path
BASE=Path('/data/build/H018-20260928/live02')
LOG=Path('/data/logs/H018-20260928/live02')
OLD='dd9c10c75214fbbf8f1d5566618ac35bafa17f709ffc12ec3f84003dc9e30786'
NEW='dbb54dd908a5f9d1e833d34f9cf5d72fce27583fea089c35071b46e0b91f4e05'
DIGEST='8636d893e23ef4a6d7b7ff2414d154aa97c74ccba61fd8186aa028304be6826c'
OLD_DIGEST='e5fa5be2a05c037ac8bac892f73c484f7bbf18e510008d1f4c00729ffd2a77fb'
OWNER=Path('/data/services/mimo-h016-20260927/source/owner.py')
CAP=datetime.datetime.fromisoformat('2026-09-28T00:25:00+00:00').timestamp()
def sha(b):return hashlib.sha256(b).hexdigest()
def utc():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def module(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def require(ok,msg):
 if not ok:raise RuntimeError(msg)
def unit(o,n):return dict(x.split('=',1) for x in o.run(['systemctl','show',n,'-p','MainPID,ActiveState,InvocationID,UnitFileState,ControlGroup,Result,ExecMainStatus'],3).splitlines())
def save(o,h,name,value):
 with h.MountedStorageGuard(h.s) as g,h.AnchoredRoot(str(LOG),g) as a:
  h.s.root_payload_guard();a.atomic_json(name,value);h.s.root_payload_guard()
def residents(o):
 rows=[]
 for cid in o.run(['docker','ps','-q','--no-trunc'],3).split():
  c=o.inspect(cid);cg=o.cgpath(c['State']['Pid'])
  rows.append({'id':cid,'name':c['Name'],'image':c['Image'],'pid':c['State']['Pid'],'started':c['State']['StartedAt'],'cgroup':str(cg),'limits':{n:(cg/n).read_text().strip() for n in ('memory.min','memory.low','memory.high','memory.max','memory.swap.max')},'swap_current':(cg/'memory.swap.current').read_text().strip(),'events':(cg/'memory.events').read_text().strip()})
 return rows
def stable(before,after):
 require(len(before)==len(after),'resident_count_changed')
 for x,y in zip(sorted(before,key=lambda r:r['id']),sorted(after,key=lambda r:r['id'])):
  require(all(x[k]==y[k] for k in ('id','name','image','pid','started','cgroup','limits')),'resident_identity_or_limits_changed')
def protected_install(o,path,raw):
 path=Path(path)
 for p in path.parents:
  st=p.lstat();require(stat.S_ISDIR(st.st_mode) and st.st_uid==0 and not st.st_mode&0o022,'protected_parent')
 if path.exists():o.protected(path)
 require(not path.is_symlink(),'symlink_refused')
 tmp=path.with_name(path.name+'.H018-LIVE02.new')
 fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o644)
 with os.fdopen(fd,'wb') as f:f.write(raw)
 os.replace(tmp,path);require(o.protected(path)==raw,'installed_bytes_changed')
def main():
 require(time.time()<CAP,'task_expired')
 require(sha(OWNER.read_bytes())==OLD,'old_owner_changed')
 o=module('live02_old_owner',OWNER);h=o.setup()
 out={'utc':utc(),'status':'PREPARING','source_commit':'637b684438660f2bea65f6c337851ccda70c6b2b','mutations':[],'primary_failure':None,'cleanup_failure':None,'dispatch_attempted':False}
 with o.settlement_lease(h) as lease,h.MountedStorageGuard(h.s) as g:
  h.s.root_payload_guard();o.storage_paths(h,g)
  for root in ('/data/build','/data/logs'):
   with h.AnchoredRoot(root,g) as a:a.mkdir('H018-20260928/live02')
  require(not (LOG/'DEPLOY.json').exists(),'one_deployment_only')
  save(o,h,'DEPLOY.json',out)
  try:
   q=json.loads(QUIET);require(sha(QUIET.encode())=='b89de894fcd4c1ad44e77c74e777a688b92fd7b0c6700cc1ab9643f7a44d9197','quiet_pin')
   require(q['status']=='QUIET_ORIGINAL_APP_PAUSED' and q['app']['MainPID']=='0' and all(q[k]==0 for k in ('activeOwnedRuns','activeFrontierRequests','activeImageJobs','uncertainImageJobs')),'quiet_receipt')
   m=o.read(o.BASE/'manifest.json');st=o.read(o.BASE/'state.json');oldsel=o.selection()
   require(o.digest(m)==OLD_DIGEST,'old_manifest_changed');o.source_preflight(h,m)
   require(oldsel=={'schema_version':1,'generation':8,'selected_frontier':o.GLM},'selection_changed')
   require(st['status']=='SETTLED' and st['request_hold'] is False and st['settlement']=={'pid_released':True,'cgroup_empty':True,'gpu_compute_empty':True},'old_unsettled')
   for n in (o.UNIT,o.GLM_UNIT,'h018-short.service','h018-last950k.service'):
    u=unit(o,n);require(u['MainPID']=='0' and u['ActiveState'] in ('inactive','failed'),'active_owner')
    if n.startswith('h018-'):require(u['UnitFileState']=='static','client_enabled')
   for p,d in CLIENT_PINS.items():require(sha(o.protected(p))==d,'preinstalled_client_changed')
   for p in ('worker1-short/AUTHORITY.json','worker1-last950k/LAST-GO.json'):
    require(not Path('/data/build/H018-20260928',p).exists(),'unexpected_authority')
   before=residents(o);stable(RESIDENTS,before);out['resident_before_reload']=before
   gpu=o.run(['nvidia-smi','--query-gpu=uuid,memory.total,memory.free,temperature.gpu','--format=csv,noheader,nounits'],3)
   for line in gpu.splitlines():
    uid,total,free,temp=[x.strip() for x in line.split(',')];total,free,temp=map(float,(total,free,temp));require(temp<85,'temperature')
    floor=total*.07 if uid==o.GPU else total*.05 if uid=='GPU-5d895991-b794-2b4c-b9c4-5f1b668afd23' else 16384
    require(free>=floor,'gpu_reserve')
   mem=o.memory();require(m['memory']['limit_bytes']<=mem['MemAvailable']-.15*mem['MemTotal'],'host_reserve')
   o.latch(h,o.BOOT.read_text().strip());out['hardware']={'gpus':gpu,'host':{k:mem[k] for k in ('MemTotal','MemAvailable','SwapTotal','SwapFree')}}
   c=o.exact_container(o.inspect(st['native']['container_id']),m,st)
   require(c['Id']=='5b7fc5b24279a290d5ca6b698d7fcf2d4baffd931a018e6c9da70462760a3208' and c['State']['Pid']==0 and not c['State']['Running'],'old_exact_stopped_required')
   require(not Path('/proc',str(st['native']['pid'])).exists() and not Path(st['native_cgroup']).exists() and not Path('/proc',str(st['proxy']['pid'])).exists(),'old_process_remains')
   out['old_settlement']=o.stop_exact(h,m,st,lease=lease)
   require(not o.inspect('llm-frontier-flash')['State']['Running'],'glm_running')
   candidate=json.loads(FILES[str(o.BASE/'manifest.json')]);require(o.digest(candidate)==DIGEST,'candidate_digest')
   require(sha(FILES[str(OWNER)].encode())==NEW,'candidate_owner')
   backup={}
   keep=set(FILES)|{str(o.BASE/x) for x in ('state.json','selection.json','guard.json','proxy-state.json')}|{str(o.GLM_BASE/x) for x in ('config.json','source/owner.py')}|{'/etc/systemd/system/llm-frontier-flash.service'}
   for name in sorted(keep):
    p=Path(name)
    if p.exists():
     raw=o.protected(p);backup[name]={'sha256':sha(raw),'mode':stat.S_IMODE(p.stat().st_mode),'base64':base64.b64encode(raw).decode()}
    else:require(not p.is_symlink(),'backup_symlink');backup[name]={'prior':'ABSENT'}
   with h.AnchoredRoot(str(BASE),g) as a:a.atomic_json('ROLLBACK.json',backup)
   out.update(rollback_path=str(BASE/'ROLLBACK.json'),rollback_sha256=sha((BASE/'ROLLBACK.json').read_bytes()),storage=h.s.read_registration(),lease_inode=[o.LEASE_PATH.stat().st_dev,o.LEASE_PATH.stat().st_ino]);save(o,h,'DEPLOY.json',out)
   o.run(['docker','rm',c['Id']],5);out['mutations'].append({'removed_exact_stopped_container':c['Id']});save(o,h,'DEPLOY.json',out)
   for name,rawtext in FILES.items():
    raw=rawtext.encode()
    if name.startswith('/data/'):
     g.check_path(name)
     with h.AnchoredRoot(str(Path(name).parent),g) as a:
      with a.open(Path(name).name,os.O_WRONLY|os.O_CREAT|os.O_TRUNC) as f:f.write(raw)
    else:protected_install(o,name,raw)
    require(sha(o.protected(name))==sha(raw),'install_hash_mismatch');out['mutations'].append({'path':name,'sha256':sha(raw)});h.s.root_payload_guard()
   new=module('live02_new_owner',OWNER);new.source_preflight(h,candidate)
   o.run(['systemctl','daemon-reload'],10)
   after=residents(o);stable(before,after);out['resident_after_reload']=after
   selected={'schema_version':1,'generation':9,'selected_frontier':o.MODEL,'manifest_sha256':DIGEST}
   o.write(h,'selection.json',selected);new.assert_launch_admission(candidate,selected,st)
   out.update(status='DEPLOYED_PRESTART',selection=selected,manifest_sha256=DIGEST,source_sha256=candidate['source_sha256'],utc=utc());save(o,h,'DEPLOY.json',out)
   lease.validate();h.s.root_payload_guard()
  except BaseException as exc:
   out.update(status='FAILED_NO_RETRY',primary_failure={'class':type(exc).__name__,'reason':str(exc) if type(exc) is RuntimeError else None},utc=utc());save(o,h,'DEPLOY.json',out);raise
 # Critical boundary: parent canonical lease is now closed before child preflight.
 out.update(staging_lease_released_before_dispatch=True,dispatch_attempted=True,dispatch_utc=utc());save(o,h,'DEPLOY.json',out)
 try:
  require(time.time()<CAP,'task_expired_before_start')
  o.run(['systemctl','start',o.UNIT],10)
  # One bounded dispatch verification, not a model-load wait.
  for _ in range(20):
   current=o.read(o.BASE/'state.json')
   if current.get('manifest_sha256')==DIGEST and current.get('native'):break
   if unit(o,o.UNIT)['ActiveState']=='failed':break
   time.sleep(.2)
  u=unit(o,o.UNIT);current=o.read(o.BASE/'state.json')
  receipt={'utc':utc(),'unit':u,'state':current,'manifest_sha256':DIGEST,'selection':o.selection(),'source_sha256':candidate['source_sha256'],'staging_lease_released_before_dispatch':True,'scope':'Dispatch and actual current stage only; no native or Sova qualification.'}
  if current.get('native') and current.get('manifest_sha256')==DIGEST and current.get('status') in ('LOADING','RUNNING'):
   receipt['memory_policy']=new.memory_policy(candidate,current['native']);receipt['guard_sample']=new.sample_guard(candidate,current['baseline'],new.temperature_limit(o.run(['nvidia-smi','--id='+o.GPU,'-q','-x'],2)),current['native'])
  save(o,h,'ROOT-START.json',receipt);print(json.dumps(receipt),flush=True)
  require(current.get('manifest_sha256')==DIGEST and current.get('status') in ('LOADING','RUNNING') and u['ActiveState']=='active','dispatch_not_loading')
  out.update(status='STARTED_INDEPENDENT',actual_stage=current['status'],utc=utc());save(o,h,'DEPLOY.json',out)
 except BaseException as exc:
  out.update(status='DISPATCH_FAILED_NO_RETRY',primary_failure={'class':type(exc).__name__,'reason':str(exc) if type(exc) is RuntimeError else None},utc=utc());save(o,h,'DEPLOY.json',out);raise
if __name__=='__main__':main()
