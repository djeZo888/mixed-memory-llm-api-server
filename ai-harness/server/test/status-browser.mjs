// Native synthetic browser fixture. Never imports production startup/nodeClient.
// Run after server build; uses existing installed Chrome with a fresh profile.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { chromium } from '../../web/node_modules/playwright/index.mjs';
import { DatabaseSync } from 'node:sqlite';
import { AdminActions } from '../dist/admin-actions.js';
import { createStatusService } from '../dist/status-service.js';
const fixture = JSON.parse(readFileSync(new URL('./fixtures/h005/node-status-v1.json', import.meta.url), 'utf8'));
const diskFixture = JSON.parse(readFileSync(new URL('./fixtures/h005/disk-volumes-v1.json', import.meta.url), 'utf8'));
const fresh = { state: 'ok', freshness: 'fresh', observed_at: new Date().toISOString(), age_ms: 0, reason: null };
let volumeFailure = false;
function snapshot(id) {
  const node = structuredClone(fixture);
  Object.assign(node, fresh, { node_id: id, boot_id: '37e425eb-3d3e-4070-80a0-5ecfb39604f1', generation: 2 });
  node.services = (id === 'ai-vm' ? ['qwen-gpu0', 'qwen-gpu1', 'image', 'control'] : ['harness', 'search', 'status']).map(service_id => ({ ...fresh, service_id, generation: 2, availability: service_id === 'qwen-gpu0' ? 'unavailable' : 'available', hardware_latched: service_id === 'qwen-gpu0', ready: service_id !== 'qwen-gpu0', admitting: service_id !== 'qwen-gpu0', activity: 'idle', active_requests: 0, queue_depth: 0, affected_services: [service_id] }));
  const GiB = 1024 ** 3;
  node.gpus = id === 'ai-vm' ? Array.from({length:4},(_,i)=>({ ...fresh,
    uuid: 'GPU-00000000-0000-0000-0000-00000000000'+(i+1), generation: 2,
    name: i===2?'Synthetic RTX 6000 Ada':'Synthetic RTX PRO 6000 Blackwell', index:i,
    memory_total_mib:i===2?49152:98304, memory_used_mib:i===3?0:40960,
    temperature_c:42+i, temperature_min_c:38+i, temperature_max_c:47+i,
    sampling_since:new Date(Date.now()-5*60*1000).toISOString(),
    power_draw_w:i===3?18:210, power_limit_w:i===2?300:600,
    ecc_mode:'enabled', ecc_uncorrected_volatile:0,
    pcie_generation:i===3?1:5, pcie_width:16, pcie_generation_max:5, pcie_width_max:16,
    affected_services:i===0?['qwen-gpu0']:i===1?['qwen-gpu1']:i===2?['image']:[],
  })):[];
  node.resources.memory = {...fresh,total_bytes:512*GiB,available_bytes:179.5*GiB,swap_total_bytes:8*GiB,swap_free_bytes:8*GiB,pressure_some_avg10:0.1,pressure_full_avg10:0};
  node.resources.disk = structuredClone(diskFixture);
  if(id==='ai-vm'&&volumeFailure){
    Object.assign(node.resources.disk.volumes.find(v=>v.volume_id==='data'),{freshness:'stale',age_ms:20000});
    Object.assign(node.resources.disk.volumes.find(v=>v.volume_id==='models'),{state:'unavailable',reason:'mount_identity_unavailable',total_bytes:null,available_bytes:null,read_bytes_per_second:null,write_bytes_per_second:null});
  }
  node.resources.network = {...fresh,rx_bytes_per_second:1.5*1024**2,tx_bytes_per_second:512*1024};
  node.resources.cpu = { ...fresh, percent: 2.3, logical_count: id === 'ai-vm' ? 72 : 8 };
  return node;
}
const calls = [], holds = new Set();
let failNextAction=false;
const db = new DatabaseSync(':memory:');
const freeze = {hold:a=>holds.add(a.idempotency_key),acknowledge:async()=>({}),release:a=>holds.delete(a.idempotency_key),settle:async()=>{},inspect:async()=>({frozen:holds.size>0,ready:true,activity:'unknown',active_requests:null,queue_depth:null})};
function backend(id) {return { status: async () => snapshot(id), action: async action => { calls.push(action);if(failNextAction){failNextAction=false;throw Error("synthetic lost response");}return { schema_version: 1, node_id: id, operation_id: 'fixture-operation', action: action.action, service_id:action.service_id??null,gpu_uuid:action.gpu_uuid??null,expected_boot_id:action.expected_boot_id,expected_generation:action.expected_generation,status: 'succeeded', affected_services: [action.service_id] }; }, operation: async () => ({ schema_version: 1, node_id: id, operation_id: 'fixture-operation', action: 'service.start', status: 'succeeded', affected_services: ['qwen-gpu0'] }) };}
const backends={'ai-vm':backend('ai-vm'),'ai-harness':backend('ai-harness')};
const actions=new AdminActions({db,freeze,backends,autoPoll:false});
const service = createStatusService({backends,actions,freeze,origins:['http://127.0.0.1:5197'],autoPoll:false});
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
  assert.equal(await page.locator('.gpu-table tr').count(),5);
  for(const text of ['UUID …00000001','UUID …00000004','Assigned: image','Unassigned','179.5 GiB / 512 GiB','16 GiB / 32 GiB','512 GiB / 1 TiB','1 TiB / 2 TiB','1.5 MiB/s'])assert.ok((await page.locator('#nodes').innerText()).includes(text),text);
  assert.ok(!(await page.locator('#nodes').innerText()).includes('[object Object]'));
  assert.equal(await page.locator('.volume-table tr').count(),8);
  assert.equal(await page.getByRole('heading',{name:'Registered volume roles'}).count(),2);
  if(process.argv[2])await page.screenshot({path:process.argv[2],fullPage:true});
  await page.setViewportSize({width:390,height:844});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth),false);
  if(process.argv[3])await page.screenshot({path:process.argv[3],fullPage:true});
  await page.setViewportSize({width:1280,height:1000});
  volumeFailure = true;
  await Promise.all(Object.values(service.caches).map(c=>c.poll()));
  await page.goto('http://127.0.0.1:5197/status');
  await page.getByText('Mount identity unavailable').waitFor();
  const volumes=page.locator('.volume-table').first();
  assert.match(await volumes.locator('tr').nth(2).innerText(),/ok · stale/);
  assert.match(await volumes.locator('tr').nth(3).innerText(),/Unknown \/ Unknown/);
  assert.ok(!(await volumes.locator('tr').nth(3).innerText()).includes('16 GiB'));
  await page.goto('http://127.0.0.1:5197/admin');
  await page.locator('#target option').nth(1).waitFor({state:'attached'});
  await page.locator('#target').selectOption({label:'ai-vm / qwen-gpu1'});
  await page.getByRole('button',{name:'Confirm action'}).click();
  await page.getByText(/Operation ai-vm~relay-.*: succeeded/).waitFor();
  assert.match(await page.locator('#impact').innerText(), /New dispatch paused: qwen-gpu1/);
  assert.ok(!(await page.locator('#impact').innerText()).includes('Harness aggregate work:'));
  assert.equal(calls.length,1);assert.match(calls[0].idempotency_key,/^[a-f0-9]{32}$/);
  await page.locator('#action').selectOption('service.restart');
  await page.getByRole('button',{name:'Confirm action'}).click();
  await page.getByText('Explicit interruption confirmation is required for this impact.').waitFor();
  assert.equal(calls.length,1);
  await page.locator('#interrupt').check();await page.getByRole('button',{name:'Confirm action'}).click();
  await page.waitForFunction(()=>document.getElementById('action-result').textContent.includes('succeeded'));
  assert.equal(calls.length,2);assert.equal(calls[1].action,'service.restart');assert.equal(calls[1].allow_interrupt,true);assert.equal(holds.size,0);assert.deepEqual(errors,[]);
  failNextAction=true;
  await page.locator('#action').selectOption('service.stop');
  await page.locator('#interrupt').check();
  await page.getByRole('button',{name:'Confirm action',exact:true}).click();
  await page.getByText(/Operation ai-vm~relay-.*: unknown/).waitFor();
  await page.locator('#recovery').waitFor({state:'visible'});
  assert.match(await page.locator('#recovery-impact').innerText(),/Boot: 37e425eb-3d3e-4070-80a0-5ecfb39604f1; generation: 2/);
  assert.equal(calls.length,3);assert.equal(holds.size,1);
  await page.getByRole('button',{name:'Confirm recovery restart',exact:true}).click();
  await page.getByText('Explicit interruption confirmation is required for recovery.').waitFor();
  assert.equal(calls.length,3);
  if(process.argv[4])await page.screenshot({path:process.argv[4],fullPage:true});
  await page.locator('#recover-interrupt').check();
  await page.getByRole('button',{name:'Confirm recovery restart',exact:true}).click();
  await page.getByText(/Operation ai-vm~relay-.*: succeeded/).waitFor();
  assert.equal(calls.length,4);assert.equal(calls[3].action,'service.restart');assert.equal(calls[3].expected_generation,2);assert.notEqual(calls[2].idempotency_key,calls[3].idempotency_key);assert.equal(holds.size,0);assert.deepEqual(errors,[]);
  console.log('PASS synthetic Chrome status/admin: typed start/restart, protected scoped freeze, explicit action and recovery confirmations, retained uncertain outcome, no replay or page errors');
} finally { await browser?.close();await service.app.close();db.close(); }
