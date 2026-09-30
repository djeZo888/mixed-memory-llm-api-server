#!/usr/bin/env python3
"""Offline preparation only. assemble-final.py STAGE RETAINED_PAYLOAD REPO SOURCE_COMMIT
Requires stage-qualified-config output after existing root review. Never builds,
installs or contacts a host. Actual root-reviewed receipt is mandatory; app apply remains separately authorized.
"""
import hashlib,json,pathlib,shutil,sys,tarfile
if '--help' in sys.argv: print(__doc__);sys.exit(0)
stage,archive,repo=map(lambda s:pathlib.Path(s).resolve(),sys.argv[1:4]);source=sys.argv[4]
assert len(source)==40 and all(c in '0123456789abcdef' for c in source)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(archive)=='0d34ca656248d8293ee4098ef1ba0202fc02353ac35a515870220e8fcc805d17'
record=json.loads((stage/'STAGED.json').read_text())
assert record['activation'] is False
for name,key in [('active-frontier.json','activeConfigSha256'),('mimo-candidate.json','candidateSha256')]:assert sha(stage/'config'/name)==record[key]
profile=repo/'ai-harness/deploy/engine/configure-profile.mjs'
assert sha(profile)==record['profileSha256']=='045d0ed290a4870182610745a5a51ba471d9797bf5aebffbb3148ca4d000e020'
inputs=json.loads((repo/'reports/h016-timeout-compile-20260927/FINAL-INPUTS.json').read_text())['files']
expected={k:v for k,v in inputs.items() if k.startswith('payload/')}
assert not (stage/'payload').exists()
with tarfile.open(archive,'r:gz') as a:
 members=a.getmembers();files={m.name:m for m in members if m.isfile() and m.name.startswith('payload/')}
 assert set(files)==set(expected)
 for m in members:
  p=pathlib.PurePosixPath(m.name)
  assert not p.is_absolute() and '..' not in p.parts and (m.isdir() or m.isfile())
 for name,m in files.items():
  data=a.extractfile(m).read();assert hashlib.sha256(data).hexdigest()==expected[name]
  dst=stage/name;dst.parent.mkdir(parents=True,exist_ok=True);dst.write_bytes(data);dst.chmod(m.mode&0o755)
# Retained vendor code/metadata/patches/pins remain exact; only reviewed profile
# replaces compile14's prior profile. Native CLI executable mode is preserved.
shutil.copy2(profile,stage/'payload/opt/ai-harness/engine/configure-profile.mjs')
config=stage/'payload/opt/ai-harness/config';config.mkdir(parents=True,exist_ok=True)
shutil.copy2(stage/'config/active-frontier.json',config/'active-frontier.json')
# The private staging umask must not become root-only /opt or /usr in COPY.
# Only directories inside this task-owned payload are adjusted.
for directory in [stage/'payload',*(p for p in (stage/'payload').rglob('*') if p.is_dir())]:directory.chmod(0o755)
for p in (config/'active-frontier.json',stage/'payload/opt/ai-harness/engine/configure-profile.mjs'):p.chmod(0o644)
# Paired host delta: no compile, dependency changes, or mutation of old release.
host=stage/'host';host.mkdir()
copy={
 'deploy/engine/configure-profile.mjs':profile,
 'deploy/run-engine.sh':repo/'ai-harness/deploy/run-engine.sh',
 'deploy/engine/pins.json':repo/'ai-harness/deploy/engine/pins.json',
 **{str(p.relative_to(repo/'ai-harness')):p for p in (repo/'ai-harness/deploy/patches').rglob('*') if p.is_file() and 'payload/usr/local/share/ai-harness-patches/'+str(p.relative_to(repo/'ai-harness/deploy/patches')) in inputs},
 'config/system-registry.json':repo/'ai-harness/config/system-registry.json',
 **{f'config/{n}':stage/'config'/n for n in ['active-frontier.json','mimo-candidate.json']},
 **{f'server/dist/{n}':repo/'reports/h016-status-timeout-staging-20260927/artifacts/server/dist'/n for n in ['gateway.js','gateway.d.ts','system-registry.js','system-registry.d.ts']}}
for rel,p in copy.items():
 dst=host/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dst)
assert sha(host/'deploy/run-engine.sh')==inputs['run-engine.sh']
assert sha(host/'deploy/engine/pins.json')==inputs['payload/opt/ai-harness/engine/pins.json']
for p in (host/'deploy/patches').rglob('*'):
 if p.is_file():assert sha(p)==inputs['payload/usr/local/share/ai-harness-patches/'+str(p.relative_to(host/'deploy/patches'))]
for rel in ['server/dist/gateway.js','server/dist/system-registry.js']:assert sha(host/rel)==inputs['host-artifacts/'+rel]
recipe=(repo/'reports/h016-timeout-compile-20260927/Containerfile.held').read_text()
recipe=recipe.replace('COPY payload/ /','COPY payload/ /\nLABEL org.opencontainers.image.ai-harness.source="'+source+'"')
(stage/'Containerfile').write_text(recipe)
# Existing staging hash list, not qualification or a new receipt schema.
(stage/'FINAL.SHA256SUMS').write_text(''.join(f'{sha(p)}  {p.relative_to(stage)}\n' for p in sorted(stage.rglob('*')) if p.is_file() and p.name!='FINAL.SHA256SUMS'))
print('Prepared one COPY layer and paired host delta; no image exists until reviewed build.')
