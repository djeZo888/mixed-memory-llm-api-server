import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer, type ServerResponse } from 'node:http';
import { setTimeout as delay } from 'node:timers/promises';
import { createHash } from 'node:crypto';
import { createGateway, type LaneState } from '../src/gateway.js';
import { FRONTIER_MODEL, type FrontierRecord } from '../src/frontier.js';
import { MIMO_MODEL, MIMO_RUNTIME, MIMO_ARTIFACT_REVISION, MIMO_ARTIFACT_MANIFEST_SHA256, prepareMimo, type MimoQualification } from '../src/mimo.js';
import { observeMimoNative, validateMimoIntegration, type MimoFrontierOptions } from '../src/mimo-frontier.js';
import { activeFrontierSelection } from '../src/active-frontier.js';
const d = 'a'.repeat(64);
const proof = (): MimoQualification => ({ qualified: true, evidenceSha256: d, identity: {
 model: MIMO_MODEL, runtimeRevision: MIMO_RUNTIME, runtimeBuildSha256: d, artifactRevision: MIMO_ARTIFACT_REVISION, artifactManifestSha256: MIMO_ARTIFACT_MANIFEST_SHA256,
 loadedTensorMetadataSha256: d, loadedTokenizerSha256: d, loadedTemplateSha256: d, serverInstance:'fixture-native', serverGeneration:'fixture-generation', actualSlotContext:131072,maxOutputTokens:65536,
 parallel:1,contextShift:false,speculative:false,mtp:false,multimodal:false,assistantPrefill:false,jinja:true,kvUnified:false,swaFull:false },
 checks:{artifactBytes:true,nativePrecision:true,allocation:true,reserves:true,templateAndTokenizer:true,textArrayRendering:true,admissionBound:{basis:"pinned-source-s-minus-one",arithmeticFixtures:true,shortNativeCountUsageMatch:true},generationCeiling:{requestedMaxTokens:65536,requestedCeilingAccepted:true,largestCompletedOutputTokens:10},reasoningAndTools:true,singleOwner:true}});
