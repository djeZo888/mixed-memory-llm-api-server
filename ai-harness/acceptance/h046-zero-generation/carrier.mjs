/** Narrow dormant H046 carrier. No application/observer/admission import. */
import {readFileSync,writeFileSync,lstatSync,readdirSync} from 'node:fs';
import {join} from 'node:path';
import {pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
import {spawnSync} from 'node:child_process';
const sha=b=>createHash('sha256').update(b).digest('hex');
const need=(v,m)=>{if(!v)throw Error(m);};
const put=(p,b)=>{writeFileSync(p,b,{flag:'wx',mode:0o600});return sha(b);};
const json=v=>JSON.stringify(v);
export function validateAcks(initialize,threadStart,input){
 need(initialize?.codexHome===input.profileDir+'/codex-home'&&initialize.platformOs==='linux'&&initialize.platformFamily==='unix'&&typeof initialize.userAgent==='string'&&initialize.userAgent.includes('0.158.0'),'Invalid genuine initialize ACK');
 need(typeof threadStart?.thread?.id==='string'&&/^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$/.test(threadStart.thread.id)&&threadStart.model==='qwen3.8-27b'&&threadStart.modelProvider==='sova'&&threadStart.cwd===input.workspace&&threadStart.approvalPolicy==='never','Invalid genuine thread/start ACK');
 return threadStart.thread.id;
}
export function effectGate(){let n=0;const wanted=['initialize','initialized','thread/start'];return raw=>{const v=JSON.parse(Buffer.from(raw).toString('utf8'));need(v.method===wanted[n++]&&n<=3,'Forbidden or repeated native effect');need(!('method' in v.params),'Invalid protocol params');};}
export function armProtocolCapture(owned){
 const gate=effectGate(),frames=[];let byteCount=0,seq=0;
 owned.stdout.on('error',error=>{frames.captureFailure=String(error.message);});
 const record=(direction,chunk)=>{const bytes=Buffer.from(chunk);need((byteCount+=bytes.length)<=2*1024*1024,'Raw protocol exceeds private bound');frames.push({sequence:++seq,direction,bytesBase64:bytes.toString('base64'),sha256:sha(bytes)});};
 const write=owned.stdin.write;owned.stdin.write=function(chunk,...args){gate(chunk);record('input',chunk);return write.call(this,chunk,...args);};
 const push=owned.stdout.push;owned.stdout.push=function(chunk,...args){try{if(chunk!==null)record('output',chunk);}catch(error){this.destroy(error);return false;}return push.call(this,chunk,...args);};
 return frames;
}
export async function protocol(owned,Connection,input,abortSignal,frames=armProtocolCapture(owned)){
 need(!frames.captureFailure,'Original raw capture failed');
 let failure;
 let rejectFailure;const failed=new Promise((_,reject)=>{rejectFailure=reject;});void failed.catch(()=>{});
 const connection=new Connection(owned.stdout,owned.stdin,(method)=>{if(!['thread/started'].includes(method)){failure=Error('Unexpected native notification');rejectFailure(failure);}},error=>{failure=error;rejectFailure(error);},15000);
 const stopped=new Promise((_,reject)=>{abortSignal.addEventListener('abort',()=>reject(Error('Finite carrier stop')),{once:true});if(abortSignal.aborted)reject(Error('Finite carrier stop'));});void stopped.catch(()=>{});
 const request=(method,params)=>Promise.race([connection.request(method,params),failed,stopped]);
 try{
  const initialize=await request('initialize',{clientInfo:{name:'sova',title:'Sova',version:'0.0.3'},capabilities:{experimentalApi:false,requestAttestation:false}});
  need(initialize?.codexHome===input.profileDir+'/codex-home'&&initialize.platformOs==='linux'&&initialize.platformFamily==='unix'&&typeof initialize.userAgent==='string'&&initialize.userAgent.includes('0.158.0'),'Invalid genuine initialize ACK');
  connection.initialized();
  const threadStart=await request('thread/start',{model:'qwen3.8-27b',modelProvider:'sova',cwd:input.workspace,approvalPolicy:'never',sandbox:'read-only',ephemeral:false});
  const nativeThreadId=validateAcks(initialize,threadStart,input);return {initialize,threadStart,nativeThreadId,frames};
 }finally{connection.fail(Error('Owned no-generation protocol closed'));}
}
export async function shutdownOwned(owned){
 const cleanup=await owned.terminateAndConfirm().catch(()=>false);
 let timer;try{
  await Promise.race([owned.exited,new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error('Owned parent exit missing after cleanup budget')),3000);})]);
 }finally{clearTimeout(timer);}
 return {cleanup,exit:await owned.exitObservation,settlement:await owned.settlementReceipt};
}
function birth(pid){const s=readFileSync(`/proc/${pid}/stat`,'utf8').split(')').slice(1).join(')').trim().split(/\s+/);return {pid,startTicks:s[19],pgid:Number(s[2]),bootId:readFileSync('/proc/sys/kernel/random/boot_id','utf8').trim()};}
function snapshot(input,out,name){const r=spawnSync(input.python,[join(input.helperDir,'metadata.py'),'--input',input.inputPath,'--output',join(out,name)],{timeout:12000,env:{PATH:'/usr/bin:/bin',HOME:process.env.HOME,USER:process.env.USER,LOGNAME:process.env.LOGNAME,XDG_RUNTIME_DIR:process.env.XDG_RUNTIME_DIR},encoding:'utf8'});need(r.status===0,'Fresh actual metadata snapshot failed');return JSON.parse(readFileSync(join(out,name),'utf8'));}
async function main(){
 const [inputPath,output]=process.argv.slice(2);need(inputPath&&output&&process.platform==='linux'&&process.getuid()>0,'Private Linux input/output required');
 const input=JSON.parse(readFileSync(inputPath,'utf8'));input.inputPath=inputPath;
 need(input.nativeThreadId==='UNALLOCATED'&&input.runtime.version==='0.158.0'&&input.runtime.upstream==='064c6b8c737f5b41d171fdda80bd9ef10ad06eb3'&&input.runtime.context===480000&&input.runtime.auto===400000&&input.runtime.output===65536,'Pinned fresh-only carrier required');
 const modules={};for(const name of ['codex-launcher','codex-connection','codex-receipts','codex-ordinary-entry'])modules[name]=await import(pathToFileURL(join(input.serverDir,'dist',name+'.js')));
 const receipts=modules['codex-receipts'];const before=snapshot(input,output,'gateway-before.json');
 const token=readFileSync(input.gatewayTokenPath,'utf8');need(token.length>=16&&token.length<=4096&&!/[\x00-\x1f\x7f]/.test(token),'Protected gateway credential format');
 let owned,launch,result,settlement,exit,cleanup=false,fault=null,validation,originals={},observedBirths=[],frames=[];
 const abort=new AbortController();const timer=setTimeout(()=>abort.abort(),Math.min(45000,input.workBudgetMs));process.once('SIGTERM',()=>abort.abort());process.once('SIGINT',()=>abort.abort());
 try{
  owned=await modules['codex-launcher'].createRootlessCodexLauncher(input.deploymentDir+'/run-codex.sh',{linuxTransportQualified:true,sourceSha256:input.receiptSources})({sessionId:input.sessionId,receiptRunId:input.controlRunId,profileDir:input.profileDir,workspace:input.workspace,codexHome:input.profileDir+'/codex-home',gatewayUrl:'http://10.0.2.2:8081/v1',gatewayToken:token,modelPolicyVersion:modules['codex-launcher'].CODEX_MODEL_POLICY,imageJobsQualified:false,imageGenerationQualified:false,technicalVisionQualified:false,nativeTraceMode:'off'});
  frames=armProtocolCapture(owned);
  put(join(output,'channel.json'),json({directory:owned.receiptChannelDirectory}));
  launch=await owned.launchReceipt;need(launch&&receipts.isVerifiedCodexLaunchReceipt(launch)&&receipts.codexReceiptProvenance(launch)&&!receipts.isHistoricalCodexReceipt(launch),'Missing genuine current launch provenance');
  validation=receipts.codexReceiptValidation(launch);need(validation,'Missing authenticated validation record');
  observedBirths=[birth(launch.producer.pid),birth(launch.container.pid)];put(join(output,'observed-births.json'),json(observedBirths));
  const binaryPath=`/proc/${launch.container.pid}/root/opt/sova/bin/codex`;const binary=readFileSync(binaryPath);need(binary.length<512*1024*1024&&sha(binary)==='167c0148a849d2444f1b5a7fb5f8bb2de1de5ae13a2a504b833fc765980f5cd9'&&birth(launch.container.pid).startTicks===launch.container.pidStartTicks,'Actual pinned native binary unavailable or changed');
  originals.binarySha256=put(join(output,'native-codex'),binary);
  result=await protocol(owned,modules['codex-connection'].CodexConnection,input,abort.signal,frames);
 }catch(error){fault=String(error?.message??error);}
 finally{
  clearTimeout(timer);
  if(owned){({cleanup,exit,settlement}=await shutdownOwned(owned));
   const diagnostics=await owned.launcherDiagnostics;if(diagnostics){put(join(output,'launcher-stderr.original'),diagnostics.bytes);put(join(output,'launcher-stderr-metadata.json'),json({sha256:diagnostics.sha256,truncated:diagnostics.truncated,complete:diagnostics.complete}));}
   const failed=await owned.launchFailureObservation;if(failed?.rawUtf8)put(join(output,'launch-failure.original.json'),failed.rawUtf8);
   if(owned.receiptChannelDirectory){for(const name of readdirSync(owned.receiptChannelDirectory)){if(!/^[a-z-]+\.(json|ready)$/.test(name))continue;const p=join(owned.receiptChannelDirectory,name),st=lstatSync(p);need(st.isFile()&&!st.isSymbolicLink()&&st.uid===process.getuid()&&(st.mode&0o777)===0o600&&st.nlink===1&&st.size<=65536,'Invalid original channel file');put(join(output,'channel-'+name),readFileSync(p));}}
  }
 }
 const after=snapshot(input,output,'gateway-after.json');
 if(launch){const raw=receipts.getCodexReceiptUtf8(launch);need(raw,'Launch raw provenance missing');originals.launchSha256=put(join(output,'launch.original.json'),raw);}
 if(settlement){need(receipts.isVerifiedCodexSettlementReceipt(settlement)&&receipts.codexReceiptProvenance(settlement),'Settlement lacks authentic current producer provenance');originals.settlementSha256=put(join(output,'settlement.original.json'),receipts.getCodexReceiptUtf8(settlement));}
 const rawProtocol=json(frames);originals.rawProtocolSha256=put(join(output,'raw-protocol.original.json'),rawProtocol);
 const successful=!!(!frames.captureFailure&&result&&launch&&settlement&&cleanup&&settlement.requestedStop&&Number.isInteger(settlement.engineExitStatus)&&Number.isInteger(exit?.code)&&exit.signal===null&&!exit.spawnFailed&&!fault);
 const ack={schema:'codex-zero-generation-acks-v1',launchNonce:launch?.nonce,initialize:result?.initialize,threadStart:result?.threadStart,providerRequests:null};
 const legacy={status:successful?'PASS':'FAIL',validatedInitialize:!!result,validatedThread:!!result,requestedStop:settlement?.requestedStop===true,cleanupOk:cleanup,engineExitStatus:settlement?.engineExitStatus,receipts:{launch:{sha256:originals.launchSha256},settlement:{sha256:originals.settlementSha256}},rawProtocolSHA256:originals.rawProtocolSha256,gatewayBefore:before,gatewayAfter:after};
 originals.protocolAckSha256=put(join(output,'protocol-acks.json'),json(ack));originals.legacyTransportSha256=put(join(output,'legacy-transport.json'),json(legacy));
 if(successful)modules['codex-ordinary-entry'].assertOrdinaryNoGenerationObservation(ack,legacy,originals);
 const projection=successful?{launchPath:join(output,'launch.original.json'),settlementPath:join(output,'settlement.original.json'),protocolAckPath:join(output,'protocol-acks.json'),legacyTransportPath:join(output,'legacy-transport.json'),rawProtocolPath:join(output,'raw-protocol.original.json'),binaryPath:join(output,'native-codex'),...originals,binaryVersion:'0.158.0',upstream:input.runtime.upstream,binding:validation.binding,observedProducer:validation.observedProducer,validatedAtMs:validation.validatedAtMs}:null;
 put(join(output,'carrier-result.json'),json({schema:'h046-zero-generation-carrier-result-v1',status:successful?'CARRIER_PROTOCOL_VALID':'FAIL',ordinaryApproval:'ROOT_REVIEW_AND_SIGN_REQUIRED',nativeThreadId:result?.nativeThreadId??null,launchCurrentProvenance:!!(launch&&receipts.codexReceiptProvenance(launch)),settlementCurrentProvenance:!!(settlement&&receipts.codexReceiptProvenance(settlement)),exitObservation:exit,cleanup,observedBirths,projection,fault,captureFailure:frames.captureFailure??null,invocations:{nativeStart:owned?1:0,ownedShutdown:owned?1:0,turnStart:0,turnResume:0,compact:0,generation:0}}));
 need(successful,'Actual native carrier proof failed');
}
if(import.meta.url===pathToFileURL(process.argv[1]??'').href)main().catch(error=>{console.error(String(error.message));process.exitCode=1;});
