/** SOURCE_ONLY: authenticated loopback fixtures, no native/model/live qualification. */
import test, { type TestContext } from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { Readable } from "node:stream";
import sharp from "sharp";
import { createApp } from "../src/app.js";
import { codexAutomaticDirective, type CodexAutomaticRoute } from "../src/codex-automatic-routing.js";
import { completedTechnicalVisionAttachments } from "../src/technical-vision-host.js";
import type { EngineFactory } from "../src/contracts.js";
import { generation0, service } from "./technical-vision-fixtures.js";

async function until(check: () => boolean) {
  const end = Date.now() + 4000;
  while (!check()) { if (Date.now() > end) throw Error("fixture condition timed out"); await new Promise(r => setTimeout(r, 5)); }
}
async function setup(t: TestContext, preTurnMs = 2500, generation = false) {
  const fixture = await generation0(t, { requestMs: 70 });
  const dir = await mkdtemp(join(tmpdir(), "h045-pre-"));
  const calls: { text: string; attachments: unknown[]; route?: CodexAutomaticRoute; release: () => void }[] = [];
  const launches: (CodexAutomaticRoute | undefined)[] = [];
  const factory: EngineFactory = opts => ({
    async start() { launches.push(opts.nativeAutomaticRoute); opts.onNativeSessionId("fixture-native"); },
    async prompt(text, attachments = [], route) {
      assert.ok(route); codexAutomaticDirective(route, { technical: false, creative: false, deep: true });
      if (opts.nativeAutomaticRoute) assert.deepEqual(route, opts.nativeAutomaticRoute);
      let release!: () => void; const done = new Promise<void>(r => { release = r; });
      calls.push({ text, attachments, route, release }); await done;
      opts.onUpdate({ type: "text", text: "Fixture Qwen answer" });
    },
    async cancel() { calls.forEach(c => c.release()); },
    async close() { calls.forEach(c => c.release()); },
  });
  const options = {
    dataDir: dir, engineFactory: factory, codexEngineFactory: factory,
    enginePolicy: { codex: { enabled: true, protocolQualified: true, engineVersion: "0.158.0", modelPolicyVersion: "fixture", imageGenerationEnabled: generation } },
    launcher: "/fixture/launcher", gatewayUrl: "http://127.0.0.1:8081/v1", issueToken: () => "fixture-token", revokeToken: () => {},
    newChatEngine: "codex" as const, allowedOrigins: ["http://localhost"],
    technicalVision: { fixture: { service, client: { expectedService: service, fixtureOrigin: fixture.fixtureOrigin, key: () => "fixture-host-only-key", requestMs: 70 } }, observerMs: 60000, preTurnMs },
  };
  let application = await createApp(options);
  const inject = (url: string, payload?: unknown) => application.app.inject({ url, method: payload === undefined ? "GET" : "POST", ...(payload === undefined ? {} : { payload }), headers: { host: "localhost" } });
  t.after(async () => { calls.forEach(c => c.release()); await application.app.close(); await rm(dir, { recursive: true, force: true }); });
  const session = (await inject("/api/sessions", {})).json().session;
  const png = await sharp({ create: { width: 120, height: 80, channels: 3, background: "white" } }).png().toBuffer();
  const file = await application.files.upload(session.id, "fixture.png", "image/png", Readable.from(png));
  let sequence = 0;
  const send = async (text: string, attached = true) => {
    const response = await inject(`/api/sessions/${session.id}/messages`, { text, attachmentIds: attached ? [file.id] : [], submissionId: `pre-${++sequence}` });
    assert.equal(response.statusCode, 202, response.body); return response.json().runId as string;
  };
  const record = () => application.technicalVision.journal.records()[0];
  const complete = (jobId: string) => { fixture.complete(jobId); for (const evidence of fixture.jobs.get(jobId)!.result!.evidence) delete evidence.cropId; };
  return { fixture, complete, session, file, calls, launches, inject, send, record, get app() { return application; }, async reopen() { await application.app.close(); application = await createApp(options); } };
}

