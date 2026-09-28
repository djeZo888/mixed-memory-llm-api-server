import assert from "node:assert/strict";
import test from "node:test";
import { createServer } from "node:http";
import { mkdtemp, rm } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { PassThrough } from "node:stream";
import { createApp } from "../src/app.js";
import { codexDeployment } from "../src/codex-deployment.js";
import { CODEX_PIN, type CodexRuntime } from "../src/codex-engine.js";

test("two loopback HTTP fixture requests use fresh live tokens, resume native history and replay browser events without inference", async (t) => {
  const alive = new Set<string>(),
    observed: string[] = [],
    resumes: string[] = [];
  let token = 0,
    turn = 0;
  const server = createServer((request, response) => {
    const auth = request.headers.authorization ?? "";
    observed.push(auth);
    response.writeHead(alive.has(auth) ? 200 : 401);
    response.end("fixture only");
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address() as { port: number };
  const dir = await mkdtemp(join(tmpdir(), "h021-followup-"));
  const runtime: CodexRuntime = {
    pin: CODEX_PIN,
    protocolQualified: true,
    modelPolicyVersion: "fixture-policy",
    model: "qwen3.8-27b",
    provider: "sova",
    contextLimit: 480000,
    gatewayUrl: "http://10.0.2.2:8081/codex/v1",
    async launchRootless(input) {
      const stdin = new PassThrough(),
        stdout = new PassThrough();
      const threadId = `native-${input.sessionId}`;
      const emit = (value: unknown) =>
        stdout.write(JSON.stringify(value) + "\n");
      stdin.on("data", (bytes) => {
        void (async () => {
          const r = JSON.parse(bytes.toString());
          if (r.method === "initialize")
            emit({
              id: r.id,
              result: {
                userAgent: "codex/0.158.0",
                codexHome: input.codexHome,
                platformOs: "linux",
                platformFamily: "unix",
              },
            });
          if (r.method === "thread/start" || r.method === "thread/resume") {
            if (r.method === "thread/resume") resumes.push(r.params.threadId);
            emit({
              id: r.id,
              result: {
                thread: { id: threadId },
                model: "qwen3.8-27b",
                modelProvider: "sova",
                cwd: input.workspace,
                approvalPolicy: "never",
              },
            });
          }
          if (r.method === "turn/start") {
            const turnId = `turn-${++turn}`;
            emit({ id: r.id, result: { turn: { id: turnId } } });
            emit({
              method: "turn/started",
              params: { threadId, turn: { id: turnId, status: "inProgress" } },
            });
            const result = await fetch(
              `http://127.0.0.1:${address.port}/fixture`,
              {
                method: "POST",
                headers: { authorization: `Bearer ${input.gatewayToken}` },
                body: "offline fixture, no inference",
              },
            );
            assert.equal(result.status, 200);
            await result.text();
            const item = {
              id: `message-${turnId}`,
              type: "agentMessage",
              phase: "final_answer",
              text: "retained fixture summary",
            };
            emit({
              method: "item/started",
              params: { threadId, turnId, item: { ...item, text: "" } },
            });
            emit({
              method: "item/agentMessage/delta",
              params: { threadId, turnId, itemId: item.id, delta: "partial " },
            });
            emit({
              method: "item/agentMessage/delta",
              params: { threadId, turnId, itemId: item.id, delta: "partial " },
            });
            emit({
              method: "item/completed",
              params: { threadId, turnId, item },
            });
            emit({
              method: "turn/completed",
              params: { threadId, turn: { id: turnId, status: "completed" } },
            });
          }
        })().catch((error) => stdout.destroy(error));
      });
      return {
        stdin,
        stdout,
        exited: new Promise<void>(() => {}),
        async terminateAndConfirm() {
          return true;
        },
      };
    },
    revokeGatewaySession() {
      alive.clear();
    },
    async confirmGatewaySettlement(input) {
      return !alive.has(`Bearer ${input.gatewayToken}`);
    },
  };
  const options = {
    dataDir: dir,
    allowedOrigins: ["http://localhost"],
    launcher: "/never",
    gatewayUrl: "http://127.0.0.1:1/v1",
    engineFactory: () => {
      throw new Error("MiniMax must not receive a Codex native ID");
    },
    issueToken: () => {
      const id = `fixture-token-${++token}`;
      alive.add(`Bearer ${id}`);
      return id;
    },
    revokeToken: (id: string) => {
      alive.delete(`Bearer ${id}`);
    },
    ...codexDeployment({ enablePreview: true, runtime }),
  };
  const app = await createApp(options);
  t.after(async () => {
    await app.app.close();
    await new Promise<void>((resolve) => server.close(() => resolve()));
    await rm(dir, { recursive: true, force: true });
  });
  const session = await app.broker.createSession(undefined, "codex");
  app.broker.enqueue(session.id, "message", "first");
  await app.broker.idle();
  app.broker.enqueue(session.id, "message", "follow up");
  await app.broker.idle();
  assert.deepEqual(observed, [
    "Bearer fixture-token-1",
    "Bearer fixture-token-2",
  ]);
  assert.deepEqual(resumes, [`native-${session.id}`]);
  assert.equal(alive.size, 0);
  const snap = app.store.snapshot(session.id);
  assert.equal(
    snap.runs.every((r) => r.status === "completed"),
    true,
  );
  assert.deepEqual(
    snap.messages.filter((m) => m.role === "user").map((m) => m.content),
    ["first", "follow up"],
  );
  assert.deepEqual(
    snap.messages.filter((m) => m.role === "assistant").map((m) => m.content),
    ["retained fixture summary", "retained fixture summary"],
  );
  assert.equal(
    snap.events.filter((e) => e.type === "assistant_delta").length,
    4,
  );
  app.store.snapshot(session.id);
  app.store.allEvents(session.id);
  assert.equal(observed.length, 2); // Refresh/reconnect never dispatches a prompt.
  app.broker.enqueue(session.id, "handoff", "summarize");
  await app.broker.idle();
  const next = app.store.listSessions().find((s) => s.id !== session.id)!;
  assert.equal(next.engineKind, "codex");
  assert.equal(
    app.store.getSession(next.id).workspaceId,
    app.store.getSession(session.id).workspaceId,
  );
  assert.equal(app.store.getSession(next.id).nativeSessionId, undefined);
  assert.equal(
    app.store.getSession(session.id).nativeSessionId,
    `native-${session.id}`,
  );
});
