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
  id: 'image-job-1', revision: 1, sessionId: 'session-fixture', runId: 'run-fixture', requestId,
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
    response({ job: record('running', { revision: 2, elapsedMs: 1000 }) }),
    response({ job: record('completed', { revision: 3, artifactId: 'artifact-1', actualSize: '1920x1080', outputPath: 'outputs/kettle.png', elapsedMs: 3000 }) })]);
  const observed = [];
  const result = await f.client.invoke('generation', { prompt: 'A copper kettle' }, { onProgress: job => observed.push([job.state, job.elapsedMs]) });
  assert.deepEqual(f.calls.map(c => [c.method, c.url]), [
    ['POST', `${GATEWAY}/image-jobs`], ['GET', `${GATEWAY}/image-jobs/image-job-1`], ['GET', `${GATEWAY}/image-jobs/image-job-1`],
  ]);
  assert.deepEqual(f.calls[0].data, { requestId, operation: 'generation', prompt: 'A copper kettle', size: '1920x1080' });
  for (const call of f.calls) { assert.equal(call.headers.Authorization, `Bearer ${token}`); assert.equal(call.redirect, 'error'); }
  assert.deepEqual(f.waits, [1000, 2000]);
  assert.deepEqual(observed, [['queued', 0], ['running', 1000]]);
  assert.equal(result.job.outputPath, 'outputs/kettle.png');
  assert.equal(result.job.artifactId, 'artifact-1');
  assert.equal(result.job.previewUrl, '/api/files/artifact-1/preview');
  assert.equal(result.job.downloadUrl, '/api/artifacts/artifact-1/download');
  assert.equal(result.imageMarkdown, '![Generated image](/api/files/artifact-1/preview)');
  assert.match(result.instruction, /relevant place in the final answer/);
  assert.match(result.instruction, /Do not regenerate to repair embedding/);
  assert.equal(result.job.seed, 42);
  assert.ok(!JSON.stringify(result).includes(token));
  assert.equal(result.job.prompt, undefined);
});

test('awaiting approval returns immediately with immutable source/target details and no polling', async () => {
  const adjustment = { sources: [{ referenceId: 'reference-1', fileId: 'upload-1', name: 'Original.png', sha256: 'a'.repeat(64), width: 2200, height: 1500, workingWidth: 1584, workingHeight: 1080, padding: { top: 0, right: 168, bottom: 0, left: 168 } }], targetSize: '1920x1080', reason: 'Aspect-preserving fit with padding is required.' };
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
  ['missing envelope', response(record('queued'), 202)],
  ['missing revision', response({ job: record('queued', { revision: undefined }) }, 202)],
]) test(`ambiguous ${name} is never replayed`, async () => {
  const f = fixture([result]);
  const value = await f.client.invoke('generation', { prompt: 'A copper kettle' });
  assert.equal(f.calls.length, 1); assert.equal(value.requestId, requestId);
  assert.equal(value.submissionUncertain, true); assert.match(value.instruction, /do not resubmit/);
  assert.ok(!JSON.stringify(value).includes(token));
});

test('known non-admission is also never retried; operation/ref-count/size errors remain useful', async () => {
  const f = fixture([response({ error: { code: 'EDIT_UNAVAILABLE', message: 'No qualified two-reference editing profile. Supported sizes: 1024x1024.' } }, 422)]);
  const value = await f.client.invoke('edit', { prompt: 'Combine these', size: '1920x1080', seed: 42, references: [{ fileId: 'upload-1' }, { workspacePath: 'references/second.png' }] });
  assert.equal(f.calls.length, 1); assert.equal(f.calls[0].data.operation, 'edit');
  assert.match(value.error.message, /Supported sizes: 1024x1024/);
  assert.equal(value.error.code, 'EDIT_UNAVAILABLE'); assert.equal(value.submissionUncertain, undefined);
});

test('explicit edit seed collision preserves seed42 and never resubmits', async () => {
  const error = { code: 'source_seed_collision', message: 'Seed 42 matches a source or ancestor generation seed. Choose a new seed or omit it.' };
  const f = fixture([response({ error }, 400)]);
  const value = await f.client.invoke('edit', { prompt: 'Make the kettle blue', seed: 42, references: [{ fileId: 'artifact-1' }] });
  assert.deepEqual(f.calls.map(call => [call.method, call.url]), [['POST', `${GATEWAY}/image-jobs`]]);
  assert.equal(f.calls[0].data.seed, 42);
  assert.deepEqual(value.error, { ...error, httpStatus: 400 });
  assert.equal(value.submissionUncertain, undefined);
  assert.deepEqual(f.waits, []);
});

