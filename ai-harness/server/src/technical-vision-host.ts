/** H043 trusted host interface. No normal route/MCP registration; default closed. */
import { createHash, randomBytes } from "node:crypto";
import { constants } from "node:fs";
import { open, lstat, realpath, rename, unlink, type FileHandle } from "node:fs/promises";
import { join, resolve } from "node:path";
import {
  TechnicalVisionError, TECHNICAL_VISION_LIMITS,
  type TechnicalVisionIdentity, type TechnicalVisionOwner, type TechnicalVisionInput,
  type TechnicalVisionPrepared, type TechnicalVisionJob,
} from "./technical-vision-contracts.js";
import { TechnicalVisionClient, type TechnicalVisionBackend, type TechnicalVisionClientOptions } from "./technical-vision-client.js";
import { validateTechnicalVisionOwner, validateTechnicalVisionInput, validateTechnicalVisionIdentity, validateTechnicalVisionJob } from "./technical-vision-validation.js";
import { technicalImageAnalyzeDefinition, type TechnicalVisionToolResponse } from "./technical-vision-tool.js";

export interface VisionHostRecord {
  handle: string;
  owner: TechnicalVisionOwner;
  service: TechnicalVisionIdentity;
  requestId: string;
  inputFingerprint: string;
  /** admitted/ambiguous claims are never resubmitted, even after host restart. */
  admission: "claimed" | "observed";
  jobId?: string;
  terminal?: { deliveryId: string; job: TechnicalVisionJob; acknowledged: boolean };
}
export interface TechnicalVisionHostJournal {
  /** Atomic unique original-owner/request binding; return false for an existing claim. */
  claim(record: VisionHostRecord): Promise<boolean>;
  read(handle: string): Promise<VisionHostRecord | undefined>;
  observe(handle: string, job: TechnicalVisionJob): Promise<VisionHostRecord>;
  acknowledge(handle: string, deliveryId: string): Promise<void>;
}
const fingerprint = (v: unknown): string => {
  const stable = (x: unknown): unknown => Array.isArray(x) ? x.map(stable) : x && typeof x === "object" ? Object.fromEntries(Object.entries(x).sort(([a], [b]) => a.localeCompare(b)).map(([k, v]) => [k, stable(v)])) : x;
  return createHash("sha256").update(JSON.stringify(stable(v))).digest("hex");
};
const id = (v: string) => { if (!/^[a-zA-Z0-9_-]{1,80}$/.test(v)) throw new TechnicalVisionError("invalid_request"); return v; };
const retained = (owner: TechnicalVisionOwner, requestId: string) => `vision-${fingerprint([owner.workspaceId, owner.sessionId, owner.runId, requestId]).slice(0, 64)}`;

/** Private single-host-process journal with durable atomic records and outbox.
 * The normal host must hold its existing single-writer/database boundary. This
 * directory is trusted configuration, never a tool argument. An exclusive private
 * lock refuses concurrent writers; a crash leaves a lock requiring owned review.
 */
