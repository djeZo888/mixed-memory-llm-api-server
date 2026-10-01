import type { RestartTicket } from './restart.js';
import { privateFile } from './checkpoint.js';
import { consumedTool, validateConsumedFollowup } from './consumed-tools.js';
import { parentManifest, type ParentProjectionSpec } from './parent-projection.js';
import { retrievalProbe } from './retrieval.js';
import { isQualifiedEntry, STAGE_CAPABILITIES, FULL_CAPABILITIES } from './qualification.js';
import { join } from 'node:path';
import { randomUUID } from 'node:crypto';
import { setTimeout as delay } from 'node:timers/promises';
import { requireId } from '../../../server/src/errors.js';
import { bootstrap, type BootstrapInput, type TemporaryHost, type BootstrapHooks } from './bootstrap.js';
import { checkpoint, durableFile } from './checkpoint.js';
import { sha256, stableJson, summaryProbeText, reviewSnapshot } from './projection.js';
import { summaryProbe } from './probe.js';
import { normalizeNativeInput, type ProbeManifest } from './dispatch-guard.js';
import { NativeCollector, type FullCheckpoint, type ParentState } from './collector.js';
import { openNativeParent } from './parent.js';
import { collectContinuationArtifacts } from './artifacts.js';

const unknown = (reason: string) => ({ value: null, reason });
const tokensUnknown = () => Object.fromEntries(['input', 'summary', 'contextAfter'].map(k => [k,
  { state: 'absent', value: null, source: null, receiptSha256: null, reason: `native ${k} token provenance not qualified` }]));
export const SUMMARY_PREFIX_SHA256 = 'e9b088e794a6bb9082ac053fcc760bd818d7e720ee4bcdc72c6e480de7b7cb0e';
export const BLOCKERS = Object.freeze([
  'Installed native/config/tool/scope/current-route qualification NOT_TESTED; source APIs alone grant no native PASS',
  'Actual runtime/model/tokenizer six-pin producer capture and complete installed source/build/helper/dependency closure required',
  'Actual durable prior-policy bridge and separately branded continuation02 policy must be consumed before app restart',
  'Actual native spawn/tool schema, whole first request, child/parent/gateway settlement and frozen delegated scope policy require live qualification',
  'All mandatory full/ordinary/automatic dimensions remain unrun pending root concrete review and live GO',
]);
export interface AdapterInput {
  bootstrap: BootstrapInput; frozenPolicy: string; compactionSummaryPrefix: string;
  /** Independently frozen root-reviewed constructor, scaffold, whole envelope
   * and portable collector closure; B derives the same exact input separately. */
  parentProjectionSpec?: ParentProjectionSpec;
  projectionSpec: { format: 'h040-fresh-persisted-message-v1'; prefixInput: unknown[]; envelope: Record<string, unknown>; collectorManifestUtf8: string };
}
/** Disabled default. A root-owned entry module can enable only separately
 * qualified capabilities after review; source fixtures are not qualifications. */
