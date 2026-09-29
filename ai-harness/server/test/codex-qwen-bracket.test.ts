import test from "node:test";
import assert from "node:assert/strict";
import { createProductionQwenVerifier, qwenPolicyReceipt } from "../src/codex-production.js";
import { createCodexQwenCounter } from "../src/codex-qwen.js";
import type { QwenAdmissionDiagnostic } from "../src/codex-admission.js";

const alias = "qwen3.8-27b";
const epoch = 1790643600000;
function fixture() {
  const receipt = qwenPolicyReceipt(), p = receipt.lanes[alias];
  let clock = epoch;
  const control: any = { schema_version: 2, slot: p.controlSlot, selected: p.deploymentId,
    observed_deployment: p.deploymentId, desired: "running", observed: "ready", container_running: true,
    observation_available: true, storage_available: true, state_persisted: true, generation_current: true,
    generation: 9, active_identity: "a".repeat(64), freshness: "fresh", observed_at: epoch / 1000,
    mutation_busy: false, current_operation: null,
    endpoint: { base_url: p.nativeBaseUrl, served_model: alias, authentication_required: true, ready: true } };
  const service: any = { service_id: p.serviceId, state: "ok", freshness: "fresh", age_ms: 0,
    observed_at: new Date(epoch).toISOString(), generation: 15, ready: true, hardware_latched: false,
    deployment_id: p.deploymentId, model_alias: alias, configured_context_tokens: 480000,
    required_gpu_uuids: [p.gpuUuid] };
  const node: any = { schema_version: 1, node_id: "ai-vm", boot_id: "11111111-2222-4333-8444-555555555555",
    state: "ok", freshness: "fresh", age_ms: 0, observed_at: new Date(epoch).toISOString(), services: [service] };
  const native: any = { status: "ready", version: "0.5.19", served_model_name: alias,
    context_length: 480000, max_total_tokens: 480000, max_total_num_tokens: 480000, max_running_requests: 1,
    default_chat_template_kwargs: { enable_thinking: false }, tool_call_parser: "qwen3_coder", reasoning_parser: "qwen3" };
  const seen: string[] = [], signals: (AbortSignal | undefined)[] = [], events: QwenAdmissionDiagnostic[] = [];
  let hook: (kind: string, signal?: AbortSignal) => Promise<void> = async () => {};
  const get = async (url: string, _key: string, signal?: AbortSignal) => {
    const kind = url.endsWith("/node/status") ? "node" : url.endsWith("/server_info") ? "native" : "control";
    seen.push(kind); signals.push(signal); await hook(kind, signal);
    return structuredClone(kind === "node" ? node : kind === "native" ? native : control);
  };
  const verify = createProductionQwenVerifier(receipt, { controlKey: "fixture", inferenceKey: "fixture" }, get, () => clock, event => events.push(event));
  return { receipt, control, service, node, native, seen, signals, events, verify, get, now: () => clock,
    advance(ms: number) { clock += ms; }, hook(value: typeof hook) { hook = value; } };
}
const rejectsReason = (reason: string) => (error: any) => error.reason === reason;

test("production count uses two control observations and two native checks; ordinary and legacy verification stay intact", async t => {
  const forwarded: unknown[] = [];
  t.mock.method(globalThis, "fetch", async (_url: Parameters<typeof fetch>[0], init?: RequestInit) => {
    forwarded.push(JSON.parse(String(init?.body)));
    return new Response(JSON.stringify({ tokens: [1, 2], count: 2, max_model_len: 262144 }));
  });
  const body = { model: alias, reasoning_effort: "none", messages: [{ role: "user", content: "count fixture" }],
    tools: [{ type: "function", function: { name: "fixture", parameters: { type: "object" } } }],
    max_tokens: 65536, temperature: 0.25, stream: true, stream_options: { include_usage: true } };
  const lane = { alias, url: "http://127.0.0.1:1/v1" };
  const f = fixture(), signal = new AbortController().signal;
  assert.deepEqual(await createCodexQwenCounter(f.verify)(body, lane, "fixture", signal), { inputTokens: 2, contextWindow: 480000 });
  assert.deepEqual(f.seen, ["control", "node", "native", "native", "control", "node"]);
  assert.ok(f.signals.every(value => value === signal));
  const { stream, stream_options, ...expectedBody } = body;
  assert.deepEqual(forwarded[0], expectedBody);
  f.seen.length = 0;
  await createCodexQwenCounter(async (a, c) => f.verify(a, c))(body, lane, "fixture", signal);
  assert.deepEqual(f.seen, ["control", "node", "native", "control", "node", "control", "node", "native", "control", "node"]);
  f.seen.length = 0;
  await f.verify(alias);
  assert.deepEqual(f.seen, ["control", "node", "native", "control", "node"]);
});