const body = (extra = {}) => ({ model:MIMO_MODEL,messages:[{role:'user',content:'Review fixture'}],max_tokens:512,...extra });
const frame = (v: unknown) => `data: ${typeof v === 'string' ? v : JSON.stringify(v)}\n\n`;
const base = {id:'chatcmpl-fixture',model:MIMO_MODEL,object:'chat.completion.chunk'};
const completeStream = (tool=false) => [
 {...base,choices:[{index:0,delta:tool ? {reasoning_content:'reason',tool_calls:[{index:0,id:'call-native',type:'function',function:{name:'lookup',arguments:'{"query":"x"}'}}]} : {reasoning_content:'reason',content:'verified'},finish_reason:null}]},
 {...base,choices:[{index:0,delta:{},finish_reason:tool?'tool_calls':'stop'}]},
 {...base,choices:[],usage:{prompt_tokens:100,completion_tokens:10,total_tokens:110}}, '[DONE]',
].map(frame).join('');
async function until(fn:()=>boolean) { for(let i=0;i<200;i++){if(fn())return;await delay(5);}throw Error('fixture timeout'); }
async function fixture(initial:Record<string,LaneState>={}, override:Partial<MimoFrontierOptions>={}) {
 const counts:string[]=[], requests:{body:string;response:ServerResponse}[]=[],records:FrontierRecord[]=[],serviceIds:string[]=[],states={...initial};
 const backend=createServer(async(req,res)=>{const chunks=[];for await(const c of req)chunks.push(c);const raw=Buffer.concat(chunks).toString();
  assert.equal(req.headers.authorization,'Bearer fixture-private-key');
  if(req.url==='/v1/chat/completions/input_tokens'){counts.push(raw);res.end('{"input_tokens":100}');return;}
  assert.equal(req.url,'/v1/chat/completions');requests.push({body:raw,response:res});
 });
 await new Promise<void>(r=>backend.listen(0,'127.0.0.1',r));
 const origin=`http://127.0.0.1:${(backend.address() as any).port}`;
 const gateway=createGateway({upstreamKey:'qwen-fixture',availability:id=>{serviceIds.push(id);return {state:'available',dispatch:'allow'};},initialLaneStates:initial,onLaneState:(a,s)=>{states[a]=s;},activeTimeoutMs:1000,
 frontier:{provider:'mimo',contextWindow:131072,qualification:proof(),capacity:{published:1048576,configured:131072,allocated:131072,occupiedTested:4096},upstreamKey:'fixture-private-key',observe:async()=>proof().identity,serialCompletionQualified:true,onRequestState:r=>records.push(r),fixtureUrl:origin+'/v1',...override}});
 const url=await gateway.app.listen({host:'127.0.0.1',port:0}),token=gateway.issueToken('fixture-session');
 const send=(v=body(),signal?:AbortSignal)=>fetch(url+'/frontier/v1/chat/completions',{method:'POST',headers:{authorization:`Bearer ${token}`,'content-type':'application/json'},body:JSON.stringify(v),signal});
 const close=async()=>{await gateway.close();backend.closeAllConnections();await new Promise<void>(r=>backend.close(()=>r()));};
 return {gateway,send,close,counts,requests,records,states,serviceIds,token};
}
test('one shared owner survives GLM/MiMo alias switch and restart; no unrelated clear',async t=>{
 for(const alias of [FRONTIER_MODEL,MIMO_MODEL])for(const state of ['active','quarantined'] as const){
  const f=await fixture({[alias]:state});t.after(f.close);
  assert.equal(f.gateway.frontierSnapshot().state,'quarantined');
  assert.equal((await f.send()).status,503);assert.equal(f.counts.length,0);assert.equal(f.requests.length,0);
  f.gateway.reconcileAfterOwnerSettlement(['qwen3.8-27b']);assert.equal(f.gateway.frontierSnapshot().state,'quarantined');
  assert.equal(f.gateway.reconcileAfterOwnerSettlement([FRONTIER_MODEL]),false);
  assert.equal(f.gateway.reconcileAfterOwnerSettlement([MIMO_MODEL]),false);
 }
});
test('canonical count bytes equal dispatch, actual selected service, validated serial completion releases existing lane',async t=>{
 const f=await fixture();t.after(f.close);
 const pending=f.send();await until(()=>f.requests.length===1);
 assert.equal(f.counts[0],f.requests[0]!.body);assert.equal(f.gateway.frontierSnapshot().model,MIMO_MODEL);
 assert.ok(f.serviceIds.includes(MIMO_MODEL));assert.ok(!f.serviceIds.includes(FRONTIER_MODEL));
 const snapshot=f.gateway.frontierSnapshot();assert.deepEqual(snapshot.capacity,{published:1048576,configured:131072,allocated:131072,occupiedTested:4096});
 f.requests[0]!.response.writeHead(200,{'content-type':'text/event-stream'});f.requests[0]!.response.end(completeStream());
 const r=await pending;assert.equal(r.status,200);assert.match(await r.text(),/\[DONE\]/);
 await until(()=>f.gateway.frontierSnapshot().state==='idle');
 const record=f.records.at(-1)!;assert.equal(record.state,'settled');assert.equal(record.model,MIMO_MODEL);assert.equal(record.backendResponseId,'chatcmpl-fixture');assert.equal(record.serverGeneration,'fixture-generation');assert.match(record.canonicalRequestSha256!,/^[a-f0-9]{64}$/);
 assert.equal(f.states[FRONTIER_MODEL],'idle');assert.equal(f.states[MIMO_MODEL],undefined);
});
test('full tool stream is retained until HTTP drain; incomplete EOF quarantines without tool execution/replay',async t=>{
 const f=await fixture();t.after(f.close);
 const v=body({tools:[{type:'function',function:{name:'lookup',strict:true,parameters:{type:'object',properties:{query:{type:'string'}},required:['query'],additionalProperties:false}}}]});
 const pending=f.send(v);await until(()=>f.requests.length===1);
 const response=f.requests[0]!.response;response.writeHead(200,{'content-type':'text/event-stream'});
 response.write(completeStream(true).replace('data: [DONE]\n\n',''));response.end();
 const result=await pending;assert.equal(result.status,502);assert.ok(!(await result.text()).includes('call-native'));
 assert.equal(f.gateway.frontierSnapshot().state,'quarantined');assert.equal((await f.send()).status,503);assert.equal(f.requests.length,1);
});
test('consumer disconnect keeps native drain owner; valid completion allows next serial request',async t=>{
 const f=await fixture();t.after(f.close);const abort=new AbortController();const pending=f.send(body(),abort.signal).catch(()=>null);
 await until(()=>f.requests.length===1);abort.abort();await pending;await delay(20);
 assert.equal(f.gateway.frontierSnapshot().state,'active');
 f.requests[0]!.response.writeHead(200,{'content-type':'text/event-stream'});f.requests[0]!.response.end(completeStream());
 await until(()=>f.gateway.frontierSnapshot().state==='idle');assert.equal(f.requests.length,1);
});
test('identity change after drain quarantines, never releases based on HTTP alone',async t=>{
 let calls=0;const f=await fixture({}, {observe:async()=>({...proof().identity,serverGeneration:++calls>3?'changed':'fixture-generation'})});t.after(f.close);
 const pending=f.send();await until(()=>f.requests.length===1);f.requests[0]!.response.writeHead(200,{'content-type':'text/event-stream'});f.requests[0]!.response.end(completeStream());
 assert.equal((await pending).status,502);assert.equal(f.gateway.frontierSnapshot().state,'quarantined');
});
test('native observations separate static provenance from props/slots and reject capacity/template drift',()=>{
 const pins={buildInfo:'pinned-build',modelPath:'/models/mimo.gguf',chatTemplateSha256:createHash('sha256').update('template').digest('hex'),toolTemplateSha256:null};
 const props={model_alias:MIMO_MODEL,build_info:pins.buildInfo,model_path:pins.modelPath,is_sleeping:false,total_slots:1,default_generation_settings:{n_ctx:131072},chat_template:'template',modalities:{vision:false,video:false,audio:false}};
 const slots=[{id:0,n_ctx:131072,speculative:false,is_processing:true}];
 assert.deepEqual(observeMimoNative(props,slots,proof(),pins),proof().identity); // processing is not GPU idle evidence
 assert.throws(()=>observeMimoNative({...props,model_alias:FRONTIER_MODEL},slots,proof(),pins));
 assert.throws(()=>observeMimoNative(props,[{...slots[0],n_ctx:1048576}],proof(),pins));
 assert.throws(()=>observeMimoNative(props,[{...slots[0],prompt:'must not retain history'}],proof(),pins));
 const manifest={serviceId:MIMO_MODEL,privatePort:30012,full17ToolRosterQualified:true,strictNestedSchemasQualified:true,serialCompletionQualified:true,qualification:{...proof(),identity:{...proof().identity,loadedTemplateSha256:pins.chatTemplateSha256}},nativePins:pins,capacity:{published:1048576,configured:131072,allocated:131072,occupiedTested:4096}};
 assert.equal(validateMimoIntegration(manifest).qualification.identity.actualSlotContext,131072);
 assert.throws(()=>validateMimoIntegration({...manifest,full17ToolRosterQualified:false}));
 assert.throws(()=>activeFrontierSelection({model:MIMO_MODEL,mimoEnabled:false}));
});
test('strict nested schemas preserved; false storage discarded before canonical count, unsupported options rejected',()=>{
 const tools=[{type:'function',function:{name:'lookup',strict:false,parameters:{type:'object',properties:{nested:{oneOf:[{type:'string'},{type:'object',additionalProperties:{type:'array',items:{type:'number'}}}]}}}}}];
 const prepared=prepareMimo(body({tools,store:false}));assert.deepEqual(prepared.body.tools,tools);assert.equal(prepared.body.store,undefined);
 assert.throws(()=>prepareMimo(body({store:true})));assert.throws(()=>prepareMimo(body({tools:[{type:'function',function:{...tools[0]!.function,strict:'true'}}]})));
});

