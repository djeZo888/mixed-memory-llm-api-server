import assert from "node:assert/strict";
import test, { type TestContext } from "node:test";
import { mkdtemp, realpath, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import sharp from "sharp";
import type { InjectOptions } from "fastify";
import { createApp, type AppOptions } from "../src/app.js";
import { ImageBroker } from "../src/image-broker.js";
import { createGateway } from "../src/gateway.js";
import type { ImageBackend, ImageJob, ImageSubmission } from "../src/image-contracts.js";
import type { EngineFactory } from "../src/contracts.js";
import { ApiError } from "../src/errors.js";

// SYNTHETIC SOURCE_ONLY: in-process backend/engine fixtures, no model, native
// host receipt, profile permission or production qualification is created here.
const evidence = "SYNTHETIC_SOURCE_ONLY_NO_HOST_PROFILE_PERMISSION";
const until = async (condition: () => boolean) => {
  const end = Date.now() + 4000;
  while (!condition()) {
    if (Date.now() >= end) throw new Error("Synthetic fixture condition timed out");
    await new Promise(resolve => setTimeout(resolve, 5));
  }
};
const generation = (requestId: string): ImageSubmission => ({ requestId, operation: "generation", prompt: evidence, size: "64x64", seed: 41 });
const operationDenied = (error: unknown) => error instanceof ApiError && error.statusCode === 503 && error.code === "image_operation_unqualified";

async function setup(t: TestContext, includeGate = true) {
  const dir = await realpath(await mkdtemp(join(tmpdir(), "v4-app-")));
  const png = await sharp({ create: { width: 64, height: 64, channels: 3, background: "#728344" } }).png().toBuffer();
  const calls: { sessionId: string; operation: "generation" | "edit" }[] = [];
  const dispatches: { input: Parameters<ImageBackend["execute"]>[0]; signal: AbortSignal; complete(): void }[] = [];
  const turns: { text: string; attachments: unknown[]; release(): void }[] = [];
  let generationQualified = true, qualifiedSession: string | undefined, forbiddenFallbackCalls = 0;
  const fullAcceptance = () => false;
  const referenceAcceptance = () => false;
  const operationQualified: NonNullable<AppOptions["imageOperationQualified"]> = (sessionId, operation) => {
    calls.push({ sessionId, operation });
    return sessionId === qualifiedSession && operation === "generation" && generationQualified;
  };
  const backend: ImageBackend = {
    async capabilities(signal) { signal.throwIfAborted(); return { evidence }; },
    profiles(value) {
      assert.deepEqual(value, { evidence });
      return [
        { operation: "generation", referenceCount: 0, size: "64x64", model: "synthetic-source-only" },
        { operation: "edit", referenceCount: 1, size: "64x64", model: "synthetic-source-only" },
      ];
    },
    async readiness(signal) { signal.throwIfAborted(); return { ready: true, idle: true }; },
    execute(input, signal) {
      // One call represents one backend dispatch/POST boundary. No HTTP listener
      // or external request is needed; settlement is explicitly controlled.
      return new Promise((resolve, reject) => {
        const finish = () => {
          clearTimeout(timer); signal.removeEventListener("abort", abort);
          resolve({ kind: "output", png, model: input.model, seed: input.seed });
        };
        const abort = () => { clearTimeout(timer); reject(new Error("Synthetic fixture abort")); };
        const timer = setTimeout(() => reject(new Error("Synthetic backend settlement timeout")), 4000);
        signal.addEventListener("abort", abort, { once: true });
        dispatches.push({ input: structuredClone(input), signal, complete: finish });
        if (signal.aborted) abort();
      });
    },
  };
  const codex: EngineFactory = options => ({
    async start() { options.onNativeSessionId("synthetic-native-id"); },
    async prompt(text, attachments = []) {
      await new Promise<void>(release => turns.push({ text, attachments, release }));
      options.onUpdate({ type: "text", text: "Synthetic text fixture; external image completion is separate" });
    },
    async cancel() { turns.forEach(turn => turn.release()); },
    async close() { turns.forEach(turn => turn.release()); },
  });
  const enginePolicy = { codex: { enabled: true, protocolQualified: true, engineVersion: "0.158.0", modelPolicyVersion: "synthetic-fixed", imageToolEnabled: false, delegationEnabled: false } };
  const options: AppOptions = {
    dataDir: dir, newChatEngine: "codex", allowedOrigins: ["http://localhost"],
    launcher: "/synthetic/source-only/never-executed", gatewayUrl: "http://127.0.0.1:1/v1",
    issueToken: () => "synthetic-unusable-token", revokeToken: () => {},
    engineFactory: () => { forbiddenFallbackCalls++; throw new Error("Historical fallback must remain unused"); },
    codexEngineFactory: codex, enginePolicy, imageBackend: backend,
    imageAcceptance: fullAcceptance, imageReferenceAcceptance: referenceAcceptance,
    technicalVision: { observerMs: 60000 },
    ...(includeGate ? { imageOperationQualified: operationQualified } : {}),
  };
  let application = await createApp(options);
  assert.ok(application.images instanceof ImageBroker, "Exercise the actual normal App broker");
  const gateway = createGateway({
    upstreamKey: "synthetic-unusable-key", images: application.images,
    codexImageJobsQualified: false, imageAcceptance: fullAcceptance,
    ownership: { recoveryReady: true, onRequestState: () => {} },
    upstreams: [
      { url: "http://127.0.0.1:1/v1", alias: "qwen3.8-27b-gpu0" },
      { url: "http://127.0.0.1:1/v1", alias: "qwen3.8-27b" },
    ],
  });
  t.after(async () => {
    dispatches.forEach(dispatch => dispatch.complete());
    turns.forEach(turn => turn.release());
    await gateway.close(); await application.app.close();
    assert.equal(forbiddenFallbackCalls, 0);
    await rm(dir, { recursive: true, force: true });
  });
  const browser = (url: string, body?: InjectOptions["payload"]) => application.app.inject({ method: body === undefined ? "GET" : "POST", url, headers: { host: "localhost" }, ...(body === undefined ? {} : { payload: body }), signal: AbortSignal.timeout(5000) });
  const session = (await browser("/api/sessions", {})).json().session;
  qualifiedSession = session.id;
  const accepted = await browser(`/api/sessions/${session.id}/messages`, { text: "Keep the synthetic original image run active", submissionId: "synthetic-original-submit" });
  assert.equal(accepted.statusCode, 202, accepted.body);
  const runId: string = accepted.json().runId;
  await until(() => turns.length === 1);
  await application.images!.reconcile();
  await until(() => application.images!.snapshot().lane === "idle");
  const token = gateway.issueToken(session.id, "codex");
  const internal = (url: string, body?: InjectOptions["payload"]) => gateway.app.inject({ method: body === undefined ? "GET" : "POST", url, headers: { authorization: `Bearer ${token}` }, ...(body === undefined ? {} : { payload: body }), signal: AbortSignal.timeout(5000) });
  return {
    session, runId, png, backend, calls, dispatches, options, browser, internal,
    get application() { return application; },
    revoke() { generationQualified = false; },
    async reopen() {
      turns.forEach(turn => turn.release()); await application.app.close();
      application = await createApp(options);
    },
    submit(body: ImageSubmission) { return application.images!.submit(session.id, body); },
    job(id: string): ImageJob { return application.images!.get(session.id, id); },
  };
}

test("SOURCE_ONLY App forwards exact generation-only callback; edit, creative child and legacy flags stay closed", async t => {
  const f = await setup(t);
  assert.equal(f.application.images!.options.operationQualified, f.options.imageOperationQualified);
  const submitted = await f.submit(generation("generation-only"));
  await until(() => f.dispatches.length === 1);
  assert.equal(submitted.sessionId, f.session.id); assert.equal(submitted.runId, f.runId);
  assert.equal(submitted.operation, "generation"); assert.deepEqual(submitted.references, []);
  await assert.rejects(f.submit({ requestId: "edit-denied", operation: "edit", prompt: evidence, size: "64x64", references: [{ fileId: "synthetic-owned-reference" }] }), operationDenied);
  assert.ok(f.calls.some(call => call.operation === "edit" && call.sessionId === f.session.id));
  assert.ok(f.calls.filter(call => call.operation === "generation").length >= 2, "Check admission and dispatch, not a disconnected private client");
  assert.equal(f.options.enginePolicy?.codex?.imageToolEnabled, false);
  assert.equal(f.options.enginePolicy?.codex?.delegationEnabled, false);
  assert.equal(f.options.imageAcceptance?.(f.session.id), false);
  assert.equal(f.options.imageReferenceAcceptance?.(f.session.id), false);
  const health = (await f.browser("/api/health")).json();
  assert.equal(health.engines.codex.imageToolEnabled, false);
  assert.equal(health.engines.codex.capabilityDetails.nativeMedia.supported, false);
  // Current R01 gateway legacy full-operation/child gates remain closed; R02
  // must independently integrate its trusted generation-only gateway producer.
  assert.equal((await f.internal("/v1/image-jobs", generation("legacy-full-route-closed"))).statusCode, 403);
  assert.equal((await f.internal("/v1/chat/completions", { messages: [{ role: "user", content: evidence }] })).statusCode, 403);
  assert.equal((await f.internal(`/v1/image-jobs/${submitted.id}/approval`, { decision: "approve" })).statusCode, 403);
  const references = await f.browser(`/api/sessions/${f.session.id}/messages`, { text: "Edit the selected reference", imageReferences: ["synthetic-owned-reference"], submissionId: "creative-reference-denied" });
  assert.equal(references.statusCode, 400); assert.equal(references.json().error.code, "codex_image_tool_unavailable");
  const boundary = "synthetic-v4-boundary";
  const upload = await f.application.app.inject({ method: "POST", url: `/api/sessions/${f.session.id}/uploads`, headers: { host: "localhost", "content-type": `multipart/form-data; boundary=${boundary}` }, payload: Buffer.concat([Buffer.from(`--${boundary}\r\nContent-Disposition: form-data; name="file"; filename="owned.png"\r\nContent-Type: image/png\r\n\r\n`), f.png, Buffer.from(`\r\n--${boundary}--\r\n`)]) });
  assert.equal(upload.statusCode, 400); assert.equal(upload.json().error.code, "codex_image_tool_unavailable");
  assert.equal(f.application.store.files(f.session.id, "attachment").length, 0);
  const forged = await f.browser(`/api/sessions/${f.session.id}/messages`, { text: evidence, imageOperationQualified: true });
  assert.equal(forged.statusCode, 400);
  assert.equal(f.dispatches.length, 1); assert.equal(f.application.images!.list(f.session.id).length, 1);
});

test("SOURCE_ONLY unqualified new jobs are refused; absent callback preserves historic normal-broker admission", async t => {
  const f = await setup(t);
  f.revoke();
  await assert.rejects(f.submit(generation("unqualified-new")), operationDenied);
  await assert.rejects(f.submit({ requestId: "unqualified-edit", operation: "edit", prompt: evidence, references: [{ fileId: "synthetic-reference" }] }), operationDenied);
  assert.equal(f.application.images!.list(f.session.id).length, 0); assert.equal(f.dispatches.length, 0);
  const legacy = await setup(t, false);
  assert.equal(legacy.application.images!.options.operationQualified, undefined);
  const job = await legacy.submit(generation("legacy-absent-gate"));
  await until(() => legacy.dispatches.length === 1);
  assert.equal(job.operation, "generation"); assert.equal(legacy.calls.length, 0);
});

test("SOURCE_ONLY revocation before queued dispatch blocks it; retained status/artifacts survive without duplicate POST", async t => {
  const f = await setup(t), firstBody = generation("already-dispatched"), queuedBody = generation("queued-before-revocation");
  const first = await f.submit(firstBody);
  await until(() => f.dispatches.length === 1);
  const queued = await f.submit(queuedBody);
  assert.equal(queued.state, "queued"); assert.equal(queued.runId, f.runId);
  f.revoke();
  await assert.rejects(f.submit(generation("new-after-revocation")), operationDenied);
  assert.equal((await f.internal(`/v1/image-jobs/${first.id}`)).statusCode, 200);
  f.dispatches[0].complete();
  await until(() => f.job(first.id).state === "completed" && f.job(queued.id).state === "failed");
  const blocked = f.job(queued.id);
  assert.equal(blocked.error?.code, "image_operation_unqualified");
  assert.equal(blocked.startedAt, undefined); assert.equal(blocked.artifactId, undefined);
  assert.equal((await f.submit(queuedBody)).id, queued.id); assert.equal((await f.submit(firstBody)).id, first.id);
  const listed = await f.browser(`/api/sessions/${f.session.id}/image-jobs`);
  assert.equal(listed.statusCode, 200); assert.equal(listed.json().jobs.length, 2);
  const artifacts = await f.browser(`/api/sessions/${f.session.id}/artifacts`);
  assert.equal(artifacts.statusCode, 200);
  assert.equal(artifacts.json().artifacts.length, 1); assert.equal(artifacts.json().artifacts[0].id, f.job(first.id).artifactId);
  const downloaded = await f.browser(`/api/artifacts/${f.job(first.id).artifactId}/download`);
  assert.equal(downloaded.statusCode, 200); assert.deepEqual(downloaded.rawPayload, f.png);
  const terminalCancel = await f.browser(`/api/sessions/${f.session.id}/image-jobs/${queued.id}/cancel`, {});
  assert.equal(terminalCancel.statusCode, 200); assert.equal(terminalCancel.json().job.state, "failed");
  assert.equal(f.dispatches.length, 1, "No second or duplicate backend POST");
  await f.reopen();
  assert.equal(f.job(queued.id).state, "failed"); assert.equal(f.job(first.id).state, "completed");
  assert.equal((await f.submit(queuedBody)).id, queued.id); assert.equal(f.dispatches.length, 1);
});

test("SOURCE_ONLY real normal cancel targets the original running job after revocation; late output stays durably cancelled", async t => {
  const f = await setup(t), body = generation("original-cancel-job");
  const original = await f.submit(body);
  await until(() => f.dispatches.length === 1);
  f.revoke();
  const cancel = await f.browser(`/api/sessions/${f.session.id}/image-jobs/${original.id}/cancel`, {});
  assert.equal(cancel.statusCode, 200);
  assert.equal(cancel.json().job.id, original.id); assert.equal(cancel.json().job.runId, f.runId);
  assert.equal(cancel.json().job.cancelRequested, true); assert.equal(cancel.json().job.state, "running");
  assert.equal(f.application.images!.snapshot().lane, "active", "Stop intent does not invent backend settlement");
  assert.equal(f.dispatches[0].signal.aborted, false);
  assert.equal((await f.internal(`/v1/image-jobs/${original.id}/cancel`, {})).statusCode, 200);
  f.dispatches[0].complete();
  await until(() => f.job(original.id).state === "cancelled" && f.application.images!.snapshot().lane === "idle");
  const settled = f.job(original.id);
  assert.equal(settled.requestId, body.requestId); assert.equal(settled.runId, original.runId);
  assert.equal(settled.cancelRequested, true); assert.ok(settled.finishedAt);
  assert.ok(settled.artifactId, "Late valid output is retained without reporting success");
  const durable = f.application.store.db.prepare("SELECT data FROM h003_image_jobs WHERE id=?").get(original.id)!;
  assert.equal(JSON.parse(String(durable.data)).job.state, "cancelled");
  const imageEvents = f.application.store.snapshot(f.session.id).messages.filter(message => message.origin === "image_service" && message.imageJobId === original.id);
  assert.equal(imageEvents.length, 1);
  assert.match(imageEvents[0].content, /Image service result: cancelled\./);
  assert.match(imageEvents[0].content, /not a successful completion/);
  assert.ok(imageEvents.every(message => !/Image service result: completed\./.test(message.content)));
  assert.equal((await f.internal(`/v1/image-jobs/${original.id}`)).json().job.state, "cancelled");
  assert.equal((await f.browser(`/api/artifacts/${settled.artifactId}/download`)).statusCode, 200);
  assert.equal((await f.submit(body)).state, "cancelled");
  assert.equal((await f.browser(`/api/sessions/${f.session.id}/image-jobs/${original.id}/cancel`, {})).json().job.state, "cancelled");
  await f.reopen();
  assert.equal(f.job(original.id).state, "cancelled"); assert.equal((await f.submit(body)).id, original.id);
  assert.equal(f.dispatches.length, 1, "Terminal durable state never resubmits the original backend POST");
});

test("SOURCE_ONLY technical-vision construction and text routing remain independent of generation qualification", async t => {
  const f = await setup(t), vision = f.application.technicalVision;
  assert.equal(vision.journal.store, f.application.store);
  assert.equal(f.application.broker.currentTechnicalVisionRun(f.session.id)?.runId, f.runId);
  const before = await vision.capabilities(), callCount = f.calls.length;
  f.revoke();
  const after = await vision.capabilities();
  assert.deepEqual(after, before); assert.equal(f.calls.length, callCount);
  assert.equal(f.application.broker.options.technicalVisionAvailable?.(), vision.configured());
  assert.ok(f.application.broker.options.technicalVisionContext);
  assert.ok(f.application.broker.options.cancelTechnicalVision);
  assert.equal(f.options.enginePolicy?.codex?.imageToolEnabled, false);
  assert.equal(f.dispatches.length, 0);
});