test("operation result remains private until the complete fresh after bracket passes", async () => {
  const f = fixture();
  const result = await f.verify.withVerifiedLane(alias, async qualification => {
    assert.equal(qualification.alias, alias);
    assert.deepEqual(f.seen, ["control", "node", "native"]);
    f.seen.push("tokenize");
    return { count: 42 };
  });
  assert.deepEqual(result, { count: 42 });
  assert.deepEqual(f.seen, ["control", "node", "native", "tokenize", "native", "control", "node"]);
  assert.deepEqual(f.events.map(event => event.step), ["control_before", "node_before", "native", "native", "control_after", "node_after"]);
});

test("boot, active identity, control generation and service generation changes during count each invalidate the result", async () => {
  for (const [target, key, value] of [
    ["node", "boot_id", "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"],
    ["control", "active_identity", "b".repeat(64)],
    ["control", "generation", 10], ["service", "generation", 16],
  ] as const) {
    const f = fixture();
    await assert.rejects(f.verify.withVerifiedLane(alias, async () => {
      f[target][key] = value; return 42;
    }), rejectsReason("identity_changed"));
  }
});

test("selection, storage, owner, hardware and native drift are rejected on both sides of count", async () => {
  for (const [target, key, value, reason] of [
    ["control", "selected", "unreviewed", "selected_profile"],
    ["control", "observed_deployment", "unreviewed", "selected_profile"],
    ["control", "storage_available", false, "storage_state"],
    ["control", "state_persisted", false, "storage_state"],
    ["control", "generation_current", false, "generation"],
    ["control", "mutation_busy", true, "operation_pending"],
    ["control", "observed", "failed", "owner_ready"],
    ["service", "hardware_latched", true, "hardware_state"],
    ["service", "hardware_latched", null, "hardware_state"],
    ["service", "configured_context_tokens", 262144, "token_capacity"],
    ["native", "max_total_num_tokens", 262144, "token_capacity"],
    ["native", "tool_call_parser", "different", "native_profile"],
  ] as const) {
    for (const side of ["before", "after"]) {
      const f = fixture(); let dispatched = false;
      if (side === "before") f[target][key] = value;
      await assert.rejects(f.verify.withVerifiedLane(alias, async () => {
        dispatched = true; f[target][key] = value; return 42;
      }), rejectsReason(reason));
      assert.equal(dispatched, side === "after");
    }
  }
});

