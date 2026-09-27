P=pathlib.Path
B=P('/data/build/H016-20260927/worker1-deploy17')
def emit(k,v):print(json.dumps({'key':k,'value':v}),flush=True)
def show(u):return dict(x.split('=',1) for x in o.run(['systemctl','show',u,'-p','MainPID,ControlPID,InvocationID,ActiveState,SubState,Result,ExecMainStatus,ControlGroup,ExecMainStartTimestamp'],4).splitlines())
def verify_deadline():o.require(time.time()<datetime.datetime.fromisoformat('2026-09-27T17:48:00+00:00').timestamp(),'launch_admission_expired')
def sha(b):return hashlib.sha256(b).hexdigest()
def protected_write(p,raw,mode,replace=False):
 p=P(p)
 for ancestor in p.parents:
  if ancestor.exists():
   st=ancestor.lstat();o.require(stat.S_ISDIR(st.st_mode) and st.st_uid==0 and not st.st_mode&0o022,'unsafe_write_parent')
 p.parent.mkdir(parents=True,exist_ok=True,mode=0o755)
 tmp=p.with_name(p.name+'.deploy17-new')
 fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,mode)
 try:
  os.write(fd,raw);os.fsync(fd)
 finally:os.close(fd)
 if p.exists():o.protected(p);o.require(replace,'unexpected_destination')
 os.replace(tmp,p)
def anchored_write(a,n,b,mode=0o600):
 with a.open(n,os.O_WRONLY|os.O_CREAT|os.O_EXCL,mode) as f:f.write(b)
verify_deadline()
sys.path.insert(0,'/data/build/H016-20260927/worker1-affinity14')
import controller
terminal=controller.proof('r12-spread4');emit('terminal',terminal)
pair=o.read('/data/logs/H016-20260927/worker1-affinity14/PAIR.json')
cu=show('h016-affinity14-20260927.service')
o.require(pair['controller_invocation_id']=='9ea907b6950f4df2841009848a9cf2f3' and pair['pid']==2823617 and pair['profiles']['r13-spread2']['status']=='NOT_TESTED','pair_identity')
o.require(cu['MainPID']==cu['ControlPID']=='0' and cu['ActiveState']=='inactive' and cu['InvocationID'] in ('','9ea907b6950f4df2841009848a9cf2f3'),'controller_live')
o.require(not P('/proc/2823617').exists() and not P('/sys/fs/cgroup/system.slice/h016-affinity14-20260927.service').exists(),'controller_process')
import candidate_owner as old
rows=[]
key=o.read_key(h)
for name in [old.GLM_ID]+old.PRESERVED:
 c=o.inspect(name);o.require(c['State']['Running'],'preserved_not_running');cg=o.cgpath(c['State']['Pid']);sched=[]
 for pid in (cg/'cgroup.procs').read_text().split():
  if P('/proc',pid,'comm').read_text().strip().startswith(('sglang::schedul','sgl_diffusion::')):
   w=P('/proc',pid,'wchan').read_text();o.require('poll' in w,'scheduler_busy');sched.append({'pid':int(pid),'wchan':w,'stat':P('/proc',pid,'stat').read_text()})
 o.require(len(sched)==1,'scheduler_ambiguous');rows.append({'container':c['Id'],'name':c['Name'],'started_at':c['State']['StartedAt'],'native_pid':c['State']['Pid'],'scheduler':sched[0]})
time.sleep(1)
for row in rows:o.require('poll' in P('/proc',str(row['scheduler']['pid']),'wchan').read_text(),'scheduler_became_busy')
for port in (30002,30004,30010):
 code,info=old.get(port,'/get_server_info',key);o.require(code==200 and info['context_length']==(1048576 if port==30010 else 480000),'preserved_context')
