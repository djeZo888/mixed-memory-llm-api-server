import assert from "node:assert/strict";
import test, { type TestContext } from "node:test";
import { mkdtemp, readFile, realpath, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createApp, type AppOptions } from "../src/app.js";
import type { EngineOptions } from "../src/contracts.js";
const policy = {
  enabled: true,
  protocolQualified: true,
  engineVersion: "fixture",
  modelPolicyVersion: "fixture",
};
async function until(check: () => boolean) {
  for (let n = 0; n < 400; n++) {
    if (check()) return;
    await new Promise((r) => setTimeout(r, 5));
  }
  assert.fail("Timed out waiting for compaction fixture");
}
function deferred() {
  let resolve!: () => void, reject!: (error: Error) => void;
  const promise = new Promise<void>((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}
async function setup(t: TestContext, maxQueued?: number) {
  const dataDir = await realpath(
    await mkdtemp(join(tmpdir(), "h024-compact-")),
  );
  const calls: {
    kind: "message" | "compact";
    options: EngineOptions;
    text?: string;
    gate: ReturnType<typeof deferred>;
  }[] = [];
  let failCleanup = false;
  const factory: AppOptions["engineFactory"] = (options) => ({
    async start() {
      options.onNativeSessionId(
        options.nativeSessionId ?? `native-${options.sessionId}`,
      );
    },
    async prompt(text) {
      const gate = deferred();
      calls.push({ kind: "message", options, text, gate });
      await gate.promise;
    },
    async compact() {
      const gate = deferred();
      calls.push({ kind: "compact", options, gate });
      options.onUpdate({
        type: "compaction",
        compactionId: "native-compact",
        status: "start",
      });
      await gate.promise;
      options.onUpdate({
        type: "compaction",
        compactionId: "native-compact",
        status: "completed",
      });
      options.onUpdate({
        type: "context",
        used: 41,
        estimated: false,
        source: "fixture-native",
      });
      return "completed";
    },
    async cancel() {
      calls
        .filter((call) => call.options.sessionId === options.sessionId)
        .forEach((call) => call.gate.resolve());
    },
    async close() {
      if (failCleanup) throw new Error("private cleanup failure");
    },
  });
  const options: AppOptions = {
    dataDir,
    allowedOrigins: ["http://localhost"],
    launcher: "/unused",
    gatewayUrl: "http://fixture.invalid",
    issueToken: () => "fixture",
    revokeToken() {},
    engineFactory: factory,
    codexEngineFactory: factory,
    enginePolicy: { codex: policy },
    maxQueued,
  };
  let app = await createApp(options);
  t.after(async () => {
    failCleanup = false;
    calls.forEach((call) => call.gate.resolve());
    await app.app.close();
    await rm(dataDir, { recursive: true, force: true });
  });
  const post = (id: string, path: string, payload: unknown) =>
    app.app.inject({
      method: "POST",
      headers: { host: "localhost" },
      url: `/api/sessions/${id}/${path}`,
      payload,
    });
  const snapshot = async (id: string) =>
    (
      await app.app.inject({
        headers: { host: "localhost" },
        url: `/api/sessions/${id}`,
      })
    ).json();
  const existing = async () => {
    const session = await app.broker.createSession(undefined, "codex");
    app.store.setNative(session.id, `retained-${session.id}`, "codex");
    app.store.addMessage(
      session.id,
      "user",
      "Remember the original constraint",
    );
    const workspace = app.files.workspace(
      app.store.getSession(session.id).workspaceId,
    );
    await writeFile(join(workspace, "retained.txt"), "unchanged file");
    await app.files.registerArtifact(
      session.id,
      "retained.txt",
      "retained.txt",
      "text/plain",
    );
    return { ...session, workspace };
  };
  return {
    get app() {
      return app;
    },
    calls,
    post,
    snapshot,
    existing,
    failCleanup() {
      failCleanup = true;
    },
    async restart() {
      await app.app.close();
      app = await createApp(options);
    },
  };
}

test("manual compaction rejects unsupported/empty chats and arbitrary request fields", async (t) => {
  const h = await setup(t),
    mini = await h.app.broker.createSession(),
    empty = await h.app.broker.createSession(undefined, "codex");
  assert.equal(
    (await h.post(mini.id, "compact", { actionId: "a" })).json().error.code,
    "compaction_unavailable",
  );
  assert.equal(
    (await h.post(empty.id, "compact", { actionId: "a" })).json().error.code,
    "compaction_empty",
  );
  assert.equal((await h.post(empty.id, "compact", {})).statusCode, 400);
  assert.equal(
    (await h.post(empty.id, "compact", { actionId: "a", threadId: "other" }))
      .statusCode,
    400,
  );
  assert.equal(
    (await h.post(empty.id, "messages", { text: "/compact" })).json().error
      .code,
    "unsupported_slash_command",
  );
  assert.equal(h.calls.length, 0);
});

test("compaction shares workspace serialization and preserves native ID, messages and files", async (t) => {
  const h = await setup(t),
    original = await h.existing(),
    before = await h.snapshot(original.id);
  const sibling = await h.app.broker.createSession(
    h.app.store.getSession(original.id).workspaceId,
  );
  await h.post(sibling.id, "messages", { text: "Earlier workspace action" });
  await until(() => h.calls.length === 1);
  assert.equal(
    (await h.post(original.id, "compact", { actionId: "serialize" }))
      .statusCode,
    202,
  );
  await h.post(sibling.id, "messages", { text: "Later workspace action" });
  assert.equal(h.calls.length, 1);
  h.calls[0].gate.resolve();
  await until(() => h.calls.length === 2);
  assert.equal(h.calls[1].kind, "compact");
  assert.equal(h.calls[1].options.nativeSessionId, `retained-${original.id}`);
  assert.equal(h.app.store.getSession(original.id).status, "compacting");
  assert.equal(
    (
      await h.post(original.id, "compact", { actionId: "distinct-pending" })
    ).json().error.code,
    "compaction_pending",
  );
  h.calls[1].gate.resolve();
  await until(() => h.calls.length === 3);
  assert.equal(h.calls[2].text, "Later workspace action");
  const after = await h.snapshot(original.id);
  assert.deepEqual(after.messages, before.messages);
  assert.deepEqual(after.artifacts, before.artifacts);
  assert.equal(
    await readFile(join(original.workspace, "retained.txt"), "utf8"),
    "unchanged file",
  );
  assert.equal(
    h.app.store.getSession(original.id).nativeSessionId,
    `retained-${original.id}`,
  );
  assert.equal(after.runs[0].kind, "compact");
  assert.equal(after.runs[0].status, "completed");
  h.calls[2].gate.resolve();
});

test("duplicate compaction returns original run during work, after completion and after restart", async (t) => {
  const h = await setup(t),
    original = await h.existing();
  const first = (
    await h.post(original.id, "compact", { actionId: "durable-action" })
  ).json();
  assert.deepEqual(
    (
      await h.post(original.id, "compact", { actionId: "durable-action" })
    ).json(),
    first,
  );
  await until(() => h.calls.length === 1);
  assert.deepEqual(
    (
      await h.post(original.id, "compact", { actionId: "durable-action" })
    ).json(),
    first,
  );
  h.calls[0].gate.resolve();
  await until(() => h.app.store.getSession(original.id).status === "idle");
  assert.deepEqual(
    (
      await h.post(original.id, "compact", { actionId: "durable-action" })
    ).json(),
    first,
  );
  await h.restart();
  assert.deepEqual(
    (
      await h.post(original.id, "compact", { actionId: "durable-action" })
    ).json(),
    first,
  );
  assert.equal(h.calls.length, 1);
  assert.equal((await h.snapshot(original.id)).runs.length, 1);
  const distinct = (
    await h.post(original.id, "compact", { actionId: "intentional-new-action" })
  ).json();
  assert.notEqual(distinct.runId, first.runId);
  await until(() => h.calls.length === 2);
  h.calls[1].gate.resolve();
});

test("failed compaction stays failed and visible, without duplicate/restart replay", async (t) => {
  const h = await setup(t),
    original = await h.existing(),
    before = await h.snapshot(original.id);
  const first = (
    await h.post(original.id, "compact", { actionId: "failed-action" })
  ).json();
  await until(() => h.calls.length === 1);
  h.calls[0].gate.reject(new Error("private native failure"));
  await until(() => h.app.store.getSession(original.id).status === "failed");
  const after = await h.snapshot(original.id);
  assert.equal(after.runs[0].status, "failed");
  assert.deepEqual(after.messages, before.messages);
  assert.deepEqual(after.artifacts, before.artifacts);
  assert.ok(
    after.events.some(
      (event: any) =>
        event.type === "error" && event.data.code === "compaction_failed",
    ),
  );
  assert.ok(!JSON.stringify(after).includes("private native failure"));
  assert.deepEqual(
    (
      await h.post(original.id, "compact", { actionId: "failed-action" })
    ).json(),
    first,
  );
  await h.restart();
  assert.deepEqual(
    (
      await h.post(original.id, "compact", { actionId: "failed-action" })
    ).json(),
    first,
  );
  assert.equal(h.calls.length, 1);
});

test("unknown compaction cleanup quarantines workspace and blocks queued siblings", async (t) => {
  const h = await setup(t),
    original = await h.existing(),
    workspaceId = h.app.store.getSession(original.id).workspaceId;
  const sibling = await h.app.broker.createSession(workspaceId);
  await h.post(original.id, "compact", { actionId: "unknown-cleanup" });
  await until(() => h.calls.length === 1);
  await h.post(sibling.id, "messages", { text: "Must not run" });
  h.failCleanup();
  h.calls[0].gate.reject(new Error("native failure"));
  await until(
    () => h.app.store.getSession(sibling.id).status === "interrupted",
  );
  assert.equal(h.calls.length, 1);
  assert.ok(h.app.store.isQuarantined(workspaceId));
  assert.ok(
    (await h.snapshot(original.id)).events.some(
      (event: any) =>
        event.type === "error" && event.data.code === "engine_cleanup_unknown",
    ),
  );
});

test("interrupted persisted compaction is returned after restart without native replay", async (t) => {
  const h = await setup(t), original = await h.existing();
  const saved = h.app.store.createRun(h.app.store.getSession(original.id), "compact", "", [], "interrupted-action");
  await h.restart();
  const response = await h.post(original.id, "compact", { actionId: "interrupted-action" });
  assert.equal(response.statusCode, 202);
  assert.equal(response.json().runId, saved.id);
  assert.equal((await h.snapshot(original.id)).runs[0].status, "interrupted");
  assert.equal(h.calls.length, 0);
});

test("queue capacity rejects compaction without reserving an action or invoking the engine", async (t) => {
  const h = await setup(t, 0), original = await h.existing();
  const response = await h.post(original.id, "compact", { actionId: "capacity" });
  assert.equal(response.statusCode, 429);
  assert.equal(response.json().error.code, "queue_full");
  assert.equal(h.app.store.compactionRun(original.id, "capacity"), undefined);
  assert.equal(h.calls.length, 0);
  assert.equal((await h.snapshot(original.id)).runs.length, 0);
});

test("Stop settles active compaction as cancelled without replaying its action", async (t) => {
  const h = await setup(t), original = await h.existing();
  const response = await h.post(original.id, "compact", { actionId: "stop" });
  await until(() => h.calls.length === 1);
  assert.equal((await h.post(original.id, "cancel", {})).statusCode, 202);
  await until(() => h.app.store.getSession(original.id).status === "idle");
  assert.equal((await h.snapshot(original.id)).runs[0].status, "cancelled");
  assert.equal((await h.post(original.id, "compact", { actionId: "stop" })).json().runId, response.json().runId);
  assert.equal(h.calls.length, 1);
});