test('transient GET failures retry only GET and keep the accepted identity', async () => {
  const f = fixture([response({ job: record('queued') }, 202), new Error('socket closed'),
    response({ error: { code: 'TEMPORARILY_UNAVAILABLE', message: 'Unavailable' } }, 503),
    response({ job: record('completed', { revision: 2, artifactId: 'artifact-1', outputPath: 'images/result.png', actualSize: '1920x1080' }) })]);
  const result = await f.client.invoke('generation', { prompt: 'A kettle' });
  assert.equal(result.job.state, 'completed');
  assert.deepEqual(f.calls.map(call => call.method), ['POST', 'GET', 'GET', 'GET']);
});

test('polling ignores stale revisions and accepts a newer running-to-queued non-admission update', async () => {
  const f = fixture([response({ job: record('running', { revision: 3, elapsedMs: 1000 }) }, 202),
    response({ job: record('completed', { revision: 2, artifactId: 'stale-artifact', outputPath: 'stale.png' }) }),
    response({ job: record('failed', { revision: 3 }) }),
    response({ job: record('queued', { revision: 4, queuePosition: 1, elapsedMs: 2000 }) }),
    response({ job: record('completed', { revision: 5, artifactId: 'artifact-1', actualSize: '1920x1080', outputPath: 'outputs/kettle.png' }) })]);
  const observed = [];
  const result = await f.client.invoke('generation', { prompt: 'A kettle' }, { onProgress: job => observed.push([job.state, job.revision]) });
  assert.deepEqual(observed, [['running', 3], ['running', 3], ['running', 3], ['queued', 4]]);
  assert.equal(result.job.revision, 5); assert.equal(result.job.artifactId, 'artifact-1');
  assert.equal(f.calls.filter(call => call.method === 'POST').length, 1);
});

test('50 minute total budget stops observation without cancelling or resubmitting the accepted job', async () => {
  let f;
  f = fixture([response({ job: record('running') }, 202)], { sleep: async ms => { assert.ok(ms <= 15_000); f.advance(LIMITS.budgetMs); } });
  const result = await f.client.invoke('generation', { prompt: 'A kettle' });
  assert.equal(result.observationStopped, true); assert.equal(result.job.state, 'running');
  assert.equal(f.calls.length, 1); assert.match(result.instruction, /survives/);
});

test('slow progress transport cannot keep an image invocation open', { timeout: 1000 }, async () => {
  const f = fixture([response({ job: record('running', { elapsedMs: 1 }) }, 202), response({ job: record('completed', { revision: 2, artifactId: 'artifact-1', actualSize: '1920x1080', outputPath: 'images/result.png' }) })]);
  const result = await f.client.invoke('generation', { prompt: 'A kettle' }, { onProgress: () => new Promise(() => {}) });
  assert.equal(result.job.state, 'completed'); assert.equal(f.calls.length, 2);
});

test('job polling ends safely on loss of access while preserving last observed state', async () => {
  const f = fixture([response({ job: record('queued') }, 202), response({ error: { code: 'SESSION_EXPIRED', message: 'This session authorization expired.' } }, 401)]);
  const result = await f.client.invoke('generation', { prompt: 'A kettle' });
  assert.equal(result.observationStopped, true); assert.equal(result.job.state, 'queued');
  assert.equal(result.error.code, 'SESSION_EXPIRED'); assert.equal(f.calls.length, 2);
});

test('separate invocations receive distinct stable submission IDs', async () => {
  const ids = [];
  const client = createImageClient({ token, fetchImpl: async (_url, options) => {
    const body = JSON.parse(options.body); ids.push(body.requestId);
    return response({ job: record('awaiting_approval', { requestId: body.requestId }) }, 202);
  } });
  await client.invoke('generation', { prompt: 'First image' });
  await client.invoke('generation', { prompt: 'Second image' });
  assert.equal(ids.length, 2); assert.notEqual(ids[0], ids[1]);
});

