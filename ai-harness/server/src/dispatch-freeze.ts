import { createHash } from "node:crypto";
import { chmodSync, lstatSync, realpathSync, unlinkSync } from "node:fs";
import { request } from "node:http";
import { createConnection } from "node:net";
import path from "node:path";
import { DatabaseSync } from "node:sqlite";
import Fastify from "fastify";
import { ApiError } from "./errors.js";
import { validateAction, type NodeAction } from "./node-contract.js";

export const DISPATCH_STATE = "/var/lib/ai-harness-dispatch/state.sqlite";
export const DISPATCH_SOCKET = "/run/ai-harness-dispatch/control.sock";
export const FREEZE_SCOPE = [
  "harness",
  "search",
  "status",
  "qwen-gpu0",
  "qwen-gpu1",
  "image",
  "control",
];
export function actionScope(action: NodeAction, affected?: string[]): string[] {
  if (action.action === "node.reboot")
    return action.node_id === "ai-vm"
      ? ["qwen-gpu0", "qwen-gpu1", "image"]
      : ["harness", "search", "status"];
  if (action.service_id) return [action.service_id];
  if (
    !affected ||
    affected.some(
      (id) => !["qwen-gpu0", "qwen-gpu1", "image", "control"].includes(id),
    )
  )
    throw new ApiError(
      503,
      "freeze_scope_unknown",
      "Canonical GPU affected services required",
    );
  return [...new Set(affected)].sort();
}
export interface FreezeImpact {
  frozen: boolean;
  ready: boolean;
  activity: "idle" | "busy" | "unknown";
  active_requests: number | null;
  queue_depth: number | null;
}
export interface FreezeAck {
  schema_version: 1;
  frozen: true;
  request_fingerprint: string;
  owner_key: string;
  scope: string[];
  app_state: "acknowledged" | "unreachable_confirmed" | "not_affected";
}
export function actionFingerprint(action: NodeAction): string {
  return createHash("sha256")
    .update(
      JSON.stringify(
        Object.fromEntries(
          Object.entries(action).sort(([a], [b]) => a.localeCompare(b)),
        ),
      ),
    )
    .digest("hex");
}
export function freezeKey(action: NodeAction): string {
  return `${action.node_id}~${action.idempotency_key}`;
}
export function permitsUnknownApp(action: NodeAction): boolean {
  return (
    action.allow_interrupt &&
    (action.action === "node.reboot" ||
      (action.node_id === "ai-harness" &&
        action.service_id === "harness" &&
        ["service.stop", "service.restart"].includes(action.action)))
  );
}
/** Fixed shared durable gate, outside all engine mounts. The UDS is only an
 * acknowledgement seam, never an alternate lifecycle owner. */
