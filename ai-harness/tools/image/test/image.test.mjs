// SPDX-License-Identifier: MIT
import test from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { InMemoryTransport } from '@modelcontextprotocol/sdk/inMemory.js';
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js';
import { createImageServer } from '../image-mcp.mjs';
import { configuredToken, createImageClient, editInput, generateInput, GATEWAY, LIMITS, publicCapabilities, publicJob } from '../image.mjs';

const token = 'fixture-session-bearer-only';
const requestId = 'fixture-request-id';
const entrypoint = fileURLToPath(new URL('../image-mcp.mjs', import.meta.url));
const record = (state, extra = {}) => ({
  id: 'image-job-1', sessionId: 'session-fixture', runId: 'run-fixture', requestId,
  operation: 'generation', state, model: 'Qwen-Image-2.1', prompt: 'A copper kettle',
  seed: 42, requestedSize: '1920x1080', references: [], createdAt: '2026-09-23T00:00:00.000Z',
  cancelRequested: false, ...extra,
});
const response = (data, status = 200, headers = {}) => new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json', ...headers } });
function fixture(steps, overrides = {}) {
  const calls = [], waits = []; let clock = 0;
  const client = createImageClient({ token, newRequestId: () => requestId,
    now: () => clock, sleep: async ms => { waits.push(ms); clock += ms; },
    fetchImpl: async (url, options) => {
      calls.push({ url, ...options, ...(options.body ? { data: JSON.parse(options.body) } : {}) });
      const step = steps.shift();
      if (step instanceof Error) throw step;
      if (typeof step === 'function') return step(url, options);
      assert.ok(step, 'unexpected network operation');
      return step;
    }, ...overrides });
  return { client, calls, waits, advance: ms => { clock += ms; } };
}

test('single POST and fixed session authorization, then bounded GET polling produces artifact metadata', async () => {
  const f = fixture([response({ job: record('queued', { queuePosition: 2, elapsedMs: 0 }) }, 202),
    response({ job: record('running', { elapsedMs: 1000 }) }),
    response({ job: record('completed', { artifactId: 'artifact-1', actualSize: '1920x1080', workspacePath: 'outputs/kettle.png', elapsedMs: 3000 }) })]);
  const observed = [];
  const result = await f.client.invoke('generation', { prompt: 'A copper kettle' }, { onProgress: job => observed.push([job.state, job.elapsedMs]) });
  assert.deepEqual(f.calls.map(c => [c.method, c.url]), [
    ['POST', `${GATEWAY}/image-jobs`], ['GET', `${GATEWAY}/image-jobs/image-job-1`], ['GET', `${GATEWAY}/image-jobs/image-job-1`],
  ]);
  assert.deepEqual(f.calls[0].data, { requestId, operation: 'generation', prompt: 'A copper kettle', size: '1920x1080' });
  for (const call of f.calls) { assert.equal(call.headers.Authorization, `Bearer ${token}`); assert.equal(call.redirect, 'error'); }
  assert.deepEqual(f.waits, [1000, 2000]);
  assert.deepEqual(observed, [['queued', 0], ['running', 1000]]);
  assert.equal(result.job.workspacePath, 'outputs/kettle.png');
  assert.equal(result.job.artifactId, 'artifact-1');
  assert.equal(result.job.seed, 42);
  assert.ok(!JSON.stringify(result).includes(token));
  assert.equal(result.job.prompt, undefined);
});

test('awaiting approval returns immediately with immutable source/target details and no polling', async () => {
  const adjustment = { sources: [{ fileId: 'upload-1', name: 'Original.png', width: 2200, height: 1500 }], targetSize: '1920x1080', reason: 'Aspect-preserving fit with padding is required.' };
  const f = fixture([response({ job: record('awaiting_approval', { operation: 'edit', references: adjustment.sources, adjustment }) }, 202)]);
  const result = await f.client.invoke('edit', { prompt: 'Change the kettle to blue', references: [{ fileId: 'upload-1' }] });
  assert.equal(f.calls.length, 1); assert.deepEqual(f.waits, []);
  assert.equal(f.calls[0].data.size, undefined, 'editing does not impose generation defaults');
  assert.deepEqual(result.job.adjustment, adjustment);
  assert.match(result.instruction, /user approval card/);
});

