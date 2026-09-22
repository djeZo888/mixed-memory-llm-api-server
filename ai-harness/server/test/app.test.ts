import assert from "node:assert/strict";
import test, { type TestContext } from "node:test";
import {
  mkdir,
  mkdtemp,
  readFile,
  readdir,
  realpath,
  rm,
  symlink,
  writeFile,
} from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import http from "node:http";
import type { FastifyInstance, InjectOptions } from "fastify";
import { createApp, type AppOptions } from "../src/app.js";
import type {
  EngineFactory,
  EngineOptions,
  EngineUpdate,
  Event,
} from "../src/contracts.js";

function inject(app: FastifyInstance, request: string | InjectOptions) {
  const options = typeof request === "string" ? { url: request } : request;
  return app.inject({
    signal: AbortSignal.timeout(5000),
    ...options,
    headers: { host: "localhost", ...options.headers },
  });
}
const delay = (ms: number) =>
  new Promise<void>((resolve) => setTimeout(resolve, ms));
async function until(
  predicate: () => boolean,
  label = "condition",
): Promise<void> {
  const deadline = Date.now() + 4000;
  while (!predicate()) {
    if (Date.now() > deadline)
      throw new Error(`Timed out waiting for ${label}`);
    await delay(5);
  }
}

interface Call {
  sessionId: string;
  text: string;
  attachments: unknown[];
  done: boolean;
  resolve: () => void;
  update: (value: EngineUpdate) => void;
}
function engines(controlled = false) {
  const calls: Call[] = [],
    options: EngineOptions[] = [],
    cancelled: string[] = [],
    closed: string[] = [];
  const factory: EngineFactory = (opts) => {
    options.push(opts);
    return {
      async start() {
        opts.onNativeSessionId(
          opts.nativeSessionId ?? `native-${opts.sessionId}`,
        );
      },
      async prompt(text, attachments = []) {
        let release!: () => void;
        const pending = new Promise<void>((resolve) => {
          release = resolve;
        });
        const call: Call = {
          sessionId: opts.sessionId,
          text,
          attachments,
          done: false,
          resolve: release,
          update: opts.onUpdate,
        };
        calls.push(call);
        if (controlled) await pending;
        else
          opts.onUpdate({
            type: "text",
            text: text.startsWith("Create a factual handoff")
              ? "Fixture engine summary: preserve requirements; continue the pending task."
              : `Fixture response to: ${text}`,
          });
        call.done = true;
      },
      async cancel() {
        cancelled.push(opts.sessionId);
      },
      async close() {
        closed.push(opts.sessionId);
      },
    };
  };
  return {
    factory,
    calls,
    options,
    cancelled,
    closed,
    releaseAll() {
      calls.forEach((call) => call.resolve());
    },
  };
}
async function setup(
  t: TestContext,
  fixture = engines(),
  overrides: Partial<AppOptions> = {},
) {
  const dir = await realpath(
    await mkdtemp(path.join(tmpdir(), "h001-app-test-")),
  );
  const issued: string[] = [],
    revoked: string[] = [];
  const options: AppOptions = {
    dataDir: dir,
    allowedOrigins: ["http://localhost"],
    engineFactory: fixture.factory,
    launcher: "/fixture/not-executed",
    gatewayUrl: "http://127.0.0.1:1/v1",
    issueToken: (id) => {
      const token = `fixture-inference-${id}`;
      issued.push(token);
      return token;
    },
    revokeToken: (token) => {
      revoked.push(token);
    },
    heartbeatMs: 20,
    ...overrides,
  };
  const built = await createApp(options);
  t.after(async () => {
    fixture.releaseAll();
    await built.app.close();
    await rm(dir, { recursive: true, force: true });
  });
  async function session() {
    const response = await inject(built.app, {
      method: "POST",
      url: "/api/sessions",
      payload: {},
    });
    assert.equal(response.statusCode, 200, response.body);
    return response.json().session as {
      id: string;
      context: { used: number | null; limit: number; stale: boolean };
    };
  }
  return { ...built, fixture, dir, options, issued, revoked, session };
}
function multipart(filename: string, mimeType: string, data: Buffer | string) {
  const boundary = "h001-fixture-boundary";
  return {
    headers: { "content-type": `multipart/form-data; boundary=${boundary}` },
    payload: Buffer.concat([
      Buffer.from(
        `--${boundary}\r\nContent-Disposition: form-data; name="file"; filename="${filename}"\r\nContent-Type: ${mimeType}\r\n\r\n`,
      ),
      Buffer.from(data),
      Buffer.from(`\r\n--${boundary}--\r\n`),
    ]),
  };
}

test("JSON contract, durable messages/native identity/events and unknown context survive reopening", async (t) => {
  const h = await setup(t);
  const health = await inject(h.app, "/api/health");
  assert.deepEqual(health.json(), {
    version: "0.0.1",
    status: "ok",
    visionAvailable: false,
  });
  const s = await h.session();
  assert.equal(s.context.used, null);
  assert.equal(s.context.limit, 480000);
  assert.equal(s.context.stale, true);
  assert.equal("workspaceId" in s, false);
  assert.equal("nativeSessionId" in s, false);
  const response = await inject(h.app, {
    method: "POST",
    url: `/api/sessions/${s.id}/messages`,
    payload: { text: "original visible user history" },
  });
  assert.equal(response.statusCode, 202);
  assert.equal(typeof response.json().runId, "string");
  await h.broker.idle();
  const before = (await inject(h.app, `/api/sessions/${s.id}`)).json();
  assert.deepEqual(
    before.messages.map((m: { role: string }) => m.role),
    ["user", "assistant"],
  );
  assert.equal(before.messages[0].content, "original visible user history");
  assert.equal(before.session.context.used, null);
  assert.equal(before.session.status, "idle");
  assert.deepEqual(
    before.events.map((e: Event) => e.id),
    before.events.map((_: unknown, i: number) => i + 1),
  );
  assert.ok(
    before.events.some(
      (e: Event) => e.type === "done" && e.runId === response.json().runId,
    ),
  );
  assert.equal(h.store.getSession(s.id).nativeSessionId, `native-${s.id}`);
  await h.app.close();
  const reopened = await createApp(h.options);
  try {
    const after = (await inject(reopened.app, `/api/sessions/${s.id}`)).json();
    assert.deepEqual(after, before);
    const next = await inject(reopened.app, {
      method: "POST",
      url: `/api/sessions/${s.id}/messages`,
      payload: { text: "resume retained native chat" },
    });
    assert.equal(next.statusCode, 202);
    await reopened.broker.idle();
    assert.equal(h.fixture.options.at(-1)?.nativeSessionId, `native-${s.id}`);
    assert.equal(reopened.store.messages(s.id).length, 4);
  } finally {
    await reopened.app.close();
  }
  assert.equal(h.revoked.length, 2);
});

