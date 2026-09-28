import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {validateCapacity,assertAdmission,preflight,PROFILE_SHA256,ADMIT_UTC,SETTLE_UTC} from './preflight.mjs';
import {sha} from './guards.mjs';
test('final capacity uses existing actual receipt without conflating occupied input',()=>{
 for(const context of [1000192,1000000,950000,917504]) {
  const validated={qualification:{identity:{actualSlotContext:context,maxOutputTokens:65536}},capacity:{configured:context,allocated:context,occupiedTested:65536}};
  assert.equal(validateCapacity({},validated),context);
  for(const key of ['configured','allocated']) assert.throws(()=>validateCapacity({}, {...validated,capacity:{...validated.capacity,[key]:context-1}}));
  assert.throws(()=>validateCapacity({}, {...validated,capacity:{...validated.capacity,occupiedTested:context}}));
  assert.throws(()=>validateCapacity({}, {...validated,qualification:{identity:{actualSlotContext:131072,maxOutputTokens:65536}}}));
 }
});
test('preflight refuses outside its independent Linux systemd owner before file or host contact',async()=>{
 await assert.rejects(preflight({},'/absent'),process.platform==='linux'?/independent Linux systemd owner required/:/linux/);
});
test('admission boundary and exact profile source pin',()=>{
 assert.equal(ADMIT_UTC,'2026-09-28T01:09:30Z');
 assert.equal(SETTLE_UTC,'2026-09-28T01:24:30Z');
 assertAdmission(Date.parse(ADMIT_UTC));assert.throws(()=>assertAdmission(Date.parse(ADMIT_UTC)+1));
 assert.equal(Date.parse(SETTLE_UTC)-Date.parse(ADMIT_UTC),900000);
 assert.equal(sha(readFileSync(new URL('../../../ai-harness/deploy/engine/configure-profile.mjs',import.meta.url))),PROFILE_SHA256);
});
