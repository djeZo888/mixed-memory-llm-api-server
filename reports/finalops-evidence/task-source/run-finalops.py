#!/usr/bin/env python3
"""Task-local reuse of HOSTRECOVER's bounded SSH dispatcher; no nested Codex."""
import argparse, hashlib, json, os, subprocess, sys
from pathlib import Path
from datetime import datetime, timezone

root=Path(__file__).resolve().parent
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('phase',choices=('reboot','postboot','cleanup_dry_run','cleanup_reconcile','cleanup_reference_review','cleanup_apply','cleanup_apply_diagnose'))
args=parser.parse_args()
incoming=(root/'incoming.md').read_text()
assert '## FINAL ACCEPTED IDLE RELEASE — EXECUTE REBOOT NOW' in incoming, 'final_idle_release_missing'
P=json.loads((root/'ready-release.json').read_text())
F={'idle_release':True,'models_accepted':True,'generation':5,
   'active_identity':'3bb1b45a90e290657f4396ab8f601a24e4f9570d14d338e5cfc094ac61e8c007',
   'container_id':'5ba104b9bcdb5c126df3d24ba1d63a987f5c72376047d12a0de7e9a7c6812ba9'}
assert F['active_identity'] in incoming and F['container_id'] in incoming, 'handoff_identity_missing'
CFG={'registered_host':{}}
for key,relative,mode in [('guard','scripts/common/registered-storage.py','0755'),('dependency','scripts/install/storage.py','0644')]:
    CFG['registered_host'][key]={'path':'/usr/local/lib/llm-server/control-api/'+relative,
        'sha256':hashlib.sha256((root/'repo'/relative).read_bytes()).hexdigest(),'expected_mode':mode}
code='P='+repr(P)+'\nF='+repr(F)+'\nCFG='+repr(CFG)+'\n'
code+=(root/'finalops-common.py').read_text()+'\n'
code+='''
guard_identity()
manifest_path=protected('/usr/local/lib/llm-server/control-api.manifest.json')
assert hashlib.sha256(manifest_path.read_bytes()).hexdigest()==P['source_manifest_sha256'], 'bootstrap_source_manifest'
manifest=json.loads(manifest_path.read_bytes())
assert manifest['source_commit']==P['source_commit'], 'bootstrap_source_commit'
for relative,row in manifest['files'].items():
    path=protected(SRC/relative)
    assert hashlib.sha256(path.read_bytes()).hexdigest()==row['sha256'], 'bootstrap_source_file'
    assert stat.S_IMODE(path.stat().st_mode)==int(row['mode'],8), 'bootstrap_source_mode'
sys.path.insert(0,str(SRC/'scripts'))
'''
code+=(root/'finalops-boot.py').read_text()+'\n'
if args.phase in ('cleanup_dry_run','cleanup_reconcile','cleanup_reference_review','cleanup_apply','cleanup_apply_diagnose'):
    maintenance=json.loads((root/'maintenance-release.json').read_text())
    assert maintenance.get('root_explicit_release') is True and maintenance.get('incoming_sha256')==hashlib.sha256(incoming.encode()).hexdigest(), 'fresh_post_demo_maintenance_release_required'
    release=json.loads((root/'cleanup-lan-release.json').read_text())
    assert release.get('worker2_lan_pass') is True and release.get('request_ownership_released') is True, 'postboot_lan_release_missing'
    code+='CLEANUP_IDLE_RELEASE=True\n'
    helper=(root/'c1_scoped_cleanup.py').read_text()
    assert hashlib.sha256(helper.encode()).hexdigest()=='c0270cda697ec29bdb71cd1e23e92a4e646bc610dc14e2715537158df353438e', 'root_reviewed_helper_source_drift'
    code+='C1_CODE='+repr(helper)+'\n'
    code+=(root/'finalops-cleanup.py').read_text()+'\n'
    if args.phase in ('cleanup_apply','cleanup_apply_diagnose'):
        assert '## ROOT APPLY APPROVAL — ACT NOW' in incoming, 'root_exact_apply_approval_missing'
        reviewed=json.loads((root/'corrected-dry-run-review.json').read_text())
        code+='ROOT_APPLY_APPROVED=True\nAPPROVED_SNAPSHOTS='+repr({r['root']:r['snapshot'] for r in reviewed['targets']})+'\n'
        code+=(root/'finalops-apply.py').read_text()+'\n'
code+='''
try:
    PHASE_FUNCTION()
except Exception as error:
    emit('FINALOPS_BLOCKED',error_type=type(error).__name__,reason=str(error) if isinstance(error,AssertionError) else 'operation_failed_private_stderr',healthy_backend_stop_attempted=False)
    raise
'''.replace('PHASE_FUNCTION()',args.phase+'()')
compile(code,'finalops-'+args.phase,'exec')
sys.path.insert(0,str(root/'repo/scripts'))
from d3t.probe import lock
stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
private=root/('worker-private-'+args.phase+'-'+stamp)
os.umask(0o077);private.mkdir(mode=0o700)
(private/'executed-source.py').write_text(code)
with lock(root.parent/'D3BASE-20260915/trial/run','request.lock'):
    with (private/'stderr').open('xb') as err,(private/'stdout').open('xb') as out:
        proc=subprocess.Popen(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','ai-vm','sudo -n /usr/bin/python3 -I -B -'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=err)
        proc.stdin.write(code.encode());proc.stdin.close()
        for line in proc.stdout:
            out.write(line);out.flush()
            try:row=json.loads(line)
            except Exception:continue
            print(json.dumps(row,sort_keys=True),flush=True)
            with (root/'live-status.md').open('a') as f:f.write('\n```json\n'+json.dumps(row,indent=2)+'\n```\n')
            (root/(args.phase+'-latest.json')).write_text(json.dumps(row,indent=2)+'\n')
        rc=proc.wait()
        print(json.dumps({'phase':'TRANSPORT_TERMINAL','operation':args.phase,'returncode':rc,'private_capture':str(private)}),flush=True)
        sys.exit(rc)
