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
import { translateResponses, ResponsesStream } from '../src/codex-responses.js';
import { CODEX_MODEL_POLICY, CODEX_TOOL_POLICY_SHA256 } from '../src/codex-launcher.js';

const binarySha256 = '788a818fbb9596869c7a487554507cb8bdca17584b8671112b23f9e225ba35c8';
const profiles = ['config.toml', 'config-image-jobs.toml'];
const readProfile = (name: string) => readFileSync(new URL(`../../deploy/codex/${name}`, import.meta.url), 'utf8');
const catalogText = readFileSync(new URL('../../deploy/codex/models.json', import.meta.url), 'utf8');

test('both mounted profiles explicitly disable native viewing while catalog remains text-only', () => {
  const files = ['config.toml', 'config-image-jobs.toml', 'requirements.toml', 'models.json', 'browser-mcp.mjs', 'skills/sova-local-tools/SKILL.md'];
  assert.equal(createHash('sha256').update(files.map(readProfile).join('')).digest('hex'), CODEX_TOOL_POLICY_SHA256);
  assert.equal(CODEX_MODEL_POLICY, 'sova-codex-0.158.0-qwen-text-v2', 'preserve retained session model-profile compatibility');
  for (const name of profiles) {
    const config = readProfile(name);
    assert.match(config, /\[features\]\nview_image = false\n/);
    assert.match(config, /^developer_instructions = "Complete the requested work/m);
  }
  for (const model of JSON.parse(catalogText).models) assert.deepEqual(model.input_modalities, ['text']);
});

// Exact released Mac binary; loopback scripted responses only. Not a PDF rerun,
// model-completion qualification, Linux declaration capture or specialist PASS.
test('pinned native default advertises/rejects view_image; both candidate profiles omit it', {
  skip: !process.env.CODEX_NATIVE_FIXTURE_BINARY,
  timeout: 60000,
}, async () => {
  const binary = resolve(process.env.CODEX_NATIVE_FIXTURE_BINARY!);
  assert.equal(createHash('sha256').update(readFileSync(binary)).digest('hex'), binarySha256);
  const captures: any[] = [];
  for (const name of ['retained-default', ...profiles]) {
    const baseline = name === 'retained-default';
    const base = mkdtempSync(join(tmpdir(), 'sova-text-native-'));
    const home = join(base, 'codex'), workspace = join(base, 'workspace');
    mkdirSync(home); mkdirSync(workspace);
    writeFileSync(join(home, 'models.json'), catalogText);
    const requests: any[] = [], events: any[] = [], errors: string[] = [];
    let stderr = '', nextId = 0;
    const server = createServer(async (request, response) => {
      try {
        assert.equal(request.url, '/v1/responses');
        const chunks: Buffer[] = []; for await (const chunk of request) chunks.push(Buffer.from(chunk));
        const body = JSON.parse(Buffer.concat(chunks).toString()); requests.push(body);
        assert.ok(requests.length <= (baseline ? 2 : 1), 'unexpected native retry');
        const translated = translateResponses(body);
        const names = translated.body.tools.map((tool: any) => tool.function?.name);
        assert.equal(names.includes('view_image'), baseline);
        assert.ok(names.includes('exec_command'), 'ordinary local tools removed');
        if (!baseline) assert.match(JSON.stringify(body.input), /Complete the requested work and create requested artifacts/);
        response.writeHead(200, { 'Content-Type': 'text/event-stream' });
        const stream = new ResponsesStream(translated, frame => response.write(frame));
        if (baseline && requests.length === 1) {
          stream.push(Buffer.from(`data: ${JSON.stringify({ choices: [{ delta: { tool_calls: [{ index: 0,
            id: 'offline_view', type: 'function', function: { name: 'view_image', arguments: '{"path":"/fixture/never-read.png"}' } }] }, finish_reason: null }] })}\n\n`));
          stream.push(Buffer.from(`data: ${JSON.stringify({ choices: [{ delta: {}, finish_reason: 'tool_calls' }] })}\n\n`));
        } else {
          if (baseline) {
            const output = body.input.find((item: any) => item.type === 'function_call_output' && item.call_id === 'offline_view');
            assert.match(JSON.stringify(output), /view_image is not allowed because you do not support image inputs/);
          }
          stream.push(Buffer.from(`data: ${JSON.stringify({ choices: [{ delta: { content: 'Offline fixture ended.' }, finish_reason: null }] })}\n\n`));
          stream.push(Buffer.from(`data: ${JSON.stringify({ choices: [{ delta: {}, finish_reason: 'stop' }] })}\n\n`));
        }
        stream.push(Buffer.from(`data: ${JSON.stringify({ choices: [], usage: { prompt_tokens: 24, completion_tokens: 4, total_tokens: 28 } })}\n\n`));
        stream.push(Buffer.from('data: [DONE]\n\n')); stream.end(); response.end();
      } catch (error) { errors.push(String(error)); if (!response.headersSent) response.writeHead(500); response.end('fixture contract error'); }
    });
    server.listen(0, '127.0.0.1'); await once(server, 'listening');
    const address = server.address(); assert.ok(address && typeof address === 'object');
    let config = readProfile(baseline ? 'config.toml' : name)
      .replace('/opt/sova/codex/models.json', join(home, 'models.json'))
      .replace('http://10.0.2.2:8081/v1', `http://127.0.0.1:${address.port}/v1`);
    if (baseline) config = config.replace('view_image = false\n', '').replace(/^developer_instructions = .*\n/m, '');
    writeFileSync(join(home, 'config.toml'), config);
    // Container-only MCP binaries are disabled in this Mac fixture. Native tool
    // and developer-instruction settings are read from the actual mounted files.
    const child = spawn(binary, ['--strict-config', '-c', 'mcp_servers.search.enabled=false',
      '-c', 'mcp_servers.browser.enabled=false', '-c', 'mcp_servers.image.enabled=false', 'app-server'], {
      cwd: workspace, env: { HOME: base, CODEX_HOME: home, TMPDIR: base, PATH: '/usr/bin:/bin',
        AI_HARNESS_GATEWAY_TOKEN: 'fixture-local-only', RUST_LOG: 'error' }, stdio: ['pipe', 'pipe', 'pipe'],
    });
    const lines = createInterface({ input: child.stdout });
    lines.on('line', line => { try { events.push(JSON.parse(line)); } catch { errors.push('non-JSON native stdout'); } });
    child.stderr.on('data', chunk => { stderr += chunk.toString(); });
    async function waitFor(predicate: (event: any) => boolean) {
      const deadline = Date.now() + 10000;
      while (Date.now() < deadline) {
        const event = events.find(predicate); if (event) return event;
        if (errors.length) throw Error(errors.join('\n'));
        if (child.exitCode !== null) throw Error(`native exited: ${stderr.slice(-2000)}`);
        await new Promise(resolveWait => setTimeout(resolveWait, 20));
      }
      throw Error(`native fixture timed out: ${stderr.slice(-2000)}`);
    }
    async function rpc(method: string, params: any) {
      const id = ++nextId; child.stdin.write(JSON.stringify({ id, method, params }) + '\n');
      const event = await waitFor(event => event.id === id); assert.equal(event.error, undefined); return event.result;
    }
    let passed = false;
    try {
      await rpc('initialize', { clientInfo: { name: 'sova_text_fixture', version: '0.0.3' }, capabilities: { experimentalApi: false } });
      child.stdin.write(JSON.stringify({ method: 'initialized', params: {} }) + '\n');
      const thread = await rpc('thread/start', { model: 'qwen3.8-27b', modelProvider: 'sova', cwd: workspace,
        approvalPolicy: 'never', sandbox: 'danger-full-access' });
      await rpc('turn/start', { threadId: thread.thread.id, input: [{ type: 'text', text: 'Offline tool declaration fixture.', text_elements: [] }] });
      const completed = await waitFor(event => event.method === 'turn/completed');
      assert.equal(completed.params.turn.status, 'completed');
      assert.equal(requests.length, baseline ? 2 : 1); assert.deepEqual(errors, []);
      const final = events.find(event => event.method === 'item/completed' && event.params.item.type === 'agentMessage');
      assert.equal(final.params.item.text, 'Offline fixture ended.');
      assert.equal(final.params.item.phase, null, 'do not invent final/reasoning tags');
      passed = true;
    } finally {
      if (child.exitCode === null && child.signalCode === null) {
        const exit = once(child, 'exit'); child.kill('SIGTERM');
        const killer = setTimeout(() => child.kill('SIGKILL'), 2000); await exit; clearTimeout(killer);
      }
      lines.close(); await new Promise<void>(resolveClose => server.close(() => resolveClose()));
      captures.push({ name, passed, config, requests, events, errors, stderr, exited: child.exitCode !== null || child.signalCode !== null });
      if (process.env.CODEX_NATIVE_FIXTURE_EVIDENCE_DIR) {
        const dir = resolve(process.env.CODEX_NATIVE_FIXTURE_EVIDENCE_DIR); mkdirSync(dir, { recursive: true });
        writeFileSync(join(dir, 'native-text-only-capture.json'), JSON.stringify({ binarySha256, captures }, null, 2) + '\n');
      }
      rmSync(base, { recursive: true, force: true });
    }
  }
});
