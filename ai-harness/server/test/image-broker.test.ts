import assert from "node:assert/strict";
import test, { type TestContext } from "node:test";
import {
  mkdtemp,
  mkdir,
  writeFile,
  readFile,
  rm,
  symlink,
  link,
  chmod,
  realpath,
} from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { Readable } from "node:stream";
import sharp from "sharp";
import { Store } from "../src/store.js";
import { Files } from "../src/files.js";
import { ImageBroker } from "../src/image-broker.js";
import type {
  AvailabilityProvider,
  ServiceAvailability,
} from "../src/service-availability.js";
import type {
  ImageBackend,
  ImageProfile,
  ImageJob,
} from "../src/image-contracts.js";
import {
  sha256,
  normalize,
  prepare,
  adjustmentFor,
} from "../src/image-codec.js";

const delay = (ms = 5) => new Promise((r) => setTimeout(r, ms));
async function until(f: () => boolean, message = "condition") {
  const end = Date.now() + 4000;
  while (!f()) {
    if (Date.now() >= end) throw new Error(`Timeout: ${message}`);
    await delay();
  }
}
const png = (width = 64, height = 64) =>
  sharp({ create: { width, height, channels: 3, background: "#b4823f" } })
    .png()
    .toBuffer();
class Fake implements ImageBackend {
  healthy = true;
  idle = true;
  calls: {
    input: Parameters<ImageBackend["execute"]>[0];
    resolve: (value: Awaited<ReturnType<ImageBackend["execute"]>>) => void;
    reject: (error: Error) => void;
  }[] = [];
  supported: ImageProfile[] = [
    {
      operation: "generation",
      referenceCount: 0,
      size: "64x64",
      model: "fixture-model",
    },
    {
      operation: "generation",
      referenceCount: 0,
      size: "1920x1080",
      model: "fixture-model",
    },
    {
      operation: "edit",
      referenceCount: 1,
      size: "64x64",
      model: "fixture-model",
    },
  ];
  async capabilities() {
    return { profiles: this.supported, unchanged: true };
  }
  profiles() {
    return this.supported;
  }
  async readiness() {
    return { ready: this.healthy, idle: this.idle };
  }
  execute(
    input: Parameters<ImageBackend["execute"]>[0],
    signal: AbortSignal,
  ): ReturnType<ImageBackend["execute"]> {
    this.idle = false;
    return new Promise((resolve, reject) => {
      signal.addEventListener(
        "abort",
        () => reject(new Error("fixture aborted")),
        { once: true },
      );
      this.calls.push({
        input,
        resolve: (value) => {
          this.idle = true;
          resolve(value);
        },
        reject,
      });
    });
  }
  async complete(index = this.calls.length - 1) {
    const c = this.calls[index],
      [w, h] = c.input.size.split("x").map(Number);
    c.resolve({
      kind: "output",
      png: await png(w, h),
      model: c.input.model,
      seed: c.input.seed,
    });
  }
}
async function fixture(
  t: TestContext,
  options: { queueMs?: number; availability?: AvailabilityProvider } = {},
) {
  const dir = await realpath(await mkdtemp(path.join(tmpdir(), "h003-image-")));
  const store = new Store(path.join(dir, "db.sqlite")),
    files = new Files(dir, store);
  await files.init();
  const session = store.createSession();
  await files.prepare(session.id, session.workspaceId);
  const run = store.createRun(session, "message", "fixture", []);
  store.updateRun(run.id, "running");
  const backend = new Fake();
  let current: { runId: string; workspaceId: string } | undefined = {
    runId: run.id,
    workspaceId: run.workspaceId,
  };
  let clock = Date.now();
  const broker = new ImageBroker({
    store,
    files,
    backend,
    currentRun: (id) => (id === session.id ? current : undefined),
    now: () => clock,
    queueMs: options.queueMs,
    availability: options.availability,
    tickMs: 5,
  });
  t.after(async () => {
    await broker.close();
    store.close();
    await rm(dir, { recursive: true, force: true });
  });
  await until(() => broker.snapshot().lane === "idle");
  const submit = (requestId: string, extra = {}) =>
    broker.submit(session.id, {
      requestId,
      operation: "generation",
      prompt: "fixture",
      size: "64x64",
      ...extra,
    });
  const upload = async (bytes: Buffer) =>
    files.upload(session.id, "actual.jpg", "image/jpeg", Readable.from(bytes));
  return {
    dir,
    store,
    files,
    session,
    run,
    backend,
    broker,
    submit,
    upload,
    advance: (ms: number) => {
      clock += ms;
    },
    endText: () => {
      current = undefined;
      store.updateRun(run.id, "completed");
    },
  };
}

