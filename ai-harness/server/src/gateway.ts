import { emitAdmission, type QwenAdmissionContext, type QwenAdmissionObserver } from "./codex-admission.js";
import { codexProvider, type CodexProviderContract } from "./codex-provider.js";
import type { ProviderBoundaryCapture, ProviderFailure } from "./provider-diagnostics.js";
import { translateResponses, ResponsesStream, responsesFailureCode, CODEX_CONTEXT, type ResponsesDiagnostic } from "./codex-responses.js";
import { GatewayOwnership, type OwnershipOptions, type SettlementQuery } from "./gateway-ownership.js";
import { MIMO_MODEL, prepareMimo, countMimo, mimoGenerationRequest, MimoStreamValidator, MimoError, type MimoAdmission } from "./mimo.js";
import { mimoUrl, MIMO_PRODUCTION_OUTPUT, type MimoFrontierOptions } from "./mimo-frontier.js";
import {
  FRONTIER_MODEL,
  frontierUrl,
  frontierBody,
  countFrontier,
  type FrontierOptions,
  type FrontierRecord,
} from "./frontier.js";
import type { ImageBroker } from "./image-broker.js";
import {
  serviceAvailability,
  type AvailabilityProvider,
  type ServiceAvailability,
} from "./service-availability.js";
import { ApiError, requireId } from "./errors.js";
import Fastify, {
  type FastifyInstance,
  type FastifyReply,
  type FastifyRequest,
} from "fastify";
import { randomBytes } from "node:crypto";
import {
  request as httpRequest,
  type ClientRequest,
  type IncomingMessage,
} from "node:http";
import { request as httpsRequest } from "node:https";
import { MAX_OUTPUT, MODEL, type GatewayUsage } from "./contracts.js";

/** Per-dispatched-request elapsed budget; queue/count retain their own limits. */
export function activeRequestTimeoutMs(model: string, override?: number): number {
  return positive(override, (model === "mimo-v2.6-pro-rl" ? 8 : 2) * 60 * 60 * 1000, "activeTimeoutMs");
}

export interface GatewayUpstream {
  url: string;
  alias: string;
}
export interface GatewayOptions {
  ownership?: OwnershipOptions;
  /** Explicit host acceptance capture only; raw bytes never enter normal logs. */
  diagnostics?: {
    capture?: (event: ProviderBoundaryCapture) => void;
    onFailure?: (event: ProviderFailure) => void;
  };
  /** Trusted temporary matched pilot ceiling for BOTH text engines; default65536. */
  qwenOutputLimit?: number;
  responses?: {
    /** Closed by default. Host reviewed policy only; never browser controlled. */
    enabled: boolean;
    /** Trusted bounded pilot may reserve less; ordinary production remains 65536. */
    outputLimit?: number;
    /** Per-request filter inside the existing shared queue; MiniMax keeps all lanes. */
    qualifiedAliases?: readonly string[];
    /** Revalidate current owner policy for each admission, not startup-only IDs. */
    currentAliases?: (context?: QwenAdmissionContext) => Promise<readonly string[]>;
    onAdmissionDiagnostic?: QwenAdmissionObserver;
    /** Independent reviewed MiMo Responses acceptance gate; holds still win. */
    frontierQualified?: true;
    frontierAcceptance?: (sessionId: string) => boolean;
    onDiagnostic?: (event: {requestId:string;sessionId:string;lane:string;diagnostic: ResponsesDiagnostic}) => void;
    /** Bounded host diagnostics keyed to the existing request owner, no model text. */
    /** Explicit private acceptance capture only; production leaves this absent. */
    onTrace?: (event: {requestId:string;sessionId:string;lane:string;chunk:Buffer}) => void;
    onError?: (event: {requestId:string;sessionId:string;lane:string;phase:'stream'|'terminal';code:string}) => void;
    /** Count the EXACT final Qwen chat template/history/tool payload on this lane. */
    countQwen: (body: Readonly<Record<string, unknown>>, lane: GatewayUpstream, key: string, signal: AbortSignal, context?: QwenAdmissionContext) => Promise<{inputTokens:number; contextWindow:480000}>;
  };
  frontier?: FrontierOptions | MimoFrontierOptions;
  /** Actual selected identity even when qualification fails; never fallback. */
  selectedFrontierModel?: typeof FRONTIER_MODEL | typeof MIMO_MODEL;
  /** Latest unresolved durable request owner, retained across profile changes. */
  initialFrontierOwnerModel?: string;
  images?: ImageBroker;
  /** Separate reviewed specialist-job gate; text settlement never releases image ownership. */
  codexImageJobsQualified?: boolean;
  /** Trusted temporary exact-session/run acceptance, checked on each new job. */
  imageAcceptance?: (sessionId: string) => boolean;
  dispatchHeld?: (alias: string) => boolean;
  /** Local cached observation only; unknown preserves existing admission behavior. */
  availability?: AvailabilityProvider;
  /** The protected credential is supplied by the host. This module never reads files. */
  upstreamKey: string | (() => string | Promise<string>);
  /** Deployment uses the fixed defaults; overrides permit local protocol fixtures. */
  upstreams?: readonly [GatewayUpstream, GatewayUpstream];
  onUsage?: (usage: GatewayUsage) => void;
  queueLimit?: number;
  /** Aggregate serialized request-body bytes waiting for a lane; default 128 MiB. */
  queueByteLimit?: number;
  queueTimeoutMs?: number;
  activeTimeoutMs?: number;
  /** Durable host ledger; previous active requests recover quarantined. */
  initialLaneStates?: Readonly<Record<string, LaneState>>;
  /** Must durably commit synchronously. Admission records active before dispatch. */
  onLaneState?: (alias: string, state: LaneState) => void;
}
export type LaneState = "idle" | "active" | "quarantined";
export interface Gateway {
  app: FastifyInstance;
  issueToken(sessionId: string, scope?: "minimax" | "codex"): string;
  revokeToken(token: string): void;
  revokeSession(sessionId: string): void;
  /** Gateway proof only; optional bounded drain observation (0..15000ms).
   * Caller separately proves native parent/children cannot emit more work. */
  confirmSettlement(query: SettlementQuery, waitMs?: number): Promise<boolean>;
  /** Observe durable session transitions until settlement/failure or host shutdown.
   * No separate timeout: existing request and queue deadlines own expiry. */
  observeSettlement(query: SettlementQuery, stop: AbortSignal): Promise<boolean>;
  sessionWork(sessionId: string): import("./gateway-ownership.js").RequestOwnership[];
  snapshot(): {
    queued: number;
    queuedBytes: number;
    lanes: {
      alias: string;
      state: LaneState;
      availability: ServiceAvailability;
    }[];
  };
  frontierSnapshot(): {
    model: string;
    contextWindow: number | null;
    configured: boolean;
    provider: "glm" | "mimo";
    maxOutputTokens: number | null;
    capacity: { published: number; configured: number | null; allocated: number | null; occupiedTested: number | null };
    queued: number;
    state: LaneState | "unavailable";
    availability: ServiceAvailability;
  };
  /** Publish cache changes promptly without touching active request settlement. */
  notifyAvailabilityChanged(): void;
  reconcileAfterOwnerSettlement(aliases: string[]): boolean;
  close(): Promise<void>;
}

