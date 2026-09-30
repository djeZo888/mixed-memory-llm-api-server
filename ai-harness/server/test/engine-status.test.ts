import assert from "node:assert/strict";
import test from "node:test";
import { createServer } from "node:http";
import { loadSystemRegistry, validateSystemRegistry } from "../src/system-registry.js";
import { projectEngines, sanitizeEngineHealth, appHealthObserver } from "../src/engine-status.js";
import { createStatusService } from "../src/status-service.js";
const health = () => ({ status: "ok", engines: {
  default: "minimax",
  minimax: { available: true, configured: true, version: null, preview: false, readiness: "not-probed", protocolQualified: null, capabilities: { text: true }, capabilityDetails: {} },
  codex: { available: true, configured: true, version: "0.158.0", preview: true, readiness: "not-probed", protocolQualified: true, imageToolEnabled: false,
    capabilities: { text: true, media: false, frontier: false },
    capabilityDetails: { coding: { supported: true, qualification: "live", reason: "Fixture claims only" }, nativeMedia: { supported: false, qualification: "not_tested", reason: "Not qualified" } },
  },
} });
const registry = () => loadSystemRegistry();
const harness = () => registry().services.find(s => s.id === "harness")!;

test("engine catalog is descriptive, bounded and confined to existing harness owner", () => {
  const r = registry();
  assert.deepEqual(harness().engines!.map(e => e.id), ["minimax", "codex"]);
  const old = structuredClone(r); delete old.services.find(s => s.id === "harness")!.engines; delete old.services.find(s => s.id === "harness")!.engine_health;
  assert.deepEqual(validateSystemRegistry(old), old); // deployed older registry still accepted
  for (const mutate of [
    (r: any) => r.services[0].engines = harness().engines,
    (r: any) => r.services.find((s: any) => s.id === "harness").engines.push(harness().engines![0]),
    (r: any) => r.services.find((s: any) => s.id === "harness").engines[0].url = "http://other/",
    (r: any) => r.services.find((s: any) => s.id === "harness").engines[0].id = "__proto__",
    (r: any) => r.services.find((s: any) => s.id === "harness").engines[0].expected_version = false,
    ...["https://evil/", "8.8.8.8", "169.254.169.254", "localhost", "0.0.0.0"].map(hostname => (r: any) => r.services.find((s: any) => s.id === "harness").engine_health.hostname = hostname),
    (r: any) => r.services.find((s: any) => s.id === "harness").engine_health.host_header = "10.1.2.3\r\nAuthorization: stolen",
    (r: any) => r.services.find((s: any) => s.id === "harness").engine_health.host_header = "8.8.8.8",
    (r: any) => r.services.find((s: any) => s.id === "harness").engine_health.path = "/control/v1/node/status",
    (r: any) => r.services.find((s: any) => s.id === "harness").engine_health.credential = "forbidden",
    (r: any) => r.services.find((s: any) => s.id === "harness").engine_health.port = 65536,
    (r: any) => delete r.services.find((s: any) => s.id === "harness").engine_health,
  ]) { const invalid = registry(); mutate(invalid); assert.throws(() => validateSystemRegistry(invalid)); }
});

test("actual health fields remain configuration evidence, with nullable MiniMax version and no startup readiness", () => {
  const raw: any = health(); raw.secret = "DO_NOT_EXPOSE"; raw.engines.codex.secret = "DO_NOT_EXPOSE";
  raw.engines.codex.capabilityDetails.secret = { reason: "DO_NOT_EXPOSE" };
  raw.engines.codex.readiness = "ready"; // not in the verified passive contract
  const value = sanitizeEngineHealth(raw, "2026-09-28T07:00:00Z");
  const rows = projectEngines(harness(), { state: "fresh", value, ageMs: 0, observedAt: 0, inflight: false, error: null });
  assert.equal(rows[0]!.observed!.version, null); assert.equal(rows[0]!.selection_enabled, true);
  assert.equal(rows[1]!.version_status, "matched"); assert.equal(rows[1]!.observed!.readiness, "unknown");
  assert.ok(rows.every(e => e.ready === null && e.actions.length === 0));
  assert.equal(rows[1]!.observed!.version_evidence, "app-deployment-policy");
  assert.equal(rows[1]!.observed!.capabilities.coding.qualification, "live");
  assert.ok(!JSON.stringify(rows).includes("DO_NOT_EXPOSE"));
});

test("missing, malformed, disabled and mismatching observations retain catalog without invented enabled state", () => {
  const raw: any = health(); delete raw.engines.minimax; raw.engines.codex.version = "9.9.9";
  let value = sanitizeEngineHealth(raw);
  const sample = () => ({ state: "fresh" as const, value, ageMs: 0, observedAt: 0, inflight: false, error: null });
  let rows = projectEngines(harness(), sample());
  assert.equal(rows[0]!.state, "missing"); assert.equal(rows[0]!.selection_enabled, null);
  assert.equal(rows[1]!.state, "mismatch"); assert.equal(rows[1]!.selection_enabled, false);
  assert.equal(rows[1]!.observed!.enabled, true); // retained evidence is explicitly separate
  raw.engines.codex.version = "0.158.0"; raw.engines.codex.available = false; raw.engines.codex.readiness = "disabled";
  value = sanitizeEngineHealth(raw); rows = projectEngines(harness(), sample());
  assert.equal(rows[1]!.selection_enabled, false); assert.equal(rows[1]!.observed!.readiness, "disabled");
  raw.engines.codex.available = "true"; raw.engines.codex.protocolQualified = "true";
  value = sanitizeEngineHealth(raw); rows = projectEngines(harness(), sample());
  assert.equal(rows[1]!.selection_enabled, null); assert.equal(rows[1]!.protocol_qualified, null);
  assert.throws(() => sanitizeEngineHealth({ status: "ok" }));
  assert.throws(() => sanitizeEngineHealth({ ...health(), status: "failed" }));
});

