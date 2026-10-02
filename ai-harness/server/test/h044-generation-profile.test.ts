import test from 'node:test';
import assert from 'node:assert/strict';
import {composeCodexHost} from '../src/codex-host.js';
import {codexReceiptSourceProfile,validateCodexLaunchReceipt} from '../src/codex-receipts.js';
import {receiptFixture} from './helpers/codex-receipt-fixture.js';
import {createCodexAutomaticRoute} from '../src/codex-automatic-routing.js';
import {createGateway} from '../src/gateway.js';
test('generation-only exact source/config profile preserves historical7/technical9 mounts and rejects ambiguous/arbitrary mounts',()=>{
 for(const technical of [false,true]){
  const f=receiptFixture(),binding={...f.binding,imageGenerationQualified:true as const,...(technical?{technicalVisionQualified:true as const}:{}),sources:Object.fromEntries(codexReceiptSourceProfile(technical,true).map(p=>[p,'b'.repeat(64)]))},v=structuredClone(f.rawLaunch);
  v.sources=binding.sources;v.container.mounts[4].source='/trusted/deploy/codex/config-generation-only.toml';
  if(technical)for(const name of ['technical-vision-mcp','technical-vision'])v.container.mounts.push({source:`/trusted/tools/technical-vision/${name}.mjs`,destination:`/opt/ai-harness/tools/technical-vision/${name}.mjs`,rw:false,type:'bind'});
  assert.equal(validateCodexLaunchReceipt(v,binding,f.producer,f.now).container.mounts.length,technical?9:7);
  assert.throws(()=>validateCodexLaunchReceipt(v,{...binding,imageJobsQualified:true},f.producer,f.now),/source profile/);
  const wrong=structuredClone(v);wrong.container.mounts[4].source='/trusted/deploy/codex/config-image-jobs.toml';assert.throws(()=>validateCodexLaunchReceipt(wrong,binding,f.producer,f.now));
  const extra=structuredClone(v);extra.container.mounts.push({source:'/arbitrary',destination:'/arbitrary',rw:false,type:'bind'});assert.throws(()=>validateCodexLaunchReceipt(extra,binding,f.producer,f.now));
 }
 assert.equal(receiptFixture().launch.container.mounts.length,7);
});
test('host generation flag independently admits creation without full image/edits/creative children and requires exact receipt closure',()=>{
 const q={protocolQualified:true as const,rootlessQualified:true as const,verifyLane:async()=>{throw Error('never inference');},imageGenerationQualified:true as const,nativeReceiptPolicy:{linuxTransportQualified:true as const,sourceSha256:Object.fromEntries(codexReceiptSourceProfile(false,true).map(p=>[p,'b'.repeat(64)]))}};
 const {runtime}=composeCodexHost('/trusted/deploy/run-codex.sh',()=>undefined,q);
 assert.equal(runtime.imageGenerationEnabled,true);assert.equal(runtime.imageToolEnabled,false);assert.equal(runtime.delegationEnabled,false);
 assert.match(runtime.automaticRouting!(createCodexAutomaticRoute({text:'Generate an image'}),'owned'),/image_generate/);
 assert.throws(()=>composeCodexHost('/trusted/deploy/run-codex.sh',()=>undefined,{...q,imageJobsQualified:true}),/Ambiguous/);
 assert.throws(()=>composeCodexHost('/trusted/deploy/run-codex.sh',()=>undefined,{...q,nativeReceiptPolicy:undefined}),/exact reviewed/);
});
test('normal Codex gateway accepts exact generation and refuses edit/unknown independently of existing status/cancel',async()=>{
 const calls:string[]=[],images={submit:async(_s:string,body:any)=>{calls.push(body.operation);return {id:'original'};},get:()=>({id:'original'}),cancel:()=>({id:'original',state:'running',cancelRequested:true}),capabilities:()=>({profiles:[{operation:'generation'},{operation:'edit'}]})};
 const g=createGateway({upstreamKey:'fixture-secret',images:images as any,codexImageGenerationQualified:true});
 try{const token=g.issueToken('owned','codex'),headers={authorization:'Bearer '+token};
  assert.equal((await g.app.inject({method:'POST',url:'/v1/image-jobs',headers,payload:{operation:'generation'}})).statusCode,200);
  for(const operation of ['edit','unknown'])assert.equal((await g.app.inject({method:'POST',url:'/v1/image-jobs',headers,payload:{operation}})).statusCode,403);
  assert.deepEqual((await g.app.inject({method:'GET',url:'/v1/image-capabilities',headers})).json().profiles,[{operation:'generation'}]);
  assert.deepEqual(calls,['generation']);assert.equal((await g.app.inject({method:'GET',url:'/v1/image-jobs/original',headers})).statusCode,200);
  assert.equal((await g.app.inject({method:'POST',url:'/v1/image-jobs/original/cancel',headers,payload:{}})).statusCode,200);
 }finally{await g.close();}
});

test('generation and technical scopes require independent exact closure while historical full remains explicit',()=>{
 const q={protocolQualified:true as const,rootlessQualified:true as const,verifyLane:async()=>{throw Error('not invoked');},imageGenerationQualified:true as const,technicalVisionQualified:true as const,nativeReceiptPolicy:{linuxTransportQualified:true as const,sourceSha256:Object.fromEntries(codexReceiptSourceProfile(true,true).map(p=>[p,'b'.repeat(64)]))}};
 const host=composeCodexHost('/trusted/deploy/run-codex.sh',()=>undefined,q);assert.equal(host.runtime.technicalVisionEnabled,true);assert.equal(host.runtime.imageGenerationEnabled,true);assert.equal(host.runtime.imageToolEnabled,false);
 assert.throws(()=>composeCodexHost('/trusted/deploy/run-codex.sh',()=>undefined,{...q,nativeReceiptPolicy:{...q.nativeReceiptPolicy,sourceSha256:Object.fromEntries(codexReceiptSourceProfile(false,true).map(p=>[p,'b'.repeat(64)]))}}),/source/);
});
