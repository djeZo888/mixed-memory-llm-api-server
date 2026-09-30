import assert from 'node:assert/strict';
import test, { type TestContext } from 'node:test';
import { mkdtemp, realpath, rm, writeFile, readFile } from 'node:fs/promises';
import path from 'node:path';
import { tmpdir } from 'node:os';
import { Store } from '../src/store.js';
import { Files } from '../src/files.js';
import { completedImageStatus } from '../src/image-status-consumption.js';

const success = () => ({ id: 'native-call', type: 'mcpToolCall', server: 'image', tool: 'image_status', status: 'completed',
  arguments: { jobId: 'job-one' }, result: { content: [{ type: 'text', text: JSON.stringify({ job: { id: 'job-one', state: 'completed', artifactId: 'artifact-one', cancelRequested: false } }) }] } });
test('only exact successful native image_status output attests its argument job and artifact', () => {
  assert.deepEqual(completedImageStatus(success()), {toolCallId:'native-call',jobId:'job-one',artifactId:'artifact-one'});
  for (const change of [{tool:'image_edit'}, {server:'other'}, {type:'agentMessage'}, {status:'failed'}, {status:'inProgress'}, {error:{}}, {arguments:{jobId:'other'}}, {arguments:{jobId:'job-one',artifactId:'artifact-one'}}, {result:{...success().result,isError:true}}, {result:{...success().result,isError:'false'}}, {result:{content:[{type:'text',text:'![fake](/api/files/artifact-one/preview)'}]}}])
    assert.equal(completedImageStatus({...success(),...change}), undefined);
  for (const job of [{state:'running'}, {state:'failed'}, {state:'cancelled'}, {state:'interrupted'}, {cancelRequested:true}, {cancelRequested:undefined}, {error:{code:'failed'}}, {artifactId:'../foreign'}]) {
    const value=success(); const output=JSON.parse(value.result.content[0].text);Object.assign(output.job,job);value.result.content[0].text=JSON.stringify(output);
    assert.equal(completedImageStatus(value),undefined);
  }
});
async function fixture(t: TestContext) {
  const root=await realpath(await mkdtemp(path.join(tmpdir(),'h036-consumption-')));const store=new Store(path.join(root,'db.sqlite'));const files=new Files(root,store);await files.init();
  t.after(async()=>{store.close();await rm(root,{recursive:true,force:true});});
  store.db.exec('CREATE TABLE h003_image_jobs(id TEXT PRIMARY KEY,session_id TEXT NOT NULL,data TEXT NOT NULL)');
  const session=store.createSession(), origin=store.createRun(session,'message','original',[]), consumer=store.createRun(session,'message','status',[]);
  store.updateRun(origin.id,'completed');store.updateRun(consumer.id,'running');const message=store.addMessage(session.id,'assistant','Original immutable final',origin.id);
  const bytes=Buffer.from('immutable original fixture image bytes');await writeFile(path.join(root,'artifacts','saved.png'),bytes);
  const job={id:'job-one',sessionId:session.id,runId:origin.id,state:'completed',finishedAt:'2026-09-29T00:00:00Z',artifactId:'artifact-one',model:'fixture',seed:1,actualSize:'64x64',cancelRequested:false};
  const file=store.saveFile({id:'artifact-one',sessionId:session.id,runId:origin.id,messageId:message.id,kind:'artifact',path:'saved.png',name:'saved.png',mimeType:'image/png',size:bytes.length,image:{jobId:job.id,actualSize:'64x64',model:'fixture',seed:1,sha256:'fixture'}});
  const save=()=>store.db.prepare('INSERT OR REPLACE INTO h003_image_jobs VALUES(?,?,?)').run(job.id,session.id,JSON.stringify({job}));save();
  return {root,store,files,session,origin,consumer,message,bytes,job,file,save,proof:{toolCallId:'native-call',jobId:job.id,artifactId:file.id}};
}
test('durable consumption adds both run memberships and ZIP access, preserving original bytes and scalars',async t=>{
  const f=await fixture(t),beforeFile=f.store.file(f.file.id),beforeMessage=f.store.message(f.message.id),beforeJob=f.store.db.prepare('SELECT data FROM h003_image_jobs').get();
  assert.deepEqual(f.store.runSnapshot(f.consumer.id).artifactIds,[]);
  const observed:string[][]=[];f.store.events.on(f.session.id,()=>observed.push(f.store.runSnapshot(f.consumer.id).artifactIds));
  f.store.recordImageStatusConsumption(f.session.id,f.consumer.id,f.proof);
  const count=f.store.allEvents(f.session.id).length;
  f.store.recordImageStatusConsumption(f.session.id,f.consumer.id,{...f.proof,toolCallId:'second-read'});
  assert.equal(f.store.allEvents(f.session.id).length,count);assert.equal(observed.length,2);assert.ok(observed.every(ids=>ids.includes(f.file.id)));
  for(const run of [f.origin,f.consumer])assert.deepEqual(f.store.runSnapshot(run.id).artifactIds,[f.file.id]);
  assert.deepEqual(f.store.file(f.file.id),beforeFile);assert.deepEqual(f.store.message(f.message.id),beforeMessage);assert.deepEqual(f.store.db.prepare('SELECT data FROM h003_image_jobs').get(),beforeJob);assert.deepEqual(await readFile(path.join(f.root,'artifacts','saved.png')),f.bytes);
  const stream=await f.files.zip(f.session.id,f.consumer.id);const chunks:Buffer[]=[];for await(const c of stream)chunks.push(Buffer.from(c));assert.ok(Buffer.concat(chunks).includes(f.bytes));
  f.store.updateRun(f.consumer.id,'completed');assert.deepEqual(f.store.snapshot(f.session.id).runs.find(x=>x.id===f.consumer.id)?.artifactIds,[f.file.id]);
  const reopened=new Store(path.join(f.root,'db.sqlite'));try{assert.deepEqual(reopened.runSnapshot(f.consumer.id).artifactIds,[f.file.id]);assert.deepEqual(reopened.file(f.file.id),beforeFile);}finally{reopened.close();}
});
test('consumption refuses cross-session, nonrunning, failed/retained, cancellation and origin/artifact mismatches',async t=>{
 const f=await fixture(t);const other=f.store.createSession();const run=f.store.createRun(other,'message','foreign',[]);f.store.updateRun(run.id,'running');
 for(const [sessionId,runId] of [[other.id,run.id],[f.session.id,run.id]])assert.throws(()=>f.store.recordImageStatusConsumption(sessionId,runId,f.proof));
 for(const status of ['queued','completed','cancelling','interrupted'] as const){f.store.updateRun(f.consumer.id,status);assert.throws(()=>f.store.recordImageStatusConsumption(f.session.id,f.consumer.id,f.proof));}f.store.updateRun(f.consumer.id,'running');
 const original={...f.job};for(const changes of [{state:'running'},{state:'failed'},{state:'interrupted'},{state:'cancelled'},{cancelRequested:true},{artifactId:'other'},{runId:run.id},{model:'foreign'},{seed:2},{actualSize:'32x32'}]){Object.assign(f.job,original,changes);f.save();assert.throws(()=>f.store.recordImageStatusConsumption(f.session.id,f.consumer.id,f.proof));}Object.assign(f.job,original);f.save();
 assert.throws(()=>f.store.recordImageStatusConsumption(f.session.id,f.consumer.id,{...f.proof,artifactId:'foreign'}));assert.deepEqual(f.store.runSnapshot(f.consumer.id).artifactIds,[]);
 assert.equal(f.store.db.prepare('SELECT COUNT(*) AS n FROM h036_image_status_refs').get()?.n,0);
});
test('failed event persistence rolls back membership and notifications',async t=>{
 const f=await fixture(t);let emitted=0;f.store.events.on(f.session.id,()=>emitted++);const before=f.store.allEvents(f.session.id);
 f.store.db.exec("CREATE TRIGGER fail_consumption BEFORE INSERT ON events WHEN NEW.type='run' BEGIN SELECT RAISE(ABORT,'fixture failure'); END;");
 assert.throws(()=>f.store.recordImageStatusConsumption(f.session.id,f.consumer.id,f.proof),/fixture failure/);assert.deepEqual(f.store.runSnapshot(f.consumer.id).artifactIds,[]);assert.deepEqual(f.store.allEvents(f.session.id),before);assert.equal(emitted,0);
});

