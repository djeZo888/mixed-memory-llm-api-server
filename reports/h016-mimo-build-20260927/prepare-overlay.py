#!/usr/bin/env python3
"""Derive a minimal H016 overlay from newly packaged output and immutable base hashes."""
import hashlib,json,pathlib,shutil,sys
if '--help' in sys.argv: print(__doc__);sys.exit(0)
t=pathlib.Path('/home/user/ai-harness-build/H016-MIMO-BUILD-20260927');base=json.loads((t/'base-inventory.json').read_text()); overlay=t/'overlay';overlay.mkdir(exist_ok=True)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
changes=[];unchanged=[]
for p in sorted((t/'packaged').rglob('*')):
 if not p.is_file():continue
 name='/opt/minimax/'+str(p.relative_to(t/'packaged'));old=base.get(name);h=sha(p)
 if old and old[0]=='file' and old[1]==h:unchanged.append(name);continue
 changes.append({'path':name,'old_sha256':old[1] if old else None,'sha256':h,'source':'packaged'})
# Review concrete names before building; no tools/deps/native replacement.
allowed={'README.md','cli.js','native-probes.mjs','native-probes.mjs.metafile.json','patched-source-revision.txt','minimax-code-0.5.1.tar.gz.sha256','release.json'}
for r in changes:
 rel=r['path'].removeprefix('/opt/minimax/')
 assert rel in allowed or rel.startswith('chunks/'),r
 dst=overlay/r['path'].lstrip('/');dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(t/'packaged'/rel,dst)
for src,dst in [('deploy/engine/pins.json','/opt/ai-harness/engine/pins.json'),('deploy/engine/configure-profile.mjs','/opt/ai-harness/engine/configure-profile.mjs'),('config/active-frontier.json','/opt/ai-harness/config/active-frontier.json')]:
 p=t/'source/ai-harness'/src;out=overlay/dst.lstrip('/');out.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,out);changes.append({'path':dst,'old_sha256':base.get(dst,[None,None])[1],'sha256':sha(p),'source':src})
for p in sorted((t/'source/ai-harness/deploy/patches').iterdir()):
 if not p.is_file():continue
 dst='/usr/local/share/ai-harness-patches/'+p.name;old=base.get(dst)
 if old and old[1]==sha(p):continue
 out=overlay/dst.lstrip('/');out.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,out);changes.append({'path':dst,'old_sha256':old[1] if old else None,'sha256':sha(p),'source':'deploy/patches/'+p.name})
assert any(x['path']=='/opt/minimax/cli.js' for x in changes)
assert sha(t/'model-token-estimator.ts')=='649b21e84263c278c1a43d8cc17ab19fdbf08a5a4b95c666d9a914dd81abea68'
manifest={'source':'928b3b470058241f089a839367d4b30d5887a6e3','base_image':'sha256:9ef88598cf54a03aa259c5aa2d2878b34b7473cfcec7c8c07cee6ba462c39f1c','compiled_image':(t/'compiled.iid').read_text().strip(),'native_source':(t/'packaged/patched-source-revision.txt').read_text().strip(),'estimator_source_sha256':sha(t/'model-token-estimator.ts'),'patchset':'a6dd7df37313edc4ea2f6bc742ffb6ff431a37abacb2facdbbf422a4c9f9d4bd','changed_file_allowlist':changes,'unchanged_packaged_files':unchanged}
(t/'overlay-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
(t/'Containerfile.overlay').write_text('FROM '+manifest['base_image']+'\nUSER root\nCOPY overlay/ /\nLABEL org.opencontainers.image.ai-harness.patchset="'+manifest['patchset']+'" \\\n      org.opencontainers.image.ai-harness.source="'+manifest['source']+'" \\\n      org.opencontainers.image.ai-harness.native-source="'+manifest['native_source']+'"\nUSER 1000:1000\n')
print(json.dumps({'changed_files':changes,'unchanged_packaged_count':len(unchanged)},indent=2))
