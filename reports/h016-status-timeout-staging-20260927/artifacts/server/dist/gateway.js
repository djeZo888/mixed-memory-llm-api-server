import { MIMO_MODEL, prepareMimo, countMimo, mimoGenerationRequest, MimoStreamValidator, MimoError } from "./mimo.js";
import { mimoUrl, MIMO_PRODUCTION_OUTPUT } from "./mimo-frontier.js";
import { FRONTIER_MODEL, frontierUrl, frontierBody, countFrontier, } from "./frontier.js";
import { serviceAvailability, } from "./service-availability.js";
import { ApiError, requireId } from "./errors.js";
import Fastify from "fastify";
import { randomBytes } from "node:crypto";
import { request as httpRequest, } from "node:http";
import { request as httpsRequest } from "node:https";
import { MAX_OUTPUT, MODEL } from "./contracts.js";
/** Per-dispatched-request elapsed budget; queue/count retain their own limits. */
export function activeRequestTimeoutMs(model, override) {
    return positive(override, (model === "mimo-v2.6-pro-rl" ? 8 : 2) * 60 * 60 * 1000, "activeTimeoutMs");
}
const DEFAULT_UPSTREAMS = [
    { url: "http://10.156.100.60:30002/v1", alias: "qwen3.8-27b-gpu0" },
    { url: "http://10.156.100.60:30004/v1", alias: "qwen3.8-27b" },
];
const OBSERVATION_LIMIT = 256 * 1024;
class GatewayError extends Error {
    status;
    code;
    constructor(status, code, message) {
        super(message);
        this.status = status;
        this.code = code;
    }
}
/** One shared FIFO for every request, including native children and compaction. */
class Admission {
    limit;
    byteLimit;
    timeout;
    onState;
    availability;
    lanes;
    queue = [];
    queueBytes = 0;
    stopped = false;
    constructor(upstreams, limit, byteLimit, timeout, initial = {}, onState, availability) {
        this.limit = limit;
        this.byteLimit = byteLimit;
        this.timeout = timeout;
        this.onState = onState;
        this.availability = availability;
        this.lanes = upstreams.map((upstream) => {
            const previous = initial[upstream.alias];
            if (previous !== undefined &&
                !["idle", "active", "quarantined"].includes(previous))
                throw new Error("Invalid persisted lane state");
            const lane = {
                upstream,
                state: previous && previous !== "idle" ? "quarantined" : "idle",
            };
            this.onState?.(upstream.alias, lane.state);
            return lane;
        });
    }
    transition(lane, state) {
        try {
            this.onState?.(lane.upstream.alias, state);
        }
        catch {
            lane.state = "quarantined";
            // A failed active write occurs before dispatch. A failed settlement write
            // leaves the previous durable active record, which recovers quarantined.
            throw new GatewayError(503, "lane_ledger_unavailable", "Inference lane ledger is unavailable");
        }
        lane.state = state;
        if (state === "active") {
            lane.dispatched = false;
            lane.ownerSettled = false;
        }
    }
    reconcileAfterOwnerSettlement(aliases) {
        const lanes = this.lanes.filter((lane) => aliases.includes(lane.upstream.alias));
        for (const lane of lanes) {
            if (lane.state === "quarantined")
                this.transition(lane, "idle");
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
    available(lane) {
        return serviceAvailability(this.availability, lane.upstream.alias);
    }
    eligible(lane) {
        return (lane.state !== "quarantined" && this.available(lane).dispatch === "allow");
    }
    blocked() {
        if (this.lanes.some((lane) => lane.state !== "quarantined" &&
            this.available(lane).dispatch !== "reject"))
            return;
        return this.lanes.some((lane) => this.available(lane).state === "unavailable")
            ? new GatewayError(503, "lanes_unavailable", "No Qwen lane is currently available")
            : new GatewayError(503, "lanes_quarantined", "Inference lanes require settlement review");
    }
    acquire(signal, bytes) {
        if (this.stopped)
            return Promise.reject(new GatewayError(503, "gateway_stopping", "Gateway is stopping"));
        if (signal.aborted)
            return Promise.reject(new GatewayError(499, "cancelled", "Request cancelled"));
        const lane = this.lanes.find((candidate) => candidate.state === "idle" && this.eligible(candidate));
        if (lane && !this.queue.length) {
            try {
                this.transition(lane, "active");
                return Promise.resolve(lane);
            }
            catch (error) {
                return Promise.reject(error);
            }
        }
        const blocked = this.blocked();
        if (blocked)
            return Promise.reject(blocked);
        if (this.queue.length >= this.limit)
            return Promise.reject(new GatewayError(429, "queue_full", "Inference queue is full"));
        if (bytes > this.byteLimit - this.queueBytes)
            return Promise.reject(new GatewayError(429, "queue_bytes_full", "Inference queue body budget is full"));
        return new Promise((resolve, reject) => {
            const ticket = {
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
                reject(new GatewayError(504, "queue_timeout", "Inference queue wait exceeded its limit"));
            }, this.timeout);
            ticket.timer.unref();
            signal.addEventListener("abort", ticket.abort, { once: true });
            this.queue.push(ticket);
            this.queueBytes += bytes;
        });
    }
    remove(ticket) {
        const index = this.queue.indexOf(ticket);
        if (index !== -1) {
            this.queue.splice(index, 1);
            this.queueBytes -= ticket.bytes;
        }
        clearTimeout(ticket.timer);
        ticket.signal.removeEventListener("abort", ticket.abort);
    }
    settle(lane, confirmed) {
        try {
            this.transition(lane, (confirmed || lane.ownerSettled) && !this.stopped
                ? "idle"
                : "quarantined");
        }
        catch {
            /* Fail closed locally; previous durable active remains unsafe. */
        }
        this.notifyAvailabilityChanged();
    }
    notifyAvailabilityChanged() {
        if (this.stopped)
            return;
        while (this.queue.length) {
            const available = this.lanes.find((candidate) => candidate.state === "idle" && this.eligible(candidate));
            if (!available)
                break;
            const ticket = this.queue[0];
            this.remove(ticket);
            if (ticket.signal.aborted) {
                ticket.reject(new GatewayError(499, "cancelled", "Request cancelled"));
                continue;
            }
            try {
                this.transition(available, "active");
                ticket.resolve(available);
            }
            catch (error) {
                ticket.reject(error);
            }
        }
        const blocked = this.blocked();
        if (blocked)
            this.rejectQueued(blocked.code, blocked.message);
    }
    rejectQueued(code, message) {
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
    stream;
    emit;
    buffered = "";
    bytes = 0;
    overflow = false;
    terminal = false;
    constructor(stream, emit) {
        this.stream = stream;
        this.emit = emit;
    }
    data(chunk) {
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
                if (!this.overflow)
                    this.line(this.buffered.trim());
                this.buffered = "";
                this.overflow = false;
            }
        }
    }
    line(line) {
        if (!line.startsWith("data:"))
            return;
        const value = line.slice(5).trim();
        if (value === "[DONE]") {
            this.terminal = true;
            return;
        }
        try {
            this.emit(JSON.parse(value));
        }
        catch {
            /* A malformed observation never alters the stream. */
        }
    }
    end() {
        if (this.stream) {
            if (!this.overflow && this.buffered)
                this.line(this.buffered.trim());
            return;
        }
        if (!this.overflow) {
            try {
                this.emit(JSON.parse(this.buffered));
            }
            catch {
                /* Usage unavailable. */
            }
        }
    }
}
function positive(value, fallback, name) {
    const result = value ?? fallback;
    if (!Number.isSafeInteger(result) || result < 1)
        throw new Error(`${name} must be a positive integer`);
    return result;
}
function requestBody(value) {
    if (!value || typeof value !== "object" || Array.isArray(value))
        throw new GatewayError(400, "invalid_request", "Expected a JSON object");
    const body = value;
    if (body.model !== MODEL)
        throw new GatewayError(400, "unsupported_model", "Only qwen3.8-27b is supported");
    if (!Array.isArray(body.messages))
        throw new GatewayError(400, "invalid_request", "messages must be an array");
    if (body.stream !== undefined && typeof body.stream !== "boolean")
        throw new GatewayError(400, "invalid_request", "stream must be a boolean");
    const result = { ...body };
    for (const field of ["max_tokens", "max_completion_tokens"]) {
        const cap = body[field];
        if (cap !== undefined) {
            if (typeof cap !== "number" || !Number.isSafeInteger(cap) || cap < 1)
                throw new GatewayError(400, "invalid_output_limit", `${field} must be a positive integer`);
            result[field] = Math.min(cap, MAX_OUTPUT);
        }
    }
    if (body.max_tokens !== undefined &&
        body.max_completion_tokens !== undefined &&
        body.max_tokens !== body.max_completion_tokens) {
        throw new GatewayError(400, "conflicting_output_limits", "Output limits must agree when both are declared");
    }
    if (body.max_tokens === undefined && body.max_completion_tokens === undefined)
        result.max_tokens = MAX_OUTPUT;
    return result;
}
export function createGateway(options) {
    const upstreams = options.upstreams ?? DEFAULT_UPSTREAMS;
    if (upstreams.length !== 2 ||
        upstreams.some((item, index) => item.alias !== DEFAULT_UPSTREAMS[index].alias))
        throw new Error("Gateway requires the reviewed two Qwen aliases");
    for (const upstream of upstreams) {
        const url = new URL(upstream.url);
        if (!["http:", "https:"].includes(url.protocol) ||
            url.username ||
            url.password ||
            url.search ||
            url.hash)
            throw new Error("Invalid inference upstream URL");
    }
    const admission = new Admission(upstreams, positive(options.queueLimit, 128, "queueLimit"), positive(options.queueByteLimit, 128 * 1024 * 1024, "queueByteLimit"), positive(options.queueTimeoutMs, 30 * 60 * 1000, "queueTimeoutMs"), options.initialLaneStates, options.onLaneState, options.availability);
    const mimo = options.frontier && "provider" in options.frontier ? options.frontier : undefined;
    const glm = options.frontier && !("provider" in options.frontier) ? options.frontier : undefined;
    const frontierModel = mimo ? MIMO_MODEL : options.selectedFrontierModel ?? FRONTIER_MODEL;
    if ((glm && frontierModel !== FRONTIER_MODEL) || (mimo && options.selectedFrontierModel === FRONTIER_MODEL))
        throw Error("Frontier selection mismatch");
    // Keep the existing durable GLM key as the one shared frontier slot. Any
    // retained prior provider uncertainty blocks selection across app restarts.
    const previousFrontier = options.initialFrontierOwnerModel !== undefined || [FRONTIER_MODEL, MIMO_MODEL].some(id => ["active", "quarantined"].includes(options.initialLaneStates?.[id] ?? "idle")) ? "quarantined" : "idle";
    const unresolvedProviderChange = previousFrontier !== "idle" && ((options.initialFrontierOwnerModel !== undefined && options.initialFrontierOwnerModel !== frontierModel) || (frontierModel === FRONTIER_MODEL && ["active", "quarantined"].includes(options.initialLaneStates?.[MIMO_MODEL] ?? "idle")));
    const frontierAvailability = options.availability ??
        (() => ({
            state: "unknown",
            reason: "readiness_unknown",
            dispatch: "hold",
        }));
    const frontierAdmission = options.frontier
        ? new Admission([{ url: mimo ? mimoUrl(mimo) : frontierUrl(glm), alias: frontierModel }], 8, 128 * 1024 * 1024, positive(options.frontier.fixtureQueueTimeoutMs, 30 * 60 * 1000, "frontier queue timeout"), { [frontierModel]: previousFrontier }, (_alias, state) => options.onLaneState?.(FRONTIER_MODEL, state), frontierAvailability)
        : undefined;
    // Validate fixture override at construction; select the real model per request.
    activeRequestTimeoutMs("qwen", options.activeTimeoutMs);
    const tokens = new Map();
    const frontierCancellations = new Map();
    const active = new Set();
    const app = Fastify({
        logger: false,
        bodyLimit: 64 * 1024 * 1024,
        requestTimeout: 0,
        connectionTimeout: 0,
        forceCloseConnections: true,
    });
    app.setErrorHandler((error, _request, reply) => {
        if (error instanceof MimoError)
            return reply.code(error.code === "mimo_context_full" || error.code === "mimo_output_limit" ? 413 : error.code === "mimo_invalid_request" || error.code === "mimo_tool_history" ? 400 : 503).send({ error: { code: error.code, message: "MiMo request or qualification rejected" } });
        if (error instanceof ApiError)
            return reply
                .code(error.statusCode)
                .send({ error: { code: error.code, message: error.message } });
        const known = error instanceof GatewayError;
        const statusCode = error && typeof error === "object" && "statusCode" in error
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
    app.setNotFoundHandler((_request, reply) => reply.code(404).send({
        error: {
            code: "unsupported_route",
            message: "Only supported inference routes are available",
        },
    }));
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
            throw new ApiError(503, "image_unavailable", "Image broker is not configured");
        return options.images;
    };
    const imageSession = (authorization) => {
        const sessionId = tokens.get(authorization.slice(7));
        if (!sessionId)
            throw new ApiError(401, "unauthorized", "Session authorization required");
        return sessionId;
    };
    app.get("/v1/image-capabilities", async () => imageBroker().capabilities());
    app.post("/v1/image-jobs", { bodyLimit: 64 * 1024 }, async (request) => ({
        job: await imageBroker().submit(imageSession(request.headers.authorization), request.body),
    }));
    app.get("/v1/image-jobs/:jobId", async (request) => ({
        job: imageBroker().get(imageSession(request.headers.authorization), requireId(request.params.jobId)),
    }));
    app.post("/v1/image-jobs/:jobId/cancel", async (request) => {
        if (!request.body ||
            typeof request.body !== "object" ||
            Array.isArray(request.body) ||
            Object.keys(request.body).length)
            throw new ApiError(400, "invalid_body", "Expected an empty object");
        return {
            job: imageBroker().cancel(imageSession(request.headers.authorization), requireId(request.params.jobId)),
        };
    });
    async function chat(request, reply) {
        const frontier = request.routeOptions.url === "/frontier/v1/chat/completions";
        const selectedAdmission = frontier ? frontierAdmission : admission;
        if (!selectedAdmission || (frontier && !options.frontier))
            throw new ApiError(503, "frontier_unavailable", "Frontier is not qualified");
        if (frontier &&
            (options.dispatchHeld?.("harness") ||
                options.dispatchHeld?.(frontierModel)))
            throw new ApiError(503, "frontier_held", "Frontier dispatch is held");
        const prepared = frontier && mimo ? prepareMimo(request.body) : undefined;
        if (prepared && prepared.outputTokens > MIMO_PRODUCTION_OUTPUT)
            throw new ApiError(413, "mimo_output_limit", "MiMo production output ceiling exceeded");
        const body = prepared ? prepared.body : frontier ? frontierBody(request.body) : requestBody(request.body);
        const bodyBytes = Buffer.byteLength(JSON.stringify(body));
        const token = request.headers.authorization.slice(7);
        const sessionId = tokens.get(token);
        if (!sessionId)
            throw new GatewayError(401, "unauthorized", "Inference authorization required");
        const record = frontier
            ? {
                id: randomBytes(16).toString("hex"),
                sessionId,
                state: "queued",
                model: frontierModel,
                contextWindow: options.frontier.contextWindow,
                updatedAt: new Date().toISOString(),
            }
            : undefined;
        const recordState = (state) => {
            if (record) {
                record.state = state;
                record.updatedAt = new Date().toISOString();
                options.frontier.onRequestState({ ...record });
            }
        };
        recordState("queued");
        const cancelled = new AbortController();
        if (frontier) {
            const owned = frontierCancellations.get(token) ?? new Set();
            frontierCancellations.set(token, owned);
            owned.add(cancelled);
            reply.raw.once("close", () => {
                owned.delete(cancelled);
                if (!owned.size)
                    frontierCancellations.delete(token);
            });
        }
        let disconnected = false;
        let upstreamResponse;
        const disconnect = () => {
            if (reply.raw.writableEnded)
                return;
            disconnected = true;
            cancelled.abort();
            // A cancelled consumer is detached. Keep consuming upstream with bounded
            // observation buffers; aborting its socket would not prove GPU settlement.
            upstreamResponse?.resume();
        };
        reply.raw.once("close", disconnect);
        let lane;
        try {
            lane = await selectedAdmission.acquire(cancelled.signal, bodyBytes);
        }
        catch (error) {
            recordState(cancelled.signal.aborted ? "cancelled" : "rejected");
            reply.raw.removeListener("close", disconnect);
            if (disconnected)
                return reply;
            throw error;
        }
        if (disconnected) {
            selectedAdmission.settle(lane, true);
            recordState("cancelled");
            reply.raw.removeListener("close", disconnect);
            return reply;
        }
        const requireCurrentToken = () => {
            if (tokens.get(token) === sessionId)
                return;
            // No upstream request exists yet: release this admission safely. Revoking
            // a token never aborts an already dispatched generation or its drain.
            selectedAdmission.settle(lane, true);
            recordState("rejected");
            reply.raw.removeListener("close", disconnect);
            throw new GatewayError(401, "unauthorized", "Inference authorization required");
        };
        requireCurrentToken();
        let key;
        try {
            const credential = frontier
                ? options.frontier.upstreamKey
                : options.upstreamKey;
            key = typeof credential === "function" ? await credential() : credential;
            if (!key || !/^[\x21-\x7e]+$/.test(key))
                throw new Error("Invalid upstream credential");
        }
        catch {
            selectedAdmission.settle(lane, true);
            recordState("rejected");
            reply.raw.removeListener("close", disconnect);
            throw new GatewayError(503, "upstream_credential_unavailable", "Inference credential is unavailable");
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
        if (frontier &&
            (options.dispatchHeld?.("harness") ||
                options.dispatchHeld?.(frontierModel))) {
            selectedAdmission.settle(lane, true);
            recordState("rejected");
            reply.raw.removeListener("close", disconnect);
            throw new ApiError(503, "frontier_held", "Frontier dispatch is held");
        }
        while (options.dispatchHeld?.(lane.upstream.alias) &&
            !disconnected &&
            !cancelled.signal.aborted)
            await new Promise((resolve) => setTimeout(resolve, 50));
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
            throw new GatewayError(503, "lane_unavailable", "Selected inference lane is unavailable");
        }
        let mimoAdmission;
        let mimoPayload;
        if (frontier) {
            try {
                if (mimo && prepared) {
                    mimoAdmission = await countMimo(prepared, mimo.qualification, {
                        observe: mimo.observe,
                        post: (r) => fetch(`${mimoUrl(mimo).replace(/\/v1$/, "")}${r.path}`, {
                            method: r.method, redirect: "error", headers: { authorization: `Bearer ${key}`, "content-type": "application/json" }, body: r.body, signal: r.signal,
                        }),
                    }, cancelled.signal);
                    const observed = await mimo.observe(cancelled.signal);
                    mimoPayload = mimoGenerationRequest(mimoAdmission, observed).body;
                    Object.assign(record, { promptTokens: mimoAdmission.promptTokens, reservedOutput: prepared.outputTokens,
                        canonicalRequestSha256: prepared.sha256, qualificationEvidenceSha256: mimo.qualification.evidenceSha256,
                        serverInstance: observed.serverInstance, serverGeneration: observed.serverGeneration });
                }
                else {
                    const counted = await countFrontier(glm, body, key, cancelled.signal);
                    Object.assign(record, counted);
                }
                if (cancelled.signal.aborted)
                    throw new ApiError(499, "cancelled", "Request cancelled");
                // This catch owns the single release. Do not call requireCurrentToken,
                // which releases before throwing and could free the next queued owner.
                if (tokens.get(token) !== sessionId)
                    throw new ApiError(401, "unauthorized", "Inference authorization required");
                if (options.dispatchHeld?.("harness") ||
                    options.dispatchHeld?.(frontierModel))
                    throw new ApiError(503, "frontier_held", "Frontier dispatch is held");
                if (selectedAdmission.available(lane).dispatch !== "allow")
                    throw new ApiError(503, "lane_unavailable", "Frontier backend is unavailable");
                recordState("active");
            }
            catch (error) {
                selectedAdmission.settle(lane, true);
                reply.raw.removeListener("close", disconnect);
                recordState(cancelled.signal.aborted ? "cancelled" : "rejected");
                throw error;
            }
        }
        lane.dispatched = true;
        lane.ownerSettled = false;
        const payload = mimoPayload ?? JSON.stringify({ ...body, model: lane.upstream.alias });
        const endpoint = new URL(`${lane.upstream.url.replace(/\/$/, "")}/chat/completions`);
        const observe = new UsageObserver(body.stream === true, (value) => {
            if (!value || typeof value !== "object")
                return;
            const usage = value.usage;
            if (!usage || typeof usage !== "object")
                return;
            const { prompt_tokens: promptTokens, completion_tokens: completionTokens, } = usage;
            if (typeof promptTokens !== "number" ||
                !Number.isSafeInteger(promptTokens) ||
                promptTokens < 0)
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
                        source: "gateway.latest-request.prompt_tokens (main/child/compaction attribution unknown)",
                    });
            }
            catch {
                /* A telemetry consumer must not alter inference transport. */
            }
        });
        reply.hijack();
        await new Promise((resolve) => {
            let settled = false;
            let timeout;
            let mimoValidator;
            const mimoChunks = [];
            const settlementAbort = new AbortController();
            const settle = (confirmed) => {
                if (settled)
                    return;
                settled = true;
                clearTimeout(timeout);
                settlementAbort.abort();
                active.delete(upstream);
                selectedAdmission.settle(lane, confirmed);
                try {
                    recordState(confirmed ? "settled" : "quarantined");
                }
                catch {
                    /* durable active remains unsafe */
                }
                reply.raw.removeListener("close", disconnect);
                resolve();
            };
            const fail = (code, message) => {
                if (settled)
                    return;
                if (!disconnected && !reply.raw.destroyed) {
                    if (!reply.raw.headersSent)
                        sendRawError(reply, code === "active_timeout" ? 504 : 502, code, message);
                    else
                        reply.raw.destroy();
                }
                settle(false);
            };
            const transport = endpoint.protocol === "https:" ? httpsRequest : httpRequest;
            const upstream = transport(endpoint, {
                method: "POST",
                agent: false,
                headers: {
                    "content-type": "application/json",
                    "content-length": Buffer.byteLength(payload),
                    authorization: `Bearer ${key}`,
                    accept: body.stream === true ? "text/event-stream" : "application/json",
                },
            }, (response) => {
                if (settled) {
                    response.resume();
                    return;
                }
                upstreamResponse = response;
                if (mimoAdmission) {
                    try {
                        mimoValidator = new MimoStreamValidator(mimoAdmission, { status: response.statusCode ?? 502, contentType: String(response.headers["content-type"] ?? "") });
                    }
                    catch {
                        response.resume();
                        fail("mimo_stream_invalid", "MiMo stream rejected; owner requires settlement review");
                        return;
                    }
                }
                if (!disconnected && !mimoValidator) {
                    reply.raw.statusCode = response.statusCode ?? 502;
                    for (const header of [
                        "content-type",
                        "content-encoding",
                        "cache-control",
                        "x-request-id",
                    ]) {
                        const value = response.headers[header];
                        if (value !== undefined)
                            reply.raw.setHeader(header, value);
                    }
                    reply.raw.setHeader("x-accel-buffering", "no");
                }
                response.on("data", (chunk) => {
                    if (settled)
                        return;
                    if (mimoValidator) {
                        try {
                            mimoValidator.push(chunk);
                            if (!disconnected)
                                mimoChunks.push(Buffer.from(chunk));
                        }
                        catch {
                            mimoChunks.length = 0;
                            fail("mimo_stream_invalid", "MiMo stream rejected; owner requires settlement review");
                        }
                        return;
                    }
                    observe.data(chunk);
                    if (!disconnected && !reply.raw.destroyed) {
                        if (!reply.raw.write(chunk)) {
                            response.pause();
                            reply.raw.once("drain", () => response.resume());
                        }
                    }
                });
                response.once("end", async () => {
                    if (settled)
                        return;
                    if (mimoValidator && mimo) {
                        try {
                            const observed = await mimo.observe(settlementAbort.signal);
                            if (settled)
                                return;
                            const result = mimoValidator.finish(response.complete, observed);
                            record.backendResponseId = result.responseId;
                            recordState("active");
                            if (mimo.serialCompletionQualified !== true)
                                throw Error("Serial native completion unqualified");
                            // Hold tool fragments until full SSE/HTTP validation under the qualified serial runtime.
                            // A detached consumer never interrupts this bounded upstream drain.
                            if (!disconnected && !reply.raw.destroyed) {
                                reply.raw.statusCode = 200;
                                reply.raw.setHeader("content-type", "text/event-stream");
                                reply.raw.end(Buffer.concat(mimoChunks));
                            }
                            settle(true);
                        }
                        catch {
                            fail("mimo_settlement_unconfirmed", "MiMo owner requires settlement review");
                        }
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
                    const confirmed = response.complete &&
                        (rejectedBeforeGeneration ||
                            (success && (body.stream !== true || observe.terminal)));
                    if (!disconnected && !reply.raw.destroyed)
                        reply.raw.end();
                    settle(confirmed);
                });
                response.once("error", () => fail("upstream_interrupted", "Inference transport was interrupted"));
                response.once("aborted", () => fail("upstream_interrupted", "Inference transport was interrupted"));
            });
            active.add(upstream);
            upstream.once("error", () => fail("upstream_interrupted", "Inference transport was interrupted"));
            timeout = setTimeout(() => {
                fail("active_timeout", "Active generation exceeded its limit; lane requires settlement review");
                upstream.destroy();
                upstreamResponse?.destroy();
            }, activeRequestTimeoutMs(frontier && mimo ? MIMO_MODEL : "qwen-or-glm", options.activeTimeoutMs));
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
        for (const request of active)
            request.destroy();
    });
    return {
        app,
        issueToken(sessionId) {
            if (!sessionId)
                throw new Error("sessionId is required");
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
            if (frontierModel === MIMO_MODEL || unresolvedProviderChange)
                return qwen && !aliases.some(a => a === MIMO_MODEL || a === FRONTIER_MODEL);
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
function sendRawError(reply, status, code, message) {
    reply.raw.statusCode = status;
    reply.raw.setHeader("content-type", "application/json");
    reply.raw.end(JSON.stringify({ error: { code, message } }));
}