for (const [name, result] of [
  ['transport rejection', new Error(`fetch failed with ${token}`)],
  ['unparseable accepted response', new Response('{', { status: 202, headers: { 'Content-Type': 'application/json' } })],
  ['gateway 503', response({ error: { code: 'BACKEND_UNAVAILABLE', message: 'Backend unavailable' } }, 503)],
  ['unrelated accepted response', response({ job: record('queued', { requestId: 'someone-else' }) }, 202)],
  ['wrong operation response', response({ job: record('queued', { operation: 'edit' }) }, 202)],
]) test(`ambiguous ${name} is never replayed`, async () => {
  const f = fixture([result]);
  const value = await f.client.invoke('generation', { prompt: 'A copper kettle' });
  assert.equal(f.calls.length, 1); assert.equal(value.requestId, requestId);
  assert.equal(value.submissionUncertain, true); assert.match(value.instruction, /do not resubmit/);
  assert.ok(!JSON.stringify(value).includes(token));
});

test('known non-admission is also never retried; operation/ref-count/size errors remain useful', async () => {
  const f = fixture([response({ error: { code: 'EDIT_UNAVAILABLE', message: 'No qualified two-reference editing profile.', supportedSizes: ['1024x1024'] } }, 422)]);
  const value = await f.client.invoke('edit', { prompt: 'Combine these', size: '1920x1080', seed: 42, references: [{ fileId: 'upload-1' }, { workspacePath: 'references/second.png' }] });
  assert.equal(f.calls.length, 1); assert.equal(f.calls[0].data.operation, 'edit');
  assert.deepEqual(value.error.supportedSizes, ['1024x1024']);
  assert.equal(value.error.code, 'EDIT_UNAVAILABLE'); assert.equal(value.submissionUncertain, undefined);
});

test('transient GET failures retry only GET and keep the accepted identity', async () => {
  const f = fixture([response(record('queued'), 202), new Error('socket closed'),
    response({ error: { code: 'TEMPORARILY_UNAVAILABLE', message: 'Unavailable' } }, 503),
    response(record('completed', { artifactId: 'artifact-1', workspacePath: 'images/result.png', actualSize: '1920x1080' }))]);
  const result = await f.client.invoke('generation', { prompt: 'A kettle' });
  assert.equal(result.job.state, 'completed');
  assert.deepEqual(f.calls.map(call => call.method), ['POST', 'GET', 'GET', 'GET']);
});

test('50 minute total budget stops observation without cancelling or resubmitting the accepted job', async () => {
  let f;
  f = fixture([response(record('running'), 202)], { sleep: async ms => { assert.ok(ms <= 15_000); f.advance(LIMITS.budgetMs); } });
  const result = await f.client.invoke('generation', { prompt: 'A kettle' });
  assert.equal(result.observationStopped, true); assert.equal(result.job.state, 'running');
  assert.equal(f.calls.length, 1); assert.match(result.instruction, /survives/);
});

test('slow progress transport cannot keep an image invocation open', { timeout: 1000 }, async () => {
  const f = fixture([response(record('running', { elapsedMs: 1 }), 202), response(record('completed', { artifactId: 'artifact-1', actualSize: '1920x1080', workspacePath: 'images/result.png' }))]);
  const result = await f.client.invoke('generation', { prompt: 'A kettle' }, { onProgress: () => new Promise(() => {}) });
  assert.equal(result.job.state, 'completed'); assert.equal(f.calls.length, 2);
});

test('job polling ends safely on loss of access while preserving last observed state', async () => {
  const f = fixture([response(record('queued'), 202), response({ error: { code: 'SESSION_EXPIRED', message: 'This session authorization expired.' } }, 401)]);
  const result = await f.client.invoke('generation', { prompt: 'A kettle' });
  assert.equal(result.observationStopped, true); assert.equal(result.job.state, 'queued');
  assert.equal(result.error.code, 'SESSION_EXPIRED'); assert.equal(f.calls.length, 2);
});

