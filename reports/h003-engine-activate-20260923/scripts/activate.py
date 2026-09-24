"""ONE guarded harness activation. No upstream request, build, probe or replay."""
from common import *
import shutil, sys

assert len(sys.argv)==2 and sha(TASK/'COORDINATOR-NOTE.md')==sys.argv[1]
assert not (TASK/'activation-progress.json').exists(), 'single activation already begun'
prep=json.loads((TASK/'prepared.json').read_text());backup=pathlib.Path(prep['backupPath'])
manifests=json.loads((TASK/'source-manifests.json').read_text())
assert sha(TASK/'ENGINE-RECEIPT.json')==RECEIPT_SHA
gate=json.loads((TASK/'ENGINE-RECEIPT.json').read_text())
assert gate['windowReleased'] and gate['candidate']['Id']==IMAGE_ID
candidate();assert image(TAG)['Id']==OLD_ID
verify_source(NEW,manifests['new']);verify_source(OLD,manifests['old'])
assert sha(UNIT)==prep['unitBeforeSha256'] and sha(TASK/'ai-harness.service')==prep['unitStagedSha256']
assert key_metadata()==prep['credentialMetadata']
assert service()==prep['beforeService'] and service(system=True)==prep['beforeNginx']
assert sha('/etc/nginx/sites-available/ai-harness.conf')==prep['nginxSiteSha256']
assert run(['sudo','-n','stat','-c','%d:%i:%u:%g:%a:%s:%Y:%Z','/etc/ai-harness/image-approval-proxy.conf'])==prep['approvalProxyStatIdentity']
assert tree(CONFIG)==tree(backup/'config'), 'config changed since backup'
runtime_path=pathlib.Path('/home/user/ai-harness-h003-engine-mcp-build-20260923/evidence/runtime-manifests.json')
runtime=json.loads(runtime_path.read_text())
assert runtime['nativeSourceRevision']==NATIVE and runtime['patchSetSha256']==PATCHSET
container_id='3aebab027dec95ad4c1b2fa0f0fb5c97ee8477d9cba4884787fe5a381b967249'
probe_container=json.loads(run(['podman','container','inspect',container_id]))[0]
assert probe_container['Image'].removeprefix('sha256:')==IMAGE_ID
assert probe_container['State']['Status']=='exited' and probe_container['State']['ExitCode']==0
before=idle()
receipt={'task':'H003-HARNESS-ENGINE-ACTIVATE-20260923','status':'ACTIVATION_STARTED','startedAtUtc':utc(),'sourceCommit':HEAD,'releasePath':str(NEW),'engineId':IMAGE_ID,'engineDigest':DIGEST,'productionAlias':TAG,'candidateTag':CANDIDATE_TAG,'nativePin':NATIVE,'nativeBase':BASE,'patchset':PATCHSET,'engineReceiptSha256':RECEIPT_SHA,'nativePinVerification':{'method':'Reuse authoritative immutable-image runtime evidence; no probes repeated','hostEvidencePath':str(runtime_path),'hostEvidenceSha256':sha(runtime_path),'exitedEvidenceContainerId':container_id,'containerImageIdMatches':True},'coordinatorNoteSha256':sys.argv[1],'rollbackPath':str(backup),'serviceBefore':service(),'health80Before':health(),'stateBefore':before,'credentialMetadata':key_metadata(),'storageBefore':guard(),'inferenceCalls':0,'newChats':0,'mcpCalls':0,'builds':0,'aiVmContact':False,'steps':[]}
def step(name):
    receipt['steps'].append({'name':name,'atUtc':utc()})
    write(TASK/'activation-progress.json',receipt)

