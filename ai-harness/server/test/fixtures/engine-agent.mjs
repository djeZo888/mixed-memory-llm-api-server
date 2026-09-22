#!/usr/bin/env node
// Protocol fixture only: no inference, no MiniMax runtime, no network requests.
import { randomUUID } from "node:crypto";
import { readFile, writeFile, rename } from "node:fs/promises";
import { join } from "node:path";
import { Readable, Writable } from "node:stream";
import * as acp from "@agentclientprotocol/sdk";
const args = process.argv.slice(2);
if (
  args.length !== 4 ||
  args[0] !== "--profile-dir" ||
  args[2] !== "--workspace"
)
  process.exit(3);
const profile = args[1];
const workspace = args[3];
const config = JSON.parse(
  await readFile(join(profile, "fixture.json"), "utf8"),
);
const calls = [];
let writes = Promise.resolve();
const save = async (value) => {
  calls.push(value);
  const body = JSON.stringify(calls);
  writes = writes.then(async () => {
    await writeFile(join(profile, "calls.next.json"), body);
    await rename(join(profile, "calls.next.json"), join(profile, "calls.json"));
  });
  await writes;
};
await save({
  method: "launch",
  argv: args,
  upstreamKeyFileInherited: Boolean(process.env.AI_HARNESS_INFERENCE_KEY_FILE),
  inheritedSecret: Boolean(process.env.AI_HARNESS_TEST_SECRET),
  gatewayPresent: Boolean(process.env.AI_HARNESS_GATEWAY_TOKEN),
  home: process.env.HOME,
  dataDir: process.env.MINIMAX_DATA_DIR,
  proxyInherited: Boolean(process.env.HTTPS_PROXY),
  authSocketInherited: Boolean(process.env.SSH_AUTH_SOCK),
  containerHostInherited: Boolean(process.env.CONTAINER_HOST),
  nodeOptionsInherited: Boolean(process.env.NODE_OPTIONS),
});
process.stderr.write(
  `fixture startup ${process.env.AI_HARNESS_GATEWAY_TOKEN.slice(0, 10)}`,
);
setTimeout(
  () =>
    process.stderr.write(
      `${process.env.AI_HARNESS_GATEWAY_TOKEN.slice(10)} ready\n`,
    ),
  5,
);
let shutdownKeepalive;
if (config.ignoreTerm) shutdownKeepalive = setInterval(() => {}, 1000);
process.on("SIGTERM", () => {
  shutdownKeepalive ??= setInterval(() => {}, 1000);
  void save({ method: "signal", signal: "SIGTERM" }).then(() => {
    if (config.ignoreTerm) return;
    setTimeout(() => {
      void save({
        method: "cleanup",
        verified: config.exitCode === undefined || config.exitCode === 0,
      }).then(() => process.exit(config.exitCode ?? 0));
    }, config.shutdownDelay ?? 0);
  });
});
let id;
const instanceId = randomUUID();
let runId = null;
let rootTurnIds = [];
let state = "unknown";
let runCount = 0;
let promptDelivered = false;
const currentReceipt = () => ({
  schemaVersion: 1,
  instanceId,
  rootSessionId: id,
  runId,
  exhaustive: state !== "unknown",
  state,
  rootTurnIds: [...rootTurnIds],
  reasons: state === "unknown" ? ["no_current_run"] : [],
});
const altered = (receipt, mode) => {
  if (mode === "missing") return undefined;
  if (mode === "unknown")
    return {
      ...receipt,
      state: "unknown",
      exhaustive: false,
      reasons: ["inspection_failed"],
    };
  if (mode === "running")
    return {
      ...receipt,
      state: "running",
      reasons: ["acp_projection_pending"],
    };
  if (mode === "stale") return { ...receipt, instanceId: randomUUID() };
  if (mode === "foreign") return { ...receipt, rootSessionId: "foreign-root" };
  if (mode === "run")
    return { ...receipt, runId: "foreign-run", rootTurnIds: ["foreign-run"] };
  if (mode === "duplicate")
    return { ...receipt, rootTurnIds: [receipt.runId, receipt.runId] };
  if (mode === "empty-turns") return { ...receipt, rootTurnIds: [] };
  if (mode === "wrong-first") return { ...receipt, rootTurnIds: ["other-turn"] };
  if (mode === "null-run") return { ...receipt, runId: null, rootTurnIds: [] };
  if (mode === "nonexhaustive") return { ...receipt, exhaustive: false };
  if (mode === "reasons") return { ...receipt, reasons: ["pending_delivery"] };
  if (mode === "malformed") return { schemaVersion: 1 };
  return receipt;
};
const promptResponse = (stopReason) => {
  state = stopReason === "cancelled" ? "cancelled" : "settled";
  promptDelivered = true;
  const receipt = altered(currentReceipt(), config.promptReceipt);
  return {
    stopReason,
    ...(receipt ? { _meta: { "minimax-code/settlement": receipt } } : {}),
  };
};

