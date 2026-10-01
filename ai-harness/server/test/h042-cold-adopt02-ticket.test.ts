/** SOURCE only: genuine in-process RestartTicket brand over private fixture
 * bytes. The narrow /proc fixture does not qualify Linux/native transport,
 * receipt provenance, protected policy adoption, or an operational restart. */
import test, {type TestContext} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {mkdirSync, mkdtempSync, realpathSync, rmSync, writeFileSync} from 'node:fs';
import {syncBuiltinESMExports} from 'node:module';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {receiptFixture} from './helpers/codex-receipt-fixture.js';
import {Store} from '../src/store.js';
import {sha256, stableJson} from '../../acceptance/compaction/native-adapter/projection.js';
import {qualifyRestart, isRestartTicket, assertRestartTicketForConfig, assertRestartBootstrap} from '../../acceptance/compaction/native-adapter/restart.js';
import {selectRestartCheckpoint} from '../../acceptance/compaction/native-adapter/restart-selection.js';
import {type ApplicationIdentity} from '../../acceptance/compaction/native-adapter/process-runner.js';

const bootId='00000000-0000-0000-0000-000000000001';
const oldPid=process.pid+10000;
const beforeProcess:ApplicationIdentity={source:'linux-proc',pid:oldPid,startTicks:'100',bootId};
const afterProcess:ApplicationIdentity={source:'linux-proc',pid:process.pid,startTicks:'200',bootId};

/** Replace only the SOURCE fixture's proc reads. All private handoff file IO
 * continues through the actual Node/fs implementation. No child is launched. */
function sourceKernel(t:TestContext) {
  const descriptor=Object.getOwnPropertyDescriptor(process,'platform')!;
  Object.defineProperty(process,'platform',{value:'linux'});
  const read=fs.readFile;
  let oldObservation:'absent'|'same-birth'|'newer-birth'|'permission'|'io'|'unknown'='absent';
  const stat=(pid:number,ticks:string)=>{
    const fields=Array<string>(24).fill('0');fields[0]='S';fields[19]=ticks;
    return `${pid} (SOURCE fixture application) ${fields.join(' ')}\n`;
  };
  t.mock.method(fs,'readFile',async(path:any,...args:any[])=>{
    if(String(path)==='/proc/sys/kernel/random/boot_id')return bootId+'\n';
    if(String(path)===`/proc/${process.pid}/stat`)return stat(process.pid,'200');
    if(String(path)===`/proc/${oldPid}/stat`) {
      if(oldObservation==='same-birth')return stat(oldPid,'100');
      if(oldObservation==='newer-birth')return stat(oldPid,'101');
      const code=oldObservation==='absent'?'ENOENT':oldObservation==='permission'?'EACCES':oldObservation==='io'?'EIO':undefined;
      throw Object.assign(Error('SOURCE fixture old application identity read'),{code,path:`/proc/${oldPid}/stat`});
    }
    return (read as any)(path,...args);
  });
  syncBuiltinESMExports();
  t.after(()=>{t.mock.restoreAll();syncBuiltinESMExports();Object.defineProperty(process,'platform',descriptor);});
  return {setOld:(value:typeof oldObservation)=>{oldObservation=value;}};
}

