import test from 'node:test';
import assert from 'node:assert/strict';
import { createImageClient, GATEWAY, statusInput } from '../image.mjs';

const token = 'fixture-session-bearer-only';
const jobId = 'existing-job-1';
const record = (state, extra = {}) => ({ id: jobId, revision: 1, operation: 'edit', state,
  requestId: 'original-request-1', runId: 'finished-parent-run', sessionId: 'private-session',
  prompt: 'private prompt', seed: 42, model: 'Qwen-Image-2.1', requestedSize: '1024x1024',
  references: [{ fileId: 'original-reference', sha256: 'a'.repeat(64), width: 1600, height: 900 }],
  cancelRequested: false, ...extra });
const response = (body, status = 200) => new Response(JSON.stringify(body), {
  status, headers: { 'Content-Type': 'application/json' },
});
function fixture() {
  const calls = [];
  let current = record('awaiting_approval');
  let nextError;
  const client = createImageClient({ token,
    newRequestId: () => { throw new Error('Status must not allocate request identity'); },
    sleep: async () => { throw new Error('Status must not wait or poll'); },
    fetchImpl: async (url, options) => {
      calls.push({ url, ...options });
      if (nextError) return nextError;
      return response({ job: current });
    },
  });
  return { client, calls, set: value => { current = value; }, fail: value => { nextError = value; } };
}

test('status strict input accepts only an existing job ID and rejects control/identity arguments before transport', async () => {
  const f = fixture();
  assert.deepEqual(statusInput.parse({ jobId }), { jobId });
  for (const input of [undefined, {}, { jobId: '' }, { jobId: '../foreign' }, { jobId: 'a/b' },
    { jobId: 'x?token=y' }, { jobId: 'x\ny' }, { jobId, sessionId: 'foreign-session' },
    { jobId, requestId: 'new-request' }, { jobId, prompt: 'new image' }, { jobId, approve: true },
    { jobId, cancel: true }, { jobId, url: 'http://elsewhere' }]) {
    await assert.rejects(f.client.status(input), { code: 'INVALID_INPUT' });
  }
  assert.equal(f.calls.length, 0);
});

test('one read observes approval then later terminal state using the original job and artifact, without submission or wait', async () => {
  const f = fixture();
  const pending = await f.client.status({ jobId });
  assert.equal(pending.job.state, 'awaiting_approval');
  assert.match(pending.instruction, /Native turn completion does not mean/);
  assert.equal(pending.imageMarkdown, undefined);
  f.set(record('completed', { revision: 6, artifactId: 'original-artifact-1', outputPath: 'image-existing-job-1.png', actualSize: '1024x1024' }));
  const done = await f.client.status({ jobId });
  const repeated = await f.client.status({ jobId });
  assert.deepEqual(repeated, done);
  assert.equal(done.job.id, pending.job.id);
  assert.equal(done.job.requestId, pending.job.requestId);
  assert.equal(done.job.runId, 'finished-parent-run');
  assert.equal(done.job.artifactId, 'original-artifact-1');
  assert.equal(done.imageMarkdown, '![Generated image](/api/files/original-artifact-1/preview)');
  assert.equal(done.job.downloadUrl, '/api/artifacts/original-artifact-1/download');
  assert.equal(done.job.references[0].fileId, 'original-reference');
  assert.equal(pending.job.state, 'awaiting_approval', 'old tool output remains an immutable snapshot');
  assert.equal(f.calls.length, 3);
  for (const call of f.calls) {
    assert.equal(call.method, 'GET');
    assert.equal(call.url, `${GATEWAY}/image-jobs/${jobId}`);
    assert.equal(call.body, undefined);
    assert.equal(call.headers.Authorization, `Bearer ${token}`);
  }
  assert.ok(!JSON.stringify(done).includes('private-session'));
  assert.ok(!JSON.stringify(done).includes('private prompt'));
});

