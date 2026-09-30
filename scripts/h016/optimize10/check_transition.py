import sys,pathlib,json,datetime
sys.path.insert(0,'/data/build/H016-20260927/worker1-r8')
from candidate_owner import dependency,require_r7_settled,inspect,get,read_key,run_cmd
h=dependency();out={'utc':h.now()}
with h.MountedStorageGuard(h.s) as g,h.AnchoredRoot('/data/logs/H016-20260927/worker1-r7',g) as a:
 out['r7_owner']=a.read_json('OWNER.json')
 c=inspect(out['r7_owner']['candidate_id']);out['native_state']=c['State']
out['r7_unit']=run_cmd(['systemctl','show','h016-mimo-profile-20260927-r7.service','-p','MainPID,ControlPID,ActiveState,SubState,InvocationID,Result'])
out['glm_unit']=run_cmd(['systemctl','show','llm-frontier-flash.service','-p','MainPID,ActiveState,SubState'])
if out['r7_owner']['status']=='SETTLED_GLM_RESTORED':
 require_r7_settled(h)
 code,value=get(30010,'/v1/readiness',read_key(h));assert code==200 and value.get('ready') is True
 out['glm_readiness']=value;out['transition']='EXACT_R7_SETTLED_ORIGINAL_GLM_READY'
else:out['transition']='R7_SETTLEMENT_IN_PROGRESS'
with h.transaction():h.s.root_payload_guard()
print(json.dumps(out))
