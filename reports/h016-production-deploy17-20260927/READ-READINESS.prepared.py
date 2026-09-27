#!/usr/bin/env python3
"""One read-only ordinary readiness snapshot. No inference or lifecycle action."""
import pathlib,json,subprocess
T=pathlib.Path(__file__).resolve().parent
code='''import pathlib,json,importlib.util,datetime,hashlib,http.client,time
p='/data/services/mimo-h016-20260927/source/owner.py';s=importlib.util.spec_from_file_location('ordinary',p);o=importlib.util.module_from_spec(s);s.loader.exec_module(o);h=o.setup()
with h.MountedStorageGuard(h.s) as g:
 h.s.root_payload_guard();state=o.read(o.BASE/'state.json');out={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'state':state,'scope':'ONE_READ_ONLY_SNAPSHOT_NO_INFERENCE'}
 m=o.read(o.BASE/'manifest.json');out['manifest']=m;out['manifest_raw_sha256']=hashlib.sha256(o.protected(o.BASE/'manifest.json')).hexdigest();out['manifest_canonical_sha256']=o.digest(m);out['selection']=o.selection()
 out['unit']=dict(x.split('=',1) for x in o.run(['systemctl','show',o.UNIT,'-p','MainPID,ControlPID,InvocationID,ActiveState,SubState,Result,ExecMainStatus,ControlGroup,ExecMainStartTimestamp,StandardOutput,StandardError'],3).splitlines())
 out['journal']=o.run(['journalctl','-u',o.UNIT,'--since','2026-09-27 17:54:50 UTC','--no-pager','-o','short-iso'],4)
 out['guard']=o.read(o.BASE/'guard.json') if (o.BASE/'guard.json').exists() else None
 if state['status']=='RUNNING':
  o.require(state['manifest_sha256']==o.digest(m) and state['selection']==out['selection'] and state['boot_id']==o.BOOT.read_text().strip(),'state_binding')
  o.require(out['unit']['ActiveState']=='active' and out['unit']['InvocationID']==state['supervisor']['invocation_id'] and int(out['unit']['MainPID'])==state['supervisor']['pid'],'unit_binding')
  o.source_preflight(h,m);out['source_pins']={p:hashlib.sha256(o.protected(p)).hexdigest() for p in m['source_sha256']}
  c=o.exact_container(o.inspect(state['native']['container_id']),m,state);out['native']=c
  proxy=o.read(o.BASE/'proxy-state.json');out['proxy']=proxy
  o.require(proxy['native']==state['native'] and proxy['launch_id']==state['launch_id'] and proxy['boot_id']==state['boot_id'] and proxy['parent_pid']==state['supervisor']['pid'] and proxy['pid_start_ticks']==o.ticks(proxy['pid']),'proxy_identity')
  o.require(state['request_hold'] is False and proxy['active_requests']==0 and proxy['quarantined'] is False,'request_disposition')
  guard=out['guard'];o.require(guard['status']=='ok' and guard['selection']==out['selection'] and guard['native']==state['native'] and 0<=time.monotonic()-guard['observed_monotonic_s']<15,'guard_binding_or_age')
  key=o.read_key(h);data={path:o.get(path,key) for path in ['/props','/slots']};out['native_http']=data
  realget=o.get
  try:
   o.get=lambda path,key,timeout=1:data[path];o.require(o.native_ready(m,key),'native_not_ready')
  finally:o.get=realget
  o.require(data['/slots'][1][0]['is_processing'] is False,'native_slot_busy')
  out['fresh_sample']=o.sample_guard(m,state['baseline'],o.temperature_limit(o.run(['nvidia-smi','--id='+o.GPU,'-q','-x'],3)),state['native']);out['fresh_latch']=o.latch(h,state['boot_id'])
  out['status']='ORDINARY_NATIVE_READINESS_PASS'
 else:out['status']='NOT_READY_'+state['status']
 key=o.protected('/etc/llm-server/control-api-key').strip();c=http.client.HTTPConnection('127.0.0.1',30008,timeout=6);c.request('GET','/control/v1/node/status',headers={'Authorization':'Bearer '+key.decode()});r=c.getresponse();out['node']={'http_status':r.status,'snapshot':json.loads(r.read(2*1024*1024))};c.close()
 out['preserved']=[]
 for name in ['ae049b4eb723d7932a1dbf72e502f907faa424c83b05eb61b96afd96ca5f98f9','3280b5d1cb3ff8e60e312eef0ca06f81f210866d10b8acfab9f6db6c1fbf5566','15031b926938cd0492e1c678d8319e4ed2363d1bc705e6d53ebed5f1ee9db1d6']:
  c=o.inspect(name);out['preserved'].append({k:c[k] for k in ['Id','Name','Image','State']})
 h.s.root_payload_guard();print(json.dumps(out,indent=2))
'''
r=subprocess.run(['ssh','-o','ConnectTimeout=5','ai-vm','sudo -n python3 -I -B -'],input=code,text=True,capture_output=True,timeout=35)
stamp=__import__('datetime').datetime.now(__import__('datetime').timezone.utc).strftime('%Y%m%dT%H%M%SZ')
p=T/'private'/('readiness-'+stamp+'.json');p.write_text(r.stdout);p.with_suffix('.stderr').write_text(r.stderr)
if r.returncode:print(json.dumps({'status':'READBACK_FAILED','receipt':str(p),'stderr':r.stderr[-1500:]}));raise SystemExit(r.returncode)
v=json.loads(r.stdout);summary={'status':v['status'],'utc':v['utc'],'receipt':str(p),'unit':v['unit'],'manifest_canonical_sha256':v['manifest_canonical_sha256'],'selection':v['selection'],'native':v['state'].get('native'),'source_readback':v.get('source_pins')}
(T/'ROOT-READINESS.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
