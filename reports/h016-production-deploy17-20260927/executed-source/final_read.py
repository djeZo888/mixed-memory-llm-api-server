import pathlib,subprocess,json
T=pathlib.Path(__file__).resolve().parents[1]
code='''import pathlib,json,importlib.util,datetime,subprocess,http.client,hashlib,sys
p='/data/services/mimo-h016-20260927/source/owner.py';s=importlib.util.spec_from_file_location('ordinary',p);o=importlib.util.module_from_spec(s);s.loader.exec_module(o);h=o.setup()
with h.MountedStorageGuard(h.s) as g:
 h.s.root_payload_guard();st=o.read(o.BASE/'state.json');m=o.read(o.BASE/'manifest.json');out={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'state':st,'selection':o.selection(),'manifest_canonical':o.digest(m),'manifest_raw':hashlib.sha256(o.protected(o.BASE/'manifest.json')).hexdigest(),'unit':o.run(['systemctl','show',o.UNIT,'-p','MainPID,ControlPID,InvocationID,ActiveState,SubState,Result,ExecMainStatus,ControlGroup'],3),'source_pins':{p:hashlib.sha256(o.protected(p)).hexdigest() for p in m['source_sha256']}}
 key=o.protected('/etc/llm-server/control-api-key').strip();c=http.client.HTTPConnection('127.0.0.1',30008,timeout=6);c.request('GET','/control/v1/node/status',headers={'Authorization':'Bearer '+key.decode()});r=c.getresponse();out['node']={'http_status':r.status,'snapshot':json.loads(r.read(2*1024*1024))};c.close()
 key=o.read_key(h)
 sys.path.insert(0,'/data/build/H016-20260927/worker1-r12-spread4');import candidate_owner as old
 out['preserved']=[]
 for name in old.PRESERVED:
  c=o.inspect(name);out['preserved'].append({k:c[k] for k in ['Id','Name','Image','State']})
 out['qwen_readiness']={str(port):old.get(port,'/v1/readiness',key) for port in (30002,30004)}
 out['qwen_info']={str(port):old.get(port,'/get_server_info',key) for port in (30002,30004)}
 out['glm_unit']=o.run(['systemctl','show',o.GLM_UNIT,'-p','MainPID,ActiveState,SubState'],3)
 out['node_unit']=o.run(['systemctl','show','llm-node.service','-p','MainPID,InvocationID,ExecMainStartTimestamp,ActiveState,SubState'],3)
 out['no_inference']=True
 with h.AnchoredRoot('/data/build/H016-20260927/worker1-deploy17',g) as a:a.atomic_json('FAILED-SETTLED-READBACK.json',out)
 # This deadline timer belongs solely to this now-settled failed launch; no pending load remains.
 o.require(st['status']=='SETTLED' and st['request_hold'] is False and all(st['settlement'].values()),'settlement_required')
 o.run(['systemctl','stop','h016-deploy17-cutoff.timer'],5);out['cutoff_timer']=o.run(['systemctl','show','h016-deploy17-cutoff.timer','-p','ActiveState,SubState'],3)
 h.s.root_payload_guard();print(json.dumps(out,indent=2))
'''
(T/'private/final-read-remote.py').write_text(code)
r=subprocess.run(['ssh','-o','ConnectTimeout=5','ai-vm','sudo -n python3 -I -B -'],input=code,text=True,capture_output=True,timeout=35)
(T/'private/final-read.json').write_text(r.stdout);(T/'private/final-read.stderr').write_text(r.stderr)
if r.returncode:print(r.stderr)
else:
 v=json.loads(r.stdout);print(json.dumps({k:v[k] for k in ['utc','unit','qwen_readiness','node_unit','glm_unit','cutoff_timer']},indent=2));print(json.dumps(v['node'],indent=2)[:6000])