emit('idle_and_preserved',rows)
with h.MountedStorageGuard(h.s) as g:
 h.s.root_payload_guard();o.require(not B.exists() and not o.BASE.exists(),'unexpected_namespace')
 for file,pin in zip(m['artifact']['files'],h.manifest()['files']):
  p=P(h.MODEL,file['name']);g.check_path(str(p));st=p.lstat()
  o.require(file['name']==pin['rfilename'] and file['sha256']==pin['lfs']['sha256'] and file['size']==pin['size'],'artifact_manifest')
  o.require(stat.S_ISREG(st.st_mode) and st.st_uid==0 and not st.st_mode&0o022 and {k:getattr(st,'st_'+k) for k in ('dev','ino','size','mtime_ns','ctime_ns')}==file['stat'],'artifact_stat')
 o.require(o.inspect(o.IMAGE)['Id']==o.IMAGE,'image')
 for p,d in m['source_sha256'].items():
  if p in guardpins:o.require(sha(o.protected(p))==d,'control_guard_drift')
 for n,d in m['glm_preserved_sha256'].items():o.require(sha(o.protected(o.GLM_BASE/n))==d,'glm_drift')
 for f in files:
  o.require(sha(base64.b64decode(f['bytes']))==f['sha256'],'packet_digest')
  actual=sha(o.protected(f['destination'])) if P(f['destination']).exists() else None
  o.require(actual==f.get('before_sha256'),'destination_changed')
 with h.acquire_lease(blocking=False):
  with h.AnchoredRoot('/data/build',g) as a:a.mkdir('H016-20260927/worker1-deploy17')
  with h.AnchoredRoot(str(B),g) as a:
   a.mkdir('rollback');a.mkdir('packet')
   for f in files:
    dest=f['destination'];raw=base64.b64decode(f['bytes'])
    anchored_write(a,'packet/'+sha(dest.encode()),raw)
    if P(dest).exists():anchored_write(a,'rollback/'+sha(dest.encode()),o.protected(dest))
   backups={}
   for p in [o.GLM_BASE/'config.json',o.GLM_BASE/'state.json',o.GLM_BASE/'source/owner.py',P('/etc/systemd/system/llm-frontier-flash.service')]:
    raw=o.protected(p);anchored_write(a,'rollback/'+sha(str(p).encode()),raw);backups[str(p)]=sha(raw)
   a.atomic_json('rollback-index.json',{'files':backups,'source_originals':[{k:f.get(k) for k in ('destination','before_sha256')} for f in files], 'selection_original':'ABSENT','glm_unit':show(o.GLM_UNIT),'glm_enablement':o.run(['systemctl','is-enabled',o.GLM_UNIT],4)})
  with h.AnchoredRoot('/data/services',g) as a:a.mkdir('mimo-h016-20260927')
  with h.AnchoredRoot(str(o.BASE),g) as a:
   a.mkdir('source');a.mkdir('qualification/r9')
   for f in files:
    if f['destination'].startswith(str(o.BASE)+'/'):anchored_write(a,str(P(f['destination']).relative_to(o.BASE)),base64.b64decode(f['bytes']),int(f['mode'],8))
   for n,d in [('numactl',o.NUMACTL_SHA),('libnuma.so.1.0.0',o.LIBNUMA_SHA)]:
    raw=o.protected('/data/build/H016-20260927/worker1-r9/'+n);o.require(sha(raw)==d,'numa_changed');anchored_write(a,'source/'+n,raw,0o755 if n=='numactl' else 0o644)
   for dest,raw in receipts.items():anchored_write(a,str(P(dest).relative_to(o.BASE)),base64.b64decode(raw))
   a.atomic_json('manifest.json',m)
   a.atomic_json('selection.json',{'schema_version':1,'selected_frontier':o.GLM,'generation':1})
  for f in files:
   if f['destination'].startswith(str(o.BASE)+'/'):continue
   if f['before_sha256']==f['sha256']:continue
   protected_write(f['destination'],base64.b64decode(f['bytes']),int(f['mode'],8),replace=f['before_sha256'] is not None)
  h.s.root_payload_guard()
 emit('installed',{'manifest_canonical':o.digest(m),'manifest_raw':sha(o.protected(o.BASE/'manifest.json')),'glm_selection':o.selection(),'artifact_stat_pins':13,'control_guard_pins':len(guardpins)})
 o.run(['systemctl','daemon-reload'],10)
 emit('node_binding',o.run(['/usr/bin/python3','-I','-B','/usr/local/lib/llm-server/node-api/scripts/control/node_serve.py','--check-binding'],10))
 o.source_preflight(h,m)
 verify_deadline()
 # Exact original GLM ordinary owner handles its own canonical lease.
 before=o.inspect(old.GLM_ID);glm_pid=before['State']['Pid'];glm_cg=o.cgpath(glm_pid)
 o.run(['systemctl','stop',o.GLM_UNIT],30)
 after=o.inspect(old.GLM_ID)
 o.require(after['Id']==before['Id'] and after['State']['Pid']==0 and not after['State']['Running'],'glm_not_stopped')
 o.require(not P('/proc',str(glm_pid)).exists() and (not glm_cg.exists() or not (glm_cg/'cgroup.procs').read_text().strip()),'glm_not_released')
 o.require(not o.run(['nvidia-smi','--id='+o.GPU,'--query-compute-apps=pid','--format=csv,noheader,nounits'],3).strip(),'gpu_not_released')
 emit('glm_settlement',{'container':before['Id'],'pid_zero':True,'cgroup_empty':True,'gpu_empty':True})
 with h.acquire_lease(blocking=False):
  previous=o.selection();o.require(previous['selected_frontier']==o.GLM,'selection_changed')
  o.write(h,'selection.json',{'schema_version':1,'selected_frontier':o.MODEL,'generation':previous['generation']+1,'manifest_sha256':o.digest(m)})
 emit('source_preflight',o.supervise(True))
 # Independent deadline coordinator is installed before launch; only normal stop if not ready at cutoff.
 with h.AnchoredRoot(str(B),g) as a:anchored_write(a,'cutoff.py',cutoff_source.encode())
 o.run(['systemd-run','--unit=h016-deploy17-cutoff','--on-calendar=2026-09-27 18:10:00 UTC','--timer-property=AccuracySec=1s','--property=Type=oneshot','--property=TimeoutStartSec=60','--property=StandardOutput=null','--property=StandardError=null','/usr/bin/python3','-I','-B',str(B/'cutoff.py')],8)
 verify_deadline()
 o.run(['systemctl','restart','llm-node.service'],12)
 o.run(['systemctl','start',o.UNIT],12)
 time.sleep(1)
 emit('launch',{'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'unit':show(o.UNIT),'selection':o.selection(),'manifest_canonical':o.digest(m),'state':o.read(o.BASE/'state.json') if (o.BASE/'state.json').exists() else None,'cutoff_timer':show('h016-deploy17-cutoff.timer')})
 h.s.root_payload_guard()
