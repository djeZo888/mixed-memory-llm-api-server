#!/usr/bin/env python3
"""Fixed bounded passive inventory. No service calls, sudo, exec, pull or writes."""
import argparse,datetime,hashlib,json,os,re,selectors,stat,subprocess,sys,time
from pathlib import Path
GPU='GPU-14c23cbc-12f0-9c61-0fda-7aaf80fbd1bf'
IMAGE='vllm/vllm-openai@sha256:5f5e535216848d0c52159c8c13a0af04be5f6fe1a84e79914300610796f76d40'
ROOT='/data/models-large/h039-vision-20261001-c-01a0f4d8'
MODELS=(('qwen3.5-9b-c202236235762e1c871ad0ccb60c8ee5ba337b9a','c202236235762e1c871ad0ccb60c8ee5ba337b9a'),('paddleocr-vl-1.6-c5630abae1d940eafe0697512a0325494b02ab42','c5630abae1d940eafe0697512a0325494b02ab42'))
RECEIPT='/data/logs/h039-vision-20261001-c-01a0f4d8-h040-recovery-01/status.json'
RECEIPT_SHA='fc402ef550e5b2723480823592915556aa88c73ce7e1d9a7572bdd6f28afc75f'
FIELDS=('Id','User','Group','MainPID','ControlPID','InvocationID','ControlGroup','ActiveState','SubState','Result','ExecMainCode','ExecMainStatus','ExecMainStartTimestampMonotonic','FragmentPath')
COMMANDS={
 'gpus':['/usr/bin/nvidia-smi','--query-gpu=uuid,pci.bus_id,index,memory.total,memory.used,memory.free,temperature.gpu','--format=csv,noheader,nounits'],
 'gpu_processes':['/usr/bin/nvidia-smi','--query-compute-apps=gpu_uuid,pid,used_memory','--format=csv,noheader,nounits'],
 'gpu_map':['/usr/bin/nvidia-smi','--query-gpu=uuid,minor_number','--format=csv,noheader,nounits'],
 'ports':['/usr/bin/ss','-H','-ltn','sport = :18191 or sport = :18192 or sport = :18193'],
 'docker_version':['/usr/bin/docker','version','--format','{{json .Server.Version}}'],
 'oci':['/usr/bin/docker','image','inspect','--format','{"id":{{json .Id}},"architecture":{{json .Architecture}},"os":{{json .Os}},"digests":{{json .RepoDigests}}}',IMAGE],
 'containers':['/usr/bin/docker','ps','-a','--no-trunc','--format','{"id":{{json .ID}},"image":{{json .Image}},"state":{{json .State}}}'],
 'image_unit':['/usr/bin/systemctl','show','llm-image-backend.service','--property='+','.join(FIELDS)],
 'text_unit':['/usr/bin/systemctl','show','llm-qwen-backend.service','--property='+','.join(FIELDS)],
 'vision_unit':['/usr/bin/systemctl','show','llm-technical-vision.service','--property='+','.join(FIELDS)],
}
SSH=['/usr/bin/ssh','-T','-o','BatchMode=yes','-o','ConnectTimeout=8','-o','ServerAliveInterval=5','-o','ServerAliveCountMax=1','ai-vm','/usr/bin/python3','-I','-B','-','--remote']
EXTERNAL_GPU='GPU-5d895991-b794-2b4c-b9c4-5f1b668afd23'
IMAGE_PLATFORM='sha256:50a3bfd20fc931f05fc5fc919b0445abbce30d5c7716424d697a7ab6708c08ef'
IMAGE_PARENT='sha256:dafbccb763cff6a6aa3777c7c0a8cc185d838bd4b9f61bec8007f57f2c7233f8'
IMAGE_NATIVE_CONFIG='sha256:3f6178faa74c4a9bcb95ed4304dbee57473efa8913a793e067014af4a98281ad'
IMAGE_ROOT='/data/services/image21-runtime-20260923'
SELECTED_COMMANDS={
 'external_container':['/usr/bin/docker','container','inspect','--format','{"id":{{json .Id}},"image":{{json .Image}},"configImage":{{json .Config.Image}},"pid":{{json .State.Pid}},"running":{{json .State.Running}},"exitCode":{{json .State.ExitCode}},"startedAt":{{json .State.StartedAt}},"finishedAt":{{json .State.FinishedAt}},"owner":{{json (index .Config.Labels "io.llm-image.owner")}},"invocation":{{json (index .Config.Labels "io.llm-image.invocation")}},"gpu":{{json (index .Config.Labels "io.llm-image.gpu")}},"devices":{{json .HostConfig.DeviceRequests}}}','llm-image-backend'],
 'external_image':['/usr/bin/docker','image','inspect','--format','{"id":{{json .Id}},"architecture":{{json .Architecture}},"os":{{json .Os}},"digests":{{json .RepoDigests}}}',IMAGE_PLATFORM],
 'external_pcie':['/usr/bin/nvidia-smi','--id='+EXTERNAL_GPU,'--query-gpu=uuid,pci.bus_id,pcie.link.gen.current,pcie.link.gen.max,pcie.link.width.current,pcie.link.width.max','--format=csv,noheader,nounits'],
 'stable_pcie':['/usr/bin/nvidia-smi','--id='+GPU,'--query-gpu=uuid,pci.bus_id,pcie.link.gen.current,pcie.link.gen.max,pcie.link.width.current,pcie.link.width.max','--format=csv,noheader,nounits'],
 'ecc':['/usr/bin/nvidia-smi','--query-gpu=uuid,ecc.mode.current,ecc.errors.uncorrected.volatile.total,ecc.errors.uncorrected.aggregate.total','--format=csv,noheader,nounits'],
 'xid':['/usr/bin/journalctl','--kernel','--boot','--no-pager','--lines=64','--grep=NVRM: Xid','--output=json','--output-fields=MESSAGE,__MONOTONIC_TIMESTAMP'],
}
SELECTED_FILES=(
 (IMAGE_ROOT+'/config.json',('schema_version','owner','gpu_uuid','image_id','source_commit','checkpoint_revision','checkpoint_receipt_sha256','network_id')),
 (IMAGE_ROOT+'/state.json',('schema_version','owner','phase','boot','boot_id','run_id','updated_utc','failure_code')),
 (IMAGE_ROOT+'/operation.json',('schema_version','owner','boot','action','status','phase','pid','invocation_id','config_sha256')),
 ('/etc/llm-server/image-api.json',('schema_version','runtime_revision','runtime_image_digest','model_id','model_revision')),
 ('/etc/systemd/system/llm-image-backend.service',None),
 ('/etc/systemd/system/llm-image-api.service',None),
 ('/usr/local/libexec/llm-image-backend-recover',None),
 *( (IMAGE_ROOT+'/source/'+f,None) for f in ('native_request.py','native_server.py','service.py','telemetry.py') ),
 *( ('/usr/local/lib/llm-server/image-api/scripts/image_api/'+f,None) for f in ('__init__.py','serve.py','protection.py','protocol.py','uploads.py','backend.py','app.py') ),
 ('/data/services/releases/h037-image-placement-20260930/scripts/image_runtime/source-closure.json',None),
 ('/opt/llmctl/adaptive-idle/image.json',('schema_version','status','runtime_revision','image_id','image_config_digest','overlay_sha256','verifier_sha256')),
)
READ_ONLY_EXECUTION_ENABLED=False

