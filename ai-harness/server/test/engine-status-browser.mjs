// Synthetic local fixture only: no production startup, node clients, models or inference.
import assert from 'node:assert/strict';
import { chromium } from '../../web/node_modules/playwright/index.mjs';
import { createStatusService } from '../dist/status-service.js';
import { loadSystemRegistry, selectRegistryFrontier } from '../dist/system-registry.js';
const registry=selectRegistryFrontier(loadSystemRegistry(),'mimo-v2.6-pro-rl');
let now=0;
const health={status:'ok',engines:{default:'minimax',
  minimax:{available:true,configured:true,version:null,preview:false,readiness:'not-probed',protocolQualified:null,capabilities:{text:true},capabilityDetails:{}},
  codex:{available:true,configured:true,version:'0.158.0',preview:true,readiness:'not-probed',protocolQualified:true,
    capabilities:{text:true,media:false,frontier:false},capabilityDetails:{coding:{supported:true,qualification:'live',reason:'Synthetic fixture representing reported qualification; no live work in this test'},image:{supported:false,qualification:'not_tested',reason:'Pending owned live acceptance'},nativeMedia:{supported:false,qualification:'not_tested',reason:'Native media remains unqualified'}}},
}};
const service=createStatusService({registry,backends:{},engineHealth:{status:async()=>health},autoPoll:false,now:()=>now,origins:['http://127.0.0.1:5198']});
await service.engineCache.poll();
let browser;
try{
  await service.app.listen({host:'127.0.0.1',port:5198});
  browser=await chromium.launch({channel:'chrome',headless:true});
  const page=await browser.newPage({viewport:{width:1280,height:1100}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
  // Existing UI polling cadence accelerated locally; no outbound backend configured.
  await page.addInitScript(()=>{const original=window.setInterval;window.setInterval=(fn,ms,...args)=>original(fn,ms===5000?100:ms,...args);});
  await page.goto('http://127.0.0.1:5198/status');
  const codex=page.locator('[data-engine-id="codex"]'),minimax=page.locator('[data-engine-id="minimax"]');
  await codex.getByText('Current selection enabled: true · Native startup readiness: unknown',{exact:true}).waitFor();
  assert.match(await minimax.innerText(),/Reported deployment version: unknown/);
  assert.match(await codex.innerText(),/native process version unobserved/);
  assert.match(await codex.innerText(),/not-probed/);
  assert.match(await codex.innerText(),/false \/ not_tested/);
  assert.match(await page.locator('#inventory').innerText(),/mimo-v2.6-pro-rl/);
  assert.match(await page.locator('#inventory').innerText(),/selection: selected/);
  if(process.argv[2])await page.locator('#engines').screenshot({path:process.argv[2]});
  // Endpoint transport failure must hide all CURRENT enablement, not merely badge stale.
  await page.route('**/api/status/v1/system',r=>r.abort());
  await codex.getByText('Current selection enabled: unknown · Native startup readiness: unknown',{exact:true}).waitFor();
  assert.match(await codex.innerText(),/Last app observation \(not current\)/);
  assert.match(await codex.innerText(),/Reported enabled: true/);
  assert.match(await codex.innerText(),/app-reported default: unknown/);
  assert.equal(await codex.locator('.badge.stale').count(),1);
  if(process.argv[3])await page.locator('#engines').screenshot({path:process.argv[3]});
  await page.unroute('**/api/status/v1/system');
  // Fresh but wrong policy version is visible and cannot advertise current selection.
  health.engines.codex.version='9.9.9';await service.engineCache.poll();
  await codex.locator('.badge.mismatch').waitFor();
  assert.match(await codex.innerText(),/Current selection enabled: unknown/);
  delete health.engines.minimax;await service.engineCache.poll();
  await minimax.locator('.badge.missing').waitFor();
  assert.match(await minimax.innerText(),/Engine not reported/);
  assert.deepEqual(errors,[]);
  console.log('PASS rendered synthetic Chrome status: configured vs app observations, unknown MiniMax/native version/readiness, capability qualification, missing/mismatch/stale transport suppression, selected MiMo preserved, no page errors');
}finally{await browser?.close();await service.app.close();}