const DEFAULT_UPSTREAMS: readonly [GatewayUpstream, GatewayUpstream] = [
  { url: "http://10.156.100.60:30002/v1", alias: "qwen3.8-27b-gpu0" },
  { url: "http://10.156.100.60:30004/v1", alias: "qwen3.8-27b" },
];
const OBSERVATION_LIMIT = 256 * 1024;

class GatewayError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
  ) {
    super(message);
  }
}
interface Lane {
  upstream: GatewayUpstream;
  state: LaneState;
  dispatched?: boolean;
  ownerSettled?: boolean;
}
interface Ticket {
  allowedAliases?: readonly string[];
  bytes: number;
  signal: AbortSignal;
  resolve: (lane: Lane) => void;
  reject: (error: Error) => void;
  timer?: NodeJS.Timeout;
  abort: () => void;
}

/** One shared FIFO for every request, including native children and compaction. */
class Admission {
  readonly lanes: Lane[];
  private queue: Ticket[] = [];
  private queueBytes = 0;
  private stopped = false;
  constructor(
    upstreams: readonly GatewayUpstream[],
    private limit: number,
    private byteLimit: number,
    private timeout: number,
    initial: Readonly<Record<string, LaneState>> = {},
    private onState?: (alias: string, state: LaneState) => void,
    private availability?: AvailabilityProvider,
  ) {
    this.lanes = upstreams.map((upstream) => {
      const previous = initial[upstream.alias];
      if (
        previous !== undefined &&
        !["idle", "active", "quarantined"].includes(previous)
      )
        throw new Error("Invalid persisted lane state");
      const lane: Lane = {
        upstream,
        state: previous && previous !== "idle" ? "quarantined" : "idle",
      };
      this.onState?.(upstream.alias, lane.state);
      return lane;
    });
  }
  private transition(lane: Lane, state: LaneState) {
    try {
      this.onState?.(lane.upstream.alias, state);
    } catch {
      lane.state = "quarantined";
      // A failed active write occurs before dispatch. A failed settlement write
      // leaves the previous durable active record, which recovers quarantined.
      throw new GatewayError(
        503,
        "lane_ledger_unavailable",
        "Inference lane ledger is unavailable",
      );
    }
    lane.state = state;
    if (state === "active") {
      lane.dispatched = false;
      lane.ownerSettled = false;
    }
  }
  reconcileAfterOwnerSettlement(aliases: string[]): boolean {
    const lanes = this.lanes.filter((lane) =>
      aliases.includes(lane.upstream.alias),
    );
    for (const lane of lanes) {
      if (lane.state === "quarantined") this.transition(lane, "idle");
      else if (lane.state === "active" && lane.dispatched)
        lane.ownerSettled = true;
    }
    this.notifyAvailabilityChanged();
    return true;
  }
  get queued() {
    return this.queue.length;
  }
  get queuedBytes() {
    return this.queueBytes;
  }
  available(lane: Lane): ServiceAvailability {
    return serviceAvailability(this.availability, lane.upstream.alias);
  }
  private eligible(lane: Lane, allowedAliases?: readonly string[]) {
    return (
      (!allowedAliases || allowedAliases.includes(lane.upstream.alias)) && lane.state !== "quarantined" && this.available(lane).dispatch === "allow"
    );
  }
  private blocked(allowedAliases?: readonly string[]): GatewayError | undefined {
    const lanes = this.lanes.filter(lane => !allowedAliases || allowedAliases.includes(lane.upstream.alias));
    if (
      lanes.some(
        (lane) =>
          lane.state !== "quarantined" &&
          this.available(lane).dispatch !== "reject",
      )
    )
      return;
    return lanes.some(
      (lane) => this.available(lane).state === "unavailable",
    )
      ? new GatewayError(
          503,
          "lanes_unavailable",
          "No Qwen lane is currently available",
        )
      : new GatewayError(
          503,
          "lanes_quarantined",
          "Inference lanes require settlement review",
        );
  }
  acquire(signal: AbortSignal, bytes: number, allowedAliases?: readonly string[]): Promise<Lane> {
    if (this.stopped)
      return Promise.reject(
        new GatewayError(503, "gateway_stopping", "Gateway is stopping"),
      );
    if (signal.aborted)
      return Promise.reject(
        new GatewayError(499, "cancelled", "Request cancelled"),
      );
    const lane = this.lanes.find(
      (candidate) => candidate.state === "idle" && this.eligible(candidate, allowedAliases),
    );
    if (lane && !this.queue.length) {
      try {
        this.transition(lane, "active");
        return Promise.resolve(lane);
      } catch (error) {
        return Promise.reject(error);
      }
    }
    const blocked = this.blocked(allowedAliases);
    if (blocked) return Promise.reject(blocked);
    if (this.queue.length >= this.limit)
      return Promise.reject(
        new GatewayError(429, "queue_full", "Inference queue is full"),
      );
    if (bytes > this.byteLimit - this.queueBytes)
      return Promise.reject(
        new GatewayError(
          429,
          "queue_bytes_full",
          "Inference queue body budget is full",
        ),
      );
    return new Promise((resolve, reject) => {
      const ticket: Ticket = {
        allowedAliases, bytes,
        signal,
        resolve,
        reject,
        abort: () => {
          this.remove(ticket);
          reject(new GatewayError(499, "cancelled", "Request cancelled"));
        },
      };
      ticket.timer = setTimeout(() => {
        this.remove(ticket);
        reject(
          new GatewayError(
            504,
            "queue_timeout",
            "Inference queue wait exceeded its limit",
          ),
        );
      }, this.timeout);
      ticket.timer.unref();
      signal.addEventListener("abort", ticket.abort, { once: true });
      this.queue.push(ticket);
      this.queueBytes += bytes;
      this.notifyAvailabilityChanged();
    });
  }
  private remove(ticket: Ticket) {
    const index = this.queue.indexOf(ticket);
    if (index !== -1) {
      this.queue.splice(index, 1);
      this.queueBytes -= ticket.bytes;
    }
    clearTimeout(ticket.timer);
    ticket.signal.removeEventListener("abort", ticket.abort);
  }
  settle(lane: Lane, confirmed: boolean) {
    try {
      this.transition(
        lane,
        (confirmed || lane.ownerSettled) && !this.stopped
          ? "idle"
          : "quarantined",
      );
    } catch {
      /* Fail closed locally; previous durable active remains unsafe. */
    }
    // Capture THIS owner's durable outcome before pumping a queued successor,
    // which can synchronously change the same mutable lane back to active.
    const ownerReleased = lane.state === "idle";
    this.notifyAvailabilityChanged();
    return ownerReleased;
  }
  notifyAvailabilityChanged() {
    if (this.stopped) return;
    for (const ticket of [...this.queue]) {
      const blocked = this.blocked(ticket.allowedAliases);
      if (blocked) { this.remove(ticket); ticket.reject(blocked); }
    }
    while (this.queue.length) {
      // Oldest request compatible with an idle lane; one queue, no second owner.
      const ticket = this.queue.find(t => this.lanes.some(l => l.state === "idle" && this.eligible(l, t.allowedAliases)));
      if (!ticket) break;
      const available = this.lanes.find(l => l.state === "idle" && this.eligible(l, ticket.allowedAliases))!;
      this.remove(ticket);
      if (ticket.signal.aborted) { ticket.reject(new GatewayError(499, "cancelled", "Request cancelled")); continue; }
      try { this.transition(available, "active"); ticket.resolve(available); }
      catch (error) { ticket.reject(error as Error); }
    }
  }

