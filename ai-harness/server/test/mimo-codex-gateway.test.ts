import test from 'node:test';
import assert from 'node:assert/strict';
import {createServer,type ServerResponse} from 'node:http';
import {setTimeout as delay} from 'node:timers/promises';
import {createGateway} from '../src/gateway.js';
import {MIMO_MODEL,MIMO_RUNTIME,MIMO_ARTIFACT_REVISION,MIMO_ARTIFACT_MANIFEST_SHA256,type MimoQualification} from '../src/mimo.js';
const d='a'.repeat(64);
const proof=():MimoQualification=>({qualified:true,evidenceSha256:d,identity:{model:MIMO_MODEL,runtimeRevision:MIMO_RUNTIME,runtimeBuildSha256:d,artifactRevision:MIMO_ARTIFACT_REVISION,artifactManifestSha256:MIMO_ARTIFACT_MANIFEST_SHA256,loadedTensorMetadataSha256:d,loadedTokenizerSha256:d,loadedTemplateSha256:d,serverInstance:'current-native',serverGeneration:'current-generation',actualSlotContext:480000,maxOutputTokens:65536,parallel:1,contextShift:false,speculative:false,mtp:false,multimodal:false,assistantPrefill:false,jinja:true,kvUnified:true,swaFull:false},checks:{artifactBytes:true,nativePrecision:true,allocation:true,reserves:true,templateAndTokenizer:true,textArrayRendering:true,admissionBound:{basis:'pinned-source-s-minus-one',arithmeticFixtures:true,shortNativeCountUsageMatch:true},generationCeiling:{requestedMaxTokens:65536,requestedCeilingAccepted:true,largestCompletedOutputTokens:20},reasoningAndTools:true,singleOwner:true}});
const user={type:'message',role:'user',content:[{type:'input_text',text:'Use fixture tool'}]};
const request={model:MIMO_MODEL,stream:true,store:false,input:[user],tools:[{type:'function',name:'lookup',description:'Fixture tool',strict:true,parameters:{type:'object',properties:{},additionalProperties:false}}],tool_choice:'auto',parallel_tool_calls:true};
async function until(f:()=>boolean){for(let i=0;i<300;i++){if(f())return;await delay(5);}throw Error('fixture timeout');}
const base={id:'chatcmpl-fixture',model:MIMO_MODEL,object:'chat.completion.chunk'};
const frame=(v:unknown)=>`data: ${typeof v==='string'?v:JSON.stringify(v)}\n\n`;
test('Codex MiMo shares serial admission/count bytes, roundtrips actual reasoning and holds native drain after revoke',async t=>{
 const counts:string[]=[],calls:{body:string;res:ServerResponse}[]=[],owners:any[]=[],captures:any[]=[],diagnostics:any[]=[];
 const backend=createServer(async(req,res)=>{const chunks=[];for await(const c of req)chunks.push(c);const raw=Buffer.concat(chunks).toString();assert.equal(req.headers.authorization,'Bearer fixture-mimo');if(req.url?.endsWith('/input_tokens')){counts.push(raw);res.end('{"input_tokens":100}');}else{calls.push({body:raw,res});}});
 await new Promise<void>(r=>backend.listen(0,'127.0.0.1',r));const backendUrl=`http://127.0.0.1:${(backend.address() as any).port}/v1`;
 let scope=true,currentCalls=0;const g=createGateway({upstreamKey:'qwen-key',ownership:{recoveryReady:true,onRequestState:r=>owners.push(r)},availability:()=>({state:'available',dispatch:'allow'}),responses:{enabled:true,frontierAcceptance:id=>scope&&id==='owned-codex',countQwen:async()=>{throw Error('Qwen tokenizer forbidden on MiMo');},onDiagnostic:e=>diagnostics.push(e)},diagnostics:{capture:e=>captures.push(e)},frontier:{provider:'mimo',contextWindow:480000,qualification:proof(),capacity:{published:1048576,configured:480000,allocated:480000,occupiedTested:16384},upstreamKey:'fixture-mimo',fixtureUrl:backendUrl,serialCompletionQualified:true,onRequestState:()=>{},observe:async()=>{throw Error('historical identity observer forbidden');},current:async()=>{currentCalls++;return {qualification:proof(),observe:async()=>proof().identity};}}});
 t.after(async()=>{await g.close();backend.closeAllConnections();await new Promise<void>(r=>backend.close(()=>r()));});
 const url=await g.app.listen({host:'127.0.0.1',port:0}),token=g.issueToken('owned-codex','codex');
 const send=(body:any)=>fetch(url+'/v1/responses',{method:'POST',headers:{authorization:`Bearer ${token}`,'content-type':'application/json'},body:JSON.stringify(body)});
 const stranger=g.issueToken('other-codex','codex');const refused=await fetch(url+'/v1/responses',{method:'POST',headers:{authorization:`Bearer ${stranger}`,'content-type':'application/json'},body:JSON.stringify(request)});assert.equal(refused.status,503);assert.equal(counts.length,0);
 const first=send(request);await until(()=>calls.length===1);assert.equal(counts[0],calls[0].body);const normalized=JSON.parse(calls[0].body);assert.equal(normalized.parallel_tool_calls,false);assert.equal(normalized.chat_template_kwargs.enable_thinking,true);assert.equal(normalized.max_tokens,65536);
 const stream=[{...base,choices:[{index:0,delta:{reasoning_content:'actual native reasoning',tool_calls:[{index:0,id:'call-one',type:'function',function:{name:'lookup',arguments:'{}'}}]},finish_reason:null}]},{...base,choices:[{index:0,delta:{},finish_reason:'tool_calls'}]},{...base,choices:[],usage:{prompt_tokens:100,completion_tokens:20,total_tokens:120}},'[DONE]'].map(frame).join('');calls[0].res.setHeader('content-type','text/event-stream');calls[0].res.write(stream);await delay(10);assert.equal(g.sessionWork('owned-codex')[0].state,'accepted');calls[0].res.end();const result=await (await first).text();const terminal=result.split('\n').filter(x=>x.startsWith('data:')).map(x=>JSON.parse(x.slice(5))).find(x=>x.type==='response.completed');assert.ok(terminal);assert.equal(await g.confirmSettlement({sessionId:'owned-codex'}),true);
 const output=terminal.response.output;assert.ok(output.some((v:any)=>v.type==='reasoning'&&v.content[0].text==='actual native reasoning'&&v.encrypted_content===null));
 const second=send({...request,input:[user,...output,{type:'function_call_output',call_id:'call-one',output:'real tool result'}]});await until(()=>calls.length===2);assert.equal(counts[1],calls[1].body);const history=JSON.parse(calls[1].body).messages;const assistant=history.find((m:any)=>m.role==='assistant');assert.equal(assistant.reasoning_content,'actual native reasoning');assert.equal(assistant.tool_calls[0].id,'call-one');assert.equal(history.at(-1).tool_call_id,'call-one');
 scope=false;g.revokeSession('owned-codex');assert.equal(await g.confirmSettlement({sessionId:'owned-codex'}),false);calls[1].res.setHeader('content-type','text/event-stream');calls[1].res.end([{...base,choices:[{index:0,delta:{reasoning_content:'continued reasoning',content:'done'},finish_reason:null}]},{...base,choices:[{index:0,delta:{},finish_reason:'stop'}]},{...base,choices:[],usage:{prompt_tokens:100,completion_tokens:20,total_tokens:120}},'[DONE]'].map(frame).join(''));await (await second).text();await until(()=>g.sessionWork('owned-codex').length===0);assert.equal(await g.confirmSettlement({sessionId:'owned-codex'}),true);assert.equal(currentCalls,2);assert.equal(calls.length,2);assert.ok(captures.some(x=>x.phase==='provider_sse'));assert.ok(diagnostics.some(x=>x.diagnostic.type==='provider_finish'));assert.equal(owners.at(-1).accounting.inputTokens,100);
});
test('MiMo source descriptor does not open frontier without independent acceptance and existing hold',async()=>{
 const g=createGateway({upstreamKey:'q',ownership:{recoveryReady:true,onRequestState:()=>{}},responses:{enabled:true,countQwen:async()=>({inputTokens:1,contextWindow:480000})}});try{const t=g.issueToken('codex','codex');const r=await g.app.inject({method:'POST',url:'/v1/responses',headers:{authorization:`Bearer ${t}`},payload:request});assert.equal(r.statusCode,503);assert.equal(r.json().error.code,'codex_frontier_unqualified');assert.equal(g.sessionWork('codex').length,0);}finally{await g.close();}
});


