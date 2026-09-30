/** Review-only synthetic regressions. No backend calls, runtime changes or secrets. */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { selectRegistryFrontier, validateSystemRegistry } from '../../ai-harness/server/src/system-registry.js';
import { sanitizeNode } from '../../ai-harness/server/src/node-contract.js';
import { projectNode } from '../../ai-harness/server/src/status-projection.js';

const selectedModel = 'mimo-v2.6-pro-rl';
const otherModel = 'glm-5.3-flash';
const raw = () => JSON.parse(readFileSync(new URL('../../ai-harness/config/system-registry.json', import.meta.url), 'utf8'));
const meta = { state: 'ok', freshness: 'fresh', age_ms: 0, observed_at: '2026-09-28T04:00:00Z' };
function service(alias: string | null, serviceId = selectedModel) {
  const r = selectRegistryFrontier(validateSystemRegistry(raw()), selectedModel);
  const config = r.nodes.find(n => n.id === 'ai-vm')!;
  const ids = r.services.filter(s => s.node_id === config.id).map(s => s.observation_key);
  const node = sanitizeNode({ schema_version: 1, node_id: config.id, ...meta,
    services: [{ ...meta, service_id: serviceId, model_alias: alias, ready: true,
      admitting: true, availability: 'available' }] }, config.id, ids);
  return projectNode(node, config, r).services.find(s => s.service_id === serviceId)!;
}
test('configured label survives selecting the frontier', () => {
  const value = raw();
  value.services.find((s: any) => s.id === selectedModel).display_name = 'Reviewed catalog label';
  const r = selectRegistryFrontier(validateSystemRegistry(value), selectedModel);
  assert.equal(r.services.find(s => s.id === selectedModel)!.display_name, 'Reviewed catalog label');
});
test('wrong observed alias cannot certify the selected model', () => {
  assert.notEqual(service(otherModel).health, 'ready');
});
test('missing observed alias cannot certify the selected model', () => {
  assert.notEqual(service(null).health, 'ready');
});
test('a dormant frontier row cannot advertise active ready health', () => {
  assert.notEqual(service(otherModel, otherModel).health, 'ready');
});
