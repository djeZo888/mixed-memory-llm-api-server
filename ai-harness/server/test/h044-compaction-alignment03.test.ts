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
import {H044_PRODUCER_CONTRACT,H044_REVIEWED_SOURCE_HASHES,H044_R01_BASELINE_SOURCE_HASHES,verifyH044ReviewedSourceHashes,assertH044ProducerSourceActivation,selectPolicyFactories,createSelectedRetentionParentPolicy} from '../../acceptance/compaction/native-adapter/policy-selection.js';
import {reviewedExpiry,FIXED_POLICY,type BootstrapInput} from '../../acceptance/compaction/native-adapter/bootstrap.js';
import {assertFiniteAutomaticTurn,projectAutomaticConfig,verifyRegularSamplingExclusion,projectNormalProductTrace,NormalProductProducer,assertNormalProductTraceReady} from '../../acceptance/compaction/native-adapter/normal-product.js';
import {runOrdinarySupplement,runOneAutomatic} from '../../acceptance/compaction/native-adapter/ordinary-runner.js';
import {sha256,stableJson} from '../../acceptance/compaction/native-adapter/projection.js';
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
test('SOURCE H044 exact closed graph activates; export aliases/copied windows or changed source cannot substitute',t=>{
 t.mock.method(Date,'now',()=>now);
 assert.equal(H044_PRODUCER_CONTRACT.sourceActivation,'EXACT_CLOSED_SOURCE_REVIEW');assert.equal(H044_PRODUCER_CONTRACT.collaborationVersionField,'collaborationVersion');
 assert.doesNotThrow(()=>assertH044ProducerSourceActivation('H044'));assert.doesNotThrow(()=>verifyH044ReviewedSourceHashes({...H044_REVIEWED_SOURCE_HASHES}));
 for(const path of Object.keys(H044_REVIEWED_SOURCE_HASHES))assert.throws(()=>verifyH044ReviewedSourceHashes({...H044_REVIEWED_SOURCE_HASHES,[path]:sha256('changed')}));
 assert.throws(()=>verifyH044ReviewedSourceHashes({}));
 assert.equal(H044_PRODUCER_CONTRACT.closedSourceCommit,'86fcd6d84381cb9c44caad75eb9785d3b0ec11bd');
 assert.equal(H044_PRODUCER_CONTRACT.rootReviewSha256,'2e597654a5ae7b6c50393f741d9dee864178a956ed1b42284678d897913dc6ee');
 assert.equal(H044_PRODUCER_CONTRACT.baselineEvidence.contractSha256,'f7f9228e9b6a3a2ce6bfa6a0c7b9508e3f68fd32d2c3744660190c9b858e340f');
 assert.equal(H044_PRODUCER_CONTRACT.declarationSha256.receipts,'202bc26fb087a32064ec3e11d2778c99714bfd6764d07945f2f0d8db61e9cc60');
 assert.equal(H044_PRODUCER_CONTRACT.baselineDeclarationSha256.receipts,'bcf97a9b95953cd694e925da6acfe3afc913ec3c2d95e0fd5e1935fc1b0422ca');
 assert.equal(H044_R01_BASELINE_SOURCE_HASHES['ai-harness/server/src/codex-instructions.ts'],'8e4925203c9236d504ec1ca30d7f08f031d8a7930dd1cd1ec515090d793b61e9');
 assert.throws(()=>verifyH044ReviewedSourceHashes({...H044_R01_BASELINE_SOURCE_HASHES}));
 assert.throws(()=>verifyH044ReviewedSourceHashes({...H044_REVIEWED_SOURCE_HASHES,'ai-harness/deploy/run-engine.sh':sha256('extra')}));
 for(const full of [false,true]){assert.equal(selectPolicyFactories(policies,'H044',full).factory,policies.createCodexH044Policy);for(const api of [{...policies,CODEX_H044_WINDOW:{...policies.CODEX_H044_WINDOW}},{...policies,createCodexH044Policy:policies.createCodexH043Policy},{...policies,createCodexH044RetentionParentPolicy:policies.createCodexH043RetentionParentPolicy}])if(full||api.createCodexH044Policy!==policies.createCodexH044Policy||api.CODEX_H044_WINDOW!==policies.CODEX_H044_WINDOW)assert.throws(()=>selectPolicyFactories(api,'H044',full));}
 for(const version of ['v1','v2'] as const){const p=createSelectedRetentionParentPolicy(selectPolicyFactories(policies,'H044',true),'H044',fields,version);assert.equal(p.window,policies.CODEX_H044_WINDOW);assert.equal(p.collaborationVersion,version);assert.throws(()=>policies.assertCodexTextOnlyPolicy({...p}));}
 assert.throws(()=>createSelectedRetentionParentPolicy(selectPolicyFactories(policies,'H044',true),'H044',fields,undefined));
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
async function sourceTrace(t:any,mode:Exclude<CodexNativeTraceMode,'off'>,includeAuto:boolean,regular=false){
 const dir=realpathSync(mkdtempSync(join(tmpdir(),'h044-source-trace-')));t.after(()=>rmSync(dir,{recursive:true,force:true}));
 const f=receiptFixture(),uid=process.getuid!(),prefix=`user.slice/user-${uid}.slice/user@${uid}.service/aiharnesstasks.slice`;
 const configUtf8='model = "qwen3.8-27b"\nmodel_provider = "sova"\nmodel_catalog_json = "/opt/sova/codex/models.json"\n',catalogUtf8=stableJson({models:[{slug:'qwen3.8-27b',context_window:480000,max_context_window:480000,auto_compact_token_limit:400000,effective_context_window_percent:100}]}),sources={...f.binding.sources,'codex/config.toml':sha256(configUtf8),'codex/models.json':sha256(catalogUtf8)};
 const producer={...f.producer,uid,cgroupPath:'/'+prefix+'/SOURCE.scope'},binding={...f.binding,sources,uid,gid:uid,nativeTraceMode:mode};
 const rawLaunch={...f.rawLaunch,sources,producer,egress:{...f.rawLaunch.egress,uid,cgroupPath:prefix},container:{...f.rawLaunch.container,user:`${uid}:${uid}`}},rawSettlement={...f.rawSettlement,producer};
 async function read(name:'launch'|'settlement'|'trace',value:any){writeFileSync(join(dir,name+'.json'),JSON.stringify(value),{mode:0o600,flag:'wx'});writeFileSync(join(dir,name+'.ready'),'',{mode:0o600,flag:'wx'});return waitCodexReceiptFile(dir,uid,name,100,()=>true);}
 const launch=validateCodexLaunchReceipt(await read('launch',rawLaunch),binding,producer,f.now),settlement=validateCodexSettlementReceipt(await read('settlement',rawSettlement),binding,launch,f.now+1);
 const spans=[{name:'turn','thread.id':'SOURCE-native-thread','turn.id':'SOURCE-native-turn'}];
 const numeric={timestamp:'2026-10-02T00:05:00.000000001Z',level:'TRACE',target:'codex_core::session::turn',fields:{message:'post sampling token usage',turn_id:'SOURCE-native-turn',total_usage_tokens:400001,auto_compact_scope_tokens:400001,auto_compact_scope_limit:'Some(400000)',auto_compact_limit_scope:'Total',auto_compact_window_prefill_tokens:'None',full_context_window_limit:'Some(480000)',full_context_window_limit_reached:false,token_limit_reached:true,model_needs_follow_up:true,has_pending_input:false,needs_follow_up:true},spans,span:spans[0]};
 const auto={timestamp:'2026-10-02T00:05:00.000000002Z',level:'TRACE',target:'codex_core::session::turn',fields:{message:'new'},spans,span:{name:'run_auto_compact',reason:'ContextLimit',phase:'MidTurn'}};
 if(regular)Object.assign(numeric.fields,{total_usage_tokens:120000,auto_compact_scope_tokens:120000,token_limit_reached:false,needs_follow_up:false});
 const v2=mode==='post-sampling-token-usage-v2',originals=[numeric,...(includeAuto?[auto]:[])].map(x=>JSON.stringify(x)+'\n');let offset=0;
 const events=originals.map((lineUtf8,i)=>{const raw=JSON.parse(lineUtf8),bytes=Buffer.byteLength(lineUtf8),event={file:`trace-event-${String(i).padStart(4,'0')}.raw`,sha256:sha256(lineUtf8),bytes,stderrSequence:i+1,stderrOffset:offset,chain:sha256('SOURCE-chain-'+i),turnId:'SOURCE-native-turn',nativeTimestamp:raw.timestamp,observedAtMs:now,observedMonotonicNs:i+1,...(v2?{kind:i?'autoCompactNew':'postSampling',threadId:'SOURCE-native-thread'}:{})};offset+=bytes;writeFileSync(join(dir,event.file),lineUtf8,{mode:0o600,flag:'wx'});return event;});
 const trace={schema:v2?'codex-native-trace-v2':'codex-native-trace-v1',mode,nonce:binding.nonce,sessionId:binding.sessionId,runId:binding.runId,producer,containerId:launch.container.id,environment:{RUST_LOG:v2?'off,codex_core::session::turn=trace,codex_core::tasks=info':'off,codex_core::session::turn=trace',LOG_FORMAT:'json'},sources:binding.sources,events,stderrBytes:offset,stderrSHA256:sha256(originals.join('')),stderrChain:sha256('SOURCE-stream'),complete:true,cleanupOk:true,engineExitStatus:settlement.engineExitStatus,requestedStop:settlement.requestedStop};
 const receipt=validateCodexTraceReceipt(await read('trace',{...trace,...(v2?{autoCalls:events.filter(e=>e.kind==='autoCompactNew')}:{})}),binding,launch,settlement);
 const carrier={launchReceiptUtf8:getCodexReceiptUtf8(launch)!,launchReceiptSha256:sha256(getCodexReceiptUtf8(launch)!),settlementReceiptUtf8:getCodexReceiptUtf8(settlement)!,settlementReceiptSha256:sha256(getCodexReceiptUtf8(settlement)!)};
 return {receipt,carrier,originals,events,configUtf8,catalogUtf8,dir,expected:{sessionId:launch.sessionId,receiptSources:launch.sources}};
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
test('SOURCE H044 factories and V2 observer are source resolved; absent native qualification still prevents generation',async t=>{
 t.mock.method(Date,'now',()=>now);assert.doesNotThrow(()=>assertNormalProductTraceReady('post-sampling-token-usage-v2'));assert.doesNotThrow(()=>assertNormalProductTraceReady('off'));assert.doesNotThrow(()=>assertNormalProductTraceReady('post-sampling-token-usage-v1'));assert.throws(()=>assertNormalProductTraceReady('invented' as never));
 const plan={source:'SOURCE-plan'},r={...review(),automaticPlan:plan},p=new NormalProductProducer({sessionId:fields.sessionId,review:r},{qualificationSha256:sha256('SOURCE')} as never),ready=p.prepareAutomatic(plan,new AbortController().signal);
 assert.equal(ready.generationAllowed,false);assert.equal(ready.status,'NOT_TESTED');
 let calls=0;const host={qualification:{},client:{sessionId:fields.sessionId,request:()=>{calls++;throw Error('SOURCE forbidden');}}} as never;
 await assert.rejects(runOrdinarySupplement({...r,approvedBy:'root',actor:'worker1'},{},host,'/SOURCE-unused',new AbortController().signal),/root_reviewed_actual_ordinary/);
 await assert.rejects(runOneAutomatic(r,{},'SOURCE-no-manual-proof',host,'/SOURCE-unused',new AbortController().signal),/actual_manual_receipt/);assert.equal(calls,0);
});
function regularFrames(){
 const values=[
  ['to-native',{id:1,method:'turn/start',params:{threadId:'SOURCE-native-thread'}}],
  ['from-native',{id:1,result:{turn:{id:'SOURCE-native-turn'}}}],
  ['from-native',{method:'turn/started',params:{threadId:'SOURCE-native-thread',turn:{id:'SOURCE-native-turn'}}}],
  ['from-native',{method:'item/started',params:{threadId:'SOURCE-native-thread',turnId:'SOURCE-native-turn',item:{id:'SOURCE-message',type:'agentMessage'}}}],
  ['from-native',{method:'item/completed',params:{threadId:'SOURCE-native-thread',turnId:'SOURCE-native-turn',item:{id:'SOURCE-message',type:'agentMessage'}}}],
  ['from-native',{method:'turn/completed',params:{threadId:'SOURCE-native-thread',turn:{id:'SOURCE-native-turn',status:'completed'}}}],
 ];return values.map(([direction,value],i)=>{const bytesUtf8=JSON.stringify(value)+'\n';return {direction,value,bytesUtf8,sha256:sha256(bytesUtf8),sequence:i,observedAt:'2026-10-02T00:05:00Z'};});
}
async function readinessFixture(t:any,mode:Exclude<CodexNativeTraceMode,'off'>='post-sampling-token-usage-v2'){
 const f=await sourceTrace(t,mode,false,true),packet=projectNormalProductTrace(f.receipt,mode,f.carrier,f.expected),frames=regularFrames();
 const expected={...f.expected,mode,runId:f.receipt.runId,launchNonce:f.receipt.nonce,nativeThreadId:'SOURCE-native-thread',nativeTurnId:'SOURCE-native-turn',framesSha256:sha256(stableJson(frames))};
 const resolvedConfig={contextWindow:480000,autoCompactTokenLimit:400000,maxOutputTokens:65536,effectiveScope:'total',tokenBudgetEnabled:false,fallbackBufferTokens:0,postTurnPercent:0},sourceRevision='064c6b8c737f5b41d171fdda80bd9ef10ad06eb3';
 // Deliberately SOURCE text. Only the pure source contract is exercised here;
 // this fixture has no EntryQualification, Linux/readback or generation brand.
 const rules=['effectiveScope','tokenBudgetEnabled','fallbackBufferTokens','postTurnPercent'].map(key=>{const spanUtf8=`SOURCE fixture ${key}=${resolvedConfig[key as keyof typeof resolvedConfig]}`,originalUtf8=spanUtf8+'\n';return {key,value:resolvedConfig[key as keyof typeof resolvedConfig],sourceRevision,originalUtf8,startByte:0,endByte:Buffer.byteLength(spanUtf8)};});
 const projection={version:'0.158.0',sourceRevision,sessionId:f.receipt.sessionId,runId:f.receipt.runId,launchNonce:f.receipt.nonce,configSha256:sha256(f.configUtf8),catalogSha256:sha256(f.catalogUtf8),resolvedConfig,sourceRules:rules};
 const originals={configUtf8:f.configUtf8,catalogUtf8:f.catalogUtf8,projectionUtf8:stableJson(projection)},spec={sourceRevision,configSha256:sha256(f.configUtf8),catalogSha256:sha256(f.catalogUtf8),projectionSha256:sha256(originals.projectionUtf8),resolvedConfigSha256:sha256(stableJson(resolvedConfig)),sourceRules:rules.map(r=>({...r,originalSha256:sha256(r.originalUtf8),spanUtf8:r.originalUtf8.slice(0,-1),spanSha256:sha256(r.originalUtf8.slice(0,-1))}))};
 return {f,packet,frames,expected,projection,originals,spec};
}
for(const mode of ['post-sampling-token-usage-v1','post-sampling-token-usage-v2'] as const)test(`SOURCE actual ${mode} config projection + completed original regular item-span exclusion is executable`,async t=>{
 const x=await readinessFixture(t,mode),config=projectAutomaticConfig(x.originals,x.spec,x.packet),regular=verifyRegularSamplingExclusion(x.packet,x.frames,x.expected);
 assert.equal(config.status,'SOURCE_VALID');assert.equal(config.nativeAcceptance,'NOT_TESTED');assert.equal(config.resolvedConfigSha256,x.spec.resolvedConfigSha256);assert.equal(regular.status,'SOURCE_VALID');assert.equal(regular.generationAllowed,false);assert.equal(regular.totalUsageTokens,120000);assert.deepEqual(regular.autoCalls,[]);assert.ok(Object.isFrozen(config));assert.ok(Object.isFrozen(x.packet));
});
for(const [name,change] of [
 ['missing config',(x:any)=>delete x.originals.configUtf8],['changed original config',(x:any)=>x.originals.configUtf8+=' '],['changed original catalog',(x:any)=>x.originals.catalogUtf8+=' '],['changed original projection',(x:any)=>x.originals.projectionUtf8+=' '],['missing projection hash',(x:any)=>delete x.spec.projectionSha256],['changed config hash',(x:any)=>x.spec.configSha256=sha256('foreign')],['changed catalog hash',(x:any)=>x.spec.catalogSha256=sha256('foreign')],['copied receipt brand',(x:any)=>x.packet=structuredClone(x.packet)],
 ['cross run',(x:any)=>x.projection.runId='FOREIGN'],['cross session',(x:any)=>x.projection.sessionId='FOREIGN'],['cross launch',(x:any)=>x.projection.launchNonce='f'.repeat(64)],['invalid native version',(x:any)=>x.projection.version='0.159.2'],['changed upstream',(x:any)=>x.projection.sourceRevision='changed'],['different effective scope',(x:any)=>x.projection.resolvedConfig.effectiveScope='prefill'],['token budget enabled',(x:any)=>x.projection.resolvedConfig.tokenBudgetEnabled=true],['fallback buffer',(x:any)=>x.projection.resolvedConfig.fallbackBufferTokens=1],['post-turn percentage',(x:any)=>x.projection.resolvedConfig.postTurnPercent=1],['changed400k',(x:any)=>x.projection.resolvedConfig.autoCompactTokenLimit=399999],['changed480k',(x:any)=>x.projection.resolvedConfig.contextWindow=480001],['changed output',(x:any)=>x.projection.resolvedConfig.maxOutputTokens=32768],['invented config field',(x:any)=>x.projection.resolvedConfig.invented=false],['missing original source rules',(x:any)=>delete x.projection.sourceRules],['changed original causal source',(x:any)=>x.projection.sourceRules[0].originalUtf8+=' '],['changed causal span',(x:any)=>x.projection.sourceRules[0].startByte++],['missing original source hash',(x:any)=>delete x.spec.sourceRules[0].originalSha256],['wrong source span digest',(x:any)=>x.spec.sourceRules[0].spanSha256=sha256('different')],
 ] as const)test(`SOURCE readiness config rejects ${name}`,async t=>{
 const x=await readinessFixture(t);change(x);if(!name.includes('original projection')){x.originals.projectionUtf8=stableJson(x.projection);x.spec.projectionSha256=sha256(x.originals.projectionUtf8);if(name==='missing projection hash')delete (x.spec as any).projectionSha256;}
 assert.throws(()=>projectAutomaticConfig(x.originals,x.spec,x.packet));
});
for(const [name,change] of [
 ['missing numeric brand',(x:any)=>x.packet=structuredClone(x.packet)],['cross run',(x:any)=>x.expected.runId='FOREIGN'],['cross mode',(x:any)=>x.expected.mode='post-sampling-token-usage-v1'],['off mode',(x:any)=>x.expected.mode='off'],['cross thread',(x:any)=>x.expected.nativeThreadId='FOREIGN'],['cross turn',(x:any)=>x.expected.nativeTurnId='FOREIGN'],['missing original item spans',(x:any)=>x.frames=x.frames.filter((f:any)=>!f.value.method?.startsWith('item/'))],['missing item terminal',(x:any)=>x.frames=x.frames.filter((f:any)=>f.value.method!=='item/completed')],['changed original hash',(x:any)=>x.frames[2].sha256=sha256('changed')],['duplicate causal span',(x:any)=>x.frames.push(x.frames[3])],['unsettled regular terminal',(x:any)=>x.frames[5].value.params.turn.status='failed'],['manual compaction span',(x:any)=>x.frames[3].value.params.item.type='contextCompaction'],['cross item turn',(x:any)=>x.frames[4].value.params.turnId='FOREIGN'],['mismatched item type',(x:any)=>x.frames[4].value.params.item.type='toolCall'],['changed original caller hash',(x:any)=>x.expected.framesSha256=sha256('foreign')],
 ] as const)test(`SOURCE readiness regular exclusion rejects ${name}`,async t=>{
 const x=await readinessFixture(t);change(x);if(!['changed original hash','changed original caller hash'].includes(name)){for(const f of x.frames){f.bytesUtf8=JSON.stringify(f.value)+'\n';f.sha256=sha256(f.bytesUtf8);}x.expected.framesSha256=sha256(stableJson(x.frames));}
 assert.throws(()=>verifyRegularSamplingExclusion(x.packet,x.frames,x.expected));
});
test('SOURCE AUTO NEW or already-at-threshold originals cannot become a regular exclusion receipt',async t=>{
 const frames=regularFrames();for(const includeAuto of [true,false]){const f=await sourceTrace(t,'post-sampling-token-usage-v2',includeAuto),packet=projectNormalProductTrace(f.receipt,'post-sampling-token-usage-v2',f.carrier,f.expected),expected={...f.expected,mode:'post-sampling-token-usage-v2',runId:f.receipt.runId,launchNonce:f.receipt.nonce,nativeThreadId:'SOURCE-native-thread',nativeTurnId:'SOURCE-native-turn',framesSha256:sha256(stableJson(frames))};assert.throws(()=>verifyRegularSamplingExclusion(packet,frames,expected));}
});
test('SOURCE finite automatic dispatch accepts exactly the reviewed ordinary turn; no manual/cross-owner/retry/input substitution',()=>{
 const input={sessionId:'SOURCE-session',threadId:'SOURCE-thread',method:'turn/start',params:{input:[{type:'text',text:'SOURCE-approved',text_elements:[]}]}};
 assert.doesNotThrow(()=>assertFiniteAutomaticTurn(input,'SOURCE-session','SOURCE-thread','SOURCE-approved',0));
 for(const mutation of [(x:any)=>x.method='thread/compact/start',(x:any)=>x.threadId='FOREIGN',(x:any)=>x.sessionId='FOREIGN',(x:any)=>x.params.input[0].text='FOREIGN',(x:any)=>x.params.input.push(x.params.input[0]),(x:any)=>x.params.input[0].text_elements.push({foreign:true})]){const x=structuredClone(input);mutation(x);assert.throws(()=>assertFiniteAutomaticTurn(x,'SOURCE-session','SOURCE-thread','SOURCE-approved',0));}
 assert.throws(()=>assertFiniteAutomaticTurn(input,'SOURCE-session','SOURCE-thread','SOURCE-approved',1));
});

test('SOURCE final R03 real ordinary factory keeps owner/run/config/catalog brands and exact H044 expiry',t=>{
 t.mock.method(Date,'now',()=>now);
 const selected=selectPolicyFactories(policies,'H044',false),p=selected.factory({...fields});
 policies.assertCodexTextOnlyPolicy(p,fields.sessionId);
 assert.equal(p.sessionId,fields.sessionId);assert.equal(p.runId,fields.runId);assert.equal(p.configSha256,fields.configSha256);assert.equal(p.modelCatalogSha256,fields.modelCatalogSha256);
 assert.throws(()=>policies.assertCodexTextOnlyPolicy({...p},fields.sessionId));
 assert.throws(()=>policies.assertCodexTextOnlyPolicy(p,'FOREIGN'));
 for(const version of ['v1','v2'] as const){
  const parent=createSelectedRetentionParentPolicy(selectPolicyFactories(policies,'H044',true),'H044',fields,version);
  assert.equal(parent.collaborationVersion,version);assert.equal(parent.mode,'retention-parent');
  assert.throws(()=>createSelectedRetentionParentPolicy(selectPolicyFactories(policies,'H044',true),'H044',{...fields,window:policies.CODEX_H043_WINDOW},version));
 }
 t.mock.method(Date,'now',()=>Date.parse(auth.capUtc));
 assert.throws(()=>policies.assertCodexTextOnlyPolicy(p,fields.sessionId));
 assert.throws(()=>createSelectedRetentionParentPolicy(selectPolicyFactories(policies,'H044',true),'H044',fields,'v2'));
 t.mock.method(Date,'now',()=>Date.parse(auth.startsUtc)-1);
 assert.throws(()=>policies.assertCodexTextOnlyPolicy(selected.factory({...fields}),fields.sessionId));
});
