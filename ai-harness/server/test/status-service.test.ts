import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { DatabaseSync } from "node:sqlite";
import { AdminActions, type AdminFreeze } from "../src/admin-actions.js";
import { createStatusService } from "../src/status-service.js";
import { sanitizeNode, validateAction } from "../src/node-contract.js";
import type { NodeBackend } from "../src/node-client.js";
const fixture = (name: string) =>
  JSON.parse(
    readFileSync(
      new URL(`./fixtures/h005/${name}.json`, import.meta.url),
      "utf8",
    ),
  );
const obs = {
  state: "ok",
  observed_at: "2026-09-25T16:10:00+00:00",
  age_ms: 0,
  freshness: "fresh",
  reason: null,
};
function vm() {
  const node = fixture("node-status-v1");
  Object.assign(node, obs, {
    boot_id: "37e425eb-3d3e-4070-80a0-5ecfb39604f1",
    generation: 7,
  });
  for (const s of node.services)
    Object.assign(s, obs, {
      generation: 3,
      activity: "idle",
      availability: "available",
      ready: true,
      admitting: true,
      hardware_latched: false,
    });
  node.services[1].availability = "unavailable";
  node.services[1].hardware_latched = true;
  node.resources.cpu = { ...obs, percent: 12, logical_count: 72 };
  node.prompts = "DO_NOT_EXPOSE";
  node.credential = "DO_NOT_EXPOSE";
  node.services[0].last_request = "DO_NOT_EXPOSE";
  return node;
}
const freeze: AdminFreeze = { hold: () => {}, acknowledge: async () => ({}), release: () => {}, settle: async () => {}, inspect: async () => ({ frozen: false, ready: true, activity: "idle", active_requests: 0, queue_depth: 0 }) };
const backend = (value: unknown): NodeBackend => ({
  status: async () => value,
  action: async () => fixture("node-operation-v1"),
  operation: async () => fixture("node-operation-v1"),
});
test("exact shared v1 fixture preserves nullable identities, independent metrics and no invented capability", () => {
  const shared = fixture("node-status-v1"),
    parsed = sanitizeNode(shared, "ai-vm");
  assert.equal(parsed.generation, null);
  assert.equal(parsed.services[0]!.hardware_latched, null);
  assert.deepEqual(parsed.resources, shared.resources);
  assert.equal(parsed.inventory.complete, false);
  assert.deepEqual(
    parsed.services[0]!.required_gpu_uuids,
    shared.services[0].required_gpu_uuids,
  );
  assert.deepEqual(
    validateAction(fixture("node-action-v1")),
    fixture("node-action-v1"),
  );
  assert.throws(() =>
    validateAction({ ...fixture("node-action-v1"), command: "reboot" }),
  );
  assert.throws(() =>
    validateAction({ ...fixture("node-action-v1"), expected_generation: null }),
  );
});
test("status works without chat/storage and one hung node cannot hold peer; sanitizes payloads", async () => {
  const service = createStatusService({
    backends: {
      "ai-vm": backend(vm()),
      "ai-harness": {
        ...backend(null),
        status: async () => new Promise(() => {}),
      },
    },
    autoPoll: false,
    deadlineMs: 15,
  });
  await Promise.all(Object.values(service.caches).map((c) => c.poll()));
  const response = await service.app.inject({
    url: "/api/status/v1/system",
    headers: { host: "10.156.100.61" },
  });
  assert.equal(response.statusCode, 200);
  assert.equal(response.json().nodes[0].services[1].hardware_latched, true);
  assert.equal(response.json().nodes[1].freshness, "unknown");
  assert.equal(response.body.includes("DO_NOT_EXPOSE"), false);
  assert.equal(response.json().nodes[0].resources.cpu.percent, 12);
  assert.equal(
    (
      await service.app.inject({
        url: "/status",
        headers: { host: "status.ai-harness" },
      })
    ).statusCode,
    200,
  );
  assert.equal(
    (
      await service.app.inject({
        url: "/admin",
        headers: { host: "status.ai-harness" },
      })
    ).statusCode,
    403,
  );
  await service.app.close();
});
test("cached successful HTTP cannot refresh aged underlying service; unknown boot disables targets", async () => {
  const stale = vm();
  stale.services[0].age_ms = 16000;
  let now = 0;
  const service = createStatusService({
    backends: {
      "ai-vm": backend(stale),
      "ai-harness": backend({
        ...fixture("node-status-v1"),
        node_id: "ai-harness",
        services: [],
      }),
    },
    autoPoll: false,
    now: () => now,
  });
  await Promise.all(Object.values(service.caches).map((c) => c.poll()));
  assert.equal(service.snapshot()[0]!.services[0]!.freshness, "stale");
  const targets = await service.app.inject({
    url: "/api/admin/v1/targets",
    headers: { host: "10.156.100.61" },
  });
  assert.equal(
    targets.json().targets.some((t: any) => t.service_id === "qwen-gpu0"),
    false,
  );
  assert.equal(
    targets.json().targets.some((t: any) => t.node_id === "ai-harness"),
    false,
  );
  now = 15000;
  assert.equal(service.snapshot()[0]!.freshness, "stale");
  await service.app.close();
});
test("typed async admin relay keeps key/boot/generation, namespaces receipts and does not replay", async () => {
  let calls = 0;
  const accepted: any[] = [];
  const remote = {
    ...backend(vm()),
    action: async (a: any) => {
      calls++;
      accepted.push(a);
      return { ...fixture("node-operation-v1"), action: a.action, service_id: a.service_id ?? null, gpu_uuid: a.gpu_uuid ?? null, expected_boot_id: a.expected_boot_id, expected_generation: a.expected_generation };
    },
  };
  const backends = { "ai-vm": remote, "ai-harness": backend(null) };
  const db = new DatabaseSync(":memory:");
  const actions = new AdminActions({ db, freeze, backends, autoPoll: false });
  const service = createStatusService({
    backends, freeze, actions,
    autoPoll: false,
  });
  const auth = await service.app.inject({
    url: "/api/admin/session",
    headers: { host: "10.156.100.61" },
  });
  const headers = {
    host: "10.156.100.61",
    origin: "http://10.156.100.61",
    "x-csrf-token": auth.json().csrf,
    cookie: String(auth.headers["set-cookie"]).split(";")[0]!,
  };
  const action = { ...fixture("node-action-v1"), action: "service.start", expected_generation: 3 };
  const receipt = await service.app.inject({
    method: "POST",
    url: "/api/admin/v1/actions",
    headers,
    payload: action,
  });
  assert.equal(receipt.statusCode, 202);
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(calls, 1);
  assert.deepEqual(accepted[0], action);
  assert.match(receipt.json().operation_id, /^ai-vm~/);
  assert.ok(Number.isFinite(Date.parse(receipt.json().created_at)));
  assert.equal(
    (
      await service.app.inject({
        url: receipt.json().poll_url,
        headers: { host: "10.156.100.61" },
      })
    ).statusCode,
    200,
  );
  assert.equal(calls, 1);
  assert.equal(
    (
      await service.app.inject({
        method: "POST",
        url: "/api/admin/v1/actions",
        headers,
        payload: { ...action, path: "/bin/sh" },
      })
    ).statusCode,
    400,
  );
  assert.equal(calls, 1);
  assert.equal(
    (
      await service.app.inject({
        method: "POST",
        url: "/api/admin/v1/actions",
        headers,
        payload: { ...action, action: "service.restart" },
      })
    ).statusCode,
    409,
  );
  assert.equal(calls, 1);
  await service.app.close();
});

