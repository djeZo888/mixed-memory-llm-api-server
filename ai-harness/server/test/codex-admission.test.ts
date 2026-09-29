import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, realpathSync, readFileSync, rmSync, statSync, symlinkSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createProductionQwenVerifier, qwenPolicyReceipt } from '../src/codex-production.js';
import { createQwenAdmissionDiagnostics } from '../src/codex-diagnostics.js';
import { composeCodexHost } from '../src/codex-host.js';
import { QWEN_CODEX_PIN } from '../src/codex-qwen.js';
import { QwenAdmissionError, type QwenAdmissionDiagnostic } from '../src/codex-admission.js';
const requestId = '1dd5841e-0e5b-4a72-9b6f-1a279ec50931';
const alias = 'qwen3.8-27b', now = 1790643600000;
function fixture() {
  const receipt = qwenPolicyReceipt(), p = receipt.lanes[alias];
  const control:any = {schema_version:2,slot:p.controlSlot,selected:p.deploymentId,observed_deployment:p.deploymentId,desired:'running',observed:'ready',container_running:true,observation_available:true,storage_available:true,state_persisted:true,generation_current:true,generation:9,active_identity:'a'.repeat(64),freshness:'fresh',observed_at:now/1000,mutation_busy:false,current_operation:null,endpoint:{base_url:p.nativeBaseUrl,served_model:alias,authentication_required:true,ready:true}};
  const service:any = {service_id:p.serviceId,state:'ok',freshness:'fresh',age_ms:0,observed_at:new Date(now).toISOString(),generation:15,ready:true,hardware_latched:false,deployment_id:p.deploymentId,model_alias:alias,configured_context_tokens:480000,required_gpu_uuids:[p.gpuUuid]};
  const node:any = {schema_version:1,node_id:'ai-vm',boot_id:'11111111-2222-4333-8444-555555555555',state:'ok',freshness:'fresh',age_ms:0,observed_at:new Date(now).toISOString(),services:[service]};
  const native:any = {status:'ready',version:'0.5.19',served_model_name:alias,context_length:480000,max_total_tokens:480000,max_total_num_tokens:480000,max_running_requests:1,default_chat_template_kwargs:{enable_thinking:false},tool_call_parser:'qwen3_coder',reasoning_parser:'qwen3'};
  const events:QwenAdmissionDiagnostic[]=[];
  const get = async(url:string) => url.endsWith('/node/status') ? node : url.endsWith('/server_info') ? native : control;
  const verify=createProductionQwenVerifier(receipt,{controlKey:'PRIVATE_CONTROL',inferenceKey:'PRIVATE_INFERENCE'},get,()=>now,e=>events.push(e));
  return {control,node,service,native,events,verify,get,receipt};
}
test('each actual rejected predicate has a static reason, correlated phase and bounded timing',async()=>{
  const cases = [
    ['control','schema_version',0,'control_schema'], ['control','selected','other','selected_profile'],
    ['control','container_running',false,'runtime_state'],['control','state_persisted',false,'storage_state'],
    ['control','generation_current',false,'generation'],['control','active_identity','changed','runtime_identity'],
    ['control','freshness','stale','freshness'],['control','mutation_busy',true,'operation_pending'],
    ['control','endpoint',null,'endpoint_policy'],['control','observed','failed','owner_ready'],
    ['node','node_id','other','node_schema'],['node','boot_id',null,'boot_identity'],
    ['node','services',[],'service_identity'],['service','hardware_latched',null,'hardware_state'],
    ['service','configured_context_tokens',200000,'token_capacity'],['native','version','wrong','native_profile'],
    ['native','max_total_tokens',200000,'token_capacity'],
  ] as const;
  for(const [where,field,value,reason] of cases){
    const f=fixture();(f[where] as any)[field]=value;
    await assert.rejects(f.verify(alias,{requestId,phase:'count'}),(error:any)=>error.reason===reason);
    const rejected=f.events.at(-1)!;
    assert.equal(rejected.reason,reason);assert.equal(rejected.outcome,'reject');assert.equal(rejected.requestId,requestId);assert.equal(rejected.phase,'count');assert.equal(rejected.lane,alias);
    assert.ok(Number.isFinite(rejected.elapsedMs)&&rejected.elapsedMs>=0);
    assert.doesNotMatch(JSON.stringify(f.events),/PRIVATE_CONTROL|PRIVATE_INFERENCE/);
  }
});
test('transport exception text cannot enter a diagnostic; observers cannot change qualification',async()=>{
  const f=fixture(),events:any[]=[];
  const verify=createProductionQwenVerifier(f.receipt,{controlKey:'c',inferenceKey:'i'},async()=>{throw Error('SECRET_PROMPT');},()=>now,e=>events.push(e));
  await assert.rejects(verify(alias,{requestId,phase:'admission'}),(e:any)=>e.reason==='transport');
  assert.equal(events[0].reason,'transport');assert.doesNotMatch(JSON.stringify(events),/SECRET_PROMPT/);
  const noisy=createProductionQwenVerifier(f.receipt,{controlKey:'c',inferenceKey:'i'},f.get,()=>now,()=>{throw Error('observer');});
  assert.equal((await noisy(alias)).alias,alias);
});
test('a failed parallel lane is logged and does not disable the healthy lane',async()=>{
  const events:any[]=[], contexts:any[]=[];
  const host=composeCodexHost('/trusted/run-codex.sh',()=>undefined,{protocolQualified:true,rootlessQualified:true,onAdmissionDiagnostic:e=>events.push(e),verifyLane:async(a,c)=>{contexts.push(c);if(a.endsWith('gpu0'))throw new QwenAdmissionError('freshness');return {...QWEN_CODEX_PIN,alias:a,instanceId:'current'};}});
  assert.deepEqual(await host.responses!.currentAliases({requestId,phase:'admission'}),[alias]);
  assert.equal(events.length,2);assert.equal(events.find(e=>e.outcome==='reject').reason,'freshness');
  assert.ok(contexts.every(c=>c.requestId===requestId));
});
test('current log projects only static fields and enforces protected bounded rotation',t=>{
  const dir=mkdtempSync(join(realpathSync(tmpdir()),'h029-admission-'));t.after(()=>rmSync(dir,{recursive:true,force:true}));
  const path=join(dir,'admission.jsonl'),log=createQwenAdmissionDiagnostics(path);
  const event={schema:1,requestId,lane:alias,phase:'admission',step:'lane',outcome:'reject',reason:'freshness',elapsedMs:2.5} as const;
  for(let i=0;i<700;i++)log({...event,prompt:'PRIVATE_PROMPT',error:Error('PRIVATE_ERROR')} as any);
  for(const p of [path,path+'.1']){const text=readFileSync(p,'utf8');assert.doesNotMatch(text,/PRIVATE_PROMPT|PRIVATE_ERROR/);assert.ok(statSync(p).size<=65536);assert.equal(statSync(p).mode&0o777,0o600);}
  const before=readFileSync(path,'utf8');
  for(const field of ['requestId','lane','phase','step','outcome','reason','elapsedMs'])log({...event,[field]:'SECRET_INJECTION'} as any);
  assert.equal(readFileSync(path,'utf8'),before);
  const target=join(dir,'target');writeFileSync(target,'untouched');symlinkSync(target,join(dir,'symlink'));
  createQwenAdmissionDiagnostics(join(dir,'symlink'))(event);assert.equal(readFileSync(target,'utf8'),'untouched');
});

