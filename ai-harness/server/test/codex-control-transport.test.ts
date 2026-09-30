import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { mkdtempSync, readFileSync, realpathSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { boundedControlGet, createProductionQwenVerifier, qwenPolicyReceipt } from '../src/codex-production.js';
import { QwenAdmissionError } from '../src/codex-admission.js';
import { createQwenAdmissionDiagnostics } from '../src/codex-diagnostics.js';

async function fixture(t: any) {
  const server = createServer((request, response) => {
    assert.equal(request.headers.authorization, 'Bearer PRIVATE_KEY');
    switch (request.url) {
      case '/known': response.writeHead(409); response.end(JSON.stringify({ error: { code: 'target_unavailable', message: 'PRIVATE_BODY' }, prompt: 'PRIVATE_PROMPT' })); break;
      case '/unknown': response.writeHead(503); response.end(JSON.stringify({ error: { code: 'PRIVATE_CODE' } })); break;
      case '/nonjson-http': response.writeHead(502); response.end('PRIVATE_BODY'); break;
      case '/json': response.end('PRIVATE_BODY'); break;
      case '/limit': response.end(Buffer.alloc(512 * 1024 + 1, 65)); break;
      case '/stream': response.writeHead(200, { 'content-length': '100' }); response.write('{'); setImmediate(() => response.destroy()); break;
      default: response.end(JSON.stringify({ schema_version: 2 }));
    }
  });
  await new Promise<void>(resolve => server.listen(0, '127.0.0.1', resolve));
  t.after(async () => { server.closeAllConnections(); await new Promise<void>(resolve => server.close(() => resolve())); });
  return `http://127.0.0.1:${(server.address() as any).port}`;
}
async function rejected(url: string, expected: any, signal?: AbortSignal) {
  await assert.rejects(boundedControlGet(url, 'PRIVATE_KEY', signal), error => {
    assert.ok(error instanceof QwenAdmissionError);
    assert.equal(error.reason, 'transport');
    assert.equal(error.statusCode, 503);
    assert.deepEqual(error.transport, expected);
    assert.doesNotMatch(JSON.stringify(error), /PRIVATE_KEY|PRIVATE_BODY|PRIVATE_PROMPT|PRIVATE_CODE/);
    return true;
  });
}
test('bounded getter distinguishes HTTP, JSON, size and truncated stream without retaining remote content', async t => {
  const url = await fixture(t);
  await rejected(url + '/known', { kind: 'http_status', httpStatus: 409, controlCode: 'target_unavailable' });
  await rejected(url + '/unknown', { kind: 'http_status', httpStatus: 503 });
  await rejected(url + '/nonjson-http', { kind: 'http_status', httpStatus: 502 });
  await rejected(url + '/json', { kind: 'invalid_json', httpStatus: 200 });
  await rejected(url + '/limit', { kind: 'response_limit', httpStatus: 200 });
  await rejected(url + '/stream', { kind: 'response_stream', httpStatus: 200 });
  assert.deepEqual(await boundedControlGet(url, 'PRIVATE_KEY'), { schema_version: 2 });
});
test('connection failure stays distinct from caller cancellation and unchanged 30000 ms deadline', async t => {
  const server = createServer();
  await new Promise<void>(resolve => server.listen(0, '127.0.0.1', resolve));
  const url = `http://127.0.0.1:${(server.address() as any).port}`;
  await new Promise<void>(resolve => server.close(() => resolve()));
  await rejected(url, { kind: 'connection' });
  await rejected(url, { kind: 'cancelled' }, AbortSignal.abort('PRIVATE_CANCEL_REASON'));
  t.mock.method(AbortSignal, 'timeout', (ms: number) => { assert.equal(ms, 30000); return AbortSignal.abort('PRIVATE_TIMEOUT_REASON'); });
  await rejected(url, { kind: 'timeout' });
});
test('exact count/control_before rejection retains subtype in protected correlated log and dispatches nothing else', async t => {
  const url = await fixture(t), dir = mkdtempSync(join(realpathSync(tmpdir()), 'h029-transport-'));
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  const path = join(dir, 'admission.jsonl'), calls: string[] = [];
  const verify = createProductionQwenVerifier(qwenPolicyReceipt(), { controlKey: 'PRIVATE_KEY', inferenceKey: 'PRIVATE_KEY' }, async (endpoint, key) => {
    calls.push(endpoint); return boundedControlGet(url + '/known', key);
  }, Date.now, createQwenAdmissionDiagnostics(path));
  const requestId = '75d651ef-86cd-4760-ad04-2867c28c6982';
  await assert.rejects(verify('qwen3.8-27b-gpu0', { requestId, phase: 'count' }), (e: any) => e.reason === 'transport');
  assert.deepEqual(calls, ['http://10.156.100.60:30000/control/v1/status/glm']);
  const text = readFileSync(path, 'utf8'), event = JSON.parse(text);
  assert.equal(event.requestId, requestId); assert.equal(event.phase, 'count'); assert.equal(event.step, 'control_before');
  assert.equal(event.reason, 'transport'); assert.equal(event.outcome, 'reject');
  assert.deepEqual(event.transport, { kind: 'http_status', httpStatus: 409, controlCode: 'target_unavailable' });
  assert.doesNotMatch(text, /PRIVATE_|error|prompt|authorization/);
});
test('logger independently projects transport allowlists and drops untrusted extra fields', t => {
  const dir = mkdtempSync(join(realpathSync(tmpdir()), 'h029-transport-log-'));
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  const path = join(dir, 'admission.jsonl'), log = createQwenAdmissionDiagnostics(path);
  const event = { schema: 1, requestId: '75d651ef-86cd-4760-ad04-2867c28c6982', lane: 'qwen3.8-27b-gpu0', phase: 'count', step: 'control_before', outcome: 'reject', reason: 'transport', elapsedMs: 9145 } as const;
  log({ ...event, transport: { kind: 'http_status', httpStatus: 409, controlCode: 'stale_state', body: 'PRIVATE_BODY' } } as any);
  log({ ...event, transport: { kind: 'connection', httpStatus: 'PRIVATE_STATUS', controlCode: 'PRIVATE_CODE', message: 'PRIVATE_MESSAGE' } } as any);
  log({ ...event, transport: { kind: 'PRIVATE_KIND' } } as any);
  log({ ...event, reason: 'freshness', transport: { kind: 'http_status', httpStatus: 409 } } as any);
  const text = readFileSync(path, 'utf8'), events = text.trim().split('\n').map(line => JSON.parse(line));
  assert.deepEqual(events.map(e => e.transport), [{ kind: 'http_status', httpStatus: 409, controlCode: 'stale_state' }, { kind: 'connection' }, undefined, undefined]);
  assert.doesNotMatch(text, /PRIVATE_/);
});