test("real measurements replace unknown occupancy; compaction preserves complete visible history", async (t) => {
  const fixture = engines(true),
    h = await setup(t, fixture),
    s = await h.session();
  await inject(h.app, {
    method: "POST",
    url: `/api/sessions/${s.id}/messages`,
    payload: { text: "Keep the full original request." },
  });
  await until(() => fixture.calls.length === 1);
  const call = fixture.calls[0]!;
  call.update({ type: "text", text: "Original assistant content. " });
  call.update({
    type: "context",
    used: 400000,
    estimated: true,
    source: "fixture-native-usage",
  });
  call.update({
    type: "compaction",
    compactionId: "fixture-compaction-1",
    status: "start",
    tokensBefore: 412416,
  });
  assert.equal(h.store.getSession(s.id).status, "compacting");
  assert.equal(h.store.getSession(s.id).context?.stale, true);
  assert.equal(
    h.store.getSession(s.id).context?.used,
    400000,
    "event counts do not replace occupied context",
  );
  call.update({
    type: "compaction",
    compactionId: "fixture-compaction-1",
    status: "completed",
    tokensAfter: 999,
  });
  assert.equal(h.store.getSession(s.id).status, "running");
  assert.equal(h.store.getSession(s.id).context?.stale, true);
  assert.equal(h.store.getSession(s.id).context?.used, 400000);
  assert.equal(
    h.store
      .allEvents(s.id)
      .filter(
        (event) =>
          event.type === "progress" && event.data.kind === "compaction",
      ).length,
    2,
  );
  call.update({
    type: "context",
    used: 1729,
    estimated: true,
    source: "fixture-real-usage",
  });
  call.update({ type: "text", text: "Content after compaction." });
  call.resolve();
  await h.broker.idle();
  assert.deepEqual(
    h.store.messages(s.id).map((m) => m.content),
    [
      "Keep the full original request.",
      "Original assistant content. Content after compaction.",
    ],
  );
  assert.deepEqual(
    { ...h.store.getSession(s.id).context, updatedAt: undefined },
    {
      used: 1729,
      limit: 480000,
      estimated: true,
      stale: false,
      source: "fixture-real-usage",
      updatedAt: undefined,
    },
  );
  await inject(h.app, {
    method: "POST",
    url: `/api/sessions/${s.id}/messages`,
    payload: { text: "next" },
  });
  await until(() => fixture.calls.length === 2);
  assert.equal(h.store.getSession(s.id).context?.used, 1729);
  assert.equal(h.store.getSession(s.id).context?.stale, true);
  fixture.calls[1]!.update({
    type: "context",
    used: -1,
    estimated: false,
    source: "invalid",
  });
  assert.equal(h.store.getSession(s.id).context?.used, 1729);
  fixture.calls[1]!.resolve();
  await h.broker.idle();
});

for (const promptFails of [false, true])
  test(`failed compaction preserves original history and defers final status to ${promptFails ? "failed" : "successful"} prompt outcome`, async (t) => {
    const fixture = engines(true);
    const baseFactory = fixture.factory;
    fixture.factory = (options) => {
      const engine = baseFactory(options);
      return {
        ...engine,
        async prompt(text, attachments) {
          await engine.prompt(text, attachments);
          if (promptFails)
            throw new Error("fixture prompt failed after compaction failure");
        },
      };
    };
    const h = await setup(t, fixture),
      s = await h.session();
    await inject(h.app, {
      method: "POST",
      url: `/api/sessions/${s.id}/messages`,
      payload: { text: "The original user requirement remains visible." },
    });
    await until(() => fixture.calls.length === 1);
    const call = fixture.calls[0]!;
    call.update({ type: "text", text: "Original assistant text. " });
    call.update({
      type: "context",
      used: 23456,
      estimated: true,
      source: "fixture-native-usage",
    });
    call.update({
      type: "compaction",
      compactionId: "failure-1",
      status: "start",
      tokensBefore: 24000,
    });
    call.update({
      type: "compaction",
      compactionId: "failure-1",
      status: "failed",
    });
    assert.equal(
      h.store.getSession(s.id).status,
      "running",
      "compaction failure alone does not fabricate prompt failure",
    );
    assert.equal(h.store.getSession(s.id).context?.stale, true);
    assert.equal(h.store.getSession(s.id).context?.used, 23456);
    const snapshot = (await inject(h.app, `/api/sessions/${s.id}`)).json();
    assert.ok(
      snapshot.events.some(
        (event: Event) =>
          event.type === "error" && event.data.code === "compaction_failed",
      ),
    );
    assert.equal(
      snapshot.events.filter(
        (event: Event) =>
          event.type === "progress" && event.data.kind === "compaction",
      ).length,
      2,
    );
    call.update({
      type: "text",
      text: "The prompt continued after the compaction failure.",
    });
    call.resolve();
    await h.broker.idle();
    assert.equal(
      h.store.getSession(s.id).status,
      promptFails ? "failed" : "idle",
    );
    assert.equal(h.store.getSession(s.id).context?.stale, true);
    assert.deepEqual(
      h.store.messages(s.id).map((message) => message.content),
      [
        "The original user requirement remains visible.",
        "Original assistant text. The prompt continued after the compaction failure.",
      ],
    );
  });

test("session snapshot message content and event watermark support replay without lost or duplicated deltas", async (t) => {
  const fixture = engines(true),
    h = await setup(t, fixture),
    s = await h.session();
  await inject(h.app, {
    method: "POST",
    url: `/api/sessions/${s.id}/messages`,
    payload: { text: "Snapshot boundary" },
  });
  await until(() => fixture.calls.length === 1);
  fixture.calls[0]!.update({ type: "text", text: "Before snapshot. " });
  const snapshot = (await inject(h.app, `/api/sessions/${s.id}`)).json();
  const watermark = Math.max(
    ...snapshot.events.map((event: Event) => event.id),
  );
  const assistant = snapshot.messages.find(
    (message: { role: string }) => message.role === "assistant",
  );
  assert.equal(assistant.content, "Before snapshot. ");
  fixture.calls[0]!.update({ type: "text", text: "After snapshot." });
  fixture.calls[0]!.resolve();
  await h.broker.idle();
  const replay = h.store.replay(s.id, watermark);
  const reconstructed =
    assistant.content +
    replay
      .filter(
        (event) =>
          event.type === "assistant_delta" &&
          event.data.messageId === assistant.id,
      )
      .map((event) => event.data.text)
      .join("");
  const finalSnapshot = (await inject(h.app, `/api/sessions/${s.id}`)).json();
  assert.equal(
    reconstructed,
    finalSnapshot.messages.find(
      (message: { id: string }) => message.id === assistant.id,
    ).content,
  );
  assert.equal(reconstructed, "Before snapshot. After snapshot.");
  assert.ok(replay.every((event) => event.id > watermark));
});

test("workspace queue serializes shared chats while unrelated workspaces run concurrently", async (t) => {
  const fixture = engines(true),
    h = await setup(t, fixture),
    first = await h.session(),
    independent = await h.session();
  const shared = await h.broker.createSession(
    h.store.getSession(first.id).workspaceId,
  );
  for (const s of [first, shared, independent])
    assert.equal(
      (
        await inject(h.app, {
          method: "POST",
          url: `/api/sessions/${s.id}/messages`,
          payload: { text: s.id },
        })
      ).statusCode,
      202,
    );
  await until(() => fixture.calls.length === 2);
  assert.deepEqual(
    new Set(fixture.calls.map((c) => c.sessionId)),
    new Set([first.id, independent.id]),
  );
  assert.equal(h.store.getSession(shared.id).status, "queued");
  fixture.calls.find((c) => c.sessionId === first.id)!.resolve();
  await until(() => fixture.calls.length === 3);
  assert.equal(fixture.calls[2]!.sessionId, shared.id);
  assert.equal(
    fixture.calls.find((c) => c.sessionId === independent.id)!.done,
    false,
  );
  fixture.releaseAll();
  await h.broker.idle();
  assert.equal(h.store.getSession(shared.id).status, "idle");
});