let resolvePrompt;
let children = [];
let connection;
const update = (body) =>
  connection.sessionUpdate({ sessionId: id, update: body });
const delegation = () => ({
  schemaVersion: 1,
  rootSessionId: id,
  members: children,
});
connection = new acp.AgentSideConnection(
  () => ({
    async initialize(params) {
      await save({ method: "initialize", params });
      if (config.initDelay)
        await new Promise((resolve) => setTimeout(resolve, config.initDelay));
      return {
        protocolVersion: acp.PROTOCOL_VERSION,
        agentCapabilities: {
          loadSession: config.restore !== "none",
          sessionCapabilities: {
            ...(config.restore === "load" || config.restore === "none"
              ? {}
              : { resume: {} }),
            close: {},
          },
          promptCapabilities: { image: false, embeddedContext: false },
        },
        _meta: {
          "minimax-code/extensions": {
            version: 1,
            notifications: ["mcode/session/compaction_update"],
            methods: config.noDelegation
              ? []
              : [
                  "mcode/session/delegation/get",
                  "mcode/session/delegation/stop",
                  ...(config.noSettlement
                    ? []
                    : ["mcode/session/settlement/get"]),
                ],
          },
        },
      };
    },
    async newSession(params) {
      id = "native-fixture-session";
      await save({ method: "new", params });
      return { sessionId: id };
    },
    async resumeSession(params) {
      id = params.sessionId;
      if (!config.restoreUnknown) {
        runId = "restored-run";
        rootTurnIds = [runId];
        state = "settled";
      }
      await save({ method: "resume", params });
      return {};
    },
    async loadSession(params) {
      id = params.sessionId;
      if (!config.restoreUnknown) {
        runId = "restored-run";
        rootTurnIds = [runId];
        state = "settled";
      }
      await save({ method: "load", params });
      await update({
        sessionUpdate: "agent_message_chunk",
        content: { type: "text", text: "historical replay must be ignored" },
      });
      return {};
    },
    async setSessionConfigOption(params) {
      await save({ method: "config", params });
      return {
        configOptions: [
          {
            type: "select",
            id: "permissionMode",
            name: "Permission",
            currentValue: config.badPolicy ? "bypassPermissions" : "default",
            options: [{ value: "default", name: "Default" }],
          },
        ],
      };
    },
    async prompt(params) {
      await save({ method: "prompt", params });
      runCount++;
      runId = `run-${config.repeatRunId ? 1 : runCount}`;
      rootTurnIds = [runId];
      state = "running";
      promptDelivered = false;
      const text =
        params.prompt
          .map((block) => (block.type === "text" ? block.text : ""))
          .at(-1) ?? "";
      if (text === "early-stop") {
        rootTurnIds = [];
        const pending = new Promise((resolve) => { resolvePrompt = resolve; });
        await save({ method: "before-root-admission", runId });
        return await pending;
      }
      if (text === "crash") {
        setTimeout(() => process.exit(12), 5);
        return await new Promise(() => {});
      }
      if (text === "wait")
        return await new Promise((resolve) => {
          resolvePrompt = resolve;
        });
      if (text === "gateway") {
        const url = new URL(
          process.env.AI_HARNESS_GATEWAY_URL + "/chat/completions",
        );
        if (url.protocol !== "http:" || url.hostname !== "127.0.0.1")
          throw new Error("Fixture gateway must be IPv4 loopback");
        const response = await fetch(url, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${process.env.AI_HARNESS_GATEWAY_TOKEN}`,
          },
          body: JSON.stringify({
            model: "qwen3.8-27b",
            messages: [{ role: "user", content: "fixture inference" }],
            max_tokens: 17,
            stream: false,
          }),
        });
        if (!response.ok)
          throw new Error(`Fixture gateway failed: ${response.status}`);
        const body = await response.json();
        const text = body.choices?.[0]?.message?.content;
        if (typeof text !== "string")
          throw new Error("Invalid fixture gateway completion");
        await update({
          sessionUpdate: "agent_message_chunk",
          content: { type: "text", text },
        });
      }
      if (text === "compaction") {
        const base = {
          schemaVersion: 1,
          sessionId: id,
          compactionId: "cmp-1",
          estimated: true,
          tokensBefore: 420000,
        };
        for (const body of [
          { ...base, status: "start" },
          { ...base, status: "completed", tokensAfter: 12000 },
          { ...base, status: "completed", tokensAfter: 12000 },
          { ...base, compactionId: "cmp-2", status: "start" },
          { ...base, compactionId: "cmp-2", status: "failed" },
          {
            ...base,
            sessionId: "foreign-session",
            compactionId: "cmp-3",
            status: "start",
          },
          { ...base, compactionId: "cmp-3", status: "start", tokensAfter: -1 },
          { ...base, compactionId: "cmp-3", status: "start", estimated: false },
          { ...base, compactionId: "../bad", status: "start" },
          {
            ...base,
            compactionId: "cmp-3",
            status: "completed",
            error: "forbidden payload",
          },
          { ...base, compactionId: "cmp-3", status: "unknown" },
        ])
          await connection.extNotification(
            "mcode/session/compaction_update",
            body,
          );
      }
      if (text === "bash-background") {
        await update({
          sessionUpdate: "tool_call",
          toolCallId: "bash-bg",
          title: "bash",
          name: "bash",
          kind: "execute",
          status: "completed",
          rawOutput: {
            details: { status: "auto_promoted", task_id: "bg-shell" },
          },
        });
      }
      if (text === "shell-policy") {
        const inputs = [
          {
            name: "bash",
            rawInput: { command: "bash build.sh | tee output.log" },
          },
          {
            name: "bash",
            rawInput: { command: 'printf "%s" "$(node script.js)"' },
          },
          { name: "bash", rawInput: { command: "npm exec tsc" } },
          {
            name: "bash",
            rawInput: {
              command: "python /opt/ai-harness/tools/render_pdf.py input.pdf",
            },
          },
          {
            name: "bash",
            rawInput: { command: "pwd", run_in_background: true },
          },
          { name: "bash", rawInput: { command: 42 } },
          { name: "bash", rawInput: { command: "pwd", cwd: "/etc" } },
          { name: "unknown_shell", rawInput: { command: "pwd" } },
          { name: "bash", rawInput: { command: "pwd", timeout: "5" } },
        ];
        for (const [index, input] of inputs.entries()) {
          const result = await connection.requestPermission({
            sessionId: id,
            toolCall: { toolCallId: `shell-${index}`, title: "bash", ...input },
            options: [
              { optionId: "yes", kind: "allow_once", name: "Allow" },
              { optionId: "no", kind: "reject_once", name: "Reject" },
            ],
          });
          await save({ method: "shell_permission", index, result });
        }
      }
      if (text === "permissions") {
        const queries = [
          {
            name: "write",
            rawInput: { path: join(workspace, "output.txt"), content: "local" },
          },
          {
            name: "write",
            rawInput: {
              path: join(workspace, "..", "escape.txt"),
              content: "outside",
            },
          },
          { name: "bash", rawInput: { command: "npm test" } },
          { name: "bash", rawInput: { command: "git push origin main" } },
          { name: "send_message", rawInput: { text: "publish me" } },
          {
            name: "write",
            rawInput: {
              path: join(workspace, "link", "secret"),
              content: "outside",
            },
          },
        ];
        for (let index = 0; index < queries.length; index++) {
          const result = await connection.requestPermission({
            sessionId: id,
            toolCall: {
              toolCallId: String(index),
              title: "safe local write",
              ...queries[index],
            },
            options: [
              { optionId: "yes", kind: "allow_once", name: "Allow once" },
              { optionId: "no", kind: "reject_once", name: "Reject once" },
            ],
          });
          await save({ method: "permission_result", index, result });
        }
      }
      if (text === "token-output") {
        for (const part of [
          process.env.AI_HARNESS_GATEWAY_TOKEN.slice(0, 10),
          process.env.AI_HARNESS_GATEWAY_TOKEN.slice(10),
        ])
          await update({
            sessionUpdate: "agent_message_chunk",
            content: { type: "text", text: part },
          });
      }
      await update({
        sessionUpdate: "agent_thought_chunk",
        content: {
          type: "text",
          text: "private reasoning that must never be progress",
        },
      });
      await update({
        sessionUpdate: "agent_message_chunk",
        content: { type: "text", text: "fixture response" },
      });
      await update({
        sessionUpdate: "tool_call",
        toolCallId: "tool-1",
        title: "read",
        name: "read",
        kind: "read",
        status: "in_progress",
      });
      await update({
        sessionUpdate: "tool_call_update",
        toolCallId: "tool-1",
        status: "completed",
        content: [
          {
            type: "content",
            content: { type: "text", text: "X".repeat(5000) },
          },
        ],
      });
      await update({
        sessionUpdate: "usage_update",
        used: 12345,
        size: config.wrongContext ? 32000 : 480000,
      });
      if (
        text === "children" ||
        text === "children-cancel" ||
        text === "background"
      ) {
        children = [
          {
            sessionId: "child-1",
            parentSessionId: id,
            status: "running",
            task: "Fixture local child",
            agentName: "worker",
            ...(text === "background"
              ? { backgroundTaskId: "native-background-task" }
              : {}),
          },
        ];
        await connection.extNotification("mcode/session/delegation_update", {
          sessionId: id,
          snapshot: delegation(),
        });
        if (text === "children-cancel")
          return await new Promise((resolve) => {
            resolvePrompt = resolve;
          });
        await new Promise((resolve) => setTimeout(resolve, 350));
        children[0].status = "completed";
        await connection.extNotification("mcode/session/delegation_update", {
          sessionId: id,
          snapshot: delegation(),
        });
        if (text === "background") {
          await connection.sessionUpdate({
            sessionId: "child-1",
            update: {
              sessionUpdate: "agent_message_chunk",
              content: { type: "text", text: "CHILD TEXT MUST NEVER PROJECT" },
            },
          });
          rootTurnIds.push(`${runId}-continuation`);
          await update({
            sessionUpdate: "agent_message_chunk",
            content: { type: "text", text: " root continuation one" },
          });
          await update({
            sessionUpdate: "agent_message_chunk",
            content: { type: "text", text: " root continuation two" },
          });
        }
      }
      if (config.nativeCancelled) return promptResponse("cancelled");
      if (config.lateText)
        setTimeout(() => {
          void update({
            sessionUpdate: "agent_message_chunk",
            content: { type: "text", text: "late forbidden text" },
          });
        }, 25);
      return promptResponse("end_turn");
    },
    async cancel(params) {
      // Deterministic Stop-before-admission fixture: publish cancellation before
      // yielding to the client's concurrent fresh settlement query.
      if (runId !== null && rootTurnIds.length === 0 && !config.ignoreStop)
        state = "cancelled";
      await save({ method: "cancel", params });
      if (config.ignoreStop) return;
      if (runId !== null) state = "cancelled";
      for (const child of children) child.status = "stopped";
      await connection.extNotification("mcode/session/delegation_update", {
        sessionId: id,
        snapshot: delegation(),
      });
      resolvePrompt?.(promptResponse("cancelled"));
    },
    async closeSession(params) {
      await save({ method: "close", params });
      if (config.ignoreStop) return await new Promise(() => {});
      return {};
    },
    async extMethod(method, params) {
      await save({ method, params });
      if (method === "mcode/session/settlement/get") {
        let receipt = currentReceipt();
        if (runId === null && config.initialRunning)
          receipt = {
            ...receipt,
            state: "running",
            exhaustive: true,
            reasons: ["acp_projection_pending"],
          };
        if (
          (params.instanceId && params.instanceId !== instanceId) ||
          (params.runId && params.runId !== runId)
        )
          receipt = {
            ...receipt,
            state: "unknown",
            exhaustive: false,
            reasons: ["stale_expectation"],
          };
        if (promptDelivered)
          receipt = altered(
            receipt,
            config.freshReceipt ??
              (config.badSnapshot ? "malformed" : undefined),
          );
        if (config.ignoreStop && runId && state === "cancelled")
          receipt = {
            ...receipt,
            state: "running",
            reasons: ["acp_projection_pending"],
          };
        return { receipt };
      }
      if (method === "mcode/session/delegation/get")
        return { snapshot: config.badSnapshot ? {} : delegation() };
      if (method === "mcode/session/delegation/stop") {
        if (config.ignoreStop) return await new Promise(() => {});
        for (const child of children) child.status = "stopped";
        return {
          receipt: {
            schemaVersion: 1,
            rootSessionId: id,
            rootStopped: true,
            activeSessionIds: [],
            failedSessionIds: [],
            stoppedSessionIds: children.map((child) => child.sessionId),
          },
        };
      }
      throw acp.RequestError.methodNotFound(method);
    },
  }),
  acp.ndJsonStream(
    Writable.toWeb(process.stdout),
    Readable.toWeb(process.stdin),
  ),
);
await connection.closed;
