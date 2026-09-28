#!/usr/bin/env python3
"""H019 ordinary app pause. Reuse inert H010 state helpers; no owner DB reads."""
import datetime, hashlib, importlib.util, json, os, pathlib, stat, subprocess

os.umask(0o077)
T = pathlib.Path('/home/user/ai-harness-build/H019-HARNESS-PREP01-20260928')
T.mkdir(mode=0o700, exist_ok=True)
(T/'private').mkdir(mode=0o700, exist_ok=True)
assert not (T/'private/BEFORE.json').exists(), 'retain prior attempt; inspect before retry'
helper = pathlib.Path('/home/user/ai-harness-build/H010-WORKER2-20260927/recover-harness-02.py')
sha = lambda p: hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
assert sha(helper) == '6851fb4639c6ba00040e707cf921442f6870e5bd59c7b9e159017d2ec1d82dee'
spec = importlib.util.spec_from_file_location('prior', helper)
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
baseline_path = pathlib.Path('/home/user/ai-harness-build/H018-HARNESS-PREP01-20260928/AFTER.json')
baseline = json.loads(baseline_path.read_text())
recovery_path = pathlib.Path('/home/user/ai-harness-build/H018-ORIGINAL-RECOVERY07-20260928/RECOVERY.json')
recovery = json.loads(recovery_path.read_text())
cutoff_ns = int(datetime.datetime.fromisoformat(recovery['finishedUtc']).timestamp()*1e9)

def metadata():
    expected = baseline['metadata']
    files = {p:sha(p) for p in expected['fileSha256']}
    assert files == expected['fileSha256'], 'installed metadata differs; preserve and review'
    image = m.run('podman','image','inspect',expected['imageTag'],'--format','{{.Id}}')
    assert image.removeprefix('sha256:') == expected['imageId'].removeprefix('sha256:')
    credentials = {}
    for name, old in expected['credentials'].items():
        p = pathlib.Path(name) if name.startswith('/') else pathlib.Path('/home/user/.config/ai-harness')/name
        s = p.lstat()
        assert stat.S_ISREG(s.st_mode)
        current = {'uid':s.st_uid,'gid':s.st_gid,'mode':oct(stat.S_IMODE(s.st_mode)),
                   'size':s.st_size,'inode':s.st_ino,'contentsRead':False}
        assert current == old, 'credential metadata differs; no content read'
        credentials[name] = current
    parents = {}
    for name, old in expected['parents'].items():
        s = pathlib.Path(name).lstat()
        current = {'uid':s.st_uid,'gid':s.st_gid,'mode':oct(stat.S_IMODE(s.st_mode)),'inode':s.st_ino}
        assert stat.S_ISDIR(s.st_mode) and current == old
        parents[name] = current
    return {'fileSha256':files,'imageTag':expected['imageTag'],'imageId':image,
            'credentials':credentials,'parents':parents}

def files_metadata():
    # Same scope as H010 inventory, but reuse the prior full content digest.
    # Capture actual metadata and hash only files changed since that completed pass.
    rows=[]; changed=[]; excluded=0
    for p in sorted(m.ROOT.rglob('*')):
        if p.is_symlink() or not p.is_file(): continue
        if p.name.endswith(('.sqlite','.sqlite-wal','.sqlite-shm','.sqlite-journal')):
            excluded+=1;continue
        s=p.stat(); rel=str(p.relative_to(m.ROOT))
        rows.append([rel,s.st_size,s.st_mtime_ns,s.st_ctime_ns,s.st_ino,stat.S_IMODE(s.st_mode)])
        if max(s.st_mtime_ns,s.st_ctime_ns)>cutoff_ns:
            changed.append({'path':rel,'size':s.st_size,'sha256':sha(p),'mtimeNs':s.st_mtime_ns,'ctimeNs':s.st_ctime_ns})
    return {'rows':rows,'changedSinceFullPass':changed,'excludedDatabaseAndTransientFiles':excluded}

def snapshot():
    s=m.summary();m.require_idle(s)
    return {'utc':m.now(),'units':m.units(),'containers':m.container_summary(),
            'data':json.loads(json.dumps(s)),'files':files_metadata(),'metadata':metadata()}

