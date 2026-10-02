/** SOURCE_ONLY: synthetic authority/owner and API fixtures never qualify native/UI/job/PNG behavior. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {randomUUID,createHmac} from 'node:crypto';
import {mkdtempSync,mkdirSync,writeFileSync,readFileSync,rmSync,chmodSync} from 'node:fs';
import {join} from 'node:path';
import {canonicalJson} from '../src/codex-canonical.js';
import {createHostGenerationAcceptance,validateCodexGenerationAcceptance,reviewedCodexSourceFlags,type CodexGenerationAcceptanceTicket} from '../src/codex-generation-acceptance.js';
import {composeCodexHost,imageGateForCodexLaunch} from '../src/codex-host.js';
import {codexDeployment} from '../src/codex-deployment.js';
import {createCodexAutomaticRoute} from '../src/codex-automatic-routing.js';
import {codexReceiptSourceProfile} from '../src/codex-receipts.js';
import {createGateway} from '../src/gateway.js';
import {currentSpecialistSourcePaths} from '../src/codex-specialist-qualification.js';
const authority={sourceCommit:'a'.repeat(40),profile:'technical-generation' as const,currentSourceSha256:'b'.repeat(64),receiptSourcesSha256:'c'.repeat(64)};
const owner={pid:123,startTicks:'456',uid:501,bootId:randomUUID(),cgroupPath:'/app'};
const key=Buffer.alloc(32,7);
const seal=(body:unknown)=>({body,seal:createHmac('sha256',key).update(canonicalJson(body)).digest('hex')});
function fixture(absent=false){
 const dir=mkdtempSync(join(process.cwd(),'.h046-generation-'));chmodSync(dir,0o700);
 const policy=join(dir,'policy.json'),keyPath=join(dir,'key'),id=randomUUID(),sid=randomUUID(),rid=randomUUID();
 let now=1000,active:string|undefined,sourcesCurrent=true,currentOwner=owner;
 const ticket:CodexGenerationAcceptanceTicket={schema:'codex-normal-generation-acceptance-v1',reviewedBy:'root',id,sessionId:sid,issuedAtMs:900,expiresAtMs:10000,maxNativeRuns:1,maxImageJobs:1,operation:'generation',size:'1920x1080',authority,owner};
 mkdirSync(join(dir,id),{mode:0o700});writeFileSync(keyPath,key,{mode:0o600});
 const write=(body:unknown=ticket)=>writeFileSync(policy,JSON.stringify(seal(body)),{mode:0o600});if(!absent)write();
 const manager=createHostGenerationAcceptance(policy,keyPath,{authority,assertCurrent(){if(!sourcesCurrent)throw Error('changed exact sources');},assertNativeReceipt(){if(!sourcesCurrent)throw Error('source-only fixture receipt rejection');}},s=>s===sid?active:undefined,()=>now,()=>currentOwner);
 return {dir,policy,sid,rid,id,ticket,manager,write,setActive:(v?:string)=>active=v,setNow:(v:number)=>now=v,setSources:(v:boolean)=>sourcesCurrent=v,setOwner:(v:typeof owner)=>currentOwner=v,close(){manager.close();rmSync(dir,{recursive:true,force:true});}};
}
test('signed finite source/owner authority rejects stale malformed foreign and broadened packets',()=>{
 const f=fixture();try{
  assert.equal(validateCodexGenerationAcceptance(seal(f.ticket),key,authority,owner,1000).sessionId,f.sid);
  assert.throws(()=>validateCodexGenerationAcceptance({...seal(f.ticket),seal:'0'.repeat(64)},key,authority,owner,1000));
  for(const patch of [{schema:2},{issuedAtMs:1001},{expiresAtMs:1000},{expiresAtMs:1900001},{maxNativeRuns:2},{maxImageJobs:2},{operation:'edit'},{size:'1024x1024'},{image:true},{authority:{...authority,currentSourceSha256:'d'.repeat(64)}},{owner:{...owner,startTicks:'789'}}])assert.throws(()=>validateCodexGenerationAcceptance(seal({...f.ticket,...patch}),key,authority,owner,1000));
  assert.throws(()=>validateCodexGenerationAcceptance(seal(f.ticket),key,{...authority,profile:'ordinary'},owner,1000));
 }finally{f.close();}
});
test('dynamic post-start ticket binds exactly one normal UI run, native invocation and immutable job',()=>{
 const f=fixture(true);try{
  f.manager.onRunAccepted(f.sid,f.rid);assert.equal(f.manager.generation(f.sid),false);
  f.write();f.manager.onRunAccepted(randomUUID(),f.rid);f.manager.onRunAccepted(f.sid,f.rid);
  assert.equal(f.manager.generation(f.sid),false);f.setActive(f.rid);assert(f.manager.generation(f.sid));assert.equal(f.manager.generation(randomUUID()),false);
  const job={requestId:randomUUID(),operation:'generation',prompt:'a blue lake',size:'1920x1080'};
  assert.equal(f.manager.authorizeJob(f.sid,job),false);assert.equal(f.manager.authorizeLaunch(randomUUID()),false);assert(f.manager.authorizeLaunch(f.sid));assert.equal(f.manager.authorizeLaunch(f.sid),false);
  assert.equal(f.manager.authorizeJob(f.sid,job),false,'native receipt admission is independently required');
  f.manager.assertLaunch({sessionId:f.sid,runId:randomUUID(),nonce:'e'.repeat(64),sources:Object.fromEntries(codexReceiptSourceProfile(true,true).map(p=>[p,'b'.repeat(64)])),container:{mounts:[],additionalMounts:[]}} as any); // SOURCE_ONLY synthetic host callback, never transport qualification.
  for(const patch of [{operation:'edit'},{references:[{fileId:randomUUID()}]},{references:'bad'},{size:'1024x1024'},{child:true}])assert.equal(f.manager.authorizeJob(f.sid,{...job,...patch}),false);
  assert(f.manager.authorizeJob(f.sid,job));assert(f.manager.authorizeJob(f.sid,job));assert.equal(f.manager.authorizeJob(f.sid,{...job,prompt:'different'}),false);assert.equal(f.manager.authorizeJob(f.sid,{...job,requestId:randomUUID()}),false);
  assert.equal(JSON.parse(readFileSync(join(f.dir,f.id,'binding.json'),'utf8')).settlementClaim,false);
  f.manager.onRunFinished(f.sid,randomUUID());assert(f.manager.generation(f.sid));f.manager.onRunFinished(f.sid,f.rid);assert.equal(f.manager.generation(f.sid),false);assert(f.manager.generationJob(f.sid),'accepted job retains existing broker drain after parent ends');f.setNow(10000);assert(f.manager.generationJob(f.sid));f.setSources(false);assert.equal(f.manager.generationJob(f.sid),false);f.setSources(true);f.setNow(1000);f.manager.onRunAccepted(f.sid,randomUUID());assert.equal(f.manager.generation(f.sid),false);
  const restart=createHostGenerationAcceptance(f.policy,join(f.dir,'key'),{authority,assertCurrent(){},assertNativeReceipt(){}},()=>f.rid,()=>1000,()=>owner);restart.onRunAccepted(f.sid,f.rid);assert.equal(restart.generation(f.sid),false);restart.close();
 }finally{f.close();}
});
test('changed source, policy, owner, expiry and active run close scoped creation',()=>{
 for(const kind of ['source','policy','owner','expiry','run','unsafe'] as const){const f=fixture();try{
  f.manager.onRunAccepted(f.sid,f.rid);f.setActive(f.rid);assert(f.manager.generation(f.sid));
  if(kind==='source')f.setSources(false);if(kind==='policy')f.write({...f.ticket,size:'1024x1024'});if(kind==='owner')f.setOwner({...owner,startTicks:'999'});if(kind==='expiry')f.setNow(10000);if(kind==='run')f.setActive(randomUUID());if(kind==='unsafe')chmodSync(f.policy,0o666);
  assert.equal(f.manager.generation(f.sid),false);assert.equal(f.manager.authorizeLaunch(f.sid),false);
 }finally{f.close();}}
});
const qualification=(technical:boolean,acceptance:(sid:string)=>boolean)=>({protocolQualified:true as const,rootlessQualified:true as const,verifyLane:async()=>{throw Error('no inference');},nativeDelegationQualified:true as const,imageGenerationAcceptance:acceptance,imageGenerationLaunchAcceptance:acceptance,...(technical?{technicalVisionQualified:true as const}:{}),nativeReceiptPolicy:{linuxTransportQualified:true as const,sourceSha256:Object.fromEntries(codexReceiptSourceProfile(technical,true).map(p=>[p,'b'.repeat(64)]))}});
test('scoped parent selects generation before startup without advertising global LIVE or full image',async()=>{
 for(const technical of [false,true]){
  const sid=randomUUID(),host=composeCodexHost('/trusted/deploy/run-codex.sh',()=>undefined,qualification(technical,s=>s===sid));
  const deployed=codexDeployment({enablePreview:true,runtime:host.runtime,runtimeForSession:host.runtimeForSession});
  assert.equal(host.runtime.imageGenerationEnabled,false);assert.equal(host.runtime.imageToolEnabled,false);assert.equal(deployed.enginePolicy!.codex!.imageGenerationEnabled,false);assert.equal(imageGateForCodexLaunch({sessionId:sid},qualification(technical,s=>s===sid)),false);
  const route=createCodexAutomaticRoute({text:'Generate an image of a lake'});assert.match(deployed.automaticRoutePreflight!(route,sid),/Edits, references and creative child delegation are closed/);
  assert.throws(()=>deployed.automaticRoutePreflight!(route,randomUUID()),/temporarily unavailable/);
  let launched:any;host.runtime.launchRootless=async input=>{launched=input;throw Error('source-test stop before any process or inference');};
  const options={sessionId:sid,engineKind:'codex' as const,engineVersion:host.runtime.pin.version,modelPolicyVersion:host.runtime.modelPolicyVersion,nativeState:{ownership:'idle' as const,activeTurnId:null,reason:null},onNativeState(){},profileDir:'/fixture/profile',workspace:'/fixture/workspace',launcher:'/trusted/deploy/run-codex.sh',gatewayUrl:host.runtime.gatewayUrl,gatewayToken:'source-fixture',stderrPath:'/fixture/err',onNativeSessionId(){},onUpdate(){}};
  const engine=deployed.codexEngineFactory!(options);await assert.rejects(engine.start(),/source-test stop/);assert.equal(launched.imageGenerationRequested,true);
  host.runtime.automaticRouting!(route,sid);assert.throws(()=>deployed.codexEngineFactory!({...options,nativeSessionId:'existing-native'}),/fresh normal parent/);
 }
});
test('source profile must be exact; ordinary and technical without generation intent retain their flags',()=>{
 const q=qualification(true,()=>true),host=composeCodexHost('/trusted/run-codex.sh',()=>undefined,q);
 const ordinary=createCodexAutomaticRoute({text:'Explain this sentence'});host.runtime.automaticRouting!(ordinary,'owned');assert.equal(host.runtimeForSession('owned').runtime.imageGenerationEnabled,false);assert.equal(host.runtime.technicalVisionEnabled,true);
 assert.throws(()=>composeCodexHost('/trusted/run-codex.sh',()=>undefined,{...q,nativeReceiptPolicy:{...q.nativeReceiptPolicy,sourceSha256:Object.fromEntries(codexReceiptSourceProfile(true,false).map(p=>[p,'b'.repeat(64)]))}}),/Generation-only/);
 assert.throws(()=>composeCodexHost('/trusted/run-codex.sh',()=>undefined,{...q,imageJobsQualified:true}),/Ambiguous/);
 assert.equal(reviewedCodexSourceFlags({...q.nativeReceiptPolicy.sourceSha256,unexpected:'b'.repeat(64)}),undefined);
 assert.equal(reviewedCodexSourceFlags({...q.nativeReceiptPolicy.sourceSha256,'run-codex.sh':'invalid'}),undefined);
 const paths=currentSpecialistSourcePaths('/release/server/dist','/release/deploy','generation');for(const name of ['codex-generation-acceptance','codex-ordinary-entry','owned-acceptance','codex-preview-main'])assert(paths.includes('/release/server/dist/'+name+'.js'));
});
test('normal gateway scopes generation only, rechallenges creation and preserves owned status/cancel after expiry',async()=>{
 let active=true,claim:string|undefined;const calls:string[]=[];
 const images={submit:async(s:string,b:any)=>{calls.push(s+':'+b.operation);return {id:'original'};},get:()=>({id:'original'}),cancel:()=>({id:'original'}),capabilities:()=>({profiles:[{operation:'generation'},{operation:'edit'}]})};
 const g=createGateway({upstreamKey:'source-fixture',images:images as any,imageGenerationAcceptance:s=>s==='owned'&&active,authorizeScopedGenerationJob:(_s,b:any)=>{if(claim&&claim!==b.requestId)return false;claim=b.requestId;return true;}});
 try{
  const headers={authorization:'Bearer '+g.issueToken('owned','codex')},foreign={authorization:'Bearer '+g.issueToken('foreign','codex')};const job={requestId:randomUUID(),operation:'generation',prompt:'lake',size:'1920x1080'};
  assert.equal((await g.app.inject({method:'POST',url:'/v1/image-jobs',headers:foreign,payload:job})).statusCode,403);
  for(const patch of [{operation:'edit'},{references:[{fileId:randomUUID()}]},{references:'bad'}])assert.equal((await g.app.inject({method:'POST',url:'/v1/image-jobs',headers,payload:{...job,...patch}})).statusCode,403);
  assert.deepEqual((await g.app.inject({method:'GET',url:'/v1/image-capabilities',headers})).json().profiles,[{operation:'generation'}]);
  assert.equal((await g.app.inject({method:'POST',url:'/v1/image-jobs',headers,payload:job})).statusCode,200);
  assert.equal((await g.app.inject({method:'POST',url:'/v1/image-jobs',headers,payload:{...job,requestId:randomUUID()}})).statusCode,403);
  active=false;assert.equal((await g.app.inject({method:'POST',url:'/v1/image-jobs',headers,payload:job})).statusCode,403);
  assert.equal((await g.app.inject({method:'GET',url:'/v1/image-jobs/original',headers})).statusCode,200);assert.equal((await g.app.inject({method:'POST',url:'/v1/image-jobs/original/cancel',headers,payload:{}})).statusCode,200);assert.deepEqual(calls,['owned:generation']);
 }finally{await g.close();}
});

test('ordinary message API follows real broker preflight/factory/start order with scoped profile and unchanged health',async()=>{
 const {createApp}=await import('../src/app.js');
 const dir=mkdtempSync(join(process.cwd(),'.h046-broker-'));chmodSync(dir,0o700);
 let ownedSid:string|undefined;const launches:{sessionId:string;imageGenerationRequested?:true}[]=[];
 const host=composeCodexHost('/fixture/deploy/run-codex.sh',()=>undefined,qualification(false,s=>s===ownedSid));
 host.runtime.launchRootless=async input=>{launches.push(input);throw Error('SOURCE_ONLY fixture stops before any native process');};
 const deployed=codexDeployment({enablePreview:true,runtime:host.runtime,runtimeForSession:host.runtimeForSession});
 const app=await createApp({...deployed,dataDir:dir,newChatEngine:'codex',launcher:'/fixture/launcher',gatewayUrl:host.runtime.gatewayUrl,engineFactory:()=>{throw Error('No alternative harness');},issueToken:()=> 'fixture-only',revokeToken(){},allowedOrigins:['http://localhost']});
 const inject=(url:string,payload?:unknown)=>app.app.inject({url,method:payload===undefined?'GET':'POST',headers:{host:'localhost'},...(payload===undefined?{}:{payload})});
 const until=async(check:()=>boolean)=>{const deadline=Date.now()+2000;while(!check()){if(Date.now()>deadline)throw Error('source API fixture timeout');await new Promise(r=>setTimeout(r,5));}};
 try{
  ownedSid=(await inject('/api/sessions',{})).json().session.id;
  const owned=await inject(`/api/sessions/${ownedSid}/messages`,{text:'Generate an image of a lake',submissionId:'fixture-scoped'});assert.equal(owned.statusCode,202,owned.body);
  await until(()=>launches.length===1);assert.equal(launches[0].sessionId,ownedSid);assert.equal(launches[0].imageGenerationRequested,true);
  const foreign=(await inject('/api/sessions',{})).json().session.id;
  const denied=await inject(`/api/sessions/${foreign}/messages`,{text:'Generate an image of a mountain',submissionId:'fixture-foreign'});assert.equal(denied.statusCode,202,denied.body);
  await until(()=>app.store.runSnapshot(denied.json().runId).status==='failed');assert.equal(launches.length,1);
  const ordinary=(await inject('/api/sessions',{})).json().session.id;
  assert.equal((await inject(`/api/sessions/${ordinary}/messages`,{text:'Explain the word lake',submissionId:'fixture-text'})).statusCode,202);
  await until(()=>launches.length===2);assert.equal(launches[1].imageGenerationRequested,undefined);
  const health=(await inject('/api/health')).json();assert.equal(health.engines.codex.imageToolEnabled,false);assert.equal(health.engines.codex.capabilityDetails.imageGeneration.supported,false);assert.equal(health.engines.codex.capabilityDetails.imageGeneration.qualification,'not_tested');
 }finally{await app.app.close();rmSync(dir,{recursive:true,force:true});}
});
test('genuine global generation gate remains independent of absent scoped binding and job claim',async()=>{
 const q={...qualification(false,()=>false),imageGenerationQualified:true as const,imageGenerationLaunchAcceptance:()=>{throw Error('scoped launch must not gate global proof');}};
 const host=composeCodexHost('/trusted/deploy/run-codex.sh',()=>undefined,q),route=createCodexAutomaticRoute({text:'Generate an image'});
 assert.match(host.runtime.automaticRouting!(route,'regular-user'),/generation-only/);assert.equal(host.runtime.imageGenerationEnabled,true);assert.equal(host.runtimeForSession('regular-user').runtime,host.runtime);
 const images={submit:async()=>({id:'global'}),capabilities:()=>({profiles:[{operation:'generation'},{operation:'edit'}]})};
 const g=createGateway({upstreamKey:'source-fixture',images:images as any,codexImageGenerationQualified:true,imageGenerationAcceptance:()=>false,authorizeScopedGenerationJob:()=>{throw Error('scoped job claim must not gate global proof');}});
 try{assert.equal((await g.app.inject({method:'POST',url:'/v1/image-jobs',headers:{authorization:'Bearer '+g.issueToken('regular-user','codex')},payload:{operation:'generation'}})).statusCode,200);}finally{await g.close();}
});