export class PrivateTechnicalVisionHostJournal implements TechnicalVisionHostJournal {
  private tail: Promise<unknown> = Promise.resolve();
  private static readonly writers = new Set<string>();
  private constructor(private readonly directory: string, private readonly lock: FileHandle, private readonly inode: number, private readonly device: number) {}
  static async open(directory: string): Promise<PrivateTechnicalVisionHostJournal> {
    const path = resolve(directory), s = await lstat(path);
    if (await realpath(path) !== path || !s.isDirectory() || s.uid !== process.getuid?.() || (s.mode & 0o777) !== 0o700 || this.writers.has(path)) throw new TechnicalVisionError("unavailable");
    const lock = await open(join(path, "owner.lock"), constants.O_WRONLY | constants.O_CREAT | constants.O_EXCL | constants.O_NOFOLLOW, 0o600);
    await lock.writeFile("H043 private host journal single writer\n"); await lock.sync();
    this.writers.add(path); return new PrivateTechnicalVisionHostJournal(path, lock, s.ino, s.dev);
  }
  /** Close only after host operations drain; no service cancellation is implied. */
  async close() { await this.tail; await this.guard(); await unlink(join(this.directory, "owner.lock")); await this.lock.close(); PrivateTechnicalVisionHostJournal.writers.delete(this.directory); }
  private async guard() {
    const s = await lstat(this.directory), lock = await this.lock.stat(), current = await lstat(join(this.directory, "owner.lock"));
    if (!s.isDirectory() || s.ino !== this.inode || s.dev !== this.device || s.uid !== process.getuid?.() || (s.mode & 0o777) !== 0o700 || lock.ino !== current.ino || !current.isFile() || current.nlink !== 1 || current.uid !== process.getuid?.() || (current.mode & 0o777) !== 0o600) throw new TechnicalVisionError("unavailable");
  }
  private serial<T>(fn: () => Promise<T>): Promise<T> { const p = this.tail.then(fn); this.tail = p.catch(() => {}); return p; }
  private async load(handle: string): Promise<VisionHostRecord | undefined> {
    await this.guard();
    const path = join(this.directory, `${id(handle)}.json`);
    let fd;
    try { fd = await open(path, constants.O_RDONLY | constants.O_NOFOLLOW); }
    catch (e) { if ((e as NodeJS.ErrnoException).code === "ENOENT") return undefined; throw new TechnicalVisionError("unavailable"); }
    try {
      const s = await fd.stat();
      if (!s.isFile() || s.nlink !== 1 || s.uid !== process.getuid?.() || (s.mode & 0o777) !== 0o600 || s.size > TECHNICAL_VISION_LIMITS.responseBytes + 16384) throw new TechnicalVisionError("unavailable");
      const bytes = await fd.readFile(), after = await fd.stat();
      if (s.ino !== after.ino || s.size !== after.size || s.mtimeMs !== after.mtimeMs) throw new TechnicalVisionError("unavailable");
      const r = JSON.parse(bytes.toString("utf8")) as VisionHostRecord;
      validateTechnicalVisionOwner(r.owner); validateTechnicalVisionIdentity(r.service); id(r.requestId);
      if (r.handle !== handle || retained(r.owner, r.requestId) !== handle || !/^[a-f0-9]{64}$/.test(r.inputFingerprint) || !["claimed", "observed"].includes(r.admission)) throw new TechnicalVisionError("unavailable");
      if (r.jobId) id(r.jobId);
      if (r.terminal) {
        validateTechnicalVisionJob(r.terminal.job, r.owner, r.service, { requestId: r.requestId, jobId: r.jobId });
        if (!r.terminal.job.settled || typeof r.terminal.acknowledged !== "boolean" || r.terminal.deliveryId !== `terminal-${handle}`) throw new TechnicalVisionError("unavailable");
      }
      return r;
    } finally { await fd.close(); }
  }
  private async save(r: VisionHostRecord): Promise<void> {
    await this.guard();
    const path = join(this.directory, `${id(r.handle)}.json`), tmp = join(this.directory, `.tmp-${randomBytes(16).toString("hex")}`);
    const fd = await open(tmp, constants.O_WRONLY | constants.O_CREAT | constants.O_EXCL | constants.O_NOFOLLOW, 0o600);
    try {
      await fd.writeFile(JSON.stringify(r)); await fd.sync(); await fd.close();
      // Refuse a replaced/hardlinked existing record rather than silently overwriting it.
      await this.load(r.handle); await rename(tmp, path);
      const dir = await open(this.directory, constants.O_RDONLY | constants.O_DIRECTORY | constants.O_NOFOLLOW);
      try { await dir.sync(); } finally { await dir.close(); }
    } finally { await fd.close().catch(() => {}); await unlink(tmp).catch(() => {}); }
  }
  claim(record: VisionHostRecord) { return this.serial(async () => {
    const existing = await this.load(record.handle);
    if (existing) { if (existing.inputFingerprint !== record.inputFingerprint) throw new TechnicalVisionError("idempotency_conflict"); return false; }
    await this.save(structuredClone(record)); return true;
  }); }
  read(handle: string) { return this.serial(() => this.load(handle)); }
  observe(handle: string, job: TechnicalVisionJob) { return this.serial(async () => {
    const r = await this.load(handle); if (!r) throw new TechnicalVisionError("not_found");
    const j = validateTechnicalVisionJob(job, r.owner, r.service, { requestId: r.requestId, jobId: r.jobId });
    r.jobId = j.jobId; r.admission = "observed";
    if (j.settled && ["completed", "failed", "cancelled"].includes(j.state) && !r.terminal) r.terminal = { deliveryId: `terminal-${handle}`, job: j, acknowledged: false };
    // A terminal outbox entry is immutable; subsequent reads cannot create a second event.
    if (r.terminal && fingerprint(r.terminal.job) !== fingerprint(j)) throw new TechnicalVisionError("invalid_response");
    await this.save(r); return r;
  }); }
  acknowledge(handle: string, deliveryId: string) { return this.serial(async () => {
    const r = await this.load(handle);
    if (!r?.terminal || r.terminal.deliveryId !== deliveryId) throw new TechnicalVisionError("not_found");
    r.terminal.acknowledged = true; await this.save(r);
  }); }
}

