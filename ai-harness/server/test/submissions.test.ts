import assert from "node:assert/strict";
import test, { type TestContext } from "node:test";
import { mkdtemp, realpath, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { Readable } from "node:stream";
import { createApp, type AppOptions } from "../src/app.js";
import { Store } from "../src/store.js";
import type { EngineKind } from "../src/contracts.js";
const policy = { enabled: true, protocolQualified: true, engineVersion: "fixture", modelPolicyVersion: "fixture" };
const body = (submissionId = "submission-a") => ({ submissionId, text: "An intentional repeat", attachmentIds: [], imageReferences: [] });
async function until(check: () => boolean) {
  for (let n = 0; n < 400; n++) {
    if (check()) return;
    await new Promise(resolve => setTimeout(resolve, 5));
  }
  assert.fail("Timed out waiting for local engine fixture");
}
async function setup(t: TestContext) {
  const dataDir = await realpath(await mkdtemp(join(tmpdir(), "h029-submission-")));
  const calls: { text: string; resolve: () => void; reject: (error: Error) => void }[] = [];
  const accepted: string[] = [];
  let frozen = false;
  const factory: AppOptions["engineFactory"] = options => ({
    async start() { options.onNativeSessionId(options.nativeSessionId ?? `native-${options.sessionId}`); },
    async prompt(text) {
      await new Promise<void>((resolve, reject) => { calls.push({ text, resolve, reject }); });
    },
    async cancel() { calls.forEach(call => call.resolve()); },
    async close() {},
  });
  const options: AppOptions = {
    dataDir, allowedOrigins: ["http://localhost"], launcher: "/unused", gatewayUrl: "http://fixture.invalid",
    issueToken: () => "fixture", revokeToken() {}, engineFactory: factory, codexEngineFactory: factory,
    enginePolicy: { codex: { ...policy } }, dispatchHeld: () => frozen,
    onRunAccepted: (_sessionId, runId) => accepted.push(runId),
  };
  let h = await createApp(options);
  t.after(async () => { calls.forEach(call => call.resolve()); await h.app.close(); await rm(dataDir, { recursive: true, force: true }); });
  return {
    get h() { return h; }, calls, accepted,
    post: (id: string, payload: unknown) => h.app.inject({ method: "POST", url: `/api/sessions/${id}/messages`, headers: { host: "localhost" }, payload }),
    unavailable() { frozen = true; options.enginePolicy!.codex!.enabled = false; },
    async restart() { await h.app.close(); h = await createApp(options); },
  };
}
for (const engine of ["minimax", "codex"] as EngineKind[]) {
  test(`${engine}: simultaneous, active, completed and restarted duplicates return one original run`, async t => {
    const f = await setup(t), session = await f.h.broker.createSession(undefined, engine);
    const [a, b] = await Promise.all([f.post(session.id, body()), f.post(session.id, body())]);
    assert.equal(a.statusCode, 202); assert.equal(b.statusCode, 202); assert.deepEqual(b.json(), a.json());
    await until(() => f.calls.length === 1);
    const events = f.h.store.allEvents(session.id);
    assert.deepEqual((await f.post(session.id, body())).json(), a.json());
    assert.deepEqual(f.h.store.allEvents(session.id), events);
    f.calls[0].resolve();
    await until(() => f.h.store.getSession(session.id).status === "idle");
    const terminalEvents = f.h.store.allEvents(session.id);
    assert.deepEqual((await f.post(session.id, body())).json(), a.json());
    assert.deepEqual(f.h.store.allEvents(session.id), terminalEvents);
    await f.restart(); f.unavailable();
    const restartedEvents = f.h.store.allEvents(session.id);
    assert.deepEqual((await f.post(session.id, body())).json(), a.json());
    assert.deepEqual(f.h.store.allEvents(session.id), restartedEvents);
    assert.equal(f.calls.length, 1); assert.equal(f.accepted.length, 1);
    assert.equal(f.h.store.snapshot(session.id).messages.filter(m => m.role === "user").length, 1);
    assert.equal(f.h.store.snapshot(session.id).runs.length, 1);
  });
  test(`${engine}: failed run remains failed across restart and same-ID replay`, async t => {
    const f = await setup(t), session = await f.h.broker.createSession(undefined, engine);
    const first = (await f.post(session.id, body())).json();
    await until(() => f.calls.length === 1);
    f.calls[0].reject(new Error("private fixture failure"));
    await until(() => f.h.store.getSession(session.id).status === "failed");
    await f.restart(); f.unavailable();
    const events = f.h.store.allEvents(session.id);
    assert.deepEqual((await f.post(session.id, body())).json(), first);
    assert.equal(f.h.store.snapshot(session.id).runs[0].status, "failed");
    assert.deepEqual(f.h.store.allEvents(session.id), events);
    assert.equal(f.calls.length, 1); assert.equal(f.accepted.length, 1);
  });
}
test("exact text, attachments and image refs conflict; input key ordering/default arrays are canonical; options rejected", async t => {
  const f = await setup(t), session = await f.h.broker.createSession();
  const first = (await f.post(session.id, { submissionId: "canonical", text: " Exact text\n" })).json();
  await until(() => f.calls.length === 1);
  const before = f.h.store.allEvents(session.id);
  assert.deepEqual((await f.post(session.id, { imageReferences: [], attachmentIds: [], text: " Exact text\n", submissionId: "canonical" })).json(), first);
  for (const change of [{ text: "Exact text" }, { attachmentIds: ["private-attachment"] }, { imageReferences: ["private-reference"] }]) {
    const response = await f.post(session.id, { submissionId: "canonical", text: " Exact text\n", ...change });
    assert.equal(response.statusCode, 409); assert.equal(response.json().error.code, "submission_conflict");
    assert.doesNotMatch(response.body, /Exact text|private-attachment|private-reference/);
  }
  const unsupported = await f.post(session.id, { submissionId: "canonical", text: " Exact text\n", options: { temperature: 0.1 } });
  assert.equal(unsupported.statusCode, 400); assert.equal(unsupported.json().error.code, "invalid_body");
  assert.deepEqual(f.h.store.allEvents(session.id), before);
  const repeated = await f.post(session.id, { submissionId: "new-action", text: " Exact text\n" });
  assert.notEqual(repeated.json().runId, first.runId);
  assert.equal(f.accepted.length, 2);
  f.calls[0].resolve(); await until(() => f.calls.length === 2); f.calls[1].resolve();
});
test("session-scoped IDs cannot retrieve another owned chat's run; first-submission ownership and deleted-chat guards remain", async t => {
  const f = await setup(t), a = await f.h.broker.createSession(), b = await f.h.broker.createSession();
  const attachment = await f.h.files.upload(a.id, "owned.txt", "text/plain", Readable.from(["owned content"]));
  const first = (await f.post(a.id, body())).json();
  const other = (await f.post(b.id, body())).json();
  assert.notEqual(first.runId, other.runId);
  assert.equal(f.h.store.snapshot(b.id).runs[0].id, other.runId);
  const before = f.h.store.snapshot(b.id).runs.length;
  const foreign = await f.post(b.id, { ...body("foreign"), attachmentIds: [attachment.id] });
  assert.equal(foreign.statusCode, 400); assert.equal(foreign.json().error.code, "invalid_attachment");
  assert.equal(f.h.store.snapshot(b.id).runs.length, before);
  f.h.store.requestDelete(a.id);
  assert.equal((await f.post(a.id, body())).statusCode, 409);
  f.h.store.finishDelete(a.id);
  assert.equal((await f.post(a.id, body())).statusCode, 404);
  await until(() => f.calls.length >= 1); f.calls.forEach(call => call.resolve());
});
test("attachment and image array order is semantic; replay skips staging and closed Codex image gates", async t => {
  const f = await setup(t), s = await f.h.broker.createSession(undefined, "codex");
  const attachments = [];
  for (const name of ["one.txt", "two.txt"]) attachments.push(await f.h.files.upload(s.id, name, "text/plain", Readable.from([name])));
  // Seed a previously accepted image submission using the store primitive. No
  // image job, capability call or native inference is performed by this fixture.
  const payload = { text: "Edit the owned references", attachmentIds: attachments.map(a => a.id), imageReferences: ["image-one", "image-two"] };
  const saved = f.h.store.createMessageSubmission(s.id, "retained-image", payload, () => true);
  f.h.store.updateRun(saved.runId, "completed"); f.h.store.setStatus(s.id, "idle");
  f.unavailable();
  const before = f.h.store.allEvents(s.id);
  assert.equal((await f.post(s.id, { ...payload, submissionId: "retained-image" })).json().runId, saved.runId);
  for (const change of [{ attachmentIds: [...payload.attachmentIds].reverse() }, { imageReferences: [...payload.imageReferences].reverse() }]) {
    const response = await f.post(s.id, { ...payload, ...change, submissionId: "retained-image" });
    assert.equal(response.statusCode, 409); assert.equal(response.json().error.code, "submission_conflict");
  }
  assert.deepEqual(f.h.store.allEvents(s.id), before); assert.equal(f.calls.length, 0); assert.equal(f.accepted.length, 0);
});
test("late event-insert failure rolls back mapping, run, refs, message, events, title and context without publication", async t => {
  const f = await setup(t), session = await f.h.broker.createSession();
  f.h.store.saveFile({ id: 'owned-image', sessionId: session.id, kind: 'artifact', path: 'original.png', name: 'original.png', mimeType: 'image/png', size: 10 });
  const before = f.h.store.snapshot(session.id); let published = 0;
  f.h.store.events.on(session.id, () => published++);
  f.h.store.db.exec("CREATE TEMP TRIGGER fail_submission BEFORE INSERT ON events WHEN NEW.type='progress' BEGIN SELECT RAISE(ABORT,'fixture creation fault'); END");
  const failed = await f.post(session.id, { ...body(), imageReferences: ['owned-image'] });
  assert.equal(failed.statusCode, 500);
  const after = f.h.store.snapshot(session.id);
  assert.deepEqual({ ...after, environment: undefined }, { ...before, environment: undefined });
  assert.equal(f.h.store.db.prepare("SELECT COUNT(*) AS n FROM h029_message_submissions").get()!.n, 0);
  assert.equal(f.h.store.db.prepare("SELECT COUNT(*) AS n FROM h003_run_image_refs").get()!.n, 0);
  assert.equal(published, 0); assert.equal(f.calls.length, 0); assert.equal(f.accepted.length, 0);
  f.h.store.db.exec("DROP TRIGGER fail_submission");
  assert.equal((await f.post(session.id, body())).statusCode, 202);
  await until(() => f.calls.length === 1); f.calls[0].resolve();
});
test("interrupted Store restart preserves durable ID without replaying queued work", async () => {
  const dir = await mkdtemp(join(tmpdir(), "h029-store-")), database = join(dir, "test.sqlite");
  let store = new Store(database);
  try {
    const session = store.createSession();
    const payload = { text: "Retained queued input", attachmentIds: [], imageReferences: [] };
    const saved = store.createMessageSubmission(session.id, "saved", payload, () => true);
    store.db.close(); store = new Store(database);
    const before = store.allEvents(session.id);
    const replay = store.createMessageSubmission(session.id, "saved", payload, () => { throw Error("must not readmit"); });
    assert.deepEqual(replay, { created: false, runId: saved.runId });
    assert.equal(store.snapshot(session.id).runs[0].status, "interrupted");
    assert.deepEqual(store.allEvents(session.id), before);
  } finally { store.db.close(); await rm(dir, { recursive: true, force: true }); }
});
test("legacy omitted IDs remain explicitly fresh requests and invalid IDs do not consume work", async t => {
  const f = await setup(t), session = await f.h.broker.createSession();
  const one = await f.post(session.id, { text: "legacy" }), two = await f.post(session.id, { text: "legacy" });
  assert.notEqual(one.json().runId, two.json().runId);
  assert.equal((await f.post(session.id, { text: "invalid", submissionId: "../wrong" })).statusCode, 400);
  assert.equal(f.accepted.length, 2);
  await until(() => f.calls.length === 1); f.calls[0].resolve(); await until(() => f.calls.length === 2); f.calls[1].resolve();
});
