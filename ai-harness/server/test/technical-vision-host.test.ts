import assert from "node:assert/strict";
import test from "node:test";
import { spawn } from "node:child_process";
import { mkdtemp, chmod, rm, readFile, readdir, stat } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createHash } from "node:crypto";
import sharp from "sharp";
import { createTechnicalVisionHost, constructTechnicalVisionHost, PrivateTechnicalVisionHostJournal } from "../src/technical-vision-host.js";
import { TechnicalVisionClient, type TechnicalVisionBackend } from "../src/technical-vision-client.js";
import { TechnicalVisionError, type TechnicalVisionIdentity, type TechnicalVisionJob, type TechnicalVisionPrepared } from "../src/technical-vision-contracts.js";

const owner = { sessionId: "session1", workspaceId: "workspace1", runId: "run1" };
const service: TechnicalVisionIdentity = { serviceId: "fixture-vision", generation: 0, mode: "mock", interpreter: { model: "Qwen/Qwen3.5-9B", revision: "generation0-not-loaded", precision: "BF16" }, parser: { model: "PaddlePaddle/PaddleOCR-VL-1.6", revision: "generation0-not-loaded" } };
const input = { requestId: "request1", source: { fileId: "source1" }, crops: [{ id: "label", page: 1, x: 1, y: 1, width: 2, height: 1 }] };
const sha = (b: Buffer) => createHash("sha256").update(b).digest("hex");
const signal = () => AbortSignal.timeout(3000);
async function prepared(): Promise<TechnicalVisionPrepared> {
  const png = await sharp({ create: { width: 4, height: 3, channels: 3, background: "white" } }).png().toBuffer();
  return { manifest: { reference: input.source, sha256: sha(png), mediaType: "image/png", coordinateSpace: "oriented_page_pixels", pages: [{ page: 1, width: 4, height: 3, originalWidth: 4, originalHeight: 3, orientation: 1 }], crops: input.crops }, images: [{ page: 1, png, sha256: sha(png) }] };
}
async function privateDir() { const dir = await mkdtemp(join(tmpdir(), "vision-")); await chmod(dir, 0o700); return dir; }
function fakeBackend(p: TechnicalVisionPrepared) {
  const job: TechnicalVisionJob = { schemaVersion: 1, jobId: "job1", requestId: "request1", owner, service, source: p.manifest, state: "running", settled: false, cancelRequested: false };
  let submits = 0, lookups = 0, cancels = 0; const seenOwners: unknown[] = [];
  const backend: TechnicalVisionBackend = {
    async readiness() { return { ready: true, admitting: true }; },
    async submit(who) { submits++; seenOwners.push(who); return structuredClone(job); },
    async lookup(who) { lookups++; seenOwners.push(who); return structuredClone(job); },
    async status(who) { seenOwners.push(who); return structuredClone(job); },
    async cancel(who) { cancels++; seenOwners.push(who); job.state = "cancelling"; job.cancelRequested = true; return structuredClone(job); },
  };
  return { backend, job, seenOwners, counters: () => ({ submits, lookups, cancels }) };
}

test("default gate closed; model cannot choose ownership or endpoints", async () => {
  const dir = await privateDir(), journal = await PrivateTechnicalVisionHostJournal.open(dir), p = await prepared(), f = fakeBackend(p);
  try {
    const host = createTechnicalVisionHost({ backend: f.backend, service, journal, owner: () => owner, authorize: () => true, prepare: async () => p });
    assert.equal(host.availability, "disabled"); await assert.rejects(host.invoke(input, signal()), (e: unknown) => e instanceof TechnicalVisionError && e.code === "unavailable");
    const active = createTechnicalVisionHost({ backend: f.backend, service, journal, enabled: true, owner: () => owner, authorize: () => true, prepare: async () => p });
    await assert.rejects(active.invoke({ ...input, owner: { runId: "attacker" } }, signal())); assert.equal(f.counters().submits, 0);
  } finally { await journal.close(); await rm(dir, { recursive: true }); }
});