test('hardware predicate evidence preserves null, false, true, missing and exact UUID mismatch without relaxing rejection',async()=>{
 for(const latch of [null,true,false,undefined,'PRIVATE_ERROR']){
  const f=fixture();
  if(latch===undefined)delete f.service.hardware_latched;else f.service.hardware_latched=latch;
  if(latch===false) f.service.required_gpu_uuids=['GPU-88058d9d-08e5-cb1e-a77a-04cbc1488237'];
  await assert.rejects(f.verify(alias,{requestId,phase:'count'}),(e:any)=>e.reason==='hardware_state');
  const event=f.events.at(-1)!;
  assert.equal(event.step,'node_before');assert.equal(event.reason,'hardware_state');
  assert.equal(event.hardware?.hardwareLatched,latch===undefined?'missing':latch==='PRIVATE_ERROR'?'invalid':latch);
  assert.equal(event.hardware?.gpuUuidMatch,latch!==false);
  assert.deepEqual(event.hardware?.requiredGpuUuids,f.service.required_gpu_uuids);
  assert.equal(event.hardware?.hardwareValidationAgeMs,null); // Current node schema does not expose this proof age.
  assert.equal(event.hardware?.serviceGeneration,15);
  assert.doesNotMatch(JSON.stringify(event),/PRIVATE_ERROR|PRIVATE_CONTROL|PRIVATE_INFERENCE/);
 }
});
test('hardware diagnostics project only bounded trusted fields to protected retained logs',async t=>{
 const f=fixture();f.service.hardware_latched=null;
 f.service.hardware_validation_age_ms=15500; f.service.hardware_validated_boot_id=f.node.boot_id;
 f.service.hardware_validated_gpu_uuids=f.service.required_gpu_uuids;
 await assert.rejects(f.verify(alias,{requestId,phase:'count'}));
 const dir=mkdtempSync(join(realpathSync(tmpdir()),'h030-hardware-'));t.after(()=>rmSync(dir,{recursive:true,force:true}));
 const path=join(dir,'hardware.jsonl'),log=createQwenAdmissionDiagnostics(path),event=f.events.at(-1)!;
 log({...event,hardware:{...event.hardware,prompt:'PRIVATE_PROMPT',reason:'PRIVATE_REMOTE_REASON',requiredGpuUuids:['PRIVATE_UUID'],bootId:'PRIVATE_BOOT',nodeAgeMs:Infinity}} as any);
 const text=readFileSync(path,'utf8'),stored=JSON.parse(text);
 assert.equal(stored.reason,'hardware_state');assert.equal(stored.hardware.hardwareLatched,null);
 assert.equal(stored.hardware.hardwareValidationAgeMs,15500);assert.equal(stored.hardware.requiredGpuUuids,null);
 assert.equal(stored.hardware.nodeAgeMs,null);assert.equal(stored.hardware.bootId,null);
 assert.doesNotMatch(text,/PRIVATE_/);assert.equal(statSync(path).mode&0o777,0o600);
});
