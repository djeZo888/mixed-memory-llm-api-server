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

export interface GatewayUpstream {
  url: string;
  alias: string;
}
export interface GatewayOptions {
  frontier?: FrontierOptions;
  images?: ImageBroker;
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
  issueToken(sessionId: string): string;
  revokeToken(token: string): void;
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
  private eligible(lane: Lane) {
    return (
      lane.state !== "quarantined" && this.available(lane).dispatch === "allow"
    );
  }
  private blocked(): GatewayError | undefined {
    if (
      this.lanes.some(
        (lane) =>
          lane.state !== "quarantined" &&
          this.available(lane).dispatch !== "reject",
      )
    )
      return;
    return this.lanes.some(
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
  acquire(signal: AbortSignal, bytes: number): Promise<Lane> {
    if (this.stopped)
      return Promise.reject(
        new GatewayError(503, "gateway_stopping", "Gateway is stopping"),
      );
    if (signal.aborted)
      return Promise.reject(
        new GatewayError(499, "cancelled", "Request cancelled"),
      );
    const lane = this.lanes.find(
      (candidate) => candidate.state === "idle" && this.eligible(candidate),
    );
    if (lane && !this.queue.length) {
      try {
        this.transition(lane, "active");
        return Promise.resolve(lane);
      } catch (error) {
        return Promise.reject(error);
      }
    }
    const blocked = this.blocked();
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
        bytes,
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
    this.notifyAvailabilityChanged();
  }
  notifyAvailabilityChanged() {
    if (this.stopped) return;
    while (this.queue.length) {
      const available = this.lanes.find(
        (candidate) => candidate.state === "idle" && this.eligible(candidate),
      );
      if (!available) break;
      const ticket = this.queue[0]!;
      this.remove(ticket);
      if (ticket.signal.aborted) {
        ticket.reject(new GatewayError(499, "cancelled", "Request cancelled"));
        continue;
      }
      try {
        this.transition(available, "active");
        ticket.resolve(available);
      } catch (error) {
        ticket.reject(error as Error);
      }
    }
    const blocked = this.blocked();
    if (blocked) this.rejectQueued(blocked.code, blocked.message);
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
  const frontierAvailability: AvailabilityProvider =
    options.availability ??
    (() => ({
      state: "unknown",
      reason: "readiness_unknown",
      dispatch: "hold",
    }));
  const frontierAdmission = options.frontier
    ? new Admission(
        [{ url: frontierUrl(options.frontier), alias: FRONTIER_MODEL }],
        8,
        128 * 1024 * 1024,
        positive(
          options.frontier.fixtureQueueTimeoutMs,
          30 * 60 * 1000,
          "frontier queue timeout",
        ),
        options.initialLaneStates,
        options.onLaneState,
        frontierAvailability,
      )
    : undefined;
  const activeTimeout = positive(
    options.activeTimeoutMs,
    2 * 60 * 60 * 1000,
    "activeTimeoutMs",
  );
  const tokens = new Map<string, string>();
  const frontierCancellations = new Map<string, Set<AbortController>>();
  const active = new Set<ClientRequest>();
  const app = Fastify({
    logger: false,
    bodyLimit: 64 * 1024 * 1024,
    requestTimeout: 0,
    connectionTimeout: 0,
    forceCloseConnections: true,
  });
  app.setErrorHandler((error, _request, reply) => {
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
    const frontier =
      request.routeOptions.url === "/frontier/v1/chat/completions";
    const selectedAdmission = frontier ? frontierAdmission : admission;
    if (!selectedAdmission || (frontier && !options.frontier))
      throw new ApiError(
        503,
        "frontier_unavailable",
        "Frontier is not qualified",
      );
    if (
      frontier &&
      (options.dispatchHeld?.("harness") ||
        options.dispatchHeld?.(FRONTIER_MODEL))
    )
      throw new ApiError(503, "frontier_held", "Frontier dispatch is held");
    const body = frontier
      ? frontierBody(request.body)
      : requestBody(request.body);
    const bodyBytes = Buffer.byteLength(JSON.stringify(body));
    const token = request.headers.authorization!.slice(7);
    const sessionId = tokens.get(token);
    if (!sessionId)
      throw new GatewayError(
        401,
        "unauthorized",
        "Inference authorization required",
      );
    const record: FrontierRecord | undefined = frontier
      ? {
          id: randomBytes(16).toString("hex"),
          sessionId,
          state: "queued",
          model: FRONTIER_MODEL,
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
    if (frontier) {
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
      upstreamResponse?.resume();
    };
    reply.raw.once("close", disconnect);
    let lane: Lane;
    try {
      lane = await selectedAdmission.acquire(cancelled.signal, bodyBytes);
    } catch (error) {
      recordState(cancelled.signal.aborted ? "cancelled" : "rejected");
      reply.raw.removeListener("close", disconnect);
      if (disconnected) return reply;
      throw error;
    }
    if (disconnected) {
      selectedAdmission.settle(lane, true);
      recordState("cancelled");
      reply.raw.removeListener("close", disconnect);
      return reply;
    }
    const requireCurrentToken = () => {
      if (tokens.get(token) === sessionId) return;
      // No upstream request exists yet: release this admission safely. Revoking
      // a token never aborts an already dispatched generation or its drain.
      selectedAdmission.settle(lane, true);
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
      selectedAdmission.settle(lane, true);
      recordState("rejected");
      reply.raw.removeListener("close", disconnect);
      throw new GatewayError(
        503,
        "upstream_credential_unavailable",
        "Inference credential is unavailable",
      );
    }
    if (disconnected) {
      selectedAdmission.settle(lane, true);
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
        options.dispatchHeld?.(FRONTIER_MODEL))
    ) {
      selectedAdmission.settle(lane, true);
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
      selectedAdmission.settle(lane, true);
      recordState("cancelled");
      reply.raw.removeListener("close", disconnect);
      return reply;
    }
    requireCurrentToken();
    if (selectedAdmission.available(lane).dispatch !== "allow") {
      selectedAdmission.settle(lane, true);
      recordState("rejected");
      reply.raw.removeListener("close", disconnect);
      throw new GatewayError(
        503,
        "lane_unavailable",
        "Selected inference lane is unavailable",
      );
    }
    if (frontier) {
      try {
        const counted = await countFrontier(
          options.frontier!,
          body,
          key,
          cancelled.signal,
        );
        Object.assign(record!, counted);
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
          options.dispatchHeld?.(FRONTIER_MODEL)
        )
          throw new ApiError(503, "frontier_held", "Frontier dispatch is held");
        if (selectedAdmission.available(lane).dispatch !== "allow")
          throw new ApiError(
            503,
            "lane_unavailable",
            "Frontier backend is unavailable",
          );
        recordState("active");
      } catch (error) {
        selectedAdmission.settle(lane, true);
        reply.raw.removeListener("close", disconnect);
        recordState(cancelled.signal.aborted ? "cancelled" : "rejected");
        throw error;
      }
    }
    lane.dispatched = true;
    lane.ownerSettled = false;
    const payload = JSON.stringify({ ...body, model: lane.upstream.alias });
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
    reply.hijack();
    await new Promise<void>((resolve) => {
      let settled = false;
      let timeout: NodeJS.Timeout | undefined;
      const settle = (confirmed: boolean) => {
        if (settled) return;
        settled = true;
        clearTimeout(timeout);
        active.delete(upstream);
        selectedAdmission.settle(lane, confirmed);
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
          if (!disconnected) {
            reply.raw.statusCode = response.statusCode ?? 502;
            for (const header of [
              "content-type",
              "content-encoding",
              "cache-control",
              "x-request-id",
            ]) {
              const value = response.headers[header];
              if (value !== undefined) reply.raw.setHeader(header, value);
            }
            reply.raw.setHeader("x-accel-buffering", "no");
          }
          response.on("data", (chunk: Buffer) => {
            if (settled) return;
            observe.data(chunk);
            if (!disconnected && !reply.raw.destroyed) {
              if (!reply.raw.write(chunk)) {
                response.pause();
                reply.raw.once("drain", () => response.resume());
              }
            }
          });
          response.once("end", () => {
            if (settled) return;
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
            if (!disconnected && !reply.raw.destroyed) reply.raw.end();
            settle(confirmed);
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
      }, activeTimeout);
      timeout.unref();
      upstream.end(payload);
    });
    return reply;
  }
  app.post("/v1/chat/completions", chat);
  app.post("/frontier/v1/chat/completions", chat);
  app.addHook("preClose", async () => {
    admission.stop();
    frontierAdmission?.stop();
    tokens.clear();
    for (const request of active) request.destroy();
  });
  return {
    app,
    issueToken(sessionId) {
      if (!sessionId) throw new Error("sessionId is required");
      const token = randomBytes(32).toString("base64url");
      tokens.set(token, sessionId);
      return token;
    },
    revokeToken(token) {
      tokens.delete(token);
      // Frontier queued/counting work cancels immediately. Dispatched generation
      // is not wired to this signal and retains its drain/settlement ownership.
      for (const controller of frontierCancellations.get(token) ?? [])
        controller.abort();
    },
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
      model: FRONTIER_MODEL,
      configured: !!options.frontier,
      contextWindow: options.frontier?.contextWindow ?? null,
      queued: frontierAdmission?.queued ?? 0,
      state: frontierAdmission?.lanes[0]?.state ?? "unavailable",
      availability: serviceAvailability(frontierAvailability, FRONTIER_MODEL),
    }),
    reconcileAfterOwnerSettlement: (aliases) => {
      const qwen = admission.reconcileAfterOwnerSettlement(aliases);
      // Only an exact owner-settlement alias may release frontier uncertainty.
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
