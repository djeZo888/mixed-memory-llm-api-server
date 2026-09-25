import { randomBytes, randomUUID } from "node:crypto";
import type { Store } from "./store.js";
import type { Files } from "./files.js";
import { ApiError, requireId } from "./errors.js";
import type {
  ImageBackend,
  ImageJob,
  ImageSubmission,
  FrozenImageReference,
} from "./image-contracts.js";
import {
  adjustmentFor,
  geometry,
  prepare,
  sha256,
  validateOutput,
} from "./image-codec.js";
import { ImageFiles } from "./image-files.js";
import {
  serviceAvailability,
  type AvailabilityProvider,
} from "./service-availability.js";

type Lane = "idle" | "active" | "quarantined";
interface RecordData {
  job: ImageJob;
  submission: ImageSubmission;
  bodyHash: string;
  workspaceId: string;
  deadline: number;
  sourceSeeds: number[];
  preparedSha256?: string[];
  snapshots: FrozenImageReference[];
  retryAt: number;
  approvalHash?: string;
  approvalTokenHash?: string;
  approvalTokenExpires?: number;
  decision?: "approve" | "reject";
}
export interface ImageBrokerOptions {
  store: Store;
  files: Files;
  backend: ImageBackend;
  availability?: AvailabilityProvider;
  /** Internal adapter identity; the node transport mapping is owned by the caller. */
  serviceId?: string;
  currentRun(
    sessionId: string,
  ): { runId: string; workspaceId: string } | undefined;
  /** Shorter clocks are injected only in offline fixtures. */
  now?: () => number;
  queueMs?: number;
  requestMs?: number;
  cleanupMs?: number;
  tickMs?: number;
}
const terminal = new Set(["completed", "failed", "cancelled", "interrupted"]);
const canonical = (value: unknown): string => {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value && typeof value === "object")
    return `{${Object.entries(value)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([k, v]) => `${JSON.stringify(k)}:${canonical(v)}`)
      .join(",")}}`;
  return JSON.stringify(value);
};
function submission(value: unknown): ImageSubmission {
  const bad = () =>
    new ApiError(
      400,
      "invalid_image_request",
      "Expected requestId, operation, prompt, optional size, seed and owned references only",
    );
  if (!value || typeof value !== "object" || Array.isArray(value)) throw bad();
  const b = value as Record<string, unknown>;
  if (
    Object.keys(b).some(
      (k) =>
        ![
          "requestId",
          "operation",
          "prompt",
          "size",
          "seed",
          "references",
        ].includes(k),
    )
  )
    throw bad();
  requireId(b.requestId);
  if (
    !["generation", "edit"].includes(String(b.operation)) ||
    typeof b.prompt !== "string" ||
    !b.prompt.trim() ||
    Buffer.byteLength(b.prompt) > 16384
  )
    throw bad();
  if (
    b.size !== undefined &&
    (typeof b.size !== "string" || !/^\d{1,5}x\d{1,5}$/.test(b.size))
  )
    throw bad();
  if (
    b.seed !== undefined &&
    (typeof b.seed !== "number" || !Number.isSafeInteger(b.seed) || b.seed < 0)
  )
    throw bad();
  if (
    b.references !== undefined &&
    (!Array.isArray(b.references) || b.references.length > 2)
  )
    throw bad();
  for (const ref of (b.references ?? []) as unknown[]) {
    if (
      !ref ||
      typeof ref !== "object" ||
      Array.isArray(ref) ||
      Object.keys(ref).length !== 1
    )
      throw bad();
    if ("fileId" in ref) requireId(ref.fileId);
    else if ("workspacePath" in ref) {
      if (
        typeof ref.workspacePath !== "string" ||
        !ref.workspacePath ||
        ref.workspacePath.length > 2048 ||
        ref.workspacePath.startsWith("/") ||
        ref.workspacePath.includes("\\") ||
        ref.workspacePath.includes(":") ||
        /[\x00-\x1f]/.test(ref.workspacePath) ||
        ref.workspacePath.split("/").some((p) => !p || p === "." || p === "..")
      )
        throw bad();
    } else throw bad();
  }
  if (
    b.operation === "edit" &&
    !(b.references as unknown[] | undefined)?.length
  )
    throw bad();
  if (
    b.operation === "generation" &&
    (b.references as unknown[] | undefined)?.length
  )
    throw new ApiError(
      400,
      "image_references_require_edit",
      "Generation accepts no references; use image_edit for reference-based creation",
    );
  return JSON.parse(JSON.stringify(b)) as ImageSubmission;
}

