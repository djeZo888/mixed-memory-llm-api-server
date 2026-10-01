import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,mkdir,readFile,writeFile,rm,realpath} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {PassThrough} from 'node:stream';
import {fileURLToPath} from 'node:url';
import {applicationProxy} from '../../acceptance/compaction/native-adapter/application-proxy.js';
import {OwnedApplicationRunner,observeApplicationIdentity} from '../../acceptance/compaction/native-adapter/process-runner.js';
import {NativeEvidence} from '../../acceptance/compaction/native-adapter/native-evidence.js';
import {consumedTool,validateConsumedFollowup} from '../../acceptance/compaction/native-adapter/consumed-tools.js';
import {sha256,stableJson} from '../../acceptance/compaction/native-adapter/projection.js';
import {AUTHORIZATIONS,reviewedAuthorization} from '../../acceptance/compaction/authorization.mjs';
import {executedImportGraph} from '../../acceptance/compaction/native-adapter/build-closure.mjs';
async function directory(t:any){const root=await realpath(await mkdtemp(join(tmpdir(),'h041-source-completion-')));t.after(()=>rm(root,{recursive:true,force:true}));return root;}
const authority=AUTHORIZATIONS['H041-COMPACTION-CONTINUATION-02'];
function review(){return {authorization:{...authority,windowId:'source-continuation02'},notAfterUtc:authority.capUtc,settlementReserveMs:120000};}
test('SOURCE frozen continuation02 cannot enlarge expiry or revive initial H041',()=>{
 const now=Date.parse(authority.startsUtc)+1,good=review();assert.equal(reviewedAuthorization(good,now).dispatchCutoffAt,Date.parse(authority.capUtc)-120000);
 for(const bad of [{...good,notAfterUtc:'2026-10-01T11:11:07Z'},{...good,settlementReserveMs:119999},{...good,authorization:{...good.authorization,startsUtc:'2026-10-01T09:11:06Z'}},{...good,authorization:{...AUTHORIZATIONS.H041,windowId:'historical'},notAfterUtc:authority.capUtc}])assert.throws(()=>reviewedAuthorization(bad,now));
});
test('SOURCE actual owned Node timeout preserves shutdown reachability and observed exit',async t=>{
 const root=await directory(t),configPath=join(root,'config.json'),marker=join(root,'shutdown'),workerPath=fileURLToPath(new URL('./fixtures/h041-application-worker.mjs',import.meta.url));
 const config=JSON.stringify({marker,handoff:join(root,'handoff')});await writeFile(configPath,config,{mode:0o600});
 const runner=new OwnedApplicationRunner({workerPath,workerSha256:sha256(await readFile(workerPath)),configPath,configSha256:sha256(config),hostPrivate:root,review:review(),operationTimeoutMs:1000});
 await runner.start();const identity=runner.identitySnapshot();assert.equal((await runner.call('echo',{value:'SOURCE'})).pid,identity.pid);
 await assert.rejects(runner.call('stall'),/deadline/);await assert.rejects(runner.call('echo'),/unavailable/);
 const exit=await runner.shutdownAndConfirm();assert.equal(exit.code,0);assert.equal(exit.signal,null);assert.match(await readFile(marker,'utf8'),/actual owned SOURCE/);
 const remaining=await observeApplicationIdentity(identity.pid).catch(()=>undefined);assert.ok(!remaining||remaining.startTicks!==identity.startTicks);
});
test('SOURCE actual process replacement waits old exit and uses new OS identity; no native qualification',async t=>{
 const root=await directory(t),configPath=join(root,'config.json'),workerPath=fileURLToPath(new URL('./fixtures/h041-application-worker.mjs',import.meta.url));const config=JSON.stringify({marker:join(root,'shutdown'),handoff:join(root,'handoff')});await writeFile(configPath,config,{mode:0o600});
 const runner=new OwnedApplicationRunner({workerPath,workerSha256:sha256(await readFile(workerPath)),configPath,configSha256:sha256(config),hostPrivate:root,review:review(),operationTimeoutMs:3000});
 await runner.start();const checkpoint={stateUtf8:'SOURCE parent bytes',stateSha256:sha256('SOURCE parent bytes'),nativeThreadId:'SYNTHETIC-parent'};
 const result=await runner.restart({checkpoint,runId:'SOURCE-run',actionId:'SOURCE-restart',windowId:'source-continuation02',observedSettlements:[]});
 assert.notEqual(result.beforeProcessId,result.afterProcessId);assert.equal(result.afterStateUtf8,checkpoint.stateUtf8);assert.deepEqual(result.replayedActionIds,[]);assert.equal(JSON.parse(result.processRestartReceiptUtf8).oldExit.code,0);
 await runner.shutdownAndConfirm();
});
test('SOURCE receipt rejection after process acquisition cleans exact owner and retains released failure',async t=>{
 const root=await directory(t),profileDir=join(root,'profile'),workspace=join(root,'workspace');for(const p of [profileDir,workspace])await mkdir(p,{mode:0o700});
 let calls=0;const evidence=new NativeEvidence(root,{receiptUtf8:()=>undefined});
 await assert.rejects(evidence.launch('SOURCE-session',{profileDir,workspace},async()=>({stdin:new PassThrough(),stdout:new PassThrough(),exited:new Promise(()=>{}),launchReceipt:Promise.reject(Error('SOURCE invalid capture')),terminateAndConfirm:async()=>{calls++;return true;}})),/failed_released_no_replay/);assert.equal(calls,1);
 await assert.rejects(evidence.close('SOURCE-run','SOURCE-window',[],{sessions:()=>[]} as any),/unconfirmed/);
});
function toolFrames(tool='write_checkpoint_artifact') {
 const args={name:'sensor-policy.json',json:'{"source":"SOURCE"}'},result={contentItems:[{type:'inputText',text:'registered SOURCE result'}],success:true};
 const values=[{method:'item/started',params:{threadId:'SOURCE-thread',turnId:'SOURCE-turn',item:{id:'SOURCE-call',type:'dynamicToolCall',tool,arguments:args,status:'inProgress'}}},{id:7,method:'item/tool/call',params:{threadId:'SOURCE-thread',turnId:'SOURCE-turn',callId:'SOURCE-call',tool,arguments:args}},{id:7,result},{method:'item/completed',params:{threadId:'SOURCE-thread',turnId:'SOURCE-turn',item:{id:'SOURCE-call',type:'dynamicToolCall',tool,arguments:args,success:true,status:'completed'}}}];
 const frames=values.map((value,i)=>{const bytesUtf8=JSON.stringify(value)+'\n';return {value,sequence:i,direction:i===2?'to-native':'from-native',bytesUtf8,sha256:sha256(bytesUtf8)};});
 const settled=[{runId:'SOURCE-window',threadId:'SOURCE-thread',turnId:'SOURCE-turn',callId:'SOURCE-call',name:args.name,artifactId:'SOURCE-artifact',sha256:sha256(args.json),responseSha256:sha256(JSON.stringify(result))}];
 return {args,frames,settled,tool:'write_checkpoint_artifact' as const,threadId:'SOURCE-thread',turnId:'SOURCE-turn',runId:'SOURCE-window'};
}
test('SOURCE artifact followup admits actual consumed result; rejects altered/oracle/foreign/uncompleted carriers',()=>{
 const b=toolFrames(),prefix=[{type:'message',role:'user',content:[{type:'input_text',text:'SOURCE frozen input'}]}];
 const input=[...prefix,{type:'function_call',call_id:'SOURCE-call',name:b.tool,arguments:JSON.stringify(b.args)},{type:'function_call_output',call_id:'SOURCE-call',output:'registered SOURCE result'}];
 assert.doesNotThrow(()=>validateConsumedFollowup(input,prefix,b));assert.equal(consumedTool(b,'SOURCE-call').settled.artifactId,'SOURCE-artifact');
 for(const mutate of [(x:any)=>x.push({type:'message',role:'user',content:[{type:'input_text',text:'ORACLE'}]}),(x:any)=>x[2].output+=' changed',(x:any)=>x[1].name='read_original',(x:any)=>x[0].hidden='ORACLE']){const changed=structuredClone(input);mutate(changed);assert.throws(()=>validateConsumedFollowup(changed,prefix,b));}
 assert.throws(()=>validateConsumedFollowup(input,prefix,{...b,frames:b.frames.slice(0,-1)}));assert.throws(()=>validateConsumedFollowup(input,prefix,{...b,turnId:'FOREIGN'}));
});
test('SOURCE emitted graph must include every imported executable, not any entry.js hash',async t=>{
 const root=await directory(t),base=join(root,'ai-harness/acceptance/compaction/native-adapter');await mkdir(base,{recursive:true});const entry='ai-harness/acceptance/compaction/native-adapter/entry.js',worker='ai-harness/acceptance/compaction/native-adapter/application-worker.js',dependency='ai-harness/acceptance/compaction/native-adapter/dependency.js';
 const contents={[entry]:"import './dependency.js';\n",[worker]:"import './dependency.js';\n",[dependency]:'export const SOURCE=1;\n'};for(const [p,b]of Object.entries(contents))await writeFile(join(root,p),b);
 const files=Object.fromEntries(Object.entries(contents).map(([p,b])=>[p,sha256(b)]));const graph=await executedImportGraph(root,files);assert.ok(graph.imports[entry].includes(dependency));
 const missing={...files};delete missing[dependency];await assert.rejects(executedImportGraph(root,missing),/manifest|layout/);await writeFile(join(root,dependency),'changed');await assert.rejects(executedImportGraph(root,files),/changed/);
});

