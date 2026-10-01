import { verifyObservedOwnedClose } from '../owned-close-verifier.mjs';
import { lstat, readdir, realpath } from 'node:fs/promises';
import { join } from 'node:path';
import { randomUUID } from 'node:crypto';
import type { Store } from '../../../server/src/store.js';
import type { Gateway } from '../../../server/src/gateway.js';
import type { RootlessCodexProcess } from '../../../server/src/codex-engine.js';
import { getCodexReceiptUtf8, isVerifiedCodexLaunchReceipt, isVerifiedCodexSettlementReceipt, type CodexNativeLaunchReceipt, type CodexNativeSettlementReceipt } from '../../../server/src/codex-receipts.js';
import { NativeObserver } from './native-observer.js';
import { durableFile } from './checkpoint.js';
import { sha256, stableJson } from './projection.js';
import { verifyObservedModelScope,verifyObservedDelegatedScope } from '../model-scope.mjs';
export type Receipt = CodexNativeLaunchReceipt | CodexNativeSettlementReceipt;
export interface EvidenceHooks { receiptUtf8(receipt: Receipt): string | undefined | Promise<string | undefined> }
interface Launch { receipt: CodexNativeLaunchReceipt; utf8: string; prelaunchUtf8: string; settlementUtf8?: string }
/** Host-private, actual branded receipts only. SOURCE synthetic peers cannot enter this registry. */
export class NativeEvidence {
  private launches = new Map<string, Launch[]>();
  private unconfirmedLaunch = false;
  private expectedActions = new Set<string>();
  expectAction(actionId: string) { this.expectedActions.add(actionId); }
  private actions = new Map<string, Record<string, unknown>>();
  constructor(private directory: string, private hooks: EvidenceHooks) {}
  private async raw(receipt: Receipt) {
    const original=getCodexReceiptUtf8(receipt);
    const bytes = await this.hooks.receiptUtf8(receipt);
    if (!original || bytes !== original) throw Error('genuine_transport_raw_provenance_required');
    if (typeof bytes !== 'string' || !Buffer.from(Buffer.from(bytes).toString('utf8')).equals(Buffer.from(bytes)) || stableJson(JSON.parse(bytes)) !== stableJson(receipt)) throw Error('exact_received_native_receipt_bytes_required');
    return bytes;
  }
  async launch(sessionId: string, input: {profileDir: string; workspace: string}, operation: () => Promise<RootlessCodexProcess>) {
    const observe = async (path: string) => {
      const s = await lstat(path);
      if (await realpath(path) !== path || !s.isDirectory() || s.isSymbolicLink() || s.uid !== process.getuid?.() || s.mode & 0o077) throw Error('prelaunch_mount_not_private_canonical');
      return { path, ino: s.ino, dev: s.dev, empty: (await readdir(path)).length === 0 };
    };
    const fresh = { source: 'owned-prelaunch-filesystem-observation', sessionId, profile: await observe(input.profileDir), workspace: await observe(input.workspace), observedAtMs: Date.now() };
    const child = await operation();
    // Claim the exact acquired process before touching a receipt, filesystem or
    // persistence callback. Every post-acquisition exception awaits this owner.
    let value: Launch | undefined, receipt: CodexNativeLaunchReceipt | undefined;
    let cleanup: Promise<boolean> | undefined;
    const bounded = async <T>(promise: Promise<T>, label: string): Promise<T> => {
      let timer: ReturnType<typeof setTimeout> | undefined;
      try { return await Promise.race([promise, new Promise<T>((_,reject) => { timer=setTimeout(()=>reject(Error(label)),15000); })]); }
      finally { if(timer)clearTimeout(timer); }
    };
    const terminateAndConfirm = () => cleanup ??= (async () => {
      const confirmed = await bounded(child.terminateAndConfirm(),'owned_native_cleanup_timeout').catch(()=>false);
      if (!confirmed) { this.unconfirmedLaunch=true; return false; }
      if (!receipt || !value) return true; // Failed acquisition stays unqualified.
      try {
        const settlement=await bounded(child.settlementReceipt!,'owned_settlement_receipt_timeout');
        if(!isVerifiedCodexSettlementReceipt(settlement)||!settlement.cleanupOk||settlement.nonce!==receipt.nonce||settlement.containerId!==receipt.container.id||settlement.sessionId!==sessionId)throw Error('actual_owned_settlement_required');
        value.settlementUtf8=await this.raw(settlement);
        await durableFile(join(this.directory,`${receipt.nonce}-settlement.raw.json`),value.settlementUtf8);
        return true;
      } catch { this.unconfirmedLaunch=true; return false; }
    })();
    const owned = {...child,terminateAndConfirm};
    try {
      receipt=await bounded(child.launchReceipt!,'owned_launch_receipt_timeout');
      if(!isVerifiedCodexLaunchReceipt(receipt)||receipt.sessionId!==sessionId||receipt.container.profileDir!==input.profileDir||receipt.container.workspace!==input.workspace)throw Error('actual_branded_native_launch_required');
      const profileAfter=await observe(input.profileDir),workspaceAfter=await observe(input.workspace);
      if(profileAfter.ino!==fresh.profile.ino||profileAfter.dev!==fresh.profile.dev||workspaceAfter.ino!==fresh.workspace.ino||workspaceAfter.dev!==fresh.workspace.dev)throw Error('fresh_mount_identity_changed_during_launch');
      value={receipt,utf8:await this.raw(receipt),prelaunchUtf8:stableJson({...fresh,postlaunch:{profile:profileAfter,workspace:workspaceAfter}})};
      const values=this.launches.get(sessionId)??[];values.push(value);this.launches.set(sessionId,values);
      await durableFile(join(this.directory,`${receipt.nonce}-launch.raw.json`),value.utf8);
      await durableFile(join(this.directory,`${receipt.nonce}-prelaunch.json`),value.prelaunchUtf8);
      return owned;
    } catch(error) {
      this.unconfirmedLaunch=true;
      const cleanupConfirmed=await terminateAndConfirm();
      await durableFile(join(this.directory,`${randomUUID()}-launch-FAILED.json`),stableJson({source:'owned-native-acquisition-failure',sessionId,observedAt:new Date().toISOString(),cleanupConfirmed,status:cleanupConfirmed?'released-failed':'quarantined',automaticReplay:false})).catch(()=>undefined);
      throw Error(cleanupConfirmed?'owned_native_launch_failed_released_no_replay':'owned_native_launch_failed_quarantined_no_replay',{cause:error});
    }
  }

