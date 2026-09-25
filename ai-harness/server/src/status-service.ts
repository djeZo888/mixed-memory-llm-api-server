import Fastify from "fastify";
import { AdminSecurity } from "./admin-security.js";
import { ApiError } from "./errors.js";
import { ObserverCache } from "./observer-cache.js";
import {
  NODE_IDS,
  sanitizeNode,
  sanitizeOperation,
  unknownNode,
  validateAction,
  type NodeId,
  type NodeSnapshot,
} from "./node-contract.js";
import type { NodeBackend } from "./node-client.js";
import { statusHtml, statusCss, statusJs } from "./status-ui.js";
export function createStatusService(options: {
  backends: Record<NodeId, NodeBackend>;
  origins?: string[];
  readOnlyOrigins?: string[];
  autoPoll?: boolean;
  deadlineMs?: number;
  now?: () => number;
}) {
  const app = Fastify({
    logger: false,
    trustProxy: false,
    bodyLimit: 8192,
    requestTimeout: 5000,
  });
  const security = new AdminSecurity(
    options.origins ?? ["http://10.156.100.61"],
    options.readOnlyOrigins ?? ["http://status.ai-harness"],
  );
  const caches = Object.fromEntries(
    NODE_IDS.map((id) => [
      id,
      new ObserverCache(
        async (signal) =>
          sanitizeNode(await options.backends[id].status(signal), id),
        { deadlineMs: options.deadlineMs, now: options.now },
      ),
    ]),
  ) as Record<NodeId, ObserverCache<NodeSnapshot>>;
  const snapshot = () =>
    NODE_IDS.map((id) => {
      const cached = caches[id].snapshot(),
        node = structuredClone(cached.value ?? unknownNode(id));
      const elapsed = cached.ageMs ?? 0;
      // Receiving cached JSON does not refresh its underlying observations.
      const age = (o: { age_ms: number | null; freshness: string }) => {
        if (o.age_ms !== null) o.age_ms += elapsed;
        if (o.age_ms === null || o.freshness === "unknown")
          o.freshness = "unknown";
        else if (o.age_ms >= 15000 || cached.state !== "fresh" || cached.error)
          o.freshness = "stale";
      };
      age(node);
      age(node.inventory);
      node.services.forEach(age);
      node.gpus.forEach(age);
      Object.values(node.resources).forEach(age);
      node.resources.disk?.volumes?.forEach(age);
      return node;
    });
  app.addHook("onRequest", async (req, reply) => {
    security.check(
      req,
      req.url.startsWith("/admin") || req.url.startsWith("/api/admin"),
    );
    reply
      .header("Cache-Control", "no-store")
      .header("X-Content-Type-Options", "nosniff")
      .header("Referrer-Policy", "same-origin")
      .header(
        "Content-Security-Policy",
        "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'",
      );
  });
  app.setErrorHandler((error, _req, reply) => {
    if (error instanceof ApiError)
      return reply
        .code(error.statusCode)
        .send({ error: { code: error.code, message: error.message } });
    const status = (error as { statusCode?: number }).statusCode;
    return reply
      .code(status && status >= 400 && status < 500 ? status : 503)
      .send({
        error: {
          code: "status_unavailable",
          message: "Status or node operation unavailable",
        },
      });
  });
  app.get("/status", async (_req, reply) =>
    reply.type("text/html").send(statusHtml(false)),
  );
  app.get("/admin", async (_req, reply) =>
    reply.type("text/html").send(statusHtml(true)),
  );
  app.get("/status-assets/status.css", async (_req, reply) =>
    reply.type("text/css").send(statusCss),
  );
  app.get("/status-assets/status.js", async (_req, reply) =>
    reply.type("application/javascript").send(statusJs),
  );
  app.get("/api/status/v1/system", async () => ({
    schema_version: 1,
    nodes: snapshot(),
  }));
  app.get("/api/admin/session", async (req, reply) =>
    security.issue(req, reply),
  );
  app.get("/api/admin/v1/targets", async () => ({
    targets: snapshot().flatMap((node) => {
      if (
        !node.boot_id ||
        node.generation === null ||
        node.freshness !== "fresh"
      )
        return [];
      const base = { node_id: node.node_id, expected_boot_id: node.boot_id };
      return [
        {
          ...base,
          expected_generation: node.generation,
          actions: ["node.reboot"],
          affected_services: node.affected_services,
          activity: node.services.every((s) => s.activity === "idle")
            ? "idle"
            : "unknown",
          active_requests: null,
          queue_depth: null,
        },
        ...node.services
          .filter((s) => s.generation !== null && s.freshness === "fresh")
          .map((s) => ({
            ...base,
            service_id: s.service_id,
            expected_generation: s.generation!,
            actions: ["service.start", "service.stop", "service.restart"],
            affected_services: s.affected_services,
            activity: s.activity,
            active_requests: s.active_requests,
            queue_depth: s.queue_depth,
          })),
        ...node.gpus
          .filter((g) => g.generation !== null && g.freshness === "fresh")
          .map((g) => ({
            ...base,
            gpu_uuid: g.uuid,
            expected_generation: g.generation!,
            actions: ["gpu.reset"],
            affected_services: g.affected_services,
            activity: "unknown",
            active_requests: null,
            queue_depth: null,
          })),
      ];
    }),
  }));
  // At most one admission per node in this relay. Node owner remains durable
  // idempotency/audit/lease authority; a timeout never causes automatic replay.
  const admitting = new Set<NodeId>();
  app.post("/api/admin/v1/actions", async (req, reply) => {
    security.mutation(req);
    const action = validateAction(req.body);
    // Intermediate source checkpoint. Root requires a protected cross-host
    // harness dispatch freeze before ALL destructive actions, including ai-vm.
    // Confirmation alone is insufficient. No hidden enable flag bypasses this.
    if (action.action !== "service.start")
      throw new ApiError(
        422,
        "admission_interlock_unavailable",
        "This source checkpoint requires the protected harness dispatch-freeze interlock before destructive actions",
      );
    if (admitting.has(action.node_id))
      throw new ApiError(
        503,
        "node_admission_busy",
        "Another node admission is pending",
      );
    admitting.add(action.node_id);
    try {
      const receipt = await options.backends[action.node_id].action(
        action,
        AbortSignal.timeout(2000),
      );
      return reply.code(202).send(sanitizeOperation(receipt, action.node_id));
    } finally {
      admitting.delete(action.node_id);
    }
  });
  app.get("/api/admin/v1/operations/:id", async (req) => {
    const match = /^(ai-vm|ai-harness)~([a-zA-Z0-9_.:-]{1,128})$/.exec(
      (req.params as { id: string }).id,
    );
    if (!match)
      throw new ApiError(
        400,
        "invalid_operation",
        "Invalid namespaced operation ID",
      );
    return sanitizeOperation(
      await options.backends[match[1] as NodeId].operation(
        match[2]!,
        AbortSignal.timeout(2000),
      ),
      match[1] as NodeId,
    );
  });
  app.addHook("onClose", async () => {
    for (const cache of Object.values(caches)) cache.stop();
  });
  if (options.autoPoll !== false)
    for (const cache of Object.values(caches)) cache.start();
  return { app, caches, snapshot };
}
