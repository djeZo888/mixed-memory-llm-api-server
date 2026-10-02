import test from 'node:test';
import assert from 'node:assert/strict';
import { composeCodexHost, imageGateForCodexLaunch } from '../src/codex-host.js';
import { createGateway } from '../src/gateway.js';

test('host remains disabled without trusted runtime proof and settlement fails closed', async () => {
  const host = composeCodexHost('/legacy/custom-minimax.sh', () => undefined);
  assert.equal(host.runtime.protocolQualified, false);
  assert.equal(host.responses, undefined);
  assert.equal(await host.runtime.confirmGatewaySettlement({ sessionId: 'x', gatewayToken: 'x', activeTurnId: null }), false);
  assert.throws(() => host.runtime.revokeGatewaySession('x'));
  assert.throws(() => composeCodexHost('/trusted/deploy/run-codex.sh', () => undefined, {} as any));
});
test('Codex scope cannot submit image work, bypass Responses or reach frontier; MiniMax unchanged', async () => {
  const g = createGateway({ upstreamKey: 'fixture-secret' });
  const token = g.issueToken('codex-session', 'codex');
  for (const url of ['/v1/image-jobs', '/v1/chat/completions', '/frontier/v1/responses']) {
    const r = await g.app.inject({ method: 'POST', url, headers: {authorization: `Bearer ${token}`}, payload: {} });
    assert.equal(r.statusCode,403);assert.equal(r.json().error.code,'codex_route_unqualified');
  }
  const native = g.issueToken('native-session');
  const r = await g.app.inject({method:'POST',url:'/v1/chat/completions',headers:{authorization:`Bearer ${native}`},payload:{}});
  assert.notEqual(r.statusCode,403);
  g.revokeSession('codex-session');
  assert.equal((await g.app.inject({url:'/v1/models',headers:{authorization:`Bearer ${token}`}})).statusCode,401);
  await g.close();
});

test('trusted bounded child gate matches managed max4 while image remains independently disabled',()=>{
 const host=composeCodexHost('/trusted/deploy/run-codex.sh',()=>undefined,{protocolQualified:true,rootlessQualified:true,nativeDelegationQualified:true,qualifiedAliases:['qwen3.8-27b-gpu0'],verifyLane:async()=>{throw Error('not invoked');}});
 assert.equal(host.runtime.delegationEnabled,true);assert.equal(host.runtime.maxChildren,4);assert.equal(host.runtime.imageToolEnabled,false);assert.deepEqual(host.responses?.qualifiedAliases,['qwen3.8-27b-gpu0']);
});

test('trusted image gate enables specialist independently and safe diagnostics are wired without tracing',()=>{
 const onResponsesError=()=>{};
 const host=composeCodexHost('/trusted/deploy/run-codex.sh',()=>undefined,{protocolQualified:true,rootlessQualified:true,imageJobsQualified:true,onResponsesError,verifyLane:async()=>{throw Error('not invoked');}});
 assert.equal(host.runtime.imageToolEnabled,true);assert.equal(host.runtime.delegationEnabled,false);assert.equal(host.responses?.onError,onResponsesError);assert.equal('onTrace' in host.responses!,false);assert.equal(host.responses?.outputLimit,undefined);
});

test('private image scope is evaluated for each launch without advertising global capability',async()=>{
 const seen:string[]=[];const host=composeCodexHost('/trusted/deploy/run-codex.sh',()=>undefined,{protocolQualified:true,rootlessQualified:true,verifyLane:async()=>{throw Error('not invoked');},imageAcceptance:id=>{seen.push(id);return id==='owned';}});
 assert.equal(host.runtime.imageToolEnabled,false);assert.deepEqual(seen,[]);
 for(const sessionId of ['owned','unrelated']) await assert.rejects(host.runtime.launchRootless({sessionId,profileDir:'/fixture',workspace:'/fixture/work',codexHome:'/fixture/codex-home',gatewayUrl:'http://invalid',gatewayToken:'fixture',modelPolicyVersion:'invalid'}),/Unqualified Codex rootless policy/);
 assert.deepEqual(seen,['owned','unrelated']);assert.equal(host.runtime.imageToolEnabled,false);
});

