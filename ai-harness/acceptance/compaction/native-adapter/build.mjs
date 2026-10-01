import { executedImportGraph } from './build-closure.mjs';
import { spawnSync } from 'node:child_process';
import { mkdir, readdir, lstat, readFile, writeFile, copyFile } from 'node:fs/promises';
import { resolve, join, dirname, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';
const here=dirname(fileURLToPath(import.meta.url)), repo=resolve(here,'../../../..'), out=resolve(process.argv[2]??'');
if(!process.argv[2]||out===repo||out.startsWith(repo+'/'))throw Error('explicit_new_private_external_build_directory_required');
await mkdir(out,{mode:0o700});
const emitted=join(out,'ai-harness');await mkdir(emitted,{mode:0o700});
const tsc=join(repo,'ai-harness/server/node_modules/.bin/tsc');
const argv=['-p',join(here,'build.tsconfig.json'),'--outDir',emitted];
const compiled=spawnSync(tsc,argv,{encoding:'utf8'});
await writeFile(join(out,'compile.log'),compiled.stdout+compiled.stderr,{mode:0o600});
if(compiled.status!==0){process.exitCode=compiled.status??1;throw Error('actual_emitted_build_failed');}
const hash=b=>createHash('sha256').update(b).digest('hex'), sourceFiles={},runtimeFiles={};
async function sources(path){const s=await lstat(path);if(s.isSymbolicLink())throw Error('build_source_symlink');if(s.isDirectory()){for(const name of(await readdir(path)).sort())await sources(join(path,name));}else if(/\.(ts|mts|mjs|json)$/.test(path)){const rel=relative(repo,path);sourceFiles[rel]=hash(await readFile(path));if(/\.(mjs|json)$/.test(path)){const target=join(out,rel);await mkdir(dirname(target),{recursive:true,mode:0o700});await copyFile(path,target);}}}
await sources(join(repo,'ai-harness/server/package.json'));await sources(join(repo,'ai-harness/server/package-lock.json'));await sources(join(repo,'ai-harness/server/src'));await sources(join(repo,'ai-harness/acceptance/compaction'));
async function runtime(path){const s=await lstat(path);if(s.isDirectory()){for(const name of(await readdir(path)).sort())await runtime(join(path,name));}else if(/\.(js|mjs|json)$/.test(path))runtimeFiles[relative(out,path)]=hash(await readFile(path));}
await runtime(emitted);
const helperFiles={},dependencyFiles={};
async function domain(path,files,copy=false) {
 const s=await lstat(path);if(s.isSymbolicLink())throw Error('closure_nested_symlink_not_reviewed');
 if(s.isDirectory()){for(const n of(await readdir(path)).sort())await domain(join(path,n),files,copy);}
 else if(s.isFile()){const rel=relative(repo,path),b=await readFile(path);files[rel]=hash(b);if(copy){const target=join(out,rel);await mkdir(dirname(target),{recursive:true,mode:0o700});await copyFile(path,target);}}
}
for(const path of ['ai-harness/deploy/engine','ai-harness/deploy/codex','ai-harness/deploy/security','ai-harness/deploy/run-codex.sh'])await domain(join(repo,path),helperFiles,true);
// The supplied top-level dependency symlink is retained as an installation
// input, never committed/copied. Every actual regular dependency byte is pinned.
const dependencyRoot=join(repo,'ai-harness/server/node_modules');
for(const n of(await readdir(dependencyRoot)).sort())if(n!=='.bin')await domain(join(dependencyRoot,n),dependencyFiles);
const importGraph=await executedImportGraph(out,runtimeFiles);
const manifest={format:'h041-source-build-v2',sourceFiles,runtimeFiles,helperFiles,dependencyFiles,importGraph,platform:process.platform,packageLockSha256:hash(await readFile(join(repo,'ai-harness/server/package-lock.json'))),compilerArgv:[tsc,...argv],compilerExit:compiled.status,nodeVersion:process.version,delivery:'Overlay reviewed emitted .js/.mjs at these same relative source paths in the staged repository; include reviewed deploy helpers/codex_receipts.py and root qualification/config separately. Do not execute the Mac build as Linux qualification.'};
await writeFile(join(out,'source-build-manifest.json'),JSON.stringify(manifest,null,2)+'\n',{mode:0o600});console.log(JSON.stringify({compilerExit:compiled.status,sourceFileCount:Object.keys(sourceFiles).length,runtimeFileCount:Object.keys(runtimeFiles).length,manifestSha256:hash(Buffer.from(JSON.stringify(manifest,null,2)+'\n'))}));
