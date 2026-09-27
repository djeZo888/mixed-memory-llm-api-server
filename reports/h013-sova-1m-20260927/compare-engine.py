import hashlib,json,pathlib,subprocess
root=pathlib.Path('/home/user/ai-harness-build/H013-SOVA-1M-20260927')
source=root/'source/ai-harness'
old='c328dac0e6ede1dfb890a0657ebafd6f6fd4a1f2281f4e1c664ab95db7dcaa20'
rows=[]
for src,dst in [('deploy/engine','/opt/ai-harness/engine'),('deploy/patches','/usr/local/share/ai-harness-patches'),('skills','/opt/ai-harness/skills'),('tools/search','/opt/ai-harness/tools/search'),('tools/pdf','/opt/ai-harness/tools/pdf'),('tools/runtime','/opt/ai-harness/tools/runtime'),('tools/image','/opt/ai-harness/tools/image')]:
 for p in sorted((source/src).rglob('*')):
  if p.is_file() and 'node_modules' not in p.parts and '__pycache__' not in p.parts:
   rows.append({'source':str(p.relative_to(source)),'image':str(pathlib.Path(dst)/p.relative_to(source/src)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
for src,dst in [('tools/LICENSE-MIT.txt','/opt/ai-harness/tools/LICENSE-MIT.txt'),('deploy/tests/native-integration.mjs','/opt/ai-harness/tests/native-integration.mjs'),('deploy/tests/native-worker-boundary.mjs','/opt/ai-harness/tests/native-worker-boundary.mjs'),('deploy/tests/fixtures/native-image-mcp-catalog.json','/opt/ai-harness/tests/fixtures/native-image-mcp-catalog.json')]:
 rows.append({'source':src,'image':dst,'sha256':hashlib.sha256((source/src).read_bytes()).hexdigest()})
recipe=[]
for name in ['deploy/Containerfile','deploy/tests/build-native-probes.mjs']:
 prior=pathlib.Path('/home/user/ai-harness-build/H008-36efaae-02/context')/name
 current=hashlib.sha256((source/name).read_bytes()).hexdigest()
 assert current==hashlib.sha256(prior.read_bytes()).hexdigest(),name
 recipe.append({'source':name,'sha256':current,'matches_prior_build_source':True})
script="""import json,sys,pathlib,hashlib
rows=json.load(sys.stdin)
for r in rows:
 p=pathlib.Path(r['image']);r['old_sha256']=hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None
print(json.dumps(rows))
"""
cmd=['podman','run','--rm','--pull=never','--network','none','--user','0:0','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges','--entrypoint','python3','-i',old,'-c',script]
rows=json.loads(subprocess.check_output(cmd,input=json.dumps(rows).encode(),timeout=30))
deltas=[r for r in rows if r['sha256']!=r['old_sha256']]
result={'base_image':old,'source_commit':(root/'source.commit').read_text().strip(),'compared_files':len(rows),'deltas':deltas,'entries':rows,'unchanged_build_recipe':recipe}
(root/'engine-source-comparison.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k!='entries'},indent=2))