test("one active/eight queued, durable admission, stable concurrent dedup and queue deadlines", async (t) => {
  const f = await fixture(t, { queueMs: 5000 });
  const [a, b] = await Promise.all([f.submit("same"), f.submit("same")]);
  assert.equal(a.id, b.id);
  assert.equal(a.seed, b.seed);
  assert.ok(a.seed >= 0 && a.seed <= 0xffffffff);
  await until(() => f.backend.calls.length === 1);
  assert.equal(f.backend.calls[0].input.seed, a.seed);
  const persisted = JSON.parse(
    String(
      f.store.db
        .prepare("SELECT data FROM h003_image_jobs WHERE id=?")
        .get(a.id)!.data,
    ),
  );
  assert.equal(persisted.job.state, "running");
  assert.equal(
    f.store.db.prepare("SELECT state FROM h003_image_lane").get()!.state,
    "active",
  );
  await assert.rejects(
    f.submit("same", { prompt: "changed" }),
    /different image request/,
  );
  const queued = [];
  for (let n = 0; n < 8; n++) queued.push(await f.submit(`queue-${n}`));
  await assert.rejects(f.submit("overflow"), /eight waiting/);
  assert.deepEqual(f.broker.snapshot(), { lane: "active", queued: 8 });
  f.advance(5001);
  await until(() =>
    queued.every((j) => f.broker.get(f.session.id, j.id).state === "failed"),
  );
  assert.equal(f.backend.calls.length, 1);
  await f.backend.complete();
  await until(() => f.broker.get(f.session.id, a.id).state === "completed");
  const events = f.store
    .allEvents(f.session.id)
    .filter(
      (e) => e.type === "image_job" && (e.data.job as ImageJob).id === a.id,
    );
  assert.deepEqual(
    events.map((e) => (e.data.job as ImageJob).revision),
    [1, 2, 3, 4, 5],
  );
  assert.ok(
    events.every(
      (e) =>
        e.runId === f.run.id && !("outputPath" in (e.data.job as ImageJob)),
    ),
  );
});

test("unknown completion is never replayed; only ready AND idle reopens image lane", async (t) => {
  const f = await fixture(t);
  const a = await f.submit("unknown");
  await until(() => f.backend.calls.length === 1);
  const b = await f.submit("next");
  f.backend.calls[0].reject(
    new Error("secret transport detail must not escape"),
  );
  await until(() => f.broker.get(f.session.id, a.id).state === "failed");
  assert.equal(f.broker.snapshot().lane, "quarantined");
  assert.equal((await f.submit("unknown")).id, a.id);
  assert.equal(f.backend.calls.length, 1);
  f.backend.healthy = false;
  f.backend.idle = true;
  await f.broker.reconcile();
  assert.equal(f.backend.calls.length, 1);
  f.backend.healthy = true;
  await f.broker.reconcile();
  await until(() => f.backend.calls.length === 2);
  assert.equal(f.broker.get(f.session.id, b.id).state, "running");
  assert.ok(!JSON.stringify(f.broker.list(f.session.id)).includes("secret"));
  await f.backend.complete();
  await until(() => f.broker.get(f.session.id, b.id).state === "completed");
});

test("known429 observes Retry-After and original queue deadline, reuses seed", async (t) => {
  const f = await fixture(t, { queueMs: 10000 });
  const job = await f.submit("retry");
  await until(() => f.backend.calls.length === 1);
  f.backend.calls[0].resolve({ kind: "not_admitted", retryAfterMs: 3000 });
  await until(() => f.broker.get(f.session.id, job.id).state === "queued");
  f.advance(2999);
  await delay(20);
  assert.equal(f.backend.calls.length, 1);
  f.advance(1);
  await until(() => f.backend.calls.length === 2);
  assert.equal(f.backend.calls[1].input.seed, job.seed);
  f.backend.calls[1].resolve({ kind: "not_admitted", retryAfterMs: 8000 });
  await until(() => f.broker.get(f.session.id, job.id).state === "failed");
  assert.equal(
    f.broker.get(f.session.id, job.id).error?.code,
    "image_queue_timeout",
  );
});

