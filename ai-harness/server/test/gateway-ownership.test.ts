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
