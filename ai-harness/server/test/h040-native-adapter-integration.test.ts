import test from 'node:test';
import assert from 'node:assert/strict';
import { PassThrough } from 'node:stream';
import { mkdtemp, mkdir, readFile, realpath, rm, writeFile, appendFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { Store } from '../src/store.js';
import { Files } from '../src/files.js';
import { CodexConnection } from '../src/codex-connection.js';
import { translateResponses } from '../src/codex-responses.js';
import { NativeObserver } from '../../acceptance/compaction/native-adapter/native-observer.js';
import { NativeCollector } from '../../acceptance/compaction/native-adapter/collector.js';
import { DispatchGuard } from '../../acceptance/compaction/native-adapter/dispatch-guard.js';
import { createSyntheticAdapter } from '../../acceptance/compaction/native-adapter/adapter.js';
import { sha256 } from '../../acceptance/compaction/native-adapter/projection.js';
const base = new URL('../../../../../B-retention-integration/repo/ai-harness/acceptance/compaction/', import.meta.url);
const b = await import(new URL('scorer.mjs', base).href), bc = await import(new URL('controller.mjs', base).href), be = await import(new URL('evidence.mjs', base).href);
const prefix = JSON.parse(await readFile(new URL('../../../../native-prefix.json', import.meta.url), 'utf8')).text;
// Entire adapter.compact path with real Store/Files/checkpoint/connection/guard
// and a clearly synthetic broker/stdin peer. Never qualifies native execution.
test('SYNTHETIC actual E adapter.compact result passes B shape/scorer with native acceptance NOT_TESTED', async t => {
  const root = await realpath(await mkdtemp(join(tmpdir(), 'h040-native-adapter-integration-'))), privateDir = join(root, 'private'), captures = join(root, 'captures');
  await mkdir(privateDir, { mode: 0o700 }); await mkdir(captures, { mode: 0o700 });
  const store = new Store(join(root, 'store.sqlite')), files = new Files(join(root, 'app'), store); await files.init();
  const s = store.createSession(undefined, 'codex', { engineVersion: '0.158.0' }); await files.prepare(s.id, s.workspaceId); store.setNative(s.id, 'synthetic-parent', 'codex');
  const observer = new NativeObserver(captures), guard = new DispatchGuard(captures), gateway: any = { confirmSettlement: async () => true, revokeSession: () => {} };
  const host: any = { application: { store, files }, layout: { dataDir: files.root, hostPrivate: privateDir }, observer, guard, gateway, closing: false, expiresAt: Date.now() + 30000, dispatchCutoffAt: Date.now() + 10000,
    withCaptureHold: async (fn: any) => fn(), close: async () => {} };
  const collector = new NativeCollector({ store, files, observer, guard, gateway, hostPrivate: privateDir, withCaptureHold: host.withCaptureHold });
  const rollout = join(files.profile(s.id), 'rollout.jsonl'); await writeFile(rollout, '{"type":"session_meta","payload":{"id":"synthetic-parent"}}\n', { mode: 0o600 });
  const opened = observer.wrap(s.id, { stdin: new PassThrough(), stdout: new PassThrough(), exited: new Promise(() => {}), terminateAndConfirm: async () => true }); await opened.terminateAndConfirm(); observer.gateway(s.id, 'synthetic-parent', null, true);
  const before = await collector.originals(s.id), suiteRunId = 'h040-source-suite', actionId = b.actionIdFor(suiteRunId, 1, 'compact');
  let connection: CodexConnection | undefined, runId: string | undefined;
  host.application.broker = { cancel: async () => {}, enqueue: (_id: string, kind: string, text: string, _a: any, _b: any, action: string) => {
    const run = store.createRun(store.getSession(s.id), kind as any, text, [], action); runId = run.id; store.updateRun(run.id, 'running');
    queueMicrotask(async () => {
      const stdin = new PassThrough(), stdout = new PassThrough(), child = observer.wrap(s.id, { stdin, stdout, exited: new Promise(() => {}), terminateAndConfirm: async () => true });
      connection = new CodexConnection(child.stdout, child.stdin, (_method, p) => { if (p.turn?.id) store.setNativeState(s.id, 'codex', { ownership: _method === 'turn/completed' ? 'idle' : 'active', activeTurnId: _method === 'turn/completed' ? null : p.turn.id, eventCursor: 0 }); }, () => {}, 1000);
      stdin.on('data', async bytes => {
        const rpc = JSON.parse(bytes.toString()); stdout.write(JSON.stringify({ id: rpc.id, result: {} }) + '\n');
        const notify = (method: string, params: any) => stdout.write(JSON.stringify({ method, params }) + '\n');
        notify('turn/started', { threadId: 'synthetic-parent', turn: { id: 'synthetic-turn' } });
        const raw = { model: 'qwen3.8-27b', stream: true, store: false, instructions: 'synthetic', input: [], tools: [], tool_choice: 'auto', parallel_tool_calls: true,
          client_metadata: { thread_id: 'synthetic-parent', turn_id: 'synthetic-turn', 'x-codex-window-id': 'synthetic-parent:0',
            'x-codex-turn-metadata': JSON.stringify({ thread_id: 'synthetic-parent', turn_id: 'synthetic-turn', window_id: 'synthetic-parent:0', window_number: 0, context_window_id: 'synthetic-context-window', request_kind: 'compaction', compaction: { trigger: 'manual', reason: 'user_requested', implementation: 'responses', phase: 'standalone_turn', strategy: 'memento' } }) } };
        guard.capture({ sessionId: s.id, requestId: 'actual-source-request', model: raw.model, phase: 'pre_normalization', bytes: Buffer.from(JSON.stringify(raw)) } as any);
        await guard.wrap(async () => ({ inputTokens: 11, contextWindow: 480000 }))({ ...translateResponses(raw).body, model: raw.model }, { alias: raw.model } as any, 'synthetic-key', new AbortController().signal, { requestId: 'actual-source-request' } as any);
        const item = { id: 'synthetic-compaction', type: 'contextCompaction' }; notify('item/started', { threadId: 'synthetic-parent', turnId: 'synthetic-turn', item });
        await appendFile(rollout, JSON.stringify({ timestamp: new Date().toISOString(), type: 'compacted', payload: { message: prefix + '\nselected source summary', replacement_history: [{ content: 'ORACLE_NEVER_PROJECT' }] } }) + '\n');
        notify('item/completed', { threadId: 'synthetic-parent', turnId: 'synthetic-turn', item }); notify('turn/completed', { threadId: 'synthetic-parent', turn: { id: 'synthetic-turn', status: 'completed', error: null } });
        await child.terminateAndConfirm(); observer.gateway(s.id, 'synthetic-parent', 'synthetic-turn', true); store.updateRun(run.id, 'completed');
      });
      await connection.request('thread/compact/start', { threadId: 'synthetic-parent' });
    });
    return run.id;
  } };
  const adapter = createSyntheticAdapter({ compactionSummaryPrefix: prefix, bootstrap: { review: { authorization: { windowId: 'h040-operation-window' } } } } as any,
    { host, collector, sessionId: s.id, acceptanceRunId: suiteRunId });
  t.after(async () => { connection?.fail(Error('synthetic fixture closed')); store.close(); await rm(root, { recursive: true, force: true }); });
  assert.equal(adapter.kind, 'synthetic'); assert.equal(adapter.enabled, false);
  const result = await adapter.compact({ session: { sessionId: s.id, nativeThreadId: 'synthetic-parent' }, actionId, runId: suiteRunId, windowId: 'h040-operation-window', baseline: before.parentState, signal: new AbortController().signal });
  assert.equal(result.outcome, 'completed'); assert.equal(result.durationMs.state, 'measured');
  const evidence = result.trigger.evidence[0]; assert.deepEqual(Object.keys(evidence).sort(), ['actionId', 'kind', 'nativeThreadId', 'ref', 'runId', 'sha256']);
  const bytes = await readFile(join(privateDir, evidence.ref)); assert.equal(evidence.sha256, sha256(bytes)); assert.equal(JSON.parse(bytes.toString()).storeRunId, runId); assert.equal(evidence.runId, suiteRunId);
  const extracted = b.extractCheckpoint(result.checkpoint, { contextSha256: result.contextSha256, parentThreadId: result.nativeThreadId, actionId, nativeTurnId: result.nativeTurnId, windowId: result.operationWindowId, baseline: before.parentState,
    summaryRepresentation: 'persisted-message-only', requireNativeMetadata: true, compactionRequests: result.requests }); assert.equal(extracted.status, 'PASS');
  const packet = await bc.fixture(), originals = { recoverable: true, beforeSha256: sha256('synthetic originals'), afterSha256: sha256('synthetic originals'), receiptSha256: before.receiptSha256 };
  const record = bc.makeRecord({ packet, runId: suiteRunId, cycle: 1, mode: 'fault', qualification: 'native', runtime: await adapter.runtime(), observation: result, originals, grade: { status: 'NOT_TESTED', errors: [] } });
  assert.deepEqual(be.validateRecord(record), []); assert.equal(record.status, 'NOT_TESTED');
});