test("handoff asks engine for summary, retains old chat, shares workspace and seeds only first new prompt", async (t) => {
  const h = await setup(t),
    original = await h.session();
  await inject(h.app, {
    method: "POST",
    url: `/api/sessions/${original.id}/messages`,
    payload: { text: "Build the original work." },
  });
  await h.broker.idle();
  const result = await inject(h.app, {
    method: "POST",
    url: `/api/sessions/${original.id}/handoff`,
    payload: {},
  });
  assert.equal(result.statusCode, 202);
  await h.broker.idle();
  const event = h.store
    .allEvents(original.id)
    .find((e) => e.type === "handoff");
  assert.ok(event, JSON.stringify(h.store.allEvents(original.id)));
  const newId = event.data.newSessionId as string;
  assert.notEqual(newId, original.id);
  assert.equal(
    h.store.getSession(newId).workspaceId,
    h.store.getSession(original.id).workspaceId,
  );
  assert.equal(h.store.listSessions().length, 2);
  assert.equal(
    h.store.messages(original.id)[0]!.content,
    "Build the original work.",
  );
  assert.match(h.store.messages(newId)[0]!.content, /Fixture engine summary/);
  assert.match(h.fixture.calls[1]!.text, /Create a factual handoff summary/);
  await inject(h.app, {
    method: "POST",
    url: `/api/sessions/${newId}/messages`,
    payload: { text: "Continue now." },
  });
  await h.broker.idle();
  assert.match(h.fixture.calls[2]!.text, /Fixture engine summary/);
  assert.match(h.fixture.calls[2]!.text, /Continue now/);
  await inject(h.app, {
    method: "POST",
    url: `/api/sessions/${newId}/messages`,
    payload: { text: "Another step." },
  });
  await h.broker.idle();
  assert.equal(h.fixture.calls[3]!.text, "Another step.");
  assert.notEqual(
    h.fixture.options[0]!.profileDir,
    h.fixture.options[1]!.profileDir,
  );
  assert.equal(
    h.fixture.options[0]!.workspace,
    h.fixture.options[1]!.workspace,
  );
});

test("a fresh handoff chat can hand off again without losing its inherited engine summary", async (t) => {
  const h = await setup(t);
  const original = await h.session();
  const first = await inject(h.app, {
    method: "POST",
    url: `/api/sessions/${original.id}/handoff`,
    payload: {},
  });
  assert.equal(first.statusCode, 202);
  await h.broker.idle();
  const inheritedSummary = h.store.messages(original.id).at(-1)!.content;
  assert.match(inheritedSummary, /Fixture engine summary/);
  const middleId = h.store
    .allEvents(original.id)
    .find((event) => event.type === "handoff")!.data.newSessionId as string;
  const originalHistory = h.store.messages(original.id);
  assert.equal(
    h.store.messages(middleId).filter((message) => message.role === "user")
      .length,
    0,
  );
  const second = await inject(h.app, {
    method: "POST",
    url: `/api/sessions/${middleId}/handoff`,
    payload: {},
  });
  assert.equal(second.statusCode, 202);
  await h.broker.idle();
  assert.equal(h.fixture.calls.length, 2);
  assert.ok(
    h.fixture.calls[1]!.text.includes(inheritedSummary),
    "the next summary engine receives the inherited project context",
  );
  assert.match(h.fixture.calls[1]!.text, /Create a factual handoff summary/);
  const finalId = h.store
    .allEvents(middleId)
    .find((event) => event.type === "handoff")!.data.newSessionId as string;
  assert.equal(
    h.store.getSession(finalId).workspaceId,
    h.store.getSession(original.id).workspaceId,
  );
  assert.ok(h.store.messages(finalId)[0]!.content.includes(inheritedSummary));
  assert.deepEqual(h.store.messages(original.id), originalHistory);
  assert.equal(h.store.listSessions().length, 3);
});

test("cancellation during artifact discovery retains workspace ownership until confirmation", async (t) => {
  let finishDiscovery!: () => void;
  let confirmCancellation!: () => void;
  const discoveryGate = new Promise<void>((resolve) => {
    finishDiscovery = resolve;
  });
  const cancelGate = new Promise<void>((resolve) => {
    confirmCancellation = resolve;
  });
  t.after(() => {
    finishDiscovery();
    confirmCancellation();
  });
  const fixture = engines();
  const baseFactory = fixture.factory;
  fixture.factory = (options) => {
    const engine = baseFactory(options);
    return {
      ...engine,
      async cancel() {
        fixture.cancelled.push(options.sessionId);
        await cancelGate;
      },
    };
  };
  const h = await setup(t, fixture);
  const original = await h.session();
  const sibling = await h.broker.createSession(
    h.store.getSession(original.id).workspaceId,
  );
  const discover = h.files.discover.bind(h.files);
  let originalScans = 0,
    postPromptScanPending = false,
    postPromptScanFinished = false;
  h.files.discover = async (sessionId) => {
    if (sessionId === original.id && ++originalScans === 2) {
      postPromptScanPending = true;
      await discoveryGate;
      const files = await discover(sessionId);
      postPromptScanFinished = true;
      return files;
    }
    return discover(sessionId);
  };
  const active = await inject(h.app, {
    method: "POST",
    url: `/api/sessions/${original.id}/messages`,
    payload: { text: "Complete a response before artifact discovery." },
  });
  assert.equal(active.statusCode, 202);
  await until(() => postPromptScanPending, "post-prompt artifact discovery");
  assert.equal(
    fixture.calls[0]!.done,
    true,
    "parent response already completed",
  );
  assert.equal(
    (
      await inject(h.app, {
        method: "POST",
        url: `/api/sessions/${sibling.id}/messages`,
        payload: { text: "Shared workspace successor." },
      })
    ).statusCode,
    202,
  );
  assert.equal(
    (
      await inject(h.app, {
        method: "POST",
        url: `/api/sessions/${original.id}/cancel`,
        payload: {},
      })
    ).statusCode,
    202,
  );
  await until(() => fixture.cancelled.includes(original.id));
  finishDiscovery();
  await until(() => postPromptScanFinished);
  await delay(20);
  assert.equal(h.store.getSession(original.id).status, "cancelling");
  assert.equal(h.store.getSession(sibling.id).status, "queued");
  assert.equal(
    fixture.calls.length,
    1,
    "successor cannot start on an unconfirmed cancellation",
  );
  assert.equal(
    h.store.allEvents(original.id).some((event) => event.type === "done"),
    false,
  );
  confirmCancellation();
  await h.broker.idle();
  assert.equal(fixture.calls.length, 2);
  assert.equal(fixture.calls[1]!.sessionId, sibling.id);
  assert.equal(h.store.getSession(original.id).status, "idle");
  assert.equal(h.store.getSession(sibling.id).status, "idle");
  assert.equal(
    h.store.db
      .prepare("SELECT status FROM runs WHERE id=?")
      .get(active.json().runId)?.status,
    "cancelled",
  );
});

test("cancel settles active work; delete remains visible until settled and preserves workspace", async (t) => {
  const fixture = engines(true),
    h = await setup(t, fixture),
    s = await h.session();
  const workspace = h.files.workspace(h.store.getSession(s.id).workspaceId);
  await writeFile(
    path.join(workspace, "keep.txt"),
    "workspace must survive delete",
  );
  await inject(h.app, {
    method: "POST",
    url: `/api/sessions/${s.id}/messages`,
    payload: { text: "running" },
  });
  await until(() => fixture.calls.length === 1);
  await inject(h.app, {
    method: "POST",
    url: `/api/sessions/${s.id}/messages`,
    payload: { text: "queued must not execute" },
  });
  const deletion = await inject(h.app, {
    method: "DELETE",
    url: `/api/sessions/${s.id}`,
  });
  assert.equal(deletion.statusCode, 202);
  assert.deepEqual(deletion.json(), { status: "deleting" });
  assert.equal(h.store.listSessions().length, 1);
  assert.equal(h.store.getSession(s.id).status, "deleting");
  assert.ok(fixture.cancelled.includes(s.id));
  assert.equal(fixture.closed.length, 0);
  assert.equal(
    (
      await inject(h.app, {
        method: "POST",
        url: `/api/sessions/${s.id}/messages`,
        payload: { text: "reject deletion race" },
      })
    ).statusCode,
    409,
  );
  fixture.calls[0]!.resolve();
  await h.broker.idle();
  assert.equal(h.store.listSessions().length, 0);
  assert.equal(fixture.calls.length, 1);
  assert.equal(fixture.closed.length, 1);
  assert.equal((await inject(h.app, `/api/sessions/${s.id}`)).statusCode, 404);
  assert.equal(
    await readFile(path.join(workspace, "keep.txt"), "utf8"),
    "workspace must survive delete",
  );
  const statuses = h.store.db
    .prepare("SELECT status FROM runs WHERE session_id=?")
    .all(s.id)
    .map((r) => r.status);
  assert.deepEqual(statuses, ["cancelled", "cancelled"]);
});

