import sys,pathlib,json,hashlib,datetime,subprocess
sys.path.insert(0,'/data/build/H016-20260927/worker1-r8')
from candidate_owner import dependency,inspect,get,read_key,run_cmd
h=dependency();P=pathlib.Path
assert ROOT_WINNER['authorized'] is True and ROOT_WINNER['normal_r8_settlement_authorized'] is True
assert ROOT_WINNER['threads']==16 and ROOT_WINNER['context']==1000000
assert datetime.datetime.now(datetime.timezone.utc)<datetime.datetime.fromisoformat(ROOT_WINNER['admission_utc'])
assert hashlib.sha256(P('/data/build/H016-20260927/worker1-r8/candidate_owner.py').read_bytes()).hexdigest()=='04d8e326506279baa5f9932df861b8cefc3b08195adc0ee25f26b705aecb2f3e'
u=run_cmd(['systemctl','show','h016-mimo-profile-20260927-r8.service','-p','MainPID,InvocationID,ActiveState'])
assert 'MainPID=939758\n' in u and 'InvocationID=f7eedd254a734907996d310a4feb7349' in u and 'ActiveState=active' in u
c=inspect('45c1a8e97199fc6876b6e9add26cfc956e03a1304d695ecf961ab940293d3aff')
assert c['State']['Running'] and c['State']['Pid']==942451 and c['State']['StartedAt']=='2026-09-27T15:15:50.592314598Z'
code,slots=get(30012,'/slots',read_key(h));assert code==200 and len(slots)==1 and slots[0]['is_processing'] is False
with h.transaction():h.s.root_payload_guard()
planned=h.now();subprocess.run(['systemctl','stop','--no-block','h016-mimo-profile-20260927-r8.service'],check=True,timeout=10)
print(json.dumps({'status':'R8_NORMAL_OWNER_STOP_REQUESTED','planned_utc':planned,'utc':h.now(),'unit_before':u,'native_pid':942451,'slot_idle':True,'capture_dispatched':False,'readback':run_cmd(['systemctl','show','h016-mimo-profile-20260927-r8.service','-p','MainPID,ControlPID,ActiveState,SubState,InvocationID'])}))