test("exact additive disk roles retain separate capacities/freshness and unavailable mount never borrows root", async () => {
  const raw = vm(),
    disk = fixture("disk-volumes-v1");
  raw.resources.disk = disk;
  const parsed = sanitizeNode(raw, "ai-vm");
  assert.deepEqual(parsed.resources.disk, disk);
  disk.volumes[2].state = "unavailable";
  disk.volumes[2].reason = "mount_identity_unavailable";
  disk.volumes[1].age_ms = 16000;
  const service = createStatusService({
    backends: { "ai-vm": backend(raw), "ai-harness": backend(null) },
    autoPoll: false,
  });
  await service.caches["ai-vm"].poll();
  const volumes = service.snapshot()[0]!.resources.disk!.volumes!;
  assert.equal(volumes[1]!.freshness, "stale");
  assert.equal(volumes[2]!.total_bytes, null);
  assert.equal(volumes[2]!.available_bytes, null);
  assert.equal(volumes[0]!.total_bytes, 34359738368);
  assert.equal(volumes[2]!.reason, "mount_identity_unavailable");
  await service.app.close();
});

test("registry retains third/unreachable node and missing service rows; support and new services gain no controls", async () => {
  const { loadSystemRegistry } = await import("../src/system-registry.js");
  const registry = loadSystemRegistry();
  registry.nodes.push({ id: "lab", display_name: "Offline lab", observation: { adapter: "unsupported", transport: null } });
  registry.services.push({ id: "lab-job", node_id: "lab", display_name: "Lab job", observation_key: "lab-job", owner: "lab owner", capabilities: [], endpoint_ref: null });
  registry.services.push({ id: "extra", node_id: "ai-harness", display_name: "Extra read-only service", observation_key: "extra", owner: "unknown", capabilities: [], endpoint_ref: null });
  const harness = { ...vm(), node_id: "ai-harness", services: [{ ...obs, service_id: "extra", generation: 3, ready: true }], support: [{ ...obs, component_id: "nginx", active_state: "active", sub_state: "running", generation: 999, actions: ["node.reboot"], ready: true, secret: "DO_NOT_EXPOSE" }] };
  const service = createStatusService({ registry, backends: { "ai-vm": backend({ ...vm(), services: [] }), "ai-harness": backend(harness) }, autoPoll: false });
  try {
    await Promise.all(Object.values(service.caches).map(c => c.poll()));
    const nodes = service.snapshot();
    assert.deepEqual(nodes.map(n => n.node_id), ["ai-vm", "ai-harness", "lab"]);
    assert.equal(nodes[2]!.display_name, "Offline lab");
    assert.equal(nodes[2]!.services[0]!.service_id, "lab-job");
    assert.equal(nodes[2]!.services[0]!.health, "unknown");
    assert.equal(nodes[2]!.resources.cpu!.percent, null);
    assert.equal(nodes[0]!.services.length, 5);
    assert.ok(nodes[0]!.services.every(s => s.freshness === "unknown" && s.ready === null));
    const nginx = nodes[1]!.components.find(c => c.component_id === "nginx")!;
    assert.equal(nginx.current_state, "active/running");
    assert.equal(nginx.health, "unknown"); assert.equal(nginx.ready, null);
    assert.deepEqual(nginx.actions, []);
    assert.equal(nodes[1]!.components.find(c => c.component_id === "gateway")!.health, "unknown");
    const result = await service.app.inject({ url: "/api/admin/v1/targets", headers: { host: "10.156.100.61" } });
    assert.ok(!result.json().targets.some((t: any) => t.node_id === "lab" || ["extra", "nginx", "gateway"].includes(t.service_id)));
    const publicResult = await service.app.inject({ url: "/api/status/v1/system", headers: { host: "10.156.100.61" } });
    assert.equal(publicResult.json().registry_version, 1);
    assert.ok(!publicResult.body.includes("DO_NOT_EXPOSE"));
    assert.ok(!publicResult.body.includes("helper.sock"));
    for (const action of [{ node_id: "lab", service_id: "lab-job" }, { node_id: "ai-harness", service_id: "nginx" }, { node_id: "ai-harness", service_id: "extra" }])
      assert.throws(() => validateAction({ ...fixture("node-action-v1"), ...action }));
  } finally { await service.app.close(); }
});

