#!/usr/bin/env python3
"""One root-authorized precreation restart; no staging, reload, or retry."""
import datetime,hashlib,importlib.util,json,os,threading,time
from pathlib import Path
P=Path;BASE=P('/data/services/mimo-h016-20260927');LOG=P('/data/logs/H018-20260928/live04');CAP=1790557200
OWNER_SHA='218c890f1f3d8f7f80998aaf5cf7463c32febf5e454713f40da76a9ed60027d0';DIGEST='952ac402a3f76b31da1e80bdb0b92541b61374737c4850aa8d4a5937fad2fcee'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def utc():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def require(ok,why):
 if not ok:raise RuntimeError(why)
def main():
 require(time.time()<CAP,'hard_cap')
 path=BASE/'source/owner.py';require(sha(path.read_bytes())==OWNER_SHA,'owner_pin')
 s=importlib.util.spec_from_file_location('start02_owner',path);o=importlib.util.module_from_spec(s);s.loader.exec_module(o);h=o.setup()
 def show(name):return dict(x.split('=',1) for x in o.run(['systemctl','show',name,'-p','MainPID,ActiveState,SubState,InvocationID,UnitFileState,Result,ExecMainStatus'],3).splitlines())
 def save(name,value):
  with h.MountedStorageGuard(h.s) as g,h.AnchoredRoot(str(LOG),g) as a:
   h.s.root_payload_guard();a.atomic_json(name,value);h.s.root_payload_guard()
 require(not (LOG/'START02-ATTEMPT.json').exists(),'one_start02_only')
 # Existing helper supplies a finite acquisition bound, with unchanged trust checks.
 with o.settlement_lease(h) as lease,h.MountedStorageGuard(h.s) as g:
  o.storage_paths(h,g);h.s.root_payload_guard();m=o.read(BASE/'manifest.json');previous=o.read(BASE/'state.json');selected=o.selection()
  require(o.digest(m)==DIGEST and selected['generation']==10,'manifest_selection_changed');o.source_preflight(h,m);o.assert_launch_admission(m,selected,previous)
  require(previous['launch_id']=='ddd222dc06b1421fb217cc08d4fd6762','predecessor_changed')
  require(show(o.UNIT)['MainPID']=='0' and show(o.GLM_UNIT)['MainPID']=='0','owner_running')
  require(show('h018-short02.service')['ActiveState']=='inactive' and show('h018-last950k.service')['ActiveState']=='inactive','client_active')
  require(not P('/data/build/H018-20260928/worker1-short02/AUTHORITY.json').exists() and not P('/data/build/H018-20260928/worker1-last950k/LAST-GO.json').exists(),'unexpected_authority')
  require(not o.run(['docker','ps','-aq','--no-trunc','--filter','name=^/'+m['container_name']+'$'],2).strip(),'native_exists')
  require(not P('/proc',str(previous['native']['pid'])).exists() and not P('/proc',str(previous['proxy']['pid'])).exists() and not P(previous['native_cgroup']).exists(),'predecessor_physical_changed')
  require(not o.run(['nvidia-smi','--id='+o.GPU,'--query-compute-apps=pid','--format=csv,noheader,nounits'],2).strip(),'frontier_compute_present')
  for line in o.run(['nvidia-smi','--query-gpu=uuid,memory.total,memory.free,temperature.gpu','--format=csv,noheader,nounits'],3).splitlines():
   uid,total,free,temp=[x.strip() for x in line.split(',')];total,free,temp=map(float,(total,free,temp));require(temp<85,'thermal');floor=total*.07 if uid==o.GPU else total*.05 if uid=='GPU-5d895991-b794-2b4c-b9c4-5f1b668afd23' else 16384;require(free>=floor,'gpu_reserve')
  baseline=o.memory();require(m['memory']['limit_bytes']<=baseline['MemAvailable']-.15*baseline['MemTotal'],'host_reserve')
  with o.bounded(5):
   hardware=o.latch(h,o.BOOT.read_text().strip());policy=o.memory_policy(m)
  from lifecycle import hardware_policy as hp
  require(sha(o.protected(hp.__file__))=='c779739a1776ea919f491a60a34811639e2df934a94ea909053710e4864e7229','shared_policy_changed')
  lease.validate();lock=o.LEASE_PATH.stat();identity=(lock.st_dev,lock.st_ino)
  intent={'utc':utc(),'status':'ONE_START02_INTENT','authority':'ROOT fresh-start GO after precreation lifecycle_busy; no model/request replay','old_invocation':'c9a82e6c31da4c46a72492370245b2cc','selection':selected,'manifest_sha256':DIGEST,'memory_policy':policy,'hardware':hardware,'lease_identity':identity,'source_sha256':m['source_sha256']}
  save('START02-ATTEMPT.json',intent)
 # Confirm this exact acquisition context has closed and left no canonical FD.
 try:lease.validate()
 except Exception as exc:require(str(exc)=='lease_not_active','unexpected_release_error')
 else:raise RuntimeError('parent_lease_still_active')
 def lock_fds(pid):
  result=[]
  try:
   for fd in P('/proc',str(pid),'fd').iterdir():
    try:
     info=fd.stat()
     if (info.st_dev,info.st_ino)==identity:result.append({'fd':fd.name,'target':os.readlink(fd)})
    except FileNotFoundError:pass
  except FileNotFoundError:pass
  return result
 require(not lock_fds(os.getpid()),'parent_canonical_fd_retained')
 samples=[];done=threading.Event()
 def sampler():
  while not done.is_set() and len(samples)<300:
   rows=[]
   for line in P('/proc/locks').read_text().splitlines():
    fields=line.split()
    if len(fields)>5 and fields[5].endswith(':'+str(identity[1])):
     pid=int(fields[4]);rows.append({'line':line,'pid':pid,'comm':P('/proc',str(pid),'comm').read_text().strip() if P('/proc',str(pid),'comm').exists() else None,'lock_fds':lock_fds(pid)})
   if rows:samples.append({'utc':utc(),'holders':rows})
   done.wait(.02)
 thread=threading.Thread(target=sampler,daemon=True);thread.start()
 try:
  require(time.time()<CAP,'hard_cap_before_start');o.run(['systemctl','start',o.UNIT],10)
  for _ in range(25):
   current=o.read(BASE/'state.json');u=show(o.UNIT)
   if current.get('manifest_sha256')==DIGEST and current.get('native'):break
   if u['ActiveState']=='failed':break
   time.sleep(.2)
  current=o.read(BASE/'state.json');u=show(o.UNIT)
 finally:done.set();thread.join(timeout=1)
 new=current.get('manifest_sha256')==DIGEST and current.get('launch_id')!=previous['launch_id']
 out={'utc':utc(),'unit':u,'state':current,'manifest_sha256':DIGEST,'selection':o.selection(),'source_sha256':m['source_sha256'],'staging_lease_released_before_dispatch':True,'parent_no_canonical_fd_before_start':True,'lock_samples':samples,'new_identity':new,'scope':'Fresh systemd start after exact no-native precreation refusal; actual stage only.'}
 if new and current.get('native'):
  out['memory_policy']=o.memory_policy(m,current['native']);out['guard_sample']=o.sample_guard(m,current['baseline'],o.temperature_limit(o.run(['nvidia-smi','--id='+o.GPU,'-q','-x'],2)),current['native'])
 save('ROOT-START-LIVE04-02.json',out);print(json.dumps(out),flush=True)
 require(new and current['status'] in ('LOADING','RUNNING') and u['ActiveState']=='active','start02_failed_no_retry')
if __name__=='__main__':main()
