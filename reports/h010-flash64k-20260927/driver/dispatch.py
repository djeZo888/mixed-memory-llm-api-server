"""Stage and dispatch exactly one authorized H010 task job; no model mutation."""
from pathlib import Path
import base64,datetime,hashlib,json,subprocess
HERE=Path(__file__).resolve().parent
TASK=Path.cwd().parent
common=(HERE/'vm-common.py').read_text()+'\n'  # Preserve executed helper separator.
contract=(TASK/'ROOT-CONTRACT.md').read_text()
assert 'actual quiet handoff; benchmark GO' in contract
quiet=json.loads((TASK/'HARNESS-QUIET-01.json').read_text())
assert quiet
expected=json.loads(Path('reports/h009-flash-phase2-20260926/evidence/FINAL-IDENTITY.json').read_text())['source_matches']
full=common+'\nFIXTURE_SOURCE='+repr((HERE/'fixture_native.py').read_text())+'\nEXPECTED_IDENTITIES='+repr(expected)+'\n'+(HERE/'qualify-body.py').read_text()
compile(full,'h010-job.py','exec')
(TASK/'tools/h010-job.py').write_text(full)
digest=hashlib.sha256(full.encode()).hexdigest()
params={'source_sha256':digest,'root_plan_commit':'200661a','base':'6772a77e9a8ecc37200509ec50f501be5fa48c11',
 'native_thread':'01a0e007-15cf-7c42-af30-7711982abd06',
 'quiet_receipt_sha256':hashlib.sha256((TASK/'HARNESS-QUIET-01.json').read_bytes()).hexdigest(),
 'contract_sha256':hashlib.sha256(contract.encode()).hexdigest()}
remote=common+'\nRAW='+repr(base64.b64encode(full.encode()).decode())+'\nPARAMS='+repr(params)+r'''
import base64
unit='h010-flash64k-qualification'
path='/data/logs/flash-h008-20260926/H010-FLASH64K-job.py'
owner='/data/logs/flash-h008-20260926/H010-FLASH64K-OWNER.json'
end=datetime.datetime(2026,9,27,1,2,tzinfo=datetime.timezone.utc).timestamp()
cap=int(end-time.time())
assert 600<cap<7200
assert not P(owner).exists() and not P(path).exists(),'existing_task_no_automatic_retry'
with transaction() as (lease,g):
 s.root_payload_guard()
 write_new(path,base64.b64decode(RAW),g)
 receipt={**PARAMS,'unit':unit,'script_path':path,'receipt_path':'/data/logs/flash-h008-20260926/H010-FLASH64K.json',
  'utc':now(),'job_cap_seconds':cap,'job_hardend_utc':'2026-09-27T01:02:00Z',
  'request_global_end_utc':'2026-09-27T00:58:00Z','warm_cap_seconds':1200,'measured_cap_seconds':4200,
  'lane_owner':'Worker1 H010 exclusive; explicit handoff may continue polling, never replay',
  'status':'OWNED_BEFORE_DISPATCH','no_model_lifecycle_action':True}
 status(owner,receipt,g)
 subprocess.run(['systemd-run','--unit='+unit,'--property=Type=exec','--property=RuntimeMaxSec='+str(cap),
  '--property=TimeoutStopSec=20','--property=KillMode=control-group','--property=Restart=no',
  '--property=StandardOutput=null','--property=StandardError=null','--property=UMask=0077',
  '/usr/bin/python3','-I','-B',path],check=True,capture_output=True,text=True)
 receipt['status']='DISPATCHED';receipt['dispatch_utc']=now()
 status(owner,receipt,g);s.root_payload_guard()
print(json.dumps(receipt))
'''
(TASK/'tools/dispatch-remote.py').write_text(remote)
r=subprocess.run(['ssh','-o','ConnectTimeout=5','-T','ai-vm','sudo -n python3 -I -B -'],input=remote.encode(),capture_output=True,timeout=120)
(TASK/'evidence/DISPATCH.stderr').write_bytes(r.stderr)
assert r.returncode==0,r.stderr.decode()[-1500:]
(TASK/'evidence/OWNER.json').write_bytes(r.stdout)
print(r.stdout.decode())
