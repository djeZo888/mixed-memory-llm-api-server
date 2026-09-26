import { randomUUID } from "node:crypto";
import type { DatabaseSync } from "node:sqlite";
import { ApiError } from "./errors.js";
import { NodeResponseError, type NodeBackend } from "./node-client.js";
import {
  record,
  validateAction,
  sanitizeNode,
  sanitizeOperation,
  type NodeAction,
  type NodeId,
  type NodeSnapshot,
} from "./node-contract.js";

export interface AdminFreeze {
  hold(action: NodeAction, scope?: string[]): void;
  acknowledge(action: NodeAction): Promise<unknown>;
  release(action: NodeAction): void;
  settle(action: NodeAction): Promise<void>;
  inspect(): Promise<{
    frozen: boolean;
    activity: "unknown" | "idle" | "busy";
    active_requests: number | null;
    queue_depth: number | null;
    ready?: boolean;
  }>;
}
type Receipt = ReturnType<typeof sanitizeOperation>;
type Row = {
  scope: string;
  id: string;
  request: string;
  fingerprint: string;
  receipt: string;
  owner_id: string | null;
  dispatched: number;
  released: number;
};
const canonical = (action: NodeAction) =>
  JSON.stringify(
    Object.fromEntries(
      Object.entries(action).sort(([a], [b]) => a.localeCompare(b)),
    ),
  );
const targetServices = (
  action: NodeAction,
  snapshot: NodeSnapshot,
): string[] =>
  action.service_id
    ? [action.service_id]
    : action.gpu_uuid
      ? (snapshot.gpus.find((g) => g.uuid === action.gpu_uuid)
          ?.affected_services ?? [])
      : snapshot.services.map((s) => s.service_id);
export function dispatchScope(
  action: Pick<NodeAction, "node_id" | "action" | "service_id" | "gpu_uuid">,
  node: NodeSnapshot,
): string[] {
  if (action.action === "node.reboot")
    return action.node_id === "ai-harness"
      ? ["harness"]
      : ["qwen-gpu0", "qwen-gpu1", "image"];
  if (action.gpu_uuid)
    return (
      node.gpus.find((g) => g.uuid === action.gpu_uuid)?.affected_services ?? []
    );
  return action.service_id ? [action.service_id] : [];
}
const overlaps = (a: string[], b: string[]) =>
  a.includes("harness") ||
  b.includes("harness") ||
  a.some((id) => b.includes(id));
const covers = (scope: string[], previous: string[]) =>
  scope.includes("harness") || previous.every((id) => scope.includes(id));
const settled = (status: string) =>
  ["succeeded", "failed", "interrupted"].includes(status);
const diagnosticCodes = new Set([
  "invalid_action", "freeze_conflict", "freeze_missing", "freeze_scope_unknown",
  "freeze_ack_unavailable", "node_target_unknown", "node_action_conflict",
  "node_action_unsupported", "node_unavailable", "node_transport_error",
]);
type DispatchPhase = "freeze_hold" | "freeze_acknowledge" | "advisory_status" |
  "advisory_check" | "owner_request" | "owner_receipt";

/** Protected durable relay journal. Node owners retain final lease/CAS authority.
 * A recorded dispatch is never posted again, including after a transport loss or
 * daemon restart. Background reconciliation only reads exact owner receipts. */
