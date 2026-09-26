/** H005 root-frozen v1. Wire authority is Worker1's shared contract; this module
 * only validates consumed fields and creates a public allowlisted projection. */
import { ApiError } from "./errors.js";
export const NODE_IDS = ["ai-vm", "ai-harness"] as const;
export type NodeId = (typeof NODE_IDS)[number];
export const SERVICE_IDS = {
  "ai-vm": ["qwen-gpu0", "qwen-gpu1", "image", "control"],
  "ai-harness": ["harness", "search", "status"],
} as const;
export const ACTIONS = [
  "service.start",
  "service.stop",
  "service.restart",
  "gpu.reset",
  "node.reboot",
] as const;
export type NodeAction = {
  schema_version: 1;
  node_id: NodeId;
  action: (typeof ACTIONS)[number];
  service_id?: string;
  gpu_uuid?: string;
  idempotency_key: string;
  expected_boot_id: string;
  expected_generation: number;
  allow_interrupt: boolean;
};
export const record = (v: unknown): Record<string, unknown> =>
  v !== null && typeof v === "object" && !Array.isArray(v)
    ? (v as Record<string, unknown>)
    : {};
const str = (v: unknown, max = 128): string | null =>
  typeof v === "string" && v.length <= max && /^[\x20-\x7e]+$/.test(v)
    ? v
    : null;
const identifier = (v: unknown): string | null =>
  typeof v === "string" && /^[a-zA-Z0-9_.:-]{1,128}$/.test(v) ? v : null;
const number = (v: unknown): number | null =>
  typeof v === "number" && Number.isFinite(v) && v >= 0 ? v : null;
const integer = (v: unknown): number | null =>
  Number.isSafeInteger(v) && Number(v) >= 0 ? Number(v) : null;
const bool = (v: unknown): boolean | null =>
  typeof v === "boolean" ? v : null;
const date = (v: unknown): string | null =>
  typeof v === "string" &&
  /^\d{4}-\d\d-\d\dT[\d:.]+(?:Z|[+-]\d\d:\d\d)$/.test(v) &&
  Number.isFinite(Date.parse(v))
    ? v
    : null;
const reasons = new Set([
  "hardware_latched",
  "hardware_missing",
  "gpu_missing",
  "gpu_fault",
  "hardware_fault",
  "boot_hardware_latch",
  "service_stopped",
  "service_failed",
  "not_ready",
  "not_admitting",
  "unknown",
  "timeout",
  "transport_error",
  "unavailable",
  "stale",
  "observer_error",
  "unsupported",
  "interrupt_required",
  "generation_conflict",
  "boot_conflict",
  "operation_failed",
  "restarted",
  "interrupted",
  "activity_unknown",
  "ready",
  "stopped",
  "loading",
  "not_installed",
  "storage_unavailable",
  "lease_busy",
  "reboot_pending",
  "request_quarantined",
  "observation_unavailable",
  "not_observed",
  "service_observation_unavailable",
  "resource_observation_unavailable",
  "resource_observation_timeout",
  "helper_restarted_no_replay",
  "owner_timeout_unknown",
  "owner_failed_unknown",
  "owner_error_unknown",
  "dispatch_observation_unavailable",
  "confirmation_stale",
  "reboot_awaiting_changed_boot",
  "local_admission_interlock_unavailable",
  "registration_unknown",
  "mount_identity_unavailable",
  "capacity_unavailable",
]);
export const reason = (v: unknown) =>
  typeof v === "string" && reasons.has(v) ? v : v == null ? null : "unknown";