test("immutable snapshots, detached browser approval, idempotent decision, original bytes and run provenance", async (t) => {
  const f = await fixture(t),
    original = await png(120, 60),
    file = await f.upload(original);
  const job = await f.submit("edit", {
    operation: "edit",
    size: undefined,
    references: [{ fileId: file.id }],
  });
  assert.equal(job.state, "awaiting_approval");
  assert.equal(job.requestedSize, "120x60");
  assert.equal(job.adjustment?.targetSize, "64x64");
  assert.deepEqual(job.adjustment?.sources[0].padding, {
    left: 0,
    right: 0,
    top: 16,
    bottom: 16,
  });
  assert.equal(job.adjustment?.sources[0].workingWidth, 64);
  const copy = structuredClone(job);
  copy.adjustment!.targetSize = "1x1";
  assert.equal(
    f.broker.get(f.session.id, job.id).adjustment?.targetSize,
    "64x64",
  );
  const uploadPath = path.join(f.dir, "uploads", file.path);
  assert.deepEqual(await readFile(uploadPath), original);
  await writeFile(uploadPath, await png(5, 5)); // Changes after staging do not affect frozen approval.
  f.endText();
  const { approvalToken } = await f.broker.issueApprovalToken(
    f.session.id,
    job.id,
  );
  const [approved, repeated] = await Promise.all([
    f.broker.approve(f.session.id, job.id, "approve", approvalToken),
    f.broker.approve(f.session.id, job.id, "approve", approvalToken),
  ]);
  assert.equal(approved.id, repeated.id);
  await until(() => f.backend.calls.length === 1);
  const input = await sharp(f.backend.calls[0].input.references[0]).metadata();
  assert.equal(input.width, 64);
  assert.equal(input.height, 64);
  await f.backend.complete();
  await until(() => f.broker.get(f.session.id, job.id).state === "completed");
  const completed = f.broker.get(f.session.id, job.id),
    saved = f.store.file(completed.artifactId!);
  assert.equal(saved.runId, f.run.id);
  assert.equal(saved.image?.seed, job.seed);
  assert.equal(
    saved.image?.sha256,
    sha256(await readFile(path.join(f.dir, "artifacts", saved.path))),
  );
  assert.equal(completed.outputPath, `image-${job.id}.png`);
  assert.ok(!("outputPath" in f.broker.list(f.session.id)[0]));
  assert.equal((await f.files.discover(f.session.id)).length, 0);
  await assert.rejects(
    f.files.registerArtifact(
      f.session.id,
      completed.outputPath!,
      undefined,
      undefined,
      f.run.id,
    ),
    /broker owns/,
  );
  assert.deepEqual(
    await readFile(path.join(f.dir, "image-jobs", job.id, "0.original")),
    original,
  );
});

test("approval rejects tampered snapshot; rejection and explicit Stop while text idle never dispatch", async (t) => {
  const f = await fixture(t),
    file = await f.upload(await png(120, 60));
  const body = { operation: "edit", references: [{ fileId: file.id }] };
  const j = await f.submit("tamper", body);
  const { approvalToken } = await f.broker.issueApprovalToken(
    f.session.id,
    j.id,
  );
  const frozen = path.join(f.dir, "image-jobs", j.id, "0.png");
  await chmod(frozen, 0o600);
  await writeFile(frozen, await png());
  await assert.rejects(
    f.broker.approve(f.session.id, j.id, "approve", approvalToken),
    /integrity/,
  );
  assert.equal(
    (await f.broker.approve(f.session.id, j.id, "reject", approvalToken)).state,
    "cancelled",
  );
  assert.equal(
    (await f.broker.approve(f.session.id, j.id, "reject", approvalToken)).state,
    "cancelled",
  );
  await assert.rejects(
    f.broker.approve(f.session.id, j.id, "approve", approvalToken),
    /no longer pending/,
  );
  const stopped = await f.submit("stop", body);
  f.endText();
  f.broker.cancelSession(f.session.id);
  assert.equal(f.broker.get(f.session.id, stopped.id).state, "cancelled");
  assert.equal(f.backend.calls.length, 0);
});

test("Stop and soft Delete retain active ownership and late artifact without reviving assistant text", async (t) => {
  const f = await fixture(t),
    j = await f.submit("late");
  await until(() => f.backend.calls.length === 1);
  const q = await f.submit("queued");
  f.broker.cancelSession(f.session.id);
  assert.equal(f.broker.get(f.session.id, q.id).state, "cancelled");
  assert.equal(f.broker.get(f.session.id, j.id).state, "running");
  assert.equal(f.broker.get(f.session.id, j.id).cancelRequested, true);
  assert.equal(f.broker.snapshot().lane, "active");
  f.store.requestDelete(f.session.id);
  f.store.finishDelete(f.session.id);
  await f.backend.complete();
  await until(() => f.broker.snapshot().lane === "idle");
  const record = JSON.parse(
    String(
      f.store.db
        .prepare("SELECT data FROM h003_image_jobs WHERE id=?")
        .get(j.id)!.data,
    ),
  );
  assert.equal(record.job.state, "cancelled");
  assert.ok(record.job.artifactId);
  assert.equal(f.store.file(record.job.artifactId).messageId, null);
  assert.equal(
    f.store.messages(f.session.id).filter((m) => m.role === "assistant").length,
    0,
  );
});

test("owned references reject cross-session files, traversal, absolute paths, URLs, symlinks and hardlinks", async (t) => {
  const f = await fixture(t);
  const other = f.store.createSession();
  const alien = await f.files.upload(
    other.id,
    "a.png",
    "image/png",
    Readable.from(await png()),
  );
  const workspace = f.files.workspace(f.session.workspaceId);
  await writeFile(path.join(f.dir, "outside.png"), await png());
  await symlink(
    path.join(f.dir, "outside.png"),
    path.join(workspace, "link.png"),
  );
  await link(path.join(f.dir, "outside.png"), path.join(workspace, "hard.png"));
  let n = 0;
  for (const ref of [
    { fileId: alien.id },
    ...[
      "../outside.png",
      "/tmp/a.png",
      "http://host/a.png",
      "link.png",
      "hard.png",
    ].map((workspacePath) => ({ workspacePath })),
  ])
    await assert.rejects(
      f.submit(`unsafe-${n++}`, { operation: "edit", references: [ref] }),
    );
  await assert.rejects(
    f.submit("approved", { approved: true }),
    /Expected requestId/,
  );
  await assert.rejects(
    f.submit("identity", { sessionId: other.id }),
    /Expected requestId/,
  );
  assert.equal(f.backend.calls.length, 0);
});

