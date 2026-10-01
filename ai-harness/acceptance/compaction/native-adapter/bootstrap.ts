import { assertRestartBootstrap,isRestartTicket,type RestartTicket } from './restart.js';
import { randomUUID } from 'node:crypto';
import { reviewedAuthorization } from '../authorization.mjs';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { join, resolve } from 'node:path';
import { createApp } from '../../../server/src/app.js';
import type { CodexReadOriginalProbe } from '../../../server/src/codex-probe.js';
import { NativeEvidence, type EvidenceHooks } from './native-evidence.js';
import { isQualifiedEntry, type EntryQualification } from './qualification.js';
import { composeCodexHost, type CodexHostQualification } from '../../../server/src/codex-host.js';
import { codexDeployment } from '../../../server/src/codex-deployment.js';
import { createProductionQwenVerifier, loadQwenReceipt } from '../../../server/src/codex-production.js';
import { readProtectedCredential } from '../../../server/src/protected-credential.js';
import { createGateway, type Gateway } from '../../../server/src/gateway.js';
import { GatewayOwnershipLedger } from '../../../server/src/gateway-ownership.js';
import { DISPATCH_STATE, DispatchFreeze } from '../../../server/src/dispatch-freeze.js';
import { DatabaseSync } from 'node:sqlite';
import { DispatchGuard } from './dispatch-guard.js';
import { createLayout, durableFile, privateFile } from './checkpoint.js';
import { sha256, stableJson, reviewSnapshot } from './projection.js';
import { sourceClosure, collectorManifest } from './source-closure.js';
import { ownedClose, failedBootstrap } from './owned-close.js';
import {NativeCountObserver} from './count-observer.js';
import { NativeObserver } from './native-observer.js';

export const FIXED_POLICY = Object.freeze({ version: '0.158.0', sourceRevision: '064c6b8c737f5b41d171fdda80bd9ef10ad06eb3',
  gatewayUrl: 'http://10.0.2.2:8081/v1', gatewayHost: '127.0.0.1', gatewayPort: 8081,
  frontendHost: '127.0.0.1', frontendPort: 18081, contextWindow: 480000, autoCompactTokenLimit: 400000, maxOutputTokens: 65536 });
export const RECOMMENDED_SETTLEMENT_RESERVE_MS = 120000;
export const STAGE_POLICY = Object.freeze({ profile: 'h040-summary-stage-v1', qualifiedAliases: Object.freeze(['qwen3.8-27b']),
  nativeDelegationQualified: false, imageJobsQualified: false, providerTools: 'empty-only' });
export interface BootstrapInput {
  review: { enabled: boolean; approvedBy: string; candidateCommit: string; notAfterUtc: string; settlementReserveMs: number;
    policy: typeof FIXED_POLICY; stagePolicy: typeof STAGE_POLICY; files: Record<string, string>; productionStateReceiptSha256: string;
    projection: { format: 'h040-fresh-persisted-message-v1'; frozenPolicySha256: string; specSha256: string; collectorSourceSha256: string };
    authorization: { task: 'H040' | 'H041' | 'H041-COMPACTION-CONTINUATION-02' | 'H041-COMPACTION-DELIVERY-03' | 'H041-COMPACTION-DELIVERY-04' | 'H041-COMPACTION-DELIVERY-05'; windowId: string; startsUtc: string; capUtc: string } };
  actualCandidateCommit: string; privateBase: string; productionDataDir: string; repository: string;
  launcherPath: string; qwenReceiptPath: string; inferenceKeyPath: string; controlKeyPath: string;
  productionStateReceiptPath: string;
}
/** No side effects at import. Root must supply a concrete source-closure review
 * and a fresh, independently obtained normal owned-stop/quiescence receipt.
 * This helper neither stops production nor sweeps/kills/changes ports.
 */
