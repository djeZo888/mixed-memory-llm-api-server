import test from "node:test";
import assert from "node:assert/strict";
import {createServer} from "node:http";
import {createCodexQwenCounter,QWEN_CODEX_PIN} from "../src/codex-qwen.js";
test('exact Qwen count uses final alias/history/tools/nonthinking/output, not tokenizer metadata as allocation',async t=>{
 const seen:any[]=[];let invalid=false;const server=createServer(async(req,res)=>{const chunks=[];for await(const c of req)chunks.push(c);seen.push({url:req.url,body:JSON.parse(Buffer.concat(chunks).toString())});res.setHeader('content-type','application/json');res.end(JSON.stringify({tokens:[1,2,3],count:invalid?4:3,max_model_len:262144}));});await new Promise<void>(r=>server.listen(0,'127.0.0.1',r));t.after(()=>new Promise<void>(r=>server.close(()=>r())));const lane={alias:'qwen3.8-27b-gpu0',url:`http://127.0.0.1:${(server.address() as any).port}/v1`};const q={...QWEN_CODEX_PIN,alias:lane.alias,instanceId:'fixture-instance'};const count=createCodexQwenCounter(async()=>q);const body={model:lane.alias,messages:[{role:'system',content:'a'},{role:'user',content:'b'}],tools:[{type:'function',function:{name:'tool',parameters:{type:'object'}}}],reasoning_effort:'none',stream:true,stream_options:{include_usage:true},max_tokens:65536};assert.deepEqual(await count(body,lane,'fixture',new AbortController().signal),{inputTokens:3,contextWindow:480000});const {stream,stream_options,...expected}=body;assert.deepEqual(seen[0],{url:'/v1/tokenize',body:expected});invalid=true;await assert.rejects(count(body,lane,'fixture',new AbortController().signal));
});
test('missing allocation/template identity cannot be replaced by approximate counting',async()=>{
 const count=createCodexQwenCounter(async alias=>({...QWEN_CODEX_PIN,alias,instanceId:'x',contextWindow:262144}));await assert.rejects(count({model:'qwen3.8-27b',reasoning_effort:'none'},{alias:'qwen3.8-27b',url:'http://127.0.0.1:1/v1'},'fixture',new AbortController().signal));
});