export class DispatchFreeze {
  readonly db: DatabaseSync;
  constructor(
    database: string,
    readonly socket = DISPATCH_SOCKET,
  ) {
    this.db = new DatabaseSync(database);
    this.db.exec(
      "PRAGMA synchronous=FULL; PRAGMA busy_timeout=100; CREATE TABLE IF NOT EXISTS dispatch_holds(key TEXT PRIMARY KEY,fingerprint TEXT NOT NULL,action TEXT NOT NULL,acknowledged INTEGER NOT NULL DEFAULT 0,scope TEXT NOT NULL)",
    );
    chmodSync(database, 0o600);
  }
  held(serviceId?: string): boolean {
    try {
      if (!serviceId)
        return !!this.db.prepare("SELECT 1 FROM dispatch_holds LIMIT 1").get();
      const service =
        (
          {
            "qwen3.8-27b-gpu0": "qwen-gpu0",
            "qwen3.8-27b": "qwen-gpu1",
          } as Record<string, string>
        )[serviceId] ?? serviceId;
      return this.db
        .prepare("SELECT scope,action FROM dispatch_holds")
        .all()
        .some((row) => {
          const scope = JSON.parse(String(row.scope)) as string[];
          // Whole-node reboot also gates the independently routed frontier.
          // Keep the existing canonical action/ack scope byte-for-byte unchanged:
          // this adds no frontier lifecycle operation or settlement authority.
          if (service === "glm-5.3-flash") {
            const action = JSON.parse(String(row.action)) as NodeAction;
            if (action.node_id === "ai-vm" && action.action === "node.reboot") return true;
          }
          return scope.includes(service) || scope.includes("harness");
        });
    } catch {
      return true;
    } // Never turn a failed gate read into permission.
  }
  hold(value: NodeAction, affected?: string[]): void {
    const action = validateAction(value),
      key = freezeKey(action),
      fingerprint = actionFingerprint(action),
      scope = actionScope(action, affected);
    this.db.exec("BEGIN IMMEDIATE");
    try {
      const row = this.db
        .prepare("SELECT fingerprint,scope FROM dispatch_holds WHERE key=?")
        .get(key);
      if (
        row &&
        (row.fingerprint !== fingerprint || row.scope !== JSON.stringify(scope))
      )
        throw new ApiError(
          409,
          "freeze_conflict",
          "Action key already belongs to another request",
        );
      if (!row)
        this.db
          .prepare("INSERT INTO dispatch_holds VALUES(?,?,?,0,?)")
          .run(key, fingerprint, JSON.stringify(action), JSON.stringify(scope));
      this.db.exec("COMMIT");
    } catch (error) {
      this.db.exec("ROLLBACK");
      throw error;
    }
  }
  verify(value: NodeAction): FreezeAck {
    const action = validateAction(value);
    const row = this.db
      .prepare("SELECT fingerprint,scope FROM dispatch_holds WHERE key=?")
      .get(freezeKey(action));
    if (!row || row.fingerprint !== actionFingerprint(action))
      throw new ApiError(
        409,
        "freeze_missing",
        "Exact durable action hold required",
      );
    return {
      schema_version: 1,
      frozen: true,
      request_fingerprint: actionFingerprint(action),
      owner_key: action.idempotency_key,
      scope: JSON.parse(String(row.scope)) as string[],
      app_state: "acknowledged",
    };
  }
  release(action: NodeAction): void {
    if (
      !this.db
        .prepare("SELECT 1 FROM dispatch_holds WHERE key=?")
        .get(freezeKey(action))
    )
      return;
    this.verify(action);
    this.db
      .prepare("DELETE FROM dispatch_holds WHERE key=? AND fingerprint=?")
      .run(freezeKey(action), actionFingerprint(action));
  }
  private call(
    method: "GET" | "POST",
    route: string,
    value?: unknown,
  ): Promise<unknown> {
    return new Promise((resolve, reject) => {
      const body = value === undefined ? undefined : JSON.stringify(value);
      const req = request(
        {
          socketPath: this.socket,
          path: route,
          method,
          agent: false,
          signal: AbortSignal.timeout(1500),
          headers: body
            ? {
                "Content-Type": "application/json",
                "Content-Length": Buffer.byteLength(body),
              }
            : {},
        },
        (res) => {
          const chunks: Buffer[] = [];
          let bytes = 0;
          res.on("data", (chunk: Buffer) => {
            bytes += chunk.length;
            if (bytes > 16384) {
              res.destroy();
              reject(Error("Invalid freeze response"));
            } else chunks.push(chunk);
          });
          res.on("error", reject);
          res.on("end", () => {
            try {
              if (res.statusCode !== 200) throw Error("Freeze unavailable");
              resolve(JSON.parse(Buffer.concat(chunks).toString()));
            } catch (error) {
              reject(error);
            }
          });
        },
      );
      req.on("error", reject);
      req.end(body);
    });
  }
  async acknowledge(action: NodeAction): Promise<FreezeAck> {
    const expected = this.verify(action);
    if (
      !expected.scope.some((id) =>
        ["harness", "qwen-gpu0", "qwen-gpu1", "image"].includes(id),
      )
    ) {
      this.db
        .prepare("UPDATE dispatch_holds SET acknowledged=1 WHERE key=?")
        .run(freezeKey(action));
      return { ...expected, app_state: "not_affected" };
    }
    try {
      const value = (await this.call(
        "POST",
        "/private/freeze/verify",
        action,
      )) as FreezeAck;
      if (
        value.schema_version !== 1 ||
        value.frozen !== true ||
        value.request_fingerprint !== expected.request_fingerprint ||
        value.owner_key !== expected.owner_key ||
        value.app_state !== "acknowledged" ||
        JSON.stringify(value.scope) !== JSON.stringify(expected.scope)
      )
        throw Error("Invalid acknowledgement");
      return value;
    } catch {
      if (permitsUnknownApp(action))
        return { ...expected, app_state: "unreachable_confirmed" };
      throw new ApiError(
        503,
        "freeze_ack_unavailable",
        "App work state unknown; protected freeze acknowledgement required",
      );
    }
  }
  async settle(action: NodeAction): Promise<void> {
    const scope =
      action.action === "service.start"
        ? actionScope(action)
        : this.verify(action).scope;
    if (
      !scope.some((id) =>
        ["harness", "qwen-gpu0", "qwen-gpu1", "image"].includes(id),
      )
    )
      return;
    await this.call("POST", "/private/freeze/reconcile", action);
  }
  async inspect(): Promise<FreezeImpact> {
    try {
      const value = (await this.call(
        "GET",
        "/private/freeze/impact",
      )) as FreezeImpact;
      if (
        !["idle", "busy", "unknown"].includes(value.activity) ||
        typeof value.ready !== "boolean" ||
        ![value.active_requests, value.queue_depth].every(
          (v) => v === null || (Number.isSafeInteger(v) && v >= 0),
        )
      )
        throw Error("Invalid impact");
      return { ...value, frozen: this.held() };
    } catch {
      return {
        frozen: this.held(),
        ready: false,
        activity: "unknown",
        active_requests: null,
        queue_depth: null,
      };
    }
  }
  close() {
    this.db.close();
  }
}

