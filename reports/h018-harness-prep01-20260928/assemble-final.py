#!/usr/bin/env python3
"""Prepare only: assemble-final.py STAGE RETAINED_PAYLOAD REPO SOURCE_COMMIT.
After root review of the actual protected receipt, prepare one profile/config
COPY layer over retained final46. No compile, build, host contact or activation.
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
assert sha(profile)==record['profileSha256']=='1767aec74793b161b07feeee9e8dc97c3a4ffc9970c5c8f532bbf443b9f8ea1c'
# Verify retained compile14 provenance without repackaging or recompiling it.
inputs=json.loads((repo/'reports/h016-timeout-compile-20260927/FINAL-INPUTS.json').read_text())['files']
expected={k:v for k,v in inputs.items() if k.startswith('payload/')}
with tarfile.open(archive,'r:gz') as a:
 members=a.getmembers();files={m.name:m for m in members if m.isfile() and m.name.startswith('payload/')}
 assert set(files)==set(expected) and len(files)==44
 assert len(files)==sum(m.isfile() and m.name.startswith('payload/') for m in members)
 for m in members:
  p=pathlib.PurePosixPath(m.name)
  assert not p.is_absolute() and '..' not in p.parts and (m.isdir() or m.isfile())
 for name,m in files.items():assert hashlib.sha256(a.extractfile(m).read()).hexdigest()==expected[name]
# Only two image files change. final46 already contains exact compile14 payload.
payload=stage/'payload';assert not payload.exists()
for rel,p in {'opt/ai-harness/engine/configure-profile.mjs':profile,
              'opt/ai-harness/config/active-frontier.json':stage/'config/active-frontier.json'}.items():
 dst=payload/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dst);dst.chmod(0o644)
for p in [payload,*(p for p in payload.rglob('*') if p.is_dir())]:p.chmod(0o755)
# Copy the retained final18 host release separately; overlay these three files only.
host=stage/'host';host.mkdir()
for rel,p in {'deploy/engine/configure-profile.mjs':profile,
              **{f'config/{n}':stage/'config'/n for n in ['active-frontier.json','mimo-candidate.json']}}.items():
 dst=host/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dst)
(stage/'Containerfile').write_text('FROM sha256:46feffff8fe00e5993a8e0d35f5a7932f82ee43ef91d87759f568c3a6029dc1e\nUSER root\nCOPY payload/ /\nLABEL org.opencontainers.image.ai-harness.source="'+source+'"\nUSER 1000:1000\n')
(stage/'FINAL.SHA256SUMS').write_text(''.join(f'{sha(p)}  {p.relative_to(stage)}\n' for p in sorted(stage.rglob('*')) if p.is_file() and p.name!='FINAL.SHA256SUMS'))
print('Prepared profile/config layer over retained final46 and three-file host delta; no build or activation.')