test("durable retained run, no reprepare or resubmit; exactly one logical terminal event", async () => {
  const dir = await privateDir(); let journal = await PrivateTechnicalVisionHostJournal.open(dir);
  const p = await prepared(), f = fakeBackend(p); let currentOwner = owner, reads = 0; const delivered = new Map<string, string>(); let deliveries = 0;
  const options = () => ({ backend: f.backend, service, journal, enabled: true, owner: () => currentOwner, authorize: () => true, prepare: async () => { reads++; return p; }, deliverOnce: async (key: string, response: unknown) => { if (!delivered.has(key)) { deliveries++; delivered.set(key, JSON.stringify(response)); } } });
  try {
    let host = createTechnicalVisionHost(options()); const result = await host.invoke(input, signal());
    assert.equal(reads, 1); assert.equal(f.counters().submits, 1); assert.equal(f.counters().cancels, 0);
    await journal.close(); journal = await PrivateTechnicalVisionHostJournal.open(dir); currentOwner = { ...owner, runId: "laterRun" }; host = createTechnicalVisionHost(options());
    await host.status(result.handle, signal()); await host.lookup(result.handle, signal()); assert.deepEqual(f.seenOwners.at(-1), owner);
    currentOwner = owner; await host.invoke(input, signal()); assert.equal(reads, 1); assert.equal(f.counters().submits, 1);
    await assert.rejects(host.invoke({ ...input, question: "changed" }, signal()), (e: unknown) => e instanceof TechnicalVisionError && e.code === "idempotency_conflict");
    f.job.state = "completed"; f.job.settled = true; f.job.result = { schemaVersion: 1, service, source: p.manifest, description: "Fake result only", extraction: { text: [], tables: [], formulas: [], layout: [] }, observations: { components: [], relationships: [] }, evidence: [], uncertainties: [], derivedConclusions: [], electricalNetReconstruction: "not_qualified" };
    await host.status(result.handle, signal()); assert.equal(await host.deliverTerminal(result.handle), true); assert.equal(await host.deliverTerminal(result.handle), false);
    await journal.close(); journal = await PrivateTechnicalVisionHostJournal.open(dir); host = createTechnicalVisionHost(options()); assert.equal(await host.deliverTerminal(result.handle), false); assert.equal(deliveries, 1);
    for (const file of await readdir(dir)) assert.equal((await stat(join(dir, file))).mode & 0o777, 0o600);
    assert.ok(![...delivered.values()][0].includes('"owner"')); assert.ok(![...delivered.values()][0].includes('"png"'));
  } finally { await journal.close(); await rm(dir, { recursive: true }); }
});

test("lost admission response has retained lookup handle and never rereads a deleted source", async () => {
  const dir = await privateDir(), journal = await PrivateTechnicalVisionHostJournal.open(dir), p = await prepared(), f = fakeBackend(p); let reads = 0;
  f.backend.submit = async () => { throw new TechnicalVisionError("timeout"); };
  const host = createTechnicalVisionHost({ backend: f.backend, service, journal, enabled: true, owner: () => owner, authorize: () => true, prepare: async () => { reads++; if (reads > 1) throw Error("source deleted"); return p; } });
  try {
    const first = await host.invoke(input, signal()); assert.ok(first.response.isError); assert.equal(JSON.parse(first.response.content[0].text).settlement, "unknown");
    await host.invoke(input, signal()); assert.equal(reads, 1); assert.equal(f.counters().lookups, 1); assert.equal(f.counters().cancels, 0);
    const denied = createTechnicalVisionHost({ backend: f.backend, service, journal, enabled: true, owner: () => owner, authorize: () => false, prepare: async () => p });
    await assert.rejects(denied.lookup(first.handle, signal()), (e: unknown) => e instanceof TechnicalVisionError && e.code === "not_found");
    await host.cancel(first.handle, signal()); assert.equal(f.counters().cancels, 1); assert.equal(f.job.settled, false);
  } finally { await journal.close(); await rm(dir, { recursive: true }); }
});