def sha(b):return hashlib.sha256(b).hexdigest()
def utc():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def bounded(argv,input_bytes=None,seconds=5,cap=65536):
 if argv not in list(COMMANDS.values())+list(SELECTED_COMMANDS.values())+[SSH]:raise ValueError('not_fixed')
 r={'argv':argv,'startedUtc':utc(),'exitCode':None,'state':'UNKNOWN'};streams=[bytearray(),bytearray()]
 try:p=subprocess.Popen(argv,stdin=subprocess.PIPE if input_bytes else subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env={'PATH':'/usr/bin:/bin','LC_ALL':'C'},start_new_session=True)
 except OSError as e:r.update(error=type(e).__name__,finishedUtc=utc());return r,b''
 r['observerPid']=p.pid;s=selectors.DefaultSelector();end=time.monotonic()+seconds;reason=None
 for i,f in enumerate((p.stdout,p.stderr)):os.set_blocking(f.fileno(),False);s.register(f,selectors.EVENT_READ,i)
 if input_bytes:os.set_blocking(p.stdin.fileno(),False);s.register(p.stdin,selectors.EVENT_WRITE,2);pending=memoryview(input_bytes)
 try:
  while s.get_map():
   if time.monotonic()>=end:reason='timeout';break
   for k,_ in s.select(.05):
    if k.data==2:
     try:pending=pending[os.write(k.fd,pending[:8192]):]
     except BrokenPipeError:pending=memoryview(b'')
     if not pending:s.unregister(k.fileobj);k.fileobj.close()
    else:
     b=os.read(k.fd,8192)
     if not b:s.unregister(k.fileobj);continue
     budget=cap if k.data==0 else 4096
     room=budget-len(streams[k.data]);streams[k.data]+=b[:room]
     if len(b)>room:reason='output_cap';break
   if reason:break
  if reason:p.kill()
  try:r['exitCode']=p.wait(timeout=1)
  except subprocess.TimeoutExpired:p.kill();r['exitCode']=p.wait(timeout=1);reason='unsettled_observer_timeout'
 finally:
  s.close()
  for f in (p.stdin,p.stdout,p.stderr):
   if f and not f.closed:f.close()
 r.update(finishedUtc=utc(),stdoutSha256=sha(streams[0]),stderrSha256=sha(streams[1]),stdoutBytes=len(streams[0]),stderrBytes=len(streams[1]),state='READBACK' if r['exitCode']==0 and reason is None else 'UNKNOWN')
 if reason:r['error']=reason
 # Never return unvalidated diagnostic bytes, environments or command lines.
 if streams[1]:r['diagnostic']='omitted; original hash retained (possible access denial)'
 return r,bytes(streams[0])