function protectedDirectory(directory: string) {
  const uid = process.getuid?.();
  if (uid === undefined || uid === 0 || realpathSync(directory) !== directory)
    throw Error("Unsafe dispatch directory");
  const metadata = lstatSync(directory);
  if (
    !metadata.isDirectory() ||
    metadata.isSymbolicLink() ||
    metadata.uid !== uid ||
    (metadata.mode & 0o777) !== 0o700
  )
    throw Error("Unsafe dispatch directory");
  for (
    let ancestor = path.dirname(directory);
    ;
    ancestor = path.dirname(ancestor)
  ) {
    const stat = lstatSync(ancestor);
    if (
      !stat.isDirectory() ||
      stat.isSymbolicLink() ||
      stat.uid !== 0 ||
      stat.mode & 0o022
    )
      throw Error("Unsafe dispatch ancestry");
    if (ancestor === "/") break;
  }
}
export function openDispatchFreeze(): DispatchFreeze {
  protectedDirectory(path.dirname(DISPATCH_STATE));
  protectedDirectory(path.dirname(DISPATCH_SOCKET));
  for (const suffix of ["", "-journal", "-wal", "-shm"]) {
    try {
      const stat = lstatSync(DISPATCH_STATE + suffix);
      if (
        !stat.isFile() ||
        stat.isSymbolicLink() ||
        stat.nlink !== 1 ||
        stat.uid !== process.getuid?.() ||
        stat.mode & 0o077
      )
        throw Error("Unsafe dispatch state");
    } catch (error) {
      if (!suffix || (error as NodeJS.ErrnoException).code !== "ENOENT")
        throw error;
    }
  }
  const existing = new DatabaseSync(DISPATCH_STATE, { readOnly: true });
  try {
    if (
      !existing
        .prepare(
          "SELECT name FROM sqlite_master WHERE type='table' AND name='dispatch_holds'",
        )
        .get()
    )
      throw Error(
        "Dispatch state requires explicit first deployment initialization",
      );
  } finally {
    existing.close();
  }
  return new DispatchFreeze(DISPATCH_STATE);
}
/** Only main opens this UDS. No routes are registered on chat/gateway Fastify. */
export async function removeStaleDispatchSocket(socket: string): Promise<void> {
  let prior;
  try {
    prior = lstatSync(socket);
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return;
    throw error;
  }
  if (
    !prior.isSocket() ||
    prior.isSymbolicLink() ||
    prior.uid !== process.getuid?.() ||
    prior.mode & 0o077
  )
    throw Error("Unsafe dispatch socket");
  const refused = await new Promise<boolean>((resolve) => {
    const probe = createConnection({ path: socket });
    probe.setTimeout(500);
    probe.once("connect", () => {
      probe.destroy();
      resolve(false);
    });
    probe.once("timeout", () => {
      probe.destroy();
      resolve(false);
    });
    probe.once("error", (error: NodeJS.ErrnoException) => {
      probe.destroy();
      resolve(error.code === "ECONNREFUSED");
    });
  });
  if (!refused) throw Error("Dispatch socket owner still live or unknown");
  const current = lstatSync(socket);
  if (
    !current.isSocket() ||
    current.dev !== prior.dev ||
    current.ino !== prior.ino ||
    current.uid !== prior.uid ||
    current.mode !== prior.mode
  )
    throw Error("Dispatch socket identity changed");
  unlinkSync(socket);
}
export async function serveDispatchFreeze(
  gate: DispatchFreeze,
  impact: () => FreezeImpact,
  changed: () => void,
  reconcile: (scope: string[]) => boolean = () => false,
) {
  const app = Fastify({ logger: false, bodyLimit: 8192, requestTimeout: 2000 });
  app.setErrorHandler((error, _req, reply) =>
    reply
      .code(error instanceof ApiError ? error.statusCode : 503)
      .send({ error: "freeze_unavailable" }),
  );
  app.get("/private/freeze/impact", async () => impact());
  app.post("/private/freeze/verify", async (req) => {
    const action = validateAction(req.body),
      ack = gate.verify(action);
    changed(); // Observe the durable gate before acknowledging to the owner.
    gate.db
      .prepare(
        "UPDATE dispatch_holds SET acknowledged=1 WHERE key=? AND fingerprint=?",
      )
      .run(freezeKey(action), ack.request_fingerprint);
    return ack;
  });
  app.post("/private/freeze/reconcile", async (req) => {
    const action = validateAction(req.body);
    if (
      !["service.start", "service.restart", "node.reboot"].includes(
        action.action,
      )
    )
      throw new ApiError(
        409,
        "settlement_proof_required",
        "Completed canonical restart required",
      );
    const row = gate.db
      .prepare(
        "SELECT request,receipt,owner_id,dispatched FROM admin_relay_operations WHERE request_key=?",
      )
      .get(`${action.node_id}:${action.idempotency_key}`);
    if (
      !row ||
      !row.owner_id ||
      row.dispatched !== 1 ||
      actionFingerprint(JSON.parse(String(row.request))) !==
        actionFingerprint(action) ||
      JSON.parse(String(row.receipt)).status !== "succeeded"
    )
      throw new ApiError(
        409,
        "settlement_proof_required",
        "Exact completed canonical operation proof required",
      );
    let scope: string[];
    if (action.action === "service.start") {
      // A start alone cannot settle old work. Require the exact outstanding
      // canonical stop and its still-held scope before permitting lane recovery.
      const stopped = gate.db
        .prepare(
          "SELECT request,receipt,owner_id,dispatched,released FROM admin_relay_operations WHERE released=0",
        )
        .all()
        .find((previous) => {
          const old = JSON.parse(String(previous.request)) as NodeAction;
          return (
            previous.owner_id &&
            previous.dispatched === 1 &&
            old.node_id === action.node_id &&
            old.service_id === action.service_id &&
            old.action === "service.stop" &&
            JSON.parse(String(previous.receipt)).status === "succeeded"
          );
        });
      if (!stopped)
        throw new ApiError(
          409,
          "settlement_proof_required",
          "Outstanding completed canonical stop required before start recovery",
        );
      scope = gate.verify(
        JSON.parse(String(stopped.request)) as NodeAction,
      ).scope;
    } else scope = gate.verify(action).scope;
    // The local process owner cannot attest remote backend invocation death.
    const upstreamScope =
      action.node_id === "ai-vm"
        ? scope.filter((id) => ["qwen-gpu0", "qwen-gpu1", "image"].includes(id))
        : [];
    if (upstreamScope.length && !reconcile(upstreamScope))
      throw new ApiError(
        409,
        "active_work_unsettled",
        "Active request still owns settlement; hold retained",
      );
    return { reconciled: true };
  });
  await removeStaleDispatchSocket(gate.socket);
  await app.listen({ path: gate.socket });
  chmodSync(gate.socket, 0o600);
  return app;
}
