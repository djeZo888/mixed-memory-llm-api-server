import assert from "node:assert/strict";
import test from "node:test";
import { spawn, execFileSync } from "node:child_process";
import { mkdtemp, chmod, rm, readFile, readdir, stat, realpath, mkdir } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { createHash } from "node:crypto";
import sharp from "sharp";
import { createTechnicalVisionHost, constructTechnicalVisionHost, PrivateTechnicalVisionHostJournal } from "../src/technical-vision-host.js";
import type { TechnicalVisionBackend } from "../src/technical-vision-client.js";
import { validateTechnicalVisionManifest } from "../src/technical-vision-validation.js";
import { TechnicalVisionError, type TechnicalVisionIdentity, type TechnicalVisionJob, type TechnicalVisionPrepared } from "../src/technical-vision-contracts.js";

const owner = { sessionId: "session1", workspaceId: "workspace1", runId: "run1" };
const service: TechnicalVisionIdentity = { serviceId: "fixture-vision", generation: 0, mode: "mock", interpreter: { model: "Qwen/Qwen3.5-9B", revision: "generation0-not-loaded", precision: "BF16" }, parser: { model: "PaddlePaddle/PaddleOCR-VL-1.6", revision: "generation0-not-loaded" } };
const input = { requestId: "request1", source: { fileId: "source1" }, crops: [{ id: "label", page: 1, x: 1, y: 1, width: 2, height: 1 }] };
const sha = (b: Buffer) => createHash("sha256").update(b).digest("hex");
const signal = () => AbortSignal.timeout(3000);
async function prepared(width = 4, height = 3): Promise<TechnicalVisionPrepared> {
  const png = await sharp({ create: { width, height, channels: 3, background: "white" } }).png().toBuffer();
  return { manifest: { reference: input.source, sha256: sha(png), mediaType: "image/png", coordinateSpace: "oriented_page_pixels", pages: [{ page: 1, width, height, originalWidth: width, originalHeight: height, orientation: 1 }], crops: input.crops }, images: [{ page: 1, png, sha256: sha(png) }] };
}
// The journal and Python ledger both reject aliases (including macOS /var -> /private/var).
// Resolve the trusted test root before creating our own directory; do not relax either guard.
async function privateDir() {
  const root = await realpath(tmpdir()), dir = await mkdtemp(join(root, "vision-"));
  await chmod(dir, 0o700); assert.equal(await realpath(dir), dir);
  const metadata = await stat(dir);
  assert.equal(metadata.uid, process.getuid?.()); assert.equal(metadata.mode & 0o777, 0o700);
  return dir;
}
/** Synthetic admitted jobs obey the real client binding; a claim alone is not a job. */
function fakeBackend(p: TechnicalVisionPrepared) {
  const job: TechnicalVisionJob = { schemaVersion: 1, jobId: "job1", requestId: "request1", owner: structuredClone(owner), service: structuredClone(service), source: structuredClone(p.manifest), state: "running", settled: false, cancelRequested: false };
  let submits = 0, lookups = 0, cancels = 0, readiness = 0, admitted = false;
  const seenOwners: unknown[] = [];
  const controls = { ready: true, admitting: true, loseSubmitResponse: false };
  function bound(who: unknown, key: string, expected: string) {
    seenOwners.push(structuredClone(who)); assert.deepEqual(who, owner); assert.equal(key, expected);
    if (!admitted) throw new TechnicalVisionError("not_found");
    return structuredClone(job);
  }
  const backend: TechnicalVisionBackend = {
    async readiness(signal) { signal.throwIfAborted(); readiness++; return { ready: controls.ready, admitting: controls.admitting }; },
    async submit(who, request, source, signal) {
      signal.throwIfAborted(); submits++; seenOwners.push(structuredClone(who));
      assert.deepEqual(who, owner); assert.deepEqual(request, input); assert.deepEqual(source, p);
      assert.equal(admitted, false, "Host must never resubmit an admitted original request");
      if (!controls.ready || !controls.admitting) throw new TechnicalVisionError("unavailable");
      admitted = true;
      if (controls.loseSubmitResponse) throw new TechnicalVisionError("timeout");
      return structuredClone(job);
    },
    async lookup(who, requestId, signal) { signal.throwIfAborted(); lookups++; return bound(who, requestId, job.requestId); },
    async status(who, jobId, signal) { signal.throwIfAborted(); return bound(who, jobId, job.jobId); },
    async cancel(who, jobId, signal) {
      signal.throwIfAborted(); bound(who, jobId, job.jobId); cancels++;
      job.state = "cancelling"; job.cancelRequested = true; return structuredClone(job);
    },
  };
  return { backend, job, controls, seenOwners, counters: () => ({ submits, lookups, cancels, readiness }) };
}

