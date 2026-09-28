import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import Ajv from "ajv";
import { PassThrough } from "node:stream";
import {
  CodexEngine,
  CODEX_PIN,
  type CodexRuntime,
} from "../src/codex-engine.js";
import type {
  EngineOptions,
  EngineUpdate,
  NativeEngineState,
} from "../src/contracts.js";
const schemaNames = {
  initialize: "InitializeParams",
  "thread/start": "ThreadStartParams",
  "thread/resume": "ThreadResumeParams",
  "turn/start": "TurnStartParams",
  "turn/interrupt": "TurnInterruptParams",
  "thread/compact/start": "ThreadCompactStartParams",
};
const ajv = new Ajv({ strict: false, validateFormats: false });
const validators = new Map(
  Object.entries(schemaNames).map(([method, name]) => [
    method,
    ajv.compile(
      JSON.parse(
        readFileSync(
          new URL(`./fixtures/codex-0.158.0/${name}.json`, import.meta.url),
          "utf8",
        ),
      ),
    ),
  ]),
);
const tick = () => new Promise<void>((resolve) => setImmediate(resolve));
function deferred<T>() {
  let resolve!: (v: T) => void;
  const promise = new Promise<T>((r) => {
    resolve = r;
  });
  return { promise, resolve };
}
function fixture(
  config: {
    nativeId?: string;
    delegation?: boolean;
    gateway?: () => Promise<boolean>;
    terminate?: () => Promise<boolean>;
  } = {},
) {
  const stdin = new PassThrough(),
    stdout = new PassThrough(),
    exit = deferred<void>();
  const states: NativeEngineState[] = [],
    updates: EngineUpdate[] = [],
    requests: any[] = [],
    calls: string[] = [];
  const events = (method: string, params: Record<string, unknown>) =>
    stdout.write(
      JSON.stringify({ method, params: { threadId: "thread-1", ...params } }) +
        "\n",
    );
  let turn = 0;
  const options: EngineOptions = {
    sessionId: "session-1",
    profileDir: "/task/profile",
    workspace: "/task/workspace",
    launcher: "/NEVER-EXECUTED",
    engineKind: "codex",
    engineVersion: CODEX_PIN.version,
    modelPolicyVersion: "fixture-policy",
    nativeSessionId: config.nativeId,
    nativeState: { ownership: "idle", activeTurnId: null, eventCursor: 0 },
    onNativeState: (s) => states.push({ ...s }),
    gatewayUrl: "http://10.0.2.2:8081/v1",
    gatewayToken: "scoped-fixture-token",
    stderrPath: "/unused",
    onNativeSessionId: (id) => {
      assert.equal(id, "thread-1");
    },
    onUpdate: (update) => updates.push(update),
    onExit: () => calls.push("revoke"),
  };
  const runtime: CodexRuntime = {
    pin: CODEX_PIN,
    delegationEnabled: config.delegation,
    protocolQualified: true,
    modelPolicyVersion: "fixture-policy",
    model: "qwen3.8-27b",
    provider: "sova",
    contextLimit: 480000,
    gatewayUrl: options.gatewayUrl,
    requestTimeoutMs: 200,
    cancelTimeoutMs: 30,
    async launchRootless(input) {
      calls.push("launch");
      assert.equal(states[0]!.ownership, "uncertain");
      assert.equal(input.codexHome, "/task/profile/codex-home");
      assert.deepEqual(
        Object.keys(input).sort(),
        [
          "sessionId",
          "profileDir",
          "workspace",
          "codexHome",
          "gatewayUrl",
          "gatewayToken",
          "modelPolicyVersion",
        ].sort(),
      );
      return {
        stdin,
        stdout,
        exited: exit.promise,
        async terminateAndConfirm() {
          calls.push("terminate");
          return config.terminate ? config.terminate() : true;
        },
      };
    },
    revokeGatewaySession(sessionId) {
      assert.equal(sessionId, options.sessionId);
      calls.push("revoke-lineage");
    },
    async confirmGatewaySettlement(input) {
      calls.push("gateway-proof");
      assert.equal(input.sessionId, options.sessionId);
      return config.gateway ? config.gateway() : true;
    },
  };
  const response = (id: number, result: unknown) =>
    stdout.write(JSON.stringify({ id, result }) + "\n");
  stdin.on("data", (bytes) => {
    const req = JSON.parse(bytes.toString());
    requests.push(req);
    const validate = validators.get(req.method);
    if (validate)
      assert.ok(validate(req.params), JSON.stringify(validate.errors));
    if (req.method === "initialize")
      response(req.id, {
        userAgent: "codex/0.158.0",
        codexHome: "/task/profile/codex-home",
        platformFamily: "unix",
        platformOs: "linux",
      });
    if (req.method === "thread/start" || req.method === "thread/resume")
      response(req.id, {
        thread: {
          id: "thread-1",
          turns: [
            {
              items: [
                { type: "agentMessage", text: "old history should not replay" },
              ],
            },
          ],
        },
        model: runtime.model,
        modelProvider: runtime.provider,
        cwd: options.workspace,
        approvalPolicy: "never",
      });
    if (req.method === "thread/compact/start") {
      events("turn/started", { turn: { id: "turn-1", status: "inProgress" } });
      response(req.id, {});
    }
    if (req.method === "turn/start") {
      assert.equal(states.at(-1)!.ownership, "uncertain");
      turn++;
      events("turn/started", {
        turn: { id: `turn-${turn}`, status: "inProgress" },
      });
      response(req.id, { turn: { id: `turn-${turn}`, status: "inProgress" } });
    }
    if (req.method === "turn/interrupt") response(req.id, {});
  });
  const engine = new CodexEngine(options, runtime);
  const item = (
    id: string,
    type: string,
    props: Record<string, unknown> = {},
    stage = "completed",
  ) =>
    events(`item/${stage}`, { turnId: "turn-1", item: { id, type, ...props } });
  const complete = (status = "completed") =>
    events("turn/completed", { turn: { id: "turn-1", status } });
  return {
    engine,
    runtime,
    options,
    states,
    updates,
    requests,
    calls,
    events,
    item,
    complete,
    stdout,
    exit,
  };
}
test("pinned initialize/start/input schema; commentary/final/absent phase with ordered streaming and authoritative completion", async () => {
  const f = fixture();
  await f.engine.start();
  const pending = f.engine.prompt("hello");
  await tick();
  for (const [id, phase] of [
    ["a", "commentary"],
    ["b", "final_answer"],
    ["c", null],
  ] as const) {
    f.item(id, "agentMessage", { text: "", phase }, "started");
    f.events("item/agentMessage/delta", {
      turnId: "turn-1",
      itemId: id,
      delta: "ha",
    });
    f.events("item/agentMessage/delta", {
      turnId: "turn-1",
      itemId: id,
      delta: "ha",
    });
    f.item(id, "agentMessage", { text: `haha done-${id}`, phase });
    f.item(id, "agentMessage", { text: `haha done-${id}`, phase });
  }
  f.complete();
  f.complete();
  assert.equal(await pending, "completed");
  assert.deepEqual(
    f.updates.filter((v) => v.type === "text").map((v) => [v.text, v.channel]),
    [
      ["ha", "commentary"],
      ["ha", "commentary"],
      [" done-a", "commentary"],
      ["ha", "final"],
      ["ha", "final"],
      [" done-b", "final"],
      ["ha", "unknown"],
      ["ha", "unknown"],
      [" done-c", "unknown"],
    ],
  );
  assert.deepEqual(f.calls.slice(-4), [
    "terminate",
    "revoke-lineage",
    "revoke",
    "gateway-proof",
  ]);
  assert.equal(f.states.at(-1)!.ownership, "idle");
  const init = f.requests[0];
  assert.equal(init.params.capabilities.experimentalApi, false);
  const start = f.requests.find((r) => r.method === "thread/start");
  assert.equal(start.params.sandbox, "danger-full-access");
  assert.equal(start.params.modelProvider, "sova");
  assert.equal("config" in start.params, false);
  assert.deepEqual(
    f.requests.find((r) => r.method === "turn/start").params.input,
    [{ type: "text", text: "hello", text_elements: [] }],
  );
  await f.engine.close();
});
test("resume uses only original native thread ID and never imports returned history", async () => {
  const f = fixture({ nativeId: "thread-1" });
  await f.engine.start();
  const request = f.requests.find((r) => r.method === "thread/resume");
  assert.equal(request.params.threadId, "thread-1");
  assert.equal("history" in request.params, false);
  assert.equal("path" in request.params, false);
  assert.deepEqual(f.updates, []);
  await f.engine.close();
});
test("latest request estimates retained context and compaction invalidate context without cumulative billing or invented reasoning", async () => {
  const f = fixture();
  const pending = f.engine.prompt("test usage");
  await tick();
  f.events("thread/tokenUsage/updated", {
    turnId: "turn-1",
    tokenUsage: {
      total: { totalTokens: 800000 },
      last: { totalTokens: 2345 },
      modelContextWindow: 480000,
    },
  });
  f.item("compact", "contextCompaction", {}, "started");
  f.item("compact", "contextCompaction");
  f.events("thread/tokenUsage/updated", {
    turnId: "turn-1",
    tokenUsage: {
      total: { totalTokens: 801000 },
      last: { totalTokens: 1000 },
      modelContextWindow: 480000,
    },
  });
  f.item("reason", "reasoning", { summary: [], content: [] }, "started");
  f.item("reason", "reasoning", {
    summary: ["native unqualified"],
    content: ["unverified"],
  });
  f.complete();
  await pending;
  assert.deepEqual(
    f.updates.filter((v) => v.type === "context").map((v) => v.used),
    [2345, null, null, 1000],
  );
  assert.equal(
    f.updates.some((v) => v.type === "text"),
    false,
  );
  assert.equal(
    f.updates
      .filter((v) => v.type === "context" && v.used !== null)
      .every(
        (v) => v.estimated && v.source === "codex.latest-request.totalTokens",
      ),
    true,
  );
});
test("cancel ACK cannot release ownership before native terminal, exact process cleanup and owned gateway proof", async () => {
  const proof = deferred<boolean>();
  const f = fixture({ gateway: () => proof.promise });
  const pending = f.engine.prompt("cancel");
  await tick();
  let done = false;
  const cancelled = f.engine.cancel().then(() => {
    done = true;
  });
  await tick();
  assert.equal(done, false);
  assert.equal(f.calls.includes("gateway-proof"), false);
  f.complete("interrupted");
  await tick();
  assert.equal(done, false);
  assert.equal(f.states.at(-1)!.ownership, "uncertain");
  proof.resolve(true);
  await cancelled;
  assert.equal(await pending, "cancelled");
  assert.equal(f.states.at(-1)!.ownership, "idle");
});
test("unsettled gateway or missing exact-container proof preserves uncertainty after native success", async () => {
  for (const kind of ["gateway", "container"]) {
    const f = fixture({
      gateway: async () => kind !== "gateway",
      terminate: async () => kind !== "container",
    });
    const pending = f.engine.prompt("do not release");
    await tick();
    f.complete();
    await assert.rejects(pending, /unconfirmed/);
    assert.equal(f.states.at(-1)!.ownership, "uncertain");
    await assert.rejects(f.engine.close(), /unconfirmed/);
  }
});
test("process death, truncated stream, wrong thread and out-of-order item fail once without prompt replay", async () => {
  for (const mode of ["death", "partial", "wrong-thread", "out-of-order"]) {
    const f = fixture();
    const pending = f.engine.prompt("one dispatch");
    const rejected = assert.rejects(pending);
    await tick();
    if (mode === "death") f.exit.resolve();
    if (mode === "partial") {
      f.stdout.write('{"method":');
      f.stdout.end();
    }
    if (mode === "wrong-thread")
      f.events("item/started", {
        threadId: "other",
        turnId: "turn-1",
        item: { type: "agentMessage", id: "x" },
      });
    if (mode === "out-of-order")
      f.item("x", "agentMessage", { text: "bad", phase: null });
    await rejected;
    assert.equal(f.states.at(-1)!.ownership, "uncertain");
    assert.equal(f.requests.filter((r) => r.method === "turn/start").length, 1);
    await f.engine.close();
  }
});
test("policy rejects unqualified runtime, foreign provider, model, engine and media", async () => {
  const f = fixture();
  for (const override of [
    { protocolQualified: false },
    { provider: "openai" },
    { model: "mimo-v2.6-pro-rl" },
    { gatewayUrl: "https://api.openai.com/v1" },
  ])
    assert.throws(
      () => new CodexEngine(f.options, { ...f.runtime, ...override }),
      /unqualified/,
    );
  assert.throws(
    () => new CodexEngine({ ...f.options, engineKind: "minimax" }, f.runtime),
    /unqualified/,
  );
  await assert.rejects(
    f.engine.prompt("image", [
      { path: "/private", mimeType: "image/png", name: "secret" },
    ]),
    /media is not qualified/,
  );
  assert.deepEqual(f.requests, []);
});
test("pending/completed/unknown native child work is explicitly unsupported, never silently killed as success", async () => {
  for (const status of ["inProgress", "completed", "unknown"]) {
    const f = fixture();
    const pending = f.engine.prompt("child");
    const rejected = assert.rejects(pending);
    await tick();
    f.item("child", "collabAgentToolCall", { status }, "started");
    await rejected;
    assert.equal(f.states.at(-1)!.ownership, "uncertain");
    await f.engine.close();
    assert.equal(f.requests.filter((r) => r.method === "turn/start").length, 1);
  }
});
test("parent completed with an unfinished native tool is interrupted rather than accepted as success", async () => {
  const f = fixture();
  const pending = f.engine.prompt("tool");
  const rejected = assert.rejects(pending);
  await tick();
  f.item("command", "commandExecution", { status: "inProgress" }, "started");
  f.complete();
  await rejected;
  assert.equal(f.states.at(-1)!.ownership, "uncertain");
  await f.engine.close();
});

