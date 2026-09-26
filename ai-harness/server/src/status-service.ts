import Fastify from "fastify";
import { dispatchScope, type AdminActions, type AdminFreeze } from "./admin-actions.js";
import { AdminSecurity } from "./admin-security.js";
import { ApiError } from "./errors.js";
import { ObserverCache } from "./observer-cache.js";
import {
  SERVICE_IDS,
  sanitizeNode,
  unknownNode,
  validateAction,
  type NodeId,
  type NodeSnapshot,
} from "./node-contract.js";
import { isActionNode, loadSystemRegistry, validateSystemRegistry, type SystemRegistry } from "./system-registry.js";
import { projectNode } from "./status-projection.js";
import type { NodeBackend } from "./node-client.js";
import { statusHtml, statusCss, statusJs } from "./status-ui.js";
export function createStatusService(options: {
  backends: Record<string, Pick<NodeBackend, "status">>;
  registry?: SystemRegistry;
  origins?: string[];
  readOnlyOrigins?: string[];
  autoPoll?: boolean;
  deadlineMs?: number;
  now?: () => number;
  actions?: AdminActions;
  freeze?: AdminFreeze;
}) {
  const registry = validateSystemRegistry(options.registry ?? loadSystemRegistry());
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
    registry.nodes.map(config => [
      config.id,
      new ObserverCache(
        async (signal) => {
          const backend = Object.hasOwn(options.backends, config.id) ? options.backends[config.id] : undefined;
          if (!backend) throw Error("Observation adapter unavailable");
          return sanitizeNode(await backend.status(signal), config.id,
            registry.services.filter(s => s.node_id === config.id).map(s => s.observation_key));
        },
        { deadlineMs: options.deadlineMs, now: options.now },
      ),
    ]),
  ) as Record<string, ObserverCache<NodeSnapshot>>;
  const snapshot = () =>
    registry.nodes.map(config => {
      const cached = caches[config.id]!.snapshot(),
        node = structuredClone(cached.value ?? unknownNode(config.id));
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
      age(node.node_manager);
      node.support.forEach(age);
      node.gpus.forEach(age);
      Object.values(node.resources).forEach(age);
      node.resources.disk?.volumes?.forEach(age);
      return projectNode(node, config, registry);
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
    registry_version: registry.schema_version,
    nodes: snapshot(),
  }));
  app.get("/api/admin/session", async (req, reply) =>
    security.issue(req, reply),
  );
  app.get("/api/admin/v1/targets", async () => ({
    dispatch_impact: await options.freeze?.inspect() ?? { frozen: false, activity: "unknown", active_requests: null, queue_depth: null, ready: false },
    targets: snapshot().flatMap((node) => {
      const config = registry.nodes.find(n => n.id === node.node_id)!;
      if (!isActionNode(node.node_id) || config.observation.adapter !== "node-v1") return [];
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
          dispatch_scope: dispatchScope({ node_id: node.node_id, action: "node.reboot" }, node),
          affected_services: node.affected_services,
          activity: node.services.some((s) => s.activity === "busy")
            ? "busy"
            : node.affected_services.length > 0 && node.affected_services.every((id) => node.services.find((s) => s.service_id === id)?.activity === "idle") ? "idle" : "unknown",
          active_requests: null,
          queue_depth: null,
        },
        ...node.services
          .filter((s) => (SERVICE_IDS[node.node_id as NodeId] as readonly string[]).includes(s.service_id) && s.generation !== null && s.freshness === "fresh")
          .map((s) => ({
            ...base,
            service_id: s.service_id,
            expected_generation: s.generation!,
            actions: ["service.start", "service.stop", "service.restart"],
            dispatch_scope: [s.service_id],
            affected_services: s.affected_services,
            activity: s.activity,
            active_requests: s.active_requests,
            queue_depth: s.queue_depth,
          })),
        ...node.gpus
          .filter((g) => node.node_id === "ai-vm" && g.generation !== null && g.freshness === "fresh")
          .map((g) => ({
            ...base,
            gpu_uuid: g.uuid,
            expected_generation: g.generation!,
            actions: ["gpu.reset"],
            dispatch_scope: g.affected_services,
            affected_services: g.affected_services,
            activity: "unknown",
            active_requests: null,
            queue_depth: null,
          })),
      ];
    }),
  }));
  app.post("/api/admin/v1/actions", async (req, reply) => {
    security.mutation(req);
    const action = validateAction(req.body);
    if (!options.actions) throw new ApiError(503, "admission_unavailable", "Protected action journal is unavailable");
    return reply.code(202).send(await options.actions.submit(action));
  });
  const operationId = (raw: string) => {
    const match = /^(ai-vm|ai-harness)~([a-zA-Z0-9_.:-]{1,128})$/.exec(raw);
    if (!match) throw new ApiError(400, "invalid_operation", "Invalid namespaced operation ID");
    return { nodeId: match[1] as NodeId, id: match[2]! };
  };
  app.get("/api/admin/v1/operations/:id", async (req) => {
    const { nodeId, id } = operationId((req.params as { id: string }).id);
    if (!options.actions) throw new ApiError(503, "admission_unavailable", "Protected action journal is unavailable");
    return options.actions.get(id, nodeId);
  });
  app.post("/api/admin/v1/operations/:id/reconcile", async (req) => {
    security.mutation(req);
    const { nodeId, id } = operationId((req.params as { id: string }).id);
    const body = req.body as Record<string, unknown> | null;
    if (!body || typeof body !== "object" || Array.isArray(body) || Object.keys(body).length !== 4 || Object.keys(body).some(key => !["allow_interrupt", "expected_boot_id", "expected_generation", "idempotency_key"].includes(key)) || body.allow_interrupt !== true)
      throw new ApiError(400, "invalid_reconciliation", "Explicit recovery interruption and displayed boot/generation/key confirmation required");
    if (!options.actions) throw new ApiError(503, "admission_unavailable", "Protected action journal is unavailable");
    return options.actions.reconcile(id, nodeId, body as { allow_interrupt: boolean; expected_boot_id: string; expected_generation: number; idempotency_key: string });
  });
  app.addHook("onClose", async () => {
    options.actions?.close();
    for (const cache of Object.values(caches)) cache.stop();
  });
  if (options.autoPoll !== false)
    for (const cache of Object.values(caches)) cache.start();
  return { app, caches, snapshot };
}
