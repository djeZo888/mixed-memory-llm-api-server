#!/usr/bin/env python3
"""Exact H014 Pro acquisition/build jobs. No model load; no generic dispatcher."""
import argparse, contextlib, datetime, hashlib, json, os, pathlib, re, signal, subprocess, sys, time
P=pathlib.Path
ROOT='/usr/local/lib/llm-server/control-api'
RUN='/data/build/h014-pro-7ac59a6-20260927'
LOG='/data/logs/h014-pro-prep-20260927'
MODEL='/data/models-large/mimo-v2.6-pro-rl-ba4eabb7'
REV='ba4eabb78b6c51ffd873ec73b9e12b0f64aced5d'
PIN='7ac59a6e3ad851cd41af00f678effab0598ba9a8'
IMAGE='local/llama-cpp:h014-mimo-7ac59a6-cu132-sm120'
SESSION='01a0e1b3-7ec8-7762-b133-555f2a792c11'
BOOT='6535a867-8e27-49d9-8a04-4ecc1adb1e32'
GUARDS={'scripts/common/registered-storage.py':'21cf082a841aeab9470bd6704b77104961b9d4afcaec696d90aa22b65f5b6f3d','scripts/install/storage.py':'4f834e92d149ea1955e79d34c53c18bf8c5846a4121d779e135a50d31a615505','scripts/install/storage_io.py':'5ba1b1356519bbb4922b563662a605459862a84b81ce4f521dfbce293d97302a','scripts/common/lifecycle_lease.py':'483ba038c62a8b4633449cef9c0f9a6664c00276662498abc748b58c8be644e0'}
now=lambda:datetime.datetime.now(datetime.timezone.utc).isoformat()
def require(v,code):
 if not v:raise RuntimeError(code)
def output(cmd,timeout=30):return subprocess.check_output(cmd,text=True,stderr=subprocess.PIPE,timeout=timeout)
def setup():
 for n,h in GUARDS.items():require(hashlib.sha256(P(ROOT,n).read_bytes()).hexdigest()==h,'installed_guard_mismatch')
 sys.path.insert(0,ROOT+'/scripts')
 global Storage,MountedStorageGuard,AnchoredRoot,acquire_lease,LeaseBusy,s
 from install.storage import Storage
 from install.storage_io import MountedStorageGuard,AnchoredRoot
 from common.lifecycle_lease import acquire_lease,LeaseBusy
 class Runner:
  def run(self,argv,*,timeout=30,env=None):return subprocess.check_output(argv,timeout=timeout,text=True,env=env)
 r=Storage({},Runner()).read_registration()
 require(r['data']['uuid']=='8daf56f1-5649-4163-9d87-919c2d271875' and r['models']['uuid']=='a6d4ab58-84e1-4e48-9a67-13ad1c6f6e0a','registry_identity')
 s=Storage({'data_dir':r['data']['path'],'data_uuid':r['data']['uuid'],'model_dir':r['models']['path'],'model_uuid':r['models']['uuid'],'storage_mode':r['storage_mode']},Runner())
 return r
@contextlib.contextmanager
def transaction(wait_seconds=30):
 # Short canonical transactions only; never retain a lease across transfer/build.
 end=time.monotonic()+wait_seconds
 while True:
  try:c=acquire_lease(blocking=False);lease=c.__enter__();break
  except LeaseBusy:
   if time.monotonic()>end:raise
   time.sleep(.25)
 try:
  with MountedStorageGuard(s) as g:
   s.root_payload_guard();yield g;s.root_payload_guard()
 finally:c.__exit__(None,None,None)
def put(name,value):
 try:
  with transaction(wait_seconds=0) as g:
   with AnchoredRoot(LOG,g) as a:a.atomic_json(name,value)
  return True
 except LeaseBusy:
  return False
def gate():
 require(P('/proc/sys/kernel/random/boot_id').read_text().strip()==BOOT,'boot_changed')
 base=P('/data/logs/flash-h008-20260926');e={}
 for prefix in ['H013-WARM02','H013-FOURWAY01']:
  j=json.loads((base/(prefix+'.json')).read_text());o=json.loads((base/(prefix+'-OWNER.json')).read_text())
  require(o['review_package_sha256']=='ff31aca7a201b29226a844c0047545f8fe79aa240b7ad915802dcf59c1bcebee' and o['boot']==BOOT,'h013_owner_identity')
  require(j.get('end_utc') and j.get('client_threads_settled') is True,'h013_still_running')
  n=j.get('native_settlement')
  if j['status']=='COMPLETE':require(n=='TERMINAL_RESPONSE_CAPTURED' or isinstance(n,dict) and all(x in ['TERMINAL_RESPONSES_CAPTURED','NO_REQUEST_SUBMITTED'] for x in n.values()),'h013_terminal_unproven')
  else:
   q=json.loads((base/(prefix+'-SETTLEMENT.json')).read_text());require(q['status']=='SETTLED' and q['owner']==prefix and q['end_utc'],'h013_settlement_unproven')
   require(all(x.get('empty_cgroup') and x.get('pid_zero_or_absent') and x['status']=='SETTLED' for x in q['lanes'].values()),'h013_owned_native_unsettled')
  for unit in [prefix.lower(),prefix.lower()+'-settle']:
   props=dict(x.split('=',1) for x in output(['systemctl','show',unit,'-p','ActiveState,MainPID']).splitlines());require(props['MainPID']=='0' and props['ActiveState'] in ['inactive','failed'],'h013_unit_running')
  e[prefix]={k:j.get(k) for k in ['status','end_utc','cancel_reason','native_settlement']}
 require(output(['systemctl','is-active','local-ai-fan-boost']).strip()=='active','fan_inactive')
 return e

