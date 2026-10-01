/** SOURCE ONLY: frozen selection and authentic source-brand/file fixture APIs.
 * No Linux process, native formatter, manual/full/AUTO or live qualification. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,realpathSync,writeFileSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import * as policies from '../src/codex-probe.js';
import {AUTHORIZATIONS,reviewedAuthorization} from '../../acceptance/compaction/authorization.mjs';
import {selectPolicyFactories,createSelectedRetentionParentPolicy,FULL_RETENTION_TASKS,ORDINARY_TASKS} from '../../acceptance/compaction/native-adapter/policy-selection.js';
import {reviewedExpiry,type BootstrapInput} from '../../acceptance/compaction/native-adapter/bootstrap.js';
import {qualifyEntry} from '../../acceptance/compaction/native-adapter/qualification.js';
import {assertOrdinaryDispatch,requireFullManualReceipt,runOrdinarySupplement} from '../../acceptance/compaction/native-adapter/ordinary-runner.js';
import {NormalProductProducer,assertNormalProductTraceReady,normalProductTraceMode,kernelProcessReceipt} from '../../acceptance/compaction/native-adapter/normal-product.js';
import {composeCodexProductObservers} from '../src/codex-product-observation.js';
import {composeCodexHost} from '../src/codex-host.js';
import {waitCodexReceiptFile,validateCodexLaunchReceipt,validateCodexSettlementReceipt,validateCodexTraceReceipt,getCodexTraceEvents,getCodexTraceUtf8} from '../src/codex-receipts.js';
import {receiptFixture} from './helpers/codex-receipt-fixture.js';
import {sha256} from '../../acceptance/compaction/native-adapter/projection.js';
const auth=AUTHORIZATIONS.H043,now=Date.parse(auth.startsUtc)+1000;
const fields={sessionId:'SOURCE-H043-parent',runId:'SOURCE-H043-run',mode:'summary-only' as const,configSha256:'a'.repeat(64),modelCatalogSha256:'b'.repeat(64)};
const review=()=>({authorization:{...auth,task:'H043' as const,windowId:'SOURCE-H043-window'},notAfterUtc:auth.capUtc,settlementReserveMs:120000});
const base={protocolQualified:true as const,rootlessQualified:true as const,verifyLane:async()=>{throw Error('SOURCE-no-native');}};
test('SOURCE H043 bootstrap, retention and ordinary/AUTO selections share the exact frozen window',t=>{
 t.mock.method(Date,'now',()=>now);const r=review(),selection=selectPolicyFactories(policies,'H043',false);
 assert.equal(selection.factory,policies.createCodexH043Policy);assert.equal(selection.adoptionAuthorization,'h043');
 assert.equal(selection.factory(fields).window,policies.CODEX_H043_WINDOW);assert.equal(reviewedExpiry(r as BootstrapInput['review']),Date.parse(auth.capUtc));
 assert.deepEqual(reviewedAuthorization(r),{authorization:auth,expiresAt:Date.parse(auth.capUtc),dispatchCutoffAt:Date.parse('2026-10-02T00:02:33Z'),settlementReserveMs:120000});
 assert.ok(FULL_RETENTION_TASKS.includes('H043')&&ORDINARY_TASKS.includes('H043'));assert.ok(Object.isFrozen(auth)&&Object.isFrozen(FULL_RETENTION_TASKS)&&Object.isFrozen(ORDINARY_TASKS));
});
test('SOURCE H043 rejects mismatched/prewindow/expired/reserve and redirected historical authority',()=>{
 for(const [r,clock] of [[review(),now-1001],[review(),Date.parse(auth.capUtc)],[review(),NaN],[{...review(),settlementReserveMs:119999},now],[{...review(),notAfterUtc:'2026-10-02T00:19:33Z'},now],[{...review(),authorization:{...auth,startsUtc:'2026-10-01T21:19:34Z',windowId:'SOURCE'}},now],[{...review(),authorization:{...auth,task:'H042',windowId:'SOURCE'}},now],[{...review(),authorization:{...AUTHORIZATIONS['H041-COMPACTION-DELIVERY-05'],windowId:'SOURCE'}},now]] as const)assert.throws(()=>reviewedAuthorization(r as ReturnType<typeof review>,clock));
 assert.equal(AUTHORIZATIONS['H041-COMPACTION-DELIVERY-05'].capUtc,'2026-10-01T18:30:02.674394+00:00');
 assert.equal(policies.CODEX_H042_WINDOW.expiresAtMs,Date.parse('2026-10-01T20:29:17Z'));
});
test('SOURCE selector rejects caller mirrored window, replacement/old factory and missing exact exports',()=>{
 for(const api of [{...policies,CODEX_H043_WINDOW:{...policies.CODEX_H043_WINDOW}},{...policies,CODEX_H043_WINDOW:policies.CODEX_H041_DELIVERY05_WINDOW},{...policies,createCodexH043Policy:policies.createCodexDelivery05Policy},{...policies,createCodexH043Policy:()=>policies.createCodexH043Policy(fields)},{...policies,createCodexH043Policy:undefined}])assert.throws(()=>selectPolicyFactories(api,'H043',false),/actual_A_source_frozen/);
 assert.throws(()=>selectPolicyFactories(policies,'unknown',false));assert.throws(()=>selectPolicyFactories(policies,'H042',false));
 const selected=selectPolicyFactories(policies,'H043',false);
 for(const extra of [{window:policies.CODEX_H043_WINDOW},{factory:policies.createCodexDelivery05Policy},{collaborationVersion:'v2'}])assert.throws(()=>selected.factory({...fields,...extra}));
});
test('SOURCE absent H043 parent/handoff stay closed; historical version input and ownership brands remain original',t=>{
 t.mock.method(Date,'now',()=>now);assert.throws(()=>selectPolicyFactories(policies,'H043',true),/actual_A_source_frozen_policy_exports_required|actual_reviewed_A_H043_handoff/);
 assert.throws(()=>createSelectedRetentionParentPolicy(selectPolicyFactories(policies,'H043',false),'H043',fields,'v2'));
 t.mock.method(Date,'now',()=>Date.parse('2026-10-01T15:00:00Z'));
 const task='H041-COMPACTION-DELIVERY-05',selected=selectPolicyFactories(policies,task,true);
 for(const v of ['v1','v2'] as const){const p=createSelectedRetentionParentPolicy(selected,task,fields,v);assert.equal(p.collaborationVersion,v);assert.equal(p.window,policies.CODEX_H041_DELIVERY05_WINDOW);assert.equal(p.mode,'retention-parent');}
 for(const v of [null,undefined,'v3',1])assert.throws(()=>createSelectedRetentionParentPolicy(selected,task,fields,v));
 assert.throws(()=>createSelectedRetentionParentPolicy({...selected,parentFactory:policies.createCodexRetentionParentPolicy},task,fields,'v2'),/actual_selected_A/);
 const p=policies.createCodexH043Policy(fields);assert.throws(()=>policies.assertCodexTextOnlyPolicy(p,'FOREIGN',now));assert.throws(()=>policies.assertCodexTextOnlyPolicy({...p},p.sessionId,now));
});
test('SOURCE H043 cutoff and cancellation grant no new dispatch, including after async observation',async()=>{
 const a=reviewedAuthorization(review(),now),c=new AbortController();assert.doesNotThrow(()=>assertOrdinaryDispatch(a,c.signal,a.dispatchCutoffAt-1));await Promise.resolve();assert.throws(()=>assertOrdinaryDispatch(a,c.signal,a.dispatchCutoffAt));c.abort();assert.throws(()=>assertOrdinaryDispatch(a,c.signal,now));
});
test('SOURCE H043 source/unbranded qualification cannot enter ordinary/manual/AUTO/native Linux gates',async t=>{
 t.mock.method(Date,'now',()=>now);let calls=0;
 await assert.rejects(qualifyEntry({bootstrap:{review:review()}}),/actual_rootless_linux_entry_qualification/);
 await assert.rejects(kernelProcessReceipt(),/requires_linux_kernel/);
 await assert.rejects(runOrdinarySupplement({...review(),approvedBy:'root',actor:'worker1'},{},{qualification:{},client:{sessionId:fields.sessionId,request:()=>{calls++;throw Error('SOURCE forbidden');}}} as never,'/SOURCE-unused',new AbortController().signal),/root_reviewed_actual_ordinary_runner/);
 assert.equal(calls,0);for(const r of [{qualification:'source',status:'PASS'},{qualification:'native',profile:'h041-full-retention-v1',status:'PASS',records:[]}]){const bytes=JSON.stringify(r);assert.throws(()=>requireFullManualReceipt(bytes,sha256(bytes)));}
});
test('SOURCE H043 AUTO remains NOT_TESTED and generation disabled without regular native/config/causal proof',t=>{
 t.mock.method(Date,'now',()=>now);const plan={source:'SOURCE-frozen-plan'},r={...review(),automaticPlan:plan},p=new NormalProductProducer({sessionId:fields.sessionId,hostPrivate:'/SOURCE-unused',review:r},{qualificationSha256:sha256('SOURCE')} as never);
 const ready=p.prepareAutomatic(plan,new AbortController().signal);assert.equal(ready.status,'NOT_TESTED');assert.equal(ready.generationAllowed,false);assert.equal(ready.sourceSha256,null);assert.equal(ready.resolvedConfigSha256,null);assert.throws(()=>p.prepareAutomatic({source:'FOREIGN'},new AbortController().signal));const c=new AbortController();c.abort();assert.throws(()=>p.prepareAutomatic(plan,c.signal));
});
test('SOURCE H043 V1/off real observer composition stays explicit; V2 producer unavailable fails closed',()=>{
 assert.equal(normalProductTraceMode({}),'off');assert.throws(()=>normalProductTraceMode({nativeTrace:{mode:'V2'}}));assert.throws(()=>assertNormalProductTraceReady('post-sampling-token-usage-v2'),/V2_trace_producer_API_not_ready/);
 for(const mode of ['off','post-sampling-token-usage-v1'] as const){const p=new NormalProductProducer({sessionId:fields.sessionId,hostPrivate:'/SOURCE-unused',review:{nativeTrace:{mode}}},{} as never),hooks=p.hooks(base),runtime=composeCodexHost('/SOURCE-never-launch',()=>undefined,composeCodexProductObservers(base,undefined,hooks)).runtime;assert.equal(runtime.nativeTraceMode,mode==='off'?undefined:mode);if(mode==='off')assert.equal(runtime.onNativeTraceReceipt,undefined);else assert.throws(()=>runtime.onNativeTraceReceipt!({schema:'codex-native-trace-v1'} as never),/actual_owned_current_A/);}
 const off=new NormalProductProducer({sessionId:fields.sessionId,review:{nativeTrace:{mode:'off'}}},{} as never);assert.throws(()=>off.hooks({...base,onNativeTraceReceipt:()=>{}}),/explicit_off_cannot_inherit/);
});
async function brandedV1(t:any){
 const dir=realpathSync(mkdtempSync(join(tmpdir(),'h043-source-brand-')));t.after(()=>rmSync(dir,{recursive:true,force:true}));
 const fixture=receiptFixture(),uid=process.getuid!(),prefix=`user.slice/user-${uid}.slice/user@${uid}.service/aiharnesstasks.slice`;
 const producer={...fixture.producer,uid,cgroupPath:'/'+prefix+'/SOURCE.scope'},binding={...fixture.binding,uid,gid:uid,nativeTraceMode:'post-sampling-token-usage-v1' as const};
 const rawLaunch={...fixture.rawLaunch,producer,egress:{...fixture.rawLaunch.egress,uid,cgroupPath:prefix},container:{...fixture.rawLaunch.container,user:`${uid}:${uid}`}},rawSettlement={...fixture.rawSettlement,producer};
 async function read(name:'launch'|'settlement'|'trace',v:unknown){writeFileSync(join(dir,name+'.json'),JSON.stringify(v),{mode:0o600,flag:'wx'});writeFileSync(join(dir,name+'.ready'),'',{mode:0o600,flag:'wx'});return waitCodexReceiptFile(dir,uid,name,100,()=>true);}
 const launch=validateCodexLaunchReceipt(await read('launch',rawLaunch),binding,producer,fixture.now),settlement=validateCodexSettlementReceipt(await read('settlement',rawSettlement),binding,launch,fixture.now+1);
 const raw={timestamp:'2026-10-01T21:19:34.000000001Z',level:'TRACE',target:'codex_core::session::turn',fields:{message:'post sampling token usage',turn_id:'SOURCE-turn',total_usage_tokens:400001,auto_compact_scope_tokens:400001,auto_compact_scope_limit:'Some(400000)',auto_compact_limit_scope:'Total',auto_compact_window_prefill_tokens:'None',full_context_window_limit:'Some(480000)',full_context_window_limit_reached:false,token_limit_reached:true,model_needs_follow_up:true,has_pending_input:false,needs_follow_up:true},spans:[{name:'turn','thread.id':'SOURCE-parent','turn.id':'SOURCE-turn'}],span:{name:'turn','thread.id':'SOURCE-parent','turn.id':'SOURCE-turn'}};
 const lineUtf8=JSON.stringify(raw)+'\n';writeFileSync(join(dir,'trace-event-0000.raw'),lineUtf8,{mode:0o600,flag:'wx'});
 const trace={schema:'codex-native-trace-v1',nonce:binding.nonce,sessionId:binding.sessionId,runId:binding.runId,mode:binding.nativeTraceMode,producer,containerId:launch.container.id,environment:{RUST_LOG:'off,codex_core::session::turn=trace',LOG_FORMAT:'json'},sources:binding.sources,events:[{file:'trace-event-0000.raw',sha256:sha256(lineUtf8),bytes:Buffer.byteLength(lineUtf8),stderrSequence:1,stderrOffset:0,chain:sha256('SOURCE-chain'),turnId:'SOURCE-turn',nativeTimestamp:raw.timestamp,observedAtMs:now,observedMonotonicNs:1}],stderrBytes:Buffer.byteLength(lineUtf8),stderrSHA256:sha256(lineUtf8),stderrChain:sha256('SOURCE-complete'),complete:true,cleanupOk:true,engineExitStatus:settlement.engineExitStatus,requestedStop:settlement.requestedStop};
 const receipt=validateCodexTraceReceipt(await read('trace',trace),binding,launch,settlement);return {dir,launch,settlement,receipt,lineUtf8};
}
test('SOURCE actual source-brand V1 file APIs compose original receipts; duplicate, foreign and cloned receipt fail',async t=>{
 t.mock.method(Date,'now',()=>now);const f=await brandedV1(t),plan={source:'SOURCE-plan'},reviewPacket={...review(),automaticPlan:plan,nativeTrace:{mode:'post-sampling-token-usage-v1'}},p=new NormalProductProducer({sessionId:f.launch.sessionId,hostPrivate:f.dir,review:reviewPacket},{receiptSources:f.launch.sources} as never),hooks=p.hooks(base);
 const sourceProcess={};// SOURCE observer identity carrier; no OS process or native launch.
 hooks.observations!.onNativeProcess!({sessionId:f.launch.sessionId,process:sourceProcess} as never);hooks.onNativeLaunchReceipt!(f.launch);hooks.onNativeSettlementReceipt!(f.settlement);hooks.onNativeTraceReceipt!(f.receipt);
 assert.equal(getCodexTraceUtf8(f.receipt),JSON.stringify(f.receipt));assert.equal(getCodexTraceEvents(f.receipt)![0].bytes.toString('utf8'),f.lineUtf8);assert.equal(p.prepareAutomatic(plan,new AbortController().signal).generationAllowed,false);
 // SOURCE current graph binding is independent of the trace's own sources.
 const foreignGraph=new NormalProductProducer({sessionId:f.launch.sessionId,hostPrivate:f.dir,review:reviewPacket},{receiptSources:Object.fromEntries(Object.keys(f.launch.sources).map(k=>[k,'c'.repeat(64)]))} as never),foreignHooks=foreignGraph.hooks(base);
 foreignHooks.observations!.onNativeProcess!({sessionId:f.launch.sessionId,process:{}} as never);foreignHooks.onNativeLaunchReceipt!(f.launch);foreignHooks.onNativeSettlementReceipt!(f.settlement);assert.throws(()=>foreignHooks.onNativeTraceReceipt!(f.receipt),/source/);
 // SOURCE settlement reserve still accepts already-owned evidence, then expiry closes it.
 const reserve=new NormalProductProducer({sessionId:f.launch.sessionId,hostPrivate:f.dir,review:reviewPacket},{receiptSources:f.launch.sources} as never),reserveHooks=reserve.hooks(base);
 reserveHooks.observations!.onNativeProcess!({sessionId:f.launch.sessionId,process:{}} as never);reserveHooks.onNativeLaunchReceipt!(f.launch);reserveHooks.onNativeSettlementReceipt!(f.settlement);t.mock.method(Date,'now',()=>Date.parse(auth.capUtc)-1);assert.doesNotThrow(()=>reserveHooks.onNativeTraceReceipt!(f.receipt));
 const expired=new NormalProductProducer({sessionId:f.launch.sessionId,hostPrivate:f.dir,review:reviewPacket},{receiptSources:f.launch.sources} as never),expiredHooks=expired.hooks(base);
 expiredHooks.observations!.onNativeProcess!({sessionId:f.launch.sessionId,process:{}} as never);expiredHooks.onNativeLaunchReceipt!(f.launch);expiredHooks.onNativeSettlementReceipt!(f.settlement);t.mock.method(Date,'now',()=>Date.parse(auth.capUtc));assert.throws(()=>expiredHooks.onNativeTraceReceipt!(f.receipt),/expired/);t.mock.method(Date,'now',()=>now);
 assert.throws(()=>hooks.onNativeLaunchReceipt!(f.launch),/no_replay/);assert.throws(()=>hooks.onNativeSettlementReceipt!(f.settlement),/replayed/);
 assert.throws(()=>hooks.onNativeTraceReceipt!(f.receipt),/actual_owned_current_A/);
 const q=new NormalProductProducer({sessionId:'FOREIGN',review:reviewPacket},{} as never);assert.throws(()=>q.hooks(base).onNativeTraceReceipt!(f.receipt),/actual_owned_current_A/);
 const cloned=new NormalProductProducer({sessionId:f.launch.sessionId,review:reviewPacket},{} as never);assert.throws(()=>cloned.hooks(base).onNativeTraceReceipt!(structuredClone(f.receipt)),/actual_owned_current_A/);
});