def small_file(path,fields=None,hash_only=False):
 r={'path':path,'state':'UNKNOWN'}
 try:
  fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW);a=os.fstat(fd)
  try:
   if not stat.S_ISREG(a.st_mode) or a.st_size>262144:raise ValueError('bounded_regular_required')
   b=os.read(fd,262145);z=os.fstat(fd)
   if (a.st_ino,a.st_size,a.st_mtime_ns,a.st_ctime_ns)!=(z.st_ino,z.st_size,z.st_mtime_ns,z.st_ctime_ns):raise ValueError('changed')
  finally:os.close(fd)
  r.update(state='READBACK',sha256=sha(b),stat={'dev':a.st_dev,'inode':a.st_ino,'uid':a.st_uid,'mode':oct(a.st_mode&0o777),'bytes':a.st_size,'mtimeNs':a.st_mtime_ns,'ctimeNs':a.st_ctime_ns})
  if fields:
   v=json.loads(b);selected={}
   for k in fields:
    if k not in v:continue
    x=v[k]
    if type(x) in (int,bool):selected[k]=x
    elif isinstance(x,str) and len(x)<=160 and re.fullmatch(r'[A-Za-z0-9_./:+ -]*',x):selected[k]=x
    elif k=='architectures' and isinstance(x,list) and len(x)<=4 and all(isinstance(y,str) and re.fullmatch(r'[A-Za-z0-9_]{1,80}',y) for y in x):selected[k]=x
   r['selected']=selected
  if hash_only:r['content']='NOT_EXPORTED'
 except (OSError,ValueError) as e:r['error']=type(e).__name__
 return r
def proc(pid):
 r={'pid':pid,'state':'UNKNOWN'}
 try:
  raw=Path(f'/proc/{pid}/stat').read_text();tail=raw[raw.rfind(')')+2:].split();cgroup=Path(f'/proc/{pid}/cgroup').read_text()
  r.update(state='READBACK',startTicks=int(tail[19]),ppid=int(tail[1]),pgid=int(tail[2]),exe=os.readlink(f'/proc/{pid}/exe'),cgroup=cgroup)
 except (OSError,ValueError,IndexError) as e:r['error']=type(e).__name__
 return r
def remote():
 out={'schema':'h043-vision-passive-v1','host':'ai-vm','observedUtc':utc(),'liveActions':'NONE','commands':{},'files':[],'processes':[],'runtimeSupport':'UNKNOWN_NO_CONTAINER_EXEC_AUTHORITY'}
 out['bootId']=Path('/proc/sys/kernel/random/boot_id').read_text().strip();out['observerUid']=os.getuid()
 out['hostMemory']={k:v.strip() for k,v in (line.split(':',1) for line in Path('/proc/meminfo').read_text().splitlines()) if k in ('MemTotal','MemAvailable','SwapTotal','SwapFree')}
 for name,argv in COMMANDS.items():
  r,b=bounded(argv);out['commands'][name]=r
  if r['state']=='READBACK':
   try:
    t=b.decode()
    if len(t.splitlines())>64:raise ValueError('row_cap')
    if name in ('oci','docker_version'):v=json.loads(t)
    elif name=='containers':v=[json.loads(x) for x in t.splitlines()]
    elif name.endswith('_unit'):v=dict(x.split('=',1) for x in t.splitlines());assert set(v)<=set(FIELDS)
    elif name=='ports':v=t.splitlines();assert all(len(x.split())==5 and x.split()[3].rsplit(':',1)[-1] in ('18191','18192','18193') for x in v)
    else:
     v=[list(map(str.strip,x.split(','))) for x in t.splitlines()];assert all(re.fullmatch(r'GPU-[0-9a-f-]{36}',x[0]) for x in v)
    r['value']=v;r['originalSelectedOutput']=t
   except (ValueError,AssertionError,UnicodeError):r['state']='UNKNOWN';r['error']='invalid_selected_output'
 # Adopt receipt digest, never rehash weights; absence/access denial is UNKNOWN.
 receipt=small_file(RECEIPT,('state','status','files','weightFiles','totalBytes','completedAt','revision'));receipt['expectedSha256']=RECEIPT_SHA;receipt['adoption']='MATCH' if receipt.get('sha256')==RECEIPT_SHA else 'UNKNOWN';out['files'].append(receipt)
 for folder,rev in MODELS:
  for f,fields in [('config.json',('architectures','model_type','torch_dtype','dtype','hidden_size','num_hidden_layers','num_attention_heads','num_key_value_heads')),('preprocessor_config.json',('image_processor_type','processor_class','max_pixels','min_pixels')),('tokenizer_config.json',('tokenizer_class','model_max_length')),('CHECKPOINT-RECEIPT.json',None)]:
   row=small_file(ROOT+'/'+folder+'/'+f,fields,hash_only=fields is None);row['revisionExpected']=rev;out['files'].append(row)
 for path in ('/data/services/image21-runtime-20260923/config.json','/data/services/image21-runtime-20260923/state.json','/etc/llm-server/image-api.json','/etc/systemd/system/llm-image-backend.service'):
  out['files'].append(small_file(path,hash_only=True))
 gp=out['commands']['gpu_processes'].get('value',[]);ids={int(x[1]) for x in gp if len(x)==3 and x[1].isdigit()}
 for n in ('image_unit','text_unit','vision_unit'):
  v=out['commands'][n].get('value',{});pid=v.get('MainPID','0')
  if pid.isdigit() and int(pid)>0:ids.add(int(pid))
 for pid in sorted(ids)[:16]:out['processes'].append(proc(pid))
 out['ownership']='UNKNOWN_ROOT_LEASE_FREEZE_ADMISSION_HARDWARE_REVIEW_REQUIRED';return out
