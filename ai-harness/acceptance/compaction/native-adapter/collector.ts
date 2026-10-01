import { bindOriginalAliases } from '../ordinary.mjs';
import { constants } from 'node:fs';
import { lstat, open, readdir, realpath } from 'node:fs/promises';
import { join, relative } from 'node:path';
import { randomUUID } from 'node:crypto';
import type { Store } from '../../../server/src/store.js';
import type { Files } from '../../../server/src/files.js';
import type { Gateway } from '../../../server/src/gateway.js';
import type { DispatchGuard } from './dispatch-guard.js';
import { NativeObserver, type ObservedOperation } from './native-observer.js';
import { durableFile } from './checkpoint.js';
import { extractPersistedSummary, sha256, stableJson, identifier, reviewSnapshot } from './projection.js';

export interface ParentState {
  capturedBy: 'host'; nativeThreadId: string; stateUtf8: string; stateSha256: string;
  receiptSha256: string; receiptUtf8: string; sourceRef: string;
}
export interface CollectorHost {
  store: Store; files: Files; gateway: Gateway; guard: DispatchGuard; observer: NativeObserver;
  hostPrivate: string; withCaptureHold<T>(operation: () => Promise<T>): Promise<T>;
}
interface OriginalRef { productionSource?:any; recordId: string; messageId: string; runId: string; offset: number; length: number; contentSha256: string }
export interface FullCheckpoint extends ParentState {
  compactedRecordUtf8: string; compactedRecordSha256: string;
  bindingReceiptUtf8: string; bindingReceiptSha256: string;
  settledOperationUtf8: string; settledOperationSha256: string;
  messages?: { role: string; content: string }[]; selectedMessageSha256: string;
}
export class NativeCollector {
  private totalStateBytes = 0;
  private baselines = new Map<string, ParentState>();
  private originalRefs = new Map<string, OriginalRef[]>();
  constructor(private host: CollectorHost) {}
  async settled(sessionId: string) {
    const s = this.host.store.getSession(sessionId);
    return s.engineKind === 'codex' && s.nativeState.ownership === 'idle' && s.nativeState.activeTurnId === null &&
      !this.host.store.runs(sessionId).some(r => ['queued', 'running', 'cancelling'].includes(r.status)) &&
      this.host.observer.settled(sessionId) && await this.host.gateway.confirmSettlement({ sessionId });
  }
  /** Read from the actual unique native rollout, not a caller-supplied state. */
  private async readRollout(sessionId: string) {
    if (!await this.settled(sessionId)) throw Error('full_state_requires_no_writer_settlement');
    const expected = this.host.store.getSession(sessionId).nativeSessionId;
    if (!expected) throw Error('native_parent_identity_not_observed');
    const root = this.host.files.profile(sessionId);
    await this.host.files.assertNoLinks(root);
    if (await realpath(root) !== root) throw Error('rollout_root_not_canonical');
    const matches: { path: string; stateUtf8: string; nativeThreadId: string }[] = [];
    let count = 0, bytes = 0;
    const walk = async (path: string): Promise<void> => {
      const st = await lstat(path);
      if (++count > 8192 || st.isSymbolicLink() || st.uid !== process.getuid?.()) throw Error('rollout_scope_unsafe_or_bound');
      if (st.isDirectory()) { for (const name of (await readdir(path)).sort()) await walk(join(path, name)); return; }
      if (!st.isFile() || !path.endsWith('.jsonl')) return;
      if (st.nlink !== 1 || (bytes += st.size) > 64 * 1024 * 1024) throw Error('rollout_file_unsafe_or_bound');
      const fd = await open(path, constants.O_RDONLY | constants.O_NOFOLLOW);
      let buffer: Buffer;
      try {
        const start = await fd.stat();
        if (!start.isFile() || start.nlink !== 1 || start.uid !== process.getuid?.() || start.ino !== st.ino || start.dev !== st.dev ||
            start.size !== st.size || start.mtimeMs !== st.mtimeMs || start.size > 64 * 1024 * 1024 || await realpath(path) !== path) throw Error('rollout_opened_scope_unsafe');
        buffer = await fd.readFile(); const end = await fd.stat(), named = await lstat(path);
        if (!end.isFile() || end.nlink !== 1 || end.uid !== start.uid || named.ino !== start.ino || named.dev !== start.dev ||
            end.ino !== start.ino || end.dev !== start.dev || start.size !== end.size || start.mtimeMs !== end.mtimeMs || buffer.length !== end.size) throw Error('rollout_changed_during_read');
      } finally { await fd.close(); }
      const text = buffer.toString('utf8');
      if (!Buffer.from(text).equals(buffer) || !text.endsWith('\n')) throw Error('rollout_not_flushed_utf8_jsonl');
      const records: unknown[] = text.slice(0, -1).split('\n').map(line => JSON.parse(line));
      const meta = records.filter((r: any) => r?.type === 'session_meta') as { payload?: { id?: string } }[];
      if (meta.length === 1 && meta[0].payload?.id === expected) matches.push({ path, stateUtf8: text, nativeThreadId: meta[0].payload.id });
    };
    await walk(root);
    if (matches.length !== 1 || !await this.settled(sessionId)) throw Error('rollout_missing_ambiguous_or_new_writer');
    return matches[0];
  }
  private async captureStateHeld(sessionId: string, purpose: string): Promise<ParentState> {
    const actual = await this.readRollout(sessionId), stateSha256 = sha256(actual.stateUtf8);
    if (this.baselines.size >= 128 || this.totalStateBytes + Buffer.byteLength(actual.stateUtf8) > 64 * 1024 * 1024) throw Error('full_state_total_capture_bound');
    this.totalStateBytes += Buffer.byteLength(actual.stateUtf8);
    const captureId = randomUUID(), sourceRef = `profile/${relative(this.host.files.profile(sessionId), actual.path)}`;
    await durableFile(join(this.host.hostPrivate, `${captureId}-state.jsonl`), actual.stateUtf8);
    const receiptUtf8 = JSON.stringify({ source: 'owned-native-persisted-state', captureId, purpose, sessionId,
      nativeThreadId: actual.nativeThreadId, sourceRef, stateSha256, bytes: Buffer.byteLength(actual.stateUtf8),
      observedAt: new Date().toISOString(), nativeCleanupObserved: true, gatewaySettlementObserved: true });
    await durableFile(join(this.host.hostPrivate, `${captureId}-state-receipt.json`), receiptUtf8);
    const state: ParentState = { capturedBy: 'host', nativeThreadId: actual.nativeThreadId, stateUtf8: actual.stateUtf8,
      stateSha256, receiptUtf8, receiptSha256: sha256(receiptUtf8), sourceRef };
    this.baselines.set(state.receiptSha256, Object.freeze(state));
    return state;
  }
  captureState(sessionId: string, purpose: string) { return this.host.withCaptureHold(() => this.captureStateHeld(sessionId, purpose)); }
  preflightOriginals(sessionId: string, records: { id: string; content: string }[]) {
    const previous = new Set((this.originalRefs.get(sessionId) ?? []).map(r => r.recordId));
    if (!Array.isArray(records) || !records.length || records.length > 1024 || records.reduce((n, r) => n + Buffer.byteLength(typeof r?.content === 'string' ? r.content : ''), 0) > 4 * 1024 * 1024 || records.some(r => !identifier(r?.id) || typeof r.content !== 'string' || !r.content || previous.has(r.id)) ||
        new Set(records.map(r => r.id)).size !== records.length) throw Error('original_records_invalid_or_duplicate_before_dispatch');
  }
  async appendOriginals<T extends { runId: string }>(sessionId: string, records: { id: string; content: string }[], dispatch: (records: { id: string; content: string }[]) => Promise<T>): Promise<T> {
    const approved = reviewSnapshot(records); this.preflightOriginals(sessionId, approved);
    const result = await dispatch(approved);
    try { this.observeOriginals(sessionId, result.runId, approved); return result; }
    catch (error) {
      const s = this.host.store.getSession(sessionId);
      this.host.store.setNativeState(sessionId, 'codex', { ...s.nativeState, ownership: 'uncertain' });
      await durableFile(join(this.host.hostPrivate, `${result.runId}-original-registration-FAILED.json`), stableJson({
        source: 'post-dispatch-original-registration-failure', sessionId, runId: result.runId, nativeThreadId: s.nativeSessionId,
        outcome: 'failed', settlement: 'quarantined', automaticReplay: false })).catch(() => undefined);
      throw Error('original_registration_failed_quarantined_no_replay');
    }
  }
  observeOriginals(sessionId: string, runId: string, records: { id: string; content: string }[]) {
    this.preflightOriginals(sessionId, records);
    const messages = this.host.store.messages(sessionId).filter(m => m.runId === runId && m.role === 'user');
    if (messages.length !== 1 || messages[0].content !== records.map(r => r.content).join('\n\n')) throw Error('original_message_bytes_not_observed');
    (this.host.store as any).memory?.indexHistory(sessionId);
    const refs = this.originalRefs.get(sessionId) ?? [], previous = new Set(refs.map(r => r.recordId));
    let offset = 0;
    for (const record of records) {
      if (previous.has(record.id)) throw Error('original_record_duplicate');
      const length = Buffer.byteLength(record.content);
      const memory=(this.host.store as any).memory?.bridge(sessionId);
      let productionSource:any;
      if(memory){const matches=memory.view().references.filter((r:any)=>r.kind==='message'&&r.availability==='complete'&&r.sha256===sha256(messages[0].content)&&r.bytes===Buffer.byteLength(messages[0].content));if(matches.length!==1)throw Error('genuine_production_message_source_missing_or_ambiguous');productionSource=bindOriginalAliases(memory,[{alias:record.id,sourceId:matches[0].id,offset,bytes:length,sha256:sha256(record.content)}])[0];}
      refs.push({ ...(productionSource?{productionSource}:{}),recordId: record.id, messageId: messages[0].id, runId, offset, length, contentSha256: sha256(record.content) });
      previous.add(record.id); offset += length + 2;
    }
    this.originalRefs.set(sessionId, refs);
  }
  originals(sessionId: string) {
    return this.host.withCaptureHold(async () => {
      const parentState = await this.captureStateHeld(sessionId, 'independent-original-baseline');
      const messages = this.host.store.messages(sessionId), recordHashes: Record<string, string> = {};
      for (const ref of this.originalRefs.get(sessionId) ?? []) {
        const m = messages.find(m => m.id === ref.messageId && m.runId === ref.runId && m.role === 'user');
        if (!m) throw Error('original_message_missing_or_foreign');
        const content = Buffer.from(m.content).subarray(ref.offset, ref.offset + ref.length);
        if (sha256(content) !== ref.contentSha256) throw Error('original_message_content_changed');
        if(ref.productionSource){const memory=(this.host.store as any).memory?.bridge(sessionId);if(!memory||stableJson(bindOriginalAliases(memory,[ref.productionSource])[0])!==stableJson(ref.productionSource))throw Error('production_original_alias_changed');}
        recordHashes[ref.recordId] = sha256(content);
      }
      const receiptUtf8 = JSON.stringify({ source: 'owned-store-original-messages', sessionId, nativeThreadId: parentState.nativeThreadId,
        recordHashes, references: this.originalRefs.get(sessionId) ?? [], parentStateReceiptSha256: parentState.receiptSha256 });
      await durableFile(join(this.host.hostPrivate, `${randomUUID()}-originals.json`), receiptUtf8);
      return { capturedBy: 'host', recordHashes, receiptUtf8, receiptSha256: sha256(receiptUtf8), parentState };
    });
  }
  async frozenOriginals(sessionId: string) {
    return this.host.withCaptureHold(async () => {
      const parentState = await this.captureStateHeld(sessionId, 'frozen-scoped-originals');
      const messages = this.host.store.messages(sessionId), originals: { reference: string; bytes: Uint8Array }[] = [];
      const checkpointId = randomUUID();
      for (const ref of this.originalRefs.get(sessionId) ?? []) {
        const message = messages.find(m => m.id === ref.messageId && m.runId === ref.runId && m.role === 'user');
        if (!message) throw Error('frozen_original_owner_missing');
        const bytes = Buffer.from(Buffer.from(message.content).subarray(ref.offset, ref.offset + ref.length));
        if (sha256(bytes) !== ref.contentSha256) throw Error('frozen_original_changed');
        await durableFile(join(this.host.hostPrivate, `${checkpointId}-${originals.length}-original.bin`), bytes);
        originals.push({ reference: ref.recordId, bytes });
      }
      const receiptUtf8 = stableJson({ source: 'owned-immutable-original-checkpoint', checkpointId, sessionId, nativeThreadId: parentState.nativeThreadId,
        parentStateSha256: parentState.stateSha256, originals: originals.map(r => ({ reference: r.reference, bytes: r.bytes.length, sha256: sha256(r.bytes) })) });
      await durableFile(join(this.host.hostPrivate, `${checkpointId}-original-scope.json`), receiptUtf8);
      return { checkpointId, parentState, originals, receiptUtf8, receiptSha256: sha256(receiptUtf8), nativeRetrieval: 'NOT_TESTED' };
    });
  }
  exportReferences(sessionId:string) { return structuredClone(this.originalRefs.get(sessionId)??[]); }
  async adoptReferences(sessionId:string,refs:OriginalRef[],checkpoint:ParentState) {
    if(this.originalRefs.has(sessionId)||!Array.isArray(refs)||!refs.length||new Set(refs.map(r=>r.recordId)).size!==refs.length)throw Error('owned_original_alias_handoff_invalid');
    const current=await this.captureState(sessionId,'restart-original-alias-independent-state');
    if(current.nativeThreadId!==checkpoint.nativeThreadId||current.stateSha256!==checkpoint.stateSha256||current.stateUtf8!==checkpoint.stateUtf8)throw Error('restart_parent_state_changed');
    const messages=this.host.store.messages(sessionId);
    for(const ref of refs){const m=messages.find(m=>m.id===ref.messageId&&m.runId===ref.runId&&m.role==='user');if(!m||!identifier(ref.recordId)||!Number.isSafeInteger(ref.offset)||!Number.isSafeInteger(ref.length)||ref.offset<0||ref.length<1||ref.offset+ref.length>Buffer.byteLength(m.content)||sha256(Buffer.from(m.content).subarray(ref.offset,ref.offset+ref.length))!==ref.contentSha256)throw Error('genuine_original_alias_bytes_not_preserved');}
    for(const ref of refs)if(ref.productionSource){const memory=(this.host.store as any).memory?.bridge(sessionId);if(!memory||stableJson(bindOriginalAliases(memory,[ref.productionSource])[0])!==stableJson(ref.productionSource))throw Error('production_original_alias_not_preserved_after_restart');}
    this.originalRefs.set(sessionId,reviewSnapshot(refs));
  }
  async compaction(sessionId: string, input: { actionId: string; runId: string; windowId: string; baseline: ParentState;
    summaryPrefix: string; summaryRole?: 'system' | 'developer' | 'user' | 'assistant' }): Promise<FullCheckpoint> {
    return this.host.withCaptureHold(async () => {
      const baseline = this.baselines.get(input.baseline?.receiptSha256);
      if (!baseline || stableJson(baseline) !== stableJson(input.baseline)) throw Error('baseline_not_independent_owned_capture');
      const action = this.host.store.db.prepare('SELECT session_id,action_id,run_id FROM h024_compaction_actions WHERE session_id=? AND action_id=?').get(sessionId, input.actionId);
      const run = this.host.store.db.prepare('SELECT session_id,status FROM runs WHERE id=?').get(input.runId);
      if (!action || action.run_id !== input.runId || run?.session_id !== sessionId || run.status !== 'completed') throw Error('compaction_store_action_binding_absent');
      const operation: ObservedOperation = this.host.observer.operation(sessionId);
      if (operation.method !== 'thread/compact/start' || operation.nativeThreadId !== baseline.nativeThreadId || !operation.compactionId) throw Error('actual_compaction_operation_absent');
      const captures = this.host.guard.requests(sessionId).filter(r => r.runId === action.run_id);
      if (!captures.length || captures.some(r => r.actionId !== input.actionId || r.nativeThreadId !== operation.nativeThreadId || r.nativeTurnId !== operation.nativeTurnId)) throw Error('trusted_capture_action_run_native_binding_absent');
      const requests = captures.map(r => JSON.parse(r.firstRequestUtf8));
      const windows = [...new Set(requests.map(r => nativeWindowId(r)))];
      if (windows.length !== 1 || typeof windows[0] !== 'string' || !windows[0] ||
          requests.some(r => nativeCompactionMetadata(r)?.request_kind !== 'compaction' || nativeCompactionMetadata(r)?.compaction?.trigger !== 'manual') ||
          requests.some(r => r.client_metadata?.thread_id !== operation.nativeThreadId || r.client_metadata?.turn_id !== operation.nativeTurnId)) throw Error('actual_native_request_window_or_turn_unavailable_or_mismatch');
      const parentState = await this.captureStateHeld(sessionId, 'post-compaction-full-state');
      const selection = extractPersistedSummary(Buffer.from(parentState.stateUtf8), { nativeThreadId: operation.nativeThreadId,
        nativeTurnId: operation.nativeTurnId, actionId: String(action.action_id), beforeBytes: Buffer.byteLength(baseline.stateUtf8),
        beforeSha256: baseline.stateSha256, dispatchedAt: operation.request.observedAt, settledAt: operation.gateway.observedAt, summaryPrefix: input.summaryPrefix });
      const lines = parentState.stateUtf8.slice(0, -1).split('\n');
      const index = lines.findLastIndex(line => JSON.parse(line).type === 'compacted');
      const compactedRecordUtf8 = lines[index] + '\n', recordSha256 = sha256(compactedRecordUtf8);
      const recordOffset = Buffer.byteLength(lines.slice(0, index).join('\n') + '\n');
      const bindingReceiptUtf8 = JSON.stringify({ source: 'native-rollout-record-owner', nativeThreadId: operation.nativeThreadId,
        compactionActionId: String(action.action_id), nativeTurnId: operation.nativeTurnId, windowId: input.windowId, operationWindowId: input.windowId, windowIdProvenance: 'host-operation-window', nativeWindowId: windows[0],
        recordSha256, stateSha256: parentState.stateSha256, recordId: `sha256:${recordSha256}@byte:${recordOffset}`,
        sourceRef: `${parentState.sourceRef}#byte=${recordOffset}`, recordIdKind: 'source-byte-address', nativeRecordId: null,
        traceReceiptSha256: operation.traceReceiptSha256 });
      const settledOperationUtf8 = JSON.stringify({ source: 'native-compaction-settlement', status: 'completed', settlement: 'released',
        nativeThreadId: operation.nativeThreadId, actionId: String(action.action_id), nativeTurnId: operation.nativeTurnId,
        windowId: input.windowId, operationWindowId: input.windowId, windowIdProvenance: 'host-operation-window', nativeWindowId: windows[0], baselineStateSha256: baseline.stateSha256, postStateSha256: parentState.stateSha256,
        recordSha256, compactionId: operation.compactionId, startedAt: operation.request.observedAt, completedAt: operation.gateway.observedAt,
        actualRpcAckSha256: operation.ack.sha256, canonicalCompactionItemSha256: operation.compactionCompleted!.sha256, nativeTerminalSha256: operation.completed.sha256, nativeRequestCaptures: captures.map(c => ({ requestId: c.requestId, sha256: c.captureSha256, normalizedSha256: c.normalizedSha256 })),
        nativeCleanup: operation.cleanup, ownedGatewaySettlement: operation.gateway });
      for (const [label, bytes] of Object.entries({ record: compactedRecordUtf8, binding: bindingReceiptUtf8, settlement: settledOperationUtf8 }))
        await durableFile(join(this.host.hostPrivate, `${randomUUID()}-${label}.json`), bytes);
      return { ...parentState, compactedRecordUtf8, compactedRecordSha256: recordSha256, bindingReceiptUtf8,
        bindingReceiptSha256: sha256(bindingReceiptUtf8), settledOperationUtf8, settledOperationSha256: sha256(settledOperationUtf8),
        ...(input.summaryRole ? { messages: [{ role: input.summaryRole, content: selection.message }] } : {}), selectedMessageSha256: sha256(selection.message) };
    });
  }
}

/** Native window and host operation window are separate provenance domains. */
export function nativeCompactionMetadata(raw: any): any | undefined {
  const carrier = raw?.client_metadata?.['x-codex-turn-metadata'];
  if (typeof carrier !== 'string') return undefined;
  try {
    const parsed = JSON.parse(carrier), flat = raw?.client_metadata?.['x-codex-window-id'];
    if (typeof parsed?.window_id !== 'string' || !parsed.window_id || (flat !== undefined && flat !== parsed.window_id)) return undefined;
    return parsed;
  } catch { return undefined; }
}
export function nativeWindowId(raw: any): string | undefined { return nativeCompactionMetadata(raw)?.window_id; }
