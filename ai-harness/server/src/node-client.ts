import { request } from "node:http";
import type { NodeAction, NodeId } from "./node-contract.js";
import type { RegistryNode, SystemRegistry } from "./system-registry.js";
import { ApiError } from "./errors.js";

// Fixed producer vocabulary from scripts/control/node_actions.py ERRORS.
const upstreamCodes = new Set([
  "invalid_request", "operation_unknown", "idempotency_conflict", "stale_state",
  "interruption_ack_required", "lifecycle_busy", "hardware_unavailable",
  "unsupported_action", "owner_unavailable", "storage_unavailable",
  "deadline_exceeded", "observation_unavailable", "invalid_owner_receipt",
  "operation_interrupted", "operation_failed", "reset_scope_unproven",
  "consumers_present", "reboot_pending", "journal_full",
]);
const RESPONSE_LIMIT = 512 * 1024;

/** Internal diagnostics only. Public ApiError fields retain their existing values. */
export class NodeResponseError extends ApiError {
  readonly upstreamStatus: number | null;
  readonly upstreamCode: string | null;
  constructor(upstreamStatus: unknown, upstreamCode: unknown) {
    const observedStatus = typeof upstreamStatus === "number" &&
      Number.isInteger(upstreamStatus) && upstreamStatus >= 100 && upstreamStatus <= 599
      ? upstreamStatus : null;
    const status = [400, 404, 409, 422, 503].includes(observedStatus ?? 0)
      ? observedStatus! : 503;
    super(
      status,
      status === 409 ? "node_action_conflict" : status === 422
        ? "node_action_unsupported" : "node_unavailable",
      status === 409
        ? "Target changed or interruption confirmation required; refresh targets"
        : status === 422
          ? "Action unsupported by the guarded node owner"
          : "Node request unavailable; retain action key and inspect operation status",
    );
    this.upstreamStatus = observedStatus;
    this.upstreamCode = typeof upstreamCode === "string" && upstreamCodes.has(upstreamCode)
      ? upstreamCode : null;
  }
}

/** Parse only a bounded allowlisted error code; never retain the response body. */
export function nodeResponseError(status: unknown, body: Buffer): NodeResponseError {
  let code: unknown = null;
  if (body.length <= RESPONSE_LIMIT) {
    try {
      const value: unknown = JSON.parse(body.toString("utf8"));
      if (value && typeof value === "object" && !Array.isArray(value)) {
        const error = (value as Record<string, unknown>).error;
        if (error && typeof error === "object" && !Array.isArray(error))
          code = (error as Record<string, unknown>).code;
      }
    } catch {
      // Malformed upstream responses still use the unchanged public error.
    }
  }
  return new NodeResponseError(status, code);
}

export interface NodeBackend {
  status(signal: AbortSignal): Promise<unknown>;
  action(action: NodeAction, signal: AbortSignal): Promise<unknown>;
  operation(id: string, signal: AbortSignal): Promise<unknown>;
  passiveReady?(service: string, signal: AbortSignal): Promise<boolean>;
}
/** Shared bounded HTTP mechanics: exact path supplied only by these adapters,
 * redirects are errors and response bodies/credentials are never public. */
function boundedNodeCall(options: { hostname: string; port: number } | { socketPath: string }, credential?: string) {
  return (
    method: string,
    path: string,
    signal: AbortSignal,
    value?: unknown,
  ) =>
    new Promise<unknown>((resolve, reject) => {
      const body = value === undefined ? undefined : JSON.stringify(value);
      const req = request(
        {
          ...options,
          method,
          path,
          signal,
          agent: false,
          headers: {
            Accept: "application/json",
            ...(credential ? { Authorization: `Bearer ${credential}` } : {}),
            ...(body
              ? {
                  "Content-Type": "application/json",
                  "Content-Length": Buffer.byteLength(body),
                }
              : {}),
          },
        },
        (res) => {
          const parts: Buffer[] = [];
          let size = 0;
          res.on("data", (chunk: Buffer) => {
            size += chunk.length;
            if (size > RESPONSE_LIMIT) {
              res.destroy();
              req.destroy();
              reject(Error("Node response too large"));
            } else parts.push(chunk);
          });
          res.on("error", () => reject(Error("Node response unavailable")));
          res.on("end", () => {
            if (
              !res.statusCode ||
              res.statusCode < 200 ||
              res.statusCode >= 300
            ) {
              reject(nodeResponseError(res.statusCode, Buffer.concat(parts)));
              return;
            }
            try {
              resolve(JSON.parse(Buffer.concat(parts).toString("utf8")));
            } catch {
              reject(Error("Invalid node response"));
            }
          });
        },
      );
      req.on("error", () =>
        reject(
          new ApiError(
            503,
            "node_transport_error",
            "Node transport unavailable; action outcome may be unknown",
          ),
        ),
      );
      req.end(body);
    });
}
/** Fixed endpoints only, no redirects, no URLs/paths from callers. Credentials
 * are injected by the protected startup loader, never returned/logged. */
