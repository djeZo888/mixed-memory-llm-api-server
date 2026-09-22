#!/usr/bin/env node
// Protocol fixture only: no inference, no MiniMax runtime, no network requests.
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
      await save({ method: "resume", params });
      return {};
    },
    async loadSession(params) {
      id = params.sessionId;
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
      const text = params.prompt
        .map((block) => (block.type === "text" ? block.text : ""))
        .join("");
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
        if (text === "children" || text === "background")
          setTimeout(() => {
            children[0].status = "completed";
          }, 350);
      }
      return { stopReason: "end_turn" };
    },
    async cancel(params) {
      await save({ method: "cancel", params });
      resolvePrompt?.({ stopReason: "cancelled" });
    },
    async closeSession(params) {
      await save({ method: "close", params });
      return {};
    },
    async extMethod(method, params) {
      await save({ method, params });
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
