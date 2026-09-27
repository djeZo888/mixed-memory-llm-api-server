import assert from 'node:assert/strict';
import {clamp} from './edge.mjs';
assert.equal(clamp(5,0,10),5);assert.equal(clamp(-1,0,10),0);
assert.equal(clamp(NaN,0,10),0);assert.equal(clamp(Infinity,0,10),10);
assert.equal(clamp(-Infinity,0,10),0);assert.equal(clamp(5,10,0),5);
assert.equal(clamp(20,10,0),10);assert.equal(clamp(3,3,3),3);
console.log('EDGE_CHECK_PASS');
