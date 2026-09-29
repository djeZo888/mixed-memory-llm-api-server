/** Host wiring regression: real production verifier and native counter over local fixtures. */
import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { composeCodexHost } from '../src/codex-host.js';
import { createProductionQwenVerifier, qwenPolicyReceipt } from '../src/codex-production.js';

test('host retains count bracket while two-lane admission keeps its full checks', async t => {
  const now = 1790690400000, receipt = qwenPolicyReceipt();
  const calls: string[] = [], diagnostics: any[] = [], received: any[] = [];
  let generation = 11, changeOnTokenize = false;
  const get = async (url: string) => {
    const node = url.endsWith('/node/status'), native = url.endsWith('/server_info');
    calls.push(node ? 'node' : native ? 'native' : 'control');
    const alias = url.endsWith('/glm') || new URL(url).port === '30002' ? 'qwen3.8-27b-gpu0' : 'qwen3.8-27b';
    const pin = receipt.lanes[alias];
    if (node) return {
      schema_version: 1, node_id: 'ai-vm', boot_id: '17ac5d50-a6a4-4df1-8f9e-7bfc3db5f125',
      state: 'ok', freshness: 'fresh', age_ms: 0, observed_at: new Date(now).toISOString(),
      services: Object.entries(receipt.lanes).map(([model, lane]) => ({
        service_id: lane.serviceId, state: 'ok', freshness: 'fresh', age_ms: 0,
        observed_at: new Date(now).toISOString(), generation, ready: true, hardware_latched: false,
        deployment_id: lane.deploymentId, model_alias: model, configured_context_tokens: 480000,
        required_gpu_uuids: [lane.gpuUuid],
      })),
    };
    if (native) return {
      status: 'ready', version: '0.5.19', served_model_name: alias, context_length: 480000,
      max_total_tokens: 480000, max_total_num_tokens: 480000, max_running_requests: 1,
      default_chat_template_kwargs: { enable_thinking: false }, tool_call_parser: 'qwen3_coder', reasoning_parser: 'qwen3',
    };
    return {
      schema_version: 2, slot: pin.controlSlot, selected: pin.deploymentId, observed_deployment: pin.deploymentId,
      desired: 'running', observed: 'ready', container_running: true, observation_available: true,
      storage_available: true, state_persisted: true, generation_current: true, generation,
      active_identity: 'a'.repeat(64), freshness: 'fresh', observed_at: now / 1000,
      mutation_busy: false, current_operation: null,
      endpoint: { base_url: pin.nativeBaseUrl, served_model: alias, authentication_required: true, ready: true },
    };
  };
  const server = createServer(async (req, res) => {
    assert.equal(req.url, '/v1/tokenize');
    const chunks: Buffer[] = [];
    for await (const chunk of req) chunks.push(chunk);
    received.push({ authorization: req.headers.authorization, body: JSON.parse(Buffer.concat(chunks).toString('utf8')) });
    calls.push('tokenize');
    if (changeOnTokenize) generation++;
    res.setHeader('content-type', 'application/json');
    res.end(JSON.stringify({ tokens: [1, 2, 3], count: 3, max_model_len: 480000 }));
  });
  await new Promise<void>(resolve => server.listen(0, '127.0.0.1', resolve));
  t.after(async () => { server.closeAllConnections(); await new Promise<void>(resolve => server.close(() => resolve())); });
  const verifyLane = createProductionQwenVerifier(receipt, { controlKey: 'fixture', inferenceKey: 'fixture' }, get, () => now);
  const host = composeCodexHost('/trusted/run-codex.sh', () => undefined, {
    protocolQualified: true, rootlessQualified: true, verifyLane, onAdmissionDiagnostic: event => diagnostics.push(event),
  });
  assert.deepEqual(await host.responses!.currentAliases(), ['qwen3.8-27b-gpu0', 'qwen3.8-27b']);
  assert.equal(calls.filter(v => v === 'control').length, 4);
  assert.equal(calls.filter(v => v === 'node').length, 4);
  assert.equal(calls.filter(v => v === 'native').length, 2);
  const alias = 'qwen3.8-27b-gpu0';
  const lane = { alias, url: `http://127.0.0.1:${(server.address() as any).port}/v1` };
  const body = { model: alias, reasoning_effort: 'none', messages: [{ role: 'user', content: 'fixture' }],
    tools: [{ type: 'function', function: { name: 'fixture', parameters: { type: 'object' } } }],
    temperature: 0.2, max_tokens: 65536, stream: true, stream_options: { include_usage: true } };
  const original = structuredClone(body);
  const count = () => host.responses!.countQwen(body, lane, 'fixture', new AbortController().signal);
  calls.length = 0;
  assert.deepEqual(await count(), { inputTokens: 3, contextWindow: 480000 });
  assert.deepEqual(calls, ['control', 'node', 'native', 'tokenize', 'native', 'control', 'node']);
  const { stream, stream_options, ...forwarded } = original;
  assert.deepEqual(received, [{ authorization: 'Bearer fixture', body: forwarded }]);
  assert.deepEqual(body, original);
  calls.length = 0;
  diagnostics.length = 0;
  changeOnTokenize = true;
  await assert.rejects(count(), (error: any) => error.reason === 'identity_changed');
  assert.deepEqual(calls, ['control', 'node', 'native', 'tokenize', 'native', 'control', 'node']);
  assert.equal(diagnostics.some(event => event.step === 'tokenize' && event.outcome === 'pass'), false);
  assert.equal(diagnostics.at(-1).reason, 'identity_changed');
});
