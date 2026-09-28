import test from "node:test";
import assert from "node:assert/strict";
import { DatabaseSync } from "node:sqlite";
import { GatewayOwnership,GatewayOwnershipLedger } from "../src/gateway-ownership.js";
test("per-session durable lineage survives accepted drain, revoked tokens and restart uncertainty",()=>{
 const db=new DatabaseSync(":memory:");const ledger=new GatewayOwnershipLedger(db);const a=new GatewayOwnership(ledger.options());a.registerSession("one");a.registerSession("two");assert.equal(a.confirm({sessionId:"one"}),true);
 const r=a.begin("one");assert.equal(a.confirm({sessionId:"one"}),false);assert.equal(a.confirm({sessionId:"two"}),true);
 a.transition(r,"counting","qwen");a.transition(r,"accepted");a.transition(r,"draining");assert.equal(a.snapshot("one")[0]?.state,"draining");
 const restarted=new GatewayOwnership(ledger.options());assert.equal(restarted.snapshot("one")[0]?.state,"uncertain");assert.equal(restarted.confirm({sessionId:"one"}),false);
 a.transition(r,"settled");assert.equal(a.confirm({sessionId:"one"}),true);assert.equal(a.confirm({sessionId:"unknown"}),false);db.close();
});
test("missing recovery proof, child/aux ownership and failed durable write fail closed",()=>{
 const a=new GatewayOwnership();a.registerSession("s");assert.equal(a.confirm({sessionId:"s"}),false);
 const b=new GatewayOwnership({recoveryReady:true,onRequestState:()=>{}});const parent=b.begin("s"),child=b.begin("s"),aux=b.begin("s");b.transition(parent,"settled");b.transition(child,"settled");assert.equal(b.confirm({sessionId:"s"}),false);b.transition(aux,"settled");assert.equal(b.confirm({sessionId:"s"}),true);
 const bad=new GatewayOwnership({recoveryReady:true,onRequestState:()=>{throw Error("disk");}});assert.throws(()=>bad.begin("s"));assert.equal(bad.confirm({sessionId:"s"}),false);
});

test('bounded observation waits for every durable session owner and ignores unrelated settlement', async () => {
 const db=new DatabaseSync(':memory:');const ledger=new GatewayOwnershipLedger(db);const a=new GatewayOwnership(ledger.options());
 const parent=a.begin('s'),child=a.begin('s'),other=a.begin('other');a.transition(parent,'draining');
 let resolved=false;const waiting=a.waitForSettlement({sessionId:'s'},1000).then(v=>{resolved=true;return v;});
 a.transition(other,'settled');a.transition(parent,'settled');await Promise.resolve();assert.equal(resolved,false);
 assert.equal(a.confirm({sessionId:'s'}),false);a.transition(child,'settled');assert.equal(await waiting,true);
 assert.equal(db.prepare("SELECT count(*) AS n FROM h021_gateway_requests WHERE session_id='s' AND state!='settled'").get()!.n,0);db.close();
});
test('observation timeout, unknown recovery, uncertainty and failed persistence retain ownership', async () => {
 const a=new GatewayOwnership({recoveryReady:true,onRequestState:()=>{}});const r=a.begin('s');a.transition(r,'draining');
 assert.equal(await a.waitForSettlement({sessionId:'s'},5),false);assert.equal(a.snapshot('s')[0]?.state,'draining');
 const waiting=a.waitForSettlement({sessionId:'s'},1000);a.transition(r,'uncertain');assert.equal(await waiting,false);
 assert.equal(await a.waitForSettlement({sessionId:'unknown'},1000),false);
 const noRecovery=new GatewayOwnership();noRecovery.registerSession('s');assert.equal(await noRecovery.waitForSettlement({sessionId:'s'},1000),false);
 let fail=false;const bad=new GatewayOwnership({recoveryReady:true,onRequestState:()=>{if(fail)throw Error('disk');}});
 const pending=bad.begin('s');const proof=bad.waitForSettlement({sessionId:'s'},1000);fail=true;
 assert.throws(()=>bad.transition(pending,'settled'));assert.equal(await proof,false);assert.equal(bad.snapshot('s')[0]?.state,'uncertain');
 for(const budget of [-1,15001,NaN])assert.throws(()=>a.waitForSettlement({sessionId:'s'},budget));
});

test('signal observation survives 46s fake time while old bounded proof remains bounded; every owner must durably settle', async t => {
 t.mock.timers.enable({apis:['setTimeout']});
 const db=new DatabaseSync(':memory:');t.after(()=>db.close());
 const a=new GatewayOwnership(new GatewayOwnershipLedger(db).options());
 const parent=a.begin('s'),child=a.begin('s'),other=a.begin('other');a.transition(parent,'draining');
 const stop=new AbortController();let resolved=false;
 const proof=a.waitForSettlement({sessionId:'s'},stop.signal).then(v=>{resolved=true;return v;});
 const old=a.waitForSettlement({sessionId:'s'},15000);
 t.mock.timers.tick(46000);assert.equal(await old,false);await Promise.resolve();assert.equal(resolved,false);
 a.transition(other,'settled');a.transition(parent,'settled');await Promise.resolve();assert.equal(resolved,false);
 assert.equal(db.prepare("SELECT count(*) AS n FROM h021_gateway_requests WHERE session_id='s' AND state!='settled'").get()!.n,1);
 a.transition(child,'settled');assert.equal(await proof,true);
 assert.equal(db.prepare("SELECT count(*) AS n FROM h021_gateway_requests WHERE session_id='s' AND state!='settled'").get()!.n,0);
 const {getEventListeners}=await import('node:events');assert.equal(getEventListeners(stop.signal,'abort').length,0);
});

test('signal observer fails closed for unknown/recovery/uncertain, ledger write failure and shutdown; listeners are removed', async () => {
 const {getEventListeners}=await import('node:events');
 const signal=new AbortController();const a=new GatewayOwnership({recoveryReady:true,onRequestState:()=>{}});
 assert.equal(await a.waitForSettlement({sessionId:'unknown'},signal.signal),false);
 const notReady=new GatewayOwnership();notReady.registerSession('s');assert.equal(await notReady.waitForSettlement({sessionId:'s'},signal.signal),false);
 const r=a.begin('s');const uncertain=a.waitForSettlement({sessionId:'s'},signal.signal);a.transition(r,'uncertain');assert.equal(await uncertain,false);
 let fail=false;const bad=new GatewayOwnership({recoveryReady:true,onRequestState:()=>{if(fail)throw Error('disk');}});
 const b=bad.begin('s');bad.transition(b,'draining');const failed=bad.waitForSettlement({sessionId:'s'},signal.signal);
 fail=true;assert.throws(()=>bad.transition(b,'settled'),/ledger/);assert.equal(await failed,false);assert.equal(bad.snapshot('s')[0]!.state,'uncertain');
 const owner=a.begin('pending');a.transition(owner,'draining');const stopped=a.waitForSettlement({sessionId:'pending'},signal.signal);
 signal.abort();assert.equal(await stopped,false);assert.equal(a.snapshot('pending')[0]!.state,'draining');
 a.transition(owner,'settled');assert.equal(await a.waitForSettlement({sessionId:'pending'},signal.signal),false);
 assert.equal(getEventListeners(signal.signal,'abort').length,0);
});
