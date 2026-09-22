import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFileSync, mkdtempSync, mkdirSync, copyFileSync, rmSync, existsSync } from 'node:fs';
import { stripTypeScriptTypes, createRequire } from 'node:module';
import { createServer } from 'node:http';
import { connect } from 'node:net';
import { once } from 'node:events';
import { spawnSync } from 'node:child_process';
import { pathToFileURL, fileURLToPath } from 'node:url';
import os from 'node:os';
import path from 'node:path';

// Exact pinned adapter helper exercised through actual Node fetch + pinned Undici.
// No gateway/model contact. FixtureAgent maps the reviewed gateway IP to our
// ephemeral loopback fixture port. Only the connection target changes in tests.
const source = process.env.AI_HARNESS_MINIMAX_SOURCE;
assert.ok(source && path.isAbsolute(source), 'Set AI_HARNESS_MINIMAX_SOURCE to pristine ae65651d source');
const deploy = fileURLToPath(new URL('../', import.meta.url));
const patches = path.join(deploy, 'patches');
const identity = JSON.parse(readFileSync(path.join(patches, 'identity.json'), 'utf8'));
const sha = (value) => createHash('sha256').update(value).digest('hex');
const copied = mkdtempSync(path.join(os.tmpdir(), 'h001-transport-check-'));
let provider;
try {
  assert.equal(sha(readFileSync(path.join(patches, 'SHA256SUMS'))), identity.patchSetSha256);
  for (const file of identity.files) {
    if (file.originalSha256 === null) {
      assert.equal(existsSync(path.join(source, file.path)), false, `Added source must be absent: ${file.path}`);
      continue;
    }
    assert.equal(sha(readFileSync(path.join(source, file.path))), file.originalSha256);
    mkdirSync(path.dirname(path.join(copied, file.path)), { recursive: true });
    copyFileSync(path.join(source, file.path), path.join(copied, file.path));
  }
  for (const patch of identity.patches) {
    const patchPath = path.join(patches, patch.path);
    assert.equal(sha(readFileSync(patchPath)), patch.sha256);
    for (const args of [['apply', '--check', patchPath], ['apply', patchPath]]) {
      const result = spawnSync('git', args, { cwd: copied, encoding: 'utf8' });
      assert.equal(result.status, 0, result.stderr);
    }
  }
  for (const file of identity.files) {
    assert.equal(sha(readFileSync(path.join(copied, file.path))), file.patchedSha256);
  }
  provider = readFileSync(path.join(copied, 'third_party/pi-mono/packages/ai/src/providers/openai-completions.ts'), 'utf8');
  const manifest = JSON.parse(readFileSync(path.join(copied, 'third_party/pi-mono/packages/ai/package.json'), 'utf8'));
  assert.equal(manifest.dependencies.undici, '7.29.1');
  const lock = readFileSync(path.join(copied, 'pnpm-lock.yaml'), 'utf8');
  const importer = lock.split('  third_party/pi-mono/packages/ai:')[1].split('\n  third_party/pi-mono/packages/coding-agent:')[0];
  assert.match(importer, /undici:\n        specifier: 7\.29\.1\n        version: 7\.29\.1/u);
  assert.ok(lock.includes(`resolution: {integrity: ${identity.transport.undiciIntegrity}}`));
} finally {
  rmSync(copied, { recursive: true, force: true });
}
const require = createRequire(import.meta.url);
const undiciPath = process.env.AI_HARNESS_UNDICI_MODULE || require.resolve('undici', { paths: [source] });
assert.ok(path.isAbsolute(undiciPath), 'AI_HARNESS_UNDICI_MODULE must be absolute');
const { Agent } = await import(pathToFileURL(undiciPath));
const undiciManifest = JSON.parse(readFileSync(path.join(path.dirname(undiciPath), 'package.json'), 'utf8'));
assert.equal(undiciManifest.version, identity.transport.undici);
const helper = provider.match(/\/\/ ai-harness transport:[\s\S]+?(?=\/\*\*\n \* Check if conversation messages)/u)?.[0];
assert.ok(helper, 'Missing exact gateway helper in patched adapter');
assert.match(provider, /fetch: harnessGatewayFetch\(baseURL, fetch\)/u);
const instantiate = (AgentType) => Function('Agent', `${stripTypeScriptTypes(helper)}\nreturn { harnessGatewayFetch, gatewayDispatcher, GATEWAY_TRANSPORT_TIMEOUT_MS };`)(AgentType);
const gateway = 'http://10.0.2.2:8081';

