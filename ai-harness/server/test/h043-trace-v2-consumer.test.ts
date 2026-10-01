/** SOURCE ONLY: synthetic original carriers exercise real consumers/composition.
 * No Linux, native trace brand, model, inference or activation is qualified. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {receiptFixture} from './helpers/codex-receipt-fixture.js';
import {verifyRetainedTrace,verifyNativeStartedAtTraceJoin,nativeCompactionStart,verifyTraceSchemaMode} from '../../acceptance/compaction/native-trace-evidence.mjs';
import {automaticThreshold} from '../../acceptance/compaction/automatic-evidence.mjs';
import {scoreAutomaticTrace} from '../../acceptance/compaction/scorer.mjs';
import {NormalProductProducer,normalProductTraceMode,assertNormalProductTraceReady} from '../../acceptance/compaction/native-adapter/normal-product.js';
import {composeCodexProductObservers} from '../src/codex-product-observation.js';
import {composeCodexHost} from '../src/codex-host.js';
import {AUTHORIZATIONS} from '../../acceptance/compaction/authorization.mjs';
const sha=(s:string)=>createHash('sha256').update(s).digest('hex');
const parent='SOURCE-parent',turn='SOURCE-turn',session='session-1',now=Date.parse('2026-10-01T15:00:00Z');
const task=()=>({name:'turn','thread.id':parent,'turn.id':turn});
const numeric=()=>({timestamp:'2026-10-01T15:00:00.000000001Z',level:'TRACE',target:'codex_core::session::turn',fields:{message:'post sampling token usage',turn_id:turn,total_usage_tokens:400001,auto_compact_scope_tokens:400001,auto_compact_scope_limit:'Some(400000)',auto_compact_limit_scope:'Total',auto_compact_window_prefill_tokens:'None',full_context_window_limit:'Some(480000)',full_context_window_limit_reached:false,token_limit_reached:true,model_needs_follow_up:true,has_pending_input:false,needs_follow_up:true},spans:[task()],span:task()});
const marker=()=>({timestamp:'2026-10-01T15:00:00.000000002Z',level:'TRACE',target:'codex_core::session::turn',fields:{message:'new'},spans:[task()],span:{name:'run_auto_compact',reason:'ContextLimit',phase:'MidTurn'}});
const line=(v:any)=>JSON.stringify(v)+'\n';
const pair=(key:string,v:any)=>{const bytes=JSON.stringify(v);return {[key+'Utf8']:bytes,[key+'Sha256']:sha(bytes)};};
function packet(v2=true,raws:any[]=[numeric(),marker()]){
 const f=receiptFixture(),schema=v2?'codex-native-trace-v2':'codex-native-trace-v1',mode=v2?'post-sampling-token-usage-v2':'post-sampling-token-usage-v1';
 const events=raws.map(x=>({lineUtf8:line(x)}));let offset=0;
 const t:any={schema,mode,nonce:f.binding.nonce,sessionId:session,runId:f.binding.runId,producer:f.rawLaunch.producer,containerId:f.rawLaunch.container.id,environment:{RUST_LOG:v2?'off,codex_core::session::turn=trace,codex_core::tasks=info':'off,codex_core::session::turn=trace',LOG_FORMAT:'json'},sources:f.binding.sources,events:events.map((e,i)=>{const p=JSON.parse(e.lineUtf8),bytes=Buffer.byteLength(e.lineUtf8),x={file:`trace-event-${String(i).padStart(4,'0')}.raw`,...(v2?{kind:p.fields.message==='new'?'autoCompactNew':'postSampling',threadId:p.spans[0]['thread.id']}:{}),turnId:p.fields.turn_id??p.spans[0]['turn.id'],sha256:sha(e.lineUtf8),bytes,stderrSequence:i+1,stderrOffset:offset,chain:sha('SOURCE-chain-'+i),nativeTimestamp:p.timestamp,observedAtMs:now,observedMonotonicNs:i+1};offset+=bytes;return x;}),stderrBytes:events.reduce((n,x)=>n+Buffer.byteLength(x.lineUtf8),0),stderrSHA256:sha(events.map(x=>x.lineUtf8).join('')),stderrChain:sha('SOURCE-complete-stream'),complete:true,cleanupOk:true,engineExitStatus:f.rawSettlement.engineExitStatus,requestedStop:f.rawSettlement.requestedStop};
 const p:any={selectedMode:mode,...pair('traceReceipt',t),...pair('launchReceipt',f.rawLaunch),...pair('settlementReceipt',f.rawSettlement),events};
 const expected:any={mode,sessionId:session,receiptSources:f.binding.sources,traceReceiptSha256:p.traceReceiptSha256,launchReceiptSha256:p.launchReceiptSha256,settlementReceiptSha256:p.settlementReceiptSha256};
 return {p,expected,t,f};
}
function refresh(x:ReturnType<typeof packet>){Object.assign(x.p,pair('traceReceipt',x.t));x.expected.traceReceiptSha256=x.p.traceReceiptSha256;}
function frame(value:any,sequence:number,direction='from-native'){const bytesUtf8=line(value);return {value,bytesUtf8,sha256:sha(bytesUtf8),direction,sequence,observedAt:'2099-01-01T00:00:00Z'};}
function automatic(v2=true,raws?:any[]){
 const x=packet(v2,raws??(v2?[numeric(),marker()]:[numeric()]));
 const frames=[frame({id:1,method:'turn/start',params:{threadId:parent}},1,'to-native'),frame({method:'turn/started',params:{threadId:parent,turn:{id:turn}}},2),frame({id:1,result:{turn:{id:turn}}},3),frame({method:'item/started',params:{threadId:parent,turnId:turn,item:{id:'SOURCE-compact',type:'contextCompaction'},startedAtMs:v2?now:now+1}},4),frame({method:'item/completed',params:{threadId:parent,turnId:turn,item:{id:'SOURCE-compact',type:'contextCompaction'}}},5),frame({method:'turn/completed',params:{threadId:parent,turn:{id:turn,status:'completed'}}},6)];
 const metadata={thread_id:parent,turn_id:turn,request_kind:'compaction',window_id:parent+':1',window_number:1,context_window_id:'SOURCE-context',compaction:{trigger:'auto',reason:'context_limit',strategy:'memento',implementation:'responses',phase:'mid_turn'}};
 const operation={sessionId:session,nativeThreadId:parent,nativeTurnId:turn,method:'turn/start',request:frames[0],started:frames[1],ack:frames[2],completed:frames[5],cleanup:{confirmed:true},gateway:{confirmed:true,nativeThreadId:parent,nativeTurnId:turn}};
 const processId=`${x.f.producer.bootId}:${x.f.producer.pid}:${x.f.producer.startTicks}`;
 const causal={source:'native-v2-item-started-timestamp-v1',requestId:'SOURCE-request',launchNonce:x.f.binding.nonce,processId};
 const config={contextWindow:480000,autoCompactTokenLimit:400000,maxOutputTokens:65536,effectiveScope:'total',tokenBudgetEnabled:false,fallbackBufferTokens:0,postTurnPercent:0};
 const r:any={sessionId:session,nativeThreadId:parent,nativeTurnId:turn,...pair('nativeTracePacket',x.p),...pair('nativeOperation',operation),nativeFramesUtf8:JSON.stringify(frames),...pair('nativeTraceCausalProof',causal),...pair('nativeResolvedConfigProof',config),producer:{...pair('launchReceipt',x.f.rawLaunch),...pair('settlementReceipt',x.f.rawSettlement)},requests:[{requestId:causal.requestId,firstRequestUtf8:JSON.stringify({client_metadata:{'x-codex-turn-metadata':JSON.stringify(metadata)}})}],gatewayRecords:[JSON.stringify({id:causal.requestId,sessionId:session,state:'settled',lane:'qwen3.8-27b',nativeMetadata:metadata})]};
 const expected:any={nativeTraceProof:x.expected,nativeTraceCausalProofSha256:r.nativeTraceCausalProofSha256,nativeResolvedConfigProofSha256:r.nativeResolvedConfigProofSha256};
 const trace=verifyRetainedTrace(x.p,x.expected),gateway={requestId:causal.requestId,nativeThreadId:parent,nativeTurnId:turn,windowId:metadata.window_id,contextWindowId:metadata.context_window_id,state:'settled'};
 const input:any={schema:trace.schema,mode:trace.mode,lines:trace.lines,autoCalls:trace.autoCalls,startFrame:frames[3],metadata,operation,gateway,producer:trace.producer,resolvedConfig:config};
 return {x,r,expected,metadata,input,frames,causal};
}
test('SOURCE retained V2 returns actual schema/mode and all original numeric/AUTO records, including empty array',()=>{
 const a=packet(),t=verifyRetainedTrace(a.p,a.expected);assert.equal(t.schema,a.t.schema);assert.equal(t.mode,a.t.mode);assert.equal(t.selectedMode,a.expected.mode);assert.equal(t.lines[0].lineUtf8,a.p.events[0].lineUtf8);assert.equal(t.autoCalls[0].lineUtf8,a.p.events[1].lineUtf8);
 const empty=packet(true,[numeric()]),e=verifyRetainedTrace(empty.p,empty.expected);assert.equal(e.schema,'codex-native-trace-v2');assert.deepEqual(e.autoCalls,[]);
 const unexpected=marker();unexpected.span.reason='ModelDownshift';const many=packet(true,[numeric(),numeric(),marker(),unexpected]);const m=verifyRetainedTrace(many.p,many.expected);assert.equal(m.lines.length,2);assert.equal(m.autoCalls.length,2);assert.equal(m.autoCalls[1].raw.span.reason,'ModelDownshift');
});
test('SOURCE real consumer/scorer accepts unique owned V2 AUTO NEW and original start without granting native PASS',()=>{
 const a=automatic(),j=verifyNativeStartedAtTraceJoin(a.input);assert.equal(j.status,'SOURCE_VALID');assert.equal(j.schema,'codex-native-trace-v2');assert.equal(j.startedAtMs,now);assert.equal(j.startFrameSha256,a.frames[3].sha256);assert.equal(j.autoCallSha256,sha(a.x.p.events[1].lineUtf8));assert.equal(j.nativeAcceptance,'NOT_TESTED');
 assert.equal(automaticThreshold(a.r,a.expected,a.metadata).status,'SOURCE_VALID');assert.equal(scoreAutomaticTrace(a.r,a.expected,a.metadata).status,'SOURCE_VALID');
 a.input.startFrame.observedAt='1900-01-01T00:00:00Z';assert.equal(verifyNativeStartedAtTraceJoin(a.input).startedAtMs,now);
});
test('SOURCE missing V2 autoCalls rejects; empty remains V2 and cannot downgrade to V1',()=>{
 const a=automatic();delete a.input.autoCalls;assert.throws(()=>verifyNativeStartedAtTraceJoin(a.input),/V2_actual_autoCalls_array/);
 for(const calls of [null,{},'']){a.input.autoCalls=calls;assert.throws(()=>verifyNativeStartedAtTraceJoin(a.input),/V2_actual_autoCalls_array/);}
 const empty=automatic(true,[numeric()]);empty.input.startFrame=frame({...empty.input.startFrame.value,params:{...empty.input.startFrame.value.params,startedAtMs:now+1}},4);assert.throws(()=>verifyNativeStartedAtTraceJoin(empty.input),/unique_actual_same_owned/);
 const verdict=scoreAutomaticTrace(empty.r,empty.expected,empty.metadata);assert.equal(verdict.status,'FAIL');assert.match(verdict.errors![0],/unique_actual_same_owned/);
});
test('SOURCE foreign numeric ancestry cannot hide alongside a valid selected record',()=>{
 for(const mutate of [(v:any)=>v.spans[0]['thread.id']='FOREIGN',(v:any)=>{v.spans[0]['turn.id']='FOREIGN';v.span['turn.id']='FOREIGN';v.fields.turn_id='FOREIGN';},(v:any)=>v.spans.push({name:'turn'}),(v:any)=>v.fields.total_usage_tokens=-1]){
  const a=automatic(),foreign=numeric();mutate(foreign);a.input.lines.push({lineUtf8:line(foreign),stderrSequence:3});assert.throws(()=>verifyNativeStartedAtTraceJoin(a.input));
 }
 const foreign=numeric();foreign.spans[0]['thread.id']='FOREIGN';foreign.span['thread.id']='FOREIGN';const a=automatic(true,[numeric(),marker(),foreign]);assert.equal(a.input.lines.length,2);assert.equal(scoreAutomaticTrace(a.r,a.expected,a.metadata).status,'FAIL');
});
test('SOURCE wrong-owned or multiple AUTO calls, incomplete ancestry and wrong cause fail closed',()=>{
 for(const mutate of [(x:any)=>x.autoCalls.push(x.autoCalls[0]),(x:any)=>{const raw=marker();raw.spans[0]['thread.id']='FOREIGN';x.autoCalls.push({lineUtf8:line(raw),stderrSequence:3});},(x:any)=>{const raw=marker();raw.span.reason='ModelDownshift';x.autoCalls[0].lineUtf8=line(raw);delete x.autoCalls[0].lineSha256;},(x:any)=>x.autoCalls[0].stderrSequence=1]){const a=automatic();mutate(a.input);assert.throws(()=>verifyNativeStartedAtTraceJoin(a.input));}
});
test('SOURCE original event digest/index timestamp and raw start corruption reject',()=>{
 for(const mutate of [(x:any)=>x.p.events[0].lineUtf8+=' ',(x:any)=>x.t.events[0].nativeTimestamp='2099-01-01T00:00:00Z',(x:any)=>x.t.events[0].sha256=sha('changed'),(x:any)=>x.t.producer.pid++]){const x=packet();mutate(x);refresh(x);assert.throws(()=>verifyRetainedTrace(x.p,x.expected));}
 for(const mutate of [(x:any)=>x.sha256=sha('changed'),(x:any)=>x.value.params.startedAtMs++,(x:any)=>{delete x.value.params.startedAtMs;x.bytesUtf8=line(x.value);x.sha256=sha(x.bytesUtf8);},(x:any)=>{x.value.params.startedAtMs=now+.5;x.bytesUtf8=line(x.value);x.sha256=sha(x.bytesUtf8);}]){const a=automatic();mutate(a.input.startFrame);assert.throws(()=>nativeCompactionStart(a.input.startFrame,parent,turn));}
});
test('SOURCE exact original integer literals reject fractions/exponents/duplicate carrier keys even when JSON numbers compare equal',()=>{
 for(const token of [String(now)+'.0',String(now)+'e0']){const a=automatic(),f=a.input.startFrame;f.bytesUtf8=f.bytesUtf8.replace(String(now),token);f.sha256=sha(f.bytesUtf8);assert.equal(JSON.parse(f.bytesUtf8).params.startedAtMs,now);assert.throws(()=>nativeCompactionStart(f,parent,turn),/integer_literal/);}
 const a=automatic(),f=a.input.startFrame;f.bytesUtf8=f.bytesUtf8.replace('"startedAtMs":'+now,'"startedAtMs":'+now+',"startedAtMs":'+now);f.sha256=sha(f.bytesUtf8);assert.throws(()=>nativeCompactionStart(f,parent,turn),/duplicate/);
 const b=automatic();b.input.lines[0].lineUtf8=b.input.lines[0].lineUtf8.replace('400001','400001.0');delete b.input.lines[0].lineSha256;assert.throws(()=>verifyNativeStartedAtTraceJoin(b.input),/integer_literal/);
});
test('SOURCE schema/mode mismatch, unknown/missing schema and root selected-mode mismatch reject explicitly',()=>{
 for(const patch of [{schema:'codex-native-trace-v1'},{mode:'post-sampling-token-usage-v1'},{schema:'unknown'},{schema:undefined},{mode:undefined}]){const a=automatic();Object.assign(a.input,patch);assert.throws(()=>verifyNativeStartedAtTraceJoin(a.input));}
 for(const mutate of [(x:any)=>x.t.mode='post-sampling-token-usage-v1',(x:any)=>x.t.schema='unknown',(x:any)=>x.expected.mode='post-sampling-token-usage-v1',(x:any)=>delete x.expected.mode,(x:any)=>x.p.selectedMode='off']){const x=packet();mutate(x);refresh(x);assert.throws(()=>verifyRetainedTrace(x.p,x.expected));}
});
test('SOURCE V2 causal proof and ordinary operation cannot borrow another nonce/process or producer',()=>{
 for(const mutate of [(a:any)=>a.causal.launchNonce='FOREIGN',(a:any)=>a.causal.processId='FOREIGN',(a:any)=>a.r.producer.launchReceiptSha256=sha('FOREIGN'),(a:any)=>{const l=JSON.parse(a.r.producer.launchReceiptUtf8);l.producer.pid++;Object.assign(a.r.producer,pair('launchReceipt',l));}]){const a=automatic();mutate(a);Object.assign(a.r,pair('nativeTraceCausalProof',a.causal));a.expected.nativeTraceCausalProofSha256=a.r.nativeTraceCausalProofSha256;assert.equal(scoreAutomaticTrace(a.r,a.expected,a.metadata).status,'FAIL');}
 const a=automatic();delete a.r.nativeTracePacketUtf8;const missing=scoreAutomaticTrace(a.r,a.expected,a.metadata);assert.equal(missing.status,'NOT_TESTED');assert.equal(missing.schema,'codex-native-trace-v2');
});
test('SOURCE V2 native clocks reject regression/later AUTO and preserve full precision',()=>{
 for(const timestamp of ['2026-10-01T14:59:59.999999999Z','2026-10-01T15:00:00.001Z','2026-02-30T15:00:00Z']){const a=automatic(),raw=marker();raw.timestamp=timestamp;a.input.autoCalls[0].lineUtf8=line(raw);delete a.input.autoCalls[0].lineSha256;assert.throws(()=>verifyNativeStartedAtTraceJoin(a.input));}
});
test('SOURCE explicit V1 strict timestamp-only join and off defaults remain generation-disabled',t=>{
 const a=automatic(false);assert.equal(verifyRetainedTrace(a.x.p,a.x.expected).mode,'post-sampling-token-usage-v1');assert.equal(verifyNativeStartedAtTraceJoin(a.input).status,'SOURCE_VALID');assert.equal(scoreAutomaticTrace(a.r,a.expected,a.metadata).status,'SOURCE_VALID');
 assert.deepEqual(verifyTraceSchemaMode(null,'off'),{schema:null,mode:'off'});assert.throws(()=>verifyNativeStartedAtTraceJoin({...a.input,schema:null,mode:'off'}),/off_trace/);
 const auth=AUTHORIZATIONS['H041-COMPACTION-DELIVERY-05'];t.mock.method(Date,'now',()=>now);const plan={source:'SOURCE-plan'},review={authorization:{...auth,windowId:'SOURCE-parser-only'},notAfterUtc:auth.capUtc,settlementReserveMs:120000,automaticPlan:plan};
 const producer=new NormalProductProducer({sessionId:session,hostPrivate:'/SOURCE-unused',review},{qualificationSha256:sha('SOURCE-qualification')} as any);assert.equal(producer.prepareAutomatic(plan,new AbortController().signal).generationAllowed,false);
});
test('SOURCE normal real observation composition preserves V1/off and refuses unbranded receipts or V2-not-ready before runtime exposure',()=>{
 const base={protocolQualified:true as const,rootlessQualified:true as const,verifyLane:async()=>{throw Error('SOURCE-unused');}};
 assert.equal(normalProductTraceMode({}),'off');assert.equal(normalProductTraceMode({nativeTrace:{mode:'off'}}),'off');assert.throws(()=>normalProductTraceMode({nativeTrace:{mode:'unknown'}}));
 for(const mode of ['off','post-sampling-token-usage-v1'] as const){const producer=new NormalProductProducer({sessionId:session,hostPrivate:'/SOURCE-unused',review:{nativeTrace:{mode}}},{} as any),hooks=producer.hooks(base),runtime=composeCodexHost('/SOURCE-never-launch',()=>undefined,composeCodexProductObservers(base,undefined,hooks)).runtime;assert.equal(runtime.nativeTraceMode,mode==='off'?undefined:mode);if(mode!=='off')assert.throws(()=>runtime.onNativeTraceReceipt!({schema:'codex-native-trace-v1'} as never),/actual_owned_current_A_trace_receipt/);}
 assert.throws(()=>assertNormalProductTraceReady('post-sampling-token-usage-v2'),/V2_trace_producer_API_not_ready/);const v2=new NormalProductProducer({sessionId:session,hostPrivate:'/SOURCE-unused',review:{nativeTrace:{mode:'post-sampling-token-usage-v2'}}},{} as any);assert.throws(()=>v2.hooks(base),/V2_trace_producer_API_not_ready/);
});

test('SOURCE optional-present V1 numeric task spans cannot hide foreign ancestry; span-less originals remain valid',()=>{
 const a=automatic(false),raw=numeric();raw.spans[0]['thread.id']='FOREIGN';raw.span['thread.id']='FOREIGN';a.input.lines.push({lineUtf8:line(raw),stderrSequence:2});assert.throws(()=>verifyNativeStartedAtTraceJoin(a.input),/ancestry/);
 const b=automatic(false),bare:any=numeric();delete bare.spans;delete bare.span;b.input.lines=[{lineUtf8:line(bare),stderrSequence:1}];assert.equal(verifyNativeStartedAtTraceJoin(b.input).status,'SOURCE_VALID');
});
test('SOURCE explicit off rejects inherited mode or receipt hooks before real observer composition can restore them',()=>{
 const producer=new NormalProductProducer({sessionId:session,hostPrivate:'/SOURCE-unused',review:{nativeTrace:{mode:'off'}}},{} as any),base={protocolQualified:true as const,rootlessQualified:true as const,verifyLane:async()=>{throw Error('SOURCE-unused');}};
 assert.throws(()=>producer.hooks({...base,nativeTraceMode:'post-sampling-token-usage-v1'}),/explicit_off_cannot_inherit/);assert.throws(()=>producer.hooks({...base,onNativeTraceReceipt:()=>undefined}),/explicit_off_cannot_inherit/);
});
