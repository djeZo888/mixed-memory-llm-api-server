import test from 'node:test';
import assert from 'node:assert/strict';
import {codexCapabilities} from '../src/codex-capabilities.js';

test('usable tool metadata distinguishes direct native qualification from matched model acceptance',()=>{
 const c=codexCapabilities();
 for(const name of ['search','browser','pdf'] as const){assert.equal(c[name].supported,true);assert.equal(c[name].qualification,'native_fixture');assert.match(c[name].reason,/passed|acceptance/);}
 assert.equal(c.coding.supported,true);assert.equal(c.coding.qualification,'live');assert.match(c.coding.reason,/Qwen0/);assert.match(c.pdf.reason,/H035 unchanged PDF workflow passed/);assert.match(c.pdf.reason,/truthful failure\/recovery reporting/);assert.match(c.pdf.reason,/native visual inspection remains unsupported/);assert.match(c.pdf.reason,/falsely reported no tool failures/);
 for(const name of ['image','frontier','nativeMedia','nativeDelegation'] as const)assert.equal(c[name].supported,false);
});
test('image and delegation metadata never override independent operational gates or native media',()=>{
 const reviewed={image:{supported:true,qualification:'native_fixture' as const,reason:'catalog only'},nativeDelegation:{supported:true,qualification:'native_fixture' as const,reason:'fixture'}};
 assert.equal(codexCapabilities(reviewed).image.supported,false);
 const c=codexCapabilities(reviewed,{imageToolEnabled:true,delegationEnabled:true});assert.equal(c.image.supported,true);assert.equal(c.image.qualification,'native_fixture');assert.equal(c.nativeDelegation.supported,true);assert.equal(c.nativeMedia.supported,false);assert.equal(c.frontier.supported,false);
});

test('current qualification reasons retain failures without stale frontier owner or changed gates',()=>{
 const c=codexCapabilities();assert.equal(c.frontier.supported,false);assert.equal(c.image.supported,false);assert.equal(c.pdf.qualification,'native_fixture');assert.match(c.frontier.reason,/Responses and tool-continuation qualification pending/);assert.doesNotMatch(c.frontier.reason,/H019/);assert.match(c.pdf.reason,/H031 original incomplete workflow remains failed/);assert.equal(c.compaction.qualification,"live");assert.match(c.compaction.reason,/H030 small manual compaction and recall passed/);assert.match(c.compaction.reason,/H031 retained cold continuation passed/);assert.match(c.compaction.reason,/402104 input tokens and a 237-token summary/);assert.match(c.compaction.reason,/distinct resumed follow-up read the retained file and returned four correct facts and 0.825 W/);assert.match(c.compaction.reason,/summary-only recall is not isolated/);assert.match(c.compaction.reason,/Automatic triggering is inferred; raw AUTO metadata is absent/);assert.match(c.compaction.reason,/original interrupted run remains unsuccessful/);assert.equal(c.nativeMedia.qualification,"not_tested");assert.match(c.nativeMedia.reason,/native pixel input is unsupported; audio\/video recognition is not tested/);assert.match(c.nativeMedia.reason,/OCR, procedural pixel inspection and specialist image tools are separate/);assert.match(c.image.reason,/Retained H034 generation and fresh native child generation passed/);assert.match(c.image.reason,/qualification remains incomplete/);assert.doesNotMatch(c.image.reason,/malformed MCP|acceptance pending/);assert.match(c.nativeDelegation.reason,/H034 actual fresh native child image generation passed/);
});
