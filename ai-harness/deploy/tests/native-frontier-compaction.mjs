#!/usr/bin/env node
/** Executes current native v2 compaction/dynamic-output paths with synthetic generation. */
import assert from 'node:assert/strict';
import {pathToFileURL} from 'node:url';
import {resolve} from 'node:path';
if(process.argv.includes('--help')){console.log('Usage: native-frontier-compaction.mjs NATIVE_PROBES.mjs');process.exit(0);}
const n=await import(pathToFileURL(resolve(process.argv[2])));
const model={api:'openai-completions',provider:'custom_provider:frontier',id:'glm-5.3-flash',name:'Flash',baseUrl:'http://10.0.2.2:8081/frontier/v1',reasoning:true,input:['text'],cost:{input:0,output:0,cacheRead:0,cacheWrite:0},contextWindow:480000,maxTokens:65536};
const user=text=>({role:'user',content:[{type:'text',text}],timestamp:0});
const history=Array.from({length:20},(_,i)=>user(`document ${i}: ${'facts 中文 '.repeat(150)}`));
const measure=n.createLocalContextFootprintMeasurer({model,systemPrompt:'Preserve evidence',tools:[{name:'read',description:'Read a document'}]});
const qmeasure=n.createLocalContextFootprintMeasurer({model:{...model,provider:'custom_provider:harness',id:'qwen3.8-27b'},systemPrompt:'Preserve evidence'});
assert(measure.measure(history).inputTokens>qmeasure.measure(history).inputTokens);
const summary=['Goal','Constraints & Preferences','Completed Work','Current State','Blockers','Key Decisions','Pending User Asks','Critical Context & Relevant Files'].map(h=>`## ${h}\nPreserved synthetic fact.\n`).join('\n');
const calls=[];
const streamFn=(m,context,options)=>{calls.push({model:m.id,context,options});return {result:async()=>({role:'assistant',content:[{type:'text',text:summary}],stopReason:'stop',usage:{input:1000,output:100,cacheRead:0,cacheWrite:0,totalTokens:1100,cost:{input:0,output:0,cacheRead:0,cacheWrite:0,total:0}},api:m.api,provider:m.provider,model:m.id,timestamp:0})};};
const checkpoint=await n.createCheckpointSession({model,providerInputLimit:400000,maxOutputTokens:16384,thinkingLevel:'high',streamFn});
assert(checkpoint.fits({messages:history}));
const tooLarge=await n.createCheckpointSession({model,providerInputLimit:100,maxOutputTokens:16384,thinkingLevel:'high',streamFn});
assert.equal(tooLarge.fits({messages:history}),false);
const before=measure.measure(history).inputTokens;
const compacted=await n.compactContext({history,instructions:'Preserve the evidence',allowLegacyToolTrim:false,limits:{providerInputLimit:400000},measurePair:async input=>measure.measurePair(input),checkpoint:{tokensBefore:before,timestamp:1,open:async()=>checkpoint}});
assert.equal(compacted.method,'llm_checkpoint');assert.equal(compacted.schemaStatus,'exact');assert(compacted.measurement.after.inputTokens<before);assert.equal(calls.length,1);assert.equal(calls[0].model,'glm-5.3-flash');assert.equal(calls[0].options.reasoning,'high');
const continuation=[...compacted.replacementMessages,user('Continue with the next document')];
const dynamic=n.withLocalDynamicMaxTokens(streamFn);
dynamic(model,{systemPrompt:'Continue',messages:continuation},{maxTokens:65536,reasoning:'high'});
assert.equal(calls.at(-1).model,'glm-5.3-flash');assert.equal(calls.at(-1).options.maxTokens,65536);
const narrow={...model,contextWindow:64000,maxTokens:32768};
dynamic(narrow,{messages:[user('hello world '.repeat(4000))]},{maxTokens:32768});
const frontierOutput=calls.at(-1).options.maxTokens;assert(frontierOutput<32768);
dynamic({...narrow,provider:'custom_provider:harness',id:'qwen3.8-27b'},{messages:[user('hello world '.repeat(4000))]},{maxTokens:32768});
assert.equal(calls.at(-1).options.maxTokens,32768);
console.log(JSON.stringify({result:'PASS',evidence:'SYNTHETIC current native v2 estimator, checkpoint fitting, actual compaction replacement and continuation with fake generation; no occupied-model acceptance',beforeEstimate:before,afterEstimate:compacted.measurement.after.inputTokens,frontierDynamicOutput:frontierOutput,qwenDynamicOutput:calls.at(-1).options.maxTokens,physicalNetworkRequests:0},null,2));