test('explicit related variants remain separate successful requests with their exact seeds and sizes', async () => {
  const calls = [];
  const client = createImageClient({ token, fetchImpl: async (_url, options) => {
    const body = JSON.parse(options.body); calls.push(body);
    return response({ job: record('completed', { requestId: body.requestId, artifactId: `variant-${calls.length}`,
      seed: body.seed, actualSize: body.size, outputPath: `images/variant-${calls.length}.png` }) });
  } });
  const first = await client.invoke('generation', { prompt: 'A kettle, first requested alternative', seed: 42, size: '1024x1024' });
  const second = await client.invoke('generation', { prompt: 'A kettle, second requested alternative', seed: 43, size: '1024x1024' });
  assert.equal(calls.length, 2);
  assert.notEqual(calls[0].requestId, calls[1].requestId);
  assert.deepEqual(calls.map(({ seed, size }) => [seed, size]), [[42, '1024x1024'], [43, '1024x1024']]);
  assert.equal(first.imageMarkdown, '![Generated image](/api/files/variant-1/preview)');
  assert.equal(second.imageMarkdown, '![Generated image](/api/files/variant-2/preview)');
});

test('a true failed output is reported without automatic retry and a deliberate retry remains possible', async () => {
  const bodies = [];
  const client = createImageClient({ token, fetchImpl: async (_url, options) => {
    const body = JSON.parse(options.body); bodies.push(body);
    return response({ job: record(bodies.length === 1 ? 'failed' : 'completed', { requestId: body.requestId,
      ...(bodies.length === 1 ? { error: { code: 'invalid_image_output', message: 'Invalid output dimensions' } }
        : { artifactId: 'retry-artifact', actualSize: body.size, outputPath: 'images/retry.png' }) }) });
  } });
  const input = { prompt: 'A kettle', seed: 42, size: '1024x1024' };
  const failed = await client.invoke('generation', input);
  assert.equal(bodies.length, 1);
  assert.equal(failed.job.error.code, 'invalid_image_output');
  assert.equal(failed.imageMarkdown, undefined);
  const retried = await client.invoke('generation', input);
  assert.equal(bodies.length, 2);
  assert.equal(retried.job.state, 'completed');
  assert.equal(bodies[1].seed, 42);
});

test('retained artifact on workspace-copy failure gets stable presentation links without hiding the error', async () => {
  const f = fixture([response({ job: record('failed', { artifactId: 'retained-1',
    error: { code: 'image_workspace_save_failed', message: 'Image artifact retained; workspace copy could not be saved' } }) })]);
  const result = await f.client.invoke('generation', { prompt: 'A kettle' });
  assert.equal(f.calls.length, 1);
  assert.equal(result.job.state, 'failed');
  assert.equal(result.job.error.code, 'image_workspace_save_failed');
  assert.equal(result.imageMarkdown, '![Generated image](/api/files/retained-1/preview)');
  assert.match(result.instruction, /disclose it/);
});

test('presentation links are derived only from safe retained IDs, ignoring supplied URLs and raw paths', () => {
  const owned = publicJob(record('completed', { artifactId: 'owned-1',
    previewUrl: 'https://untrusted.invalid/image.svg', downloadUrl: 'javascript:alert(1)',
    imageMarkdown: '<img src=x onerror=alert(1)>', outputPath: '/private/image.png' }), token);
  assert.equal(owned.previewUrl, '/api/files/owned-1/preview');
  assert.equal(owned.downloadUrl, '/api/artifacts/owned-1/download');
  assert.equal(owned.imageMarkdown, undefined);
  for (const artifactId of ['../other', 'path/image', 'bad%2fpath', 'a'.repeat(81), 'id.with.dots']) {
    const value = publicJob(record('completed', { artifactId }), token);
    assert.equal(value.previewUrl, undefined, artifactId);
    assert.equal(value.downloadUrl, undefined, artifactId);
  }
  for (const state of ['queued', 'running', 'cancelled', 'interrupted', 'awaiting_approval']) {
    assert.equal(publicJob(record(state, { artifactId: 'owned-1' }), token).previewUrl, undefined);
  }
});

