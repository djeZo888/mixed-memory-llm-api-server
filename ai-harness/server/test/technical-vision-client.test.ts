import assert from "node:assert/strict";
import test from "node:test";
import { TechnicalVisionClient } from "../src/technical-vision-client.js";
import { generation0, httpFixture, service, owner, input, prepared, signal, resultFor } from "./technical-vision-fixtures.js";

test("host-only service origin/auth, no untrusted endpoints or native image payloads", async t => {
  for (const fixtureOrigin of ["http://example.com:80", "http://localhost:10000", "http://127.0.0.1:1234/other", "http://user:password@127.0.0.1:1234", "http://127.0.0.1:1234/?token=x", "https://127.0.0.1:1234"]) assert.throws(() => new TechnicalVisionClient({ key: () => "test", fixtureOrigin, expectedService: service }));
  assert.throws(() => new TechnicalVisionClient({ key: () => "test", serviceOrigin: "http://10.156.100.61:30008", expectedService: service }));
  const f = await generation0(t);
  assert.deepEqual(await f.client.readiness(signal()), { ready: true, admitting: true });
  const p = await prepared(), job = await f.client.submit(owner, input, p, signal());
  assert.equal(job.state, "queued"); assert.equal(job.settled, false); assert.deepEqual(job.source, p.manifest);
  assert.equal(f.counters().admissions, 1);
});
test("duplicate keys reuse one admission; changed work conflicts; queue capacity is enforced", async t => {
  const f = await generation0(t), p = await prepared();
  const [a, b] = await Promise.all([f.client.submit(owner, input, p, signal()), f.client.submit(owner, input, p, signal())]);
  assert.equal(a.jobId, b.jobId); assert.equal(f.counters().admissions, 1);
  await assert.rejects(f.client.submit(owner, { ...input, question: "changed work" }, p, signal()), { code: "idempotency_conflict" });
  await f.client.submit(owner, { ...input, requestId: "request2" }, p, signal());
  await assert.rejects(f.client.submit(owner, { ...input, requestId: "request3" }, p, signal()), { code: "queue_full" });
  assert.equal(f.counters().admissions, 2);
});
test("admission with lost response times out without retries, then same request reconciles the surviving job", async t => {
  const f = await generation0(t, { requestMs: 40 }), p = await prepared(); f.controls.loseSubmitResponse = true;
  await assert.rejects(f.client.submit(owner, input, p, signal()), { code: "timeout" });
  assert.deepEqual(f.counters(), { admissions: 1, submitCalls: 1, cancellationCalls: 0 });
  const recovered = await f.client.lookup(owner, input.requestId, signal()); assert.equal(recovered.jobId, "job-1");
  assert.equal(f.counters().submitCalls, 1);
  await assert.rejects(f.client.lookup({ ...owner, runId: "other" }, input.requestId, signal()), { code: "not_found" });
  f.controls.loseSubmitResponse = false;
  const reconciled = await f.client.submit(owner, input, p, signal()); assert.equal(reconciled.jobId, "job-1"); assert.equal(f.counters().admissions, 1);
});
test("queued and running cancellation are distinct; Stop drains before settlement and late results are suppressed", async t => {
  const f = await generation0(t), p = await prepared();
  const queued = await f.client.submit(owner, input, p, signal());
  const stopped = await f.client.cancel(owner, queued.jobId, signal()); assert.equal(stopped.state, "cancelled"); assert.equal(stopped.settled, true);
  assert.equal((await f.client.cancel(owner, queued.jobId, signal())).state, "cancelled");
  const active = await f.client.submit(owner, { ...input, requestId: "request2" }, p, signal()); f.start(active.jobId);
  const draining = await f.client.cancel(owner, active.jobId, signal()); assert.equal(draining.state, "cancelling"); assert.equal(draining.settled, false); assert.equal(draining.cancelRequested, true);
  f.complete(active.jobId); assert.equal((await f.client.status(owner, active.jobId, signal())).result, undefined);
  f.settleCancelled(active.jobId); assert.equal((await f.client.status(owner, active.jobId, signal())).settled, true);
});
test("observer abort never implicitly cancels and job lookup is scoped to owner task", async t => {
  const f = await generation0(t), p = await prepared(), job = await f.client.submit(owner, input, p, signal());
  const stop = new AbortController(); stop.abort();
  await assert.rejects(f.client.status(owner, job.jobId, stop.signal), { code: "observation_cancelled" });
  assert.equal(f.counters().cancellationCalls, 0); assert.equal(f.jobs.get(job.jobId)!.state, "queued");
  await assert.rejects(f.client.status({ ...owner, runId: "different" }, job.jobId, signal()), { code: "not_found" });
  await assert.rejects(f.client.cancel({ ...owner, sessionId: "different" }, job.jobId, signal()), { code: "not_found" });
  await assert.rejects(f.client.status(owner, "../secret", signal()), { code: "invalid_request" });
});
test("completed generation0 results are validated, exact and explicitly unqualified", async t => {
  const f = await generation0(t), p = await prepared(), job = await f.client.submit(owner, input, p, signal()); f.complete(job.jobId);
  const done = await f.client.status(owner, job.jobId, signal());
  assert.equal(done.state, "completed"); assert.equal(done.service.mode, "mock"); assert.deepEqual(done.result, resultFor(p.manifest));
  f.jobs.get(job.jobId)!.result!.evidence[0].box.x = 999;
  await assert.rejects(f.client.status(owner, job.jobId, signal()), { code: "invalid_evidence" });
});
test("unavailability, malformed envelopes, redirects, bounded bodies and identity drift fail closed without diagnostics", async t => {
  for (const mode of ["503", "redirect", "invalid-json", "oversize", "identity", "html"]) {
    let calls = 0;
    const f = await httpFixture(t, (_req, res) => {
      calls++;
      if (mode === "503") { res.writeHead(503); res.end("private diagnostic secret"); }
      else if (mode === "redirect") { res.writeHead(302, { location: "http://127.0.0.1/private" }); res.end(); }
      else if (mode === "html") { res.writeHead(200, { "content-type": "text/html" }); res.end("secret"); }
      else { res.writeHead(200, { "content-type": "application/json" }); res.end(mode === "invalid-json" ? "private non-json" : mode === "oversize" ? "x".repeat(1024 * 1024 + 1) : JSON.stringify({ schemaVersion: 1, service: { ...service, generation: 3 }, ready: true, admitting: true })); }
    });
    await assert.rejects(f.client.readiness(signal()), (e: any) => ["unavailable", "invalid_response"].includes(e.code) && !e.message.includes("secret")); assert.equal(calls, 1);
  }
});
test("auth callbacks are bounded and never exposed; bad snapshot integrity rejects before POST", async t => {
  let requests = 0;
  const f = await httpFixture(t, (_req, res) => { requests++; res.end(); }, 30);
  const blocked = new TechnicalVisionClient({ key: () => new Promise(() => {}), fixtureOrigin: f.fixtureOrigin, expectedService: service, requestMs: 30 });
  await assert.rejects(blocked.readiness(signal()), { code: "timeout" }); assert.equal(requests, 0);
  const broken = new TechnicalVisionClient({ key: () => { throw Error("private-token-value"); }, fixtureOrigin: f.fixtureOrigin, expectedService: service });
  await assert.rejects(broken.readiness(signal()), (e: any) => e.code === "unavailable" && !e.message.includes("private-token-value"));
  const p = await prepared(); p.images[0].sha256 = "0".repeat(64);
  await assert.rejects(f.client.submit(owner, input, p, signal()), { code: "invalid_source" }); assert.equal(requests, 0);
});
test("HTTP job responses cannot use array-valued failed state to bypass settlement validation", async t => {
  const p = await prepared();
  const f = await httpFixture(t, (_req, res) => {
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify({ schemaVersion: 1, jobId: "job1", requestId: input.requestId, owner, service, source: p.manifest, state: ["failed"], settled: false, cancelRequested: false }));
  });
  await assert.rejects(f.client.status(owner, "job1", signal()), { code: "invalid_response" });
});