test("real codec decodes actual JPEG orientation/colour; never rewrites source or stretches odd aspect ratios", async () => {
  const jpeg = await sharp({
    create: { width: 120, height: 60, channels: 3, background: "#c03b29" },
  })
    .withMetadata({ orientation: 6 })
    .jpeg()
    .toBuffer();
  const before = sha256(jpeg),
    result = await normalize(jpeg);
  assert.equal(result.width, 60);
  assert.equal(result.height, 120);
  assert.equal(result.orientation, 6);
  assert.equal(sha256(jpeg), before);
  const metadata = await sharp(result.png).metadata();
  assert.equal(metadata.space, "srgb");
  assert.equal(metadata.hasAlpha, false);
  assert.equal(metadata.orientation, undefined);
  await assert.rejects(normalize(Buffer.from("fake png")), /decode/);
  const bytes = await png(333, 257);
  const adjustment = adjustmentFor(
    [
      {
        referenceId: "r",
        name: "r",
        sha256: sha256(bytes),
        width: 333,
        height: 257,
      },
    ],
    "64x64",
  )!;
  const prepared = await prepare(bytes, adjustment.sources[0]);
  const m = await sharp(prepared).metadata();
  assert.equal(m.width, 64);
  assert.equal(m.height, 64);
});

test("unqualified edit profiles never fall back; explicit unsupported geometry returns supported list", async (t) => {
  const f = await fixture(t);
  f.backend.supported = f.backend.supported.filter(
    (p) => p.operation === "generation",
  );
  await assert.rejects(
    f.submit("edit", {
      operation: "edit",
      references: [{ workspacePath: "missing.png" }],
    }),
    /No qualified profile/,
  );
  await assert.rejects(
    f.submit("size", { size: "1920x1088" }),
    /Supported sizes: 64x64, 1920x1080/,
  );
  await assert.rejects(
    f.submit("gen-reference", { references: [{ workspacePath: "ref.png" }] }),
    /use image_edit/,
  );
  const job = await f.broker.submit(f.session.id, {
    requestId: "default",
    operation: "generation",
    prompt: "fhd",
  });
  assert.equal(job.requestedSize, "1920x1080");
});

test("restart interrupts running/queued/approval and reconciles independently without replay", async (t) => {
  const f = await fixture(t);
  const a = await f.submit("active");
  await until(() => f.backend.calls.length === 1);
  const b = await f.submit("waiting");
  const file = await f.upload(await png(120, 60));
  const c = await f.submit("approval", {
    operation: "edit",
    references: [{ fileId: file.id }],
  });
  // Preserve a crash-time durable snapshot in a separate DB, not a graceful close.
  const copy = path.join(f.dir, "restart.sqlite");
  f.store.db.prepare("VACUUM INTO ?").run(copy);
  const recoveredStore = new Store(copy),
    backend = new Fake();
  backend.idle = false;
  const recovered = new ImageBroker({
    store: recoveredStore,
    files: new Files(f.dir, recoveredStore),
    backend,
    currentRun: () => undefined,
    tickMs: 5,
  });
  t.after(async () => {
    await recovered.close();
    recoveredStore.close();
  });
  for (const j of [a, b, c])
    assert.equal(recovered.get(f.session.id, j.id).state, "interrupted");
  assert.equal(recovered.snapshot().lane, "quarantined");
  backend.idle = true;
  await recovered.reconcile();
  await delay(20);
  assert.equal(recovered.snapshot().lane, "idle");
  assert.equal(backend.calls.length, 0);
  assert.equal(
    (
      await recovered.submit(f.session.id, {
        requestId: "active",
        operation: "generation",
        prompt: "fixture",
        size: "64x64",
      })
    ).state,
    "interrupted",
  );
});

test("browser capability is job-bound, expires, hides token and allows only identical consumed decision", async (t) => {
  const f = await fixture(t),
    file = await f.upload(await png(120, 60));
  const body = { operation: "edit", references: [{ fileId: file.id }] };
  const a = await f.submit("cap-a", body),
    b = await f.submit("cap-b", body);
  const { approvalToken } = await f.broker.issueApprovalToken(
    f.session.id,
    a.id,
  );
  await assert.rejects(
    f.broker.approve(f.session.id, b.id, "approve", approvalToken),
    /browser-issued/,
  );
  await assert.rejects(
    f.broker.approve(f.session.id, a.id, "approve", ""),
    /browser-issued/,
  );
  const durable = String(
    f.store.db.prepare("SELECT data FROM h003_image_jobs WHERE id=?").get(a.id)!
      .data,
  );
  assert.ok(!durable.includes(approvalToken));
  assert.ok(
    !JSON.stringify(f.store.allEvents(f.session.id)).includes(approvalToken),
  );
  f.advance(600001);
  await assert.rejects(
    f.broker.approve(f.session.id, a.id, "approve", approvalToken),
    /expired/,
  );
  const fresh = (await f.broker.issueApprovalToken(f.session.id, a.id))
    .approvalToken;
  const rejected = await f.broker.approve(f.session.id, a.id, "reject", fresh);
  assert.deepEqual(
    await f.broker.approve(f.session.id, a.id, "reject", fresh),
    rejected,
  );
  await assert.rejects(
    f.broker.approve(f.session.id, a.id, "approve", fresh),
    /no longer pending/,
  );
  assert.equal(
    f.store
      .activities(f.session.id)
      .filter((a) => a.name === "Image canvas approval").length,
    1,
  );
  assert.equal(f.backend.calls.length, 0);
});

