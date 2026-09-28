import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { selectRegistryFrontier, validateSystemRegistry } from '../src/system-registry.js';
import { projectNode } from '../src/status-projection.js';
import { sanitizeNode } from '../src/node-contract.js';

const raw = () => JSON.parse(readFileSync(new URL('../../config/system-registry.json', import.meta.url), 'utf8'));
const frontier = ['glm-5.3-flash', 'mimo-v2.6-pro-rl'];
test('retained frontier identities retain both visible rows without relabeling identities or altering Qwen/image', () => {
  const registry = validateSystemRegistry(raw());
  assert.deepEqual(registry.services.filter(s => frontier.includes(s.id)).map(s => [s.id, s.observation_key]), frontier.map(id => [id, id]));
  for (const model of frontier) {
    const selected = selectRegistryFrontier(registry, model);
    assert.deepEqual(selected.services.filter(s => frontier.includes(s.id)).map(s => [s.id,s.observation_key]), frontier.map(id => [id,id]));
    assert.deepEqual(selected.services.filter(s => !frontier.includes(s.id)), registry.services.filter(s => !frontier.includes(s.id)));
    assert.equal(selected.services.filter(s => s.endpoint_ref === 'frontier-private').length, 2);
    assert.equal(selected.selected_frontier, model);
    assert.deepEqual(selected.services, registry.services);
  }
  assert.equal(registry.services.find(s => s.id === frontier[1])!.display_name, 'MiMo V2.6 Pro-RL');
  assert.equal(registry.services.filter(s => frontier.includes(s.id)).length, 2);

  for (const key of ['id', 'observation_key', 'node_id', 'endpoint_ref']) {
    const value = raw(), row = value.services.find((s: any) => s.id === frontier[1]);
    row[key] = key === 'observation_key' ? frontier[0] : key === 'node_id' ? 'ai-harness' : key === 'endpoint_ref' ? 'qwen-gpu0-private' : 'renamed-mimo';
    assert.throws(() => validateSystemRegistry(value));
  }
});
test('MiMo readiness requires exact fresh canonical node observation; GLM ready cannot supply it', () => {
  const selected = selectRegistryFrontier(validateSystemRegistry(raw()), frontier[1]!);
  const config = selected.nodes.find(n => n.id === 'ai-vm')!;
  const meta = { state: 'ok', freshness: 'fresh', age_ms: 0, observed_at: '2026-09-27T15:00:00Z' };
  const projection = (services: any[]) => projectNode(sanitizeNode({ schema_version: 1, node_id: 'ai-vm', ...meta, services }, 'ai-vm', frontier), config, selected).services.find(s => s.service_id === frontier[1])!;
  assert.equal(projection([{ ...meta, service_id: frontier[0], ready: true, availability: 'available' }]).health, 'unknown');
  assert.equal(projection([{ ...meta, service_id: frontier[1], model_alias: frontier[1], ready: true, availability: 'available' }]).health, 'ready');
  assert.equal(projection([{ ...meta, service_id: frontier[1], model_alias: frontier[1], ready: false, availability: 'unavailable' }]).health, 'not_ready');
  assert.equal(projection([{ ...meta, freshness: 'stale', service_id: frontier[1], model_alias: frontier[1], ready: true, availability: 'available' }]).health, 'unknown');
  const both = projectNode(sanitizeNode({ schema_version: 1, node_id: 'ai-vm', ...meta, services: [
    { ...meta, service_id: frontier[0], model_alias: frontier[0], ready: false, admitting: false, reason: 'unqualified', availability: 'unavailable' },
    { ...meta, service_id: frontier[1], model_alias: frontier[1], ready: true, admitting: true, availability: 'available' },
  ] }, 'ai-vm', frontier), config, selected).services;
  assert.equal(both.find(s => s.service_id === frontier[0])!.health, 'unknown');
  assert.equal(both.find(s => s.service_id === frontier[0])!.admitting, null);
  assert.equal(both.find(s => s.service_id === frontier[1])!.health, 'ready');

});