test('status preserves every current state, cancellation drain and uncertain errors without fake completion', async () => {
  const f = fixture();
  for (const state of ['queued', 'running', 'saving', 'failed', 'cancelled', 'interrupted']) {
    f.set(record(state, { cancelRequested: true, artifactId: 'retained-while-draining',
      ...(state === 'failed' ? { error: { code: 'image_completion_unknown', message: 'Completion is unknown; request will not be replayed' } } : {}),
    }));
    const result = await f.client.status({ jobId });
    assert.equal(result.job.state, state);
    assert.equal(result.job.cancelRequested, true);
    assert.equal(result.imageMarkdown, undefined);
    if (state === 'failed') assert.equal(result.job.error.code, 'image_completion_unknown');
    assert.match(result.instruction, new RegExp(`original job state is ${state}`));
    assert.match(result.instruction, /do not busy-poll/);
  }
  f.set(record('failed', { artifactId: 'retained-artifact', error: { code: 'image_workspace_save_failed', message: 'Artifact retained; workspace copy failed' } }));
  const retained = await f.client.status({ jobId });
  assert.equal(retained.job.state, 'failed');
  assert.equal(retained.imageMarkdown, undefined);
  assert.equal(retained.job.artifactId, 'retained-artifact');
  assert.equal(retained.job.downloadUrl, '/api/artifacts/retained-artifact/download');
  assert.match(retained.instruction, /original job state is failed/);
});

test('foreign authorization failures and unrelated responses are never substituted, retried or submitted', async () => {
  for (const code of [401, 404]) {
    const f = fixture();
    f.fail(response({ error: { code: 'not_found', message: 'Image job not found' } }, code));
    await assert.rejects(f.client.status({ jobId }), { code: 'not_found' });
    assert.equal(f.calls.length, 1);
    assert.equal(f.calls[0].method, 'GET');
  }
  const f = fixture();
  f.set(record('completed', { id: 'unrelated-job', artifactId: 'foreign-artifact' }));
  await assert.rejects(f.client.status({ jobId }), { code: 'INVALID_JOB_RESPONSE' });
  assert.equal(f.calls.length, 1);
  const aborted = new AbortController(); aborted.abort();
  await assert.rejects(f.client.status({ jobId }, { signal: aborted.signal }), { code: 'OBSERVATION_STOPPED' });
  assert.equal(f.calls.length, 1);
});

test('actual MCP delivery exposes a read-only strict contract and preserves pending, saved, failed and cancelled results', async () => {
  const { Client } = await import('@modelcontextprotocol/sdk/client/index.js');
  const { InMemoryTransport } = await import('@modelcontextprotocol/sdk/inMemory.js');
  const { createImageServer } = await import('../image-mcp.mjs');
  const f = fixture();
  const server = createImageServer(f.client);
  const client = new Client({ name: 'offline-image-status-contract', version: '1' });
  const [left, right] = InMemoryTransport.createLinkedPair();
  await server.connect(right); await client.connect(left);
  try {
    const descriptor = (await client.listTools()).tools.find(tool => tool.name === 'image_status');
    assert.deepEqual(descriptor.inputSchema.required, ['jobId']);
    assert.equal(descriptor.inputSchema.additionalProperties, false);
    assert.deepEqual(descriptor.annotations, { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: false });
    const invalid = await client.callTool({ name: 'image_status', arguments: { jobId, approved: true } });
    assert.equal(invalid.isError, true);
    assert.equal(f.calls.length, 0);
    for (const state of ['awaiting_approval', 'completed', 'failed', 'cancelled', 'interrupted']) {
      f.set(record(state, state === 'completed' ? { artifactId: 'original-artifact-1' } : {}));
      const result = await client.callTool({ name: 'image_status', arguments: { jobId } });
      const parsed = JSON.parse(result.content[0].text);
      assert.equal(parsed.job.state, state);
      assert.equal(Boolean(result.isError), ['failed', 'interrupted'].includes(state));
      assert.equal(parsed.imageMarkdown, state === 'completed' ? '![Generated image](/api/files/original-artifact-1/preview)' : undefined);
    }
    assert.equal(f.calls.length, 5);
    assert.ok(f.calls.every(call => call.method === 'GET'));
  } finally { await client.close(); await server.close(); }
});
