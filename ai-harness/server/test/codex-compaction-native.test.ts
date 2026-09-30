import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { spawn } from 'node:child_process';
import { createServer } from 'node:http';
import { once } from 'node:events';
import { createInterface } from 'node:readline';
import { mkdtempSync, mkdirSync, readFileSync, writeFileSync, readdirSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { translateResponses, ResponsesStream } from '../src/codex-responses.js';

const pin = '788a818fbb9596869c7a487554507cb8bdca17584b8671112b23f9e225ba35c8';
const fact = 'COBALT-731';
const original = `COMPACT_ORIGINAL: retain fixture code ${fact}. Original user message must remain in native history.`;
const summary = `COMPACT_SYNTHETIC_SUMMARY: fixture code is ${fact}. This is deterministic mock recall evidence only.`;

test('pinned native explicit compaction has canonical lifecycle and fresh resume preserves thread/history', {
  skip: !process.env.CODEX_NATIVE_FIXTURE_BINARY, timeout: 60000,
}, async () => {
  const binary = resolve(process.env.CODEX_NATIVE_FIXTURE_BINARY!);
  assert.equal(createHash('sha256').update(readFileSync(binary)).digest('hex'), pin);
  const base = mkdtempSync(join(tmpdir(), 'sova-compact-native-')); const home = join(base, 'codex'); const workspace = join(base, 'workspace');
  mkdirSync(home); mkdirSync(workspace);
  const requests: any[] = []; const exchanges: any[] = []; const errors: string[] = []; const processes: any[] = [];
  let threadId = ''; let historyPrefixPreserved = false; let compactLifecycle: string[] = [];
  const server = createServer(async (request, response) => {
    try {
      assert.equal(request.url, '/v1/responses'); assert.equal(request.headers.authorization, 'Bearer fixture-local-only');
      const chunks: Buffer[] = []; for await (const chunk of request) chunks.push(Buffer.from(chunk));
      const body = JSON.parse(Buffer.concat(chunks).toString()); requests.push(body);
      assert.ok(requests.length <= 3, 'duplicate provider dispatch');
      const content = JSON.stringify(body.input); const compact = body.tools.length === 0;
      let answer = 'Fixture original acknowledged.';
      if (compact) { assert.ok(content.includes(fact)); answer = summary; }
      else if (requests.length > 1) {
        assert.ok(content.includes('COMPACT_SYNTHETIC_SUMMARY'), 'compacted context absent after fresh resume');
        assert.ok(content.includes(fact), 'compacted fact absent'); answer = fact;
      }
      response.writeHead(200, { 'Content-Type': 'text/event-stream' });
      const stream = new ResponsesStream(translateResponses(body), frame => response.write(frame));
      for (const chunk of [
        { choices: [{ delta: { content: answer }, finish_reason: null }] },
        { choices: [{ delta: {}, finish_reason: 'stop' }] },
        { choices: [], usage: { prompt_tokens: 50, completion_tokens: 10, total_tokens: 60 } },
      ]) stream.push(Buffer.from(`data: ${JSON.stringify(chunk)}\n\n`));
      stream.push(Buffer.from('data: [DONE]\n\n')); stream.end(); response.end();
    } catch (error) { errors.push(String(error)); response.writeHead(500); response.end('fixture contract error'); }
  });
  server.listen(0, '127.0.0.1'); await once(server, 'listening'); const address = server.address(); assert.ok(address && typeof address === 'object');
  const catalog = JSON.parse(readFileSync(new URL('../../deploy/codex/models.json', import.meta.url), 'utf8'));
  writeFileSync(join(home, 'models.json'), JSON.stringify(catalog));
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
`);
  async function startNative() {
    const child = spawn(binary, ['app-server'], { cwd: workspace, env: { HOME: base, CODEX_HOME: home, TMPDIR: base,
      PATH: '/usr/bin:/bin', AI_HARNESS_GATEWAY_TOKEN: 'fixture-local-only', RUST_LOG: 'error' }, stdio: ['pipe', 'pipe', 'pipe'] });
    const exited = once(child, 'exit'); let nextId = 0; let stderr = ''; const events: any[] = []; const rpcRequests: any[] = [];
    const lines = createInterface({ input: child.stdout }); lines.on('line', line => { try { events.push(JSON.parse(line)); } catch { errors.push('non-JSON stdout'); } });
    child.stderr.on('data', chunk => { stderr += chunk.toString(); });
    async function waitFor(predicate: (event: any) => boolean, start = 0) {
      const deadline = Date.now() + 12000;
      while (Date.now() < deadline) {
        const event = events.slice(start).find(predicate); if (event) return event;
        if (errors.length) throw Error(errors.join('\n'));
        await new Promise(resolveWait => setTimeout(resolveWait, 20));
      }
      throw Error(`native compaction timeout: ${stderr.slice(-2000)}`);
    }
    async function rpc(method: string, params: any) {
      const id = ++nextId; const message = { id, method, params }; rpcRequests.push(message); child.stdin.write(JSON.stringify(message) + '\n');
      const event = await waitFor(event => event.id === id); assert.equal(event.error, undefined); return event.result;
    }
    let closed = false;
    const native = { child, events, rpcRequests, waitFor, rpc, async close() {
      if (closed) return; closed = true; child.kill('SIGTERM');
      const killer = setTimeout(() => child.kill('SIGKILL'), 3000); await exited; clearTimeout(killer); lines.close();
      exchanges.push({ rpcRequests, events, stderr, processExited: child.exitCode !== null || child.signalCode !== null });
    } };
    processes.push(native);
    await rpc('initialize', { clientInfo: { name: 'sova_compact_fixture', version: '0.0.3' }, capabilities: { experimentalApi: false } });
    child.stdin.write(JSON.stringify({ method: 'initialized', params: {} }) + '\n');
    return native;
  }
  const threadParams = { model: 'qwen3.8-27b', modelProvider: 'sova', cwd: workspace, approvalPolicy: 'never', sandbox: 'danger-full-access' };
  let passed = false;
  try {
    const first = await startNative(); const started = await first.rpc('thread/start', { ...threadParams, ephemeral: false }); threadId = started.thread.id;
    await first.rpc('turn/start', { threadId, input: [{ type: 'text', text: original, text_elements: [] }] });
    const firstTerminal = await first.waitFor(event => event.method === 'turn/completed'); assert.equal(firstTerminal.params.turn.status, 'completed');
    await first.close();
    const sessions = join(home, 'sessions');
    const relative = readdirSync(sessions, { recursive: true }).map(String).find(name => name.endsWith('.jsonl') && name.includes(threadId));
    assert.ok(relative, 'owned native rollout absent'); const rollout = join(sessions, relative); const before = readFileSync(rollout);
    assert.ok(before.toString().includes(original));

    const second = await startNative(); const resumed = await second.rpc('thread/resume', { ...threadParams, threadId });
    assert.equal(resumed.thread.id, threadId); assert.ok(JSON.stringify(resumed.thread.turns).includes(original), 'resume omitted original visible history');
    const eventStart = second.events.length;
    await second.rpc('thread/compact/start', { threadId });
    const compactTerminal = await second.waitFor(event => event.method === 'turn/completed', eventStart);
    assert.equal(compactTerminal.params.turn.status, 'completed');
    const lifecycle = second.events.slice(eventStart).filter(event => event.method === 'turn/started' || event.method === 'turn/completed' ||
      (['item/started', 'item/completed'].includes(event.method) && event.params.item.type === 'contextCompaction'));
    compactLifecycle = lifecycle.map(event => event.method);
    assert.deepEqual(compactLifecycle, ['turn/started', 'item/started', 'item/completed', 'turn/completed']);
    const compactTurn = lifecycle[0].params.turn.id;
    assert.ok(lifecycle.every(event => event.params.threadId === threadId));
    assert.equal(lifecycle[1].params.turnId, compactTurn); assert.equal(lifecycle[2].params.turnId, compactTurn);
    assert.equal(lifecycle[3].params.turn.id, compactTurn);
    assert.equal(lifecycle[1].params.item.id, lifecycle[2].params.item.id);
    await second.close();
    const after = readFileSync(rollout); historyPrefixPreserved = after.subarray(0, before.length).equals(before); assert.equal(historyPrefixPreserved, true);

    const third = await startNative(); const finalResume = await third.rpc('thread/resume', { ...threadParams, threadId });
    assert.equal(finalResume.thread.id, threadId);
    assert.ok(JSON.stringify(finalResume.thread.turns).includes(original), 'post-compaction resume rewrote original visible history');
    const recallStart = third.events.length;
    await third.rpc('turn/start', { threadId, input: [{ type: 'text', text: 'COMPACT_RECALL: return the retained fixture code.', text_elements: [] }] });
    const final = await third.waitFor(event => event.method === 'turn/completed', recallStart); assert.equal(final.params.turn.status, 'completed');
    assert.ok(third.events.slice(recallStart).some(event => event.method === 'item/completed' && event.params.item.type === 'agentMessage' && event.params.item.text === fact));
    await third.close();
    assert.equal(requests.length, 3); assert.deepEqual(requests.map(body => body.tools.length === 0), [false, true, false]);
    assert.equal(exchanges.flatMap(exchange => exchange.rpcRequests).filter(message => message.method === 'thread/compact/start').length, 1);
    assert.equal(exchanges.flatMap(exchange => exchange.rpcRequests).filter(message => message.method === 'turn/start').length, 2);
    assert.deepEqual(errors, []); passed = true;
  } finally {
    for (const native of processes) await native.close();
    await new Promise<void>(resolveClose => server.close(() => resolveClose()));
    if (process.env.CODEX_NATIVE_FIXTURE_EVIDENCE_DIR) {
      const output = resolve(process.env.CODEX_NATIVE_FIXTURE_EVIDENCE_DIR); mkdirSync(output, { recursive: true });
      const clean = (value: any) => JSON.stringify(value, null, 2).replaceAll(base, '<fixture>') + '\n';
      writeFileSync(join(output, 'native-compaction-capture.json'), clean({ requests, exchanges, errors }));
      writeFileSync(join(output, 'native-compaction-result.json'), clean({ status: passed ? 'PASS' : 'FAIL', binarySha256: pin, threadId,
        providerRequests: requests.length, freshProcesses: processes.length, historyPrefixPreserved, compactLifecycle,
        fixtureProcessesExited: exchanges.every(exchange => exchange.processExited),
        scope: 'Synthetic Chat through Responses adapter and direct pinned Mac App Server RPC. Three fresh native processes; deterministic mock recall only, no model semantic recall or Linux engine attestation.' }));
    }
    rmSync(base, { recursive: true, force: true });
  }
});
