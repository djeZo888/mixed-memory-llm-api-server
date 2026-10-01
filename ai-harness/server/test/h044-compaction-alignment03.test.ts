/** SOURCE fixtures only. Transport brands are exercised through original file
 * APIs; these generated carriers are never native, formatter or Linux evidence. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,realpathSync,writeFileSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import * as policies from '../src/codex-probe.js';
import {receiptFixture} from './helpers/codex-receipt-fixture.js';
import {waitCodexReceiptFile,validateCodexLaunchReceipt,validateCodexSettlementReceipt,validateCodexTraceReceipt,getCodexReceiptUtf8,getCodexRetainedTraceEvidence,type CodexNativeTraceMode} from '../src/codex-receipts.js';
import {AUTHORIZATIONS,reviewedAuthorization} from '../../acceptance/compaction/authorization.mjs';
import {H044_PRODUCER_CONTRACT,assertH044ProducerSourceActivation,selectPolicyFactories,createSelectedRetentionParentPolicy} from '../../acceptance/compaction/native-adapter/policy-selection.js';
import {reviewedExpiry,FIXED_POLICY,type BootstrapInput} from '../../acceptance/compaction/native-adapter/bootstrap.js';
import {projectNormalProductTrace,NormalProductProducer,assertNormalProductTraceReady} from '../../acceptance/compaction/native-adapter/normal-product.js';
import {runOrdinarySupplement,runOneAutomatic} from '../../acceptance/compaction/native-adapter/ordinary-runner.js';
import {sha256} from '../../acceptance/compaction/native-adapter/projection.js';
const auth=AUTHORIZATIONS.H044,now=Date.parse('2026-10-02T00:05:00Z');
const review=()=>({authorization:{...auth,task:'H044' as const,windowId:'SOURCE-H044-window'},notAfterUtc:'2026-10-02T00:20:00Z',settlementReserveMs:120000});
const fields={sessionId:'SOURCE-parent',runId:'SOURCE-run',mode:'summary-only' as const,configSha256:'a'.repeat(64),modelCatalogSha256:'b'.repeat(64)};
test('SOURCE H044 finite operation expires inside the confirmed window with its own 120s reserve',()=>{
 const r=review(),a=reviewedAuthorization(r,now);
 assert.equal(a.expiresAt,Date.parse(r.notAfterUtc));assert.equal(a.dispatchCutoffAt,Date.parse('2026-10-02T00:18:00Z'));
 assert.equal(reviewedExpiry(r as BootstrapInput['review'],now),a.expiresAt);
 assert.equal(auth.startsUtc,'2026-10-01T23:14:41Z');assert.equal(auth.capUtc,'2026-10-02T07:45:00Z');assert.ok(Object.isFrozen(auth));
 for(const [r,at] of [[review(),Date.parse(auth.startsUtc)-1],[review(),Date.parse(review().notAfterUtc)],[review(),NaN],[{...review(),notAfterUtc:'2026-10-02T08:00:00Z'},now],[{...review(),settlementReserveMs:119999},now],[{...review(),authorization:{...auth,windowId:'SOURCE',startsUtc:'2026-10-01T23:14:42Z'}},now]] as const)assert.throws(()=>reviewedAuthorization(r as ReturnType<typeof review>,at));
 assert.equal(AUTHORIZATIONS.H043.capUtc,'2026-10-02T00:04:33Z');assert.equal(policies.CODEX_H043_WINDOW.expiresAtMs,Date.parse(AUTHORIZATIONS.H043.capUtc));
 assert.throws(()=>reviewedAuthorization({...review(),authorization:{...AUTHORIZATIONS.H043,task:'H043',windowId:'SOURCE'}},now));
 assert.deepEqual([FIXED_POLICY.version,FIXED_POLICY.sourceRevision,FIXED_POLICY.contextWindow,FIXED_POLICY.autoCompactTokenLimit,FIXED_POLICY.maxOutputTokens],['0.158.0','064c6b8c737f5b41d171fdda80bd9ef10ad06eb3',480000,400000,65536]);
});
test('SOURCE proposed H044 names cannot unlock missing exact root reviewed producer declarations/implementation/brands',()=>{
 assert.equal(H044_PRODUCER_CONTRACT.sourceActivation,'CLOSED');assert.equal(H044_PRODUCER_CONTRACT.collaborationVersionField,'collaborationVersion');
 assert.throws(()=>assertH044ProducerSourceActivation('H044'),/root_reviewed_R_H044/);
 for(const full of [false,true])for(const api of [policies,{...policies,CODEX_H044_WINDOW:{startAtMs:Date.parse(auth.startsUtc),expiresAtMs:Date.parse(auth.capUtc),settlementReserveMs:120000},createCodexH044Policy:policies.createCodexH043Policy,createCodexH044RetentionParentPolicy:policies.createCodexH043RetentionParentPolicy}])assert.throws(()=>selectPolicyFactories(api,'H044',full),/root_reviewed_R_H044/);
});
test('SOURCE actual retained parent field is collaborationVersion; brands, selected mode and pins remain checked',t=>{
 t.mock.method(Date,'now',()=>Date.parse('2026-10-01T15:00:00Z'));
 const task='H041-COMPACTION-DELIVERY-05',selected=selectPolicyFactories(policies,task,true);
 for(const version of ['v1','v2'] as const){const p=createSelectedRetentionParentPolicy(selected,task,fields,version);assert.equal(p.mode,'retention-parent');assert.equal(p.collaborationVersion,version);assert.equal(p.runId,fields.runId);assert.equal(p.window,policies.CODEX_H041_DELIVERY05_WINDOW);assert.throws(()=>policies.assertCodexTextOnlyPolicy({...p},p.sessionId));assert.throws(()=>policies.assertCodexTextOnlyPolicy(p,'FOREIGN'));}
 assert.throws(()=>createSelectedRetentionParentPolicy(selected,task,{...fields,observedCollaborationVersion:'v2'},'v2'));
 assert.throws(()=>createSelectedRetentionParentPolicy({...selected,parentFactory:policies.createCodexH043RetentionParentPolicy},task,fields,'v2'));
 t.mock.method(Date,'now',()=>Date.parse('2026-10-01T23:00:00Z'));
 const parent=policies.createCodexH043RetentionParentPolicy({...fields,collaborationVersion:'v2'});assert.equal(parent.collaborationVersion,'v2');assert.equal(parent.mode,'retention-parent');
});
async function sourceTrace(t:any,mode:Exclude<CodexNativeTraceMode,'off'>,includeAuto:boolean){
 const dir=realpathSync(mkdtempSync(join(tmpdir(),'h044-source-trace-')));t.after(()=>rmSync(dir,{recursive:true,force:true}));
 const f=receiptFixture(),uid=process.getuid!(),prefix=`user.slice/user-${uid}.slice/user@${uid}.service/aiharnesstasks.slice`;
 const producer={...f.producer,uid,cgroupPath:'/'+prefix+'/SOURCE.scope'},binding={...f.binding,uid,gid:uid,nativeTraceMode:mode};
 const rawLaunch={...f.rawLaunch,producer,egress:{...f.rawLaunch.egress,uid,cgroupPath:prefix},container:{...f.rawLaunch.container,user:`${uid}:${uid}`}},rawSettlement={...f.rawSettlement,producer};
 async function read(name:'launch'|'settlement'|'trace',value:any){writeFileSync(join(dir,name+'.json'),JSON.stringify(value),{mode:0o600,flag:'wx'});writeFileSync(join(dir,name+'.ready'),'',{mode:0o600,flag:'wx'});return waitCodexReceiptFile(dir,uid,name,100,()=>true);}
 const launch=validateCodexLaunchReceipt(await read('launch',rawLaunch),binding,producer,f.now),settlement=validateCodexSettlementReceipt(await read('settlement',rawSettlement),binding,launch,f.now+1);
 const spans=[{name:'turn','thread.id':'SOURCE-native-thread','turn.id':'SOURCE-native-turn'}];
 const numeric={timestamp:'2026-10-02T00:05:00.000000001Z',level:'TRACE',target:'codex_core::session::turn',fields:{message:'post sampling token usage',turn_id:'SOURCE-native-turn',total_usage_tokens:400001,auto_compact_scope_tokens:400001,auto_compact_scope_limit:'Some(400000)',auto_compact_limit_scope:'Total',auto_compact_window_prefill_tokens:'None',full_context_window_limit:'Some(480000)',full_context_window_limit_reached:false,token_limit_reached:true,model_needs_follow_up:true,has_pending_input:false,needs_follow_up:true},spans,span:spans[0]};
 const auto={timestamp:'2026-10-02T00:05:00.000000002Z',level:'TRACE',target:'codex_core::session::turn',fields:{message:'new'},spans,span:{name:'run_auto_compact',reason:'ContextLimit',phase:'MidTurn'}};
 const v2=mode==='post-sampling-token-usage-v2',originals=[numeric,...(includeAuto?[auto]:[])].map(x=>JSON.stringify(x)+'\n');let offset=0;
 const events=originals.map((lineUtf8,i)=>{const raw=JSON.parse(lineUtf8),bytes=Buffer.byteLength(lineUtf8),event={file:`trace-event-${String(i).padStart(4,'0')}.raw`,sha256:sha256(lineUtf8),bytes,stderrSequence:i+1,stderrOffset:offset,chain:sha256('SOURCE-chain-'+i),turnId:'SOURCE-native-turn',nativeTimestamp:raw.timestamp,observedAtMs:now,observedMonotonicNs:i+1,...(v2?{kind:i?'autoCompactNew':'postSampling',threadId:'SOURCE-native-thread'}:{})};offset+=bytes;writeFileSync(join(dir,event.file),lineUtf8,{mode:0o600,flag:'wx'});return event;});
 const trace={schema:v2?'codex-native-trace-v2':'codex-native-trace-v1',mode,nonce:binding.nonce,sessionId:binding.sessionId,runId:binding.runId,producer,containerId:launch.container.id,environment:{RUST_LOG:v2?'off,codex_core::session::turn=trace,codex_core::tasks=info':'off,codex_core::session::turn=trace',LOG_FORMAT:'json'},sources:binding.sources,events,stderrBytes:offset,stderrSHA256:sha256(originals.join('')),stderrChain:sha256('SOURCE-stream'),complete:true,cleanupOk:true,engineExitStatus:settlement.engineExitStatus,requestedStop:settlement.requestedStop};
 const receipt=validateCodexTraceReceipt(await read('trace',{...trace,...(v2?{autoCalls:events.filter(e=>e.kind==='autoCompactNew')}:{})}),binding,launch,settlement);
 const carrier={launchReceiptUtf8:getCodexReceiptUtf8(launch)!,launchReceiptSha256:sha256(getCodexReceiptUtf8(launch)!),settlementReceiptUtf8:getCodexReceiptUtf8(settlement)!,settlementReceiptSha256:sha256(getCodexReceiptUtf8(settlement)!)};
 return {receipt,carrier,originals,events,expected:{sessionId:launch.sessionId,receiptSources:launch.sources}};
}
for(const [mode,includeAuto] of [['post-sampling-token-usage-v1',false],['post-sampling-token-usage-v2',false],['post-sampling-token-usage-v2',true]] as const)test(`SOURCE ${mode} separate originals with AUTO=${includeAuto}; never native evidence`,async t=>{
 const f=await sourceTrace(t,mode,includeAuto),packet=projectNormalProductTrace(f.receipt,mode,f.carrier,f.expected),retained=packet.retainedTrace;
 assert.equal(retained.nativeAcceptance,'NOT_TESTED');assert.equal(retained.selectedMode,mode);assert.equal(retained.lines[0].lineUtf8,f.originals[0]);assert.equal(retained.lines[0].lineSha256,f.events[0].sha256);assert.equal(retained.autoCalls.length,includeAuto?1:0);
 if(includeAuto){assert.equal(retained.autoCalls[0].lineUtf8,f.originals[1]);assert.equal(retained.autoCalls[0].stderrSequence,2);assert.equal(retained.autoCalls[0].lineSha256,f.events[1].sha256);assert.equal(JSON.parse(retained.autoCalls[0].lineUtf8).timestamp,'2026-10-02T00:05:00.000000002Z');}
 assert.deepEqual(retained,getCodexRetainedTraceEvidence(f.receipt,mode));
 assert.throws(()=>projectNormalProductTrace(structuredClone(f.receipt),mode,f.carrier,f.expected),/actual_owned_current_A/);
 assert.throws(()=>projectNormalProductTrace(f.receipt,mode,f.carrier,{...f.expected,sessionId:'FOREIGN'}));
 assert.throws(()=>projectNormalProductTrace(f.receipt,mode,f.carrier,{...f.expected,receiptSources:{}}));
 assert.throws(()=>projectNormalProductTrace(f.receipt,mode,{...f.carrier,launchReceiptUtf8:f.carrier.launchReceiptUtf8+' '},f.expected),/digest/);
 assert.throws(()=>projectNormalProductTrace(f.receipt,mode==='post-sampling-token-usage-v1'?'post-sampling-token-usage-v2':'post-sampling-token-usage-v1',f.carrier,f.expected));
});
test('SOURCE H044 ordinary/AUTO and regular V2 activation stay closed without root review and genuine prerequisite acceptance',async t=>{
 t.mock.method(Date,'now',()=>now);assert.throws(()=>assertNormalProductTraceReady('post-sampling-token-usage-v2'),/V2_trace_producer_API_not_ready/);
 const plan={source:'SOURCE-plan'},r={...review(),automaticPlan:plan},p=new NormalProductProducer({sessionId:fields.sessionId,review:r},{qualificationSha256:sha256('SOURCE')} as never),ready=p.prepareAutomatic(plan,new AbortController().signal);
 assert.equal(ready.generationAllowed,false);assert.equal(ready.status,'NOT_TESTED');
 let calls=0;const host={qualification:{},client:{sessionId:fields.sessionId,request:()=>{calls++;throw Error('SOURCE forbidden');}}} as never;
 await assert.rejects(runOrdinarySupplement({...r,approvedBy:'root',actor:'worker1'},{},host,'/SOURCE-unused',new AbortController().signal),/root_reviewed_R_H044/);
 await assert.rejects(runOneAutomatic(r,{},'SOURCE-no-manual-proof',host,'/SOURCE-unused',new AbortController().signal),/root_reviewed_R_H044/);assert.equal(calls,0);
});
