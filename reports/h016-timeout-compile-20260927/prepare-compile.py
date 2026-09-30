#!/usr/bin/env python3
"""Assert and patch an isolated retained source; derive bundle-only upstream recipe."""
import hashlib,json,pathlib,subprocess,sys
if '--help' in sys.argv: print(__doc__);sys.exit(0)
t=pathlib.Path(sys.argv[1]).resolve();s=t/'native-source'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def run(*a):return subprocess.check_output(a,cwd=s,text=True).strip()
c=json.loads((t/'ENGINE-PATCH-CLOSURE.json').read_text())
assert sha(t/'0011-mimo-request-budget.patch')==c['patchSha256']
assert run('git','status','--porcelain','--untracked-files=no')==''
base=run('git','rev-parse','HEAD');assert base=='51d06736d5dd56d0e7b7e34dbb107fa015864817'
paths=run('git','ls-files').splitlines();before={p:sha(s/p) for p in paths if (s/p).is_file()}
(t/'source-before.json').write_text(json.dumps(before,sort_keys=True))
for f in c['files']:assert sha(s/f['path'])==f['originalSha256'],f['path']
run('git','apply','--check','--unidiff-zero',str(t/'0011-mimo-request-budget.patch'))
run('git','apply','--unidiff-zero',str(t/'0011-mimo-request-budget.patch'))
for f in c['files']:assert sha(s/f['path'])==f['patchedSha256'],f['path']
after={p:sha(s/p) for p in paths if (s/p).is_file()};changed=[p for p in before if before[p]!=after[p]]
assert sorted(changed)==sorted(f['path'] for f in c['files'])
assert after['packages/local-runtime-v2/src/service/model-system/resolution/model-token-estimator.ts']=='649b21e84263c278c1a43d8cc17ab19fdbf08a5a4b95c666d9a914dd81abea68'
run('git','add',*[f['path'] for f in c['files']])
import os
env=dict(os.environ,GIT_AUTHOR_DATE='2026-09-27T15:55:06Z',GIT_COMMITTER_DATE='2026-09-27T15:55:06Z')
subprocess.run(['git','-c','user.name=H016 source build','-c','user.email=h016-build@localhost','commit','--no-gpg-sign','-m','Apply reviewed MiMo timeout and zero-retry patch'],cwd=s,env=env,check=True,stdout=subprocess.DEVNULL)
head=run('git','rev-parse','HEAD')
(t/'source-after.json').write_text(json.dumps(after,sort_keys=True))
original=(s/'scripts/build.mjs').read_text();assert original.count('copyLocalRuntimeAssets({')==1
compile=original[:original.index('copyLocalRuntimeAssets({')]+'''writeFileSync(path.join(outdir,"metafile.json"),JSON.stringify(result.metafile,null,2)+"\\n");
chmodSync(path.join(outdir,"cli.js"),0o755);
'''
# Use a fresh output location. No asset/native/dependency/artifact steps run.
compile=compile.replace('path.join(root, "dist")','path.join(root, "timeout-dist")')
(s/'scripts/h016-compile-only.mjs').write_text(compile)
(t/'SOURCE-CHECKS.json').write_text(json.dumps({'upstream':c['upstream'],'retainedPatchedRevision':base,'patchedRevision':head,'exactChangedFiles':changed,'sourceFileCount':len(after),'patchSha256':c['patchSha256'],'estimatorSha256':after['packages/local-runtime-v2/src/service/model-system/resolution/model-token-estimator.ts'],'lockedDependenciesSha256':after['pnpm-lock.yaml'],'upstreamBuildRecipeSha256':sha(s/'scripts/build.mjs'),'derivedBundleOnlyRecipeSha256':sha(s/'scripts/h016-compile-only.mjs'),'baseImage':c['baseImage']},indent=2)+'\n')
print((t/'SOURCE-CHECKS.json').read_text())