test('selected registry reports one actual frontier and retains rollback config',async()=>{
 const {selectRegistryFrontier,validateSystemRegistry}=await import('../src/system-registry.js');
 const {readFileSync}=await import('node:fs');
 const registry=validateSystemRegistry(JSON.parse(readFileSync(new URL('../../config/system-registry.json',import.meta.url),'utf8')));
 const selected=selectRegistryFrontier(registry,MIMO_MODEL);
 assert.equal(selected.services.filter(s=>s.endpoint_ref==='frontier-private').length,1);
 assert.ok(selected.services.some(s=>s.id===MIMO_MODEL&&s.observation_key===MIMO_MODEL));assert.ok(!selected.services.some(s=>s.id===FRONTIER_MODEL));
 assert.ok(registry.services.some(s=>s.id===FRONTIER_MODEL));
});
test('granular qualification cannot mistake arithmetic or requested ceiling for native occupied/output proof',()=>{
 const q=proof();assert.equal(q.checks.generationCeiling.largestCompletedOutputTokens,10);assert.equal(q.checks.generationCeiling.requestedMaxTokens,65536);
 const invalid={...q,checks:{...q.checks,admissionBound:true}};
 assert.throws(()=>validateMimoIntegration({qualification:invalid}));
});

test('durable unresolved request blocks a switch even if lane row was missing',async()=>{
 const gateway=createGateway({upstreamKey:'fixture',selectedFrontierModel:MIMO_MODEL,initialFrontierOwnerModel:FRONTIER_MODEL,
 frontier:{provider:'mimo',contextWindow:131072,qualification:proof(),capacity:{published:1048576,configured:131072,allocated:131072,occupiedTested:4096},upstreamKey:'fixture',observe:async()=>proof().identity,serialCompletionQualified:true,onRequestState:()=>{}}});
 try {assert.equal(gateway.frontierSnapshot().state,'quarantined');assert.equal(gateway.reconcileAfterOwnerSettlement([FRONTIER_MODEL]),false);}
 finally {await gateway.close();}
});
