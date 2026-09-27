#!/usr/bin/env node
/** Gated task runner. Never promotes or starts units; no native code/profile patch. */
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync,copyFileSync,openSync,writeSync,fsyncSync,closeSync,existsSync} from 'node:fs';
import {join,dirname,resolve} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {execFileSync} from 'node:child_process';
import {createGuards,sha,FLASH} from './guards.mjs';
import {preflight,checkPromoted,podman,RELEASE,RUNROOT,KEY,IMAGE,SOURCE} from './preflight.mjs';
const here=dirname(fileURLToPath(import.meta.url));
if(process.argv.includes('--help')){
  console.log('Usage: node live.mjs --gate ABS/ROOT-LIVE-GATE.json --gate-sha256 HEX --activation-manifest ABS/ACTIVATION-MANIFEST-03.json\nLinux user1000 only. Exact promotion, root live gate and Worker1 lane release first. Reuses existing observer and launcher. Default refuses; no promotion/start/replay.');process.exit(0);
}
const args={};for(let i=2;i<process.argv.length;i+=2){assert(['--gate','--gate-sha256','--activation-manifest'].includes(process.argv[i])&&!args[process.argv[i]]&&process.argv[i+1]);args[process.argv[i]]=process.argv[i+1];}
assert.equal(Object.keys(args).length,3,'explicit coordinator gate/digest/activation manifest required');
process.umask(0o077);
const {gate,promoted,observerCredential}=preflight(args,here);
assert(!existsSync(RUNROOT),'never replay/reopen a prior acceptance run or clear its quarantine');
mkdirSync(RUNROOT,{mode:0o700});mkdirSync(join(RUNROOT,'payloads'),{mode:0o700});
const started=Date.now(),deadline=Math.min(started+480000,Date.parse(gate.expiresUtc)-60000);
assert(deadline>started+60000,'insufficient coordinator window');
const fd=openSync(join(RUNROOT,'events.jsonl'),'wx',0o600),secretValues=new Set();
const write=(file,value)=>{const text=JSON.stringify(value,null,2)+'\n';for(const secret of secretValues)assert(!text.includes(secret),'secret echo refused');writeFileSync(join(RUNROOT,file),text,{mode:0o600,flag:'wx'});};
let lastRecordSync=Date.now();
function record(value,durable=true){const text=JSON.stringify({at:new Date().toISOString(),...value})+'\n';for(const s of secretValues)assert(!text.includes(s),'secret echo refused');writeSync(fd,text);if(durable||Date.now()-lastRecordSync>=1000){fsyncSync(fd);lastRecordSync=Date.now();}}
write('OWNER.json',{pid:process.pid,source:SOURCE,image:IMAGE,startedUtc:new Date(started).toISOString(),deadlineUtc:new Date(deadline).toISOString(),rootGateSha256:args['--gate-sha256'],taskRoot:RUNROOT,promoted});
const dist=join(RELEASE,'server/dist');const load=n=>import(pathToFileURL(join(dist,n+'.js')));
const [{createApp},{createGateway},{createEngine},{FrontierLedger},{readProtectedCredential},{prepareMimo},{NodeAvailability},{nodeClient},{createBackendReadiness}]=await Promise.all(['app','gateway','engine','frontier-ledger','protected-credential','mimo','node-availability','node-client','backend-readiness'].map(load));
const key=await readProtectedCredential(KEY);secretValues.add(key);
const observerKey=await readProtectedCredential(observerCredential);secretValues.add(observerKey);
const prompts=JSON.parse(readFileSync(join(here,'prompts.json')));
const tokenSessions=new Map(),engines=new Map(),requests=[],states=[],qwenUsage=[],ownedContainers=new Map();
let mode='full-live',phase='code',app,gateway,ledger,closing=false;
const observer=new NodeAvailability({backend:nodeClient('ai-vm',observerKey),readiness:createBackendReadiness(key),onLatch:l=>record({event:'node-latch',ledger:l}),changed:()=>gateway?.notifyAvailabilityChanged()});
const available=id=>Date.now()<Date.parse(gate.expiresUtc)?observer.get(id):{state:'unknown',dispatch:'reject'};
function within(p,ms=Math.max(1,deadline-Date.now())){let timer;return Promise.race([p,new Promise((_,no)=>timer=setTimeout(()=>no(Error('fixture_deadline')),ms))]).finally(()=>clearTimeout(timer));}
function capture(original,effective,meta){
  assert(Date.now()<deadline&&!closing,'fixture_dispatch_closed');
  assert.equal(available(meta.route.startsWith('/frontier')?FLASH:'qwen3.8-27b').dispatch,'allow');
  if(meta.route.startsWith('/frontier'))assert(original.tool_choice===undefined||original.tool_choice==='auto','H009 requires native default/explicit auto tool choice');
  const countAndInferencePayload=meta.route.startsWith('/frontier')?prepareMimo(effective).json:null;
  const seq=requests.length+1;const item={seq,phase,...meta,original,effective,...(countAndInferencePayload?{countAndInferencePayload,countAndInferencePayloadSha256:sha(countAndInferencePayload)}:{})};requests.push(item);
  write(`payloads/${String(seq).padStart(4,'0')}.json`,item);
  record({event:'payload-captured',seq,phase,...meta});
}
const guards=createGuards({record,capture,getMode:()=>mode,toolsSha256:gate.toolsSha256,
  resolveSession:req=>tokenSessions.get(req.headers.authorization?.slice(7))??null,
  persist:r=>{
    if(r.state==='queued'){
      const item=requests.find(p=>p.sessionId===r.sessionId&&p.route.startsWith('/frontier')&&!p.boundFrontierId);assert(item,'missing actual native payload binding');item.boundFrontierId=r.id;
      record({event:'payload-binding',frontierRequestId:r.id,requestId:item.requestId,seq:item.seq,countAndInferencePayloadSha256:item.countAndInferencePayloadSha256});
    }
    ledger.record(r);states.push({...r,phase});
  },

});
function ownedEngine(o){
  checkPromoted();const engine=createEngine({...o,onNativeSessionId:id=>{record({event:'native-session',sessionId:o.sessionId,nativeSessionId:id});o.onNativeSessionId(id);},
    onUpdate:u=>{record({event:'native-update',sessionId:o.sessionId,type:u.type,kind:u.kind,name:u.name,taskId:u.taskId,subagentId:u.subagentId,parentSessionId:u.parentSessionId,backgroundTaskId:u.backgroundTaskId,status:u.status,update:u},u.type!=='text');o.onUpdate(u);}});
  engines.set(o.sessionId,engine);
  const start=engine.start.bind(engine);engine.start=async()=>{await start();
    for(const id of podman('ps','--quiet','--no-trunc').split('\n').filter(Boolean)){
      const mounts=JSON.parse(podman('inspect','--format','{{json .Mounts}}',id));
      if(mounts.some(m=>m.Source===o.profileDir)&&mounts.some(m=>m.Source===o.workspace)){
        ownedContainers.set(id,{profileDir:o.profileDir,workspace:o.workspace});record({event:'owned-container',id,sessionId:o.sessionId,profileDir:o.profileDir,workspace:o.workspace});
      }
    }
  };return engine;
}
const issue=id=>{const token=gateway.issueToken(id);tokenSessions.set(token,id);secretValues.add(token);return token;};
async function api(method,url,payload){const r=await app.app.inject({method,url,headers:{host:'127.0.0.1:8080'},...(payload===undefined?{}:{payload})});assert(r.statusCode<300,'fixture API failed: '+r.statusCode);return r.json();}
async function newSession(label){const {session}=await api('POST','/api/sessions',{});record({event:'session',label,sessionId:session.id});const s=app.store.getSession(session.id),workspace=app.files.workspace(s.workspaceId);
  for(const file of ['edge.mjs','check.mjs','policy-a.txt','policy-b.txt'])copyFileSync(join(here,file),join(workspace,file));return session.id;}