test('tool cancellation/disconnection only stops observation; an active cancellation retains real running state', async () => {
  const abort = new AbortController();
  const f = fixture([response({ job: record('running', { cancelRequested: true }) }, 202)], { sleep: async () => { abort.abort(); } });
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
    { prompt: 'x', approvalToken: 'browser-token-fixture' },
    { prompt: 'x', url: GATEWAY }, { prompt: 'x', token }, { prompt: 'x', n: 2 }, { prompt: 'x', transparent: true },
    { prompt: 'x', seed: -1 }, { prompt: 'x', seed: 1.2 }, { prompt: 'x', seed: Number.MAX_SAFE_INTEGER + 1 },
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
    artifactId: 'artifact-1', outputPath: '/data/private/image.png', base64: 'private-bytes', token, approvalToken: 'browser-token-fixture', backend: { apiKey: token },
    references: [{ referenceId: 'reference-1', fileId: 'upload-1', name: '/data/private/original.png', width: 1920, height: 1080, path: '/data/private/original.png', base64: 'private-bytes', sha256: 'a'.repeat(64), approvalToken: 'browser-token-fixture' }],
    error: { code: 'SAVE_FAILED', message: `Failed ${token} Bearer secret123 at /data/private/x.png api_key=secret456 API key: spacedCredential at C:\\private\\x.png and \\\\private\\share data:image/png;base64,private-bytes diagnostic {"api_key":"upstream-secret-fixture","approvalToken":"browser-token-fixture","retry":"later"} retained explanation`, detail: { token } },
  }), token);
  const serialized = JSON.stringify(result);
  for (const forbidden of [token, 'secret123', 'secret456', 'spacedCredential', 'upstream-secret-fixture', 'browser-token-fixture', 'private-bytes', '/data/private', 'C:', 'share', 'apiKey', 'base64']) assert.ok(!serialized.includes(forbidden), forbidden);
  assert.equal(result.outputPath, undefined);
  assert.equal(result.references[0].name, 'original.png');
  assert.equal(result.error.code, 'SAVE_FAILED');
  assert.match(result.error.message, /"retry":"later"/);
  assert.match(result.error.message, /retained explanation/);
  assert.equal(result.references[0].sha256, 'a'.repeat(64));
});

test('capabilities retain exact upstream flat profiles and metadata without changing harness generation default', async () => {
  const caps = { ready: true, admitting: true, busy: false, state: 'ready', model: 'Qwen-Image-2.1', runtime_revision: 'reviewed-runtime', runtime_image_digest: `sha256:${'b'.repeat(64)}`, model_id: 'Qwen/Qwen-Image-2.1', model_revision: 'c'.repeat(40),
    profiles: [{ operation: 'generation', size: '1920x1080', references: 0, transparent: false, evidence_sha256: 'a'.repeat(64), native_size: '1920x1088', crop_bottom: 8 }],
    limits: { n: 1, max_width: 1920, max_height: 1080 }, defaults: { size: '1024x1024', n: 1 }, masks: false, response_format: ['b64_json'], output_format: 'png' };
  const f = fixture([response({ ...caps, apiKey: token, backendUrl: 'http://private.invalid', base64: 'abc' }), response({ job: record('awaiting_approval') }, 202)]);
  const result = await f.client.capabilities();
  assert.equal(f.calls[0].method, 'GET'); assert.equal(f.calls[0].url, `${GATEWAY}/image-capabilities`);
  assert.deepEqual(result, caps); assert.equal(result.profiles.some(profile => profile.operation === 'edit'), false);
  assert.ok(!JSON.stringify(result).includes(token)); assert.equal(result.backendUrl, undefined);
  await f.client.invoke('generation', { prompt: 'A kettle' });
  assert.equal(f.calls[1].data.size, '1920x1080');
  assert.throws(() => publicCapabilities({ available: true }, token), { code: 'INVALID_CAPABILITIES' });
});

test('missing or malformed edit qualification keeps generation discoverable and disables edits', () => {
  const generation = { operation: 'generation', size: '1920x1080', references: 0, transparent: false, evidence_sha256: 'a'.repeat(64) };
  for (const edit of [undefined, { operation: 'edit' }, { operation: 'edit', size: 'auto', references: 1, transparent: false }, { ...generation, operation: 'edit', references: 1, evidence_sha256: undefined }, { ...generation, operation: 'edit', references: 1, transparent: true }]) {
    const result = publicCapabilities({ profiles: [generation, ...(edit ? [edit] : [])] }, token);
    assert.deepEqual(result.profiles, [generation]);
  }
  assert.throws(() => publicCapabilities({ operations: { generation } }, token), { code: 'INVALID_CAPABILITIES' });
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
  const f = fixture([() => { submitted(); return response({ job: record('running') }, 202); }], {
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
