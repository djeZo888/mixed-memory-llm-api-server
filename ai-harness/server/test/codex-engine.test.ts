import assert from "node:assert/strict";
import test from "node:test";
import { PassThrough } from "node:stream";
import { CodexEngine, CODEX_PIN, type CodexRuntime } from "../src/codex-engine.js";
import type { EngineOptions, EngineUpdate, NativeEngineState } from "../src/contracts.js";
const tick = () => new Promise<void>((resolve) => setImmediate(resolve));
function deferred<T>() { let resolve!: (v: T) => void; const promise = new Promise<T>(r => { resolve = r; }); return { promise, resolve }; }
function fixture(config: { nativeId?: string; gateway?: () => Promise<boolean>; terminate?: () => Promise<boolean> } = {}) {
  const stdin = new PassThrough(), stdout = new PassThrough(), exit = deferred<void>();
  const states: NativeEngineState[] = [], updates: EngineUpdate[] = [], requests: any[] = [], calls: string[] = [];
  const events = (method: string, params: Record<string, unknown>) => stdout.write(JSON.stringify({ method, params: { threadId: "thread-1", ...params } }) + "\n");
  let turn = 0;
  const options: EngineOptions = { sessionId: "session-1", profileDir: "/task/profile", workspace: "/task/workspace", launcher: "/NEVER-EXECUTED",
    engineKind: "codex", engineVersion: CODEX_PIN.version, modelPolicyVersion: "fixture-policy", nativeSessionId: config.nativeId,
    nativeState: { ownership: "idle", activeTurnId: null, eventCursor: 0 }, onNativeState: s => states.push({ ...s }),
    gatewayUrl: "http://10.0.2.2:8081/v1", gatewayToken: "scoped-fixture-token", stderrPath: "/unused",
    onNativeSessionId: id => { assert.equal(id, "thread-1"); }, onUpdate: update => updates.push(update), onExit: () => calls.push("revoke") };
  const runtime: CodexRuntime = { pin: CODEX_PIN, protocolQualified: true, modelPolicyVersion: "fixture-policy", model: "qwen3.8-27b", provider: "sova", contextLimit: 480000,
    gatewayUrl: options.gatewayUrl, requestTimeoutMs: 200, cancelTimeoutMs: 30,
    async launchRootless(input) { calls.push("launch"); assert.equal(states[0]!.ownership, "uncertain"); assert.equal(input.codexHome, "/task/profile/codex-home");
      assert.deepEqual(Object.keys(input).sort(), ["sessionId", "profileDir", "workspace", "codexHome", "gatewayUrl", "gatewayToken", "modelPolicyVersion"].sort());
      return { stdin, stdout, exited: exit.promise, async terminateAndConfirm() { calls.push("terminate"); return config.terminate ? config.terminate() : true; } }; },
    revokeGatewaySession(sessionId) { assert.equal(sessionId, options.sessionId); calls.push("revoke-lineage"); },
    async confirmGatewaySettlement(input) { calls.push("gateway-proof"); assert.equal(input.sessionId, options.sessionId); return config.gateway ? config.gateway() : true; } };
  const response = (id: number, result: unknown) => stdout.write(JSON.stringify({ id, result }) + "\n");
  stdin.on("data", bytes => {
    const req = JSON.parse(bytes.toString()); requests.push(req);
    if (req.method === "initialize") response(req.id, { userAgent: "codex/0.158.0", codexHome: "/task/profile/codex-home", platformFamily: "unix", platformOs: "linux" });
    if (req.method === "thread/start" || req.method === "thread/resume") response(req.id, { thread: { id: "thread-1", turns: [{ items: [{ type: "agentMessage", text: "old history should not replay" }] }] }, model: runtime.model, modelProvider: runtime.provider, cwd: options.workspace, approvalPolicy: "never" });
    if (req.method === "turn/start") {
      assert.equal(states.at(-1)!.ownership, "uncertain");
      turn++; events("turn/started", { turn: { id: `turn-${turn}`, status: "inProgress" } });
      response(req.id, { turn: { id: `turn-${turn}`, status: "inProgress" } });
    }
    if (req.method === "turn/interrupt") response(req.id, {});
  });
  const engine = new CodexEngine(options, runtime);
  const item = (id: string, type: string, props: Record<string, unknown> = {}, stage = "completed") => events(`item/${stage}`, { turnId: "turn-1", item: { id, type, ...props } });
  const complete = (status = "completed") => events("turn/completed", { turn: { id: "turn-1", status } });
  return { engine, runtime, options, states, updates, requests, calls, events, item, complete, stdout, exit };
}
test("pinned initialize/start/input schema; commentary/final/absent phase mapped from authoritative items only", async () => {
  const f = fixture(); await f.engine.start(); const pending = f.engine.prompt("hello"); await tick();
  for (const [id, phase] of [["a", "commentary"], ["b", "final_answer"], ["c", null]] as const) {
    f.item(id, "agentMessage", { text: "", phase }, "started");
    f.events("item/agentMessage/delta", { turnId: "turn-1", itemId: id, delta: "repeat" });
    f.events("item/agentMessage/delta", { turnId: "turn-1", itemId: id, delta: "repeat" });
    f.item(id, "agentMessage", { text: `canonical-${id}`, phase });
    f.item(id, "agentMessage", { text: `canonical-${id}`, phase });
  }
  f.complete(); f.complete(); assert.equal(await pending, "completed");
  assert.deepEqual(f.updates.filter(v => v.type === "text").map(v => [v.text, v.channel]), [["canonical-a", "commentary"], ["canonical-b", "final"], ["canonical-c", "unknown"]]);
  assert.deepEqual(f.calls.slice(-4), ["terminate", "revoke-lineage", "revoke", "gateway-proof"]);
  assert.equal(f.states.at(-1)!.ownership, "idle");
  const init = f.requests[0]; assert.equal(init.params.capabilities.experimentalApi, false);
  const start = f.requests.find(r => r.method === "thread/start"); assert.equal(start.params.sandbox, "danger-full-access");
  assert.equal(start.params.modelProvider, "sova"); assert.equal("config" in start.params, false);
  assert.deepEqual(f.requests.find(r => r.method === "turn/start").params.input, [{ type: "text", text: "hello", text_elements: [] }]);
  await f.engine.close();
});
test("resume uses only original native thread ID and never imports returned history", async () => {
  const f = fixture({ nativeId: "thread-1" }); await f.engine.start();
  const request = f.requests.find(r => r.method === "thread/resume"); assert.equal(request.params.threadId, "thread-1");
  assert.equal("history" in request.params, false); assert.equal("path" in request.params, false); assert.deepEqual(f.updates, []);
  await f.engine.close();
});
test("last occupied tokens and compaction invalidate context without cumulative billing or invented reasoning", async () => {
  const f = fixture(); const pending = f.engine.prompt("test usage"); await tick();
  f.events("thread/tokenUsage/updated", { turnId: "turn-1", tokenUsage: { total: { totalTokens: 800000 }, last: { totalTokens: 2345 }, modelContextWindow: 480000 } });
  f.item("compact", "contextCompaction", {}, "started"); f.item("compact", "contextCompaction");
  f.events("thread/tokenUsage/updated", { turnId: "turn-1", tokenUsage: { total: { totalTokens: 801000 }, last: { totalTokens: 1000 }, modelContextWindow: 480000 } });
  f.item("reason", "reasoning", { summary: [], content: [] }, "started"); f.item("reason", "reasoning", { summary: ["native unqualified"], content: ["unverified"] });
  f.complete(); await pending;
  assert.deepEqual(f.updates.filter(v => v.type === "context").map(v => v.used), [2345, null, null, 1000]);
  assert.equal(f.updates.some(v => v.type === "text"), false);
});
test("cancel ACK cannot release ownership before native terminal, exact process cleanup and owned gateway proof", async () => {
  const proof = deferred<boolean>(); const f = fixture({ gateway: () => proof.promise }); const pending = f.engine.prompt("cancel"); await tick();
  let done = false; const cancelled = f.engine.cancel().then(() => { done = true; }); await tick();
  assert.equal(done, false); assert.equal(f.calls.includes("gateway-proof"), false);
  f.complete("interrupted"); await tick(); assert.equal(done, false); assert.equal(f.states.at(-1)!.ownership, "uncertain");
  proof.resolve(true); await cancelled; assert.equal(await pending, "cancelled"); assert.equal(f.states.at(-1)!.ownership, "idle");
});
test("unsettled gateway or missing exact-container proof preserves uncertainty after native success", async () => {
  for (const kind of ["gateway", "container"]) {
    const f = fixture({ gateway: async () => kind !== "gateway", terminate: async () => kind !== "container" });
    const pending = f.engine.prompt("do not release"); await tick(); f.complete(); await assert.rejects(pending, /unconfirmed/);
    assert.equal(f.states.at(-1)!.ownership, "uncertain"); await assert.rejects(f.engine.close(), /unconfirmed/);
  }
});
test("process death, truncated stream, wrong thread and out-of-order item fail once without prompt replay", async () => {
  for (const mode of ["death", "partial", "wrong-thread", "out-of-order"]) {
    const f = fixture(); const pending = f.engine.prompt("one dispatch"); const rejected = assert.rejects(pending); await tick();
    if (mode === "death") f.exit.resolve();
    if (mode === "partial") { f.stdout.write('{"method":'); f.stdout.end(); }
    if (mode === "wrong-thread") f.events("item/started", { threadId: "other", turnId: "turn-1", item: { type: "agentMessage", id: "x" } });
    if (mode === "out-of-order") f.item("x", "agentMessage", { text: "bad", phase: null });
    await rejected; assert.equal(f.states.at(-1)!.ownership, "uncertain");
    assert.equal(f.requests.filter(r => r.method === "turn/start").length, 1); await f.engine.close();
  }
});
test("policy rejects unqualified runtime, foreign provider, model, engine and media", async () => {
  const f = fixture();
  for (const override of [{ protocolQualified: false }, { provider: "openai" }, { model: "mimo-v2.6-pro-rl" }, { gatewayUrl: "https://api.openai.com/v1" }])
    assert.throws(() => new CodexEngine(f.options, { ...f.runtime, ...override }), /unqualified/);
  assert.throws(() => new CodexEngine({ ...f.options, engineKind: "minimax" }, f.runtime), /unqualified/);
  await assert.rejects(f.engine.prompt("image", [{ path: "/private", mimeType: "image/png", name: "secret" }]), /media is not qualified/);
  assert.deepEqual(f.requests, []);
});
test("pending/completed/unknown native child work is explicitly unsupported, never silently killed as success", async () => {
  for (const status of ["inProgress", "completed", "unknown"]) {
    const f = fixture(); const pending = f.engine.prompt("child"); const rejected = assert.rejects(pending); await tick();
    f.item("child", "collabAgentToolCall", { status }, "started"); await rejected;
    assert.equal(f.states.at(-1)!.ownership, "uncertain"); await f.engine.close();
    assert.equal(f.requests.filter(r => r.method === "turn/start").length, 1);
  }
});
test("parent completed with an unfinished native tool is interrupted rather than accepted as success", async () => {
  const f = fixture(); const pending = f.engine.prompt("tool"); const rejected = assert.rejects(pending); await tick();
  f.item("command", "commandExecution", { status: "inProgress" }, "started"); f.complete(); await rejected;
  assert.equal(f.states.at(-1)!.ownership, "uncertain"); await f.engine.close();
});
