#!/usr/bin/env python3
"""Mac-side single dispatch handshake; Linux systemd owns the receiver."""
import datetime,hashlib,json,pathlib,subprocess,sys
T=pathlib.Path(__file__).resolve().parents[4]
plan=json.loads((T/'CAPTURE-READY.json').read_text())
assert plan['status']=='READY_AWAIT_ROOT_CAPTURE_GO', 'capture deferred; no dispatch'
go=json.loads((T/'ROOT-CAPTURE-GO.json').read_text())
now=datetime.datetime.now(datetime.timezone.utc)
assert go.get('authorized') is True and go.get('request')=='HOST-UMC512-REPLACEMENT'
assert datetime.datetime.fromisoformat(go['expires_utc'].replace('Z','+00:00'))>now
assert now<datetime.datetime(2026,9,27,15,12,tzinfo=datetime.timezone.utc)
assert not (T/'CAPTURE-DISPATCH.json').exists(), 'no replay; inspect actual unit first'
source=pathlib.Path(__file__).with_name('umc512_client.py')
assert hashlib.sha256(source.read_bytes()).hexdigest()==plan['source_sha256']
intent={'status':'DISPATCH_INTENT','planned_utc':now.isoformat(),'go':go,'command':plan['command'],'source_sha256':plan['source_sha256']}
(T/'CAPTURE-DISPATCH.json').write_text(json.dumps(intent,indent=2)+'\n')
code='''import datetime,hashlib,json,pathlib,subprocess,sys
sys.path.insert(0,'/data/build/H016-20260927/worker1-r7')
from candidate_owner import dependency
h=dependency()
p=PLAN
assert hashlib.sha256(pathlib.Path('/data/build/H016-20260927/worker1-optimize10/umc512_client.py').read_bytes()).hexdigest()==p['source_sha256']
assert subprocess.check_output(['systemctl','show',p['unit'],'-p','LoadState','--value'],text=True).strip()=='not-found'
assert datetime.datetime.now(datetime.timezone.utc)<datetime.datetime.fromisoformat(EXPIRY.replace('Z','+00:00'))
with h.transaction():h.s.root_payload_guard()
subprocess.run(p['command'],check=True,stdout=subprocess.DEVNULL,timeout=10)
print(json.dumps({'status':'DISPATCHED','utc':h.now(),'unit':p['unit'],'readback':subprocess.check_output(['systemctl','show',p['unit'],'-p','MainPID,InvocationID,ExecMainStartTimestamp,ActiveState,SubState,ControlGroup,RuntimeMaxUSec'],text=True)}))
'''.replace('PLAN',repr(plan)).replace('EXPIRY',repr(go['expires_utc']))
r=subprocess.run(['ssh','ai-vm','sudo -n python3 -B -'],input=code,text=True,capture_output=True,timeout=25)
intent.update(returncode=r.returncode,readback=json.loads(r.stdout) if r.returncode==0 else None,error=r.stderr[-1500:] if r.returncode else None)
(T/'CAPTURE-DISPATCH.json').write_text(json.dumps(intent,indent=2)+'\n')
print(json.dumps(intent))
sys.exit(r.returncode)
