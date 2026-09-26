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
      ...options,
      store,
      files,
      cancelImages: (id) => images?.cancelSession(id),
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
      ...(options.availabilitySummary ? { availability: options.availabilitySummary() } : {}),
    }));
    app.get("/api/sessions", async () => ({ sessions: store.listSessions() }));
    app.post("/api/sessions", async (req) => {
      only(object(req.body), []);
      return { session: await broker.createSession() };
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
    app.post("/api/sessions/:id/messages", async (req, reply) => {
      const body = object(req.body);
      only(body, ["text", "attachmentIds", "imageReferences"]);
      if (typeof body.text !== "string" || body.text.length > 250000)
        throw new ApiError(
          400,
          "invalid_message",
          "text must be a string of at most 250000 characters",
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
      const runId = broker.enqueue(
        id(req),
        "message",
        body.text,
        attachmentIds,
        imageReferences,
      );
      return reply.code(202).send({ runId });
    });
    app.post("/api/sessions/:id/cancel", async (req, reply) => {
      only(object(req.body), []);
      await broker.cancel(id(req));
      return reply.code(202).send({ status: "cancelling" });
    });
    app.post("/api/sessions/:id/handoff", async (req, reply) => {
      only(object(req.body), []);
      return reply
        .code(202)
        .send({ runId: broker.enqueue(id(req), "handoff", "") });
    });
    app.post("/api/sessions/:id/uploads", async (req, reply) => {
      const sessionId = id(req);
      store.getSession(sessionId);
      let uploaded: import("./store.js").FileRecord | undefined;
      try {
        for await (const part of req.parts()) {
          if (part.type !== "file" || uploaded)
            throw new ApiError(
              400,
              "invalid_upload",
              "Expected exactly one multipart file",
            );
          if (
            options.visionAvailable !== true &&
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
