/** SOURCE ONLY: owned local Node IPC fixtures and OS exit readback.
 * The frozen clock exercises source guards; it grants no historical live GO.
 * No native adapter admission, inference, generation or deployment is claimed. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,realpath,writeFile,readFile,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {setTimeout as delay} from 'node:timers/promises';
import {getEventListeners} from 'node:events';
import fsPromises from 'node:fs/promises';
import {syncBuiltinESMExports} from 'node:module';
import {OwnedApplicationRunner,observeApplicationIdentity} from '../../acceptance/compaction/native-adapter/process-runner.js';
import {withOwnedManualRunner} from '../../acceptance/compaction/native-adapter/manual-entry.js';
import {qualifyOwnedEntry} from '../../acceptance/compaction/native-adapter/entry.js';
import {AUTHORIZATIONS} from '../../acceptance/compaction/authorization.mjs';
import {sha256} from '../../acceptance/compaction/native-adapter/projection.js';

const worker = `
import {readFileSync,appendFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
const bytes=readFileSync(process.argv[2]),config=JSON.parse(bytes);
const mark=event=>appendFileSync(config.marker,JSON.stringify({event,pid:process.pid})+'\\n');
mark('acquired');
const ready=setTimeout(()=>{mark('ready');process.send({ready:true,protocol:'h041-owned-application-ipc-v1',configSha256:config.badReady?'bad':createHash('sha256').update(bytes).digest('hex')});},config.readyDelayMs??0);
process.on('message',message=>{
 if(message.cancel){mark('cancel');return;}
 mark(message.method);
 if(message.method==='shutdown'){
  clearTimeout(ready);
  process.send({id:message.id,result:{shutdownAcknowledged:true}},()=>{process.disconnect();process.exit(0);});
 }else if(message.method==='exit'){
  process.send({id:message.id,result:{exiting:true}},()=>{process.disconnect();process.exit(0);});
 }else if(message.method===config.failMethod){process.send({id:message.id,error:'SOURCE fixture failure'});
 }else if(message.method!=='stall'&&message.method!=='qualification'){
  process.send({id:message.id,result:{sourceOnly:true,pid:process.pid}});
 }
});
`;
async function waitFor<T>(read:()=>Promise<T>,accept:(value:T)=>boolean):Promise<T> {
 const until=performance.now()+4000;
 while(true){const value=await read();if(accept(value))return value;if(performance.now()>=until)throw Error('SOURCE fixture observation timeout');await delay(10);}
}
async function ownedFixture(t:any,options:Record<string,unknown>={}) {
 t.mock.method(Date,'now',()=>Date.parse('2026-10-01T15:00:00Z'));
 const root=await realpath(await mkdtemp(join(tmpdir(),'h042-source-cleanup01-'))),marker=join(root,'events.jsonl'),configPath=join(root,'config.json'),workerPath=join(root,'worker.mjs');
 const config=JSON.stringify({marker,...options});await writeFile(configPath,config,{mode:0o600});await writeFile(workerPath,worker,{mode:0o600});
 const authority=AUTHORIZATIONS['H041-COMPACTION-DELIVERY-05'];
 const runner=new OwnedApplicationRunner({workerPath,workerSha256:sha256(worker),configPath,configSha256:sha256(config),hostPrivate:root,review:{authorization:{...authority,windowId:'SOURCE-h042-cleanup01'},notAfterUtc:authority.capUtc,settlementReserveMs:120000},operationTimeoutMs:1000});
 // Test teardown still owns cleanup if an assertion fails; never signal any
 // unrelated PID. Removal follows the acquired process's close readback.
 t.after(async()=>{if(runner.hasAcquiredProcess())await runner.shutdownAndConfirm();await rm(root,{recursive:true,force:true});});
 const events=async()=>{try{return (await readFile(marker,'utf8')).trim().split('\n').filter(Boolean).map(line=>JSON.parse(line));}catch(error:any){if(error.code==='ENOENT')return [];throw error;}};
 const waitEvent=async(event:string)=>waitFor(events,rows=>rows.some(row=>row.event===event));
 const confirmed=async(pid:number)=>{
  // Read OS absence before a second shutdown call could conceal a missing
  // cleanup in the caller under test. Then read the already recorded close.
  await assert.rejects(observeApplicationIdentity(pid));
  const exit=await runner.shutdownAndConfirm();assert.deepEqual(exit,{code:0,signal:null});
  assert.ok((await events()).some(row=>row.event==='shutdown'&&row.pid===pid));
  t.diagnostic(JSON.stringify({source:'owned-local-node-fixture',qualification:'source',pid,exit,osAbsentBeforeSecondShutdown:true,shutdownObserved:true}));
 };
 return {runner,events,waitEvent,confirmed};
}

test('SOURCE acquired manual runner success awaits actual shutdown and exit, then returns result',async t=>{
 const f=await ownedFixture(t);await f.runner.start();const pid=f.runner.identitySnapshot().pid;
 const result=await withOwnedManualRunner({shutdown:()=>f.runner.shutdownAndConfirm()},()=>f.runner.call('echo'));
 assert.deepEqual(result,{sourceOnly:true,pid});await f.confirmed(pid);
});

test('SOURCE acquired pre-open operation failure preserves error and confirms owned exit',async t=>{
 const f=await ownedFixture(t,{failMethod:'runtime'});await f.runner.start();const pid=f.runner.identitySnapshot().pid;
 let operationFailure:unknown;
 await assert.rejects(withOwnedManualRunner({shutdown:()=>f.runner.shutdownAndConfirm()},async()=>{
  try{await f.runner.call('runtime');}catch(error){operationFailure=error;throw error;}
 }),(error:unknown)=>error===operationFailure&&error instanceof Error&&/owned_worker_operation_failed_preserved/.test(error.message));
 assert.ok(!(await f.events()).some(row=>row.event==='open'));await f.confirmed(pid);
});

test('SOURCE manual cancellation during acquired IPC closes dispatch and joins actual exit',async t=>{
 const f=await ownedFixture(t);await f.runner.start();const pid=f.runner.identitySnapshot().pid,abort=new AbortController();
 const operation=withOwnedManualRunner({shutdown:()=>f.runner.shutdownAndConfirm()},()=>f.runner.call('stall',{},abort.signal));void operation.catch(()=>undefined);
 await f.waitEvent('stall');abort.abort();await assert.rejects(operation,/owned_runner_deadline_no_replay/);
 await f.confirmed(pid);assert.ok((await f.events()).some(row=>row.event==='cancel'));
 await assert.rejects(f.runner.call('echo'),/owned_runner_unavailable/);
});

test('SOURCE failed qualification after acquisition never returns an adapter and confirms exit',async t=>{
 const f=await ownedFixture(t,{failMethod:'qualification'});let pid:number|undefined;
 await assert.rejects(qualifyOwnedEntry({qualifyWorker:async(signal?:AbortSignal)=>{await f.runner.start(signal);pid=f.runner.identitySnapshot().pid;await f.runner.call('qualification',{},signal);},shutdown:()=>f.runner.shutdownAndConfirm()}),/owned_worker_operation_failed_preserved/);
 assert.ok(pid);await f.confirmed(pid!);
});

test('SOURCE abort while worker qualification is pending reaches owned cleanup before loader rejects',async t=>{
 const f=await ownedFixture(t),abort=new AbortController();let pid:number|undefined;
 const loading=qualifyOwnedEntry({qualifyWorker:async(signal?:AbortSignal)=>{await f.runner.start(signal);pid=f.runner.identitySnapshot().pid;await f.runner.call('qualification',{},signal);},shutdown:()=>f.runner.shutdownAndConfirm()},abort.signal);void loading.catch(()=>undefined);
 await f.waitEvent('qualification');abort.abort();await assert.rejects(loading,/owned_runner_deadline_no_replay/);
 assert.ok(pid);await f.confirmed(pid!);
});

test('SOURCE aborted startup before READY shuts acquired Node and confirms exit without late READY',async t=>{
 const f=await ownedFixture(t,{readyDelayMs:60000}),abort=new AbortController();
 const loading=qualifyOwnedEntry({qualifyWorker:(signal?:AbortSignal)=>f.runner.start(signal),shutdown:()=>f.runner.shutdownAndConfirm()},abort.signal);void loading.catch(()=>undefined);
 const events=await f.waitEvent('acquired'),pid=events[0].pid;assert.ok(f.runner.hasAcquiredProcess());const at=performance.now();abort.abort();
 await assert.rejects(loading,/owned_worker_start_deadline_cancelled/);assert.ok(performance.now()-at<2000);
 await f.confirmed(pid);assert.ok(!(await f.events()).some(row=>row.event==='ready'));
});

test('SOURCE mismatched READY fails closed and startup still confirms acquired exit',async t=>{
 const f=await ownedFixture(t,{badReady:true});await assert.rejects(f.runner.start(),/actual_worker_ready_config_mismatch/);
 const pid=(await f.events())[0].pid;await f.confirmed(pid);
});

test('SOURCE abort during actual durable startup receipt joins exit instead of returning success',async t=>{
 const f=await ownedFixture(t),abort=new AbortController(),open=fsPromises.open;let receiptSynced=false;
 // Keep real protected file IO. Abort exactly at its awaited fsync boundary,
 // after READY, so this is a deterministic acquired-process cancellation race.
 t.mock.method(fsPromises,'open',async(...args:Parameters<typeof open>)=>{
  const fd=await open(...args);
  if(String(args[0]).endsWith('-runner-start.json')){
   const sync=fd.sync.bind(fd);t.mock.method(fd,'sync',async()=>{await sync();receiptSynced=true;abort.abort();});
  }
  return fd;
 });syncBuiltinESMExports();t.after(()=>{t.mock.restoreAll();syncBuiltinESMExports();});
 await assert.rejects(f.runner.start(abort.signal),/owned_application_ready_cancelled/);
 assert.equal(receiptSynced,true);await f.confirmed((await f.events())[0].pid);
});

test('SOURCE cancelled call releases parent deadline timer and emits one cancellation IPC',async t=>{
 const f=await ownedFixture(t);await f.runner.start();const pid=f.runner.identitySnapshot().pid,abort=new AbortController();
 const baseline=process.getActiveResourcesInfo().filter(resource=>resource==='Timeout').length;
 const operation=f.runner.call('stall',{},abort.signal);void operation.catch(()=>undefined);await f.waitEvent('stall');abort.abort();await assert.rejects(operation,/owned_runner_deadline_no_replay/);
 assert.equal(process.getActiveResourcesInfo().filter(resource=>resource==='Timeout').length,baseline);
 assert.equal(getEventListeners(abort.signal,'abort').length,0);
 await delay(1100);assert.equal((await f.events()).filter(row=>row.event==='cancel').length,1);await f.runner.shutdownAndConfirm();await f.confirmed(pid);
});

test('SOURCE timed-out call removes abort listener and cannot emit a second cancellation later',async t=>{
 const f=await ownedFixture(t);await f.runner.start();const pid=f.runner.identitySnapshot().pid,abort=new AbortController();
 await assert.rejects(f.runner.call('stall',{},abort.signal),/owned_runner_deadline_no_replay/);
 assert.equal(getEventListeners(abort.signal,'abort').length,0);abort.abort();await delay(30);
 assert.equal((await f.events()).filter(row=>row.event==='cancel').length,1);await f.runner.shutdownAndConfirm();await f.confirmed(pid);
});

test('SOURCE pre-aborted startup acquires no process and writes no fixture marker',async t=>{
 const f=await ownedFixture(t),abort=new AbortController();abort.abort();
 await assert.rejects(f.runner.start(abort.signal),/owned_application_start_cancelled/);
 assert.equal(f.runner.hasAcquiredProcess(),false);assert.deepEqual(await f.events(),[]);
});

test('SOURCE already exited acquired runner returns actual close readback without shutdown dispatch',async t=>{
 const f=await ownedFixture(t);await f.runner.start();const pid=f.runner.identitySnapshot().pid;
 await f.runner.call('exit');await waitFor(()=>observeApplicationIdentity(pid).catch(()=>undefined),identity=>identity===undefined);
 const at=performance.now();assert.deepEqual(await f.runner.shutdownAndConfirm(),{code:0,signal:null});
 assert.deepEqual(await f.runner.shutdownAndConfirm(),{code:0,signal:null});assert.ok(performance.now()-at<500);
 assert.ok(!(await f.events()).some(row=>row.event==='shutdown'));
 t.diagnostic(JSON.stringify({source:'owned-local-node-fixture',qualification:'source',pid,exit:{code:0,signal:null},osAbsent:true,shutdownDispatchObserved:false}));
});

test('SOURCE manual cleanup aggregates every original failure value, including falsy values',async()=>{
 const cleanup=Error('SOURCE unconfirmed cleanup');
 for(const original of [Error('SOURCE operation failed'),undefined,null,false,0,'']){
  await assert.rejects(withOwnedManualRunner({shutdown:async()=>{throw cleanup;}},async()=>{throw original;}),(error:any)=>error instanceof AggregateError&&error.message==='manual_operation_and_owned_cleanup_failed'&&error.errors.length===2&&error.errors[0]===original&&error.errors[1]===cleanup);
 }
 await assert.rejects(withOwnedManualRunner({shutdown:async()=>{throw cleanup;}},async()=>({status:'PASS'})),error=>error===cleanup);
});

test('SOURCE loader qualification and cleanup failures both survive with exact original identity',async()=>{
 const operation=Error('SOURCE qualification failed'),cleanup=Error('SOURCE cleanup failed');
 await assert.rejects(qualifyOwnedEntry({qualifyWorker:async()=>{throw operation;},shutdown:async()=>{throw cleanup;}}),(error:any)=>error instanceof AggregateError&&error.errors[0]===operation&&error.errors[1]===cleanup);
});