test('separate invocations receive distinct stable submission IDs', async () => {
  const ids = [];
  const client = createImageClient({ token, fetchImpl: async (_url, options) => {
    const body = JSON.parse(options.body); ids.push(body.requestId);
    return response(record('awaiting_approval', { requestId: body.requestId }), 202);
  } });
  await client.invoke('generation', { prompt: 'First image' });
  await client.invoke('generation', { prompt: 'Second image' });
  assert.equal(ids.length, 2); assert.notEqual(ids[0], ids[1]);
});

test('tool cancellation/disconnection only stops observation; an active cancellation retains real running state', async () => {
  const abort = new AbortController();
  const f = fixture([response(record('running', { cancelRequested: true }), 202)], { sleep: async () => { abort.abort(); } });
  const result = await f.client.invoke('generation', { prompt: 'A kettle' }, { signal: abort.signal });
  assert.equal(result.job.state, 'running'); assert.equal(result.job.cancelRequested, true);
  assert.equal(result.observationStopped, true); assert.equal(f.calls.length, 1);
  assert.match(result.instruction, /drains/);
});

test('a stopped turn before submission does not POST', async () => {
  const f = fixture([]);
  await assert.rejects(f.client.invoke('generation', { prompt: 'A kettle' }, { signal: AbortSignal.abort() }), { code: 'OBSERVATION_STOPPED' });
  assert.equal(f.calls.length, 0);
});

test('invalid references, unsupported settings and caller identity/approval are rejected before transport', async () => {
  const f = fixture([]);
  for (const input of [
    { prompt: '' }, { prompt: 'x', host: 'anything' }, { prompt: 'x', requestId: 'caller-id' },
    { prompt: 'x', sessionId: 'another' }, { prompt: 'x', runId: 'another' }, { prompt: 'x', approved: true },
    { prompt: 'x', url: GATEWAY }, { prompt: 'x', token }, { prompt: 'x', n: 2 }, { prompt: 'x', transparent: true },
    { prompt: 'x', seed: 1.2 }, { prompt: 'x', seed: Number.MAX_SAFE_INTEGER + 1 },
    ...['/tmp/x.png', '../x.png', 'dir/../x.png', './x.png', 'C:\\x.png', 'https://example.com/x.png', 'data:image/png;base64,abc', 'dir/%2e%2e/x.png', 'a//b.png', 'a\u0000b.png'].map(workspacePath => ({ prompt: 'x', references: [{ workspacePath }] })),
    { prompt: 'x', references: [{ fileId: 'owned', workspacePath: 'x.png' }] },
    { prompt: 'x', references: [{ fileId: '../other' }] },
  ]) await assert.rejects(f.client.invoke('generation', input), { code: 'INVALID_INPUT' });
  assert.equal(f.calls.length, 0);
  assert.ok(!editInput.safeParse({ prompt: 'x', references: [] }).success);
  assert.ok(generateInput.safeParse({ prompt: 'x', references: [{ workspacePath: 'uploads/teapot original.png' }] }).success);
});

test('response allowlist excludes secrets, bytes, URLs, absolute host paths and backend controls', () => {
  const result = publicJob(record('completed', {
    artifactId: 'artifact-1', workspacePath: '/data/private/image.png', base64: 'private-bytes', token, backend: { apiKey: token },
    references: [{ fileId: 'upload-1', name: '/data/private/original.png', path: '/data/private/original.png', base64: 'private-bytes', hash: 'a'.repeat(64) }],
    error: { code: 'SAVE_FAILED', message: `Failed ${token} Bearer secret123 at /data/private/x.png api_key=secret456 API key: spacedCredential at C:\\private\\x.png and \\\\private\\share data:image/png;base64,private-bytes diagnostic {"api_key":"upstream-secret-fixture","retry":"later"} retained explanation`, detail: { token } },
  }), token);
  const serialized = JSON.stringify(result);
  for (const forbidden of [token, 'secret123', 'secret456', 'spacedCredential', 'upstream-secret-fixture', 'private-bytes', '/data/private', 'C:', 'share', 'apiKey', 'base64']) assert.ok(!serialized.includes(forbidden), forbidden);
  assert.equal(result.workspacePath, undefined);
  assert.equal(result.references[0].name, 'original.png');
  assert.equal(result.error.code, 'SAVE_FAILED');
  assert.match(result.error.message, /"retry":"later"/);
  assert.match(result.error.message, /retained explanation/);
  assert.equal(result.references[0].hash, 'a'.repeat(64));
});