async function run(id,text,{allowFailed=false}={}){
  assert(Date.now()<deadline);const {runId}=await api('POST',`/api/sessions/${id}/messages`,{text});record({event:'run',sessionId:id,runId,phase});
  await within(app.broker.idle());const row=app.store.db.prepare('SELECT status FROM runs WHERE id=?').get(runId);
  const snapshot=await api('GET',`/api/sessions/${id}`);write(`snapshot-${runId}.json`,snapshot);
  assert(row && (row.status==='completed'||allowFailed),'native run did not complete');
  assert(!app.store.isQuarantined(app.store.getSession(id).workspaceId),'native settlement quarantine');return {runId,snapshot};
}
function calls(sessionId,name){const found=new Map();for(const r of requests.filter(r=>r.sessionId===sessionId&&r.mode==='qwen'))for(const m of r.original.messages??[])for(const c of m.tool_calls??[])if(c.function?.name===name)found.set(c.id,c);return [...found.values()];}
function taskResult(sessionId){
  for(const r of [...requests].reverse().filter(r=>r.sessionId===sessionId&&r.mode==='qwen'))for(const m of r.original.messages??[]){
    if(m.role!=='tool')continue;const value=typeof m.content==='string'?m.content:(m.content??[]).map(p=>p.text??'').join('');
    const match=/<task_result\s+task_id="([^"]+)"\s+session_id="([^"]+)"/.exec(value);if(match){const content=value.slice(match.index+match[0].length).replace(/^[^>]*>/,'').replace(/<\/task_result>[\s\S]*$/,'').trim();const finalText=/\nfinal_text:\n([\s\S]*?)\nerror_message:/.exec(content)?.[1]?.trim();assert(content.includes('run_status: succeeded')&&content.includes('resolved_agent_name: frontier')&&finalText,'missing successful nonempty frontier final result');return {taskId:match[1],childSessionId:match[2],resultSha256:sha(value),finalTextSha256:sha(finalText),finalTextLength:finalText.length};}
  }throw Error('actual native foreground task result IDs absent');
}
async function snapshotChildren(id){const engine=engines.get(id);assert(engine?.connection?.request,'pinned ACP connection inspection seam unavailable');const nativeId=app.store.getSession(id).nativeSessionId;
  const result=await within(engine.connection.request('mcode/session/delegation/get',{sessionId:nativeId}),5000);assert(result.snapshot?.complete===true&&result.snapshot.rootSessionId===nativeId);return result.snapshot;}
