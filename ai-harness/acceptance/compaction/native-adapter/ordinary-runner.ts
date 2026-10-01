import {randomUUID} from 'node:crypto';
import {join} from 'node:path';
import {reviewedAuthorization} from '../authorization.mjs';
import {validateRecord} from '../evidence.mjs';
import {verifyNormalRestart,verifyNormalRecovery} from '../ordinary-proof.mjs';
import {verifyAutomaticCapture} from '../ordinary.mjs';
import {verifyBrowserHumanReceipt,verifyBrowserReconnectReceipt} from './browser-evidence.js';
import {OrdinaryClient,parseOrdinarySse} from './ordinary-client.js';
import {durableFile} from './checkpoint.js';
import {identifier,sha256,stableJson,reviewSnapshot} from './projection.js';
import {isQualifiedEntry,type EntryQualification} from './qualification.js';
export const ORDINARY_BUDGET=Object.freeze({generationTurns:10,manualCompactions:2,automaticCompactions:1,applicationRestarts:1});
export interface OrdinaryHost {
 qualification:EntryQualification;
 /** Already authenticated actual browser/API context; never inject proxy keys. */
 client:OrdinaryClient;
 captureSettled(sessionId:string,signal:AbortSignal):Promise<any>;
 settleRun(sessionId:string,runId:string,signal:AbortSignal):Promise<any>;
 browserReview(sessionId:string,proposalId:string,expectedVersion:string|null,signal:AbortSignal):Promise<{receiptUtf8:string}>;
 browserReconnect(sessionId:string,signal:AbortSignal,activity:{generate(text:string):Promise<unknown>;approvedTexts:string[]}):Promise<{receiptUtf8:string;beforeUtf8:string;afterUtf8:string;cursor:number;initialCursor:number}>;
 restart?(sessionId:string,baseline:any,signal:AbortSignal):Promise<any>;
 recoveryCapture?(sessionId:string,checkpointId:string,signal:AbortSignal):Promise<any>;
 /** Root-frozen bounded fault after O1–O6. Not an old unresolved checkpoint. */
 createVerificationFault?(sessionId:string,reviewedFault:any,baseline:any,signal:AbortSignal):Promise<any>;
 prepareAutomatic?(sessionId:string,plan:any,signal:AbortSignal):Promise<any>;
 automaticCapture?(sessionId:string,runId:string,operationId:string,baseline:any,signal:AbortSignal):Promise<any>;
}
/** Read-only gate on independently root-reviewed native manual output bytes.
 * Source fixtures cannot satisfy it by status strings or a stage-only PASS. */
export function requireFullManualReceipt(bytes:string,expectedSha256:string){
 if(sha256(bytes)!==expectedSha256)throw Error('root_frozen_actual_manual_receipt_required');const r=JSON.parse(bytes);
 if(r.qualification!=='native'||r.profile!=='h041-full-retention-v1'||r.status!=='PASS'||r.nativeAcceptance!=='PASS'||r.semanticAcceptance!=='PASS'||!identifier(r.runId)||!Array.isArray(r.records)||r.records.length!==12||r.records.some((record:any)=>record.qualification!=='native'||record.status!=='PASS'||validateRecord(record).length))throw Error('actual_full_manual_native_PASS_required_before_automatic');
 return r;
}
/** Actual normal product endpoints only; no temporary private adapter startup.
 * Host callbacks retain native/browser/process evidence outside model mounts.
 * SOURCE_VALID never promotes normal UI or native acceptance to PASS. */
