import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { spawn } from 'node:child_process';
import { createServer } from 'node:http';
import { once } from 'node:events';
import { createInterface } from 'node:readline';
import { mkdtempSync, mkdirSync, readFileSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { translateResponses, ResponsesStream } from '../src/codex-responses.js';

const pin = '788a818fbb9596869c7a487554507cb8bdca17584b8671112b23f9e225ba35c8';
const reasoning = 'Synthetic private reasoning fixture: preserve exactly Ω and a newline.\nSecond line.';
const provider = { model: 'mimo-v2.6-pro-rl', contextWindow: 950000, maxOutputTokens: 65536,
  autoCompactTokenLimit: 880000, reasoning: 'mimo-plaintext', parallelToolCalls: false,
  tokenizer: 'mimo-native-input-tokens' } as const;
const bodyFixture = () => {
  const body = JSON.parse(readFileSync(new URL('./fixtures/codex/native-mcp-namespaces.json', import.meta.url), 'utf8'));
  body.model = provider.model; body.parallel_tool_calls = false;
  return body;
};

test('explicit serial MiMo emits one call and retains plaintext reasoning with historical multicall identities', () => {
  const body = bodyFixture(); const translation = translateResponses(body, 65536, provider);
  const frames: string[] = []; const stream = new ResponsesStream(translation, frame => frames.push(frame));
  for (const chunk of [
    { choices: [{ delta: { reasoning_content: reasoning.slice(0, 23) }, finish_reason: null }] },
    { choices: [{ delta: { reasoning_content: reasoning.slice(23) }, finish_reason: null }] },
    { choices: [{ delta: { tool_calls: [0].map(index => ({ index, id: `mimo_fixture_call_${index}`, type: 'function',
      function: { name: 'sova_ns_mcp__image_image_capabilities', arguments: '{}' } })) }, finish_reason: null }] },
    { choices: [{ delta: {}, finish_reason: 'tool_calls' }] },
    { choices: [], usage: { prompt_tokens: 10, completion_tokens: 5, total_tokens: 15 } },
  ]) stream.push(Buffer.from(`data: ${JSON.stringify(chunk)}\n\n`));
  stream.push(Buffer.from('data: [DONE]\n\n')); stream.end();
  const events = frames.map(frame => JSON.parse(frame.split('\ndata: ')[1]!));
  const items = events.filter(event => event.type === 'response.output_item.done').map(event => event.item);
  const reasoningItem = items.find(item => item.type === 'reasoning');
  assert.ok(reasoningItem);
  assert.deepEqual(reasoningItem.summary, []);
  assert.deepEqual(reasoningItem.content, [{ type: 'reasoning_text', text: reasoning }]);
  assert.equal(reasoningItem.encrypted_content, null);
  const calls = items.filter(item => item.type === 'function_call');
  assert.deepEqual(calls.map(call => call.call_id), ['mimo_fixture_call_0']);
  // Older stored multicall history must remain intact even though new MiMo emission is serial.
  const historicalCalls = [calls[0], { ...calls[0], id: 'fc_mimo_historical_1', call_id: 'mimo_fixture_call_1' }];
  const next = structuredClone(body);
  next.input.push(reasoningItem, ...historicalCalls, ...historicalCalls.map((call, index) => ({ type: 'function_call_output', call_id: call.call_id, output: `distinct result ${index}` })));
  const messages = translateResponses(next, 65536, provider).body.messages;
  const assistant = messages.find((message: any) => message.tool_calls?.[0]?.id === calls[0].call_id);
  assert.equal(assistant.reasoning_content, reasoning);
  assert.deepEqual(assistant.tool_calls.map((call: any) => call.id), historicalCalls.map(call => call.call_id));
  assert.deepEqual(messages.filter((message: any) => message.role === 'tool').map((message: any) => [message.tool_call_id, message.content]),
    [['mimo_fixture_call_0', 'distinct result 0'], ['mimo_fixture_call_1', 'distinct result 1']]);
  const nativeConflict = structuredClone(body); nativeConflict.parallel_tool_calls = true;
  const adapted = translateResponses(nativeConflict, 65536, provider);
  assert.deepEqual(adapted.toolPolicy, { requestedParallelToolCalls: true, effectiveParallelToolCalls: false });
  assert.equal(adapted.body.parallel_tool_calls, false);
});

test('serial MiMo rejects a provider attempting to emit tool index one', () => {
  const stream = new ResponsesStream(translateResponses(bodyFixture(), 65536, provider), () => {});
  assert.throws(() => stream.push(Buffer.from(`data: ${JSON.stringify({ choices: [{ delta: { tool_calls: [
    { index: 1, id: 'disallowed_second_call', type: 'function', function: { name: 'sova_ns_mcp__image_image_capabilities', arguments: '{}' } },
  ] }, finish_reason: null }] })}\n\n`)), /Invalid tool index\/type/);
});

// Root-reviewed serial adaptation is explicit in toolPolicy. Actual native input remains
// true and is captured unchanged; only the trusted provider's outbound policy becomes false.
test('pinned native MiMo roundtrips reasoning and one tool through the adapter with explicit serial policy', {
  skip: !process.env.CODEX_NATIVE_FIXTURE_BINARY, timeout: 60000,
}, async () => {
  const binary = resolve(process.env.CODEX_NATIVE_FIXTURE_BINARY!);
  assert.equal(createHash('sha256').update(readFileSync(binary)).digest('hex'), pin);
  const base = mkdtempSync(join(tmpdir(), 'sova-mimo-native-')); const home = join(base, 'codex'); const workspace = join(base, 'workspace');
  mkdirSync(home); mkdirSync(workspace);
  const requests: any[] = []; const translations: any[] = []; const emitted: any[] = []; const events: any[] = []; const errors: string[] = []; let stderr = ''; let nextId = 0;
  const server = createServer(async (request, response) => {
    try {
      assert.equal(request.url, '/v1/responses'); assert.equal(request.headers.authorization, 'Bearer fixture-local-only');
      const chunks: Buffer[] = []; for await (const chunk of request) chunks.push(Buffer.from(chunk));
      const body = JSON.parse(Buffer.concat(chunks).toString()); requests.push(body);
      assert.ok(requests.length <= 2, 'unexpected retry'); assert.equal(body.model, provider.model);
      const translation = translateResponses(body, 65536, provider);
      translations.push({ body: translation.body, toolPolicy: translation.toolPolicy });
      assert.equal(body.parallel_tool_calls, true);
      assert.deepEqual(translation.toolPolicy, { requestedParallelToolCalls: true, effectiveParallelToolCalls: false });
      assert.equal(translation.body.parallel_tool_calls, false);
      const providerChunks = requests.length === 1 ? [
        { choices: [{ delta: { reasoning_content: reasoning }, finish_reason: null }] },
        { choices: [{ delta: { tool_calls: [{ index: 0, id: 'mimo_native_call_0', type: 'function',
          function: { name: 'sova_ns_mcp__image_image_capabilities', arguments: '{"query":"capabilities"}' } }] }, finish_reason: null }] },
        { choices: [{ delta: {}, finish_reason: 'tool_calls' }] },
      ] : [
        { choices: [{ delta: { content: 'Native reasoning serialization fixture complete.' }, finish_reason: null }] },
        { choices: [{ delta: {}, finish_reason: 'stop' }] },
      ];
      response.writeHead(200, { 'Content-Type': 'text/event-stream' });
      const stream = new ResponsesStream(translation, frame => {
        emitted.push(JSON.parse(frame.split('\ndata: ')[1]!)); response.write(frame);
      });
      for (const chunk of providerChunks) stream.push(Buffer.from(`data: ${JSON.stringify(chunk)}\n\n`));
      stream.push(Buffer.from(`data: ${JSON.stringify({ choices: [], usage: { prompt_tokens: 10, completion_tokens: 5, total_tokens: 15 } })}\n\n`));
      stream.push(Buffer.from('data: [DONE]\n\n')); stream.end(); response.end();
    } catch (error) { errors.push(String(error)); response.writeHead(500); response.end('fixture error'); }
  });
  server.listen(0, '127.0.0.1'); await once(server, 'listening'); const address = server.address(); assert.ok(address && typeof address === 'object');
  const catalog = JSON.parse(readFileSync(new URL('../../deploy/codex/models.json', import.meta.url), 'utf8'));
  const model = structuredClone(catalog.models[0]); Object.assign(model, { slug: provider.model, display_name: 'MiMo native fixture',
    context_window: 950000, max_context_window: 950000, auto_compact_token_limit: 880000, use_responses_lite: false });
  writeFileSync(join(home, 'models.json'), JSON.stringify({ models: [model] }));
  const mcp = fileURLToPath(new URL('./fixtures/codex-image-native-mcp.mjs', import.meta.url));
  writeFileSync(join(home, 'config.toml'), `model = "${provider.model}"
model_provider = "sova"
model_catalog_json = ${JSON.stringify(join(home, 'models.json'))}
approval_policy = "never"
sandbox_mode = "danger-full-access"
web_search = "disabled"
check_for_update_on_startup = false
[analytics]
enabled = false
[feedback]
enabled = false
[features]
multi_agent = false
apps = false
plugins = false
standalone_web_search = false
[model_providers.sova]
name = "Sova offline fixture"
base_url = "http://127.0.0.1:${address.port}/v1"
wire_api = "responses"
env_key = "AI_HARNESS_GATEWAY_TOKEN"
requires_openai_auth = false
request_max_retries = 0
stream_max_retries = 0
supports_websockets = false
[mcp_servers.image]
command = ${JSON.stringify(process.execPath)}
args = ${JSON.stringify([mcp, join(base, 'mcp.jsonl')])}
enabled_tools = ["image_capabilities"]
startup_timeout_sec = 10
tool_timeout_sec = 10
`);
  const child = spawn(binary, ['app-server'], { cwd: workspace, env: { HOME: base, CODEX_HOME: home, TMPDIR: base,
    PATH: '/usr/bin:/bin', AI_HARNESS_GATEWAY_TOKEN: 'fixture-local-only', RUST_LOG: 'error' }, stdio: ['pipe', 'pipe', 'pipe'] });
  const exited = once(child, 'exit');
  const lines = createInterface({ input: child.stdout }); lines.on('line', line => { try { events.push(JSON.parse(line)); } catch { errors.push('non-JSON stdout'); } });
  child.stderr.on('data', chunk => { stderr += chunk.toString(); });
  async function waitFor(predicate: (event: any) => boolean) {
    const deadline = Date.now() + 12000;
    while (Date.now() < deadline) {
      const event = events.find(predicate); if (event) return event;
      if (errors.length) throw Error(errors.join('\n'));
      await new Promise(resolveWait => setTimeout(resolveWait, 20));
    }
    throw Error(`native fixture timeout: ${stderr.slice(-2000)}`);
  }
  async function rpc(method: string, params: any) {
    const id = ++nextId; child.stdin.write(JSON.stringify({ id, method, params }) + '\n');
    const event = await waitFor(event => event.id === id); assert.equal(event.error, undefined); return event.result;
  }
  let passed = false;
  try {
    await rpc('initialize', { clientInfo: { name: 'sova_mimo_fixture', version: '0.0.3' }, capabilities: { experimentalApi: false } });
    child.stdin.write(JSON.stringify({ method: 'initialized', params: {} }) + '\n');
    const thread = await rpc('thread/start', { model: provider.model, modelProvider: 'sova', cwd: workspace, approvalPolicy: 'never', sandbox: 'danger-full-access' });
    await rpc('turn/start', { threadId: thread.thread.id, input: [{ type: 'text', text: 'MIMO_REASONING_SERIALIZATION_FIXTURE', text_elements: [] }] });
    const completed = await waitFor(event => event.method === 'turn/completed'); assert.equal(completed.params.turn.status, 'completed');
    assert.equal(requests.length, 2); assert.ok(requests.every(body => body.parallel_tool_calls === true));
    const next = requests[1]; const item = next.input.find((item: any) => item.type === 'reasoning');
    const originalReasoning = emitted.find(event => event.type === 'response.output_item.done' && event.item.type === 'reasoning').item;
    assert.deepEqual(item, originalReasoning);
    assert.deepEqual(item.content, [{ type: 'reasoning_text', text: reasoning }]); assert.deepEqual(item.summary, []); assert.equal(item.encrypted_content, null);
    const calls = next.input.filter((item: any) => item.type === 'function_call');
    const results = next.input.filter((item: any) => item.type === 'function_call_output');
    assert.deepEqual(calls.map((call: any) => call.call_id), ['mimo_native_call_0']);
    assert.deepEqual(results.map((result: any) => result.call_id).sort(), calls.map((call: any) => call.call_id).sort());
    assert.ok(calls.every((call: any) => call.namespace === 'mcp__image' && call.name === 'image_capabilities' && call.arguments === '{"query":"capabilities"}'));
    assert.ok(results.every((result: any) => JSON.stringify(result.output).includes('image_capabilities accepted explicit capabilities query')));
    const assistant = translations[1].body.messages.find((message: any) => message.tool_calls?.[0]?.id === 'mimo_native_call_0');
    assert.equal(assistant.reasoning_content, reasoning); assert.equal(assistant.tool_calls[0].function.arguments, '{"query":"capabilities"}');
    assert.equal(assistant.tool_calls[0].function.name, 'sova_ns_mcp__image_image_capabilities');
    const toolResult = translations[1].body.messages.find((message: any) => message.tool_call_id === 'mimo_native_call_0');
    assert.ok(toolResult); assert.match(toolResult.content, /image_capabilities accepted explicit capabilities query/);
    assert.deepEqual(errors, []); passed = true;
  } finally {
    child.kill('SIGTERM'); const killer = setTimeout(() => child.kill('SIGKILL'), 3000); await exited; clearTimeout(killer); lines.close();
    await new Promise<void>(resolveClose => server.close(() => resolveClose()));
    if (process.env.CODEX_NATIVE_FIXTURE_EVIDENCE_DIR) {
      const output = resolve(process.env.CODEX_NATIVE_FIXTURE_EVIDENCE_DIR); mkdirSync(output, { recursive: true });
      const clean = (value: any) => JSON.stringify(value, null, 2).replaceAll(base, '<fixture>') + '\n';
      writeFileSync(join(output, 'native-mimo-capture.json'), clean({ requests, translations, emitted, events, errors, stderr }));
      writeFileSync(join(output, 'native-mimo-result.json'), clean({ status: passed ? 'PASS' : 'FAIL', binarySha256: pin,
        providerRequests: requests.length, observedParallelToolCalls: requests.map(body => body.parallel_tool_calls),
        effectiveParallelToolCalls: translations.map(translation => translation.toolPolicy.effectiveParallelToolCalls),
        fixtureProcessExited: child.exitCode !== null || child.signalCode !== null,
        scope: 'Actual pinned native requests pass through Responses adapter and synthetic Chat reasoning/tool stream; native continuation returns through adapter. Explicit root-reviewed requested=true/effective=false serial policy. No live model, gateway admission/tokenizer or Linux qualification.' }));
    }
    rmSync(base, { recursive: true, force: true });
  }
});
