import assert from 'node:assert/strict';
import test from 'node:test';
import { loadPositive } from './load.mjs';
test('results are values in input order even when requests finish in reverse',async()=>{
 const result=await loadPositive([3,1,2],id=>new Promise(resolve=>setTimeout(()=>resolve(id*7),5-id)));
 assert.deepEqual(result,[21,7,14]);assert.deepEqual(await loadPositive([],()=>{throw Error('unexpected')}),[]);
});
test('all invalid IDs are rejected before side effects',async()=>{
 for(const ids of [[1,0],[1,-2],[1,NaN],[1,1.5],['1'],null]) {
   let calls=0;await assert.rejects(loadPositive(ids,async()=>{calls++;return 1}),TypeError);assert.equal(calls,0);
 }
});
test('upstream failure rejects outer promise',async()=>{
 await assert.rejects(loadPositive([1],async()=>{throw Error('fixture failure')}),/fixture failure/);
});
