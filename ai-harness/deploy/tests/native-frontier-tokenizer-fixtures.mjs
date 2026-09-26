#!/usr/bin/env node
/** Offline comparison only: actual pinned tokenizer counts, no HTTP/inference. */
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {pathToFileURL} from 'node:url';
import {resolve} from 'node:path';
if(process.argv.includes('--help')) { console.log('Usage: native-frontier-tokenizer-fixtures.mjs NATIVE_PROBES.mjs'); process.exit(0); }
const n=await import(pathToFileURL(resolve(process.argv[2])));
const fixtures=JSON.parse(readFileSync(new URL('../../server/test/fixtures/h008/tokenizer-fixtures.json',import.meta.url),'utf8'));
const model={api:'openai-completions',provider:'custom_provider:frontier',id:'glm-5.3-flash',name:'Flash',baseUrl:'http://10.0.2.2:8081/frontier/v1',reasoning:true,input:['text'],cost:{input:0,output:0,cacheRead:0,cacheWrite:0},contextWindow:480000,maxTokens:65536};
const rows=fixtures.fixtures.map(f=>{
  const systemPrompt=f.request.messages.filter(m=>m.role==='system').map(m=>m.content).join('\n');
  const tools=(f.request.tools??[]).map(t=>t.function);
  // Deterministic equivalent Pi history. Native SGLang normalizes JSON tool-call
  // argument strings to objects before templating; preserve original wire fixtures.
  const messages=f.request.messages.filter(m=>m.role!=='system').map(m=>{
    const content=[...(m.reasoning_content?[{type:'thinking',thinking:m.reasoning_content}]:[]),
      ...(m.content?[{type:'text',text:m.content}]:[]),
      ...(m.tool_calls??[]).map(c=>({type:'toolCall',id:c.id,name:c.function.name,arguments:JSON.parse(c.function.arguments)}))];
    if(m.role==='assistant') return {role:'assistant',content,api:model.api,provider:model.provider,model:model.id,stopReason:'toolUse',usage:{input:0,output:0,cacheRead:0,cacheWrite:0,totalTokens:0,cost:{input:0,output:0,cacheRead:0,cacheWrite:0,total:0}},timestamp:0};
    if(m.role==='tool') return {role:'toolResult',toolCallId:m.tool_call_id,toolName:'weather',content,isError:false,timestamp:0};
    return {role:m.role,content,timestamp:0};
  });
  const estimator=n.modelTokenEstimator(model);
  const dynamicEstimate=estimator.estimateMessages(messages)+estimator.estimateTextTokens(systemPrompt)+tools.reduce((sum,t)=>sum+estimator.estimateTextTokens([t.name??'',t.description??'',JSON.stringify(t.parameters)].join('\n')),0);
  const footprintEstimate=n.createLocalContextFootprintMeasurer({model,systemPrompt,tools}).measure(messages).inputTokens;
  assert(Number.isSafeInteger(dynamicEstimate)); assert(Number.isSafeInteger(footprintEstimate));
  assert.deepEqual(f.response,{count:{prose:36,multilingual:42,tools_history:212}[f.id],tokenizer_revision:fixtures.model_revision,template_revision:fixtures.model_revision,context_limit:480000});
  return {id:f.id,exactCount:f.response.count,dynamicEstimate,dynamicRatio:dynamicEstimate/f.response.count,footprintEstimate,footprintRatio:footprintEstimate/f.response.count};
});
console.log(JSON.stringify({status:'PASS_OFFLINE_COMPARISON',provenance:fixtures.status,revision:fixtures.model_revision,normalization:fixtures.normalization,mapping:'Deterministic equivalent Pi history; original complete HTTP fixtures preserved byte-for-byte',rows,limits:'Three small fixtures do not prove an upper bound for all inputs or effective 480K context. Native scheduling may compact much earlier; exact gateway admission is authoritative. Backend HTTP parity pending.',physicalNetworkRequests:0},null,2));