test("canonical correction emits explicit snapshot and tool Activity uses actual command/url/result fields", async () => {
  const f = fixture();
  const pending = f.engine.prompt("stream");
  await tick();
  f.item(
    "message",
    "agentMessage",
    { text: "", phase: "commentary" },
    "started",
  );
  f.events("item/agentMessage/delta", {
    turnId: "turn-1",
    itemId: "message",
    delta: "partial",
  });
  assert.equal(
    f.updates.some((u) => u.type === "text" && u.text === "partial"),
    true,
  );
  f.item("message", "agentMessage", {
    text: "corrected canonical",
    phase: "final_answer",
  });
  f.item(
    "command",
    "commandExecution",
    {
      command: "python3 fixture.py",
      cwd: "/task/workspace",
      processId: "p1",
      status: "inProgress",
    },
    "started",
  );
  f.item("command", "commandExecution", {
    command: "python3 fixture.py",
    cwd: "/task/workspace",
    processId: "p1",
    status: "completed",
    aggregatedOutput: "passed",
    exitCode: 0,
  });
  f.item(
    "mcp",
    "mcpToolCall",
    {
      server: "local-browser",
      tool: "open",
      arguments: { url: "https://example.test/page" },
      status: "inProgress",
    },
    "started",
  );
  f.item("mcp", "mcpToolCall", {
    server: "local-browser",
    tool: "open",
    arguments: { url: "https://example.test/page" },
    status: "completed",
    result: { content: [{ type: "text", text: "page read" }] },
  });
  f.complete();
  await pending;
  assert.equal(
    f.updates.some(
      (u) =>
        u.type === "text" &&
        u.replace === true &&
        u.text === "corrected canonical",
    ),
    true,
  );
  assert.equal(
    f.updates.some(
      (u) =>
        u.type === "progress" &&
        u.command === "python3 fixture.py" &&
        u.detail?.includes("passed"),
    ),
    true,
  );
  assert.equal(
    f.updates.some(
      (u) =>
        u.type === "progress" &&
        u.url === "https://example.test/page" &&
        u.detail?.includes("page read"),
    ),
    true,
  );
});
test("launch rejection after possible spawn retains uncertain ownership even when gateway is idle", async () => {
  const f = fixture();
  let attempted = false;
  const engine = new CodexEngine(f.options, {
    ...f.runtime,
    async launchRootless() {
      attempted = true;
      throw new Error("lost launcher handle after possible spawn");
    },
  });
  await assert.rejects(engine.start(), /lost launcher handle/);
  assert.equal(attempted, true);
  await assert.rejects(engine.close(), /unconfirmed/);
  assert.equal(f.states.at(-1)!.ownership, "uncertain");
});
test("declined native command remains cancelled in Activity", async () => {
  const f = fixture();
  const pending = f.engine.prompt("tool refused");
  await tick();
  f.item(
    "command",
    "commandExecution",
    { command: "unapproved", status: "inProgress" },
    "started",
  );
  f.item("command", "commandExecution", {
    command: "unapproved",
    status: "declined",
  });
  f.complete();
  await pending;
  assert.equal(
    f.updates.some((u) => u.type === "progress" && u.status === "cancelled"),
    true,
  );
});

