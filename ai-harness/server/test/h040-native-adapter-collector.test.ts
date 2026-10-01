import test from 'node:test';
import assert from 'node:assert/strict';
import { PassThrough } from 'node:stream';
import { mkdtemp, mkdir, readFile, realpath, rm, writeFile, symlink, appendFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { Store } from '../src/store.js';
import { Files } from '../src/files.js';
import { CodexConnection } from '../src/codex-connection.js';
import { NativeObserver } from '../../acceptance/compaction/native-adapter/native-observer.js';
import { NativeCollector, nativeWindowId } from '../../acceptance/compaction/native-adapter/collector.js';
import { DispatchGuard } from '../../acceptance/compaction/native-adapter/dispatch-guard.js';
import { translateResponses } from '../src/codex-responses.js';
import { sha256 } from '../../acceptance/compaction/native-adapter/projection.js';
// SYNTHETIC peers only. Real stdio parser, Store, Files, translator and fsynced
// registry execute. No native binary or provider is started or qualified.
const b = await import(new URL('../../acceptance/compaction/scorer.mjs', import.meta.url).href);
const auditedPrefix = JSON.parse(await readFile(new URL('./fixtures/h040-native-prefix.json', import.meta.url), 'utf8'));
const prefix = auditedPrefix.text;
assert.equal(auditedPrefix.bytes, 399);
assert.equal(Buffer.byteLength(prefix, 'utf8'), 399);
assert.equal(auditedPrefix.sha256, 'e9b088e794a6bb9082ac053fcc760bd818d7e720ee4bcdc72c6e480de7b7cb0e');
assert.equal(sha256(prefix), auditedPrefix.sha256);
async function fixture(t: any, opts: any = {}) {
  const root = await realpath(await mkdtemp(join(tmpdir(), 'h040-native-adapter-collector-')));
  const privateDir = join(root, 'private'), captures = join(privateDir, 'captures');
  await mkdir(privateDir, { mode: 0o700 }); await mkdir(captures, { mode: 0o700 });
  const store = new Store(join(root, 'store.sqlite')), files = new Files(join(root, 'app'), store); await files.init();
  const s = store.createSession(undefined, 'codex', { engineVersion: '0.158.0' }); await files.prepare(s.id, s.workspaceId); store.setNative(s.id, 'synthetic-parent', 'codex');
  const observer = new NativeObserver(captures), guard = new DispatchGuard(captures);
  const collector = new NativeCollector({ store, files, gateway: { confirmSettlement: async () => true } as any, guard, observer, hostPrivate: privateDir, withCaptureHold: async fn => fn() });
  const rollout = join(files.profile(s.id), 'rollout.jsonl');
  await writeFile(rollout, JSON.stringify({ type: 'session_meta', payload: { id: 'synthetic-parent' } }) + '\n', { mode: 0o600 });
  const handle = () => { const stdin = new PassThrough(), stdout = new PassThrough(); return { stdin, stdout, child: observer.wrap(s.id, { stdin, stdout, exited: new Promise(() => {}), terminateAndConfirm: async () => true }) }; };
  const opened = handle(); await opened.child.terminateAndConfirm(); observer.gateway(s.id, 'synthetic-parent', null, true);
  const original = store.createRun(store.getSession(s.id), 'message', 'source fact α\n\nsource fact β', []); store.updateRun(original.id, 'completed'); store.addMessage(s.id, 'user', original.text, original.id);
  collector.observeOriginals(s.id, original.id, [{ id: 'a', content: 'source fact α' }, { id: 'b', content: 'source fact β' }]); const before = await collector.originals(s.id);
  const actionId = 'h040-synthetic-c1-compact', run = store.createRun(store.getSession(s.id), 'compact', '', [], actionId); store.updateRun(run.id, 'running');
  const h = handle(), conn = new CodexConnection(h.child.stdout, h.child.stdin, () => {}, () => {}, 500); conn.initialized();
  h.stdin.on('data', data => {
    const req = JSON.parse(data.toString()); if (req.method === 'initialized') return; h.stdout.write(JSON.stringify({ id: req.id, result: {} }) + '\n');
    const notify = (method: string, params: any) => h.stdout.write(JSON.stringify({ method, params }) + '\n');
    notify('turn/started', { threadId: 'synthetic-parent', turn: { id: 'synthetic-turn' } });
    notify('item/started', { threadId: opts.wrongItemStart ? 'foreign' : 'synthetic-parent', turnId: 'synthetic-turn', item: { id: 'synthetic-compaction', type: 'contextCompaction' } });
    if (!opts.unfinished) notify('item/completed', { threadId: 'synthetic-parent', turnId: 'synthetic-turn', item: { id: 'synthetic-compaction', type: 'contextCompaction' } });
    notify('turn/completed', { threadId: 'synthetic-parent', turn: { id: 'synthetic-turn', status: 'completed', error: null } });
  });
  await conn.request('thread/compact/start', { threadId: 'synthetic-parent' });
  if (opts.capture !== false) {
    guard.register({ sessionId: s.id, actionId, runId: run.id, mode: 'main', expiresAt: Date.now() + 10000, signal: new AbortController().signal,
      identity: () => ({ nativeThreadId: 'synthetic-parent', nativeTurnId: 'synthetic-turn', activeRunId: run.id }) });
    const raw = { model: 'qwen3.8-27b', instructions: 'synthetic', tools: [], input: [{ type: 'message', role: 'user', content: [{ type: 'input_text', text: 'synthetic compaction' }] }], stream: true, store: false, tool_choice: 'auto', parallel_tool_calls: true,
      client_metadata: { thread_id: 'synthetic-parent', turn_id: 'synthetic-turn', 'x-codex-window-id': opts.windowMismatch ? 'wrong' : 'synthetic-parent:0',
        'x-codex-turn-metadata': JSON.stringify({ request_kind: 'compaction', window_id: 'synthetic-parent:0', compaction: { trigger: 'manual' } }) } };
    guard.capture({ sessionId: s.id, requestId: 'synthetic-request', model: raw.model, phase: 'pre_normalization', bytes: Buffer.from(JSON.stringify(raw)) } as any);
    await guard.wrap(async () => ({ inputTokens: 17, contextWindow: 480000 }))({ ...translateResponses(raw).body, model: raw.model }, { alias: raw.model } as any, 'synthetic-key', new AbortController().signal, { requestId: 'synthetic-request' } as any);
  }
  const message = prefix + '\nAccepted current facts', record = JSON.stringify({ type: 'compacted', timestamp: new Date().toISOString(), payload: { message, replacement_history: [{ role: 'user', content: 'ORACLE_MUST_NEVER_PROJECT' }] } }) + '\n';
  await appendFile(rollout, record); store.updateRun(run.id, opts.failedRun ? 'failed' : 'completed'); await h.child.terminateAndConfirm(); observer.gateway(s.id, 'synthetic-parent', 'synthetic-turn', true);
  t.after(async () => { store.close(); conn.fail(Error('synthetic fixture closed')); await rm(root, { recursive: true, force: true }); });
  return { collector, observer, guard, before, s, run, actionId, record, message, rollout, captures, files,
    collect: (extra = {}) => collector.compaction(s.id, { actionId, runId: run.id, windowId: 'h040-root-operation', baseline: before.parentState, summaryPrefix: prefix, ...extra }) };
}
test('SYNTHETIC full persisted collector interoperates with B and excludes replacement history', async t => {
  const f = await fixture(t), checkpoint = await f.collect();
  assert.equal(checkpoint.stateSha256, sha256(await readFile(f.rollout))); assert.notEqual(checkpoint.stateSha256, sha256(f.message));
  assert.equal(checkpoint.compactedRecordUtf8, f.record); assert.equal(checkpoint.selectedMessageSha256, sha256(f.message)); assert.equal(checkpoint.messages, undefined);
  const binding = JSON.parse(checkpoint.bindingReceiptUtf8), settled = JSON.parse(checkpoint.settledOperationUtf8);
  assert.equal(binding.nativeWindowId, 'synthetic-parent:0'); assert.equal(binding.operationWindowId, 'h040-root-operation'); assert.equal(binding.windowIdProvenance, 'host-operation-window');
  assert.equal(settled.settlement, 'released'); assert.equal(settled.canonicalCompactionItemSha256, f.observer.operation(f.s.id).compactionCompleted?.sha256);
  const expected = { contextSha256: checkpoint.stateSha256, parentThreadId: 'synthetic-parent', actionId: f.actionId, nativeTurnId: 'synthetic-turn', windowId: 'h040-root-operation', baseline: f.before.parentState, summaryRepresentation: 'persisted-message-only' };
  const extracted = b.extractCheckpoint(checkpoint, expected); assert.equal(extracted.status, 'PASS'); assert.equal(extracted.summaryText, f.message); assert.ok(!extracted.summaryText.includes('ORACLE_MUST_NEVER_PROJECT'));
  assert.deepEqual((await f.collector.originals(f.s.id)).recordHashes, f.before.recordHashes);
  assert.equal(b.extractCheckpoint({ ...checkpoint, stateUtf8: checkpoint.stateUtf8.replace('Accepted current facts', 'tampered') }, expected).status, 'FAIL');
});
test('SYNTHETIC collector rejects fabricated capture, unfinished/foreign item, inconsistent metadata and failed run', async t => {
  for (const opts of [{ capture: false }, { unfinished: true }, { wrongItemStart: true }, { windowMismatch: true }, { failedRun: true }]) {
    const f = await fixture(t, opts); await assert.rejects(f.collect({ requests: [{ runId: f.run.id, firstRequestUtf8: '{}' }] }));
  }
});
test('SYNTHETIC retained capture tampering and unowned baseline cannot attest compaction', async t => {
  const f = await fixture(t); await assert.rejects(f.collect({ baseline: { ...f.before.parentState, receiptSha256: '0'.repeat(64) } }), /baseline/);
  await writeFile(join(f.captures, 'synthetic-request-pre.bin'), '{}'); await assert.rejects(f.collect(), /capture/);
});
test('SYNTHETIC rollout rejects aliases outside native file scope', async t => {
  const f = await fixture(t); await symlink(f.rollout, join(f.files.profile(f.s.id), 'alias.jsonl')); await assert.rejects(f.collector.captureState(f.s.id, 'unsafe-link'), /scope/);
});
test('native metadata parsing never substitutes host labels', () => {
  assert.equal(nativeWindowId({ client_metadata: { 'x-codex-turn-metadata': '{bad', 'x-codex-window-id': 'h040-label' } }), undefined);
  assert.equal(nativeWindowId({ client_metadata: { 'x-codex-turn-metadata': '{"window_id":"native:3"}', 'x-codex-window-id': 'native:2' } }), undefined);
  assert.equal(nativeWindowId({ client_metadata: { 'x-codex-turn-metadata': '{"window_id":"native:3"}' } }), 'native:3');
});
test('SYNTHETIC original preflight rejects duplicate prior and batch IDs before any Store/native write', async t => {
  const f = await fixture(t), before = f.collector.originals(f.s.id);
  assert.throws(() => f.collector.preflightOriginals(f.s.id, [{ id: 'a', content: 'retry content' }]), /before_dispatch/);
  assert.throws(() => f.collector.preflightOriginals(f.s.id, [{ id: 'new', content: 'one' }, { id: 'new', content: 'two' }]), /before_dispatch/);
  f.collector.preflightOriginals(f.s.id, [{ id: 'distinct-correction', content: 'corrected original' }]);
  assert.deepEqual((await f.collector.originals(f.s.id)).recordHashes, (await before).recordHashes);
});
test('SYNTHETIC immutable scoped originals are copied from actual owned Store bytes, with no oracle projection', async t => {
  const f = await fixture(t), snapshot = await f.collector.frozenOriginals(f.s.id);
  assert.equal(Buffer.from(snapshot.originals[0].bytes).toString(), 'source fact α'); assert.equal(snapshot.nativeRetrieval, 'NOT_TESTED');
  snapshot.originals[0].bytes[0] = 0; const second = await f.collector.frozenOriginals(f.s.id);
  assert.equal(Buffer.from(second.originals[0].bytes).toString(), 'source fact α'); assert.equal(second.receiptSha256, sha256(second.receiptUtf8));
});
test('SYNTHETIC append duplicate preflight never calls dispatch; post-dispatch registration failure quarantines and cannot settle', async t => {
  const f = await fixture(t); let dispatches = 0;
  const dispatch = async () => { dispatches++; return { runId: f.run.id }; };
  await assert.rejects(f.collector.appendOriginals(f.s.id, [{ id: 'a', content: 'duplicate' }], dispatch));
  await assert.rejects(f.collector.appendOriginals(f.s.id, [{ id: 'new', content: 'x' }, { id: 'new', content: 'y' }], dispatch)); assert.equal(dispatches, 0);
  await assert.rejects(f.collector.appendOriginals(f.s.id, [{ id: 'new', content: 'missing actual persisted message' }], dispatch), /quarantined_no_replay/);
  assert.equal(dispatches, 1); assert.equal(await f.collector.settled(f.s.id), false);
});
