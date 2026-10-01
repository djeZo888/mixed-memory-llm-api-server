import test from 'node:test';
import assert from 'node:assert/strict';
import {createCodexH042Policy,CODEX_H042_WINDOW,assertCodexTextOnlyPolicy,createCodexTextOnlyPolicy,createCodexDelivery05Policy,CODEX_H041_WINDOW,CODEX_H041_DELIVERY05_WINDOW,codexTextOnlyThreadParams} from '../src/codex-probe.js';
const fields={sessionId:'h042-startup01-test',runId:'h042-no-turn-test',mode:'summary-only' as const,configSha256:'a'.repeat(64),modelCatalogSha256:'b'.repeat(64)};
test('H042 source factory has its own exact frozen finite window; prior windows remain original',()=>{
 const p=createCodexH042Policy(fields);assert.equal(p.window,CODEX_H042_WINDOW);assert.equal(p.window.startAtMs,Date.parse('2026-10-01T17:44:17Z'));assert.equal(p.window.expiresAtMs,Date.parse('2026-10-01T20:29:17Z'));assert.equal(p.window.settlementReserveMs,120000);assert.ok(Object.isFrozen(p)&&Object.isFrozen(p.window));
 assert.equal(createCodexTextOnlyPolicy(fields).window,CODEX_H041_WINDOW);assert.equal(CODEX_H041_WINDOW.startAtMs,Date.parse('2026-10-01T08:05:07Z'));assert.equal(CODEX_H041_WINDOW.expiresAtMs,Date.parse('2026-10-01T10:05:07Z'));assert.equal(createCodexDelivery05Policy(fields).window,CODEX_H041_DELIVERY05_WINDOW);assert.equal(CODEX_H041_DELIVERY05_WINDOW.expiresAtMs,Date.parse('2026-10-01T18:30:02.674394Z'));
});
test('H042 ownership branding, wrong session, prewindow and dispatch/terminal cutoff guards stay active',()=>{
 const p=createCodexH042Policy(fields),w=p.window;assert.doesNotThrow(()=>assertCodexTextOnlyPolicy(p,p.sessionId,w.startAtMs));assert.throws(()=>assertCodexTextOnlyPolicy({...p},p.sessionId,w.startAtMs));assert.throws(()=>assertCodexTextOnlyPolicy(p,'other',w.startAtMs));assert.throws(()=>assertCodexTextOnlyPolicy(p,p.sessionId,w.startAtMs-1));assert.doesNotThrow(()=>assertCodexTextOnlyPolicy(p,p.sessionId,w.expiresAtMs-120001));assert.throws(()=>assertCodexTextOnlyPolicy(p,p.sessionId,w.expiresAtMs-120000));assert.doesNotThrow(()=>assertCodexTextOnlyPolicy(p,p.sessionId,w.expiresAtMs-1,false));assert.throws(()=>assertCodexTextOnlyPolicy(p,p.sessionId,w.expiresAtMs,false));
});
test('H042 factory rejects supplied window, unknown fields, invalid hashes, and retention widening',()=>{
 for(const v of [{...fields,window:CODEX_H042_WINDOW},{...fields,authority:true},{...fields,configSha256:'bad'},{...fields,mode:'retention-parent'},{...fields,collaborationVersion:'v2'}])assert.throws(()=>createCodexH042Policy(v as any));
});
test('H042 summary source capability keeps no-tools and no-agent read-only parameters',()=>{
 const p=createCodexH042Policy(fields),old=Date.now;Date.now=()=>CODEX_H042_WINDOW.startAtMs+1;
 try{const params=codexTextOnlyThreadParams(p);assert.equal(params.sandbox,'read-only');assert.deepEqual(params.environments,[]);assert.equal(params.config['agents.enabled'],false);assert.equal(params.config['features.multi_agent'],false);assert.equal(params.config['web_search'],'disabled');assert.equal(params.config['mcp_servers.image.enabled'],false);}finally{Date.now=old;}
});
