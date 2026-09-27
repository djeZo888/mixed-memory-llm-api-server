"""Exact H011 task dispatch; refuses prior owner. Run from isolated repo."""
from pathlib import Path
import json,hashlib,subprocess,base64,datetime
HERE=Path(__file__).resolve().parent;TASK=Path.cwd().parent
contract=(TASK/'ROOT-CONTRACT.md').read_text();assert 'Actual quiet handoff' in contract and 'inference GO' in contract
assert 'Root explicit corrected-pass GO' in contract
settled=json.loads((TASK/'evidence/NATIVE-SETTLED.json').read_text())
assert settled['all_native_settled'] is True, 'native_settlement_required'
quiet=json.loads((TASK/'HARNESS-QUIET-01.json').read_text());assert quiet['after_units']['ai-harness.service']['ActiveState']=='inactive'
baseline=json.loads((TASK/'evidence/LIVE-BASELINE.json').read_text())
lanes=['qwen0','qwen1','image','flash']
params={'base':'5328a771596db54bee8b28e5f33b99892b3f5b7e','session_id':json.loads((TASK/'PROGRESS.json').read_text())['session_id'],'boot':baseline['boot_id'],'source_matches':json.loads((TASK/'evidence/PREFLIGHT.json').read_text())['source_matches'],'containers':{lane:{'Id':v['id'],'Image':v['image'],'StartedAt':v['state']['StartedAt']} for lane,v in zip(lanes,baseline['containers'])},'capacities':{lane:baseline['native'][str(port)]['capacity'] for lane,port in [('flash',30010),('qwen0',30002),('qwen1',30004)]},'quiet_sha256':hashlib.sha256((TASK/'HARNESS-QUIET-01.json').read_bytes()).hexdigest(),'root_contract_sha256':hashlib.sha256(contract.encode()).hexdigest()}
common=(HERE/'vm-common.py').read_text()
full=common+'\nPARAMETERS='+repr(params)+'\n'+(HERE/'job-body.py').read_text();compile(full,'h011-job.py','exec')
(TASK/'tools/h011-job.py').write_text(full)
fixtures=(TASK/'evidence/FIXTURES02.json').read_bytes()
files={'H011-FOURWAY02-job.py':full.encode(),'H011-FOURWAY02-FIXTURES.json':fixtures}
params['staged_hashes']={n:hashlib.sha256(b).hexdigest() for n,b in files.items()}
remote=common+'\nFILES='+repr({n:base64.b64encode(b).decode() for n,b in files.items()})+'\nPARAMS='+repr(params)+r'''
import base64
log='/data/logs/flash-h008-20260926';unit='h011-fourway02';owner=log+'/H011-FOURWAY02-OWNER.json'
assert not P(owner).exists(),'existing_owner_no_replay'
assert time.time()<datetime.datetime(2026,9,27,1,25,tzinfo=datetime.timezone.utc).timestamp(),'too_late_to_dispatch'
with transaction() as (_,g):
 s.root_payload_guard()
 for n,raw in FILES.items():write_new(log+'/'+n,base64.b64decode(raw),g)
 receipt={**PARAMS,'utc':now(),'status':'OWNED_BEFORE_DISPATCH','unit':unit,'request_cap_seconds':900,'job_cap_seconds':1200,'submission_window_seconds':300,'automatic_retry':False,'count_caps':{'flash':1,'qwen0':12,'qwen1':12,'image':8}}
 status(owner,receipt,g)
 p=subprocess.run(['systemd-run','--unit='+unit,'--property=Type=exec','--property=RuntimeMaxSec=1200','--property=TimeoutStopSec=20','--property=KillMode=control-group','--property=Restart=no','--property=StandardOutput=null','--property=StandardError=null','--property=UMask=0077','/usr/bin/python3','-I','-B',log+'/H011-FOURWAY02-job.py'],capture_output=True,text=True)
 assert p.returncode==0,p.stderr
 receipt.update(status='DISPATCHED',dispatch_utc=now());status(owner,receipt,g);s.root_payload_guard()
print(json.dumps(receipt))
'''
(TASK/'tools/dispatch-remote.py').write_text(remote)
r=subprocess.run(['ssh','-o','ConnectTimeout=5','-T','ai-vm','sudo -n python3 -I -B -'],input=remote.encode(),capture_output=True,timeout=120)
(TASK/'evidence/DISPATCH.stderr').write_bytes(r.stderr)
assert r.returncode==0,r.stderr.decode()[-1200:]
(TASK/'evidence/OWNER02.json').write_bytes(r.stdout)
x=json.loads(r.stdout);print({k:x[k] for k in ['unit','status','dispatch_utc','staged_hashes','count_caps']})
