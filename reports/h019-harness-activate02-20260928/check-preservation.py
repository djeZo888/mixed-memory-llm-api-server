"""Compact paused production-data check using the retained summary helper."""
import hashlib, importlib.util, json, pathlib, stat, sys

task = pathlib.Path('/home/user/ai-harness-build/H019-HARNESS-PREP01-20260928')
helper = pathlib.Path('/home/user/ai-harness-build/H010-WORKER2-20260927/recover-harness-02.py')
assert hashlib.sha256(helper.read_bytes()).hexdigest() == '6851fb4639c6ba00040e707cf921442f6870e5bd59c7b9e159017d2ec1d82dee'
spec = importlib.util.spec_from_file_location('retained', helper)
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
app = m.unit('ai-harness.service', True)
assert app['ActiveState'] == 'inactive' and app['MainPID'] == '0'
current = m.summary(); m.require_idle(current)
current = json.loads(json.dumps(current))
baseline = json.loads((task/'private/AFTER.json').read_text())
assert current == baseline['data'], 'preserve unexpected changes for review'
credentials = {}
for name, old in baseline['metadata']['credentials'].items():
    p = pathlib.Path(name) if name.startswith('/') else pathlib.Path('/home/user/.config/ai-harness')/name
    s = p.lstat()
    new = dict(uid=s.st_uid, gid=s.st_gid, mode=oct(stat.S_IMODE(s.st_mode)), size=s.st_size, inode=s.st_ino, contentsRead=False)
    assert stat.S_ISREG(s.st_mode) and new == old
    credentials[name] = True
result = {'status':'PASS_PRODUCTION_STILL_PAUSED_AND_PRESERVED','utc':m.now(), 'app':app, 'data':current,
          'allHistoryHashesMatchPrep01':True,'credentialMetadataUnchanged':all(credentials.values()),
          'ownerSqliteRead':False,'credentialContentsRead':False,'fileRehashPerformed':False,
          'regularFilesBaseline':{'count':17597,'sha256':'1e262519cde8059973b23a2fc2a2838e2a15cb4429269fe18e57cc4adb906f51','scope':'retained PREP01 evidence; no new content hash or full filesystem scan'},
          'activeOwnedRuns':0,'activeFrontierRequests':0,'ownedEngineContainers':0}
output = task/'private'/sys.argv[1]
with output.open('x') as f: json.dump(result,f,indent=2); f.write('\n')
print(json.dumps({'status':result['status'],'utc':result['utc'],'path':str(output),'sha256':hashlib.sha256(output.read_bytes()).hexdigest()}))
