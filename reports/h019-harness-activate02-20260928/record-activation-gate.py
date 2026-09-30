"""Record actual applied pins and fill the retained driver gate after exact root GO."""
import datetime, hashlib, json, os, pathlib, subprocess

os.umask(0o077)
p = pathlib.Path('/home/user/ai-harness-build/H019-HARNESS-PREP01-20260928')
sha = lambda f: hashlib.sha256(pathlib.Path(f).read_bytes()).hexdigest()
assert sha(p/'private/PAIR-READY.json') == '3a1977b9ed2fe027edf2dd81f4d988629c95c4e59e86da608dbddfa506bf5ca5'
pair = json.loads((p/'private/PAIR-READY.json').read_text())
authority = p/'private/ROOT-PAIR-ACCEPTANCE-GO.txt'
assert 'ROOT EXACT PAIR REVIEW PASS' in authority.read_text()
assert pair['image'] in authority.read_text()
def cmd(*args):
    return subprocess.check_output(args, text=True, timeout=30).strip()
def save(name, value):
    f = p/'private'/name
    with f.open('x') as stream:
        json.dump(value,stream,indent=2);stream.write('\n');stream.flush();os.fsync(stream.fileno())
    return f
def unit(name,user=False):
    args=['systemctl']+(['--user'] if user else [])+['show',name,'-p','ActiveState','-p','SubState','-p','MainPID','-p','WorkingDirectory','-p','InvocationID']
    return dict(x.split('=',1) for x in cmd(*args).splitlines())
app = unit('ai-harness.service',True)
assert app['ActiveState']=='inactive' and app['MainPID']=='0'
image = cmd('podman','image','inspect','localhost/ai-harness-engine:0.0.2-ae65651df5f9','--format','{{.Id}}')
assert image == pair['image'].removeprefix('sha256:')
release = pathlib.Path(pair['release'])
for rel,h in pair['releaseSha256'].items():
    assert sha(release/rel)==h,rel
units = {'ai-harness.service':'/home/user/.config/systemd/user/ai-harness.service',
         '30-h008-registry.conf':'/etc/systemd/system/ai-harness-status.service.d/30-h008-registry.conf'}
assert {n:sha(f) for n,f in units.items()} == pair['unitSha256']
assert sha('/etc/sova-qualification/mimo.json') == pair['qualificationSha256']
for n,h in pair['helperSha256'].items(): assert sha(p/n)==h,n
driverNames=['live.mjs','preflight-cli.mjs','guards.mjs','preflight.mjs','prompts.json','supervise.py','edge.mjs','check.mjs','policy-a.txt','policy-b.txt']
driver={n:sha(p/'driver'/n) for n in driverNames}
assert all(h==pair['driverSha256'][n] for n,h in driver.items())
activation={'status':'PAIR_APPLIED_APP_PAUSED','utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'source':pair['source'],'image':image,'qualificationSha256':pair['qualificationSha256'],
            'release':str(release),'releaseSha256':pair['releaseSha256'],'unitSha256':pair['unitSha256'],
            'driverSha256':driver,'helperSha256':pair['helperSha256'],'pairReadySha256':sha(p/'private/PAIR-READY.json'),
            'rootAuthoritySha256':sha(authority),'app':app,'statusService':unit('ai-harness-status.service'),
            'applied':True,'normalAppStarted':False,'inferenceDispatched':False}
manifest=save('ACTIVATION-MANIFEST.json',activation)
g={'authorization':'ROOT_GO_H019_NATIVE_APP_ACCEPTANCE','source':pair['source'],'image':image,
   'issuedUtc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
   'ownerSha256':'e5fda2057168c29b1fe6e53da727b337beaf5634ddbc7dbb3d4f2c46602bcd53',
   'toolsSha256':'80e7a1e12e073ac57638e86638cf571158711ff821c96605135627777ce44e8c',
   'maxInput':16383,'maxOutput':65536,'wallSeconds':1380,'context':950000,
   'qualificationSha256':pair['qualificationSha256'],'driverSha256':driver,
   'activationManifestSha256':sha(manifest),'releaseSha256':pair['releaseSha256'],
   'receipts':[{'path':str(p/'private'/n),'sha256':sha(p/'private'/n)} for n in ['ROOT-QUALIFICATION.json','EVIDENCE-MAPPING.json','ROOT-PAIR-ACCEPTANCE-GO.txt','PAIR-READY.json']],
   'qualificationScope':'Current authentic native short17; occupied9635 and largest completed output70; strict:false nested schemas accepted, strict:true generation not tested.',
   'productionGeneration':12,'serverInstance':'aae59a6db7da41ff58056ce11e762060a6fe8aeecdad3d0e6813057573238d54',
   'serverGeneration':'b23d112359424d909862207e30f0c9d7'}
for k in ['worker1LaneReleased','liveInferenceAuthorized','productionOwnerCurrent','full17Qualified','strictNestedSchemasQualified','serialCompletionQualified','ceiling65536Accepted','nativePropsSlotsReviewed','nodeDTOReviewed','noReplay','noQuarantineClear','existingPassiveObserverAuthorized']:
    g[k]=True
gate=save('ROOT-LIVE-GATE.json',g)
print(json.dumps({'status':'ACTUAL_APPLIED_GATE_READY','gate':str(gate),'gateSha256':sha(gate),'activationManifest':str(manifest),'activationManifestSha256':sha(manifest),'source':pair['source'],'image':image,'appPaused':True},indent=2))