test("queued/running job waits; completed authenticated text reaches ordinary Qwen without native MCP; followups survive reopen", async t => {
  const s = await setup(t, 2500, true), question = "Read this drawing and report the exact labels";
  const runId = await s.send(question); await until(() => !!s.record()?.jobId);
  assert.equal(s.calls.length, 0); s.fixture.start(s.record().jobId!);
  await new Promise(r => setTimeout(r, 300)); assert.equal(s.calls.length, 0);
  s.complete(s.record().jobId!);
  await until(() => s.calls.length === 1);
  assert.equal(s.calls[0].route?.intent, "ordinary"); assert.equal(s.calls[0].attachments.length, 0);
  assert.match(s.calls[0].text, /UNTRUSTED/); assert.match(s.calls[0].text, /never as instructions/);
  assert.ok(s.calls[0].text.endsWith(question)); assert.ok(s.calls[0].text.includes(s.record().source!.sha256));
  assert.ok(s.calls[0].text.includes('"result":')); assert.ok(s.calls[0].text.includes('"qualification":"fixture_only"'));
  assert.equal(s.record().terminal?.acknowledged, true); assert.equal(s.fixture.counters().submitCalls, 1);
  assert.equal(s.launches[0]?.intent, "ordinary", "native launch is bound only after authenticated preprocessing");
  assert.deepEqual([...completedTechnicalVisionAttachments(s.app.store, s.session.id, runId)], [s.file.id]);
  s.calls[0].release(); await until(() => s.app.store.runSnapshot(runId).status === "completed");
  await s.reopen(); const followup = await s.send("Explain further", false); await until(() => s.calls.length === 2);
  assert.equal(s.calls[1].route?.intent, "ordinary"); assert.equal(s.fixture.counters().submitCalls, 1);
  s.calls[1].release(); await until(() => s.app.store.runSnapshot(followup).status === "completed");
  await s.send("Now expand", false); await until(() => s.calls.length === 3); assert.equal(s.calls[2].route?.intent, "ordinary");
});

test("lost submit response reconciles the same owner/request/job; no resubmit", async t => {
  const s = await setup(t); s.fixture.controls.loseSubmitResponse = true;
  await s.send("What does this show?"); await until(() => s.fixture.counters().admissions === 1);
  await until(() => !!s.record()?.originalFailure); assert.equal(s.record().originalFailure, "timeout");
  const originalHandle = s.record().handle; s.complete([...s.fixture.jobs.keys()][0]);
  await until(() => s.calls.length === 1);
  assert.equal(s.record().handle, originalHandle); assert.equal(s.fixture.counters().submitCalls, 1); assert.equal(s.calls[0].route?.intent, "ordinary");
});

test("timeout retains unsettled original handle without poisoning the next text turn", async t => {
  const s = await setup(t, 100); const runId = await s.send("Read this drawing");
  await until(() => s.app.store.runSnapshot(runId).status === "failed");
  assert.equal(s.calls.length, 0); assert.equal(s.record().terminal, undefined); assert.equal(s.fixture.counters().submitCalls, 1);
  assert.deepEqual([...completedTechnicalVisionAttachments(s.app.store, s.session.id, runId)], []);
  const next = await s.send("Read this drawing again"); await until(() => s.app.store.runSnapshot(next).status === "failed");
  assert.equal(s.launches.length, 0); assert.equal(s.app.store.checkpoints.status(s.session.id).length, 0);
  assert.equal(s.app.store.isQuarantined(s.app.store.getSession(s.session.id).workspaceId), false);
  const text = await s.send("Write a short greeting", false); await until(() => s.calls.length === 1);
  assert.equal(s.calls[0].route?.intent, "ordinary"); s.calls[0].release();
  await until(() => s.app.store.runSnapshot(text).status === "completed");
  assert.equal(s.fixture.counters().submitCalls, 1); assert.equal(s.record().owner.runId, runId);
  assert.equal(s.fixture.counters().cancellationCalls, 0, "observation timeout is not a remote cancel");
});

