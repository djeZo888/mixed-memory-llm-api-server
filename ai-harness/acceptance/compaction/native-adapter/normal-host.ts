/** Connected normal main / real subprocess / protected browser composition.
 * No factory call runs at import. Both processes independently qualify the same
 * immutable protected packet; an IPC copy never receives a qualification brand. */
import {qualifyEntry,type EntryQualification} from './qualification.js';
import {NormalApplicationRunner} from './normal-runner.js';
import {NormalBrowser} from './normal-browser.js';
import {OrdinaryClient} from './ordinary-client.js';
import type {OrdinaryHost} from './ordinary-runner.js';
import {privateFile} from './checkpoint.js';
import {sha256,stableJson,reviewSnapshot} from './projection.js';
import {reviewedAuthorization} from '../authorization.mjs';
import {verifyNormalRecovery} from '../ordinary-proof.mjs';
export class NormalOrdinaryHost implements OrdinaryHost {
 readonly client:OrdinaryClient;
 private fault?:{checkpointId:string;baseline:any};
 constructor(readonly qualification:EntryQualification,private runner:NormalApplicationRunner,private browser:NormalBrowser,readonly config:any){this.client=new OrdinaryClient(config.sessionId,browser,config.hostPrivate);}
 private active(signal:AbortSignal){signal.throwIfAborted();if(Date.now()>=reviewedAuthorization(this.config.review).dispatchCutoffAt)throw Error('normal_host_dispatch_cutoff');}
 async captureSettled(sessionId:string,signal:AbortSignal){if(sessionId!==this.config.sessionId)throw Error('foreign_normal_host');return this.runner.call('baseline',{},signal);}
 settleRun(sessionId:string,runId:string,signal:AbortSignal){if(sessionId!==this.config.sessionId)throw Error('foreign_normal_run');return this.runner.call('settleRun',{runId},signal);}
 browserReview(sessionId:string,proposalId:string,expectedVersion:string|null,signal:AbortSignal){this.active(signal);return this.browser.review(sessionId,proposalId,expectedVersion,signal);}
 browserReconnect(sessionId:string,signal:AbortSignal,activity:{generate(text:string):Promise<unknown>;approvedTexts:string[]}){this.active(signal);return this.browser.reconnect(sessionId,signal,activity);}
 async restart(sessionId:string,baseline:any,signal:AbortSignal){this.active(signal);const value=await this.runner.restart(sessionId,baseline,signal);this.active(signal);return value;}
 async createVerificationFault(sessionId:string,plan:any,baseline:any,signal:AbortSignal){this.active(signal);if(baseline.sessionId!==sessionId)throw Error('exact_pre_fault_baseline_required');await this.runner.call('armVerificationFault',{plan,baseline},signal);this.active(signal);const response=await this.client.request('/compact','POST',{actionId:crypto.randomUUID()},signal,202),settled=await this.settleRun(sessionId,response.value.runId,signal);if(settled.nativeOutcome!=='failed')throw Error('actual_completed_compaction_fault_not_observed');const rows=await this.runner.call('recoveryRows',{checkpointId:undefined,runId:response.value.runId},signal),checkpoint=JSON.parse(rows.checkpointUtf8);if(checkpoint.status!=='recovery_required'||checkpoint.runId!==response.value.runId||checkpoint.verification?.status!=='rejected'||!checkpoint.verification.physicalCompactions.length)throw Error('actual_sticky_replacement_verification_fault_required');this.fault={checkpointId:checkpoint.id,baseline};return {sessionId,checkpointId:checkpoint.id,nativeOutcome:'failed'};}
 async recoveryCapture(sessionId:string,checkpointId:string,signal:AbortSignal){if(sessionId!==this.config.sessionId||checkpointId!==this.fault?.checkpointId)throw Error('foreign_normal_recovery');const capture=await this.runner.call('recoveryCapture',{checkpointId},signal);if(capture.recoveryReceiptUtf8){const v=verifyNormalRecovery(capture,{...this.config.review.normalProductProof,sessionId,checkpointId,beforeBaselineSha256:sha256(stableJson(this.fault.baseline)),acceptedVersionBodySha256:this.fault.baseline.acceptedStateSha256,receiptSources:this.qualification.receiptSources});if(v.status!=='SOURCE_VALID')throw Error('actual_normal_recovery_producer_independent_verification');}return capture;}
 async prepareAutomatic(sessionId:string,plan:any,signal:AbortSignal){this.active(signal);if(sessionId!==this.config.sessionId)throw Error('foreign_normal_auto');const r=await this.runner.call('prepareAutomatic',{plan},signal);this.active(signal);return r;}
 async automaticCapture(sessionId:string,runId:string,operationId:string,baseline:any,signal:AbortSignal){if(sessionId!==this.config.sessionId)throw Error('foreign_normal_auto');return this.runner.call('automaticCapture',{runId,operationId,baseline},signal);}
 async close(){this.browser.close();return this.runner.shutdown();}
}
export async function createNormalOrdinaryHost(path:string,signal:AbortSignal){
 const config=reviewSnapshot(JSON.parse((await privateFile(path)).toString('utf8')));if(process.platform!=='linux'||!process.getuid?.()||config.review?.approvedBy!=='root'||config.review.actor!=='worker1'||config.enabled!==true)throw Error('reviewed_linux_normal_host_only');
 const qualification=await qualifyEntry(config.qualificationConfig),workerBytes=await privateFile(config.runner.configPath);if(sha256(workerBytes)!==config.runner.configSha256)throw Error('exact_normal_worker_config_hash');const worker=JSON.parse(workerBytes.toString('utf8'));if(stableJson(worker.qualificationConfig)!==stableJson(config.qualificationConfig)||worker.sessionId!==config.sessionId||worker.dataDir!==config.review.normalProductProof.dataDir||stableJson(worker.review)!==stableJson(config.review))throw Error('outer_and_worker_exact_protected_packet_required');
 const graph=JSON.parse((await privateFile(config.qualificationConfig.sourceBuildManifestPath)).toString('utf8')).importGraph;if(!graph.entrypoints.includes('ai-harness/acceptance/compaction/native-adapter/normal-entry.js')||!graph.entrypoints.includes('ai-harness/acceptance/compaction/native-adapter/normal-worker.js'))throw Error('normal_executable_graph_not_reviewed');
 const runner=new NormalApplicationRunner({...config.runner,review:config.review,hostPrivate:config.hostPrivate},{...config.review.normalProductProof,sessionId:config.sessionId,qualificationSha256:qualification.qualificationSha256,receiptSources:qualification.receiptSources}),browser=new NormalBrowser({...config.browser,reviewedDraft:config.plan.reviewedDraft,sessionId:config.sessionId,hostPrivate:config.hostPrivate,review:config.review});try{await runner.start(signal);signal.throwIfAborted();await browser.connect(signal);signal.throwIfAborted();return new NormalOrdinaryHost(qualification,runner,browser,config);}catch(error){browser.close();await runner.shutdown();throw error;}
}
export default Object.freeze({enabled:false,capabilities:[],nativeAcceptance:'NOT_TESTED'});