const enumValue = <T extends string>(
  v: unknown,
  values: readonly T[],
  fallback: T,
): T => (values.includes(v as T) ? (v as T) : fallback);
export function observation(raw: unknown) {
  const v = record(raw);
  return {
    state: enumValue(
      v.state,
      ["ok", "unknown", "error", "timeout"] as const,
      "unknown",
    ),
    observed_at: date(v.observed_at),
    age_ms: number(v.age_ms),
    freshness: enumValue(
      date(v.observed_at) !== null && number(v.age_ms) !== null ? v.freshness : "unknown",
      ["fresh", "stale", "unknown"] as const,
      "unknown",
    ),
    reason: reason(v.reason),
  };
}
const resourceFields = {
  cpu: ["percent", "logical_count"],
  memory: [
    "total_bytes",
    "available_bytes",
    "swap_total_bytes",
    "swap_free_bytes",
    "pressure_some_avg10",
    "pressure_full_avg10",
  ],
  disk: [
    "total_bytes",
    "available_bytes",
    "read_bytes_per_second",
    "write_bytes_per_second",
  ],
  network: ["rx_bytes_per_second", "tx_bytes_per_second"],
} as const;
export function diskVolumes(raw: unknown) {
  if (!Array.isArray(raw)) return [];
  const entries = raw.slice(0, 3).map(record);
  if (new Set(entries.map((v) => v.volume_id)).size !== entries.length)
    return [];
  return entries
    .filter((v) => ["root", "data", "models"].includes(String(v.volume_id)))
    .map((v) => ({
      ...observation(v),
      volume_id: v.volume_id as string,
      state: enumValue(
        v.state,
        ["ok", "unknown", "unavailable"] as const,
        "unknown",
      ),
      reason: [
        "registration_unknown",
        "mount_identity_unavailable",
        "capacity_unavailable",
      ].includes(String(v.reason))
        ? String(v.reason)
        : v.reason == null
          ? null
          : "registration_unknown",
      mount_point:
        typeof v.mount_point === "string" &&
        /^\/[a-zA-Z0-9_./-]*$/.test(v.mount_point) &&
        v.mount_point.length <= 256
          ? v.mount_point
          : null,
      filesystem_uuid: identifier(v.filesystem_uuid),
      filesystem_type: identifier(v.filesystem_type),
      total_bytes: v.state === "ok" ? number(v.total_bytes) : null,
      available_bytes: v.state === "ok" ? number(v.available_bytes) : null,
      read_bytes_per_second:
        v.state === "ok" ? number(v.read_bytes_per_second) : null,
      write_bytes_per_second:
        v.state === "ok" ? number(v.write_bytes_per_second) : null,
    }));
}
export function sanitizeNode(raw: unknown, nodeId: string, serviceIds: readonly string[] =
  Object.hasOwn(SERVICE_IDS, nodeId) ? SERVICE_IDS[nodeId as NodeId] : []) {
  const v = record(raw);
  if (v.schema_version !== 1 || v.node_id !== nodeId)
    throw Error("Invalid node snapshot");
  const inventory = record(v.inventory);
  const gpuId = (id: unknown): id is string =>
    typeof id === "string" && /^GPU-[0-9a-f-]{36}$/i.test(id);
  const rawUuids = inventory.gpu_uuids;
  const rawFaults = inventory.hardware_faults;
  const inventoryValid =
    Array.isArray(rawUuids) &&
    rawUuids.every(gpuId) &&
    new Set(rawUuids).size === rawUuids.length &&
    rawFaults !== null &&
    typeof rawFaults === "object" &&
    !Array.isArray(rawFaults) &&
    Object.entries(rawFaults).every(
      ([id, code]) => gpuId(id) && typeof code === "string" && code.length > 0,
    );
  const services = (Array.isArray(v.services) ? v.services : [])
    .map(record)
    .filter((s) =>
      (serviceIds as readonly unknown[]).includes(s.service_id),
    )
    .map((s) => ({
      ...observation(s),
      service_id: s.service_id as string,
      generation: integer(s.generation),
      affected_services: (Array.isArray(s.affected_services)
        ? s.affected_services
        : []
      ).filter((id) =>
        (serviceIds as readonly unknown[]).includes(id),
      ) as string[],
      installed_capabilities: (Array.isArray(s.installed_capabilities)
        ? s.installed_capabilities
        : []
      ).filter((c) =>
        [
          "chat.completions",
          "images.generations",
          "images.edits",
          "model.control",
          "node.status",
          "node.actions",
          "search",
          "chat",
          "gateway",
        ].includes(String(c)),
      ) as string[],
      availability: enumValue(
        s.availability,
        ["available", "unavailable", "unknown"] as const,
        "unknown",
      ),
      ready: bool(s.ready),
      admitting: bool(s.admitting),
      required_gpu_uuids: (Array.isArray(s.required_gpu_uuids)
        ? s.required_gpu_uuids
        : []
      ).filter(
        (u) => typeof u === "string" && /^GPU-[0-9a-f-]{36}$/i.test(u),
      ) as string[],
      hardware_latched: bool(s.hardware_latched),
      hardware_latched_boot_id: identifier(s.hardware_latched_boot_id),
      activity: enumValue(
        s.activity,
        ["idle", "busy", "unknown"] as const,
        "unknown",
      ),
      queue_depth: integer(s.queue_depth),
      active_requests: integer(s.active_requests),
      model_alias: identifier(s.model_alias),
      deployment_id: identifier(s.deployment_id),
      configured_context_tokens: integer(s.configured_context_tokens),
      max_output_tokens: integer(s.max_output_tokens),
      operation_profiles: (Array.isArray(s.operation_profiles)
        ? s.operation_profiles
        : []
      )
        .slice(0, 32)
        .map((p) => {
          const q = record(p);
          return {
            operation: enumValue(
              q.operation,
              ["generation", "edit", "unknown"] as const,
              "unknown",
            ),
            size:
              typeof q.size === "string" && /^\d{3,4}x\d{3,4}$/.test(q.size)
                ? q.size
                : null,
            references: integer(q.references),
            transparent: bool(q.transparent),
          };
        }),
    }));
  if (new Set(services.map((s) => s.service_id)).size !== services.length)
    throw Error("Ambiguous services");
  const gpus = (Array.isArray(v.gpus) ? v.gpus : [])
    .slice(0, 32)
    .map(record)
    .filter(
      (g) => typeof g.uuid === "string" && /^GPU-[0-9a-f-]{36}$/i.test(g.uuid),
    )
    .map((g) => ({
      ...observation(g),
      uuid: g.uuid as string,
      generation: integer(g.generation),
      name: str(g.name),
      index: integer(g.index),
      pci_bus_id: identifier(g.pci_bus_id),
      ...Object.fromEntries(
        [
          "memory_total_mib",
          "memory_used_mib",
          "temperature_c",
          "ecc_uncorrected_volatile",
          "pcie_generation",
          "pcie_width",
          "pcie_generation_max",
          "pcie_width_max",
          "power_draw_w",
          "power_limit_w",
          "temperature_min_c",
          "temperature_max_c",
        ].map((k) => [k, number(g[k])]),
      ),
      ecc_mode: ["enabled", "disabled", "Enabled", "Disabled"].includes(
        String(g.ecc_mode),
      )
        ? String(g.ecc_mode)
        : null,
      sampling_since: date(g.sampling_since),
      reset_supported: bool(g.reset_supported),
      affected_services: (Array.isArray(g.affected_services)
        ? g.affected_services
        : []
      ).filter((s) =>
        (serviceIds as readonly unknown[]).includes(s),
      ) as string[],
    }));
  const resources = record(v.resources);
  return {
    schema_version: 1 as const,
    node_id: nodeId,
    boot_id: identifier(v.boot_id),
    generation: integer(v.generation),
    affected_services: (Array.isArray(v.affected_services)
      ? v.affected_services
      : []
    ).filter((id) =>
      (serviceIds as readonly unknown[]).includes(id),
    ) as string[],
    ...observation(v),
    inventory: {
      ...observation(inventory),
      ...(!inventoryValid ? { state: "unknown" as const } : {}),
      boot_id: identifier(inventory.boot_id),
      complete: inventory.complete === true && inventoryValid,
      observation_id: identifier(inventory.observation_id),
      gpu_uuids: (Array.isArray(inventory.gpu_uuids)
        ? inventory.gpu_uuids
        : []
      ).filter(gpuId),
      hardware_faults: Object.fromEntries(
        Object.entries(record(inventory.hardware_faults))
          .filter(([uuid]) => gpuId(uuid))
          .map(([uuid, code]) => [uuid, reason(code)]),
      ),
    },
    resources: Object.fromEntries(
      Object.entries(resourceFields).map(([key, fields]) => {
        const metric = record(resources[key]);
        return [
          key,
          {
            ...observation(metric),
            ...Object.fromEntries(
              fields.map((field) => [field, number(metric[field])]),
            ),
            ...(key === "disk" && Array.isArray(metric.volumes)
              ? { volumes: diskVolumes(metric.volumes) }
              : {}),
          },
        ];
      }),
    ),
    services,
    // Informational producer facts, never merged into lifecycle targets.
    node_manager: {
      ...observation(v.node_manager),
      service_id: "node",
      running: bool(record(v.node_manager).running),
      generation: integer(record(v.node_manager).generation),
      actions: [] as string[],
    },
    support: (nodeId === "ai-harness" ? ["nginx", "admin", "egress", "task-slice"] : []).map(component_id => {
      const matches = (Array.isArray(v.support) ? v.support : []).map(record).filter(c => c.component_id === component_id);
      const c = matches.length === 1 ? matches[0]! : {};
      return {
        ...observation(c), component_id,
        active_state: enumValue(c.active_state, ["active", "inactive", "failed", "activating", "deactivating", "unknown"] as const, "unknown"),
        sub_state: enumValue(c.sub_state, ["running", "exited", "dead", "failed", "start", "stop", "unknown"] as const, "unknown"),
        ready: null,
      };
    }),
    gpus,
  };
}
export type NodeSnapshot = ReturnType<typeof sanitizeNode>;
export function unknownNode(nodeId: string, serviceIds: readonly string[] = []): NodeSnapshot {
  return sanitizeNode({ schema_version: 1, node_id: nodeId }, nodeId, serviceIds);
}
export function validateAction(raw: unknown): NodeAction {
  const v = record(raw);
  const allowed = [
    "schema_version",
    "node_id",
    "action",
    "service_id",
    "gpu_uuid",
    "idempotency_key",
    "expected_boot_id",
    "expected_generation",
    "allow_interrupt",
  ];
  const reject = (): never => {
    throw new ApiError(400, "invalid_action", "Invalid registered node action");
  };
  if (
    Object.keys(v).some((k) => !allowed.includes(k)) ||
    v.schema_version !== 1 ||
    !(NODE_IDS as readonly unknown[]).includes(v.node_id) ||
    !(ACTIONS as readonly unknown[]).includes(v.action) ||
    typeof v.allow_interrupt !== "boolean" ||
    integer(v.expected_generation) === null ||
    !identifier(v.expected_boot_id) ||
    typeof v.idempotency_key !== "string" ||
    !/^[a-zA-Z0-9_-]{16,128}$/.test(v.idempotency_key)
  )
    reject();
  if (String(v.action).startsWith("service.")) {
    if (
      !(SERVICE_IDS[v.node_id as NodeId] as readonly unknown[]).includes(
        v.service_id,
      ) ||
      v.gpu_uuid !== undefined
    )
      reject();
  } else if (v.action === "gpu.reset") {
    if (
      v.node_id !== "ai-vm" ||
      v.service_id !== undefined ||
      typeof v.gpu_uuid !== "string" ||
      !/^GPU-[0-9a-f-]{36}$/i.test(v.gpu_uuid)
    )
      reject();
  } else if (v.service_id !== undefined || v.gpu_uuid !== undefined) reject();
  return v as unknown as NodeAction;
}
export function sanitizeOperation(raw: unknown, nodeId: NodeId) {
  const v = record(raw);
  if (
    v.schema_version !== 1 ||
    v.node_id !== nodeId ||
    !identifier(v.operation_id) ||
    !(ACTIONS as readonly unknown[]).includes(v.action)
  )
    throw Error("Invalid operation receipt");
  return {
    schema_version: 1,
    node_id: nodeId,
    operation_id: `${nodeId}~${v.operation_id}`,
    action: v.action as string,
    status: enumValue(
      v.status,
      [
        "accepted",
        "running",
        "succeeded",
        "failed",
        "interrupted",
        "unknown",
      ] as const,
      "unknown",
    ),
    created_at: date(v.created_at),
    updated_at: date(v.updated_at),
    reason: reason(v.reason),
    affected_services: (Array.isArray(v.affected_services)
      ? v.affected_services
      : []
    ).filter((s) => (SERVICE_IDS[nodeId] as readonly unknown[]).includes(s)),
    poll_url: `/api/admin/v1/operations/${nodeId}~${v.operation_id}`,
  };
}