function handoffFixture(t:TestContext,accepted=true) {
  const base=realpathSync(mkdtempSync(join(tmpdir(),'h042-cold-source-ticket-')));
  const root=join(base,'owned-layout'),dataDir=join(root,'app-data'),hostPrivate=join(root,'host-private');
  for(const path of [root,dataDir,hostPrivate])mkdirSync(path,{mode:0o700});
  t.after(()=>rmSync(base,{recursive:true,force:true}));
  const f=receiptFixture();
  const stateUtf8=JSON.stringify({type:'session_meta',payload:{id:'SOURCE-SAMEparent'}})+'\n'+JSON.stringify({type:'compacted',payload:{message:'SOURCE retained summary'}})+'\n';
  const artifactUtf8='{"SOURCE":"original accepted bytes"}\n';
  const artifact={id:'SOURCE-artifact-id',messageId:'SOURCE-artifact-message',bytes:Buffer.byteLength(artifactUtf8),sha256:sha256(artifactUtf8),jsonUtf8:artifactUtf8};
  const checkpoint={nativeThreadId:'SOURCE-SAMEparent',stateUtf8,stateSha256:sha256(stateUtf8),rolloutReceiptUtf8:'SOURCE original rollout receipt',rolloutReceiptSha256:sha256('SOURCE original rollout receipt')};
  const acceptedContinuation=accepted?{
    actionId:'SOURCE-accepted-action',artifactHashes:{'sensor-policy.json':artifact.sha256},
    artifactBaseline:{sessionId:f.binding.sessionId,nativeThreadId:checkpoint.nativeThreadId,storeRunId:'SOURCE-Store-run',actionId:'SOURCE-accepted-action',checkpointStateSha256:checkpoint.stateSha256,artifacts:[artifact]},
  }:null;
  const config={bootstrap:{privateBase:base,review:{candidateCommit:'a'.repeat(40),authorization:{windowId:'SOURCE-window'},receiptSources:f.binding.sources}},heldAdmission:{transactionId:'SOURCE-held-transaction',ownHoldKey:'SOURCE-own-hold'},fixedSource:{configSha256:sha256('SOURCE-fixed-config'),bootstrapSha256:sha256('SOURCE-fixed-bootstrap')}};
  const state:any={source:'owned-application-restart-handoff',candidateCommit:config.bootstrap.review.candidateCommit,windowId:'SOURCE-window',runId:'SOURCE-run',sessionId:f.binding.sessionId,parentNativeThreadId:checkpoint.nativeThreadId,layout:{root,dataDir,hostPrivate},checkpoint,acceptedContinuation,observedSettlements:[],
    // Receipt producer is deliberately distinct from the application identity.
    producer:f.producer,policyHandoff:{purpose:accepted?'accepted-continuation':'settled-compaction',path:join(hostPrivate,'SOURCE-policy-handoff'),sha256:sha256('SOURCE-HMAC-policy-bytes'),storeRunId:'SOURCE-Store-run',checkpointId:'SOURCE-Store-checkpoint',sourceClosure:{'SOURCE-adapter.ts':sha256('SOURCE-original-source')}}};
  const close={source:'native-acceptance-run-close',format:'h041-owned-close-v1',runId:state.runId,operationWindowId:state.windowId,status:'released',producers:[{launchReceiptUtf8:stableJson(f.rawLaunch),settlementReceiptUtf8:stableJson(f.rawSettlement)}],settledOwnedActions:[],outstandingOwnedActions:[],unconfirmedOwnedActions:[]};
  const closeReceiptUtf8=stableJson(close),closeReceiptSha256=sha256(closeReceiptUtf8);
  const closed={outcome:'closed',closeReceiptUtf8,closeReceiptSha256,settlement:{state:'released',receiptSha256:closeReceiptSha256,automaticReplay:false}};
  const statePath=join(hostPrivate,'restart-handoff.json'),stateBytes=stableJson(state);
  writeFileSync(statePath,stateBytes,{mode:0o600});
  const input:any={statePath,stateSha256:sha256(stateBytes),checkpoint,acceptedContinuation,closed,beforeProcess,afterProcess,oldExit:{code:0,signal:null},runId:state.runId,actionId:'SOURCE-restart-action',windowId:state.windowId};
  return {state,input,config,f,close,stateBytes,statePath,artifact};
}

