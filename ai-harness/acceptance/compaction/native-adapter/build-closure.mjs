import { readFile, lstat } from 'node:fs/promises';
import { dirname,resolve,relative,join } from 'node:path';
import { createHash } from 'node:crypto';
const sha=b=>createHash('sha256').update(b).digest('hex');
export const ENTRY_PATH='ai-harness/acceptance/compaction/native-adapter/entry.js';
export const WORKER_PATH='ai-harness/acceptance/compaction/native-adapter/application-worker.js';
/** Enumerate every literal local import reachable from BOTH executable roots.
 * Unknown computed imports fail closure unless separately source-reviewed. */
export async function executedImportGraph(root,runtimeFiles) {
  const imports={},external=new Set(),visited=new Set(),unavailableImports=[];
  async function visit(path) {
    if(visited.has(path))return;visited.add(path);
    if(!runtimeFiles[path])throw Error('executed_local_import_not_in_manifest');
    const bytes=await readFile(join(root,path));if(sha(bytes)!==runtimeFiles[path])throw Error('executed_import_bytes_changed');
    if(!/\.(js|mjs)$/.test(path)){imports[path]=[];return;}
    const text=bytes.toString('utf8'),edges=[];
    const deferred=[...text.matchAll(/new\s+URL\(\s*["']([^"']+\.(?:js|mjs))["']\s*,\s*import\.meta\.url/g)].map(m=>m[1]);
    const specs=[...text.matchAll(/(?:\bfrom\s*|\bimport\s*(?:\(\s*)?)["']([^"']+)["']/g)].map(m=>m[1]);
    for(const spec of [...specs,...deferred]) {
      if(!spec.startsWith('.')){if(!spec.startsWith('node:'))external.add(spec.split('/').slice(0,spec.startsWith('@')?2:1).join('/'));continue;}
      const absolute=resolve(root,dirname(path),spec),rel=relative(root,absolute);
      if(rel==='..'||rel.startsWith('../'))throw Error('executed_import_outside_reviewed_layout');if(!runtimeFiles[rel]){if(deferred.includes(spec)){unavailableImports.push({importer:path,target:rel});continue;}throw Error('executed_import_outside_reviewed_layout');}edges.push(rel);await visit(rel);
    }
    imports[path]=[...new Set(edges)].sort();
  }
  const entrypoints=[ENTRY_PATH,WORKER_PATH];for(const p of ['normal-entry.js','normal-worker.js']){const path='ai-harness/acceptance/compaction/native-adapter/'+p;if(runtimeFiles[path])entrypoints.push(path);}for(const path of entrypoints)await visit(path);
  return {entrypoints,imports,externalPackages:[...external].sort(),unavailableImports};
}
export async function verifyInstalledBuild(repository,manifest) {
  if(manifest?.format!=='h041-source-build-v2'||!manifest.sourceFiles||!manifest.runtimeFiles||!manifest.helperFiles||!manifest.dependencyFiles||!manifest.importGraph||manifest.compilerExit!==0||manifest.nodeVersion!==process.version)throw Error('complete_executed_build_closure_required');
  for(const domain of ['sourceFiles','runtimeFiles','helperFiles','dependencyFiles'])for(const [path,digest]of Object.entries(manifest[domain])) {
    if(!path.startsWith('ai-harness/')||path.split('/').includes('..')||typeof digest!=='string'||!/^[a-f0-9]{64}$/.test(digest)||sha(await readFile(join(repository,path)))!==digest)throw Error('installed_source_build_dependency_or_helper_mismatch');
  }
  for(const suffix of ['run-codex.sh','redact-acp.py','task-egress.py','codex_receipts.py','codex/config.toml','codex/models.json','security/task-egress-policy.py'])if(!Object.keys(manifest.helperFiles).some(p=>p.endsWith(suffix)))throw Error('protected_required_helper_omitted');
  const graph=await executedImportGraph(repository,manifest.runtimeFiles);
  if(graph.unavailableImports.length||JSON.stringify(graph)!==JSON.stringify(manifest.importGraph)||!manifest.dependencyFiles['ai-harness/server/node_modules/.package-lock.json']||manifest.platform!==process.platform)throw Error('executed_import_dependency_platform_closure_mismatch');
  return graph;
}
