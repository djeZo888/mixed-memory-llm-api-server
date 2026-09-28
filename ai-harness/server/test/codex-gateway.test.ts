import test from "node:test";
import assert from "node:assert/strict";
import { createServer, type ServerResponse } from "node:http";
import { readFileSync } from "node:fs";
import { setTimeout as delay } from "node:timers/promises";
import { createGateway, type GatewayOptions } from "../src/gateway.js";
const captured=JSON.parse(readFileSync(new URL('./fixtures/codex/native-requests.json',import.meta.url),'utf8'))[0].body;
async function until(f:()=>boolean){for(let n=0;n<500;n++){if(f())return;await delay(5);}throw Error('timeout');}
async function fixture(responses?:GatewayOptions['responses']){
 const seen:{body:any,res:ServerResponse}[]=[],states:any[]=[];
 const backend=createServer(async(req,res)=>{const chunks=[];for await(const c of req)chunks.push(c);seen.push({body:JSON.parse(Buffer.concat(chunks).toString()),res});});await new Promise<void>(r=>backend.listen(0,'127.0.0.1',r));const port=(backend.address() as any).port;
 const gateway=createGateway({upstreamKey:'fixture-key',upstreams:[{url:`http://127.0.0.1:${port}/0/v1`,alias:'qwen3.8-27b-gpu0'},{url:`http://127.0.0.1:${port}/1/v1`,alias:'qwen3.8-27b'}],ownership:{recoveryReady:true,onRequestState:r=>states.push(r)},responses:responses??{enabled:true,countQwen:async()=>({inputTokens:100,contextWindow:480000})}});
 const url=await gateway.app.listen({host:'127.0.0.1',port:0});const token=gateway.issueToken('s');
 const send=(tokenOverride=token,signal?:AbortSignal,overrides:any={})=>fetch(url+'/v1/responses',{method:'POST',headers:{authorization:`Bearer ${tokenOverride}`,'content-type':'application/json'},body:JSON.stringify({...captured,...overrides}),signal});
 const emit=(i:number,v:unknown)=>{if(!seen[i].res.headersSent)seen[i].res.setHeader('content-type','text/event-stream');seen[i].res.write(`data: ${JSON.stringify(v)}\n\n`);};
 const done=(i:number)=>{emit(i,{choices:[{delta:{},finish_reason:'stop'}]});emit(i,{choices:[],usage:{prompt_tokens:100,completion_tokens:1}});seen[i].res.end('data: [DONE]\n\n');};
 return {seen,states,gateway,send,emit,done,token,async close(){backend.closeAllConnections();await gateway.close();await new Promise(r=>backend.close(r));}};
}
test('converter rejection fails client but drains accepted owner through true native terminal',async t=>{
 const f=await fixture();t.after(f.close);const pending=f.send().catch(e=>e);await until(()=>f.seen.length===1);f.emit(0,{choices:[{delta:{reasoning_content:'unqualified internal text'}}]});const reply=await pending;if(reply instanceof Response)assert.doesNotMatch(await reply.text().catch(()=>''),/response.completed/);else assert.ok(reply instanceof Error);f.gateway.revokeToken(f.token);assert.equal(await f.gateway.confirmSettlement({sessionId:'s'}),false);assert.equal(f.gateway.sessionWork('s')[0]?.state,'draining');f.done(0);await until(()=>f.gateway.sessionWork('s').length===0);assert.equal(await f.gateway.confirmSettlement({sessionId:'s'}),true);assert.equal(f.seen.length,1);
});
test('session token lineage cancels queued children; accepted drains remain, unrelated work is separate',async t=>{
 const f=await fixture();t.after(f.close);const child=f.gateway.issueToken('s'),other=f.gateway.issueToken('other');const a=f.send(),b=f.send(other);await until(()=>f.seen.length===2);const queued=f.send(child);await until(()=>f.gateway.snapshot().queued===1);f.gateway.revokeSession('s');assert.equal((await queued).status,401);assert.equal(await f.gateway.confirmSettlement({sessionId:'s'}),false);f.done(0);await(await a).text();await until(()=>f.gateway.sessionWork('s').length===0);assert.equal(await f.gateway.confirmSettlement({sessionId:'s'}),true);assert.equal(await f.gateway.confirmSettlement({sessionId:'other'}),false);f.done(1);await(await b).text();
 const newToken=f.gateway.issueToken('s'),followup=f.send(newToken);await until(()=>f.seen.length===3);f.done(2);assert.match(await(await followup).text(),/response.completed/);
});
test('queued count cancellation dispatches nothing; exact input plus output reservation rejects overflow',async t=>{
 let counting=false;const f=await fixture({enabled:true,countQwen:async(_b,_l,_k,signal)=>{counting=true;await new Promise((_,reject)=>signal.addEventListener('abort',()=>reject(Error('cancelled')),{once:true}));return {inputTokens:1,contextWindow:480000};}});t.after(f.close);const p=f.send();await until(()=>counting);assert.equal(f.gateway.sessionWork('s')[0]?.state,'counting');f.gateway.revokeSession('s');assert.equal((await p).status,500);assert.equal(f.seen.length,0);assert.equal(await f.gateway.confirmSettlement({sessionId:'s'}),true);
 const full=await fixture({enabled:true,countQwen:async b=>{assert.equal(b.max_tokens,65536);assert.equal(b.model,'qwen3.8-27b-gpu0');return {inputTokens:480000-65535,contextWindow:480000};}});t.after(full.close);assert.equal((await full.send()).status,413);assert.equal(full.seen.length,0);
});
test('disconnect/partial native EOF retains uncertainty after token revocation and lane reconciliation',async t=>{
 const f=await fixture();t.after(f.close);const p=f.send().catch(e=>e);await until(()=>f.seen.length===1);f.emit(0,{choices:[{delta:{content:'partial'}}]});f.seen[0].res.end();const reply=await p;if(reply instanceof Response)await reply.text().catch(()=>{});await until(()=>f.gateway.sessionWork('s')[0]?.state==='uncertain');f.gateway.revokeToken(f.token);f.gateway.reconcileAfterOwnerSettlement(['qwen3.8-27b-gpu0']);assert.equal(await f.gateway.confirmSettlement({sessionId:'s'}),false);assert.equal(f.seen.length,1);
});