  private rejectQueued(code: string, message: string) {
    for (const ticket of [...this.queue]) {
      this.remove(ticket);
      ticket.reject(new GatewayError(503, code, message));
    }
  }
  stop() {
    this.stopped = true;
    this.rejectQueued("gateway_stopping", "Gateway is stopping");
  }
}

/** Observe real usage without changing forwarded bytes or buffering an unbounded response. */
class UsageObserver {
  private buffered = "";
  private bytes = 0;
  private overflow = false;
  terminal = false;
  constructor(
    private stream: boolean,
    private emit: (value: unknown) => void,
  ) {}
  data(chunk: Buffer) {
    if (!this.stream) {
      this.bytes += chunk.length;
      if (this.bytes <= OBSERVATION_LIMIT)
        this.buffered += chunk.toString("utf8");
      else {
        this.buffered = "";
        this.overflow = true;
      }
      return;
    }
    // SSE data lines are ASCII JSON. Splitting across UTF-8 characters does not
    // affect token counts or terminal recognition; response bytes are untouched.
    for (const piece of chunk.toString("utf8").split(/(?<=\n)/)) {
      if (!this.overflow) {
        this.buffered += piece;
        if (this.buffered.length > OBSERVATION_LIMIT) {
          this.buffered = "";
          this.overflow = true;
        }
      }
      if (piece.endsWith("\n")) {
        if (!this.overflow) this.line(this.buffered.trim());
        this.buffered = "";
        this.overflow = false;
      }
    }
  }
  private line(line: string) {
    if (!line.startsWith("data:")) return;
    const value = line.slice(5).trim();
    if (value === "[DONE]") {
      this.terminal = true;
      return;
    }
    try {
      this.emit(JSON.parse(value));
    } catch {
      /* A malformed observation never alters the stream. */
    }
  }
  end() {
    if (this.stream) {
      if (!this.overflow && this.buffered) this.line(this.buffered.trim());
      return;
    }
    if (!this.overflow) {
      try {
        this.emit(JSON.parse(this.buffered));
      } catch {
        /* Usage unavailable. */
      }
    }
  }
}

function positive(
  value: number | undefined,
  fallback: number,
  name: string,
): number {
  const result = value ?? fallback;
  if (!Number.isSafeInteger(result) || result < 1)
    throw new Error(`${name} must be a positive integer`);
  return result;
}

function requestBody(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value))
    throw new GatewayError(400, "invalid_request", "Expected a JSON object");
  const body = value as Record<string, unknown>;
  if (body.model !== MODEL)
    throw new GatewayError(
      400,
      "unsupported_model",
      "Only qwen3.8-27b is supported",
    );
  if (!Array.isArray(body.messages))
    throw new GatewayError(400, "invalid_request", "messages must be an array");
  if (body.stream !== undefined && typeof body.stream !== "boolean")
    throw new GatewayError(400, "invalid_request", "stream must be a boolean");
  const result = { ...body };
  for (const field of ["max_tokens", "max_completion_tokens"]) {
    const cap = body[field];
    if (cap !== undefined) {
      if (typeof cap !== "number" || !Number.isSafeInteger(cap) || cap < 1)
        throw new GatewayError(
          400,
          "invalid_output_limit",
          `${field} must be a positive integer`,
        );
      result[field] = Math.min(cap, MAX_OUTPUT);
    }
  }
  if (
    body.max_tokens !== undefined &&
    body.max_completion_tokens !== undefined &&
    body.max_tokens !== body.max_completion_tokens
  ) {
    throw new GatewayError(
      400,
      "conflicting_output_limits",
      "Output limits must agree when both are declared",
    );
  }
  if (body.max_tokens === undefined && body.max_completion_tokens === undefined)
    result.max_tokens = MAX_OUTPUT;
  return result;
}

