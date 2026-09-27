#!/usr/bin/env python3
"""One H013 reviewed warm or matched main dispatch. No default inference.
Requires task ROOT-GO.json with exact package hash, mode and fresh UTC expiry.
Use --dry-run for local assembly only. Remote job persists independently.
"""
from pathlib import Path
import argparse,ast,base64,hashlib,json,subprocess,datetime
HERE=Path(__file__).resolve().parent;TASK=HERE.parents[3]
FILES=('vm-common.py','fan-readings.py','job-body.py','warm-tail.py','dispatch.py','settle-body.py','prepare.py','preflight-body.py')
def digest(raw):return hashlib.sha256(raw).hexdigest()
def package_hash():return digest(json.dumps({n:digest((HERE/n).read_bytes()) for n in FILES},sort_keys=True).encode())
def require_full_preflight(report):
 assert report['status']=='FULL_PREFLIGHT_PASS','image_recovery_and_full_preflight_required'
def main():
 a=argparse.ArgumentParser(description=__doc__);a.add_argument('--mode',choices=['warm','main'],required=True);a.add_argument('--dry-run',action='store_true');args=a.parse_args()
 report=json.loads((TASK/'private/PREFLIGHT.json').read_text());require_full_preflight(report)
 params=report['parameters'];params['query_fields']=report['query_fields'];params['preflight_only']=False;params['review_package_sha256']=package_hash()
 assert set(params['containers'])=={'flash','qwen0','qwen1','image'}
 for file,expected in [('FIXTURES03.json','135f2bbbea8deda81576feb667fbbd2411810a04150da9a76e6f0b730b467dec'),('H011-FOURWAY03-telemetry.jsonl','410c2bb545f9859469750455356b8a349c67a8902ec18b3cb275fd8f3660b4f3')]:assert digest((TASK/'private'/file).read_bytes())==expected
 common=(HERE/'vm-common.py').read_text();fans=(HERE/'fan-readings.py').read_text();body=(HERE/'job-body.py').read_text()
 prefix='H013-FOURWAY01' if args.mode=='main' else 'H013-WARM02';unit=prefix.lower();duration=900 if args.mode=='main' else 1100
 fixtures=(TASK/'private/FIXTURES03.json').read_bytes() if args.mode=='main' else (TASK/'private/H011-WARM03-warm8192-FIXTURE.jsonl').read_bytes()
 if args.mode=='warm':
  params['warm_fixture_sha256']=digest(fixtures)
  tree=ast.parse(body);tree.body=[n for n in tree.body if not (isinstance(n,ast.If) and isinstance(n.test,ast.Compare) and isinstance(n.test.left,ast.Name) and n.test.left.id=='__name__')]
  body=ast.unparse(tree)
  # Only warm request; main body remains byte-identical to reviewed job-body.py.
  body=body.replace('timeout=540','timeout=900').replace('threading.Timer(540,','threading.Timer(900,')+'\n'+(HERE/'warm-tail.py').read_text()
 full=common+'\nPARAMETERS='+repr(params)+'\n'+fans+'\n'+body;compile(full,'h013-owned-job','exec')
 paths={prefix+'-job.py':full.encode(),prefix+('-FIXTURES.json' if args.mode=='main' else '-FIXTURE.jsonl'):fixtures}
 paths[prefix+'-settle.py']=(common+'\nPARAMETERS='+repr(params)+'\nPREFIX='+repr(prefix)+'\n'+(HERE/'settle-body.py').read_text()).encode()
 hashes={name:digest(raw) for name,raw in paths.items()};(TASK/'private'/ (prefix+'-job.py')).write_text(full)
 print(json.dumps({'mode':args.mode,'package_sha256':package_hash(),'files':hashes,'job_seconds':duration,'dry_run':args.dry_run}),flush=True)
 if args.dry_run:return
 go=json.loads((TASK/'ROOT-GO.json').read_text());assert go['review_package_sha256']==package_hash() and args.mode in go['modes'],'exact_root_source_GO_required'
 assert datetime.datetime.now(datetime.timezone.utc)<datetime.datetime.fromisoformat(go['expires_utc']),'root_GO_expired'
 assert go.get('quiet_confirmed') is True and go.get('quiet_evidence'),'root_quiet_handoff_required'
 params['root_GO_sha256']=digest((TASK/'ROOT-GO.json').read_bytes())
 # Root GO is persisted in the owner; job embeds the exact reviewed package and identities.
 # Stage exclusive owned files under current guard. Existing owner is never replayed.
 remote=common+'\nPARAMS='+repr(params)+'\nFILES='+repr({n:base64.b64encode(raw).decode() for n,raw in paths.items()})+'\nPREFIX='+repr(prefix)+'\nUNIT='+repr(unit)+'\nDURATION='+repr(duration)+'\nHASHES='+repr(hashes)+r'''
import base64
log='/data/logs/flash-h008-20260926';owner=log+'/'+PREFIX+'-OWNER.json'
assert P('/proc/sys/kernel/random/boot_id').read_text().strip()==PARAMS['boot']
assert not P(owner).exists(),'existing_owner_no_replay'
for path,h in PARAMS['source_matches'].items():assert hashlib.sha256(P(path).read_bytes()).hexdigest()==h,'source_changed:'+path
with transaction() as (_,g):
 s.root_payload_guard();g.check_path(log)
 for name,raw in FILES.items():write_new(log+'/'+name,base64.b64decode(raw),g)
 receipt={**PARAMS,'utc':now(),'status':'OWNED_BEFORE_DISPATCH','unit':UNIT,'files':HASHES,'request_cap_seconds':540 if DURATION==900 else 900,'job_cap_seconds':DURATION,'submission_window_seconds':300 if DURATION==900 else 1100,'automatic_retry':False}
 status(owner,receipt,g)
 p=subprocess.run(['systemd-run','--unit='+UNIT,'--property=Type=exec','--property=RuntimeMaxSec='+str(DURATION),'--property=TimeoutStopSec=20','--property=KillMode=control-group','--property=Restart=no','--property=StandardOutput=null','--property=StandardError=null','--property=UMask=0077','/usr/bin/python3','-I','-B',log+'/'+PREFIX+'-job.py'],capture_output=True,text=True,timeout=15)
 assert p.returncode==0,'systemd_dispatch_failed_no_replay'
 receipt.update(status='DISPATCHED',dispatch_utc=now());status(owner,receipt,g);s.root_payload_guard()
print(json.dumps(receipt))
'''
 (TASK/'private'/('dispatch-'+args.mode+'-remote.py')).write_text(remote)
 r=subprocess.run(['ssh','-o','ConnectTimeout=5','-T','ai-vm','sudo -n python3 -I -B -'],input=remote.encode(),capture_output=True,timeout=120)
 (TASK/'private'/('dispatch-'+args.mode+'.stderr')).write_bytes(r.stderr);(TASK/'private'/('dispatch-'+args.mode+'.json')).write_bytes(r.stdout)
 assert r.returncode==0,'dispatch_failed_or_uncertain_inspect_receipts_no_replay'
 print('DISPATCHED: capture short start proof; do not poll through owned inference')
if __name__=='__main__':main()