export function nodeClient(nodeId: NodeId, credential?: string): NodeBackend {
  if (nodeId !== "ai-vm" && nodeId !== "ai-harness")
    throw Error("Unsupported node adapter");
  const options =
    nodeId === "ai-vm"
      ? { hostname: "10.156.100.60", port: 30008 }
      : { socketPath: "/run/ai-harness-admin/helper.sock" };
  if (nodeId === "ai-vm" && !credential)
    throw Error("Node control credential required");
  const call = boundedNodeCall(options, credential);
  const passiveReady = async (
    service: string,
    signal: AbortSignal,
  ): Promise<boolean> => {
    if (nodeId !== "ai-harness") return false;
    // This callback executes inside the independent status process itself.
    if (service === "status") return true;
    if (service !== "harness" && service !== "search") return false;
    return new Promise<boolean>((resolve) => {
      const req = request(
        {
          ...(service === "harness"
            ? {
                socketPath: "/run/ai-harness-dispatch/control.sock",
                path: "/private/freeze/impact",
                method: "GET",
              }
            : { hostname: "127.0.0.1", port: 8082, path: "/", method: "HEAD" }),
          signal,
          agent: false,
          headers: {
            Accept: service === "harness" ? "application/json" : "text/html",
          },
        },
        (res) => {
          let size = 0;
          const chunks: Buffer[] = [];
          res.on("data", (chunk: Buffer) => {
            size += chunk.length;
            if (size > 16384) {
              res.destroy();
              resolve(false);
            } else chunks.push(chunk);
          });
          res.on("error", () => resolve(false));
          res.on("end", () => {
            if (res.statusCode !== 200) return resolve(false);
            if (service === "search")
              return resolve(
                String(res.headers["content-type"]).startsWith("text/html"),
              );
            try {
              const impact = JSON.parse(Buffer.concat(chunks).toString("utf8"));
              resolve(
                impact.ready === true && typeof impact.frozen === "boolean",
              );
            } catch {
              resolve(false);
            }
          });
        },
      );
      req.on("error", () => resolve(false));
      req.end();
    });
  };
  return {
    passiveReady,
    status: (signal) => call("GET", "/control/v1/node/status", signal),
    action: (value, signal) =>
      call("POST", "/control/v1/node/actions", signal, value),
    operation: (id, signal) => {
      if (!/^[a-zA-Z0-9_.:-]{1,128}$/.test(id))
        throw new ApiError(400, "invalid_operation", "Invalid operation ID");
      return call("GET", `/control/v1/node/operations/${id}`, signal);
    },
  };
}

/** Registry-selected passive adapter: no mutation methods for generic nodes. */
export function nodeObserver(node: RegistryNode, registry: SystemRegistry,
  credentials: Readonly<Record<string, string>> = {}): Pick<NodeBackend, "status"> {
  if (node.observation.adapter === "unsupported" && node.observation.transport === null)
    return { status: async () => ({ schema_version: 1, node_id: node.id, reason: "unsupported" }) };
  const transport = registry.transports.find(t => t.id === node.observation.transport);
  if (node.observation.adapter !== "node-v1" || !transport || (transport.kind === "local-helper" && node.id !== "ai-harness"))
    throw Error("Unsupported node binding");
  if (transport.credential_ref === "control-api-key" && (node.id !== "ai-vm" || transport.kind !== "private-http" || transport.host !== "10.156.100.60" || transport.port !== 30008))
    throw Error("Node credential scope mismatch");
  const credential = transport.credential_ref && Object.hasOwn(credentials, transport.credential_ref) ? credentials[transport.credential_ref] : undefined;
  if (transport.credential_ref && !credential) throw Error("Node control credential required");
  const call = boundedNodeCall(transport.kind === "private-http"
    ? { hostname: transport.host!, port: transport.port! } : { socketPath: transport.socket_path! }, credential);
  return { status: signal => call("GET", "/control/v1/node/status", signal) };
}