before=snapshot()
assert before['units']['ai-harness.service']['WorkingDirectory'] == '/opt/ai-harness/releases/7143c17d73173db9364b77956679c86d7026a4ae/ai-harness/server'
assert before['units']['ai-harness.service']['ActiveState'] == 'active'
(T/'private/BEFORE.json').write_text(json.dumps(before,indent=2)+'\n')
# Recheck request ownership immediately before ordinary stop; no model call.
m.require_idle(m.summary())
stop_utc=m.now()
subprocess.run(['systemctl','--user','stop','ai-harness.service'],check=True,timeout=90)
returned_utc=m.now()
after=snapshot()
(T/'private/AFTER.json').write_text(json.dumps(after,indent=2)+'\n')
app=after['units']['ai-harness.service']
assert app['MainPID']=='0' and app['ActiveState']=='inactive'
protected=['sessions','messages','files','runs','events','quarantined_workspaces','h003_image_jobs','h005_image_ownership','frontier_requests']
preserved={k:before['data'][k]==after['data'][k] for k in protected}
historical={k:after['data'][k]==recovery['afterData'][k] for k in protected}
same_files=before['files']['rows']==after['files']['rows'] and before['files']['changedSinceFullPass']==after['files']['changedSinceFullPass']
other={k:before['units'][k]==after['units'][k] for k in before['units'] if k!='ai-harness.service'}
assert all(preserved.values()) and same_files and all(other.values())
r={'status':'QUIET_ORIGINAL_APP_PAUSED','utc':after['utc'],'stopCommandUtc':stop_utc,'stopReturnedUtc':returned_utc,
   'app':app,'otherServices':{k:v for k,v in after['units'].items() if k!='ai-harness.service'},
   'runningContainers':after['containers'],'ownedEngineContainers':0,'activeOwnedRuns':0,
   'activeFrontierRequests':0,'activeImageJobs':0,'uncertainImageJobs':0,
   'data':after['data'],'historyPreservedAcrossPause':preserved,'historyMatchesRecoveredBaseline':historical,
   'changedTablesAcrossPause':[k for k in before['data'] if before['data'][k]!=after['data'][k]],
   'regularFiles':{'count':len(after['files']['rows']),'priorFullSha256':recovery['afterFiles']['sha256'],
     'priorFullPassFinishedUtc':recovery['finishedUtc'],'priorFullCount':recovery['afterFiles']['regular_non_database_files'],
     'metadataRowsSha256':m.sha(m.serialized(after['files']['rows'])),
     'changedSinceFullPassCount':len(after['files']['changedSinceFullPass']),
     'targetedHashesOnly':True,'fullRehashPerformed':False,'metadataPreservedAcrossPause':same_files},
   'metadataPreserved':before['metadata']==after['metadata'],'otherServicesPreserved':all(other.values()),
   'pair':{'release':'7143c17d73173db9364b77956679c86d7026a4ae','image':after['metadata']['imageId']},
   'privateReceiptRoot':str(T/'private'),'privateBeforeSha256':sha(T/'private/BEFORE.json'),
   'privateAfterSha256':sha(T/'private/AFTER.json'),'historicalBaselineSha256':sha(baseline_path),
   'historicalRecoverySha256':sha(recovery_path),'helperSha256':sha(helper),
   'modelRequests':0,'ownerSqliteRead':False,'credentialsContentsRead':False,
   'aiVmContact':False,'atomicNativeGpuIdleClaim':False,'backendSettlement':'W1-owned; not observed here',
   'rollback':'No automatic GLM rollback; keep Sova paused until reviewed deployment in fresh session'}
(T/'QUIET.json').write_text(json.dumps(r,indent=2)+'\n')
print(json.dumps({'status':r['status'],'utc':r['utc'],'counts':{k:v['count'] for k,v in after['data'].items()},
                  'historyPreserved':all(preserved.values()),'historicalMatch':all(historical.values()),'regularFiles':r['regularFiles']}))
