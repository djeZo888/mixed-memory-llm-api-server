import { readdir, readFile, lstat } from 'node:fs/promises';
import { join } from 'node:path';
import { randomUUID } from 'node:crypto';
import { setTimeout as delay } from 'node:timers/promises';
import { requireId } from '../../../server/src/errors.js';
import { bootstrap, type BootstrapInput, type TemporaryHost } from './bootstrap.js';
import { checkpoint, durableFile } from './checkpoint.js';
import { extractPersistedSummary, sha256, stableJson, type CompactionBinding } from './projection.js';
import { summaryProbe } from './probe.js';
import type { ProbeManifest } from './dispatch-guard.js';

const unknown = (reason: string) => ({ value: null, reason });
const tokensUnknown = () => ({ input: { state: 'absent', value: null, source: null, receiptSha256: null, reason: 'native per-phase usage not observed' },
  summary: { state: 'absent', value: null, source: null, receiptSha256: null, reason: 'native summary usage not observed' },
  contextAfter: { state: 'absent', value: null, source: null, receiptSha256: null, reason: 'native post-compaction occupancy not observed' } });
export const BLOCKERS = Object.freeze([
  'B must accept fresh persisted-message projection; no summary fork/resume qualification exists',
  'Pinned CodexConnection rejects dynamic tool server calls; scoped durable retrieval unavailable',
  'Installed binary support for no-tools config and exact compiled manifest NOT_TESTED',
  'Actual native binary/tokenizer metadata and runtime/model observation binding unavailable before open',
  'Actual mount/egress attestation bound to probe thread/turn/request NOT_TESTED',
  'Cold checkpoint acceptance after latest graded continuation and no-writer same-parent resume interface unqualified',
  'Exact pinned compaction summary prefix must be supplied from A source audit; not available on this Mac',
]);
export interface AdapterInput {
  bootstrap: BootstrapInput; frozenPolicy: string; compactionSummaryPrefix: string;
  /** Host-only manifest approved for this exact summary/question payload. No
   * captures, answer key or controller implementation may enter model mounts.
   */
  manifests: Record<string, ProbeManifest>;
}
/** B run-reviewed loads an external root-owned module that calls this factory.
 * Exported default is disabled; capability names are never forged to pass B.
 * Original phases use unchanged createApp -> Broker -> CodexEngine composition.
 */
