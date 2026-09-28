import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,mkdirSync,writeFileSync,readFileSync,rmSync,readdirSync,chmodSync} from 'node:fs';
import {join} from 'node:path';
import {randomUUID} from 'node:crypto';
import {createHostOwnedAcceptance} from '../src/owned-acceptance.js';
function fixture() {
 const dir=mkdtempSync(join(process.cwd(),'.owned-acceptance-'));chmodSync(dir,0o700);
 const policy=join(dir,'policy.json'),sid=randomUUID(),rid=randomUUID(),id=randomUUID();let now=1000,active:string|undefined;
 const ticket={id,sessionId:sid,expiresAt:10000,image:true,frontier:false};mkdirSync(join(dir,id),{mode:0o700});
 const write=(tickets:unknown[])=>writeFileSync(policy,JSON.stringify({schema:1,tickets}),{mode:0o600});write([ticket]);
 const manager=createHostOwnedAcceptance(policy,s=>s===sid?active:undefined,()=>now);
 return {dir,policy,sid,rid,id,ticket,write,manager,setActive:(v?:string)=>active=v,setNow:(v:number)=>now=v,close:()=>{manager.close();rmSync(dir,{recursive:true,force:true});}};
}
test('private ticket binds actual accepted UUID before running, captures exact owner, never rebinds same ticket',()=>{
 const f=fixture();try{f.manager.onRunAccepted(f.sid,f.rid);const binding=JSON.parse(readFileSync(join(f.dir,f.id,'binding.json'),'utf8'));assert.equal(binding.runId,f.rid);assert.equal(f.manager.image(f.sid),false);f.setActive(f.rid);assert.equal(f.manager.image(f.sid),true);assert.equal(f.manager.frontier(f.sid),false);assert.equal(f.manager.image(randomUUID()),false);
 f.manager.capture({requestId:randomUUID(),sessionId:f.sid,model:'qwen3.8-27b',phase:'pre_normalization',bytes:Buffer.from('exact private input')});assert(readdirSync(join(f.dir,f.id)).some(n=>n.endsWith('.bin')));
 f.manager.onRunFinished(f.sid,f.rid);f.setActive(randomUUID());f.manager.onRunAccepted(f.sid,f.rid);assert.equal(f.manager.image(f.sid),false);assert.equal(JSON.parse(readFileSync(join(f.dir,f.id,'binding.json'),'utf8')).runId,f.rid);
 const restart=createHostOwnedAcceptance(f.policy,()=>f.rid,()=>1000);restart.onRunAccepted(f.sid,f.rid);assert.equal(restart.image(f.sid),false);restart.close();}finally{f.close();}
});
test('policy removal, expiry and mismatched Store run revoke new capability',()=>{
 for(const action of ['remove','expire','run'] as const){const f=fixture();try{f.manager.onRunAccepted(f.sid,f.rid);f.setActive(f.rid);assert(f.manager.image(f.sid));if(action==='remove')f.write([]);if(action==='expire')f.setNow(10000);if(action==='run')f.setActive(randomUUID());assert.equal(f.manager.image(f.sid),false);}finally{f.close();}}
});
test('invalid or task-writable policy never grants permission',()=>{
 const f=fixture();try{chmodSync(f.policy,0o666);assert.throws(()=>createHostOwnedAcceptance(f.policy,()=>f.rid,()=>1000));f.manager.onRunAccepted(f.sid,f.rid);assert.equal(f.manager.image(f.sid),false);}finally{f.close();}
});

test('expiry stops new requests but retains exact accepted request terminal capture',()=>{
 const f=fixture();try{f.manager.onRunAccepted(f.sid,f.rid);f.setActive(f.rid);const requestId=randomUUID();
 const capture=(id:string,phase:'pre_normalization'|'provider_sse',text:string)=>f.manager.capture({requestId:id,sessionId:f.sid,model:'qwen3.8-27b',phase,bytes:Buffer.from(text)});
 capture(requestId,'pre_normalization','owned');f.setNow(10000);assert.equal(f.manager.image(f.sid),false);
 capture(requestId,'provider_sse','[DONE]');capture(randomUUID(),'pre_normalization','denied');
 const index=readFileSync(join(f.dir,f.id,'capture-index.jsonl'),'utf8').trim().split('\n').map(x=>JSON.parse(x));assert.equal(index.length,2);assert.equal(index[1].requestId,requestId);f.manager.onRunFinished(f.sid,f.rid);capture(requestId,'provider_sse','too late');assert.equal(readFileSync(join(f.dir,f.id,'capture-index.jsonl'),'utf8').trim().split('\n').length,2);
 }finally{f.close();}
});

test('unconsumed exact private ticket stages references without granting launch or jobs',()=>{
 const f=fixture();try{assert(f.manager.imageReference(f.sid));assert.equal(f.manager.image(f.sid),false);assert.equal(f.manager.frontier(f.sid),false);assert.equal(f.manager.imageReference(randomUUID()),false);
 f.manager.onRunAccepted(f.sid,f.rid);assert.equal(f.manager.imageReference(f.sid),false);f.setActive(f.rid);assert(f.manager.imageReference(f.sid));assert(f.manager.image(f.sid));f.manager.onRunFinished(f.sid,f.rid);assert.equal(f.manager.imageReference(f.sid),false);
 const restart=createHostOwnedAcceptance(f.policy,()=>undefined,()=>1000);assert.equal(restart.imageReference(f.sid),false);restart.close();}finally{f.close();}
});
test('reference staging rejects expired removed reused unsafe and unprepared tickets',()=>{
 for(const kind of ['expire','remove','unsafe','bound','unprepared'] as const){const f=fixture();try{if(kind==='expire')f.setNow(10000);if(kind==='remove')f.write([]);if(kind==='unsafe')chmodSync(join(f.dir,f.id),0o777);if(kind==='bound')writeFileSync(join(f.dir,f.id,'binding.json'),'{}');if(kind==='unprepared')rmSync(join(f.dir,f.id),{recursive:true});assert.equal(f.manager.imageReference(f.sid),false);assert.equal(f.manager.image(f.sid),false);}finally{f.close();}}
});
