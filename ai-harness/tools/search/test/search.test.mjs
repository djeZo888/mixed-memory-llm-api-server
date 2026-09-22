// SPDX-License-Identifier: MIT
import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import { once } from 'node:events';
import { spawn, spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js';
import { configuredEndpoint, LIMITS, normalizedResults } from '../search.mjs';

const entrypoint = fileURLToPath(new URL('../searxng-mcp.mjs', import.meta.url));
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const requests = [];
const closed = new Set();
let fixture, endpoint, client, transport;
let stderr = '';

before(async () => {
  fixture = http.createServer((req, res) => {
    const url = new URL(req.url, 'http://127.0.0.1');
    const q = url.searchParams.get('q');
    requests.push({ path: url.pathname, params: Object.fromEntries(url.searchParams), method: req.method });
    res.on('close', () => closed.add(q));
    if (q === 'timeout' || q?.startsWith('cancel') || q?.startsWith('busy')) return;
    if (q === 'redirect') { res.writeHead(302, { Location: endpoint + '/should-never-be-requested' }); res.end(); return; }
    if (q === 'http-error') { res.writeHead(503); res.end('secret upstream diagnostic'); return; }
    if (q === 'wrong-type') { res.end('<html>not json</html>'); return; }
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    if (q === 'body-timeout') { res.write('{"results":['); return; }
    if (q === 'bad-json') { res.end('{'); return; }
    if (q === 'bad-utf8') { res.end(Buffer.from([0xff])); return; }
    if (q === 'missing-results') { res.end('{}'); return; }
    if (q === 'too-large-length') { res.writeHead(200, { 'Content-Length': LIMITS.bodyBytes + 1 }); res.end(); return; }
    if (q === 'too-large-stream') { res.write(' '.repeat(LIMITS.bodyBytes)); res.end('overflow'); return; }
    if (q === 'empty') { res.end('{"results":[]}'); return; }
    if (q === 'invalid-results') {
      res.end(JSON.stringify({ results: [
        { title: 'Bad', url: 'javascript:alert(1)', content: 'wrong' },
        { title: 'Bad', url: 'https://user:pass@example.com/', content: 'wrong' },
        { title: 'Bad', url: 'http://127.0.0.1/private', content: 'wrong' },
        { title: {}, url: 'https://example.com', content: 'wrong' },
        { title: 'Bad', url: 'https://example.com', content: {} },
        { title: '<b>Datasheet</b> &amp; pins\u0007\u202e', url: 'https://example.com/datasheet', content: '<em>Voltage</em>: 3.3 V &lt; maximum. &#27; &#x202e;' },
        { title: 'Duplicate', url: 'https://example.com/datasheet', content: 'duplicate' },
      ] })); return;
    }
    if (q === 'partial') { res.end(JSON.stringify({ results: [], unresponsive_engines: [['test-engine', 'secret detail']] })); return; }
    res.end(JSON.stringify({ results: Array.from({ length: 12 }, (_, i) => ({
      title: `Source ${i}`, url: `https://example.com/source/${i}`, content: `Fixture snippet ${i}`,
    })) }));
  });
  fixture.listen(0, '127.0.0.1');
  await once(fixture, 'listening');
  endpoint = `http://127.0.0.1:${fixture.address().port}`;
  transport = new StdioClientTransport({ command: process.execPath, args: [entrypoint], env: { AI_HARNESS_SEARXNG_URL: endpoint }, stderr: 'pipe' });
  transport.stderr.on('data', chunk => { stderr += chunk; });
  client = new Client({ name: 'local-fixture-tests', version: '0.0.1' });
  await client.connect(transport);
});
after(async () => {
  await client?.close();
  fixture.closeAllConnections();
  await new Promise(resolve => fixture.close(resolve));
  assert.equal(stderr, '', 'successful protocol exchange has no stderr diagnostics');
});
async function call(query, extra = {}, options) {
  const result = await client.callTool({ name: 'searxng_search', arguments: { query, ...extra } }, undefined, options);
  return { result, data: JSON.parse(result.content[0].text) };
}
async function waitUntil(predicate, ms = 2000) {
  const deadline = Date.now() + ms;
  while (!predicate() && Date.now() < deadline) await sleep(10);
  assert.ok(predicate(), 'condition reached before deadline');
}

test('real SDK stdio initialize, ping, tools/list and schema', async () => {
  assert.equal(client.getServerVersion().name, 'ai-harness-searxng');
  await client.ping();
  const { tools } = await client.listTools();
  assert.equal(tools.length, 1);
  assert.equal(tools[0].name, 'searxng_search');
  assert.equal(tools[0].inputSchema.additionalProperties, false);
  assert.equal(tools[0].inputSchema.properties.limit.maximum, 10);
  assert.equal(tools[0].annotations.readOnlyHint, true);
});
test('successful search returns default five citation-ready results and fixed upstream request', async () => {
  const { result, data } = await call('  capacitors  ');
  assert.ok(!result.isError);
  assert.equal(data.query, 'capacitors');
  assert.equal(data.results.length, 5);
  assert.equal(data.truncated, true);
  assert.deepEqual(data.results[0], { title: 'Source 0', url: 'https://example.com/source/0', snippet: 'Fixture snippet 0' });
  assert.deepEqual(requests.at(-1), { path: '/search', method: 'GET', params: { q: 'capacitors', format: 'json', pageno: '1', categories: 'general' } });
});
test('explicit result limit works', async () => assert.equal((await call('one', { limit: 1 })).data.results.length, 1));
test('empty result is successful with empty list', async () => {
  const { result, data } = await call('empty');
  assert.ok(!result.isError);
  assert.deepEqual(data.results, []);
});
test('schema rejects oversized, control, empty, fractional and endpoint override inputs before HTTP', async () => {
  const count = requests.length;
  for (const args of [
    { query: '' }, { query: 'x'.repeat(513) }, { query: 'line\nline' }, { query: 'hidden\u202e' },
    { query: 'x', limit: 0 }, { query: 'x', limit: 11 }, { query: 'x', limit: 1.5 },
    { query: 'x', url: 'http://127.0.0.1/' },
  ]) {
    const result = await client.callTool({ name: 'searxng_search', arguments: args });
    assert.equal(result.isError, true);
  }
  assert.equal(requests.length, count);
});
test('unknown tool returns native SDK failure', async () => {
  const result = await client.callTool({ name: 'missing', arguments: {} });
  assert.equal(result.isError, true);
});
test('validates links and text types, strips HTML/control characters and removes duplicate URLs', async () => {
  const { data } = await call('invalid-results');
  assert.equal(data.results.length, 1);
  assert.deepEqual(data.results[0], { title: 'Datasheet & pins', url: 'https://example.com/datasheet', snippet: 'Voltage : 3.3 V maximum.' });
  assert.equal(data.truncated, true);
});
test('partial engine failure has safe coverage warning', async () => {
  const { data } = await call('partial');
  assert.match(data.warning, /incomplete/);
  assert.ok(!JSON.stringify(data).includes('secret detail'));
});
for (const [query, code] of [
  ['http-error', 'UPSTREAM_HTTP'], ['wrong-type', 'UPSTREAM_FORMAT'], ['bad-json', 'UPSTREAM_FORMAT'],
  ['bad-utf8', 'UPSTREAM_FORMAT'], ['missing-results', 'UPSTREAM_FORMAT'],
  ['too-large-length', 'UPSTREAM_TOO_LARGE'], ['too-large-stream', 'UPSTREAM_TOO_LARGE'],
]) {
  test(`bounded safe failure: ${query}`, async () => {
    const { result, data } = await call(query);
    assert.equal(result.isError, true);
    assert.equal(data.error.code, code);
    assert.ok(!JSON.stringify(data).includes('secret'));
  });
}
test('redirects are rejected and never followed', async () => {
  const beforeCount = requests.length;
  assert.equal((await call('redirect')).data.error.code, 'UPSTREAM_UNAVAILABLE');
  assert.equal(requests.length, beforeCount + 1);
});
for (const query of ['timeout', 'body-timeout']) {
  test(`real 10 second deadline aborts ${query}`, { timeout: 15_000 }, async () => {
    const started = Date.now();
    const { result, data } = await call(query);
    assert.equal(result.isError, true);
    assert.equal(data.error.code, 'TIMEOUT');
    assert.ok(Date.now() - started >= 9500 && Date.now() - started < 14_000);
    await waitUntil(() => closed.has(query));
  });
}
test('MCP cancellation notification aborts in-flight HTTP and leaves server usable', async () => {
  const abort = new AbortController();
  const promise = call('cancel-one', {}, { signal: abort.signal });
  const rejected = assert.rejects(promise);
  await waitUntil(() => requests.some(r => r.params.q === 'cancel-one'));
  abort.abort();
  await rejected;
  await waitUntil(() => closed.has('cancel-one'));
  await client.ping();
  assert.equal((await call('post-cancel')).data.results.length, 5);
});
test('two-call concurrency ceiling rejects third call and cancellation frees capacity', async () => {
  const controllers = [new AbortController(), new AbortController()];
  const promises = controllers.map((abort, i) => call(`busy-${i}`, {}, { signal: abort.signal }));
  const rejections = promises.map(p => assert.rejects(p));
  await waitUntil(() => requests.filter(r => r.params.q?.startsWith('busy-')).length === 2);
  assert.equal((await call('third')).data.error.code, 'BUSY');
  controllers.forEach(abort => abort.abort());
  await Promise.all(rejections);
  await waitUntil(() => closed.has('busy-0') && closed.has('busy-1'));
  assert.equal((await call('after-busy')).data.results.length, 5);
});
test('output byte cap applies to multibyte titles/snippets', () => {
  const output = normalizedResults({ results: Array.from({ length: 100 }, (_, i) => ({
    title: '😀'.repeat(512), content: '😀'.repeat(5000), url: `https://example.com/${i}?${'x'.repeat(1500)}`,
  })) }, '字'.repeat(512), 10);
  assert.ok(output.results.length > 0);
  assert.ok(output.results.length < 10);
  assert.ok(Buffer.byteLength(JSON.stringify(output)) <= LIMITS.outputBytes);
  assert.ok(Array.from(output.results[0].title).length <= LIMITS.title);
  assert.ok(Array.from(output.results[0].snippet).length <= LIMITS.snippet);
});
test('endpoint config rejects public, DNS, malformed, credentials, query and path values', () => {
  for (const value of [undefined, '', 'https://example.com', 'http://8.8.8.8', 'file:///tmp/x', 'http://localhost:8082',
    'http://127.0.0.1/path', 'http://u:p@127.0.0.1', 'http://127.0.0.1?q=x', 'http://127.0.0.1#frag', 'http://[::1]', 'http://127.0.0.1/\n']) {
    assert.throws(() => configuredEndpoint(value), /AI_HARNESS_SEARXNG_URL/);
  }
  assert.equal(configuredEndpoint('http://10.0.2.2:8082').href, 'http://10.0.2.2:8082/search');
});
test('missing config fails with safe stderr and no stdout', () => {
  const result = spawnSync(process.execPath, [entrypoint], { env: {}, encoding: 'utf8', timeout: 5000 });
  assert.equal(result.status, 1);
  assert.equal(result.stdout, '');
  assert.match(result.stderr, /AI_HARNESS_SEARXNG_URL/);
});
test('help requires no service connection or configuration', () => {
  const result = spawnSync(process.execPath, [entrypoint, '--help'], { env: {}, encoding: 'utf8', timeout: 5000 });
  assert.equal(result.status, 0);
  assert.match(result.stdout, /Usage:/);
  assert.equal(result.stderr, '');
});

test('official stdio transport closes on an oversized unframed request', { timeout: 5000 }, async () => {
  const child = spawn(process.execPath, [entrypoint], {
    env: { AI_HARNESS_SEARXNG_URL: endpoint }, stdio: ['pipe', 'pipe', 'pipe'],
  });
  let output = '';
  let errors = '';
  child.stdout.on('data', chunk => { output += chunk; });
  child.stderr.on('data', chunk => { errors += chunk; });
  child.stdin.on('error', () => {});
  const exit = once(child, 'exit');
  child.stdin.end('x'.repeat(LIMITS.stdioBytes + 1));
  const kill = setTimeout(() => child.kill('SIGKILL'), 4000);
  try {
    const [code, signal] = await exit;
    assert.equal(signal, null);
    assert.equal(code, 0);
    assert.equal(output, '');
    assert.match(errors, /^MCP transport or protocol error\.\n$/);
  } finally { clearTimeout(kill); }
});
test('EOF closes the adapter and aborts an active upstream request', { timeout: 5000 }, async () => {
  const closingTransport = new StdioClientTransport({
    command: process.execPath, args: [entrypoint],
    env: { AI_HARNESS_SEARXNG_URL: endpoint }, stderr: 'pipe',
  });
  const closingClient = new Client({ name: 'close-fixture', version: '0.0.1' });
  await closingClient.connect(closingTransport);
  const promise = closingClient.callTool({ name: 'searxng_search', arguments: { query: 'cancel-eof' } });
  const rejected = assert.rejects(promise);
  await waitUntil(() => requests.some(r => r.params.q === 'cancel-eof'));
  const started = Date.now();
  await closingClient.close();
  await rejected;
  await waitUntil(() => closed.has('cancel-eof'));
  assert.ok(Date.now() - started < 1500, 'graceful EOF closes before SDK forced-kill timeout');
});