test('SOURCE qualifyRestart issues its genuine brand only over exact original private handoff/config/bootstrap and retains SAMEparent evidence',async t=>{
  sourceKernel(t);const x=handoffFixture(t),ticket=await qualifyRestart(x.input,x.config);
  assert.equal(isRestartTicket(ticket),true);
  assert.doesNotThrow(()=>assertRestartTicketForConfig(ticket,x.config));
  assert.doesNotThrow(()=>assertRestartBootstrap(ticket,x.config.bootstrap));
  assert.equal(ticket.input.beforeProcess.pid,oldPid);
  assert.notEqual(ticket.input.beforeProcess.pid,ticket.state.producer.pid);
  assert.deepEqual(ticket.input.afterProcess,afterProcess);
  assert.deepEqual(ticket.input.oldExit,{code:0,signal:null});
  assert.equal(ticket.state.sessionId,x.f.binding.sessionId);
  assert.equal(ticket.state.parentNativeThreadId,'SOURCE-SAMEparent');
  assert.deepEqual(ticket.state.layout,x.state.layout);
  assert.equal(ticket.state.checkpoint.stateUtf8,x.state.checkpoint.stateUtf8);
  assert.deepEqual(ticket.state.acceptedContinuation,x.state.acceptedContinuation);
  assert.equal(ticket.state.acceptedContinuation.artifactBaseline.artifacts[0].id,x.artifact.id);
  assert.equal(ticket.closed.closeReceiptUtf8,x.input.closed.closeReceiptUtf8);
  assert.equal(stableJson(ticket.state),x.stateBytes);
  assert.ok(Object.isFrozen(ticket)&&Object.isFrozen(ticket.state.policyHandoff)&&Object.isFrozen(ticket.input.beforeProcess));
  for(const copy of [{...ticket},structuredClone(ticket),JSON.parse(stableJson(ticket))]) {
    assert.equal(isRestartTicket(copy),false);
    assert.throws(()=>assertRestartTicketForConfig(copy,x.config),/exact_config_and_handoff/);
    assert.throws(()=>assertRestartBootstrap(copy,x.config.bootstrap),/exact_bootstrap/);
  }
  for(const mutate of [
    (v:any)=>v.bootstrap.review.candidateCommit='b'.repeat(40),
    (v:any)=>v.bootstrap.review.authorization.windowId='FOREIGN',
    (v:any)=>v.bootstrap.review.receiptSources[Object.keys(v.bootstrap.review.receiptSources)[0]!]=sha256('FOREIGN-source'),
    (v:any)=>v.fixedSource.configSha256=sha256('FOREIGN-config'),
    (v:any)=>v.heldAdmission.transactionId='FOREIGN',
    (v:any)=>v.heldAdmission.ownHoldKey='FOREIGN',
  ]) {const config=structuredClone(x.config);mutate(config);assert.throws(()=>assertRestartTicketForConfig(ticket,config),/exact_config_and_handoff/);}
  const changedBootstrap=structuredClone(x.config.bootstrap);changedBootstrap.privateBase=x.state.layout.root;
  assert.throws(()=>assertRestartBootstrap(ticket,changedBootstrap),/exact_bootstrap/);
});

test('SOURCE durable handoff hash rejects changed rollout/artifact/policy/source bytes without manufacturing replacement evidence',async t=>{
  sourceKernel(t);const x=handoffFixture(t);
  for(const mutate of [
    (v:any)=>v.checkpoint.stateUtf8+='SOURCE replacement rollout\n',
    (v:any)=>v.checkpoint.rolloutReceiptUtf8='FOREIGN rollout receipt',
    (v:any)=>v.acceptedContinuation.artifactBaseline.artifacts[0].jsonUtf8='{}\n',
    (v:any)=>v.acceptedContinuation.artifactBaseline.artifacts[0].messageId='FOREIGN-message',
    (v:any)=>v.policyHandoff.sha256=sha256('FOREIGN-policy'),
    (v:any)=>v.policyHandoff.sourceClosure['SOURCE-adapter.ts']=sha256('FOREIGN-source'),
  ]) {
    const changed=structuredClone(x.state);mutate(changed);writeFileSync(x.statePath,stableJson(changed),{mode:0o600});
    await assert.rejects(qualifyRestart(x.input,x.config),/handoff_bytes_changed/);
  }
  writeFileSync(x.statePath,x.stateBytes,{mode:0o600});
  assert.equal(isRestartTicket(await qualifyRestart(x.input,x.config)),true);
});

