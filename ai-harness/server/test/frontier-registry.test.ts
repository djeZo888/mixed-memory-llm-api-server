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
    assert.ok(selected.services.find(s => frontier.includes(s.id) && s.id !== model)!.display_name.includes('dormant'));
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
  assert.equal(projection([{ ...meta, service_id: frontier[1], ready: true, availability: 'available' }]).health, 'ready');
  assert.equal(projection([{ ...meta, service_id: frontier[1], ready: false, availability: 'unavailable' }]).health, 'not_ready');
  assert.equal(projection([{ ...meta, freshness: 'stale', service_id: frontier[1], ready: true, availability: 'available' }]).health, 'unknown');
  const both = projectNode(sanitizeNode({ schema_version: 1, node_id: 'ai-vm', ...meta, services: [
    { ...meta, service_id: frontier[0], model_alias: frontier[0], ready: false, admitting: false, reason: 'unqualified', availability: 'unavailable' },
    { ...meta, service_id: frontier[1], model_alias: frontier[1], ready: true, admitting: true, availability: 'available' },
  ] }, 'ai-vm', frontier), config, selected).services;
  assert.equal(both.find(s => s.service_id === frontier[0])!.health, 'not_ready');
  assert.equal(both.find(s => s.service_id === frontier[0])!.admitting, false);
  assert.equal(both.find(s => s.service_id === frontier[1])!.health, 'ready');

});
