"""Guarded one-shot supervisor. No production service installation or promotion."""
import datetime,signal,sys
sys.path.insert(0,'/data/services/image21-reference-20260923/source')
from remote_common import *
NAME='llm-image21-reference-20260923'
IMAGE=json.loads((BASE/'build-result.json').read_text())['image_id']
GPU=m.GPU_UUID
cid=None;sampler=None;summary={'session_id':SESSION,'utc':m.now(),'status':'preflight','inference_attempt_limit':1,'request_bound_seconds':900}
def interrupted(signum,frame):raise RuntimeError('trial_supervisor_interrupted')
signal.signal(signal.SIGTERM,interrupted);signal.signal(signal.SIGINT,interrupted)
def owned():
 v=json.loads(m.run(['docker','inspect',cid]).stdout)[0];h=v['HostConfig'];labels=v['Config']['Labels']
 assert v['Id']==cid and v['Name']=='/'+NAME and v['Image']==IMAGE
 assert labels['io.llm-reference.owner']==TASK and labels['io.llm-reference.session']==SESSION
 assert h['DeviceRequests'][0]['DeviceIDs']==[GPU] and h['CpusetCpus']=='8-15'
 assert h['Memory']==h['MemorySwap']==96*1024**3 and h['NetworkMode']=='none'
 assert v['Config']['User']=='1000:1001'
 return v
r.guards()
assert datetime.datetime.now(datetime.timezone.utc)<datetime.datetime.fromisoformat('2026-09-23T03:55:56.581908+00:00')
with m.acquire_lease(blocking=False):
 before=qwens();sg=r.state();summary['before_qwens']=before;summary['before_sglang']=r.verify_resident(sg)
 assert m.run(['systemctl','show','llm-image-api.service','-p','LoadState','--value']).stdout.strip()=='not-found'
 assert m.run(['docker','inspect',NAME],check=False).returncode!=0
 with anchor(BASE) as a:
  assert not (BASE/'trial.json').exists(),'single trial already recorded'
  a.atomic_json('trial.json',summary)
