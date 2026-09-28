#!/usr/bin/env python3
"""Copy the retained H018 source and exact reviewed H019 helper overlay only."""
import datetime, hashlib, importlib.util, json, os, pathlib, shutil, sys

os.umask(0o077)
source=sys.argv[1]
assert len(source)==40 and all(c in '0123456789abcdef' for c in source)
old=pathlib.Path('/home/user/ai-harness-build/H018-HARNESS-PREP01-20260928')
task=pathlib.Path('/home/user/ai-harness-build/H019-HARNESS-PREP01-20260928')
overlay=task/'helper-overlay'
sha=lambda p:hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
old_manifest=old/'SOURCE.SHA256SUMS'
assert sha(old_manifest)=='ad0a8b847a3d477907085d157eef2dbdd7df084f4d0aacb067d05834eb57c60c'
assert (old/'SOURCE-COMMIT').read_text().strip()=='3760c615ec4c4785d1a3e5f5ca4781066782ad66'
clock=json.loads((old/'CLOCK-OVERLAY.json').read_text())
assert clock['clockOverlayCommit']=='5b6f9335b9e362e590f8c1541a1581dd70e332d3'
rows=[line.split('  ',1) for line in old_manifest.read_text().splitlines()]
assert len(rows)==479
reused={name:digest for digest,name in rows if name.startswith('source/')}
assert len(reused)==446
assert not (task/'source').exists(), 'keep prior stage; no overwrite/replay'
helper=pathlib.Path('/home/user/ai-harness-build/H010-WORKER2-20260927/recover-harness-02.py')
assert sha(helper)=='6851fb4639c6ba00040e707cf921442f6870e5bd59c7b9e159017d2ec1d82dee'
spec=importlib.util.spec_from_file_location('prior',helper)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
before=m.units()
assert before['ai-harness.service']['ActiveState']=='inactive' and before['ai-harness.service']['MainPID']=='0'
m.require_idle(m.summary())
# Source closure is only 3.6 MB. No compiled payload/model/workspace rehash.
for name,digest in reused.items(): assert sha(old/name)==digest, name
overlay_rows=[line.split('  ',1) for line in (overlay/'OVERLAY.SHA256SUMS').read_text().splitlines()]
for digest,name in overlay_rows:
    p=pathlib.PurePosixPath(name)
    assert not p.is_absolute() and '..' not in p.parts
    assert sha(overlay/name)==digest, name
shutil.copytree(old/'source',task/'source',copy_function=shutil.copy2)
for digest,name in overlay_rows:
    for dest in [task/name,task/'source/reports/h019-harness-prep01-20260928'/name]:
        dest.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        if dest.exists(): assert sha(dest)==digest, 'preserve existing stage entry'
        else: shutil.copy2(overlay/name,dest)
(task/'SOURCE-COMMIT').write_text(source+'\n')
files={name:sha(task/name) for name in reused}
for digest,name in overlay_rows:
    files[name]=digest
    files['source/reports/h019-harness-prep01-20260928/'+name]=digest
files['SOURCE-COMMIT']=sha(task/'SOURCE-COMMIT')
manifest=''.join(f'{digest}  {name}\n' for name,digest in sorted(files.items()))
(task/'SOURCE.SHA256SUMS').write_text(manifest)
for name,digest in files.items(): assert sha(task/name)==digest, name
assert m.units()==before
m.require_idle(m.summary())
record={'utc':m.now(),'status':'STAGED_PREPARATION_ONLY','sourceCommit':source,
    'sourceIdentity':'retained H018 source plus explicit H019 task/clock/context helper overlay',
    'retainedBaseSource':'3760c615ec4c4785d1a3e5f5ca4781066782ad66',
    'retainedClockOverlay':'5b6f9335b9e362e590f8c1541a1581dd70e332d3',
    'retainedStage':str(old),'retainedManifestSha256':sha(old_manifest),
    'retainedManifestEntries':479,'reusedSourceEntries':len(reused),
    'overlayEntries':len(overlay_rows),'overlayManifestSha256':sha(overlay/'OVERLAY.SHA256SUMS'),
    'stageRoot':str(task),'sourceManifestSha256':sha(task/'SOURCE.SHA256SUMS'),
    'sourceManifestEntries':len(files),'sourceBytes':sum((task/n).stat().st_size for n in files),
    'oldStageUntouched':True,'retainedCompiledArtifactsRebuilt':False,
    'installedUnitsUnchanged':True,'appPaused':True,'modelRequests':0,
    'qualificationCreated':False,'build':False,'pairApplied':False,'daemonReload':False,
    'currentQualification':'PENDING genuine native950K/full17 acceptance and root review',
    'files':files}
(task/'STAGE-INPUTS.json').write_text(json.dumps(record,indent=2)+'\n')
compact={k:v for k,v in record.items() if k!='files'}
(task/'STAGE.json').write_text(json.dumps(compact,indent=2)+'\n')
print(json.dumps(compact,indent=2))