test("status engine freshness is independent from failed model/node observers and suppresses stale enablement", async () => {
  let now = 0, fail = false;
  const service = createStatusService({ registry: registry(), backends: {}, autoPoll: false, now: () => now,
    engineHealth: { status: async () => { if (fail) throw Error("private transport error"); return health(); } } });
  try {
    await service.engineCache!.poll();
    let nodes = service.snapshot(), rows = nodes.find(n => n.node_id === "ai-harness")!.engines;
    assert.equal(nodes[0]!.services[0]!.ready, null); assert.equal(rows[1]!.selection_enabled, true);
    assert.equal(rows[1]!.freshness, "fresh");
    now = 15000; rows = service.snapshot()[1]!.engines;
    assert.equal(rows[1]!.state, "stale"); assert.equal(rows[1]!.selection_enabled, null);
    assert.equal(rows[1]!.observed!.enabled, true); assert.equal(rows[1]!.default_engine, null);
    now = 15001; await service.engineCache!.poll(); fail = true; await service.engineCache!.poll();
    rows = service.snapshot()[1]!.engines;
    assert.equal(rows[1]!.state, "unavailable"); assert.equal(rows[1]!.freshness, "stale");
    assert.equal(rows[1]!.reason, "transport_error"); assert.equal(rows[1]!.selection_enabled, null);
    const response = await service.app.inject({ url: "/api/status/v1/system", headers: { host: "10.156.100.61" } });
    assert.equal(response.statusCode, 200); assert.ok(!response.body.includes("private transport error"));
    const targets = await service.app.inject({ url: "/api/admin/v1/targets", headers: { host: "10.156.100.61" } });
    assert.deepEqual(targets.json().targets, []);
  } finally { await service.app.close(); }
});

test("unavailable and hung app retain catalog; timeout does not spawn replacement observations", async () => {
  let calls = 0;
  const service = createStatusService({ registry: registry(), backends: {}, autoPoll: false, deadlineMs: 10,
    engineHealth: { status: async () => { calls++; return new Promise(() => {}); } } });
  try {
    assert.ok(service.snapshot()[1]!.engines.every(e => e.state === "unavailable" && e.freshness === "unknown"));
    await service.engineCache!.poll(); await service.engineCache!.poll();
    assert.equal(calls, 1); assert.equal(service.snapshot()[1]!.engines[0]!.reason, "timeout");
  } finally { await service.app.close(); }
});

test("configured passive health adapter uses one bounded local GET, no redirects, credentials or retries", async () => {
  let mode = "ok", calls = 0;
  const mock = createServer((req, res) => {
    calls++; assert.equal(req.url, "/api/health"); assert.equal(req.method, "GET"); assert.equal(req.headers.authorization, undefined); assert.equal(req.headers.host, "10.20.30.40:9999");
    if (mode === "redirect") { res.writeHead(302, { Location: "/forbidden" }); res.end(); }
    else if (mode === "oversize") res.end("x".repeat(65537));
    else if (mode === "badjson") res.end("{");
    else if (mode === "failure") { res.writeHead(503); res.end("private failure"); }
    else res.end(JSON.stringify(health()));
  });
  await new Promise<void>((resolve, reject) => { mock.on("error", reject); mock.listen(0, "127.0.0.1", resolve); });
  try {
    const configured = registry(); configured.services.find(s => s.id === "harness")!.engine_health = { hostname: "127.0.0.1", port: (mock.address() as { port: number }).port, host_header: "10.20.30.40:9999", path: "/api/health" };
    const observer = appHealthObserver(configured);
    assert.deepEqual(await observer.status(AbortSignal.timeout(1000)), health());
    for (mode of ["redirect", "oversize", "badjson", "failure"]) await assert.rejects(observer.status(AbortSignal.timeout(1000)), /Application health unavailable/);
    assert.equal(calls, 5);
    const r = registry(); delete r.services.find(s => s.id === "harness")!.engines; delete r.services.find(s => s.id === "harness")!.engine_health;
    assert.throws(() => appHealthObserver(r));
  } finally { await new Promise<void>(resolve => mock.close(() => resolve())); }
});

test("actual app health additive descriptors expose selection policy without starting either native engine", async () => {
  const { mkdtemp, rm } = await import("node:fs/promises");
  const { tmpdir } = await import("node:os");
  const { createApp } = await import("../src/app.js");
  const dataDir = await mkdtemp(`${tmpdir()}/h021-health-`);
  let starts = 0;
  const service = await createApp({ newChatEngine: "minimax", dataDir, engineFactory: () => { starts++; throw Error("No native startup allowed"); } });
  try {
    const response = await service.app.inject({ url: "/api/health", headers: { host: "127.0.0.1:8080" } });
    assert.equal(response.statusCode, 200);
    const raw = response.json(), value = sanitizeEngineHealth(raw);
    assert.equal(raw.engines.default, "minimax");
    assert.equal(value.engines.minimax!.enabled, true);
    assert.equal(value.engines.minimax!.version, null);
    assert.equal(value.engines.minimax!.protocol_qualified, null);
    assert.equal(value.engines.minimax!.readiness, "not-probed");
    assert.equal(value.engines.codex!.enabled, false);
    assert.equal(raw.engines.codex.versionSource, "deployment-policy");
    assert.equal(starts, 0);
  } finally { await service.app.close(); await rm(dataDir, { recursive: true, force: true }); }
});
