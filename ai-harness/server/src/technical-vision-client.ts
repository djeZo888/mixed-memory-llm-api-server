import { request } from "node:http";
import { randomBytes } from "node:crypto";
import {
  TECHNICAL_VISION_LIMITS as L, TechnicalVisionError,
  type TechnicalVisionIdentity, type TechnicalVisionOwner, type TechnicalVisionInput,
  type TechnicalVisionPrepared, type TechnicalVisionJob,
} from "./technical-vision-contracts.js";
import { technicalVisionEqual, validateTechnicalVisionIdentity, validateTechnicalVisionOwner, validateTechnicalVisionInput, validateTechnicalVisionManifest, validateTechnicalVisionJob } from "./technical-vision-validation.js";
import { technicalVisionSha256 } from "./technical-vision-sources.js";
import { technicalVisionWithinSignal } from "./technical-vision-lifecycle.js";

export interface TechnicalVisionClientOptions {
  /** Host-only protected credential callback; never accepted from a tool argument. */
  key: () => string | Promise<string>;
  expectedService: TechnicalVisionIdentity;
  /** Root/C must select the service port. No production default or environment lookup. */
  serviceOrigin?: string;
  /** Generation0 HTTP fixtures only, strictly IPv4 loopback. */
  fixtureOrigin?: string;
  requestMs?: number;
}
export interface TechnicalVisionBackend {
  readiness(signal: AbortSignal): Promise<{ ready: boolean; admitting: boolean }>;
  submit(owner: TechnicalVisionOwner, input: TechnicalVisionInput, prepared: TechnicalVisionPrepared, signal: AbortSignal): Promise<TechnicalVisionJob>;
  status(owner: TechnicalVisionOwner, jobId: string, signal: AbortSignal): Promise<TechnicalVisionJob>;
  cancel(owner: TechnicalVisionOwner, jobId: string, signal: AbortSignal): Promise<TechnicalVisionJob>;
  lookup(owner: TechnicalVisionOwner, requestId: string, signal: AbortSignal): Promise<TechnicalVisionJob>;
}
export class TechnicalVisionClient implements TechnicalVisionBackend {
  private readonly origin: string;
  private readonly expected: TechnicalVisionIdentity;
  private readonly requestMs: number;
  constructor(private readonly options: TechnicalVisionClientOptions) {
    this.expected = structuredClone(validateTechnicalVisionIdentity(options.expectedService));
    if (!!options.serviceOrigin === !!options.fixtureOrigin) throw new TechnicalVisionError("invalid_request");
    const u = new URL(options.fixtureOrigin ?? options.serviceOrigin!);
    if (u.protocol !== "http:" || u.hostname !== (options.fixtureOrigin ? "127.0.0.1" : "10.156.100.60") || !u.port || u.username || u.password || u.pathname !== "/" || u.search || u.hash || (options.fixtureOrigin && this.expected.mode !== "mock")) throw new TechnicalVisionError("invalid_request");
    this.origin = u.origin;
    this.requestMs = options.requestMs ?? 15000;
    if (!Number.isSafeInteger(this.requestMs) || this.requestMs < 1 || this.requestMs > 120000) throw new TechnicalVisionError("invalid_request");
  }
  private async call(route: string, signal: AbortSignal, body?: Buffer, contentType = "application/json", requestId?: string): Promise<unknown> {
    const bounded = AbortSignal.any([signal, AbortSignal.timeout(this.requestMs)]);
    try {
      bounded.throwIfAborted();
      const key = await technicalVisionWithinSignal(Promise.resolve().then(() => this.options.key()), bounded);
      if (!key || !/^[\x21-\x7e]+$/.test(key)) throw new TechnicalVisionError("unavailable");
      bounded.throwIfAborted();
      const response = await new Promise<{ status: number; bytes: Buffer; contentType: string }>((resolve, reject) => {
        const req = request(new URL(route, this.origin), {
          method: body ? "POST" : "GET", signal: bounded, agent: false,
          headers: { Authorization: `Bearer ${key}`, Accept: "application/json", ...(body ? { "Content-Type": contentType, "Content-Length": String(body.length) } : {}), ...(requestId ? { "Idempotency-Key": requestId } : {}) },
        }, res => {
          const chunks: Buffer[] = []; let length = 0;
          res.on("data", (chunk: Buffer) => { length += chunk.length; if (length > L.responseBytes) { req.destroy(); reject(new TechnicalVisionError("invalid_response")); return; } chunks.push(chunk); });
          res.on("error", () => reject(new TechnicalVisionError("unavailable")));
          res.on("end", () => res.complete ? resolve({ status: res.statusCode ?? 0, bytes: Buffer.concat(chunks), contentType: String(res.headers["content-type"] ?? "") }) : reject(new TechnicalVisionError("unavailable")));
        });
        req.on("error", () => reject(new TechnicalVisionError("unavailable")));
        req.end(body);
      });
      const code = ({ 404: "not_found", 409: "idempotency_conflict", 429: "queue_full", 503: "unavailable" } as const)[response.status as 404];
      if (code) throw new TechnicalVisionError(code);
      // No redirect following, no HTTP fallback, no blind retry after an ambiguous POST.
      if (![200, 202].includes(response.status)) throw new TechnicalVisionError("unavailable");
      if (!/^application\/json(?:\s*;|$)/i.test(response.contentType)) throw new TechnicalVisionError("invalid_response");
      try { return JSON.parse(response.bytes.toString("utf8")); } catch { throw new TechnicalVisionError("invalid_response"); }
    } catch (e) {
      if (signal.aborted) throw new TechnicalVisionError("observation_cancelled");
      if (bounded.aborted) throw new TechnicalVisionError("timeout");
      if (e instanceof TechnicalVisionError) throw e;
      throw new TechnicalVisionError("unavailable");
    }
  }
  async readiness(signal: AbortSignal) {
    const raw = await this.call("/v1/technical-vision/capabilities", signal);
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) throw new TechnicalVisionError("invalid_response");
    const r = raw as Record<string, unknown>;
    if (Object.keys(r).sort().join() !== ["admitting", "ready", "schemaVersion", "service"].sort().join() || r.schemaVersion !== 1 || typeof r.ready !== "boolean" || typeof r.admitting !== "boolean" || !technicalVisionEqual(validateTechnicalVisionIdentity(r.service), this.expected)) throw new TechnicalVisionError("invalid_response");
    return { ready: r.ready, admitting: r.admitting };
  }
  async submit(owner: TechnicalVisionOwner, raw: TechnicalVisionInput, prepared: TechnicalVisionPrepared, signal: AbortSignal) {
    const input = validateTechnicalVisionInput(raw);
    validateTechnicalVisionOwner(owner); validateTechnicalVisionManifest(prepared.manifest);
    if (!technicalVisionEqual(input.source, prepared.manifest.reference) || !technicalVisionEqual(input.crops ?? [], prepared.manifest.crops) || (input.pages && !technicalVisionEqual(input.pages, prepared.manifest.pages.map(p => p.page))) || prepared.images.length !== prepared.manifest.pages.length || prepared.images.reduce((n, p) => n + p.png.length, 0) > 50 * 1024 * 1024) throw new TechnicalVisionError("invalid_source");
    for (const p of prepared.manifest.pages) {
      const images = prepared.images.filter(i => i.page === p.page);
      if (images.length !== 1 || !Buffer.isBuffer(images[0].png) || images[0].sha256 !== technicalVisionSha256(images[0].png)) throw new TechnicalVisionError("invalid_source");
    }
    const metadata = {
      schemaVersion: 1, owner, requestId: input.requestId, service: this.expected,
      source: prepared.manifest, ...(input.question ? { question: input.question } : {}),
      pageImages: prepared.images.map(i => ({ page: i.page, sha256: i.sha256, part: `page-${i.page}` })),
    };
    const boundary = `technical-vision-${randomBytes(16).toString("hex")}`;
    const chunks: Buffer[] = [Buffer.from(`--${boundary}\r\nContent-Disposition: form-data; name="metadata"\r\nContent-Type: application/json\r\n\r\n${JSON.stringify(metadata)}\r\n`)];
    for (const i of prepared.images) chunks.push(Buffer.from(`--${boundary}\r\nContent-Disposition: form-data; name="page-${i.page}"; filename="page-${i.page}.png"\r\nContent-Type: image/png\r\n\r\n`), i.png, Buffer.from("\r\n"));
    chunks.push(Buffer.from(`--${boundary}--\r\n`));
    const rawJob = await this.call("/v1/technical-vision/jobs", signal, Buffer.concat(chunks), `multipart/form-data; boundary=${boundary}`, input.requestId);
    return validateTechnicalVisionJob(rawJob, owner, this.expected, { requestId: input.requestId, source: prepared.manifest });
  }
  private async job(operation: "status" | "cancel", owner: TechnicalVisionOwner, jobId: string, signal: AbortSignal) {
    validateTechnicalVisionOwner(owner);
    if (!/^[a-zA-Z0-9_-]{1,80}$/.test(jobId)) throw new TechnicalVisionError("invalid_request");
    const raw = await this.call(`/v1/technical-vision/jobs/${jobId}/${operation}`, signal, Buffer.from(JSON.stringify({ schemaVersion: 1, owner })));
    return validateTechnicalVisionJob(raw, owner, this.expected, { jobId });
  }
  status(owner: TechnicalVisionOwner, jobId: string, signal: AbortSignal) { return this.job("status", owner, jobId, signal); }
  cancel(owner: TechnicalVisionOwner, jobId: string, signal: AbortSignal) { return this.job("cancel", owner, jobId, signal); }
  async lookup(owner: TechnicalVisionOwner, requestId: string, signal: AbortSignal) {
    validateTechnicalVisionOwner(owner);
    if (!/^[a-zA-Z0-9_-]{1,80}$/.test(requestId)) throw new TechnicalVisionError("invalid_request");
    const raw = await this.call(`/v1/technical-vision/requests/${requestId}/status`, signal, Buffer.from(JSON.stringify({ schemaVersion: 1, owner })));
    return validateTechnicalVisionJob(raw, owner, this.expected, { requestId });
  }
}
