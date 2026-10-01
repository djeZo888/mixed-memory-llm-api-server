import assert from "node:assert/strict";
import test, { type TestContext } from "node:test";
import { mkdtemp, rm, readFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { Readable } from "node:stream";
import sharp from "sharp";
import { createApp } from "../src/app.js";
import { createGateway } from "../src/gateway.js";
import { loadTechnicalVisionQualification, isTechnicalVisionQualification } from "../src/technical-vision-qualification.js";
import type { EngineFactory } from "../src/contracts.js";
import { generation0, service } from "./technical-vision-fixtures.js";

const until = async (predicate: () => boolean) => { const end = Date.now() + 4000; while (!predicate()) { if (Date.now() > end) throw Error("fixture condition timed out"); await new Promise(r => setTimeout(r, 5)); } };
async function setup(t: TestContext, qualified = true) {
  const fixture = await generation0(t, { requestMs: 70, capacity: 8 });
  const dir = await mkdtemp(join(tmpdir(), "vw-"));
  const calls: { text: string; attachments: unknown[]; release: () => void }[] = [];
  const factory: EngineFactory = opts => ({ async start() { opts.onNativeSessionId("fixture-native"); }, async prompt(text, attachments = []) { let release!: () => void; const wait = new Promise<void>(r => { release = r; }); calls.push({ text, attachments, release }); await wait; opts.onUpdate({ type: "text", text: "Fixture native text only" }); }, async cancel() { calls.forEach(c => c.release()); }, async close() { calls.forEach(c => c.release()); } });
  const appOptions = { approvalProxyKey: "fixture-human-control-only", dataDir: dir, engineFactory: factory, codexEngineFactory: factory, enginePolicy: { codex: { enabled: true, protocolQualified: true, engineVersion: "0.158.0", modelPolicyVersion: "fixture-fixed" } }, launcher: "/fixture/launcher", gatewayUrl: "http://127.0.0.1:8081/v1", issueToken: () => "fixture-token", revokeToken: () => {}, newChatEngine: "codex" as const, allowedOrigins: ["http://localhost"], ...(qualified ? { technicalVision: { fixture: { service, client: { expectedService: service, fixtureOrigin: fixture.fixtureOrigin, key: () => "fixture-host-only-key", requestMs: 70 } }, observerMs: 60000 } } : {}) };
  let application = await createApp(appOptions);
  const inject = (url: string, body?: unknown, headers: Record<string,string> = {}) => application.app.inject({ url, method: body === undefined ? "GET" : "POST", ...(body === undefined ? {} : { payload: body }), headers: { host: "localhost", ...headers } });
  t.after(async () => { calls.forEach(c => c.release()); await application.app.close(); await rm(dir, { recursive: true, force: true }); });
  const session = (await inject("/api/sessions", {})).json().session;
  const png = await sharp({ create: { width: 120, height: 80, channels: 3, background: "white" } }).png().toBuffer();
  const file = await application.files.upload(session.id, "owned.png", "image/png", Readable.from(png));
  return { fixture, dir, calls, inject, session, file, png, get application() { return application; }, async reopen() { calls.forEach(c => c.release()); await application.app.close(); application = await createApp(appOptions); } };
}

function completeTechnical(s: Awaited<ReturnType<typeof setup>>, jobId: string) {
  const j = s.fixture.jobs.get(jobId)!; j.state = "completed"; j.settled = true; delete j.queuePosition;
  j.result = { schemaVersion: 1, service, source: structuredClone(j.source), description: "Explicit synthetic model result only", extraction: { text: [{ id: "literal1", kind: "text", exactText: "R1  10 kΩ\n  Vcc\n", evidenceIds: ["region1"] }], tables: [], formulas: [], layout: [] }, observations: { components: [], relationships: [] }, evidence: [{ id: "region1", page: 1, box: { x: 0, y: 0, width: 30, height: 20 } }], uncertainties: [{ id: "uncertain1", description: "Fixture crossing unresolved", evidenceIds: ["region1"], affectedIds: ["literal1"] }], derivedConclusions: [], electricalNetReconstruction: "not_qualified" };
}
function multipart(bytes: Buffer, filename = "owned.png") { const boundary = "fixture-wiring-boundary"; return { bytes: Buffer.concat([Buffer.from(`--${boundary}\r\nContent-Disposition: form-data; name="file"; filename="${filename}"\r\nContent-Type: image/png\r\n\r\n`), bytes, Buffer.from(`\r\n--${boundary}--\r\n`)]), type: `multipart/form-data; boundary=${boundary}` }; }

test("production main fixed root gate is closed; forged live bool/config and generation0 cannot grant acceptance", async () => {
  assert.equal(loadTechnicalVisionQualification(), undefined);
  assert.equal(isTechnicalVisionQualification({ service, enabled: true, evidenceSha256: "a".repeat(64) }), false);
  const main = await readFile(new URL("../src/main.ts", import.meta.url), "utf8");
  assert.match(main, /loadTechnicalVisionQualification\(\)/); assert.match(main, /technicalVision: application.technicalVision/);
});

test("normal app/broker upload and send use technical specialist while creative qualification and native pixels stay closed", async t => {
  const s = await setup(t);
  const health = (await s.inject("/api/health")).json();
  assert.equal(health.technicalVision.available, true); assert.equal(health.technicalVision.qualification, "fixture_only"); assert.equal(health.engines.codex.imageToolEnabled, false); assert.equal(health.engines.codex.capabilityDetails.nativeMedia.supported, false);
  const form = multipart(s.png), upload = await s.inject(`/api/sessions/${s.session.id}/uploads`, form.bytes, { "content-type": form.type });
  assert.equal(upload.statusCode, 201, upload.body);
  const uploaded = upload.json().attachment;
  const result = await s.inject(`/api/sessions/${s.session.id}/messages`, { text: "Read exact labels", attachmentIds: [uploaded.id], submissionId: "original-submit" });
  assert.equal(result.statusCode, 202, result.body); const runId = result.json().runId;
  await until(() => s.calls.length === 1);
  assert.equal(s.fixture.counters().admissions, 1); assert.equal(s.calls[0].attachments.length, 0); assert.match(s.calls[0].text, /never native Codex pixels/);
  const record = s.application.technicalVision.journal.records()[0];
  assert.equal(record.owner.runId, runId); assert.equal(record.owner.sessionId, s.session.id); assert.equal(record.source?.sha256, (await import("node:crypto")).createHash("sha256").update(s.png).digest("hex"));
  assert.ok(s.application.store.snapshot(s.session.id).messages.some(m => m.origin === "technical_vision"));
  const deniedCreative = await s.inject(`/api/sessions/${s.session.id}/messages`, { text: "Edit", imageReferences: [uploaded.id], submissionId: "creative-submit" });
  assert.equal(deniedCreative.statusCode, 400);
});

test("authenticated gateway strict fields, original owner followup after run end, cross-session negatives", async t => {
  const s = await setup(t), sent = await s.inject(`/api/sessions/${s.session.id}/messages`, { text: "Keep original running", submissionId: "gateway-original" });
  await until(() => s.calls.length === 1); const runId = sent.json().runId;
  const gateway = createGateway({ upstreamKey: "fixture-upstream", technicalVision: s.application.technicalVision });
  t.after(() => gateway.close()); await gateway.app.ready();
  const token = gateway.issueToken(s.session.id, "codex");
  const gw = (body: unknown, route = "/v1/technical-vision-jobs", bearer = token) => gateway.app.inject({ method: "POST", url: route, headers: { authorization: `Bearer ${bearer}` }, payload: body });
  assert.equal((await gw({ requestId: "forged", source: { fileId: s.file.id }, owner: { runId: "attacker" } })).statusCode, 400);
  assert.equal((await gw({ requestId: "forged-endpoint", source: { fileId: s.file.id }, endpoint: "http://attacker" })).statusCode, 400);
  assert.equal((await gw({}, "/v1/technical-vision-jobs", "wrong")).statusCode, 401);
  const admitted = await gw({ requestId: "gateway-request", source: { fileId: s.file.id }, crops: [{ id: "label", page: 1, x: 0, y: 0, width: 30, height: 20 }] });
  assert.equal(admitted.statusCode, 200, admitted.body); const handle = admitted.json().handle;
  const record = s.application.technicalVision.journal.records()[0]; assert.equal(record.owner.runId, runId);
  const other = (await s.inject("/api/sessions", {})).json().session;
  assert.equal((await gw({}, `/v1/technical-vision-jobs/${handle}/status`, gateway.issueToken(other.id, "codex"))).statusCode, 404);
  assert.equal((await gw({ owner: record.owner }, `/v1/technical-vision-jobs/${handle}/cancel`)).statusCode, 400);
  s.calls[0].release(); await until(() => s.application.store.runSnapshot(runId).status === "completed");
  const later = await s.inject(`/api/sessions/${s.session.id}/messages`, { text: "Distinct later run", submissionId: "later-submit" });
  await until(() => s.calls.length === 2);
  assert.equal(s.application.broker.currentTechnicalVisionRun(s.session.id)?.runId, later.json().runId);
  completeTechnical(s, record.jobId!);
  const status = await gw({}, `/v1/technical-vision-jobs/${handle}/status`); assert.equal(status.statusCode, 200, status.body);
  const terminal = s.application.store.message(handle); assert.equal(terminal.runId, runId); assert.notEqual(terminal.runId, later.json().runId); assert.match(terminal.content, /electricalNetReconstruction/);
  assert.equal(s.fixture.counters().submitCalls, 1);
  assert.equal((await s.inject(`/api/sessions/${s.session.id}/technical-vision-jobs/${handle}/cancel`, {})).statusCode, 403);
});

test("terminal Store transaction dedup survives lost ack and reopen; original content/run immutable", async t => {
  const s = await setup(t); const sent = await s.inject(`/api/sessions/${s.session.id}/messages`, { text: "Analyze", attachmentIds: [s.file.id], submissionId: "dedup-submit" });
  await until(() => s.calls.length === 1); const record = s.application.technicalVision.journal.records()[0]; completeTechnical(s, record.jobId!);
  let loseAck = true; const original = s.application.technicalVision.journal.deliverOnce.bind(s.application.technicalVision.journal);
  s.application.technicalVision.journal.deliverOnce = async (...args) => { await original(...args); if (loseAck) { loseAck = false; throw Error("fixture lost ack after COMMIT"); } };
  await assert.rejects(s.application.technicalVision.followup(s.session.id, record.handle, "status"));
  const first = s.application.store.message(record.handle).content;
  await s.application.technicalVision.followup(s.session.id, record.handle, "status");
  assert.equal(s.application.store.db.prepare("SELECT COUNT(*) AS n FROM h043_vision_deliveries").get()!.n, 1);
  const terminalEvents = () => s.application.store.replay(s.session.id, 0).filter(e => e.type === "message" && (e.data.message as any)?.technicalVision?.settled === true);
  assert.equal(terminalEvents().length, 1); s.calls[0].release(); await until(() => s.application.store.runSnapshot(sent.json().runId).status === "completed");
  await s.reopen(); await s.application.technicalVision.followup(s.session.id, record.handle, "lookup");
  assert.equal(terminalEvents().length, 1); assert.equal(s.application.store.message(record.handle).content, first); assert.equal(s.fixture.counters().submitCalls, 1);
  const j = s.fixture.jobs.get(record.jobId!)!; j.result = { ...j.result!, description: "Changed terminal forbidden" };
  await assert.rejects(s.application.technicalVision.followup(s.session.id, record.handle, "status"));
  assert.equal(s.application.store.message(record.handle).content, first);
});

test("ambiguous POST is one claim across restart and source deletion; explicit lookup/cancel uses original request", async t => {
  const s = await setup(t); s.fixture.controls.loseSubmitResponse = true;
  const send = await s.inject(`/api/sessions/${s.session.id}/messages`, { text: "Analyze", attachmentIds: [s.file.id], submissionId: "ambiguous-submit" });
  await until(() => s.calls.length === 1); const r = s.application.technicalVision.journal.records()[0];
  assert.equal(r.originalFailure, "timeout"); assert.equal(s.fixture.counters().submitCalls, 1); assert.equal(s.fixture.counters().admissions, 1);
  await rm(join(s.application.files.root, "uploads", s.file.path)); s.calls[0].release(); await until(() => s.application.store.runSnapshot(send.json().runId).status === "completed"); await s.reopen();
  assert.equal(s.application.technicalVision.list(s.session.id)[0].state, "interrupted");
  await s.application.technicalVision.followup(s.session.id, r.handle, "lookup");
  assert.equal(s.application.technicalVision.journal.records()[0].originalFailure, "timeout"); assert.equal(s.fixture.counters().submitCalls, 1);
  await s.application.technicalVision.followup(s.session.id, r.handle, "cancel"); assert.equal(s.fixture.counters().cancellationCalls, 1);
  assert.equal(s.application.store.message(r.handle).technicalVision?.state, "cancelled");
});

test("normal caps reject oversize upload and multi-page/PDF dispatch; durable claim precedes readiness/source", async t => {
  const s = await setup(t); const big = await sharp({ create: { width: 2048, height: 1025, channels: 3, background: "white" } }).png().toBuffer(); const form = multipart(big);
  const upload = await s.inject(`/api/sessions/${s.session.id}/uploads`, form.bytes, { "content-type": form.type }); assert.equal(upload.statusCode, 400, upload.body);
  const sent = await s.inject(`/api/sessions/${s.session.id}/messages`, { text: "Keep running", submissionId: "caps-submit" }); await until(() => s.calls.length === 1);
  const r = await s.application.technicalVision.invoke(s.session.id, { requestId: "pdf-pages", source: { fileId: s.file.id }, pages: [1,2] });
  assert.equal(r.response.isError, true); assert.equal(s.fixture.counters().submitCalls, 0);
  assert.equal(s.application.technicalVision.journal.records()[0].owner.runId, sent.json().runId);
  const journal = s.application.technicalVision.journal;
  const duplicate = await Promise.all([journal.claim({ ...journal.records()[0] }), journal.claim({ ...journal.records()[0] })]); assert.deepEqual(duplicate, [false, false]);
});

test("unqualified technical path cannot borrow creative/native availability", async t => {
  const s = await setup(t, false); const form = multipart(s.png); const upload = await s.inject(`/api/sessions/${s.session.id}/uploads`, form.bytes, { "content-type": form.type }); assert.equal(upload.statusCode, 400);
  assert.equal((await s.inject("/api/technical-vision-capabilities")).json().available, false); assert.equal(s.fixture.counters().submitCalls, 0);
});


test("concurrent duplicate admissions claim once before HTTP and ambiguous source cannot get a new run/request", async t => {
  const s = await setup(t); await s.inject(`/api/sessions/${s.session.id}/messages`, { text: "Keep creator running", submissionId: "race-submit" }); await until(() => s.calls.length === 1);
  const input = { requestId: "concurrent-original", source: { fileId: s.file.id } };
  const outcomes = await Promise.allSettled([s.application.technicalVision.invoke(s.session.id, input), s.application.technicalVision.invoke(s.session.id, input)]);
  assert.ok(outcomes.some(r => r.status === "fulfilled")); assert.equal(s.fixture.counters().submitCalls, 1); assert.equal(s.application.technicalVision.journal.records().length, 1);
  const original = s.application.technicalVision.journal.records()[0];
  assert.ok(original.pageImages?.[0].sha256); assert.deepEqual(original.input?.source, { fileId: s.file.id });
  const job = s.fixture.jobs.get(original.jobId!)!; job.state = "interrupted"; job.settled = false; job.error = { code: "interrupted", message: "Explicit fixture restart" }; delete job.queuePosition;
  await s.application.technicalVision.followup(s.session.id, original.handle, "status");
  const blocked = await s.application.technicalVision.invoke(s.session.id, { requestId: "new-key-for-old-unknown", source: { fileId: s.file.id } });
  assert.equal(blocked.handle, original.handle); assert.equal(blocked.response.isError, true); assert.equal(s.fixture.counters().submitCalls, 1);
});

test('public retained-job controls use exact human proxy key, bounded fields and authorized original journal scope', async t => {
  const s=await setup(t);
  await s.inject(`/api/sessions/${s.session.id}/messages`,{text:'Keep original running',submissionId:'human-control-origin'});
  await until(()=>s.calls.length===1);
  const admitted=await s.application.technicalVision.invoke(s.session.id,{requestId:'human-control-request',source:{fileId:s.file.id}});
  const route=`/api/sessions/${s.session.id}/technical-vision-jobs/${admitted.handle}/status`;
  const auth={'x-ai-harness-approval-proxy':'fixture-human-control-only'};
  assert.equal((await s.inject(route,{}, {'x-ai-harness-approval-proxy':'spoofed'})).statusCode,403);
  assert.equal((await s.inject(route,{}, {...auth,authorization:'Bearer raw-engine-token'})).statusCode,403);
  assert.equal((await s.inject(route,{owner:'forged'},auth)).statusCode,400);
  assert.equal((await s.inject(route+'?requestId=new',{},auth)).statusCode,400);
  assert.equal((await s.inject(route,{padding:'x'.repeat(1100)},auth)).statusCode,413);
  assert.ok((await s.inject(route)).statusCode>=400);
  const observed=await s.inject(route,{},auth);assert.equal(observed.statusCode,200,observed.body);
  const journal=await s.application.technicalVision.journalStatus(s.session.id,admitted.handle);
  assert.equal(journal.originalRunId,s.application.technicalVision.journal.records()[0].owner.runId);
  assert.equal(journal.settled,false);assert.equal(journal.terminalDelivered,false);
  const other=(await s.inject('/api/sessions',{})).json().session;
  assert.deepEqual((await s.inject(`/api/sessions/${other.id}/technical-vision-jobs`)).json().jobs,[]);
  await assert.rejects(s.application.technicalVision.journalStatus(other.id,admitted.handle));
  assert.equal((await s.inject('/api/technical-vision-capabilities',undefined,{authorization:'Bearer raw-engine-token'})).statusCode,403);
  assert.equal((await s.inject(`/api/sessions/${s.session.id}/technical-vision-jobs`,undefined,{authorization:'Bearer raw-engine-token'})).statusCode,403);
  completeTechnical(s,s.application.technicalVision.journal.records()[0].jobId!);
  assert.equal((await s.inject(route,{},auth)).statusCode,200);
  const terminal=await s.application.technicalVision.journalStatus(s.session.id,admitted.handle);
  assert.equal(terminal.settled,true);assert.equal(terminal.terminalDelivered,true);
  assert.match(terminal.response!.content[0].text,/R1  10 kΩ/);
  assert.ok(!terminal.response!.content[0].text.includes('fixture-human-control-only'));
  assert.equal(s.fixture.counters().submitCalls,1);
});
