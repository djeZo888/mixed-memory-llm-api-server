// Native synthetic browser fixture. Never imports production startup/nodeClient.
// Run after server build; uses existing installed Chrome with a fresh profile.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { chromium } from '../../web/node_modules/playwright/index.mjs';
import { createStatusService } from '../dist/status-service.js';
const fixture = JSON.parse(readFileSync(new URL('./fixtures/h005/node-status-v1.json', import.meta.url), 'utf8'));
const fresh = { state: 'ok', freshness: 'fresh', observed_at: new Date().toISOString(), age_ms: 0, reason: null };
function snapshot(id) {
  const node = structuredClone(fixture);
  Object.assign(node, fresh, { node_id: id, boot_id: '37e425eb-3d3e-4070-80a0-5ecfb39604f1', generation: 2 });
  node.services = (id === 'ai-vm' ? ['qwen-gpu0', 'qwen-gpu1', 'image', 'control'] : ['harness', 'search', 'status']).map(service_id => ({ ...fresh, service_id, generation: 2, availability: service_id === 'qwen-gpu0' ? 'unavailable' : 'available', hardware_latched: service_id === 'qwen-gpu0', ready: service_id !== 'qwen-gpu0', admitting: service_id !== 'qwen-gpu0', activity: 'idle', active_requests: 0, queue_depth: 0, affected_services: [service_id] }));
  node.resources.cpu = { ...fresh, percent: 2.3, logical_count: id === 'ai-vm' ? 72 : 8 };
  return node;
}
const calls = [];
function backend(id) {return { status: async () => snapshot(id), action: async action => { calls.push(action);return { schema_version: 1, node_id: id, operation_id: 'fixture-operation', action: action.action, status: 'accepted', affected_services: [action.service_id] }; }, operation: async () => ({ schema_version: 1, node_id: id, operation_id: 'fixture-operation', action: 'service.start', status: 'succeeded', affected_services: ['qwen-gpu0'] }) };}
const service = createStatusService({backends:{'ai-vm':backend('ai-vm'),'ai-harness':backend('ai-harness')},origins:['http://127.0.0.1:5197'],autoPoll:false});
await Promise.all(Object.values(service.caches).map(c=>c.poll()));
let browser;
try {
  await service.app.listen({host:'127.0.0.1',port:5197});
  browser = await chromium.launch({channel:'chrome',headless:true});
  const page = await browser.newPage({viewport:{width:1280,height:1000}});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto('http://127.0.0.1:5197/status');
  await page.getByText('Hardware disabled for this boot').waitFor();
  assert.equal(await page.locator('#nodes .panel').count(),2);
  assert.equal(await page.locator('#action-form').count(),0);
  if(process.argv[2])await page.screenshot({path:process.argv[2],fullPage:true});
  await page.goto('http://127.0.0.1:5197/admin');
  await page.locator('#target option').nth(1).waitFor({state:'attached'});
  await page.locator('#target').selectOption({label:'ai-vm / qwen-gpu0'});
  await page.getByRole('button',{name:'Confirm action'}).click();
  await page.getByText('Operation ai-vm~fixture-operation: succeeded').waitFor();
  assert.equal(calls.length,1);assert.match(calls[0].idempotency_key,/^[a-f0-9]{32}$/);
  await page.locator('#action').selectOption('service.restart');
  await page.getByRole('button',{name:'Confirm action'}).click();
  await page.getByText('Explicit interruption confirmation is required for this impact.').waitFor();
  assert.equal(calls.length,1);
  await page.locator('#interrupt').check();await page.getByRole('button',{name:'Confirm action'}).click();
  await page.getByText(/requires the protected harness dispatch-freeze interlock/).waitFor();
  assert.equal(calls.length,1);assert.deepEqual(errors,[]);
  console.log('PASS synthetic Chrome status/admin: partial availability, no chat process, typed start, explicit interrupt and destructive422, no page errors');
} finally { await browser?.close();await service.app.close(); }