def manifest():
 j=json.loads(P(RUN,'SELECTED-ARTIFACT.json').read_text());f=j['files']
 require(j['repo']=='AesSedai/MiMo-V2.6-Pro-RL-GGUF' and j['revision']==REV and j['total_bytes']==577669438240,'artifact_identity')
 require([x['rfilename'] for x in f]==[f'MXFP4/MiMo-V2.6-Pro-RL-MXFP4-{i:05}-of-00013.gguf' for i in range(1,14)],'artifact_files')
 require(sum(x['size'] for x in f)==577669438240 and all(re.fullmatch('[0-9a-f]{64}',x['lfs']['sha256']) and x['lfs']['size']==x['size'] for x in f),'artifact_size_hash')
 return j

def run_job(kind):
 setup();gating=gate();m=manifest();start=time.time();deadline=start+5400
 state={'kind':kind,'status':'STARTED','started_utc':now(),'deadline_utc':datetime.datetime.fromtimestamp(deadline,datetime.timezone.utc).isoformat(),'pid':os.getpid(),'ppid':os.getppid(),'session':SESSION,'runtime_pin':PIN,'model_revision':REV,'source_sha256':hashlib.sha256(P(__file__).read_bytes()).hexdigest(),'h013_gate':gating,'model_loaded':False}
 children=[]
 def stop(_sig,_frame):raise TimeoutError('bounded_job_terminated')
 signal.signal(signal.SIGTERM,stop)
 def save():state['updated_utc']=now();put(kind+'-STATUS.json',state)
 def monitor(proc,guards):
  children.append(proc)
  try:
   while proc.poll() is None:
    require(time.time()<deadline,'first_phase_deadline')
    for a in guards:a.check()
    time.sleep(2)
   require(proc.returncode==0,'child_exit_'+str(proc.returncode))
  finally:
   if proc.poll() is None:
    proc.terminate()
    try:proc.wait(timeout=10)
    except subprocess.TimeoutExpired:proc.kill();proc.wait()
   children.remove(proc)
 save()
 try:
  with MountedStorageGuard(s) as g,AnchoredRoot(RUN,g) as a,AnchoredRoot(LOG,g) as log,AnchoredRoot(MODEL,g) as model:
   for path in [RUN,LOG,MODEL,'/data/docker','/data/containerd']:g.check_path(path)
   require(output(['docker','info','--format','{{.DockerRootDir}}']).strip()=='/data/docker','docker_root')
   require('root = "/data/containerd/root"' in P('/etc/containerd/config.toml').read_text(),'containerd_root')
   require(os.statvfs(RUN).f_bavail*os.statvfs(RUN).f_frsize>100*1024**3,'build_space')
   if kind=='download':
    have=0
    for f in m['files']:
     for suffix in ['', '.partial']:
      st=model.stat(f['rfilename']+suffix,missing_ok=True)
      if st:have+=st.st_size
    require(os.statvfs(MODEL).f_bavail*os.statvfs(MODEL).f_frsize>m['total_bytes']-have+20*1024**3,'model_space')
    state['files']={};save()
    # Four independent exact-file curl processes, each retaining offsets on disk.
    pending=list(m['files']);active=[]
    while pending or active:
     require(time.time()<deadline,'first_phase_deadline')
     while pending and len(active)<4:
      f=pending.pop(0);name=f['rfilename'];row={'size':f['size'],'sha256':f['lfs']['sha256']};state['files'][name]=row
      st=model.stat(name,missing_ok=True)
      if st:require(st.st_size==f['size'],'final_file_size');part=name
      else:part=name+'.partial'
      with transaction() as _g:
       with model.open(part,os.O_WRONLY|os.O_CREAT) as fd:require(fd.stat().st_size<=f['size'],'partial_too_large')
      if st:proc=None
      else:
       err=log.open('curl-'+str(len(state['files']))+'.log',os.O_WRONLY|os.O_CREAT|os.O_APPEND)
       url='https://huggingface.co/'+m['repo']+'/resolve/'+REV+'/'+name
       proc=subprocess.Popen(['curl','--fail','--location','--silent','--show-error','--proto','=https','--connect-timeout','20','--max-time',str(max(1,int(deadline-time.time()))),'--continue-at','-','--output',model.proc_path(part),url],stdout=subprocess.DEVNULL,stderr=err.fileno())
       children.append(proc);row.update(status='DOWNLOADING',pid=proc.pid)
      active.append((f,part,proc,err if proc else None))
     for item in list(active):
      f,part,proc,err=item;row=state['files'][f['rfilename']];model.check(part);row['bytes_present']=model.stat(part).st_size
      require(row['bytes_present']<=f['size'],'transfer_overrun')
      if proc and proc.poll() is None:continue
      if proc:
       err.close();children.remove(proc);require(proc.returncode==0,'curl_exit_'+str(proc.returncode))
      require(row['bytes_present']==f['size'],'download_size')
      row['status']='HASHING';save()
      with log.open('hash-'+str(m['files'].index(f))+'.txt',os.O_WRONLY|os.O_CREAT|os.O_TRUNC) as h:
       q=subprocess.Popen(['sha256sum',model.proc_path(part)],stdout=h.fileno(),stderr=subprocess.DEVNULL);monitor(q,[model,log])
      actual=P(LOG,'hash-'+str(m['files'].index(f))+'.txt').read_text().split()[0];require(actual==f['lfs']['sha256'],'published_hash_mismatch')
      if part!=f['rfilename']:
       with transaction() as _g:model.replace(part,f['rfilename'])
      row.update(status='VERIFIED',sha256_verified=True);active.remove(item)
     state['bytes_present']=sum(x.get('bytes_present',0) for x in state['files'].values());state['verified_shards']=sum(x.get('sha256_verified',False) for x in state['files'].values());save();time.sleep(5)
    state['status']='VERIFIED_COMPLETE'
   else:
    # New isolated shallow checkout; no mutation or trust exception for D1.
    state['phase']='FETCH_PINNED_SOURCE';save()
    with log.open('build.log',os.O_WRONLY|os.O_CREAT|os.O_APPEND) as logfile:
     if not P(RUN,'source/.git').exists():
      monitor(subprocess.Popen(['git','init',a.proc_path('source')],stdout=logfile.fileno(),stderr=subprocess.STDOUT),[a,log])
     source=a.proc_path('source')
     monitor(subprocess.Popen(['git','-C',source,'fetch','--depth=1','https://github.com/ggml-org/llama.cpp.git',PIN],stdout=logfile.fileno(),stderr=subprocess.STDOUT),[a,log])
     monitor(subprocess.Popen(['git','-C',source,'checkout','--detach',PIN],stdout=logfile.fileno(),stderr=subprocess.STDOUT),[a,log])
     require(output(['git','-C',source,'rev-parse','HEAD']).strip()==PIN and not output(['git','-C',source,'status','--porcelain']).strip(),'source_pin_dirty')
     state['phase']='BUILDING_SM120';state['image_tag']=IMAGE;save()
     env=dict(os.environ,TMPDIR=RUN+'/tmp',DOCKER_CONFIG=RUN+'/docker-client',XDG_CACHE_HOME=RUN+'/tmp/xdg',DOCKER_BUILDKIT='1')
     cmd=['docker','build','--progress=plain','--platform','linux/amd64','--build-arg','LLAMA_COMMIT='+PIN,'--build-arg','CUDA_ARCHITECTURES=120a-real','--build-arg','BUILD_JOBS=8','--iidfile',a.proc_path('image.iid'),'-t',IMAGE,'-f',a.proc_path('Dockerfile'),source]
     q=subprocess.Popen(cmd,stdout=logfile.fileno(),stderr=subprocess.STDOUT,env=env);state['child_pid']=q.pid;save();monitor(q,[a,log])
     iid=P(RUN,'image.iid').read_text().strip();state['image_id']=iid
     state['image_identity']=json.loads(output(['docker','image','inspect',iid,'--format','{{json .}}']))
     # No GPU access/model mount/listener. CLI parsing alone is not live qualification.
     state['phase']='CLI_IDENTITY_ONLY';save()
     for option in ['version','help']:
      with log.open('llama-'+option+'.txt',os.O_WRONLY|os.O_CREAT|os.O_EXCL) as f:
       q=subprocess.Popen(['docker','run','--rm','--network','none','--read-only','--log-driver','none','--cap-drop','ALL','--security-opt','no-new-privileges',iid,'--'+option],stdout=f.fileno(),stderr=subprocess.STDOUT);monitor(q,[a,log])
     require('7ac59a6' in P(LOG,'llama-version.txt').read_text(),'version_mismatch')
     state['status']='BUILT_CLI_ONLY_NOT_LOADED'
  s.root_payload_guard();state['exit_code']=0
 except BaseException as exc:
  state.update(status='STOPPED_PARTIAL_PRESERVED',error_type=type(exc).__name__,error=str(exc) if isinstance(exc,RuntimeError) else type(exc).__name__,exit_code=1)
  for child in children:
   if child.poll() is None:child.terminate()
  for child in children:
   try:child.wait(timeout=10)
   except subprocess.TimeoutExpired:child.kill();child.wait()
 finally:
  state['finished_utc']=now()
  until=time.monotonic()+900
  while not put(kind+'-STATUS.json',state):
   if time.monotonic()>until:break
   time.sleep(2)
 return state['exit_code']
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('kind',choices=['download','build']);args=p.parse_args();sys.exit(run_job(args.kind))