test("actual pinned native delegation event replay preserves child terminal before parent", async () => {
  const f = fixture({ delegation: true });
  const capture = JSON.parse(
    readFileSync(
      new URL(
        "./fixtures/codex/native-delegation-events.json",
        import.meta.url,
      ),
      "utf8",
    ),
  );
  const pending = f.engine.prompt("delegate");
  await tick();
  for (const event of capture.events) {
    const p = { ...event.params };
    if (p.threadId === capture.parentThreadId) p.threadId = "thread-1";
    if (p.turnId === capture.parentTurnId) p.turnId = "turn-1";
    if (p.turn?.id === capture.parentTurnId)
      p.turn = { ...p.turn, id: "turn-1" };
    if (p.item?.senderThreadId === capture.parentThreadId)
      p.item = { ...p.item, senderThreadId: "thread-1" };
    f.events(event.method, p);
  }
  assert.equal(await pending, "completed");
  const summaries = f.updates
    .filter((u) => u.type === "progress" && u.subagents)
    .map((u) => u.subagents!);
  assert.ok(summaries.some((s) => s.active === 1));
  assert.equal(summaries.at(-1)?.completed, 1);
  assert.equal(summaries.at(-1)?.active, 0);
});

test("finished spawn tool with pending child cannot turn native cleanup into parent success", async () => {
  const f = fixture({ delegation: true });
  const pending = f.engine.prompt("delegate");
  const rejected = assert.rejects(pending, /incomplete/);
  await tick();
  const item = {
    tool: "spawnAgent",
    status: "inProgress",
    senderThreadId: "thread-1",
    receiverThreadIds: [],
    agentsStates: {},
    model: "",
  };
  f.item("spawn", "collabAgentToolCall", item, "started");
  f.item("spawn", "collabAgentToolCall", {
    ...item,
    status: "completed",
    model: "qwen3.8-27b",
    receiverThreadIds: ["child-1"],
    agentsStates: { "child-1": { status: "pendingInit", message: null } },
  });
  f.complete();
  await rejected;
  await f.engine.close();
  assert.ok(
    f.updates.some(
      (u) =>
        u.type === "progress" &&
        u.subagentId === "child-1" &&
        u.status === "cancelled" &&
        u.detail?.includes("cleanup"),
    ),
  );
});

