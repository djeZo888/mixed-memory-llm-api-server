/** Independent H020 REVIEW02 fixtures. Synthetic data and in-memory app only. */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { sanitizeNode, SERVICE_IDS } from '../../ai-harness/server/src/node-contract.js';
import { projectNode } from '../../ai-harness/server/src/status-projection.js';
import { selectRegistryFrontier, validateSystemRegistry } from '../../ai-harness/server/src/system-registry.js';
import { createStatusService } from '../../ai-harness/server/src/status-service.js';
import { statusJs } from '../../ai-harness/server/src/status-ui.js';

const raw = () => JSON.parse(readFileSync(new URL('../../ai-harness/config/system-registry.json', import.meta.url), 'utf8'));
const meta = { state: 'ok', freshness: 'fresh', observed_at: '2026-09-28T04:00:00Z', age_ms: 0 };
const ids = ['glm-5.3-flash', 'mimo-v2.6-pro-rl'];
const uuid = 'GPU-cccccccc-aaaa-bbbb-cccc-111111111111';
const otherUuid = 'GPU-cccccccc-aaaa-bbbb-cccc-222222222222';
const row = (id: string) => ({ ...meta, service_id: id, model_alias: id, deployment_id: id + '-native', required_gpu_uuids: [uuid], ready: true, admitting: true, configured_context_tokens: 12345, max_output_tokens: 2345 });
function projected(selection: string | null, overrides: any = {}) {
  let registry = validateSystemRegistry(raw());
  if (selection !== null) registry = selectRegistryFrontier(registry, selection);
  const config = registry.nodes.find(n => n.id === 'ai-vm')!;
  const node = sanitizeNode({ schema_version: 1, node_id: config.id, ...meta, services: ids.map(row), gpus: [{ ...meta, uuid, index: 9, affected_services: ids }], ...overrides }, config.id, registry.services.filter(s => s.node_id === config.id).map(s => s.observation_key));
  return projectNode(node, config, registry);
}

test('both raw frontier ready observations retain contradiction but only selected model joins measured UUID', () => {
  for (const selected of ids) {
    const p = projected(selected);
    const dormant = p.services.find(s => ids.includes(s.service_id) && s.service_id !== selected)!;
    assert.equal(dormant.ready, null);
    assert.equal(dormant.admitting, null);
    assert.equal(dormant.observed_model.ready, true);
    assert.equal(dormant.selection_conflict, true);
    assert.deepEqual(p.gpus[0]!.observed_ready_dependents.map(s => s.service_id), [selected]);
    assert.deepEqual(p.gpus[0]!.affected_services, ids);
    assert.equal(p.gpus[0]!.index, 9);
  }
});

test('unknown selection preserves raw evidence without ready service or ready GPU dependent', () => {
  const p = projected(null);
  assert.equal(p.selected_frontier, null);
  for (const s of p.services.filter(s => ids.includes(s.service_id))) {
    assert.equal(s.selection, 'unknown'); assert.equal(s.ready, null);
    assert.equal(s.health, 'unknown'); assert.equal(s.observed_model.ready, true);
  }
  assert.deepEqual(p.gpus[0]!.observed_ready_dependents, []);
});

test('node, service and GPU freshness and exact UUID matching independently gate GPU joins', () => {
  const selected = ids[1]!;
  for (const overrides of [
    { freshness: 'stale' },
    { state: 'timeout' },
    { services: [{ ...row(selected), freshness: 'stale' }] },
    { services: [{ ...row(selected), model_alias: ids[0] }] },
    { gpus: [{ ...meta, uuid, freshness: 'stale' }] },
    { gpus: [{ ...meta, uuid, state: 'timeout' }] },
    { gpus: [{ ...meta, uuid: otherUuid, index: 9 }] },
  ]) assert.deepEqual(projected(selected, overrides).gpus[0]!.observed_ready_dependents, []);
  const staleGpu = projected(selected, { gpus: [{ ...meta, uuid, freshness: 'stale' }] });
  assert.equal(staleGpu.services.find(s => s.service_id === selected)!.ready, true);
  assert.deepEqual(projected(selected, { gpus: [] }).gpus, []);
});

test('native capacity remains observed evidence under mismatch and missing rows stay null', () => {
  const selected = ids[1]!;
  const mismatch = projected(selected, { services: [{ ...row(selected), model_alias: ids[0] }] }).services.find(s => s.service_id === selected)!;
  assert.equal(mismatch.configured_context_tokens, 12345);
  assert.equal(mismatch.max_output_tokens, 2345);
  assert.equal(mismatch.observed_model.model_alias, ids[0]);
  assert.equal(mismatch.identity_status, 'mismatch'); assert.equal(mismatch.ready, null);
  assert.equal(Object.hasOwn(mismatch.configured_model!, 'configured_context_tokens'), false);
  const missing = projected(selected, { services: [] }).services.find(s => s.service_id === selected)!;
  assert.equal(missing.observed_model.node_id, null); assert.equal(missing.observed_model.service_id, null);
  assert.equal(missing.configured_context_tokens, null); assert.equal(missing.max_output_tokens, null);
});

test('new model metadata rejects unexpected fields; public JSON omits registry and native transport secrets', async () => {
  const malformed = raw(); malformed.services[0].model.credential_path = '/private/sentinel';
  assert.throws(() => validateSystemRegistry(malformed));
  const registry = selectRegistryFrontier(validateSystemRegistry(raw()), ids[1]!);
  const native = { schema_version: 1, node_id: 'ai-vm', ...meta, credential_path: '/private/sentinel', transport: { token: 'secret-sentinel' }, services: [{ ...row(ids[1]!), authorization: 'secret-sentinel', model: { credentials: 'secret-sentinel' } }] };
  const svc = createStatusService({ registry, autoPoll: false, backends: { 'ai-vm': { status: async () => native } } });
  try {
    await Promise.all(Object.values(svc.caches).map(c => c.poll()));
    const result = await svc.app.inject({ url: '/api/status/v1/system', headers: { host: 'status.ai-harness' } });
    assert.equal(result.statusCode, 200);
    for (const forbidden of ['secret-sentinel', '/private/sentinel', 'socket_path', 'systemd_credential', 'credential_ref', 'transports', 'qualificationSha256']) assert.equal(result.body.includes(forbidden), false, forbidden);
    assert.equal(Object.values(SERVICE_IDS).flat().length, 7);
  } finally { await svc.app.close(); }
});

test('UI model labels are generic and read projected readiness with separate observed alias and conflict', () => {
  const modelDetails = new Function('s', statusJs.slice(statusJs.indexOf('function modelDetails(s){'), statusJs.indexOf('function render(data){')) + '\nreturn modelDetails(s);');
  const p = projected(ids[1]!);
  const dormant = p.services.find(s => s.service_id === ids[0])!;
  dormant.configured_model!.display_name = '<script>literal-label</script>';
  assert.ok(modelDetails(dormant).includes('Selection conflict: nonselected instance reports ready'));
  assert.ok(modelDetails(dormant).some((s: string) => s.includes('literal-label')));
  assert.ok(statusJs.includes('String(s.ready??"unknown")'));
  assert.ok(statusJs.includes('e.textContent=String(text)'));
  assert.equal(statusJs.includes('.innerHTML'), false);
  assert.equal(statusJs.includes('configured_context_tokens'), false); // Native legacy capacity is not advertised as configured UI capacity.
});
