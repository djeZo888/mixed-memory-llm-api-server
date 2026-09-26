import { readFileSync } from "node:fs";
import { frontierConfiguration } from "./frontier.js";
import { FrontierLedger } from "./frontier-ledger.js";
import { readProtectedCredential } from "./protected-credential.js";
export { readProtectedCredential } from "./protected-credential.js";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { createApp } from "./app.js";
import { createGateway, type LaneState } from "./gateway.js";
import { ImageUpstream } from "./image-upstream.js";
import { createEngine } from "./engine.js";
import {
  NodeAvailability,
  type HardwareLatchLedger,
} from "./node-availability.js";
import { nodeClient } from "./node-client.js";
import { openDispatchFreeze, serveDispatchFreeze } from "./dispatch-freeze.js";
import { serviceAvailability } from "./service-availability.js";
import { createBackendReadiness } from "./backend-readiness.js";

function required(name: string): string {
  const value = process.env[name];
  if (!value || !path.isAbsolute(value))
    throw new Error(`${name} must be an absolute path`);
  return value;
}
function port(name: string, fallback: number) {
  const value = process.env[name];
  if (!value) return fallback;
  if (!/^\d+$/.test(value) || +value < 1 || +value > 65535)
    throw new Error(`${name} must be a TCP port`);
  return +value;
}
export async function start() {
  if (Number(process.versions.node.split(".")[0]) !== 24)
    throw new Error("Node 24 is required");
  const dataDir = required("AI_HARNESS_DATA_DIR"),
    launcher = required("AI_HARNESS_ENGINE_LAUNCHER"),
    keyFile = required("AI_HARNESS_INFERENCE_KEY_FILE");
  const freeze = openDispatchFreeze();
  const key = await readProtectedCredential(keyFile);
  const approvalKeyFile = process.env.AI_HARNESS_BROWSER_APPROVAL_KEY_FILE;
  const approvalProxyKey = approvalKeyFile
    ? await readProtectedCredential(approvalKeyFile)
    : undefined;
  const gatewayPort = port("AI_HARNESS_GATEWAY_PORT", 8081);
  let frontierLedger: FrontierLedger | undefined;
  let gateway: ReturnType<typeof createGateway> | undefined;
  let nodeAvailability: NodeAvailability | undefined;
  let freezeServer: Awaited<ReturnType<typeof serveDispatchFreeze>> | undefined;
  let freezeTimer: NodeJS.Timeout | undefined;
  const availability = (id: string) => {
    const observed = serviceAvailability(
      nodeAvailability ? (name) => nodeAvailability!.get(name) : undefined,
      id,
    );
    return freeze.held(id) && observed.dispatch !== "reject"
      ? {
          ...observed,
          dispatch: "hold" as const,
          reason: "admin_dispatch_frozen",
        }
      : observed;
  };
  const application = await createApp({
    dataDir,
    launcher,
    engineFactory: createEngine,
    imageBackend: new ImageUpstream({ key }),
    frontierStatus: (sessionId) => ({
      ...gateway?.frontierSnapshot(),
      requests: frontierLedger?.latest(sessionId) ?? [],
    }),
    approvalProxyKey,
    availability,
    dispatchHeld: () => freeze.held("harness"),
    availabilitySummary: () =>
      nodeAvailability?.states() ?? {
        qwenGpu0: "unknown",
        qwenGpu1: "unknown",
        image: "unknown",
      },
    gatewayUrl:
      process.env.AI_HARNESS_GATEWAY_URL ??
      `http://127.0.0.1:${gatewayPort}/v1`,
    issueToken: (id) => gateway!.issueToken(id),
    revokeToken: (token) => gateway!.revokeToken(token),
    allowedOrigins: process.env.AI_HARNESS_ALLOWED_ORIGINS?.split(",").map(
      (s) => s.trim(),
    ),
    webDist: process.env.AI_HARNESS_WEB_DIST,
    visionAvailable: process.env.AI_HARNESS_VISION_AVAILABLE !== "false", // fixed deployment capability approved by root probe; UI path remains untested
  });
  try {
    application.store.db.exec(
      "CREATE TABLE IF NOT EXISTS gateway_lanes(alias TEXT PRIMARY KEY,state TEXT NOT NULL); CREATE TABLE IF NOT EXISTS gateway_usage(session_id TEXT PRIMARY KEY,prompt_tokens INTEGER NOT NULL,completion_tokens INTEGER,source TEXT NOT NULL,observed_at TEXT NOT NULL)",
    );
    application.store.db.exec(
      "CREATE TABLE IF NOT EXISTS node_hardware_latches(id INTEGER PRIMARY KEY CHECK(id=1), value TEXT NOT NULL)",
    );
    const latchRow = application.store.db
      .prepare("SELECT value FROM node_hardware_latches WHERE id=1")
      .get() as { value: string } | undefined;
    const controlKeyFile = process.env.AI_HARNESS_NODE_CONTROL_KEY_FILE;
    // Optional H005 source wiring. The status daemon is never a chat startup
    // dependency. Once a durable latch exists, disabling config cannot erase it.
    if (controlKeyFile || latchRow) {
      const controlKey = controlKeyFile
        ? await readProtectedCredential(controlKeyFile)
        : undefined;
      nodeAvailability = new NodeAvailability({
        readiness: createBackendReadiness(key),
        backend: controlKey
          ? nodeClient("ai-vm", controlKey)
          : {
              status: async () => {
                throw Error("Passive node not configured");
              },
            },
        initialLatches: latchRow
          ? (JSON.parse(latchRow.value) as HardwareLatchLedger)
          : {},
        onLatch: (ledger) => {
          application.store.db
            .prepare("INSERT OR REPLACE INTO node_hardware_latches VALUES(1,?)")
            .run(JSON.stringify(ledger));
        },
        changed: () => {
          gateway?.notifyAvailabilityChanged();
          application.images?.notifyAvailabilityChanged();
        },
      });
    }
    frontierLedger = new FrontierLedger(application.store.db);
    let configured: ReturnType<typeof frontierConfiguration>;
    try {
      configured = frontierConfiguration(
        JSON.parse(
          readFileSync(
            new URL("../../config/frontier.json", import.meta.url),
            "utf8",
          ),
        ),
      );
    } catch {
      /* Missing/invalid frontier config never prevents Qwen startup. */
    }
    const frontier = configured
      ? {
          ...configured,
          // Lazy read: missing frontier credential never prevents Qwen startup.
          upstreamKey: () =>
            readProtectedCredential(required("AI_HARNESS_FRONTIER_KEY_FILE")),
          onRequestState: (record: import("./frontier.js").FrontierRecord) =>
            frontierLedger!.record(record),
        }
      : undefined;
    const states = Object.fromEntries(
      (
        application.store.db
          .prepare("SELECT alias,state FROM gateway_lanes")
          .all() as { alias: string; state: LaneState }[]
      ).map((r) => [r.alias, r.state]),
    );
    gateway = createGateway({
      frontier,
      upstreamKey: key,
      images: application.images,
      availability,
      dispatchHeld: (alias) => freeze.held(alias),
      initialLaneStates: states,
      onLaneState: (alias, state) => {
        application.store.db
          .prepare("INSERT OR REPLACE INTO gateway_lanes VALUES(?,?)")
          .run(alias, state);
      },
      onUsage: (usage) => {
        // Native children/compression share a token. Retain real request evidence but
        // never overwrite main-chat context with a request of unknown attribution.
        application.store.db
          .prepare("INSERT OR REPLACE INTO gateway_usage VALUES(?,?,?,?,?)")
          .run(
            usage.sessionId,
            usage.promptTokens,
            usage.completionTokens ?? null,
            usage.source,
            new Date().toISOString(),
          );
      },
    });
    const changed = () => {
      application.broker.notifyDispatchChanged();
      gateway?.notifyAvailabilityChanged();
      application.images?.notifyAvailabilityChanged();
    };
    let previousHolds = JSON.stringify(
      freeze.db.prepare("SELECT key FROM dispatch_holds ORDER BY key").all(),
    );
    freezeTimer = setInterval(() => {
      try {
        const holds = JSON.stringify(
          freeze.db
            .prepare("SELECT key FROM dispatch_holds ORDER BY key")
            .all(),
        );
        if (holds !== previousHolds) {
          previousHolds = holds;
          changed();
        }
      } catch {
        changed();
      } // Dispatch gates independently fail closed on read error.
    }, 250);
    freezeTimer.unref();
    nodeAvailability?.start();
    await gateway.app.listen({ host: "127.0.0.1", port: gatewayPort });
    await application.app.listen({
      host: "127.0.0.1",
      port: port("AI_HARNESS_PORT", 8080),
    });
    freezeServer = await serveDispatchFreeze(
      freeze,
      () => {
        const broker = application.broker.dispatchImpact(),
          lanes = gateway!.snapshot(),
          image = application.images?.dispatchImpact();
        const active =
          (gateway!.frontierSnapshot().state === "active" ? 1 : 0) +
          broker.active +
          lanes.lanes.filter((lane) => lane.state === "active").length +
          (image?.lane === "active" ? 1 : 0);
        const queued =
          gateway!.frontierSnapshot().queued +
          broker.queued +
          lanes.queued +
          (image?.queued ?? 0) +
          (image?.awaitingApproval ?? 0);
        // Counts are component reservations, not distinct user requests. Quarantine
        // and native activity cannot be inferred idle from passive readiness.
        return {
          frozen: freeze.held(),
          ready: true,
          activity: active ? "busy" : "unknown",
          active_requests: active,
          queue_depth: queued,
        };
      },
      changed,
      (scope) => {
        const aliases = [
          scope.includes("qwen-gpu0") ? "qwen3.8-27b-gpu0" : null,
          scope.includes("qwen-gpu1") ? "qwen3.8-27b" : null,
        ].filter((id): id is string => !!id);
        if (!gateway!.reconcileAfterOwnerSettlement(aliases)) return false;
        if (
          scope.includes("image") &&
          application.images &&
          !application.images.reconcileAfterOwnerSettlement()
        )
          return false;
        return true;
      },
    );
  } catch (error) {
    nodeAvailability?.stop();
    clearInterval(freezeTimer);
    await freezeServer?.close();
    freeze.close();
    await gateway?.close();
    await application.app.close();
    throw error;
  }
  let stopping = false;
  const close = async () => {
    if (stopping) return;
    stopping = true;
    nodeAvailability?.stop();
    clearInterval(freezeTimer);
    await freezeServer?.close();
    await Promise.all([
      application.broker.close(),
      application.images?.close(),
    ]);
    await gateway!.close();
    await application.app.close();
    freeze.close();
  };
  for (const signal of ["SIGINT", "SIGTERM"] as const)
    process.once(signal, () => {
      const timer = setTimeout(() => process.exit(1), 70000);
      timer.unref();
      void close().then(
        () => {
          clearTimeout(timer);
          process.exitCode = 0;
        },
        () => {
          clearTimeout(timer);
          process.exitCode = 1;
        },
      );
    });
  process.stdout.write("ai-harness 0.0.3 listening on IPv4 loopback\n");
  return { ...application, gateway, close };
}
if (
  process.argv[1] &&
  import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href
) {
  start().catch(() => {
    process.stderr.write(
      "ai-harness startup failed; check protected configuration and local ports\n",
    );
    process.exitCode = 1;
  });
}
