import { privateFile, canonicalDirectory, within } from './checkpoint.js';
import { sha256, stableJson, reviewSnapshot } from './projection.js';
import { verifyObservedOwnedClose } from '../owned-close-verifier.mjs';
import { observeApplicationIdentity, type ApplicationIdentity } from './process-runner.js';
const tickets=new WeakMap<object,{configSha256:string;receiptSha256:string;ticketSha256:string;bootstrapSha256:string}>();
export interface RestartTicket {state:any;closed:any;input:any}
export function isRestartTicket(value:unknown):value is RestartTicket{return !!value&&typeof value==='object'&&tickets.has(value);}
export function assertRestartTicketForConfig(value:unknown,config:any){const b=value&&typeof value==='object'?tickets.get(value):undefined;if(!b||b.configSha256!==sha256(stableJson(config))||b.ticketSha256!==sha256(stableJson(value))||(value as RestartTicket).input.stateSha256!==b.receiptSha256)throw Error('restart_ticket_exact_config_and_handoff_required');}
export function assertRestartBootstrap(value:unknown,input:any){const b=value&&typeof value==='object'?tickets.get(value):undefined;if(!b||b.bootstrapSha256!==sha256(stableJson(input)))throw Error('restart_ticket_exact_bootstrap_required');}
type IdentityObserver=(pid:number)=>Promise<ApplicationIdentity>;
function linuxBirth(value:ApplicationIdentity) {
  return value?.source==='linux-proc'&&Number.isSafeInteger(value.pid)&&value.pid>0&&typeof value.startTicks==='string'&&/^(0|[1-9][0-9]*)$/.test(value.startTicks)&&typeof value.bootId==='string'&&value.bootId.length>0;
}
/** Narrow SOURCE-test seam. Production qualification always uses the native
 * observer. A failed identity read is not evidence that the owned PID died. */
export async function confirmOldApplicationAbsent(before:ApplicationIdentity,observe:IdentityObserver=observeApplicationIdentity):Promise<void> {
  if(!linuxBirth(before))throw Error('old_application_linux_birth_required');
  let old:ApplicationIdentity;
  try {old=await observe(before.pid);}
  catch(error) {
    const failure=error as NodeJS.ErrnoException;
    // observeApplicationIdentity also reads boot_id. Missing that file cannot
    // prove absence of the old PID, so retain the exact failed stat pathname.
    if(error instanceof Error&&failure.code==='ENOENT'&&failure.path===`/proc/${before.pid}/stat`)return;
    throw new Error('old_application_identity_read_unconfirmed',{cause:error});
  }
  if(!linuxBirth(old)||old.pid!==before.pid||old.bootId!==before.bootId)throw Error('old_application_identity_observation_mismatch');
  if(old.startTicks===before.startTicks)throw Error('old_application_still_present');
  if(BigInt(old.startTicks)<BigInt(before.startTicks))throw Error('old_application_identity_observation_mismatch');
  // The same PID and boot with a distinct, independently observed birth is the
  // only successful observation proving this old application no longer owns it.
}
/** IPC host-owned adoption, independently checked against private raw handoff,
 * actual new OS identity, actual absence of the old process, and all producer
 * bytes. Does not brand a Codex policy; A must revalidate its own durable bridge. */
export async function qualifyRestart(input:any,config:any):Promise<RestartTicket> {
  input=reviewSnapshot(input);config=reviewSnapshot(config);
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
  if(stableJson(actual)!==stableJson(input.afterProcess)||actual.bootId!==input.beforeProcess.bootId||input.beforeProcess.pid===actual.pid&&input.beforeProcess.startTicks===actual.startTicks)throw Error('new_application_process_identity_mismatch');
  await confirmOldApplicationAbsent(input.beforeProcess);
  const ticket=reviewSnapshot({state,closed:input.closed,input});tickets.set(ticket,{configSha256:sha256(stableJson(config)),receiptSha256:input.stateSha256,ticketSha256:sha256(stableJson(ticket)),bootstrapSha256:sha256(stableJson(config.bootstrap))});return ticket;
}