test("bounded workspace queue and explicit cancellation never execute cancelled queued prompts", async (t) => {
  const fixture = engines(true),
    h = await setup(t, fixture, { maxQueued: 1 }),
    first = await h.session();
  const queued = await h.broker.createSession(
    h.store.getSession(first.id).workspaceId,
  );
  await inject(h.app, {
    method: "POST",
    url: `/api/sessions/${first.id}/messages`,
    payload: { text: "active" },
  });
  await until(() => fixture.calls.length === 1);
  const queuedResponse = await inject(h.app, {
    method: "POST",
    url: `/api/sessions/${queued.id}/messages`,
    payload: { text: "cancel me before start" },
  });
  assert.equal(queuedResponse.statusCode, 202);
  const overflow = await inject(h.app, {
    method: "POST",
    url: `/api/sessions/${queued.id}/messages`,
    payload: { text: "overflow" },
  });
  assert.equal(overflow.statusCode, 429);
  assert.equal(overflow.json().error.code, "queue_full");
  const cancelled = await inject(h.app, {
    method: "POST",
    url: `/api/sessions/${queued.id}/cancel`,
    payload: {},
  });
  assert.equal(cancelled.statusCode, 202);
  assert.deepEqual(cancelled.json(), { status: "cancelling" });
  assert.equal(h.store.getSession(queued.id).status, "idle");
  assert.equal(fixture.cancelled.length, 0);
  assert.ok(
    h.store
      .allEvents(queued.id)
      .some(
        (e) => e.type === "done" && e.runId === queuedResponse.json().runId,
      ),
  );
  const activeCancel = await inject(h.app, {
    method: "POST",
    url: `/api/sessions/${first.id}/cancel`,
    payload: {},
  });
  assert.equal(activeCancel.statusCode, 202);
  assert.equal(h.store.getSession(first.id).status, "cancelling");
  assert.equal(fixture.calls[0]!.done, false);
  assert.deepEqual(fixture.cancelled, [first.id]);
  fixture.calls[0]!.resolve();
  await h.broker.idle();
  assert.equal(fixture.calls.length, 1);
  assert.equal(h.store.getSession(first.id).status, "idle");
});

test("cancel acknowledges immediately while prompt and cancel settlement retain the workspace", async (t) => {
  const fixture = engines(true),
    baseFactory = fixture.factory;
  let confirmCancellation!: () => void;
  const cancellation = new Promise<void>((resolve) => {
    confirmCancellation = resolve;
  });
  t.after(() => confirmCancellation());
  fixture.factory = (options) => {
    const engine = baseFactory(options);
    return {
      ...engine,
      async cancel() {
        fixture.cancelled.push(options.sessionId);
        await cancellation;
      },
    };
  };
  const h = await setup(t, fixture),
    s = await h.session();
  await inject(h.app, {
    method: "POST",
    url: `/api/sessions/${s.id}/messages`,
    payload: { text: "wait for settlement" },
  });
  await until(() => fixture.calls.length === 1);
  const response = await Promise.race([
    inject(h.app, {
      method: "POST",
      url: `/api/sessions/${s.id}/cancel`,
      payload: {},
    }),
    delay(500).then(() => {
      throw new Error("Cancel endpoint waited for engine settlement");
    }),
  ]);
  assert.equal(response.statusCode, 202);
  assert.equal(h.store.getSession(s.id).status, "cancelling");
  fixture.calls[0]!.resolve();
  await delay(20);
  assert.equal(h.store.getSession(s.id).status, "cancelling");
  assert.equal(
    h.store.allEvents(s.id).some((e) => e.type === "done"),
    false,
  );
  confirmCancellation();
  await h.broker.idle();
  assert.equal(h.store.getSession(s.id).status, "idle");
});

test(
  "shutdown closes all active runners in parallel before waiting for unresponsive prompts",
  { timeout: 3000 },
  async (t) => {
    let allCloseCallsStarted!: () => void;
    const closeBarrier = new Promise<void>((resolve) => {
      allCloseCallsStarted = resolve;
    });
    t.after(() => allCloseCallsStarted());
    const fixture = engines(true),
      baseFactory = fixture.factory;
    fixture.factory = (options) => {
      const engine = baseFactory(options);
      return {
        ...engine,
        async close() {
          await engine.close();
          if (fixture.closed.length === 2) allCloseCallsStarted();
          await closeBarrier;
          fixture.calls
            .find((call) => call.sessionId === options.sessionId)!
            .resolve();
        },
      };
    };
    const h = await setup(t, fixture),
      first = await h.session(),
      second = await h.session();
    for (const session of [first, second])
      assert.equal(
        (
          await inject(h.app, {
            method: "POST",
            url: `/api/sessions/${session.id}/messages`,
            payload: { text: "Prompt settles only after launcher close." },
          })
        ).statusCode,
        202,
      );
    await until(() => fixture.calls.length === 2);
    assert.equal(
      fixture.calls.every((call) => !call.done),
      true,
    );
    await Promise.race([
      h.broker.close(),
      delay(500).then(() => {
        throw new Error(
          "Shutdown waited for prompts or sequential launcher closure",
        );
      }),
    ]);
    assert.deepEqual(new Set(fixture.closed), new Set([first.id, second.id]));
    assert.equal(
      fixture.calls.every((call) => call.done),
      true,
    );
    assert.equal(h.revoked.length, 2);
    assert.deepEqual(
      h.store.db
        .prepare("SELECT status FROM runs ORDER BY rowid")
        .all()
        .map((run) => run.status),
      ["cancelled", "cancelled"],
    );
  },
);

test(
  "shutdown during workspace preparation cannot create a late native runner or inference token",
  { timeout: 3000 },
  async (t) => {
    let finishPreparation!: () => void;
    const preparation = new Promise<void>((resolve) => {
      finishPreparation = resolve;
    });
    t.after(() => finishPreparation());
    const h = await setup(t),
      s = await h.session();
    const prepare = h.files.prepare.bind(h.files);
    let preparing = false;
    h.files.prepare = async (sessionId, workspaceId) => {
      if (sessionId === s.id) {
        preparing = true;
        await preparation;
      }
      await prepare(sessionId, workspaceId);
    };
    assert.equal(
      (
        await inject(h.app, {
          method: "POST",
          url: `/api/sessions/${s.id}/messages`,
          payload: {
            text: "Accepted request must not launch after shutdown starts.",
          },
        })
      ).statusCode,
      202,
    );
    await until(() => preparing);
    assert.equal(h.fixture.options.length, 0);
    const shutdown = h.broker.close();
    finishPreparation();
    await Promise.race([
      shutdown,
      delay(500).then(() => {
        throw new Error("Shutdown did not settle preparation race");
      }),
    ]);
    assert.equal(
      h.fixture.options.length,
      0,
      "engine factory never runs after shutdown admission closes",
    );
    assert.equal(
      h.issued.length,
      0,
      "no runner credential is minted after shutdown",
    );
    assert.equal(h.store.getSession(s.id).nativeSessionId, undefined);
    assert.equal(
      h.store.messages(s.id)[0]!.content,
      "Accepted request must not launch after shutdown starts.",
    );
  },
);