export interface TechnicalVisionHostOptions {
  backend: TechnicalVisionBackend;
  service: TechnicalVisionIdentity;
  journal: TechnicalVisionHostJournal;
  enabled?: boolean;
  /** Host authorization binds a running creator on invoke; follow-ups check the retained scope. */
  owner: () => TechnicalVisionOwner | Promise<TechnicalVisionOwner>;
  authorize: (action: "invoke" | "followup" | "cancel", originalOwner: TechnicalVisionOwner) => boolean | Promise<boolean>;
  prepare: (input: TechnicalVisionInput, owner: TechnicalVisionOwner, signal: AbortSignal) => Promise<TechnicalVisionPrepared>;
  /** Must atomically deduplicate deliveryId in the host event/database transaction.
   * A lost acknowledgement retries the same durable event, never a new event.
   */
  deliverOnce?: (deliveryId: string, response: TechnicalVisionToolResponse, originalOwner: TechnicalVisionOwner) => Promise<void>;
}
export function createTechnicalVisionHost(options: TechnicalVisionHostOptions) {
  const service = structuredClone(validateTechnicalVisionIdentity(options.service));
  function gate() { if (options.enabled !== true) throw new TechnicalVisionError("unavailable"); }
  async function access(handle: string, action: "followup" | "cancel") {
    gate(); const r = await options.journal.read(id(handle));
    if (!r || !await options.authorize(action, structuredClone(r.owner))) throw new TechnicalVisionError("not_found");
    return r;
  }
  function publicResponse(job: TechnicalVisionJob, handle: string): TechnicalVisionToolResponse {
    const { owner: _owner, ...publicJob } = job;
    const value = { handle, job: publicJob, observation: job.settled ? "settled" : "pending", qualification: "source_preparation_only" };
    const text = JSON.stringify(value); if (Buffer.byteLength(text) > TECHNICAL_VISION_LIMITS.responseBytes) throw new TechnicalVisionError("invalid_response");
    return { ...(["failed", "cancelled", "interrupted"].includes(job.state) ? { isError: true } : {}), content: [{ type: "text", text }] };
  }
  async function observed(r: VisionHostRecord, j: TechnicalVisionJob) {
    const valid = validateTechnicalVisionJob(j, r.owner, r.service, { requestId: r.requestId, jobId: r.jobId });
    await options.journal.observe(r.handle, valid); return { handle: r.handle, response: publicResponse(valid, r.handle) };
  }
  return {
    definition: technicalImageAnalyzeDefinition,
    availability: options.enabled === true ? "candidate" as const : "disabled" as const,
    async invoke(raw: unknown, signal: AbortSignal) {
      gate(); const input = validateTechnicalVisionInput(raw), owner = structuredClone(validateTechnicalVisionOwner(await options.owner()));
      if (!await options.authorize("invoke", owner)) throw new TechnicalVisionError("unavailable");
      const handle = retained(owner, input.requestId), r: VisionHostRecord = { handle, owner, service, requestId: input.requestId, inputFingerprint: fingerprint(input), admission: "claimed" };
      // Claim before readiness/source read/POST. A crashed or ambiguous attempt only looks up.
      if (!await options.journal.claim(r)) return observed((await options.journal.read(handle))!, await options.backend.lookup(owner, input.requestId, signal));
      try {
        const readiness = await options.backend.readiness(signal);
        if (!readiness.ready || !readiness.admitting) throw new TechnicalVisionError("unavailable");
        const prepared = await options.prepare(input, owner, signal); signal.throwIfAborted();
        return observed(r, await options.backend.submit(owner, input, prepared, signal));
      } catch (e) {
        // Retain the original key/owner; caller receives a reconciliation handle.
        const error = e instanceof TechnicalVisionError ? e : new TechnicalVisionError(signal.aborted ? "observation_cancelled" : "unavailable");
        return { handle, response: { isError: true, content: [{ type: "text" as const, text: JSON.stringify({ handle, requestId: input.requestId, error: { code: error.code, message: error.message }, settlement: "unknown", instruction: "Use lookup with this handle; do not resubmit or create a new requestId." }) }] } };
      }
    },
    async lookup(handle: string, signal: AbortSignal) { const r = await access(handle, "followup"); return observed(r, await options.backend.lookup(r.owner, r.requestId, signal)); },
    async status(handle: string, signal: AbortSignal) { const r = await access(handle, "followup"); return observed(r, r.jobId ? await options.backend.status(r.owner, r.jobId, signal) : await options.backend.lookup(r.owner, r.requestId, signal)); },
    async cancel(handle: string, signal: AbortSignal) {
      const r = await access(handle, "cancel"), jobId = r.jobId ?? (await options.backend.lookup(r.owner, r.requestId, signal)).jobId;
      return observed(r, await options.backend.cancel(r.owner, jobId, signal));
    },
    /** No polling or inference; drain exactly one logical durable terminal event.
     * Exactly-once sink behavior requires deliverOnce's transactional unique key.
     */
    async deliverTerminal(handle: string) {
      const r = await access(handle, "followup");
      if (!r.terminal || r.terminal.acknowledged || !options.deliverOnce) return false;
      await options.deliverOnce(r.terminal.deliveryId, publicResponse(r.terminal.job, handle), structuredClone(r.owner));
      await options.journal.acknowledge(handle, r.terminal.deliveryId); return true;
    },
  };
}
/** Real client construction uses the existing strict service origin policy. */
export function constructTechnicalVisionHost(options: Omit<TechnicalVisionHostOptions, "backend"> & { client: TechnicalVisionClientOptions }) {
  return createTechnicalVisionHost({ ...options, backend: new TechnicalVisionClient(options.client) });
}
