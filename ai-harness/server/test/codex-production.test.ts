import test from 'node:test';
import assert from 'node:assert/strict';
import {createProductionQwenVerifier,QWEN_SOURCE_PIN,validateQwenReceipt} from '../src/codex-production.js';
import {QWEN_CODEX_PIN} from '../src/codex-qwen.js';
const alias='qwen3.8-27b-gpu0', activeIdentity='a'.repeat(64);
const receipt={schema:1,source:{...QWEN_CODEX_PIN,...QWEN_SOURCE_PIN},lanes:{[alias]:{controlUrl:"http://10.156.100.60:30000/control/v1/status/glm",controlSlot:"glm",nativeBaseUrl:"http://10.156.100.60:30002/v1",deploymentId:"qwen38-27b-q0-480000-yarn4-bf16kv",activeIdentity,generation:54,containerId:'b'.repeat(64),startedAt:'2026-09-27T07:23:02.292Z'}}};
const identity=()=>({schema_version:2,slot:'glm',selected:'qwen38-27b-q0-480000-yarn4-bf16kv',observed_deployment:'qwen38-27b-q0-480000-yarn4-bf16kv',desired:'running',container_running:true,observation_available:true,storage_available:true,state_persisted:true,generation_current:true,generation:54,active_identity:activeIdentity,freshness:'fresh',observed_at:100,mutation_busy:false,current_operation:null,endpoint:{base_url:'http://10.156.100.60:30002/v1',served_model:alias,authentication_required:true}});
const native=()=>({status:'ready',version:'0.5.19',served_model_name:alias,context_length:480000,max_total_tokens:480000,max_total_num_tokens:480000,max_running_requests:1,default_chat_template_kwargs:{enable_thinking:false},tool_call_parser:'qwen3_coder',reasoning_parser:'qwen3'});
test('production qualifier uses source receipt, exact Qwen slot identity and real allocation with no SSH',async()=>{
 const seen:string[]=[];const verify=createProductionQwenVerifier(receipt,{controlKey:'host-control',inferenceKey:'host-inference'},async(url,key)=>{seen.push(url);assert.equal(key,url.endsWith('/server_info')?'host-inference':'host-control');return url.endsWith('/server_info')?native():identity();},()=>100000);
 assert.equal((await verify(alias)).contextWindow,480000);assert.deepEqual(seen,['http://10.156.100.60:30000/control/v1/status/glm','http://10.156.100.60:30002/server_info','http://10.156.100.60:30000/control/v1/status/glm']);
 await assert.rejects(verify('qwen3.8-27b'));await assert.rejects(verify('mimo-v2.6-pro-rl'));await assert.rejects(verify('__proto__'));await assert.rejects(verify('constructor'));
});
test('restart while checking allocation invalidates the immutable deployment receipt',async()=>{
 let calls=0;const verify=createProductionQwenVerifier(receipt,{controlKey:'c',inferenceKey:'i'},async url=>url.endsWith('/server_info')?native():({...identity(),active_identity:++calls===1?activeIdentity:'c'.repeat(64)}),()=>100000);
 await assert.rejects(verify(alias));assert.equal(calls,2);
});
test('declared context cannot substitute for native allocation, freshness, or current persisted generation',async()=>{
 for(const drift of ['allocation','stale','generation','busy']) {
 const verify=createProductionQwenVerifier(receipt,{controlKey:'c',inferenceKey:'i'},async url=>url.endsWith('/server_info')?({...native(),max_total_num_tokens:drift==='allocation'?262144:480000}):({...identity(),observed_at:drift==='stale'?1:100,generation_current:drift!=='generation',mutation_busy:drift==='busy'}),()=>100000);await assert.rejects(verify(alias));
 }
 assert.throws(()=>validateQwenReceipt({...receipt,source:{...receipt.source,templateSha256:'0'.repeat(64)}}));
});
