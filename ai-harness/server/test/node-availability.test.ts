import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createServer } from "node:http";
import { validateAction } from "../src/node-contract.js";
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
      hardware_latched_boot_id: null,
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
    state: "unknown",
    reason: "readiness_unknown",
    dispatch: "hold",
  });
  await observer.poll();
  assert.deepEqual(observer.states(), {
    qwenGpu0: "available",
    qwenGpu1: "available",
    image: "available",
  });
  assert.deepEqual(observer.get("qwen3.8-27b-gpu0"), {
    state: "available",
    dispatch: "allow",
  });
  assert.deepEqual(observer.get("image"), {
    state: "available",
    dispatch: "allow",
  });
  assert.equal(statusCalls, 1);
  observer.stop();
});

test("positive hardware latch survives late same-boot readiness and a restarted observer", async () => {
  const f = fixture();
  const latched = healthy();
  latched.services[0].hardware_latched = true;
  latched.services[0].hardware_latched_boot_id = "boot-a";
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
    dispatch: "reject",
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

test("new boot requires fresh authoritative target validation with unchanged exact UUIDs", async () => {
  const f = fixture();
  const latched = healthy();
  latched.services[0].hardware_latched = true;
  latched.services[0].hardware_latched_boot_id = "boot-a";
  f.set(latched);
  await f.observer.poll();
  for (const alter of [
    (node: ReturnType<typeof healthy>) => {
      node.boot_id = null;
    },
    (node: ReturnType<typeof healthy>) => {
      node.boot_id = "boot-a";
    },
    (node: ReturnType<typeof healthy>) => {
      node.services[0].state = "unknown";
    },
    (node: ReturnType<typeof healthy>) => {
      node.services[0].freshness = "stale";
    },
    (node: ReturnType<typeof healthy>) => {
      node.services[0].age_ms = 15000;
    },
    (node: ReturnType<typeof healthy>) => {
      node.services[0].observed_at = null;
    },
    (node: ReturnType<typeof healthy>) => {
      node.services[0].hardware_latched = null;
    },
    (node: ReturnType<typeof healthy>) => {
      node.services[0].required_gpu_uuids = [];
    },
    (node: ReturnType<typeof healthy>) => {
      node.services[0].required_gpu_uuids = node.services[1].required_gpu_uuids;
    },
    (node: ReturnType<typeof healthy>) => {
      node.services[0].required_gpu_uuids.push(
        node.services[1].required_gpu_uuids[0],
      );
    },
    (node: ReturnType<typeof healthy>) => {
      node.services[0].required_gpu_uuids.push(uuid);
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

test("authoritative positive target recovery clears a prior-boot latch despite unrelated global inventory failure", async () => {
  const f = fixture();
  const inherited = healthy("boot-b");
  inherited.services[0].hardware_latched = true;
  inherited.services[0].hardware_latched_boot_id = "boot-a";
  Object.assign(inherited.inventory, {
    state: "error",
    freshness: "unknown",
    complete: false,
    observed_at: null,
    age_ms: null,
    observation_id: null,
    gpu_uuids: [],
  });
  f.set(inherited);
  await f.observer.poll();
  assert.equal(f.observer.get("qwen3.8-27b-gpu0").dispatch, "reject");
  const validated = structuredClone(inherited);
  validated.services[0].hardware_latched = false;
  validated.services[0].hardware_latched_boot_id = null;
  f.set(validated);
  await f.observer.poll();
  assert.equal(f.observer.get("qwen3.8-27b-gpu0").dispatch, "allow");
  assert.deepEqual(f.ledger(), {});
  assert.equal(f.observer.snapshot().value?.inventory.complete, false);
  f.observer.stop();
});

test("target validation cannot clear a retained latch without an originating or observed boot", async () => {
  for (const observedBootId of [undefined, null]) {
    const observer = new NodeAvailability({
      backend: { status: async () => healthy("boot-b") },
      initialLatches: {
        "qwen-gpu0": { bootId: null, observedBootId, requiredGpuUuids: [uuid] },
      },
      onLatch: () => assert.fail("missing boot provenance must not clear"),
    });
    await observer.poll();
    assert.equal(observer.get("qwen3.8-27b-gpu0").dispatch, "reject");
    observer.stop();
  }
});

test("readiness unknown or stale gates only new admission and never writes a hardware latch", async () => {
  const f = fixture();
  await f.observer.poll();
  f.advance(15000);
  assert.equal(f.observer.states().qwenGpu0, "unknown");
  assert.deepEqual(f.observer.get("qwen3.8-27b-gpu0"), {
    state: "unknown",
    reason: "readiness_unknown",
    dispatch: "hold",
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

test("targeted new-boot recovery and passive fallback never settle an ambiguous gateway request or replay it", async (t) => {
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
  let telemetryFailed = false;
  let node = healthy();
  const observer = new NodeAvailability({
    backend: {
      status: async () => {
        if (telemetryFailed) throw Error("fixture telemetry outage");
        return node;
      },
    },
    readiness: {
      "qwen-gpu0": async () => ({ ready: true }),
      "qwen-gpu1": async () => ({ ready: true }),
    },
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
  node.services[0].hardware_latched = true;
  node.services[0].hardware_latched_boot_id = "boot-a";
  await observer.poll();
  assert.equal(gateway.snapshot().lanes[0]!.availability.dispatch, "reject");
  node = healthy("boot-b");
  Object.assign(node.inventory, {
    state: "error",
    freshness: "unknown",
    complete: false,
    observed_at: null,
    age_ms: null,
    observation_id: null,
    gpu_uuids: [],
  });
  await observer.poll();
  assert.equal(gateway.snapshot().lanes[0]!.availability.state, "available");
  assert.equal(gateway.snapshot().lanes[0]!.state, "quarantined");
  telemetryFailed = true;
  await observer.poll();
  assert.equal(observer.states().qwenGpu1, "unknown");
  assert.equal((await send()).statusCode, 200);
  assert.deepEqual(seen, ["qwen3.8-27b-gpu0", "qwen3.8-27b"]);
  assert.deepEqual(writes, [
    { "qwen-gpu0": { bootId: "boot-a", requiredGpuUuids: [uuid] } },
    {},
  ]);
});

test("passive backend fallback permits telemetry-only outage while preserving unknown public state and hardware latch", async () => {
  let node = healthy();
  let failed = false;
  let reads = 0;
  const observer = new NodeAvailability({
    backend: {
      status: async () => {
        if (failed) throw Error("telemetry outage");
        return node;
      },
    },
    readiness: {
      "qwen-gpu0": async () => {
        reads++;
        return { ready: true };
      },
      image: async () => ({ ready: false }),
    },
    onLatch: () => {},
  });
  await observer.poll();
  assert.equal(reads, 0);
  failed = true;
  await observer.poll();
  assert.deepEqual(observer.get("qwen3.8-27b-gpu0"), {
    state: "unknown",
    reason: "passive_backend_ready",
    dispatch: "allow",
  });
  assert.equal(observer.states().qwenGpu0, "unknown");
  assert.equal(observer.get("image").dispatch, "hold");
  failed = false;
  node = healthy();
  node.services[0].availability = "unavailable";
  await observer.poll();
  failed = true;
  await observer.poll();
  assert.equal(observer.get("qwen3.8-27b-gpu0").dispatch, "hold");
  assert.equal(observer.states().qwenGpu0, "unknown");
  failed = false;
  node = healthy();
  node.services[0].hardware_latched = true;
  node.services[0].hardware_latched_boot_id = "boot-a";
  await observer.poll();
  failed = true;
  await observer.poll();
  assert.equal(observer.get("qwen3.8-27b-gpu0").dispatch, "reject");
  observer.stop();
});

test("independent hung backend readiness probes remain capped and cannot invent admission or hardware absence", async () => {
  let calls = 0;
  const observer = new NodeAvailability({
    backend: {
      status: async () => {
        throw Error("telemetry outage");
      },
    },
    readiness: {
      image: () => {
        calls++;
        return new Promise(() => {});
      },
    },
    onLatch: () => assert.fail("unknown must not latch"),
    deadlineMs: 5,
  });
  await observer.poll();
  await observer.poll();
  assert.equal(calls, 1);
  assert.deepEqual(observer.get("image"), {
    state: "unknown",
    reason: "readiness_unknown",
    dispatch: "hold",
  });
  observer.stop();
});

test("inherited latch keeps authoritative origin across reboot and clears only after validation of the new boot", async () => {
  const f = fixture();
  const initial = healthy("boot-a");
  initial.services[0].hardware_latched = true;
  initial.services[0].hardware_latched_boot_id = "boot-a";
  f.set(initial);
  await f.observer.poll();
  const inherited = healthy("boot-b");
  inherited.services[0].hardware_latched = true;
  inherited.services[0].hardware_latched_boot_id = "boot-a";
  f.set(inherited);
  await f.observer.poll();
  assert.equal(f.ledger()["qwen-gpu0"]?.bootId, "boot-a");
  assert.equal(f.observer.get("qwen3.8-27b-gpu0").dispatch, "reject");
  f.set(healthy("boot-b"));
  await f.observer.poll();
  assert.equal(f.observer.get("qwen3.8-27b-gpu0").dispatch, "allow");
  const faultedNow = healthy("boot-b");
  faultedNow.services[0].hardware_latched = true;
  faultedNow.services[0].hardware_latched_boot_id = "boot-b";
  f.set(faultedNow);
  await f.observer.poll();
  f.set(healthy("boot-b"));
  await f.observer.poll();
  assert.equal(f.ledger()["qwen-gpu0"]?.bootId, "boot-b");
  assert.equal(f.observer.get("qwen3.8-27b-gpu0").dispatch, "reject");
  f.observer.stop();
});

test("unknown latch origin is not relabeled current boot and cannot clear on same-boot late success", async () => {
  const f = fixture();
  const unknownOrigin = healthy("boot-b");
  unknownOrigin.services[0].hardware_latched = true;
  unknownOrigin.services[0].hardware_latched_boot_id = null;
  f.set(unknownOrigin);
  await f.observer.poll();
  assert.deepEqual(f.ledger()["qwen-gpu0"], {
    bootId: null,
    observedBootId: "boot-b",
    requiredGpuUuids: [uuid],
  });
  f.set(healthy("boot-b"));
  await f.observer.poll();
  assert.equal(f.observer.get("qwen3.8-27b-gpu0").dispatch, "reject");
  const inheritedUnknown = healthy("boot-c");
  inheritedUnknown.services[0].hardware_latched = true;
  inheritedUnknown.services[0].hardware_latched_boot_id = null;
  f.set(inheritedUnknown);
  await f.observer.poll();
  assert.equal(f.ledger()["qwen-gpu0"]?.observedBootId, "boot-b");
  assert.equal(f.observer.get("qwen3.8-27b-gpu0").dispatch, "reject");
  f.set(healthy("boot-c"));
  await f.observer.poll();
  assert.equal(f.observer.get("qwen3.8-27b-gpu0").dispatch, "allow");
  f.observer.stop();
});

test("canonical Flash node-status observation/latch is passive and isolated from Qwen", async () => {
  const f = fixture();
  await f.observer.poll();
  assert.equal(f.observer.get("glm-5.3-flash").dispatch, "hold");
  const node = healthy();
  const flash = {
    ...structuredClone(node.services[0]),
    service_id: "glm-5.3-flash",
  };
  node.services.push(flash);
  f.set(node);
  await f.observer.poll();
  assert.equal(f.observer.get("glm-5.3-flash").dispatch, "allow");
  flash.ready = false;
  f.set(structuredClone(node));
  await f.observer.poll();
  assert.equal(f.observer.get("glm-5.3-flash").dispatch, "hold");
  assert.equal(f.observer.get("qwen3.8-27b").dispatch, "allow");
  flash.hardware_latched = true;
  flash.hardware_latched_boot_id = "boot-a";
  f.set(structuredClone(node));
  await f.observer.poll();
  assert.equal(f.observer.get("glm-5.3-flash").dispatch, "reject");
  assert.equal(f.ledger()["glm-5.3-flash"]?.bootId, "boot-a");
  flash.ready = true;
  flash.hardware_latched = false;
  f.set(structuredClone(node));
  await f.observer.poll();
  assert.equal(f.observer.get("glm-5.3-flash").dispatch, "reject");
  assert.equal(f.observer.get("qwen3.8-27b").dispatch, "allow");
  f.observer.stop();
});

test("passive canonical Flash recognition grants no service lifecycle action", () => {
  assert.throws(() =>
    validateAction({
      schema_version: 1,
      node_id: "ai-vm",
      action: "service.restart",
      service_id: "glm-5.3-flash",
      idempotency_key: "fixture-key-123456",
      expected_boot_id: "boot-a",
      expected_generation: 1,
      allow_interrupt: false,
    }),
  );
});