test("private compaction uses exact pinned RPC; missing/failed compaction never claims readiness", async () => {
  for (const outcome of ["success", "missing", "failure", "interrupted"]) {
    const f = fixture();
    const pending = f.engine.compact();
    const result = ["success", "interrupted"].includes(outcome)
      ? pending
      : assert.rejects(pending);
    await tick();
    if (outcome !== "missing")
      f.item("compact", "contextCompaction", {}, "started");
    if (outcome === "success") f.item("compact", "contextCompaction");
    f.complete(
      outcome === "failure"
        ? "failed"
        : outcome === "interrupted"
          ? "interrupted"
          : "completed",
    );
    await result;
    assert.equal(
      f.requests.filter((r) => r.method === "thread/compact/start").length,
      1,
    );
    assert.equal(f.requests.filter((r) => r.method === "turn/start").length, 0);
    assert.ok(f.updates.some((u) => u.type === "context" && u.used === null));
    if (outcome !== "success") {
      assert.ok(
        f.updates.some((u) => u.type === "compaction" && u.status === "failed"),
      );
      await f.engine.close();
    }
  }
});

test("actual native child trajectory rejects an unfinished child command before success", async () => {
  const f = fixture({ delegation: true });
  const capture = JSON.parse(
    readFileSync(
      new URL(
        "./fixtures/codex/native-delegation-events.json",
        import.meta.url,
      ),
      "utf8",
    ),
  );
  const pending = f.engine.prompt("delegate");
  const rejected = assert.rejects(pending, /child has incomplete/);
  await tick();
  for (const event of capture.events) {
    const p = { ...event.params };
    if (p.threadId === capture.parentThreadId) p.threadId = "thread-1";
    if (p.turnId === capture.parentTurnId) p.turnId = "turn-1";
    if (p.turn?.id === capture.parentTurnId)
      p.turn = { ...p.turn, id: "turn-1" };
    if (p.item?.senderThreadId === capture.parentThreadId)
      p.item = { ...p.item, senderThreadId: "thread-1" };
    if (event.method === "turn/completed" && p.threadId !== "thread-1")
      f.events("item/started", {
        threadId: p.threadId,
        turnId: p.turn.id,
        item: {
          id: "unfinished-command",
          type: "commandExecution",
          status: "inProgress",
        },
      });
    f.events(event.method, p);
  }
  await rejected;
  await f.engine.close();
  assert.ok(
    f.updates.some(
      (u) =>
        u.type === "progress" &&
        u.kind === "subagent" &&
        u.status === "cancelled",
    ),
  );
});

