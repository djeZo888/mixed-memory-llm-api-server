import test from 'node:test';
import assert from 'node:assert/strict';
import { PassThrough } from 'node:stream';
import { mkdtemp, mkdir, readdir, readFile, rm, realpath } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { NativeObserver } from '../../acceptance/compaction/native-adapter/native-observer.js';
import { DispatchGuard } from '../../acceptance/compaction/native-adapter/dispatch-guard.js';
import { translateResponses } from '../src/codex-responses.js';
import { summaryProbe } from '../../acceptance/compaction/native-adapter/probe.js';
import { sha256, summaryProbeText } from '../../acceptance/compaction/native-adapter/projection.js';

// Explicit synthetic stdio peer; real CodexConnection parses JSONL. These tests
// exercise source ownership/settlement, never execute or attest native Codex.
async function fixture(t: any, { wrongThread = false, tool = false, nativeGone = true, gatewaySettled = true, stall = false, premature = false, rerouted = false, notLoaded = false, reordered = false, invalidAnswer = false, ownedDeadline = false, commentary = false } = {}) {
  const root = await realpath(await mkdtemp(join(tmpdir(), 'h039-native-adapter-protocol-')));
  const dataDir = join(root, 'data'), hostPrivate = join(root, 'private');
  for (const dir of [dataDir, hostPrivate]) await mkdir(dir, { mode: 0o700 });
  t.after(() => rm(root, { recursive: true, force: true }));
  const stdin = new PassThrough(), stdout = new PassThrough(), callerAbort=new AbortController();
  const observer=new NativeObserver(hostPrivate), guard=new DispatchGuard(hostPrivate);
  const raw=JSON.parse(await readFile(new URL('./fixtures/codex/native-requests.json',import.meta.url),'utf8'))[0].body;
  raw.tools=[];raw.instructions='frozen policy';raw.input=[{type:'message',role:'user',content:[{type:'input_text',text:summaryProbeText('summary-only-fixture','frozen policy',{questions:[]})}]}];
  raw.client_metadata={thread_id:'fixture-probe',turn_id:'fixture-turn',root_turn_id:'fixture-turn'};
  const envelope:any=Object.fromEntries(Object.entries(raw).filter(([k])=>!['input','tools'].includes(k)));
  let appSession:string;
  const methods: string[] = [], scopes: any[] = [], cleanup: string[] = [];
  let home: string, workspace: string;
  const notify = (method: string, params: any) => stdout.write(JSON.stringify({ method, params }) + '\n');
  stdin.on('data', async bytes => {
    for (const line of bytes.toString('utf8').trim().split('\n')) {
      const request = JSON.parse(line); methods.push(request.method);
      if (request.method === 'initialized') continue;
      let result: any = {};
      if (request.method === 'initialize') {
        assert.equal(request.params.capabilities.experimentalApi, true);
        result = { codexHome: home, platformOs: 'linux', platformFamily: 'unix', userAgent: 'synthetic-protocol-fixture/0.158.0' };
      } else if (request.method === 'thread/start') {
        assert.deepEqual(request.params.environments, []);
        assert.equal(request.params.config['features.shell_tool'], false);
        result = { thread: { id: wrongThread ? 'fixture-parent' : 'fixture-probe' }, model: 'qwen3.8-27b', modelProvider: 'sova', cwd: workspace, approvalPolicy: 'never' };
      } else if (request.method === 'turn/start') {
        result = { turn: { id: 'fixture-turn' } };
        notify('turn/started', { threadId: 'fixture-probe', turn: { id: 'fixture-turn' } });
        guard.capture({sessionId:appSession,requestId:'source-request',model:raw.model,phase:'pre_normalization',bytes:Buffer.from(JSON.stringify(raw))} as any);
        try { await guard.wrap(async()=>({inputTokens:7,contextWindow:480000}))({...translateResponses(raw).body,model:raw.model},{alias:raw.model} as any,'fixture-key',new AbortController().signal,{requestId:'source-request'} as any); } catch { stdout.end();return; }
        notify('thread/status/changed', { threadId: 'fixture-probe', status: { type: 'active' } });
        if (rerouted) notify('model/rerouted', { threadId: 'fixture-probe', fromModel: 'qwen3.8-27b', toModel: 'unreviewed' });
        if (!stall) {
          const item = { id: 'fixture-message', type: tool ? 'commandExecution' : 'agentMessage', text: invalidAnswer ? 'not json' : '{"answers":{}}', ...(commentary ? { phase: 'commentary' } : {}) };
          if (!premature) notify('item/started', { threadId: 'fixture-probe', turnId: 'fixture-turn', item });
          if (reordered) {
            const earlier = { ...item, id: 'second-started-first-completed', text: '{"wrongEarlier":true}' };
            notify('item/started', { threadId: 'fixture-probe', turnId: 'fixture-turn', item: earlier });
            notify('item/completed', { threadId: 'fixture-probe', turnId: 'fixture-turn', item: earlier });
          }
          notify('item/completed', { threadId: 'fixture-probe', turnId: 'fixture-turn', item });
          notify('turn/completed', { threadId: 'fixture-probe', turn: { id: 'fixture-turn', status: 'completed', itemsView: notLoaded ? 'notLoaded' : 'summary', items: [item], error: null } });
        }
      }
      stdout.write(JSON.stringify({ id: request.id, result }) + '\n');
      if(request.method==='turn/start'&&stall&&!ownedDeadline)setTimeout(()=>callerAbort.abort(),20);
    }
  });
  const host = { layout: { root, dataDir, hostPrivate }, expiresAt: Date.now() + (ownedDeadline ? 2000 : 120000), dispatchCutoffAt: Date.now() + (ownedDeadline ? 2000 : 120000), observer, launchHeld:()=>false, directProbes: new Map(), closing: false,
    host: { runtime: { gatewayUrl: 'http://10.0.2.2:8081/v1', modelPolicyVersion: 'sova-codex-0.158.0-qwen-text-v2',
      launchRootless: async (input: any) => { home = input.codexHome; workspace = input.workspace; appSession=input.sessionId;
        assert.deepEqual(await readdir(input.profileDir), []); assert.deepEqual(await readdir(input.workspace), []);
        return observer.wrap(input.sessionId, { stdin, stdout, exited: new Promise<void>(() => {}), terminateAndConfirm: async () => { cleanup.push('native');stdout.end(); return nativeGone; } }); } } },
    gateway: { issueToken: () => 'synthetic-source-token', revokeSession: () => { cleanup.push('revoke'); },
      confirmSettlement: async () => { cleanup.push('gateway'); return gatewaySettled; } },
    guard: Object.assign(guard,{register:(scope:any)=>{scopes.push(scope);DispatchGuard.prototype.register.call(guard,scope);},retire:()=>cleanup.push('retire')}) };
  const signal = callerAbort.signal;
  const text = summaryProbeText('summary-only-fixture', 'frozen policy', { questions: [] });
  const input = { parentNativeThreadId: 'fixture-parent', summary: 'summary-only-fixture', contextSha256: sha256('summary-only-fixture'),
    windowId:'source-window',compactedRecordSha256:sha256('record-fixture'),collectorSourceSha256:sha256('closure-fixture'),collectorManifestUtf8:'closure-fixture',frozenPolicy: 'frozen policy', request: { questions: [] }, actionId: 'fixture-action', runId: 'fixture-run', signal,
    manifest: { userText: text, instructions: 'frozen policy', input: raw.input, envelope, contextSha256: sha256('summary-only-fixture') } };
  return { host, input, methods, scopes, cleanup };
}
test('SYNTHETIC fresh probe uses exact protocol operations and records separate IDs/unknown runtime facts', async t => {
  const f = await fixture(t); const result: any = await summaryProbe(f.host as any, f.input);
  assert.deepEqual(f.methods, ['initialize', 'initialized', 'thread/start', 'turn/start']);
  assert.equal(result.nativeThreadId, 'fixture-probe'); assert.equal(result.nativeTurnId, 'fixture-turn');
  assert.equal(result.parentNativeThreadId, 'fixture-parent'); assert.equal(result.settlement.state, 'released');
  assert.equal(result.isolation.mountAttestation, null); assert.equal(result.isolation.networkDenied, null);
  assert.deepEqual(f.cleanup, ['revoke', 'native', 'gateway', 'retire']);
  assert.notEqual(f.scopes[0].sessionId, 'fixture-parent');
});
test('SYNTHETIC foreign identity, tools, unstarted items, cleanup failures and deadline stop without retry', async t => {
  for (const options of [{ wrongThread: true }, { tool: true }, { premature: true }, { nativeGone: false }, { gatewaySettled: false }, { stall: true }, { rerouted: true }, { notLoaded: true }, { commentary: true }]) {
    const f = await fixture(t, options); const result: any = await summaryProbe(f.host as any, f.input);
    assert.equal(result.outcome, 'failed'); assert.ok(result.failure); assert.equal(result.automaticReplay, false);
    assert.ok(f.cleanup.includes('native')); assert.ok(f.cleanup.includes('gateway'));
    assert.equal(f.methods.filter(m => m === 'turn/start').length, options.wrongThread ? 0 : 1);
    if (options.nativeGone === false || options.gatewaySettled === false) assert.equal(result.settlement.state, 'quarantined');
    if (options.stall) assert.equal(f.methods.filter(m => m === 'turn/interrupt').length, 1);
    assert.equal(f.host.directProbes.size, 0);
  }
});
test('SYNTHETIC terminal selection follows actual completion order', async t => {
  const f = await fixture(t, { reordered: true }); const result: any = await summaryProbe(f.host as any, f.input);
  assert.equal(result.outcome, 'completed'); assert.deepEqual(result.answer, { answers: {} });
});
test('SYNTHETIC adapter owns a total terminal deadline after ACK, even without controller timeout', async t => {
  const f = await fixture(t, { stall: true, ownedDeadline: true });
  const result: any = await summaryProbe(f.host as any, f.input);
  assert.equal(result.outcome, 'failed'); assert.ok(f.methods.includes('turn/interrupt'));
  assert.equal(f.host.directProbes.size, 0); assert.equal(result.settlement.state, 'released');
});
test('SYNTHETIC invalid answer JSON retains independently confirmed settlement', async t => {
  const f = await fixture(t, { invalidAnswer: true }); const result: any = await summaryProbe(f.host as any, f.input);
  assert.equal(result.outcome, 'failed'); assert.equal(result.failure, 'probe_answer_invalid_json');
  assert.equal(result.settlement.state, 'released'); assert.equal(result.nativeTurnId, 'fixture-turn');
});
test('SYNTHETIC host close racing mount preparation prevents token registration and native launch', async t => {
  const f = await fixture(t); const pending = summaryProbe(f.host as any, f.input);
  queueMicrotask(() => { f.host.closing = true; });
  await assert.rejects(pending, /closed/); assert.deepEqual(f.methods, []); assert.deepEqual(f.scopes, []);
});