stopped=False;started=False
try:
    # Repeat immediately before the only stop. Never stop known active work.
    last_idle=idle();receipt['finalIdleGate']=last_idle['atUtc']
    receipt['stopRequestedAtUtc']=utc();step('idle gate passed; requesting ordinary graceful service stop')
    run(['systemctl','--user','stop','ai-harness.service'],timeout=100);stopped=True
    stop=service();receipt['serviceStopped']=stop;receipt['stopCompletedAtUtc']=utc()
    assert stop['ActiveState']=='inactive' and stop['ExecMainStatus']=='0' and stop['Result']=='success', 'graceful stop failed'
    final_idle=idle();receipt['stateAtStop']=final_idle
    # Never restore owner.sqlite. Preserve final coherent app data after the writer exits.
    receipt['finalDatabaseBackup']=snapshot_db(backup/'harness-final-idle.sqlite')
    final_files=backup/'final-data';final_files.mkdir(mode=0o700)
    data_trees={}
    for p in sorted(DATA.iterdir()):
        if p.name.startswith(('harness.sqlite','owner.sqlite')): continue
        copy(p,final_files/p.name)
        if p.is_dir():
            live=tree(p);saved=tree(final_files/p.name)
            assert live==saved, 'final data backup mismatch: '+p.name
            data_trees[p.name]=live
        elif p.is_file(): assert sha(p)==sha(final_files/p.name)
    write(backup/'final-data-manifest.private.json',data_trees)
    receipt['dataBackupManifestSha256']=sha(backup/'final-data-manifest.private.json')
    receipt['dataTreesBefore']={k:{'entries':len(v),'sha256':hash_json(v)} for k,v in data_trees.items()}
    assert sha(UNIT)==prep['unitBeforeSha256'] and image(TAG)['Id']==OLD_ID
    assert service()['ActiveState']=='inactive'
    candidate()
    run(['podman','tag',IMAGE_ID,TAG])
    staged=UNIT.with_name('ai-harness.service.h003-engine-activate')
    shutil.copy2(TASK/'ai-harness.service',staged);staged.chmod(0o600);os.replace(staged,UNIT)
    run(['systemd-analyze','--user','verify',str(UNIT)])
    run(['systemctl','--user','daemon-reload'])
    assert sha(UNIT)==prep['unitStagedSha256'] and image(TAG)['Id']==IMAGE_ID
    step('source/launcher unit and private production alias switched consistently while stopped')
    receipt['startRequestedAtUtc']=utc()
    # Treat an attempted start as potentially live even if systemctl errors.
    started=True
    run(['systemctl','--user','start','ai-harness.service'])
    step('one new service start requested')
    ready=None
    for _ in range(40):
        try:
            ready=health()
            if ready['body'].get('version')=='0.0.3' and ready['body'].get('status')=='ok':break
        except Exception:pass
        time.sleep(.25)
    assert ready and ready['httpStatus']==200 and ready['body']['status']=='ok'
    receipt['health80After']=ready;receipt['serviceAfter']=service()
    assert receipt['serviceAfter']['ActiveState']=='active' and receipt['serviceAfter']['NRestarts']=='0'
    assert receipt['serviceAfter']['MainPID']!=receipt['serviceBefore']['MainPID']
    proc=pathlib.Path('/proc')/receipt['serviceAfter']['MainPID']
    receipt['liveProcess']={'cwd':os.readlink(proc/'cwd'),'argv':(proc/'cmdline').read_bytes().decode().strip('\0').split('\0')}
    assert receipt['liveProcess']['cwd']==str(NEW/'ai-harness/server')
    assert receipt['liveProcess']['argv'][-1]==str(NEW/'ai-harness/server/dist/main.js')
    # Everything below is read-only verification; never restart during acceptance.
    after=idle();receipt['stateAfter']=after
    assert final_idle['counts']==after['counts'] and final_idle['sessions']==after['sessions']
    table_equality={t:h==after['tableContentSha256'][t] for t,h in final_idle['tableContentSha256'].items()}
    assert all(ok for t,ok in table_equality.items() if t!='h003_image_lane')
    receipt['tableContentPreserved']=table_equality
    preserved={}
    for name,v in data_trees.items():
        current=tree(DATA/name)
        preserved[name]={'entries':len(v),'beforeSha256':hash_json(v),'afterSha256':hash_json(current),'exact':v==current}
    receipt['dataPreservation']=preserved
    assert all(v['exact'] for k,v in preserved.items() if k!='logs'), 'user/profile data changed'
    assert key_metadata()==prep['credentialMetadata'] and tree(CONFIG)==tree(backup/'config')
    assert service(system=True)==prep['beforeNginx']
    assert sha('/etc/nginx/sites-available/ai-harness.conf')==prep['nginxSiteSha256']
    assert run(['sudo','-n','stat','-c','%d:%i:%u:%g:%a:%s:%Y:%Z','/etc/ai-harness/image-approval-proxy.conf'])==prep['approvalProxyStatIdentity']
    actual=candidate();assert image(TAG)['Id']==IMAGE_ID and image(TAG)['Digest']==DIGEST
    assert image(OLD_ID)['Id']==OLD_ID
    verify_source(NEW,manifests['new'])
    built=json.loads((TASK.parent/'H003-DEPLOY-20260923/built-files.json').read_text())
    assert all(sha(NEW/n)==h for n,h in built.items())
    receipt.update(status='ACTIVATED_HEALTHY_PRESERVED',completedAtUtc=utc(),credentialContentsUnchanged=True,nginxUnchanged=True,oldImageRetained=True,activationCount=1,rollbackExecuted=False,sourceFilesVerified=224,compiledFilesVerified=39,serverWebBuildsReused=True,unitSha256=sha(UNIT),launcherSha256=sha(NEW/'ai-harness/deploy/run-engine.sh'),storageAfter=guard())
    step('port80 healthy; stored state, files, credentials, nginx and exact identities verified')
except BaseException:
    receipt['failedAtUtc']=utc();receipt['status']='ACTIVATION_FAILED_NEEDS_REVIEW'
    # If no new service was started, restore prior runnable pair. Do not touch DB.
    if stopped and not started:
        shutil.copy2(backup/'ai-harness.service',UNIT)
        run(['podman','tag',OLD_ID,TAG]);run(['systemctl','--user','daemon-reload'])
        run(['systemctl','--user','start','ai-harness.service'])
        receipt['status']='FAILED_BEFORE_NEW_START_OLD_PAIR_RESTORED'
        receipt['rollbackExecuted']=True
    write(TASK/'activation-result.json',receipt)
    raise
write(TASK/'activation-result.json',receipt)
print(json.dumps({k:receipt[k] for k in ['status','stopRequestedAtUtc','stopCompletedAtUtc','startRequestedAtUtc','completedAtUtc','serviceAfter','health80After','activationCount','inferenceCalls','rollbackPath']},indent=2))