// This is deliberately sequential because one tiny HTTP server owns each case.
test('exact gateway scope, native signal/options retention and no global fetch mutation', async () => {
  const originalFetch = globalThis.fetch;
  const calls = [];
  const fallback = async (...args) => { calls.push(args); return new Response('fixture'); };
  const { harnessGatewayFetch, gatewayDispatcher, GATEWAY_TRANSPORT_TIMEOUT_MS } = instantiate(Agent);
  try {
    assert.equal(GATEWAY_TRANSPORT_TIMEOUT_MS, 9_060_000);
    for (const origin of ['https://api.openai.com/v1', 'http://10.0.2.2:8082/v1', 'https://10.0.2.2:8081/v1', 'http://10.0.2.20:8081/v1', 'invalid']) {
      assert.equal(harnessGatewayFetch(origin, fallback), fallback);
    }
    const selected = harnessGatewayFetch(`${gateway}/v1`, fallback);
    const signal = new AbortController().signal;
    const init = { signal, method: 'POST', body: 'fixture', headers: { 'x-fixture': 'preserved' } };
    for (const input of [`${gateway}/v1/chat/completions`, new URL(`${gateway}/v1/chat/completions`), new Request(`${gateway}/v1/chat/completions`)]) {
      await selected(input, init);
      const [actualInput, actualInit] = calls.pop();
      assert.equal(actualInput, input);
      assert.equal(actualInit.signal, signal);
      assert.equal(actualInit.headers, init.headers);
      assert.equal(actualInit.body, init.body);
      assert.equal(actualInit.dispatcher, gatewayDispatcher);
    }
    await selected('http://127.0.0.1:8081/v1', init);
    assert.equal(calls.pop()[1], init);
    assert.equal(globalThis.fetch, originalFetch);
  } finally { await gatewayDispatcher.destroy(); }
});

test('short-timeout fixture proves delayed headers/body survive dispatch defaults and AbortSignal still cancels', async () => {
  const server = createServer((request, response) => {
    if (request.url === '/headers') setTimeout(() => response.end('headers survived'), 1600).unref();
    else if (request.url === '/body') { response.writeHead(200); response.write('first '); setTimeout(() => response.end('second'), 1600).unref(); }
    else if (request.url === '/cancel') { response.writeHead(200); response.write('first '); }
    else response.end('fixture');
  });
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  const port = server.address().port;
  const dispatched = [];
  class FixtureAgent extends Agent {
    constructor() {
      super({ connect: (_options, callback) => {
        const socket = connect({ host: '127.0.0.1', port });
        socket.once('connect', () => callback(null, socket));
        socket.once('error', (error) => callback(error, null));
      } });
    }
    dispatch(options, handler) { dispatched.push(options); return super.dispatch(options, handler); }
  }
  // Inject the known short underlying limit instead of waiting 300 seconds.
  const short = new FixtureAgent().compose((dispatch) => (options, handler) => dispatch({ ...options, headersTimeout: 20, bodyTimeout: 20 }, handler));
  const { harnessGatewayFetch, gatewayDispatcher } = instantiate(FixtureAgent);
  const longFetch = harnessGatewayFetch(`${gateway}/v1`);
  try {
    await assert.rejects(fetch(`${gateway}/headers`, { dispatcher: short }), (error) => error.cause?.code === 'UND_ERR_HEADERS_TIMEOUT');
    const shortBody = await fetch(`${gateway}/body`, { dispatcher: short });
    await assert.rejects(shortBody.text(), (error) => error.cause?.code === 'UND_ERR_BODY_TIMEOUT');
    assert.equal(await (await longFetch(`${gateway}/headers`)).text(), 'headers survived');
    assert.equal(await (await longFetch(`${gateway}/body`)).text(), 'first second');
    const extended = dispatched.filter((entry) => entry.headersTimeout === 9_060_000);
    assert.ok(extended.length >= 2);
    assert.ok(extended.every((entry) => entry.bodyTimeout === 9_060_000));
    for (const url of ['/headers', '/cancel']) {
      const controller = new AbortController();
      const started = performance.now();
      const result = longFetch(`${gateway}${url}`, { signal: controller.signal }).then((response) => response.text());
      setTimeout(() => controller.abort(), 50).unref();
      await assert.rejects(result, (error) => error.name === 'AbortError');
      assert.ok(performance.now() - started < 1000, 'Explicit cancellation settles promptly');
    }
  } finally {
    await Promise.all([short.destroy(), gatewayDispatcher.destroy()]);
    server.closeAllConnections();
    await new Promise((resolve) => server.close(resolve));
  }
});