test('SOURCE retained checkpoint and accepted artifact baseline must match exact caller state before branding',async t=>{
  sourceKernel(t);const x=handoffFixture(t);
  for(const mutate of [
    (v:any)=>v.checkpoint.nativeThreadId='FOREIGN-parent',
    (v:any)=>{v.checkpoint.stateUtf8+='SOURCE answer replay\n';v.checkpoint.stateSha256=sha256(v.checkpoint.stateUtf8);},
    (v:any)=>v.checkpoint.rolloutReceiptSha256=sha256('FOREIGN-rollout'),
    (v:any)=>v.acceptedContinuation.actionId='FOREIGN-action',
    (v:any)=>v.acceptedContinuation.artifactBaseline.sessionId='FOREIGN-session',
    (v:any)=>v.acceptedContinuation.artifactBaseline.artifacts[0].id='FOREIGN-artifact',
    (v:any)=>v.acceptedContinuation.artifactBaseline.artifacts[0].messageId='FOREIGN-message',
    (v:any)=>v.acceptedContinuation.artifactBaseline.artifacts[0].bytes++,
    (v:any)=>v.acceptedContinuation.artifactBaseline.artifacts[0].sha256=sha256('FOREIGN-bytes'),
  ]) {const input=structuredClone(x.input);mutate(input);await assert.rejects(qualifyRestart(input,x.config),/checkpoint_or_accepted_baseline_changed/);}
  const changed=structuredClone(x.state);changed.policyHandoff.purpose='settled-compaction';
  writeFileSync(x.statePath,stableJson(changed),{mode:0o600});
  await assert.rejects(qualifyRestart({...x.input,stateSha256:sha256(stableJson(changed))},x.config),/handoff_purpose_changed/);
});

test('SOURCE branding rejects wrong current application birth/boot, native-producer substitution, old live birth, and uncertain identity reads',async t=>{
  const kernel=sourceKernel(t),x=handoffFixture(t);
  for(const mutate of [
    (v:any)=>v.afterProcess.pid++,
    (v:any)=>v.afterProcess.startTicks='201',
    (v:any)=>v.afterProcess.bootId='FOREIGN-boot',
    (v:any)=>v.beforeProcess.bootId='FOREIGN-boot',
    (v:any)=>v.beforeProcess={source:'linux-proc',pid:process.pid,startTicks:'200',bootId},
    (v:any)=>v.beforeProcess={...x.f.producer,source:'native-supervisor'},
    (v:any)=>v.oldExit.code=1,
    (v:any)=>v.oldExit.signal='SIGTERM',
  ]) {const input=structuredClone(x.input);mutate(input);await assert.rejects(qualifyRestart(input,x.config),/process_identity_mismatch|actual_old_application_exit/);}
  kernel.setOld('same-birth');await assert.rejects(qualifyRestart(x.input,x.config),/still_present/);
  for(const observation of ['permission','io','unknown'] as const) {
    kernel.setOld(observation);await assert.rejects(qualifyRestart(x.input,x.config),/identity_read_unconfirmed/);
  }
  kernel.setOld('newer-birth');assert.equal(isRestartTicket(await qualifyRestart(x.input,x.config)),true);
  kernel.setOld('absent');assert.equal(isRestartTicket(await qualifyRestart(x.input,x.config)),true);
});

test('SOURCE owned close bytes remain mandatory and exact pinned source/producer/settlement evidence cannot be replaced',async t=>{
  sourceKernel(t);const x=handoffFixture(t);
  for(const mutate of [
    (v:any)=>v.producers[0].launchReceiptUtf8='{}',
    (v:any)=>{const launch=JSON.parse(v.producers[0].launchReceiptUtf8);launch.sources[Object.keys(launch.sources)[0]!]=sha256('FOREIGN-source');v.producers[0].launchReceiptUtf8=stableJson(launch);},
    (v:any)=>{const settlement=JSON.parse(v.producers[0].settlementReceiptUtf8);settlement.producer.pid++;v.producers[0].settlementReceiptUtf8=stableJson(settlement);},
    (v:any)=>{const settlement=JSON.parse(v.producers[0].settlementReceiptUtf8);settlement.cleanupOk=false;v.producers[0].settlementReceiptUtf8=stableJson(settlement);},
    (v:any)=>v.outstandingOwnedActions.push({actionId:'FOREIGN-live'}),
    (v:any)=>v.operationWindowId='FOREIGN-window',
  ]) {
    const close=structuredClone(x.close);mutate(close);const bytes=stableJson(close),digest=sha256(bytes);
    const input={...x.input,closed:{...x.input.closed,closeReceiptUtf8:bytes,closeReceiptSha256:digest,settlement:{...x.input.closed.settlement,receiptSha256:digest}}};
    await assert.rejects(qualifyRestart(input,x.config),/actual_old_application_exit_and_owned_close/);
  }
  const input=structuredClone(x.input);input.closed.closeReceiptUtf8+=' ';
  await assert.rejects(qualifyRestart(input,x.config),/actual_old_application_exit_and_owned_close/);
});