export function createGateway(options: GatewayOptions): Gateway {
  const upstreams = options.upstreams ?? DEFAULT_UPSTREAMS;
  if (
    upstreams.length !== 2 ||
    upstreams.some(
      (item, index) => item.alias !== DEFAULT_UPSTREAMS[index]!.alias,
    )
  )
    throw new Error("Gateway requires the reviewed two Qwen aliases");
  for (const upstream of upstreams) {
    const url = new URL(upstream.url);
    if (
      !["http:", "https:"].includes(url.protocol) ||
      url.username ||
      url.password ||
      url.search ||
      url.hash
    )
      throw new Error("Invalid inference upstream URL");
  }
  const admission = new Admission(
    upstreams,
    positive(options.queueLimit, 128, "queueLimit"),
    positive(options.queueByteLimit, 128 * 1024 * 1024, "queueByteLimit"),
    positive(options.queueTimeoutMs, 30 * 60 * 1000, "queueTimeoutMs"),
    options.initialLaneStates,
    options.onLaneState,
    options.availability,
  );
  const mimo = options.frontier && "provider" in options.frontier ? options.frontier : undefined;
  const glm = options.frontier && !("provider" in options.frontier) ? options.frontier : undefined;
  const frontierModel = mimo ? MIMO_MODEL : options.selectedFrontierModel ?? FRONTIER_MODEL;
  if ((glm && frontierModel !== FRONTIER_MODEL) || (mimo && options.selectedFrontierModel === FRONTIER_MODEL)) throw Error("Frontier selection mismatch");
  // Keep the existing durable GLM key as the one shared frontier slot. Any
  // retained prior provider uncertainty blocks selection across app restarts.
  const previousFrontier = options.initialFrontierOwnerModel !== undefined || [FRONTIER_MODEL, MIMO_MODEL].some(id =>
    ["active", "quarantined"].includes(options.initialLaneStates?.[id] ?? "idle")) ? "quarantined" : "idle";
  const unresolvedProviderChange = previousFrontier !== "idle" && ((options.initialFrontierOwnerModel !== undefined && options.initialFrontierOwnerModel !== frontierModel) || (frontierModel === FRONTIER_MODEL && ["active", "quarantined"].includes(options.initialLaneStates?.[MIMO_MODEL] ?? "idle")));
  const frontierAvailability: AvailabilityProvider =
    options.availability ??
    (() => ({
      state: "unknown",
      reason: "readiness_unknown",
      dispatch: "hold",
    }));
  const frontierAdmission = options.frontier
    ? new Admission(
        [{ url: mimo ? mimoUrl(mimo) : frontierUrl(glm!), alias: frontierModel }],
        8,
        128 * 1024 * 1024,
        positive(
          options.frontier.fixtureQueueTimeoutMs,
          30 * 60 * 1000,
          "frontier queue timeout",
        ),
        { [frontierModel]: previousFrontier },
        (_alias, state) => options.onLaneState?.(FRONTIER_MODEL, state),
        frontierAvailability,
      )
    : undefined;
  // Validate fixture override at construction; select the real model per request.
  activeRequestTimeoutMs("qwen", options.activeTimeoutMs);
  const ownership = new GatewayOwnership(options.ownership);
  const tokens = new Map<string, string>();
  const codexTokens = new Set<string>();
  const frontierCancellations = new Map<string, Set<AbortController>>();
  const active = new Set<ClientRequest>();
  const app = Fastify({
    logger: false,
    bodyLimit: 64 * 1024 * 1024,
    requestTimeout: 0,
    connectionTimeout: 0,
    forceCloseConnections: true,
  });
  const rawBodies = new WeakMap<FastifyRequest, Buffer>();
  if (options.diagnostics?.capture) {
    const parseJson = app.getDefaultJsonParser("error", "error");
    app.removeContentTypeParser("application/json");
    app.addContentTypeParser("application/json", { parseAs: "buffer" }, (request, body, done) => {
      const bytes = body as Buffer;
      if (request.method === "POST" && /\/(responses|chat\/completions)$/.test(request.url)) rawBodies.set(request, Buffer.from(bytes));
      parseJson(request, bytes.toString("utf8"), done);
    });
  }
  app.setErrorHandler((error, _request, reply) => {
    if (error instanceof MimoError)
      return reply.code(error.code === "mimo_context_full" || error.code === "mimo_output_limit" ? 413 : error.code === "mimo_invalid_request" || error.code === "mimo_tool_history" ? 400 : 503).send({ error: { code: error.code, message: "MiMo request or qualification rejected" } });
    if (error instanceof ApiError)
      return reply
        .code(error.statusCode)
        .send({ error: { code: error.code, message: error.message } });
    const known = error instanceof GatewayError;
    const statusCode =
      error && typeof error === "object" && "statusCode" in error
        ? error.statusCode
        : undefined;
    const status = known
      ? error.status
      : typeof statusCode === "number"
        ? statusCode
        : 500;
    reply.code(status).send({
      error: {
        code: known
          ? error.code
          : status === 413
            ? "body_too_large"
            : "invalid_request",
        message: known
          ? error.message
          : status === 413
            ? "Request body is too large"
            : "Request could not be processed",
      },
    });
  });
  app.addHook("onRequest", async (request, reply) => {
    const authorization = request.headers.authorization;
    const token = authorization?.startsWith("Bearer ")
      ? authorization.slice(7)
      : undefined;
    if (!token || !tokens.has(token))
      return reply.code(401).send({
        error: {
          code: "unauthorized",
          message: "Inference authorization required",
        },
      });
    // Codex text settlement cannot prove image job ownership or frontier settlement.
    // Expiry closes creation only. Existing jobs retain broker-enforced exact
    // session/job ownership for reads, cancellation and normal settlement.
    const existingImageRoute =
      (request.method === "GET" && /^\/v1\/image-jobs\/[a-zA-Z0-9_-]+$/.test(request.url)) ||
      (request.method === "POST" && /^\/v1\/image-jobs\/[a-zA-Z0-9_-]+\/cancel$/.test(request.url));
    const qualifiedImageRoute = existingImageRoute ||
      (request.method === "POST" && request.url === "/v1/image-jobs" &&
       (options.codexImageJobsQualified === true || options.imageAcceptance?.(tokens.get(token)!) === true));
    if (codexTokens.has(token) && !qualifiedImageRoute && !["/v1/responses", "/v1/models", "/v1/image-capabilities"].includes(request.url))
      return reply.code(403).send({ error: { code: "codex_route_unqualified", message: "Route unavailable under Codex preview qualification" } });
    // This internal bearer service has no browser API and never grants CORS.
    if (request.headers.origin)
      return reply.code(403).send({
        error: {
          code: "browser_forbidden",
          message: "Browser access is not supported",
        },
      });
  });
  app.setNotFoundHandler((_request, reply) =>
    reply.code(404).send({
      error: {
        code: "unsupported_route",
        message: "Only supported inference routes are available",
      },
    }),
  );
  app.get("/v1/models", async () => ({
    object: "list",
    data: [
      {
        id: MODEL,
        object: "model",
        owned_by: "local",
        availability: admission.lanes.map((lane) => ({
          alias: lane.upstream.alias,
          state: admission.available(lane).state,
          requestState: lane.state,
        })),
      },
    ],
  }));

  const imageBroker = () => {
    if (!options.images)
      throw new ApiError(
        503,
        "image_unavailable",
        "Image broker is not configured",
      );
    return options.images;
  };
  const imageSession = (authorization: string | undefined) => {
    const sessionId = tokens.get(authorization!.slice(7));
    if (!sessionId)
      throw new ApiError(401, "unauthorized", "Session authorization required");
    return sessionId;
  };
  app.get("/v1/image-capabilities", async () => imageBroker().capabilities());
  app.post("/v1/image-jobs", { bodyLimit: 64 * 1024 }, async (request) => ({
    job: await imageBroker().submit(
      imageSession(request.headers.authorization),
      request.body,
    ),
  }));
  app.get("/v1/image-jobs/:jobId", async (request) => ({
    job: imageBroker().get(
      imageSession(request.headers.authorization),
      requireId((request.params as { jobId: string }).jobId),
    ),
  }));
  app.post("/v1/image-jobs/:jobId/cancel", async (request) => {
    if (
      !request.body ||
      typeof request.body !== "object" ||
      Array.isArray(request.body) ||
      Object.keys(request.body).length
    )
      throw new ApiError(400, "invalid_body", "Expected an empty object");
    return {
      job: imageBroker().cancel(
        imageSession(request.headers.authorization),
        requireId((request.params as { jobId: string }).jobId),
      ),
    };
  });

  async function chat(request: FastifyRequest, reply: FastifyReply) {
    const isResponses = request.routeOptions.url?.endsWith("/responses") === true;
    if (isResponses && options.responses?.enabled !== true) throw new ApiError(503,"codex_protocol_disabled","Codex Responses preview is disabled");
    if (isResponses && options.ownership?.recoveryReady !== true) throw new ApiError(503,"codex_ownership_unavailable","Durable session ownership required");
    const token = request.headers.authorization!.slice(7);
    const sessionId = tokens.get(token);
    if (!sessionId) throw new GatewayError(401, "unauthorized", "Inference authorization required");
    const ownedRequest = ownership.begin(sessionId);
    const requestedModel = (request.body as any)?.model;
    const model = typeof requestedModel === "string" && [MODEL, MIMO_MODEL, FRONTIER_MODEL].includes(requestedModel) ? requestedModel : MODEL;
    const capture = (phase: ProviderBoundaryCapture["phase"], bytes: Buffer, lane?: string) => {
      try { options.diagnostics?.capture?.({ requestId: ownedRequest.id, sessionId, model, phase, bytes, lane }); } catch { /* Diagnostics cannot change ownership. */ }
    };
    const diagnosticFailure = (error: unknown, phase: ProviderFailure["phase"]) => {
      // Only validator-owned static codes; no request or exception text.
      const code = error instanceof MimoError || error instanceof ApiError || error instanceof GatewayError ? error.code : "provider_validation_failed";
      try { options.diagnostics?.onFailure?.({ requestId: ownedRequest.id, sessionId, model, phase, code,
        ...(error instanceof MimoError && error.rule ? {rule:error.rule} : {}) }); } catch { /* Best effort. */ }
    };
    if (options.diagnostics?.capture) capture("pre_normalization", rawBodies.get(request) ?? Buffer.from(JSON.stringify(request.body)));
    rawBodies.delete(request);
    let provider: CodexProviderContract | undefined;
    let translated: ReturnType<typeof translateResponses> | undefined;
    let prepared: ReturnType<typeof prepareMimo> | undefined;
    let body: Record<string, any>;
    const frontier = request.routeOptions.url?.startsWith("/frontier/") === true || (isResponses && requestedModel === MIMO_MODEL);
    const selectedAdmission = frontier ? frontierAdmission : admission;
    const frontierAllowed = () => {
      if (options.responses?.frontierQualified === true) return true;
      try { return options.responses?.frontierAcceptance?.(sessionId) === true; } catch { return false; }
    };
    try {
      provider = isResponses ? codexProvider(requestedModel) : undefined;
      if (isResponses && frontier && (!frontierAllowed() || !mimo || provider?.model !== MIMO_MODEL))
        throw new ApiError(503, "codex_frontier_unqualified", "Codex frontier live routing is not qualified");
      if (!selectedAdmission || (frontier && !options.frontier)) throw new ApiError(503, "frontier_unavailable", "Frontier is not qualified");
      if (frontier && (options.dispatchHeld?.("harness") || options.dispatchHeld?.(frontierModel)))
        throw new ApiError(503, "frontier_held", "Frontier dispatch is held");
      translated = isResponses ? translateResponses(request.body, options.responses?.outputLimit, provider) : undefined;
      const input = translated?.body ?? request.body;
      prepared = frontier && mimo ? prepareMimo(input) : undefined;
      if (prepared && prepared.outputTokens > MIMO_PRODUCTION_OUTPUT) throw new ApiError(413, "mimo_output_limit", "MiMo production output ceiling exceeded");
      body = prepared ? prepared.body : frontier ? frontierBody(input) : requestBody(input);
      if (!frontier && options.qwenOutputLimit !== undefined) {
        if (!Number.isSafeInteger(options.qwenOutputLimit) || options.qwenOutputLimit < 1 || options.qwenOutputLimit > MAX_OUTPUT) throw Error("Invalid trusted Qwen output cap");
        body.max_tokens = Math.min(Number(body.max_tokens ?? body.max_completion_tokens ?? MAX_OUTPUT), options.qwenOutputLimit);
        if (body.max_completion_tokens !== undefined) body.max_completion_tokens = body.max_tokens;
      }
    } catch (error) {
      diagnosticFailure(error, "validation");
      ownership.transition(ownedRequest, "settled");
      throw error;
    }
    // The preceding validation proved this owner exists; no inference accepted yet.
    if (!selectedAdmission) throw Error("Validated admission missing");
    const bodyBytes = Buffer.byteLength(JSON.stringify(body));
    const settleLane = (lane: Lane, confirmed: boolean) => {
      const ownerReleased = selectedAdmission.settle(lane, confirmed);
      try { ownership.transition(ownedRequest, confirmed && ownerReleased ? "settled" : "uncertain", lane.upstream.alias); } catch { /* ledger retains uncertainty; callback must never crash transport */ }
    };
    const record: FrontierRecord | undefined = frontier
      ? {
          id: randomBytes(16).toString("hex"),
          sessionId,
          state: "queued",
          model: frontierModel,
          contextWindow: options.frontier!.contextWindow,
          updatedAt: new Date().toISOString(),
        }
      : undefined;
    const recordState = (state: FrontierRecord["state"]) => {
      if (record) {
        record.state = state;
        record.updatedAt = new Date().toISOString();
        options.frontier!.onRequestState({ ...record });
      }
    };
    recordState("queued");
    const cancelled = new AbortController();
    {
      const owned =
        frontierCancellations.get(token) ?? new Set<AbortController>();
      frontierCancellations.set(token, owned);
      owned.add(cancelled);
      reply.raw.once("close", () => {
        owned.delete(cancelled);
        if (!owned.size) frontierCancellations.delete(token);
      });
    }
    let disconnected = false;
    let upstreamResponse: IncomingMessage | undefined;
    const disconnect = () => {
      if (reply.raw.writableEnded) return;
      disconnected = true;
      cancelled.abort();
      // A cancelled consumer is detached. Keep consuming upstream with bounded
      // observation buffers; aborting its socket would not prove GPU settlement.
      if (ownedRequest.state === "accepted") ownership.transition(ownedRequest, "draining");
      upstreamResponse?.resume();
    };
    reply.raw.once("close", disconnect);
    let lane: Lane;
    try {
      const aliases = translated && !frontier ? await options.responses?.currentAliases?.({ requestId: ownedRequest.id, phase: "admission" }) ?? options.responses?.qualifiedAliases : undefined;
      if (aliases && !aliases.length) throw new ApiError(503, "codex_qwen_identity_unqualified", "No currently qualified Qwen lane");
      lane = await selectedAdmission.acquire(cancelled.signal, bodyBytes, aliases);
    } catch (error) {
      ownership.transition(ownedRequest, "settled");
      recordState(cancelled.signal.aborted ? "cancelled" : "rejected");
      reply.raw.removeListener("close", disconnect);
      if (disconnected) return reply;
      if (!frontier && tokens.get(token) !== sessionId) throw new GatewayError(401,"unauthorized","Inference authorization required");
      throw error;
    }
    if (disconnected) {
      settleLane(lane, true);
      recordState("cancelled");
      reply.raw.removeListener("close", disconnect);
      return reply;
    }
    const requireCurrentToken = () => {
      if (tokens.get(token) === sessionId) return;
      // No upstream request exists yet: release this admission safely. Revoking
      // a token never aborts an already dispatched generation or its drain.
      settleLane(lane, true);
      recordState("rejected");
      reply.raw.removeListener("close", disconnect);
      throw new GatewayError(
        401,
        "unauthorized",
        "Inference authorization required",
      );
    };
    requireCurrentToken();
    let key: string;
    try {
      const credential = frontier
        ? options.frontier!.upstreamKey
        : options.upstreamKey;
      key = typeof credential === "function" ? await credential() : credential;
      if (!key || !/^[\x21-\x7e]+$/.test(key))
        throw new Error("Invalid upstream credential");
    } catch {
      settleLane(lane, true);
      recordState("rejected");
      reply.raw.removeListener("close", disconnect);
      throw new GatewayError(
        503,
        "upstream_credential_unavailable",
        "Inference credential is unavailable",
      );
    }
    if (disconnected) {
      settleLane(lane, true);
      recordState("cancelled");
      reply.raw.removeListener("close", disconnect);
      return reply;
    }
    requireCurrentToken();
    // Credential loading may yield. Recheck before the first upstream byte; an
    // unavailable lane never causes replay or migration of already active work.
    if (
      frontier &&
      (options.dispatchHeld?.("harness") ||
        options.dispatchHeld?.(frontierModel))
    ) {
      settleLane(lane, true);
      recordState("rejected");
      reply.raw.removeListener("close", disconnect);
      throw new ApiError(503, "frontier_held", "Frontier dispatch is held");
    }
    while (
      options.dispatchHeld?.(lane.upstream.alias) &&
      !disconnected &&
      !cancelled.signal.aborted
    )
      await new Promise<void>((resolve) => setTimeout(resolve, 50));
    if (disconnected || cancelled.signal.aborted) {
      settleLane(lane, true);
      recordState("cancelled");
      reply.raw.removeListener("close", disconnect);
      return reply;
    }
    requireCurrentToken();
    if (selectedAdmission.available(lane).dispatch !== "allow") {
      settleLane(lane, true);
      recordState("rejected");
      reply.raw.removeListener("close", disconnect);
      throw new GatewayError(
        503,
        "lane_unavailable",
        "Selected inference lane is unavailable",
      );
    }
    if (translated && !frontier) {
      try {
        ownership.transition(ownedRequest, "counting", lane.upstream.alias);
        const finalBody = { ...body, model: lane.upstream.alias };
        const count = await options.responses!.countQwen(finalBody, lane.upstream, key, cancelled.signal, { requestId: ownedRequest.id, phase: "count" });
        if (count.contextWindow !== CODEX_CONTEXT["qwen3.8-27b"] || !Number.isSafeInteger(count.inputTokens) || count.inputTokens < 0)
          throw new ApiError(503,"codex_tokenizer_unqualified","Exact input count is unavailable");
        ownership.account(ownedRequest, { inputTokens: count.inputTokens, reservedOutputTokens: Number(body.max_tokens) });
        emitAdmission(options.responses?.onAdmissionDiagnostic, { schema: 1, requestId: ownedRequest.id, phase: "count", lane: lane.upstream.alias, step: "capacity", outcome: count.inputTokens + Number(body.max_tokens) > count.contextWindow ? "reject" : "pass", reason: count.inputTokens + Number(body.max_tokens) > count.contextWindow ? "token_capacity" : "ok", elapsedMs: 0 });
        if (count.inputTokens + Number(body.max_tokens) > count.contextWindow)
          throw new ApiError(413,"codex_context_full","Input plus reserved output exceeds model context");
        if (cancelled.signal.aborted || tokens.get(token) !== sessionId) throw new ApiError(499,"cancelled","Request cancelled before dispatch");
        if (selectedAdmission.available(lane).dispatch !== "allow") throw new ApiError(503,"lane_unavailable","Lane unavailable after count");
      } catch (error) { diagnosticFailure(error, "counting"); settleLane(lane,true); reply.raw.removeListener("close",disconnect); if (cancelled.signal.aborted) throw new ApiError(499,"cancelled","Request cancelled before dispatch"); throw error; }
    }
    let mimoAdmission: MimoAdmission | undefined;
    let mimoPayload: string | undefined;
    let requestMimo: Awaited<ReturnType<NonNullable<MimoFrontierOptions["current"]>>> | undefined;
    if (frontier) {
      try {
        if (isResponses && !frontierAllowed()) throw new ApiError(503, "codex_frontier_unqualified", "Owned frontier acceptance expired");
        if (mimo && prepared) {
          ownership.transition(ownedRequest, "counting", lane.upstream.alias);
          if (provider && (provider.contextWindow !== mimo.contextWindow || provider.maxOutputTokens !== MIMO_PRODUCTION_OUTPUT))
            throw new ApiError(503, "codex_frontier_unqualified", "MiMo provider capacity is not qualified");
          requestMimo = mimo.current ? await mimo.current(cancelled.signal) : { qualification: mimo.qualification, observe: mimo.observe };
          mimoAdmission = await countMimo(prepared, requestMimo.qualification, {
            observe: requestMimo.observe,
            post: (r) => fetch(`${mimoUrl(mimo).replace(/\/v1$/, "")}${r.path}`, {
              method: r.method, redirect: "error", headers: { authorization: `Bearer ${key}`, "content-type": "application/json" }, body: r.body, signal: r.signal,
            }),
          }, cancelled.signal);
          ownership.account(ownedRequest, { inputTokens: mimoAdmission.promptTokens, reservedOutputTokens: prepared.outputTokens });
          const observed = await requestMimo.observe(cancelled.signal);
          mimoPayload = mimoGenerationRequest(mimoAdmission, observed).body;
          Object.assign(record!, { promptTokens: mimoAdmission.promptTokens, reservedOutput: prepared.outputTokens,
            canonicalRequestSha256: prepared.sha256, qualificationEvidenceSha256: requestMimo.qualification.evidenceSha256,
            serverInstance: observed.serverInstance, serverGeneration: observed.serverGeneration });
        } else {
          const counted = await countFrontier(glm!, body, key, cancelled.signal);
          Object.assign(record!, counted);
        }
        if (cancelled.signal.aborted)
          throw new ApiError(499, "cancelled", "Request cancelled");
        // This catch owns the single release. Do not call requireCurrentToken,
        // which releases before throwing and could free the next queued owner.
        if (tokens.get(token) !== sessionId)
          throw new ApiError(
            401,
            "unauthorized",
            "Inference authorization required",
          );
        if (
          options.dispatchHeld?.("harness") ||
          options.dispatchHeld?.(frontierModel)
        )
          throw new ApiError(503, "frontier_held", "Frontier dispatch is held");
        if (selectedAdmission.available(lane).dispatch !== "allow")
          throw new ApiError(
            503,
            "lane_unavailable",
            "Frontier backend is unavailable",
          );
        if (isResponses && !frontierAllowed()) throw new ApiError(503, "codex_frontier_unqualified", "Owned frontier acceptance expired");
        recordState("active");
      } catch (error) {
        diagnosticFailure(error, "counting");
        settleLane(lane, true);
        reply.raw.removeListener("close", disconnect);
        recordState(cancelled.signal.aborted ? "cancelled" : "rejected");
        throw error;
      }
    }
    ownership.transition(ownedRequest, "accepted", lane.upstream.alias);
    lane.dispatched = true;
    lane.ownerSettled = false;
    const payload = mimoPayload ?? JSON.stringify({ ...body, model: lane.upstream.alias });
    if (options.diagnostics?.capture) capture("normalized_request", Buffer.from(payload), lane.upstream.alias);
    const endpoint = new URL(
      `${lane.upstream.url.replace(/\/$/, "")}/chat/completions`,
    );
    const observe = new UsageObserver(
      body.stream === true,
      (value: unknown) => {
        if (!value || typeof value !== "object") return;
        const usage = (value as { usage?: unknown }).usage;
        if (!usage || typeof usage !== "object") return;
        const {
          prompt_tokens: promptTokens,
          completion_tokens: completionTokens,
        } = usage as Record<string, unknown>;
        if (
          typeof promptTokens !== "number" ||
          !Number.isSafeInteger(promptTokens) ||
          promptTokens < 0
        )
          return;
        // This is one request's input occupancy, never a sum. A runner can issue
        // child/compression requests: callers must keep that attribution uncertain.
        try {
          if (!frontier) ownership.account(ownedRequest, { promptTokens,
            ...(Number.isSafeInteger(completionTokens) && Number(completionTokens) >= 0 ? {completionTokens:Number(completionTokens)} : {}) });
          if (!frontier)
            options.onUsage?.({
              sessionId,
              promptTokens,
              ...(typeof completionTokens === "number" &&
              Number.isSafeInteger(completionTokens) &&
              completionTokens >= 0
                ? { completionTokens }
                : {}),
              source:
                "gateway.latest-request.prompt_tokens (main/child/compaction attribution unknown)",
            });
        } catch {
          /* A telemetry consumer must not alter inference transport. */
        }
      },
    );
    let bridgeInvalid = false;
    const bridge = translated ? new ResponsesStream(translated, data => {
      if (options.diagnostics?.capture) capture("responses_sse", Buffer.from(data), lane.upstream.alias);
      if (!disconnected && !reply.raw.destroyed) reply.raw.write(data);
    }, diagnostic => {
      try { options.responses?.onDiagnostic?.({requestId:ownedRequest.id,sessionId,lane:lane.upstream.alias,diagnostic}); } catch { /* Observer never owns settlement. */ }
    }) : undefined;
    reply.hijack();
    await new Promise<void>((resolve) => {
      let settled = false;
      let timeout: NodeJS.Timeout | undefined;
      let mimoValidator: MimoStreamValidator | undefined;
      const mimoChunks: Buffer[] = [];
      const settlementAbort = new AbortController();
      const settle = (confirmed: boolean) => {
        if (settled) return;
        settled = true;
        clearTimeout(timeout);
        settlementAbort.abort();
        active.delete(upstream);
        settleLane(lane, confirmed);
        try {
          recordState(confirmed ? "settled" : "quarantined");
        } catch {
          /* durable active remains unsafe */
        }
        reply.raw.removeListener("close", disconnect);
        resolve();
      };
      const fail = (code: string, message: string) => {
        if (settled) return;
        if (!disconnected && !reply.raw.destroyed) {
          if (!reply.raw.headersSent)
            sendRawError(
              reply,
              code === "active_timeout" ? 504 : 502,
              code,
              message,
            );
          else reply.raw.destroy();
        }
        settle(false);
      };
      const transport =
        endpoint.protocol === "https:" ? httpsRequest : httpRequest;
      const upstream = transport(
        endpoint,
        {
          method: "POST",
          agent: false,
          headers: {
            "content-type": "application/json",
            "content-length": Buffer.byteLength(payload),
            authorization: `Bearer ${key}`,
            accept:
              body.stream === true ? "text/event-stream" : "application/json",
          },
        },
        (response) => {
          if (settled) {
            response.resume();
            return;
          }
          upstreamResponse = response;
          if (mimoAdmission) {
            try { mimoValidator = new MimoStreamValidator(mimoAdmission, { status: response.statusCode ?? 502, contentType: String(response.headers["content-type"] ?? "") }); }
            catch { response.resume(); fail("mimo_stream_invalid", "MiMo stream rejected; owner requires settlement review"); return; }
          }
          if (!disconnected && !mimoValidator) {
            reply.raw.statusCode = response.statusCode ?? 502;
            for (const header of [
              "content-type",
              "content-encoding",
              "cache-control",
              "x-request-id",
            ]) {
              if (bridge && header === "content-encoding") continue;
              const value = response.headers[header];
              if (value !== undefined) reply.raw.setHeader(header, value);
            }
            reply.raw.setHeader("x-accel-buffering", "no");
          }
          const bridgeSuccess = bridge && response.statusCode === 200;
          if (bridgeSuccess && !disconnected) reply.raw.setHeader("content-type", "text/event-stream");
          response.on("data", (chunk: Buffer) => {
            if (settled) return;
            if (options.diagnostics?.capture) capture("provider_sse", Buffer.from(chunk), lane.upstream.alias);
            if (bridgeSuccess) try { options.responses?.onTrace?.({requestId:ownedRequest.id,sessionId,lane:lane.upstream.alias,chunk:Buffer.from(chunk)}); } catch { /* private capture */ }
            if (mimoValidator) {
              try { mimoValidator.push(chunk); if (!disconnected) mimoChunks.push(Buffer.from(chunk)); }
              catch { mimoChunks.length = 0; fail("mimo_stream_invalid", "MiMo stream rejected; owner requires settlement review"); }
              return;
            }
            observe.data(chunk);
            if (bridgeSuccess) {
              if (!bridgeInvalid) try { bridge.push(chunk); } catch (error) {
                try { options.responses?.onError?.({requestId:ownedRequest.id,sessionId,lane:lane.upstream.alias,phase:'stream',code:responsesFailureCode(error)}); } catch { /* diagnostics never affect ownership */ }
                bridgeInvalid = true;
                // Client format failure is not native/GPU failure: keep draining
                // and observing Chat terminal evidence under the existing permit.
                if (!disconnected && !reply.raw.destroyed) {
                  if (!reply.raw.headersSent) sendRawError(reply,502,"responses_stream_invalid","Unqualified Responses output contract");
                  else reply.raw.destroy();
                }
                disconnected = true;
                cancelled.abort();
                try { ownership.transition(ownedRequest,"draining"); } catch { /* retain failed ledger */ }
                response.resume();
              }
              return;
            }
            if (!disconnected && !reply.raw.destroyed) {
              if (!reply.raw.write(chunk)) {
                response.pause();
                reply.raw.once("drain", () => response.resume());
              }
            }
          });
          response.once("end", async () => {
            if (settled) return;
            if (mimoValidator && mimo) {
              try {
                const observed = await requestMimo!.observe(settlementAbort.signal);
                if (settled) return;
                const result = mimoValidator.finish(response.complete, observed);
                record!.backendResponseId = result.responseId;
                recordState("active");
                if (mimo.serialCompletionQualified !== true) throw Error("Serial native completion unqualified");
                // Hold tool fragments until full SSE/HTTP validation under the qualified serial runtime.
                // A detached consumer never interrupts this bounded upstream drain.
                // Native serial completion is proven before any tool completion
                // reaches the client. Converter failure cannot un-settle GPU work.
                settle(true);
                if (!disconnected && !reply.raw.destroyed) {
                  reply.raw.statusCode = 200;
                  reply.raw.setHeader("content-type", "text/event-stream");
                  if (bridge) {
                    try { for (const chunk of mimoChunks) bridge.push(chunk); bridge.end(); reply.raw.end(); }
                    catch (error) {
                      try { options.responses?.onError?.({requestId:ownedRequest.id,sessionId,lane:lane.upstream.alias,phase:'terminal',code:responsesFailureCode(error)}); } catch { /* Diagnostics only. */ }
                      if (!reply.raw.headersSent) sendRawError(reply,502,"responses_stream_invalid","Unqualified Responses output contract");
                      else reply.raw.destroy();
                    }
                  } else reply.raw.end(Buffer.concat(mimoChunks));
                }
              } catch { fail("mimo_settlement_unconfirmed", "MiMo owner requires settlement review"); }
              return;
            }
            observe.end();
            const status = response.statusCode ?? 502;
            const rejectedBeforeGeneration = [
              400, 401, 403, 404, 405, 413, 415, 422, 429,
            ].includes(status);
            const success = status >= 200 && status < 300;
            // For SSE success, an early EOF without [DONE] is ambiguous. Even if
            // content was emitted, no retry and no automatic lane recovery occurs.
            // A proxy 5xx/timeout also cannot prove that its backend GPU is idle.
            const confirmed =
              response.complete &&
              (rejectedBeforeGeneration ||
                (success && (body.stream !== true || observe.terminal)));
            // Release the proven native inference owner before exposing tool
            // completions: parents cannot retain a GPU permit while tools run.
            settle(confirmed);
            if (bridgeSuccess && !bridgeInvalid) { try { bridge.end(); } catch (error) {
              try { options.responses?.onError?.({requestId:ownedRequest.id,sessionId,lane:lane.upstream.alias,phase:'terminal',code:responsesFailureCode(error)}); } catch { /* diagnostics never affect ownership */ }
              bridgeInvalid = true;
              if (!disconnected && !reply.raw.destroyed) {
                if (!reply.raw.headersSent) sendRawError(reply,502,"responses_stream_invalid","Responses stream truncated or missing usage"); else reply.raw.destroy();
              }
              disconnected = true;
            } }
            if (!disconnected && !reply.raw.destroyed) reply.raw.end();
          });
          response.once("error", () =>
            fail("upstream_interrupted", "Inference transport was interrupted"),
          );
          response.once("aborted", () =>
            fail("upstream_interrupted", "Inference transport was interrupted"),
          );
        },
      );
      active.add(upstream);
      upstream.once("error", () =>
        fail("upstream_interrupted", "Inference transport was interrupted"),
      );
      timeout = setTimeout(() => {
        fail(
          "active_timeout",
          "Active generation exceeded its limit; lane requires settlement review",
        );
        upstream.destroy();
        upstreamResponse?.destroy();
      }, activeRequestTimeoutMs(frontier && mimo ? MIMO_MODEL : "qwen-or-glm", options.activeTimeoutMs));
      timeout.unref();
      upstream.end(payload);
    });
    return reply;
  }
  app.post("/v1/responses", chat);
  app.post("/frontier/v1/responses", chat);
  app.post("/v1/chat/completions", chat);
  app.post("/frontier/v1/chat/completions", chat);
  app.addHook("preClose", async () => {
    admission.stop();
    frontierAdmission?.stop();
    tokens.clear();
    codexTokens.clear();
    for (const request of active) request.destroy();
  });
  return {
    app,
    issueToken(sessionId, scope = "minimax") {
      if (!sessionId) throw new Error("sessionId is required");
      const token = randomBytes(32).toString("base64url");
      ownership.registerSession(sessionId);
      tokens.set(token, sessionId);
      if (scope === "codex") codexTokens.add(token);
      return token;
    },
    revokeToken(token) {
      tokens.delete(token);
      codexTokens.delete(token);
      // Frontier queued/counting work cancels immediately. Dispatched generation
      // is not wired to this signal and retains its drain/settlement ownership.
      for (const controller of frontierCancellations.get(token) ?? [])
        controller.abort();
    },
    revokeSession(sessionId) {
      for (const [token, owner] of tokens) if (owner === sessionId) {
        tokens.delete(token);
      codexTokens.delete(token);
        for (const controller of frontierCancellations.get(token) ?? []) controller.abort();
      }
    },
    confirmSettlement: async (query, waitMs = 0) => ownership.waitForSettlement(query, waitMs),
    observeSettlement: (query, stop) => ownership.waitForSettlement(query, stop),
    sessionWork: (sessionId) => ownership.snapshot(sessionId),
    snapshot: () => ({
      queued: admission.queued,
      queuedBytes: admission.queuedBytes,
      lanes: admission.lanes.map((lane) => ({
        alias: lane.upstream.alias,
        state: lane.state,
        availability: admission.available(lane),
      })),
    }),
    frontierSnapshot: () => ({
      model: frontierModel,
      provider: frontierModel === MIMO_MODEL ? "mimo" : "glm",
      maxOutputTokens: mimo ? Math.min(MIMO_PRODUCTION_OUTPUT, mimo.qualification.identity.maxOutputTokens) : glm ? 65536 : null,
      capacity: mimo ? mimo.capacity : { published: 1048576, configured: glm?.contextWindow ?? null, allocated: null, occupiedTested: null },
      configured: !!options.frontier,
      contextWindow: options.frontier?.contextWindow ?? null,
      queued: frontierAdmission?.queued ?? 0,
      state: frontierAdmission?.lanes[0]?.state ?? "unavailable",
      availability: serviceAvailability(frontierAvailability, frontierModel),
    }),
    reconcileAfterOwnerSettlement: (aliases) => {
      const qwen = admission.reconcileAfterOwnerSettlement(aliases);
      // Only an exact owner-settlement alias may release frontier uncertainty.
      // Normal MiMo serial completion is handled above. Generic administration
      // cannot clear ambiguity or authorize a physical model switch.
      if (frontierModel === MIMO_MODEL || unresolvedProviderChange) return qwen && !aliases.some(a => a === MIMO_MODEL || a === FRONTIER_MODEL);
      const frontier = aliases.includes(FRONTIER_MODEL)
        ? (frontierAdmission?.reconcileAfterOwnerSettlement([FRONTIER_MODEL]) ??
          true)
        : true;
      return qwen && frontier;
    },
    notifyAvailabilityChanged: () => {
      admission.notifyAvailabilityChanged();
      frontierAdmission?.notifyAvailabilityChanged();
    },
    close: () => app.close(),
  };
}

function sendRawError(
  reply: FastifyReply,
  status: number,
  code: string,
  message: string,
) {
  reply.raw.statusCode = status;
  reply.raw.setHeader("content-type", "application/json");
  reply.raw.end(JSON.stringify({ error: { code, message } }));
}
