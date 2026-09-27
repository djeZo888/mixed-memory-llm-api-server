import sys,pathlib,json,hashlib,datetime,subprocess
sys.path.insert(0,'/data/build/H016-20260927/worker1-r7')
from candidate_owner import dependency,inspect,get,read_key,run_cmd
h=dependency();P=pathlib.Path;B=P('/data/build/H016-20260927/worker1-r8')
go=json.loads((B/'ROOT-R8-GO.json').read_text())
assert go['authorized'] is True and datetime.datetime.now(datetime.timezone.utc)<datetime.datetime.fromisoformat(go['expires_utc'])
for n,d in go['source_sha256'].items():assert hashlib.sha256((B/n).read_bytes()).hexdigest()==d
assert hashlib.sha256(P('/data/build/H016-20260927/worker1-r7/candidate_owner.py').read_bytes()).hexdigest()=='4e2c9e98503d4e7ce7a2bb18cd589f5767d53cf7fdca2cd04b397173aa258c71'
u=run_cmd(['systemctl','show','h016-mimo-profile-20260927-r7.service','-p','MainPID,InvocationID,ActiveState'])
assert 'MainPID=229308\n' in u and 'InvocationID=2034e3b8f6004f6da8ebf7a92a389690' in u and 'ActiveState=active' in u
c=inspect('b0c319cce5c8fcececc28acb01ec92f68693588ba843c8136107927aa7ffbac1')
assert c['State']['Running'] and c['State']['Pid']==232672 and c['State']['StartedAt']=='2026-09-27T14:28:05.871420053Z'
code,slots=get(30012,'/slots',read_key(h));assert code==200 and len(slots)==1 and slots[0]['is_processing'] is False
with h.transaction():h.s.root_payload_guard()
planned=h.now();subprocess.run(['systemctl','stop','--no-block','h016-mimo-profile-20260927-r7.service'],check=True,timeout=10)
print(json.dumps({'status':'R7_NORMAL_OWNER_STOP_REQUESTED','planned_utc':planned,'utc':h.now(),'unit_before':u,'native_pid':232672,'slot_idle':True,'capture_dispatched':False,'readback':run_cmd(['systemctl','show','h016-mimo-profile-20260927-r7.service','-p','MainPID,ControlPID,ActiveState,SubState,InvocationID'])}))
