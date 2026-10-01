import assert from "node:assert/strict";
import test from "node:test";
import { createTechnicalImageAnalyzeTool } from "../src/technical-vision-tool.js";
import { generation0, service, owner, input, prepared, signal } from "./technical-vision-fixtures.js";

const decode = (response: { content: { text: string }[] }) => JSON.parse(response.content[0].text);
test("unregistered factory returns text-only pending/completed jobs and host Stop hooks with no credential/pixel dump", async t => {
  const f = await generation0(t), p = await prepared(); let preparations = 0;
  const tool = createTechnicalImageAnalyzeTool({ backend: f.client, service, owner: () => owner, prepare: async () => { preparations++; return p; } });
  assert.equal(tool.definition.name, "technical_image_analyze");
  const queued = decode(await tool.invoke(input, signal())); assert.equal(queued.observation, "pending"); assert.equal(queued.job.state, "queued"); assert.equal(queued.job.owner, undefined);
  f.complete(queued.job.jobId);
  const completed = await tool.status(queued.job.jobId, signal()), publicResult = decode(completed);
  assert.equal(publicResult.observation, "settled"); assert.equal(publicResult.job.result.electricalNetReconstruction, "not_qualified"); assert.equal(publicResult.qualification, "source_preparation_only");
  assert.deepEqual(completed.content.map(c => c.type), ["text"]);
  for (const forbidden of ["fixture-host-only-key", '"png"', "imageBase64", "b64_json", '"owner"']) assert.ok(!completed.content[0].text.includes(forbidden));
  assert.equal(preparations, 1); assert.equal(f.counters().admissions, 1);
});
test("invalid input and unavailable readiness cannot read files or submit work", async t => {
  const f = await generation0(t); let preparations = 0;
  const tool = createTechnicalImageAnalyzeTool({ backend: f.client, service, owner: () => owner, prepare: async () => { preparations++; return prepared(); } });
  const invalid = await tool.invoke({ ...input, source: { url: "http://10.156.100.60/private" } }, signal()); assert.equal(invalid.isError, true); assert.equal(decode(invalid).error.code, "invalid_request");
  f.controls.admitting = false;
  const unavailable = await tool.invoke(input, signal()); assert.equal(unavailable.isError, true); assert.equal(decode(unavailable).error.code, "unavailable");
  assert.equal(preparations, 0); assert.equal(f.counters().submitCalls, 0);
});
test("factory timeouts preserve unknown settlement and duplicate key; explicit Stop cancels the owned job", async t => {
  const f = await generation0(t, { requestMs: 40 }), p = await prepared();
  const tool = createTechnicalImageAnalyzeTool({ backend: f.client, service, owner: () => owner, prepare: async () => p });
  f.controls.loseSubmitResponse = true;
  const timedOut = decode(await tool.invoke(input, signal())); assert.equal(timedOut.error.code, "timeout"); assert.equal(timedOut.settlement, "unknown"); assert.equal(f.counters().admissions, 1);
  f.controls.loseSubmitResponse = false;
  const existing = decode(await tool.invoke(input, signal())); assert.equal(existing.job.jobId, "job-1"); assert.equal(f.counters().admissions, 1);
  const cancelled = await tool.cancel(existing.job.jobId, signal()); assert.equal(cancelled.isError, true); assert.equal(decode(cancelled).job.state, "cancelled"); assert.equal(decode(cancelled).observation, "settled");
});
test("adapter revalidates backend envelopes and suppresses raw exceptions", async t => {
  const f = await generation0(t), p = await prepared();
  const tool = createTechnicalImageAnalyzeTool({ service, owner: () => owner, prepare: async () => p, backend: { ...f.client,
    readiness: () => f.client.readiness(signal()),
    submit: async () => { throw Error("/private/host/token sensitive"); },
    status: async () => ({ imageBase64: "pixels", token: "secret" } as any),
    cancel: (...args) => f.client.cancel(...args),
    lookup: (...args) => f.client.lookup(...args),
  } });
  const response = await tool.invoke(input, signal()); assert.equal(response.isError, true); assert.ok(!response.content[0].text.includes("sensitive"));
  const invalid = await tool.status("job1", signal()); assert.equal(invalid.isError, true); assert.equal(decode(invalid).error.code, "invalid_response"); assert.ok(!invalid.content[0].text.includes('"token"'));
});
test("lost-response lookup bypasses source reads and admission readiness without repeating inference", async t => {
  const f = await generation0(t), p = await prepared(); await f.client.submit(owner, input, p, signal());
  f.controls.admitting = false;
  const tool = createTechnicalImageAnalyzeTool({ backend: f.client, service, owner: () => owner, prepare: async () => { throw Error("source has been removed"); } });
  const recovered = decode(await tool.lookup(input.requestId, signal())); assert.equal(recovered.job.jobId, "job-1"); assert.equal(f.counters().submitCalls, 1);
});
test("tool response remains bounded even for a structurally valid oversized host adapter result", async t => {
  const f = await generation0(t), p = await prepared(), job = await f.client.submit(owner, input, p, signal()); f.complete(job.jobId);
  const oversized = structuredClone(f.jobs.get(job.jobId)!);
  oversized.result!.extraction.text.push(...Array.from({ length: 140 }, (_, i) => ({ id: `extra-${i}`, kind: "text" as const, exactText: "x".repeat(8192), evidenceIds: ["region1"] })));
  const tool = createTechnicalImageAnalyzeTool({ backend: { readiness: (...a) => f.client.readiness(...a), submit: (...a) => f.client.submit(...a), cancel: (...a) => f.client.cancel(...a), lookup: (...a) => f.client.lookup(...a), status: async () => oversized }, service, owner: () => owner, prepare: async () => p });
  const response = await tool.status(job.jobId, signal()); assert.equal(response.isError, true); assert.equal(decode(response).error.code, "invalid_response"); assert.ok(response.content[0].text.length < 1000);
});