export class AdminActions {
  private readonly running = new Set<NodeId>();
  private readonly observing = new Set<string>();
  private timer?: NodeJS.Timeout;
  constructor(
    private readonly options: {
      db: DatabaseSync;
      freeze: AdminFreeze;
      backends: Record<NodeId, NodeBackend>;
      autoPoll?: boolean;
      deadlineMs?: number;
      now?: () => number;
    },
  ) {
    options.db.exec(
      "CREATE TABLE IF NOT EXISTS admin_relay_operations(id TEXT PRIMARY KEY, request_key TEXT UNIQUE NOT NULL, fingerprint TEXT NOT NULL, request TEXT NOT NULL, scope TEXT NOT NULL, receipt TEXT NOT NULL, owner_id TEXT, dispatched INTEGER NOT NULL DEFAULT 0, released INTEGER NOT NULL DEFAULT 0, release_reason TEXT, released_by TEXT)",
    );
    // Protected diagnostics for future failures only. Never backfill old receipts
    // or expose exception messages, bodies, stacks, or credentials in this table.
    options.db.exec(
      "CREATE TABLE IF NOT EXISTS admin_relay_failures(id TEXT PRIMARY KEY, phase TEXT NOT NULL, attempted INTEGER NOT NULL, error_code TEXT, status_code INTEGER, node_error_code TEXT, node_status_code INTEGER)",
    );
    for (const row of this.rows()) {
      const receipt = JSON.parse(row.receipt) as Receipt;
      if (["accepted", "running"].includes(receipt.status))
        this.update(row.id, {
          ...receipt,
          status: "unknown",
          reason: "helper_restarted_no_replay",
        });
    }
    if (options.autoPoll !== false)
      this.timer = setInterval(() => {
        void this.refresh();
      }, 5000).unref();
  }
  private rows() {
    return this.options.db
      .prepare("SELECT * FROM admin_relay_operations")
      .all() as unknown as Row[];
  }
  private row(id: string) {
    return this.options.db
      .prepare("SELECT * FROM admin_relay_operations WHERE id=?")
      .get(id) as unknown as Row | undefined;
  }
  private timestamp() {
    return new Date((this.options.now ?? Date.now)()).toISOString();
  }
  private update(id: string, receipt: Receipt, ownerId?: string) {
    this.options.db
      .prepare(
        "UPDATE admin_relay_operations SET receipt=?, owner_id=COALESCE(?,owner_id) WHERE id=?",
      )
      .run(
        JSON.stringify({ ...receipt, updated_at: this.timestamp() }),
        ownerId ?? null,
        id,
      );
  }
  private signal() {
    return AbortSignal.timeout(this.options.deadlineMs ?? 2000);
  }
  private async node(action: NodeAction) {
    return sanitizeNode(
      await this.options.backends[action.node_id].status(this.signal()),
      action.node_id,
    );
  }
  private check(action: NodeAction, node: NodeSnapshot) {
    const target = action.service_id
      ? node.services.find((s) => s.service_id === action.service_id)
      : action.gpu_uuid
        ? node.gpus.find((g) => g.uuid === action.gpu_uuid)
        : node;
    if (
      node.freshness !== "fresh" ||
      node.age_ms === null ||
      node.age_ms >= 15000 ||
      !target ||
      target.freshness !== "fresh" ||
      target.age_ms === null ||
      target.age_ms >= 15000 ||
      node.boot_id === null ||
      target.generation === null
    )
      throw new ApiError(
        503,
        "node_target_unknown",
        "Current action target is unknown; refresh its observations",
      );
    if (
      node.boot_id !== action.expected_boot_id ||
      target.generation !== action.expected_generation
    )
      throw new ApiError(
        409,
        "node_action_conflict",
        "Target boot or generation changed; refresh targets and confirm again",
      );
  }
  async submit(action: NodeAction): Promise<Receipt> {
    const fingerprint = canonical(action),
      key = `${action.node_id}:${action.idempotency_key}`;
    // Lookup precedes CAS and live observations: exact repeats survive target changes.
    const previous = this.options.db
      .prepare("SELECT * FROM admin_relay_operations WHERE request_key=?")
      .get(key) as unknown as Row | undefined;
    if (previous) {
      if (previous.fingerprint !== fingerprint)
        throw new ApiError(
          409,
          "idempotency_conflict",
          "Action key belongs to a different action",
        );
      return JSON.parse(previous.receipt) as Receipt;
    }
    if (action.action !== "service.start" && !action.allow_interrupt)
      throw new ApiError(
        409,
        "interrupt_required",
        "Explicit interruption confirmation is required, including unknown affected work",
      );
    if (this.running.has(action.node_id))
      throw new ApiError(
        503,
        "node_admission_busy",
        "Another node admission is pending",
      );
    if (this.rows().length >= 10000)
      throw new ApiError(
        503,
        "operation_capacity",
        "Protected operation journal requires reviewed archival",
      );
    this.running.add(action.node_id);
    try {
      const node = await this.node(action);
      this.check(action, node);
      const scope = dispatchScope(action, node);
      const conflict = this.rows().some((row) => {
        const request = JSON.parse(row.request) as NodeAction,
          receipt = JSON.parse(row.receipt) as Receipt,
          previousScope = JSON.parse(row.scope) as string[];
        if (
          request.node_id !== action.node_id ||
          row.released ||
          settled(receipt.status) ||
          !overlaps(scope, previousScope)
        )
          return false;
        // A new explicitly confirmed canonical restart/reboot may reconcile the
        // previous unknown invocation. It has a NEW key; no uncertain POST replay.
        return !(
          receipt.status === "unknown" &&
          action.allow_interrupt &&
          ["service.restart", "node.reboot"].includes(action.action) &&
          covers(scope, previousScope)
        );
      });
      if (conflict)
        throw new ApiError(
          503,
          "target_admission_busy",
          "An affected target operation is active or requires a confirmed recovery restart",
        );
      const id = `relay-${randomUUID()}`;
      const receipt = sanitizeOperation(
        {
          schema_version: 1,
          node_id: action.node_id,
          operation_id: id,
          action: action.action,
          status: "accepted",
          affected_services: targetServices(action, node),
          created_at: this.timestamp(),
          updated_at: this.timestamp(),
        },
        action.node_id,
      );
      this.options.db
        .prepare(
          "INSERT INTO admin_relay_operations(id,request_key,fingerprint,request,scope,receipt) VALUES(?,?,?,?,?,?)",
        )
        .run(
          id,
          key,
          fingerprint,
          JSON.stringify(action),
          JSON.stringify(scope),
          JSON.stringify(receipt),
        );
      // Admission is durable before freeze/owner I/O. Dispatch never runs in GET.
      void this.dispatch(id, action);
      return receipt;
    } catch (error) {
      this.running.delete(action.node_id);
      throw error;
    }
  }
  private async dispatch(id: string, action: NodeAction) {
    let attempted = false;
    let phase: DispatchPhase = "advisory_status";
    try {
      if (action.action !== "service.start") {
        phase = "freeze_hold";
        this.options.freeze.hold(action, JSON.parse(this.row(id)!.scope));
        phase = "freeze_acknowledge";
        await this.options.freeze.acknowledge(action);
      }
      // This check is advisory; the canonical owner repeats it under its lease.
      phase = "advisory_status";
      const node = await this.node(action);
      phase = "advisory_check";
      this.check(action, node);
      this.options.db
        .prepare("UPDATE admin_relay_operations SET dispatched=1 WHERE id=?")
        .run(id);
      attempted = true;
      phase = "owner_request";
      const raw = await this.options.backends[action.node_id].action(
        action,
        this.signal(),
      );
      phase = "owner_receipt";
      await this.acceptOwner(id, action, raw);
    } catch (error) {
      this.recordFailure(id, phase, attempted, error);
      const rejected =
        error instanceof ApiError && [400, 409, 422].includes(error.statusCode);
      const receipt = JSON.parse(this.row(id)!.receipt) as Receipt;
      this.update(id, {
        ...receipt,
        status: !attempted || rejected ? "failed" : "unknown",
        reason:
          !attempted || rejected ? "operation_failed" : "owner_timeout_unknown",
      });
      if (!attempted || rejected) {
        // Explicit durable pre-dispatch rejection; no owner mutation occurred.
        this.options.db
          .prepare("UPDATE admin_relay_operations SET dispatched=0 WHERE id=?")
          .run(id);
        this.release(id, action, id, "rejected_before_owner_dispatch");
      }
    } finally {
      this.running.delete(action.node_id);
    }
  }
  private recordFailure(id: string, phase: DispatchPhase, attempted: boolean, error: unknown) {
    try {
      this.options.db.prepare(
        "INSERT OR IGNORE INTO admin_relay_failures(id,phase,attempted,error_code,status_code,node_error_code,node_status_code) VALUES(?,?,?,?,?,?,?)",
      ).run(
        id, phase, attempted ? 1 : 0,
        error instanceof ApiError && diagnosticCodes.has(error.code) ? error.code : null,
        error instanceof ApiError && [400, 404, 409, 422, 503].includes(error.statusCode) ? error.statusCode : null,
        error instanceof NodeResponseError ? error.upstreamCode : null,
        error instanceof NodeResponseError ? error.upstreamStatus : null,
      );
    } catch {
      // Diagnostic storage must not change owner/hold settlement or replay rules.
    }
  }
  private async acceptOwner(id: string, action: NodeAction, raw: unknown) {
    const value = record(raw),
      row = this.row(id)!,
      owner = sanitizeOperation(raw, action.node_id);
    if (
      owner.action !== action.action ||
      (value.service_id ?? null) !== (action.service_id ?? null) ||
      (value.gpu_uuid ?? null) !== (action.gpu_uuid ?? null) ||
      value.expected_boot_id !== action.expected_boot_id ||
      value.expected_generation !== action.expected_generation ||
      (row.owner_id !== null && row.owner_id !== value.operation_id)
    )
      throw Error("Owner receipt identity mismatch");
    const receipt = JSON.parse(row.receipt) as Receipt;
    this.update(
      id,
      {
        ...owner,
        operation_id: receipt.operation_id,
        poll_url: receipt.poll_url,
        created_at: receipt.created_at,
      },
      owner.operation_id.slice(action.node_id.length + 1),
    );
    if (owner.status === "succeeded") {
      try {
        await this.reconcileReady(id, action);
      } catch {
        /* Preserve known owner outcome; readiness/settlement still retains hold. */
      }
    }
  }
  private release(
    id: string,
    action: NodeAction,
    releasedBy = id,
    reason = "validated_owner_readiness",
  ) {
    this.options.freeze.release(action);
    this.options.db
      .prepare(
        "UPDATE admin_relay_operations SET released=1,release_reason=?,released_by=? WHERE id=?",
      )
      .run(reason, releasedBy, id);
  }
  private async ready(action: NodeAction): Promise<boolean> {
    const node = await this.node(action);
    if (
      node.freshness !== "fresh" ||
      node.age_ms === null ||
      node.age_ms >= 15000 ||
      !node.boot_id ||
      (action.action === "node.reboot" &&
        node.boot_id === action.expected_boot_id)
    )
      return false;
    const services =
      action.action === "node.reboot" && action.node_id === "ai-vm"
        ? ["qwen-gpu0", "qwen-gpu1", "image"]
        : targetServices(action, node);
    if (services.length === 0) return false;
    let validatedReady = 0;
    for (const serviceId of services) {
      const service = node.services.find((s) => s.service_id === serviceId);
      // Canonical reboot success plus changed boot settles every old invocation.
      // Each peer keeps its independent availability/fallback/latch gate; an
      // unrelated unknown collector must not hold a fresh ready target hostage.
      const positive =
        !!service &&
        service.freshness === "fresh" &&
        service.age_ms !== null &&
        service.age_ms < 15000 &&
        service.availability === "available" &&
        service.hardware_latched !== true;
      if (!positive) {
        if (action.action === "node.reboot") continue;
        return false;
      }
      const ready =
        action.node_id === "ai-vm"
          ? service!.ready === true
          : await this.options.backends[action.node_id].passiveReady?.(
              serviceId,
              this.signal(),
            );
      if (!ready) {
        if (action.action === "node.reboot") continue;
        return false;
      }
      validatedReady++;
    }
    return validatedReady > 0;
  }
  private async reconcileReady(id: string, action: NodeAction) {
    if (JSON.parse(this.row(id)!.scope).length === 0) {
      this.release(id, action);
      return;
    }
    if (action.action === "service.stop" || !(await this.ready(action))) return;
    const completedStop =
      action.action === "service.start" &&
      this.rows().some((previous) => {
        const old = JSON.parse(previous.request) as NodeAction;
        return (
          !previous.released &&
          old.node_id === action.node_id &&
          old.service_id === action.service_id &&
          old.action === "service.stop" &&
          JSON.parse(previous.receipt).status === "succeeded"
        );
      });
    if (
      ["service.restart", "node.reboot"].includes(action.action) ||
      completedStop
    )
      await this.options.freeze.settle(action);
    this.release(id, action);
    // Canonical successful restart/reboot settles the prior owned invocation;
    // only then does fresh readiness permit releasing its retained admission
    // hold. Old receipts and independent request quarantine are never rewritten.
    const scope = JSON.parse(this.row(id)!.scope) as string[];
    for (const previous of this.rows()) {
      const old = JSON.parse(previous.request) as NodeAction,
        receipt = JSON.parse(previous.receipt) as Receipt;
      if (
        previous.id === id ||
        previous.released ||
        old.node_id !== action.node_id ||
        !covers(scope, JSON.parse(previous.scope))
      )
        continue;
      const restoredStop =
        receipt.status === "succeeded" &&
        old.action === "service.stop" &&
        (action.action === "node.reboot" ||
          old.service_id === action.service_id);
      const settledUnknown =
        ["unknown", "failed", "interrupted"].includes(receipt.status) &&
        ["service.restart", "node.reboot"].includes(action.action);
      if (restoredStop || settledUnknown)
        this.release(
          previous.id,
          old,
          id,
          restoredStop
            ? action.action === "node.reboot"
              ? "changed_boot_reconciled_stop_intent"
              : "matching_stop_validated_start"
            : "canonical_recovery_settled_old_owner",
        );
    }
  }
  async reconcile(
    id: string,
    nodeId: NodeId,
    confirmation: Pick<
      NodeAction,
      | "expected_boot_id"
      | "expected_generation"
      | "allow_interrupt"
      | "idempotency_key"
    >,
  ): Promise<Receipt> {
    const receipt = this.get(id, nodeId),
      row = this.row(id)!;
    if (!confirmation.allow_interrupt)
      throw new ApiError(
        409,
        "reconciliation_confirmation",
        "Explicit interruption confirmation is required for a new recovery restart",
      );
    if (row.released) return receipt;
    if (
      ["accepted", "running"].includes(receipt.status) ||
      this.running.has(nodeId)
    )
      throw new ApiError(
        409,
        "operation_running",
        "The node owner still has an active operation",
      );
    const old = JSON.parse(row.request) as NodeAction;
    if (old.gpu_uuid)
      throw new ApiError(
        409,
        "recovery_target_required",
        "Confirm a registered restart for each affected service, or confirm a whole-node reboot",
      );
    // Recovery is a new typed owner action with fresh confirmation identity.
    // A positive readiness observation alone cannot settle uncertain ownership.
    return this.submit(
      validateAction({
        ...old,
        action: old.service_id ? "service.restart" : "node.reboot",
        ...confirmation,
      }),
    );
  }
  get(id: string, nodeId: NodeId): Receipt {
    const row = this.row(id);
    if (!row)
      throw new ApiError(404, "operation_not_found", "Operation not found");
    const receipt = JSON.parse(row.receipt) as Receipt;
    if (receipt.node_id !== nodeId)
      throw new ApiError(404, "operation_not_found", "Operation not found");
    const action = JSON.parse(row.request) as NodeAction;
    return {
      ...receipt,
      service_id: action.service_id ?? null,
      gpu_uuid: action.gpu_uuid ?? null,
      dispatch_frozen:
        !row.released &&
        action.action !== "service.start" &&
        (JSON.parse(row.scope) as string[]).some((service) =>
          ["harness", "qwen-gpu0", "qwen-gpu1", "image"].includes(service),
        ),
      recovery_action: action.gpu_uuid
        ? null
        : action.service_id
          ? "service.restart"
          : "node.reboot",
    } as Receipt;
  }
  /** Periodic bounded passive reconciliation. No owner POST or automatic replay. */
  async refresh() {
    const rows = this.rows().filter(
      (row) =>
        row.owner_id &&
        !row.released &&
        !(
          JSON.parse(row.receipt).status === "succeeded" &&
          JSON.parse(row.request).action === "service.stop"
        ),
    );
    // At most one passive owner request per node, including across timer ticks.
    // A hung backend never creates replacement requests or growing concurrency.
    await Promise.all(
      (["ai-vm", "ai-harness"] as const).map(async (nodeId) => {
        if (this.observing.has(nodeId)) return;
        this.observing.add(nodeId);
        try {
          for (const row of rows) {
            const action = JSON.parse(row.request) as NodeAction;
            if (action.node_id !== nodeId || this.row(row.id)?.released)
              continue;
            try {
              await this.acceptOwner(
                row.id,
                action,
                await this.options.backends[nodeId].operation(
                  row.owner_id!,
                  this.signal(),
                ),
              );
            } catch {
              /* Retain receipt, freeze and ownership on uncertainty. */
            }
          }
        } finally {
          this.observing.delete(nodeId);
        }
      }),
    );
  }
  close() {
    if (this.timer) clearInterval(this.timer);
  }
}