let status='FAILED',failure,summary={},timer;
try{
  await observer.poll();for(const alias of [FLASH,'qwen3.8-27b-gpu0','qwen3.8-27b'])assert.equal(available(alias).dispatch,'allow','fresh canonical ready/unlatched DTO required');
  write('initial-node-observation.json',observer.snapshot());observer.start();
  app=await createApp({dataDir:join(RUNROOT,'data'),launcher:join(RELEASE,'deploy/run-engine.sh'),engineFactory:ownedEngine,gatewayUrl:'http://10.0.2.2:8081/v1',issueToken:issue,revokeToken:t=>gateway.revokeToken(t),allowedOrigins:['http://127.0.0.1:8080'],visionAvailable:false,availability:available,
    dispatchHeld:()=>closing||Date.now()>=deadline,frontierStatus:id=>({...gateway.frontierSnapshot(),requests:ledger.latest(id)})});
  ledger=new FrontierLedger(app.store.db);app.store.db.exec('CREATE TABLE fixture_lanes(alias TEXT PRIMARY KEY,state TEXT NOT NULL)');
  gateway=createGateway({upstreamKey:key,availability:available,dispatchHeld:()=>closing||Date.now()>=deadline,
    onLaneState:(alias,state)=>{app.store.db.prepare('INSERT OR REPLACE INTO fixture_lanes VALUES(?,?)').run(alias,state);record({event:'lane',alias,state});},
    onUsage:u=>{qwenUsage.push(u);record({event:'qwen-usage',...u});},
    frontier:(await load('active-frontier')).loadActiveFrontier((await load('active-frontier')).loadFrontierSelection(),key,guards.onRequestState)});
  gateway.app.addHook('preValidation',guards.preValidation);
  await gateway.app.listen({host:'127.0.0.1',port:8081});
  timer=setTimeout(()=>{closing=true;record({event:'deadline-stop'});app.broker.close().catch(()=>{});},Math.max(1,deadline-Date.now()));
  const codeId=await newSession('h016-foreground-edge-code');const code=await run(codeId,prompts.code);
  const call=calls(codeId,'task');assert.equal(call.length,1);const input=JSON.parse(call[0].function.arguments);assert(input.agent_name==='frontier'&&input.run_in_background!==true&&!input.model);
  const codeResult=taskResult(codeId),children=await snapshotChildren(codeId);assert(children.members.some(m=>m.sessionId===codeResult.childSessionId&&m.agentName==='frontier'));
  assert(calls(codeId,'bash').some(c=>JSON.parse(c.function.arguments).command?.includes('check.mjs')),'Qwen independent bash verification missing');
  const workspace=app.files.workspace(app.store.getSession(codeId).workspaceId);assert.equal(sha(readFileSync(join(workspace,'check.mjs'))),sha(readFileSync(join(here,'check.mjs'))),'verification file changed');assert.notEqual(sha(readFileSync(join(workspace,'edge.mjs'))),sha(readFileSync(join(here,'edge.mjs'))),'child made no change');execFileSync(process.execPath,['check.mjs'],{cwd:workspace,timeout:5000,env:{PATH:'/usr/bin:/bin'},stdio:'pipe'});
  write('code-native-ids.json',{parentSessionId:children.rootSessionId,...codeResult,children,parentModel:'custom_provider:harness/qwen3.8-27b',childModel:'custom_provider:frontier/mimo-v2.6-pro-rl',modelEvidence:'actual native route payloads, unchanged profile, native foreground result and ACP delegation graph'});
  const childRequests=requests.filter(r=>r.sessionId===codeId&&['full-live','narrow-live'].includes(r.mode));
  assert(childRequests.length>0 && childRequests.every(r=>r.original.model===FLASH && r.route==='/frontier/v1/chat/completions'),'actual child model/route mismatch');
  const pairedTools=new Map();
  for(const r of childRequests) {
    const messages=r.original.messages??[];
    for(let i=0;i<messages.length;i++) {
      const m=messages[i];if(m.role!=='assistant')continue;
      for(const c of m.tool_calls??[]) {
        if(!['read','edit','write','bash'].includes(c.function?.name))continue;
        const result=messages.slice(i+1).find(v=>v.role==='tool'&&v.tool_call_id===c.id);
        const resultText=typeof result?.content==='string'?result.content:(result?.content??[]).map(p=>p.text??'').join('');
        if(!resultText.trim())continue;
        pairedTools.set(c.id,{toolCallId:c.id,name:c.function.name,argumentsSha256:sha(c.function.arguments),resultSha256:sha(result.content),requestSeq:r.seq,frontierRequestId:r.boundFrontierId});
      }
    }
  }
  assert(pairedTools.size>0,'actual MiMo assistant tool call with matching tool result absent');
  assert([...pairedTools.values()].some(c=>c.name==='bash'),'MiMo bash tool result absent');
  const final=code.snapshot.messages.filter(m=>m.role==='assistant'&&m.phase==='final'&&m.content?.trim());
  assert(final.length>0,'actual Qwen final answer absent');
  write('child-tool-proof.json',{childNativeSessionId:codeResult.childSessionId,parentNativeSessionId:children.rootSessionId,taskId:codeResult.taskId,provider:'custom_provider:frontier',model:FLASH,route:'/frontier/v1/chat/completions',toolChoices:[...new Set(childRequests.map(r=>r.original.tool_choice??'native-default-auto'))],binding:'exactly one foreground frontier task; native task result and delegation graph; its MiMo wire history with paired tool_call_id',pairedTools:[...pairedTools.values()],childResult:codeResult,parentFinal:final.map(m=>({id:m.id,sha256:sha(m.content)}))});
  assert.equal(gateway.frontierSnapshot().state,'idle');const finals=new Map();for(const r of states)finals.set(r.id,r);assert(finals.size>1&&[...finals.values()].every(r=>r.state==='settled'),'native requests not serially settled');
  summary={codeSessionId:codeId,qwenUsage,mimoRequests:states,childUsefulToolNames:[...new Set([...pairedTools.values()].map(c=>c.name))],semanticReview:'PENDING_ROOT_REVIEW',additionalCases:'NOT_TESTED: no new cancellation/reconnect concern',scope:'one Qwen parent and MiMo foreground child; full production tools; no projection, count-only replay or overlap test'};status='COMPLETED_PENDING_ROOT_REVIEW';
}catch(e){failure=String(e.code??e.message).slice(0,200);for(const s of secretValues)failure=failure.replaceAll(s,'[REDACTED]');record({event:'failed',code:failure});}
finally{
  closing=true;clearTimeout(timer);mode='closed';observer.stop();
  try{if(app)await within(app.broker.close(),40000);if(gateway)await within(gateway.close(),20000);if(app)await within(app.app.close(),10000);}catch{status='SETTLEMENT_UNKNOWN';}
  for(const [id,paths]of ownedContainers){const present=podman('ps','--all','--quiet','--filter',`id=${id}`);record({event:'container-settlement',id,present:!!present,...paths});if(present)status='SETTLEMENT_UNKNOWN';}
  write('RESULT.json',{status,failure,startedUtc:new Date(started).toISOString(),endedUtc:new Date().toISOString(),...summary,upperStartAuthorized:false,productionDataModified:false});
  fsyncSync(fd);closeSync(fd);
}
process.exitCode=status==='COMPLETED_PENDING_ROOT_REVIEW'?0:1;
