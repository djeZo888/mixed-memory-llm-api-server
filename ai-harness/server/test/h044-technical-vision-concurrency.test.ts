import assert from "node:assert/strict";
import test, { type TestContext } from "node:test";
import { Worker } from "node:worker_threads";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { createHash } from "node:crypto";
import { Store } from "../src/store.js";
import { StoreTechnicalVisionJournal, visionHostExpectation, technicalVisionHostResponse, type VisionHostRecord } from "../src/technical-vision-host.js";
import { generation0, prepared, service, resultFor, input as fixtureInput } from "./technical-vision-fixtures.js";
import type { TechnicalVisionJob } from "../src/technical-vision-contracts.js";

const hash = (x: unknown): string => {
  const stable = (v: any): any => Array.isArray(v) ? v.map(stable) : v && typeof v === "object" ? Object.fromEntries(Object.entries(v).sort(([a],[b]) => a.localeCompare(b)).map(([k,v])=>[k,stable(v)])) : v;
  return createHash("sha256").update(JSON.stringify(stable(x))).digest("hex");
};
async function fixture(t: TestContext) {
  const dir=await mkdtemp(join(tmpdir(),"v-cas-")), db=join(dir,"host.sqlite"), store=new Store(db);
  const session=store.createSession(undefined,"codex"), run=store.createRun(session,"message","Synthetic concurrency",[]);
  store.updateRun(run.id,"running");
  const owner={sessionId:session.id,workspaceId:session.workspaceId,runId:run.id};
  const record=(requestId: string, sourceId = "source1"): VisionHostRecord => {
    const input={requestId,source:{fileId:sourceId},crops:fixtureInput.crops};
    return {handle:`vision-${hash([owner.workspaceId,owner.sessionId,owner.runId,requestId]).slice(0,64)}`,owner,service,requestId,input,inputFingerprint:hash(input),admission:"claimed"};
  };
  const journal=new StoreTechnicalVisionJournal(store,{recoverInterrupted:false});
  t.after(async()=>{store.db.close();await rm(dir,{recursive:true,force:true});});
  return {db,store,journal,record,owner};
}

