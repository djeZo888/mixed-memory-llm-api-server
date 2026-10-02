/** SYNTHETIC fixtures only: private preserved ordering; never native qualification. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {PassThrough} from 'node:stream';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {spawn} from 'node:child_process';
import {protocol,effectGate,validateAcks,armProtocolCapture,shutdownOwned} from './carrier.mjs';
assert.ok(process.env.H046_ORIGINAL_PROTOCOL,'explicit private original protocol fixture required');
const originals=JSON.parse(readFileSync(process.env.H046_ORIGINAL_PROTOCOL,'utf8'));
const output=originals.filter(x=>x.direction==='output').map(x=>{
 const bytes=Buffer.from(x.bytesBase64,'base64');
 assert.equal(createHash('sha256').update(bytes).digest('hex'),x.sha256,'original frame hash');
 return bytes.toString('utf8').trimEnd().split('\n').map(JSON.parse);
});
const initialize=output[0][0].result,threadStart=output[1][0].result;
const input={profileDir:initialize.codexHome.replace(/\/codex-home$/,''),workspace:threadStart.cwd};
// Synchronous response/callback ordering of CodexConnection, explicitly SYNTHETIC.
class SyntheticConnection{
 constructor(stdout,stdin,notification,failed){this.stdin=stdin;this.notification=notification;this.failed=failed;this.pending=new Map();this.nextId=1;this.buffer='';stdout.setEncoding('utf8');stdout.on('data',chunk=>{if(this.failure)return;this.buffer+=chunk;let n;while(!this.failure&&(n=this.buffer.indexOf('\n'))>=0){const line=this.buffer.slice(0,n);this.buffer=this.buffer.slice(n+1);try{const v=JSON.parse(line);if(typeof v.method==='string'){if('id' in v)throw Error('SYNTHETIC unsupported server request');this.notification(v.method,v.params);}else{const p=this.pending.get(v.id);assert.ok(p,'SYNTHETIC unexpected response');this.pending.delete(v.id);if('error' in v){p.reject(Error('App Server rejected the requested operation'));this.fail(Error('App Server rejected the requested operation'));}else p.resolve(v.result);}}catch(error){this.fail(error);}}});}
 request(method,params){const id=this.nextId++;return new Promise((resolve,reject)=>{this.pending.set(id,{resolve,reject});try{this.stdin.write(JSON.stringify({id,method,params})+'\n');}catch(error){this.fail(error);}});}
 initialized(){this.stdin.write(JSON.stringify({method:'initialized',params:{}})+'\n');}
 fail(error){if(this.failure)return;this.failure=error;for(const p of this.pending.values())p.reject(error);this.pending.clear();this.failed(error);}
}
function fixture(mutate=()=>{},split=false){
 const chunks=structuredClone(output);mutate(chunks);
 const stdin=new PassThrough(),stdout=new PassThrough(),methods=[],timers=[];let buffer='';
 const emit=index=>{const raw=chunks[index].map(v=>JSON.stringify(v)+'\n').join('');if(split){stdout.write(raw.slice(0,17));stdout.write(raw.slice(17));}else stdout.write(raw);};
 stdin.on('data',chunk=>{buffer+=chunk;let n;while((n=buffer.indexOf('\n'))>=0){const value=JSON.parse(buffer.slice(0,n));buffer=buffer.slice(n+1);methods.push(value.method);if(value.method==='initialize')timers.push(setImmediate(()=>emit(0)));if(value.method==='thread/start'){timers.push(setImmediate(()=>emit(1)));for(let i=2;i<chunks.length;i++)timers.push(setTimeout(()=>emit(i),i*10));}}});
 return {stdin,stdout,methods,close(){for(const timer of timers){clearImmediate(timer);clearTimeout(timer);}stdin.end();stdout.end();}};
}
async function run(mutate,split=false){const f=fixture(mutate,split),frames=armProtocolCapture(f);try{return {result:await protocol(f,SyntheticConnection,input,new AbortController().signal,frames),methods:f.methods};}finally{f.close();}}
const remote=c=>c[0][1],mcp=c=>c[1][2];
test('SYNTHETIC preserved same-buffer ACK ordering and later MCP ready',async()=>{
 const {result,methods}=await run();assert.equal(result.nativeThreadId,threadStart.thread.id);assert.deepEqual(result.initialize,initialize);assert.deepEqual(result.threadStart,threadStart);assert.deepEqual(methods,['initialize','initialized','thread/start']);assert.equal(result.frames.filter(v=>v.direction==='input').length,3);assert.equal(result.frames.filter(v=>v.direction==='output').length,output.length);
 assert.equal(output.flat().filter(v=>v.params?.name==='browser'&&v.params?.status==='ready').length,0,'original lacks browser readiness; do not invent it');
});
test('SYNTHETIC split envelopes retain ACK binding',async()=>assert.equal((await run(undefined,true)).result.nativeThreadId,threadStart.thread.id));
test('SYNTHETIC invalid notification beside initialize ACK prevents later effects',async t=>{
 for(const [name,mutate] of [
 ['unknown method',c=>remote(c).method='turn/started'],
 ['enabled remote',c=>remote(c).params.status='enabled'],
 ['wrong environment',c=>remote(c).params.environmentId='local'],
 ['missing remote field',c=>delete remote(c).params.installationId],
 ['extra remote field',c=>remote(c).params.extra=true],
 ['bad remote server',c=>remote(c).params.serverName=''],
 ['bad installation',c=>remote(c).params.installationId='bad'],
 ['bad emittedAtMs',c=>remote(c).emittedAtMs='1790956047340'],
 ['extra envelope',c=>remote(c).extra=true],
 ['request envelope',c=>remote(c).id=22],
 ['timestamp in payload',c=>remote(c).params.emittedAtMs=remote(c).emittedAtMs],
 ['thread before dispatch',c=>c[0].push(structuredClone(c[1][2]))],
 ])await t.test(name,async()=>{const f=fixture(mutate);try{await assert.rejects(protocol(f,SyntheticConnection,input,new AbortController().signal));assert.deepEqual(f.methods,['initialize']);}finally{f.close();}});
});
test('SYNTHETIC wrong-thread/failing/malformed bootstrap refuses after same-buffer ACK',async t=>{
 for(const [name,mutate] of [
 ['wrong MCP thread',c=>mcp(c).params.threadId='wrong-thread'],
 ['wrong thread/started',c=>c[1][1].params.thread.id='wrong-thread'],
 ['changed thread/started',c=>c[1][1].params.thread.turns=[{id:'forbidden'}]],
 ['malformed thread/started',c=>c[1][1].params.thread=null],
 ['unknown server',c=>mcp(c).params.name='other'],
 ['error',c=>mcp(c).params.error='failed'],
 ['failure reason',c=>mcp(c).params.failureReason='failed'],
 ['failed status',c=>mcp(c).params.status='failed'],
 ['missing MCP field',c=>delete mcp(c).params.error],
 ['extra MCP field',c=>mcp(c).params.extra=true],
 ['array payload',c=>mcp(c).params=[]],
 ['tool notification',c=>mcp(c).method='item/tool/call'],
 ['tool request',c=>{mcp(c).method='item/tool/call';mcp(c).id=7;}],
 ['ready before starting',c=>mcp(c).params.status='ready'],
 ['duplicate starting',c=>c[1].push(structuredClone(mcp(c)))],
 ['unknown delayed notification',c=>c[3][0].method='turn/completed'],
 ['wrong delayed thread',c=>c[3][0].params.threadId='wrong-thread'],
 ['notification flood',c=>{for(let i=0;i<17;i++)c[1].push(structuredClone(mcp(c)));}],
 ])await t.test(name,async()=>assert.rejects(run(mutate)));
});
test('SYNTHETIC strict initialize/thread ACK guards and failed ACK remain closed',async t=>{
 for(const [name,mutate] of [
 ['wrong version',c=>c[0][0].result.userAgent='codex/0.159.2'],
 ['wrong home',c=>c[0][0].result.codexHome='/wrong'],
 ['wrong workspace',c=>c[1][0].result.cwd='/wrong'],
 ['wrong model',c=>c[1][0].result.model='other'],
 ['invalid ID',c=>c[1][0].result.thread.id=null],
 ['failed thread ACK',c=>{delete c[1][0].result;c[1][0].error={code:-1,message:'SYNTHETIC startup failure'};}],
 ])await t.test(name,async()=>assert.rejects(run(mutate)));
 assert.throws(()=>validateAcks(initialize,{...threadStart,approvalPolicy:'on-request'},input));
});
test('SYNTHETIC outbound gate refuses turns/tools/compaction and repeated startup before write',()=>{
 for(const method of ['turn/start','turn/resume','thread/resume','thread/compact/start','turn/interrupt','item/tool/call']){const owned={stdin:new PassThrough(),stdout:new PassThrough()};armProtocolCapture(owned);let writes=0;owned.stdin.on('data',()=>writes++);assert.throws(()=>owned.stdin.write(JSON.stringify({method,params:{}})),/Forbidden/);assert.equal(writes,0);owned.stdin.end();owned.stdout.end();}
 for(const repeatAt of [0,1,2]){const gate=effectGate(),methods=['initialize','initialized','thread/start'];for(let i=0;i<=repeatAt;i++)gate(JSON.stringify({method:methods[i],params:{}}));assert.throws(()=>gate(JSON.stringify({method:methods[repeatAt],params:{}})),/Forbidden/);}
 const gate=effectGate();for(const method of ['initialize','initialized','thread/start'])gate(JSON.stringify({method,params:{}}));assert.throws(()=>gate(JSON.stringify({method:'turn/start',params:{}})),/Forbidden/);
});
test('SYNTHETIC capture keeps 2MiB bound; abort remains finite',async()=>{
 const f=fixture(),frames=armProtocolCapture(f);const error=new Promise(resolve=>f.stdout.once('error',e=>resolve(e.message)));f.stdout.push(Buffer.alloc(2*1024*1024+1));assert.match(await error,/bound/);assert.match(frames.captureFailure,/bound/);f.close();
 const g=fixture(),abort=new AbortController();abort.abort();try{await assert.rejects(protocol(g,SyntheticConnection,input,abort.signal),/Finite carrier stop/);}finally{g.close();}
});
test('SYNTHETIC failed startup has one owned shutdown awaiting actual child exit and settlement',async()=>{
 const f=fixture(c=>mcp(c).params.error='SYNTHETIC failure');await assert.rejects(protocol(f,SyntheticConnection,input,new AbortController().signal));f.close();
 const child=spawn(process.execPath,['-e',"setTimeout(()=>process.exit(7),90)"],{stdio:'ignore'});let count=0,closed=false;
 const exitObservation=new Promise(resolve=>child.once('exit',(code,signal)=>{closed=true;resolve({code,signal,spawnFailed:false});})),exited=exitObservation.then(()=>undefined);
 const settlementReceipt=exited.then(()=>({synthetic:true,engineExitStatus:7}));
 const owned={exited,exitObservation,settlementReceipt,terminateAndConfirm:async()=>{count++;return false;}};
 const shutdown=shutdownOwned(owned);let settled=false;void shutdown.then(()=>settled=true);await new Promise(resolve=>setTimeout(resolve,20));assert.equal(settled,false);assert.equal(closed,false);
 const result=await shutdown;assert.equal(count,1);assert.equal(closed,true);assert.equal(result.cleanup,false);assert.equal(result.exit.code,7);assert.equal(result.exit.signal,null);assert.equal(result.settlement.engineExitStatus,7);
 console.log(JSON.stringify({label:'SYNTHETIC shutdown child',actualWaitExit:result.exit.code,pid:child.pid,birth:'UNKNOWN short-child birth; recorder proves outer group absence',awaited:true}));
});
