import test from 'node:test';
import assert from 'node:assert/strict';
import { PassThrough } from 'node:stream';
import { mkdtemp, mkdir, readFile, readdir, realpath, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { summaryProbe } from '../../acceptance/compaction/native-adapter/probe.js';
import { NativeObserver } from '../../acceptance/compaction/native-adapter/native-observer.js';
import { DispatchGuard } from '../../acceptance/compaction/native-adapter/dispatch-guard.js';
import { sha256, stableJson, summaryProbeText } from '../../acceptance/compaction/native-adapter/projection.js';
import { translateResponses } from '../src/codex-responses.js';
const native = JSON.parse(await readFile(new URL('./fixtures/codex/native-requests.json', import.meta.url), 'utf8'))[0].body;
const b = await import(new URL('../../../../../B-retention-integration/repo/ai-harness/acceptance/compaction/scorer.mjs', import.meta.url).href);
// SYNTHETIC protocol and counter. Production parser/translator/guard/stdio tap
// execute; no native/model/container/mount or token measurement is qualified.
async function fixture(t: any, opts: any = {}) {
  const root = await realpath(await mkdtemp(join(tmpdir(), 'h040-native-adapter-protocol-'))), dataDir = join(root, 'data'), hostPrivate = join(root, 'private'), captures = join(root, 'captures');
  for (const p of [dataDir, hostPrivate, captures]) await mkdir(p, { mode: 0o700 });
  t.after(() => rm(root, { recursive: true, force: true }));
  const observer = new NativeObserver(captures), guard = new DispatchGuard(captures), stdin = new PassThrough(), stdout = new PassThrough();
  const methods: string[] = [], cleanup: string[] = [];
  const contextSha256 = sha256('FULL SYNTHETIC PARENT JSONL'), request = { questions: [] }, frozenPolicy = 'frozen reviewed fixture policy', summary = 'actual selected synthetic summary';
  const text = summaryProbeText(summary, frozenPolicy, request);
  const raw = { ...structuredClone(native), tools: [], instructions: frozenPolicy, input: [{ type: 'message', role: 'user', content: [{ type: 'input_text', text }] }],
    client_metadata: { thread_id: 'synthetic-probe', turn_id: 'synthetic-turn', root_turn_id: 'synthetic-turn' } };
  const envelope: any = Object.fromEntries(Object.entries(raw).filter(([k]) => !['input', 'tools'].includes(k)));
  envelope.client_metadata = { thread_id: '@h040:probe-native-thread-id', turn_id: '@h040:probe-native-turn-id', root_turn_id: '@h040:probe-native-turn-id' };
  let home: string, workspace: string, appSession: string;
  const notify = (method: string, params: any) => stdout.write(JSON.stringify({ method, params }) + '\n');
  const host: any = { layout: { root, dataDir, hostPrivate }, expiresAt: Date.now() + (opts.stall ? 2000 : 10000), dispatchCutoffAt: Date.now() + (opts.stall ? 2000 : 10000), closing: false,
    launchHeld: () => host.closing || !!opts.held, directProbes: new Map(), observer, guard,
    host: { runtime: { gatewayUrl: 'http://10.0.2.2:8081/v1', modelPolicyVersion: 'synthetic-policy',
      launchRootless: async (p: any) => { home = p.codexHome; workspace = p.workspace; appSession = p.sessionId;
        assert.deepEqual(await readdir(p.profileDir), []); assert.deepEqual(await readdir(p.workspace), []);
        return observer.wrap(p.sessionId, { stdin, stdout, exited: new Promise(() => {}), terminateAndConfirm: async () => {
          cleanup.push('native'); if (opts.truncatedCleanup) stdout.write('{'); stdout.end(); return opts.nativeGone !== false; } }); } } },
    gateway: { issueToken: () => 'synthetic-token', revokeSession: () => cleanup.push('revoke'), confirmSettlement: async () => { cleanup.push('gateway'); return opts.gatewaySettled !== false; } } };
  if (opts.receiptFailure) observer.gateway = () => { throw Error('synthetic durable receipt write failure'); };
  stdin.on('data', async bytes => {
    for (const line of bytes.toString().trim().split('\n')) {
      const r = JSON.parse(line); methods.push(r.method); if (r.method === 'initialized') continue;
      let result: any = {};
      if (r.method === 'initialize') result = { codexHome: home, platformOs: 'linux', platformFamily: 'unix', userAgent: 'SYNTHETIC/0.158.0' };
      else if (r.method === 'thread/start') {
        assert.deepEqual(r.params.environments, []); assert.equal(r.params.config['agents.enabled'], false); assert.equal(r.params.ephemeral, false);
        result = { thread: { id: 'synthetic-probe' }, model: 'qwen3.8-27b', modelProvider: 'sova', cwd: workspace, approvalPolicy: 'never' };
      } else if (r.method === 'turn/start') {
        assert.equal(r.params.input[0].text, text); result = { turn: { id: 'synthetic-turn' } };
        notify('turn/started', { threadId: 'synthetic-probe', turn: { id: 'synthetic-turn' } });
        guard.capture({ sessionId: appSession, requestId: 'source-request', model: raw.model, phase: 'pre_normalization', bytes: Buffer.from(JSON.stringify(raw)) } as any);
        try { await guard.wrap(async () => ({ inputTokens: 19, contextWindow: 480000 }))({ ...translateResponses(raw).body, model: raw.model }, { alias: raw.model } as any, 'synthetic-key', new AbortController().signal, { requestId: 'source-request' } as any); }
        catch { stdout.end(); return; }
        if (opts.preterminalEof) { stdout.end(); return; }
        if (!opts.stall) {
          const item = { id: 'synthetic-answer', type: opts.tool ? 'commandExecution' : 'agentMessage', phase: 'final_answer', text: '{"answers":{}}' };
          if (!opts.unstarted) notify('item/started', { threadId: 'synthetic-probe', turnId: 'synthetic-turn', item });
          notify('item/completed', { threadId: 'synthetic-probe', turnId: 'synthetic-turn', item });
          notify('turn/completed', { threadId: 'synthetic-probe', turn: { id: 'synthetic-turn', status: 'completed', error: null, itemsView: 'summary', items: [item] } });
        }
      }
      stdout.write(JSON.stringify({ id: r.id, result }) + '\n');
    }
  });
  const input = { parentNativeThreadId: 'synthetic-parent', summary, contextSha256, frozenPolicy, request, actionId: 'h040-source-probe', runId: 'suite-source-run', windowId: 'host-operation-window',
    compactedRecordSha256: sha256('synthetic selected record bytes'), collectorSourceSha256: sha256('synthetic closure'), collectorManifestUtf8: 'synthetic closure', signal: new AbortController().signal,
    manifest: { input: raw.input, instructions: raw.instructions, userText: text, contextSha256, envelope } };
  return { host, input, methods, cleanup, raw, captures };
}
test('SYNTHETIC completed probe survives intentional owned cleanup EOF and retains real request bytes', async t => {
  const f = await fixture(t), r: any = await summaryProbe(f.host, f.input);
  assert.equal(r.outcome, 'completed'); assert.equal(r.settlement.state, 'released'); assert.deepEqual(r.answer, { answers: {} });
  assert.deepEqual(f.methods, ['initialize', 'initialized', 'thread/start', 'turn/start']); assert.equal(f.host.directProbes.size, 0);
  assert.equal(r.isolation.captureSha256, sha256(await readFile(join(f.captures, 'source-request-pre.bin'))));
  assert.equal(r.isolation.normalizedSha256, sha256(r.isolation.normalizedRequestUtf8)); assert.equal(r.isolation.networkDenied, null);
  assert.deepEqual(JSON.parse(r.isolation.firstRequestUtf8).input, f.raw.input); assert.deepEqual(JSON.parse(r.isolation.normalizedRequestUtf8), translateResponses(f.raw).body);
  assert.equal(b.verifySummaryIsolation(r.isolation, { parentThreadId: 'synthetic-parent', probeThreadId: r.nativeThreadId, probeTurnId: r.nativeTurnId,
    actionId: r.actionId, runId: r.runId, inputMessageHashes: [sha256(stableJson({ role: 'user', content: f.input.manifest.userText }))] }).status, 'NOT_TESTED');
});
test('SYNTHETIC preterminal/truncated EOF, tools, incomplete items and unconfirmed cleanup never pass', async t => {
  for (const opts of [{ preterminalEof: true }, { truncatedCleanup: true }, { tool: true }, { unstarted: true }, { nativeGone: false }, { gatewaySettled: false }]) {
    const f = await fixture(t, opts);
    try { const r: any = await summaryProbe(f.host, f.input); assert.equal(r.outcome, 'failed'); } catch (error) { assert.match(String(error), /native_operation|capture|trace|cleanup/); }
    assert.equal(f.host.directProbes.size, 0); assert.ok(f.cleanup.includes('native')); assert.ok(f.cleanup.includes('gateway'));
  }
});
test('SYNTHETIC failed settlement receipt cannot strand host close handle', async t => {
  const f = await fixture(t, { receiptFailure: true }), p = summaryProbe(f.host, f.input);
  while (!f.host.directProbes.size) await new Promise(r => setImmediate(r));
  const finished = [...f.host.directProbes.values()][0].finished;
  const result: any = await p; await Promise.race([finished, new Promise((_, reject) => setTimeout(() => reject(Error('stranded handle')), 500))]);
  assert.equal(result.outcome, 'failed'); assert.equal(result.failure, 'probe_settlement_capture_failed'); assert.equal(f.host.directProbes.size, 0);
});
test('SYNTHETIC total post-ACK deadline settles once without replay', async t => {
  const f = await fixture(t, { stall: true }), r: any = await summaryProbe(f.host, f.input);
  assert.equal(r.outcome, 'failed'); assert.equal(f.methods.filter(m => m === 'turn/start').length, 1); assert.equal(f.methods.filter(m => m === 'turn/interrupt').length, 1); assert.equal(f.host.directProbes.size, 0);
});
test('SYNTHETIC trusted shared launch hold prevents probe creation', async t => {
  const f = await fixture(t, { held: true }); await assert.rejects(summaryProbe(f.host, f.input), /mismatch_or_aborted/); assert.deepEqual(f.methods, []);
});
