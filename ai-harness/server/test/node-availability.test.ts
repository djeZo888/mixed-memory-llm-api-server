import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createServer } from "node:http";
import { createGateway, type Gateway } from "../src/gateway.js";
import { setTimeout as delay } from "node:timers/promises";
import {
  NodeAvailability,
  type HardwareLatchLedger,
} from "../src/node-availability.js";

// Worker1 root-frozen v1 fixture, copied without schema edits; see fixture README.
const canonical = JSON.parse(
  readFileSync(
    new URL("./fixtures/h005/node-status-v1.json", import.meta.url),
    "utf8",
  ),
);
const uuid = canonical.services[0].required_gpu_uuids[0] as string;
const stamp = "2026-09-25T18:00:00.000Z";
const fresh = {
  state: "ok",
  observed_at: stamp,
  age_ms: 0,
  freshness: "fresh",
  reason: null,
};
function healthy(boot = "boot-a") {
  const node = structuredClone(canonical);
  Object.assign(node, fresh, { boot_id: boot, generation: 1 });
  for (const service of node.services)
    Object.assign(service, fresh, {
      generation: 1,
      availability: "available",
      ready: true,
      admitting: true,
      hardware_latched: false,
    });
  Object.assign(node.inventory, fresh, {
    boot_id: boot,
    complete: true,
    observation_id: "observation-1",
    gpu_uuids: node.services.flatMap(
      (service: { required_gpu_uuids: string[] }) => service.required_gpu_uuids,
    ),
    hardware_faults: {},
  });
  return node;
}
function fixture() {
  let value = healthy();
  let clock = 0;
  let ledger: HardwareLatchLedger = {};
  const writes: HardwareLatchLedger[] = [];
  const observer = new NodeAvailability({
    backend: { status: async () => value },
    onLatch: (next) => {
      ledger = structuredClone(next);
      writes.push(next);
    },
    now: () => clock,
  });
  return {
    observer,
    writes,
    ledger: () => ledger,
    set: (next: unknown) => {
      value = next;
    },
    advance: (ms: number) => {
      clock += ms;
    },
  };
}

test("direct passive backend independently exposes healthy lane aliases and no status daemon dependency", async () => {
  let statusCalls = 0;
  const observer = new NodeAvailability({
    backend: {
      status: async () => {
        statusCalls++;
        return healthy();
      },
    },
    onLatch: () => {},
  });
  assert.deepEqual(observer.get("qwen3.8-27b"), {
    state: "unavailable",
    reason: "readiness_unknown",
  });
  await observer.poll();
  assert.deepEqual(observer.states(), {
    qwenGpu0: "available",
    qwenGpu1: "available",
    image: "available",
  });
  assert.deepEqual(observer.get("qwen3.8-27b-gpu0"), { state: "available" });
  assert.deepEqual(observer.get("image"), { state: "available" });
  assert.equal(statusCalls, 1);
  observer.stop();
});

test("positive hardware latch survives late same-boot readiness and a restarted observer", async () => {
  const f = fixture();
  const latched = healthy();
  latched.services[0].hardware_latched = true;
  latched.services[0].availability = "unavailable";
  f.set(latched);
  await f.observer.poll();
  assert.deepEqual(f.ledger(), {
    "qwen-gpu0": { bootId: "boot-a", requiredGpuUuids: [uuid] },
  });
  f.set(healthy());
  await f.observer.poll();
  assert.deepEqual(f.observer.get("qwen3.8-27b-gpu0"), {
    state: "unavailable",
    reason: "hardware_latched",
  });
  assert.equal(f.observer.get("qwen3.8-27b").state, "available");
  assert.equal(f.writes.length, 1);
  f.observer.stop();
  const recovered = new NodeAvailability({
    backend: { status: async () => healthy() },
    initialLatches: f.ledger(),
    onLatch: () => assert.fail("same boot must not clear"),
  });
  await recovered.poll();
  assert.equal(recovered.get("qwen3.8-27b-gpu0").reason, "hardware_latched");
  recovered.stop();
});