# Fixed unit's ExecStop independently acquires the same lease; no parent lease here.
m.run(['systemctl','stop',m.UNIT],timeout=125)
with m.acquire_lease(blocking=False):
 r.guards();r.require_ada_idle();assert qwens()==before
 with anchor(BASE) as a:
  a.mkdir('work',mode=0o755)
  a.mkdir('work/tmp',mode=0o700);a.mkdir('work/cache',mode=0o700)
  for p in (BASE/'work',BASE/'work/tmp',BASE/'work/cache'):os.chown(p,1000,1001)
  a.check()
  argv=['docker','create','--name',NAME,'--label','io.llm-reference.owner='+TASK,'--label','io.llm-reference.session='+SESSION,'--gpus','device='+GPU,'--network','none','--user','1000:1001','--cpuset-cpus','8-15','--cpuset-mems','0','--memory','96g','--memory-swap','96g','--pids-limit','1024','--shm-size','1g','--restart','no','--log-driver','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges','--mount','type=bind,src='+r.model+',dst=/models,readonly','--mount','type=bind,src='+str(BASE/'source')+',dst=/reference,readonly','--mount','type=bind,src='+str(BASE/'work')+',dst=/work','--mount','type=bind,src='+str(BASE/'work/tmp')+',dst=/tmp']
  env={'CUDA_VISIBLE_DEVICES':GPU,'NVIDIA_VISIBLE_DEVICES':GPU,'CUDA_DEVICE_ORDER':'PCI_BUS_ID','HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1','HF_HOME':'/work/cache/hf','XDG_CACHE_HOME':'/work/cache','TORCH_HOME':'/work/cache/torch','TMPDIR':'/tmp','PYTHONDONTWRITEBYTECODE':'1','PYTHONUNBUFFERED':'1','TOKENIZERS_PARALLELISM':'false'}
  for k,v in env.items():argv.extend(['--env',k+'='+v])
  argv.extend([IMAGE,'-I','-B','/reference/reference_edit.py'])
  summary['launch_argv']=argv
  try:
   cid=m.run(argv).stdout.strip();assert len(cid)==64
   summary.update(status='created',container_id=cid,image_id=IMAGE);a.atomic_json('trial.json',summary);owned()
   a.mkdir('receipts',mode=0o700)
   m.run(['docker','cp',cid+':/opt/reference-receipts/.',str(BASE/'receipts')],timeout=30)
   with a.open('telemetry.jsonl',os.O_WRONLY|os.O_CREAT|os.O_EXCL) as telemetry:
    sampler=subprocess.Popen(['/usr/bin/python3','-I','-B',str(m.BASE/'source/telemetry.py'),'--output-fd',str(telemetry.fileno()),'--output-path',str(BASE/'telemetry.jsonl'),'--cgroup','/sys/fs/cgroup/system.slice/docker-'+cid+'.scope'],pass_fds=(telemetry.fileno(),),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
     time.sleep(.4);assert sampler.poll() is None
     r.guards();r.require_ada_idle();r.host_headroom()
     assert r.current_device()['free_bytes']>=33131614782+r.current_device()['total_bytes']//20
     with a.open('trial.log',os.O_WRONLY|os.O_CREAT|os.O_EXCL) as log:
      summary.update(status='running',start_monotonic=time.monotonic(),start_utc=m.now());a.atomic_json('trial.json',summary)
      result=subprocess.run(['docker','start','--attach',cid],stdout=log.fileno(),stderr=subprocess.STDOUT,timeout=900)
      log.fsync()
     summary['load_and_edit_container_wall_seconds']=time.monotonic()-summary['start_monotonic']
     v=owned();assert not v['State']['Running']
     summary['container_exit']=v['State'];summary['attach_exit_code']=result.returncode
     summary['status']='FINISHED_VISUAL_REVIEW_PENDING' if result.returncode==0 and v['State']['ExitCode']==0 else 'TRIAL_FAILED'
    finally:
     if cid:
      v=owned()
      if v['State']['Running']:m.run(['docker','kill',cid],timeout=10)
      assert not owned()['State']['Running']
     summary['sampler_exit']=m.settle_sampler(sampler);telemetry.fsync()
   records=[json.loads(x) for x in (BASE/'telemetry.jsonl').read_text().splitlines()]
   hosts=[x['host']['meminfo_bytes']['value']['values'] for x in records if x.get('host',{}).get('meminfo_bytes',{}).get('status')=='ok']
   swaps=[x['host']['cgroup_bytes']['memory.swap.current']['value'] for x in records if x.get('host',{}).get('cgroup_bytes',{}).get('memory.swap.current',{}).get('status')=='ok']
   peaks=[x['host']['cgroup_bytes']['memory.peak']['value'] for x in records if x.get('host',{}).get('cgroup_bytes',{}).get('memory.peak',{}).get('status')=='ok']
   summary['telemetry_summary']=records[-1];summary['host_min_available_bytes']=min(x['MemAvailable'] for x in hosts);summary['host_min_available_fraction']=min(x['MemAvailable']/x['MemTotal'] for x in hosts);summary['host_swap_used_max_bytes']=max(x['SwapTotal']-x['SwapFree'] for x in hosts)
   summary['cgroup_swap_max_bytes']=max(swaps) if swaps else None;summary['cgroup_observed_lifetime_peak_bytes']=max(peaks) if peaks else None
   summary['sampled_margins_pass']=records[-1]['sampled_min_free_bytes']*20>=r.current_device()['total_bytes'] and summary['host_min_available_fraction']>=.15 and swaps and max(swaps)==0
   summary['telemetry_scope']='200ms device totals;1s host/cgroup;between-sample peaks unobserved;initial/final cgroup absent samples retained'
  except BaseException as error:
   summary.update(status='TRIAL_FAILED',error_type=type(error).__name__,error=str(error))
   if cid:
    v=owned()
    if v['State']['Running']:m.run(['docker','kill',cid],timeout=10)
   m.settle_sampler(sampler)
  finally:
   r.require_ada_idle();summary['ada_released']=True
   assert qwens()==before;summary['qwens_unchanged']=True
   summary['finish_utc']=m.now();a.atomic_json('trial.json',summary);r.guards()
print(json.dumps(summary),flush=True)
sys.exit(0 if summary['status']=='FINISHED_VISUAL_REVIEW_PENDING' else 1)