test("malformed/missing fields stay unknown; explicit model.control and node_manager facts remain informational and age independently", async () => {
  const raw = vm();
  raw.services.find((s: any) => s.service_id === "control").installed_capabilities = ["model.control", "invented"];
  raw.node_manager = { ...obs, running: true, generation: 9, age_ms: 13000, actions: ["service.restart"], secret: "DO_NOT_EXPOSE" };
  raw.resources.memory = { ...obs, total_bytes: "123", available_bytes: -1 };
  raw.resources.network = { freshness: "fresh", rx_bytes_per_second: "42", tx_bytes_per_second: null };
  raw.support = [{ ...obs, component_id: "nginx", active_state: { malicious: true } }];
  let now = 0;
  const service = createStatusService({ backends: { "ai-vm": backend(raw) }, autoPoll: false, now: () => now });
  try {
    await service.caches["ai-vm"]!.poll();
    let node = service.snapshot()[0]!;
    assert.deepEqual(node.services.find(s => s.service_id === "control")!.installed_capabilities, ["model.control"]);
    assert.equal(node.node_manager.running, true); assert.deepEqual(node.node_manager.actions, []);
    assert.equal(node.components.find(c => c.component_id === "node-manager")!.current_state, "running");
    assert.equal(node.components.find(c => c.component_id === "node-manager")!.health, "unknown");
    assert.equal(node.resources.memory!.total_bytes, null); assert.equal(node.resources.memory!.available_bytes, null);
    assert.equal(node.resources.network!.freshness, "unknown"); assert.equal(node.resources.network!.rx_bytes_per_second, null);
    now = 2500; node = service.snapshot()[0]!;
    assert.equal(node.node_manager.age_ms, 15500); assert.equal(node.node_manager.observed_at, obs.observed_at);
    assert.equal(node.node_manager.freshness, "stale");
    assert.equal(node.components.find(c => c.component_id === "node-manager")!.current_state, "unknown");
    assert.equal(node.services[0]!.freshness, "fresh");
    assert.equal(node.resources.cpu!.freshness, "fresh");
  } finally { await service.app.close(); }
});

test("mismatched or duplicate native evidence leaves configured rows visible and unknown", async () => {
  const duplicate = vm(); duplicate.services.push(duplicate.services[0]);
  const service = createStatusService({ backends: { "ai-vm": backend(duplicate), "ai-harness": backend(vm()) }, autoPoll: false });
  try {
    await Promise.all(Object.values(service.caches).map(c => c.poll()));
    for (const node of service.snapshot()) {
      assert.equal(node.freshness, "unknown"); assert.ok(node.services.length > 0);
      assert.ok(node.services.every(s => s.health === "unknown"));
    }
  } finally { await service.app.close(); }
});
