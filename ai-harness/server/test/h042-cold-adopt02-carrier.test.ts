/** SOURCE only: real owned Mac old process/Unix socket/HMAC transport, with
 * explicitly typed synthetic Linux protected-file/proc readbacks. No native GO. */
import test from 'node:test';import assert from 'node:assert/strict';
import fs from 'node:fs';import fsp from 'node:fs/promises';import net from 'node:net';
import {fork} from 'node:child_process';import {once} from 'node:events';import {syncBuiltinESMExports} from 'node:module';
import {createHmac} from 'node:crypto';import {tmpdir} from 'node:os';import {join} from 'node:path';
import {loadQualificationTaskAdmission,isQualificationTaskAdmission} from '../src/qualification-task-admission.js';
import {CarrierAdmission} from '../../acceptance/compaction/native-adapter/carrier-admission.js';
import {actionFingerprint,freezeKey} from '../src/dispatch-freeze.js';
import {AUTHORIZATIONS} from '../../acceptance/compaction/authorization.mjs';
import {sha256,stableJson} from '../../acceptance/compaction/native-adapter/projection.js';
import {observeApplicationIdentity} from '../../acceptance/compaction/native-adapter/process-runner.js';
const authority=AUTHORIZATIONS['H041-COMPACTION-DELIVERY-05'],at=Date.parse(authority.startsUtc)+10000;
const boot='00000000-0000-0000-0000-000000000042';
const action={action:'service.stop',node_id:'ai-harness',service_id:'harness',idempotency_key:'SOURCE-cold-adopt02',allow_interrupt:true};

