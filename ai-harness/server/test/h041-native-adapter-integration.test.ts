import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile, mkdtemp, mkdir, realpath, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { PassThrough } from 'node:stream';
import { DispatchGuard } from '../../acceptance/compaction/native-adapter/dispatch-guard.js';
import { NativeEvidence } from '../../acceptance/compaction/native-adapter/native-evidence.js';
import { parentManifest } from '../../acceptance/compaction/native-adapter/parent-projection.js';
import { validateOriginalFollowup, consumedOriginalTrace } from '../../acceptance/compaction/native-adapter/retrieval.js';
import { createArtifactSink } from '../../acceptance/compaction/native-adapter/artifact-sink.js';
import { collectContinuationArtifacts } from '../../acceptance/compaction/native-adapter/artifacts.js';
import { Store } from '../src/store.js';
import { Files } from '../src/files.js';
import { translateResponses } from '../src/codex-responses.js';
import { sha256, stableJson } from '../../acceptance/compaction/native-adapter/projection.js';
// @ts-ignore JavaScript acceptance module is exercised independently at runtime.
import { reviewedAuthorization } from '../../acceptance/compaction/authorization.mjs';
// @ts-ignore independent JavaScript verifier.
import { verifyObservedOwnedClose } from '../../acceptance/compaction/owned-close-verifier.mjs';
const native=JSON.parse(await readFile(new URL('./fixtures/codex/native-requests.json',import.meta.url),'utf8'))[0].body;
const review={authorization:{task:'H041',startsUtc:'2026-10-01T08:05:07Z',capUtc:'2026-10-01T10:05:07Z',windowId:'h041-source-fixture'},notAfterUtc:'2026-10-01T10:05:07Z',settlementReserveMs:120000};
test('SOURCE frozen H041 window/common reserve rejects caller enlargement and expired H040',()=>{
  const now=Date.parse('2026-10-01T09:00:00Z'),r=reviewedAuthorization(review,now);
  assert.equal(r.dispatchCutoffAt,Date.parse(review.notAfterUtc)-120000);
  for(const bad of [{...review,settlementReserveMs:75000},{...review,notAfterUtc:'2026-10-02T10:05:07Z'},{...review,authorization:{...review.authorization,capUtc:'2026-10-02T10:05:07Z'}}])assert.throws(()=>reviewedAuthorization(bad,now));
  assert.throws(()=>reviewedAuthorization({...review,authorization:{task:'H040',startsUtc:'2026-10-01T02:26:10Z',capUtc:'2026-10-01T04:26:10Z',windowId:'old'}},now));
});
test('SYNTHETIC parent approval from independent persisted state rejects hidden provider history before count',async t=>{
  const root=await realpath(await mkdtemp(join(tmpdir(),'h041-parent-gate-')));t.after(()=>rm(root,{recursive:true,force:true}));
  const raw={...structuredClone(native),tools:[],input:[{type:'message',role:'user',content:[{type:'input_text',text:'frozen owned append'}]}],client_metadata:{thread_id:'synthetic-parent',turn_id:'synthetic-turn'}};
  const envelope=Object.fromEntries(Object.entries(raw).filter(([k])=>!['input','tools'].includes(k)));
  const stateUtf8='{"type":"session_meta","payload":{"id":"synthetic-parent"}}\n';
  const manifest=parentManifest({capturedBy:'host',nativeThreadId:'synthetic-parent',stateUtf8,stateSha256:sha256(stateUtf8),receiptUtf8:'SOURCE',receiptSha256:sha256('SOURCE'),sourceRef:'synthetic'},'frozen owned append','message',{format:'h041-persisted-parent-input-v1',prefixInput:[],envelope,compactionPrompt:'frozen compact'});
  let counts=0;
  for(const hidden of [false,true]){
    const dir=join(root,String(hidden));await mkdir(dir,{mode:0o700});const guard=new DispatchGuard(dir);
    guard.register({sessionId:'synthetic-session',actionId:'synthetic-action',runId:'synthetic-run',mode:'main',manifest,expiresAt:Date.now()+5000,signal:new AbortController().signal,identity:()=>({nativeThreadId:'synthetic-parent',nativeTurnId:'synthetic-turn',activeRunId:'synthetic-run'})});
    const body=structuredClone(raw);if(hidden)body.input.push({type:'message',role:'user',content:[{type:'input_text',text:'UNAPPROVED_ORACLE_CARRIER'}]});
    guard.capture({sessionId:'synthetic-session',requestId:String(hidden),model:raw.model,phase:'pre_normalization',bytes:Buffer.from(JSON.stringify(body))} as any);
    const call=guard.wrap(async()=>{counts++;return {inputTokens:1,contextWindow:480000} as any;});
    const promise=call({...translateResponses(body).body,model:raw.model},{alias:raw.model} as any,'SYNTHETIC',new AbortController().signal,{requestId:String(hidden)} as any);
    if(hidden)await assert.rejects(promise,/frozen_complete_input/);else await promise;
  }
  assert.equal(counts,1); // SOURCE counter invocations, not native token measurements.
});
test('SYNTHETIC receipt-shaped process cannot enter genuine native evidence; cleanup is attempted',async t=>{
  const root=await realpath(await mkdtemp(join(tmpdir(),'h041-brand-denial-')));t.after(()=>rm(root,{recursive:true,force:true}));
  const profileDir=join(root,'profile'),workspace=join(root,'workspace');for(const p of[profileDir,workspace])await mkdir(p,{mode:0o700});
  let cleanup=0;const registry=new NativeEvidence(root,{receiptUtf8:()=>'{"schema":"codex-launch-v1"}'});
  await assert.rejects(registry.launch('synthetic-session',{profileDir,workspace},async()=>({stdin:new PassThrough(),stdout:new PassThrough(),exited:Promise.resolve(),launchReceipt:Promise.resolve({schema:'codex-launch-v1'} as any),terminateAndConfirm:async()=>{cleanup++;return true;}})),/failed_released_no_replay/);
  assert.equal(cleanup,1);
});
test('SYNTHETIC retrieval followup requires exact consumed call/result and preserves original prefix',()=>{
  const prefix=[{type:'message',role:'user',content:[{type:'input_text',text:'frozen summary'}]}],args={reference:'r1',offset:0,limit:8192};
  const request={id:7,method:'item/tool/call',params:{callId:'call1',tool:'read_original',threadId:'t',turnId:'v',arguments:args}},result={id:7,result:{contentItems:[{type:'inputText',text:'original bytes'}],success:true}},done={method:'item/completed',params:{item:{id:'call1',success:true}}};
  const frames=[{direction:'from-native',value:request,bytesUtf8:JSON.stringify(request)},{direction:'to-native',value:result,bytesUtf8:JSON.stringify(result)},{direction:'from-native',value:done,bytesUtf8:JSON.stringify(done)}];
  const settled=[{callId:'call1',success:true,runId:'run',checkpointId:'checkpoint',threadId:'t',turnId:'v',arguments:args,responseSha256:sha256(JSON.stringify(result.result))}];
  const input=[...prefix,{type:'function_call',call_id:'call1',name:'read_original',arguments:JSON.stringify(args)},{type:'function_call_output',call_id:'call1',output:'original bytes'}];
  validateOriginalFollowup(input,prefix,frames,settled);
  assert.throws(()=>validateOriginalFollowup([...input.slice(0,-1),{...input.at(-1),output:'unobserved answer'}],prefix,frames,settled));
  assert.throws(()=>validateOriginalFollowup(input,prefix,frames,[]));
  const trace=consumedOriginalTrace({frames,settled,originals:[{reference:'r1',bytes:Buffer.from('original bytes')}],scopeId:'scope',checkpointId:'checkpoint',threadId:'t',turnId:'v',runId:'run'});
  assert.equal(trace.calls[0].records[0].sha256,sha256('original bytes'));
  assert.throws(()=>consumedOriginalTrace({frames,settled:[{...settled[0],arguments:{...args,offset:1}}],originals:[{reference:'r1',bytes:Buffer.from('original bytes')}],scopeId:'scope',checkpointId:'checkpoint',threadId:'t',turnId:'v',runId:'run'}));
});
test('SYNTHETIC JSON registrar/finalizer uses actual Store/Files and binds completed assistant bytes',async t=>{
  const root=await realpath(await mkdtemp(join(tmpdir(),'h041-artifact-sink-'))),store=new Store(join(root,'store.sqlite')),files=new Files(join(root,'app'),store);await files.init();
  t.after(async()=>{store.close();await rm(root,{recursive:true,force:true});});const s=store.createSession(undefined,'codex',{engineVersion:'0.158.0'});await files.prepare(s.id,s.workspaceId);store.setNative(s.id,'synthetic-parent','codex');
  const run=store.createRun(store.getSession(s.id),'message','SYNTHETIC continuation',[]);store.updateRun(run.id,'running');store.setNativeState(s.id,'codex',{ownership:'active',activeTurnId:'synthetic-turn',eventCursor:1});const sink=createArtifactSink(store,files);
  for(const [i,name]of ['sensor-policy.json','engineering-calculation.json'].entries())await sink({sessionId:s.id,runId:run.id,threadId:'synthetic-parent',turnId:'synthetic-turn',callId:'synthetic-call'+i,name,jsonUtf8:'{"actual":1}\n'},new AbortController().signal);
  await assert.rejects(sink({sessionId:s.id,runId:run.id,threadId:'synthetic-parent',turnId:'synthetic-turn',callId:'foreign',name:'other.json',jsonUtf8:'{}'},new AbortController().signal));
  store.updateRun(run.id,'completed');store.addMessage(s.id,'assistant','Actual SOURCE peer completion',run.id,[],undefined,{phase:'final',streamState:'completed'} as any);
  const collected=await collectContinuationArtifacts(store,files,root,s.id,run.id),receipt=JSON.parse(collected.artifactReceiptUtf8);
  assert.ok(receipt.artifacts.every((a:any)=>a.messageId&&a.bytes===13&&a.sha256===sha256('{"actual":1}\n')));
});
test('SOURCE owned close refuses opaque caller hashes without actual raw native/gateway content',()=>{
  const raw=JSON.stringify({source:'native-acceptance-run-close',format:'h041-owned-close-v1',runId:'run',operationWindowId:'window',status:'released',producers:[],settledOwnedActions:[],outstandingOwnedActions:[],unconfirmedOwnedActions:[]});
  assert.equal(verifyObservedOwnedClose({outcome:'closed',closeReceiptUtf8:raw,closeReceiptSha256:sha256(raw),settlement:{state:'released',receiptSha256:sha256(raw),automaticReplay:false}},{runId:'run',operationWindowId:'window',observedSettlements:[],receiptSources:{}}).status,'FAIL');
});
