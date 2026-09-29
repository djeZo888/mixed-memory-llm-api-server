"""One ordinary owner start, only after exact source reconciliation and renewed gap."""
import datetime,hashlib,importlib.util,json,pathlib,subprocess,sys
P=pathlib.Path;B=P('/data/services/mimo-h016-20260927');S=P('/data/backups/H030-SPECIAL01-stage')
p=json.loads((S/'MIMO-DEPLOY-PROPOSAL.json').read_bytes())
assert datetime.datetime.now(datetime.timezone.utc)<datetime.datetime(2026,9,29,7,43,tzinfo=datetime.timezone.utc)
assert hashlib.sha256((B/'source/owner.py').read_bytes()).hexdigest()==p['ownerSha256']
spec=importlib.util.spec_from_file_location('mimo_owner',B/'source/owner.py');o=importlib.util.module_from_spec(spec);spec.loader.exec_module(o)
m=o.read(B/'manifest.json');previous=o.read(B/'state.json');selected=o.require_selected(m)
assert o.digest(m)==p['newManifestCanonicalSha256']
assert hashlib.sha256((B/'state.json').read_bytes()).hexdigest()==p['predecessorHashes']['state.json']
h=o.setup();o.source_preflight(h,m)
recovery,old=o.settled_source_for_start(m,selected,previous);o.assert_launch_admission(m,selected,previous,recovery)
o.settled_source_absence(old,previous,'992bf979-efae-495b-9ab2-26e75ed5c5d0')
r=subprocess.run(['systemctl','start','--no-block',o.UNIT],capture_output=True,text=True,timeout=10)
print(json.dumps({'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'action':'one normal systemctl start --no-block','unit':o.UNIT,'rc':r.returncode,'stdout':r.stdout,'stderr':r.stderr,'manifestSha256':o.digest(m),'recoverySha256':o.digest(recovery),'inferenceSubmitted':0}))
raise SystemExit(r.returncode)
