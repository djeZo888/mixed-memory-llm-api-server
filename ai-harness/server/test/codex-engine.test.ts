import assert from "node:assert/strict";
import test, { mock } from "node:test";
import { readFileSync } from "node:fs";
import { Ajv } from "ajv";
import { createCodexReadOriginalProbe, createCodexTextOnlyPolicy, createCodexParentArtifactScope, CODEX_H041_WINDOW } from "../src/codex-probe.js";
import { receiptFixture } from "./helpers/codex-receipt-fixture.js";
import { PassThrough } from "node:stream";
import { loadCodexResumeInstructions } from "../src/codex-instructions.js";
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
// Synthetic H041 authorization clock; never a native window acceptance.
mock.timers.enable({ apis: ["Date"], now: CODEX_H041_WINDOW.startAtMs + 60000 });
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
    probe?: boolean;
    textOnly?: boolean;
    artifacts?: boolean;
    registerArtifact?: CodexRuntime["registerCheckpointArtifact"];
    admission?: () => Promise<void>;
    originalAdmission?: (signal: AbortSignal) => Promise<void>;
    receipts?: "valid" | "missing" | "tampered";
    probeSandboxMismatch?: boolean;
    delegation?: boolean;
    qualifiedChildModels?: readonly string[];
    gateway?: () => Promise<boolean>;
    terminate?: () => Promise<boolean>;
    interrupt?: "reject" | "timeout";
    compactStart?: "ack-only" | "timeout";
    requestTimeoutMs?: number;
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
    qualifiedChildModels: config.qualifiedChildModels,
    protocolQualified: true,
    nativeReceiptsRequired: config.probe || config.textOnly || config.artifacts,
    textOnlyPolicy: config.probe || config.textOnly || config.artifacts ? () => createCodexTextOnlyPolicy({sessionId:"session-1",runId:"probe-run",mode:config.probe?"read-original":config.artifacts?"parent-artifacts":"text-only-parent",configSha256:"b".repeat(64),modelCatalogSha256:"b".repeat(64)}) : undefined,
    authorizeNativeTurn: config.probe || config.textOnly || config.artifacts ? async () => { calls.push("native-admission"); await config.admission?.(); } : undefined,
    authorizeOriginalRead: config.probe ? async (_, signal) => { calls.push("original-admission"); await config.originalAdmission?.(signal); } : undefined,
    onNativeThreadPolicy: config.probe || config.textOnly || config.artifacts ? () => { calls.push("thread-policy"); } : undefined,
    parentArtifactScope: config.artifacts ? () => createCodexParentArtifactScope({sessionId:"session-1",runId:"probe-run",checkpointId:"cp",names:["recall.json","state.json"],maxBytes:4096}) : undefined,
    registerCheckpointArtifact: config.artifacts ? config.registerArtifact ?? (async input => {calls.push("artifact-registered");return {artifactId:"actual-synthetic-file-id",sha256:input.sha256};}) : undefined,
    onCheckpointArtifactSettled: config.artifacts ? () => { calls.push("artifact-consumed"); } : undefined,
    readOriginalProbe: config.probe ? () => createCodexReadOriginalProbe({sessionId: "session-1", runId: "probe-run", checkpointId: "frozen-cp", baseInstructions: "Host-authored isolated recovery probe", originals: [{reference: "old-1", bytes: Buffer.from("retained original requirement")}]}) : undefined,
    onNativeLaunchReceipt: config.probe ? () => { calls.push("launch-receipt"); } : undefined,
    onNativeSettlementReceipt: config.probe ? () => { calls.push("settlement-receipt"); } : undefined,
    onOriginalReadSettled: config.probe ? () => { calls.push("read-consumed"); } : undefined,
    modelPolicyVersion: "fixture-policy",
    model: "qwen3.8-27b",
    provider: "sova",
    contextLimit: 480000,
    gatewayUrl: options.gatewayUrl,
    requestTimeoutMs: config.requestTimeoutMs ?? 200,
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
          ...(config.probe || config.textOnly || config.artifacts ? ["receiptRunId"] : []),
        ].sort(),
      );
      const receipts = config.probe || config.textOnly || config.artifacts ? receiptFixture() : undefined;
      return {
        stdin,
        stdout,
        exited: exit.promise,
        launchReceipt: receipts ? Promise.resolve(config.receipts === "missing" ? undefined : config.receipts === "tampered" ? structuredClone(receipts.launch) : receipts.launch) : undefined,
        settlementReceipt: receipts ? Promise.resolve(receipts.settlement) : undefined,
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
          ...(config.probe || config.textOnly || config.artifacts ? {environments:[]} : {}),
          turns: req.params.excludeTurns ? [] : [
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
        ...(config.probe || config.textOnly || config.artifacts ? { sandbox: { type: config.probeSandboxMismatch ? "dangerFullAccess" : "readOnly" } } : {}),
      });
    if (req.method === "thread/compact/start") {
      if (config.compactStart !== "ack-only")
        events("turn/started", { turn: { id: "turn-1", status: "inProgress" } });
      if (config.compactStart !== "timeout") response(req.id, {});
    }
    if (req.method === "turn/start") {
      assert.equal(states.at(-1)!.ownership, "uncertain");
      turn++;
      events("turn/started", {
        turn: { id: `turn-${turn}`, status: "inProgress" },
      });
      response(req.id, { turn: { id: `turn-${turn}`, status: "inProgress" } });
    }
    if (req.method === "turn/interrupt") {
      if (config.interrupt === "reject") stdout.write(JSON.stringify({ id: req.id, error: { code: -1, message: "fixture rejection" } }) + "\n");
      else if (config.interrupt !== "timeout") response(req.id, {});
    }
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
      .filter((v): v is Extract<EngineUpdate, {type:"context"}> => v.type === "context" && v.used !== null)
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
    .filter((u): u is Extract<EngineUpdate, {type:"progress"}> => u.type === "progress" && !!u.subagents)
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

// H034 retained failed/not_found outcome, with the inProgress start reconstructed
// from pinned close_agent.rs. Parent identity is remapped to this stdio fixture.
const historicalClose = {
  tool: "closeAgent", status: "inProgress", senderThreadId: "thread-1",
  receiverThreadIds: ["01a0ede6-0fad-7191-9e87-bcad69beb761"],
  prompt: null, model: null, reasoningEffort: null, agentsStates: {},
};
const historicalCloseId = "call_c6b86a86548d4b99953770e9";
const historicalCloseFailed = {
  ...historicalClose, status: "failed",
  agentsStates: { [historicalClose.receiverThreadIds[0]]: { status: "notFound", message: null } },
};