test('old 950K MiMo gateway configuration rejects before native count or inference under 480K descriptor', async () => {
 let countOrObserve = 0;
 const old = proof(); old.identity.actualSlotContext = 950000;
 const g = createGateway({upstreamKey:'fixture',ownership:{recoveryReady:true,onRequestState:()=>{}},availability:()=>({state:'available',dispatch:'allow'}),
  responses:{enabled:true,frontierAcceptance:()=>true,countQwen:async()=>{throw Error('not Qwen');}},
  frontier:{provider:'mimo',contextWindow:950000,qualification:old,
   capacity:{published:1048576,configured:950000,allocated:950000,occupiedTested:9635},
   upstreamKey:'fixture',serialCompletionQualified:true,onRequestState:()=>{},
   observe:async()=>{countOrObserve++;throw Error('must reject before observe/count');}}});
 try {
  const token=g.issueToken('owned','codex');
  const response=await g.app.inject({method:'POST',url:'/v1/responses',headers:{authorization:`Bearer ${token}`},payload:request});
  assert.equal(response.statusCode,503); assert.equal(countOrObserve,0);
  assert.equal(await g.confirmSettlement({sessionId:'owned'}),true);
 } finally {await g.close();}
});

test('480K MiMo retains the exact S-1 admission boundary and full 65536 output reserve', async () => {
 const {prepareMimo,countMimo}=await import('../src/mimo.js');
 const q=proof(), prepared=prepareMimo({model:MIMO_MODEL,messages:[{role:'user',content:'synthetic boundary'}],max_tokens:65536});
 const count=(tokens:number)=>countMimo(prepared,q,{observe:async()=>q.identity,
  post:async()=>new Response(JSON.stringify({input_tokens:tokens}))},new AbortController().signal);
 assert.equal((await count(414463)).promptTokens,414463);
 await assert.rejects(count(414464),{code:'mimo_context_full'});
 assert.equal(prepared.outputTokens,65536);
 const stale={...q.identity,actualSlotContext:950000};
 await assert.rejects(countMimo(prepared,q,{observe:async()=>stale,
  post:async()=>{throw Error('must reject stale identity before count');}},new AbortController().signal),{code:'mimo_identity_mismatch'});
});
