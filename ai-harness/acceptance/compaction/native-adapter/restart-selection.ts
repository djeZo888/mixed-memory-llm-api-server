import {sha256} from './projection.js';
import type {Store} from '../../../server/src/store.js';
export type RestartPurpose='settled-compaction'|'accepted-continuation';
/** Select the actual latest completed Store run. A genuine protected Store proof
 * is issued separately; this selector never brands input IDs or receipt JSON. */
export function selectRestartCheckpoint(store:Store,sessionId:string,nativeThreadId:string,checkpoint:any,accepted?:any) {
 if(checkpoint?.nativeThreadId!==nativeThreadId||sha256(checkpoint.stateUtf8)!==checkpoint.stateSha256)throw Error('exact_owned_restart_state_required');
 const purpose:RestartPurpose=accepted?'accepted-continuation':'settled-compaction';
 const run=store.runs(sessionId).at(-1),record=store.checkpoints.status(sessionId).find(c=>c.runId===run?.id);
 if(!run||run.status!=='completed'||!record||record.status!=='settled'||record.nativeThreadId!==nativeThreadId)throw Error('latest_completed_protected_store_checkpoint_required');
 if(purpose==='settled-compaction'){
  if(run.kind!=='compact'||!record.compactions.length||record.compactions.some(c=>c.status!=='completed')||typeof checkpoint.settledOperationUtf8!=='string'||sha256(checkpoint.settledOperationUtf8)!==checkpoint.settledOperationSha256)throw Error('actual_latest_compaction_baseline_required_before_artifacts');
  const operation=JSON.parse(checkpoint.settledOperationUtf8);
  if(operation.nativeThreadId!==nativeThreadId||operation.status!=='completed'||operation.settlement!=='released'||operation.postStateSha256!==checkpoint.stateSha256||!record.compactions.some(c=>c.id===operation.compactionId))throw Error('latest_store_compaction_and_full_state_binding_required');
 }else if(accepted.artifactBaseline?.storeRunId!==run.id||accepted.artifactBaseline?.checkpointStateSha256!==checkpoint.stateSha256||accepted.artifactBaseline?.sessionId!==sessionId||accepted.artifactBaseline?.actionId!==accepted.actionId||accepted.artifactBaseline?.nativeThreadId!==nativeThreadId)throw Error('latest_accepted_continuation_checkpoint_required');
 return {purpose,storeRunId:run.id,checkpointId:record.id};
}
