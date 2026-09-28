import test from 'node:test';
import assert from 'node:assert/strict';
import { composeCodexHost } from '../src/codex-host.js';
import { createGateway } from '../src/gateway.js';

test('host remains disabled without trusted runtime proof and settlement fails closed', async () => {
  const host = composeCodexHost('/trusted/deploy/run-codex.sh', () => undefined);
  assert.equal(host.runtime.protocolQualified, false);
  assert.equal(host.responses, undefined);
  assert.equal(await host.runtime.confirmGatewaySettlement({ sessionId: 'x', gatewayToken: 'x', activeTurnId: null }), false);
  assert.throws(() => host.runtime.revokeGatewaySession('x'));
  assert.throws(() => composeCodexHost('/trusted/deploy/run-codex.sh', () => undefined, {} as any));
});
test('Codex scope cannot submit image work, bypass Responses or reach frontier; MiniMax unchanged', async () => {
  const g = createGateway({ upstreamKey: 'fixture-secret' });
  const token = g.issueToken('codex-session', 'codex');
  for (const url of ['/v1/image-jobs', '/v1/chat/completions', '/frontier/v1/responses']) {
    const r = await g.app.inject({ method: 'POST', url, headers: {authorization: `Bearer ${token}`}, payload: {} });
    assert.equal(r.statusCode,403);assert.equal(r.json().error.code,'codex_route_unqualified');
  }
  const native = g.issueToken('native-session');
  const r = await g.app.inject({method:'POST',url:'/v1/chat/completions',headers:{authorization:`Bearer ${native}`},payload:{}});
  assert.notEqual(r.statusCode,403);
  g.revokeSession('codex-session');
  assert.equal((await g.app.inject({url:'/v1/models',headers:{authorization:`Bearer ${token}`}})).statusCode,401);
  await g.close();
});