test("app restart never launches interrupted work or replays effects, and blocks unsafe workspace reuse", async (t) => {
  const h = await setup(t),
    s = await h.session(),
    stored = h.store.getSession(s.id);
  const run = h.store.createRun(
    stored,
    "message",
    "must not be automatically replayed",
    [],
  );
  h.store.updateRun(run.id, "running");
  h.store.setStatus(s.id, "running");
  h.store.addMessage(s.id, "user", "original accepted text", run.id);
  await h.app.close();
  const reopened = await createApp(h.options);
  try {
    await reopened.broker.idle();
    assert.equal(h.fixture.options.length, 0);
    const state = (await inject(reopened.app, `/api/sessions/${s.id}`)).json();
    assert.equal(state.session.status, "interrupted");
    assert.equal(state.messages[0].content, "original accepted text");
    const blocked = await inject(reopened.app, {
      method: "POST",
      url: `/api/sessions/${s.id}/messages`,
      payload: { text: "must await settlement review" },
    });
    assert.equal(blocked.statusCode, 409);
    assert.equal(blocked.json().error.code, "workspace_quarantined");
    const deletion = await inject(reopened.app, {
      method: "DELETE",
      url: `/api/sessions/${s.id}`,
    });
    assert.equal(deletion.statusCode, 202);
    assert.equal(reopened.store.listSessions().length, 1);
  } finally {
    await reopened.app.close();
  }
});

test("unknown native background settlement preserves history and blocks queued workspace siblings", async (t) => {
  const fixture = engines(true);
  const baseFactory = fixture.factory;
  fixture.factory = (options) => {
    const engine = baseFactory(options);
    return {
      ...engine,
      async prompt(text, attachments) {
        await engine.prompt(text, attachments);
        throw Object.assign(
          new Error("fixture background continuation remains unknown"),
          {
            code: "engine_settlement_unknown",
          },
        );
      },
      async close() {
        throw new Error("fixture process cleanup is unconfirmed");
      },
    };
  };
  const h = await setup(t, fixture);
  const original = await h.session();
  const workspaceId = h.store.getSession(original.id).workspaceId;
  const sibling = await h.broker.createSession(workspaceId);
  const first = await inject(h.app, {
    method: "POST",
    url: `/api/sessions/${original.id}/messages`,
    payload: { text: "Preserve this original request." },
  });
  assert.equal(first.statusCode, 202);
  await until(() => fixture.calls.length === 1);
  fixture.calls[0]!.update({
    type: "text",
    text: "Visible answer before background settlement failed.",
  });
  const queued = await inject(h.app, {
    method: "POST",
    url: `/api/sessions/${sibling.id}/messages`,
    payload: { text: "Queued sibling must not touch this workspace." },
  });
  assert.equal(queued.statusCode, 202);
  assert.equal(h.store.getSession(sibling.id).status, "queued");
  fixture.calls[0]!.resolve();
  await h.broker.idle();
  assert.equal(fixture.calls.length, 1);
  assert.equal(
    fixture.options.length,
    1,
    "queued sibling never launches a native process",
  );
  assert.ok(h.store.isQuarantined(workspaceId));
  assert.equal(h.store.getSession(original.id).status, "interrupted");
  assert.equal(h.store.getSession(sibling.id).status, "interrupted");
  const publicState = (
    await inject(h.app, `/api/sessions/${original.id}`)
  ).json();
  assert.deepEqual(
    publicState.messages.map((message: { content: string }) => message.content),
    [
      "Preserve this original request.",
      "Visible answer before background settlement failed.",
    ],
  );
  assert.ok(
    publicState.events.some(
      (event: Event) =>
        event.type === "error" &&
        event.data.code === "engine_settlement_unknown",
    ),
  );
  assert.equal(
    h.store.messages(sibling.id)[0]!.content,
    "Queued sibling must not touch this workspace.",
  );
  assert.ok(
    h.store
      .allEvents(sibling.id)
      .some(
        (event) =>
          event.type === "error" && event.data.code === "workspace_quarantined",
      ),
  );
  for (const sessionId of [original.id, sibling.id]) {
    assert.equal(
      h.store
        .allEvents(sessionId)
        .some(
          (event) => event.type === "state" && event.data.status === "idle",
        ),
      false,
      "unknown background settlement never reports idle",
    );
    assert.equal(
      (
        await inject(h.app, {
          method: "POST",
          url: `/api/sessions/${sessionId}/messages`,
          payload: { text: "No replay or new work before settlement review." },
        })
      ).statusCode,
      409,
    );
  }
});

for (const outcome of ["unknown", "failed", "cancelled", "deleted"] as const)
  test(
    `verified process cleanup releases the workspace without promoting ${outcome} prompt to success`,
    { timeout: 5000 },
    async (t) => {
      let confirmCleanup!: () => void;
      const cleanupProof = new Promise<void>((resolve) => {
        confirmCleanup = resolve;
      });
      t.after(() => confirmCleanup());
      const fixture = engines(true),
        baseFactory = fixture.factory;
      let originalId = "",
        closeStarted = false;
      fixture.factory = (options) => {
        const engine = baseFactory(options);
        return {
          ...engine,
          async prompt(text, attachments) {
            await engine.prompt(text, attachments);
            if (options.sessionId === originalId) {
              if (outcome === "failed")
                throw new Error("fixture ordinary prompt failure");
              throw Object.assign(
                new Error("fixture native settlement is unknown"),
                { code: "engine_settlement_unknown" },
              );
            }
          },
          async close() {
            if (options.sessionId === originalId) {
              closeStarted = true;
              await cleanupProof;
            }
            await engine.close();
          },
        };
      };
      const h = await setup(t, fixture),
        original = await h.session();
      originalId = original.id;
      const workspaceId = h.store.getSession(original.id).workspaceId;
      const sibling = await h.broker.createSession(workspaceId);
      const started = await inject(h.app, {
        method: "POST",
        url: `/api/sessions/${original.id}/messages`,
        payload: {
          text: "Preserve the accepted original request; never replay it.",
        },
      });
      assert.equal(started.statusCode, 202);
      await until(() => fixture.calls.length === 1);
      fixture.calls[0]!.update({
        type: "text",
        text: "Partial visible response before cleanup.",
      });
      assert.equal(
        (
          await inject(h.app, {
            method: "POST",
            url: `/api/sessions/${sibling.id}/messages`,
            payload: { text: "Explicit queued work in the shared workspace." },
          })
        ).statusCode,
        202,
      );
      if (outcome === "cancelled")
        assert.equal(
          (
            await inject(h.app, {
              method: "POST",
              url: `/api/sessions/${original.id}/cancel`,
              payload: {},
            })
          ).statusCode,
          202,
        );
      if (outcome === "deleted")
        assert.equal(
          (
            await inject(h.app, {
              method: "DELETE",
              url: `/api/sessions/${original.id}`,
            })
          ).statusCode,
          202,
        );
      fixture.calls[0]!.resolve();
      await until(() => closeStarted, "verified process cleanup attempt");
      assert.ok(h.store.isQuarantined(workspaceId));
      assert.equal(
        fixture.calls.length,
        1,
        "queued work cannot start before process cleanup proof",
      );
      assert.equal(h.store.getSession(sibling.id).status, "queued");
      assert.equal(
        h.store.allEvents(original.id).some((event) => event.type === "done"),
        false,
      );
      assert.ok(
        h.store.listSessions().some((session) => session.id === original.id),
        "deletion stays visible until process cleanup is proven",
      );
      confirmCleanup();
      await until(
        () => fixture.calls.length === 2,
        "queued sibling after cleanup proof",
      );
      assert.equal(fixture.calls[1]!.sessionId, sibling.id);
      assert.equal(h.store.isQuarantined(workspaceId), false);
      fixture.calls[1]!.resolve();
      await h.broker.idle();
      const stored = h.store.getSession(original.id, true);
      assert.equal(
        stored.status,
        outcome === "unknown"
          ? "interrupted"
          : outcome === "failed"
            ? "failed"
            : "idle",
      );
      assert.equal(stored.deleted, outcome === "deleted");
      assert.equal(stored.context?.stale, true);
      assert.equal(
        h.store.db
          .prepare("SELECT status FROM runs WHERE id=?")
          .get(started.json().runId)?.status,
        outcome === "unknown"
          ? "interrupted"
          : outcome === "failed"
            ? "failed"
            : "cancelled",
      );
      assert.deepEqual(
        h.store.messages(original.id).map((message) => message.content),
        [
          "Preserve the accepted original request; never replay it.",
          "Partial visible response before cleanup.",
        ],
      );
      assert.equal(
        fixture.calls.filter((call) => call.sessionId === original.id).length,
        1,
      );
      assert.equal(
        h.store
          .allEvents(original.id)
          .some((event) => event.type === "handoff"),
        false,
      );
      assert.equal(
        h.store
          .allEvents(original.id)
          .some(
            (event) =>
              event.type === "error" &&
              event.data.code ===
                (outcome === "failed"
                  ? "engine_failed"
                  : "engine_settlement_unknown"),
          ),
        outcome === "unknown" || outcome === "failed",
        "Stop/delete intent at prompt failure plus exact cleanup is cancellation",
      );
    },
  );