export function createNativeAdapter(input?: AdapterInput) {
  let host: TemporaryHost | undefined, parentId: string | undefined, busy = false, opened = false;
  let summary: ReturnType<typeof extractPersistedSummary> | undefined;
  const seenActions = new Set<string>();
  const originals = new Map<string, string>();
  const sessionOwner = (session: any) => {
    if (!host || !parentId || session?.sessionId !== parentId) throw Error('foreign_or_absent_session');
    return host;
  };
  const settled = async (h: TemporaryHost) => {
    if (!parentId) return false;
    const s = h.application.store.getSession(parentId);
    return s.nativeState.ownership === 'idle' && s.nativeState.activeTurnId === null &&
      !h.application.store.runs(parentId).some(r => ['queued', 'running', 'cancelling'].includes(r.status)) &&
      await h.gateway.confirmSettlement({ sessionId: parentId });
  };
  async function rollout(h: TemporaryHost) {
    const id = h.application.store.getSession(parentId!).nativeSessionId;
    if (!id) throw Error('parent_native_identity_absent');
    const root = h.application.files.profile(parentId!);
    const matches: { path: string; bytes: Buffer }[] = [];
    let entries = 0, total = 0;
    async function visit(path: string) {
      const stat = await lstat(path);
      if (++entries > 8192 || stat.isSymbolicLink()) throw Error('native_rollout_scope_unsafe');
      if (stat.isDirectory()) { for (const n of await readdir(path)) await visit(join(path, n)); }
      else if (stat.isFile() && path.endsWith('.jsonl')) {
        if ((total += stat.size) > 64 * 1024 * 1024 || stat.nlink !== 1) throw Error('rollout_capture_bound');
        const bytes = await readFile(path);
        let first: any;
        try { first = JSON.parse(bytes.toString('utf8').split('\n')[0]); } catch { return; }
        if (first.type === 'session_meta' && first.payload?.id === id) matches.push({ path, bytes });
      }
    }
    await visit(root);
    if (matches.length !== 1) throw Error('native_rollout_missing_or_ambiguous');
    return { ...matches[0], nativeThreadId: id };
  }
  async function captureCheckpoint(h: TemporaryHost, binding: Record<string, unknown>) {
    const s = h.application.store.getSession(parentId!);
    return checkpoint({ hostPrivate: h.layout.hostPrivate,
      sources: { profile: h.application.files.profile(parentId!), files: h.application.files.workspace(s.workspaceId) },
      binding: { ...binding, sessionId: parentId, parentNativeThreadId: s.nativeSessionId, eventCursor: s.nativeState.eventCursor,
        originals: Object.fromEntries([...originals].map(([id, content]) => [id, sha256(content)])) },
      settled: () => settled(h), databaseExport: async file => { h.application.store.db.prepare('VACUUM INTO ?').run(file); } });
  }
  async function main(h: TemporaryHost, signal: AbortSignal, kind: 'message' | 'compact', text: string, actionId: string) {
    signal = AbortSignal.any([signal, AbortSignal.timeout(Math.max(1, Math.min(120000, h.expiresAt - Date.now())))]);
    if (busy || signal.aborted || h.closing || Date.now() >= h.expiresAt) throw Error('adapter_busy_or_deadline');
    if (seenActions.has(actionId)) throw Error('duplicate_action_no_replay');
    requireId(actionId); // Existing app/native action contract; B owns ID repair.
    seenActions.add(actionId); busy = true;
    let runId: string | undefined;
    let cancellation: Promise<void> | undefined;
    const abort = () => { h.gateway.revokeSession(parentId!); cancellation ??= h.application.broker.cancel(parentId!).then(() => undefined).catch(() => undefined); };
    signal.addEventListener('abort', abort, { once: true });
    try {
      runId = h.application.broker.enqueue(parentId!, kind, text, [], [], kind === 'compact' ? actionId : undefined);
      h.guard.register({ sessionId: parentId!, actionId, runId, mode: 'main', signal,
        expiresAt: Math.min(h.expiresAt, Date.now() + 120000), identity: () => {
          const s = h.application.store.getSession(parentId!);
          return { nativeThreadId: s.nativeSessionId, nativeTurnId: s.nativeState.activeTurnId ?? undefined };
        } });
      for (;;) {
        const run = h.application.store.runSnapshot(runId);
        if (!['queued', 'running', 'cancelling'].includes(run.status)) {
          const proof = await settled(h);
          const requests = h.guard.requests(parentId!).filter(r => r.runId === runId);
          const nativeTurns = [...new Set(requests.map(r => r.nativeTurnId))];
          if (nativeTurns.length !== 1 || !nativeTurns[0]) throw Error('parent_phase_native_turn_unavailable_or_ambiguous');
          const receipt = { sessionId: parentId, actionId, runId, nativeThreadId: h.application.store.getSession(parentId!).nativeSessionId,
            nativeTurnId: nativeTurns[0], createdAt: run.createdAt, settledAt: new Date().toISOString(), requests,
            nativeOutcome: run.status, settled: proof, automaticReplay: false };
          await durableFile(join(h.layout.hostPrivate, `${runId}-parent-output.json`), stableJson({ receipt, snapshot: h.application.store.snapshot(parentId!) }) + '\n');
          if (!proof || run.status !== 'completed') throw Error('parent_native_failed_or_unsettled');
          return { ...receipt, outcome: 'completed', tokens: tokensUnknown(),
            settlement: { state: 'settled', receiptSha256: sha256(stableJson(receipt)), automaticReplay: false } };
        }
        if (signal.aborted || Date.now() >= h.expiresAt) { abort(); throw Error('parent_deadline_no_replay'); }
        await delay(10);
      }
    } catch {
      await cancellation;
      await durableFile(join(h.layout.hostPrivate, `${runId ?? randomUUID()}-parent-FAILED.json`), stableJson({
        actionId, runId: runId ?? null, outcome: 'failed', automaticReplay: false,
        settlement: await settled(h) ? 'settled' : 'unknown', snapshot: h.application.store.snapshot(parentId!) }) + '\n').catch(() => undefined);
      throw Error('parent_phase_failed_output_preserved_no_replay');
    } finally { signal.removeEventListener('abort', abort); h.guard.retire(parentId!); busy = false; }
  }
  return {
    interfaceVersion: 'h039-compaction-adapter-v1', kind: 'native', enabled: false,
    capabilities: [] as string[], blockers: BLOCKERS,
    async runtime() {
      // Static source pins belong to bootstrap review, not observed runtime.
      return { name: 'codex', version: unknown('installed native initialization not yet observed'),
        sourceRevision: unknown('installed runtime not independently observed'), binarySha256: unknown('binary attestation unavailable'),
        model: unknown('current provider admission not yet observed'), modelRevision: unknown('current model not yet observed'),
        tokenizerRevision: unknown('tokenizer revision absent'), promptRevision: 'kpm-technical-v1' };
    },
    async open({ signal }: any) {
      if (!input || opened || signal.aborted) throw Error('adapter_disabled_duplicate_or_aborted');
      opened = true; host = await bootstrap(input.bootstrap);
      const s = await host.application.broker.createSession(undefined, 'codex'); parentId = s.id;
      return { sessionId: parentId };
    },
    async append({ session, records, signal }: any) {
      const h = sessionOwner(session);
      if (!Array.isArray(records) || !records.length || records.some(r => !r.id || typeof r.content !== 'string' || originals.has(r.id))) throw Error('original_records_invalid_duplicate');
      const result = await main(h, signal, 'message', records.map(r => r.content).join('\n\n'), randomUUID());
      session.nativeThreadId = result.nativeThreadId;
      for (const r of records) originals.set(r.id, r.content);
      await durableFile(join(h.layout.hostPrivate, `${result.runId}-original-records.json`), stableJson(records) + '\n');
      return result;
    },
    async originals({ session }: any) {
      const h = sessionOwner(session);
      if (!await settled(h)) throw Error('original_checkpoint_requires_settlement');
      const result = await captureCheckpoint(h, { kind: 'original-preservation' });
      return { capturedBy: 'host', recordHashes: Object.fromEntries([...originals].map(([id, content]) => [id, sha256(content)])), receiptSha256: result.receiptSha256 };
    },
    async compact({ session, actionId, signal }: any) {
      const h = sessionOwner(session);
      requireId(actionId);
      if (!input?.compactionSummaryPrefix?.trim()) throw Error('pinned_summary_prefix_source_review_required_before_dispatch');
      if (!await settled(h)) throw Error('precompaction_settlement_required');
      const before = await rollout(h);
      const original = await captureCheckpoint(h, { actionId, kind: 'before-manual-compaction',
        originalRolloutSha256: sha256(before.bytes), originalRolloutBytes: before.bytes.length });
      const dispatchedAt = new Date().toISOString();
      const result = await main(h, signal, 'compact', '', actionId);
      const after = await rollout(h);
      if (after.nativeThreadId !== before.nativeThreadId) throw Error('compaction_parent_identity_changed');
      const binding: CompactionBinding = { nativeThreadId: before.nativeThreadId, nativeTurnId: result.nativeTurnId!, actionId,
        beforeBytes: before.bytes.length, beforeSha256: sha256(before.bytes), dispatchedAt, settledAt: result.settledAt,
        summaryPrefix: input.compactionSummaryPrefix };
      summary = extractPersistedSummary(after.bytes, binding);
      const afterCheckpoint = await captureCheckpoint(h, { kind: 'persisted-summary-checkpoint', ...binding, contextSha256: summary.contextSha256 });
      return { ...result, summaryState: 'complete', contextSha256: summary.contextSha256,
        trigger: { type: 'manual', evidence: ['owned thread/compact/start action; canonical native item required by CodexEngine'] },
        originalCheckpointReceiptSha256: original.receiptSha256, summaryCheckpointReceiptSha256: afterCheckpoint.receiptSha256,
        atomicRollback: false };
    },
    async probe({ session, contextSha256, mode, request, signal, actionId = randomUUID(), runId = randomUUID() }: any) {
      const h = sessionOwner(session);
      if (mode !== 'summary-only') throw Error('scoped_dynamic_retrieval_unavailable_pinned_connection');
      if (busy || !await settled(h) || !summary || summary.contextSha256 !== contextSha256) throw Error('summary_checkpoint_or_settlement_mismatch');
      const manifest = input!.manifests[sha256(stableJson({ contextSha256, request }))];
      if (!manifest) throw Error('exact_reviewed_compiled_probe_manifest_absent');
      busy = true;
      try { return await summaryProbe(h, { parentNativeThreadId: summary.nativeThreadId, summary: summary.message,
        contextSha256, request, signal, actionId, runId, frozenPolicy: input!.frozenPolicy, manifest }); }
      finally { busy = false; }
    },
    async continue({ session, request, signal, actionId = randomUUID() }: any) {
      const h = sessionOwner(session);
      if (!await settled(h)) throw Error('continuation_parent_unsettled');
      const result = await main(h, signal, 'message', stableJson(request), actionId);
      const checkpoint = await captureCheckpoint(h, { kind: 'after-latest-continuation-awaiting-grade', runId: result.runId });
      return { ...result, checkpoint, artifacts: null, failure: 'continuation_artifact_contract_not_qualified' };
    },
    async coldResume() { throw Error('latest_accepted_continuation_checkpoint_and_same_parent_no_writer_resume_unqualified'); },
    async cleanChild() { throw Error('separate_child_first_request_qualification_unavailable'); },
    async close() {
      if (host) {
        // Preserve all temporary state/output. Failed settlement is not released
        // by close, deleting directories, reconciliation, or an automatic retry.
        await host.close(); host = undefined;
      }
      return { outcome: 'closed', nativeAcceptance: 'NOT_TESTED' };
    },
  };
}
export default createNativeAdapter();