test("15-second proof expires independently before dispatch and after a slow count or final node read", async () => {
  for (const target of ["control", "node", "service"] as const) {
    const f = fixture();
    f[target].observed_at = target === "control" ? epoch / 1000 - 15.001 : new Date(epoch - 15001).toISOString();
    await assert.rejects(f.verify.withVerifiedLane(alias, async () => assert.fail("stale proof dispatched count")), rejectsReason("freshness"));
  }
  const slowNative = fixture();
  slowNative.hook(async kind => { if (kind === "native") slowNative.advance(15001); });
  await assert.rejects(slowNative.verify.withVerifiedLane(alias, async () => assert.fail("expired proof dispatched count")), rejectsReason("freshness"));
  for (const target of ["node", "service"] as const) {
    const oldAge = fixture(); oldAge[target].age_ms = 14999;
    oldAge.hook(async kind => { if (kind === "native") oldAge.advance(2); });
    await assert.rejects(oldAge.verify.withVerifiedLane(alias, async () => assert.fail("reported age expired before dispatch")), rejectsReason("freshness"));
  }
  const slowCount = fixture();
  await assert.rejects(slowCount.verify.withVerifiedLane(alias, async () => { slowCount.advance(15001); return 42; }), rejectsReason("freshness"));
  const slowNode = fixture(); let reads = 0;
  slowNode.hook(async kind => { if (kind === "node" && ++reads === 2) {
    slowNode.advance(15001); slowNode.node.observed_at = slowNode.service.observed_at = new Date(epoch + 15001).toISOString();
  } });
  await assert.rejects(slowNode.verify.withVerifiedLane(alias, async () => 42), rejectsReason("freshness"));
});

test("operation and metadata failures do not retry, publish, or reuse a prior successful observation", async () => {
  const f = fixture();
  await f.verify.withVerifiedLane(alias, async () => 42);
  f.seen.length = 0;
  const failure = Error("fixture operation failed");
  await assert.rejects(f.verify.withVerifiedLane(alias, async () => { throw failure; }), error => error === failure);
  assert.deepEqual(f.seen, ["control", "node", "native"]);
  f.seen.length = 0;
  f.hook(async kind => { if (kind === "control") throw Error("fixture unavailable"); });
  await assert.rejects(f.verify.withVerifiedLane(alias, async () => assert.fail("failure dispatched count")), rejectsReason("transport"));
  assert.deepEqual(f.seen, ["control"]);
});

test("abort/deadline is operation-local and propagates into pending metadata reads", async () => {
  const f = fixture(), cancelled = new AbortController();
  cancelled.abort();
  await assert.rejects(f.verify.withVerifiedLane(alias, async () => 42, undefined, cancelled.signal), rejectsReason("cancelled"));
  assert.deepEqual(f.seen, []);
  const pending = new AbortController();
  f.hook(async (_kind, signal) => {
    assert.equal(signal, pending.signal);
    await new Promise<void>(resolve => signal!.addEventListener("abort", () => resolve(), { once: true }));
  });
  const work = f.verify.withVerifiedLane(alias, async () => assert.fail("deadline dispatched count"), undefined, pending.signal);
  pending.abort();
  await assert.rejects(work, rejectsReason("cancelled"));
  assert.deepEqual(f.seen, ["control"]);
});

test("overlapping operations keep identities, diagnostic contexts and cancellation isolated", async () => {
  const f = fixture(), firstSignal = new AbortController(), secondSignal = new AbortController();
  let release!: () => void, entered!: () => void;
  const barrier = new Promise<void>(resolve => { release = resolve; });
  const ready = new Promise<void>(resolve => { entered = resolve; });
  const first = f.verify.withVerifiedLane(alias, async () => { entered(); await barrier; return "first"; }, { requestId: "first", phase: "count" }, firstSignal.signal);
  await ready;
  f.control.generation++;
  const second = await f.verify.withVerifiedLane(alias, async () => "second", { requestId: "second", phase: "count" }, secondSignal.signal);
  assert.equal(second, "second");
  release();
  await assert.rejects(first, rejectsReason("identity_changed"));
  assert.equal(f.events.filter(event => event.requestId === "second").length, 6);
  assert.ok(f.events.every(event => ["first", "second"].includes(event.requestId)));
  assert.deepEqual(f.seen.filter(kind => kind === "control").length, 4);
});

