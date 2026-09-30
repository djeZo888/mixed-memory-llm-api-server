#!/usr/bin/env node
// Execute the patched native projection functions without installing engine dependencies.
// Usage: node test-compaction.mjs /absolute/path/to/pristine/pinned/source
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { readFileSync, mkdtempSync, mkdirSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { stripTypeScriptTypes } from 'node:module';
import { after, test } from 'node:test';

const source = resolve(process.argv[2] ?? process.env.MINIMAX_SOURCE_DIR ?? '/tmp/h001-minimax-source');
const patch = resolve(dirname(fileURLToPath(import.meta.url)), '../patches/0002-acp-compaction-notifications.patch');
const temp = mkdtempSync(join(tmpdir(), 'h001-compaction-check-'));
after(() => rmSync(temp, { recursive: true, force: true }));
const identities = {
  'packages/tui/src/acp/agent.ts': 'f52c7031a0f22663c79cf33819e5df8f7b56c1352c2f087eb4c3d798c9728b79',
  'packages/tui/src/acp/extensions.ts': '85ffe239d726d88106f15ce85835a6af810850954cf4a9eda54c61246c9f379a',
};
for (const [name, hash] of Object.entries(identities)) {
  const raw = readFileSync(join(source, name));
  assert.equal(createHash('sha256').update(raw).digest('hex'), hash, `Pinned original ${name}`);
  mkdirSync(dirname(join(temp, name)), { recursive: true });
  writeFileSync(join(temp, name), raw);
}
execFileSync('git', ['apply', '--check', patch], { cwd: temp });
execFileSync('git', ['apply', patch], { cwd: temp });
const read = (name, patched = false) => readFileSync(join(patched ? temp : source, `packages/tui/src/${name}`), 'utf8');
const agent = read('acp/agent.ts', true);
const extensions = read('acp/extensions.ts', true);
const interactions = read('acp/interactions.ts');
const control = read('acp/control-state.ts');
const delegation = read('runtime/delegation.ts');

// Extract complete unchanged/patched native functions; no copied implementation in fixtures.
function fn(text, name) {
  const match = new RegExp(`^(?:export )?(?:async )?function ${name}\\(`, 'm').exec(text);
  assert.ok(match, `Native function ${name} exists`);
  const next = /\n(?:export )?(?:async )?function /.exec(text.slice(match.index + match[0].length));
  return text.slice(match.index, next ? match.index + match[0].length + next.index : undefined).trim();
}
const pieces = [
  extensions.slice(extensions.indexOf('export const TUI_ACP_EXTENSION_VERSION'), extensions.indexOf('export interface RegisterTuiAcpExtensionsOptions')),
  fn(extensions, 'supportsTuiAcpExtensionNotifications'), fn(extensions, 'isRecord'),
  ...['createRuntimeControlProjections', 'notifyUsageUpdate', 'resolveAttachedRuntimeSession',
    'isCurrentAttachment', 'isSessionActivityEvent', 'shouldRefreshMode', 'isDelegationRefreshEvent']
    .map((name) => fn(agent, name)),
  fn(control, 'usageUpdate'),
  delegation.slice(delegation.indexOf('const WORKER_PURPOSE_PREFIXES'), delegation.indexOf('export function collectTuiDelegatedSessions')),
  interactions.slice(interactions.indexOf('const MAX_PENDING_PROJECTIONS'), interactions.indexOf('const MAX_PENDING_INTERACTIONS')),
  fn(interactions, 'createProjectionScheduler'),
].join('\n').replace(/^export /gm, '');
const js = stripTypeScriptTypes(pieces);
const native = new Function('acp', `${js}\nreturn {createRuntimeControlProjections,createProjectionScheduler,tuiAcpExtensionCapabilities,TUI_ACP_EXTENSION_VERSION};`)({
  methods: { client: { session: { update: 'session/update' } } },
});

const METHOD = 'mcode/session/compaction_update';
function fixture(capabilities = { _meta: { 'minimax-code/extensions': { version: 1, notifications: true } } }) {
  const sent = [];
  const active = { session: { sessionId: 'native-main' }, attachmentController: new AbortController() };
  const sessions = new Map([['acp-main', active]]);
  const runtime = {
    isGoalEnabled: () => false,
    getContextSnapshot: async () => ({ contextUsage: { usedTokens: 12345, contextWindowTokens: 480000 } }),
    getSessionUsage: async () => ({ summary: {} }),
  };
  const options = { runtime, client: { notify: async (method, data) => { sent.push({ method, data }); } },
    clientCapabilities: capabilities, sessions, activePlans: new Map(), planAttachments: new Map(),
    runtimeParentSessionIds: new Map([['native-child', 'native-main']]) };
  const event = (status, extra = {}) => ({ type: `session.compaction.${status}`, sessionId: 'native-main',
    compactionId: 'native-compaction', timestampMs: 1, ...extra });
  const project = (value) => native.createRuntimeControlProjections({ ...options, event: value });
  const run = async (value) => { for (const p of project(value)) await p.run(new AbortController().signal); };
  return { sent, active, sessions, runtime, event, project, run };
}
const compactions = (f) => f.sent.filter(({ method }) => method === METHOD).map(({ data }) => data);
const tick = () => new Promise((done) => setImmediate(done));

test('complete modified TypeScript files pass Node type-stripping syntax validation', () => {
  for (const text of [agent, extensions]) assert.doesNotThrow(() => stripTypeScriptTypes(text));
});

test('patch applies to exact original identities and advertises extension version 1', () => {
  assert.equal(native.TUI_ACP_EXTENSION_VERSION, 1);
  for (const enabled of [false, true]) {
    assert.ok(native.tuiAcpExtensionCapabilities({ isGoalEnabled: () => enabled }).notifications.includes(METHOD));
  }
});

test('native start/completed/failed map exactly and preserve native safe token counts', async () => {
  const f = fixture();
  for (const status of ['started', 'completed', 'failed']) {
    await f.run(f.event(status, { tokensBefore: 412416, tokensAfter: 12345 }));
  }
  assert.deepEqual(compactions(f), ['start', 'completed', 'failed'].map((status) => ({
    schemaVersion: 1, sessionId: 'acp-main', compactionId: 'native-compaction', status,
    estimated: true, tokensBefore: 412416, tokensAfter: 12345,
  })));
});

test('opt-in is required, including explicit version and notifications flag', async () => {
  for (const capabilities of [{}, { _meta: { 'minimax-code/extensions': { version: 2, notifications: true } } },
    { _meta: { 'minimax-code/extensions': { version: 1, notifications: false } } }]) {
    const f = fixture(capabilities);
    await f.run(f.event('started'));
    assert.deepEqual(compactions(f), []);
  }
  const enabled = fixture({ _meta: { 'minimax-code/extensions': true } });
  await enabled.run(enabled.event('started'));
  assert.equal(compactions(enabled).length, 1);
});

test('child/foreign/missing event session does not project onto the attached main session', async () => {
  for (const sessionId of ['native-child', 'foreign', undefined]) {
    const f = fixture();
    await f.run(f.event('started', { sessionId }));
    assert.deepEqual(compactions(f), []);
  }
  const attachedChild = fixture();
  attachedChild.active.session.sessionKind = 'task';
  await attachedChild.run(attachedChild.event('started'));
  assert.deepEqual(compactions(attachedChild), []);
});

test('no synthetic lifecycle event for unrelated native activity or invalid compaction ID', async () => {
  const f = fixture();
  for (const type of ['unrelated', 'session.queue.unchanged']) await f.run({ type, sessionId: 'native-main' });
  for (const compactionId of ['', null, undefined, 123]) await f.run(f.event('started', { compactionId }));
  assert.deepEqual(compactions(f), []);
});

test('only nonnegative safe integer native counts are forwarded; raw payload never escapes', async () => {
  for (const count of [undefined, null, '123', -1, 1.5, NaN, Infinity, Number.MAX_SAFE_INTEGER + 1]) {
    const f = fixture();
    await f.run(f.event('failed', { tokensBefore: count, tokensAfter: count,
      error: 'RAW_ERROR_SENTINEL', prompt: 'PROMPT_SENTINEL', stack: 'STACK_SENTINEL',
      history: ['HISTORY_SENTINEL'], token: 'TOKEN_SENTINEL', tokenUsage: { totalTokens: 500 } }));
    assert.deepEqual(Object.keys(compactions(f)[0]).sort(), ['schemaVersion', 'sessionId', 'compactionId', 'status', 'estimated'].sort());
    assert.ok(!JSON.stringify(compactions(f)).includes('SENTINEL'));
  }
  const f = fixture();
  await f.run(f.event('started', { tokensBefore: 0, tokensAfter: Number.MAX_SAFE_INTEGER }));
  assert.equal(compactions(f)[0].tokensBefore, 0);
  assert.equal(compactions(f)[0].tokensAfter, Number.MAX_SAFE_INTEGER);
});

test('retired, replaced, identity-changed, and cancelled projections never notify', async () => {
  for (const change of ['delete', 'replace', 'identity', 'retire', 'cancel']) {
    const f = fixture();
    const pending = f.project(f.event('started'));
    const controller = new AbortController();
    if (change === 'delete') f.sessions.clear();
    if (change === 'replace') f.sessions.set('acp-main', { ...f.active });
    if (change === 'identity') f.active.session = { sessionId: 'other-native' };
    if (change === 'retire') f.active.attachmentController.abort();
    if (change === 'cancel') controller.abort();
    for (const p of pending) await p.run(controller.signal);
    assert.deepEqual(compactions(f), [], change);
  }
});

test('transition keys retain exact session, compaction ID and status', () => {
  const f = fixture();
  const keys = ['started', 'completed', 'failed'].flatMap((s) => f.project(f.event(s)).map((p) => p.key)).filter((k) => k.includes('\0compaction\0'));
  assert.deepEqual(keys, ['start', 'completed', 'failed'].map((s) => `acp-main\0compaction\0native-compaction\0${s}`));
});

test('native scheduler preserves quick ordered transitions while all lanes are initially busy', async () => {
  const f = fixture();
  let release;
  const blocked = new Promise((resolve) => { release = resolve; });
  const closed = [];
  const scheduler = native.createProjectionScheduler({ close: (e) => closed.push(e) }, 5000);
  for (let i = 0; i < 8; i++) scheduler.enqueue({ key: `block-${i}`, run: () => blocked });
  await tick();
  for (const status of ['started', 'completed', 'failed']) {
    for (const p of f.project(f.event(status))) scheduler.enqueue(p);
  }
  release();
  await tick();
  await tick();
  scheduler.close();
  assert.deepEqual(closed, []);
  assert.deepEqual(compactions(f).map(({ status }) => status), ['start', 'completed', 'failed']);
});

test('completed preserves genuine usage_update independently of extension opt-in', async () => {
  for (const capability of [undefined, {}]) {
    const f = fixture(capability);
    await f.run(f.event('completed', { tokensAfter: 10 }));
    const usage = f.sent.filter(({ data }) => data.update?.sessionUpdate === 'usage_update');
    assert.deepEqual(usage, [{ method: 'session/update', data: { sessionId: 'acp-main',
      update: { sessionUpdate: 'usage_update', used: 12345, size: 480000 } } }]);
  }
});