test("known source and ancestor seeds are rejected before dispatch, fresh defaults persist across workspace copies", async (t) => {
  const f = await fixture(t),
    source = await f.submit("source", { seed: 42 });
  await until(() => f.backend.calls.length === 1);
  await f.backend.complete();
  await until(
    () => f.broker.get(f.session.id, source.id).state === "completed",
  );
  const parent = f.broker.get(f.session.id, source.id);
  await assert.rejects(
    f.submit("collision", {
      operation: "edit",
      seed: 42,
      references: [{ fileId: parent.artifactId }],
    }),
    (e) => (e as { code: string }).code === "source_seed_collision",
  );
  const edited = await f.submit("edit-fresh", {
    operation: "edit",
    references: [{ workspacePath: parent.outputPath }],
  });
  assert.notEqual(edited.seed, 42);
  await until(() => f.backend.calls.length === 2);
  // Different real output bytes so ancestor recognition requires retained lineage.
  const c = f.backend.calls[1];
  c.resolve({
    kind: "output",
    png: await sharp({
      create: { width: 64, height: 64, channels: 3, background: "#123abc" },
    })
      .png()
      .toBuffer(),
    seed: edited.seed,
    model: edited.model,
  });
  await until(
    () => f.broker.get(f.session.id, edited.id).state === "completed",
  );
  const child = f.broker.get(f.session.id, edited.id);
  for (const seed of [42, child.seed])
    await assert.rejects(
      f.submit(`ancestor-${seed}`, {
        operation: "edit",
        seed,
        references: [{ fileId: child.artifactId }],
      }),
      /known source or ancestor/,
    );
  assert.equal(f.backend.calls.length, 2);
});

test("workspace save failure retains authoritative output artifact and provenance", async (t) => {
  const f = await fixture(t),
    job = await f.submit("save-failure");
  await until(() => f.backend.calls.length === 1);
  await writeFile(
    path.join(f.files.workspace(f.session.workspaceId), `image-${job.id}.png`),
    "existing file must not be replaced",
  );
  await f.backend.complete();
  await until(() => f.broker.get(f.session.id, job.id).state === "failed");
  const failed = f.broker.get(f.session.id, job.id);
  assert.equal(failed.error?.code, "image_workspace_save_failed");
  assert.ok(failed.artifactId);
  assert.equal(failed.outputPath, undefined);
  const saved = f.store.file(failed.artifactId!);
  assert.equal(saved.image?.jobId, job.id);
  assert.equal(
    await readFile(
      path.join(
        f.files.workspace(f.session.workspaceId),
        `image-${job.id}.png`,
      ),
      "utf8",
    ),
    "existing file must not be replaced",
  );
});

test("known429 with eight waiters fails truthfully without ninth admission or automatic resubmission", async (t) => {
  const f = await fixture(t),
    job = await f.submit("retry-full");
  await until(() => f.backend.calls.length === 1);
  for (let i = 0; i < 8; i++) await f.submit(`waiting-${i}`);
  f.backend.calls[0].resolve({ kind: "not_admitted", retryAfterMs: 1000 });
  await until(() => f.broker.get(f.session.id, job.id).state === "failed");
  assert.equal(
    f.broker.get(f.session.id, job.id).error?.code,
    "image_queue_full",
  );
  assert.ok(f.broker.snapshot().queued <= 8);
  assert.equal((await f.submit("retry-full")).state, "failed");
});

test("bad output metadata or transparent output never completes as a valid owned PNG", async (t) => {
  const f = await fixture(t);
  const wrong = await f.submit("seed-mismatch", { seed: 42 });
  await until(() => f.backend.calls.length === 1);
  f.backend.calls[0].resolve({
    kind: "output",
    png: await png(),
    seed: 43,
    model: wrong.model,
  });
  await until(() => f.broker.get(f.session.id, wrong.id).state === "failed");
  assert.equal(
    f.broker.get(f.session.id, wrong.id).error?.code,
    "image_provenance_mismatch",
  );
  const transparent = await f.submit("transparent");
  await until(() => f.backend.calls.length === 2);
  f.backend.calls[1].resolve({
    kind: "output",
    png: await sharp({
      create: {
        width: 64,
        height: 64,
        channels: 4,
        background: { r: 0, g: 0, b: 0, alpha: 0 },
      },
    })
      .png()
      .toBuffer(),
    seed: transparent.seed,
    model: transparent.model,
  });
  await until(
    () => f.broker.get(f.session.id, transparent.id).state === "failed",
  );
  assert.equal(
    f.broker.get(f.session.id, transparent.id).error?.code,
    "invalid_image_output",
  );
  assert.equal(f.store.files(f.session.id, "artifact").length, 0);
});