export function reviewedExpiry(review: BootstrapInput['review'], now = Date.now()) {
  return reviewedAuthorization(review, now).expiresAt;
}
export interface BootstrapHooks { qualification: EntryQualification; evidence: EvidenceHooks; carrier?:import('./carrier-admission.js').CarrierAdmission; applicationRestart?(method:'coldResume'|'resumeAcceptedContinuation',input:any):Promise<any>; delegatedChild?(input:any):Promise<any>; retainPolicy?(input:any):Promise<any>; adoptPolicy?(input:any):Promise<void>; configureHost(base: CodexHostQualification, context: { guard: DispatchGuard; observer: NativeObserver; layout: Awaited<ReturnType<typeof createLayout>>; application(): Awaited<ReturnType<typeof createApp>> | undefined; originalProbes: Map<string,CodexReadOriginalProbe>; originalSettlements: any[]; artifactSettlements: any[] }): CodexHostQualification; }
export async function bootstrap(input: BootstrapInput, hooks?: BootstrapHooks,restart?:RestartTicket) {
  if(restart){if(!isRestartTicket(restart))throw Error('owned_qualified_restart_required');assertRestartBootstrap(restart,input);}
  input = reviewSnapshot(input);
  const review = input.review, expiry = Date.parse(review?.notAfterUtc);
  if (review?.enabled !== true || review.approvedBy !== 'root' || !/^[a-f0-9]{40}$/.test(review.candidateCommit) ||
      input.actualCandidateCommit !== review.candidateCommit || !Number.isFinite(expiry) || expiry <= Date.now() ||
      stableJson(review.policy) !== stableJson(FIXED_POLICY) || stableJson(review.stagePolicy) !== stableJson(STAGE_POLICY)) throw Error('root_concrete_review_required_or_expired');
  reviewedExpiry(review);
  const dispatchCutoffAt = expiry - review.settlementReserveMs;
  if (Date.now() >= dispatchCutoffAt) throw Error('native_settlement_reserve_no_new_bootstrap');
  if (process.platform !== 'linux' || process.getuid?.() === 0) throw Error('reviewed_linux_rootless_host_required');
  if (input.repository !== resolve(fileURLToPath(new URL('../../../../', import.meta.url)))) throw Error('reviewed_repository_is_not_imported_repository');
  // Root includes protected source successors, verifier/gateway/engine/launcher,
  // policy and egress files in the same review, not merely the entrypoint hash.
  const closure = await sourceClosure(input.repository, input.launcherPath, input.qwenReceiptPath);
  if (review.projection?.collectorSourceSha256 !== sha256(collectorManifest(closure, input.repository))) throw Error('reviewed_collector_closure_mismatch');
  if (stableJson(closure) !== stableJson(review.files)) throw Error('imported_source_closure_mismatch');
  if (!input.launcherPath.endsWith('/deploy/run-codex.sh') || review.files[input.launcherPath] !== sha256(await readFile(input.launcherPath))) throw Error('reviewed_launcher_mismatch');
  if (review.files[input.qwenReceiptPath] !== sha256(await readFile(input.qwenReceiptPath))) throw Error('reviewed_qwen_receipt_mismatch');
  const productionBytes = await privateFile(input.productionStateReceiptPath);
  if (sha256(productionBytes) !== review.productionStateReceiptSha256) throw Error('production_state_receipt_mismatch');
  const production = JSON.parse(productionBytes.toString('utf8'));
  if (production.schema !== 1 || production.capturedBy !== 'root-owned-host-observation' ||
      production.dataDir !== input.productionDataDir || production.stopMethod !== 'normal-owned-stop' ||
      production.noWriters !== true || production.nativeSettled !== true || production.gatewaySettled !== true ||
      !/^[a-f0-9]{64}$/.test(production.preservedStateSha256 ?? '') ||
      !Number.isFinite(Date.parse(production.observedAt)) || Date.now() - Date.parse(production.observedAt) < 0 ||
      (!restart&&Date.now() - Date.parse(production.observedAt) > 60000)) throw Error('fresh_preserved_production_quiescence_unavailable');
  const layout = restart ? restart.state.layout as Awaited<ReturnType<typeof createLayout>> : await createLayout(input.privateBase, [input.productionDataDir, input.repository,
    input.inferenceKeyPath, input.controlKeyPath, input.productionStateReceiptPath]);
  const captures = join(layout.hostPrivate, `captures-${randomUUID()}`);
  const { mkdir } = await import('node:fs/promises');
  await mkdir(captures, { mode: 0o700 });
  const guard = new DispatchGuard(captures);
  const observer = new NativeObserver(captures);
  const counts=new NativeCountObserver(captures);
  if (hooks && !isQualifiedEntry(hooks.qualification)) throw Error('qualified_entry_object_required');
  const evidence = hooks ? new NativeEvidence(captures, hooks.evidence) : undefined;
  if(restart&&evidence)evidence.importClosed(restart.closed,{runId:restart.state.runId,operationWindowId:restart.state.windowId,observedSettlements:restart.state.observedSettlements,receiptSources:(review as any).receiptSources});
  const receipt = await loadQwenReceipt(input.qwenReceiptPath);
  const inferenceKey = await readProtectedCredential(input.inferenceKeyPath);
  const controlKey = await readProtectedCredential(input.controlKeyPath);
  const verifyLane = createProductionQwenVerifier(receipt, { inferenceKey, controlKey });
  if(hooks){const current=await verifyLane('qwen3.8-27b');if(current.instanceId!==hooks.qualification.routeInstanceId)throw Error('current_qwen_operation_identity_changed');}
  // Reuse the existing fail-closed held() semantics with a read-only connection.
  // Opening the normal owner would create/chmod shared production gate state.
  await privateFile(DISPATCH_STATE);
  const freezeDb = new DatabaseSync(DISPATCH_STATE, { readOnly: true });
  const freeze = { held: (alias: string) => {try{return hooks?.carrier ? hooks.carrier.held(freezeDb.prepare('SELECT key,fingerprint,action,acknowledged,scope FROM dispatch_holds').all(),alias) : DispatchFreeze.prototype.held.call({ db: freezeDb } as DispatchFreeze, alias);}catch{return true;}}, close: () => freezeDb.close() };
  const authorizeTaskAction=async(sessionId:string,requestId:string,signal?:AbortSignal)=>{if(hooks?.carrier)await hooks.carrier.verify(sessionId,requestId,signal,captures);};
  let gateway: Gateway | undefined, closed = false;
  const originalProbes = new Map<string,CodexReadOriginalProbe>(), originalSettlements: any[] = [], artifactSettlements: any[] = [];
  const baseQualification: CodexHostQualification = { protocolQualified: true, rootlessQualified: true, verifyLane, outputLimit: 65536, qualifiedAliases: STAGE_POLICY.qualifiedAliases };
  const host = composeCodexHost(input.launcherPath, () => gateway, hooks ? hooks.configureHost(baseQualification,{guard,observer,layout,application:() => application,originalProbes,originalSettlements,artifactSettlements}) : baseQualification);
  if (hooks && (!host.runtime.nativeReceiptsRequired || typeof (host.runtime as unknown as Record<string,unknown>).textOnlyPolicy !== 'function')) throw Error('actual_receipt_and_thread_policy_consumer_required');
  const originalLaunch = host.runtime.launchRootless, originalSettlement = host.runtime.confirmGatewaySettlement;
  const beforeAction=host.runtime.beforeNativeAction;
  host.runtime.beforeNativeAction=async action=>{await authorizeTaskAction(action.sessionId,'native-action-'+randomUUID());await beforeAction?.(action);};
  host.runtime.launchRootless = async params => {
    await authorizeTaskAction(params.sessionId,'native-launch-'+randomUUID());
    if (launchHeld()) throw Error('trusted_shared_native_launch_held');
    const process = evidence ? await evidence.launch(params.sessionId,params,() => originalLaunch(params)) : await originalLaunch(params);
    // A hold arriving during launch blocks all subsequent request admission.
    return observer.wrap(params.sessionId, process);
  };
  host.runtime.confirmGatewaySettlement = async query => {
    const confirmed = await originalSettlement(query);
    observer.gateway(query.sessionId, query.nativeThreadId, query.activeTurnId, confirmed);
    return confirmed;
  };
  let captureHeld = false;
  const withCaptureHold = async <T>(operation: () => Promise<T>): Promise<T> => {
    if (captureHeld) throw Error('capture_hold_already_owned');
    captureHeld = true;
    try { return await operation(); } finally { captureHeld = false; application.broker.notifyDispatchChanged(); gateway?.notifyAvailabilityChanged(); }
  };
  const held = () => closed || captureHeld || Date.now() >= dispatchCutoffAt || freeze.held('harness');
  const launchHeld = () => closed || held() || Object.keys(receipt.lanes).some(alias => freeze.held(alias));
  const application = await createApp({ newChatEngine: 'codex', dataDir: layout.dataDir,
    allowedOrigins: ['http://127.0.0.1:18081'], launcher: input.launcherPath, ...codexDeployment({ enablePreview: true, runtime: host.runtime }),
    engineFactory: () => { throw Error('minimax_outside_adapter_scope'); },
    gatewayUrl: FIXED_POLICY.gatewayUrl, dispatchHeld: held,
    issueToken: id => gateway!.issueToken(id, 'codex'), revokeToken: token => gateway!.revokeToken(token), visionAvailable: false });
  if (evidence && hooks) guard.beforeDispatch = async (scope, capture) => {
    evidence.expectAction(scope.actionId);
    if (!['summary-only','durable-retrieval','clean-child'].includes(scope.mode)) return {};
    const parent = application.store.db.prepare('SELECT id FROM sessions WHERE native_session_id=?').get(scope.parentNativeThreadId!);
    if (!parent) throw Error('observed_parent_session_mapping_required');
    const mode = scope.mode === 'durable-retrieval' ? 'read-original' : scope.mode === 'clean-child' ? 'clean-child' : 'summary-only';
    if(scope.authenticationSessionId){return evidence.delegatedScope({sessionId:scope.sessionId,parentSessionId:scope.authenticationSessionId,runId:scope.runId,actionId:scope.actionId,windowId:review.authorization.windowId,...capture,proof:scope.delegatedProof,policy:hooks.qualification.scopePolicies[mode],observer});}
    return evidence.scope({sessionId:scope.sessionId,parentSessionId:String(parent.id),runId:scope.runId,actionId:scope.actionId,windowId:review.authorization.windowId,
      ...capture,policy:hooks.qualification.scopePolicies[mode],observer});
  };
  const directProbes = new Map<string, { abort(): void; finished: Promise<void> }>();
  const close = ownedClose(async () => {
    closed = true;
    const handles = [...directProbes.values()];
    for (const handle of handles) handle.abort();
    await Promise.all(handles.map(handle => handle.finished));
    const failures: unknown[] = [];
    try { await application.broker.close(); } catch (error) { failures.push(error); }
    host.stopSettlementObservation();
    try { await gateway?.close(); } catch (error) { failures.push(error); }
    try { await application.app.close(); } catch (error) { failures.push(error); }
    try { freeze.close(); } catch (error) { failures.push(error); }
    if (failures.length) throw new AggregateError(failures, 'temporary_host_close_unconfirmed');
  });
  try {
  const ownership = new GatewayOwnershipLedger(application.store.db).options();
  gateway = createGateway({ upstreamKey: inferenceKey, ownership, dispatchHeld: alias => held() || freeze.held(alias),
    qwenOutputLimit: 65536, responses: { ...host.responses!, countQwen: guard.wrap(counts.wrap(async(body,lane,key,signal,context)=>{if(!context?.requestId)throw Error('actual_carrier_request_context_required');await authorizeTaskAction(guard.authenticationSession(context.requestId),context.requestId,signal);if(held()||freeze.held(lane.alias))throw Error('shared_hold_before_actual_count');const result=await host.responses!.countQwen(body,lane,key,signal,context);await authorizeTaskAction(guard.authenticationSession(context.requestId),context.requestId,signal);if(held()||freeze.held(lane.alias))throw Error('shared_hold_after_actual_count');return result;})) },
    diagnostics: { capture: guard.capture }, activeTimeoutMs: 120000, queueTimeoutMs: 120000 });
    // Fixed bind only. EADDRINUSE is retained and propagated; no fallback/sweep.
    await gateway.app.listen({ host: '127.0.0.1', port: 8081 });
    await application.app.listen({ host: '127.0.0.1', port: 18081 });
    await durableFile(join(layout.hostPrivate, `bootstrap-${randomUUID()}-receipt.json`), stableJson({
      schema: 1, candidateCommit: review.candidateCommit, policy: FIXED_POLICY, layout,
      reviewSha256: sha256(stableJson(review)), productionStateReceiptSha256: review.productionStateReceiptSha256,
      productionBrowserQualification: 'NOT_TESTED', runtimeBinaryQualification: 'NOT_TESTED' }) + '\n');
    return { application, gateway, host, guard, observer, counts, originalProbes, originalSettlements, artifactSettlements, evidence, qualification: hooks?.qualification, authorizeTaskAction, hostId:randomUUID(), launchHeld, launcherPath: input.launcherPath, withCaptureHold, layout, close, expiresAt: expiry, dispatchCutoffAt, verifyLane, directProbes, get closing() { return closed; } };
  } catch (error) {
    return failedBootstrap(error, () => durableFile(join(layout.hostPrivate, 'bootstrap-FAILED.json'), stableJson({
      outcome: 'failed', code: (error as NodeJS.ErrnoException).code === 'EADDRINUSE' ? 'EADDRINUSE' : 'bootstrap_failed', automaticRetry: false }) + '\n'), close);
  }
}
export type TemporaryHost = Awaited<ReturnType<typeof bootstrap>>;