for (const scenario of ["confirmed", "cancel-rejected", "cancel-pending", "cancel-timeout", "cleanup-unknown", "settlement-unknown", "unexpected", "late-stop", "post-prompt-failure"] as const)
  test(`Stop prompt rejection race preserves proof boundaries: ${scenario}`, async (t) => {
    let confirmCancel!: () => void;
    let confirmCleanup!: () => void;
    const cancelProof = new Promise<void>((resolve) => { confirmCancel = resolve; });
    const cleanupProof = new Promise<void>((resolve) => { confirmCleanup = resolve; });
    t.after(() => { confirmCancel(); confirmCleanup(); });
    const fixture = engines(true), baseFactory = fixture.factory;
    let closeStarted = false;
    let logicalMs = 0;
    const timeline: { event: string; at: number }[] = [];
    const successfulStop = ["confirmed", "cancel-rejected", "cancel-pending", "cancel-timeout", "settlement-unknown"].includes(scenario);
    fixture.factory = (options) => {
      const engine = baseFactory(options);
      return {
        ...engine,
        async prompt(text, attachments) {
          await engine.prompt(text, attachments);
          if (fixture.calls.length !== 1 || scenario === "post-prompt-failure") return;
          if (scenario === "settlement-unknown")
            throw Object.assign(new Error("Unknown native receipt"), { code: "engine_settlement_unknown" });
          throw new Error("Prompt request rejected");
        },
        async cancel() {
          await engine.cancel();
          await cancelProof;
          if (scenario === "cancel-timeout") {
            timeline.push({ event: "cancel-timeout", at: logicalMs });
            throw new Error("Engine cancellation settlement timed out");
          }
          if (scenario === "cancel-rejected") throw new Error("Cancellation not proven");
        },
        async close() {
          closeStarted = true;
          await cleanupProof;
          if (scenario === "cleanup-unknown") throw new Error("Exact cleanup unconfirmed");
          if (scenario === "cancel-timeout") timeline.push({ event: "cleanup-confirmed", at: logicalMs });
          await engine.close();
        },
      };
    };
    const h = await setup(t, fixture), session = await h.session();
    if (scenario === "post-prompt-failure") {
      const discover = h.files.discover.bind(h.files);
      let discoveries = 0;
      h.files.discover = async (id) => {
        if (++discoveries === 2) throw new Error("Unrelated artifact discovery failure");
        return discover(id);
      };
    }
    const request = await inject(h.app, {
      method: "POST", url: `/api/sessions/${session.id}/messages`, payload: { text: "Bounded Stop fixture" },
    });
    await until(() => fixture.calls.length === 1);
    fixture.calls[0]!.update({ type: "text", text: "Original partial response" });
    if (scenario !== "unexpected" && scenario !== "late-stop")
      await inject(h.app, { method: "POST", url: `/api/sessions/${session.id}/cancel`, payload: {} });
    fixture.calls[0]!.resolve();
    if (scenario === "post-prompt-failure") confirmCancel();
    await until(() => closeStarted);
    if (scenario === "late-stop") {
      assert.ok(h.store.allEvents(session.id).some((event) =>
        event.type === "error" && event.data.code === "engine_failed"));
      await inject(h.app, { method: "POST", url: `/api/sessions/${session.id}/cancel`, payload: {} });
    }
    assert.equal(h.store.allEvents(session.id).some((event) => event.type === "done"), false);
    assert.ok(h.store.isQuarantined(h.store.getSession(session.id).workspaceId));
    if (successfulStop)
      assert.equal(h.store.allEvents(session.id).some((event) => event.type === "error"), false,
        "requested cancellation remains pending until exact cleanup is known");
    // Controlled promises model a 30s cancel deadline and cleanup at 46s.
    // No wall-clock timeout or 46-second sleep is used in this fixture.
    if (scenario === "cancel-timeout") logicalMs = 30_000;
    if (scenario !== "cancel-pending") confirmCancel();
    await delay(0);
    if (scenario === "cancel-timeout") {
      assert.deepEqual(timeline, [{ event: "cancel-timeout", at: 30_000 }]);
      assert.equal(h.store.allEvents(session.id).some((event) => event.type === "done"), false);
      logicalMs = 46_000;
    }
    confirmCleanup();
    await h.broker.idle();
    const errors = h.store.allEvents(session.id).filter((event) => event.type === "error");
    if (successfulStop) {
      assert.deepEqual(errors, []);
      if (scenario === "cancel-timeout")
        assert.deepEqual(timeline, [
          { event: "cancel-timeout", at: 30_000 },
          { event: "cleanup-confirmed", at: 46_000 },
        ]);
      // Even a still-pending cancel RPC cannot veto independently proven cleanup.
      confirmCancel();
      assert.equal(h.store.db.prepare("SELECT status FROM runs WHERE id=?").get(request.json().runId)?.status, "cancelled");
      assert.equal(h.store.getSession(session.id).status, "idle");
      assert.equal(h.store.isQuarantined(h.store.getSession(session.id).workspaceId), false);
      await inject(h.app, { method: "POST", url: `/api/sessions/${session.id}/messages`, payload: { text: "Explicit follow-up" } });
      await until(() => fixture.calls.length === 2);
      fixture.calls[1]!.resolve();
      await h.broker.idle();
      assert.deepEqual(h.store.messages(session.id).map((m) => m.content),
        ["Bounded Stop fixture", "Original partial response", "Explicit follow-up"]);
    } else {
      assert.ok(errors.some((event) => event.data.code ===
        (scenario === "settlement-unknown" ? "engine_settlement_unknown" : "engine_failed")));
      if (scenario === "cleanup-unknown") {
        assert.ok(errors.some((event) => event.data.code === "engine_cleanup_unknown"));
        assert.ok(h.store.isQuarantined(h.store.getSession(session.id).workspaceId));
      }
    }
  });

test(
  "late native cancel rejection cannot quarantine a workspace after verified process cleanup admits its successor",
  { timeout: 3000 },
  async (t) => {
    let rejectCancellation!: (error: Error) => void;
    const nativeCancellation = new Promise<void>((_resolve, reject) => {
      rejectCancellation = reject;
    });
    void nativeCancellation.catch(() => {});
    t.after(() =>
      rejectCancellation(new Error("fixture cancellation transport closed")),
    );
    const fixture = engines(true),
      baseFactory = fixture.factory;
    let originalId = "";
    fixture.factory = (options) => {
      const engine = baseFactory(options);
      return {
        ...engine,
        async prompt(text, attachments) {
          await engine.prompt(text, attachments);
          if (options.sessionId === originalId)
            throw Object.assign(new Error("fixture native proof missing"), {
              code: "engine_settlement_unknown",
            });
        },
        async cancel() {
          if (options.sessionId === originalId) return nativeCancellation;
          await engine.cancel();
        },
      };
    };
    const h = await setup(t, fixture),
      original = await h.session();
    originalId = original.id;
    const workspaceId = h.store.getSession(originalId).workspaceId;
    const successor = await h.broker.createSession(workspaceId);
    await inject(h.app, {
      method: "POST",
      url: `/api/sessions/${originalId}/messages`,
      payload: { text: "Original interrupted request" },
    });
    await until(() => fixture.calls.length === 1);
    await inject(h.app, {
      method: "POST",
      url: `/api/sessions/${successor.id}/messages`,
      payload: { text: "Explicit successor" },
    });
    assert.equal(
      (
        await inject(h.app, {
          method: "POST",
          url: `/api/sessions/${originalId}/cancel`,
          payload: {},
        })
      ).statusCode,
      202,
    );
    fixture.calls[0]!.resolve();
    await until(
      () => fixture.calls.length === 2,
      "verified close admits successor despite unresolved native cancel transport",
    );
    assert.equal(h.store.isQuarantined(workspaceId), false);
    assert.equal(h.store.getSession(successor.id).status, "running");
    rejectCancellation(
      new Error("late native cancellation rejection after process cleanup"),
    );
    await delay(10);
    assert.equal(
      h.store.isQuarantined(workspaceId),
      false,
      "a stale request cannot revoke the newer cleanup proof",
    );
    fixture.calls[1]!.resolve();
    await h.broker.idle();
    assert.equal(h.store.getSession(originalId).status, "idle");
    assert.equal(h.store.getSession(successor.id).status, "idle");
  },
);