test("new boot needs complete fresh valid inventory without target faults before clearing retained latch", async () => {
  const f = fixture();
  const latched = healthy();
  latched.services[0].hardware_latched = true;
  f.set(latched);
  await f.observer.poll();
  for (const alter of [
    (node: ReturnType<typeof healthy>) => {
      node.boot_id = null;
    },
    (node: ReturnType<typeof healthy>) => {
      node.inventory.complete = false;
    },
    (node: ReturnType<typeof healthy>) => {
      node.inventory.freshness = "stale";
    },
    (node: ReturnType<typeof healthy>) => {
      node.inventory.age_ms = 15000;
    },
    (node: ReturnType<typeof healthy>) => {
      node.inventory.boot_id = "boot-a";
    },
    (node: ReturnType<typeof healthy>) => {
      node.inventory.gpu_uuids = [];
    },
    (node: ReturnType<typeof healthy>) => {
      node.inventory.gpu_uuids.push(uuid);
    },
    (node: ReturnType<typeof healthy>) => {
      node.inventory.hardware_faults[uuid] = "hardware_fault";
    },
    (node: ReturnType<typeof healthy>) => {
      node.inventory.hardware_faults = null;
    },
    (node: ReturnType<typeof healthy>) => {
      node.inventory.gpu_uuids.push("invalid-inventory-identity");
    },
    (node: ReturnType<typeof healthy>) => {
      node.services[0].hardware_latched = null;
    },
  ]) {
    const next = healthy("boot-b");
    alter(next);
    f.set(next);
    await f.observer.poll();
    assert.equal(f.observer.get("qwen3.8-27b-gpu0").reason, "hardware_latched");
  }
  f.set(healthy("boot-b"));
  await f.observer.poll();
  assert.equal(f.observer.get("qwen3.8-27b-gpu0").state, "available");
  assert.deepEqual(f.ledger(), {});
  f.observer.stop();
});

test("readiness unknown or stale gates only new admission and never writes a hardware latch", async () => {
  const f = fixture();
  await f.observer.poll();
  f.advance(15000);
  assert.equal(f.observer.states().qwenGpu0, "unknown");
  assert.deepEqual(f.observer.get("qwen3.8-27b-gpu0"), {
    state: "unavailable",
    reason: "readiness_unknown",
  });
  const partial = healthy();
  partial.services[0].ready = null;
  f.set(partial);
  await f.observer.poll();
  assert.equal(f.observer.states().qwenGpu0, "unknown");
  assert.equal(f.observer.states().qwenGpu1, "available");
  const cached = healthy();
  cached.services[0].age_ms = 14000;
  f.set(cached);
  await f.observer.poll();
  f.advance(1000);
  assert.equal(f.observer.states().qwenGpu0, "unknown");
  assert.equal(f.observer.states().qwenGpu1, "available");
  assert.deepEqual(f.writes, []);
  f.observer.stop();
});

test("backend transport error reports unknown while retaining a persisted hardware latch", async () => {
  const observer = new NodeAvailability({
    backend: {
      status: async () => {
        throw Error("private fixture network detail");
      },
    },
    initialLatches: {
      "qwen-gpu0": { bootId: "boot-a", requiredGpuUuids: [uuid] },
    },
    onLatch: () => assert.fail("transport failure cannot change latch"),
  });
  await observer.poll();
  assert.deepEqual(observer.states(), {
    qwenGpu0: "unavailable",
    qwenGpu1: "unknown",
    image: "unknown",
  });
  assert.ok(!JSON.stringify(observer.states()).includes("private"));
  assert.equal(observer.get("qwen3.8-27b").reason, "readiness_unknown");
  observer.stop();
});

