import assert from "node:assert/strict";
import test from "node:test";
import { loadSystemRegistry, validateSystemRegistry } from "../src/system-registry.js";
import { nodeClient, nodeObserver } from "../src/node-client.js";
import { SERVICE_IDS } from "../src/node-contract.js";

export function thirdNodeRegistry() {
  const r = loadSystemRegistry();
  r.nodes.push({ id: "offline-lab", display_name: "Offline laboratory", observation: { adapter: "unsupported", transport: null } });
  r.services.push({ id: "lab-service", node_id: "offline-lab", display_name: "Expected lab service", observation_key: "lab-service", owner: "unassigned", capabilities: [], endpoint_ref: null });
  return r;
}
test("default registry retains seven action identities and adds passive frontier inventory", () => {
  const r = loadSystemRegistry();
  assert.deepEqual(r.nodes.map(n => [n.id, n.observation.transport]), [["ai-vm", "ai-vm-private"], ["ai-harness", "local-helper"]]);
  for (const [node, ids] of Object.entries(SERVICE_IDS)) assert.deepEqual(r.services.filter(s => s.node_id === node && s.id !== "glm-5.3-flash").map(s => s.id), ids);
  assert.equal(validateSystemRegistry(thirdNodeRegistry()).nodes.length, 3);
  assert.ok(r.components.every(c => c.type === "support" || c.independently_restartable === false));
});
test("malformed, duplicate, unbounded and dangling registry input fails closed", () => {
  const changes: ((r: any) => void)[] = [
    r => r.credentials.push(r.credentials[0]),
    r => r.credentials[0].systemd_credential = "node-other",
    r => r.credentials.push({ id: "lab", systemd_credential: "control-api-key" }),
    r => r.credentials.push({ id: "lab", systemd_credential: "/tmp/node-key" }),
    r => r.credentials.push({ id: "lab", systemd_credential: "node-../control-api-key" }),
    r => r.transports.push(r.transports[0]),
    r => { r.credentials.push({id:"lab",systemd_credential:"node-lab"}); r.transports.push(...["lab1","lab2"].map(id=>({id,kind:"private-http",host:"10.1.2.3",port:30008,socket_path:null,credential_ref:"lab"}))); },
    r => r.transports[0].host = "example.com", r => r.transports[0].host = "0.0.0.0",
    r => r.transports[0].host = "8.8.8.8", r => r.transports[0].port = 0,
    r => r.transports[0].credential_ref = "/tmp/secret", r => r.transports[0].credential_ref = null,
    r => r.nodes[0].observation.transport = "missing",
    r => r.nodes.push(r.nodes[0]), r => r.services.push(r.services[0]),
    r => r.components.push(r.components[0]), r => r.nodes[0].id = "__proto__",
    r => r.nodes[0].observation.url = "http://untrusted/",
    r => r.nodes[0].observation.credential = "secret",
    r => r.nodes[0].observation.transport = "local-helper",
    r => r.nodes[0].observation.adapter = "shell",
    r => r.nodes[0].display_name = null, r => r.schema_version = 2,
    r => r.services[0].node_id = "missing", r => r.services[0].node_id = "ai-harness",
    r => r.services[0].endpoint_ref = "arbitrary-endpoint",
    r => r.services[0].endpoint_ref = ["qwen-gpu0-private"],
    r => r.components[0].type = ["capability"],
    r => r.services[0].observation_key = "qwen-gpu1",
    r => r.components[0].parent_id = "missing",
    r => r.components[0].parent_id = "qwen-gpu0",
    r => r.components[0].parent_id = r.components[0].id,
    r => r.components[0].independently_restartable = true,
    r => r.components[0].observation = { source: "support", key: "nginx" },
    r => r.components.find((c: any) => c.id === "nginx").observation.key = "arbitrary-unit",
    r => r.services = {}, r => r.nodes = [],
    r => r.nodes.push(...Array.from({ length: 16 }, (_, i) => ({ id: `lab-${i}`, display_name: "Lab", observation: { adapter: "unsupported", transport: null } }))),
  ];
  for (const change of changes) { const r = loadSystemRegistry(); change(r); assert.throws(() => validateSystemRegistry(r), /Invalid system registry/); }
});
test("unknown node cannot fall through to local helper; unsupported adapter is passive unknown", async () => {
  assert.throws(() => nodeClient("unexpected" as any), /Unsupported node adapter/);
  const node = thirdNodeRegistry().nodes[2]!;
  const observer = nodeObserver(node, thirdNodeRegistry());
  assert.deepEqual(Object.keys(observer), ["status"]);
  assert.deepEqual(await observer.status(new AbortController().signal), { schema_version: 1, node_id: "offline-lab", reason: "unsupported" });
  assert.throws(() => nodeObserver({ ...node, observation: { adapter: "node-v1", transport: "local-helper" } }, thirdNodeRegistry()), /Unsupported node binding/);
  assert.throws(() => nodeObserver(loadSystemRegistry().nodes[0]!, loadSystemRegistry()), /credential required/);
});

