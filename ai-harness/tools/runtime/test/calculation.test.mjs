// SPDX-License-Identifier: MIT
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { divider } from './calculation.ts';
test('voltage divider units and limiting cases', () => {
  assert.equal(divider(5, 1000, 1000), 2.5);
  assert.equal(divider(0, 1000, 1000), 0);
  assert.ok(divider(5, 1e9, 1) < 1e-8);
});
test('rejects invalid circuit inputs', () => {
  for (const r of [0, -1, NaN, Infinity]) assert.throws(() => divider(5, r, 1), RangeError);
});