test("real Python service/backend + fake model HTTP + existing TS client + host end to end", async t => {
  const dir = await privateDir(), ledger = join(dir, "ledger"), hostdir = join(dir, "host");
  const { mkdir } = await import("node:fs/promises"); await mkdir(ledger, { mode: 0o700 }); await mkdir(hostdir, { mode: 0o700 });
  const child = spawn("python3", ["../../scripts/vision/tests/test_service.py", "--fixture-server", ledger], { stdio: ["pipe", "pipe", "pipe"] }); let stderr = ""; child.stderr.on("data", b => { stderr += b; });
  child.stdin.write("fixture-private-bearer-0001\n");
  const exit = new Promise<number | null>(resolve => child.once("exit", resolve));
  t.after(async () => { if (child.exitCode === null) { child.stdin.write("stop\n"); child.stdin.end(); await exit; } await rm(dir, { recursive: true }); });
  const line = await new Promise<string>((resolve, reject) => { let out = ""; child.stdout.on("data", b => { out += b; if (out.includes("\n")) resolve(out.split("\n")[0]); }); child.once("exit", () => reject(Error(stderr))); });
  const ready = JSON.parse(line); assert.deepEqual(ready.service, service);
  const journal = await PrivateTechnicalVisionHostJournal.open(hostdir), p = await prepared(); let reads = 0;
  const host = constructTechnicalVisionHost({ client: { expectedService: service, fixtureOrigin: `http://127.0.0.1:${ready.port}`, key: () => "fixture-private-bearer-0001" }, service, journal, enabled: true, owner: () => owner, authorize: () => true, prepare: async () => { reads++; return p; } });
  try {
    const first = await host.invoke(input, signal()); assert.equal(first.response.isError, undefined);
    let result = first;
    for (let n = 0; n < 20; n++) { result = await host.status(first.handle, signal()); if (JSON.parse(result.response.content[0].text).job.state === "completed") break; await new Promise(r => setTimeout(r, 10)); }
    assert.equal(JSON.parse(result.response.content[0].text).job.state, "completed"); assert.equal(JSON.parse(result.response.content[0].text).job.result.extraction.text[0].exactText, "R1  10 kΩ\n  Vcc\n"); await host.invoke(input, signal()); assert.equal(reads, 1);
    const record = JSON.parse(await readFile(join(ledger, (await readdir(ledger)).find(n => n.endsWith(".json"))!), "utf8"));
    assert.equal(record.metadata.pageImages[0].sha256, sha(p.images[0].png)); assert.deepEqual(Buffer.from(record.images["1"], "base64"), p.images[0].png);
    assert.ok(!result.response.content[0].text.includes("fixture-private-bearer")); assert.ok(!result.response.content[0].text.includes('"images"'));
    console.log(JSON.stringify({ fixture: "real Python service/backend + TS client + host; fake model HTTP only", ledger, tmpdir: tmpdir(), uid: process.getuid?.(), mode: (await stat(dir)).mode & 0o777, servicePort: ready.port, rawPngBytes: p.images[0].png.length }));
  } finally { await journal.close(); child.stdin.write("stop\n"); child.stdin.end(); assert.equal(await exit, 0, stderr); }
});


test("H043 one-page/two-megapixel host cap rejects before any backend POST and retains original claim", async () => {
  const dir = await privateDir(), journal = await PrivateTechnicalVisionHostJournal.open(dir), p = await prepared(), f = fakeBackend(p);
  const oversized = { ...p, manifest: { ...p.manifest, pages: [{ ...p.manifest.pages[0], width: 2048, height: 1025, originalWidth: 2048, originalHeight: 1025 }] } };
  const host = createTechnicalVisionHost({ backend: f.backend, service, journal, enabled: true, owner: () => owner, authorize: () => true, prepare: async () => oversized });
  try {
    const result = await host.invoke(input, signal());
    assert.equal(JSON.parse(result.response.content[0].text).error.code, "source_too_large");
    assert.equal(f.counters().submits, 0); assert.equal((await journal.read(result.handle))?.admission, "claimed");
    await host.invoke(input, signal()); assert.equal(f.counters().submits, 0); assert.equal(f.counters().lookups, 1);
  } finally { await journal.close(); await rm(dir, { recursive: true }); }
});


test("explicit Stop during preparation durably records intent and prevents the initial POST", async () => {
  const dir = await privateDir(), journal = await PrivateTechnicalVisionHostJournal.open(dir), p = await prepared(), f = fakeBackend(p);
  let release!: () => void, started!: () => void; const begun = new Promise<void>(r => { started = r; }), wait = new Promise<void>(r => { release = r; });
  const host = createTechnicalVisionHost({ backend: f.backend, service, journal, enabled: true, owner: () => owner, authorize: () => true, prepare: async () => { started(); await wait; return p; } });
  try {
    const invocation = host.invoke(input, signal()); await begun;
    const files = (await readdir(dir)).filter(f => f.startsWith("vision-")); const handle = files[0].replace(/\.json$/, "");
    await host.cancel(handle, signal()); release(); const result = await invocation;
    assert.equal(f.counters().submits, 0); assert.equal((await journal.read(handle))?.cancelIntent, true);
    assert.equal(JSON.parse(result.response.content[0].text).error.code, "observation_cancelled");
  } finally { release(); await journal.close(); await rm(dir, { recursive: true }); }
});
