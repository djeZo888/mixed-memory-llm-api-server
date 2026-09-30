#!/usr/bin/env node
/** Focused compiled-payload behavior, synthetic profile, no model requests. */
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {createServer} from 'node:http';
import {setTimeout as delay} from 'node:timers/promises';
if(process.argv.includes('--help')){console.log('Run in exact6641 --network none with read-only compiled mounts.');process.exit(0);}
const platformFetch=globalThis.fetch;
let blockedFetches=0;globalThis.fetch=async()=>{blockedFetches++;throw Error('offline external fetch blocked');};
const n=await import('/opt/minimax/native-probes-check.mjs');
const baseline=await import('/opt/minimax/native-probes-baseline.mjs');
const {localConfig,selectedFrontierProfile}=await import('/work/configure-profile.mjs');
const checks={};
const compiled=readFileSync('/opt/minimax/native-probes.mjs'),bridge=readFileSync('/opt/minimax/native-probes-check.mjs');
assert.deepEqual(bridge.subarray(0,compiled.length),compiled);
const model=id=>({id,name:id,api:'openai-completions',provider:'custom_provider:frontier',baseUrl:'http://10.0.2.2:8081/frontier/v1',reasoning:false,input:['text'],cost:{input:0,output:0,cacheRead:0,cacheWrite:0},contextWindow:131072,maxTokens:65536});
for(const id of ['mimo-v2.6-pro-rl','glm-5.3-flash','qwen3.8-27b']){
 const fn=n.wrapStreamFnWithTimeout((_m,_c,o)=>o,9060000);
 assert.equal(fn(model(id),{},{}).timeoutMs,id.startsWith('mimo')?30660000:9060000);
 assert.equal(fn(model(id),{},{timeoutMs:37}).timeoutMs,37);
}
checks.compiledWrapper='PASS MiMo511min; Qwen/GLM151min; explicit override';
const attempts={};
for(const id of ['mimo-v2.6-pro-rl','glm-5.3-flash','qwen3.8-27b']){
 let calls=0;const fn=n.withLLMRetry(async()=>{calls++;throw Object.assign(new Error('503 fixture server failure'),{status:503});},{sessionId:'synthetic',turnId:'synthetic',scope:'agent',policy:{maxRetries:2,baseDelayMs:0,maxDelayMs:0},sleep:async()=>{}});
 try{const stream=await fn(model(id),{messages:[]},{});for await(const e of stream){} }catch{}
 attempts[id]=calls;assert.equal(calls,id.startsWith('mimo')?1:3);
}
checks.compiledFrameworkAttempts=attempts;
assert.equal(n.GATEWAY_TRANSPORT_TIMEOUT_MS,30660000);
let transport;const fake=async(_url,init)=>{transport=init;return new Response('fixture');};const signal=new AbortController().signal;
await n.harnessGatewayFetch('http://10.0.2.2:8081/frontier/v1',fake)('http://10.0.2.2:8081/frontier/v1/chat/completions',{signal});assert.equal(transport.dispatcher,n.gatewayDispatcher);assert.equal(transport.signal,signal);assert.equal(n.harnessGatewayFetch('http://10.0.2.2:8082/v1',fake),fake);
checks.compiledTransport='PASS 511min inactivity, exact reviewed origin only';
// Observe the real compiled SDK request deadline at fetch creation with synthetic SSE.
const realSetTimeout=globalThis.setTimeout,realSignalTimeout=AbortSignal.timeout;
const observed={};
try{
 for(const id of ['mimo-v2.6-pro-rl','glm-5.3-flash','qwen3.8-27b']){
  const timers=[],signals=[];globalThis.setTimeout=(fn,ms,...a)=>{timers.push(ms);return realSetTimeout(fn,ms,...a);};AbortSignal.timeout=ms=>{signals.push(ms);return realSignalTimeout(ms);};
  let calls=0;const fetch=async()=>{calls++;return new Response('data: {"id":"fixture","choices":[{"index":0,"delta":{"content":"ok"},"finish_reason":null}]}\n\ndata: {"id":"fixture","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n',{headers:{'content-type':'text/event-stream'}});};
  const stream=n.streamOpenAICompletions(model(id),{messages:[{role:'user',content:'synthetic',timestamp:0}]},{apiKey:'synthetic-fixture-token',fetch});for await(const e of stream){};const result=await stream.result();assert.equal(result.stopReason,'stop');assert.equal(calls,1);assert(timers.includes(id.startsWith('mimo')?30660000:9060000));assert.deepEqual(signals,id.startsWith('mimo')?[30660000]:[]);observed[id]={sdkTimeoutMs:timers.filter(x=>x>=9000000),streamDeadlineMs:signals,calls};
 }
}finally{globalThis.setTimeout=realSetTimeout;AbortSignal.timeout=realSignalTimeout;}
checks.compiledProviderDefaults=observed;
// Actual compiled provider + actual SDK, loopback SSE headers then delayed body.
let calls=0;const server=createServer((_req,res)=>{calls++;res.writeHead(200,{'content-type':'text/event-stream'});res.write('data: {"id":"fixture","choices":[]}\n\n');});
await new Promise(r=>server.listen(0,'127.0.0.1',r));
try{
 const m={...model('mimo-v2.6-pro-rl'),baseUrl:`http://127.0.0.1:${server.address().port}/v1`};
 const started=Date.now();const stream=n.streamOpenAICompletions(m,{messages:[{role:'user',content:'synthetic',timestamp:0}]},{apiKey:'synthetic-fixture-token',timeoutMs:80,maxRetries:5,fetch:platformFetch});
 for await(const e of stream){};const result=await stream.result();assert(['error','aborted'].includes(result.stopReason));assert.equal(calls,1);assert(Date.now()-started<2500);checks.compiledFullStreamAbort={calls,elapsedMs:Date.now()-started,stopReason:result.stopReason};
}finally{server.closeAllConnections();await new Promise(r=>server.close(r));}
// A retryable HTTP500 must still have one physical provider request for MiMo.
let retryCalls=0;const stream=n.streamOpenAICompletions(model('mimo-v2.6-pro-rl'),{messages:[{role:'user',content:'synthetic',timestamp:0}]},{apiKey:'synthetic-fixture-token',maxRetries:5,timeoutMs:500,fetch:async()=>{retryCalls++;return new Response('{"error":{"message":"fixture"}}',{status:500,headers:{'content-type':'application/json'}});}});for await(const e of stream){};assert.equal(retryCalls,1);checks.compiledSdkRetryCalls=retryCalls;
const env={AI_HARNESS_GATEWAY_URL:'http://10.0.2.2:8081/v1',AI_HARNESS_GATEWAY_TOKEN:'synthetic-fixture-token',AI_HARNESS_SESSION_ID:'synthetic'};
for(const context of [131072,917504,1000000,1048576]){const cfg=localConfig(env,selectedFrontierProfile({model:'mimo-v2.6-pro-rl',mimoEnabled:true,mimoQualificationSha256:'a'.repeat(64),mimoContextWindow:context,mimoMaxOutputTokens:65536}));assert.equal(cfg.custom_provider.frontier.options.timeout,30660000);assert.equal(cfg.custom_provider.harness.options.timeout,9060000);assert.equal(cfg.defaultModel,'custom_provider:harness/qwen3.8-27b');}
assert.equal(JSON.stringify(n.LOCAL_BASE_TOOL_DEFS),JSON.stringify(baseline.LOCAL_BASE_TOOL_DEFS));assert.deepEqual(n.AGENT_BUILTIN_MCP_TOOL_IDS,baseline.AGENT_BUILTIN_MCP_TOOL_IDS);assert.equal(n.modelTokenEstimator(model('mimo-v2.6-pro-rl')).estimateTextTokens('中文'),6);
checks.profileToolsEstimator='PASS synthetic numeric contexts; Qwen default; exact baseline tool definitions; unchanged estimator';
await n.gatewayDispatcher.destroy();
console.log(JSON.stringify({result:'PASS',checks,compiledProbeSha256:createHash('sha256').update(compiled).digest('hex'),probeSourceRevision:n.probeSourceRevision,blockedMetadataFetches:blockedFetches,modelRequests:0,toolExecutions:0,native17Acceptance:false},null,2));
