import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { readFileSync } from 'node:fs';
import { Store } from '../src/store.js';
import { GatewayOwnershipLedger } from '../src/gateway-ownership.js';
import { createGateway } from '../src/gateway.js';
import { DispatchGuard } from '../../acceptance/compaction/native-adapter/dispatch-guard.js';
import { sha256 } from '../../acceptance/compaction/native-adapter/projection.js';

const native = JSON.parse(readFileSync(new URL('./fixtures/codex/native-requests.json', import.meta.url), 'utf8'))[0].body;
const clean = () => ({ ...structuredClone(native), instructions: 'frozen source fixture policy',
  tools: [], input: [{ type: 'message', role: 'user', content: [{ type: 'input_text', text: 'summary fixture and questions' }] }],
  client_metadata: { thread_id: 'fresh-fixture', turn_id: 'probe-fixture', root_turn_id: 'probe-fixture' } });
async function fixture(t: any, { expire = false, brokenCapture = false, afterCount = false } = {}) {
  const directory = await mkdtemp(join(tmpdir(), 'h040-native-adapter-gateway-'));
  const store = new Store(join(directory, 'fixture.sqlite'));
  const seen: any[] = []; let counts = 0, clock = 0;
  const backend = createServer(async (req, res) => {
    const chunks = []; for await (const chunk of req) chunks.push(chunk);
    seen.push(JSON.parse(Buffer.concat(chunks).toString('utf8')));
    res.setHeader('content-type', 'text/event-stream');
    res.end('data: {"choices":[{"delta":{"content":"fixture"}}]}\n\ndata: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\ndata: {"choices":[],"usage":{"prompt_tokens":7,"completion_tokens":1}}\n\ndata: [DONE]\n\n');
  });
  await new Promise<void>(r => backend.listen(0, '127.0.0.1', r));
  const port = (backend.address() as any).port;
  const guard = new DispatchGuard(brokenCapture ? join(directory, 'absent') : directory, () => clock);
  const request = clean();
  guard.register({ sessionId: 'owned-source-fixture', actionId: 'action-source-fixture', runId: 'run-source-fixture',
    parentNativeThreadId: 'parent-fixture', mode: 'summary-only', expiresAt: 1000, signal: new AbortController().signal,
    identity: () => ({ nativeThreadId: 'fresh-fixture', nativeTurnId: 'probe-fixture' }),
    manifest: { envelope: Object.fromEntries(Object.entries(request).filter(([k]) => !['input', 'tools'].includes(k))), input: request.input, instructions: request.instructions, userText: 'summary fixture and questions', contextSha256: sha256('summary fixture') } });
  if (expire) clock = 1001;
  const gateway = createGateway({ upstreamKey: 'source-fixture-key', ownership: new GatewayOwnershipLedger(store.db).options(),
    upstreams: [{ alias: 'qwen3.8-27b-gpu0', url: `http://127.0.0.1:${port}/v1` }, { alias: 'qwen3.8-27b', url: `http://127.0.0.1:${port}/v1` }],
    responses: { enabled: true, countQwen: guard.wrap(async () => { counts++; if (afterCount) clock = 1001; return { inputTokens: 7, contextWindow: 480000 }; }) },
    diagnostics: { capture: guard.capture } });
  const url = await gateway.app.listen({ port: 0, host: '127.0.0.1' });
  const token = gateway.issueToken('owned-source-fixture', 'codex');
  t.after(async () => { backend.closeAllConnections(); await gateway.close(); await new Promise(r => backend.close(r)); store.close(); await rm(directory, { recursive: true, force: true }); });
  return { gateway, guard, directory, seen, counts: () => counts, request,
    send: (body = request, authorization = token) => fetch(url + '/v1/responses', { method: 'POST', headers: { authorization: `Bearer ${authorization}`, 'content-type': 'application/json' }, body: JSON.stringify(body) }) };
}
test('SYNTHETIC real gateway parser/count path captures both inputs and owns settlement independently', async t => {
  const f = await fixture(t);
  const response = await f.send(); assert.equal(response.status, 200); assert.match(await response.text(), /response.completed/);
  assert.equal(f.seen.length, 1); assert.equal(f.counts(), 1);
  const r = f.guard.receipt('owned-source-fixture');
  assert.equal(r.nativeThreadId, 'fresh-fixture'); assert.equal(r.nativeTurnId, 'probe-fixture');
  assert.equal(r.parentNativeThreadId, 'parent-fixture'); assert.deepEqual(r.actualTools, []);
  assert.equal(r.captureSha256, sha256(await readFile(join(f.directory, `${r.requestId}-pre.bin`))));
  assert.equal(r.normalizedSha256, sha256(await readFile(join(f.directory, `${r.requestId}-normalized.bin`))));
  assert.equal(await f.gateway.confirmSettlement({ sessionId: 'owned-source-fixture' }), true);
  const second = await f.send(); assert.notEqual(second.status, 200); assert.equal(f.seen.length, 1);
});
test('SYNTHETIC tools, old tool history, extra original input and foreign native IDs never dispatch', async t => {
  const mutations = [
    (r: any) => { r.tools = [{ type: 'function', name: 'exec_command', parameters: { type: 'object', properties: {} }, strict: false }]; },
    (r: any) => { r.input.push({ type: 'function_call', name: 'exec_command', call_id: 'old', arguments: '{}' }); },
    (r: any) => { r.input.push({ type: 'message', role: 'user', content: [{ type: 'input_text', text: 'ORIGINAL_SECRET' }] }); },
    (r: any) => { r.client_metadata.thread_id = 'parent-fixture'; },
    (r: any) => { r.client_metadata.turn_id = 'another-turn'; },
    (r: any) => { r.prompt_cache_key = 'UNAPPROVED_CONTEXT_LINK'; },
    (r: any) => { r.client_metadata.extra = 'UNAPPROVED_CARRIER'; },
    (r: any) => { r.instructions += ' unreviewed extra instructions'; },
  ];
  for (const mutate of mutations) {
    const f = await fixture(t); const body = structuredClone(f.request); mutate(body);
    const response = await f.send(body); assert.notEqual(response.status, 200);
    assert.equal(f.seen.length, 0); assert.equal(f.counts(), 0);
    assert.equal(await f.gateway.confirmSettlement({ sessionId: 'owned-source-fixture' }), true);
  }
});
test('SYNTHETIC expired scopes, swallowed capture errors and expiry after counter all reject', async t => {
  for (const options of [{ expire: true }, { brokenCapture: true }, { afterCount: true }]) {
    const f = await fixture(t, options); assert.notEqual((await f.send()).status, 200);
    assert.equal(f.seen.length, 0); assert.equal(f.counts(), options.afterCount ? 1 : 0);
    assert.equal(await f.gateway.confirmSettlement({ sessionId: 'owned-source-fixture' }), true);
  }
});
test('SYNTHETIC unregistered authenticated owners cannot bypass the temporary counter guard', async t => {
  const f = await fixture(t); const other = f.gateway.issueToken('unrelated-fixture', 'codex');
  assert.notEqual((await f.send(f.request, other)).status, 200);
  assert.equal(f.seen.length, 0); assert.equal(f.counts(), 0);
});

test('SYNTHETIC exact native metadata placeholders bind only observed IDs', async t => {
  const f = await fixture(t); const receipt = await f.send(); assert.equal(receipt.status, 200); await receipt.text();
  const capture = f.guard.receipt('owned-source-fixture');
  const raw = JSON.parse(capture.firstRequestUtf8);
  assert.equal(capture.captureSha256, sha256(capture.firstRequestUtf8));
  assert.deepEqual(JSON.parse(capture.normalizedRequestUtf8).tools, []);
  assert.equal(raw.instructions, f.request.instructions);
});