test("ambiguous engine failure quarantines shared workspace, keeps partial history and sanitizes error", async (t) => {
  const fixture = engines();
  fixture.factory = (options) => ({
    async start() {
      options.onNativeSessionId("fixture-native-failure");
    },
    async prompt() {
      options.onUpdate({ type: "text", text: "Saved before failure" });
      throw new Error("private diagnostic fixture secret that must not leak");
    },
    async cancel() {},
    async close() {
      throw new Error("fixture process cleanup is unconfirmed");
    },
  });
  const h = await setup(t, fixture),
    s = await h.session();
  const response = await inject(h.app, {
    method: "POST",
    url: `/api/sessions/${s.id}/messages`,
    payload: { text: "original" },
  });
  assert.equal(response.statusCode, 202);
  await h.broker.idle();
  const state = (await inject(h.app, `/api/sessions/${s.id}`)).json();
  assert.equal(state.session.status, "failed");
  assert.equal(state.messages[1].content, "Saved before failure");
  assert.ok(
    state.events.some(
      (e: Event) => e.type === "error" && e.data.code === "engine_failed",
    ),
  );
  assert.equal(JSON.stringify(state).includes("private diagnostic"), false);
  assert.equal(h.revoked.length, 1);
  const retry = await inject(h.app, {
    method: "POST",
    url: `/api/sessions/${s.id}/messages`,
    payload: { text: "do not retry automatically" },
  });
  assert.equal(retry.statusCode, 409);
});

test("public API rejects rebinding, cross-origin writes/SSE and gateway bearer administration", async (t) => {
  const h = await setup(t),
    s = await h.session();
  const badRequests = [
    {
      method: "POST" as const,
      url: "/api/sessions",
      payload: {},
      headers: { host: "attacker.example" },
    },
    {
      method: "POST" as const,
      url: "/api/sessions",
      payload: {},
      headers: { origin: "http://attacker.example" },
    },
    {
      method: "POST" as const,
      url: "/api/sessions",
      payload: {},
      headers: { "sec-fetch-site": "cross-site" },
    },
    {
      method: "GET" as const,
      url: `/api/sessions/${s.id}/events`,
      headers: { origin: "http://attacker.example" },
    },
    {
      method: "GET" as const,
      url: `/api/sessions/${s.id}/events`,
      headers: { "sec-fetch-site": "same-site" },
    },
    {
      method: "POST" as const,
      url: "/api/sessions",
      payload: {},
      headers: { authorization: "Bearer fixture-inference-token" },
    },
  ];
  for (const req of badRequests) {
    const res = await inject(h.app, req);
    assert.equal(res.statusCode, 403, JSON.stringify(req));
    assert.equal(typeof res.json().error.code, "string");
    assert.equal(res.headers["access-control-allow-origin"], undefined);
  }
  assert.equal(
    (
      await inject(h.app, {
        method: "POST",
        url: "/api/sessions",
        payload: {},
        headers: {
          origin: "http://localhost",
          "sec-fetch-site": "same-origin",
        },
      })
    ).statusCode,
    200,
  );
  for (const after of ["-1", "1.1", "NaN", "9007199254740992"])
    assert.equal(
      (await inject(h.app, `/api/sessions/${s.id}/events?after=${after}`))
        .statusCode,
      400,
    );
  assert.equal(
    (
      await inject(h.app, {
        method: "POST",
        url: `/api/sessions/${s.id}/messages`,
        payload: { text: "x", model: "other" },
      })
    ).statusCode,
    400,
  );
  assert.equal(
    (
      await inject(h.app, {
        method: "POST",
        url: `/api/sessions/${s.id}/messages`,
        payload: { text: "" },
      })
    ).statusCode,
    400,
  );
  assert.equal(
    (await inject(h.app, "/api/sessions/..%2Fsecret")).statusCode,
    400,
  );
});

test("multipart uploads sanitize names, reject images and cross-chat attachment references", async (t) => {
  const h = await setup(t),
    s = await h.session(),
    other = await h.session();
  const result = await inject(h.app, {
    method: "POST",
    url: `/api/sessions/${s.id}/uploads`,
    ...multipart(
      "../../unsafe<script>.txt",
      "text/plain",
      "fixture attachment",
    ),
  });
  assert.equal(result.statusCode, 201, result.body);
  const file = result.json().attachment;
  assert.equal(file.name, "unsafe_script_.txt");
  assert.equal(file.size, 18);
  assert.equal(file.mimeType, "text/plain");
  assert.match(file.id, /^[a-zA-Z0-9_-]+$/);
  assert.equal("path" in file, false);
  assert.equal(
    (
      await inject(h.app, {
        method: "POST",
        url: `/api/sessions/${s.id}/uploads`,
        ...multipart("photo.png", "application/octet-stream", "not-image"),
      })
    ).statusCode,
    415,
  );
  assert.equal(
    (
      await inject(h.app, {
        method: "POST",
        url: `/api/sessions/${s.id}/uploads`,
        ...multipart("mislabelled.txt", "image/png", "not-image"),
      })
    ).statusCode,
    415,
  );
  assert.equal(
    (
      await inject(h.app, {
        method: "POST",
        url: `/api/sessions/${other.id}/messages`,
        payload: { text: "steal", attachmentIds: [file.id] },
      })
    ).statusCode,
    400,
  );
  assert.equal(
    (
      await inject(h.app, {
        method: "POST",
        url: `/api/sessions/${s.id}/messages`,
        payload: { text: "read", attachmentIds: [file.id] },
      })
    ).statusCode,
    202,
  );
  await h.broker.idle();
  assert.equal(h.fixture.calls[0]!.attachments.length, 1);
  assert.equal(
    (await inject(h.app, `/api/artifacts/${file.id}/download`)).statusCode,
    404,
  );
});

test("explicit reviewed vision availability enables image health and upload with safely sanitized Unicode names", async (t) => {
  const h = await setup(t, engines(), { visionAvailable: true }),
    s = await h.session();
  assert.equal(
    (await inject(h.app, "/api/health")).json().visionAvailable,
    true,
  );
  const uploaded = await inject(h.app, {
    method: "POST",
    url: `/api/sessions/${s.id}/uploads`,
    ...multipart(
      "načrt prostora 東京.png",
      "image/png",
      Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]),
    ),
  });
  assert.equal(uploaded.statusCode, 201, uploaded.body);
  const attachment = uploaded.json().attachment;
  assert.equal(attachment.mimeType, "image/png");
  assert.match(attachment.name, /^[a-zA-Z0-9._ -]+$/);
  assert.ok(attachment.name.includes(" "));
  const projected = await h.files.attachments(s.id, [attachment.id]);
  assert.equal(projected.length, 1);
  assert.equal(projected[0]!.name, attachment.name);
  assert.deepEqual(
    await readFile(projected[0]!.path),
    Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]),
  );
});

