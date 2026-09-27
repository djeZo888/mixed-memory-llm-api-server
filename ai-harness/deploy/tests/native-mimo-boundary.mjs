#!/usr/bin/env node
/** Reuse retained pinned native probes; no inference, tools or network. */
import assert from 'node:assert/strict';
import {pathToFileURL} from 'node:url';
import {resolve} from 'node:path';
import {readFileSync,writeFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {localConfig,frontierAgentMarkdown,selectedFrontierProfile} from '../engine/configure-profile.mjs';
import {prepareMimo} from '../../server/dist/mimo.js';
if(process.argv.includes('--help')) {console.log('Usage: native-mimo-boundary.mjs NATIVE_PROBES.mjs [PRIVATE_FIXTURE.json]');process.exit(0);}
const native=await import(pathToFileURL(resolve(process.argv[2])));
const selection={model:'mimo-v2.6-pro-rl',mimoEnabled:true,mimoQualificationSha256:'a'.repeat(64),mimoContextWindow:131072,mimoMaxOutputTokens:65536};
const selected=selectedFrontierProfile(selection);
const config={...localConfig({AI_HARNESS_GATEWAY_URL:'http://10.0.2.2:8081/v1',AI_HARNESS_GATEWAY_TOKEN:'offline-fixture-placeholder',AI_HARNESS_SESSION_ID:'mimo-fixture'},selected),dataDir:'/offline/profile'};
const canonical=native.parseCanonicalAgentMarkdown(frontierAgentMarkdown(selected),'frontier');
assert.deepEqual(canonical.diagnostics,[]);
const catalog=new native.BuiltinAgentCatalog();
const meta={name:'frontier',agentRole:'worker',creationSource:'manual',greetingSent:false,createdAtMs:0,updatedAtMs:0};
const repository={get:async()=>meta,getCanonicalConfig:async()=>canonical,getAgentDir:()=>'/offline/frontier'};
const renderer={repository,catalog,resolveContext:async input=>native.resolveAgentProfileRenderContext({...input,capabilities:config.agents.default},{repository,requireMeta:async()=>meta,resolveExecutionTarget:async owner=>owner,definitionFor:owner=>catalog.readDefinition(owner),isBuiltin:()=>false,resolveBuiltinReadAgentNames:async owner=>[owner]})};
const renderProfile=input=>native.renderAgentProfile(renderer,input);
const profile=await renderProfile({exactOwnerName:'frontier',surface:'task-child',promptProfile:'tui',appMode:'coding'});
const retained=JSON.parse(readFileSync(new URL('./fixtures/native-image-mcp-catalog.json',import.meta.url)));
const discovered=retained.nativeMcpCatalog.map(t=>({...t,toolName:t.name}));
const mcp=new native.LocalMcpService(()=>'/offline/nonexistent-profile');
let executions=0,requests=0;
const noExecute={execute(){executions++;throw Error('FORBIDDEN');}};
const sources={nativeTools:native.LOCAL_BASE_TOOL_DEFS.map(def=>({def,impl:noExecute})),mcpEntries:mcp.runtimeToolsFromNative(discovered).map((tool,i)=>({tool:{...tool,impl:noExecute},source:discovered[i].source,serverName:discovered[i].server})),threadGoalTools:[],cuRuntimeAvailable:false};
const coordinator=native.createTaskAgentBindingCaptureCoordinator({agentService:{renderProfile,getConfigDocument:async()=>({ownerKind:'custom',exactOwnerName:'frontier',ownerInstanceId:'fixture-frontier-owner'})},config:()=>config,inventory:{capture:async()=>({sources,skills:[{name:'image',sourceType:2},{name:'pdf',sourceType:2}]})},runtimeOwnerKind:'tui',capabilityProfile:'cli'});
const parent={sessionId:'parent-qwen',workspaceDir:'/offline/workspace',appMode:'coding',effectiveModel:'custom_provider:harness/qwen3.8-27b',effectiveModelContextWindow:480000,effectiveModelMaxOutputTokens:2048};
const captured=await coordinator.capture({agentName:'frontier',parent});
assert.equal(captured.effectiveModel,'custom_provider:frontier/mimo-v2.6-pro-rl');
assert.equal(captured.effectiveModelContextWindow,131072);
assert.equal(captured.effectiveModelMaxOutputTokens,65536);
const binding=captured.taskAgentBinding.definition.capabilities;
for(const name of ['task','task_append'])assert(!binding.tools.includes(name));
const model={api:'openai-completions',provider:'custom_provider:frontier',id:selected.model,name:'MiMo-V2.6-Pro-RL',baseUrl:'http://10.0.2.2:8081/frontier/v1',reasoning:true,input:['text'],cost:{input:0,output:0,cacheRead:0,cacheWrite:0},contextWindow:selected.contextWindow,maxTokens:selected.maxOutputTokens};
const assembled=native.buildLocalTurnToolCatalog({sessionId:'frontier-child',sources,llmModel:model,modelCapabilities:{support_image:false},agentProfile:{capabilityCeiling:profile.capabilityCeiling,trustedBuiltin:false,surface:'task-child',configSelection:binding},config:config.mcpToolSearch,env:{}});
const tools=native.newTools('/offline/workspace',assembled.tools,{}, {disableBuiltinFallback:true});
let payload;
const stream=native.streamOpenAICompletions(model,{systemPrompt:'Offline MiMo fixture',messages:[{role:'user',content:[{type:'text',text:'Review the fixture.'}],timestamp:0}],tools},{apiKey:'synthetic-session-bearer',maxTokens:65536,fetch:async()=>{requests++;throw Error('FORBIDDEN_NETWORK');},onPayload:p=>{payload=p;throw Error('CAPTURE_COMPLETE');}});
await stream.result();assert(payload);
// Match actual HTTP JSON serialization, which drops undefined options.
payload=JSON.parse(JSON.stringify(payload));
let prepared;try { prepared=prepareMimo(payload); } catch(e) { console.error({payloadKeys:Object.keys(payload),toolFunctionFields:[...new Set(payload.tools.flatMap(t=>Object.keys(t.function)))],code:e.code});throw e; }
assert.deepEqual(prepared.body.messages,payload.messages);
assert.equal(payload.reasoning_effort,undefined); // managed MiMo profile never inherits GLM high
if(process.argv[3]) writeFileSync(resolve(process.argv[3]),JSON.stringify({kind:'OFFLINE_NATIVE_SDK_FIXTURE_NOT_PRODUCTION_ROSTER',sourceRevision:native.probeSourceRevision,rosterDifference:'Contains code_review; browser feature not injected. Production17 browser/no-code_review qualification remains pending.',canonicalBody:prepared.body,canonicalSha256:prepared.sha256,toolsSha256:createHash('sha256').update(JSON.stringify(prepared.body.tools)).digest('hex')},null,2)+'\n',{mode:0o600,flag:'wx'});
const names=payload.tools.map(t=>t.function.name);assert.equal(names.length,17);assert(!names.includes('task'));assert(!names.includes('task_append'));
assert.equal(executions,0);assert.equal(requests,0);
console.log(JSON.stringify({result:'PASS',evidence:'OFFLINE retained MiniMax child binding/SDK payload.17 fixture tools include code_review, omit browser; NOT production17 qualification, no deployed-image or llama runtime proof',sourceRevision:native.probeSourceRevision,model:captured.effectiveModel,contextWindow:captured.effectiveModelContextWindow,maxOutputTokens:captured.effectiveModelMaxOutputTokens,tools:names,toolFunctionFields:[...new Set(payload.tools.flatMap(t=>Object.keys(t.function)))],networkRequests:requests,toolExecutions:executions},null,2));