test('projection revalidates durable provenance without changing memberships on ordinary reads',async t=>{
 const f=await fixture(t);const before=f.store.allEvents(f.session.id).length;
 f.store.runSnapshot(f.consumer.id);f.store.snapshot(f.session.id);f.store.artifactsForRun(f.session.id,f.consumer.id);
 assert.equal(f.store.db.prepare('SELECT COUNT(*) AS n FROM h036_image_status_refs').get()?.n,0);assert.equal(f.store.allEvents(f.session.id).length,before);
 f.store.recordImageStatusConsumption(f.session.id,f.consumer.id,f.proof);f.store.updateRun(f.consumer.id,'completed');
 const original={...f.job};
 for(const changes of [{state:'failed'},{cancelRequested:true},{runId:f.consumer.id},{sessionId:'foreign'},{model:'foreign'},{artifactId:'foreign'}]){
  Object.assign(f.job,original,changes);f.save();assert.deepEqual(f.store.runSnapshot(f.consumer.id).artifactIds,[]);
  assert.deepEqual(f.store.runSnapshot(f.origin.id).artifactIds,[f.file.id]);
 }
 Object.assign(f.job,original);f.save();assert.deepEqual(f.store.runSnapshot(f.consumer.id).artifactIds,[f.file.id]);
 f.store.db.prepare('UPDATE h036_image_status_refs SET origin_run_id=? WHERE run_id=?').run(f.consumer.id,f.consumer.id);
 assert.deepEqual(f.store.runSnapshot(f.consumer.id).artifactIds,[]);
});
