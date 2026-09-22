import assert from "node:assert/strict";
import test from "node:test";
import { mkdtemp, realpath, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { createApp } from "../src/app.js";

test("API rejects pinned slash commands without mutations; ordinary tasks and native compression still work", async (t) => {
  const dataDir = await realpath(await mkdtemp(path.join(tmpdir(), "h001-slash-")));
  const prompts: string[] = [];
  let launches = 0, tokens = 0, enqueues = 0;
  const h = await createApp({
    dataDir,
    allowedOrigins: ["http://localhost"],
    launcher: "/fixture/not-executed",
    gatewayUrl: "http://127.0.0.1:1/v1",
    issueToken: () => { tokens++; return "fixture-token"; },
    revokeToken: () => {},
    engineFactory: (options) => {
      launches++;
      return {
        async start() { options.onNativeSessionId("fixture-native"); },
        async prompt(text) {
          prompts.push(text);
          options.onUpdate({ type: "compaction", compactionId: `fixture-${prompts.length}`, status: "start" });
          options.onUpdate({ type: "compaction", compactionId: `fixture-${prompts.length}`, status: "completed" });
          options.onUpdate({ type: "text", text: "Fixture task completed" });
        },
        async cancel() {},
        async close() {},
      };
    },
  });
  t.after(async () => {
    await h.app.close();
    await rm(dataDir, { recursive: true, force: true });
  });
  const sessionResponse = await h.app.inject({
    method: "POST", url: "/api/sessions", headers: { host: "localhost" }, payload: {},
  });
  assert.equal(sessionResponse.statusCode, 200);
  const sessionId = sessionResponse.json().session.id as string;
  const enqueue = h.broker.enqueue.bind(h.broker);
  h.broker.enqueue = (...args) => { enqueues++; return enqueue(...args); };
  const send = (text: string, attachmentIds: string[] = []) => h.app.inject({
    method: "POST", url: `/api/sessions/${sessionId}/messages`,
    headers: { host: "localhost" }, payload: { text, attachmentIds },
  });
  const baseline = h.store.snapshot(sessionId);
  const changes = () => h.store.db.prepare("SELECT total_changes() AS count").get();
  const beforeChanges = changes();
  // Independently enumerate the ae65651 ACP roster and the reviewed skill aliases.
  const rejected = [
    "help", "new", "model", "status", "doctor", "context", "skills", "mcp",
    "usage", "compact", "technical-research", "code-investigation", "calculations",
    "technical-testing", "pdf", "code-review", "control-in-app-browser",
  ];
  for (const name of rejected) {
    for (const suffix of ["", " argument", "\nmultiline\ninstructions\t"]) {
      const text = `/${name}${suffix}`;
      const response = await send(text);
      assert.equal(response.statusCode, 400, text);
      assert.equal(response.json().error.code, "unsupported_slash_command", text);
      assert.match(response.json().error.message, /phrase a normal task/i);
      assert.deepEqual(changes(), beforeChanges, `no SQL mutation for ${text}`);
      assert.deepEqual(h.store.snapshot(sessionId), baseline, text);
      assert.equal(enqueues, 0);
      assert.equal(launches, 0);
      assert.equal(tokens, 0);
      assert.deepEqual(prompts, []);
    }
  }
  // Attachment references must not bypass the early command rejection.
  assert.equal((await send("/compact", ["fixture-attachment"])).json().error.code, "unsupported_slash_command");
  assert.deepEqual(changes(), beforeChanges);
  assert.equal(enqueues, 0);

  const ordinary = [
    "/home/user/project/readme.md", "/help/file.txt", "/pdf/report.pdf", "/model.json",
    "Please explain /help and /compact in the documentation.",
    "Use the technical-research skill to investigate this task.",
    "  /help", "/HELP", "/clear", "/unknown-task", "/skill:pdf", "/helpful",
    "Explain this file.\n/help is mentioned in it.",
  ];
  for (const text of ordinary) {
    const response = await send(text);
    assert.equal(response.statusCode, 202, `${text}: ${response.body}`);
    await h.broker.idle();
    assert.equal(h.store.db.prepare("SELECT status FROM runs WHERE id=?").get(response.json().runId)?.status, "completed");
    assert.equal(h.store.getSession(sessionId).status, "idle");
  }
  assert.deepEqual(prompts, ordinary);
  assert.deepEqual(h.store.messages(sessionId).filter((message) => message.role === "user").map((message) => message.content), ordinary);
  assert.equal(enqueues, ordinary.length);
  assert.equal(h.store.allEvents(sessionId).filter((event) => event.type === "progress" && event.data.label === "Compaction completed").length, ordinary.length);
});