test('capabilities are discovered from API, preserve disabled edit and per-reference profiles, exclude unknown fields', async () => {
  const caps = { model: 'Qwen-Image-2.1', available: true, opaque: true, operations: {
    generation: { available: true, profiles: [{ referenceCount: 0, sizes: ['1920x1080', '1024x1024'] }] },
    edit: { available: false, reason: 'No accepted preservation profile.', profiles: [] },
  }, apiKey: token, backendUrl: 'http://private.invalid', base64: 'abc' };
  const f = fixture([response(caps)]);
  const result = await f.client.capabilities();
  assert.equal(f.calls[0].method, 'GET'); assert.equal(f.calls[0].url, `${GATEWAY}/image-capabilities`);
  assert.equal(result.capabilities.operations.edit.available, false);
  assert.deepEqual(result.capabilities.operations.generation.profiles[0], { referenceCount: 0, sizes: ['1920x1080', '1024x1024'] });
  assert.ok(!JSON.stringify(result).includes(token)); assert.equal(result.capabilities.backendUrl, undefined);
  assert.throws(() => publicCapabilities({ available: true }, token), { code: 'INVALID_CAPABILITIES' });
});

test('missing or malformed edit qualification keeps generation discoverable and disables edits', () => {
  const generation = { available: true, profiles: [{ referenceCount: 0, sizes: ['1920x1080'] }] };
  for (const edit of [undefined, { available: true }, { available: true, profiles: [] }, { available: true, profiles: [{ referenceCount: 1, sizes: ['auto'] }] }]) {
    const result = publicCapabilities({ operations: { generation, ...(edit ? { edit } : {}) } }, token);
    assert.deepEqual(result.operations.generation, generation);
    assert.deepEqual(result.operations.edit, { available: false, profiles: [] });
  }
  assert.throws(() => publicCapabilities({ operations: { unknown: generation } }, token), { code: 'INVALID_CAPABILITIES' });
  assert.equal(publicJob(record('running', { model: 'a'.repeat(120) }), token).model, undefined);
});

test('response body and UTF-8 validation are bounded; malformed success is uncertain and never retried', async () => {
  for (const res of [
    new Response('not json', { headers: { 'Content-Type': 'text/html' } }),
    new Response(Buffer.from([0xff]), { headers: { 'Content-Type': 'application/json' } }),
    response({}, 200, { 'Content-Length': String(LIMITS.bodyBytes + 1) }),
    new Response(' '.repeat(LIMITS.bodyBytes + 1), { headers: { 'Content-Type': 'application/json' } }),
  ]) {
    const f = fixture([res]);
    const result = await f.client.invoke('generation', { prompt: 'A kettle' });
    assert.equal(result.submissionUncertain, true); assert.equal(f.calls.length, 1);
  }
});