const meta = { state: 'ok', freshness: 'fresh', age_ms: 0, observed_at: '2026-09-28T04:00:00Z' };
const gpu = 'GPU-00000000-0000-0000-0000-000000000001';
function project(registry: ReturnType<typeof validateSystemRegistry>, services: any[], options: any = {}) {
  const config = registry.nodes[0]!;
  return projectNode(sanitizeNode({ schema_version: 1, node_id: config.id, ...meta,
    services, gpus: [{ ...meta, uuid: gpu, name: 'Measured GPU', affected_services: frontier }], ...options,
  }, config.id, registry.services.filter(s => s.node_id === config.id).map(s => s.observation_key)), config, registry);
}
const observed = (service_id: string, model_alias: string | null = service_id) => ({ ...meta,
  service_id, model_alias, deployment_id: 'observed-instance', ready: true, admitting: true,
  availability: 'available', required_gpu_uuids: [gpu],
});
test('custom configured labels and both frontier selections stay separate from observed identities and impact scope', () => {
  for (const model of frontier) {
    const custom = raw();
    custom.nodes[0].display_name = 'Custom compute host';
    for (const s of custom.services) {
      s.display_name = 'Custom service ' + s.id;
      if (s.model) { s.model.display_name = 'Custom model ' + s.id; s.model.instance_name = 'Instance ' + s.id; }
    }
    const registry = selectRegistryFrontier(validateSystemRegistry(custom), model);
    const actual = project(registry, frontier.map(id => ({ ...observed(id), ready: id === model })));
    const active = actual.services.find(s => s.service_id === model)!;
    const dormant = actual.services.find(s => frontier.includes(s.service_id) && s.service_id !== model)!;
    assert.equal(actual.display_name, 'Custom compute host');
    assert.equal(active.display_name, 'Custom service ' + model);
    assert.equal(active.configured_model!.display_name, 'Custom model ' + model);
    assert.equal(active.configured_model!.instance_name, 'Instance ' + model);
    assert.equal(actual.selected_frontier, model);
    assert.equal(active.selection, 'selected'); assert.equal(active.identity_status, 'matched');
    assert.equal(active.observed_model.model_alias, model); assert.equal(active.health, 'ready');
    assert.equal(dormant.selection, 'dormant'); assert.equal(dormant.current_state, 'dormant');
    assert.equal(dormant.health, 'unknown'); assert.equal(dormant.ready, null);
    assert.deepEqual(actual.gpus[0]!.affected_services, frontier); // Never rewrite action impact.
    assert.deepEqual(actual.gpus[0]!.observed_ready_dependents.map(s => s.service_id), [model]);
    assert.equal(actual.gpus[0]!.uuid, gpu);
  }
});
test('missing, stale, mismatched, unavailable and unselected evidence cannot certify configured model or GPU dependency', () => {
  const model = frontier[1]!;
  const registry = selectRegistryFrontier(validateSystemRegistry(raw()), model);
  for (const [row, expected] of [
    [null, 'unavailable'], [observed(model, null), 'unknown'],
    [observed(model, frontier[0]), 'mismatch'],
    [{ ...observed(model), freshness: 'stale' }, 'stale'],
    [{ ...observed(model), state: 'timeout' }, 'unavailable'],
  ] as const) {
    const actual = project(registry, row ? [row] : []);
    const service = actual.services.find(s => s.service_id === model)!;
    assert.equal(service.identity_status, expected);
    if (!row) { assert.equal(service.observed_model.node_id, null); assert.equal(service.observed_model.service_id, null); }
    assert.equal(service.health, 'unknown'); assert.equal(service.ready, null); assert.equal(service.admitting, null);
    assert.deepEqual(actual.gpus[0]!.observed_ready_dependents, []);
  }
  const staleNode = project(registry, [observed(model)], { freshness: 'stale' });
  assert.equal(staleNode.services.find(s => s.service_id === model)!.identity_status, 'stale');
  assert.deepEqual(staleNode.gpus[0]!.observed_ready_dependents, []);
  const staleGpu = project(registry, [observed(model)], { gpus: [{ ...meta, freshness: 'stale', uuid: gpu }] });
  assert.deepEqual(staleGpu.gpus[0]!.observed_ready_dependents, []);
  const missingGpu = project(registry, [observed(model)], { gpus: [] });
  assert.deepEqual(missingGpu.gpus, []); // A required UUID cannot invent measured hardware.
  const unselectedNode = project(validateSystemRegistry(raw()), [observed(model)]);
  assert.deepEqual(unselectedNode.gpus[0]!.observed_ready_dependents, []);
  const unknownSelection = unselectedNode.services.find(s => s.service_id === model)!;
  assert.equal(unknownSelection.selection, 'unknown'); assert.equal(unknownSelection.ready, null);
  const conflictNode = project(registry, frontier.map(id => observed(id)));
  assert.deepEqual(conflictNode.gpus[0]!.observed_ready_dependents.map(s => s.service_id), [model]);
  const conflicting = conflictNode.services.find(s => s.service_id === frontier[0])!;
  assert.equal(conflicting.selection_conflict, true);
  assert.equal(conflicting.current_state, 'dormant'); assert.equal(conflicting.health, 'unknown');
  assert.equal(conflicting.observed_model.ready, true); // Explicit observer evidence remains separate from current health.
});
test('Qwen instances keep distinct configured aliases, observed deployments and UUIDs; unsupported nodes remain visible', () => {
  const registry = validateSystemRegistry(raw());
  const secondGpu = gpu.replace(/1$/, '2');
  const actual = project(registry, [observed('qwen-gpu0', 'qwen3.8-27b-gpu0'),
    { ...observed('qwen-gpu1', 'qwen3.8-27b'), deployment_id: 'second-instance', required_gpu_uuids: [secondGpu] }],
    { gpus: [gpu, secondGpu].map(uuid => ({ ...meta, uuid })) });
  const qwen = actual.services.filter(s => s.service_id.startsWith('qwen-'));
  assert.deepEqual(qwen.map(s => s.health), ['ready', 'ready']);
  assert.deepEqual(qwen.map(s => s.observed_model.deployment_id), ['observed-instance', 'second-instance']);
  assert.deepEqual(actual.gpus.map(g => g.observed_ready_dependents.map(s => s.service_id)), [['qwen-gpu0'], ['qwen-gpu1']]);
  registry.nodes.push({ id: 'unsupported', display_name: 'Planned host', observation: { adapter: 'unsupported', transport: null } });
  registry.services.push({ ...registry.services[0]!, id: 'third-qwen', node_id: 'unsupported', observation_key: 'third-qwen' });
  const config = registry.nodes.at(-1)!;
  const missing = projectNode(sanitizeNode({ schema_version: 1, node_id: config.id }, config.id), config, validateSystemRegistry(registry));
  assert.equal(missing.display_name, 'Planned host'); assert.equal(missing.services[0]!.health, 'unknown');
  assert.deepEqual(missing.gpus, []);
  const wrongNode = { schema_version: 1, node_id: 'another', services: [observed('qwen-gpu0')] };
  assert.throws(() => sanitizeNode(wrongNode, 'ai-vm'), /Invalid node snapshot/);
});
