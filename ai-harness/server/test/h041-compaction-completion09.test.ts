/** SOURCE09 only: real UDS/HMAC transport with explicitly synthetic protected
 * filesystem/kernel readbacks. No native/model/production access or PASS. */
import test from 'node:test';import assert from 'node:assert/strict';
import fs from 'node:fs';import net from 'node:net';import {syncBuiltinESMExports} from 'node:module';import {createHmac} from 'node:crypto';import {tmpdir} from 'node:os';import {join} from 'node:path';
import {loadQualificationTaskAdmission,isQualificationTaskAdmission} from '../src/qualification-task-admission.js';
import {CarrierAdmission,carrierRowsHeld,validateCarrierBinding} from '../../acceptance/compaction/native-adapter/carrier-admission.js';
import {actionFingerprint,freezeKey} from '../src/dispatch-freeze.js';import {AUTHORIZATIONS} from '../../acceptance/compaction/authorization.mjs';
import {loadReviewedCarrierEntry} from '../../acceptance/compaction/native-adapter/entry.js';
const now=Date.parse('2026-10-01T15:00:00Z'),authority=AUTHORIZATIONS['H041-COMPACTION-DELIVERY-05'];
const action={action:'service.stop',node_id:'ai-harness',service_id:'harness',idempotency_key:'SOURCE-owned-stop',allow_interrupt:true};
function binding(){return {admissionPath:'/run/ai-harness-qualification/source09-test/admission.json',transactionId:'SOURCE-transaction',sessionId:'SOURCE-parent',ownHold:{key:freezeKey(action as any),fingerprint:actionFingerprint(action as any),action:JSON.stringify(action),scope:JSON.stringify(['harness'])}};}
function row(){return {...binding().ownHold,acknowledged:1};}
const review=()=>({authorization:{...authority,windowId:'SOURCE09'},notAfterUtc:authority.capUtc,settlementReserveMs:120000,carrier:binding()});
test('SOURCE exact own STOP exclusion preserves foreign holds, immutable rows and whole-node frontier semantics',()=>{
 assert.equal(carrierRowsHeld([row()],binding(),'qwen3.8-27b'),false);
 const foreign={...row(),key:'SOURCE-foreign',scope:JSON.stringify(['qwen-gpu1'])};assert.equal(carrierRowsHeld([row(),foreign],binding(),'qwen3.8-27b'),true);assert.equal(carrierRowsHeld([row(),foreign],binding(),'qwen3.8-27b-gpu0'),false);
 for(const bad of [{...row(),acknowledged:0},{...row(),fingerprint:'CHANGED'},{...row(),action:row().action+' '},{...row(),scope:'[]'}])assert.throws(()=>carrierRowsHeld([bad],binding()));assert.throws(()=>carrierRowsHeld([],binding()));assert.throws(()=>carrierRowsHeld([row(),row()],binding()));assert.throws(()=>carrierRowsHeld([row(),{...foreign,scope:'broken'}],binding()));
 assert.equal(carrierRowsHeld([row(),{...foreign,action:JSON.stringify({node_id:'ai-vm',action:'node.reboot'}),scope:'[]'}],binding(),'glm-5.3-flash'),true);
});
test('SOURCE carrier rejects JSON brands and cross-config STOP bindings before files/workers/native',async t=>{
 t.mock.method(Date,'now',()=>now);await assert.rejects(loadReviewedCarrierEntry('/SOURCE-never-read',{} as any),/actual_A_carrier/);assert.throws(()=>new CarrierAdmission({verify:async()=>({status:'admit'})} as any,binding(),review()),/brand_required/);
 assert.deepEqual(validateCarrierBinding({carrier:binding(),bootstrap:{review:review()}}),binding());const config={carrier:binding(),bootstrap:{review:review()}};config.carrier.transactionId='FOREIGN';assert.throws(()=>validateCarrierBinding(config),/exact_root_reviewed/);
});
test('SOURCE actual A challenge + E retained parsed response; fresh exact owner/STOP/request only, no session alias or stale grant',async t=>{
 const directory=fs.realpathSync(fs.mkdtempSync(join(tmpdir(),'h041-source09-uds-'))),socketPath=join(directory,'source.sock'),key=Buffer.alloc(32,7),boot='00000000-0000-0000-0000-000000000009',fields=Array(20).fill('0');fields[19]='123';
 const platform=Object.getOwnPropertyDescriptor(process,'platform')!;Object.defineProperty(process,'platform',{value:'linux'});t.mock.method(Date,'now',()=>now);
 const b=binding(),p={schema:'qualification-task-admission-v1',carrier:{pid:9999,startTicks:'123',bootId:boot},dispatchCutoffMs:Date.parse(authority.capUtc)-120000,expiresAtMs:Date.parse(authority.capUtc),key:key.toString('hex'),lane:'qwen3.8-27b',ownHoldKey:b.ownHold.key,sessionId:b.sessionId,socketPath:b.admissionPath.replace('admission.json','admission.sock'),transactionId:b.transactionId};
 let fault='',seen=0;const server=net.createServer(socket=>{let raw='';socket.on('data',chunk=>{raw+=chunk;if(!raw.endsWith('\n'))return;seen++;const e=JSON.parse(raw),q=JSON.parse(e.body);assert.equal(e.mac,createHmac('sha256',key).update(e.body).digest('hex'));const v={...q,ownHoldKey:b.ownHold.key,ownerStartTicks:'123',status:'admit',observedAtMs:now};if(fault==='transaction')v.transactionId='FOREIGN';if(fault==='freshness')v.observedAtMs=NaN;const body=JSON.stringify(v);socket.end(JSON.stringify({body,mac:createHmac('sha256',key).update(body).digest('hex')})+'\n');});});
 await new Promise<void>(resolve=>server.listen(socketPath,resolve));
 const read=fs.readFileSync,lstat=fs.lstatSync,realpath=fs.realpathSync,connect=net.connect;
 t.mock.method(fs,'readFileSync',(path:any,...args:any[])=>{if(path===b.admissionPath)return JSON.stringify(p);if(path==='/proc/9999/stat')return `9999 (SOURCE mocked kernel) ${fields.join(' ')}`;if(path==='/proc/9999/status')return 'Uid:\t0\t0\t0\t0\n';if(path==='/proc/sys/kernel/random/boot_id')return boot;return (read as any)(path,...args);});
 t.mock.method(fs,'lstatSync',(path:any,...args:any[])=>path===b.admissionPath||path===p.socketPath?{uid:0,mode:path===b.admissionPath?0o640:0o660,nlink:1,size:1000,isFile:()=>path===b.admissionPath,isSocket:()=>path===p.socketPath}:(lstat as any)(path,...args));
 t.mock.method(fs,'realpathSync',(path:any,...args:any[])=>path===b.admissionPath?path:(realpath as any)(path,...args));t.mock.method(net,'connect',((path:any,...args:any[])=>path===p.socketPath?connect(socketPath):(connect as any)(path,...args)) as any);syncBuiltinESMExports();
 t.after(async()=>{t.mock.restoreAll();syncBuiltinESMExports();Object.defineProperty(process,'platform',platform);await new Promise<void>(resolve=>server.close(()=>resolve()));fs.rmSync(directory,{recursive:true,force:true});});
 const admission=loadQualificationTaskAdmission(b.admissionPath);assert.equal(isQualificationTaskAdmission(admission),true);const gate=new CarrierAdmission(admission,b,review());assert.equal(gate.held([row()],'harness'),true);
 const actual=await gate.verify('SOURCE-parent','SOURCE-request',undefined,directory);assert.equal(actual.requestId,'SOURCE-request');assert.equal(gate.held([row()],'harness'),false);assert.equal(gate.held([row(),{...row(),key:'FOREIGN'}],'harness'),true);assert.equal(fs.readdirSync(directory).filter(n=>n.startsWith('carrier-')).length,1);
 await assert.rejects(gate.verify('FOREIGN-probe','SOURCE-request'),/foreign_or_expired/);assert.equal(seen,1);fault='transaction';await assert.rejects(gate.verify('SOURCE-parent','SOURCE-request2'),/challenge_scope/);assert.equal(gate.held([row()],'harness'),true);fault='freshness';await assert.rejects(gate.verify('SOURCE-parent','SOURCE-request3'),/current_exact|challenge_scope/);
 t.mock.method(Date,'now',()=>Date.parse(authority.capUtc));assert.equal(gate.held([row()],'harness'),true);await assert.rejects(gate.verify('SOURCE-parent','SOURCE-request4'));
});
