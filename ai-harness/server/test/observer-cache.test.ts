import assert from "node:assert/strict";
import test from "node:test";
import { ObserverCache } from "../src/observer-cache.js";

test("hung observer is capped, deadline does not block healthy peer, late success discarded", async () => {
  let calls = 0,
    release!: (value: string) => void;
  const hung = new ObserverCache<string>(
    () => {
      calls++;
      return new Promise((r) => {
        release = r;
      });
    },
    { deadlineMs: 15 },
  );
  const healthy = new ObserverCache(async () => "healthy", { deadlineMs: 15 });
  await Promise.all([hung.poll(), healthy.poll()]);
  assert.equal(healthy.snapshot().value, "healthy");
  assert.equal(hung.snapshot().error, "timeout");
  await Promise.all(Array.from({ length: 20 }, () => hung.poll()));
  assert.equal(calls, 1);
  assert.equal(hung.snapshot().state, "unknown");
  release("late false certainty");
  await new Promise((r) => setImmediate(r));
  assert.equal(hung.snapshot().value, undefined);
  hung.stop();
  healthy.stop();
});

test("fresh success ages independently, transport errors never invent absence", async () => {
  let now = 0,
    fail = false;
  const cache = new ObserverCache(
    async () => {
      if (fail) throw Error("secret endpoint credential");
      return { available: true };
    },
    { now: () => now },
  );
  await cache.poll();
  assert.equal(cache.snapshot().state, "fresh");
  fail = true;
  now = 5000;
  await cache.poll();
  assert.equal(cache.snapshot().error, "transport_error");
  assert.deepEqual(cache.snapshot().value, { available: true });
  now = 15000;
  assert.equal(cache.snapshot().state, "stale");
  assert.equal(JSON.stringify(cache.snapshot()).includes("secret"), false);
  cache.stop();
});
