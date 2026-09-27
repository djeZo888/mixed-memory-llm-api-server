#!/usr/bin/env python3
"""One exact-source GO dispatch after predecessor settlement; no replay."""
import datetime,hashlib,json,pathlib,subprocess
T=pathlib.Path(__file__).resolve().parents[4];S=T/'repo/scripts/h016/r9'
go=json.loads((T/'ROOT-R9-GO.json').read_text())
assert go['authorized'] is True and datetime.datetime.now(datetime.timezone.utc)<datetime.datetime.fromisoformat(go['expires_utc'])
import sys
sys.path.insert(0,str(S))
from candidate_owner import SOURCE_NAMES
assert set(go['source_sha256'])==SOURCE_NAMES
assert hashlib.sha256((T/'ROOT-WINNER.json').read_bytes()).hexdigest()==go['winner_sha256']
for n,d in go['source_sha256'].items():assert hashlib.sha256((S/n).read_bytes()).hexdigest()==d
assert not (T/'R9-DISPATCH-INTENT.json').exists(),'dispatch already attempted; inspect actual owner'
intent={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'status':'ONE_R9_DISPATCH_INTENT','go':go}
(T/'R9-DISPATCH-INTENT.json').write_text(json.dumps(intent,indent=2)+'\n')
code='''import datetime,hashlib,json,pathlib,sys
B=pathlib.Path('/data/build/H016-20260927/worker1-r9');go=PAYLOAD_AUTHORITY
assert datetime.datetime.now(datetime.timezone.utc)<datetime.datetime.fromisoformat(go['expires_utc'])
assert go['authorized'] is True
assert hashlib.sha256((B/'ROOT-WINNER.json').read_bytes()).hexdigest()==go['winner_sha256']
for n,d in go['source_sha256'].items():assert hashlib.sha256((B/n).read_bytes()).hexdigest()==d
sys.path.insert(0,str(B))
from launch_r9 import main
main(run=True)
'''.replace('PAYLOAD_AUTHORITY',repr(go))
r=subprocess.run(['ssh','ai-vm','sudo -n python3 -B -'],input=code,text=True,capture_output=True,timeout=60)
(T/'private/finalprep11/R9-DISPATCH.stderr').write_text(r.stderr)
(T/'private/finalprep11/R9-DISPATCH.stdout').write_text(r.stdout)
if r.returncode:raise RuntimeError('R9 launcher failed; inspect actual state; no replay: '+r.stderr[-1500:])
out=json.loads(r.stdout);(T/'private/finalprep11/R9-INITIAL-LAUNCH.json').write_text(json.dumps(out,indent=2)+'\n')
notice={k:out[k] for k in ['utc','status','unit','unit_readback','admission_end_utc','settlement_utc','global_end_utc']}
(T/'R9-DISPATCH.json').write_text(json.dumps(notice,indent=2)+'\n')
with (T/'ROOT-NOTICE.md').open('a') as f:f.write('\n## R9 SYSTEMD DISPATCH\n'+json.dumps(notice,indent=2)+'\n')
print(json.dumps(notice))