test('official SDK initialize/list/schema and actual tool call reject injected settings without transport', async () => {
  const f = fixture([response({ job: record('awaiting_approval', { adjustment: { sources: [], targetSize: '1024x1024', reason: 'Canvas change' } }) }, 202)]);
  const server = createImageServer(f.client);
  const client = new Client({ name: 'offline-image-fixture', version: '1' });
  const [left, right] = InMemoryTransport.createLinkedPair();
  await server.connect(right); await client.connect(left);
  try {
    const { tools } = await client.listTools();
    assert.deepEqual(tools.map(tool => tool.name), ['image_capabilities', 'image_generate', 'image_edit']);
    for (const tool of tools) assert.equal(tool.inputSchema.additionalProperties, false);
    for (const name of ['image_generate', 'image_edit']) {
      const bad = await client.callTool({ name, arguments: { prompt: 'x', approved: true, references: [{ fileId: 'upload-1' }] } });
      assert.equal(bad.isError, true);
    }
    assert.equal(f.calls.length, 0);
    const accepted = await client.callTool({ name: 'image_generate', arguments: { prompt: 'A kettle' } });
    assert.ok(!accepted.isError); assert.equal(JSON.parse(accepted.content[0].text).job.state, 'awaiting_approval');
    assert.equal(f.calls.length, 1);
  } finally { await client.close(); await server.close(); }
});

test('main and delegated-child MCP processes expose the same tools with only existing bearer environment', async () => {
  // Two real stdio processes model the same profile MCP launch inherited by main
  // and native children. Native engine roster acceptance is a separate live gate.
  for (const role of ['main', 'delegated-child']) {
    const transport = new StdioClientTransport({ command: process.execPath, args: [entrypoint], env: { AI_HARNESS_GATEWAY_URL: GATEWAY, AI_HARNESS_GATEWAY_TOKEN: token }, stderr: 'pipe' });
    let stderr = ''; transport.stderr.on('data', data => { stderr += data; });
    const client = new Client({ name: `offline-${role}`, version: '1' });
    try {
      await client.connect(transport); await client.ping();
      assert.equal(client.getServerVersion().name, 'ai-harness-image');
      assert.deepEqual((await client.listTools()).tools.map(tool => tool.name), ['image_capabilities', 'image_generate', 'image_edit']);
    } finally { await client.close(); }
    assert.equal(stderr, '');
  }
});

test('actual MCP cancellation notification ends polling without cancelling the stored job', { timeout: 2000 }, async () => {
  let submitted;
  const submission = new Promise(resolve => { submitted = resolve; });
  const abort = new AbortController();
  const f = fixture([() => { submitted(); return response(record('running'), 202); }], {
    sleep: async (_ms, signal) => { await new Promise(resolve => {
      if (signal.aborted) resolve(); else signal.addEventListener('abort', resolve, { once: true });
    }); },
  });
  const server = createImageServer(f.client);
  const client = new Client({ name: 'offline-cancellation-fixture', version: '1' });
  const [left, right] = InMemoryTransport.createLinkedPair();
  await server.connect(right); await client.connect(left);
  try {
    const call = client.callTool({ name: 'image_generate', arguments: { prompt: 'A kettle' } }, undefined, { signal: abort.signal });
    const rejected = assert.rejects(call);
    await submission; abort.abort(); await rejected;
    await client.ping();
    assert.deepEqual(f.calls.map(value => [value.method, value.url]), [['POST', `${GATEWAY}/image-jobs`]]);
  } finally { await client.close(); await server.close(); }
});

test('CLI help is offline and invalid environment fails safely without echoing token or paths', () => {
  const help = spawnSync(process.execPath, [entrypoint, '--help'], { env: {}, encoding: 'utf8' });
  assert.equal(help.status, 0); assert.match(help.stdout, /Usage:/);
  const bad = spawnSync(process.execPath, [entrypoint], { env: { AI_HARNESS_GATEWAY_TOKEN: token, AI_HARNESS_GATEWAY_URL: 'http://unapproved.invalid' }, encoding: 'utf8' });
  assert.equal(bad.status, 1); assert.equal(bad.stdout, ''); assert.ok(!bad.stderr.includes(token));
  for (const endpoint of ['http://10.0.2.2:8081/v1/', 'http://127.0.0.1:8081/v1', 'https://10.0.2.2:8081/v1']) assert.throws(() => configuredToken({ AI_HARNESS_GATEWAY_TOKEN: token, AI_HARNESS_GATEWAY_URL: endpoint }));
  assert.equal(configuredToken({ AI_HARNESS_GATEWAY_TOKEN: token }), token);
});