test("failed durable lane admission rolls back and recovers after readiness without restart", async (t) => {
  const f = await fixture(t);
  f.backend.healthy = false;
  const events: ImageJob[] = [];
  f.store.events.on(f.session.id, (event) => {
    if (event.type === "image_job") events.push(event.data.job as ImageJob);
  });
  const stored = (id: string) =>
    JSON.parse(
      String(
        f.store.db
          .prepare("SELECT data FROM h003_image_jobs WHERE id=?")
          .get(id)!.data,
      ),
    );
  f.store.db.exec(
    "CREATE TRIGGER fail_image_admission BEFORE INSERT ON h003_image_lane WHEN NEW.state='active' BEGIN SELECT RAISE(FAIL,'fixture ledger failure'); END",
  );
  const a = await f.submit("ledger-failure"),
    b = await f.submit("ledger-waiter");
  const before = [stored(a.id), stored(b.id)];
  const eventCount = events.length;
  const checkRollback = () => {
    assert.equal(f.broker.snapshot().lane, "quarantined");
    for (const [index, job] of [a, b].entries()) {
      const current = f.broker.get(f.session.id, job.id);
      assert.equal(current.state, "queued");
      assert.equal(current.startedAt, undefined);
      assert.equal(current.elapsedMs, undefined);
      assert.equal(current.queuePosition, index + 1);
      assert.equal(current.revision, before[index].job.revision);
      assert.deepEqual(stored(job.id), before[index]);
    }
    assert.equal(events.length, eventCount, "no uncommitted transition event");
    assert.equal(f.backend.calls.length, 0, "no unpersisted inference");
  };
  checkRollback();
  // A second failed admission also rolls back the other waiter's position/revision.
  f.backend.healthy = true;
  await f.broker.reconcile();
  f.backend.healthy = false;
  checkRollback();
  f.store.db.exec("DROP TRIGGER fail_image_admission");
  await f.broker.reconcile();
  checkRollback();
  f.backend.healthy = true;
  f.backend.idle = false;
  await f.broker.reconcile();
  checkRollback();

  const dispatches: string[] = [];
  const execute = f.backend.execute.bind(f.backend);
  f.backend.execute = (input, signal) => {
    const job = [a, b][dispatches.length];
    const durable = stored(job.id);
    assert.equal(durable.job.state, "running");
    assert.equal(
      durable.job.startedAt,
      f.broker.get(f.session.id, job.id).startedAt,
    );
    assert.ok(durable.job.startedAt);
    assert.equal(durable.job.queuePosition, undefined);
    assert.equal(durable.job.seed, input.seed);
    assert.equal(durable.deadline, before[dispatches.length].deadline);
    assert.equal(
      f.store.db.prepare("SELECT state FROM h003_image_lane WHERE id=1").get()!
        .state,
      "active",
    );
    dispatches.push(job.id);
    return execute(input, signal);
  };
  f.backend.idle = true;
  await f.broker.reconcile();
  await until(() => f.backend.calls.length === 1);
  const waiter = f.broker.get(f.session.id, b.id);
  assert.equal(waiter.queuePosition, 1);
  assert.equal(waiter.revision, before[1].job.revision + 1);
  assert.equal(stored(b.id).job.queuePosition, 1);
  const projected = events.filter((job) => job.id === b.id).at(-1)!;
  assert.equal(projected.revision, waiter.revision);
  assert.equal(projected.queuePosition, waiter.queuePosition);
  await f.backend.complete(0);
  await until(() => f.backend.calls.length === 2);
  await f.backend.complete(1);
  await until(() =>
    f.broker.list(f.session.id).every((job) => job.state === "completed"),
  );
  await until(() => f.broker.snapshot().lane === "idle");
  await f.broker.reconcile();
  await delay(20);
  assert.deepEqual(dispatches, [a.id, b.id]);
  assert.equal(f.broker.snapshot().queued, 0);
  assert.equal(f.backend.calls.length, 2);
});