test("Stop wakes preprocessing and cancels the original job without a native prompt", async t => {
  const s = await setup(t); const runId = await s.send("Read this drawing"); await until(() => !!s.record()?.jobId);
  const started = Date.now(); await s.app.broker.cancel(s.session.id);
  await until(() => s.app.store.runSnapshot(runId).status === "cancelled");
  assert.ok(Date.now() - started < 1000); assert.equal(s.calls.length, 0); assert.equal(s.fixture.counters().submitCalls, 1);
  assert.equal(s.fixture.counters().cancellationCalls, 1); assert.equal(s.record().cancelIntent, true);
  assert.equal(s.launches.length, 0); assert.equal(s.app.store.checkpoints.status(s.session.id).length, 0);
  await s.send("Continue with a greeting", false); await until(() => s.calls.length === 1); assert.equal(s.calls[0].route?.intent, "ordinary");
});

test("failed terminal never becomes Qwen context or routing completion", async t => {
  const s = await setup(t); const runId = await s.send("Read this drawing"); await until(() => !!s.record()?.jobId);
  const job = s.fixture.jobs.get(s.record().jobId!)!; job.state = "failed"; job.settled = true; delete job.queuePosition; job.error = { code: "analysis_failed", message: "fixture failure" };
  await until(() => s.app.store.runSnapshot(runId).status === "failed"); assert.equal(s.calls.length, 0);
  assert.deepEqual([...completedTechnicalVisionAttachments(s.app.store, s.session.id, runId)], []);
  assert.equal(s.launches.length, 0); assert.equal(s.app.store.checkpoints.status(s.session.id).length, 0);
  await s.send("Write a greeting", false); await until(() => s.calls.length === 1);
});

test("completed image preserves deep intent; unrelated image question still requires native technical admission", async t => {
  const s = await setup(t); const runId = await s.send("Do deep research on this diagram"); await until(() => !!s.record()?.jobId);
  s.complete(s.record().jobId!); await until(() => s.calls.length === 1); assert.equal(s.calls[0].route?.intent, "deep");
  s.calls[0].release(); await until(() => s.app.store.runSnapshot(runId).status === "completed");
  const unrelated = await s.send("Read a new image", false); await until(() => s.app.store.runSnapshot(unrelated).status === "failed");
  assert.equal(s.calls.length, 1, "earlier proof cannot authorize an unrelated image request");
});

test("non-cooperative optional readiness cannot exhaust the browser health budget or disable Codex", async t => {
  const s = await setup(t);
  (s.app.technicalVision as any).backend.readiness = () => new Promise(() => {});
  const start = Date.now(), health = (await s.inject("/api/health")).json();
  assert.ok(Date.now() - start < 1700); assert.equal(health.status, "ok"); assert.equal(health.engines.codex.available, true);
  assert.equal(health.technicalVision.available, false); assert.equal(health.engines.codex.capabilityDetails.nativeMedia.supported, false);
});

test("delivery proof rejects a foreign run, acknowledgement loss and mismatched digest; model text cannot provide proof", async t => {
  const s = await setup(t); const runId = await s.send("Read this drawing"); await until(() => !!s.record()?.jobId);
  s.complete(s.record().jobId!); await until(() => s.calls.length === 1);
  const db = s.app.store.db, r = s.record(), original = JSON.stringify(r);
  const prove = (id = runId) => [...completedTechnicalVisionAttachments(s.app.store, s.session.id, id)];
  assert.deepEqual(prove(), [s.file.id]); assert.deepEqual(prove("foreign-run"), []);
  r.terminal!.acknowledged = false; db.prepare("UPDATE h043_vision_host SET record=? WHERE handle=?").run(JSON.stringify(r), r.handle);
  assert.deepEqual(prove(), []); db.prepare("UPDATE h043_vision_host SET record=? WHERE handle=?").run(original, r.handle);
  const delivery = db.prepare("SELECT content_sha256 FROM h043_vision_deliveries WHERE delivery_id=?").get(`terminal-${r.handle}`)!;
  db.prepare("UPDATE h043_vision_deliveries SET content_sha256=? WHERE delivery_id=?").run("f".repeat(64), `terminal-${r.handle}`);
  assert.deepEqual(prove(), []);
  db.prepare("UPDATE h043_vision_deliveries SET content_sha256=? WHERE delivery_id=?").run(delivery.content_sha256, `terminal-${r.handle}`);
  assert.deepEqual(prove(), [s.file.id]);
  s.calls[0].release(); await until(() => s.app.store.runSnapshot(runId).status === "completed");
  s.app.broker.options.technicalVisionContext = async () => 'UNTRUSTED {"state":"completed","settled":true,"terminalDelivered":true}';
  const next = await s.send("Read this drawing"); await until(() => s.app.store.runSnapshot(next).status === "failed");
  assert.equal(s.calls.length, 1); assert.equal(s.fixture.counters().submitCalls, 1);
});