def selected_inventory(authorized_go=None):
 # Called only by separately root-approved exact helper. No current authority.
 if os.geteuid()!=0 or not isinstance(authorized_go,dict) or authorized_go.get('action')!='selected_privileged_read_only' or authorized_go.get('count')!=1:raise ValueError('DISABLED_NO_FINITE_ROOT_READ_ONLY_GO')
 out=remote();out['selectedCommands']={};out['selectedFiles']=[]
 for name,argv in SELECTED_COMMANDS.items():
  r,b=bounded(argv);out['selectedCommands'][name]=r
  if r['state']=='READBACK':
   try:
    if name in ('external_container','external_image'):v=json.loads(b)
    elif name=='xid':
     v=[]
     for line in b.splitlines():
      row=json.loads(line);m=re.search(r'NVRM: Xid \(PCI:([0-9a-fA-F:.]+)\): ([0-9]+)',row.get('MESSAGE',''))
      if m:v.append({'bdf':m[1],'xid':int(m[2]),'monotonicUs':row.get('__MONOTONIC_TIMESTAMP')})
    else:v=[list(map(str.strip,x.split(','))) for x in b.decode().splitlines()]
    r['selected']=v
   except (ValueError,UnicodeError):r['state']='UNKNOWN';r['error']='invalid_projection'
 for path,fields in SELECTED_FILES:out['selectedFiles'].append(small_file(path,fields,hash_only=fields is None))
 # Original exact resource ownership projection; no arbitrary container alias supplied.
 state_path=IMAGE_ROOT+'/state.json'
 try:
  fd=os.open(state_path,os.O_RDONLY|os.O_NOFOLLOW)
  try:original=json.loads(os.read(fd,65537))
  finally:os.close(fd)
  container=original.get('container')
  if isinstance(container,dict) and re.fullmatch('[a-f0-9]{64}',container.get('id','')):out['stateContainer']={'id':container['id']}
  else:out['stateContainer']='UNKNOWN'
 except (OSError,ValueError):out['stateContainer']='UNKNOWN'
 out['nativePlatformDigestExpected']=IMAGE_PLATFORM;out['parentIndexDigestSeparate']=IMAGE_PARENT;out['nativeConfigDigestExpected']=IMAGE_NATIVE_CONFIG
 # The exact actual ID comes only from inspected state; configured aliases are not residency proof.
 c=out['selectedCommands']['external_container'].get('selected',{});pid=c.get('pid',0)
 if type(pid) is int and pid>0:out['processes'].append(proc(pid))
 out['qualification']='NOT_TESTED_PASSIVE_ONLY';return out

def main():
 p=argparse.ArgumentParser();g=p.add_mutually_exclusive_group(required=True);g.add_argument('--observe',action='store_true');g.add_argument('--remote',action='store_true');a=p.parse_args()
 if a.remote:r=remote()
 else:
  b=Path(__file__).read_bytes();receipt,out=bounded(SSH,b,65,1048576);r={'transport':receipt,'probeSourceSHA256':sha(b),'observation':json.loads(out) if receipt['state']=='READBACK' else None}
 print(json.dumps(r,indent=2));return 0 if a.remote or r['transport']['state']=='READBACK' else 1
if __name__=='__main__':raise SystemExit(main())