test("queue start, cancel and busy429 reorder every affected waiter with durable newer revisions", async (t) => {
  const f = await fixture(t);
  // Match the browser's strict revision reducer: equal revisions are ignored.
  const projected = new Map<string, ImageJob>();
  f.store.events.on(f.session.id, (event) => {
    if (event.type !== "image_job") return;
    const job = event.data.job as ImageJob;
    if (job.revision > (projected.get(job.id)?.revision ?? 0))
      projected.set(job.id, job);
  });
  const a = await f.submit("position-active");
  await until(() => f.backend.calls.length === 1);
  const b = await f.submit("position-b"),
    c = await f.submit("position-c"),
    d = await f.submit("position-d");
  const read = (id: string) => f.broker.get(f.session.id, id);
  const stored = (id: string) =>
    JSON.parse(
      String(
        f.store.db
          .prepare("SELECT data FROM h003_image_jobs WHERE id=?")
          .get(id)!.data,
      ),
    );
  const deadlines = new Map(
    [b, c, d].map((job) => [job.id, stored(job.id).deadline]),
  );
  const check = () => {
    for (const job of f.broker.list(f.session.id)) {
      const seen = projected.get(job.id)!;
      assert.equal(seen.revision, job.revision);
      assert.equal(seen.state, job.state);
      assert.equal(seen.queuePosition, job.queuePosition);
      assert.equal(stored(job.id).job.queuePosition, job.queuePosition);
      // A refresh at equal revision gives precisely the same queue position.
      if (job.revision > seen.revision) projected.set(job.id, job);
      assert.equal(projected.get(job.id)!.queuePosition, job.queuePosition);
    }
  };
  check();
  assert.deepEqual(
    [
      read(b.id).queuePosition,
      read(c.id).queuePosition,
      read(d.id).queuePosition,
    ],
    [1, 2, 3],
  );
  const cBefore = read(c.id).revision,
    dBefore = read(d.id).revision;
  await f.backend.complete(0);
  await until(() => f.backend.calls.length === 2);
  assert.equal(read(a.id).state, "completed");
  assert.equal(read(b.id).queuePosition, undefined);
  assert.deepEqual(
    [read(c.id).queuePosition, read(d.id).queuePosition],
    [1, 2],
  );
  assert.ok(read(c.id).revision > cBefore && read(d.id).revision > dBefore);
  check();
  const dStarted = read(d.id).revision;
  f.broker.cancel(f.session.id, c.id);
  assert.equal(read(d.id).queuePosition, 1);
  assert.ok(read(d.id).revision > dStarted);
  check();
  const e = await f.submit("position-e"),
    dCancelled = read(d.id).revision,
    eBefore = read(e.id).revision;
  f.backend.calls[1].resolve({ kind: "not_admitted", retryAfterMs: 1000 });
  await until(() => read(b.id).state === "queued");
  assert.deepEqual(
    [
      read(b.id).queuePosition,
      read(d.id).queuePosition,
      read(e.id).queuePosition,
    ],
    [1, 2, 3],
  );
  assert.ok(read(d.id).revision > dCancelled && read(e.id).revision > eBefore);
  check();
  const dRequeued = read(d.id).revision;
  f.advance(1000);
  await until(() => f.backend.calls.length === 3);
  assert.deepEqual(
    [read(d.id).queuePosition, read(e.id).queuePosition],
    [1, 2],
  );
  assert.ok(read(d.id).revision > dRequeued);
  check();
  for (const [id, deadline] of deadlines)
    assert.equal(stored(id).deadline, deadline);
  assert.equal(f.backend.calls[2].input.seed, b.seed);
  assert.equal(f.broker.snapshot().queued, 2);
});

test("token issuance waits behind delayed approval and cannot rotate the consumed token", async (t) => {
  const f = await fixture(t),
    file = await f.upload(await png(120, 60));
  const job = await f.submit("token-race", {
    operation: "edit",
    references: [{ fileId: file.id }],
  });
  const t1 = await f.broker.issueApprovalToken(f.session.id, job.id);
  const original = f.broker.imageFiles.frozen.bind(f.broker.imageFiles);
  let enter!: () => void, release!: () => void;
  const entered = new Promise<void>((resolve) => {
    enter = resolve;
  });
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  f.broker.imageFiles.frozen = async (...args) => {
    enter();
    await gate;
    return original(...args);
  };
  t.after(() => {
    release();
  });
  const approval = f.broker.approve(
    f.session.id,
    job.id,
    "approve",
    t1.approvalToken,
  );
  await entered;
  let issuanceSettled = false;
  const t2 = f.broker.issueApprovalToken(f.session.id, job.id).then(
    (value) => {
      issuanceSettled = true;
      return value;
    },
    (error) => {
      issuanceSettled = true;
      throw error;
    },
  );
  const refused = assert.rejects(t2, /no longer pending/);
  await delay(10);
  assert.equal(issuanceSettled, false);
  release();
  const approved = await approval;
  await refused;
  await until(() => f.backend.calls.length === 1);
  const retry = await f.broker.approve(
    f.session.id,
    job.id,
    "approve",
    t1.approvalToken,
  );
  assert.equal(retry.id, approved.id);
  assert.equal(f.backend.calls.length, 1);
  const durable = JSON.parse(
    String(
      f.store.db
        .prepare("SELECT data FROM h003_image_jobs WHERE id=?")
        .get(job.id)!.data,
    ),
  );
  assert.equal(durable.approvalTokenHash, sha256(t1.approvalToken));
  assert.equal(durable.decision, "approve");
  await f.backend.complete();
  await until(() => readCompleted());
  function readCompleted() {
    return f.broker.get(f.session.id, job.id).state === "completed";
  }
  assert.equal(
    (await f.broker.approve(f.session.id, job.id, "approve", t1.approvalToken))
      .state,
    "completed",
  );
  assert.equal(f.backend.calls.length, 1);
});

