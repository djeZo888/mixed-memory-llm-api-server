/** Review-only synthetic contract fixtures; all observers are in-memory. */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { selectRegistryFrontier, validateSystemRegistry } from '../../ai-harness/server/src/system-registry.js';
import { createStatusService } from '../../ai-harness/server/src/status-service.js';

const raw = () => JSON.parse(readFileSync(new URL('../../ai-harness/config/system-registry.json', import.meta.url), 'utf8'));
const meta = { state: 'ok', freshness: 'fresh', age_ms: 0, observed_at: '2026-09-28T04:00:00Z' };
const uuidA = 'GPU-11111111-1111-1111-1111-111111111111';
const uuidB = 'GPU-22222222-2222-2222-2222-222222222222';

test('unknown selection fails without silently defaulting to GLM', () => {
  assert.throws(() => selectRegistryFrontier(validateSystemRegistry(raw()), 'unregistered-model'));
});
test('reordered unsupported node and same-model instances remain separate; observed UUIDs are not ordinal joins', async () => {
  const r = raw();
  r.nodes.unshift({ id: 'offline', display_name: 'Optional host', observation: { adapter: 'unsupported', transport: null } });
  r.services.push({ id: 'offline-instance', node_id: 'offline', display_name: 'Offline instance', observation_key: 'offline-slot', owner: 'fixture', capabilities: [], endpoint_ref: null });
  for (const [id, key] of [['instance-a', 'slot-a'], ['instance-b', 'slot-b']])
    r.services.push({ id, node_id: 'ai-vm', display_name: 'Same model label', observation_key: key, owner: 'fixture', capabilities: ['chat.completions'], endpoint_ref: null });
  const registry = validateSystemRegistry(r);
  const dto = { schema_version: 1, node_id: 'ai-vm', ...meta,
    services: [
      { ...meta, service_id: 'slot-a', model_alias: 'shared-model', deployment_id: 'instance-a-deployment', required_gpu_uuids: [uuidB], ready: true },
      { ...meta, service_id: 'slot-b', model_alias: 'shared-model', deployment_id: 'instance-b-deployment', required_gpu_uuids: [uuidA], ready: false },
    ],
    gpus: [{ ...meta, uuid: uuidB, index: 0, name: 'Measured GPU B' }, { ...meta, uuid: uuidA, index: 1, name: 'Measured GPU A' }],
  };
  const service = createStatusService({ registry, autoPoll: false, backends: { 'ai-vm': { status: async () => dto } } });
  try {
    await Promise.all(Object.values(service.caches).map(c => c.poll()));
    const nodes = service.snapshot();
    assert.deepEqual(nodes.map(n => n.node_id), registry.nodes.map(n => n.id));
    assert.equal(nodes[0]!.services[0]!.service_id, 'offline-instance');
    assert.equal(nodes[0]!.services[0]!.health, 'unknown');
    const vm = nodes.find(n => n.node_id === 'ai-vm')!;
    const a = vm.services.find(s => s.service_id === 'instance-a')!;
    const b = vm.services.find(s => s.service_id === 'instance-b')!;
    assert.equal(a.model_alias, b.model_alias);
    assert.notEqual(a.deployment_id, b.deployment_id);
    assert.deepEqual(a.required_gpu_uuids, [uuidB]);
    assert.deepEqual(b.required_gpu_uuids, [uuidA]);
    assert.equal(a.health, 'ready'); assert.equal(b.health, 'not_ready');
    assert.deepEqual(vm.gpus.map(g => [g.uuid, g.index]), [[uuidB, 0], [uuidA, 1]]);
    const targets = await service.app.inject({ url: '/api/admin/v1/targets', headers: { host: '10.156.100.61' } });
    assert.deepEqual(targets.json().targets, []);
  } finally { await service.app.close(); }
});
