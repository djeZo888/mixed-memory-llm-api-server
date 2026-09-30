#!/usr/bin/env python3
"""One finite read, conditional one-shot dispatch; no reload, polling, or replay.
PINNED_CONFIG is supplied by the native-written mac-worker1 wrapper.
"""
import datetime,hashlib,http.client,importlib.util,json,os,time
from pathlib import Path
P=Path;B=P('/data/services/mimo-h016-20260927');L=P('/data/logs/H018-20260928/worker1-short');A=P('/data/build/H018-20260928/worker1-short')
def require(ok,why):
 if not ok:raise RuntimeError(why)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def module(name,p):
 s=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def show(o,u):return dict(x.split('=',1) for x in o.run(['systemctl','show',u,'-p','MainPID,ActiveState,SubState,InvocationID,Result,ExecMainStatus,UnitFileState'],3).splitlines())
def get(host,port,path,key):
 c=http.client.HTTPConnection(host,port,timeout=4)
 try:
  c.request('GET',path,headers={'Authorization':'Bearer '+key.decode()});r=c.getresponse();raw=r.read(2097153);require(r.status==200 and len(raw)<=2097152,'read_http_failed');return json.loads(raw)
 finally:c.close()
def main():
 cfg=PINNED_CONFIG
 p=B/'source/owner.py';require(sha(p.read_bytes())==cfg['source_sha256'][str(p)],'owner_pin_changed');o=module('dispatch_owner',p);h=o.setup()
 with h.MountedStorageGuard(h.s) as g:
  h.s.root_payload_guard();o.storage_paths(h,g)
  state=o.read(B/'state.json');identity={k:state.get(k) for k in ('boot_id','manifest_sha256','supervisor','launch_id','native')}
  require(identity==cfg['production_identity'],'not_this_launch')
  out={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'stage':state['status'],'production_identity':identity,'ordinary_unit':show(o,o.UNIT),'dispatched':False}
  if state['status']!='RUNNING':
   out.update(status='LOADING_RETURN_WITHOUT_WAIT' if state['status']=='LOADING' else 'NOT_READY_NO_DISPATCH',primary_failure=state.get('primary_failure'),cleanup_failure=state.get('settlement_failure'));print(json.dumps(out));return
  require(time.time()<cfg['admit_before_epoch'] and time.time()+600<cfg['hard_end_epoch'],'short_window_closed')
  require(not (L/'DISPATCH-ATTEMPT.json').exists() and not (L/'CLIENT.json').exists() and not (A/'AUTHORITY.json').exists(),'already_attempted_or_authorized_no_replay')
  u=show(o,'h018-short.service');require(u['MainPID']=='0' and u['ActiveState']=='inactive' and u['UnitFileState']=='static','short_not_inactive')
  for path,pin in cfg['source_sha256'].items():require(sha(o.protected(path))==pin,'source_pin_changed')
  transport=module('dispatch_transport',P('/data/build/H016-20260927/worker1-final13-long/client.py'))
  m,state,guard=transport.check_identity(o,cfg);o.source_preflight(h,m)
  key=o.read_key(h);require(o.native_ready(m,key) is True,'ordinary_native_not_ready')
  props=get('127.0.0.1',30012,'/props',key);slots=get('127.0.0.1',30012,'/slots',key)
  pp=get('10.156.100.60',30012,'/props',key);ps=get('10.156.100.60',30012,'/slots',key)
  for pr,sl in ((props,slots),(pp,ps)):
   require(pr['default_generation_settings']['n_ctx']==950000 and len(sl)==1 and sl[0]['n_ctx']==950000 and sl[0]['is_processing'] is False,'actual950000_idle_required')
  node=get('127.0.0.1',30008,'/control/v1/node/status',o.protected('/etc/llm-server/control-api-key').strip())
  rows=[r for r in node['services'] if r['service_id']==o.MODEL]
  require(len(rows)==1 and rows[0]['ready'] is True and rows[0]['freshness']=='fresh' and rows[0]['hardware_latched'] is False and node['node_manager']['actions']==[],'canonical_not_ready_unlatched')
  with o.settlement_lease(h) as lease:
   # Admission facts under canonical lease; request owner takes its own lease later.
   m,state,guard=transport.check_identity(o,cfg);o.latch(h,state['boot_id']);sample=o.sample_guard(m,state['baseline'],o.temperature_limit(o.run(['nvidia-smi','--id='+o.GPU,'-q','-x'],2)),state['native'])
   require(not (L/'DISPATCH-ATTEMPT.json').exists() and not (A/'AUTHORITY.json').exists(),'one_attempt')
   with h.AnchoredRoot(str(A),g) as a:a.atomic_json('AUTHORITY.json',cfg)
   out.update(status='SHORT_DISPATCH_INTENT',authority_sha256=sha(o.protected(A/'AUTHORITY.json')),actual_usable_context=950000,private_usable_context=950000,guard=guard,memory_policy=sample['memory_policy'],node=rows[0])
   with h.AnchoredRoot(str(L),g) as a:a.atomic_json('DISPATCH-ATTEMPT.json',out)
   h.s.root_payload_guard();lease.validate()
 # No staging lease is held across start. No retry on uncertain dispatch.
 o.run(['systemctl','start','h018-short.service'],10)
 out.update(status='SHORT_DISPATCHED',dispatched=True,staging_lease_released_before_dispatch=True,short_unit=show(o,'h018-short.service'))
 with h.MountedStorageGuard(h.s) as g,h.AnchoredRoot(str(L),g) as a:
  h.s.root_payload_guard();a.atomic_json('DISPATCH.json',out);h.s.root_payload_guard()
 print(json.dumps(out))
if __name__=='__main__':main()