// Two worker threads open separate DatabaseSync connections to the same WAL file.
// Parent holds the first actual BEGIN IMMEDIATE while the second attempts its lock.
// This proves the SQL read location; Promise.all in one Node event loop cannot.
const workerCode=String.raw`
const {parentPort,workerData:d,threadId}=require('node:worker_threads');
require('tsx/cjs');
const {Store}=require(d.storeModule);
const {StoreTechnicalVisionJournal,visionHostExpectation,createTechnicalVisionHost,technicalVisionHostResponse}=require(d.hostModule);
const {TechnicalVisionClient}=require(d.clientModule);
(async()=>{
 const store=new Store(d.db,undefined,{mode:'offline-recovery'});
 store.db.exec('PRAGMA busy_timeout='+ (d.busyMs??2000));
 const journal=new StoreTechnicalVisionJournal(store,{recoverInterrupted:false});
 const original=d.handle ? await journal.read(d.handle):undefined;
 const expected=original ? visionHostExpectation(original):undefined;
 const gate=new Int32Array(d.gate);let locked=false,first=true;
 const exec=store.db.exec.bind(store.db),prepare=store.db.prepare.bind(store.db);
 store.db.exec=(sql)=>{
  if(sql==='BEGIN IMMEDIATE'){
   parentPort.postMessage({kind:'attempt',threadId});exec(sql);locked=true;
   parentPort.postMessage({kind:'locked',threadId});
   if(first&&d.hold){first=false;Atomics.wait(gate,1,0,3000);}
  }else{exec(sql);if(sql==='COMMIT'||sql==='ROLLBACK')locked=false;}
 };
 store.db.prepare=(sql)=>{
  const statement=prepare(sql);
  if(sql.includes('h043_vision_host')&&sql.startsWith('SELECT')){
   const get=statement.get.bind(statement);
   statement.get=(...args)=>{parentPort.postMessage({kind:'read',threadId,locked,sql});return get(...args);};
  }
  return statement;
 };
 parentPort.postMessage({kind:'ready',threadId,db:d.db,connection:'independently opened DatabaseSync'});
 Atomics.wait(gate,0,0,3000);
 let value,error;
 try{
  if(d.operation==='claim')value=await journal.claim(d.record);
  else if(d.operation==='invoke'){
   const backend=new TechnicalVisionClient({fixtureOrigin:d.origin,expectedService:d.record.service,key:()=> 'fixture-host-only-key',requestMs:1000});
   const host=createTechnicalVisionHost({backend,service:d.record.service,journal,enabled:true,owner:()=>d.record.owner,authorize:()=>true,prepare:async()=>({manifest:d.prepared.manifest,images:d.prepared.images.map(i=>({...i,png:Buffer.from(i.png)}))})});
   value=await host.invoke(d.record.input,AbortSignal.timeout(3000));
  }else if(d.operation==='observe')value=await journal.observe(d.handle,d.job,expected);
  else if(d.operation==='deliver')value=await journal.deliverOnce('terminal-'+d.handle,technicalVisionHostResponse(original.terminal.job,d.handle),original.owner);
  else if(d.operation==='cancel-dispatch')value=await journal.markCancelDispatched(d.handle);
 }catch(e){error={code:e.code,message:e.message};}
 store.db.close();parentPort.postMessage({kind:'done',threadId,value,error});
})().catch(e=>{parentPort.postMessage({kind:'fatal',message:e.stack});process.exitCode=1;});
`;
async function compete(t: TestContext, db: string, tasks: Record<string,unknown>[]) {
  const events: any[][]=[[],[]], gates=tasks.map(()=>new SharedArrayBuffer(8));
  const workerData={db,storeModule:fileURLToPath(new URL("../src/store.ts",import.meta.url)),hostModule:fileURLToPath(new URL("../src/technical-vision-host.ts",import.meta.url)),clientModule:fileURLToPath(new URL("../src/technical-vision-client.ts",import.meta.url))};
  const workers=tasks.map((task,i)=>new Worker(workerCode,{eval:true,workerData:{...workerData,...task,gate:gates[i],hold:i===0}}));
  const exits=workers.map(w=>new Promise<number>((resolve,reject)=>{w.once("exit",resolve);w.once("error",reject);}));
  workers.forEach((w,i)=>w.on("message",m=>events[i].push(m)));
  t.after(async()=>{for(const w of workers)await w.terminate();});
  const until=async(predicate:()=>boolean)=>{const end=Date.now()+5000;while(!predicate()){if(Date.now()>end)throw Error(JSON.stringify(events));await new Promise(r=>setTimeout(r,5));}};
  await until(()=>events.every(e=>e.some(m=>m.kind==='ready')));
  assert.notEqual(events[0][0].threadId,events[1][0].threadId);
  Atomics.store(new Int32Array(gates[0]),0,1);Atomics.notify(new Int32Array(gates[0]),0);
  await until(()=>events[0].some(m=>m.kind==='locked'));
  Atomics.store(new Int32Array(gates[1]),0,1);Atomics.notify(new Int32Array(gates[1]),0);
  await until(()=>events[1].some(m=>m.kind==='attempt'));
  await new Promise(r=>setTimeout(r,25));
  assert.equal(events[1].some(m=>m.kind==='locked'),false,'second independent connection waits on first writer');
  assert.equal(events[1].some(m=>m.kind==='read'),false,'no claim or cap read before BEGIN IMMEDIATE acquires the lock');
  Atomics.store(new Int32Array(gates[0]),1,1);Atomics.notify(new Int32Array(gates[0]),1);
  const codes=await Promise.all(exits);assert.deepEqual(codes,[0,0]);
  assert.ok(events.every(e=>!e.some(m=>m.kind==='fatal')),JSON.stringify(events));
  console.log(JSON.stringify({fixture:'two independently opened SQLite connections; held BEGIN IMMEDIATE',db,TMPDIR:process.env.TMPDIR,workerThreadIds:events.map(e=>e.find(m=>m.kind==='ready').threadId),exits:codes,events}));
  return events.map(e=>e.find(m=>m.kind==='done'));
}

test('independent admission: read and cap occur inside writer lock; only one actual HTTP submit',async t=>{
  const f=await fixture(t),backend=await generation0(t,{requestMs:1000}),p=await prepared(),r=f.record('same-request');
  const tasks=[0,1].map(()=>({operation:'invoke',record:r,origin:backend.fixtureOrigin,prepared:p}));
  const results=await compete(t,f.db,tasks);
  assert.ok(results.some(r=>r.value&&!r.value.response.isError),JSON.stringify(results));
  assert.equal(backend.counters().submitCalls,1);assert.equal(backend.counters().admissions,1);
  const original=f.journal.records()[0];assert.equal(original.owner.runId,f.owner.runId);assert.equal(original.inputFingerprint,r.inputFingerprint);assert.equal(f.journal.records().length,1);
  await assert.rejects(f.journal.claim({...r,inputFingerprint:'f'.repeat(64)}));
  await assert.rejects(f.journal.claim({...r,service:{...service,serviceId:'different-service'}}));
  const second=new Store(f.db,undefined,{mode:'offline-recovery'});const j2=new StoreTechnicalVisionJournal(second,{recoverInterrupted:false});
  assert.equal(await j2.claim(r),false);assert.equal((await j2.read(r.handle))!.owner.runId,f.owner.runId);second.db.close();
});

test('independent capacity admission serializes both COUNT and unique INSERT',async t=>{
  const f=await fixture(t);for(let i=0;i<127;i++)assert.equal(await f.journal.claim(f.record('capacity-'+i,'source-'+i)),true);
  const results=await compete(t,f.db,[{operation:'claim',record:f.record('last-a','source-a')},{operation:'claim',record:f.record('last-b','source-b')}]);
  assert.equal(results.filter(r=>r.value===true).length,1);assert.equal(results.filter(r=>r.error?.code==='queue_full').length,1);assert.equal(f.journal.records().length,128);
});

