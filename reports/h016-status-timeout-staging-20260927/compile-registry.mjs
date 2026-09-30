/** Offline, one-source-file emit using the existing locked compiler. */
import ts from '../../ai-harness/server/node_modules/typescript/lib/typescript.js';
import assert from 'node:assert/strict';
import {readFileSync, mkdirSync, writeFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {resolve, basename} from 'node:path';
const root=fileURLToPath(new URL('../../',import.meta.url));
const configPath=resolve(root,'ai-harness/server/tsconfig.json');
const config=ts.readConfigFile(configPath,ts.sys.readFile);
assert(!config.error);
const parsed=ts.parseJsonConfigFileContent(config.config,ts.sys,resolve(root,'ai-harness/server'));
const program=ts.createProgram(parsed.fileNames,parsed.options);
const diagnostics=ts.getPreEmitDiagnostics(program);
if(diagnostics.length){console.error(ts.formatDiagnosticsWithColorAndContext(diagnostics,{getCanonicalFileName:p=>p,getCurrentDirectory:()=>root,getNewLine:()=> '\n'}));process.exit(1);}
const sources=['system-registry','gateway'];
const out=resolve(root,'reports/h016-status-timeout-staging-20260927/artifacts/server/dist');
mkdirSync(out,{recursive:true});
const written=[];
for(const changed of sources) {
const source=program.getSourceFile(resolve(root,`ai-harness/server/src/${changed}.ts`));assert(source);
const result=program.emit(source,(name,data)=>{
 assert(sources.flatMap(s=>[s+'.js',s+'.d.ts']).includes(basename(name)));
 writeFileSync(resolve(out,basename(name)),data);written.push(basename(name));
});
assert(!result.emitSkipped && result.diagnostics.length===0);
}
assert.deepEqual(written.sort(),sources.flatMap(s=>[s+'.js',s+'.d.ts']).sort());
console.log(JSON.stringify({result:'PASS',compiler:ts.version,typecheck:'current server source',emittedOnly:written,activeFrontierSourceChanged:false}));
