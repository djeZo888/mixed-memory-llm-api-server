import { privateFile, canonicalDirectory, within } from './checkpoint.js';
import { sha256, stableJson } from './projection.js';
import { verifyObservedOwnedClose } from '../owned-close-verifier.mjs';
import { observeApplicationIdentity } from './process-runner.js';
const tickets=new WeakSet<object>();
export interface RestartTicket {state:any;closed:any;input:any}
export function isRestartTicket(value:unknown):value is RestartTicket{return !!value&&typeof value==='object'&&tickets.has(value);}
/** IPC host-owned adoption, independently checked against private raw handoff,
 * actual new OS identity, actual absence of the old process, and all producer
 * bytes. Does not brand a Codex policy; A must revalidate its own durable bridge. */
export async function qualifyRestart(input:any,config:any):Promise<RestartTicket> {
  const bytes=await privateFile(input.statePath);
  if(sha256(bytes)!==input.stateSha256)throw Error('restart_handoff_bytes_changed');
  const state=JSON.parse(bytes.toString('utf8'));
  if(state.source!=='owned-application-restart-handoff'||state.candidateCommit!==config.bootstrap.review.candidateCommit||state.windowId!==config.bootstrap.review.authorization.windowId||state.runId!==input.runId||state.parentNativeThreadId!==input.checkpoint?.nativeThreadId||stableJson(state.checkpoint)!==stableJson(input.checkpoint)||stableJson(state.acceptedContinuation)!==stableJson(input.acceptedContinuation??null)||state.checkpoint.stateSha256!==sha256(state.checkpoint.stateUtf8))throw Error('exact_restart_checkpoint_or_accepted_baseline_changed');
  const purpose=state.acceptedContinuation?'accepted-continuation':'settled-compaction';
  if(state.policyHandoff?.purpose!==purpose)throw Error('retained_restart_handoff_purpose_changed');
  for(const p of [state.layout.root,state.layout.dataDir,state.layout.hostPrivate])await canonicalDirectory(p);
  if(!within(config.bootstrap.privateBase,state.layout.root)||!within(state.layout.root,state.layout.dataDir)||!within(state.layout.root,state.layout.hostPrivate)||within(state.layout.dataDir,state.layout.hostPrivate)||!within(state.layout.hostPrivate,input.statePath))throw Error('restart_layout_outside_owned_private_scope');
  const proof=verifyObservedOwnedClose(input.closed,{runId:state.runId,operationWindowId:state.windowId,observedSettlements:state.observedSettlements,receiptSources:config.bootstrap.review.receiptSources});
  if(proof.status!=='PASS'||input.oldExit?.code!==0||input.oldExit?.signal!==null||!input.beforeProcess||!input.afterProcess||input.beforeProcess.source!=='linux-proc'||input.afterProcess.source!=='linux-proc')throw Error('actual_old_application_exit_and_owned_close_required');
  const actual=await observeApplicationIdentity(process.pid);
  if(stableJson(actual)!==stableJson(input.afterProcess)||input.beforeProcess.pid===actual.pid&&input.beforeProcess.startTicks===actual.startTicks)throw Error('new_application_process_identity_mismatch');
  const old=await observeApplicationIdentity(input.beforeProcess.pid).catch(()=>undefined);
  if(old&&old.bootId===input.beforeProcess.bootId&&old.startTicks===input.beforeProcess.startTicks)throw Error('old_application_still_present');
  const ticket={state,closed:input.closed,input};tickets.add(ticket);return ticket;
}