export function createNativeAdapter(input?: AdapterInput) { return assembleAdapter(input); }
/** Explicit SOURCE fixture seam: cannot acquire native kind/capabilities or call bootstrap. */
export function createSyntheticAdapter(input: AdapterInput, fixture: { host: TemporaryHost; collector: NativeCollector; sessionId: string; acceptanceRunId: string }) {
  return assembleAdapter(input, fixture);
}
export function createQualifiedNativeAdapter(input: AdapterInput, hooks: BootstrapHooks) {
  if(hooks.qualification.profile==='h041-full-retention-v1'&&(!hooks.retainPolicy||!hooks.adoptPolicy||!hooks.delegatedChild))throw Error('actual_durable_policy_adoption_consumer_required');
  if (!isQualifiedEntry(hooks.qualification)) throw Error('actual_reviewed_entry_qualification_required');
  return assembleAdapter(input, undefined, hooks);
}
function assembleAdapter(input?: AdapterInput, fixture?: { host: TemporaryHost; collector: NativeCollector; sessionId: string; acceptanceRunId: string }, hooks?: BootstrapHooks) {
  // Snapshot expected digests and the approved content together, before open.
  input = input ? reviewSnapshot(input) : undefined;
  let host: TemporaryHost | undefined = fixture?.host, collector: NativeCollector | undefined = fixture?.collector, parentId: string | undefined = fixture?.sessionId;
  let acceptanceOwnerRunId: string | undefined = fixture?.acceptanceRunId;
  let opening: Promise<TemporaryHost> | undefined, closingRequested = false;
  let busy = false, opened = !!fixture, faulted = false, latest: FullCheckpoint | undefined;
  let lastContinuation:any;
  const seenActions = new Set<string>();
  const sessionOwner = (session: any) => {
    if (!host || !collector || !parentId || session?.sessionId !== parentId ||
        session.nativeThreadId !== host.application.store.getSession(parentId).nativeSessionId) throw Error('foreign_or_absent_session');
    return host;
  };
  const settled = (h: TemporaryHost) => collector!.settled(parentId!);
  async function captureCheckpoint(h: TemporaryHost, binding: Record<string, unknown>) {
    return h.withCaptureHold(async () => {
      const s = h.application.store.getSession(parentId!);
      return checkpoint({ hostPrivate: h.layout.hostPrivate,
        sources: { profile: h.application.files.profile(parentId!), files: h.application.files.workspace(s.workspaceId) },
        binding: { ...binding, sessionId: parentId, parentNativeThreadId: s.nativeSessionId, eventCursor: s.nativeState.eventCursor },
        settled: () => settled(h), databaseExport: async file => { h.application.store.db.prepare('VACUUM INTO ?').run(file); } });
    });
  }
  async function main(h: TemporaryHost, signal: AbortSignal, kind: 'message' | 'compact', text: string, actionId: string, dispatchMode: 'main' | 'parent-artifacts' = 'main', purpose: 'append' | 'continuation' | 'compaction' | 'child' = 'append') {
    signal = AbortSignal.any([signal, AbortSignal.timeout(Math.max(1, Math.min(120000, h.dispatchCutoffAt - Date.now())))]);
    if (faulted || busy || signal.aborted || h.closing || Date.now() >= h.dispatchCutoffAt) throw Error('adapter_failed_busy_or_deadline');
    if (seenActions.has(actionId)) throw Error('duplicate_action_no_replay');
    const manifest = hooks ? parentManifest(await collector!.captureState(parentId!,'independent-pre-action-parent-input'),text,kind,input!.parentProjectionSpec!) : undefined;
    if(hooks?.qualification.profile==='h041-full-retention-v1'&&kind==='message')dispatchMode='parent-artifacts';
    requireId(actionId); seenActions.add(actionId); busy = true;
    let runId: string | undefined, cancellation: Promise<void> | undefined;
    const abort = () => { h.gateway.revokeSession(parentId!); cancellation ??= h.application.broker.cancel(parentId!).then(() => undefined).catch(() => undefined); };
    signal.addEventListener('abort', abort, { once: true });
    try {
      await h.authorizeTaskAction?.(parentId!,actionId,signal);
      runId = h.application.broker.enqueue(parentId!, kind, text, [], [], kind === 'compact' ? actionId : undefined);
      h.guard.register({ sessionId: parentId!, actionId, runId, mode: dispatchMode, purpose, manifest, validateFollowup: dispatchMode==='parent-artifacts' ? body=>{if(purpose==='child')return h.guard.delegatedFollowup!(parentId!,body,manifest!.input);const current=h.application.store.getSession(parentId!);validateConsumedFollowup(body,manifest!.input,{tool:'write_checkpoint_artifact',threadId:current.nativeSessionId!,turnId:current.nativeState.activeTurnId!,runId:h.host.runtime.textOnlyPolicy!(parentId!)!.runId,frames:h.observer.frames(parentId!),settled:h.artifactSettlements});} : undefined, toolPolicy: dispatchMode === 'parent-artifacts' ? (hooks?.qualification.profile==='h041-full-retention-v1'?(input!.bootstrap.review as any).retentionParentPolicy?.[purpose==='child'?'childPolicy':'artifactPolicy']:(input!.bootstrap.review as any).parentArtifactPolicy) : undefined, signal,
        expiresAt: Math.min(h.dispatchCutoffAt, Date.now() + 120000), identity: () => {
          const s = h.application.store.getSession(parentId!);
          const active = h.application.store.db.prepare("SELECT id FROM runs WHERE session_id=? AND status IN ('running','cancelling')").all(parentId!);
          return { nativeThreadId: s.nativeSessionId, nativeTurnId: s.nativeState.activeTurnId ?? undefined,
            activeRunId: active.length === 1 ? String(active[0].id) : undefined };
        } });
      for (;;) {
        const run = h.application.store.runSnapshot(runId);
        if (!['queued', 'running', 'cancelling'].includes(run.status)) {
          const proof = await settled(h), requests = h.guard.requests(parentId!).filter(r => r.runId === runId);
          if (!proof || run.status !== 'completed') throw Error('parent_native_failed_or_unsettled');
          const op = h.observer.operation(parentId!);
          if (op.method !== (kind === 'compact' ? 'thread/compact/start' : 'turn/start') || !requests.length ||
              requests.some(r => r.nativeThreadId !== op.nativeThreadId || r.nativeTurnId !== op.nativeTurnId) ||
              h.application.store.getSession(parentId!).nativeSessionId !== op.nativeThreadId) throw Error('parent_run_native_request_trace_mismatch');
          const receipt = { sessionId: parentId, actionId, runId, nativeThreadId: op.nativeThreadId, nativeTurnId: op.nativeTurnId,
            observedHandleId: op.handleId, nativeTraceReceiptSha256: op.traceReceiptSha256, createdAt: run.createdAt,
            settledAt: op.gateway.observedAt, requests, nativeOutcome: run.status, automaticReplay: false };
          await durableFile(join(h.layout.hostPrivate, `${runId}-parent-output.json`), stableJson({ receipt, snapshot: h.application.store.snapshot(parentId!) }) + '\n');
          const durationReceiptUtf8 = stableJson({ source: 'host-native-operation-observation', startedAt: op.request.observedAt, completedAt: op.gateway.observedAt, traceReceiptSha256: op.traceReceiptSha256, runId });
          await durableFile(join(h.layout.hostPrivate, `${runId}-duration.json`), durationReceiptUtf8);
          const result = { ...receipt, outcome: 'completed', durationMs: { state: 'measured', value: Date.parse(op.gateway.observedAt) - Date.parse(op.request.observedAt), source: 'host-native-operation-observation', receiptSha256: sha256(durationReceiptUtf8), reason: null }, tokens: tokensUnknown(),
            settlementReceiptUtf8: stableJson(receipt), settlement: { state: 'released', receiptSha256: sha256(stableJson(receipt)), automaticReplay: false } };
          if (h.evidence) await h.evidence.operation(result,parentId!,input!.bootstrap.review.authorization.windowId,h.application.store,h.gateway,h.observer);
          return result;
        }
        if (signal.aborted || Date.now() >= h.dispatchCutoffAt) { abort(); throw Error('parent_deadline_no_replay'); }
        await delay(10);
      }
    } catch {
      faulted = true; abort(); await cancellation;
      await durableFile(join(h.layout.hostPrivate, `${runId ?? randomUUID()}-parent-FAILED.json`), stableJson({
        actionId, runId: runId ?? null, outcome: 'failed', automaticReplay: false,
        settlement: await settled(h) ? 'released' : 'quarantined', snapshot: h.application.store.snapshot(parentId!) }) + '\n').catch(() => undefined);
      throw Error('parent_phase_failed_output_preserved_no_replay');
    } finally { signal.removeEventListener('abort', abort); h.guard.retire(parentId!); busy = false; }
  }
  return {
    interfaceVersion: 'h039-compaction-adapter-v1', kind: fixture ? 'synthetic' : 'native', enabled: !!hooks,
    capabilities: hooks ? [...(hooks.qualification.profile==='h041-full-retention-v1'?FULL_CAPABILITIES:STAGE_CAPABILITIES)] : [] as string[], blockers: BLOCKERS,
    async runtime() {
      if (hooks) return { name: 'codex', ...hooks.qualification.runtime, promptRevision: 'kpm-technical-v1' };
      return { name: 'codex', version: unknown('installed native initialization not yet observed'),
        sourceRevision: unknown('installed runtime not independently observed'), binarySha256: unknown('binary attestation unavailable'),
        model: unknown('current protected provider admission not yet observed'), modelRevision: unknown('current model not yet observed'),
        tokenizerRevision: unknown('tokenizer revision absent'), promptRevision: 'kpm-technical-v1' };
    },
    async open({ signal, runId }: any) {
      if (!input || opened || signal.aborted) throw Error('adapter_disabled_duplicate_or_aborted');
      const p = input.bootstrap.review.projection;
      if (sha256(input.compactionSummaryPrefix) !== SUMMARY_PREFIX_SHA256 || Buffer.byteLength(input.compactionSummaryPrefix) !== 399 ||
          p?.format !== 'h040-fresh-persisted-message-v1' || p.frozenPolicySha256 !== sha256(input.frozenPolicy) ||
          p.specSha256 !== sha256(stableJson(input.projectionSpec)) || p.collectorSourceSha256 !== sha256(input.projectionSpec.collectorManifestUtf8))
        throw Error('independent_reviewed_prefix_policy_projection_source_required');
      requireId(runId); acceptanceOwnerRunId = runId;
      opened = true; opening = bootstrap(input.bootstrap, hooks); host = await opening;
      if (closingRequested) { await host.close(); throw Error('adapter_closed_during_bootstrap'); }
      collector = new NativeCollector({ store: host.application.store, files: host.application.files, gateway: host.gateway,
        observer: host.observer, guard: host.guard, hostPrivate: host.layout.hostPrivate, withCaptureHold: host.withCaptureHold });
      const s = await host.application.broker.createSession(undefined, 'codex'); parentId = s.id;
      await host.registerTaskSession?.(parentId,'parent',undefined,signal);
      const actual = await openNativeParent(host, parentId, AbortSignal.any([signal, AbortSignal.timeout(Math.max(1, Math.min(120000, host.dispatchCutoffAt - Date.now())))]));
      await durableFile(join(host.layout.hostPrivate, 'suite-owner.json'), stableJson({ source: 'owned-controller-open-and-observed-native-parent', acceptanceRunId: acceptanceOwnerRunId, ...actual, operationWindowId: input.bootstrap.review.authorization.windowId }));
      return actual;
    },
    async append({ session, records, signal }: any) {
      const h = sessionOwner(session);
      try {
        return await collector!.appendOriginals(parentId!, records, approved => main(h, signal, 'message', approved.map(r => r.content).join('\n\n'), randomUUID()));
      } catch (error) {
        if (h.application.store.getSession(parentId!).nativeState.ownership !== 'idle') faulted = true;
        throw error;
      }
    },
    async originals({ session }: any) { sessionOwner(session); return collector!.originals(parentId!); },
    async compact({ session, actionId, runId: acceptanceRunId, windowId, baseline, signal }: { session: any; actionId: string; runId: string; windowId: string; baseline: ParentState; signal: AbortSignal }) {
      const h = sessionOwner(session); requireId(actionId);
      if (acceptanceRunId !== acceptanceOwnerRunId || windowId !== input!.bootstrap.review.authorization.windowId || !await settled(h)) throw Error('reviewed_compaction_window_or_settlement_required');
      const actual = await collector!.captureState(parentId!, 'pre-compaction-baseline-verification');
      if (actual.stateSha256 !== baseline?.stateSha256 || actual.nativeThreadId !== baseline.nativeThreadId) throw Error('pre-compaction_baseline_changed');
      const original = await captureCheckpoint(h, { actionId, kind: 'before-manual-compaction', originalRolloutSha256: actual.stateSha256 });
      const result = await main(h, signal, 'compact', '', actionId,'main','compaction');
      try {
        latest = await collector!.compaction(parentId!, { actionId, runId: result.runId, windowId, baseline,
          summaryPrefix: input!.compactionSummaryPrefix });
        const after = await captureCheckpoint(h, { kind: 'persisted-summary-checkpoint', contextSha256: latest.stateSha256 });
        const manualReceiptUtf8 = stableJson({ source: 'owned-store-action-and-native-trace', acceptanceRunId, storeRunId: result.runId,
          actionId, operationWindowId: windowId, nativeTraceReceiptSha256: result.nativeTraceReceiptSha256, nativeThreadId: result.nativeThreadId,
          nativeTurnId: result.nativeTurnId, compactionId: h.observer.operation(parentId!).compactionId,
          checkpointStateSha256: latest.stateSha256, settledOperationSha256: latest.settledOperationSha256 });
        const ref = `${result.runId}-manual-action.json`;
        await durableFile(join(h.layout.hostPrivate, ref), manualReceiptUtf8);
        const evidence = { kind: 'manual-action', ref, sha256: sha256(manualReceiptUtf8), runId: acceptanceRunId, actionId, nativeThreadId: result.nativeThreadId };
        return { ...result, summaryState: 'complete', contextSha256: latest.stateSha256, checkpoint: latest, operationWindowId: windowId,
          selectedMessageSha256: latest.selectedMessageSha256, compactedRecordSha256: latest.compactedRecordSha256,
          trigger: { type: 'manual', evidence: [evidence] },
          originalCheckpointReceiptSha256: original.receiptSha256, summaryCheckpointReceiptSha256: after.receiptSha256, atomicRollback: false };
      } catch (error) { faulted = true; throw error; }
    },
    async probe({ session, contextSha256, mode, request, signal, actionId, runId, hostOnlyHoldouts = [], scopeId }: any) {
      const h = sessionOwner(session);
      if (!['summary-only','durable-retrieval'].includes(mode) || (mode === 'durable-retrieval' && !hooks)) throw Error('qualified_scoped_retrieval_unavailable');
      if (faulted || busy || !await settled(h) || !latest || latest.stateSha256 !== contextSha256) throw Error('summary_checkpoint_or_settlement_mismatch');
      const spec = input!.projectionSpec;
      if (spec.format !== 'h040-fresh-persisted-message-v1' || normalizeNativeInput(spec.prefixInput).some(m => !['system', 'developer'].includes(String(m.role)))) throw Error('reviewed_projection_scaffold_invalid');
      let selectedSummary = JSON.parse(latest.compactedRecordUtf8).payload.message;
      if (mode === 'durable-retrieval') for (const h of hostOnlyHoldouts) { if (typeof h.value !== 'string' || !h.value || !['schema','temperature_range','manifest_format'].includes(h.id)) throw Error('invalid_frozen_holdout'); selectedSummary=selectedSummary.replaceAll(h.value,'[OMITTED_FOR_RETRIEVAL_PROBE]'); }
      const userText = summaryProbeText(selectedSummary, input!.frozenPolicy, request);
      const manifest: ProbeManifest = { input: [...structuredClone(spec.prefixInput), { type: 'message', role: 'user', content: [{ type: 'input_text', text: userText }] }],
        instructions: spec.envelope.instructions as string, userText, contextSha256, envelope: structuredClone(spec.envelope) };
      const before = await collector!.captureState(parentId!, 'pre-summary-probe');
      if (before.stateSha256 !== latest.stateSha256) throw Error('summary_parent_state_changed');
      busy = true;
      try {
        const frozen = mode === 'durable-retrieval' ? await collector!.frozenOriginals(parentId!) : undefined;
        const result = mode === 'durable-retrieval' ? await retrievalProbe(h,{parentNativeThreadId:latest.nativeThreadId,runId,actionId,windowId:input!.bootstrap.review.authorization.windowId,scopeId,checkpointId:frozen!.checkpointId,originals:frozen!.originals,summary:selectedSummary,frozenPolicy:input!.frozenPolicy,manifest,signal,omittedFactIds:hostOnlyHoldouts.map((x:any)=>x.id),contextSha256,compactedRecordSha256:latest.compactedRecordSha256,collectorSourceSha256:input!.bootstrap.review.projection.collectorSourceSha256,collectorManifestUtf8:spec.collectorManifestUtf8,request}) : await summaryProbe(h, { parentNativeThreadId: latest.nativeThreadId,
          summary: JSON.parse(latest.compactedRecordUtf8).payload.message, contextSha256, request, signal, actionId, runId,
          windowId: input!.bootstrap.review.authorization.windowId, compactedRecordSha256: latest.compactedRecordSha256,
          collectorSourceSha256: input!.bootstrap.review.projection.collectorSourceSha256, collectorManifestUtf8: spec.collectorManifestUtf8, frozenPolicy: input!.frozenPolicy, manifest });
        const parentStateAfter = await collector!.captureState(parentId!, 'post-summary-probe');
        if (parentStateAfter.stateSha256 !== before.stateSha256 || result.outcome !== 'completed' || !('isolation' in result)) { faulted = true; throw Error('probe_failure_or_parent_contamination'); }
        if (h.evidence) await h.evidence.operation({...result,requests:h.guard.requests(String(result.sessionId))},String(result.sessionId),input!.bootstrap.review.authorization.windowId,h.application.store,h.gateway,h.observer);
        return { ...result, isolation: { ...result.isolation, parentStateAfter } };
      } catch (error) { faulted = true; throw error; } finally { busy = false; }
    },
    async continue({ session, request, signal, actionId }: any) {
      const h = sessionOwner(session);
      if (!await settled(h)) throw Error('continuation_parent_unsettled');
      const result = await main(h, signal, 'message', stableJson(request), actionId, hooks ? 'parent-artifacts' : 'main','continuation');
      try {
        const artifacts = await collectContinuationArtifacts(h.application.store, h.application.files, h.layout.hostPrivate, parentId!, result.runId);
        if(hooks){const receipt=JSON.parse(artifacts.artifactReceiptUtf8);for(const artifact of receipt.artifacts){const settlements=h.artifactSettlements.filter(s=>s.threadId===result.nativeThreadId&&s.turnId===result.nativeTurnId&&s.artifactId===artifact.artifactId);if(settlements.length!==1||settlements[0].name!==artifact.name||settlements[0].sha256!==artifact.sha256)throw Error('actual_artifact_consumption_or_registered_bytes_mismatch');consumedTool({tool:'write_checkpoint_artifact',threadId:result.nativeThreadId,turnId:result.nativeTurnId,runId:h.host.runtime.textOnlyPolicy!(parentId!)!.runId,frames:h.observer.frames(parentId!),settled:h.artifactSettlements},settlements[0].callId);}}
        const parentState = await collector!.captureState(parentId!, 'after-latest-continuation-awaiting-independent-grade');
        lastContinuation={ ...result, ...artifacts, parentState };
        return { ...lastContinuation, acceptance: 'awaiting-independent-B-grade', coldCheckpoint: null };
      } catch (error) { faulted = true; throw error; }
    },
    async coldResume(args:any) {if(!hooks?.applicationRestart)throw Error('actual_application_process_proxy_unqualified');return hooks.applicationRestart('coldResume',args);},
    async resumeAcceptedContinuation(args:any) {if(!hooks?.applicationRestart)throw Error('actual_application_process_proxy_unqualified');return hooks.applicationRestart('resumeAcceptedContinuation',args);},
    async prepareRestart({checkpoint:expected,acceptedContinuation,runId,actionId,windowId,observedSettlements,signal}:any) {
      if(!host||!collector||!parentId||!hooks?.retainPolicy||faulted||busy||signal.aborted||runId!==acceptanceOwnerRunId||windowId!==input!.bootstrap.review.authorization.windowId||!await settled(host))throw Error('settled_owned_restart_preparation_required');
      const actual=await collector.captureState(parentId,'independent-before-whole-application-restart');
      if(actual.stateUtf8!==expected?.stateUtf8||actual.stateSha256!==expected.stateSha256||actual.nativeThreadId!==expected.nativeThreadId)throw Error('latest_parent_checkpoint_not_current');
      if(acceptedContinuation){const baseline=acceptedContinuation.artifactBaseline;if(!lastContinuation||lastContinuation.actionId!==acceptedContinuation.actionId||baseline?.artifactReceiptUtf8!==lastContinuation.artifactReceiptUtf8||baseline.artifactReceiptSha256!==lastContinuation.artifactReceiptSha256||lastContinuation.parentState.stateSha256!==actual.stateSha256)throw Error('original_accepted_artifact_baseline_not_owned');}
      const preserved=await captureCheckpoint(host,{kind:'before-whole-application-restart',actionId,parentStateSha256:actual.stateSha256});
      const producer=host.evidence!.parentProducer(parentId);
      const policyHandoff=await hooks.retainPolicy({sessionId:parentId,nativeThreadId:actual.nativeThreadId,checkpoint:actual,expectedCheckpoint:expected,acceptedContinuation,producer,profileDir:host.application.files.profile(parentId),workspace:host.application.files.workspace(host.application.store.getSession(parentId).workspaceId),hostPrivate:host.layout.hostPrivate,application:host.application});
      const state={source:'owned-application-restart-handoff',candidateCommit:input!.bootstrap.review.candidateCommit,runId,actionId,windowId,layout:host.layout,beforeHostId:host.hostId,parentId,parentNativeThreadId:actual.nativeThreadId,checkpoint:expected,latest,acceptedContinuation:acceptedContinuation??null,originalRefs:collector.exportReferences(parentId),seenActions:[...seenActions],observedSettlements,policyHandoff,producer,preservedCheckpointReceiptSha256:preserved.receiptSha256};
      const utf8=stableJson(state),statePath=join(host.layout.hostPrivate,`${randomUUID()}-restart-handoff.json`);await durableFile(statePath,utf8);
      return {statePath,stateSha256:sha256(utf8)};
    },
    async adoptRestart({ticket,signal}: {ticket:RestartTicket;signal:AbortSignal}) {
      if(host||opened||!hooks?.adoptPolicy||signal.aborted)throw Error('fresh_process_durable_adoption_required');
      const state=ticket.state;
      opened=true;acceptanceOwnerRunId=state.runId;parentId=state.parentId;latest=state.latest;
      host=await bootstrap(input!.bootstrap,hooks,ticket);
      await hooks.adoptPolicy({handoff:state.policyHandoff,checkpoint:state.checkpoint,producer:state.producer,sessionId:state.parentId,nativeThreadId:state.parentNativeThreadId,hostPrivate:state.layout.hostPrivate,application:host.application});
      collector=new NativeCollector({store:host.application.store,files:host.application.files,gateway:host.gateway,observer:host.observer,guard:host.guard,hostPrivate:host.layout.hostPrivate,withCaptureHold:host.withCaptureHold});
      for(const action of state.seenActions)seenActions.add(action);
      const actual=await openNativeParent(host,parentId!,signal,state.parentNativeThreadId);
      await collector.adoptReferences(parentId!,state.originalRefs,state.checkpoint);
      const after=await collector.captureState(parentId!,'actual-reopened-parent-without-answer-replay');
      if(after.stateUtf8!==state.checkpoint.stateUtf8||actual.nativeThreadId!==state.parentNativeThreadId)throw Error('native_parent_changed_after_process_restart');
      if(state.acceptedContinuation)lastContinuation={actionId:state.acceptedContinuation.actionId,runId:state.acceptedContinuation.artifactBaseline.storeRunId,artifactReceiptUtf8:state.acceptedContinuation.artifactBaseline.artifactReceiptUtf8,artifactReceiptSha256:state.acceptedContinuation.artifactBaseline.artifactReceiptSha256,parentState:after};
      return {nativeThreadId:actual.nativeThreadId,afterStateUtf8:after.stateUtf8,parentState:after,replayedActionIds:[],layout:host.layout,beforeHostId:state.beforeHostId,afterHostId:host.hostId};
    },
    async captureAcceptedArtifacts({acceptedContinuation,checkpoint:expected,signal}:any) {
      if(!host||!parentId||!collector||signal.aborted||!await settled(host)||!lastContinuation||lastContinuation.actionId!==acceptedContinuation?.actionId)throw Error('actual_reopened_accepted_artifact_owner_required');
      const baseline=acceptedContinuation.artifactBaseline;
      const capture=await collectContinuationArtifacts(host.application.store,host.application.files,host.layout.hostPrivate,parentId,baseline.storeRunId),receipt=JSON.parse(capture.artifactReceiptUtf8),artifactUtf8:Record<string,string>={};
      for(const artifact of receipt.artifacts){const original=baseline.artifacts[artifact.name];if(!original||original.artifactId!==artifact.artifactId||original.sha256!==artifact.sha256||original.bytes!==artifact.bytes||original.messageId!==artifact.messageId)throw Error('original_registered_artifact_bytes_not_preserved');artifactUtf8[artifact.name]=(await privateFile(join(host.layout.hostPrivate,`${artifact.captureId}-${artifact.name}`))).toString('utf8');}
      const current=await collector.captureState(parentId,'accepted-artifacts-after-application-restart');if(current.stateUtf8!==expected.stateUtf8)throw Error('accepted_parent_checkpoint_changed_after_restart');
      return {...capture,artifactUtf8,parentState:current,sessionId:parentId};
    },
    async childContext(args:any) {
      const h=sessionOwner(args.session);
      if(!hooks?.delegatedChild)throw Error('actual_native_delegated_child_lineage_capability_unavailable');
      try{return await hooks.delegatedChild({...args,host:h,parentId,collector,runId:acceptanceOwnerRunId,runParent:(text:string,id:string,purpose:any)=>main(h,args.signal,'message',text,id,'parent-artifacts',purpose)});}catch(error){faulted=true;throw error;}
    },
    async freshBriefControl({session,actionId,brief,hostOnlyParentCanary,childNonce,signal}:any) {
      const h=sessionOwner(session);if(!hooks||hooks.qualification.profile!=='h041-full-retention-v1'||typeof brief!=='string'||!brief.includes(childNonce)||typeof hostOnlyParentCanary!=='string'||brief.includes(hostOnlyParentCanary))throw Error('frozen_clean_child_contract_required');
      const placementResult=await main(h,signal,'message',`Keep this marker private to the parent: ${hostOnlyParentCanary}`,randomUUID(),'parent-artifacts','append');
      const state=await collector!.captureState(parentId!,'independent-parent-only-canary-placement');
      if(!state.stateUtf8.includes(hostOnlyParentCanary))throw Error('actual_parent_canary_placement_absent');
      const spec=input!.projectionSpec,manifest:ProbeManifest={input:[...structuredClone(spec.prefixInput),{type:'message',role:'user',content:[{type:'input_text',text:brief}]}],instructions:spec.envelope.instructions as string,userText:brief,contextSha256:state.stateSha256,envelope:structuredClone(spec.envelope)};
      const result=await summaryProbe(h,{parentNativeThreadId:state.nativeThreadId,summary:brief,childBrief:brief,contextSha256:state.stateSha256,frozenPolicy:input!.frozenPolicy,windowId:input!.bootstrap.review.authorization.windowId,compactedRecordSha256:latest!.compactedRecordSha256,collectorSourceSha256:input!.bootstrap.review.projection.collectorSourceSha256,collectorManifestUtf8:spec.collectorManifestUtf8,request:{childNonce},manifest,actionId,runId:acceptanceOwnerRunId!,signal});
      if(result.outcome!=='completed'||!('isolation'in result))throw Error('clean_child_native_failed');
      const after=await collector!.captureState(parentId!,'post-clean-child-parent-preservation');if(after.stateUtf8!==state.stateUtf8)throw Error('child_parent_contamination');
      await h.evidence!.operation({...result,requests:h.guard.requests(result.sessionId)},result.sessionId,input!.bootstrap.review.authorization.windowId,h.application.store,h.gateway,h.observer);
      return {...result,ownedSettlements:[{actionId:placementResult.actionId,nativeThreadId:placementResult.nativeThreadId,nativeTurnId:placementResult.nativeTurnId,settlementReceiptSha256:placementResult.settlement.receiptSha256}],probe:{...result.isolation,capturedBy:'host',parentId:state.nativeThreadId,childId:result.nativeThreadId,firstRequestId:(result.isolation as any).requestId,compiledMessages:normalizeNativeInput(JSON.parse((result.isolation as any).firstRequestUtf8).input),reply:result.answer,tools:[],parentPlacement:{capturedBy:'host',nativeThreadId:state.nativeThreadId,stateUtf8:state.stateUtf8,stateSha256:state.stateSha256,receiptSha256:state.receiptSha256,receiptUtf8:state.receiptUtf8}}};
    },
    async close({ runId, observedSettlements = [] }: any = {}) {
      closingRequested = true; await opening?.catch(() => undefined);
      if (host) { const h = host; await h.close(); host = undefined;
        if (h.evidence) return h.evidence.close(runId,input!.bootstrap.review.authorization.windowId,observedSettlements,h.observer);
      }
      return { outcome: 'closed', nativeAcceptance: 'NOT_TESTED' };
    },
  };
}
export default createNativeAdapter();
