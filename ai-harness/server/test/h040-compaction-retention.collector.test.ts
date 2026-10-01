import assert from 'node:assert/strict';
import test from 'node:test';
import { mkdtemp, mkdir, writeFile, appendFile, rm, realpath, access } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { resolve, join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { fixture } from '../../acceptance/compaction/controller.mjs';
import { actionIdFor, extractCheckpoint, extractNativeCompactionWindow, sha256 } from '../../acceptance/compaction/scorer.mjs';
import { translateResponses } from '../src/codex-responses.js';

const packet = await fixture();
const eRoot = process.env.H040_E_SOURCE_ROOT ?? resolve(import.meta.dirname, '../../acceptance/compaction/native-adapter');
const ready = await access(join(eRoot, 'collector.ts')).then(() => true, () => false);

// The actual concurrently authored E collector/guard run against real private
// files. Database/engine/observer/gateway boundaries are explicitly SYNTHETIC;
// no launch/cleanup receipt or installed-binary qualification is invented.
async function captured(t: any, wrongNativeWindow = false) {
  const { NativeCollector } = await import(pathToFileURL(join(eRoot, 'collector.ts')).href);
  const { DispatchGuard } = await import(pathToFileURL(join(eRoot, 'dispatch-guard.ts')).href);
  const directory = await realpath(await mkdtemp(join(tmpdir(), 'h040-b-e-collector-'))), profile = join(directory, 'profile'), hostPrivate = join(directory, 'host-private');
  await mkdir(profile, { mode: 0o700 }); await mkdir(hostPrivate, { mode: 0o700 });
  t.after(() => rm(directory, { recursive: true, force: true }));
  const parent = 'synthetic-parent', turn = 'synthetic-native-turn', sessionId = 'synthetic-host-session', runId = 'synthetic-broker-run';
  const actionId = actionIdFor('synthetic-controller-run', 1, 'compact'), windowId = 'synthetic-host-operation-window';
  const records = packet.corpus.records.filter((r: any) => r.cycle === 1).slice(0, 2), text = records.map((r: any) => r.content).join('\n\n');
  const typed = (text: string) => ({ type: 'message', role: 'user', content: [{ type: 'input_text', text }] });
  const rollout = join(profile, 'owned.jsonl');
  await writeFile(rollout, JSON.stringify({ type: 'session_meta', payload: { id: parent } }) + '\n' + JSON.stringify({ type: 'response_item', payload: typed(text) }) + '\n', { mode: 0o600 });
  const store = { getSession: () => ({ engineKind: 'codex', nativeSessionId: parent, nativeState: { ownership: 'idle', activeTurnId: null } }), runs: () => [],
    messages: () => [{ id: 'synthetic-message', runId: 'synthetic-append-run', role: 'user', content: text }],
    db: { prepare: (sql: string) => ({ get: () => sql.includes('h024_compaction_actions') ? { session_id: sessionId, action_id: actionId, run_id: runId } : { session_id: sessionId, status: 'completed' } }) } };
  const guard = new DispatchGuard(hostPrivate);
  const operation = { method: 'thread/compact/start', nativeThreadId: parent, nativeTurnId: turn, compactionId: 'synthetic-owned-compact-item',
    traceReceiptSha256: sha256('SYNTHETIC protocol observer'), request: { observedAt: '2026-10-01T02:30:02Z' },
    ack: { sha256: sha256('SYNTHETIC ACK') }, compactionCompleted: { sha256: sha256('SYNTHETIC canonical item') }, completed: { sha256: sha256('SYNTHETIC terminal') },
    cleanup: { confirmed: true, observedAt: '2026-10-01T02:30:04Z' }, gateway: { confirmed: true, observedAt: '2026-10-01T02:30:05Z' } };
  const collector = new NativeCollector({ store, files: { profile: () => profile, async assertNoLinks() {} }, gateway: { async confirmSettlement() { return true; } },
    observer: { settled: () => true, operation: () => operation }, guard, hostPrivate, async withCaptureHold(callback: () => Promise<any>) { return callback(); } });
  collector.observeOriginals(sessionId, 'synthetic-append-run', records);
  const before = await collector.originals(sessionId);
  guard.register({ sessionId, actionId, runId, mode: 'main', expiresAt: Date.now() + 10000, signal: new AbortController().signal,
    identity: () => ({ nativeThreadId: parent, nativeTurnId: turn, activeRunId: runId }) });
  const nativeMetadata = { thread_id: parent, turn_id: turn, window_id: `${parent}:${wrongNativeWindow ? 99 : 0}`, window_number: 0,
    context_window_id: 'synthetic-context-uuid', request_kind: 'compaction',
    compaction: { trigger: 'manual', reason: 'user_requested', implementation: 'responses', phase: 'standalone_turn', strategy: 'memento' } };
  const raw = { model: 'qwen3.8-27b', instructions: 'Synthetic frozen main policy.', input: [typed(text)], tools: [], tool_choice: 'auto', parallel_tool_calls: false,
    store: false, stream: true, client_metadata: { thread_id: parent, turn_id: turn,
      'x-codex-turn-metadata': JSON.stringify(nativeMetadata), 'x-codex-window-id': nativeMetadata.window_id } };
  guard.capture({ phase: 'pre_normalization', sessionId, requestId: 'synthetic-request', model: raw.model, bytes: Buffer.from(JSON.stringify(raw)) });
  const body = translateResponses(raw).body;
  await guard.wrap(async () => ({ inputTokens: 123, contextWindow: 480000 }))(body, { alias: raw.model }, 'unused-synthetic-key', new AbortController().signal, { requestId: 'synthetic-request' });
  guard.capture({ phase: 'normalized_request', sessionId, requestId: 'synthetic-request', model: raw.model, bytes: Buffer.from(JSON.stringify(body)) });
  await appendFile(rollout, JSON.stringify({ timestamp: '2026-10-01T02:30:03Z', type: 'compacted', payload: { message: 'SYNTHETIC_PREFIX\nExact useful project state.', replacement_history: [typed('ORIGINAL_HISTORY')] } }) + '\n');
  const checkpoint = await collector.compaction(sessionId, { actionId, runId, windowId, baseline: before.parentState, summaryPrefix: 'SYNTHETIC_PREFIX\n' });
  const expected = { contextSha256: checkpoint.stateSha256, parentThreadId: parent, actionId, nativeTurnId: turn, windowId,
    baseline: before.parentState, summaryRepresentation: 'persisted-message-only', requireNativeMetadata: true, compactionRequests: guard.requests(sessionId) };
  return { checkpoint, expected, before, collector, sessionId, records };
}
test('actual E collector preserves full raw state, originals, ownership and independent B native-window verification', { skip: !ready && 'E collector not in this candidate; set H040_E_SOURCE_ROOT to reviewed read-only sibling' }, async t => {
  const p = await captured(t), extraction = extractCheckpoint(p.checkpoint, p.expected);
  assert.equal(extraction.status, 'PASS'); assert.ok('summaryText' in extraction); // synthetic host/protocol consistency ONLY
  assert.equal(extraction.nativeWindowId, 'synthetic-parent:0');
  assert.notEqual(extraction.nativeWindowId, p.expected.windowId);
  assert.equal(extraction.summaryText.includes('ORIGINAL_HISTORY'), false); assert.equal(p.checkpoint.messages, undefined);
  assert.notEqual(p.checkpoint.stateSha256, p.checkpoint.compactedRecordSha256);
  const after = await p.collector.originals(p.sessionId); assert.deepEqual(after.recordHashes, p.before.recordHashes);
  for (const record of p.records) assert.equal(after.recordHashes[record.id], sha256(record.content));
  const missing = extractCheckpoint(p.checkpoint, { ...p.expected, compactionRequests: p.expected.compactionRequests.map((c: any) => ({ ...c, firstRequestUtf8: undefined })) });
  assert.equal(missing.status, 'NOT_TESTED');
});
test('B rejects inconsistent native thread:window_number even if actual E collector supplied a consistent flat alias', { skip: !ready && 'E collector not in this candidate; source contract remains unqualified' }, async t => {
  const p = await captured(t, true);
  assert.equal(extractNativeCompactionWindow(p.expected.compactionRequests, p.expected).status, 'FAIL');
  assert.equal(extractCheckpoint(p.checkpoint, p.expected).status, 'FAIL');
  const flat = structuredClone(p.expected.compactionRequests), request = JSON.parse(flat[0].firstRequestUtf8);
  request.client_metadata['x-codex-window-id'] = 'foreign:7'; flat[0].firstRequestUtf8 = JSON.stringify(request); flat[0].captureSha256 = sha256(flat[0].firstRequestUtf8);
  assert.equal(extractNativeCompactionWindow(flat, p.expected).status, 'FAIL');
});
