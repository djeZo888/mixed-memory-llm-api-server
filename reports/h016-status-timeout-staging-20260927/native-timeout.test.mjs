import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {stripTypeScriptTypes,createRequire} from 'node:module';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {resolve} from 'node:path';
import {setTimeout as delay} from 'node:timers/promises';
import {createServer} from 'node:http';
import {localConfig,selectedFrontierProfile,REQUEST_TIMEOUT_MS,MIMO_REQUEST_TIMEOUT_MS} from '../../ai-harness/deploy/engine/configure-profile.mjs';
const root=fileURLToPath(new URL('../../',import.meta.url));
const patched=resolve(root,'../private/native-timeout-source');
const retained=resolve(root,'../../H008-FRONTIER-20260926/native-source');
const provider=readFileSync(resolve(patched,'third_party/pi-mono/packages/ai/src/providers/openai-completions.ts'),'utf8');
const llm=readFileSync(resolve(patched,'packages/agent-core/src/pi-turn-runner/llm.ts'),'utf8');
const requestCode=provider.slice(provider.indexOf('\t\t\tconst mimo ='),provider.indexOf('\t\t\tconst { data: openaiStream'));
const requestOptions=Function('model','options',requestCode+'\nreturn requestOptions;');
test('exact profile and native wrapper select MiMo511min, others151min; explicit titles stay short',()=>{
 const env={AI_HARNESS_GATEWAY_URL:'http://10.0.2.2:8081/v1',AI_HARNESS_GATEWAY_TOKEN:'synthetic-fixture-token',AI_HARNESS_SESSION_ID:'fixture'};
 assert.equal(REQUEST_TIMEOUT_MS,9060000);assert.equal(MIMO_REQUEST_TIMEOUT_MS,30660000);
 for(const n of [131072,917504,1000000,1048576]){
  const f=selectedFrontierProfile({model:'mimo-v2.6-pro-rl',mimoEnabled:true,mimoQualificationSha256:'a'.repeat(64),mimoContextWindow:n,mimoMaxOutputTokens:65536});
  const config=localConfig(env,f);assert.equal(config.custom_provider.frontier.options.timeout,30660000);assert.equal(config.custom_provider.harness.options.timeout,9060000);assert.equal(config.defaultModel,'custom_provider:harness/qwen3.8-27b');
 }
 assert.equal(localConfig(env).custom_provider.frontier.options.timeout,9060000);
 const fn=stripTypeScriptTypes(llm.slice(llm.indexOf('export function wrapStreamFnWithTimeout'))).replace('export function','function');
 const wrap=Function(fn+';return wrapStreamFnWithTimeout;')();
 for(const id of ['mimo-v2.6-pro-rl','glm-5.3-flash','qwen3.8-27b']){
  const run=wrap((_m,_c,o)=>o,9060000);
  assert.equal(run({id},{},{}).timeoutMs,id.startsWith('mimo')?30660000:9060000);
  assert.equal(run({id},{},{timeoutMs:10000}).timeoutMs,10000);
  const options=requestOptions({id},{});assert.equal(options.timeout,id.startsWith('mimo')?30660000:9060000);assert.equal(options.maxRetries,0);
 }
});
test('actual SDK stream remains abortable after headers by exact MiMo provider signal; zero replay',async()=>{
 const require=createRequire(import.meta.url);const OpenAI=require(resolve(retained,'node_modules/openai')).default;
 let calls=0;
 const server=createServer((_req,res)=>{calls++;res.writeHead(200,{'content-type':'text/event-stream'});res.write('data: {"id":"fixture","choices":[]}\n\n');});
 await new Promise(r=>server.listen(0,'127.0.0.1',r));
 try{
  const opts=requestOptions({id:'mimo-v2.6-pro-rl'},{timeoutMs:80,maxRetries:5});assert.equal(opts.maxRetries,0);
  const client=new OpenAI({apiKey:'synthetic-fixture',baseURL:`http://127.0.0.1:${server.address().port}/v1`});
  const stream=await client.chat.completions.create({model:'mimo-v2.6-pro-rl',messages:[{role:'user',content:'fixture'}],stream:true},opts);
  try{for await(const _ of stream){} }catch(e){assert.ok(opts.signal.aborted);}
  assert.equal(opts.signal.aborted,true);assert.equal(calls,1);
 }finally{server.closeAllConnections();await new Promise(r=>server.close(r));}
});
test('exact shared dispatcher raises only reviewed gateway transport; upstream budgets stay per-model',async()=>{
 const {Agent}=await import(pathToFileURL(resolve(retained,'third_party/pi-mono/packages/ai/node_modules/undici/index.js')));
 const helper=provider.match(/\/\/ ai-harness transport:[\s\S]+?(?=\/\*\*\n \* Check if conversation messages)/)[0];
 const api=Function('Agent',stripTypeScriptTypes(helper)+'\nreturn {harnessGatewayFetch,gatewayDispatcher,GATEWAY_TRANSPORT_TIMEOUT_MS};')(Agent);
 try{assert.equal(api.GATEWAY_TRANSPORT_TIMEOUT_MS,30660000);let called;
 const fetch=async(_input,init)=>{called=init;return new Response('fixture')};
 const signal=new AbortController().signal;
 await api.harnessGatewayFetch('http://10.0.2.2:8081/frontier/v1',fetch)('http://10.0.2.2:8081/frontier/v1/chat/completions',{signal});
 assert.equal(called.signal,signal);assert.equal(called.dispatcher,api.gatewayDispatcher);
 assert.equal(api.harnessGatewayFetch('http://10.0.2.2:8082/v1',fetch),fetch);
 }finally{await api.gatewayDispatcher.destroy();}
});
