#!/usr/bin/env python3
"""Offline packaging fixture using exact retained archive and accepted final46 inventory.
Usage: package-fixture.py RETAINED_ARCHIVE FINAL46_INVENTORY
Fixture config explicitly disables MiMo. This is no qualification, image build,
service stage, activation or proof of 950000 actual capacity.
"""
import hashlib,json,pathlib,subprocess,sys,tarfile,tempfile
if '--help' in sys.argv: print(__doc__);sys.exit(0)
archive,inventory=map(pathlib.Path,sys.argv[1:3]);here=pathlib.Path(__file__).resolve().parent;repo=here.parents[1]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(archive)=='0d34ca656248d8293ee4098ef1ba0202fc02353ac35a515870220e8fcc805d17'
assert sha(inventory)=='7846eb5f9befb44e55cc4c62cfe15e114bb21c7ef7f10a9cdb410491da2d9fcf'
base=json.loads(inventory.read_text())
inputs=json.loads((repo/'reports/h016-timeout-compile-20260927/FINAL-INPUTS.json').read_text())['files']
payload={k:v for k,v in inputs.items() if k.startswith('payload/')};assert len(payload)==44
profile_rel='/opt/ai-harness/engine/configure-profile.mjs'
for rel,h in payload.items():
 path='/'+rel.removeprefix('payload/')
 assert base[path][1]==('045d0ed290a4870182610745a5a51ba471d9797bf5aebffbb3148ca4d000e020' if path==profile_rel else h),path
assert base['/opt/minimax/cli.js'][3]&0o111
with tarfile.open(archive) as a:
 regular=[m.name for m in a.getmembers() if m.isfile()]
 assert len(regular)==53 and len([n for n in regular if n.startswith('payload/')])==44
with tempfile.TemporaryDirectory(prefix='h017-package-fixture-') as temp:
 stage=pathlib.Path(temp)/'stage';(stage/'config').mkdir(parents=True)
 for name in ['active-frontier.json','mimo-candidate.json']:
  (stage/'config'/name).write_text(json.dumps({'fixtureOnly':True,'mimoEnabled':False,'qualified':False})+'\n')
 profile=repo/'ai-harness/deploy/engine/configure-profile.mjs'
 record={'activation':False,'profileSha256':sha(profile),'activeConfigSha256':sha(stage/'config/active-frontier.json'),'candidateSha256':sha(stage/'config/mimo-candidate.json')}
 (stage/'STAGED.json').write_text(json.dumps(record))
 subprocess.run([sys.executable,str(here/'assemble-final.py'),str(stage),str(archive),str(repo),'d09620402007046881606dfbdc74c9ee3fde09b2'],check=True,capture_output=True,text=True)
 image={str(p.relative_to(stage/'payload')) for p in (stage/'payload').rglob('*') if p.is_file()}
 host={str(p.relative_to(stage/'host')) for p in (stage/'host').rglob('*') if p.is_file()}
 assert image=={'opt/ai-harness/engine/configure-profile.mjs','opt/ai-harness/config/active-frontier.json'}
 assert host=={'deploy/engine/configure-profile.mjs','config/active-frontier.json','config/mimo-candidate.json'}
 for p in [stage/'payload',*(stage/'payload').rglob('*')]:assert p.stat().st_mode&0o777==(0o755 if p.is_dir() else 0o644)
 recipe=(stage/'Containerfile').read_text();assert recipe.count('COPY ')==1 and 'RUN ' not in recipe
 assert recipe.startswith('FROM sha256:46feffff8fe00e5993a8e0d35f5a7932f82ee43ef91d87759f568c3a6029dc1e\n')
 assert recipe.endswith('USER 1000:1000\n')
 for line in (stage/'FINAL.SHA256SUMS').read_text().splitlines():
  h,rel=line.split('  ',1);assert sha(stage/rel)==h
 print(json.dumps({'result':'PASS','archiveSha256':sha(archive),'regularArchiveFiles':53,'verifiedPayloadFiles':44,'extraFilesCopiedToImage':0,'baseInventorySha256':sha(inventory),'baseInventoryEntries':len(base),'imageFiles':sorted(image),'hostFiles':sorted(host),'ancestorMode':'0755','fileMode':'0644','inheritedCliExecutable':True,'compiledPayloadUnchangedInBase':True,'fixtureOnly':True,'qualification':False,'build':False,'activation':False},indent=2))
