import pathlib,subprocess,json
T=pathlib.Path(__file__).resolve().parents[1]
code='''import pathlib,json,importlib.util,datetime,subprocess
p='/data/services/mimo-h016-20260927/source/owner.py';s=importlib.util.spec_from_file_location('ordinary',p);o=importlib.util.module_from_spec(s);s.loader.exec_module(o);h=o.setup()
def tryread(f):
 try:return {'pass':True,'value':f()}
 except Exception as e:return {'pass':False,'type':type(e).__name__,'reason':str(e)}
with h.MountedStorageGuard(h.s) as g:
 h.s.root_payload_guard();m=o.read(o.BASE/'manifest.json');st=o.read(o.BASE/'state.json');out={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'state':st,'unit':o.run(['systemctl','show',o.UNIT,'-p','MainPID,ControlPID,InvocationID,ActiveState,SubState,Result,ExecMainStatus,ExecMainStartTimestamp,ExecMainExitTimestamp,ExecStopPost,ControlGroup'],3),'source_preflight':tryread(lambda:o.source_preflight(h,m)),'current_sample':tryread(lambda:o.sample_guard(m,st['baseline'],85)),'latch':tryread(lambda:o.latch(h,st['boot_id']))}
 c=o.inspect(st['native']['container_id']);out['container']={k:c[k] for k in ['Id','Name','Image','State','HostConfig']};out['settlement_readback']={'old_pid_exists':pathlib.Path('/proc',str(st['native']['pid'])).exists(),'old_cgroup_exists':pathlib.Path(st['native_cgroup']).exists(),'gpu_compute':o.run(['nvidia-smi','--id='+o.GPU,'--query-compute-apps=pid','--format=csv,noheader,nounits'],3)}
 logs=subprocess.run(['docker','logs','--timestamps',c['Id']],capture_output=True,timeout=10);out['logs']={'stdout':logs.stdout.decode(errors='replace'),'stderr':logs.stderr.decode(errors='replace'),'rc':logs.returncode}
 out['journal']=subprocess.run(['journalctl','-u',o.UNIT,'--since','2026-09-27 17:44:50 UTC','--no-pager','-o','short-iso'],capture_output=True,text=True,timeout=5).stdout
 h.s.root_payload_guard();print(json.dumps(out,indent=2))
'''
r=subprocess.run(['ssh','-o','ConnectTimeout=5','ai-vm','sudo -n python3 -I -B -'],input=code,text=True,capture_output=True,timeout=30)
(T/'private/diagnostic.json').write_text(r.stdout);(T/'private/diagnostic.stderr').write_text(r.stderr)
v=json.loads(r.stdout);print(json.dumps({k:v[k] for k in ['utc','state','unit','current_sample','latch','settlement_readback','logs','journal']},indent=2))