test('independent stale snapshot CAS preserves terminal/source/job identity and one terminal event after restart/lost ack',async t=>{
  const f=await fixture(t),r=f.record('snapshot-race'),p=await prepared();await f.journal.claim(r);await f.journal.freezeSource(r.handle,p.manifest,p.images.map(i=>({page:i.page,sha256:i.sha256})));
  const queued:TechnicalVisionJob={schemaVersion:1,jobId:'original-job',requestId:r.requestId,owner:f.owner,service,source:p.manifest,state:'queued',settled:false,cancelRequested:false,queuePosition:1};
  await f.journal.observe(r.handle,queued,visionHostExpectation((await f.journal.read(r.handle))!));
  const terminal:TechnicalVisionJob={...queued,state:'completed',settled:true,result:resultFor(p.manifest)};delete terminal.queuePosition;
  const results=await compete(t,f.db,[{operation:'observe',handle:r.handle,job:terminal},{operation:'observe',handle:r.handle,job:queued}]);
  assert.equal(results[0].value.terminal.job.state,'completed');assert.equal(results[1].error.code,'idempotency_conflict');
  const committed=(await f.journal.read(r.handle))!;assert.deepEqual(committed.source,p.manifest);assert.equal(committed.jobId,'original-job');
  await assert.rejects(f.journal.observe(r.handle,queued,visionHostExpectation(committed)),e=>(e as any).code==='invalid_response');
  await assert.rejects(f.journal.observe(r.handle,{...terminal,jobId:'new-job'},visionHostExpectation(committed)));
  await assert.rejects(f.journal.observe(r.handle,{...terminal,source:{...p.manifest,sha256:'f'.repeat(64)}},visionHostExpectation(committed)));
  await assert.rejects(f.journal.observe(r.handle,terminal),e=>(e as any).code==='invalid_request');
  await compete(t,f.db,[{operation:'deliver',handle:r.handle},{operation:'deliver',handle:r.handle}]);
  const logical=()=>f.store.replay(f.owner.sessionId,0).filter(e=>e.type==='message'&&(e.data.message as any)?.technicalVision?.settled===true);
  assert.equal(logical().length,1);assert.equal(f.store.db.prepare('SELECT COUNT(*) AS n FROM h043_vision_deliveries').get()!.n,1);
  const reopened=new Store(f.db,undefined,{mode:'offline-recovery'}),journal=new StoreTechnicalVisionJournal(reopened);
  await journal.deliverOnce('terminal-'+r.handle,technicalVisionHostResponse(terminal,r.handle),f.owner);await journal.acknowledge(r.handle,'terminal-'+r.handle);
  assert.equal(logical().length,1);assert.equal((await journal.read(r.handle))!.terminal!.acknowledged,true);
  await assert.rejects(journal.deliverOnce('terminal-'+r.handle,{content:[{type:'text',text:'forged terminal'}]},f.owner));reopened.db.close();
});

test('busy admission propagates SQLite busy and never reports false or overwrites the claim',async t=>{
  const f=await fixture(t),second=new Store(f.db,undefined,{mode:'offline-recovery'});second.db.exec('PRAGMA busy_timeout=20');const journal=new StoreTechnicalVisionJournal(second,{recoverInterrupted:false});
  f.store.db.exec('BEGIN IMMEDIATE');try{await assert.rejects(journal.claim(f.record('busy')),e=>/busy|locked/.test(String(e)));}finally{f.store.db.exec('ROLLBACK');second.db.close();}
  assert.equal(f.journal.records().length,0);
});

test('independent cancel-dispatch claim is unique',async t=>{
  const f=await fixture(t),r=f.record('cancel-race');await f.journal.claim(r);await f.journal.requestCancel(r.handle);
  const results=await compete(t,f.db,[{operation:'cancel-dispatch',handle:r.handle},{operation:'cancel-dispatch',handle:r.handle}]);
  assert.deepEqual(results.map(r=>r.value),[true,false]);
});

test('independent new keys for the same unknown source cannot create two original claims',async t=>{
  const f=await fixture(t);
  const results=await compete(t,f.db,[{operation:'claim',record:f.record('unknown-a')},{operation:'claim',record:f.record('unknown-b')}]);
  assert.equal(results[0].value,true);assert.equal(results[1].error.code,'idempotency_conflict');
  assert.equal(f.journal.records().length,1);assert.equal(f.journal.records()[0].requestId,'unknown-a');
});

test('Stop wins before new admission; ended original claim remains available without resubmission',async t=>{
  const f=await fixture(t),r=f.record('stop-admission');f.store.updateRun(f.owner.runId,'cancelled');
  await assert.rejects(f.journal.claim(r),e=>(e as any).code==='unavailable');assert.equal(f.journal.records().length,0);
  f.store.updateRun(f.owner.runId,'running');assert.equal(await f.journal.claim(r),true);
  f.store.updateRun(f.owner.runId,'cancelled');assert.equal(await f.journal.claim(r),false);
  assert.equal((await f.journal.read(r.handle))!.owner.runId,f.owner.runId);
});