test("generic third-node passive transport reaches only bounded fixed GET; failed peers and absent services remain visible without targets", async () => {
  const { createServer } = await import("node:http");
  const { createStatusService } = await import("../src/status-service.js");
  let mode = "ok", calls = 0;
  const mock = createServer((req, res) => {
    calls++;
    assert.equal(req.method, "GET"); assert.equal(req.url, "/control/v1/node/status");
    assert.equal(req.headers.authorization, "Bearer synthetic-lab-token");
    if (mode === "redirect") { res.writeHead(302, { Location: "/unexpected" }); res.end(); return; }
    if (mode === "oversize") { res.end("x".repeat(512 * 1024 + 1)); return; }
    if (mode === "failed") { res.writeHead(503); res.end('{}'); return; }
    const obs = { state: "ok", freshness: "fresh", age_ms: 0, observed_at: "2026-09-26T10:00:00Z" };
    res.setHeader("content-type", "application/json");
    res.end(JSON.stringify({ schema_version: 1, node_id: "offline-lab", ...obs, boot_id: "lab-boot", generation: 4,
      services: [{ ...obs, service_id: "lab-service", generation: 2, ready: true, availability: "available" }],
      resources: { cpu: { ...obs, percent: 15, logical_count: 8 } } }));
  });
  await new Promise<void>(resolve => mock.listen(0, "127.0.0.1", resolve));
  const registry = thirdNodeRegistry();
  registry.credentials.push({ id: "lab-observation", systemd_credential: "node-lab" });
  registry.transports.push({ id: "lab-status", kind: "private-http", host: "127.0.0.1", port: (mock.address() as { port: number }).port, socket_path: null, credential_ref: "lab-observation" });
  registry.nodes[2]!.observation = { adapter: "node-v1", transport: "lab-status" };
  registry.services.push({ id: "lab-missing", display_name: "Missing lab service", node_id: "offline-lab", observation_key: "missing", owner: "lab owner", capabilities: [], endpoint_ref: null });
  const valid = validateSystemRegistry(registry);
  const observer = nodeObserver(valid.nodes[2]!, valid, { "control-api-key": "synthetic-control", "lab-observation": "synthetic-lab-token" });
  assert.throws(() => nodeObserver(valid.nodes[2]!, valid, { "control-api-key": "synthetic-control" }), /credential required/);
  const stolen = structuredClone(valid); stolen.nodes[2]!.observation.transport = "ai-vm-private";
  assert.throws(() => validateSystemRegistry(stolen), /Invalid system registry/);
  assert.throws(() => nodeObserver(stolen.nodes[2]!, stolen, { "control-api-key": "synthetic-control" }), /credential scope mismatch/);
  const service = createStatusService({ registry: valid, backends: { "offline-lab": observer }, autoPoll: false });
  try {
    await Promise.all(Object.values(service.caches).map(c => c.poll()));
    let lab = service.snapshot()[2]!;
    assert.equal(lab.services[0]!.health, "ready"); assert.equal(lab.resources.cpu!.percent, 15);
    assert.equal(lab.services[1]!.health, "unknown");
    assert.equal(service.snapshot()[0]!.freshness, "unknown");
    const targets = await service.app.inject({ url: "/api/admin/v1/targets", headers: { host: "10.156.100.61" } });
    assert.deepEqual(targets.json().targets, []);
    const result = await service.app.inject({ url: "/api/status/v1/system", headers: { host: "10.156.100.61" } });
    for (const privateValue of ["synthetic-control", "synthetic-lab-token", "credential_ref", "socket_path", "127.0.0.1", "lab-status"])
      assert.ok(!result.body.includes(privateValue));
    mode = "failed"; await service.caches["offline-lab"]!.poll(); lab = service.snapshot()[2]!;
    assert.equal(lab.freshness, "stale"); assert.equal(lab.services[0]!.health, "unknown");
    assert.equal(lab.services[0]!.observed_at, "2026-09-26T10:00:00Z");
    for (const failure of ["redirect", "oversize"]) {
      mode = failure; const before = calls;
      await assert.rejects(observer.status(AbortSignal.timeout(1000)));
      assert.equal(calls, before + 1); // No redirects, replay or second endpoint.
    }
    assert.deepEqual(Object.keys(observer), ["status"]);
  } finally {
    await service.app.close();
    await new Promise<void>((resolve, reject) => mock.close(error => error ? reject(error) : resolve()));
  }
});