// Cold resume replays historical usage after the resume response in pinned0.158.0.
// It must never adopt an old turn, mark a new turn active, or replay history.
test("resume usage snapshot permits follow-up without adopting historical turn", async () => {
  const f = fixture({ nativeId: "thread-1" });
  await f.engine.start();
  const stateCount = f.states.length;
  f.events("thread/tokenUsage/updated", { turnId: "previous-turn", tokenUsage: { last: { totalTokens: 2345 }, modelContextWindow: 480000 } });
  try {
    assert.deepEqual(f.updates, [{ type: "context", used: null, estimated: true, source: "codex.restored-usage.awaiting-current-request" }]);
    assert.equal(f.states.length, stateCount, "usage snapshot must not write ownership");
    const pending = f.engine.prompt("distinct follow-up");
    await tick(); f.complete(); assert.equal(await pending, "completed");
    assert.equal(f.requests.filter(r => r.method === "turn/start").length, 1);
  } finally { await f.engine.close(); }
});
for (const bad of ["wrong-thread", "wrong-context", "negative-usage", "bad-usage-shape", "empty-turn"]) {
  test(`resume usage rejects ${bad}`, async () => {
    const f = fixture({ nativeId: "thread-1" }); await f.engine.start();
    f.events("thread/tokenUsage/updated", { threadId: bad === "wrong-thread" ? "other-thread" : "thread-1", turnId: bad === "empty-turn" ? "" : "previous-turn", tokenUsage: bad === "bad-usage-shape" ? {} : { last: { totalTokens: bad === "negative-usage" ? -1 : 2345 }, modelContextWindow: bad === "wrong-context" ? 950000 : 480000 } });
    await assert.rejects(f.engine.prompt("must not dispatch"));
    assert.equal(f.requests.filter(r => r.method === "turn/start").length, 0);
    assert.equal(f.updates.filter(u => u.type === "context").length, 0); await f.engine.close();
  });
}
test("resume usage does not weaken real item ordering", async () => {
  const f = fixture({ nativeId: "thread-1" }); await f.engine.start();
  f.events("item/completed", { turnId: "previous-turn", item: { id: "old-item", type: "agentMessage", text: "must not replay" } });
  await assert.rejects(f.engine.prompt("must not dispatch"));
  assert.equal(f.requests.filter(r => r.method === "turn/start").length, 0); await f.engine.close();
});

