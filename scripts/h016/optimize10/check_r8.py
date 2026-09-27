#!/usr/bin/env python3
"""Short read-only R8 owner/start/guard snapshot; no inference or waiting."""
import json,pathlib,subprocess,datetime
T=pathlib.Path(__file__).resolve().parents[4]
code='''import sys,json,pathlib
sys.path.insert(0,'/data/build/H016-20260927/worker1-r8')
from candidate_owner import dependency,inspect,run_cmd
h=dependency();out={'utc':h.now()}
out['unit']=run_cmd(['systemctl','show','h016-mimo-profile-20260927-r8.service','-p','MainPID,ControlPID,InvocationID,ExecMainStartTimestamp,ActiveState,SubState,Result,ControlGroup,RuntimeMaxUSec,TimeoutStopUSec'])
with h.MountedStorageGuard(h.s) as g,h.AnchoredRoot('/data/logs/H016-20260927/worker1-r8',g) as a:
 if a.stat('OWNER.json',missing_ok=True):
  owner=a.read_json('OWNER.json');out['owner']=owner
  if owner.get('candidate_id'):
   c=inspect(owner['candidate_id']);out['native']={'id':c['Id'],'image':c['Image'],'state':c['State'],'limits':{k:c['HostConfig'][k] for k in ['Memory','MemorySwap','CpusetCpus','CpusetMems']},'treatment_env':[x for x in c['Config']['Env'] if x.split('=',1)[0] in ['GOMP_SPINCOUNT','OMP_NUM_THREADS']],'argv':c['Config']['Cmd']}
 if a.stat('TELEMETRY.jsonl',missing_ok=True):
  with a.open('TELEMETRY.jsonl') as f:
   f.seek(max(0,a.stat('TELEMETRY.jsonl').st_size-20000));lines=f.read(30000).decode().splitlines()
  if lines:out['latest_guard']=json.loads(lines[-1])
with h.transaction():h.s.root_payload_guard()
out['registered_root_guards']='PASS'
print(json.dumps(out))
'''
r=subprocess.run(['ssh','ai-vm','sudo -n python3 -B -'],input=code,text=True,capture_output=True,timeout=20)
if r.returncode:raise RuntimeError('R8 short check failed: '+r.stderr[-1000:])
v=json.loads(r.stdout);now=datetime.datetime.now(datetime.timezone.utc).strftime('%H%M%S');(T/('private/optimize10/R8-CHECK-'+now+'.json')).write_text(json.dumps(v,indent=2)+'\n')
(T/'R8-PROGRESS.json').write_text(json.dumps({k:v[k] for k in ['utc','unit','registered_root_guards']}|{'status':v.get('owner',{}).get('status'),'native':v.get('native'),'latest_guard':v.get('latest_guard')},indent=2)+'\n')
print(json.dumps({'utc':v['utc'],'unit':v['unit'],'owner_status':v.get('owner',{}).get('status'),'owner_pid':v.get('owner',{}).get('pid'),'native':v.get('native'),'guard_utc':v.get('latest_guard',{}).get('utc')}))