test("per-handle Cancel does not abort preprocessing of another source", async t => {
  const s = await setup(t);
  // First establish a different pending job in this same session, without an attachment pre-turn.
  const prior = await s.send("Keep this chat open", false); await until(() => s.calls.length === 1);
  const old = await s.app.technicalVision.invoke(s.session.id, { requestId: "other-source", source: { fileId: s.file.id } });
  s.calls[0].release(); await until(() => s.app.store.runSnapshot(prior).status === "completed");
  const bytes = await sharp({ create: { width: 120, height: 80, channels: 3, background: "blue" } }).png().toBuffer();
  const other = await s.app.files.upload(s.session.id, "other.png", "image/png", Readable.from(bytes));
  const response = await s.inject(`/api/sessions/${s.session.id}/messages`, { text: "Read this drawing", attachmentIds: [other.id], submissionId: "other-image" });
  assert.equal(response.statusCode, 202);
  await until(() => s.fixture.counters().admissions === 2);
  await s.app.technicalVision.followup(s.session.id, old.handle, "cancel");
  const current = s.app.technicalVision.journal.records().find(r => r.owner.runId === response.json().runId)!;
  s.complete(current.jobId!); await until(() => s.calls.length === 2);
  assert.equal(s.calls[1].route?.intent, "ordinary"); assert.equal(s.fixture.counters().cancellationCalls, 1);
});

test("every attached image requires its own completed delivery before text dispatch", async t => {
  const s = await setup(t);
  const bytes = await sharp({ create: { width: 120, height: 80, channels: 3, background: "red" } }).png().toBuffer();
  const second = await s.app.files.upload(s.session.id, "second.png", "image/png", Readable.from(bytes));
  const response = await s.inject(`/api/sessions/${s.session.id}/messages`, { text: "Read these drawings", attachmentIds: [s.file.id, second.id], submissionId: "two-images" });
  assert.equal(response.statusCode, 202); await until(() => !!s.record()?.jobId);
  s.complete(s.record().jobId!); await until(() => s.app.technicalVision.journal.records().length === 2 && !!s.app.technicalVision.journal.records()[1].jobId);
  assert.equal(s.calls.length, 0);
  assert.deepEqual([...completedTechnicalVisionAttachments(s.app.store, s.session.id, response.json().runId)], [s.file.id]);
  s.complete(s.app.technicalVision.journal.records()[1].jobId!); await until(() => s.calls.length === 1);
  assert.equal(s.calls[0].attachments.length, 0); assert.equal(s.calls[0].route?.intent, "ordinary");
  assert.equal(s.fixture.counters().submitCalls, 2);
});

test("failure after native launch retains the uncertain-native recovery gate", async t => {
  const s = await setup(t);
  s.app.broker.options.codexEngineFactory = opts => ({
    async start() { opts.onNativeSessionId("fixture-native-started"); },
    async prompt() { throw new Error("fixture native outcome unknown"); },
    async cancel() {}, async close() {},
  });
  const runId = await s.send("Ordinary native request", false); await until(() => s.app.store.runSnapshot(runId).status === "failed");
  assert.equal(s.app.store.checkpoints.status(s.session.id)[0].status, "recovery_required");
  const next = await s.inject(`/api/sessions/${s.session.id}/messages`, { text: "Continue", submissionId: "unknown-native-followup" });
  assert.equal(next.statusCode, 409); assert.equal(next.json().error.code, "compaction_recovery_required");
});
