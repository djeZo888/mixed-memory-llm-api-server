import test from 'node:test';
import assert from 'node:assert/strict';
import { PassThrough } from 'node:stream';
import { mkdtemp, mkdir, realpath, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { Store } from '../src/store.js';
import { Files } from '../src/files.js';
import { CODEX_PIN } from '../src/codex-engine.js';
import { NativeObserver } from '../../acceptance/compaction/native-adapter/native-observer.js';
import { openNativeParent } from '../../acceptance/compaction/native-adapter/parent.js';
// SYNTHETIC peer, real CodexEngine state transitions/Store and stdio observer.
async function fixture(t: any, opts: any = {}) {
  const root = await realpath(await mkdtemp(join(tmpdir(), 'h040-native-adapter-lifecycle-'))), captures = join(root, 'captures'), privateDir = join(root, 'private');
  await mkdir(captures, { mode: 0o700 }); await mkdir(privateDir, { mode: 0o700 });
  const store = new Store(join(root, 'store.sqlite')), files = new Files(join(root, 'app'), store); await files.init();
  const s = store.createSession(undefined, 'codex', { engineVersion: CODEX_PIN.version, modelPolicyVersion: 'synthetic-policy' }), observer = new NativeObserver(captures);
  let release!: () => void, started!: () => void, home: string, workspace: string, finishedCleanup = false;
  const pendingInitialize = new Promise<void>(resolve => { started = resolve; });
  const stdin = new PassThrough(), stdout = new PassThrough();
  const methods: string[] = [];
  stdin.on('data', bytes => {
    for (const line of bytes.toString().trim().split('\n')) {
      const r = JSON.parse(line); methods.push(r.method); if (r.method === 'initialized') continue;
      const answer = () => stdout.write(JSON.stringify({ id: r.id, result: r.method === 'initialize'
        ? { codexHome: home, platformOs: 'linux', platformFamily: 'unix', userAgent: 'SYNTHETIC/0.158.0' }
        : { thread: { id: 'synthetic-native-parent' }, model: 'qwen3.8-27b', modelProvider: 'sova', cwd: workspace, approvalPolicy: 'never' } }) + '\n');
      if (r.method === 'initialize') {
        assert.equal(r.params.capabilities.experimentalApi, false); release = answer; started(); if (!opts.pause) answer();
      } else answer();
    }
  });
  const h: any = { application: { store, files }, layout: { hostPrivate: privateDir }, launcherPath: '/reviewed/source-only/run-codex.sh', closing: false, expiresAt: Date.now() + 10000, launchHeld: () => h.closing || !!opts.held, observer, directProbes: new Map(),
    gateway: { issueToken: () => 'synthetic', revokeSession: () => {}, revokeToken: () => {} }, host: { runtime: { pin: CODEX_PIN, protocolQualified: true, modelPolicyVersion: 'synthetic-policy', model: 'qwen3.8-27b', provider: 'sova', contextLimit: 480000, gatewayUrl: 'http://10.0.2.2:8081/v1', requestTimeoutMs: 500,
      launchRootless: async (p: any) => { home = p.codexHome; workspace = p.workspace; return observer.wrap(s.id, { stdin, stdout, exited: new Promise(() => {}), terminateAndConfirm: async () => { stdout.end(); finishedCleanup = true; return true; } }); },
      revokeGatewaySession: () => {}, confirmGatewaySettlement: async (q: any) => { observer.gateway(s.id, q.nativeThreadId, q.activeTurnId, true); return true; } } } };
  if (opts.receiptFailure) h.layout.hostPrivate = join(root, 'missing-directory');
  t.after(async () => { store.close(); await rm(root, { recursive: true, force: true }); });
  return { h, s, methods, pendingInitialize, release: () => release(), cleanupDone: () => finishedCleanup };
}
test('SYNTHETIC open exposes actual thread/start native ID before returning, without an inference turn', async t => {
  const f = await fixture(t), result = await openNativeParent(f.h, f.s.id, new AbortController().signal);
  assert.equal(result.nativeThreadId, 'synthetic-native-parent'); assert.deepEqual(f.methods, ['initialize', 'initialized', 'thread/start']); assert.equal(f.h.directProbes.size, 0); assert.equal(f.cleanupDone(), true);
});
test('SYNTHETIC close during pending initialization awaits actual cleanup before Store release', async t => {
  const f = await fixture(t, { pause: true }), operation = openNativeParent(f.h, f.s.id, new AbortController().signal); void operation.catch(() => {});
  await f.pendingInitialize; assert.equal(f.h.directProbes.size, 1);
  f.h.closing = true; const handles: any[] = [...f.h.directProbes.values()]; for (const handle of handles) handle.abort();
  let closed = false; const closing = Promise.all(handles.map(h => h.finished)).then(() => { closed = true; });
  await new Promise(r => setImmediate(r)); assert.equal(closed, false); assert.equal(f.cleanupDone(), false);
  f.release(); await assert.rejects(operation, /initialization_or_settlement/); await closing;
  assert.equal(f.cleanupDone(), true); assert.equal(f.h.directProbes.size, 0);
});
test('SYNTHETIC initialization receipt failure finishes handle and preserves uncertainty', async t => {
  const f = await fixture(t, { receiptFailure: true }); await assert.rejects(openNativeParent(f.h, f.s.id, new AbortController().signal), /unqualified/);
  assert.equal(f.h.directProbes.size, 0); assert.equal(f.cleanupDone(), true); assert.equal(f.h.application.store.getSession(f.s.id).nativeState.ownership, 'uncertain');
});
test('SYNTHETIC shared launch hold prevents direct parent engine creation', async t => {
  const f = await fixture(t, { held: true }); await assert.rejects(openNativeParent(f.h, f.s.id, new AbortController().signal), /held/); assert.deepEqual(f.methods, []);
});
test('SYNTHETIC concurrent close callers await the same cleanup promise', async () => {
  const { ownedClose } = await import('../../acceptance/compaction/native-adapter/owned-close.js');
  let release!: () => void, actualCleanup = false, calls = 0;
  const gate = new Promise<void>(r => { release = r; });
  const close = ownedClose(async () => { calls++; await gate; actualCleanup = true; });
  const first = close(), second = close(); assert.equal(first, second); assert.equal(calls, 1);
  let observed = false; void second.then(() => { observed = true; }); await new Promise(r => setImmediate(r)); assert.equal(observed, false);
  release(); await Promise.all([first, second]); assert.equal(actualCleanup, true);
});
test('SYNTHETIC diagnostic disk failure after actual loopback bind cannot skip resource teardown', async () => {
  const { createServer } = await import('node:http');
  const { failedBootstrap, ownedClose } = await import('../../acceptance/compaction/native-adapter/owned-close.js');
  const gateway = createServer(); await new Promise<void>(r => gateway.listen(0, '127.0.0.1', r));
  let closed = false; const close = ownedClose(async () => { await new Promise<void>((resolve, reject) => gateway.close(e => e ? reject(e) : resolve())); closed = true; });
  const bindError = Object.assign(Error('synthetic frontend already occupied'), { code: 'EADDRINUSE' });
  await assert.rejects(failedBootstrap(bindError, async () => { await mkdir('/dev/null/h040-native-adapter-impossible-capture'); }, close), AggregateError);
  assert.equal(closed, true); assert.equal(gateway.listening, false);
});