test('SOURCE authenticated retained registration -> real old exit0/death -> branded new adoption -> first verification; rejection matrix',async t=>{
 const directory=fs.realpathSync(fs.mkdtempSync(join(tmpdir(),'h042-cold-uds-'))),socketPath=join(directory,'source.sock');
 const key=Buffer.alloc(32,42),events:any[]=[],registered=new Map<string,any>();let fault='',now=at,abortOnReply:AbortController|undefined;
 const b={admissionPath:'/run/ai-harness-qualification/source-cold-adopt02/admission.json',transactionId:'SOURCE-cold-transaction',sessionId:'SOURCE-carrier',ownHold:{key:freezeKey(action as any),fingerprint:actionFingerprint(action as any),action:JSON.stringify(action),scope:JSON.stringify(['harness'])}};
 const review={authorization:{...authority,windowId:'SOURCE-cold-adopt02'},notAfterUtc:authority.capUtc,settlementReserveMs:120000,carrier:b};
 const expected={pid:process.pid,startTicks:'200',bootId:boot,source:'linux-proc'};
 const sessions=['success','alive','old-birth','old-boot','worker-pid','worker-birth','worker-boot','worker-missing','transaction','hold','stale','future','session','cutoff','abort','read-abort','verify-worker'].map(x=>'SOURCE-'+x);
 let oldPid=0;const previous=()=>({pid:oldPid,startTicks:'100',bootId:boot});
 const alive=()=>{try{process.kill(oldPid,0);return true;}catch(e){if((e as NodeJS.ErrnoException).code==='ESRCH')return false;throw e;}};
 const server=net.createServer(socket=>{let raw='';socket.on('error',error=>{events.push({socketError:error.message,code:(error as NodeJS.ErrnoException).code,fault});if(fault!=='abort')throw error;});socket.on('data',chunk=>{raw+=chunk;if(!raw.endsWith('\n'))return;
  const envelope=JSON.parse(raw),q=JSON.parse(envelope.body);assert.equal(envelope.mac,createHmac('sha256',key).update(envelope.body).digest('hex'));
  events.push({operation:q.operation,sessionId:q.sessionId,oldAlive:alive(),requestUtf8:envelope.body});
  const reject=()=>socket.end('{"status":"reject"}\n');
  if(q.operation==='register'){if(registered.has(q.sessionId))return void reject();registered.set(q.sessionId,{role:'parent',worker:previous()});}
  if(q.operation==='adopt'){
   const prior=registered.get(q.sessionId);if(!prior||stableJson(q.previousWorker)!==stableJson(prior.worker)||alive())return void reject();
   registered.set(q.sessionId,{role:'parent',worker:{pid:expected.pid,startTicks:expected.startTicks,bootId:expected.bootId}});
  }
  if(q.operation==='admit'&&!registered.has(q.sessionId))return void reject();
  const v:any={...q,status:q.operation==='register'?'registered':q.operation==='adopt'?'adopted':'admit',worker:q.operation==='register'?previous():{pid:expected.pid,startTicks:expected.startTicks,bootId:expected.bootId},observedAtMs:now,ownerStartTicks:'123',ownHoldKey:b.ownHold.key};
  if(fault==='worker-pid')v.worker.pid++;if(fault==='worker-birth')v.worker.startTicks='201';if(fault==='worker-boot')v.worker.bootId='FOREIGN';if(fault==='worker-missing')delete v.worker;
  if(fault==='transaction')v.transactionId='FOREIGN';if(fault==='hold')v.ownHoldKey='FOREIGN';if(fault==='stale')v.observedAtMs=now-1501;if(fault==='future')v.observedAtMs=now+1;if(fault==='session')v.sessionId='FOREIGN';
  if(fault==='cutoff')now=Date.parse(authority.capUtc)-120000;if(fault==='abort')abortOnReply!.abort();
  const body=JSON.stringify(v);socket.end(JSON.stringify({body,mac:createHmac('sha256',key).update(body).digest('hex')})+'\n');
 });});
 await new Promise<void>(resolve=>server.listen(socketPath,resolve));
 const workerPath=join(directory,'old-source-worker.mjs'),configPath=join(directory,'source-config.json');
 fs.writeFileSync(workerPath,`import{readFileSync}from'node:fs';import{connect}from'node:net';import{createHmac,randomBytes}from'node:crypto';const c=JSON.parse(readFileSync(process.argv[2],'utf8'));const key=Buffer.from(c.key,'hex');process.send({ready:true,pid:process.pid});process.on('message',async m=>{if(m.method==='register'){const replies=[];for(const sessionId of c.sessions){const body=JSON.stringify({challenge:randomBytes(32).toString('hex'),transactionId:c.transactionId,sessionId,requestId:'register:'+sessionId,lane:'qwen3.8-27b',operation:'register',role:'parent'}),mac=createHmac('sha256',key).update(body).digest('hex');replies.push(await new Promise((resolve,reject)=>{const s=connect(c.socket);let raw='';s.on('error',reject);s.on('data',b=>{raw+=b;if(raw.endsWith('\\n')){s.end();resolve(JSON.parse(JSON.parse(raw).body));}});s.on('connect',()=>s.write(JSON.stringify({body,mac})+'\\n'));}));}process.send({registered:replies});}if(m.method==='shutdown')process.send({closing:true},()=>{process.disconnect();process.exit(0);});});`,{mode:0o600});
 fs.writeFileSync(configPath,JSON.stringify({key:key.toString('hex'),socket:socketPath,sessions,transactionId:b.transactionId}),{mode:0o600});
 const old=fork(workerPath,[configPath],{execArgv:[],stdio:['ignore','ignore','ignore','ipc']});const oldClose=once(old,'close');let oldActualBirth:any,oldExit:any;
 t.after(async()=>{if(old.exitCode===null&&old.signalCode===null)old.send({method:'shutdown'});const [code,signal]=await oldClose;oldExit={code,signal};await new Promise<void>(resolve=>server.close(()=>resolve()));if(process.env.H042_COLD_ADOPT_EVIDENCE_DIR){const out=join(process.env.H042_COLD_ADOPT_EVIDENCE_DIR,'carrier-'+process.pid);fs.mkdirSync(out,{recursive:true,mode:0o700});fs.writeFileSync(join(out,'protocol-original.json'),stableJson({scope:'SOURCE_ONLY',native:'NOT_TESTED',oldActualBirth,oldExit,oldOSAbsent:!alive(),linuxProc:'typed SOURCE fixture',events})+'\n',{mode:0o600});for(const name of fs.readdirSync(directory).filter(n=>n.startsWith('carrier-')))fs.copyFileSync(join(directory,name),join(out,name));}fs.rmSync(directory,{recursive:true,force:true});});
 const ready=(await once(old,'message'))[0] as any;oldPid=ready.pid;oldActualBirth=await observeApplicationIdentity(oldPid);
 old.send({method:'register'});const registeredReplies=(await once(old,'message'))[0] as any;assert.equal(registeredReplies.registered.length,sessions.length);
 const packet={schema:'qualification-task-admission-v1',maxOwnedSessions:64,carrier:{pid:9999,startTicks:'123',bootId:boot},dispatchCutoffMs:Date.parse(authority.capUtc)-120000,expiresAtMs:Date.parse(authority.capUtc),key:key.toString('hex'),lane:'qwen3.8-27b',ownHoldKey:b.ownHold.key,sessionId:b.sessionId,socketPath:b.admissionPath.replace('admission.json','admission.sock'),transactionId:b.transactionId};
 const platform=Object.getOwnPropertyDescriptor(process,'platform')!,read=fs.readFileSync,lstat=fs.lstatSync,real=fs.realpathSync,connect=net.connect,readAsync=fsp.readFile;
 const procStat=(pid:number,ticks:string)=>{const fields=Array(24).fill('0');fields[19]=ticks;return `${pid} (SOURCE typed kernel) ${fields.join(' ')}\n`;};
 Object.defineProperty(process,'platform',{value:'linux'});t.mock.method(Date,'now',()=>now);
 t.mock.method(fs,'readFileSync',(path:any,...args:any[])=>path===b.admissionPath?JSON.stringify(packet):path==='/proc/9999/stat'?procStat(9999,'123'):path==='/proc/9999/status'?'Uid:\t0\t0\t0\t0\n':path==='/proc/sys/kernel/random/boot_id'?boot:(read as any)(path,...args));
 t.mock.method(fs,'lstatSync',(path:any,...args:any[])=>path===b.admissionPath||path===packet.socketPath?{uid:0,mode:path===b.admissionPath?0o640:0o660,nlink:1,size:1000,isFile:()=>path===b.admissionPath,isSocket:()=>path===packet.socketPath}:(lstat as any)(path,...args));
 t.mock.method(fs,'realpathSync',(path:any,...args:any[])=>path===b.admissionPath?path:(real as any)(path,...args));
 t.mock.method(net,'connect',((path:any,...args:any[])=>path===packet.socketPath?connect(socketPath):(connect as any)(path,...args)) as any);
 let abortOnRead:AbortController|undefined,identityReads=0;
 t.mock.method(fsp,'readFile',async(path:any,...args:any[])=>{if(path===`/proc/${process.pid}/stat`){identityReads++;if(abortOnRead&&identityReads>=2)abortOnRead.abort();return procStat(process.pid,'200');}if(path==='/proc/sys/kernel/random/boot_id')return boot+'\n';return (readAsync as any)(path,...args);});syncBuiltinESMExports();
 t.after(()=>{t.mock.restoreAll();syncBuiltinESMExports();Object.defineProperty(process,'platform',platform);});
 const gate=()=>{const admission=loadQualificationTaskAdmission(b.admissionPath);assert.equal(isQualificationTaskAdmission(admission),true);return new CarrierAdmission(admission,b,review);};
 const input=(sessionId:string)=>({sessionId,role:'parent' as const,previousWorker:{...previous(),source:'linux-proc'}});
 await assert.rejects(gate().adoptSession(input('SOURCE-alive'),expected,undefined,directory));assert.equal(alive(),true);
 old.send({method:'shutdown'});const [code,signal]=await oldClose;assert.equal(code,0);assert.equal(signal,null);assert.equal(alive(),false);
 const g=gate(),actual=await g.adoptSession(input('SOURCE-success'),expected,undefined,directory);
 assert.deepEqual(actual.worker,{pid:process.pid,startTicks:'200',bootId:boot});assert.deepEqual(actual.previousWorker,previous());
 const captured=fs.readFileSync(join(directory,`carrier-adopt-${sha256('SOURCE-success')}-${actual.challenge}.json`),'utf8');assert.equal(captured,JSON.stringify(actual));
 assert.equal((await g.verify('SOURCE-success','SOURCE-first-parent-verification',undefined,directory)).sessionId,'SOURCE-success');
 await assert.rejects(g.adoptSession(input('SOURCE-success'),expected,undefined,directory),/duplicate/);await assert.rejects(g.registerSession({sessionId:'SOURCE-success',role:'parent'}),/must_not_register/);
 await assert.rejects(gate().registerSession({sessionId:'SOURCE-success',role:'parent'}));
 for(const [session,patch]of [['old-birth',{startTicks:'101'}],['old-boot',{bootId:'FOREIGN'}]] as const)await assert.rejects(gate().adoptSession({...input('SOURCE-'+session),previousWorker:{...input('SOURCE-'+session).previousWorker,...patch}},expected,undefined,directory));
 for(const bad of [{...expected,pid:process.pid+1},{...expected,startTicks:'201'},{...expected,bootId:'FOREIGN'},{...expected,source:'darwin-ps-source-only'}])await assert.rejects(gate().adoptSession(input('SOURCE-success'),bad,undefined,directory));
 for(const mode of ['worker-pid','worker-birth','worker-boot','worker-missing','transaction','hold','stale','future','session','cutoff','abort']){
  fault=mode;now=at;const failed=gate(),controller=new AbortController();abortOnReply=controller;
  await assert.rejects(failed.adoptSession(input('SOURCE-'+mode),expected,controller.signal,directory));
  if(['worker-pid','worker-birth','worker-boot','worker-missing','future','abort'].includes(mode))await assert.rejects(failed.verify('SOURCE-'+mode,'SOURCE-denied-after-failed-adoption'),/readoption_unconfirmed|expired/);
 }
 fault='';now=at;identityReads=0;abortOnRead=new AbortController();await assert.rejects(gate().adoptSession(input('SOURCE-read-abort'),expected,abortOnRead.signal,directory));abortOnRead=undefined;
 const vg=gate();await vg.adoptSession(input('SOURCE-verify-worker'),expected,undefined,directory);fault='worker-birth';await assert.rejects(vg.verify('SOURCE-verify-worker','SOURCE-wrong-current-worker'),/worker_changed/);fault='';
 const rows=[{...b.ownHold,acknowledged:1}];assert.equal(g.held([...rows,{...rows[0],key:'FOREIGN',scope:JSON.stringify(['harness'])}],'harness'),true);
 const parentEvents=events.filter(e=>e.sessionId==='SOURCE-success');assert.deepEqual(parentEvents.slice(0,3).map(e=>e.operation),['register','adopt','admit']);assert.equal(parentEvents[1].oldAlive,false);
 if(process.env.H042_COLD_ADOPT_EVIDENCE_DIR){const out=join(process.env.H042_COLD_ADOPT_EVIDENCE_DIR,'carrier-'+process.pid);fs.mkdirSync(out,{recursive:true,mode:0o700});const evidence={scope:'SOURCE_ONLY',native:'NOT_TESTED',oldActualBirth,oldExit:{code,signal},oldOSAbsent:!alive(),newActualPid:process.pid,linuxProc:'typed SOURCE fixture',events,adoptionResponseUtf8:captured,adoptionResponseSha256:sha256(captured)};fs.writeFileSync(join(out,'protocol.json'),stableJson(evidence)+'\n',{mode:0o600});for(const name of fs.readdirSync(directory).filter(n=>n.startsWith('carrier-')))fs.copyFileSync(join(directory,name),join(out,name));}
});
