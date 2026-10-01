import test from 'node:test';
import assert from 'node:assert/strict';
import {createCodexH043Policy,CODEX_H043_WINDOW,assertCodexTextOnlyPolicy,createCodexTextOnlyPolicy,createCodexDelivery05Policy,CODEX_H041_WINDOW,CODEX_H041_DELIVERY05_WINDOW,codexTextOnlyThreadParams} from '../src/codex-probe.js';
const fields={sessionId:'h043-startup01-test',runId:'h043-no-turn-test',mode:'summary-only' as const,configSha256:'a'.repeat(64),modelCatalogSha256:'b'.repeat(64)};
test('H043 source factory has its own exact frozen finite window; prior windows remain original',()=>{
 const p=createCodexH043Policy(fields);assert.equal(p.window,CODEX_H043_WINDOW);assert.equal(p.window.startAtMs,Date.parse('2026-10-01T21:19:33Z'));assert.equal(p.window.expiresAtMs,Date.parse('2026-10-02T00:04:33Z'));assert.equal(p.window.settlementReserveMs,120000);assert.ok(Object.isFrozen(p)&&Object.isFrozen(p.window));
 assert.equal(createCodexTextOnlyPolicy(fields).window,CODEX_H041_WINDOW);assert.equal(CODEX_H041_WINDOW.startAtMs,Date.parse('2026-10-01T08:05:07Z'));assert.equal(CODEX_H041_WINDOW.expiresAtMs,Date.parse('2026-10-01T10:05:07Z'));assert.equal(createCodexDelivery05Policy(fields).window,CODEX_H041_DELIVERY05_WINDOW);assert.equal(CODEX_H041_DELIVERY05_WINDOW.expiresAtMs,Date.parse('2026-10-01T18:30:02.674394Z'));
});
test('H043 ownership branding, wrong session, prewindow and dispatch/terminal cutoff guards stay active',()=>{
 const p=createCodexH043Policy(fields),w=p.window;assert.doesNotThrow(()=>assertCodexTextOnlyPolicy(p,p.sessionId,w.startAtMs));assert.throws(()=>assertCodexTextOnlyPolicy({...p},p.sessionId,w.startAtMs));assert.throws(()=>assertCodexTextOnlyPolicy(p,'other',w.startAtMs));assert.throws(()=>assertCodexTextOnlyPolicy(p,p.sessionId,w.startAtMs-1));assert.doesNotThrow(()=>assertCodexTextOnlyPolicy(p,p.sessionId,w.expiresAtMs-120001));assert.throws(()=>assertCodexTextOnlyPolicy(p,p.sessionId,w.expiresAtMs-120000));assert.doesNotThrow(()=>assertCodexTextOnlyPolicy(p,p.sessionId,w.expiresAtMs-1,false));assert.throws(()=>assertCodexTextOnlyPolicy(p,p.sessionId,w.expiresAtMs,false));
});
test('H043 factory rejects supplied window, unknown fields, invalid hashes, and retention widening',()=>{
 for(const v of [{...fields,window:CODEX_H043_WINDOW},{...fields,authority:true},{...fields,configSha256:'bad'},{...fields,mode:'retention-parent'},{...fields,collaborationVersion:'v2'}])assert.throws(()=>createCodexH043Policy(v as any));
});
test('H043 summary source capability keeps no-tools and no-agent read-only parameters',()=>{
 const p=createCodexH043Policy(fields),old=Date.now;Date.now=()=>CODEX_H043_WINDOW.startAtMs+1;
 try{const params=codexTextOnlyThreadParams(p);assert.equal(params.sandbox,'read-only');assert.deepEqual(params.environments,[]);assert.equal(params.config['agents.enabled'],false);assert.equal(params.config['features.multi_agent'],false);assert.equal(params.config['web_search'],'disabled');assert.equal(params.config['mcp_servers.image.enabled'],false);}finally{Date.now=old;}
});

test('H043 does not redirect H042 or permit retention/general installer scope',async()=>{
 const {createCodexH042Policy,CODEX_H042_WINDOW}=await import('../src/codex-probe.js');
 assert.equal(createCodexH042Policy(fields).window,CODEX_H042_WINDOW);
 assert.equal(CODEX_H042_WINDOW.expiresAtMs,Date.parse('2026-10-01T20:29:17Z'));
 for(const mode of ['retention-parent','installer','image'])assert.throws(()=>createCodexH043Policy({...fields,mode} as any));
});