test(
  "multipart oversize/multiple files fail without retained attachment metadata or partial files",
  { timeout: 10000 },
  async (t) => {
    const h = await setup(t),
      s = await h.session();
    const oversized = await inject(h.app, {
      method: "POST",
      url: `/api/sessions/${s.id}/uploads`,
      ...multipart(
        "too-large.txt",
        "text/plain",
        Buffer.alloc(50 * 1024 * 1024 + 1, 120),
      ),
    });
    assert.equal(oversized.statusCode, 413, oversized.body);
    assert.equal(h.store.files(s.id, "attachment").length, 0);
    assert.equal((await readdir(path.join(h.dir, "uploads"))).length, 0);
    const boundary = "h001-fixture-boundary";
    const payload =
      ["one.txt", "two.txt"]
        .map(
          (filename) =>
            `--${boundary}\r\nContent-Disposition: form-data; name="file"; filename="${filename}"\r\nContent-Type: text/plain\r\n\r\nfixture\r\n`,
        )
        .join("") + `--${boundary}--\r\n`;
    const multiple = await inject(h.app, {
      method: "POST",
      url: `/api/sessions/${s.id}/uploads`,
      headers: { "content-type": `multipart/form-data; boundary=${boundary}` },
      payload,
    });
    assert.ok(
      multiple.statusCode >= 400 && multiple.statusCode < 500,
      multiple.body,
    );
    assert.equal(h.store.files(s.id, "attachment").length, 0);
    assert.equal((await readdir(path.join(h.dir, "uploads"))).length, 0);
  },
);

test("artifact transfer resolves registered ID only and keeps an immutable generated snapshot", async (t) => {
  const h = await setup(t),
    s = await h.session(),
    workspace = h.files.workspace(h.store.getSession(s.id).workspaceId);
  const file = path.join(workspace, "result.txt");
  await writeFile(file, "reviewed result");
  const artifact = await h.files.registerArtifact(s.id, file);
  await writeFile(file, "later workspace edit");
  const download = await inject(
    h.app,
    `/api/artifacts/${artifact.id}/download`,
  );
  assert.equal(download.statusCode, 200);
  assert.equal(download.body, "reviewed result");
  assert.equal(download.headers["content-type"], "application/octet-stream");
  assert.match(String(download.headers["content-disposition"]), /attachment/);
  assert.equal(
    (
      await inject(
        h.app,
        `/api/artifacts/${artifact.id}/download?path=/etc/passwd`,
      )
    ).statusCode,
    400,
  );
  assert.equal(
    (await inject(h.app, "/api/artifacts/result.txt/download")).statusCode,
    400,
  );
  assert.equal(
    (await inject(h.app, "/api/artifacts/unknown/download")).statusCode,
    404,
  );
  const listing = (
    await inject(h.app, `/api/sessions/${s.id}/artifacts`)
  ).json().artifacts;
  assert.equal(
    listing[0].downloadUrl,
    `/api/artifacts/${artifact.id}/download`,
  );
  assert.equal("path" in listing[0], false);
});

test("optional frontend serves ordinary assets but never symlink assets or private data trees", async (t) => {
  const root = await realpath(
      await mkdtemp(path.join(tmpdir(), "h001-static-test-")),
    ),
    web = path.join(root, "web");
  t.after(() => rm(root, { recursive: true, force: true }));
  await mkdir(web);
  await writeFile(
    path.join(web, "index.html"),
    "<!doctype html><p>Fixture frontend</p>",
  );
  await writeFile(path.join(web, "app.js"), "const fixture = true;");
  await writeFile(path.join(root, "private.txt"), "fixture private content");
  await symlink(path.join(root, "private.txt"), path.join(web, "leak.txt"));
  await symlink(root, path.join(web, "linked-directory"));
  const h = await setup(t, engines(), { webDist: web });
  const index = await inject(h.app, "/");
  assert.equal(index.statusCode, 200);
  assert.match(index.body, /Fixture frontend/);
  assert.equal((await inject(h.app, "/app.js")).statusCode, 200);
  for (const url of [
    "/leak.txt",
    "/linked-directory/private.txt",
    "/..%2Fprivate.txt",
  ]) {
    const response = await inject(h.app, url);
    assert.ok(response.statusCode >= 400, url);
    assert.equal(response.body.includes("fixture private content"), false);
  }
  const dataDir = path.join(root, "private-data");
  await assert.rejects(
    createApp({ ...h.options, dataDir, webDist: root }),
    /Static assets must be separate/,
  );
  await assert.rejects(
    createApp({ ...h.options, dataDir, webDist: dataDir }),
    /Static assets must be separate/,
  );
});

async function sse(
  port: number,
  url: string,
  headers: Record<string, string> = {},
) {
  let data = "";
  const request = http.get({
    hostname: "127.0.0.1",
    port,
    path: url,
    headers: { host: "localhost", ...headers },
  });
  const response = await new Promise<http.IncomingMessage>(
    (resolve, reject) => {
      request.once("response", resolve);
      request.once("error", reject);
    },
  );
  response.setEncoding("utf8");
  response.on("data", (value) => {
    data += value;
  });
  response.on("error", () => {});
  return {
    response,
    read: () => data,
    events: () =>
      data
        .split("\n\n")
        .filter((p) => p.startsWith("id:"))
        .map(
          (p) =>
            JSON.parse(
              p
                .split("\n")
                .find((v) => v.startsWith("data: "))!
                .slice(6),
            ) as Event,
        ),
    close() {
      response.destroy();
      request.destroy();
    },
  };
}

test("real HTTP SSE heartbeat/replay/Last-Event-ID are monotonic; browser disconnect does not cancel", async (t) => {
  const fixture = engines(true),
    h = await setup(t, fixture),
    s = await h.session();
  await h.app.listen({ host: "127.0.0.1", port: 0 });
  const address = h.app.server.address();
  assert.ok(address && typeof address === "object");
  const first = h.store.emit(s.id, "progress", {
    kind: "fixture",
    label: "before first connection",
  });
  const stream = await sse(address.port, `/api/sessions/${s.id}/events`);
  t.after(() => stream.close());
  assert.equal(stream.response.statusCode, 200);
  assert.match(
    String(stream.response.headers["content-type"]),
    /text\/event-stream/,
  );
  await until(() => stream.events().some((e) => e.id === first.id));
  await until(() => stream.read().includes(": heartbeat"));
  await inject(h.app, {
    method: "POST",
    url: `/api/sessions/${s.id}/messages`,
    payload: { text: "must outlive the browser" },
  });
  await until(() => fixture.calls.length === 1);
  fixture.calls[0]!.update({ type: "text", text: "first chunk " });
  await until(() => stream.events().some((e) => e.type === "assistant_delta"));
  const cursor = stream.events().at(-1)!.id;
  stream.close();
  await delay(30);
  assert.equal(fixture.cancelled.length, 0);
  fixture.calls[0]!.update({ type: "text", text: "after disconnect" });
  fixture.calls[0]!.resolve();
  await h.broker.idle();
  const resumed = await sse(address.port, `/api/sessions/${s.id}/events`, {
    "last-event-id": String(cursor),
  });
  t.after(() => resumed.close());
  await until(() => resumed.events().some((e) => e.type === "done"));
  assert.deepEqual(resumed.events(), h.store.replay(s.id, cursor));
  assert.ok(resumed.events().every((e) => e.id > cursor));
  assert.equal(
    h.store.messages(s.id).at(-1)!.content,
    "first chunk after disconnect",
  );
  const explicit = await sse(
    address.port,
    `/api/sessions/${s.id}/events?after=${cursor}`,
    { "last-event-id": "0" },
  );
  t.after(() => explicit.close());
  await until(() => explicit.events().some((e) => e.type === "done"));
  assert.deepEqual(explicit.events(), h.store.replay(s.id, cursor));
  resumed.close();
  explicit.close();
});
