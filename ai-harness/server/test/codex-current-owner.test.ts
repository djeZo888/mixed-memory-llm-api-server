import test from 'node:test';
import assert from 'node:assert/strict';
import {createProductionQwenVerifier,qwenPolicyReceipt,validateQwenReceipt} from '../src/codex-production.js';
const now=1790615400000;
function fixture(alias: 'qwen3.8-27b-gpu0'|'qwen3.8-27b') {
 const receipt=qwenPolicyReceipt(), p=receipt.lanes[alias];
 let boot='17ac5d50-a6a4-4df1-8f9e-7bfc3db5f125', generation=9, active='a'.repeat(64), drift:any={}, nodeDrift:any={}, serviceDrift:any={}, nativeDrift:any={};
 const service=()=>({service_id:p.serviceId,state:'ok',freshness:'fresh',age_ms:0,observed_at:new Date(now).toISOString(),generation:15,ready:true,hardware_latched:false,deployment_id:p.deploymentId,model_alias:alias,configured_context_tokens:480000,required_gpu_uuids:[p.gpuUuid],...serviceDrift});
 const get=async(url:string)=>url.endsWith('/node/status')?{schema_version:1,node_id:'ai-vm',boot_id:boot,state:'ok',freshness:'fresh',age_ms:0,observed_at:new Date(now).toISOString(),services:[service()],...nodeDrift}:url.endsWith('/server_info')?{status:'ready',version:'0.5.19',served_model_name:alias,context_length:480000,max_total_tokens:480000,max_total_num_tokens:480000,max_running_requests:1,default_chat_template_kwargs:{enable_thinking:false},tool_call_parser:'qwen3_coder',reasoning_parser:'qwen3',...nativeDrift}:{schema_version:2,slot:p.controlSlot,selected:p.deploymentId,observed_deployment:p.deploymentId,desired:'running',observed:'ready',container_running:true,observation_available:true,storage_available:true,state_persisted:true,generation_current:true,generation,active_identity:active,freshness:'fresh',observed_at:now/1000,mutation_busy:false,current_operation:null,endpoint:{base_url:p.nativeBaseUrl,served_model:alias,authentication_required:true,ready:true},...drift};
 const verify=createProductionQwenVerifier(receipt,{controlKey:'fixture-control',inferenceKey:'fixture-inference'},get,()=>now);
 return {receipt,verify,get, reboot(){boot='11111111-2222-4333-8444-555555555555';generation++;active='b'.repeat(64);},control(v:any){drift=v;},node(v:any){nodeDrift=v;},service(v:any){serviceDrift=v;},native(v:any){nativeDrift=v;}};
}
for(const alias of ['qwen3.8-27b-gpu0','qwen3.8-27b'] as const) {
 test(`${alias}: same immutable policy reattests after reboot without recording new IDs`,async()=>{
  const f=fixture(alias), before=await f.verify(alias);f.reboot();const after=await f.verify(alias);
  assert.notEqual(before.instanceId,after.instanceId);assert.equal(after.contextWindow,480000);
  assert.equal(JSON.stringify(f.receipt).includes('activeIdentity'),false);
 });
 test(`${alias}: owner source/readiness/generation, hardware and native drift stay closed`,async()=>{
  for(const change of [{generation_current:false},{observed:'failed'},{mutation_busy:true},{active_identity:'not-an-identity'},{selected:'unreviewed'}]) {const f=fixture(alias);f.control(change);await assert.rejects(f.verify(alias));}
  for(const change of [{required_gpu_uuids:['GPU-other']},{hardware_latched:null},{hardware_latched:true},{ready:false},{generation:null},{configured_context_tokens:1048576}]) {const f=fixture(alias);f.service(change);await assert.rejects(f.verify(alias));}
  for(const change of [{boot_id:null},{age_ms:15001},{freshness:'stale'},{observed_at:new Date(now-20000).toISOString()}]) {const f=fixture(alias);f.node(change);await assert.rejects(f.verify(alias));}
  const f=fixture(alias);f.native({max_total_num_tokens:262144});await assert.rejects(f.verify(alias));
 });
}
test('immutable endpoint/profile/source/UUID substitutions cannot become v2 policy',()=>{
 for(const key of ['nativeBaseUrl','controlUrl','gpuUuid','profileSha256','deploymentId']) {
  const r=qwenPolicyReceipt();(r.lanes['qwen3.8-27b'] as any)[key]='arbitrary';assert.throws(()=>validateQwenReceipt(r));
 }
 const r=qwenPolicyReceipt();r.ownerPolicy={...r.ownerPolicy!,modelManifestSha256:'0'.repeat(64)} as any;assert.throws(()=>validateQwenReceipt(r));
});
test('changed boot/container/generation during the native read is refused',async()=>{
 const f=fixture('qwen3.8-27b');const verify=createProductionQwenVerifier(f.receipt,{controlKey:'c',inferenceKey:'i'},async u=>{const value=await f.get(u);if(u.endsWith('/server_info'))f.reboot();return value;},()=>now);
 await assert.rejects(verify('qwen3.8-27b'));
});

test('deliberate MiMo children require host qualification and immutable model identity',async()=>{
 const {CodexChildren}=await import('../src/codex-children.js');
 const thread={id:'child-one',parentThreadId:'parent',modelProvider:'sova',model:'mimo-v2.6-pro-rl'};
 assert.throws(()=>new CodexChildren(()=>'parent',()=>{}).thread(thread));
 const events:any[]=[];const children=new CodexChildren(()=>'parent',e=>events.push(e),4,['qwen3.8-27b','mimo-v2.6-pro-rl']);children.thread(thread);assert.equal(events[0].name,'MiMo child');
 assert.throws(()=>children.thread({...thread,model:'qwen3.8-27b'}));
});
