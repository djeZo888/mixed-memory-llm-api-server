/** Synthetic policy fixtures only. No Linux/native qualification. */
import test, { mock } from "node:test";
import assert from "node:assert/strict";
import { createCodexTextOnlyPolicy, assertCodexTextOnlyPolicy, codexTextOnlyThreadParams, CODEX_H041_WINDOW, createCodexParentArtifactScope, claimCodexParentArtifactScope, reserveCodexParentArtifact, codexPolicyOwnsSettledThread, recordCodexPolicyThread, recordCodexPolicySettlement } from "../src/codex-probe.js";
import { codexReceiptProvenance, getCodexReceiptUtf8, CODEX_RECEIPT_SOURCES } from "../src/codex-receipts.js";
import { composeCodexHost } from "../src/codex-host.js";
import { receiptFixture } from "./helpers/codex-receipt-fixture.js";
mock.timers.enable({apis:["Date"],now:CODEX_H041_WINDOW.startAtMs+60000});
const policy=()=>createCodexTextOnlyPolicy({sessionId:"session-1",runId:"probe-run",mode:"text-only-parent",configSha256:"b".repeat(64),modelCatalogSha256:"b".repeat(64)});
test("fixed H041 window rejects forged scope, request deadlines and boundary dispatch",()=>{
 const p=policy();assert.equal(p.window.settlementReserveMs,120000);assert.ok(Object.isFrozen(p.window));
 assert.throws(()=>assertCodexTextOnlyPolicy(structuredClone(p)),/Unowned/);
 assert.throws(()=>assertCodexTextOnlyPolicy(p,"wrong"),/Unowned/);
 assert.throws(()=>assertCodexTextOnlyPolicy(p,p.sessionId,p.window.startAtMs-1),/expired/);
 assertCodexTextOnlyPolicy(p,p.sessionId,p.window.expiresAtMs-120001);
 assert.throws(()=>assertCodexTextOnlyPolicy(p,p.sessionId,p.window.expiresAtMs-120000),/expired/);
 assertCodexTextOnlyPolicy(p,p.sessionId,p.window.expiresAtMs-1,false);
 assert.throws(()=>assertCodexTextOnlyPolicy(p,p.sessionId,p.window.expiresAtMs,false),/expired/);
 assert.throws(()=>createCodexTextOnlyPolicy({...p}));
});
test("native resume does not invent unsupported environment parameter; each turn separately omits environments",()=>{
 const p=policy();assert.deepEqual(codexTextOnlyThreadParams(p).environments,[]);
 assert.equal("environments" in codexTextOnlyThreadParams(p,"thread/resume"),false);
 const c=codexTextOnlyThreadParams(p).config;
 for(const key of ["features.shell_tool","features.goals","features.memories","features.code_mode","features.token_budget","tools.update_plan.enabled","tools.experimental_request_user_input.enabled","mcp_servers.image.enabled"]) assert.equal(c[key],false);
 assert.equal(c.web_search,"disabled");
});
const scope=()=>createCodexParentArtifactScope({sessionId:"session-1",runId:"probe-run",checkpointId:"cp",names:["recall.json","state.json"],maxBytes:16});
test("artifact scope is frozen, one-shot, exact names and bounded JSON",()=>{
 const s=scope();assert.ok(Object.isFrozen(s.names));assert.throws(()=>claimCodexParentArtifactScope(structuredClone(s),"session-1"));
 assert.throws(()=>claimCodexParentArtifactScope(s,"other"));claimCodexParentArtifactScope(s,"session-1");assert.throws(()=>claimCodexParentArtifactScope(s,"session-1"));
 for(const args of [{name:"../oracle.json",json:"{}"},{name:"recall.json",json:"invalid"},{name:"recall.json",json:"1"},{name:"recall.json",json:"{}",path:"/host"},{name:"recall.json",json:'{"oversized":"value"}'}]) assert.throws(()=>reserveCodexParentArtifact(s,args));
 const result=reserveCodexParentArtifact(s,{name:"recall.json",json:"{}"});assert.equal(result.jsonUtf8,"{}");assert.equal(result.sha256.length,64);
 assert.throws(()=>reserveCodexParentArtifact(s,{name:"recall.json",json:"{}"}));
 assert.equal(reserveCodexParentArtifact(s,{name:"state.json",json:"[]"}).name,"state.json");
});
test("synthetic validators provide neither raw channel bytes nor settled thread ownership",()=>{
 const f=receiptFixture(),p=policy();assert.equal(getCodexReceiptUtf8(f.launch),undefined);assert.equal(codexReceiptProvenance(f.launch),undefined);assert.equal(getCodexReceiptUtf8(f.settlement),undefined);
 recordCodexPolicyThread(p,"thread-1",f.launch);recordCodexPolicySettlement(p,f.settlement);assert.equal(codexPolicyOwnsSettledThread(p,"thread-1"),false);
 assert.ok(CODEX_RECEIPT_SOURCES.includes("codex/config.toml"));assert.ok(CODEX_RECEIPT_SOURCES.includes("codex/models.json"));
});
test("composed trusted admission denies synthetic receipts before E callback",async()=>{
 let called=0;const host=composeCodexHost("/trusted/deploy/run-codex.sh",()=>undefined,{protocolQualified:true,rootlessQualified:true,verifyLane:async()=>{throw Error("unused");},nativeReceiptPolicy:{linuxTransportQualified:true,sourceSha256:{}},textOnlyPolicy:()=>policy(),authorizeNativeTurn:async()=>{called++;}});
 const f=receiptFixture();await assert.rejects(host.runtime.authorizeNativeTurn!({policy:policy(),launchReceipt:f.launch,threadId:"thread-1",params:{},method:"turn/start"}),/genuine transport/);assert.equal(called,0);
});
