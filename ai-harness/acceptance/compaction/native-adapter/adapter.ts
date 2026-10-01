import { join } from 'node:path';
import { randomUUID } from 'node:crypto';
import { setTimeout as delay } from 'node:timers/promises';
import { requireId } from '../../../server/src/errors.js';
import { bootstrap, type BootstrapInput, type TemporaryHost } from './bootstrap.js';
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
  'Pinned main engine has no reviewed no-tools thread/start override; stage rejects nonempty tools before dispatch',
  'Installed no-tools config, actual compiled whole-envelope and empty-history qualification NOT_TESTED',
  'Actual native binary/tokenizer/model revisions and current protected provider tuple unavailable',
  'OwnedCodexProcess has no exact effective-container/mount/egress attestation seam; scope NOT_TESTED',
  'Pinned CodexConnection rejects all dynamic server calls; scoped durable retrieval unavailable',
  'Cold resume needs independent continuation acceptance followed by actual app/process restart and same-parent no-replay proof',
  'Clean child requires actual parent-canary placement, independent child first request and owned settlement',
]);
export interface AdapterInput {
  bootstrap: BootstrapInput; frozenPolicy: string; compactionSummaryPrefix: string;
  /** Independently frozen root-reviewed constructor, scaffold, whole envelope
   * and portable collector closure; B derives the same exact input separately. */
  projectionSpec: { format: 'h040-fresh-persisted-message-v1'; prefixInput: unknown[]; envelope: Record<string, unknown>; collectorManifestUtf8: string };
}
/** Disabled default. A root-owned entry module can enable only separately
 * qualified capabilities after review; source fixtures are not qualifications. */
