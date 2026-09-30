#!/usr/bin/env python3
"""Assemble compiled artifact closure, never an image or qualified config."""
import pathlib,json,hashlib,shutil,sys,subprocess,tarfile
if '--help' in sys.argv: print(__doc__);sys.exit(0)
t=pathlib.Path(sys.argv[1]).resolve();s=t/'native-source';b=pathlib.Path('/home/user/ai-harness-build/H016-MIMO-BUILD-20260927');pkg=t/'packaged';pkg.mkdir(exist_ok=True)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
base=json.loads((b/'candidate-inventory.json').read_text());check=json.loads((t/'SOURCE-CHECKS.json').read_text())
# Runtime package and asset lineage comes from the accepted compiled package.
shutil.copytree(t/'packaged-base',pkg,dirs_exist_ok=True)
meta=json.loads((s/'timeout-dist/metafile.json').read_text());probe=json.loads((t/'native-probes.mjs.metafile.json').read_text())
changed=check['exactChangedFiles'];closure={}
for label,m in [('cli',meta),('nativeProbe',probe)]:
 for p in changed:assert p in m['inputs'],(label,p)
 closure[label]={'inputs':len(m['inputs']),'outputs':len(m['outputs']),'changedInputOutputs':{p:[o for o,v in m['outputs'].items() if p in v.get('inputs',{})] for p in changed}}
 for p in changed:assert closure[label]['changedInputOutputs'][p],(label,p)
for path in meta['outputs']:
 f=s/path;rel=f.relative_to(s/'timeout-dist');dst=pkg/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(f,dst)
shutil.copy2(s/'timeout-dist/metafile.json',pkg/'metafile.json')
for name in ['native-probes.mjs','native-probes.mjs.metafile.json']:shutil.copy2(t/name,pkg/name)
(pkg/'patched-source-revision.txt').write_text(check['patchedRevision']+'\n')
release=json.loads((pkg/'release.json').read_text());release['revision']=check['patchedRevision'];(pkg/'release.json').write_text(json.dumps(release,indent=2)+'\n')
# Verify complete emitted import graph for every preserved native entrypoint.
outputs=meta['outputs'];roots=['timeout-dist/'+n for n in ['cli.js','image-preview-worker.js','mcode-tools.js','matrix-mcp-stdio.js']];visited=set()
def visit(p):
 if p in visited:return
 visited.add(p);assert p in outputs,p
 for i in outputs[p]['imports']:
  if not i.get('external',False):visit(i['path'])
visit(roots[0]);closure['cliReachableOutputs']=len(visited)
for p in roots[1:]:visit(p)
closure['allActualEntrypointsReachAllOutputs']=visited==set(outputs)
assert visited==set(outputs),set(outputs)-visited
closure['actualEntrypoints']=roots;closure['entrypoints']={p:v['entryPoint'] for p,v in outputs.items() if 'entryPoint' in v};closure['reachableOutputs']=len(visited)
# Preserve all old non-JS assets and tools, comparing exact immutable image inventory.
delta=[];unchanged=[]
allowed={'cli.js','image-preview-worker.js','mcode-tools.js','matrix-mcp-stdio.js','metafile.json','native-probes.mjs','native-probes.mjs.metafile.json','patched-source-revision.txt','release.json','minimax-code-0.5.1.tar.gz.sha256'}
for p in sorted(pkg.rglob('*')):
 if not p.is_file():continue
 rel=p.relative_to(pkg).as_posix();name='/opt/minimax/'+rel;old=base.get(name);h=sha(p)
 if old and old[0]=='file' and old[1]==h:unchanged.append(name);continue
 assert rel in allowed or rel.startswith('chunks/'),rel
 delta.append({'path':name,'oldSha256':old[1] if old else None,'sha256':h,'bytes':p.stat().st_size})
# Release archive is assembled from existing assets plus changed compiled output.
(pkg/'minimax-code-0.5.1.tar.gz.sha256').unlink()
with tarfile.open(t/'minimax-code-0.5.1-timeout14.tar.gz','w:gz') as a:a.add(pkg,arcname='minimax-code-0.5.1')
archiveSha=sha(t/'minimax-code-0.5.1-timeout14.tar.gz')
(pkg/'minimax-code-0.5.1.tar.gz.sha256').write_text(archiveSha+'  minimax-code-0.5.1-timeout14.tar.gz\n')
p=pkg/'minimax-code-0.5.1.tar.gz.sha256';name='/opt/minimax/'+p.name;unchanged=[x for x in unchanged if x!=name];delta=[d for d in delta if d['path']!=name];delta.append({'path':name,'oldSha256':base[name][1],'sha256':sha(p),'bytes':p.stat().st_size})
payload=t/'payload';payload.mkdir()
for d in delta:
 p=payload/d['path'].lstrip('/');p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(pkg/d['path'].removeprefix('/opt/minimax/'),p)
# Test-only export bridge: unmodified compiled bytes followed by exports, never release.
bridge=(pkg/'native-probes.mjs').read_bytes()+b'\nexport {wrapStreamFnWithTimeout,withLLMRetry,harnessGatewayFetch,gatewayDispatcher,GATEWAY_TRANSPORT_TIMEOUT_MS};\n'
(t/'native-probes-check.mjs').write_bytes(bridge)
closure.update({'result':'PASS','baseImage':check['baseImage'],'patchedRevision':check['patchedRevision'],'changedFiles':delta,'unchangedPackagedFiles':len(unchanged),'immutableBaseInventoryEntries':len(base),'toolsDependenciesChanged':[],'archiveSha256':archiveSha,'archive':'minimax-code-0.5.1-timeout14.tar.gz','metafiles':{'cli':sha(pkg/'metafile.json'),'probe':sha(pkg/'native-probes.mjs.metafile.json')},'testBridgePrefixSha256':sha(pkg/'native-probes.mjs'),'testBridgeSha256':sha(t/'native-probes-check.mjs'),'finalImageBuilt':False})
(t/'COMPILED-CLOSURE.json').write_text(json.dumps(closure,indent=2)+'\n');print(json.dumps({'changedFiles':len(delta),'unchangedPackageFiles':len(unchanged),'reachableOutputs':len(visited),'archiveSha256':archiveSha}))
