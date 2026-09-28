import test from 'node:test';
import assert from 'node:assert/strict';
import {randomUUID,createHash} from 'node:crypto';
import {mkdtempSync,readFileSync,readdirSync,rmSync,chmodSync} from 'node:fs';
import {join} from 'node:path';
import {createGateway} from '../src/gateway.js';
import {createOwnedProviderCapture} from '../src/provider-diagnostics.js';
import {codexProvider} from '../src/codex-provider.js';
import {prepareMimo,MimoError} from '../src/mimo.js';
import {MIMO_MODEL,MIMO_RUNTIME,MIMO_ARTIFACT_REVISION,MIMO_ARTIFACT_MANIFEST_SHA256,type MimoQualification} from '../src/mimo.js';
const d = 'a'.repeat(64);
const qualification = (): MimoQualification => ({ qualified: true, evidenceSha256: d, identity: {
 model: MIMO_MODEL, runtimeRevision: MIMO_RUNTIME, runtimeBuildSha256: d, artifactRevision: MIMO_ARTIFACT_REVISION, artifactManifestSha256: MIMO_ARTIFACT_MANIFEST_SHA256,
 loadedTensorMetadataSha256: d, loadedTokenizerSha256: d, loadedTemplateSha256: d, serverInstance:'fixture-native', serverGeneration:'fixture-generation', actualSlotContext:950000,maxOutputTokens:65536,
 parallel:1,contextShift:false,speculative:false,mtp:false,multimodal:false,assistantPrefill:false,jinja:true,kvUnified:false,swaFull:false },
 checks:{artifactBytes:true,nativePrecision:true,allocation:true,reserves:true,templateAndTokenizer:true,textArrayRendering:true,admissionBound:{basis:"pinned-source-s-minus-one",arithmeticFixtures:true,shortNativeCountUsageMatch:true},generationCeiling:{requestedMaxTokens:65536,requestedCeilingAccepted:true,largestCompletedOutputTokens:10},reasoningAndTools:true,singleOwner:true}});


test('model budgets, tokenizer, reasoning and compaction are deliberate per provider',()=>{
 assert.deepEqual(codexProvider('qwen3.8-27b'),{model:'qwen3.8-27b',contextWindow:480000,maxOutputTokens:65536,autoCompactTokenLimit:400000,reasoning:'none',parallelToolCalls:true,tokenizer:'qwen-native-tokenize'});
 const m=codexProvider(MIMO_MODEL);assert.equal(m.contextWindow,950000);assert.equal(m.reasoning,'mimo-plaintext');assert.equal(m.parallelToolCalls,false);assert.throws(()=>codexProvider('hosted'));
});
test('static MiMo validation sites preserve strict rejection and reasoning',()=>{
 const base={model:MIMO_MODEL,messages:[{role:'user',content:'fixture'}],max_tokens:100};
 for(const [field,value,rule] of [['parallel_tool_calls',true,'serial_tool_calls_required'],['tool_choice','none','auto_tool_choice_required'],['private-model-argument',true,'request_fields']] as const) {
  assert.throws(()=>prepareMimo({...base,[field]:value}),(e:any)=>e instanceof MimoError && e.code==='mimo_invalid_request'&&e.rule===rule);
 }
 const p=prepareMimo({...base,messages:[{role:'assistant',content:'actual answer',reasoning_content:'actual reason'},{role:'user',content:'next'}]});assert.equal((p.body.messages as any)[0].reasoning_content,'actual reason');assert.equal((p.body.chat_template_kwargs as any).enable_thinking,true);
});
test('owned raw PRE-normalization capture survives a strict invalid MiMo request and settles without dispatch',async()=>{
 const captures:any[]=[],failures:any[]=[],owners:any[]=[];
 const g=createGateway({upstreamKey:'fixture-secret',ownership:{recoveryReady:true,onRequestState:r=>owners.push(r)},diagnostics:{capture:e=>captures.push(e),onFailure:e=>failures.push(e)},availability:()=>({state:'available',dispatch:'allow'}),frontier:{provider:'mimo',contextWindow:950000,qualification:qualification(),capacity:{published:1048576,configured:950000,allocated:950000,occupiedTested:16384},upstreamKey:'fixture',observe:async()=>{throw Error('must not count');},serialCompletionQualified:true,onRequestState:()=>{}}});
 const session=randomUUID(),token=g.issueToken(session);const raw=' {"model":"mimo-v2.6-pro-rl", "messages":[{"role":"user","content":"private original"}], "max_tokens":100,"parallel_tool_calls":true} ';
 try {const r=await g.app.inject({method:'POST',url:'/frontier/v1/chat/completions',headers:{authorization:`Bearer ${token}`,'content-type':'application/json'},payload:raw});assert.equal(r.statusCode,400);assert.equal(captures[0].bytes.toString(),raw);assert.equal(captures[0].phase,'pre_normalization');assert.equal(failures[0].rule,'serial_tool_calls_required');assert.equal(failures[0].requestId,captures[0].requestId);assert.doesNotMatch(JSON.stringify(failures),/private original/);assert.equal(owners.at(-1).state,'settled');assert.equal(await g.confirmSettlement({sessionId:session}),true);assert.equal(g.frontierSnapshot().state,'idle');}finally{await g.close();}
});
test('private sink captures only selected session with byte limit and hashes; no ambient enablement',()=>{
 // Use an existing owner-private ancestry; system /tmp may be world writable.
 const directory=mkdtempSync(join(process.cwd(),'.capture-fixture-'));chmodSync(directory,0o700);
 const session=randomUUID(),requestId=randomUUID();const capture=createOwnedProviderCapture(directory,session,4);
 try{capture.capture({requestId,sessionId:randomUUID(),model:MIMO_MODEL,phase:'provider_sse',bytes:Buffer.from('skip')});capture.capture({requestId,sessionId:session,model:MIMO_MODEL,phase:'provider_sse',bytes:Buffer.from('real')});capture.capture({requestId,sessionId:session,model:MIMO_MODEL,phase:'provider_sse',bytes:Buffer.from('overflow')});capture.close();const lines=readFileSync(join(directory,'capture-index.jsonl'),'utf8').trim().split('\n').map(x=>JSON.parse(x));assert.equal(lines.length,2);assert.equal(lines[0].sha256,createHash('sha256').update('real').digest('hex'));assert.equal(lines[1].complete,false);assert.equal(readdirSync(directory).length,2);}finally{capture.close();rmSync(directory,{recursive:true,force:true});}
});
