#!/usr/bin/env node
/** H010 one-shot task client. Reuses installed clients; never starts Sova. */
import assert from 'node:assert/strict';
import {readFileSync,openSync,writeSync,fsyncSync,closeSync,writeFileSync,mkdirSync,existsSync,lstatSync,realpathSync,statfsSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {pathToFileURL,fileURLToPath} from 'node:url';
import {execFileSync} from 'node:child_process';
import http from 'node:http';
import {syncBuiltinESMExports} from 'node:module';

export const RELEASE='/opt/ai-harness/releases/296ae49e44eb250773223885b843994e2c5b9bcc/ai-harness';
export const TASK='/home/user/ai-harness-build/H010-WORKER2-20260927';
const RUN=TASK+'/overlap-02';
const aliases=['qwen3.8-27b-gpu0','qwen3.8-27b'];
const sha=x=>createHash('sha256').update(x).digest('hex');
const now=()=>new Date().toISOString();
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const pins={
 'protected-credential':'d2710addaebfe7a446cd3b32547982bb07599dbddbebc1ca2928718621d7b03f',
 gateway:'efa66cba65511378b6063795dcc1c313640f7c0d66c8c5d318f0c586b0a9325d',
 'image-upstream':'dca47d44a68a39ef56334420117494fb62df817463387db21a9bf924cc193bce',
 'image-codec':'e81900119efd15844fc4c74b68afcda46925319247c6adabb0a8d46a1d8c053b',
 'node-client':'60b8822056fb690b1a9f2148ac3301ceb3a6d55e267f2a7ac4fb79a8be732572',
 'node-availability':'4b8307d5917761a571bdf90de4cd96ac1d9a3afec2746a84f1b3fc83764d7e63',
 'backend-readiness':'8b29c3c44eb27999ae88d4d1428dce02f0b57b2a686b74f18e83b42bb379030f',
};
function localPreflight(){
 assert.equal(process.getuid(),1000);
 for(const p of ['/home/user',TASK,'/home/user/.config/ai-harness']){
  const s=lstatSync(p);assert.equal(realpathSync(p),p);assert(s.isDirectory()&&s.uid===1000&&!(s.mode&0o022));
 }
 assert(statfsSync(TASK).bavail*statfsSync(TASK).bsize>20*1024**3);
 assert.equal(sha(readFileSync('/home/user/.config/systemd/user/ai-harness.service')),'7e339dc3e44e566f5eb8c5206cf37b7123047502564465fda6afaea5a0321b57');
 const unit=execFileSync('systemctl',['--user','show','ai-harness.service','-p','ActiveState','-p','MainPID'],{encoding:'utf8'});
 assert(unit.includes('ActiveState=inactive')&&unit.includes('MainPID=0'));
 for(const [name,digest] of Object.entries(pins))assert.equal(sha(readFileSync(`${RELEASE}/server/dist/${name}.js`)),digest,name);
 const source=readFileSync(`${RELEASE}/server/dist/gateway.js`,'utf8');
 const endpoints=[...source.matchAll(/\{ url: "(http:[^"]+)", alias: "(qwen[^"]+)" \}/g)].map(m=>({url:m[1],alias:m[2]}));
 assert.deepEqual(endpoints.map(x=>x.alias),aliases);
 return {utc:now(),pid:process.pid,release:RELEASE,pins,endpoints,app:'inactive',inference:false};
}
export async function main(argv=process.argv.slice(2)){
 if(argv.includes('--help')){console.log('Usage: node overlap-smoke-02.mjs --prepare | --execute --start-utc ROOT_AGREED_UTC --deadline-utc SESSION_DEADLINE --handback ABS_WORKER1_HANDBACK --coordination-note ABS_ROOT_START_NOTE\nNo inference/import side effects. Execute only after actual Worker1 release and agreed start. One run directory; no retry.');return;}
 process.umask(0o077);
 const preflight=localPreflight();
 if(argv.length===1&&argv[0]==='--prepare'){console.log(JSON.stringify(preflight,null,2));return;}
 assert.equal(argv[0],'--execute');const a={};for(let i=1;i<argv.length;i+=2){assert(['--start-utc','--deadline-utc','--handback','--coordination-note'].includes(argv[i])&&!a[argv[i]]&&argv[i+1]);a[argv[i]]=argv[i+1];}assert.equal(Object.keys(a).length,4);
 const start=Date.parse(a['--start-utc']),deadline=Date.parse(a['--deadline-utc']);
 assert(Number.isFinite(start)&&start>Date.now()&&deadline-start>=900000&&deadline<=Date.parse('2026-09-27T01:06:00Z'),'future agreed window with >=15 minutes required');
 const handback=JSON.parse(readFileSync(a['--handback'],'utf8')),coordination=readFileSync(a['--coordination-note'],'utf8');
 assert.equal(handback.status,'COMPLETE');assert(handback.explicitWorker1Release&&handback.unit.includes('MainPID=0')&&handback.unit.includes('ActiveState=inactive'));
 assert(coordination.includes(a['--start-utc']),'exact agreed UTC absent in root note');
 assert(!existsSync(RUN),'prior attempt exists: no retry');mkdirSync(RUN,{mode:0o700});
 const secrets=new Set(),fd=openSync(RUN+'/ownership.jsonl','wx',0o600);
 const safe=x=>{const t=JSON.stringify(x);for(const s of secrets)assert(!t.includes(s),'secret echo refused');return t;};
 const record=x=>{writeSync(fd,safe({utc:now(),...x})+'\n');fsyncSync(fd);};
 const save=(name,x)=>writeFileSync(RUN+'/'+name,safe(x)+'\n',{mode:0o600,flag:'wx'});
 record({event:'owner',pid:process.pid,startUtc:a['--start-utc'],deadlineUtc:a['--deadline-utc'],handbackSha256:sha(readFileSync(a['--handback'])),coordinationSha256:sha(coordination),scriptSha256:sha(readFileSync(fileURLToPath(import.meta.url))),preflight});
 // Transport-only timestamps in memory. Never inspect auth headers or sync in data callbacks.
 const intervals=[],original=http.request;
 http.request=function(...args){
  const url=args[0] instanceof URL?args[0]:null,options=args[1];
  const measured=url&&options?.method==='POST'&&['/v1/chat/completions','/v1/images/generations'].includes(url.pathname);
  let item;
  if(measured){
   const service=url.pathname.includes('images')?'image':preflight.endpoints.find(e=>new URL(e.url).port===url.port)?.alias;
   assert(service&&!intervals.some(r=>r.service===service),'duplicate or unknown dispatch refused');
   item={service,endpoint:url.origin+url.pathname,requestStartUtc:now(),requestStartMonotonicNs:process.hrtime.bigint().toString()};intervals.push(item);
  }
  const req=original.apply(this,args);
  if(item){req.once('finish',()=>item.requestBodySentUtc=now());req.once('response',res=>{item.firstResponseUtc=now();item.httpStatus=res.statusCode;res.once('data',()=>item.firstBodyByteUtc=now());res.once('end',()=>{item.responseEndUtc=now();item.responseComplete=res.complete;});});req.once('close',()=>item.clientClosedUtc=now());req.once('error',()=>item.transportError=true);}
  return req;
 };syncBuiltinESMExports();
 let observer,gateway,result={status:'FAIL',classification:'H010_OPTIONAL_OVERLAP_SMOKE_ONLY',intervals,atomicDrainClaim:false,gpuKernelSimultaneity:'NOT_TESTED',qwen:[],image:{status:'NOT_TESTED'}};
 try{
  const load=n=>import(pathToFileURL(`${RELEASE}/server/dist/${n}.js`));
  const [{readProtectedCredential},{createGateway},{ImageUpstream},{validateOutput},{NodeAvailability},{nodeClient},{createBackendReadiness}]=await Promise.all(['protected-credential','gateway','image-upstream','image-codec','node-availability','node-client','backend-readiness'].map(load));
  const key=await readProtectedCredential('/home/user/.config/ai-harness/inference-key'),nodeKey=await readProtectedCredential('/home/user/.config/ai-harness/node-control-key');secrets.add(key);secrets.add(nodeKey);
  observer=new NodeAvailability({backend:nodeClient('ai-vm',nodeKey),readiness:createBackendReadiness(key),onLatch:l=>record({event:'observed-hardware-latches',ledger:l})});
  const image=new ImageUpstream({key,requestMs:600000,responseMs:30000});
  gateway=createGateway({upstreamKey:key,availability:id=>observer.get(id),queueTimeoutMs:1000,activeTimeoutMs:180000,onLaneState:(alias,state)=>record({event:'qwen-lane',alias,state})});
  await gateway.app.ready();
  while(Date.now()<start-4000)await delay(Math.min(1000,start-4000-Date.now()));
  localPreflight();await observer.poll();
  for(const id of [...aliases,'image','glm-5.3-flash'])assert.equal(observer.get(id).state,'available',id);
  const caps=await image.capabilities(AbortSignal.timeout(10000));
  const profile=caps.profiles.find(p=>p.operation==='generation'&&p.size==='1024x576'&&p.references===0&&p.transparent===false);
  assert(profile&&caps.ready&&caps.admitting&&!caps.busy,'exact qualified 1024x576 opaque profile unavailable; no resize');
  save('capabilities.json',caps);save('initial-node.json',observer.snapshot());record({event:'boundary-ready',profile});
  assert(Date.now()<start,'missed agreed start: no dispatch');
  while(Date.now()<start)await delay(Math.min(50,start-Date.now()));
  record({event:'dispatch-intent',requests:2,imageGenerations:1});
  observer.start();
  const prompts=[{prompt:'Compute 17 * 19. Reply with exactly 323 and nothing else.',expected:'323'},{prompt:'Sort these integers ascending: 9, 2, 5. Reply with exactly 2,5,9 and nothing else.',expected:'2,5,9'}];
  async function qwen(p,i){
   const token=gateway.issueToken('h010-overlap-'+i);secrets.add(token);
   try{const response=await gateway.app.inject({method:'POST',url:'/v1/chat/completions',headers:{authorization:'Bearer '+token},payload:{model:'qwen3.8-27b',messages:[{role:'user',content:p.prompt}],max_tokens:128,temperature:0,stream:false}});
    let v;try{v=response.json();}catch{throw Error('invalid-response');}
    const text=v.choices?.[0]?.message?.content??'';
    const r={prompt:p.prompt,expected:p.expected,httpStatus:response.statusCode,model:v.model,usage:v.usage??null,finishReason:v.choices?.[0]?.finish_reason??null,content:text,semanticStatus:text.trim()===p.expected?'PASS':'FAIL'};
    r.status=response.statusCode===200&&aliases.includes(v.model)&&r.semanticStatus==='PASS'?'PASS':'FAIL';result.qwen.push(r);
   }catch{result.qwen.push({status:'FAIL',failure:'qwen_request_failed_no_retry'});}finally{gateway.revokeToken(token);}
  }
  async function generate(){
   record({event:'image-owner-active',size:'1024x576',model:caps.model});
   try{
    const out=await image.execute({operation:'generation',model:caps.model,prompt:'A simple flat illustration of a red ceramic mug on a plain pale blue background, centered, landscape composition, no text.',size:'1024x576',seed:20260927,references:[]},AbortSignal.timeout(630000));
    if(out.kind==='not_admitted'){result.image={status:'FAIL',settlement:'NOT_ADMITTED',retry:false};record({event:'image-not-admitted'});return;}
    const artifact=RUN+'/image.png';writeFileSync(artifact,out.png,{mode:0o600,flag:'wx'});
    result.image={status:'FAIL',settlement:'COMPLETE_RESPONSE',model:out.model,seed:out.seed,artifact,sha256:sha(out.png),bytes:out.png.length};
    await validateOutput(out.png,'1024x576');Object.assign(result.image,{status:'PASS',width:1024,height:576,opaque:true,semanticStatus:'PENDING_VISUAL_REVIEW'});record({event:'image-owner-terminal',settlement:'COMPLETE_RESPONSE',sha256:result.image.sha256});
   }catch{result.image.failure='image_failed_no_retry';result.image.settlement??='UNPROVEN';record({event:'image-owner-uncertain',settlement:result.image.settlement});}
  }
  await Promise.all([qwen(prompts[0],0),qwen(prompts[1],1),generate()]);
  await observer.poll();result.finalAvailability=Object.fromEntries([...aliases,'image','glm-5.3-flash'].map(id=>[id,observer.get(id)]));
  result.qwenSettlement=gateway.snapshot();result.imageReadiness=await image.readiness(AbortSignal.timeout(10000));
  result.allOwnedRequestsSettled=result.qwenSettlement.lanes.every(l=>l.state==='idle')&&['COMPLETE_RESPONSE','NOT_ADMITTED'].includes(result.image.settlement)&&result.imageReadiness.ready&&result.imageReadiness.idle;
  result.status=result.qwen.length===2&&result.qwen.every(q=>q.status==='PASS')&&new Set(result.qwen.map(q=>q.model)).size===2&&result.image.status==='PASS'&&result.allOwnedRequestsSettled?'PASS_PENDING_IMAGE_VISUAL_REVIEW':'FAIL';
 }catch{result.failure='smoke_boundary_or_execution_failed_no_retry';}
 finally{
  result.finishedUtc=now();if(gateway)result.qwenSettlement=gateway.snapshot();observer?.stop();await gateway?.close();
  await delay(100);record({event:'terminal',status:result.status,allOwnedRequestsSettled:result.allOwnedRequestsSettled??false});save('SMOKE-02.json',result);closeSync(fd);http.request=original;syncBuiltinESMExports();
 }
 console.log(JSON.stringify({status:result.status,receipt:RUN+'/SMOKE-02.json',allOwnedRequestsSettled:result.allOwnedRequestsSettled??false}));
 if(!result.allOwnedRequestsSettled)process.exitCode=2;
}
if(process.argv[1]&&fileURLToPath(import.meta.url)===process.argv[1])main().catch(()=>{console.error('H010 client refused or failed; inspect retained task evidence; no retry.');process.exitCode=1;});