  parentProducer(sessionId:string) {
    const launch=this.launches.get(sessionId)?.at(-1);
    if(!launch?.settlementUtf8)throw Error('actual_settled_parent_producer_absent');
    return {launchReceiptUtf8:launch.utf8,settlementReceiptUtf8:launch.settlementUtf8,prelaunchReceiptUtf8:launch.prelaunchUtf8};
  }
  importClosed(closed:any,expected:any) {
    if(this.launches.size||this.actions.size||verifyObservedOwnedClose(closed,expected).status!=='PASS')throw Error('independently_verified_prior_close_required');
    const receipt=JSON.parse(closed.closeReceiptUtf8);
    for(const p of receipt.producers){const launch=JSON.parse(p.launchReceiptUtf8),values=this.launches.get(launch.sessionId)??[];values.push({receipt:launch,utf8:p.launchReceiptUtf8,prelaunchUtf8:'',settlementUtf8:p.settlementReceiptUtf8});this.launches.set(launch.sessionId,values);}
    for(const action of receipt.settledOwnedActions){this.actions.set(action.actionId,action);this.expectedActions.add(action.actionId);}
  }
  async scope(input: { sessionId: string; parentSessionId: string; runId: string; actionId: string; windowId: string; nativeThreadId: string; nativeTurnId: string;
    firstRequestUtf8: string; normalizedRequestUtf8: string; policy: any; observer: NativeObserver }) {
    const launch = this.launches.get(input.sessionId)?.at(-1), parent = this.launches.get(input.parentSessionId)?.at(-1);
    if (!launch || !parent) throw Error('observed_scope_launch_or_parent_absent');
    const frames = input.observer.frames(input.sessionId);
    const receipt = { source: 'h041-observed-model-scope', ...Object.fromEntries(Object.entries(input).filter(([k]) => !['policy','observer'].includes(k))),
      scopePolicySha256: sha256(stableJson(input.policy)), launchReceiptUtf8: launch.utf8, launchReceiptSha256: sha256(launch.utf8),
      parentLaunchReceiptUtf8: parent.utf8, parentLaunchReceiptSha256: sha256(parent.utf8),
      prelaunchReceiptUtf8: launch.prelaunchUtf8, prelaunchReceiptSha256: sha256(launch.prelaunchUtf8),
      nativeFramesUtf8: stableJson(frames), nativeFramesSha256: sha256(stableJson(frames)),
      firstRequestSha256: sha256(input.firstRequestUtf8), normalizedRequestSha256: sha256(input.normalizedRequestUtf8) };
    const scopeReceiptUtf8 = stableJson(receipt), scopeReceiptSha256 = sha256(scopeReceiptUtf8);
    const probe = { scopeReceiptUtf8, scopeReceiptSha256, firstRequestUtf8: input.firstRequestUtf8, normalizedRequestUtf8: input.normalizedRequestUtf8 };
    const verified = verifyObservedModelScope(probe, { scopePolicy: input.policy, probeThreadId: input.nativeThreadId, probeTurnId: input.nativeTurnId, actionId: input.actionId, runId: input.runId, windowId: input.windowId });
    if (verified.status !== 'PASS') throw Error('actual_observed_model_scope_rejected_before_dispatch');
    await durableFile(join(this.directory, `${randomUUID()}-model-scope.json`), scopeReceiptUtf8);
    return { ...probe, physicalMounts: verified.physicalMounts, networkPolicy: 'gateway-only', modelFileTools: [] };
  }
  async delegatedScope(input:any){
    const launch=this.launches.get(input.parentSessionId)?.at(-1);if(!launch)throw Error('actual_owned_parent_launch_absent');
    const framesUtf8=stableJson(input.observer.frames(input.parentSessionId));
    const receipt={source:'h041-observed-delegated-model-scope',sessionId:input.sessionId,authenticationSessionId:input.parentSessionId,actionId:input.actionId,runId:input.runId,windowId:input.windowId,nativeThreadId:input.nativeThreadId,nativeTurnId:input.nativeTurnId,proof:input.proof,scopePolicySha256:sha256(stableJson(input.policy)),launchReceiptUtf8:launch.utf8,launchReceiptSha256:sha256(launch.utf8),nativeFramesUtf8:framesUtf8,nativeFramesSha256:sha256(framesUtf8),firstRequestUtf8:input.firstRequestUtf8,normalizedRequestUtf8:input.normalizedRequestUtf8};
    const scopeReceiptUtf8=stableJson(receipt),probe={scopeReceiptUtf8,scopeReceiptSha256:sha256(scopeReceiptUtf8),firstRequestUtf8:input.firstRequestUtf8,normalizedRequestUtf8:input.normalizedRequestUtf8};
    const verified=verifyObservedDelegatedScope(probe,{scopePolicy:input.policy,probeThreadId:input.nativeThreadId,probeTurnId:input.nativeTurnId,actionId:input.actionId,runId:input.runId,windowId:input.windowId});if(verified.status!=='PASS')throw Error('actual_delegated_scope_rejected_before_dispatch');
    await durableFile(join(this.directory,`${randomUUID()}-delegated-scope.json`),scopeReceiptUtf8);return {...probe,physicalMounts:verified.physicalMounts};
  }
  async delegatedOperation(result:any,parent:any,sessionId:string,windowId:string,store:Store,gateway:Gateway,observer:NativeObserver){
    const ownedParent=this.actions.get(parent.actionId),launch=this.launches.get(sessionId)?.at(-1);if(!ownedParent||!launch?.settlementUtf8||this.actions.has(result.actionId)||!observer.settled(sessionId)||gateway.sessionWork(sessionId).length||!await gateway.confirmSettlement({sessionId}))throw Error('actual_owned_delegated_settlement_required');
    const capture=result.requests[0],rows=store.db.prepare('SELECT record FROM h021_gateway_requests WHERE id=? AND session_id=? AND state=?').all(capture.requestId,sessionId,'settled');if(rows.length!==1||capture.authenticationSessionId!==sessionId)throw Error('actual_authenticated_child_gateway_row_required');
    const gatewayReceiptUtf8=stableJson({source:'owned-durable-gateway-ledger-observation',sessionId,nativeThreadId:result.nativeThreadId,nativeTurnId:result.nativeTurnId,authenticationParentThreadId:parent.nativeThreadId,authenticationParentTurnId:parent.nativeTurnId,records:rows.map(r=>String(r.record)),outstanding:gateway.sessionWork(sessionId)});
    this.actions.set(result.actionId,{actionId:result.actionId,nativeThreadId:result.nativeThreadId,nativeTurnId:result.nativeTurnId,settlementReceiptSha256:result.settlement.receiptSha256,sessionId,windowId,requestIds:[capture.requestId],operationFramesUtf8:stableJson(observer.frames(sessionId)),operationSettlementUtf8:result.settlementReceiptUtf8,nativeLaunchReceiptUtf8:launch.utf8,nativeSettlementReceiptUtf8:launch.settlementUtf8,gatewayReceiptUtf8,delegatedParentActionId:parent.actionId,firstRequestUtf8:capture.firstRequestUtf8,normalizedRequestUtf8:capture.normalizedRequestUtf8,scopeReceiptUtf8:capture.scopeReceiptUtf8});
  }
  async operation(result: any, sessionId: string, windowId: string, store: Store, gateway: Gateway, observer: NativeObserver) {
    if (!result.actionId || this.actions.has(result.actionId)) throw Error('owned_action_duplicate_or_absent');
    const op = observer.operation(sessionId), launch = this.launches.get(sessionId)?.at(-1);
    if (!launch?.settlementUtf8 || op.nativeThreadId !== result.nativeThreadId || op.nativeTurnId !== result.nativeTurnId || gateway.sessionWork(sessionId).length || !await gateway.confirmSettlement({sessionId})) throw Error('actual_owned_native_gateway_settlement_required');
    const requestIds = new Set((result.requests ?? []).map((r:any) => r.requestId));
    if (!requestIds.size) throw Error('current_action_provider_request_ids_required');
    const requests = store.db.prepare('SELECT id,session_id,state,record FROM h021_gateway_requests WHERE session_id=? ORDER BY id').all(sessionId).filter(r => requestIds.has(String(r.id)));
    if (requests.length !== requestIds.size || requests.some(r => r.state !== 'settled' || JSON.parse(String(r.record)).id !== r.id || JSON.parse(String(r.record)).sessionId !== sessionId || JSON.parse(String(r.record)).state !== r.state)) throw Error('actual_gateway_ledger_not_settled');
    const gatewayReceiptUtf8 = stableJson({ source: 'owned-durable-gateway-ledger-observation', sessionId, nativeThreadId: op.nativeThreadId, nativeTurnId: op.nativeTurnId, observedAt: op.gateway.observedAt, records: requests.map(r => String(r.record)), outstanding: gateway.sessionWork(sessionId) });
    await durableFile(join(this.directory, `${randomUUID()}-gateway-ledger.json`), gatewayReceiptUtf8);
    this.actions.set(result.actionId, { actionId: result.actionId, nativeThreadId: op.nativeThreadId, nativeTurnId: op.nativeTurnId, settlementReceiptSha256: result.settlement.receiptSha256,
      sessionId, windowId, requestIds:[...requestIds], operationFramesUtf8:stableJson(observer.frames(sessionId)),
      operationSettlementUtf8:result.settlementReceiptUtf8 ?? result.isolation?.probeSettledOperationUtf8, nativeLaunchReceiptUtf8: launch.utf8, nativeSettlementReceiptUtf8: launch.settlementUtf8, gatewayReceiptUtf8 });
  }
  async close(runId: string, windowId: string, observedSettlements: any[], observer: NativeObserver) {
    const launches = [...this.launches.values()].flat();
    if (this.unconfirmedLaunch || [...this.expectedActions].some(a => !this.actions.has(a)) || !launches.length || launches.some(l => !l.settlementUtf8) || observer.sessions().some(s => !observer.settled(s))) throw Error('unconfirmed_owned_producer_no_close_receipt');
    const settledOwnedActions = [...this.actions.values()];
    const keys = ['actionId','nativeThreadId','nativeTurnId','settlementReceiptSha256'];
    const observed = settledOwnedActions.map(r => Object.fromEntries(keys.map(k => [k,r[k]])));
    if (stableJson(observed.slice().sort((a,b) => String(a.actionId).localeCompare(String(b.actionId)))) !== stableJson(observedSettlements.slice().sort((a,b) => a.actionId.localeCompare(b.actionId)))) throw Error('exhaustive_controller_owned_action_map_mismatch');
    const closeReceiptUtf8 = stableJson({ source: 'native-acceptance-run-close', format: 'h041-owned-close-v1', runId, operationWindowId: windowId, status: 'released',
      producers: launches.map(l => ({ launchReceiptUtf8: l.utf8, settlementReceiptUtf8: l.settlementUtf8 })), settledOwnedActions,
      outstandingOwnedActions: [], unconfirmedOwnedActions: [], allOwnedWorkSettled: true });
    await durableFile(join(this.directory, `${randomUUID()}-owned-close.json`), closeReceiptUtf8);
    return { outcome: 'closed', closeReceiptUtf8, closeReceiptSha256: sha256(closeReceiptUtf8), settlement: {state:'released',receiptSha256:sha256(closeReceiptUtf8),automaticReplay:false} };
  }
}