/** Own the actual spawned child before any fallible identity/readiness/receipt work.
 * No detached child or PID/group guessed from external state is ever signalled.
 * Node's close event is the direct child wait, after its original streams drain.
 */
async function withPythonFixture<T>(ledger: string, body: (ready: { port: number; service: TechnicalVisionIdentity }) => Promise<T>, fault?: "identity" | "readiness" | "receipt") {
  const argv = ["-I", "-B", resolve("../../scripts/vision/tests/test_service.py"), "--fixture-server", ledger];
  const executable = "/usr/bin/python3", cwd = process.cwd(), startedUTC = new Date().toISOString();
  const child = spawn(executable, argv, { stdio: ["pipe", "pipe", "pipe"], cwd, env: { ...process.env, TMPDIR: tmpdir() } });
  let stdout = "", stderr = "", spawnError: Error | undefined, stdinError: Error | undefined;
  let identity: { pid: number; pgid: number; birth: string } | undefined;
  child.stdin.on("error", e => { stdinError = e; });
  const terminal = new Promise<{ code: number | null; signal: NodeJS.Signals | null }>(done => child.once("close", (code, signal) => done({ code, signal })));
  const readyLine = new Promise<string>((done, reject) => {
    child.stdout.on("data", b => { stdout += b; if (stdout.includes("\n")) done(stdout.split("\n")[0]); });
    child.stderr.on("data", b => { stderr += b; });
    child.once("error", e => { spawnError = e; reject(e); });
    child.once("close", () => reject(Error(`Fixture closed before readiness: ${stderr}`)));
  });
  // A metadata failure before awaiting readiness must not leave an unhandled rejection.
  void readyLine.catch(() => {});
  const bounded = async <V>(promise: Promise<V>, ms: number): Promise<V | undefined> => {
    let timer: ReturnType<typeof setTimeout> | undefined;
    try { return await Promise.race([promise, new Promise<undefined>(done => { timer = setTimeout(() => done(undefined), ms); })]); }
    finally { clearTimeout(timer); }
  };
  try {
    // Queue both protocol lines even if identity capture fails before Python reads stdin.
    child.stdin.write("fixture-private-bearer-0001\n");
    if (fault === "identity") throw Error("Injected fixture identity metadata failure");
    assert.ok(child.pid, "Actual owned child PID required");
    const fields = execFileSync("/bin/ps", ["-p", String(child.pid), "-o", "pid=,pgid=,lstart="], { encoding: "utf8", timeout: 2000 }).trim().split(/\s+/);
    assert.equal(Number(fields[0]), child.pid); assert.equal(fields.length, 7);
    identity = { pid: child.pid, pgid: Number(fields[1]), birth: fields.slice(2).join(" ") };
    console.log(JSON.stringify({ fixtureChildLaunch: { executable, argv, cwd, TMPDIR: tmpdir(), startedUTC, ...identity } }));
    const line = await bounded(readyLine, 5000); assert.ok(line, "Bounded original readiness line required");
    const ready = JSON.parse(fault === "readiness" ? "{invalid synthetic metadata" : line); assert.deepEqual(Object.keys(ready).sort(), ["port", "service"]);
    assert.deepEqual(ready.service, service); assert.ok(Number.isInteger(ready.port) && ready.port > 0 && ready.port <= 65535);
    return await body(ready);
  } finally {
    // This runs even when ps, JSON parsing, service metadata, the body or receipt work fails.
    if (child.exitCode === null && child.signalCode === null) child.stdin.end("stop\n");
    let actual = await bounded(terminal, 5000);
    const signals: string[] = [];
    if (!actual) {
      if (child.exitCode === null && child.signalCode === null) { signals.push("SIGTERM"); child.kill("SIGTERM"); }
      actual = await bounded(terminal, 1000);
    }
    if (!actual) {
      if (child.exitCode === null && child.signalCode === null) { signals.push("SIGKILL"); child.kill("SIGKILL"); }
      actual = await terminal;
    }
    // Preserve the actual direct wait result before fallible absence/hash/assertion work.
    console.log(JSON.stringify({ fixtureChildTerminal: { executable, argv, cwd, startedUTC, finishedUTC: new Date().toISOString(), pid: child.pid ?? null, identity: identity ?? null, actualExitCode: actual.code, signal: actual.signal, directCloseWaitCompleted: true, fault: fault ?? null, signals, spawnError: spawnError?.message, stdinError: stdinError?.message } }));
    assert.equal(actual.code, 0, stderr); assert.equal(actual.signal, null); assert.deepEqual(signals, []);
    console.log(JSON.stringify({ fixtureChildOriginalStreams: { pid: child.pid ?? null, stdout, stderr } }));
    const stdoutSHA256 = sha(Buffer.from(stdout)), stderrSHA256 = sha(Buffer.from(stderr));
    console.log(JSON.stringify({ fixtureChildStreamHashes: { pid: child.pid ?? null, stdoutSHA256, stderrSHA256 } }));
    if (fault === "receipt") throw Error("Injected fixture receipt failure after direct wait");
    const observedIdentity = identity;
    const rows = execFileSync("/bin/ps", ["-axo", "pid=,pgid=,lstart="], { encoding: "utf8", timeout: 2000 }).trim().split("\n").map(line => line.trim().split(/\s+/));
    const remaining = observedIdentity ? rows.filter(row => Number(row[0]) === observedIdentity.pid && row.slice(2).join(" ") === observedIdentity.birth) : undefined;
    console.log(JSON.stringify({ fixtureChildReceipt: { originalStdout: stdout, originalStderr: stderr, stdoutSHA256, stderrSHA256, sameIdentityRemaining: remaining ?? null, unknownIdentityMetadata: !identity } }));
    if (identity) assert.deepEqual(remaining, []);
  }
}

