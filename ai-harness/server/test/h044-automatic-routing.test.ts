/** Meaningful SOURCE fixtures only; no native/Linux/inference acceptance. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {createCodexAutomaticRoute as route,codexAutomaticDirective,assertCodexAutomaticRoute} from '../src/codex-automatic-routing.js';
import {composeCodexHost,validateCurrentCodexFrontier,CURRENT_CODEX_FRONTIER_PINS} from '../src/codex-host.js';
import {CodexChildren} from '../src/codex-children.js';
import {validateCodexChildMetadata} from '../src/codex-child-metadata.js';
import {assertEngineAvailable} from '../src/engine-router.js';
const gates={deep:true,technical:true,creative:true};
test('primary scoped company research wins over optional visuals while quick lookups stay ordinary',()=>{
 for(const text of [
  'Research company Example Motors as much as you can.',
  'Research company Example Motors comprehensively; include charts and drawings if useful.',
  'Please investigate the company Example Motors in depth; if useful create images and drawings.',
  'Can you research business Example thoroughly and make an SVG chart to illustrate the results?',
 ]) {
  const selected=route({text});assert.equal(selected.intent,'deep');
  assert.doesNotThrow(()=>codexAutomaticDirective(selected,{...gates,creative:false}));
  assert.throws(()=>codexAutomaticDirective(selected,{...gates,deep:false}),/temporarily unavailable/);
 }
 for(const text of ['Who founded Example Motors?','Research company Example Motors address.',
  'What is a research company?','Research company Everything Ltd address.','Find the phone number of Example Motors.',
  'Create an SVG diagram of the data.','Make an HTML chart.'])assert.equal(route({text}).intent,'ordinary',text);
 for(const text of ['Generate images of motorcycles.','Please draw drawings of a forest.',
  'Create pictures of a research company.','Generate an image showing HTML source code.',
  'Generate a photorealistic image and also create SVG charts.',
  'Generate an image of a motorcycle; add an SVG chart of the stats.'])assert.equal(route({text}).intent,'creative',text);
});
test('ordinary/deep/analysis/generation and one-parent follow-up select deterministic intent',()=>{
 for(const [text,intent] of [['Write a function','ordinary'],['Do deep research on this problem','deep'],['Use greater intelligence for this','deep'],['Analyze this drawing','technical'],['Generate an image of a bird','creative']] as const)assert.equal(route({text}).intent,intent);
 assert.equal(route({text:'What does this show?',hasImages:true}).intent,'technical');
 assert.equal(route({text:'Make it red',previous:'creative'}).intent,'creative');assert.equal(route({text:'Continue',previous:'deep'}).intent,'deep');
 assert.equal(route({text:'Write a new function',previous:'deep'}).intent,'ordinary');
 assert.throws(()=>assertCodexAutomaticRoute({...route({text:'hello'})}));
 assert.match(codexAutomaticDirective(route({text:'deep research'}),gates),/mimo-v2.6-pro-rl/);
});
test('unavailable selected lane refuses substitution and technical/creative gates are independent',()=>{
 assert.throws(()=>codexAutomaticDirective(route({text:'deep research'}),{...gates,deep:false}),/temporarily unavailable/);
 assert.doesNotThrow(()=>codexAutomaticDirective(route({text:'Analyze this image'}),{...gates,creative:false}));
 assert.throws(()=>codexAutomaticDirective(route({text:'Generate an image'}),{...gates,creative:false}));
 assert.doesNotThrow(()=>codexAutomaticDirective(route({text:'Generate an image'}),{...gates,technical:false}));
});
test('host needs both current scoped frontier and native child gates; no historical harness executes',()=>{
 const q={protocolQualified:true as const,rootlessQualified:true as const,verifyLane:async()=>{throw Error('not invoked');},frontierAcceptance:(id:string)=>id==='owned'};
 const disabled=composeCodexHost('/trusted/deploy/run-codex.sh',()=>undefined,q),host=composeCodexHost('/trusted/deploy/run-codex.sh',()=>undefined,{...q,nativeDelegationQualified:true});
 assert.throws(()=>disabled.runtime.automaticRouting!(route({text:'deep research'}),'owned'));
 assert.deepEqual(host.runtime.qualifiedChildModels,['qwen3.8-27b']);assert.deepEqual(host.runtime.qualifiedChildModelsForSession!('foreign'),['qwen3.8-27b']);assert.deepEqual(host.runtime.qualifiedChildModelsForSession!('owned'),['qwen3.8-27b','mimo-v2.6-pro-rl']);
 assert.throws(()=>host.runtime.automaticRouting!(route({text:'deep research'}),'foreign'));assert.match(host.runtime.automaticRouting!(route({text:'deep research'}),'owned'),/owned native child/);
 assert.throws(()=>assertEngineAvailable('minimax'),/Start a new chat/);assert.equal(host.runtime.model,'qwen3.8-27b');
});
test('selected MiMo needs clean pinned current child metadata and actual completed turn',()=>{
 const child={id:'child',parentThreadId:'parent',forkedFromId:null,model:'mimo-v2.6-pro-rl',modelProvider:'sova',cliVersion:'0.158.0',source:{subAgent:{thread_spawn:{parent_thread_id:'parent',depth:1}}},turns:[]};
 validateCodexChildMetadata(child,'parent',['qwen3.8-27b','mimo-v2.6-pro-rl'],'sova');
 for(const patch of [{parentThreadId:'foreign'},{model:'qwen3.8-27b-gpu0'},{modelProvider:'minimax'},{cliVersion:'0.159.2'},{forkedFromId:'foreign'}])assert.throws(()=>validateCodexChildMetadata({...child,...patch},'parent',['mimo-v2.6-pro-rl'],'sova'));
 const c=new CodexChildren(()=> 'parent',()=>{},4,['qwen3.8-27b','mimo-v2.6-pro-rl']);c.thread(child);assert.equal(c.completedModel('mimo-v2.6-pro-rl'),false);
 c.notification('turn/started',{threadId:'child',turn:{id:'turn'}});c.notification('turn/completed',{threadId:'child',turn:{id:'turn',status:'completed'}});
 assert.equal(c.completedModel('mimo-v2.6-pro-rl',new Set(['foreign'])),false);assert.equal(c.completedModel('mimo-v2.6-pro-rl',new Set(['child'])),true);
});
test('protected current Codex frontier rejects historical MiniMax, source-only/native-unknown and different parent',()=>{
 const value:any={schema:1,kind:'current-native-codex-frontier-review',pins:CURRENT_CODEX_FRONTIER_PINS,sourceRevision:'a'.repeat(40),sourceClosure:{'/synthetic/source.js':'b'.repeat(64)},reviewedBy:'root',reviewedAt:'2026-10-01T23:20:00Z',workflows:{}};const records:any={};
 for(const workflow of ['responses','toolContinuation','automaticSelection']){const run={schema:1,kind:'current-native-codex-frontier-workflow',workflow,result:'PASS',harness:'codex',pins:value.pins,sourceRevision:value.sourceRevision,sessionId:'11111111-1111-1111-1111-111111111111',parentThreadId:'parent',parentTurnId:'parent-turn',childThreadId:'child',childTurnId:'child-turn',dispatchEventSha256:'e'.repeat(64),childTerminalSha256:'f'.repeat(64),model:'mimo-v2.6-pro-rl',provider:'sova',nativeSemanticAcceptance:'PASS',transcriptSha256:'b'.repeat(64),settlementSha256:'c'.repeat(64),currentOwnerReceiptSha256:'d'.repeat(64)},text=JSON.stringify(run);records[workflow+'.json']={text,value:run};value.workflows[workflow]={file:workflow+'.json',sha256:createHash('sha256').update(text).digest('hex')};}
 const read=(name:string)=>records[name];assert.equal(validateCurrentCodexFrontier(value,read,Date.parse('2026-10-02T00:00:00Z')),true);
 const first=records['responses.json'];for(const patch of [{harness:'minimax'},{nativeSemanticAcceptance:'NOT_TESTED'},{model:'qwen3.8-27b'},{parentThreadId:'another'},{sourceOnly:true}]){const invalid={...first.value,...patch},text=JSON.stringify(invalid),v=structuredClone(value);v.workflows.responses.sha256=createHash('sha256').update(text).digest('hex');assert.equal(validateCurrentCodexFrontier(v,name=>name==='responses.json'?{text,value:invalid}:read(name)),false);}
 assert.equal(validateCurrentCodexFrontier({schema:1,kind:'reviewed-codex-specialists'},read),false);
});

test('first deep success, second Qwen-only completion fails; resumed current MiMo terminal succeeds after close',()=>{
 const c=new CodexChildren(()=> 'parent',()=>{},4,['qwen3.8-27b','mimo-v2.6-pro-rl']),verified=new Set(['mimo']);
 c.thread({id:'mimo',parentThreadId:'parent',modelProvider:'sova',model:'mimo-v2.6-pro-rl'});
 const dispatch=(parentTurnId:string)=>{c.beginParentTurn();c.bindParentTurn(parentTurnId);const item={id:'send-'+parentTurnId,type:'collabAgentToolCall',tool:'sendInput',status:'completed',senderThreadId:'parent',receiverThreadIds:['mimo'],agentsStates:{mimo:{status:'running'}}};const start={...item,status:'inProgress',agentsStates:{}};c.item(start,false);c.bindParentCollaboration(parentTurnId,start,false);c.item(item,true);c.bindParentCollaboration(parentTurnId,item,true);};
 dispatch('parent-1');c.notification('turn/started',{threadId:'mimo',turn:{id:'child-1'}});c.notification('turn/completed',{threadId:'mimo',turn:{id:'child-1',status:'completed'}});
 assert.equal(c.completedCurrentModel('mimo-v2.6-pro-rl',verified),true);
 c.beginParentTurn();c.bindParentTurn('parent-2');
 // Previously validated MiMo identity+old terminal are insufficient even after parent Qwen completes.
 assert.equal(c.completedModel('mimo-v2.6-pro-rl',verified),true);assert.equal(c.completedCurrentModel('mimo-v2.6-pro-rl',verified),false);
 c.notification('turn/completed',{threadId:'mimo',turn:{id:'child-1',status:'completed'}});assert.equal(c.completedCurrentModel('mimo-v2.6-pro-rl',verified),false);
 assert.throws(()=>c.notification('turn/started',{threadId:'mimo',turn:{id:'child-1'}}),/Replayed/);
 dispatch('parent-3');c.notification('turn/started',{threadId:'mimo',turn:{id:'child-2'}});c.notification('turn/completed',{threadId:'mimo',turn:{id:'child-2',status:'completed'}});
 c.item({id:'close',tool:'closeAgent',status:'completed',senderThreadId:'parent',receiverThreadIds:['mimo'],agentsStates:{mimo:{status:'shutdown'}}},true);
 assert.equal(c.completedCurrentModel('mimo-v2.6-pro-rl',verified),true);assert.equal(c.currentTerminalEvidence('mimo-v2.6-pro-rl',verified)[0].parentTurnId,'parent-3');
 c.notification('turn/started',{threadId:'mimo',turn:{id:'child-3'}});c.notification('turn/completed',{threadId:'mimo',turn:{id:'child-3',status:'failed'}});assert.equal(c.completedCurrentModel('mimo-v2.6-pro-rl',verified),false);
 assert.throws(()=>c.bindParentCollaboration('foreign',{receiverThreadIds:['mimo']},true),/Foreign/);
});

test('a pre-dispatch terminal cannot gain lineage from a later ACK; genuine dispatch permits terminal before ACK',()=>{
 const c=new CodexChildren(()=> 'parent',()=>{},4,['qwen3.8-27b','mimo-v2.6-pro-rl']),verified=new Set(['mimo']);
 c.thread({id:'mimo',parentThreadId:'parent',modelProvider:'sova',model:'mimo-v2.6-pro-rl'});
 const item={id:'send',type:'collabAgentToolCall',tool:'sendInput',status:'inProgress',senderThreadId:'parent',receiverThreadIds:['mimo'],agentsStates:{}};
 c.beginParentTurn();c.bindParentTurn('parent-1');
 c.notification('turn/started',{threadId:'mimo',turn:{id:'before-dispatch'}});c.notification('turn/completed',{threadId:'mimo',turn:{id:'before-dispatch',status:'completed'}});
 c.item(item,false);c.bindParentCollaboration('parent-1',item,false);
 const ack={...item,status:'completed',agentsStates:{mimo:{status:'completed'}}};c.item(ack,true);c.bindParentCollaboration('parent-1',ack,true);
 assert.equal(c.completedCurrentModel('mimo-v2.6-pro-rl',verified),false);
 c.beginParentTurn();c.bindParentTurn('parent-2');c.item(item,false);c.bindParentCollaboration('parent-2',item,false);
 c.notification('turn/started',{threadId:'mimo',turn:{id:'after-dispatch'}});c.notification('turn/completed',{threadId:'mimo',turn:{id:'after-dispatch',status:'completed'}});
 assert.equal(c.completedCurrentModel('mimo-v2.6-pro-rl',verified),false);
 c.item(ack,true);c.bindParentCollaboration('parent-2',ack,true);
 assert.equal(c.completedCurrentModel('mimo-v2.6-pro-rl',verified),true);
 assert.match(c.currentTerminalEvidence('mimo-v2.6-pro-rl',verified)[0].dispatchSnapshot,/inProgress/);
 c.beginParentTurn();c.bindParentTurn('parent-3');c.item(item,false);c.bindParentCollaboration('parent-3',item,false);
 c.notification('turn/started',{threadId:'mimo',turn:{id:'cancelled'}});c.notification('turn/completed',{threadId:'mimo',turn:{id:'cancelled',status:'interrupted'}});
 const cancelled={...item,status:'interrupted'};c.item(cancelled,true);c.bindParentCollaboration('parent-3',cancelled,true);
 assert.equal(c.completedCurrentModel('mimo-v2.6-pro-rl',verified),false);
});

test('unambiguous visual creation nouns have creative admission; reasoning and image analysis remain separate',()=>{
 for(const text of ['draw a simple circuit diagram','create a portrait','create a photo','create a sketch','make an architectural drawing','render a photograph']){
  const selected=route({text});assert.equal(selected.intent,'creative');assert.equal(selected.target,'qwen-image-2.1');
  assert.throws(()=>codexAutomaticDirective(selected,{deep:true,technical:true,creative:false}),/temporarily unavailable/);
  assert.match(codexAutomaticDirective(selected,{deep:false,technical:false,creative:true,generationOnly:true}),/generation-only/);
 }
 for(const text of ['draw conclusions','draw conclusions about the photo','create a report','create a report about image compression','draw on experience to solve the problem'])assert.equal(route({text}).intent,'ordinary');
 for(const text of ['analyze this circuit diagram','read this drawing']){
  const selected=route({text,hasImages:true});assert.equal(selected.intent,'technical');assert.equal(selected.target,'qwen3.5-9b+paddleocr-vl-1.6');
  assert.throws(()=>codexAutomaticDirective(selected,{deep:true,technical:false,creative:true}),/temporarily unavailable/);
 }
});
