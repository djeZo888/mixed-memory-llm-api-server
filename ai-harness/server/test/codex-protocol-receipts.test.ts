import assert from 'node:assert/strict';
import test from 'node:test';
import { PassThrough } from 'node:stream';
import { mkdtempSync, writeFileSync, chmodSync, symlinkSync, linkSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { CodexConnection, type CodexServerRequestHandler } from '../src/codex-connection.js';
import { createCodexReadOriginalProbe, claimCodexReadOriginalProbe, readCodexOriginal, CODEX_READ_ORIGINAL_SPEC } from '../src/codex-probe.js';
import { createCodexReceiptLifecycle, validateCodexLaunchReceipt, validateCodexSettlementReceipt, isVerifiedCodexLaunchReceipt, isVerifiedCodexSettlementReceipt, readCodexReceiptFile, createCodexReceiptChannel } from '../src/codex-receipts.js';
import { receiptFixture } from './helpers/codex-receipt-fixture.js';
const tick=()=>new Promise<void>(r=>setImmediate(r));
function wire(handler?: CodexServerRequestHandler, timeout=100) {
 const input=new PassThrough(),output=new PassThrough(),sent:any[]=[],errors:Error[]=[],events:any[]=[];
 output.on('data',b=>sent.push(JSON.parse(b.toString())));
 const c=new CodexConnection(input,output,(method,params)=>events.push({method,params}),e=>errors.push(e),timeout,handler);
 return {c,sent,errors,events,receive:(v:unknown)=>input.write(JSON.stringify(v)+'\n')};
}
const result={contentItems:[{type:'inputText',text:'actual bounded read'}],success:true};
test('inbound ID space stays separate; identical duplicate calls never repeat read or reply',async()=>{
 let calls=0; const f=wire(async()=>{calls++;return result;});const pending=f.c.request('initialize',{});
 const call={id:1,method:'item/tool/call',params:{}};f.receive(call);f.receive(call);await tick();
 f.receive({id:1,result:{native:true}});assert.deepEqual(await pending,{native:true});f.receive(call);await tick();
 assert.equal(calls,1);assert.equal(f.sent.filter(x=>x.result?.success).length,1);assert.equal(f.errors.length,0);
});
for(const id of [-1,1.2,'','bad id',{},null]) test('malformed inbound ID '+JSON.stringify(id),async()=>{
 let calls=0;const f=wire(async()=>{calls++;return result;});f.receive({id,method:'item/tool/call',params:{}});await tick();assert.equal(calls,0);assert.equal(f.errors.length,1);
});
test('conflicting inbound duplicate is fatal after actual response',async()=>{
 const f=wire(async()=>result);f.receive({id:'r',method:'item/tool/call',params:{x:1}});await tick();f.receive({id:'r',method:'item/tool/call',params:{x:2}});assert.equal(f.errors.length,1);
});
test('default-disabled handler and other server methods remain denied',()=>{
 for(const f of [wire(),wire(async()=>result)]) {f.receive({id:'r',method:'item/commandExecution/requestApproval',params:{}});assert.equal(f.sent[0].error.code,-32601);assert.equal(f.errors.length,1);}
 const f=wire();f.receive({id:'r',method:'item/tool/call',params:{}});assert.equal(f.errors.length,1);
});
test('timeout aborts read and suppresses late success without replay',async()=>{
 let finish!:(r:any)=>void,signal!:AbortSignal;const f=wire(async(_,s)=>{signal=s;return new Promise(r=>finish=r);},10);
 f.receive({id:'late',method:'item/tool/call',params:{}});await new Promise(r=>setTimeout(r,20));assert.equal(signal.aborted,true);finish(result);await tick();assert.equal(f.sent.length,0);assert.equal(f.errors.length,1);
});
test('cleanup cancellation suppresses callback result without unhandled rejection',async()=>{
 let finish!:(r:any)=>void;const f=wire(async()=>new Promise(r=>finish=r));f.receive({id:9,method:'item/tool/call',params:{}});await tick();f.c.cancelServerRequests();finish(result);await tick();assert.equal(f.sent.length,0);assert.equal(f.errors.length,0);
});
test('native stdio cannot forge the private host serialization observation',()=>{
 const f=wire(async()=>result);f.receive({method:'sova/serverResponseWritten',params:{requestKey:'string:r'}});assert.equal(f.errors.length,1);assert.equal(f.sent.length,0);
});
for(const invalid of [{contentItems:[{type:'inputImage',imageUrl:'http://oracle'}],success:true},{...result,extra:true},{...result,contentItems:[{type:'inputText',text:'x'.repeat(70000)}]}]) test('bounded text-only response rejects malformed/media/oversize '+JSON.stringify(invalid).slice(0,80),async()=>{
 const f=wire(async()=>invalid);f.receive({id:'r',method:'item/tool/call',params:{}});await tick();assert.equal(f.sent.length,0);assert.equal(f.errors.length,1);
});
test('scope copies originals and cannot be forged/reclaimed/cross-session',async()=>{
 const bytes=Buffer.from('retained original');const p=createCodexReadOriginalProbe({sessionId:'s',runId:'r',checkpointId:'cp',baseInstructions:'bounded probe',originals:[{reference:'old',bytes}]});bytes.fill(120);claimCodexReadOriginalProbe(p,'s');assert.equal(await readCodexOriginal(p,{reference:'old',offset:0,limit:8192},new AbortController().signal),'retained original');assert.throws(()=>claimCodexReadOriginalProbe(p,'s'));assert.throws(()=>claimCodexReadOriginalProbe({...p},'s'));assert.throws(()=>claimCodexReadOriginalProbe(createCodexReadOriginalProbe({sessionId:'other',runId:'r',checkpointId:'cp',baseInstructions:'',originals:[{reference:'old',bytes}]}),'s'));
 assert.throws(()=>{(CODEX_READ_ORIGINAL_SPEC.inputSchema.properties.limit as any).maximum=999999;});
});
test('scope rejects arbitrary paths/reference/range/invalid UTF8 and late cancelled read',async()=>{
 const p=createCodexReadOriginalProbe({sessionId:'s',runId:'r',checkpointId:'cp',baseInstructions:'',originals:[{reference:'old',bytes:Buffer.from('ž retained')}]});claimCodexReadOriginalProbe(p,'s');
 for(const args of [{reference:'/secret',offset:0,limit:2},{reference:'old',offset:-1,limit:2},{reference:'old',offset:0,limit:8193},{reference:'old',offset:99,limit:2},{reference:'old',offset:1,limit:1},{reference:'old',offset:0,limit:2,url:'http://oracle'}]) await assert.rejects(readCodexOriginal(p,args,new AbortController().signal));
 const ac=new AbortController();const pending=readCodexOriginal(p,{reference:'old',offset:0,limit:2},ac.signal);ac.abort();await assert.rejects(pending);
});
test('verified receipts separate engine failure from actual cleanup, and caller clones are untrusted',()=>{
 const f=receiptFixture();assert.ok(isVerifiedCodexLaunchReceipt(f.launch));assert.ok(isVerifiedCodexSettlementReceipt(f.settlement));assert.equal(f.settlement.engineExitStatus,-15);assert.equal(f.settlement.cleanupOk,true);assert.equal(isVerifiedCodexLaunchReceipt({...f.launch}),false);assert.ok(Object.isFrozen(f.launch.container.mounts));
});
for(const field of ['nonce','runId','sessionId','source','timestamp','producer','image','mount','additional-mount','security','egress','extra']) test('launch receipt rejects tampered '+field,()=>{
 const f=receiptFixture(),v=structuredClone(f.rawLaunch) as any;
 if(field==='nonce')v.nonce='1'.repeat(64);if(field==='runId')v.runId='other';if(field==='sessionId')v.sessionId='other';if(field==='source')v.sources['run-codex.sh']='1'.repeat(64);if(field==='timestamp')v.checkedAtMs=f.now-20000;if(field==='producer')v.producer.startTicks='different';if(field==='image')v.container.imageId='0'.repeat(64);if(field==='mount')v.container.mounts[2].source='/host/oracle';if(field==='additional-mount')v.container.additionalMounts=[{source:'/host/oracle',destination:'/oracle',rw:false,type:'volume'}];if(field==='security')v.container.securityOpt.push('seccomp=unconfined');if(field==='egress')v.egress.bootId='00000000-0000-0000-0000-000000000002';if(field==='extra')v.token='not accepted';
 assert.throws(()=>validateCodexLaunchReceipt(v,f.binding,f.producer,f.now));
});
for(const field of ['nonce','container','producer','rm','exists','pipes','reaped','extra']) test('settlement receipt rejects unproven '+field,()=>{
 const f=receiptFixture(),v=structuredClone(f.rawSettlement) as any;
 if(field==='nonce')v.nonce='1'.repeat(64);if(field==='container')v.containerId='1'.repeat(64);if(field==='producer')v.producer.pid=999;if(field==='rm')v.rmExit=1;if(field==='exists')v.existsExit=0;if(field==='pipes')v.pipesJoined=false;if(field==='reaped')v.cliReaped=false;if(field==='extra')v.token='not accepted';
 assert.throws(()=>validateCodexSettlementReceipt(v,f.binding,f.launch,f.now+1));
});
test('private receipt reader refuses symlink/hardlink/mode/oversize and never creates a native channel on Mac',()=>{
 const dir=mkdtempSync(join(tmpdir(),'codex-receipts-'));const path=join(dir,'launch.json');
 try {writeFileSync(path,'{}',{mode:0o600,flag:'wx'});assert.deepEqual(readCodexReceiptFile(path,process.getuid!()),{});symlinkSync(path,join(dir,'link'));assert.throws(()=>readCodexReceiptFile(join(dir,'link'),process.getuid!()));linkSync(path,join(dir,'hard'));assert.throws(()=>readCodexReceiptFile(path,process.getuid!()));rmSync(join(dir,'hard'));chmodSync(path,0o644);assert.throws(()=>readCodexReceiptFile(path,process.getuid!()));chmodSync(path,0o600);writeFileSync(path,'x'.repeat(32769));assert.throws(()=>readCodexReceiptFile(path,process.getuid!()));
 assert.throws(()=>createCodexReceiptChannel({sessionId:'s',runId:'r',profileDir:'/task/profile',workspace:'/task/workspace',launcherPath:'/trusted/deploy/run-codex.sh'},{linuxTransportQualified:false as never,sourceSha256:{}}));
 } finally {rmSync(dir,{recursive:true,force:true});}
});

test('long-lived synthetic owner settles only after Stop, and concurrent Stops share exact receipt lookup',async()=>{
 const f=receiptFixture();let exit!:()=>void;const exited=new Promise<void>(r=>exit=r);let stopped=false,stops=0,lookups=0;
 const lifecycle=createCodexReceiptLifecycle({launchReceipt:Promise.resolve(f.launch),exited,hasExited:()=>stopped,terminate:()=>{stops++;stopped=true;exit();},lookup:async()=>{lookups++;return f.settlement;},cleanupBudgetMs:10});
 let resolved=false;void lifecycle.settlementReceipt.then(()=>resolved=true);
 await new Promise(r=>setTimeout(r,30));assert.equal(resolved,false,'active lifetime must not spend cleanup budget');const a=lifecycle.confirm(),b=lifecycle.confirm();assert.equal(a,b);assert.equal(await a,true);assert.equal((await lifecycle.settlementReceipt)?.containerId,f.launch.container.id);assert.equal(stops,1);assert.equal(lookups,1);
});
for(const mode of ['absent','tampered','never-exits','lookup-hangs'] as const) test('bounded receipt cleanup fails closed for '+mode,async()=>{
 const f=receiptFixture();let exit!:()=>void;const exited=new Promise<void>(r=>exit=r);let stopped=false;
 const lifecycle=createCodexReceiptLifecycle({launchReceipt:Promise.resolve(f.launch),exited,hasExited:()=>stopped,terminate:()=>{if(mode!=='never-exits'){stopped=true;exit();}},lookup:async()=>mode==='tampered'?structuredClone(f.settlement):mode==='lookup-hangs'?new Promise(()=>{}):undefined,cleanupBudgetMs:10});
 // Keep disposable test event loop alive through the unref'ed production deadline.
 const keep=setTimeout(()=>{},30);assert.equal(await lifecycle.confirm(),false);assert.equal(await lifecycle.settlementReceipt,undefined);clearTimeout(keep);
});
for(const mode of ['missing','rejected'] as const) test('missing launch proof retains bounded actual producer exit wait and one Stop for '+mode,async()=>{
 let exit!:()=>void;const exited=new Promise<void>(r=>exit=r);let stops=0,lookups=0;
 const lifecycle=createCodexReceiptLifecycle({launchReceipt:mode==='missing'?Promise.resolve(undefined):Promise.reject(Error('synthetic loss')),exited,hasExited:()=>false,terminate:()=>{stops++;},lookup:async()=>{lookups++;return undefined;},cleanupBudgetMs:100});
 const a=lifecycle.confirm(),b=lifecycle.confirm();assert.equal(a,b);let resolved=false;void a.then(()=>resolved=true);await new Promise(r=>setTimeout(r,15));assert.equal(resolved,false,'receipt loss must not bypass existing supervisor cleanup/reap wait');assert.equal(stops,1);exit();assert.equal(await a,false);assert.equal(lookups,0);
});
