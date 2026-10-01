import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { createServer, type IncomingMessage, type ServerResponse } from "node:http";
import type { TestContext } from "node:test";
import sharp from "sharp";
import type { TechnicalVisionIdentity, TechnicalVisionJob, TechnicalVisionManifest, TechnicalVisionPrepared } from "../src/technical-vision-contracts.js";
import { TechnicalVisionClient } from "../src/technical-vision-client.js";
import { technicalVisionEqual, validateTechnicalVisionManifest } from "../src/technical-vision-validation.js";
import { technicalVisionSha256 } from "../src/technical-vision-sources.js";

export const resultFixture = JSON.parse(await readFile(new URL("./fixtures/technical-vision/result-generation0.json", import.meta.url), "utf8"));
export const service = resultFixture.service as TechnicalVisionIdentity;
export const owner = { sessionId: "session1", workspaceId: "workspace1", runId: "run1" };
export const input = { requestId: "request1", source: { fileId: "source1" }, crops: resultFixture.source.crops };
export const signal = () => AbortSignal.timeout(3000);
export async function prepared(): Promise<TechnicalVisionPrepared> {
  const png = await sharp({ create: { width: 120, height: 80, channels: 3, background: "#fff" } }).png().toBuffer();
  return { manifest: { ...structuredClone(resultFixture.source), sha256: technicalVisionSha256(png) }, images: [{ page: 1, png, sha256: technicalVisionSha256(png) }] };
}
export function resultFor(source: TechnicalVisionManifest) { return { ...structuredClone(resultFixture), source: structuredClone(source) }; }
export async function httpFixture(t: TestContext, handler: (req: IncomingMessage, res: ServerResponse) => void | Promise<void>, requestMs = 500) {
  const server = createServer((req, res) => { Promise.resolve(handler(req, res)).catch(() => { res.writeHead(500); res.end(); }); });
  await new Promise<void>(resolve => server.listen(0, "127.0.0.1", resolve));
  t.after(() => new Promise<void>(resolve => { server.closeAllConnections(); server.close(() => resolve()); }));
  const fixtureOrigin = `http://127.0.0.1:${(server.address() as { port: number }).port}`;
  const client = new TechnicalVisionClient({ key: () => "fixture-host-only-key", fixtureOrigin, expectedService: service, requestMs });
  return { client, fixtureOrigin };
}
function json(res: ServerResponse, status: number, value: unknown) { res.writeHead(status, { "content-type": "application/json" }); res.end(JSON.stringify(value)); }
async function body(req: IncomingMessage) { const chunks: Buffer[] = []; for await (const c of req) chunks.push(c); return Buffer.concat(chunks); }
/** In-memory generation0 contract fixture. No GPU, parsing model or durable-store claim. */
export async function generation0(t: TestContext, options: { requestMs?: number; capacity?: number } = {}) {
  const jobs = new Map<string, TechnicalVisionJob>(), requests = new Map<string, { fingerprint: string; jobId: string }>();
  let submitCalls = 0, admissions = 0, cancellationCalls = 0;
  const controls = { ready: true, admitting: true, loseSubmitResponse: false };
  const http = await httpFixture(t, async (req, res) => {
    assert.equal(req.headers.authorization, "Bearer fixture-host-only-key");
    if (req.url === "/v1/technical-vision/capabilities" && req.method === "GET") return json(res, 200, { schemaVersion: 1, service, ready: controls.ready, admitting: controls.admitting });
    if (req.url === "/v1/technical-vision/jobs" && req.method === "POST") {
      submitCalls++;
      const bytes = await body(req), type = String(req.headers["content-type"]), boundary = type.split("boundary=")[1];
      assert.match(type, /^multipart\/form-data; boundary=technical-vision-[a-f0-9]+$/);
      const delimiter = Buffer.from(`\r\n--${boundary}`), headEnd = bytes.indexOf("\r\n\r\n"), metadataEnd = bytes.indexOf(delimiter, headEnd);
      const metadata = JSON.parse(bytes.subarray(headEnd + 4, metadataEnd).toString());
      assert.ok(!JSON.stringify(metadata).includes("fixture-host-only-key"));
      assert.equal(req.headers["idempotency-key"], metadata.requestId);
      assert.equal(metadata.schemaVersion, 1); validateTechnicalVisionManifest(metadata.source);
      assert.deepEqual(metadata.service, service);
      for (const p of metadata.pageImages) {
        const part = bytes.indexOf(`name="${p.part}"`), start = bytes.indexOf("\r\n\r\n", part) + 4, end = bytes.indexOf(delimiter, start), png = bytes.subarray(start, end);
        assert.equal(technicalVisionSha256(png), p.sha256);
        const m = await sharp(png).metadata(), page = metadata.source.pages.find((x: any) => x.page === p.page);
        assert.equal(m.format, "png"); assert.equal(m.width, page.width); assert.equal(m.height, page.height);
      }
      const key = JSON.stringify([metadata.owner, metadata.requestId]), fingerprint = technicalVisionSha256(JSON.stringify(metadata)), existing = requests.get(key);
      if (existing) {
        if (existing.fingerprint !== fingerprint) return json(res, 409, { privateDiagnostic: "must not escape" });
        return json(res, 200, jobs.get(existing.jobId));
      }
      if (!controls.ready || !controls.admitting) return json(res, 503, {});
      if ([...jobs.values()].filter(j => !j.settled).length >= (options.capacity ?? 2)) return json(res, 429, {});
      const jobId = `job-${++admissions}`;
      const job: TechnicalVisionJob = { schemaVersion: 1, jobId, requestId: metadata.requestId, owner: metadata.owner, service, source: metadata.source, state: "queued", settled: false, cancelRequested: false, queuePosition: admissions };
      jobs.set(jobId, job); requests.set(key, { fingerprint, jobId });
      if (controls.loseSubmitResponse) return; // Admission survives the observer's timeout.
      return json(res, 202, job);
    }
    const lookup = req.url?.match(/^\/v1\/technical-vision\/requests\/([a-zA-Z0-9_-]+)\/status$/);
    if (lookup && req.method === "POST") {
      const envelope = JSON.parse((await body(req)).toString()), record = requests.get(JSON.stringify([envelope.owner, lookup[1]]));
      return record ? json(res, 200, jobs.get(record.jobId)) : json(res, 404, {});
    }
    const match = req.url?.match(/^\/v1\/technical-vision\/jobs\/([a-zA-Z0-9_-]+)\/(status|cancel)$/);
    if (match && req.method === "POST") {
      const envelope = JSON.parse((await body(req)).toString()), job = jobs.get(match[1]);
      if (!job || !technicalVisionEqual(envelope.owner, job.owner)) return json(res, 404, {});
      if (match[2] === "cancel") {
        cancellationCalls++;
        if (!job.settled) {
          job.cancelRequested = true;
          if (job.state === "queued") { job.state = "cancelled"; job.settled = true; delete job.queuePosition; }
          else job.state = "cancelling";
        }
      }
      return json(res, 200, job);
    }
    return json(res, 404, {});
  }, options.requestMs ?? 500);
  return {
    ...http, jobs, controls,
    counters: () => ({ submitCalls, admissions, cancellationCalls }),
    start(jobId: string) { const job = jobs.get(jobId)!; job.state = "running"; delete job.queuePosition; },
    complete(jobId: string) { const job = jobs.get(jobId)!; if (job.cancelRequested) return; job.state = "completed"; job.settled = true; delete job.queuePosition; job.result = resultFor(job.source); },
    settleCancelled(jobId: string) { const job = jobs.get(jobId)!; assert.equal(job.state, "cancelling"); job.state = "cancelled"; job.settled = true; delete job.result; },
  };
}