test("known image unavailability rejects queued and approval jobs promptly while active artifacts survive", async (t) => {
  let state: ServiceAvailability["state"] = "available";
  const f = await fixture(t, { availability: () => ({ state }) });
  const running = await f.submit("running", { seed: 41 });
  await until(() => f.backend.calls.length === 1);
  const waiting = await f.submit("waiting", { seed: 42 });
  const bytes = await png(120, 60),
    reference = await f.upload(bytes);
  const editInput = {
    operation: "edit",
    size: undefined,
    seed: 43,
    references: [{ fileId: reference.id }],
  };
  const approval = await f.submit("approval", editInput);
  const token = await f.broker.issueApprovalToken(f.session.id, approval.id);
  assert.equal(approval.state, "awaiting_approval");
  state = "unavailable";
  f.broker.notifyAvailabilityChanged();
  for (const original of [waiting, approval]) {
    const failed = f.broker.get(f.session.id, original.id);
    assert.equal(failed.state, "failed");
    assert.equal(failed.error?.code, "image_service_unavailable");
    assert.equal(failed.seed, original.seed);
    assert.deepEqual(failed.references, original.references);
    assert.deepEqual(failed.adjustment, original.adjustment);
  }
  assert.equal((await f.submit("waiting", { seed: 42 })).id, waiting.id);
  assert.equal((await f.submit("approval", editInput)).id, approval.id);
  await assert.rejects(
    f.submit("waiting", { seed: 44 }),
    /different image request/,
  );
  await assert.rejects(
    f.broker.approve(f.session.id, approval.id, "approve", token.approvalToken),
    /no longer pending/,
  );
  await assert.rejects(f.submit("new"), /Image service is unavailable/);
  await assert.rejects(f.broker.capabilities(), /Image service is unavailable/);
  assert.equal(f.broker.snapshot().queued, 0);
  assert.equal(f.broker.get(f.session.id, running.id).state, "running");
  await f.backend.complete();
  await until(
    () => f.broker.get(f.session.id, running.id).state === "completed",
  );
  assert.ok(f.broker.get(f.session.id, running.id).artifactId);
  assert.deepEqual(
    await readFile(path.join(f.dir, "uploads", reference.path)),
    bytes,
  );
  state = "available";
  f.broker.notifyAvailabilityChanged();
  await delay(20);
  assert.equal(f.backend.calls.length, 1);
});

test("hardware unavailability blocks ready-idle reconciliation without replacing request quarantine", async (t) => {
  let state: ServiceAvailability["state"] = "available";
  const f = await fixture(t, { availability: () => ({ state }) });
  const unknown = await f.submit("ambiguous");
  await until(() => f.backend.calls.length === 1);
  state = "unavailable";
  f.backend.calls[0]!.reject(new Error("fixture transport ambiguity"));
  await until(() => f.broker.get(f.session.id, unknown.id).state === "failed");
  f.backend.healthy = true;
  f.backend.idle = true;
  await f.broker.reconcile();
  assert.equal(f.broker.snapshot().lane, "quarantined");
  assert.equal(
    f.broker.get(f.session.id, unknown.id).error?.code,
    "image_completion_unknown",
  );
  f.backend.healthy = false;
  state = "available";
  f.broker.notifyAvailabilityChanged();
  await f.broker.reconcile();
  assert.equal(f.broker.snapshot().lane, "quarantined");
  f.backend.healthy = true;
  await f.broker.reconcile();
  await until(() => f.broker.snapshot().lane === "idle");
  assert.equal(f.backend.calls.length, 1);
  assert.equal((await f.submit("ambiguous")).id, unknown.id);
});

test("unknown observer failures preserve image runtime and never declare hardware missing", async (t) => {
  const f = await fixture(t, {
    availability: () => {
      throw new Error("observer failure fixture");
    },
  });
  const job = await f.submit("normal");
  await until(() => f.backend.calls.length === 1);
  await f.backend.complete();
  await until(() => f.broker.get(f.session.id, job.id).state === "completed");
  assert.equal(f.broker.get(f.session.id, job.id).error, undefined);
});

test("image availability is rechecked after asynchronous reference preparation before dispatch", async (t) => {
  let state: ServiceAvailability["state"] = "available",
    preparing = false;
  const f = await fixture(t, { availability: () => ({ state }) });
  const frozen = f.broker.imageFiles.frozen.bind(f.broker.imageFiles);
  let release!: () => void;
  const pause = new Promise<void>((resolve) => {
    release = resolve;
  });
  f.broker.imageFiles.frozen = async (...args) => {
    preparing = true;
    await pause;
    return frozen(...args);
  };
  const job = await f.submit("preparing");
  await until(() => preparing);
  state = "unavailable";
  f.broker.notifyAvailabilityChanged();
  release();
  await until(() => f.broker.get(f.session.id, job.id).state === "failed");
  assert.equal(
    f.broker.get(f.session.id, job.id).error?.code,
    "image_service_unavailable",
  );
  assert.equal(f.backend.calls.length, 0);
});
