import { MAX_MESSAGE_CHARACTERS, MAX_MESSAGE_BODY_BYTES } from "./message-limits.js";
import { codexCapabilities } from "./codex-capabilities.js";
import Fastify, { type FastifyInstance } from "fastify";
import multipart from "@fastify/multipart";
import staticPlugin from "@fastify/static";
import { existsSync, lstatSync, realpathSync } from "node:fs";
import path from "node:path";
import { timingSafeEqual } from "node:crypto";
import { DatabaseSync } from "node:sqlite";
import { ApiError, requireId } from "./errors.js";
import { Store } from "./store.js";
import { Files, MAX_UPLOAD } from "./files.js";
import { ImageBroker } from "./image-broker.js";
import type { ImageBackend } from "./image-contracts.js";
import { Broker, type BrokerOptions } from "./broker.js";
import { contentDisposition, imageMime } from "./file-metadata.js";
import { environment } from "./locale.js";
import { REVIEWED_SKILLS } from "./policy.js";
import { codexAvailable, assertEngineAvailable } from "./engine-router.js";
import { loadNewChatEngine } from "./system-registry.js";
import type { Event } from "./contracts.js";
import type { AvailabilityProvider } from "./service-availability.js";
// MiniMax ae65651 packages/tui/src/acp/commands.ts: exact, case-sensitive
// command tokens, plus the direct slash aliases advertised for reviewed skills.
const unsupportedSlashCommands = new Set<string>([
  "help",
  "new",
  "model",
  "status",
  "doctor",
  "context",
  "skills",
  "mcp",
  "usage",
  "compact",
  ...REVIEWED_SKILLS,
]);
export interface AppOptions extends Omit<BrokerOptions, "store" | "files"> {
  /** Root-reviewed ordinary recovery host. Absent by default; no browser body can qualify this seam. */
  memoryRecoveryHost?: (input:{sessionId:string;checkpointId:string;signal:AbortSignal;reservation:import("./store.js").WorkspaceRecoveryReservation;memory:import("./session-memory.js").SessionMemoryBridge}) => Promise<import("./session-checkpoint.js").FreshParentRecoveryEvidence>;
  /** Trusted host/fixture configuration only; existing session identity is separate. */
  newChatEngine?: "codex" | "minimax";
  dataDir: string;
  allowedOrigins?: string[];
  webDist?: string;
  heartbeatMs?: number;
  visionAvailable?: boolean;
  imageBackend?: ImageBackend;
  /** Separate protected nginx-to-server capability; never passed to engines. */
  approvalProxyKey?: string;
  availability?: AvailabilityProvider;
  frontierStatus?: (sessionId: string) => unknown;
  availabilitySummary?: () => { qwenGpu0: string; qwenGpu1: string; image: string };
}
function object(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value))
    throw new ApiError(400, "invalid_body", "Expected a JSON object");
  return value as Record<string, unknown>;
}
function only(value: Record<string, unknown>, keys: string[]) {
  if (Object.keys(value).some((k) => !keys.includes(k)))
    throw new ApiError(400, "invalid_body", "Unknown request field");
}
function id(req: { params: unknown }): string {
  return requireId((req.params as { id: unknown }).id);
}
export async function createApp(options: AppOptions): Promise<{
  app: FastifyInstance;
  store: Store;
  files: Files;
  broker: Broker;
  images?: ImageBroker;
}> {
  const newChatEngine = options.newChatEngine ?? loadNewChatEngine();
  const origins = new Set(
    (
      options.allowedOrigins ?? [
        "http://10.156.100.61",
        "http://127.0.0.1:8080",
        "http://localhost:8080",
      ]
    ).map((s) => {
      const u = new URL(s);
      if (
        !["http:", "https:"].includes(u.protocol) ||
        u.username ||
        u.password ||
        u.pathname !== "/" ||
        u.search ||
        u.hash
      )
        throw new Error("Invalid allowed origin");
      return u.origin;
    }),
  );
  const hosts = new Set([...origins].map((s) => new URL(s).host));
  const app = Fastify({
    logger: false,
    bodyLimit: 1024 * 1024,
    trustProxy: false,
    requestTimeout: 30000,
  });
  const streams = new Set<import("node:http").ServerResponse>();
  app.addHook("preClose", async () => {
    for (const stream of streams) stream.destroy();
  });
  // Data directory is private and outside the served frontend tree.
  const temporary = { root: path.resolve(options.dataDir) };
  const { mkdir, lstat, realpath, chmod } = await import("node:fs/promises");
  await mkdir(temporary.root, { recursive: true, mode: 0o700 });
  const rootStat = await lstat(temporary.root);
  if (
    rootStat.isSymbolicLink() ||
    !rootStat.isDirectory() ||
    (rootStat.mode & 0o077) !== 0
  )
    throw new Error("Data root must be a private directory");
  temporary.root = await realpath(temporary.root);
  for (const suffix of [
    "harness.sqlite",
    "harness.sqlite-wal",
    "harness.sqlite-shm",
    "owner.sqlite",
    "owner.sqlite-journal",
  ]) {
    try {
      const info = await lstat(path.join(temporary.root, suffix));
      if (!info.isFile() || info.isSymbolicLink() || info.nlink !== 1)
        throw new Error("Unsafe database file");
    } catch (e) {
      if ((e as NodeJS.ErrnoException).code !== "ENOENT") throw e;
    }
  }
  const owner = new DatabaseSync(path.join(temporary.root, "owner.sqlite"));
  try {
    owner.exec("PRAGMA busy_timeout=0; BEGIN EXCLUSIVE");
  } catch {
    owner.close();
    throw new Error("Another server owns this data directory");
  }
  let cleanupResources = () => owner.close();
  let images: ImageBroker | undefined;
  try {
    const store = new Store(
      path.join(temporary.root, "harness.sqlite"),
      path.join(temporary.root, "workspaces"),
    );
    let closed = false;
    cleanupResources = () => {
      if (closed) return;
      closed = true;
      try {
        store.close();
      } finally {
        owner.close();
      }
    };
    await chmod(path.join(temporary.root, "harness.sqlite"), 0o600);
    const files = new Files(temporary.root, store);
    await files.init();
    const broker = new Broker({
      beforeNativeReplacementCommit:options.beforeNativeReplacementCommit,
      ...options,
      store,
      files,
      cancelImages: (id) => images?.cancelSession(id),
      imageContext: (id, runId) => images?.context(id, runId) ?? "",
      validateCodexImageReferences: (sessionId, count) => assertCodexImageReferences(sessionId, count),
    });
    if (options.imageBackend)
      images = new ImageBroker({
        store,
        files,
        backend: options.imageBackend,
        availability: options.availability,
        currentRun: (id) => broker.currentImageRun(id),
      });
    const imageBroker = () => {
      if (!images)
        throw new ApiError(
          503,
          "image_unavailable",
          "Image broker is not configured",
        );
      return images;
    };
    const codexImageEnabled = (sessionId?: string, beforeEnqueue = false) => !!images && (options.enginePolicy?.codex?.imageToolEnabled === true ||
      (sessionId !== undefined && (options.imageAcceptance?.(sessionId) === true ||
        (beforeEnqueue && options.imageReferenceAcceptance?.(sessionId) === true)))) &&
      codexAvailable(options.enginePolicy, options.codexEngineFactory);
    async function assertCodexImageReferences(sessionId: string, count: number, { upload = false, beforeEnqueue = false }: { upload?: boolean; beforeEnqueue?: boolean } = {}) {
      if (!codexImageEnabled(sessionId, beforeEnqueue)) throw new ApiError(400,"codex_image_tool_unavailable","Codex image specialist is not qualified");
      const capabilities = await imageBroker().capabilities();
      if (!codexImageEnabled(sessionId, beforeEnqueue)) throw new ApiError(400,"codex_image_tool_unavailable","Codex image specialist is not qualified");
      if (!options.imageBackend?.profiles(capabilities).some(p => p.operation === "edit" && (upload ? p.referenceCount >= count : p.referenceCount === count)))
        throw new ApiError(400,"codex_image_tool_unavailable","Qualified image editing is unavailable");
    }
    app.addHook("onRequest", async (req, reply) => {
      const host = req.headers.host;
      if (
        !host ||
        !hosts.has(host.toLowerCase()) ||
        host.includes(",") ||
        (req.headers["sec-fetch-site"] &&
          req.headers["sec-fetch-site"] !== "same-origin" &&
          req.headers["sec-fetch-site"] !== "none")
      )
        throw new ApiError(
          403,
          "origin_forbidden",
          "Request Host or browser origin is not allowed",
        );
      const origin = req.headers.origin;
      if (
        origin &&
        (!origins.has(origin) || new URL(origin).host !== host.toLowerCase())
      )
        throw new ApiError(
          403,
          "origin_forbidden",
          "Cross-origin requests are not allowed",
        );
      if (req.headers.authorization)
        throw new ApiError(
          403,
          "wrong_auth_surface",
          "Bearer credentials are not accepted on the public application",
        );
      reply
        .header("X-Content-Type-Options", "nosniff")
        .header("Referrer-Policy", "same-origin")
        .header("Cross-Origin-Resource-Policy", "same-origin")
        .header("Cache-Control", "no-store");
      reply.header(
        "Content-Security-Policy",
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'",
      );
    });
    app.setErrorHandler((error, _req, reply) => {
      if (error instanceof ApiError)
        return reply
          .code(error.statusCode)
          .send({ error: { code: error.code, message: error.message } });
      const e = error as { statusCode?: number; code?: string };
      if (e.statusCode && e.statusCode >= 400 && e.statusCode < 500)
        return reply.code(e.statusCode).send({
          error: {
            code:
              e.statusCode === 413 ? "payload_too_large" : "invalid_request",
            message:
              e.statusCode === 413
                ? "Payload exceeds allowed size"
                : "Invalid request",
          },
        });
      return reply.code(500).send({
        error: { code: "internal_error", message: "Internal server error" },
      });
    });
    await app.register(multipart, {
      limits: { fileSize: MAX_UPLOAD, files: 1, fields: 0, parts: 1 },
      throwFileSizeLimit: true,
    });
    app.get("/api/health", async () => ({
      version: "0.0.3",
      environment: environment(),
      status: "ok",
      visionAvailable: options.visionAvailable === true,
      engines: { default: newChatEngine,
        minimax: { configured: true, available: true, preview: false,
          version: null, versionSource: "not-observed", readiness: "not-probed",
          protocolQualified: null, capabilities: { text: true }, capabilityDetails: {},
        },
        codex: { available: codexAvailable(options.enginePolicy, options.codexEngineFactory), preview: true,
        configured: !!options.codexEngineFactory,
        imageToolEnabled: codexImageEnabled(),
        version: options.enginePolicy?.codex?.engineVersion ?? null,
        versionSource: "deployment-policy",
        readiness: codexAvailable(options.enginePolicy, options.codexEngineFactory) ? "not-probed" : "disabled",
        protocolQualified: options.enginePolicy?.codex?.protocolQualified === true,
        capabilities: { text: true, media: false, steering: false, delegation: options.enginePolicy?.codex?.delegationEnabled === true, frontier: codexAvailable(options.enginePolicy, options.codexEngineFactory) && codexCapabilities(options.enginePolicy?.codex?.capabilities, options.enginePolicy?.codex).frontier.supported === true, reasoning: false },
        capabilityDetails: codexCapabilities(options.enginePolicy?.codex?.capabilities, options.enginePolicy?.codex),
      } },
      ...(options.availabilitySummary ? { availability: options.availabilitySummary() } : {}),
    }));
    app.get("/api/sessions", async () => ({ sessions: store.listSessions() }));
    app.post("/api/sessions", async (req) => {
      const body = object(req.body);
      only(body, ["engineKind"]);
      const engineKind = body.engineKind ?? newChatEngine;
      assertEngineAvailable(engineKind, options.enginePolicy, options.codexEngineFactory);
      return { session: await broker.createSession(undefined, engineKind) };
    });
    app.get("/api/image-capabilities", async () =>
      imageBroker().capabilities(),
    );
    app.get("/api/sessions/:id/image-jobs", async (req) => ({
      jobs: imageBroker().list(id(req)),
    }));
    app.get(
      "/api/sessions/:id/image-jobs/:jobId/approval-token",
      async (req) => {
        const received = req.headers["x-ai-harness-approval-proxy"],
          expected = options.approvalProxyKey;
        if (
          !expected ||
          typeof received !== "string" ||
          Buffer.byteLength(received) !== Buffer.byteLength(expected) ||
          !timingSafeEqual(Buffer.from(received), Buffer.from(expected))
        )
          throw new ApiError(
            403,
            "image_approval_forbidden",
            "Image approval token requires the trusted browser proxy",
          );
        return imageBroker().issueApprovalToken(
          id(req),
          requireId((req.params as { jobId: string }).jobId),
        );
      },
    );
    app.post("/api/sessions/:id/image-jobs/:jobId/approval", async (req) => {
      const body = object(req.body);
      only(body, ["decision", "approvalToken"]);
      if (body.decision !== "approve" && body.decision !== "reject")
        throw new ApiError(
          400,
          "invalid_decision",
          "Expected approve or reject",
        );
      return {
        job: imageBroker().browser(
          await imageBroker().approve(
            id(req),
            requireId((req.params as { jobId: string }).jobId),
            body.decision,
            body.approvalToken as string,
          ),
        ),
      };
    });
    app.post("/api/sessions/:id/image-jobs/:jobId/cancel", async (req) => {
      only(object(req.body), []);
      return {
        job: imageBroker().browser(
          imageBroker().cancel(
            id(req),
            requireId((req.params as { jobId: string }).jobId),
          ),
        ),
      };
    });
    app.get("/api/sessions/:id/frontier", async (req) => {
      const sessionId = id(req); store.getSession(sessionId);
      return options.frontierStatus?.(sessionId) ?? { model: "glm-5.3-flash", configured: false, state: "unavailable", requests: [] };
    });
    app.get("/api/sessions/:id", async (req) => {
      const snapshot = store.snapshot(id(req));
      snapshot.artifacts = await files.withLegacyReferences(
        id(req),
        snapshot.artifacts,
      );
      return snapshot;
    });
    app.delete("/api/sessions/:id", async (req, reply) => {
      const status = await broker.delete(id(req));
      return reply.code(status === "deleted" ? 200 : 202).send({ status });
    });
    app.post("/api/sessions/:id/references", async (req,reply) => {
      const body = object(req.body);
      only(body,["fileId"]);
      const attachment = await files.referenceAttachment(id(req),requireId(body.fileId));
      return reply.code(201).send({attachment:store.publicFile(attachment)});
    });
    app.post("/api/sessions/:id/messages", { bodyLimit: MAX_MESSAGE_BODY_BYTES }, async (req, reply) => {
      const body = object(req.body);
      only(body, ["text", "attachmentIds", "imageReferences", "submissionId"]);
      const submissionId = body.submissionId === undefined ? undefined : requireId(body.submissionId);
      if (typeof body.text !== "string" || body.text.length > MAX_MESSAGE_CHARACTERS)
        throw new ApiError(
          400,
          "invalid_message",
          `text must be a string of at most ${MAX_MESSAGE_CHARACTERS} characters`,
        );
      const ids = body.attachmentIds ?? [];
      if (
        !Array.isArray(ids) ||
        ids.length > 10 ||
        new Set(ids).size !== ids.length
      )
        throw new ApiError(
          400,
          "invalid_attachment",
          "Invalid attachment identifiers",
        );
      const attachmentIds = ids.map(requireId);
      const references = body.imageReferences ?? [];
      if (
        !Array.isArray(references) ||
        references.length > 10 ||
        new Set(references).size !== references.length
      )
        throw new ApiError(
          400,
          "invalid_image_reference",
          "Invalid image references",
        );
      const imageReferences = references.map(requireId);
      if (!body.text.trim() && !attachmentIds.length && !imageReferences.length)
        throw new ApiError(400, "invalid_message", "Message is empty");
      const command = /^\/([^\s]+)(?:\s+([\s\S]*?))?\s*$/u.exec(body.text)?.[1];
      if (command && unsupportedSlashCommands.has(command))
        throw new ApiError(
          400,
          "unsupported_slash_command",
          "Native CLI slash commands are not supported in ai-harness v0.0.3. Please phrase a normal task instead.",
        );
      // Durable retrieval precedes mutable readiness/staging. The broker repeats
      // this lookup inside its creation transaction to close concurrent-request races.
      if (submissionId) {
        const existing = store.submissionRun(id(req), submissionId, {
          text: body.text, attachmentIds, imageReferences,
        });
        if (existing) return reply.code(202).send({ runId: existing });
      }
      if (store.getSession(id(req)).engineKind === "codex" && imageReferences.length) {
        try {
          await assertCodexImageReferences(id(req), imageReferences.length, { beforeEnqueue: true });
        } catch (error) {
          // Another matching request may have committed while this asynchronous
          // observation waited (and consumed its one-shot acceptance ticket).
          if (submissionId) {
            const existing = store.submissionRun(id(req), submissionId, {
              text: body.text, attachmentIds, imageReferences,
            });
            if (existing) return reply.code(202).send({ runId: existing });
          }
          throw error;
        }
      }
      const runId = broker.enqueue(
        id(req),
        "message",
        body.text,
        attachmentIds,
        imageReferences,
        undefined,
        submissionId,
      );
      return reply.code(202).send({ runId });
    });
    app.post("/api/sessions/:id/cancel", async (req, reply) => {
      only(object(req.body), []);
      await broker.cancel(id(req));
      return reply.code(202).send({ status: "cancelling" });
    });
    app.post("/api/sessions/:id/compact", async (req, reply) => {
      const body = object(req.body);
      only(body, ["actionId"]);
      const actionId = requireId(body.actionId);
      return reply.code(202).send({
        runId: broker.enqueue(id(req), "compact", "", [], [], actionId),
      });
    });
    app.get("/api/sessions/:id/memory", async (req) => {
      store.memory.indexHistory(id(req));
      return { ...store.memory.view(id(req)), versions: store.memory.versions(id(req)), proposals: store.db.prepare("SELECT id,body FROM h041_memory_proposals WHERE session_id=? ORDER BY rowid DESC LIMIT 16").all(id(req)).map(row=>({id:String(row.id),state:JSON.parse(String(row.body))})), recovery: store.checkpoints.status(id(req)) };
    });
    app.get("/api/sessions/:id/memory/originals/:originalId", async (req) => {
      const q = object(req.query); only(q,["offset","limit"]);
      return store.memory.read(id(req),requireId((req.params as {originalId:unknown}).originalId),Number(q.offset ?? 0),Number(q.limit ?? 8192));
    });
    app.post("/api/sessions/:id/memory/search", async (req) => {
      const body = object(req.body); only(body,["query","reference","after","limit"]);
      if (typeof body.query !== "string") throw new ApiError(400,"invalid_memory","Literal query required");
      return store.memory.search(id(req),body.query,{ ...(body.reference === undefined ? {} : {reference:requireId(body.reference)}), ...(body.after === undefined ? {} : {after:Number(body.after)}), ...(body.limit === undefined ? {} : {limit:Number(body.limit)}) });
    });
    app.post("/api/sessions/:id/memory/files/:fileId", async (req) => {
      only(object(req.body),[]); return files.retainOriginal(id(req),requireId((req.params as {fileId:unknown}).fileId));
    });
    app.post("/api/sessions/:id/memory/messages/:messageId", async (req) => {
      only(object(req.body),[]); return store.memory.resolveMessage(id(req),requireId((req.params as {messageId:unknown}).messageId));
    });
    app.post("/api/sessions/:id/memory/proposals", async (req) => {
      const body = object(req.body); only(body,["state"]); return store.memory.propose(id(req),body.state);
    });
    const assertMemoryHuman = (headers: Record<string, unknown>) => {
      const received = headers["x-ai-harness-approval-proxy"], expected = options.approvalProxyKey;
      if (!expected || typeof received !== "string" || Buffer.byteLength(received) !== Buffer.byteLength(expected) || !timingSafeEqual(Buffer.from(received),Buffer.from(expected)))
        throw new ApiError(403,"memory_acceptance_forbidden","Accepted memory requires the trusted human browser proxy");
    };
    app.post("/api/sessions/:id/memory/accept", async (req) => {
      assertMemoryHuman(req.headers); const body = object(req.body); only(body,["proposalId","expectedVersion"]);
      if (body.expectedVersion !== null && typeof body.expectedVersion !== "string") throw new ApiError(400,"invalid_memory","Expected current version or null required");
      return store.memory.acceptHuman(id(req),requireId(body.proposalId),body.expectedVersion);
    });
    app.post("/api/sessions/:id/memory/recovery/:checkpointId/acknowledge", async (req) => {
      assertMemoryHuman(req.headers); const body = object(req.body); only(body,["note"]);
      if (typeof body.note !== "string") throw new ApiError(400,"invalid_memory","Recovery note required");
      return store.checkpoints.acknowledge(id(req),requireId((req.params as {checkpointId:unknown}).checkpointId),body.note);
    });
    app.post("/api/sessions/:id/memory/recovery/:checkpointId/recover", async (req) => {
      assertMemoryHuman(req.headers);only(object(req.body),[]);const sessionId=id(req),checkpointId=requireId((req.params as {checkpointId:unknown}).checkpointId);
      if(!options.memoryRecoveryHost)throw new ApiError(503,"memory_recovery_unqualified","Fresh no-replay recovery host is not qualified");
      if(broker.currentImageRun(sessionId))throw new ApiError(409,"memory_recovery_busy","Session has active work");
      return broker.recoverMemory(sessionId,checkpointId,options.memoryRecoveryHost);
    });
    app.post("/api/sessions/:id/handoff", async (req, reply) => {
      const body = object(req.body);
      only(body, ["engineKind"]);
      if (body.engineKind !== undefined)
        assertEngineAvailable(body.engineKind, options.enginePolicy, options.codexEngineFactory);
      return reply
        .code(202)
        .send({ runId: broker.enqueue(id(req), "handoff", "", [], [], undefined, undefined, body.engineKind) });
    });
    app.post("/api/sessions/:id/uploads", async (req, reply) => {
      const sessionId = id(req);
      const uploadSession = store.getSession(sessionId);
      let specialistUpload = false;
      let uploaded: import("./store.js").FileRecord | undefined;
      try {
        for await (const part of req.parts()) {
          if (part.type !== "file" || uploaded)
            throw new ApiError(
              400,
              "invalid_upload",
              "Expected exactly one multipart file",
            );
          const imageUpload = part.mimetype.startsWith("image/") || /\.(png|jpe?g|webp|gif|bmp|tiff?|svg|heic)$/i.test(part.filename);
          if (uploadSession.engineKind === "codex" && imageUpload) {
            if (!["image/png","image/jpeg"].includes(part.mimetype)) {
              part.file.resume(); throw new ApiError(415,"codex_media_unsupported","Specialist references require PNG or JPEG");
            }
            try { await assertCodexImageReferences(sessionId, 1, { upload: true, beforeEnqueue: true }); } catch (error) { part.file.resume(); throw error; }
            specialistUpload = true;
          }
          if (
            !specialistUpload && options.visionAvailable !== true &&
            (part.mimetype.startsWith("image/") ||
              /\.(png|jpe?g|webp|gif|bmp|tiff?|svg|heic)$/i.test(part.filename))
          ) {
            part.file.resume();
            throw new ApiError(
              415,
              "vision_unavailable",
              "Image inputs have not been accepted for this deployment",
            );
          }
          uploaded = await files.upload(
            sessionId,
            part.filename,
            part.mimetype,
            part.file,
          );
        }
        if (!uploaded)
          throw new ApiError(
            400,
            "missing_file",
            "Expected one multipart file",
          );
        if (specialistUpload) await files.validateImageReference(sessionId, uploaded.id, true);
        return reply.code(201).send({ attachment: store.publicFile(uploaded) });
      } catch (error) {
        if (uploaded) await files.discardAttachment(uploaded);
        throw error;
      }
    });
    app.get("/api/sessions/:id/artifacts", async (req) => {
      const sessionId = id(req);
      store.getSession(sessionId);
      return {
        artifacts: await files.withLegacyReferences(
          sessionId,
          store.files(sessionId, "artifact").map((f) => store.publicFile(f)),
        ),
      };
    });
    for (const kind of ["artifact", "attachment"] as const) {
      app.get(`/api/${kind}s/:id/download`, async (req, reply) => {
        if (Object.keys(req.query as object).length)
          throw new ApiError(
            400,
            "invalid_query",
            "Downloads accept a file ID only",
          );
        const value = await files.download(id(req), kind);
        reply
          .type("application/octet-stream")
          .header("Content-Disposition", contentDisposition(value.file.name))
          .header("Content-Length", value.size);
        return reply.send(value.stream);
      });
    }
    app.get("/api/files/:id/preview", async (req, reply) => {
      if (Object.keys(req.query as object).length)
        throw new ApiError(
          400,
          "invalid_query",
          "Preview accepts a file ID only",
        );
      const file = store.file(id(req));
      const mime = imageMime(file.name);
      if (!mime)
        throw new ApiError(
          415,
          "unsupported_preview",
          "Only image assets have previews",
        );
      const value = await files.download(file.id, file.kind);
      reply
        .type(mime)
        .header("Content-Disposition", contentDisposition(file.name, true))
        .header("Content-Length", value.size)
        .header(
          "Content-Security-Policy",
          "sandbox; default-src 'none'; script-src 'none'; style-src 'unsafe-inline'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'",
        );
      return reply.send(value.stream);
    });
    for (const selection of ["artifacts", "files"] as const)
      app.get(
        `/api/sessions/:id/runs/:runId/${selection}.zip`,
        async (req, reply) => {
          if (Object.keys(req.query as object).length)
            throw new ApiError(
              400,
              "invalid_query",
              "ZIP selection is the owned run only",
            );
          const runId = requireId((req.params as { runId: string }).runId);
          const stream = await files.zip(id(req), runId, selection === "files");
          reply
            .type("application/zip")
            .header(
              "Content-Disposition",
              contentDisposition(`reply-${runId}.zip`),
            );
          return reply.send(stream);
        },
      );
    app.get(
      "/api/sessions/:id/messages/:messageId/files.zip",
      async (req, reply) => {
        if (Object.keys(req.query as object).length)
          throw new ApiError(
            400,
            "invalid_query",
            "ZIP selection is the owned message only",
          );
        const messageId = requireId(
          (req.params as { messageId: string }).messageId,
        );
        const stream = await files.messageZip(id(req), messageId);
        return reply
          .type("application/zip")
          .header(
            "Content-Disposition",
            contentDisposition(`message-${messageId}.zip`),
          )
          .send(stream);
      },
    );
    app.get("/api/sessions/:id/events", async (req, reply) => {
      const sessionId = id(req);
      store.getSession(sessionId);
      const query = req.query as { after?: unknown };
      if (Object.keys(query).some((k) => k !== "after"))
        throw new ApiError(400, "invalid_query", "Unknown SSE query");
      const value = query.after ?? req.headers["last-event-id"] ?? "0";
      if (
        typeof value !== "string" ||
        !/^\d+$/.test(value) ||
        !Number.isSafeInteger(Number(value))
      )
        throw new ApiError(
          400,
          "invalid_cursor",
          "after must be a nonnegative event ID",
        );
      let after = Number(value);
      reply.hijack();
      const res = reply.raw;
      res.writeHead(200, {
        "Content-Type": "text/event-stream; charset=utf-8",
        "Cache-Control": "no-cache, no-transform",
        Connection: "keep-alive",
        "X-Accel-Buffering": "no",
        "X-Content-Type-Options": "nosniff",
        "Cross-Origin-Resource-Policy": "same-origin",
      });
      res.flushHeaders();
      streams.add(res);
      let closed = false,
        blocked = false,
        scheduled = false;
      const cleanup = () => {
        closed = true;
        streams.delete(res);
        clearInterval(heartbeat);
        store.events.off(sessionId, wake);
        res.off("drain", drain);
      };
      const flush = () => {
        scheduled = false;
        if (closed || blocked) return;
        for (const event of store.replay(sessionId, after, 100)) {
          after = event.id;
          if (
            !res.write(
              `id: ${event.id}\nevent: ${event.type}\ndata: ${JSON.stringify(event)}\n\n`,
            )
          ) {
            blocked = true;
            return;
          }
        }
        if (store.replay(sessionId, after, 1).length) wake();
      };
      const wake = () => {
        if (!scheduled && !closed) {
          scheduled = true;
          setImmediate(flush);
        }
      };
      const drain = () => {
        blocked = false;
        wake();
      };
      res.on("drain", drain);
      store.events.on(sessionId, wake);
      const heartbeat = setInterval(() => {
        if (closed) return;
        if (res.writableLength > 1024 * 1024) {
          res.destroy();
          return;
        }
        if (!blocked && !res.write(": heartbeat\n\n")) blocked = true;
      }, options.heartbeatMs ?? 15000);
      heartbeat.unref();
      res.once("close", cleanup);
      wake();
    });
    const web =
      options.webDist ?? path.resolve(import.meta.dirname, "../../web/dist");
    if (existsSync(web)) {
      const webRoot = await realpath(web),
        dataRoot = files.root;
      const inside = (root: string, candidate: string) =>
        candidate === root || candidate.startsWith(root + path.sep);
      if (inside(webRoot, dataRoot) || inside(dataRoot, webRoot)) {
        throw new Error(
          "Static assets must be separate from private server data",
        );
      }
      if (existsSync(path.join(webRoot, "index.html")))
        await app.register(staticPlugin, {
          root: webRoot,
          index: ["index.html"],
          dotfiles: "deny",
          list: false,
          allowedPath: (pathname, root) => {
            try {
              let target = path.resolve(root, "." + pathname);
              if (!inside(root, target)) return false;
              if (lstatSync(target).isDirectory())
                target = path.join(target, "index.html");
              let cursor = root;
              for (const part of path.relative(root, target).split(path.sep)) {
                cursor = path.join(cursor, part);
                if (lstatSync(cursor).isSymbolicLink()) return false;
              }
              return (
                lstatSync(target).isFile() && realpathSync(target) === target
              );
            } catch {
              return false;
            }
          },
        });
    }
    app.setNotFoundHandler((_req, reply) =>
      reply
        .code(404)
        .send({ error: { code: "not_found", message: "Route not found" } }),
    );
    app.addHook("onClose", async () => {
      await Promise.all([broker.close(), images?.close()]);
      cleanupResources();
    });
    await app.ready();
    return { app, store, files, broker, images };
  } catch (error) {
    await images?.close();
    cleanupResources();
    throw error;
  }
}
