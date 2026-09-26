#!/usr/bin/env node
/** Actual pinned native custom renderer -> binding capture -> provider payload; no inference. */
import assert from 'node:assert/strict';
import {pathToFileURL} from 'node:url';
import {resolve} from 'node:path';
import {readFileSync} from 'node:fs';
import {localConfig,frontierAgentMarkdown,FRONTIER_CONTEXT} from '../engine/configure-profile.mjs';
import {frontierBody} from '../../server/dist/frontier.js';
if(process.argv.includes('--help')) {console.log('Usage: native-frontier-boundary.mjs NATIVE_PROBES.mjs');process.exit(0);}
const native=await import(pathToFileURL(resolve(process.argv[2])));
const config={...localConfig({AI_HARNESS_GATEWAY_URL:'http://10.0.2.2:8081/v1',AI_HARNESS_GATEWAY_TOKEN:'offline-fixture-placeholder',AI_HARNESS_SESSION_ID:'frontier-fixture'}),dataDir:'/offline/profile'};
const canonical=native.parseCanonicalAgentMarkdown(frontierAgentMarkdown(),'frontier');
assert.deepEqual(canonical.diagnostics,[]);
const catalog=new native.BuiltinAgentCatalog();
const meta={name:'frontier',agentRole:'worker',creationSource:'manual',greetingSent:false,createdAtMs:0,updatedAtMs:0};
const repository={get:async()=>meta,getCanonicalConfig:async()=>canonical,getAgentDir:()=>'/offline/frontier'};
const renderer={repository,catalog,resolveContext:async input=>native.resolveAgentProfileRenderContext({...input,capabilities:config.agents.default},{repository,requireMeta:async()=>meta,resolveExecutionTarget:async owner=>owner,definitionFor:owner=>catalog.readDefinition(owner),isBuiltin:()=>false,resolveBuiltinReadAgentNames:async owner=>[owner]})};
const renderProfile=input=>native.renderAgentProfile(renderer,input);
const profile=await renderProfile({exactOwnerName:'frontier',surface:'task-child',promptProfile:'tui',appMode:'coding'});
assert.equal(profile.creationSource,'manual');assert.equal(profile.configSelection.model,'custom_provider:frontier/glm-5.3-flash');
const retained=JSON.parse(readFileSync(new URL('./fixtures/native-image-mcp-catalog.json',import.meta.url)));
const discovered=retained.nativeMcpCatalog.map(t=>({...t,toolName:t.name}));
const mcp=new native.LocalMcpService(()=>'/offline/nonexistent-profile');
let executions=0,requests=0;
const noExecute={execute(){executions++;throw Error('FORBIDDEN');}};
const sources={nativeTools:native.LOCAL_BASE_TOOL_DEFS.map(def=>({def,impl:noExecute})),mcpEntries:mcp.runtimeToolsFromNative(discovered).map((tool,i)=>({tool:{...tool,impl:noExecute},source:discovered[i].source,serverName:discovered[i].server})),threadGoalTools:[],cuRuntimeAvailable:false};
const coordinator=native.createTaskAgentBindingCaptureCoordinator({
 agentService:{renderProfile,getConfigDocument:async()=>({ownerKind:'custom',exactOwnerName:'frontier',ownerInstanceId:'fixture-frontier-owner'})},
 config:()=>config,inventory:{capture:async()=>({sources,skills:[{name:'image',sourceType:2},{name:'pdf',sourceType:2}]})},runtimeOwnerKind:'tui',capabilityProfile:'cli',
});
const parent={sessionId:'parent-qwen',workspaceDir:'/offline/workspace',appMode:'coding',effectiveModel:'custom_provider:harness/qwen3.8-27b',effectiveModelContextWindow:480000,effectiveModelMaxOutputTokens:2048};
const captured=await coordinator.capture({agentName:'frontier',parent});
assert.equal(captured.effectiveModel,'custom_provider:frontier/glm-5.3-flash');
assert.equal(captured.effectiveModelContextWindow,FRONTIER_CONTEXT);
assert.equal(captured.effectiveModelMaxOutputTokens,65536);
assert.equal(captured.effectiveModelThinking.effort,'high');
const binding=captured.taskAgentBinding.definition.capabilities;
for(const name of ['task','task_append'])assert(!binding.tools.includes(name));
for(const name of ['read','write','edit','bash','mcp__image__image_generate','mcp__searxng__searxng_search'])assert(binding.tools.includes(name),name);
const override=await coordinator.capture({agentName:'frontier',parent,taskModelSelection:{model:'custom_provider:harness/qwen3.8-27b'}});
assert.equal(override.effectiveModel,'custom_provider:harness/qwen3.8-27b');
assert.equal(override.effectiveModelContextWindow,480000);
const model={api:'openai-completions',provider:'custom_provider:frontier',id:'glm-5.3-flash',name:'GLM-5.3-Flash',baseUrl:'http://10.0.2.2:8081/frontier/v1',reasoning:true,input:['text'],cost:{input:0,output:0,cacheRead:0,cacheWrite:0},contextWindow:FRONTIER_CONTEXT,maxTokens:65536};
const assembled=native.buildLocalTurnToolCatalog({sessionId:'frontier-child',sources,llmModel:model,modelCapabilities:{support_image:false},agentProfile:{capabilityCeiling:profile.capabilityCeiling,trustedBuiltin:false,surface:'task-child',configSelection:binding},config:config.mcpToolSearch,env:{}});
const tools=native.newTools('/offline/workspace',assembled.tools,{}, {disableBuiltinFallback:true});
let payload;
const stream=native.streamOpenAICompletions(model,{systemPrompt:'Offline frontier fixture',messages:[{role:'user',content:[{type:'text',text:'Research fixture part one.'},{type:'text',text:' Part two.'}],timestamp:0}],tools},{apiKey:'synthetic-session-bearer',maxTokens:65536,reasoning:'high',fetch:async()=>{requests++;throw Error('FORBIDDEN_NETWORK');},onPayload:p=>{payload=p;throw Error('CAPTURE_COMPLETE');}});
await stream.result();assert(payload);
try { frontierBody(payload); } catch(e) { console.error({payloadKeys:Object.keys(payload),model:payload.model}); throw e; } // Real native payload must pass fixed host admission schema.
const userContent=payload.messages.find(m=>m.role==='user').content;
assert.deepEqual(userContent,[{type:'text',text:'Research fixture part one.'},{type:'text',text:' Part two.'}]);
assert.deepEqual(frontierBody(payload).messages,payload.messages);
const names=payload.tools.map(t=>t.function.name);assert(!names.includes('task'));assert(!names.includes('task_append'));assert(names.includes('mcp__image__image_edit'));assert(names.includes('skill'));
const estimator=native.modelTokenEstimator(model);const qwen=native.modelTokenEstimator({...model,provider:'custom_provider:harness',id:'qwen3.8-27b'});
assert.notEqual(estimator,qwen);assert.equal(estimator.estimateTextTokens('中文'),Buffer.byteLength('中文'));
assert.equal(native.modelTokenEstimator({...model,provider:'other'}),qwen);
assert.equal(executions,0);assert.equal(requests,0);
console.log(JSON.stringify({result:'PASS',evidence:'SYNTHETIC actual native renderer, fresh custom child binding, provider payload; no inference or tool execution',sourceRevision:native.probeSourceRevision,model:captured.effectiveModel,contextWindow:captured.effectiveModelContextWindow,maxOutputTokens:captured.effectiveModelMaxOutputTokens,effort:captured.effectiveModelThinking.effort,override:override.effectiveModel,tools:names,localEstimator:'UTF-8 scheduling heuristic; exact upstream gateway admission required',networkRequests:requests,toolExecutions:executions},null,2));
