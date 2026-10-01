import assert from "node:assert/strict";
import test from "node:test";
import { TechnicalVisionError, technicalVisionInputSchema } from "../src/technical-vision-contracts.js";
import { validateTechnicalVisionInput, validateTechnicalVisionIdentity, validateTechnicalVisionResult, validateTechnicalVisionJob } from "../src/technical-vision-validation.js";
import { resultFixture, input, service, owner } from "./technical-vision-fixtures.js";
import Fastify from "fastify";
import { technicalVisionResultSchema, technicalVisionJobSchema } from "../src/technical-vision-schema.js";

test("strict tool schema and runtime admission reject URLs, traversal, extra fields, invalid pages/crops", () => {
  assert.equal(technicalVisionInputSchema.additionalProperties, false);
  assert.deepEqual(validateTechnicalVisionInput(input), input);
  for (const source of [{ url: "http://127.0.0.1/private" }, { workspacePath: "/etc/passwd" }, { workspacePath: "a/../auth.json" }, { workspacePath: "a\\secret.png" }, { workspacePath: "a/%2e%2e/x" }, { workspacePath: "https://example.com/x" }, { fileId: "source1", workspacePath: "x" }, { workspacePath: "./x" }, { workspacePath: "a//x" }, { workspacePath: "x\0.png" }, { fileId: "" }]) assert.throws(() => validateTechnicalVisionInput({ ...input, source }), { code: "invalid_request" });
  for (const patch of [{ owner }, { token: "not allowed" }, { imageBase64: "a" }, { pages: [0] }, { pages: [1, 1] }, { pages: [1, 2, 3, 4, 5] }, { pages: [2] }, { crops: [{ ...input.crops[0], x: -1 }] }, { crops: [input.crops[0], input.crops[0]] }, { crops: [{ ...input.crops[0], width: 1.5 }] }, { question: "x".repeat(4001) }]) assert.throws(() => validateTechnicalVisionInput({ ...input, ...patch }), { code: "invalid_request" });
});
test("generation0 pins the approved tandem names; mock is not a loaded revision and live requires actual pins", () => {
  assert.deepEqual(validateTechnicalVisionIdentity(service), service);
  assert.throws(() => validateTechnicalVisionIdentity({ ...service, generation: 1 }));
  assert.throws(() => validateTechnicalVisionIdentity({ ...service, mode: "live" }));
  assert.throws(() => validateTechnicalVisionIdentity({ ...service, interpreter: { ...service.interpreter, precision: "FP8" } }));
  assert.throws(() => validateTechnicalVisionIdentity({ ...service, parser: { ...service.parser, model: "other" } }));
});
test("literal labels/values/units/tables/formulas preserve exact text with evidence and separate derivation", () => {
  const r = validateTechnicalVisionResult(resultFixture, resultFixture.source, service);
  assert.equal(r.extraction.text.find(x => x.id === "r1-unit")!.exactText, "kΩ");
  assert.equal(r.extraction.formulas[0].exactText, "V = I × R");
  assert.equal(r.extraction.tables[0].cells[1].exactText, "3.3");
  assert.equal(r.observations.relationships[0].kind, "crossing");
  assert.equal(r.electricalNetReconstruction, "not_qualified");
  assert.equal(r.uncertainties[0].affectedIds[0], "crossing1");
});
test("result evidence rejects bounds, crop/page mismatch, missing claims, bad graph references and raw pixels", () => {
  const mutations: ((r: any) => void)[] = [
    r => r.evidence[0].box.x = 120,
    r => r.evidence[0].box.width = 0,
    r => r.evidence[0].box.x = NaN,
    r => r.evidence[0].page = 2,
    r => r.evidence[0].cropId = "absent",
    r => r.evidence[0].box.x = 9,
    r => r.evidence[1].id = "region1",
    r => r.extraction.text[0].evidenceIds = [],
    r => r.extraction.text[0].evidenceIds = ["missing"],
    r => r.observations.components[0].unitIds = ["r1-value"],
    r => r.observations.relationships[0].from = "missing",
    r => r.uncertainties[0].affectedIds = ["absent"],
    r => r.derivedConclusions[0].basisIds = [],
    r => r.derivedConclusions[0].basisIds = ["conclusion1"],
    r => r.derivedConclusions[0].uncertaintyIds = ["region1"],
    r => r.extraction.tables[0].cells[1].column = 0,
    r => r.source.sha256 = "b".repeat(64),
    r => r.source.pages[0].width = 121,
    r => r.service.parser.revision = "different",
    r => r.electricalNetReconstruction = "qualified",
    r => r.imageBase64 = "pixels",
    r => r.description = "data:image/png;base64,abc",
  ];
  for (const mutate of mutations) { const r = structuredClone(resultFixture); mutate(r); assert.throws(() => validateTechnicalVisionResult(r, resultFixture.source, service), { code: "invalid_evidence" }); }
});
test("job completion requires settled execution; interrupted ownership remains unsettled; diagnostics are redacted", () => {
  const job = { schemaVersion: 1, jobId: "job1", requestId: "request1", owner, service, source: resultFixture.source, state: "completed", settled: true, cancelRequested: false, result: resultFixture };
  assert.equal(validateTechnicalVisionJob(job, owner, service).state, "completed");
  for (const patch of [{ settled: false }, { cancelRequested: true }, { state: "running" }, { owner: { ...owner, runId: "other" } }, { token: "x" }]) assert.throws(() => validateTechnicalVisionJob({ ...job, ...patch }, owner, service));
  const interrupted = { ...job, state: "interrupted", result: undefined, settled: false, error: { code: "interrupted", message: "/private/auth secret fixture" } };
  delete interrupted.result;
  const safe = validateTechnicalVisionJob(interrupted, owner, service);
  assert.equal(safe.settled, false); assert.ok(!safe.error!.message.includes("secret"));
  assert.ok(new TechnicalVisionError("unavailable").message.length < 100);
});
test("exported wire schemas admit the fixture and reject missing evidence/settlement and extra payloads", async t => {
  const app = Fastify({ ajv: { customOptions: { removeAdditional: false, strict: false } } }); t.after(() => app.close());
  app.post("/result", { schema: { body: technicalVisionResultSchema } }, async () => ({ ok: true }));
  app.post("/job", { schema: { body: technicalVisionJobSchema } }, async () => ({ ok: true }));
  assert.equal((await app.inject({ method: "POST", url: "/result", payload: resultFixture })).statusCode, 200);
  const withoutEvidence = structuredClone(resultFixture); withoutEvidence.extraction.text[0].evidenceIds = [];
  assert.equal((await app.inject({ method: "POST", url: "/result", payload: withoutEvidence })).statusCode, 400);
  assert.equal((await app.inject({ method: "POST", url: "/result", payload: { ...resultFixture, imageBase64: "bad" } })).statusCode, 400);
  const job = { schemaVersion: 1, jobId: "job1", requestId: "request1", owner, service, source: resultFixture.source, state: "completed", settled: true, cancelRequested: false, result: resultFixture };
  assert.equal((await app.inject({ method: "POST", url: "/job", payload: job })).statusCode, 200);
  assert.equal((await app.inject({ method: "POST", url: "/job", payload: { ...job, settled: false } })).statusCode, 400);
});