export function assertOrdinaryDispatch(authorization:{dispatchCutoffAt:number},signal:AbortSignal,now=Date.now()){if(signal.aborted||now>=authorization.dispatchCutoffAt)throw Error('ordinary_dispatch_cutoff_no_replay');}
export async function runOrdinarySupplement(review:any,plan:any,host:OrdinaryHost,directory:string,signal:AbortSignal){
 review=reviewSnapshot(review);plan=reviewSnapshot(plan);
 const a=reviewedAuthorization(review);if(!isQualifiedEntry(host.qualification)||review.approvedBy!=='root'||review.actor!=='worker1'||!['H041-COMPACTION-DELIVERY-04','H041-COMPACTION-DELIVERY-05'].includes(review.authorization.task)||sha256(stableJson(plan))!==review.planSha256||stableJson(plan.budgets)!==stableJson(ORDINARY_BUDGET)||Date.now()>=a.dispatchCutoffAt)throw Error('root_reviewed_actual_ordinary_runner_required');
 const sessionId=host.client.sessionId,runId=randomUUID(),steps:any[]=[],receipts:any[]=[];let turns=0,manual=0,restarts=0;
 const active=()=>assertOrdinaryDispatch(a,signal);
 const save=async(id:string,value:any)=>{const bytes=stableJson(value),receiptId=randomUUID();await durableFile(join(directory,`${runId}-${id}-${receiptId}.json`),bytes);receipts.push({id,receiptId,sha256:sha256(bytes)});return value;};
 const generation=async(text:string)=>{active();if(++turns>10||!text||Buffer.byteLength(text)>2000000)throw Error('ordinary_turn_budget_or_frozen_input');const q=await host.client.request('/messages','POST',{text,submissionId:randomUUID(),attachmentIds:[]},signal,202);if(!identifier(q.value.runId))throw Error('actual_normal_store_run_required');const result=await host.settleRun(sessionId,q.value.runId,signal);await save('native-operation',result);if(result.nativeOutcome!=='completed'||result.settlement?.state!=='released')throw Error('ordinary_failed_native_operation_no_retry');return q.value.runId;};
 try{
  const before=await host.captureSettled(sessionId,signal);await save('O1-baseline',before);
  const view=(await host.client.request('/memory','GET',undefined,signal)).value;
  const descriptors=plan.originalSha256s.map((hash:string)=>{const matches=view.references.filter((r:any)=>r.sha256===hash&&r.availability==='complete');if(matches.length!==1)throw Error('actual_original_missing_or_ambiguous');return matches[0];});
  for(const descriptor of descriptors){await save('O1-original',await host.client.readOriginal(descriptor,signal));const search=await host.client.searchLiteral(plan.literalQuery,descriptor.id,signal);if(!Array.isArray(search.value.hits)||search.value.hits.some((h:any)=>h.id!==descriptor.id||h.sha256!==descriptor.sha256)||!search.value.hits.length)throw Error('owned_literal_search_not_observed');}
  steps.push({id:'O1',status:'SOURCE_VALID'});
  active();if(++manual>2)throw Error('manual_budget');const actionId=randomUUID(),compact=await host.client.request('/compact','POST',{actionId},signal,202);const compacted=await host.settleRun(sessionId,compact.value.runId,signal);await save('O2-compact',compacted);if(compacted.nativeOutcome!=='completed'||compacted.settlement?.state!=='released'||compacted.nativeThreadId!==before.nativeThreadId)throw Error('normal_manual_compaction_failure');
  for(const descriptor of descriptors)await save('O2-original',await host.client.readOriginal(descriptor,signal));active();const duplicateBefore=await host.captureSettled(sessionId,signal);active();const duplicate=await host.client.request('/compact','POST',{actionId},signal,202);const duplicateAfter=await host.captureSettled(sessionId,signal);if(duplicate.value.runId!==compact.value.runId||duplicateAfter.nativeThreadId!==duplicateBefore.nativeThreadId||duplicateAfter.stateSha256!==duplicateBefore.stateSha256||!Number.isSafeInteger(duplicateBefore.gatewayAdmissionSequence)||duplicateAfter.gatewayAdmissionSequence!==duplicateBefore.gatewayAdmissionSequence)throw Error('actual_manual_duplicate_no_dispatch_evidence_required');steps.push({id:'O2',status:'SOURCE_VALID'});
  const allowed=new Map(descriptors.map((d:any)=>[d.id,d.sha256]));for(const list of ['constraints','decisions','pending','checks'])for(const item of plan.reviewedDraft[list]??[])if(!Array.isArray(item.sources)||!item.sources.length||item.sources.some((ref:any)=>allowed.get(ref.id)!==ref.sha256))throw Error('reviewed_state_source_not_current_owned_original');
  const prior=(await host.client.request('/memory','GET',undefined,signal)).value.current?.id??null;active();const proposal=await host.client.request('/memory/proposals','POST',{state:plan.reviewedDraft},signal);
  if(!identifier(proposal.value.id))throw Error('actual_proposal_id_required');active();const browser=await host.browserReview(sessionId,proposal.value.id,prior,signal);await save('O3-human-browser',browser);if(verifyBrowserHumanReceipt(browser.receiptUtf8,sessionId,proposal.value.id,prior).status!=='SOURCE_VALID')throw Error('actual_human_browser_click_and_request_required');
  const accepted=(await host.client.request('/memory','GET',undefined,signal)).value.current;
  if(!accepted||accepted.id===prior||stableJson(accepted.state)!==stableJson(plan.reviewedDraft)||accepted.acceptedBy!=='human'||accepted.trustedChecks.some((c:any)=>c.status!=='unknown'&&!c.receiptId))throw Error('actual_human_state_and_trusted_checks_required');
  active();await host.client.request('/memory/accept','POST',{proposalId:proposal.value.id,expectedVersion:prior},signal,409);steps.push({id:'O3',status:'SOURCE_VALID'});
  await generation(plan.continuationText);const continued=await host.captureSettled(sessionId,signal);await save('O4-continuation',continued);if(continued.nativeThreadId!==before.nativeThreadId)throw Error('ordinary_parent_identity_changed');steps.push({id:'O4',status:'SOURCE_VALID'});
  if(host.restart){active();if(++restarts>1)throw Error('restart_budget');const restarted=await host.restart(sessionId,continued,signal);await save('O5-restart',restarted);const verified=verifyNormalRestart(restarted,{...review.normalProductProof,sessionId,beforeBaselineSha256:sha256(stableJson(continued)),receiptSources:host.qualification.receiptSources});if(verified.status!=='SOURCE_VALID')throw Error('actual_normal_restart_independent_evidence_failed');for(const descriptor of descriptors)await host.client.readOriginal(descriptor,signal);steps.push({id:'O5',status:'SOURCE_VALID',nativeAcceptance:'NOT_TESTED'});}else steps.push({id:'O5',status:'NOT_TESTED'});
  const stream=await host.browserReconnect(sessionId,signal,{generate:generation,approvedTexts:plan.sseGenerationTexts});await save('O6-browser-sse',stream);if(verifyBrowserReconnectReceipt(stream.receiptUtf8,sessionId).status!=='SOURCE_VALID')throw Error('actual_browser_network_reconnect_receipt_required');const first=parseOrdinarySse(Buffer.from(stream.beforeUtf8),sessionId,stream.initialCursor),second=parseOrdinarySse(Buffer.from(stream.afterUtf8),sessionId,stream.cursor);const network=JSON.parse(stream.receiptUtf8),networkFrames=network.events.filter((e:any)=>e.method==='Network.eventSourceMessageReceived');if(networkFrames.length!==first.events.length+second.events.length||networkFrames.some((f:any,i:number)=>stableJson(JSON.parse(f.data))!==stableJson([...first.events,...second.events][i])||Number(f.eventId)!==[...first.events,...second.events][i].id)||verifyBrowserReconnectReceipt(stream.receiptUtf8,sessionId).cursor!==second.cursor||stream.cursor!==first.cursor||!second.events.length)throw Error('actual_browser_reconnect_cursor_evidence_required');steps.push({id:'O6',status:'SOURCE_VALID'});
  if(plan.reviewedVerificationFault&&host.createVerificationFault&&host.recoveryCapture){
   active();if(plan.reviewedVerificationFault.kind!=='manual-replacement-verification'||++manual>2)throw Error('controlled_second_manual_fault_budget');const faultBaseline=await host.captureSettled(sessionId,signal);active();const fault=await host.createVerificationFault(sessionId,plan.reviewedVerificationFault,faultBaseline,signal);if(!identifier(fault.checkpointId)||fault.sessionId!==sessionId||fault.nativeOutcome!=='failed')throw Error('actual_new_controlled_verification_fault_required');
   const preserved=await host.recoveryCapture(sessionId,fault.checkpointId,signal);await save('O7-preserved-failure',preserved);if(preserved.nativeOutcome!=='failed'||typeof preserved.failedRunUtf8!=='string'||preserved.beforeBaselineSha256!==sha256(stableJson(faultBaseline)))throw Error('actual_failed_checkpoint_inventories_required');
   active();await host.client.request(`/memory/recovery/${encodeURIComponent(fault.checkpointId)}/acknowledge`,'POST',{note:plan.recoveryNote},signal);active();const recovered=await host.client.request(`/memory/recovery/${encodeURIComponent(fault.checkpointId)}/recover`,'POST',{},signal);await save('O7-recovery',recovered);const after=await host.recoveryCapture(sessionId,fault.checkpointId,signal);
   if(after.failedRunUtf8!==preserved.failedRunUtf8||!after.recoveryReceiptUtf8)throw Error('actual_fresh_no_replay_recovery_preservation_producer_required');for(const descriptor of descriptors)await host.client.readOriginal(descriptor,signal);const verified=verifyNormalRecovery(after,{...review.normalProductProof,sessionId,checkpointId:fault.checkpointId,beforeBaselineSha256:sha256(stableJson(faultBaseline)),acceptedVersionBodySha256:faultBaseline.acceptedStateSha256,receiptSources:host.qualification.receiptSources});if(verified.status!=='SOURCE_VALID')throw Error('actual_normal_recovery_independent_evidence_failed');steps.push({id:'O7',status:'SOURCE_VALID',nativeOutcome:'failed',nativeAcceptance:'NOT_TESTED'});
  }else steps.push({id:'O7',status:'NOT_TESTED'});
  steps.push({id:'O8',status:'NOT_TESTED'});
 }catch(error){await save('failure',{source:'owned-ordinary-supplement-failure',failure:'critical-retention-scope-settlement-or-protocol-failure',automaticReplay:false,prospectiveExit:null});throw Error('ordinary_supplement_failed_preserved_no_retry',{cause:error});}
 return {runId,steps,receipts,budgetsUsed:{generationTurns:turns,manualCompactions:manual,applicationRestarts:restarts,automaticCompactions:0},nativeAcceptance:'NOT_TESTED',limitation:'Protected HTTP and producer bytes require root independent native/UI qualification; automatic is separate.'};
}
/** One approved normal turn only; no threshold loop, manual compaction or retry. */
export async function runOneAutomatic(review:any,plan:any,manualReceiptUtf8:string,host:OrdinaryHost,directory:string,signal:AbortSignal){
 review=reviewSnapshot(review);plan=reviewSnapshot(plan);requireFullManualReceipt(manualReceiptUtf8,review.manualQualificationSha256);const a=reviewedAuthorization(review);
 if(!isQualifiedEntry(host.qualification)||review.approvedBy!=='root'||review.actor!=='worker1'||!['H041-COMPACTION-DELIVERY-04','H041-COMPACTION-DELIVERY-05'].includes(review.authorization.task)||sha256(stableJson(plan))!==review.planSha256||plan.autoCompactTokenLimit!==400000||plan.contextWindow!==480000||plan.maxOutputTokens!==65536||plan.maximumGenerationTurns!==1||!host.automaticCapture||signal.aborted||Date.now()>=a.dispatchCutoffAt)throw Error('one_actual_qualified_auto_case_required');
 const sessionId=host.client.sessionId;if(!host.prepareAutomatic)throw Error('actual_auto_producer_readiness_unavailable');const ready=await host.prepareAutomatic(sessionId,plan,signal);if(ready.status!=='SOURCE_VALID'||ready.planSha256!==review.activeContextProducerPlanSha256||ready.sourceSha256!==review.activeContextProducerSourceSha256||ready.qualificationSha256!==host.qualification.qualificationSha256||!ready.resolvedConfigSha256)throw Error('actual_auto_producer_not_ready_no_generation');const baseline=await host.captureSettled(sessionId,signal);if(signal.aborted||Date.now()>=a.dispatchCutoffAt)throw Error('automatic_post_baseline_dispatch_cutoff');const operationId=randomUUID(),request=await host.client.request('/messages','POST',{text:plan.approvedText,submissionId:operationId,attachmentIds:[]},signal,202);
 await host.settleRun(sessionId,request.value.runId,signal);const capture=await host.automaticCapture(sessionId,request.value.runId,operationId,baseline,signal),verified=verifyAutomaticCapture(capture,{sessionId,nativeThreadId:baseline.nativeThreadId,storeRunId:request.value.runId,operationId,beforeStateSha256:baseline.stateSha256,summaryPrefix:plan.summaryPrefix,receiptSources:host.qualification.receiptSources,activeContextReceiptSha256:review.activeContextReceiptSha256,activeContextProducerPlanSha256:review.activeContextProducerPlanSha256,activeContextProducerSourceSha256:review.activeContextProducerSourceSha256,runtimeQualificationSha256:review.runtimeQualificationSha256});await durableFile(join(directory,`${operationId}-actual-automatic.json`),stableJson({capture,verified}));if(verified.status!=='SOURCE_VALID')throw Error('automatic_capture_missing_or_failed_no_retry');return verified;
}
export default Object.freeze({enabled:false,capabilities:[],nativeAcceptance:'NOT_TESTED'});