/** A single durable image lane. It neither acquires nor releases text gateway lanes. */
export class ImageBroker {
  private records = new Map<string, RecordData>();
  private lane: Lane = "quarantined";
  private closed = false;
  private pumping = false;
  private reconciling = false;
  private serial: Promise<unknown> = Promise.resolve();
  private timer: NodeJS.Timeout;
  private controller?: AbortController;
  private execution?: Promise<void>;
  private resumePreparation?: () => void;
  readonly imageFiles: ImageFiles;
  readonly now: () => number;
  constructor(readonly options: ImageBrokerOptions) {
    this.now = options.now ?? Date.now;
    this.imageFiles = new ImageFiles(options.files);
    const db = options.store.db;
    db.exec(`CREATE TABLE IF NOT EXISTS h003_image_jobs(id TEXT PRIMARY KEY, session_id TEXT NOT NULL, request_id TEXT NOT NULL, data TEXT NOT NULL, UNIQUE(session_id,request_id));
      CREATE TABLE IF NOT EXISTS h003_image_lane(id INTEGER PRIMARY KEY CHECK(id=1),state TEXT NOT NULL);`);
    for (const row of db
      .prepare("SELECT data FROM h003_image_jobs ORDER BY rowid")
      .all()) {
      const record = JSON.parse(String(row.data)) as RecordData;
      this.records.set(record.job.id, record);
    }
    this.setLane("quarantined");
    for (const r of this.records.values())
      if (!terminal.has(r.job.state)) {
        r.job.state = "interrupted";
        r.job.finishedAt = this.iso();
        r.job.error = {
          code: "server_restarted",
          message:
            "Server restarted; image work was interrupted and will not be replayed",
        };
        this.persist(r);
      }
    this.timer = setInterval(() => this.kick(), options.tickMs ?? 1000);
    this.timer.unref();
    this.kick();
  }
  private iso() {
    return new Date(this.now()).toISOString();
  }
  private lock<T>(f: () => Promise<T>): Promise<T> {
    const next = this.serial.then(f, f);
    this.serial = next.catch(() => {});
    return next;
  }
  private setLane(state: Lane) {
    this.options.store.db
      .prepare("INSERT OR REPLACE INTO h003_image_lane VALUES(1,?)")
      .run(state);
    this.lane = state;
  }
  private persist(r: RecordData, lane?: Lane) {
    const db = this.options.store.db;
    // Queue position is a revisioned part of each job, not an unversioned GET
    // calculation. Commit the transition and every affected waiter together.
    const changed = new Set<RecordData>([r]);
    const positions = new Map(
      this.queued().map((entry, index) => [entry, index + 1]),
    );
    const before = new Map<
      RecordData,
      { revision: number; position?: number }
    >();
    for (const entry of this.records.values()) {
      const position = positions.get(entry);
      if (entry.job.queuePosition !== position) changed.add(entry);
    }
    for (const entry of changed)
      before.set(entry, {
        revision: entry.job.revision,
        position: entry.job.queuePosition,
      });
    db.exec("BEGIN IMMEDIATE");
    try {
      for (const entry of changed) {
        entry.job.revision++;
        const position = positions.get(entry);
        if (position === undefined) delete entry.job.queuePosition;
        else entry.job.queuePosition = position;
        db.prepare(
          "INSERT OR REPLACE INTO h003_image_jobs VALUES(?,?,?,?)",
        ).run(
          entry.job.id,
          entry.job.sessionId,
          entry.job.requestId,
          JSON.stringify(entry),
        );
      }
      if (lane)
        db.prepare("INSERT OR REPLACE INTO h003_image_lane VALUES(1,?)").run(
          lane,
        );
      db.exec("COMMIT");
    } catch (e) {
      for (const [entry, old] of before) {
        entry.job.revision = old.revision;
        if (old.position === undefined) delete entry.job.queuePosition;
        else entry.job.queuePosition = old.position;
      }
      db.exec("ROLLBACK");
      this.lane = "quarantined";
      throw e;
    }
    if (lane) this.lane = lane;
    for (const entry of changed)
      this.options.store.emit(
        entry.job.sessionId,
        "image_job",
        { job: this.public(entry, true) },
        entry.job.runId,
      );
  }
  private queued() {
    return [...this.records.values()].filter((r) => r.job.state === "queued");
  }
  private public(r: RecordData, browser = false): ImageJob {
    const value = { ...r.job };
    if (browser) delete value.outputPath;
    return structuredClone({
      ...value,
      ...(r.job.startedAt
        ? {
            elapsedMs: Math.max(
              0,
              (r.job.finishedAt ? Date.parse(r.job.finishedAt) : this.now()) -
                Date.parse(r.job.startedAt),
            ),
          }
        : {}),
    });
  }
  private owned(sessionId: string, jobId: string) {
    this.options.store.getSession(sessionId);
    const r = this.records.get(requireId(jobId));
    if (!r || r.job.sessionId !== sessionId)
      throw new ApiError(404, "not_found", "Image job not found");
    return r;
  }
  browser(job: ImageJob) {
    const value = structuredClone(job);
    delete value.outputPath;
    return value;
  }
  list(sessionId: string) {
    this.options.store.getSession(sessionId);
    return [...this.records.values()]
      .filter((r) => r.job.sessionId === sessionId)
      .map((r) => this.public(r, true));
  }
  get(sessionId: string, jobId: string) {
    return this.public(this.owned(sessionId, jobId));
  }
  snapshot() {
    return { lane: this.lane, queued: this.queued().length };
  }
  private dispatch() {
    return serviceAvailability(
      this.options.availability,
      this.options.serviceId ?? "image",
    ).dispatch;
  }
  private unavailable() {
    return this.dispatch() === "reject";
  }
  private requireAvailable() {
    if (this.dispatch() === "hold")
      throw new ApiError(
        503,
        "image_readiness_unknown",
        "Image readiness is temporarily unavailable; pending work is retained",
      );
    if (this.unavailable())
      throw new ApiError(
        503,
        "image_service_unavailable",
        "Image service is unavailable",
      );
  }
  /** Active requests keep their settlement/artifact path. Only undispatched work fails. */
  notifyAvailabilityChanged() {
    this.kick();
  }
  private rejectUnavailablePending() {
    if (!this.unavailable()) return false;
    for (const r of this.records.values())
      if (["queued", "awaiting_approval"].includes(r.job.state))
        this.finish(
          r,
          "failed",
          "image_service_unavailable",
          "Image service is unavailable; request was not dispatched",
        );
    return true;
  }
  async capabilities() {
    this.requireAvailable();
    try {
      return await this.options.backend.capabilities(
        AbortSignal.timeout(10000),
      );
    } catch {
      throw new ApiError(
        503,
        "image_unavailable",
        "Image capabilities are unavailable",
      );
    }
  }
  private binding(sessionId: string) {
    const session = this.options.store.getSession(sessionId),
      current = this.options.currentRun(sessionId);
    if (
      this.closed ||
      session.deleteRequested ||
      !current ||
      session.workspaceId !== current.workspaceId
    )
      throw new ApiError(
        409,
        "no_active_run",
        "Image submission requires the current active session run",
      );
    return current;
  }
  async submit(sessionId: string, value: unknown): Promise<ImageJob> {
    const body = submission(value),
      bodyHash = sha256(canonical(body));
    return this.lock(async () => {
      this.options.store.getSession(sessionId);
      const old = [...this.records.values()].find(
        (r) =>
          r.job.sessionId === sessionId && r.job.requestId === body.requestId,
      );
      if (old) {
        if (old.bodyHash !== bodyHash)
          throw new ApiError(
            409,
            "request_id_conflict",
            "requestId already belongs to a different image request",
          );
        return this.public(old);
      }
      this.requireAvailable();
      const binding = this.binding(sessionId),
        id = randomUUID();
      const capabilities = await this.capabilities();
      const profiles = this.options.backend
        .profiles(capabilities)
        .filter(
          (p) =>
            p.operation === body.operation &&
            p.referenceCount === (body.references?.length ?? 0),
        );
      if (!profiles.length)
        throw new ApiError(
          503,
          "image_operation_unavailable",
          "No qualified profile is available for this operation and reference count",
        );
      const supported = [...new Set(profiles.map((p) => p.size))];
      if (body.size && !supported.includes(body.size))
        throw new ApiError(
          400,
          "unsupported_image_size",
          `Supported sizes: ${supported.join(", ")}`,
        );
      const snapshots = await this.imageFiles.snapshot(
        sessionId,
        binding.workspaceId,
        id,
        body.references ?? [],
      );
      const sourceSeeds = this.sourceSeeds(
        sessionId,
        snapshots.map((ref) => ref.sha256),
      );
      if (body.seed !== undefined && sourceSeeds.includes(body.seed))
        throw new ApiError(
          400,
          "source_seed_collision",
          "Seed matches a known source or ancestor image; choose another seed",
        );
      let seed = body.seed;
      if (seed === undefined) {
        do {
          seed = randomBytes(4).readUInt32BE();
        } while (sourceSeeds.includes(seed));
      }
      const refs = snapshots.map(
        ({ referenceId, fileId, name, sha256, width, height }) => ({
          referenceId,
          ...(fileId ? { fileId } : {}),
          name,
          sha256,
          width,
          height,
        }),
      );
      const original = refs[0]
        ? `${refs[0].width}x${refs[0].height}`
        : "1920x1080";
      const requestedSize =
        body.size ?? (body.operation === "generation" ? "1920x1080" : original);
      let target = requestedSize;
      if (!supported.includes(target)) {
        if (body.operation === "generation")
          throw new ApiError(
            400,
            "unsupported_image_size",
            `Supported sizes: ${supported.join(", ")}`,
          );
        target = [...supported].sort((a, b) => {
          const cost = (size: string) => {
            const [w, h] = geometry(size);
            return refs.reduce(
              (n, r) =>
                n +
                Math.abs(Math.log(w / r.width)) +
                Math.abs(Math.log(h / r.height)),
              0,
            );
          };
          return cost(a) - cost(b);
        })[0]!;
      }
      geometry(target);
      const adjustment = adjustmentFor(refs, target),
        current = this.binding(sessionId);
      if (current.runId !== binding.runId)
        throw new ApiError(
          409,
          "run_changed",
          "Originating run ended before image admission",
        );
      if (!adjustment && this.queued().length >= 8)
        throw new ApiError(
          429,
          "image_queue_full",
          "Image queue has eight waiting jobs",
        );
      this.requireAvailable();
      const job: ImageJob = {
        revision: 0,
        id,
        sessionId,
        runId: binding.runId,
        requestId: body.requestId,
        operation: body.operation,
        prompt: body.prompt,
        seed,
        requestedSize,
        model: profiles.find((p) => p.size === target)!.model,
        state: adjustment ? "awaiting_approval" : "queued",
        references: refs,
        createdAt: this.iso(),
        cancelRequested: false,
        ...(adjustment ? { adjustment } : {}),
      };
      const record: RecordData = {
        job,
        submission: body,
        sourceSeeds,
        snapshots,
        bodyHash,
        workspaceId: binding.workspaceId,
        deadline: this.now() + (this.options.queueMs ?? 30 * 60 * 1000),
        retryAt: 0,
        ...(adjustment
          ? { approvalHash: this.approvalHash(job, snapshots) }
          : {}),
      };
      this.records.set(id, record);
      try {
        this.persist(record);
      } catch (e) {
        this.records.delete(id);
        throw e;
      }
      this.kick();
      return this.public(record);
    });
  }
  private sourceSeeds(sessionId: string, hashes: string[]): number[] {
    const seeds = new Set<number>();
    // Match actual snapshot bytes, including workspace copies and next-edit copies.
    // Imported images without retained provenance have no provable source seed.
    for (const file of this.options.store.files(sessionId, "artifact")) {
      if (!file.image || !hashes.includes(file.image.sha256)) continue;
      seeds.add(file.image.seed);
      for (const seed of this.records.get(file.image.jobId)?.sourceSeeds ?? [])
        seeds.add(seed);
    }
    return [...seeds].sort((a, b) => a - b);
  }
  private approvalHash(job: ImageJob, snapshots: FrozenImageReference[]) {
    return sha256(
      canonical({
        references: job.references,
        snapshots,
        adjustment: job.adjustment,
      }),
    );
  }
  issueApprovalToken(sessionId: string, jobId: string) {
    return this.lock(async () => {
      const r = this.owned(sessionId, jobId);
      this.rejectUnavailablePending();
      if (
        this.closed ||
        r.job.state !== "awaiting_approval" ||
        r.decision ||
        this.options.store.getSession(sessionId).deleteRequested
      )
        throw new ApiError(
          409,
          "invalid_image_state",
          "Image approval is no longer pending",
        );
      if (r.approvalHash !== this.approvalHash(r.job, r.snapshots))
        throw new ApiError(
          409,
          "approval_changed",
          "Approval adjustment has changed",
        );
      const approvalToken = randomBytes(32).toString("hex");
      r.approvalTokenHash = sha256(approvalToken);
      r.approvalTokenExpires = this.now() + 10 * 60 * 1000;
      this.persist(r);
      return {
        approvalToken,
        expiresAt: new Date(r.approvalTokenExpires).toISOString(),
      };
    });
  }
  /** Issuance is restricted to the browser proxy capability route. Never gateway tools. */
  async approve(
    sessionId: string,
    jobId: string,
    decision: "approve" | "reject",
    approvalToken: string,
  ) {
    return this.lock(async () => {
      const r = this.owned(sessionId, jobId);
      if (!["approve", "reject"].includes(decision))
        throw new ApiError(
          400,
          "invalid_decision",
          "Expected approve or reject",
        );
      if (
        typeof approvalToken !== "string" ||
        !/^[a-f0-9]{64}$/.test(approvalToken) ||
        sha256(approvalToken) !== r.approvalTokenHash
      )
        throw new ApiError(
          403,
          "image_approval_forbidden",
          "A browser-issued image approval token is required",
        );
      // The consumed token can read back only the identical decision after a lost
      // response; it cannot authorize another job, changed input or opposite decision.
      if (r.decision === decision) return this.public(r);
      if (!r.approvalTokenExpires || r.approvalTokenExpires <= this.now())
        throw new ApiError(
          403,
          "image_approval_expired",
          "Image approval token expired",
        );
      if (this.closed || r.decision || r.job.state !== "awaiting_approval")
        throw new ApiError(
          409,
          "invalid_image_state",
          "Image approval is no longer pending",
        );
      if (this.options.store.getSession(sessionId).deleteRequested)
        throw new ApiError(409, "deleting", "Session is deleting");
      if (decision === "approve") {
        this.requireAvailable();
        if (r.approvalHash !== this.approvalHash(r.job, r.snapshots))
          throw new ApiError(
            409,
            "approval_changed",
            "Approval adjustment has changed",
          );
        await this.imageFiles.frozen(r.job, r.snapshots);
        if (
          this.closed ||
          r.job.state !== "awaiting_approval" ||
          this.options.store.getSession(sessionId).deleteRequested
        )
          throw new ApiError(
            409,
            "invalid_image_state",
            "Image approval is no longer pending",
          );
        this.requireAvailable();
        if (this.queued().length >= 8)
          throw new ApiError(
            429,
            "image_queue_full",
            "Image queue has eight waiting jobs",
          );
        r.job.state = "queued";
        r.deadline = this.now() + (this.options.queueMs ?? 30 * 60 * 1000);
      } else {
        r.job.state = "cancelled";
        r.job.cancelRequested = true;
        r.job.finishedAt = this.iso();
      }
      r.decision = decision;
      this.persist(r);
      this.options.store.upsertActivity(sessionId, {
        id: `image-approval:${jobId}`,
        runId: r.job.runId,
        kind: "tool",
        name: "Image canvas approval",
        status: "completed",
        updatedAt: this.iso(),
        finishedAt: this.iso(),
        summary:
          decision === "approve"
            ? "Canvas adjustment approved by user"
            : "Canvas adjustment rejected by user",
      });
      this.kick();
      return this.public(r);
    });
  }
  cancel(sessionId: string, jobId: string) {
    const r = this.owned(sessionId, jobId);
    if (!terminal.has(r.job.state)) {
      r.job.cancelRequested = true;
      if (["queued", "awaiting_approval"].includes(r.job.state)) {
        r.job.state = "cancelled";
        r.job.finishedAt = this.iso();
      }
      this.persist(r);
      this.kick();
    }
    return this.public(r);
  }
  cancelSession(sessionId: string) {
    for (const r of this.records.values())
      if (r.job.sessionId === sessionId && !terminal.has(r.job.state))
        this.cancel(sessionId, r.job.id);
  }
  private kick() {
    this.resumePreparation?.();
    if (this.closed || this.rejectUnavailablePending()) return;
    for (const r of this.queued())
      if (this.now() >= r.deadline)
        this.finish(
          r,
          "failed",
          "image_queue_timeout",
          "Image queue deadline exceeded",
        );
    if (this.dispatch() === "hold") return;
    if (this.lane === "quarantined") {
      void this.reconcile();
      return;
    }
    if (this.pumping || this.lane !== "idle") return;
    const r = this.queued()[0];
    if (!r || this.now() < r.retryAt) return;
    const previousState = r.job.state,
      previousStartedAt = r.job.startedAt;
    this.pumping = true;
    r.job.state = "running";
    r.job.startedAt = this.iso();
    try {
      this.persist(r, "active");
    } catch {
      // persist restores revisions/positions; also undo this tentative admission
      // so readiness reconciliation cannot strand a job that never dispatched.
      r.job.state = previousState;
      if (previousStartedAt === undefined) delete r.job.startedAt;
      else r.job.startedAt = previousStartedAt;
      this.pumping = false;
      return;
    }
    this.execution = this.execute(r)
      .catch(() => {
        this.lane = "quarantined";
      })
      .finally(() => {
        this.pumping = false;
        this.execution = undefined;
        this.controller = undefined;
        this.kick();
      });
  }
  async reconcile(): Promise<void> {
    if (
      this.closed ||
      this.dispatch() !== "allow" ||
      this.reconciling ||
      this.pumping ||
      this.lane !== "quarantined"
    )
      return;
    this.reconciling = true;
    try {
      const health = await this.options.backend.readiness(
        AbortSignal.timeout(10000),
      );
      if (
        !this.closed &&
        this.dispatch() === "allow" &&
        health.ready === true &&
        health.idle === true
      )
        this.setLane("idle");
    } catch {
      /* Retain quarantine without positive readiness AND idle evidence. */
    } finally {
      this.reconciling = false;
    }
    if (!this.closed && this.snapshot().lane === "idle") this.kick();
  }
  private finish(
    r: RecordData,
    state: ImageJob["state"],
    code?: string,
    message?: string,
    lane?: Lane,
  ) {
    r.job.state = state;
    r.job.finishedAt = this.iso();
    if (code && message) r.job.error = { code, message };
    this.persist(r, lane);
  }
  private async execute(r: RecordData) {
    let dispatched = false,
      settled = false;
    const controller = new AbortController();
    this.controller = controller;
    const timer = setTimeout(
      () => controller.abort(),
      (this.options.requestMs ?? 900000) + (this.options.cleanupMs ?? 60000),
    );
    timer.unref();
    try {
      const source = await this.imageFiles.frozen(r.job, r.snapshots),
        references = [];
      for (const [i, bytes] of source.entries())
        references.push(await prepare(bytes, r.job.adjustment?.sources[i]));
      if (controller.signal.aborted) throw new Error("timeout");
      if (r.job.cancelRequested) {
        this.finish(r, "cancelled", undefined, undefined, "idle");
        return;
      }
      while (
        this.dispatch() === "hold" &&
        !controller.signal.aborted &&
        !r.job.cancelRequested
      ) {
        // Keep this preparation's active reservation while telemetry is unknown.
        // Requeueing here could create a ninth waiter and reorder the shared lane.
        await new Promise<void>((resolve) => {
          const release = () => {
            this.resumePreparation = undefined;
            controller.signal.removeEventListener("abort", release);
            resolve();
          };
          this.resumePreparation = release;
          controller.signal.addEventListener("abort", release, { once: true });
          if (this.dispatch() !== "hold" || controller.signal.aborted)
            release();
        });
      }
      if (controller.signal.aborted) throw new Error("timeout");
      if (r.job.cancelRequested) {
        this.finish(r, "cancelled", undefined, undefined, "idle");
        return;
      }
      this.requireAvailable();
      r.preparedSha256 = references.map(sha256);
      this.persist(r); // Exact conditioned bytes are hashed before native dispatch.
      dispatched = true;
      const result = await this.options.backend.execute(
        {
          operation: r.job.operation,
          prompt: r.job.prompt,
          seed: r.job.seed,
          model: r.job.model,
          size: r.job.adjustment?.targetSize ?? r.job.requestedSize,
          references,
        },
        controller.signal,
      );
      settled = true;
      if (result.kind === "not_admitted") {
        if (this.unavailable())
          this.finish(
            r,
            "failed",
            "image_service_unavailable",
            "Image service is unavailable; request was not admitted",
            "idle",
          );
        else if (r.job.cancelRequested)
          this.finish(r, "cancelled", undefined, undefined, "idle");
        else {
          if (!Number.isFinite(result.retryAfterMs) || result.retryAfterMs < 0)
            throw new Error("invalid retry");
          r.retryAt = this.now() + Math.max(1000, result.retryAfterMs);
          if (r.retryAt >= r.deadline)
            this.finish(
              r,
              "failed",
              "image_queue_timeout",
              "Retry-After exceeds image queue deadline",
              "idle",
            );
          else if (this.queued().length >= 8)
            this.finish(
              r,
              "failed",
              "image_queue_full",
              "Retry was not admitted because eight image jobs are already waiting",
              "idle",
            );
          else {
            r.job.state = "queued";
            delete r.job.startedAt;
            this.persist(r, "idle");
          }
        }
        return;
      }
      r.job.state = "saving";
      this.persist(r);
      clearTimeout(timer);
      const saveSignal = AbortSignal.timeout(this.options.cleanupMs ?? 60000);
      const size = r.job.adjustment?.targetSize ?? r.job.requestedSize;
      await validateOutput(result.png, size);
      if (result.seed !== r.job.seed || result.model !== r.job.model)
        throw new ApiError(
          502,
          "image_provenance_mismatch",
          "Upstream image metadata does not match the admitted job",
        );
      r.job.actualSize = size;
      const saved = await this.imageFiles.save(
        r.job,
        r.workspaceId,
        result.png,
        saveSignal,
      );
      Object.assign(r.job, {
        artifactId: saved.artifactId,
        ...(saved.outputPath ? { outputPath: saved.outputPath } : {}),
      });
      if (!saved.outputPath) {
        this.finish(
          r,
          r.job.cancelRequested ? "cancelled" : "failed",
          "image_workspace_save_failed",
          "Image artifact retained; workspace copy could not be saved",
          "idle",
        );
        return;
      }
      this.finish(
        r,
        r.job.cancelRequested ? "cancelled" : "completed",
        undefined,
        undefined,
        "idle",
      );
    } catch (error) {
      const ambiguous = dispatched && !settled,
        known = error instanceof ApiError;
      this.finish(
        r,
        this.closed
          ? "interrupted"
          : r.job.cancelRequested
            ? "cancelled"
            : "failed",
        this.closed
          ? "server_stopped"
          : ambiguous
            ? "image_completion_unknown"
            : known
              ? error.code
              : "image_processing_failed",
        this.closed
          ? "Server stopped; image work will not be replayed"
          : ambiguous
            ? "Image completion is unknown; request will not be replayed and lane requires readiness and idle confirmation"
            : known
              ? error.message
              : "Image processing failed",
        ambiguous || this.closed ? "quarantined" : "idle",
      );
    } finally {
      clearTimeout(timer);
    }
  }
  private closePromise?: Promise<void>;
  close(): Promise<void> {
    this.closePromise ??= this.shutdown();
    return this.closePromise;
  }
  private async shutdown() {
    if (this.closed) return;
    this.closed = true;
    clearInterval(this.timer);
    await this.serial;
    this.controller?.abort();
    await this.execution;
    for (const r of this.records.values())
      if (!terminal.has(r.job.state))
        this.finish(
          r,
          "interrupted",
          "server_stopped",
          "Server stopped; image work was not replayed",
        );
    this.setLane("quarantined");
  }
}