test("durable clear failure keeps the previous latch and permits recovery only after a committed validation", async () => {
  let fail = true;
  const observer = new NodeAvailability({
    backend: { status: async () => healthy("boot-b") },
    initialLatches: {
      "qwen-gpu0": { bootId: "boot-a", requiredGpuUuids: [uuid] },
    },
    onLatch: () => {
      if (fail) throw Error("fixture ledger unavailable");
    },
  });
  await observer.poll();
  assert.equal(observer.get("qwen3.8-27b-gpu0").reason, "hardware_latched");
  assert.equal(observer.get("image").reason, "availability_ledger_unavailable");
  fail = false;
  await observer.poll();
  assert.equal(observer.get("qwen3.8-27b-gpu0").state, "available");
  observer.stop();
});

test("poll ticks publish expiry while a deadline-exceeding observer keeps one capped hung slot", async () => {
  let calls = 0,
    changed = 0;
  let release!: (value: unknown) => void;
  const pending = new Promise<unknown>((resolve) => {
    release = resolve;
  });
  const observer = new NodeAvailability({
    backend: {
      status: () => {
        calls++;
        return pending;
      },
    },
    onLatch: () => assert.fail("timeout is not missing hardware"),
    changed: () => {
      changed++;
    },
    deadlineMs: 10,
    pollMs: 10,
  });
  observer.start();
  await delay(65);
  assert.equal(calls, 1);
  assert.ok(changed >= 4);
  assert.equal(observer.snapshot().error, "timeout");
  assert.equal(observer.states().image, "unknown");
  observer.stop();
  release(healthy());
  await delay(0);
  assert.equal(observer.states().image, "unknown");
});

test("successful passive snapshots never settle an ambiguous real gateway request or replay it", async (t) => {
  const seen: string[] = [];
  const upstream = createServer(async (request, response) => {
    const chunks: Buffer[] = [];
    for await (const chunk of request) chunks.push(chunk as Buffer);
    seen.push(JSON.parse(Buffer.concat(chunks).toString()).model);
    response.writeHead(seen.length === 1 ? 502 : 200, {
      "content-type": "application/json",
    });
    response.end(
      seen.length === 1
        ? '{"error":{"message":"fixture ambiguous proxy"}}'
        : '{"choices":[]}',
    );
  });
  await new Promise<void>((resolve) =>
    upstream.listen(0, "127.0.0.1", resolve),
  );
  const port = (upstream.address() as { port: number }).port;
  let gateway: Gateway | undefined;
  const writes: HardwareLatchLedger[] = [];
  const observer = new NodeAvailability({
    backend: { status: async () => healthy() },
    onLatch: (value) => {
      writes.push(value);
    },
    changed: () => gateway?.notifyAvailabilityChanged(),
  });
  gateway = createGateway({
    upstreamKey: "synthetic-key",
    availability: observer.get,
    upstreams: [
      { url: `http://127.0.0.1:${port}/v1`, alias: "qwen3.8-27b-gpu0" },
      { url: `http://127.0.0.1:${port}/v1`, alias: "qwen3.8-27b" },
    ],
  });
  t.after(async () => {
    observer.stop();
    await gateway!.close();
    upstream.closeAllConnections();
    await new Promise<void>((resolve) => upstream.close(() => resolve()));
  });
  await observer.poll();
  const token = gateway.issueToken("synthetic-session");
  const send = () =>
    gateway!.app.inject({
      method: "POST",
      url: "/v1/chat/completions",
      headers: { authorization: `Bearer ${token}` },
      payload: { model: "qwen3.8-27b", messages: [] },
    });
  assert.equal((await send()).statusCode, 502);
  assert.equal(gateway.snapshot().lanes[0]!.state, "quarantined");
  await observer.poll();
  assert.equal(gateway.snapshot().lanes[0]!.availability.state, "available");
  assert.equal(gateway.snapshot().lanes[0]!.state, "quarantined");
  assert.equal((await send()).statusCode, 200);
  assert.deepEqual(seen, ["qwen3.8-27b-gpu0", "qwen3.8-27b"]);
  assert.deepEqual(writes, []);
});