export function createNativeAdapter(input?: AdapterInput) { return assembleAdapter(input); }
/** Explicit SOURCE fixture seam: cannot acquire native kind/capabilities or call bootstrap. */
export function createSyntheticAdapter(input: AdapterInput, fixture: { host: TemporaryHost; collector: NativeCollector; sessionId: string; acceptanceRunId: string }) {
  return assembleAdapter(input, fixture);
}
function assembleAdapter(input?: AdapterInput, fixture?: { host: TemporaryHost; collector: NativeCollector; sessionId: string; acceptanceRunId: string }) {
  // Snapshot expected digests and the approved content together, before open.
  input = input ? reviewSnapshot(input) : undefined;
  let host: TemporaryHost | undefined = fixture?.host, collector: NativeCollector | undefined = fixture?.collector, parentId: string | undefined = fixture?.sessionId;
  let acceptanceOwnerRunId: string | undefined = fixture?.acceptanceRunId;
  let opening: Promise<TemporaryHost> | undefined, closingRequested = false;
  let busy = false, opened = !!fixture, faulted = false, latest: FullCheckpoint | undefined;
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
  async function main(h: TemporaryHost, signal: AbortSignal, kind: 'message' | 'compact', text: string, actionId: string) {
    signal = AbortSignal.any([signal, AbortSignal.timeout(Math.max(1, Math.min(120000, h.dispatchCutoffAt - Date.now())))]);
    if (faulted || busy || signal.aborted || h.closing || Date.now() >= h.dispatchCutoffAt) throw Error('adapter_failed_busy_or_deadline');
    if (seenActions.has(actionId)) throw Error('duplicate_action_no_replay');
    requireId(actionId); seenActions.add(actionId); busy = true;
    let runId: string | undefined, cancellation: Promise<void> | undefined;
    const abort = () => { h.gateway.revokeSession(parentId!); cancellation ??= h.application.broker.cancel(parentId!).then(() => undefined).catch(() => undefined); };
    signal.addEventListener('abort', abort, { once: true });
    try {
      runId = h.application.broker.enqueue(parentId!, kind, text, [], [], kind === 'compact' ? actionId : undefined);
      h.guard.register({ sessionId: parentId!, actionId, runId, mode: 'main', signal,
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
          return { ...receipt, outcome: 'completed', durationMs: { state: 'measured', value: Date.parse(op.gateway.observedAt) - Date.parse(op.request.observedAt), source: 'host-native-operation-observation', receiptSha256: sha256(durationReceiptUtf8), reason: null }, tokens: tokensUnknown(),
            settlement: { state: 'released', receiptSha256: sha256(stableJson(receipt)), automaticReplay: false } };
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
    interfaceVersion: 'h039-compaction-adapter-v1', kind: fixture ? 'synthetic' : 'native', enabled: false,
    capabilities: [] as string[], blockers: BLOCKERS,
    async runtime() {
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
      opened = true; opening = bootstrap(input.bootstrap); host = await opening;
      if (closingRequested) { await host.close(); throw Error('adapter_closed_during_bootstrap'); }
      collector = new NativeCollector({ store: host.application.store, files: host.application.files, gateway: host.gateway,
        observer: host.observer, guard: host.guard, hostPrivate: host.layout.hostPrivate, withCaptureHold: host.withCaptureHold });
      const s = await host.application.broker.createSession(undefined, 'codex'); parentId = s.id;
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
      const result = await main(h, signal, 'compact', '', actionId);
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
    async probe({ session, contextSha256, mode, request, signal, actionId, runId }: any) {
      const h = sessionOwner(session);
      if (mode !== 'summary-only') throw Error('scoped_dynamic_retrieval_unavailable_pinned_connection');
      if (faulted || busy || !await settled(h) || !latest || latest.stateSha256 !== contextSha256) throw Error('summary_checkpoint_or_settlement_mismatch');
      const spec = input!.projectionSpec;
      if (spec.format !== 'h040-fresh-persisted-message-v1' || normalizeNativeInput(spec.prefixInput).some(m => !['system', 'developer'].includes(String(m.role)))) throw Error('reviewed_projection_scaffold_invalid');
      const selectedSummary = JSON.parse(latest.compactedRecordUtf8).payload.message;
      const userText = summaryProbeText(selectedSummary, input!.frozenPolicy, request);
      const manifest: ProbeManifest = { input: [...structuredClone(spec.prefixInput), { type: 'message', role: 'user', content: [{ type: 'input_text', text: userText }] }],
        instructions: spec.envelope.instructions as string, userText, contextSha256, envelope: structuredClone(spec.envelope) };
      const before = await collector!.captureState(parentId!, 'pre-summary-probe');
      if (before.stateSha256 !== latest.stateSha256) throw Error('summary_parent_state_changed');
      busy = true;
      try {
        const result = await summaryProbe(h, { parentNativeThreadId: latest.nativeThreadId,
          summary: JSON.parse(latest.compactedRecordUtf8).payload.message, contextSha256, request, signal, actionId, runId,
          windowId: input!.bootstrap.review.authorization.windowId, compactedRecordSha256: latest.compactedRecordSha256,
          collectorSourceSha256: input!.bootstrap.review.projection.collectorSourceSha256, collectorManifestUtf8: spec.collectorManifestUtf8, frozenPolicy: input!.frozenPolicy, manifest });
        const parentStateAfter = await collector!.captureState(parentId!, 'post-summary-probe');
        if (parentStateAfter.stateSha256 !== before.stateSha256 || result.outcome !== 'completed' || !('isolation' in result)) { faulted = true; throw Error('probe_failure_or_parent_contamination'); }
        return { ...result, isolation: { ...result.isolation, parentStateAfter } };
      } catch (error) { faulted = true; throw error; } finally { busy = false; }
    },
    async continue({ session, request, signal, actionId }: any) {
      const h = sessionOwner(session);
      if (!await settled(h)) throw Error('continuation_parent_unsettled');
      const result = await main(h, signal, 'message', stableJson(request), actionId);
      try {
        const artifacts = await collectContinuationArtifacts(h.application.store, h.application.files, h.layout.hostPrivate, parentId!, result.runId);
        const parentState = await collector!.captureState(parentId!, 'after-latest-continuation-awaiting-independent-grade');
        return { ...result, ...artifacts, parentState, acceptance: 'awaiting-independent-B-grade', coldCheckpoint: null };
      } catch (error) { faulted = true; throw error; }
    },
    async resumeAcceptedContinuation() { throw Error('actual_application_restart_and_independent_latest_continuation_acceptance_unqualified'); },
    async coldResume() { throw Error('accepted_continuation_then_actual_app_restart_same_parent_no_replay_seam_unqualified'); },
    async childContext() { throw Error('actual_parent_canary_child_scope_first_request_and_settlement_unqualified'); },
    async cleanChild() { throw Error('use_childContext_contract_actual_child_qualification_unavailable'); },
    async close() {
      closingRequested = true; await opening?.catch(() => undefined);
      if (host) { await host.close(); host = undefined; }
      return { outcome: 'closed', nativeAcceptance: 'NOT_TESTED' };
    },
  };
}
export default createNativeAdapter();