test("historical close failure allows new owned work after cold resume without inventing a child", async () => {
  const f = fixture({ nativeId: "thread-1", delegation: true });
  const pending = f.engine.prompt("historical close fixture");
  await tick();
  f.item(historicalCloseId, "collabAgentToolCall", historicalClose, "started");
  f.item(historicalCloseId, "collabAgentToolCall", historicalCloseFailed);
  const spawn = { tool: "spawnAgent", status: "inProgress", senderThreadId: "thread-1",
    receiverThreadIds: [], agentsStates: {}, model: null };
  f.item("fresh-spawn", "collabAgentToolCall", spawn, "started");
  f.item("fresh-spawn", "collabAgentToolCall", { ...spawn, status: "completed", model: "qwen3.8-27b",
    receiverThreadIds: ["fresh-child"], agentsStates: { "fresh-child": { status: "completed", message: null } } });
  f.complete();
  assert.equal(await pending, "completed");
  assert.ok(f.requests.some(r => r.method === "thread/resume"));
  const children = f.updates.filter((u): u is Extract<EngineUpdate, {type:"progress"}> => u.type === "progress" && u.kind === "subagent");
  assert.ok(children.length > 0);
  assert.ok(children.every(u => u.subagentId === "fresh-child"));
  assert.equal(children.at(-1)?.subagents?.completed, 1);
  assert.equal(children.at(-1)?.subagents?.cancelled, 0);
});

for (const outcome of ["missing", "success", "changed-tool", "changed-receiver", "changed-call"])
test(`historical close ${outcome} cannot become parent success`, async () => {
  const f = fixture({ delegation: true });
  const pending = f.engine.prompt("invalid historical close fixture");
  const rejected = assert.rejects(pending, /incomplete|unowned native close|before start/);
  await tick();
  f.item(historicalCloseId, "collabAgentToolCall", historicalClose, "started");
  if (outcome !== "missing") {
    const completion = { ...historicalCloseFailed,
      ...(outcome === "success" ? { status: "completed" } : {}),
      ...(outcome === "changed-tool" ? { tool: "spawnAgent", model: "qwen3.8-27b" } : {}),
      ...(outcome === "changed-receiver" ? { receiverThreadIds: ["different"] } : {}),
    };
    f.item(outcome === "changed-call" ? "other-call" : historicalCloseId, "collabAgentToolCall", completion);
  }
  f.complete();
  await rejected;
  await f.engine.close();
  assert.equal(f.updates.some(u => u.type === "progress" && u.kind === "subagent"), false);
  assert.ok(f.calls.indexOf("terminate") < f.calls.indexOf("gateway-proof"));
});

test("pending historical close cancellation still waits for gateway drain after native cleanup", async () => {
  const drain = deferred<boolean>();
  const f = fixture({ delegation: true, gateway: () => drain.promise });
  const pending = f.engine.prompt("pending historical close cancellation fixture");
  await tick();
  f.item(historicalCloseId, "collabAgentToolCall", historicalClose, "started");
  const cancelled = f.engine.cancel();
  f.complete("interrupted");
  await tick();
  assert.equal(f.states.at(-1)!.ownership, "uncertain");
  assert.ok(f.calls.indexOf("terminate") < f.calls.indexOf("gateway-proof"));
  assert.equal(f.updates.some(u => u.type === "progress" && u.kind === "subagent"), false);
  drain.resolve(true);
  await cancelled;
  assert.equal(await pending, "cancelled");
  assert.equal(f.states.at(-1)!.ownership, "idle");
});

