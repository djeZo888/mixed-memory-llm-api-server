/** SOURCE ONLY. Actual owned local Mac Node application processes and OS reads;
 * the parent/checkpoint/admission protocol below is a fixture, not native or
 * Linux qualification. The frozen historical clock grants no operational GO. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,realpath,writeFile,readFile,readdir,mkdir,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {OwnedApplicationRunner,observeApplicationIdentity,type ApplicationIdentity} from '../../acceptance/compaction/native-adapter/process-runner.js';
import {AUTHORIZATIONS} from '../../acceptance/compaction/authorization.mjs';
import {sha256,stableJson} from '../../acceptance/compaction/native-adapter/projection.js';

// The fixture independently reads OS identity in each acquired process. No
// source fixture supplies linux-proc evidence or constructs a RestartTicket.
const worker=String.raw`
import {readFile,writeFile,appendFile} from 'node:fs/promises';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {createHash} from 'node:crypto';
const exec=promisify(execFile),bytes=await readFile(process.argv[2]),config=JSON.parse(bytes);
const sha=x=>createHash('sha256').update(x).digest('hex'),same=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
if(process.platform!=='darwin')throw Error('SOURCE_Mac_only_fixture');
const identity=async pid=>({pid,startTicks:(await exec('/bin/ps',['-p',String(pid),'-o','lstart='])).stdout.trim(),bootId:(await exec('/usr/sbin/sysctl',['-n','kern.boottime'])).stdout.trim(),source:'darwin-ps-source-only'});
const self=await identity(process.pid);
const mark=async(event,details={})=>appendFile(config.events,JSON.stringify({event,pid:process.pid,...details})+'\n',{mode:0o600});
const send=(id,result)=>new Promise(resolve=>process.send({id,result},()=>resolve()));
await mark('acquired',{identity:self});
let registered=false,adopted=false,parent;
async function oldAbsence(before){
 const argv=['-p',String(before.pid),'-o','lstart='];let observed;
 try{observed=await exec('/bin/ps',argv);}
 catch(error){
  if(error.code===1&&!error.signal&&String(error.stdout??'').trim()==='')return {kind:'known-ps-no-process',command:'/bin/ps',argv,exitCode:1,signal:null,stdout:error.stdout??'',stderr:error.stderr??''};
  throw error;
 }
 const startTicks=observed.stdout.trim();if(!startTicks)throw Error('SOURCE_ambiguous_old_identity_read');
 const bootId=(await exec('/usr/sbin/sysctl',['-n','kern.boottime'])).stdout.trim();
 if(bootId!==before.bootId)throw Error('SOURCE_old_boot_changed');
 if(startTicks===before.startTicks)throw Error('SOURCE_old_application_still_present');
 return {kind:'exact-pid-birth-reuse',observed:{pid:before.pid,startTicks,bootId,source:'darwin-ps-source-only'}};
}
process.on('message',async m=>{
 if(m.cancel)return;
 try{
  if(m.method==='registerParent'){
   if(registered||adopted)throw Error('SOURCE_duplicate_registration');
   parent=config.parent;registered=true;await mark('registered',{sessionId:parent.sessionId,identity:self});
   await send(m.id,{sessionId:parent.sessionId,registered:true});return;
  }
  if(m.method==='prepareRestart'){
   if(!registered)throw Error('SOURCE_registered_old_parent_required');
   const state={source:'SOURCE-only-parent-handoff',oldApplication:self,parent,checkpoint:m.args.checkpoint,acceptedContinuation:m.args.acceptedContinuation??null,
    producer:{pid:process.pid+10000000,startTicks:'SOURCE-supervisor-not-application',bootId:'SOURCE-native-producer',source:'SOURCE-native-producer-fixture'}};
   const stateUtf8=JSON.stringify(state);await writeFile(config.handoff,stateUtf8,{mode:0o600});
   await mark('prepareRestart',{oldApplication:self,producer:state.producer,stateSha256:sha(stateUtf8)});
   await send(m.id,{statePath:config.handoff,stateSha256:sha(stateUtf8)});return;
  }
  if(m.method==='close'){
   const closeReceiptUtf8=JSON.stringify({source:'SOURCE-only-owned-close',worker:self,sessionId:config.parent.sessionId,state:'released'});
   await mark('close',{closeReceiptUtf8,closeReceiptSha256:sha(closeReceiptUtf8)});
   await send(m.id,{settlement:{state:'released'},closeReceiptUtf8,closeReceiptSha256:sha(closeReceiptUtf8)});return;
  }
  if(m.method==='shutdown'){
   await mark('shutdown');await send(m.id,{shutdownAcknowledged:true});process.disconnect();process.exit(0);
  }
  if(m.method==='adoptRestart'){
   if(registered||adopted)throw Error('SOURCE_restart_worker_not_fresh');
   const actual=await identity(process.pid),stateBytes=await readFile(m.args.statePath),state=JSON.parse(stateBytes);
   if(sha(stateBytes)!==m.args.stateSha256)throw Error('SOURCE_handoff_changed');
   if(!same(m.args.beforeProcess,state.oldApplication))throw Error('SOURCE_previous_application_identity_changed');
   if(!same(m.args.afterProcess,actual))throw Error('SOURCE_current_application_identity_changed');
   if(actual.bootId!==m.args.beforeProcess.bootId)throw Error('SOURCE_wrong_old_boot');
   const absence=await oldAbsence(m.args.beforeProcess);
   if(m.args.oldExit?.code!==0||m.args.oldExit?.signal!==null)throw Error('SOURCE_original_old_exit_required');
   if(actual.pid===m.args.beforeProcess.pid&&actual.startTicks===m.args.beforeProcess.startTicks)throw Error('SOURCE_new_birth_required');
   if(!same(state.checkpoint,m.args.checkpoint)||!same(state.parent,config.parent))throw Error('SOURCE_same_parent_bytes_changed');
   if(!same(state.acceptedContinuation,m.args.acceptedContinuation??null))throw Error('SOURCE_accepted_artifact_bytes_changed');
   parent=state.parent;adopted=true;
   const sourceFixtureAdoptionReceiptUtf8=JSON.stringify({source:'SOURCE-only-application-adoption',before:m.args.beforeProcess,after:actual,oldExit:m.args.oldExit,oldAbsence:absence,sessionId:parent.sessionId,nativeThreadId:parent.nativeThreadId,parent,stateSha256:m.args.stateSha256});
   await mark('adoptRestart',{sourceFixtureAdoptionReceiptUtf8,sourceFixtureAdoptionReceiptSha256:sha(sourceFixtureAdoptionReceiptUtf8)});
   await send(m.id,{nativeThreadId:config.changedParent?'SOURCE-replacement-parent':parent.nativeThreadId,afterStateUtf8:state.checkpoint.stateUtf8,replayedActionIds:config.replay?['SOURCE-replayed-answer']:[],sourceFixtureAdoptionReceiptUtf8,sourceFixtureAdoptionReceiptSha256:sha(sourceFixtureAdoptionReceiptUtf8)});return;
  }
  if(m.method==='verifyParent'){
   if(!adopted)throw Error('SOURCE_adoption_required_before_first_verification');
   await mark('firstVerification',{sessionId:parent.sessionId,nativeThreadId:parent.nativeThreadId});
   await send(m.id,{sessionId:parent.sessionId,nativeThreadId:parent.nativeThreadId,parent});return;
  }
  throw Error('SOURCE_unknown_method');
 }catch(error){await mark('failure',{method:m.method,error:String(error.message)});process.send({id:m.id,error:'SOURCE_fixture_operation_rejected'});}
});
process.send({ready:true,protocol:'h041-owned-application-ipc-v1',configSha256:sha(bytes)});
`;

const authority=AUTHORIZATIONS['H041-COMPACTION-DELIVERY-05'];
const checkpoint={stateUtf8:'SOURCE full parent state, original messages and checkpoint bytes\n',stateSha256:sha256('SOURCE full parent state, original messages and checkpoint bytes\n'),nativeThreadId:'SOURCE-SAMEparent-thread'};
const acceptedContinuation={artifactId:'SOURCE-registered-artifact',messageId:'SOURCE-registered-message',bytesUtf8:'{"source":"SOURCE accepted artifact bytes"}',digest:sha256('{"source":"SOURCE accepted artifact bytes"}')};
const parent={sessionId:'SOURCE-SAMEparent-session',nativeThreadId:checkpoint.nativeThreadId,layout:{root:'SOURCE-owned-layout',dataDir:'SOURCE-store',hostPrivate:'SOURCE-private'},policyReceiptUtf8:'SOURCE-original-accepted-policy-receipt',rolloutUtf8:'SOURCE-original-native-rollout',artifact:acceptedContinuation};
function identityOnly(p:ApplicationIdentity){return {pid:p.pid,startTicks:p.startTicks,bootId:p.bootId,source:p.source};}

async function fixture(t:any,label:string,options:Record<string,unknown>={}){
 t.mock.method(Date,'now',()=>Date.parse('2026-10-01T15:00:00Z'));
 const root=await realpath(await mkdtemp(join(tmpdir(),'h042-cold-adopt02-ipc-'))),eventsPath=join(root,'events.jsonl'),configPath=join(root,'config.json'),workerPath=join(root,'worker.mjs');
 const config=JSON.stringify({events:eventsPath,handoff:join(root,'handoff.json'),parent,...options});await writeFile(configPath,config,{mode:0o600});await writeFile(workerPath,worker,{mode:0o600});
 const runners:OwnedApplicationRunner[]=[],facts:any={source:'owned-local-Mac-Node-IPC',qualification:'SOURCE',native:'NOT_TESTED',linux:'NOT_TESTED',status:'INCOMPLETE',label};
 const runner=()=>{const r=new OwnedApplicationRunner({workerPath,workerSha256:sha256(worker),configPath,configSha256:sha256(config),hostPrivate:root,review:{authorization:{...authority,windowId:'SOURCE-h042-cold-adopt02'},notAfterUtc:authority.capUtc,settlementReserveMs:120000},operationTimeoutMs:3000});runners.push(r);return r;};
 const events=async()=>{try{return (await readFile(eventsPath,'utf8')).trim().split('\n').filter(Boolean).map(line=>JSON.parse(line));}catch(error:any){if(error.code==='ENOENT')return [];throw error;}};
 // Teardown preserves raw bytes even on assertion failure. Cleanup signals no
 // unrelated PID: each runner retains its exact acquired process owner.
 t.after(async()=>{
  const errors:unknown[]=[],exits=[];for(const r of runners)if(r.hasAcquiredProcess())try{const exit=await r.shutdownAndConfirm();exits.push(exit);assert.deepEqual(exit,{code:0,signal:null});}catch(error){errors.push(error);}facts.finalOwnedExits=exits;
  const rows=await events();facts.applicationIdentities=rows.filter(row=>row.event==='acquired').map(row=>row.identity);facts.finalAbsence=[];
  for(const id of facts.applicationIdentities){
   let current:ApplicationIdentity|undefined;
   try{current=await observeApplicationIdentity(id.pid);}catch(error:any){
    // Only the actual known ps no-process read is source evidence of absence.
    if(error.code===1&&!error.signal&&String(error.stdout??'').trim()==='')facts.finalAbsence.push({identity:id,knownPsAbsent:true,exitCode:error.code,signal:error.signal??null,stdout:error.stdout??'',stderr:error.stderr??''});
    else{errors.push(error);facts.finalAbsence.push({identity:id,observationRejected:true,error:String(error)});}
   }
   if(current){try{assert.notDeepEqual(identityOnly(current),id);assert.equal(current.bootId,id.bootId);facts.finalAbsence.push({identity:id,exactBirthReused:true,current});}catch(error){errors.push(error);facts.finalAbsence.push({identity:id,exactOldBirthStillPresent:true,current});}}
  }
  if(errors.length){facts.sourceAssertionsStatus=facts.status;facts.status='FAIL';facts.cleanupFailures=errors.map(error=>String(error));facts.retainedTemporaryDirectory=root;}
  const exportDirectory=process.env.H042_COLD_ADOPT_EVIDENCE_DIR;
  if(exportDirectory){const destination=join(exportDirectory,'ipc-'+label);await mkdir(destination,{recursive:true,mode:0o700});
   const files:Record<string,string>={};for(const name of await readdir(root))if(name==='events.jsonl'||name.endsWith('-runner-start.json')||name.endsWith('-cold-restart.json')||name==='handoff.json'){const bytes=await readFile(join(root,name));await writeFile(join(destination,name),bytes,{mode:0o600});files[name]=sha256(bytes);}
   facts.rawFileSha256=files;await writeFile(join(destination,'source-process-evidence.json'),stableJson(facts)+'\n',{mode:0o600});
  }
  t.diagnostic(stableJson(facts));if(errors.length)throw new AggregateError(errors,'SOURCE_owned_cleanup_or_absence_unconfirmed');await rm(root,{recursive:true,force:true});
 });
 return {runner,events,facts};
}

test('SOURCE actual Mac old worker exit0/death and distinct new birth preserve SAMEparent before first verification',{skip:process.platform!=='darwin'},async t=>{
 const f=await fixture(t,'sameparent'),runner=f.runner();await runner.start();const before=await observeApplicationIdentity(runner.identitySnapshot().pid);
 await runner.call('registerParent');
 const result=await runner.restart({checkpoint,acceptedContinuation,runId:'SOURCE-run',actionId:'SOURCE-restart',windowId:'SOURCE-h042-cold-adopt02',observedSettlements:[]});
 const after=await observeApplicationIdentity(runner.identitySnapshot().pid),receipt=JSON.parse(result.processRestartReceiptUtf8),adoption=JSON.parse(result.sourceFixtureAdoptionReceiptUtf8);
 assert.deepEqual(receipt.before,before);assert.deepEqual(receipt.after,after);assert.deepEqual(receipt.oldExit,{code:0,signal:null});
 assert.notEqual(result.beforeProcessId,result.afterProcessId);assert.notDeepEqual(before,after);assert.equal(before.bootId,after.bootId);
 assert.equal(receipt.stateSha256,adoption.stateSha256);assert.equal(sha256(result.sourceFixtureAdoptionReceiptUtf8),result.sourceFixtureAdoptionReceiptSha256);
 assert.deepEqual(adoption.before,before);assert.deepEqual(adoption.after,after);assert.deepEqual(adoption.oldExit,{code:0,signal:null});assert.ok(['known-ps-no-process','exact-pid-birth-reuse'].includes(adoption.oldAbsence.kind));
 assert.deepEqual(adoption.parent,parent);assert.equal(adoption.sessionId,parent.sessionId);assert.equal(adoption.nativeThreadId,parent.nativeThreadId);
 assert.equal(result.afterStateUtf8,checkpoint.stateUtf8);assert.equal(result.nativeThreadId,checkpoint.nativeThreadId);assert.deepEqual(result.replayedActionIds,[]);
 const verification=await runner.call('verifyParent');assert.deepEqual(verification,{sessionId:parent.sessionId,nativeThreadId:parent.nativeThreadId,parent});
 await assert.rejects(runner.call('registerParent'),/owned_worker_operation_failed_preserved/);
 const rows=await f.events(),sequence=rows.map(row=>row.event);
 assert.equal(rows.filter(row=>row.event==='registered').length,1);assert.equal(rows.find(row=>row.event==='registered')!.pid,before.pid);
 assert.ok(sequence.indexOf('prepareRestart')<sequence.indexOf('close'));assert.ok(sequence.indexOf('close')<sequence.indexOf('shutdown'));assert.ok(sequence.indexOf('shutdown')<sequence.lastIndexOf('acquired'));assert.ok(sequence.lastIndexOf('acquired')<sequence.indexOf('adoptRestart'));assert.ok(sequence.indexOf('adoptRestart')<sequence.indexOf('firstVerification'));
 const prepared=rows.find(row=>row.event==='prepareRestart')!;assert.deepEqual(prepared.oldApplication,before);assert.notDeepEqual(prepared.producer,before);
 assert.equal(rows.find(row=>row.event==='failure')!.error,'SOURCE_duplicate_registration');
 f.facts.status='PASS';f.facts.originalProcessRestartReceiptUtf8=result.processRestartReceiptUtf8;f.facts.originalProcessRestartReceiptSha256=result.processRestartReceiptSha256;f.facts.originalSourceAdoptionReceiptUtf8=result.sourceFixtureAdoptionReceiptUtf8;f.facts.originalSourceAdoptionReceiptSha256=result.sourceFixtureAdoptionReceiptSha256;
});

test('SOURCE live old application rejects a claimed exit0 in fresh real Mac worker before verification',{skip:process.platform!=='darwin'},async t=>{
 const f=await fixture(t,'old-still-alive'),old=f.runner(),fresh=f.runner();await old.start();const before=await observeApplicationIdentity(old.identitySnapshot().pid);await old.call('registerParent');
 const handoff=await old.call('prepareRestart',{checkpoint,acceptedContinuation});await fresh.start();const after=await observeApplicationIdentity(fresh.identitySnapshot().pid);
 assert.notDeepEqual(before,after);await assert.rejects(fresh.call('verifyParent'),/owned_worker_operation_failed_preserved/);
 await assert.rejects(fresh.call('adoptRestart',{...handoff,checkpoint,acceptedContinuation,beforeProcess:before,afterProcess:after,oldExit:{code:0,signal:null}}),/owned_worker_operation_failed_preserved/);
 assert.deepEqual(await observeApplicationIdentity(before.pid),before);
 const rows=await f.events();assert.ok(rows.some(row=>row.event==='failure'&&row.error==='SOURCE_old_application_still_present'));assert.ok(!rows.some(row=>row.event==='adoptRestart'||row.event==='firstVerification'));
 f.facts.status='PASS';f.facts.claimedOldExitRejected={code:0,signal:null};f.facts.actualOldApplicationStillAlive=before;f.facts.actualFreshApplication=after;
});

for(const [label,options]of [['changed-parent',{changedParent:true}],['replayed-answer',{replay:true}]] as const){
 test('SOURCE actual Mac restart rejects '+label+' after new process adoption; no verification/re-registration',{skip:process.platform!=='darwin'},async t=>{
  const f=await fixture(t,label,options),runner=f.runner();await runner.start();await runner.call('registerParent');
  await assert.rejects(runner.restart({checkpoint,acceptedContinuation,runId:'SOURCE-run',actionId:'SOURCE-restart',windowId:'SOURCE-h042-cold-adopt02',observedSettlements:[]}),/accepted_parent_changed_or_replayed/);
  const rows=await f.events();assert.equal(rows.filter(row=>row.event==='registered').length,1);assert.equal(rows.filter(row=>row.event==='adoptRestart').length,1);assert.ok(!rows.some(row=>row.event==='firstVerification'));
  const adoption=JSON.parse(rows.find(row=>row.event==='adoptRestart')!.sourceFixtureAdoptionReceiptUtf8);assert.deepEqual(adoption.oldExit,{code:0,signal:null});assert.notDeepEqual(adoption.before,adoption.after);
  f.facts.status='PASS';f.facts.expectedRejectedChange=label;f.facts.originalSourceAdoptionReceiptUtf8=rows.find(row=>row.event==='adoptRestart')!.sourceFixtureAdoptionReceiptUtf8;
 });
}