test("default gate closed; model cannot choose ownership or endpoints", async () => {
  const dir = await privateDir(), journal = await PrivateTechnicalVisionHostJournal.open(dir), p = await prepared(), f = fakeBackend(p);
  try {
    const host = createTechnicalVisionHost({ backend: f.backend, service, journal, owner: () => owner, authorize: () => true, prepare: async () => p });
    assert.equal(host.availability, "disabled"); await assert.rejects(host.invoke(input, signal()), (e: unknown) => e instanceof TechnicalVisionError && e.code === "unavailable");
    const active = createTechnicalVisionHost({ backend: f.backend, service, journal, enabled: true, owner: () => owner, authorize: () => true, prepare: async () => p });
    await assert.rejects(active.invoke({ ...input, owner: { runId: "attacker" } }, signal()), { code: "invalid_request" });
    await assert.rejects(active.invoke({ ...input, endpoint: "http://attacker" }, signal()), { code: "invalid_request" });
    assert.equal(f.counters().submits, 0); assert.equal(f.counters().readiness, 0);
    f.controls.ready = false;
    const unavailable = await active.invoke(input, signal());
    assert.equal(JSON.parse(unavailable.response.content[0].text).error.code, "unavailable");
    assert.equal((await journal.read(unavailable.handle))?.admission, "claimed"); assert.equal(f.counters().submits, 0);
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
  f.controls.loseSubmitResponse = true;
  const host = createTechnicalVisionHost({ backend: f.backend, service, journal, enabled: true, owner: () => owner, authorize: () => true, prepare: async () => { reads++; if (reads > 1) throw Error("source deleted"); return p; } });
  try {
    const first = await host.invoke(input, signal()); assert.ok(first.response.isError); assert.equal(JSON.parse(first.response.content[0].text).settlement, "unknown");
    await host.invoke(input, signal()); assert.equal(reads, 1); assert.equal(f.counters().lookups, 1); assert.equal(f.counters().cancels, 0);
    const denied = createTechnicalVisionHost({ backend: f.backend, service, journal, enabled: true, owner: () => owner, authorize: () => false, prepare: async () => p });
    await assert.rejects(denied.lookup(first.handle, signal()), (e: unknown) => e instanceof TechnicalVisionError && e.code === "not_found");
    await host.cancel(first.handle, signal()); assert.equal(f.counters().cancels, 1); assert.equal(f.job.settled, false);
  } finally { await journal.close(); await rm(dir, { recursive: true }); }
});

test("real Python service/backend + fake model HTTP + existing TS client + host end to end", async () => {
  const dir = await privateDir(), ledger = join(dir, "ledger"), hostdir = join(dir, "host");
  try {
    await mkdir(ledger, { mode: 0o700 }); await mkdir(hostdir, { mode: 0o700 });
    assert.equal(await realpath(ledger), ledger); assert.equal(await realpath(hostdir), hostdir);
    await withPythonFixture(ledger, async ready => {
      const journal = await PrivateTechnicalVisionHostJournal.open(hostdir), p = await prepared(); let reads = 0;
      try {
        const host = constructTechnicalVisionHost({ client: { expectedService: service, fixtureOrigin: `http://127.0.0.1:${ready.port}`, key: () => "fixture-private-bearer-0001" }, service, journal, enabled: true, owner: () => owner, authorize: () => true, prepare: async () => { reads++; return p; } });
        const first = await host.invoke(input, signal()); assert.equal(first.response.isError, undefined);
        let result = first;
        for (let n = 0; n < 20; n++) { result = await host.status(first.handle, signal()); if (JSON.parse(result.response.content[0].text).job.state === "completed") break; await new Promise(r => setTimeout(r, 10)); }
        const response = JSON.parse(result.response.content[0].text);
        assert.equal(response.job.state, "completed"); assert.equal(response.job.settled, true);
        assert.equal(response.job.result.extraction.text[0].exactText, "R1  10 kΩ\n  Vcc\n"); await host.invoke(input, signal()); assert.equal(reads, 1);
        const record = JSON.parse(await readFile(join(ledger, (await readdir(ledger)).find(n => n.endsWith(".json"))!), "utf8"));
        assert.deepEqual(record.metadata.owner, owner); assert.deepEqual(record.job.owner, owner);
        assert.equal(record.metadata.requestId, input.requestId); assert.deepEqual(record.metadata.service, service);
        assert.deepEqual(record.metadata.source, p.manifest); assert.equal(record.job.jobId, response.job.jobId);
        assert.equal(record.metadata.pageImages[0].sha256, sha(p.images[0].png)); assert.deepEqual(Buffer.from(record.images["1"], "base64"), p.images[0].png);
        assert.ok(!result.response.content[0].text.includes("fixture-private-bearer")); assert.ok(!result.response.content[0].text.includes('"images"'));
        console.log(JSON.stringify({ fixture: "SOURCE_ONLY real Python service/backend + TS client + host; fake model HTTP only; NATIVE_LIVE_NOT_TESTED", ledger, tmpdir: tmpdir(), tmpdirBytes: Buffer.byteLength(tmpdir()), uid: process.getuid?.(), mode: (await stat(dir)).mode & 0o777, servicePort: ready.port, rawPngBytes: p.images[0].png.length }));
      } finally { await journal.close(); }
    });
    // Exercise failure paths using real owned Python children, no model endpoints.
    for (const fault of ["identity", "readiness", "receipt"] as const) {
      const faultLedger = join(dir, `ledger-${fault}`); await mkdir(faultLedger, { mode: 0o700 });
      let bodyReached = false;
      await assert.rejects(withPythonFixture(faultLedger, async () => { bodyReached = true; }, fault), fault === "readiness" ? { name: "SyntaxError" } : /Injected fixture/);
      assert.equal(bodyReached, fault === "receipt");
    }
  } finally { await rm(dir, { recursive: true }); }
});


test("H043 one-page/two-megapixel host cap rejects before any backend POST and retains original claim", async () => {
  const dir = await privateDir(), journal = await PrivateTechnicalVisionHostJournal.open(dir), p = await prepared(), f = fakeBackend(p);
  const oversized = await prepared(2048, 1025);
  validateTechnicalVisionManifest(oversized.manifest); // Valid raster bytes/geometry, above the normal host cap.
  const host = createTechnicalVisionHost({ backend: f.backend, service, journal, enabled: true, owner: () => owner, authorize: () => true, prepare: async () => oversized });
  try {
    const result = await host.invoke(input, signal());
    assert.equal(JSON.parse(result.response.content[0].text).error.code, "source_too_large");
    assert.equal(f.counters().submits, 0); assert.equal((await journal.read(result.handle))?.admission, "claimed");
    await assert.rejects(host.invoke(input, signal()), { code: "not_found" });
    assert.equal(f.counters().submits, 0); assert.equal(f.counters().lookups, 1);
    assert.equal((await journal.read(result.handle))?.admission, "claimed");
    // Synthetic output uses the actual PDF renderer metadata contract; no PDF/native accuracy claim.
    const pdf: TechnicalVisionPrepared = {
      manifest: { ...p.manifest, sha256: sha(Buffer.from("%PDF-1.4\n% synthetic source fixture\n")), mediaType: "application/pdf",
        pages: [1, 2].map(page => ({ ...p.manifest.pages[0], page, pdf: { widthPoints: 4, heightPoints: 3, rotation: 0 as const } })) },
      images: [1, 2].map(page => ({ ...p.images[0], page })),
    };
    validateTechnicalVisionManifest(pdf.manifest);
    const pdfHost = createTechnicalVisionHost({ backend: f.backend, service, journal, enabled: true, owner: () => owner, authorize: () => true, prepare: async () => pdf });
    const pdfResult = await pdfHost.invoke({ ...input, requestId: "pdf-cap" }, signal());
    assert.equal(JSON.parse(pdfResult.response.content[0].text).error.code, "source_too_large");
    assert.equal(f.counters().submits, 0); assert.equal((await journal.read(pdfResult.handle))?.admission, "claimed");
  } finally { await journal.close(); await rm(dir, { recursive: true }); }
});


test("explicit Stop during preparation durably records intent and prevents the initial POST", async () => {
  const dir = await privateDir(), journal = await PrivateTechnicalVisionHostJournal.open(dir), p = await prepared(), f = fakeBackend(p);
  let release!: () => void, started!: () => void; const begun = new Promise<void>(r => { started = r; }), wait = new Promise<void>(r => { release = r; });
  const host = createTechnicalVisionHost({ backend: f.backend, service, journal, enabled: true, owner: () => owner, authorize: () => true, prepare: async () => { started(); await wait; return p; } });
  let invocation: ReturnType<typeof host.invoke> | undefined, closed = false;
  try {
    invocation = host.invoke(input, signal()); await begun;
    const files = (await readdir(dir)).filter(f => f.startsWith("vision-")); const handle = files[0].replace(/\.json$/, "");
    // No job exists before POST. Stop persists intent even when original-key lookup is 404.
    await assert.rejects(host.cancel(handle, signal()), { code: "not_found" });
    assert.equal((await journal.read(handle))?.cancelIntent, true);
    release(); const result = await invocation;
    assert.equal(f.counters().submits, 0); assert.equal((await journal.read(handle))?.cancelIntent, true);
    assert.equal(JSON.parse(result.response.content[0].text).error.code, "observation_cancelled");
    assert.equal(f.counters().cancels, 0); assert.equal((await journal.read(handle))?.admission, "claimed");
    await journal.close(); closed = true;
    const reopened = await PrivateTechnicalVisionHostJournal.open(dir);
    try { assert.equal((await reopened.read(handle))?.cancelIntent, true); }
    finally { await reopened.close(); }
  } finally {
    release(); await invocation?.catch(() => {});
    try { if (!closed) await journal.close(); } finally { await rm(dir, { recursive: true }); }
  }
});