test("MiMo child lifecycle requires the explicit trusted runtime model policy", async () => {
  for (const qualified of [false, true]) {
    const f = fixture({ delegation: true,
      ...(qualified ? { qualifiedChildModels: ["qwen3.8-27b", "mimo-v2.6-pro-rl"] } : {}) });
    const pending = f.engine.prompt("synthetic qualified child lifecycle");
    const checked = qualified ? pending : assert.rejects(pending, /unqualified|Unqualified/);
    await tick();
    const item = { tool: "spawnAgent", status: "inProgress", senderThreadId: "thread-1",
      receiverThreadIds: [], agentsStates: {}, model: "" };
    f.item("spawn", "collabAgentToolCall", item, "started");
    f.item("spawn", "collabAgentToolCall", { ...item, status: "completed", model: "mimo-v2.6-pro-rl",
      receiverThreadIds: ["child-mimo"], agentsStates: { "child-mimo": { status: "completed", message: null } } });
    if (qualified) {
      f.complete();
      assert.equal(await checked, "completed");
      assert.ok(f.updates.some(update => update.type === "progress" && update.name === "MiMo child" && update.status === "completed"));
    } else { await checked; await f.engine.close(); }
  }
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

for (const actions of [["compact", "compact"], ["prompt", "prompt"], ["compact", "prompt"], ["prompt", "compact"]] as const) {
  test(`shared startup permits only one owned operation: ${actions.join(" / ")}`, async () => {
    const f = fixture();
    const pending = actions.map(action => action === "compact" ? f.engine.compact() : f.engine.prompt("fixture summary request"));
    pending.forEach(p => { void p.catch(() => undefined); });
    try {
      await tick();
      const dispatched = f.requests.filter(r => r.method === "turn/start" || r.method === "thread/compact/start");
      assert.equal(dispatched.length, 1, "startup wait must not bypass operation serialization");
      assert.equal(f.calls.filter(c => c === "launch").length, 1);
      if (dispatched[0].method === "thread/compact/start") {
        f.item("compact", "contextCompaction", {}, "started");
        f.item("compact", "contextCompaction");
      }
      f.complete();
      const results = await Promise.allSettled(pending);
      assert.equal(results.filter(r => r.status === "fulfilled" && r.value === "completed").length, 1);
      assert.equal(results.filter(r => r.status === "rejected").length, 1);
      assert.equal(f.calls.filter(c => c === "terminate").length, 1);
      assert.equal(f.states.at(-1)!.ownership, "idle");
    } finally {
      await f.engine.close();
    }
  });
}

test("native compaction retry preserves operation identity and awaits terminal plus gateway settlement without usage", async () => {
  const proof = deferred<boolean>();
  const f = fixture({ nativeId: "thread-1", gateway: () => proof.promise });
  let settled = false;
  const pending = f.engine.compact().then(outcome => { settled = true; return outcome; });
  void pending.catch(() => undefined);
  await tick();
  f.item("compact", "contextCompaction", {}, "started");
  f.events("error", { turnId: "turn-1", willRetry: true, error: { message: "synthetic private retry detail" } });
  await tick();
  assert.equal(settled, false);
  assert.equal(f.states.at(-1)!.ownership, "active");
  assert.equal(f.calls.includes("terminate"), false);
  assert.equal(f.updates.some(u => u.type === "compaction" && u.status === "failed"), false);
  assert.ok(f.updates.some(u => u.type === "progress" && u.kind === "native_retry"));
  assert.doesNotMatch(JSON.stringify(f.updates), /synthetic private retry detail|old history should not replay/);
  f.item("compact", "contextCompaction");
  f.item("compact", "contextCompaction"); // Exact duplicate is harmless.
  const terminal = { turn: { id: "turn-1", status: "completed", items: [], itemsView: "notLoaded", error: null } };
  f.events("turn/completed", terminal);
  f.events("turn/completed", terminal);
  await tick();
  assert.equal(settled, false, "native completion does not prove owned inference settled");
  assert.equal(f.states.at(-1)!.ownership, "uncertain");
  proof.resolve(true);
  assert.equal(await pending, "completed");
  assert.equal(f.updates.filter(u => u.type === "compaction" && u.status === "completed").length, 1);
  assert.ok(f.updates.filter(u => u.type === "context").every(u => u.type === "context" && u.used === null));
  assert.equal(f.states.at(-1)!.ownership, "idle");
  assert.equal(f.requests.filter(r => r.method === "thread/resume").length, 1);
  assert.equal(f.requests.filter(r => r.method === "thread/compact/start").length, 1);
  assert.equal(f.requests.filter(r => r.method === "turn/start").length, 0);
});

test("cold resume requests metadata only without replacing native history or uploading a synthetic history", async () => {
  const f = fixture({ nativeId: "thread-1" });
  await f.engine.start();
  const resume = f.requests.find(r => r.method === "thread/resume");
  assert.equal(resume.params.excludeTurns, true);
  assert.equal(resume.params.threadId, "thread-1");
  assert.equal("history" in resume.params, false);
  assert.equal("path" in resume.params, false);
  assert.equal(f.updates.some(u => u.type === "text"), false);
  const pending = f.engine.prompt("Continue using the same native thread.");
  await tick(); f.complete();
  assert.equal(await pending, "completed");
  assert.equal(f.requests.find(r => r.method === "turn/start").params.threadId, "thread-1");
});

for (const mode of ["wrong-thread", "wrong-turn", "malformed", "terminal", "failed-after-retry"] as const) {
  test(`compaction retry does not relax failure or scope validation: ${mode}`, async () => {
    const f = fixture();
    const pending = f.engine.compact();
    const rejected = assert.rejects(pending);
    await tick();
    f.item("compact", "contextCompaction", {}, "started");
    f.events("error", {
      threadId: mode === "wrong-thread" ? "foreign-thread" : "thread-1",
      turnId: mode === "wrong-turn" ? "foreign-turn" : "turn-1",
      willRetry: mode !== "terminal",
      error: mode === "malformed" ? {} : { message: "fixture error" },
    });
    if (mode === "failed-after-retry") f.complete("failed");
    await rejected;
    assert.ok(f.updates.some(u => u.type === "compaction" && u.status === "failed"));
    await f.engine.close();
    assert.equal(f.requests.filter(r => r.method === "thread/compact/start").length, 1);
    assert.equal(f.states.at(-1)!.ownership, "idle");
  });
}

test("prompt text alone cannot create a compaction lifecycle", async () => {
  const f = fixture();
  const pending = f.engine.prompt("Summarize the summary and perform automatic compaction now.");
  await tick();
  f.complete();
  assert.equal(await pending, "completed");
  assert.equal(f.updates.some(u => u.type === "compaction"), false);
  assert.equal(f.requests.filter(r => r.method === "thread/compact/start").length, 0);
});

test("compaction ACK without native identity cannot support an unscoped Stop", async () => {
  const f = fixture({ compactStart: "ack-only" });
  const pending = f.engine.compact();
  const rejected = assert.rejects(pending, /process cleanup/);
  await tick();
  await assert.rejects(f.engine.cancel(), /identity unknown/);
  assert.equal(f.requests.some(r => r.method === "turn/interrupt"), false);
  await f.engine.close();
  await rejected;
  assert.equal(f.calls.filter(c => c === "terminate").length, 1);
  assert.equal(f.states.at(-1)!.ownership, "idle");
});

for (const failure of ["timeout", "process-death"] as const) {
  test(`compaction ${failure} retains failure and requires cleanup without native replay`, async () => {
    const f = fixture({ compactStart: failure === "timeout" ? "timeout" : undefined, requestTimeoutMs: 10 });
    const pending = f.engine.compact();
    const rejected = assert.rejects(pending, failure === "timeout" ? /will not be replayed/ : /process exited/);
    await tick();
    f.item("compact", "contextCompaction", {}, "started");
    if (failure === "process-death") f.exit.resolve();
    await rejected;
    assert.equal(f.states.at(-1)!.ownership, "uncertain");
    assert.ok(f.updates.some(u => u.type === "compaction" && u.status === "failed"));
    await f.engine.close();
    assert.equal(f.requests.filter(r => r.method === "thread/compact/start").length, 1);
    await assert.rejects(f.engine.compact(), /cannot compact/);
    assert.equal(f.states.at(-1)!.ownership, "idle");
  });
}

test("compaction Stop still waits for native interruption, descendant cleanup and gateway drain", async () => {
  const proof = deferred<boolean>();
  const f = fixture({ gateway: () => proof.promise });
  const pending = f.engine.compact();
  await tick();
  f.item("compact", "contextCompaction", {}, "started");
  const cancelled = f.engine.cancel();
  f.complete("interrupted");
  await tick();
  assert.equal(f.states.at(-1)!.ownership, "uncertain");
  assert.deepEqual(f.requests.find(r => r.method === "turn/interrupt").params, { threadId: "thread-1", turnId: "turn-1" });
  proof.resolve(true);
  await cancelled;
  assert.equal(await pending, "cancelled");
  assert.ok(f.updates.some(u => u.type === "compaction" && u.status === "failed"));
  assert.equal(f.states.at(-1)!.ownership, "idle");
});

for (const outcome of ["retry-success", "failed", "process-death", "interrupted"] as const) {
  test(`real adapter and durable broker retain original history/files and action across restart: ${outcome}`, async t => {
    const { createApp } = await import("../src/app.js");
    const { mkdtemp, readFile, writeFile, rm } = await import("node:fs/promises");
    const { tmpdir } = await import("node:os");
    const { join } = await import("node:path");
    const dir = await mkdtemp(join(tmpdir(), "h039-adapter-retention-"));
    const retained = [{ id: "old-message", type: "agentMessage", text: "Original native history is not a new answer." }];
    const retainedBefore = structuredClone(retained);
    const requests: any[] = [];
    const template = fixture().runtime;
    const runtime: CodexRuntime = {
      ...template,
      revokeGatewaySession() {},
      async confirmGatewaySettlement() { return true; },
      async launchRootless(input) {
        const stdin = new PassThrough(), stdout = new PassThrough(), exit = deferred<void>();
        const emit = (value: unknown) => stdout.write(JSON.stringify(value) + "\n");
        const event = (method: string, params: Record<string, unknown>) => emit({ method, params: { threadId: "thread-1", ...params } });
        const turn = (status: string) => event("turn/completed", { turn: { id: "compact-turn", status, items: [], itemsView: "notLoaded", error: null } });
        stdin.on("data", data => {
          const r = JSON.parse(data.toString()); requests.push(r);
          const reply = (result: unknown) => emit({ id: r.id, result });
          if (r.method === "initialize") reply({ userAgent: "codex/0.158.0", codexHome: input.codexHome, platformOs: "linux", platformFamily: "unix" });
          if (r.method === "thread/resume") reply({ thread: { id: "thread-1", turns: r.params.excludeTurns ? [] : [{ items: retained }] }, model: runtime.model, modelProvider: runtime.provider, cwd: input.workspace, approvalPolicy: "never" });
          if (r.method === "thread/compact/start") {
            reply({});
            event("turn/started", { turn: { id: "compact-turn", status: "inProgress" } });
            event("item/started", { turnId: "compact-turn", item: { id: "compact-item", type: "contextCompaction" } });
            if (outcome === "retry-success") {
              event("error", { turnId: "compact-turn", willRetry: true, error: { message: "fixture transient detail" } });
              event("item/completed", { turnId: "compact-turn", item: { id: "compact-item", type: "contextCompaction" } });
              turn("completed");
            } else if (outcome === "failed") turn("failed");
            else if (outcome === "process-death") exit.resolve();
          }
          if (r.method === "turn/interrupt") { reply({}); turn("interrupted"); }
        });
        return { stdin, stdout, exited: exit.promise, async terminateAndConfirm() { return true; } };
      },
    };
    const appOptions = {
      newChatEngine: "minimax" as const,
      dataDir: dir, launcher: "/never", gatewayUrl: runtime.gatewayUrl,
      allowedOrigins: ["http://localhost"], issueToken: () => "synthetic-fixture-token", revokeToken() {},
      engineFactory: () => { throw Error("Unexpected non-Codex engine"); },
      codexEngineFactory: (o: EngineOptions) => new CodexEngine(o, runtime),
      enginePolicy: { codex: { enabled: true, protocolQualified: true, engineVersion: CODEX_PIN.version, modelPolicyVersion: runtime.modelPolicyVersion } },
    };
    let app = await createApp(appOptions);
    t.after(async () => { await app.app.close(); await rm(dir, { recursive: true, force: true }); });
    const session = await app.broker.createSession(undefined, "codex");
    app.store.setNative(session.id, "thread-1", "codex");
    app.store.addMessage(session.id, "user", "Original accepted requirement: keep 24 V return separate.");
    app.store.addMessage(session.id, "assistant", "Original failed check remains unqualified.");
    const workspace = app.files.workspace(app.store.getSession(session.id).workspaceId);
    await writeFile(join(workspace, "retained.txt"), "Original source evidence\n");
    await app.files.registerArtifact(session.id, "retained.txt", "retained.txt", "text/plain");
    const before = app.store.snapshot(session.id);
    const submit = () => app.app.inject({ method: "POST", headers: { host: "localhost" }, url: `/api/sessions/${session.id}/compact`, payload: { actionId: "retained-action" } });
    const first = await submit();
    assert.equal(first.statusCode, 202);
    for (let i = 0; !requests.some(r => r.method === "thread/compact/start"); i++) {
      assert.ok(i < 1000, "fixture compaction did not dispatch"); await tick();
    }
    if (outcome === "interrupted") await app.broker.cancel(session.id);
    for (let i = 0; !["idle", "failed", "interrupted"].includes(app.store.getSession(session.id).status); i++) {
      assert.ok(i < 1000, "fixture operation did not settle"); await tick();
    }
    const after = app.store.snapshot(session.id);
    // The broker conservatively retains CodexProtocolError as interrupted, even after cleanup.
    const status = outcome === "retry-success" ? "completed" : outcome === "interrupted" ? "cancelled" : "interrupted";
    assert.equal(after.runs[0]!.status, status);
    assert.deepEqual(after.messages, before.messages, "resume history and compaction must not replace visible originals");
    assert.deepEqual(after.artifacts, before.artifacts);
    assert.equal(await readFile(join(workspace, "retained.txt"), "utf8"), "Original source evidence\n");
    assert.equal(app.store.getSession(session.id).nativeSessionId, "thread-1");
    assert.deepEqual(retained, retainedBefore);
    assert.equal(app.store.getSession(session.id).nativeState!.ownership, "idle");
    if (outcome === "retry-success") assert.equal(app.store.getSession(session.id).context!.used, null);
    else assert.ok(after.events.some(e => e.type === "error" && e.data.code === "compaction_failed"));
    await app.app.close();
    app = await createApp(appOptions);
    const duplicate = await submit();
    assert.equal(duplicate.json().runId, first.json().runId);
    assert.equal(app.store.snapshot(session.id).runs[0]!.status, status);
    assert.deepEqual(app.store.snapshot(session.id).messages, before.messages);
    assert.deepEqual(app.store.snapshot(session.id).artifacts, before.artifacts);
    assert.equal(requests.filter(r => r.method === "thread/compact/start").length, 1);
    assert.equal(requests.filter(r => r.method === "thread/resume").length, 1);
    assert.equal(requests.find(r => r.method === "thread/resume").params.excludeTurns, true);
    assert.equal(requests.some(r => r.method === "turn/start"), false);
  });
}

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

const retainedFinal = JSON.parse(readFileSync(new URL('./fixtures/codex/h032-unclassified-final.json', import.meta.url), 'utf8'));
const finalItem = () => ({ type: 'agentMessage', id: retainedFinal.message.payload.id,
  text: retainedFinal.message.payload.content[0].text, phase: null });
const promotion = (f: ReturnType<typeof fixture>) => f.updates.filter(u =>
  u.type === 'phase' && u.phaseSource === 'codex.completed_agent_message+settled_root_turn');
function finishRetained(f: ReturnType<typeof fixture>, override: Record<string, unknown> = {}) {
  const item = finalItem();
  f.item(item.id, item.type, { text: '', phase: null }, 'started');
  f.item(item.id, item.type, { text: item.text, phase: null });
  const turn = { id: 'turn-1', items: [item], itemsView: 'summary', status: 'completed', error: null, ...override };
  return turn;
}
test('H032 retained unclassified native answer is associated only after matching successful turn and settlement', async () => {
  assert.equal(retainedFinal.message.payload.phase, undefined);
  assert.equal(retainedFinal.terminal.payload.last_agent_message, finalItem().text);
  assert.equal(retainedFinal.terminal.payload.error, undefined);
  const proof = deferred<boolean>(), f = fixture({ gateway: () => proof.promise });
  const pending = f.engine.prompt('retained event fixture'); await tick();
  const turn = finishRetained(f);
  f.events('task_complete', retainedFinal.terminal.payload);
  assert.equal(promotion(f).length, 0, 'task_complete alone never associates final');
  f.events('turn/completed', { turn }); f.events('turn/completed', { turn }); await tick();
  assert.equal(promotion(f).length, 0, 'gateway still draining');
  proof.resolve(true); assert.equal(await pending, 'completed');
  assert.deepEqual(promotion(f), [{ type: 'phase', nativeMessageId: finalItem().id,
    nativeTurnId: 'turn-1', channel: 'final', streamState: 'completed',
    phaseSource: 'codex.completed_agent_message+settled_root_turn' }]);
  assert.equal(f.updates.filter(u => u.type === 'text').map(u => u.text).join(''), finalItem().text);
});
for (const mode of ['failed', 'interrupted', 'cancelled', 'incomplete', 'mismatched-turn', 'mismatched-message', 'mismatched-text', 'mismatched-phase', 'duplicate-message', 'conflicting-terminal', 'error', 'unsettled'] as const) {
  test(`retained final is never promoted for ${mode}`, async () => {
    const f = fixture({ gateway: async () => mode !== 'unsettled' });
    const pending = f.engine.prompt('retained rejection fixture');
    const bad = !['interrupted', 'cancelled'].includes(mode);
    const checked = bad ? assert.rejects(pending) : pending;
    await tick(); const turn: any = finishRetained(f);
    if (mode === 'failed' || mode === 'interrupted') turn.status = mode;
    let cancel: Promise<void> | undefined;
    if (mode === 'cancelled') cancel = f.engine.cancel();
    if (mode === 'incomplete') f.item('pending-tool', 'commandExecution', { status: 'inProgress' }, 'started');
    if (mode === 'mismatched-turn') turn.id = 'foreign-turn';
    if (mode === 'mismatched-message') turn.items[0].id = 'foreign-message';
    if (mode === 'mismatched-text') turn.items[0].text = 'different';
    if (mode === 'mismatched-phase') turn.items[0].phase = 'final_answer';
    if (mode === 'duplicate-message') turn.items.push(turn.items[0]);
    if (mode === 'error') turn.error = { message: 'failed' };
    f.events('turn/completed', { turn });
    if (mode === 'conflicting-terminal') f.events('turn/completed', { turn: { ...turn, status: 'failed' } });
    await checked; await cancel;
    assert.equal(promotion(f).length, 0);
    if (mode === 'unsettled') await assert.rejects(f.engine.close()); else await f.engine.close();
  });
}
test('explicit native phases remain authoritative and earlier absent phases stay unknown', async () => {
  for (const explicit of ['commentary', 'final_answer', null]) {
    const f = fixture(), pending = f.engine.prompt('phase fixture'); await tick();
    const first = { id: 'first', type: 'agentMessage', text: 'earlier', phase: null };
    f.item(first.id, first.type, { text: '', phase: null }, 'started'); f.item(first.id, first.type, first);
    const turn: any = finishRetained(f);
    // Keep the terminal and completed item exactly matched for this variant.
    if (explicit !== null) {
      const item = { id: 'explicit', type: 'agentMessage', text: 'explicit', phase: explicit };
      f.item(item.id, item.type, { text: '', phase: explicit }, 'started'); f.item(item.id, item.type, item);
      if (explicit === "final_answer") turn.items = [item];
    }

    f.events('turn/completed', { turn }); await pending;
    assert.equal(promotion(f).length, explicit === 'final_answer' ? 0 : 1);
    assert.ok(f.updates.filter(u => u.type === 'phase' && u.nativeMessageId === 'first').every(u => u.type === 'phase' && u.channel === 'unknown'));
  }
});

test('actual H032 pinned native default terminal summary contains the completed null-phase message', async () => {
  const capture = JSON.parse(readFileSync(new URL('./fixtures/codex/h032-native-null-phase-events.json', import.meta.url), 'utf8'));
  const terminal = capture.events.find((e: any) => e.method === 'turn/completed');
  assert.equal(terminal.params.turn.itemsView, 'summary');
  assert.equal(terminal.params.turn.items.length, 1);
  assert.equal(terminal.params.turn.items[0].phase, null);
  const f = fixture(), pending = f.engine.prompt('actual H032 native capture'); await tick();
  for (const event of capture.events) {
    const p = structuredClone(event.params); p.threadId = 'thread-1';
    if (p.turnId) p.turnId = 'turn-1'; if (p.turn) p.turn.id = 'turn-1';
    f.events(event.method, p);
  }
  assert.equal(await pending, 'completed');
  assert.equal(promotion(f).length, 1);
  assert.equal((promotion(f)[0] as any).nativeMessageId, terminal.params.turn.items[0].id);
});
for (const mode of ['omitted-last', 'reordered', 'empty-summary', 'not-loaded', 'no-items-view'] as const) {
  test(`terminal summary ${mode} cannot associate an earlier or unsupported final`, async () => {
    const f = fixture(), pending = f.engine.prompt('summary integrity');
    const invalid = !['not-loaded', 'no-items-view'].includes(mode);
    const checked = invalid ? assert.rejects(pending) : pending;
    await tick(); const turn: any = finishRetained(f), earlier = turn.items[0];
    const last = { type: 'agentMessage', id: 'later', text: 'later content', phase: null };
    f.item(last.id, last.type, { text: '', phase: null }, 'started'); f.item(last.id, last.type, last);
    if (mode === 'reordered') turn.items = [last, earlier];
    if (mode === 'empty-summary') turn.items = [];
    if (mode === 'not-loaded') { turn.items = []; turn.itemsView = 'notLoaded'; }
    if (mode === 'no-items-view') { turn.items = [last]; delete turn.itemsView; }
    f.events('turn/completed', { turn }); await checked;
    assert.equal(promotion(f).length, 0); await f.engine.close();
  });
}
test('late cancellation during settlement cannot retroactively promote a completed native message', async () => {
  const proof = deferred<boolean>(), f = fixture({ gateway: () => proof.promise });
  const pending = f.engine.prompt('late stop'); await tick();
  f.events('turn/completed', { turn: finishRetained(f) }); await tick();
  const cancelled = f.engine.cancel(); proof.resolve(true);
  await pending; await cancelled; assert.equal(promotion(f).length, 0);
});
test('same-status terminal duplicate with changed summary is conflicting, never a final', async () => {
  const f = fixture(), pending = f.engine.prompt('duplicate conflict'), checked = assert.rejects(pending);
  await tick(); const turn = finishRetained(f);
  f.events('turn/completed', { turn }); f.events('turn/completed', { turn: { ...turn, items: [] } });
  await checked; assert.equal(promotion(f).length, 0); await f.engine.close();
});

const schemaCapture = JSON.parse(readFileSync(new URL('./fixtures/codex/h033-schema-errors.json', import.meta.url), 'utf8'));
function replaySchemaFailures(f: ReturnType<typeof fixture>, count = 3) {
  for (const call of schemaCapture.calls.slice(0, count)) {
    f.item(call.callId, 'mcpToolCall', call.started, 'started');
    f.item(call.callId, 'mcpToolCall', call.completed);
  }
}
test('actual H033 three identical completed schema errors interrupt once and settle before ordinary failure', async () => {
  const proof = deferred<boolean>(), f = fixture({ gateway: () => proof.promise });
  const pending = f.engine.prompt('retained H033 fixture');
  const checked = assert.rejects(pending, (error: any) => error.code === 'native_tool_schema_repetition');
  let done = false; void checked.then(() => { done = true; });
  await tick(); replaySchemaFailures(f);
  assert.equal(f.requests.filter(r => r.method === 'turn/interrupt').length, 1);
  assert.deepEqual(f.requests.find(r => r.method === 'turn/interrupt').params, { threadId: 'thread-1', turnId: 'turn-1' });
  // An ACK without terminal still falls through bounded cancellation to cleanup.
  await new Promise(resolve => setTimeout(resolve, 45));
  assert.equal(done, false); assert.ok(f.calls.includes('gateway-proof'));
  proof.resolve(true); await checked;
  assert.equal(f.states.at(-1)!.ownership, 'idle');
  assert.deepEqual(f.calls.slice(-4), ['terminate', 'revoke-lineage', 'revoke', 'gateway-proof']);
  const trace = f.updates.filter(u => u.type === 'progress' && u.kind === 'tool_schema_error');
  assert.equal(trace.length, 1);
  const receipt = JSON.parse((trace[0] as any).detail);
  assert.deepEqual(receipt.callIds, schemaCapture.calls.map((call: any) => call.callId));
  for (const call of schemaCapture.calls) {
    const event = f.updates.find((u: any) => u.type === 'progress' && u.toolCallId === call.callId && u.status === 'failed') as any;
    assert.deepEqual(JSON.parse(event.detail).result, call.completed.result);
  }
  assert.equal(promotion(f).length, 0); await f.engine.close();
});
for (const interrupt of ['reject', 'timeout'] as const) {
  test(`schema guard still settles after interrupt ${interrupt}`, async () => {
    const f = fixture({ interrupt }), pending = f.engine.prompt('schema stop');
    const checked = assert.rejects(pending, (error: any) => error.code === 'native_tool_schema_repetition');
    await tick(); replaySchemaFailures(f); await checked;
    assert.equal(f.states.at(-1)!.ownership, 'idle');
    assert.equal(f.calls.filter(c => c === 'terminate').length, 1);
  });
}
for (const mode of ['native', 'gateway'] as const) {
  test(`schema guard retains uncertainty when ${mode} settlement fails`, async () => {
    const f = fixture({ terminate: async () => mode !== 'native', gateway: async () => mode !== 'gateway' });
    const pending = f.engine.prompt('schema stop');
    const expected = mode === 'native' ? 'native_cleanup_unconfirmed' : 'gateway_settlement_unconfirmed';
    const checked = assert.rejects(pending, (error: any) => error.cleanupFailure === expected);
    await tick(); replaySchemaFailures(f); f.complete('interrupted'); await checked;
    assert.equal(f.states.at(-1)!.ownership, 'uncertain');
    await assert.rejects(f.engine.close(), (error: any) => error.cleanupFailure === expected);
  });
}
test('native completion racing the schema stop cannot become a successful final', async () => {
  const f = fixture(), pending = f.engine.prompt('schema stop race');
  const checked = assert.rejects(pending, (error: any) => error.code === 'native_tool_schema_repetition');
  await tick(); replaySchemaFailures(f);
  f.events('turn/completed', { turn: finishRetained(f) }); await checked;
  assert.equal(promotion(f).length, 0); assert.equal(f.states.at(-1)!.ownership, 'idle');
});
test('duplicate completions and changed arguments cannot prematurely stop the owned turn', async () => {
  const f = fixture(), pending = f.engine.prompt('schema retry'); await tick();
  replaySchemaFailures(f, 2);
  f.item(schemaCapture.calls[1].callId, 'mcpToolCall', schemaCapture.calls[1].completed);
  const next = structuredClone(schemaCapture.calls[2]);
  next.started.arguments = {}; next.completed.arguments = {}; next.completed.status = 'completed'; next.completed.result = { content: [{ type: 'text', text: 'capabilities' }] };
  f.item(next.callId, 'mcpToolCall', next.started, 'started'); f.item(next.callId, 'mcpToolCall', next.completed);
  assert.equal(f.requests.filter(r => r.method === 'turn/interrupt').length, 0);
  f.complete(); assert.equal(await pending, 'completed');
});
test('user cancellation and an incomplete third call do not produce schema-loop failure', async () => {
  const f = fixture(), pending = f.engine.prompt('cancel incomplete retry'); await tick(); replaySchemaFailures(f, 2);
  f.item(schemaCapture.calls[2].callId, 'mcpToolCall', schemaCapture.calls[2].started, 'started');
  const cancelled = f.engine.cancel(); f.complete('interrupted');
  assert.equal(await pending, 'cancelled'); await cancelled;
  assert.equal(f.updates.some(u => u.type === 'progress' && u.kind === 'tool_schema_error'), false);
});
test('cold resume sends exact reviewed catalog instructions with original thread/history and explicit provenance', async () => {
  const reviewed = await loadCodexResumeInstructions(new URL('../../deploy/run-codex.sh', import.meta.url).pathname);
  const f = fixture({ nativeId: 'thread-1' }); let reads = 0;
  f.runtime.loadResumeInstructions = async () => { reads++; return reviewed; };
  await f.engine.start();
  const resumed = f.requests.find(r => r.method === 'thread/resume');
  assert.equal(reads, 1); assert.equal(resumed.params.threadId, 'thread-1');
  assert.equal(resumed.params.baseInstructions, reviewed.text); assert.equal(resumed.params.model, 'qwen3.8-27b');
  assert.equal(f.requests.some(r => r.method === 'thread/start'), false);
  assert.equal('history' in resumed.params, false);
  assert.equal(f.updates.some(u => u.type === 'text'), false);
  const provenance = f.updates.find(u => u.type === 'progress' && u.kind === 'instruction_refresh') as any;
  assert.deepEqual(JSON.parse(provenance.detail), { nativeThreadId: 'thread-1', source: 'cold_thread_resume.baseInstructions',
    instructionsSha256: reviewed.sha256, toolPolicySha256: reviewed.toolPolicySha256,
    modelPolicyVersion: 'fixture-policy', existingChildrenRefreshed: false });
  const pending = f.engine.prompt('retained follow-up'); await tick(); f.complete(); await pending;
  assert.equal(reads, 1); assert.equal('baseInstructions' in f.requests.find(r => r.method === 'turn/start').params, false);
});
test('fresh threads continue using the mounted catalog without a resume override', async () => {
  const f = fixture(); f.runtime.loadResumeInstructions = async () => { throw Error('fresh path must not load override'); };
  await f.engine.start(); assert.equal('baseInstructions' in f.requests.find(r => r.method === 'thread/start').params, false);
  assert.equal(f.updates.some(u => u.type === 'progress' && u.kind === 'instruction_refresh'), false);
  await f.engine.close();
});
test('tampered reviewed instruction result cannot dispatch a resume or rewrite the retained thread', async () => {
  const reviewed = await loadCodexResumeInstructions(new URL('../../deploy/run-codex.sh', import.meta.url).pathname);
  const f = fixture({ nativeId: 'thread-1' });
  f.runtime.loadResumeInstructions = async () => ({ ...reviewed, text: reviewed.text + 'tamper' });
  await assert.rejects(f.engine.start());
  assert.equal(f.requests.some(r => ['thread/start', 'thread/resume', 'turn/start'].includes(r.method)), false);
  await f.engine.close(); assert.equal(f.states.at(-1)!.ownership, 'idle');
});
test('owned child schema loop stops the parent and settles every unfinished child', async () => {
  const f = fixture({ delegation: true }), pending = f.engine.prompt('child schema loop');
  const checked = assert.rejects(pending, (error: any) => error.code === 'native_tool_schema_repetition');
  await tick();
  f.events('thread/started', { thread: { id: 'child-1', parentThreadId: 'thread-1', modelProvider: 'sova', model: 'qwen3.8-27b' } });
  f.events('turn/started', { threadId: 'child-1', turn: { id: 'child-turn-1', status: 'inProgress' } });
  for (const call of schemaCapture.calls) {
    f.events('item/started', { threadId: 'child-1', turnId: 'child-turn-1', item: call.started });
    f.events('item/completed', { threadId: 'child-1', turnId: 'child-turn-1', item: call.completed });
  }
  f.complete('interrupted'); await checked;
  assert.deepEqual(f.requests.find(r => r.method === 'turn/interrupt').params, { threadId: 'thread-1', turnId: 'turn-1' });
  const trace = f.updates.find(u => u.type === 'progress' && u.kind === 'tool_schema_error') as any;
  assert.equal(trace.subagentId, 'child-1'); assert.equal(JSON.parse(trace.detail).turnId, 'child-turn-1');
  assert.equal(JSON.parse(trace.detail).attempts.length, 3);
  assert.ok(f.updates.some(u => u.type === 'progress' && u.kind === 'subagent' && u.subagentId === 'child-1' && u.status === 'cancelled'));
  assert.equal(f.states.at(-1)!.ownership, 'idle');
});

test('successful native image_status completion emits a typed consumption signal, never prose or failed output', async () => {
  const f=fixture();const pending=f.engine.prompt('existing image status');await tick();
  const value={server:'image',tool:'image_status',arguments:{jobId:'job-one'},status:'completed',result:{content:[{type:'text',text:JSON.stringify({job:{id:'job-one',state:'completed',artifactId:'artifact-one',cancelRequested:false}})}]}};
  f.item('call_a166a1a2f52e487780836616','mcpToolCall',{...value,status:'inProgress'},'started');
  assert.equal(f.updates.filter(u=>u.type==='image_status_result').length,0);
  f.item('call_a166a1a2f52e487780836616','mcpToolCall',value);
  f.item('failed-call','mcpToolCall',{...value,status:'inProgress'},'started');
  f.item('failed-call','mcpToolCall',{...value,result:{...value.result,isError:true}});
  f.item('prose','agentMessage',{text:'',phase:'final_answer'},'started');
  f.item('prose','agentMessage',{text:value.result.content[0].text,phase:'final_answer'});
  f.complete();await pending;
  assert.deepEqual(f.updates.filter(u=>u.type==='image_status_result'),[{type:'image_status_result',toolCallId:'call_a166a1a2f52e487780836616',jobId:'job-one',artifactId:'artifact-one'}]);
  await f.engine.close();
});

// H040 source fixtures only: no native process, provider request or Linux attestation.
function originalCall(f: ReturnType<typeof fixture>, args: Record<string, unknown> = {reference:'old-1',offset:0,limit:8192}, callId='original-call') {
 f.item(callId,'dynamicToolCall',{namespace:null,tool:'read_original',arguments:args,status:'inProgress',contentItems:null,success:null},'started');
 f.stdout.write(JSON.stringify({id:'server-'+callId,method:'item/tool/call',params:{threadId:'thread-1',turnId:'turn-1',callId,namespace:null,tool:'read_original',arguments:args}})+'\n');
}
test('isolated probe registers only on a fresh receipt-qualified ephemeral thread; actual read needs canonical item consumption',async()=>{
 const f=fixture({probe:true});await f.engine.start();
 assert.equal(f.requests.find(x=>x.method==='initialize').params.capabilities.experimentalApi,true);
 const thread=f.requests.find(x=>x.method==='thread/start');assert.equal(thread.params.ephemeral,true);assert.equal(thread.params.sandbox,'read-only');assert.equal(thread.params.dynamicTools[0].name,'read_original');assert.equal(thread.params.baseInstructions,'Host-authored isolated recovery probe');
 const pending=f.engine.prompt('host-approved question');await tick();originalCall(f);await tick();await tick();
 const response=f.requests.find(x=>x.id==='server-original-call');assert.equal(response.result.success,true);assert.equal(response.result.contentItems[0].text,'retained original requirement');assert.ok(!f.calls.includes('read-consumed'));
 f.item('original-call','dynamicToolCall',{namespace:null,tool:'read_original',arguments:{reference:'old-1',offset:0,limit:8192},status:'completed',contentItems:response.result.contentItems,success:true});assert.ok(f.calls.includes('read-consumed'));
 f.complete();assert.equal(await pending,'completed');assert.ok(f.calls.includes('settlement-receipt'));assert.ok(f.calls.includes('gateway-proof'));
 assert.ok(f.updates.filter(x=>x.type==='context').every(x=>x.type!=='context'||x.used===null));
});
for(const receipts of ['missing','tampered'] as const) test('probe refuses '+receipts+' host launch receipt before initialization',async()=>{
 const f=fixture({probe:true,receipts});await assert.rejects(f.engine.start(),/receipt unavailable/);assert.equal(f.requests.length,0);await f.engine.close().catch(()=>undefined);
});
test('probe cannot activate saved tools on an existing native thread or enable delegation',()=>{
 assert.throws(()=>fixture({probe:true,nativeId:'old-native'}),/fresh receipt/);assert.throws(()=>fixture({probe:true,delegation:true}),/fresh receipt/);
});
test('probe rejects observed native sandbox mismatch while model scope remains separately unqualified',async()=>{
 const f=fixture({probe:true,probeSandboxMismatch:true});await assert.rejects(f.engine.start(),/trusted model policy mismatch/);await f.engine.close();
});
test('ordinary production chat has no dynamic registration or experimental opt-in',async()=>{
 const f=fixture();await f.engine.start();assert.equal(f.requests.find(x=>x.method==='initialize').params.capabilities.experimentalApi,false);assert.equal(f.requests.find(x=>x.method==='thread/start').params.dynamicTools,undefined);await f.engine.close();
});
test('unknown original reference returns bounded failure, consumed only by canonical failed item',async()=>{
 const f=fixture({probe:true});const pending=f.engine.prompt('question');await tick();originalCall(f,{reference:'file:///host/oracle',offset:0,limit:1});await tick();await tick();
 const response=f.requests.find(x=>x.id==='server-original-call');assert.equal(response.result.success,false);assert.equal(response.result.contentItems[0].text,'Original excerpt unavailable within this frozen scope');
 f.item('original-call','dynamicToolCall',{namespace:null,tool:'read_original',arguments:{reference:'file:///host/oracle',offset:0,limit:1},status:'failed',contentItems:response.result.contentItems,success:false});f.complete();assert.equal(await pending,'completed');
});
for(const mode of ['wrong-thread','no-start','early-completion','changed-completion','duplicate-start'] as const) test('probe rejects unowned or unsettled dynamic lifecycle '+mode,async()=>{
 const f=fixture({probe:true});const pending=f.engine.prompt('question');const rejected=assert.rejects(pending);await tick();
 const args={reference:'old-1',offset:0,limit:8};
 if(mode==='wrong-thread'||mode==='no-start') f.stdout.write(JSON.stringify({id:'call',method:'item/tool/call',params:{threadId:mode==='wrong-thread'?'unowned':'thread-1',turnId:'turn-1',callId:'original-call',namespace:null,tool:'read_original',arguments:args}})+'\n');
 else if(mode==='early-completion') {f.item('original-call','dynamicToolCall',{namespace:null,tool:'read_original',arguments:args,status:'inProgress'},'started');f.item('original-call','dynamicToolCall',{namespace:null,tool:'read_original',arguments:args,status:'completed',contentItems:[{type:'inputText',text:'fabricated'}],success:true});}
 else if(mode==='duplicate-start'){originalCall(f,args);f.item('original-call','dynamicToolCall',{namespace:null,tool:'read_original',arguments:{...args,offset:1},status:'inProgress'},'started');}
 else {originalCall(f,args);await tick();await tick();f.item('original-call','dynamicToolCall',{namespace:null,tool:'read_original',arguments:args,status:'completed',contentItems:[{type:'inputText',text:'fabricated'}],success:true});}
 await rejected;assert.ok(!f.calls.includes('read-consumed'));await f.engine.close();assert.ok(f.calls.includes('terminate'));
});
test('turn completion cannot substitute for an unfinished dynamic read',async()=>{
 const f=fixture({probe:true});const pending=f.engine.prompt('question');const rejected=assert.rejects(pending);await tick();originalCall(f);await tick();f.complete();await rejected;assert.ok(!f.calls.includes('read-consumed'));
});

test('pinned optional namespace can be omitted; conflicting namespace stays rejected',async()=>{
 for (const namespace of [undefined,'oracle']) {
  const f=fixture({probe:true});const pending=f.engine.prompt('question');const rejection=namespace ? assert.rejects(pending) : undefined;await tick();
  const args={reference:'old-1',offset:0,limit:8};f.item('original-call','dynamicToolCall',{tool:'read_original',arguments:args,status:'inProgress'},'started');
  f.stdout.write(JSON.stringify({id:'optional-ns',method:'item/tool/call',params:{threadId:'thread-1',turnId:'turn-1',callId:'original-call',...(namespace?{namespace}:{}),tool:'read_original',arguments:args}})+'\n');await tick();await tick();
  if(namespace){await rejection;assert.equal(f.requests.find(x=>x.id==='optional-ns'),undefined);await f.engine.close();}
  else {const response=f.requests.find(x=>x.id==='optional-ns').result;f.item('original-call','dynamicToolCall',{tool:'read_original',arguments:args,status:'completed',contentItems:response.contentItems,success:true});f.complete();assert.equal(await pending,'completed');}
 }
});

test("H041 synthetic text-only parent sends consumed native config without changing ordinary defaults", async () => {
  const f = fixture({textOnly:true}); await f.engine.start();
  const start = f.requests.find(x => x.method === "thread/start").params;
  assert.equal(start.sandbox, "read-only"); assert.equal(start.ephemeral, false);
  assert.deepEqual(start.environments, []); assert.equal(start.config["features.shell_tool"], false);
  assert.equal(start.config["tools.experimental_request_user_input.enabled"], false);
  assert.equal(start.config["mcp_servers.search.enabled"], false);
  assert.equal(start.dynamicTools, undefined); assert.ok(f.calls.includes("thread-policy"));
  await assert.rejects(f.engine.prompt("synthetic", [{path:"/arbitrary",mimeType:"image/png",name:"x"}]), /attachments/);
  await f.engine.close();
});
test("H041 synthetic rejected admission never dispatches a native turn", async () => {
  const f=fixture({textOnly:true,admission:async()=>{throw Error("observed tools gate rejected");}});
  await assert.rejects(f.engine.prompt("synthetic"), /gate rejected/);
  assert.equal(f.requests.filter(x=>x.method==="turn/start").length,0); await f.engine.close();
});
test("H041 synthetic late original admission cannot publish after close", async () => {
  const gate=deferred<void>(); const f=fixture({probe:true,originalAdmission:()=>gate.promise});
  const pending=f.engine.prompt("synthetic"); const rejected=assert.rejects(pending); await tick();
  originalCall(f); await tick(); await f.engine.close(); gate.resolve(); await tick(); await rejected;
  assert.equal(f.requests.filter(x=>x.id==="server-original-call").length,0); assert.ok(!f.calls.includes("read-consumed"));
});

test("H041 synthetic bounded artifact registration needs canonical native consumption",async()=>{
  const f=fixture({artifacts:true});const pending=f.engine.prompt("synthetic");await tick();
  const params=f.requests.find(x=>x.method==="thread/start").params;
  assert.equal(params.sandbox,"read-only");assert.deepEqual(params.environments,[]);
  assert.deepEqual(params.dynamicTools.map((x:{name:string})=>x.name),["write_checkpoint_artifact"]);
  const args={name:"recall.json",json:'{"retained":true}'};
  f.item("artifact-call","dynamicToolCall",{tool:"write_checkpoint_artifact",arguments:args,status:"inProgress"},"started");
  f.stdout.write(JSON.stringify({id:"server-artifact",method:"item/tool/call",params:{threadId:"thread-1",turnId:"turn-1",callId:"artifact-call",tool:"write_checkpoint_artifact",arguments:args}})+"\n");await tick();await tick();
  const response=f.requests.find(x=>x.id==="server-artifact").result;
  assert.equal(response.success,true);assert.ok(f.calls.includes("artifact-registered"));assert.ok(!f.calls.includes("artifact-consumed"));
  f.item("artifact-call","dynamicToolCall",{tool:"write_checkpoint_artifact",arguments:args,status:"completed",contentItems:response.contentItems,success:true});
  assert.ok(f.calls.includes("artifact-consumed"));f.complete();assert.equal(await pending,"completed");
});
test("H041 synthetic artifact registrar cannot claim a different byte digest",async()=>{
  const f=fixture({artifacts:true,registerArtifact:async()=>({artifactId:"fixture",sha256:"wrong"})});
  const pending=f.engine.prompt("synthetic");const rejected=assert.rejects(pending);await tick();
  const args={name:"state.json",json:"{}"};f.item("a","dynamicToolCall",{tool:"write_checkpoint_artifact",arguments:args,status:"inProgress"},"started");
  f.stdout.write(JSON.stringify({id:"server-a",method:"item/tool/call",params:{threadId:"thread-1",turnId:"turn-1",callId:"a",tool:"write_checkpoint_artifact",arguments:args}})+"\n");
  await rejected;assert.ok(!f.calls.includes("artifact-consumed"));await f.engine.close();
});
test("H041 synthetic observed builtin tool violates text-only parent policy",async()=>{
  const f=fixture({textOnly:true});const pending=f.engine.prompt("synthetic");const rejected=assert.rejects(pending);await tick();
  f.item("shell","commandExecution",{command:"synthetic"},"started");await rejected;await f.engine.close();
});

test("H041 synthetic manual compaction requires method-aware admission before RPC",async()=>{
 const f=fixture({textOnly:true,admission:async()=>{throw Error("compaction gate rejected");}});
 await assert.rejects(f.engine.compact(),/compaction gate rejected/);
 assert.equal(f.requests.filter(x=>x.method==="thread/compact/start").length,0);await f.engine.close();
});
