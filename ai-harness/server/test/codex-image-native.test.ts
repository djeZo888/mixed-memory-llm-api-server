import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { spawn } from 'node:child_process';
import { createServer } from 'node:http';
import { once } from 'node:events';
import { createInterface } from 'node:readline';
import { mkdtempSync, mkdirSync, readFileSync, writeFileSync, rmSync, existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { translateResponses, ResponsesStream } from '../src/codex-responses.js';

// Middle three strings are byte-exact argument values retained in ACCEPT06/REPAIR-ACCEPT09.
const cases = ['{}', '{"__v": "0"}', '{"__ns": "10"}', '{"ns": "10"}', '{"ns":10}'];
const alias = 'sova_ns_mcp__image_image_capabilities';
const pin = '788a818fbb9596869c7a487554507cb8bdca17584b8671112b23f9e225ba35c8';
const fixtureBody = () => JSON.parse(readFileSync(new URL('./fixtures/codex/native-mcp-namespaces.json', import.meta.url), 'utf8'));

function toolFrames(translation: ReturnType<typeof translateResponses>, arguments_: string, callId: string): string[] {
  const frames: string[] = [];
  const stream = new ResponsesStream(translation, frame => frames.push(frame));
  const chunks = [arguments_.slice(0, 2), arguments_.slice(2)];
  chunks.forEach((chunk, index) => stream.push(Buffer.from(`data: ${JSON.stringify({ choices: [{ delta: {
    tool_calls: [{ index: 0, ...(index ? {} : { id: callId, type: 'function' }),
      function: { ...(index ? {} : { name: alias }), arguments: chunk } }],
  }, finish_reason: null }] })}\n\n`)));
  stream.push(Buffer.from(`data: ${JSON.stringify({ choices: [{ delta: {}, finish_reason: 'tool_calls' }] })}\n\n`));
  stream.push(Buffer.from(`data: ${JSON.stringify({ choices: [], usage: { prompt_tokens: 12, completion_tokens: 4, total_tokens: 16 } })}\n\n`));
  stream.push(Buffer.from('data: [DONE]\n\n')); stream.end();
  return frames;
}
function parsedFrames(frames: string[]) { return frames.map(frame => JSON.parse(frame.split('\ndata: ')[1]!)); }

test('retained image __v and namespace argument shapes survive schema, stream and history without repair', () => {
  const body = fixtureBody(); const translated = translateResponses(body);
  const declaration = translated.body.tools.find((tool: any) => tool.function.name === alias).function;
  assert.deepEqual(declaration.parameters, { type: 'object', properties: {}, additionalProperties: false });
  assert.equal(declaration.strict, false);
  for (const [index, arguments_] of cases.entries()) {
    const callId = `fixture_image_${index}`;
    const events = parsedFrames(toolFrames(translated, arguments_, callId));
    const item = events.find(event => event.type === 'response.output_item.done').item;
    assert.equal(item.arguments, arguments_);
    assert.equal(item.call_id, callId);
    assert.equal(item.namespace, 'mcp__image'); assert.equal(item.name, 'image_capabilities');
    assert.equal(events.find(event => event.type === 'response.function_call_arguments.done').arguments, arguments_);
    const next = structuredClone(body);
    next.input.push(item, { type: 'function_call_output', call_id: callId, output: 'MCP error -32602: retained fixture error' });
    const messages = translateResponses(next).body.messages;
    assert.equal(messages.at(-2).tool_calls[0].function.arguments, arguments_);
    assert.equal(messages.at(-2).tool_calls[0].id, callId);
    assert.equal(messages.at(-1).tool_call_id, callId);
    assert.equal(messages.at(-1).content, 'MCP error -32602: retained fixture error');
  }
});

// Opt-in: run with the retained, hash-pinned Mac binary and cached image MCP dependencies.
// All model responses are local synthetic Chat chunks. No live model/gateway/image jobs.
test('pinned native forwards actual image argument shapes to strict MCP and preserves rejection continuation', {
  skip: !process.env.CODEX_NATIVE_FIXTURE_BINARY,
  timeout: 90000,
}, async () => {
  const binary = resolve(process.env.CODEX_NATIVE_FIXTURE_BINARY!);
  assert.equal(createHash('sha256').update(readFileSync(binary)).digest('hex'), pin, 'unreviewed native binary');
  const base = mkdtempSync(join(tmpdir(), 'sova-image-native-'));
  const home = join(base, 'codex'); const workspace = join(base, 'workspace');
  mkdirSync(home); mkdirSync(workspace);
  const capture = join(base, 'mcp.jsonl');
  const requests: any[] = []; const events: any[] = []; const emitted: any[] = []; const errors: string[] = [];
  let stderr = ''; let nextId = 0;
  const server = createServer(async (request, response) => {
    try {
      assert.equal(request.url, '/v1/responses');
      assert.equal(request.headers.authorization, 'Bearer fixture-local-only');
      const chunks: Buffer[] = []; for await (const chunk of request) chunks.push(Buffer.from(chunk));
      const body = JSON.parse(Buffer.concat(chunks).toString()); requests.push(body);
      assert.ok(requests.length <= cases.length * 2, 'unexpected native retry');
      const scenario = JSON.stringify(body.input).match(/IMAGE_CASE_(\d+)/)?.[1];
      assert.notEqual(scenario, undefined); const index = Number(scenario);
      const translated = translateResponses(body);
      const declaration = translated.body.tools.find((tool: any) => tool.function.name === alias).function;
      assert.deepEqual(declaration.parameters, { type: 'object', properties: {}, additionalProperties: false });
      const continuation = body.input.some((item: any) => item.type === 'function_call_output' && item.call_id === `fixture_image_${index}`);
      response.writeHead(200, { 'Content-Type': 'text/event-stream' });
      if (!continuation) {
        const frames = toolFrames(translated, cases[index]!, `fixture_image_${index}`);
        emitted.push(...parsedFrames(frames)); for (const frame of frames) response.write(frame);
      } else {
        const stream = new ResponsesStream(translated, frame => { emitted.push(...parsedFrames([frame])); response.write(frame); });
        for (const chunk of [
          { choices: [{ delta: { content: 'Fixture terminal.' }, finish_reason: null }] },
          { choices: [{ delta: {}, finish_reason: 'stop' }] },
          { choices: [], usage: { prompt_tokens: 24, completion_tokens: 3, total_tokens: 27 } },
        ]) stream.push(Buffer.from(`data: ${JSON.stringify(chunk)}\n\n`));
        stream.push(Buffer.from('data: [DONE]\n\n')); stream.end();
      }
      response.end();
    } catch (error) { errors.push(String(error)); response.writeHead(500); response.end('fixture contract error'); }
  });
  server.listen(0, '127.0.0.1'); await once(server, 'listening');
  const address = server.address(); assert.ok(address && typeof address === 'object');
  const catalog = JSON.parse(readFileSync(new URL('../../deploy/codex/models.json', import.meta.url), 'utf8'));
  writeFileSync(join(home, 'models.json'), JSON.stringify(catalog));
  const mcp = fileURLToPath(new URL('./fixtures/codex-image-native-mcp.mjs', import.meta.url));
  writeFileSync(join(home, 'config.toml'), `model = "qwen3.8-27b"
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
args = ${JSON.stringify([mcp, capture])}
enabled_tools = ["image_capabilities"]
startup_timeout_sec = 10
tool_timeout_sec = 10
`);
  const child = spawn(binary, ['app-server'], { cwd: workspace, env: {
    HOME: base, CODEX_HOME: home, TMPDIR: base, PATH: '/usr/bin:/bin',
    AI_HARNESS_GATEWAY_TOKEN: 'fixture-local-only', RUST_LOG: 'error',
  }, stdio: ['pipe', 'pipe', 'pipe'] });
  const lines = createInterface({ input: child.stdout });
  lines.on('line', line => { try { events.push(JSON.parse(line)); } catch { errors.push('non-JSON native stdout'); } });
  child.stderr.on('data', chunk => { stderr += chunk.toString(); });
  async function waitFor(predicate: (event: any) => boolean, start = 0) {
    const deadline = Date.now() + 12000;
    while (Date.now() < deadline) {
      const event = events.slice(start).find(predicate); if (event) return event;
      if (errors.length) throw Error(errors.join('\n'));
      await new Promise(resolveWait => setTimeout(resolveWait, 20));
    }
    throw Error(`native fixture timed out; stderr=${stderr.slice(-2000)}`);
  }
  async function rpc(method: string, params: any) {
    const id = ++nextId; child.stdin.write(JSON.stringify({ id, method, params }) + '\n');
    const event = await waitFor(event => event.id === id); assert.equal(event.error, undefined); return event.result;
  }
  let passed = false;
  try {
    await rpc('initialize', { clientInfo: { name: 'sova_image_fixture', version: '0.0.3' }, capabilities: { experimentalApi: false } });
    child.stdin.write(JSON.stringify({ method: 'initialized', params: {} }) + '\n');
    for (const [index, arguments_] of cases.entries()) {
      const thread = await rpc('thread/start', { model: 'qwen3.8-27b', modelProvider: 'sova', cwd: workspace, approvalPolicy: 'never', sandbox: 'danger-full-access' });
      const start = events.length; const threadId = thread.thread.id;
      await rpc('turn/start', { threadId, input: [{ type: 'text', text: `IMAGE_CASE_${index}`, text_elements: [] }] });
      const completed = await waitFor(event => event.method === 'turn/completed' && event.params.threadId === threadId, start);
      assert.equal(completed.params.turn.status, 'completed');
      const call = events.slice(start).find(event => event.method === 'item/completed' && event.params.item.type === 'mcpToolCall')?.params.item;
      assert.ok(call, 'native MCP lifecycle event absent');
      assert.equal(call.id, `fixture_image_${index}`); assert.equal(call.tool, 'image_capabilities'); assert.equal(call.server, 'image');
      assert.deepEqual(call.arguments, JSON.parse(arguments_));
      assert.equal(call.status, index === 0 ? 'completed' : 'failed');
      if (index) assert.match(JSON.stringify(call), /Unrecognized key/);
      const followup = requests.find(body => body.input.some((item: any) => item.type === 'function_call_output' && item.call_id === call.id));
      assert.ok(followup); const functionCall = followup.input.find((item: any) => item.type === 'function_call' && item.call_id === call.id);
      assert.equal(functionCall.arguments, arguments_); assert.equal(functionCall.namespace, 'mcp__image'); assert.equal(functionCall.name, 'image_capabilities');
      if (index) assert.match(JSON.stringify(followup.input.find((item: any) => item.type === 'function_call_output' && item.call_id === call.id)), /Unrecognized key/);
    }
    const calls = readFileSync(capture, 'utf8').trim().split('\n').map(line => JSON.parse(line));
    assert.deepEqual(calls.filter(call => call.kind === 'mcp_input').map(call => call.message.params.arguments), cases.map(arguments_ => JSON.parse(arguments_)));
    assert.deepEqual(calls.filter(call => call.kind === 'client_invocation').map(call => call.input), [{}], 'invalid args reached client');
    assert.equal(requests.length, cases.length * 2); assert.deepEqual(errors, []); passed = true;
  } finally {
    const exit = once(child, 'exit'); child.kill('SIGTERM');
    const killer = setTimeout(() => child.kill('SIGKILL'), 3000); await exit; clearTimeout(killer); lines.close();
    await new Promise<void>(resolveClose => server.close(() => resolveClose()));
    if (process.env.CODEX_NATIVE_FIXTURE_EVIDENCE_DIR) {
      const output = resolve(process.env.CODEX_NATIVE_FIXTURE_EVIDENCE_DIR); mkdirSync(output, { recursive: true });
      const clean = (value: any) => JSON.stringify(value, null, 2).replaceAll(base, '<fixture>') + '\n';
      writeFileSync(join(output, 'native-image-capture.json'), clean({ requests, events, emitted, errors, stderr,
        mcp: existsSync(capture) ? readFileSync(capture, 'utf8').trim().split('\n').map(line => JSON.parse(line)) : [] }));
      writeFileSync(join(output, 'native-image-result.json'), clean({ status: passed ? 'PASS' : 'FAIL', binarySha256: pin,
        cases, providerRequests: requests.length, fixtureProcessExited: child.exitCode !== null || child.signalCode !== null,
        scope: 'Synthetic Chat through current Responses adapter, pinned native Mac binary and actual strict image MCP schema; no live model or image job.' }));
    }
    rmSync(base, { recursive: true, force: true });
  }
});