test('cancel keeps native uncertainty until delayed durable gateway drain and returns cancelled', async () => {
 const {GatewayOwnership}=await import('../src/gateway-ownership.js');
 const owners=new GatewayOwnership({recoveryReady:true,onRequestState:()=>{}}),request=owners.begin('session');
 owners.transition(request,'draining');
 const f=fixture({gateway:()=>owners.waitForSettlement({sessionId:'session'},1000)});
 const pending=f.engine.prompt('stop fixture');await tick();
 const cancelled=f.engine.cancel();f.complete('interrupted');await tick();
 assert.equal(f.states.at(-1)!.ownership,'uncertain');assert.ok(f.calls.indexOf('terminate')<f.calls.indexOf('gateway-proof'));
 owners.transition(request,'settled');await cancelled;assert.equal(await pending,'cancelled');
 assert.equal(f.states.at(-1)!.ownership,'idle');assert.equal(f.requests.filter(r=>r.method==='turn/start').length,1);
});
test('drain observation timeout or unconfirmed native process never releases cancellation ownership', async () => {
 const {GatewayOwnership}=await import('../src/gateway-ownership.js');
 for(const nativeConfirmed of [true,false]){
  const owners=new GatewayOwnership({recoveryReady:true,onRequestState:()=>{}}),request=owners.begin('session');
  if(!nativeConfirmed)owners.transition(request,'settled');
  const f=fixture({terminate:async()=>nativeConfirmed,gateway:()=>owners.waitForSettlement({sessionId:'session'},5)});
  const pending=f.engine.prompt('stop fixture');const rejected=assert.rejects(pending,/unconfirmed/);await tick();
  const cancelled=assert.rejects(f.engine.cancel(),/unconfirmed/);f.complete('interrupted');
  await Promise.all([rejected,cancelled]);assert.equal(f.states.at(-1)!.ownership,'uncertain');
  await assert.rejects(f.engine.close(),/unconfirmed/);
 }
});
