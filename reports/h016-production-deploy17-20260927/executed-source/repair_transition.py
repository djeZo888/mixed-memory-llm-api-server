import pathlib,json,subprocess,hashlib,base64
T=pathlib.Path(__file__).resolve().parents[1];R=T/'repo';sha=lambda b:hashlib.sha256(b).hexdigest();m=json.load(open(R/'reports/h016-production-deploy17-20260927/REPAIR-MANIFEST.proposed.json'));oldm=json.load(open(T/'private/manifest-final.json'));last=json.load(open(T/'private/final-read.json'))
owner=(R/'scripts/runtime/mimo/owner.py').read_bytes();unit=(R/'scripts/runtime/mimo/llm-frontier-mimo.service').read_bytes()
assert sha(owner)=='7768181c10bb35c7fcaa02d243913aaedf9ff7396416252b826dc2bbdb814a2c';assert sha(unit)=='c0c260e2fd554fc74ab045d072bdfa902780d05fa23b88f69f6324079e40573a'
header='import pathlib,json,subprocess,hashlib,base64,importlib.util,datetime,time,os,stat\n'
for k,v in [('m',m),('oldm',oldm),('expected_preserved',last['preserved']),('owner_raw',base64.b64encode(owner).decode()),('unit_raw',base64.b64encode(unit).decode())]:header+=k+'='+repr(v)+'\n'
code=header+'''
P=pathlib.Path;B=P('/data/build/H016-20260927/worker1-deploy17');CID='144757b104c97ffad8d05158e93f1abcb929d34083a1a944c5690e0e801e7fdc'
def emit(k,v):print(json.dumps({'key':k,'value':v}),flush=True)
def load():
 s=importlib.util.spec_from_file_location('ordinary', '/data/services/mimo-h016-20260927/source/owner.py');o=importlib.util.module_from_spec(s);s.loader.exec_module(o);return o
o=load();h=o.setup()
def deadline():o.require(time.time()<datetime.datetime.fromisoformat('2026-09-27T17:55:00+00:00').timestamp(),'corrected_admission_expired')
def sh(b):return hashlib.sha256(b).hexdigest()
def rawfile(a,n,b,mode=0o600):
 with a.open(n,os.O_WRONLY|os.O_CREAT|os.O_EXCL,mode) as f:f.write(b)
def show(u):return o.run(['systemctl','show',u,'-p','MainPID,ControlPID,ActiveState,SubState,Result,InvocationID,ExecMainStatus,ExecMainStartTimestamp,ControlGroup'],3)
def replace(p,b,mode):
 p=P(p);o.protected(p);tmp=p.with_name(p.name+'.repair17-new');fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,mode)
 try:os.write(fd,b);os.fsync(fd)
 finally:os.close(fd)
 os.replace(tmp,p)
deadline()
with h.acquire_lease(blocking=False),h.MountedStorageGuard(h.s) as g:
 h.s.root_payload_guard();o.source_preflight(h,oldm);o.require(o.read(o.BASE/'manifest.json')==oldm,'manifest_drift')
 state=o.read(o.BASE/'state.json');selected=o.selection()
 o.require(selected['generation']==2 and selected['manifest_sha256']==o.digest(oldm),'selection_drift')
 o.require(state['status']=='SETTLED' and state['request_hold'] is False and state['settlement']=={'cgroup_empty':True,'gpu_compute_empty':True,'pid_released':True},'unsettled')
 o.require(state['native']['container_id']==CID and state['launch_id']=='6c00066c594c420183430c5014d403f1','wrong_failed_instance')
 identity=show(o.UNIT);props=dict(x.split('=',1) for x in identity.splitlines());o.require(props['MainPID']==props['ControlPID']=='0' and props['InvocationID']=='c378d6ca8b384f6787c2fcdfe9e36842' and props['ActiveState'] in ('inactive','failed'),'owner_not_terminal')
 rawinspect=o.run(['docker','inspect',CID],4);c=o.exact_container(json.loads(rawinspect)[0],oldm,state)
 o.require(c['State']['Pid']==0 and not c['State']['Running'] and not P('/proc',str(state['native']['pid'])).exists(),'failed_native_live')
 cg=P(state['native_cgroup']);o.require(not cg.exists() or not (cg/'cgroup.procs').read_text().strip(),'cgroup_live')
 o.require(not o.run(['nvidia-smi','--id='+o.GPU,'--query-compute-apps=pid','--format=csv,noheader,nounits'],3).strip(),'gpu_live')
 for prior in expected_preserved:
  current=o.inspect(prior['Id']);o.require(current['Id']==prior['Id'] and current['Image']==prior['Image'] and current['State']['Running'] and current['State']['Pid']==prior['State']['Pid'] and current['State']['StartedAt']==prior['State']['StartedAt'],'other_model_changed')
 logs=subprocess.run(['docker','logs','--timestamps',CID],capture_output=True,timeout=8);o.require(logs.returncode==0,'failed_logs_unreadable')
 journal=o.run(['journalctl','-u',o.UNIT,'--since','2026-09-27 17:44:50 UTC','--no-pager','-o','short-iso'],5)
 with h.AnchoredRoot(str(B),g) as a:
  o.require(not (B/'failed-original').exists(),'archive_exists_no_replay');a.mkdir('failed-original');a.mkdir('repair')
  for n in ['manifest.json','selection.json','state.json','source/owner.py','source/llm-frontier-mimo.service']:
   rawfile(a,'failed-original/'+n.replace('/','_'),o.protected(o.BASE/n))
  rawfile(a,'failed-original/installed-unit',o.protected('/etc/systemd/system/llm-frontier-mimo.service'))
  for n,b in [('docker-inspect.json',rawinspect.encode()),('docker-stdout.log',logs.stdout),('docker-stderr.log',logs.stderr),('systemctl.txt',identity.encode()),('journal.txt',journal.encode())]:rawfile(a,'failed-original/'+n,b)
  a.atomic_json('failed-original/source-closure.json',oldm['source_sha256'])
  rawfile(a,'repair/owner.py',base64.b64decode(owner_raw));rawfile(a,'repair/llm-frontier-mimo.service',base64.b64decode(unit_raw))
 h.s.root_payload_guard();emit('failed_archived',{'path':str(B/'failed-original'),'container':CID,'settlement':'PASS'})
 o.require(o.digest(m)=='c2d4cb314ce86a6c082faf784a5c3c55a6bb95acc1056f43f8baaeaa43f9016b','new_manifest_digest')
 deadline();removed=o.run(['docker','rm',CID],5).strip();o.require(removed==CID,'wrong_removal');emit('removed_only',CID)
 replace(o.BASE/'source/owner.py',base64.b64decode(owner_raw),0o600)
 replace(o.BASE/'source/llm-frontier-mimo.service',base64.b64decode(unit_raw),0o600)
 replace('/etc/systemd/system/llm-frontier-mimo.service',base64.b64decode(unit_raw),0o644)
 with h.AnchoredRoot(str(o.BASE),g) as a:
  a.atomic_json('manifest.json',m);a.atomic_json('selection.json',{'schema_version':1,'selected_frontier':o.MODEL,'generation':selected['generation']+1,'manifest_sha256':o.digest(m)})
 h.s.root_payload_guard()
o=load();h=o.setup();o.run(['systemctl','daemon-reload'],8);emit('source_preflight',o.supervise(True))
timer=o.run(['systemctl','show','h016-deploy17-cutoff.timer','-p','LoadState'],3)
if timer.strip()=='LoadState=loaded':o.run(['systemctl','start','h016-deploy17-cutoff.timer'],5)
else:o.run(['systemd-run','--unit=h016-deploy17-cutoff','--on-calendar=2026-09-27 18:10:00 UTC','--timer-property=AccuracySec=1s','--property=Type=oneshot','--property=TimeoutStartSec=60','--property=StandardOutput=null','--property=StandardError=null','/usr/bin/python3','-I','-B',str(B/'cutoff.py')],8)
deadline();o.run(['systemctl','start',o.UNIT],10)
time.sleep(2)
with h.MountedStorageGuard(h.s) as g:
 h.s.root_payload_guard();out={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'unit':show(o.UNIT),'state':o.read(o.BASE/'state.json'),'selection':o.selection(),'manifest_canonical':o.digest(m),'manifest_raw':sh(o.protected(o.BASE/'manifest.json')),'source_changes':{p:sh(o.protected(p)) for p in [str(o.BASE/'source/owner.py'),str(o.BASE/'source/llm-frontier-mimo.service'),'/etc/systemd/system/llm-frontier-mimo.service']},'cutoff_timer':o.run(['systemctl','show','h016-deploy17-cutoff.timer','-p','ActiveState,SubState,NextElapseUSecRealtime'],3),'journal':o.run(['journalctl','-u',o.UNIT,'--since','2026-09-27 17:52:00 UTC','--no-pager','-o','short-iso'],4)}
 with h.AnchoredRoot(str(B),g) as a:a.atomic_json('repair/LAUNCH.json',out)
 h.s.root_payload_guard();emit('corrected_launch',out)
'''
compile(code,'repair-remote','exec');(T/'private/repair-remote.py').write_text(code)
r=subprocess.run(['ssh','-o','ConnectTimeout=5','ai-vm','sudo -n python3 -I -B -'],input=code,text=True,capture_output=True,timeout=60)
(T/'private/repair-launch.raw.jsonl').write_text(r.stdout);(T/'private/repair-launch.stderr').write_text(r.stderr)
events=[json.loads(l) for l in r.stdout.splitlines()];out={'returncode':r.returncode,'stderr':r.stderr,'events':events};(T/'ROOT-REPAIR-LAUNCH.json').write_text(json.dumps(out,indent=2)+'\n');(T/'ROOT-REPAIR-LAUNCH.md').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