test('SOURCE real Store selection preserves latest completed settled compaction and exact accepted SAMEparent linkage',t=>{
  const base=realpathSync(mkdtempSync(join(tmpdir(),'h042-cold-source-store-'))),store=new Store(join(base,'store.sqlite'));
  t.after(()=>{store.close();rmSync(base,{recursive:true,force:true});});
  const session=store.createSession(undefined,'codex');store.setNative(session.id,'SOURCE-SAMEparent','codex');
  const run=store.createRun(session,'compact','SOURCE-compaction',[]),record=store.checkpoints.prepare(session.id,run.id,'compact','SOURCE-SAMEparent');
  store.checkpoints.observeCompaction(session.id,run.id,'SOURCE-compact-id','start');
  store.checkpoints.observeCompaction(session.id,run.id,'SOURCE-compact-id','completed');
  store.checkpoints.finish(session.id,run.id,'completed');store.updateRun(run.id,'completed');
  const stateUtf8='SOURCE original full parent state\n',stateSha256=sha256(stateUtf8);
  const settledOperationUtf8=stableJson({nativeThreadId:'SOURCE-SAMEparent',status:'completed',settlement:'released',postStateSha256:stateSha256,compactionId:'SOURCE-compact-id'});
  const checkpoint={nativeThreadId:'SOURCE-SAMEparent',stateUtf8,stateSha256,settledOperationUtf8,settledOperationSha256:sha256(settledOperationUtf8)};
  assert.deepEqual(selectRestartCheckpoint(store,session.id,'SOURCE-SAMEparent',checkpoint),{purpose:'settled-compaction',storeRunId:run.id,checkpointId:record.id});
  for(const mutate of [(v:any)=>v.compactionId='FOREIGN',(v:any)=>v.postStateSha256=sha256('FOREIGN-state'),(v:any)=>v.settlement='unconfirmed']) {
    const operation=JSON.parse(settledOperationUtf8);mutate(operation);const bytes=stableJson(operation);
    assert.throws(()=>selectRestartCheckpoint(store,session.id,'SOURCE-SAMEparent',{...checkpoint,settledOperationUtf8:bytes,settledOperationSha256:sha256(bytes)}),/store_compaction_and_full_state/);
  }
  const later=store.createRun(store.getSession(session.id),'message','SOURCE accepted continuation',[]),laterRecord=store.checkpoints.prepare(session.id,later.id,'message','SOURCE-SAMEparent');
  store.checkpoints.finish(session.id,later.id,'completed');store.updateRun(later.id,'completed');
  assert.throws(()=>selectRestartCheckpoint(store,session.id,'SOURCE-SAMEparent',checkpoint),/before_artifacts/);
  const artifact={id:'SOURCE-kept-artifact',messageId:'SOURCE-kept-message',bytes:13,sha256:sha256('SOURCE artifact')};
  const accepted={actionId:'SOURCE-accepted-action',artifactHashes:{'sensor-policy.json':artifact.sha256},artifactBaseline:{nativeThreadId:'SOURCE-SAMEparent',storeRunId:later.id,sessionId:session.id,actionId:'SOURCE-accepted-action',checkpointStateSha256:stateSha256,artifacts:[artifact]}};
  const baselineBytes=stableJson(accepted);
  assert.deepEqual(selectRestartCheckpoint(store,session.id,'SOURCE-SAMEparent',checkpoint,accepted),{purpose:'accepted-continuation',storeRunId:later.id,checkpointId:laterRecord.id});
  assert.equal(stableJson(accepted),baselineBytes);
  for(const mutate of [(v:any)=>v.artifactBaseline.storeRunId=run.id,(v:any)=>v.artifactBaseline.sessionId='FOREIGN',(v:any)=>v.artifactBaseline.nativeThreadId='FOREIGN',(v:any)=>v.artifactBaseline.actionId='FOREIGN',(v:any)=>v.artifactBaseline.checkpointStateSha256=sha256('FOREIGN-state')]) {
    const changed=structuredClone(accepted);mutate(changed);assert.throws(()=>selectRestartCheckpoint(store,session.id,'SOURCE-SAMEparent',checkpoint,changed),/latest_accepted_continuation/);
  }
});
