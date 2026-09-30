"""Stage exact reviewed source, reuse verified builds, retain private rollback."""
from common import *
import shutil, tarfile

assert not (TASK/'prepared.json').exists(), 'preparation already recorded'
storage=guard()
assert sha(TASK/'ENGINE-RECEIPT.json')==RECEIPT_SHA
gate=json.loads((TASK/'ENGINE-RECEIPT.json').read_text())
assert gate['windowReleased'] and gate['status']=='COMPLETE_PRIVATE_BUILD_OFFLINE_PROBES_PASS'
assert gate['runtime']['nativeSourceRevision']==NATIVE and gate['runtime']['patchSetSha256']==PATCHSET
new_image=candidate();old_image=image(TAG);assert old_image['Id']==OLD_ID
before=service(); assert before['ActiveState']=='active' and before['MainPID']=='33683'
before_state=idle()
manifests=json.loads((TASK/'source-manifests.json').read_text())
assert manifests['old']['commit']==OLD_HEAD and manifests['new']['commit']==HEAD
assert manifests['old']['trees']==manifests['new']['trees']
verify_source(OLD,manifests['old'])
built_path=TASK.parent/'H003-DEPLOY-20260923/built-files.json'
assert sha(built_path)=='adbec40e21249988d8a53cd832fbb958b25b637f30ef52b0a363a5187288a6f3'
built=json.loads(built_path.read_text());assert len(built)==39
assert all(sha(OLD/n)==h for n,h in built.items())
assert not NEW.exists(), 'refuse existing destination'
NEW.mkdir(mode=0o700)
with tarfile.open(TASK/'reviewed-harness-source.tar') as tf:
    assert all(m.name.startswith('ai-harness/') or m.name=='ai-harness' for m in tf.getmembers())
    tf.extractall(NEW,filter='data')
verify_source(NEW,manifests['new'])
copied={}
for component in ['server','web']:
    for kind in ['dist','node_modules']:
        rel='ai-harness/'+component+'/'+kind
        if not (OLD/rel).exists(): continue
        copy(OLD/rel,NEW/rel)
        old_tree=tree(OLD/rel);new_tree=tree(NEW/rel)
        assert old_tree==new_tree, 'copied build/dependency mismatch: '+rel
        copied[rel]={'entries':len(old_tree),'treeSha256':hash_json(old_tree),'byteModeSymlinkEquality':True}
assert all(sha(NEW/n)==h for n,h in built.items())
write(NEW/'SOURCE-IDENTITY.json',{'commit':HEAD,'filesVerified':224,'sourceArchiveSha256':sha(TASK/'reviewed-harness-source.tar'),'serverWebBuildsReusedFrom':OLD_HEAD,'compiledFilesVerified':39,'noBuild':True})
staged_unit=UNIT.read_text().replace(str(OLD),str(NEW))
assert staged_unit!=UNIT.read_text() and str(OLD) not in staged_unit
unit_path=TASK/'ai-harness.service';unit_path.write_text(staged_unit);unit_path.chmod(0o600)
run(['systemd-analyze','--user','verify',str(unit_path)])
stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
backup=TASK/('rollback-'+stamp);backup.mkdir(mode=0o700)
db_backup=snapshot_db(backup/'harness.sqlite')
copy(OLD,backup/'prior-release');copy(CONFIG,backup/'config');copy(UNIT,backup/'ai-harness.service')
write(backup/'engine-identity.json',old_image)
# Every data directory is retained, including logs and prior evidence. Runtime
# ownership SQLite files are deliberately excluded; application DB uses backup API.
for p in sorted(DATA.iterdir()):
    if p.name.startswith(('harness.sqlite','owner.sqlite')): continue
    copy(p,backup/p.name)
keys=key_metadata()
nginx=service(system=True)
site=pathlib.Path('/etc/nginx/sites-available/ai-harness.conf')
site_sha=sha(site)
proxy_stat=run(['sudo','-n','stat','-c','%d:%i:%u:%g:%a:%s:%Y:%Z','/etc/ai-harness/image-approval-proxy.conf'])
assert service()==before and image(TAG)['Id']==OLD_ID
receipt={'preparedAtUtc':utc(),'storage':storage,'sourceCommit':HEAD,'priorRelease':str(OLD),'releasePath':str(NEW),'sourceFilesVerified':224,'priorSourceFilesVerified':217,'sourceTrees':manifests['new']['trees'],'serverWebUnchanged':True,'buildsReused':copied,'compiledFilesVerified':39,'compiledManifestSha256':sha(built_path),'sourceManifestSha256':sha(TASK/'source-manifests.json'),'sourceArchiveSha256':sha(TASK/'reviewed-harness-source.tar'),'beforeService':before,'beforeNginx':nginx,'beforeState':before_state,'beforeHealth80':health(),'priorEngine':old_image,'candidateEngine':new_image,'backupPath':str(backup),'initialDatabaseBackup':db_backup,'unitBeforeSha256':sha(UNIT),'unitStagedSha256':sha(unit_path),'launcherBeforeSha256':sha(OLD/'ai-harness/deploy/run-engine.sh'),'launcherAfterSha256':sha(NEW/'ai-harness/deploy/run-engine.sh'),'credentialMetadata':keys,'nginxSiteSha256':site_sha,'approvalProxyStatIdentity':proxy_stat,'guardAfter':guard(),'activated':False}
write(TASK/'prepared.json',receipt)
print(json.dumps({k:receipt[k] for k in ['preparedAtUtc','sourceCommit','sourceFilesVerified','compiledFilesVerified','backupPath','launcherBeforeSha256','launcherAfterSha256','activated']},indent=2))