test("cancelling one held operation leaves the overlapping operation independent and skips cancelled after reads", async () => {
  const f = fixture(), firstSignal = new AbortController(), secondSignal = new AbortController();
  let release!: () => void, entered!: () => void;
  const barrier = new Promise<void>(resolve => { release = resolve; });
  const ready = new Promise<void>(resolve => { entered = resolve; });
  const first = f.verify.withVerifiedLane(alias, async () => { entered(); await barrier; return "first"; },
    { requestId: "cancelled", phase: "count" }, firstSignal.signal);
  await ready;
  firstSignal.abort();
  assert.equal(await f.verify.withVerifiedLane(alias, async () => "second",
    { requestId: "healthy", phase: "count" }, secondSignal.signal), "second");
  release();
  await assert.rejects(first, rejectsReason("cancelled"));
  assert.equal(secondSignal.signal.aborted, false);
  assert.equal(f.signals.filter(signal => signal === firstSignal.signal).length, 3);
  assert.equal(f.signals.filter(signal => signal === secondSignal.signal).length, 6);
  assert.deepEqual(f.events.filter(event => event.requestId === "cancelled").map(event => event.step),
    ["control_before", "node_before", "native"]);
  assert.equal(f.seen.filter(kind => kind === "control").length, 3);
});

test("counter retains its exact 15000 ms tokenize deadline and does not begin after caller cancellation", async t => {
  const f = fixture(), deadlines: number[] = [];
  const timeout = AbortSignal.timeout;
  t.mock.method(AbortSignal, "timeout", (ms: number) => { deadlines.push(ms); return timeout(ms); });
  t.mock.method(globalThis, "fetch", async (_url: Parameters<typeof fetch>[0], init?: RequestInit) => {
    assert.ok(init?.signal); return new Response(JSON.stringify({ tokens: [1], count: 1, max_model_len: 262144 }));
  });
  const count = createCodexQwenCounter(f.verify), body = { model: alias, reasoning_effort: "none" }, lane = { alias, url: "http://127.0.0.1:1/v1" };
  await count(body, lane, "fixture", new AbortController().signal);
  assert.deepEqual(deadlines, [15000]);
  const signal = new AbortController(); signal.abort(); f.seen.length = 0;
  await assert.rejects(count(body, lane, "fixture", signal.signal), rejectsReason("cancelled"));
  assert.deepEqual(f.seen, []); assert.deepEqual(deadlines, [15000]);
});


test("schema 1 brackets preserve fixed receipt identity and enforce observation expiry without a node read", async () => {
  const f = fixture();
  const receipt = { ...f.receipt, schema: 1, lanes: { [alias]: { ...f.receipt.lanes[alias],
    activeIdentity: f.control.active_identity, generation: f.control.generation,
    containerId: "b".repeat(64), startedAt: "2026-09-27T07:23:02.292Z" } } };
  const verify = createProductionQwenVerifier(receipt, { controlKey: "fixture", inferenceKey: "fixture" }, f.get, f.now);
  assert.equal(await verify.withVerifiedLane(alias, async q => { assert.equal(q.instanceId.includes("b".repeat(64)), true); return 42; }), 42);
  assert.deepEqual(f.seen, ["control", "native", "native", "control"]);
  await assert.rejects(verify.withVerifiedLane(alias, async () => { f.control.generation++; return 42; }), rejectsReason("generation"));
  f.control.generation--;
  f.hook(async kind => { if (kind === "native") f.advance(15001); });
  await assert.rejects(verify.withVerifiedLane(alias, async () => assert.fail("expired schema 1 proof dispatched count")), rejectsReason("freshness"));
});

test("an expiring tokenize deadline rejects the optimized count without final checks or publication", async t => {
  const f = fixture(), deadline = new AbortController();
  t.mock.method(AbortSignal, "timeout", (ms: number) => { assert.equal(ms, 15000); return deadline.signal; });
  t.mock.method(globalThis, "fetch", async (_url: Parameters<typeof fetch>[0], init?: RequestInit) => {
    const pending = new Promise<Response>((_resolve, reject) => init!.signal!.addEventListener("abort", () => reject(Error("fixture deadline")), { once: true }));
    deadline.abort(); return pending;
  });
  await assert.rejects(createCodexQwenCounter(f.verify)({ model: alias, reasoning_effort: "none" },
    { alias, url: "http://127.0.0.1:1/v1" }, "fixture", new AbortController().signal));
  assert.deepEqual(f.seen, ["control", "node", "native"]);
});