test('SOURCE delivery03 is separately frozen; old authorization caps are preserved',()=>{
 const a=AUTHORIZATIONS['H041-COMPACTION-DELIVERY-03'];const r={authorization:{...a,windowId:'source-delivery03'},notAfterUtc:a.capUtc,settlementReserveMs:120000};
 const now=Date.parse(a.startsUtc)+1;assert.equal(reviewedAuthorization(r,now).dispatchCutoffAt,Date.parse(a.capUtc)-120000);
 assert.throws(()=>reviewedAuthorization({...r,notAfterUtc:'2026-10-01T13:07:12Z'},now));
 assert.throws(()=>reviewedAuthorization({...r,authorization:{...authority,windowId:'source-02'}},now));
 assert.equal(AUTHORIZATIONS.H041.capUtc,'2026-10-01T10:05:07Z');assert.equal(authority.capUtc,'2026-10-01T11:11:06.096969+00:00');
});
test('SOURCE outer full profile cannot advertise worker capabilities before real worker loader qualification',async()=>{
 const proxy=applicationProxy({} as any,{profile:'h041-full-retention-v1'} as any);
 assert.equal(proxy.enabled,false);assert.deepEqual(proxy.capabilities,[]);
 await assert.rejects(proxy.qualifyWorker(),/genuine_entry_qualification_required/);
 await assert.rejects(proxy.open({runId:'SOURCE'}),/worker_capability_qualification_required/);
 assert.equal(proxy.enabled,false);assert.deepEqual(proxy.capabilities,[]);
});
