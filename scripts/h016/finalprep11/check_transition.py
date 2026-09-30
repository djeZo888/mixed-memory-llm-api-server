import sys,pathlib,json,datetime
sys.path.insert(0,'/data/build/H016-20260927/worker1-r8')
from candidate_owner import dependency,inspect,get,read_key,run_cmd,IMAGE
P=pathlib.Path
def require_r8_settled(h):
    """Exact predecessor proof; never stop, extend, or adopt R8 here."""
    old_log = P('/data/logs/H016-20260927/worker1-r8')
    old = json.loads((old_log / 'OWNER.json').read_text())
    cid = '45c1a8e97199fc6876b6e9add26cfc956e03a1304d695ecf961ab940293d3aff'
    h.require(old['candidate_id'] == cid and old['native_pid'] == 942451 and
              old['pid'] == 939758 and
              old['native_started_at'] == '2026-09-27T15:15:50.592314598Z', 'r8_identity_changed')
    h.require(old['status'] == 'SETTLED_GLM_RESTORED' and not old['glm_suppressed'] and
              old.get('glm_restored_utc') and all(old['native_settled'][k] is True
              for k in ['pid_zero', 'cgroup_empty', 'gpu_compute_empty']), 'r8_not_normally_settled')
    c = inspect(cid)
    h.require(c['Id'] == cid and c['Image'] == IMAGE and c['Name'] == '/llm-h016-mimo-pro-r8' and
              not c['State']['Running'] and c['State']['Pid'] == 0 and
              c['State']['StartedAt'] == old['native_started_at'], 'r8_native_not_settled')
    unit = 'h016-mimo-profile-20260927-r8.service'
    props = dict(x.split('=', 1) for x in run_cmd(['systemctl', 'show', unit, '-p',
                     'MainPID,ControlPID,ActiveState,InvocationID']).splitlines())
    h.require(props.get('InvocationID') == 'f7eedd254a734907996d310a4feb7349', 'r8_invocation_changed')
    h.require(props.get('MainPID') == props.get('ControlPID') == '0' and
              props.get('ActiveState') in ['inactive', 'failed'], 'r8_owner_active')
    h.require(not P('/sys/fs/cgroup/system.slice', unit).exists(), 'r8_unit_cgroup_present')
    h.require(not P(old['native_cgroup']).exists() and not P('/proc/942451').exists() and
              not P('/proc/939758').exists(), 'r8_process_or_cgroup_present')
    h.require(not old.get('proxy_pid') or not P('/proc', str(old['proxy_pid'])).exists(),
              'r8_proxy_present')
h=dependency();out={'utc':h.now()}
with h.MountedStorageGuard(h.s) as g,h.AnchoredRoot('/data/logs/H016-20260927/worker1-r8',g) as a:
 out['r8_owner']=a.read_json('OWNER.json')
 c=inspect(out['r8_owner']['candidate_id']);out['native_state']=c['State']
out['r8_unit']=run_cmd(['systemctl','show','h016-mimo-profile-20260927-r8.service','-p','MainPID,ControlPID,ActiveState,SubState,InvocationID,Result'])
out['glm_unit']=run_cmd(['systemctl','show','llm-frontier-flash.service','-p','MainPID,ActiveState,SubState'])
if out['r8_owner']['status']=='SETTLED_GLM_RESTORED':
 require_r8_settled(h)
 code,value=get(30010,'/v1/readiness',read_key(h));assert code==200 and value.get('ready') is True
 out['glm_readiness']=value;out['transition']='EXACT_R8_SETTLED_ORIGINAL_GLM_READY'
else:out['transition']='R8_SETTLEMENT_IN_PROGRESS'
with h.transaction():h.s.root_payload_guard()
print(json.dumps(out))