test('isolated receipt-run cannot bypass text-only policy through per-session image acceptance',()=>{
 const host=composeCodexHost('/trusted/deploy/run-codex.sh',()=>undefined,{protocolQualified:true,rootlessQualified:true,imageAcceptance:()=>true,verifyLane:async()=>{throw Error('unused');}});
 // Actual launch cannot run on Mac; source composition must put the probe gate before acceptance.
 let calls=0;const gate={protocolQualified:true as const,rootlessQualified:true as const,imageAcceptance:()=>{calls++;return true;},verifyLane:async()=>{throw Error('unused');}};
 assert.equal(imageGateForCodexLaunch({sessionId:'s',receiptRunId:'probe'},gate),false);assert.equal(calls,0);assert.equal(imageGateForCodexLaunch({sessionId:'s'},gate),true);assert.equal(calls,1);
 assert.equal(imageGateForCodexLaunch({sessionId:'s',receiptRunId:'probe'},{...gate,imageJobsQualified:true}),false);
 assert.equal(host.runtime.imageToolEnabled,false);
 assert.throws(()=>composeCodexHost('/trusted/deploy/run-codex.sh',()=>undefined,{protocolQualified:true,rootlessQualified:true,readOriginalProbe:()=>undefined,verifyLane:async()=>{throw Error('unused');}}),/receipt transport/);
 assert.throws(()=>composeCodexHost('/trusted/deploy/run-codex.sh',()=>undefined,{protocolQualified:true,rootlessQualified:true,nativeReceiptPolicy:{linuxTransportQualified:true,sourceSha256:{}},readOriginalProbe:()=>undefined,verifyLane:async()=>{throw Error('unused');}}),/model tool\/sandbox scope is unqualified/);
});

import {PassThrough} from 'node:stream';
import {CodexEngine} from '../src/codex-engine.js';
import {createCodexAutomaticRoute} from '../src/codex-automatic-routing.js';
import {loadCodexResumeInstructions} from '../src/codex-instructions.js';
import {fileURLToPath} from 'node:url';
test('qualified ordinary Qwen receives source-backed delegation guidance in actual native turn/start; fresh startup retains mounted catalog',async()=>{
 const launcher=fileURLToPath(new URL('../../deploy/run-codex.sh',import.meta.url));
 const host=composeCodexHost(launcher,()=>undefined,{protocolQualified:true,rootlessQualified:true,nativeDelegationQualified:true,frontierResponsesQualified:true,verifyLane:async()=>{throw Error('not invoked');}});
 const stdin=new PassThrough(),stdout=new PassThrough(),calls:any[]=[];let pending='';
 stdin.on('data',chunk=>{pending+=chunk.toString();let end;while((end=pending.indexOf('\n'))!==-1){const r=JSON.parse(pending.slice(0,end));pending=pending.slice(end+1);calls.push(r);if(!r.id)continue;
  const result=r.method==='initialize'?{codexHome:'/task/profile/codex-home',platformOs:'linux',platformFamily:'unix',userAgent:'codex/0.158.0'}:r.method==='thread/start'?{thread:{id:'parent'},model:'qwen3.8-27b',modelProvider:'sova',cwd:'/task/workspace',approvalPolicy:'never'}:r.method==='turn/start'?{turn:{id:'turn'}}:{};
  stdout.write(JSON.stringify({id:r.id,result})+'\n');if(r.method==='turn/start')setImmediate(()=>stdout.write(JSON.stringify({method:'turn/completed',params:{threadId:'parent',turn:{id:'turn',status:'completed'}}})+'\n'));
 }});
 host.runtime.launchRootless=async()=>({stdin,stdout,exited:new Promise(()=>{}),terminateAndConfirm:async()=>true});host.runtime.confirmGatewaySettlement=async()=>true;host.runtime.revokeGatewaySession=()=>{};
 const engine=new CodexEngine({sessionId:'chat',profileDir:'/task/profile',workspace:'/task/workspace',launcher,engineKind:'codex',engineVersion:host.runtime.pin.version,modelPolicyVersion:host.runtime.modelPolicyVersion,nativeState:{ownership:'idle',activeTurnId:null,eventCursor:0},onNativeState:()=>{},gatewayUrl:host.runtime.gatewayUrl,gatewayToken:'synthetic-only',stderrPath:'/unused',onUpdate:()=>{},onNativeSessionId:()=>{},onExit:()=>{}},host.runtime);
 try{assert.equal(await engine.prompt('Investigate a difficult multi-step design',[],createCodexAutomaticRoute({text:'Investigate a difficult multi-step design'})),'completed');
  assert.equal(calls.find(c=>c.method==='thread/start').params.baseInstructions,undefined);
  const input=calls.find(c=>c.method==='turn/start').params.input;assert.match(input[0].text,/automatically delegates deeper research/);assert.match(input[0].text,/new work for this controlling turn/);assert.match(input[0].text,/Investigate a difficult multi-step design/);
  assert.equal(host.runtime.model,'qwen3.8-27b');
 }finally{await engine.close();stdin.destroy();stdout.destroy();}
 const closed=composeCodexHost(launcher,()=>undefined,{protocolQualified:true,rootlessQualified:true,nativeDelegationQualified:true,verifyLane:async()=>{throw Error('never');}});
 assert.match(closed.runtime.automaticRouting!(createCodexAutomaticRoute({text:'ordinary task'}),'chat'),/unqualified/);
});
