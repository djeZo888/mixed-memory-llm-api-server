import { sanitizeNode, type NodeSnapshot } from "./node-contract.js";
import type { NodeBackend } from "./node-client.js";
import { ObserverCache } from "./observer-cache.js";
import type {
  AvailabilityProvider,
  ServiceAvailability,
} from "./service-availability.js";

const SERVICES = ["qwen-gpu0", "qwen-gpu1", "image"] as const;
type ServiceId = (typeof SERVICES)[number];
export interface HardwareLatch {
  /** Authoritative latch origin, never inferred from the current node boot. */
  bootId: string | null;
  /** Conservative reboot boundary when the authority could not identify origin. */
  observedBootId?: string | null;
  requiredGpuUuids: string[];
}
export type HardwareLatchLedger = Partial<Record<ServiceId, HardwareLatch>>;
export interface NodeAvailabilityOptions {
  /** Direct passive node transport; never the status/admin daemon or native /health. */
  backend: Pick<NodeBackend, "status">;
  /** Authenticated fixed passive backend probes, independently capped by service. */
  readiness?: Partial<
    Record<
      ServiceId,
      (signal: AbortSignal) => Promise<{ ready: boolean | null }>
    >
  >;
  initialLatches?: HardwareLatchLedger;
  /** Must synchronously durably commit the full replacement ledger before returning. */
  onLatch: (ledger: HardwareLatchLedger) => void;
  changed?: () => void;
  /** Clock/short intervals are injected only by offline fixtures. */
  now?: () => number;
  pollMs?: number;
  deadlineMs?: number;
  staleMs?: number;
}
const serviceId = (id: string): ServiceId | undefined =>
  id === "qwen3.8-27b-gpu0"
    ? "qwen-gpu0"
    : id === "qwen3.8-27b"
      ? "qwen-gpu1"
      : (SERVICES as readonly string[]).includes(id)
        ? (id as ServiceId)
        : undefined;
const validUuid = (id: string) => /^GPU-[0-9a-f-]{36}$/i.test(id);

/** Independent passive routing observer. It consumes authoritative boot latches;
 * it never infers absence, resets hardware, or changes request quarantine.
 *
 * Optional H005 wiring is deliberate: without a configured observer (and without
 * a retained latch ledger), the brokers keep their pre-H005 unknown baseline.
 * Once configured, this provider gates new work on unknown backend readiness.
 * A retained ledger must keep this provider active even if configuration is removed;
 * neither removing a key path nor a status-daemon outage clears hardware latches. */
export class NodeAvailability {
  private readonly cache: ObserverCache<NodeSnapshot>;
  private readonly readiness = new Map<
    ServiceId,
    ObserverCache<{ ready: boolean | null }>
  >();
  private latches: HardwareLatchLedger;
  private ledgerFailed = false;
  private lastValue?: NodeSnapshot;
  private timer?: NodeJS.Timeout;
  private stopped = false;
  private readonly staleMs: number;
  constructor(private readonly options: NodeAvailabilityOptions) {
    this.latches = structuredClone(options.initialLatches ?? {});
    for (const [id, value] of Object.entries(this.latches))
      if (
        !(SERVICES as readonly string[]).includes(id) ||
        !value ||
        (value.bootId !== null &&
          (typeof value.bootId !== "string" ||
            !/^[a-zA-Z0-9_.:-]{1,128}$/.test(value.bootId))) ||
        (value.observedBootId !== undefined &&
          value.observedBootId !== null &&
          (typeof value.observedBootId !== "string" ||
            !/^[a-zA-Z0-9_.:-]{1,128}$/.test(value.observedBootId))) ||
        !Array.isArray(value.requiredGpuUuids) ||
        !value.requiredGpuUuids.length ||
        value.requiredGpuUuids.some(
          (uuid) => typeof uuid !== "string" || !validUuid(uuid),
        ) ||
        new Set(value.requiredGpuUuids).size !== value.requiredGpuUuids.length
      )
        throw Error("Invalid persisted hardware latch ledger");
    this.staleMs = options.staleMs ?? 15000;
    this.cache = new ObserverCache(
      async (signal) =>
        sanitizeNode(await options.backend.status(signal), "ai-vm"),
      {
        now: options.now,
        deadlineMs: options.deadlineMs ?? 2000,
        staleMs: this.staleMs,
        changed: () => this.publish(),
      },
    );
    for (const id of SERVICES) {
      const probe = options.readiness?.[id];
      if (probe)
        this.readiness.set(
          id,
          new ObserverCache(probe, {
            now: options.now,
            deadlineMs: options.deadlineMs ?? 2000,
            staleMs: this.staleMs,
            changed: () => this.publish(),
          }),
        );
    }
  }
  private fresh(
    observation: {
      state: string;
      freshness: string;
      age_ms: number | null;
      observed_at: string | null;
    },
    elapsed: number,
  ) {
    return (
      observation.state === "ok" &&
      observation.freshness === "fresh" &&
      observation.observed_at !== null &&
      observation.age_ms !== null &&
      observation.age_ms + elapsed < this.staleMs
    );
  }
  private applyLatches(value: NodeSnapshot) {
    const next = structuredClone(this.latches);
    for (const id of SERVICES) {
      const service = value.services.find((s) => s.service_id === id);
      if (!service) continue;
      const old = next[id];
      // A positive authority receipt remains useful even when readiness is stale.
      if (
        service.hardware_latched === true &&
        service.required_gpu_uuids.length
      ) {
        next[id] = {
          bootId: service.hardware_latched_boot_id,
          ...(service.hardware_latched_boot_id === null
            ? {
                observedBootId:
                  old?.bootId === null
                    ? (old.observedBootId ?? value.boot_id)
                    : value.boot_id,
              }
            : {}),
          requiredGpuUuids: [...new Set(service.required_gpu_uuids)],
        };
        continue;
      }
      const inventory = value.inventory;
      if (
        old &&
        value.boot_id !== null &&
        (old.bootId ?? old.observedBootId) != null &&
        (old.bootId ?? old.observedBootId) !== value.boot_id &&
        service.hardware_latched === false &&
        this.fresh(service, 0) &&
        this.fresh(inventory, 0) &&
        inventory.complete &&
        inventory.boot_id === value.boot_id &&
        inventory.observation_id !== null &&
        new Set(inventory.gpu_uuids).size === inventory.gpu_uuids.length &&
        old.requiredGpuUuids.every(
          (uuid) =>
            inventory.gpu_uuids.includes(uuid) &&
            !Object.hasOwn(inventory.hardware_faults, uuid),
        ) &&
        service.required_gpu_uuids.length > 0 &&
        service.required_gpu_uuids.every(
          (uuid) =>
            inventory.gpu_uuids.includes(uuid) &&
            !Object.hasOwn(inventory.hardware_faults, uuid),
        )
      )
        delete next[id];
    }
    if (
      JSON.stringify(next) === JSON.stringify(this.latches) &&
      !this.ledgerFailed
    )
      return;
    try {
      this.options.onLatch(structuredClone(next));
      this.latches = next;
      this.ledgerFailed = false;
    } catch {
      // Never clear an old latch on a failed durable write. New positive latches
      // still gate this process, and all new work waits for a successful ledger.
      for (const id of SERVICES) if (next[id]) this.latches[id] = next[id];
      this.ledgerFailed = true;
    }
  }
  private publish() {
    if (this.stopped) return;
    const observation = this.cache.snapshot();
    if (observation.value && observation.value !== this.lastValue) {
      this.lastValue = observation.value;
      this.applyLatches(observation.value);
    }
    try {
      this.options.changed?.();
    } catch {
      /* A consumer cannot break observation. */
    }
  }
  private readable(id: ServiceId): ServiceAvailability {
    if (this.latches[id])
      return {
        state: "unavailable",
        reason: "hardware_latched",
        dispatch: "reject",
      };
    if (this.ledgerFailed)
      return {
        state: "unknown",
        reason: "availability_ledger_unavailable",
        dispatch: "hold",
      };
    const cached = this.cache.snapshot();
    const value = cached.value;
    const service = value?.services.find((s) => s.service_id === id);
    if (
      this.stopped ||
      cached.state !== "fresh" ||
      cached.error !== null ||
      !value?.boot_id ||
      !service ||
      !this.fresh(service, cached.ageMs ?? this.staleMs)
    )
      return {
        state: "unknown",
        reason: "readiness_unknown",
        dispatch: "hold",
      };
    if (service.hardware_latched === true)
      return {
        state: "unavailable",
        reason: "hardware_latched",
        dispatch: "reject",
      };
    if (
      service.availability === "unavailable" ||
      service.ready === false ||
      (id !== "image" && service.admitting === false)
    )
      return {
        state: "unavailable",
        reason: service.reason ?? "not_ready",
        dispatch: "hold",
      };
    if (
      service.availability !== "available" ||
      service.ready !== true ||
      (id !== "image" && service.admitting === false) ||
      service.hardware_latched !== false
    )
      return {
        state: "unknown",
        reason: "readiness_unknown",
        dispatch: "hold",
      };
    return { state: "available", dispatch: "allow" };
  }
  /** Configured H005 admission gates unknown readiness without inventing a latch. */
  readonly get: AvailabilityProvider = (alias) => {
    const id = serviceId(alias);
    const value: ServiceAvailability = id
      ? this.readable(id)
      : { state: "unknown", reason: "readiness_unknown", dispatch: "hold" };
    if (
      id &&
      !this.stopped &&
      value.state === "unknown" &&
      value.reason === "readiness_unknown"
    ) {
      const fallback = this.readiness.get(id)?.snapshot();
      const cached = this.cache.snapshot();
      const last = cached.value?.services.find(
        (service) => service.service_id === id,
      );
      // Software readiness has an observation lifetime. Only the separate durable
      // hardware latch remains authoritative after this soft observation expires.
      const softUnavailable =
        last?.availability === "unavailable" &&
        this.fresh(last, cached.ageMs ?? this.staleMs);
      if (
        !softUnavailable &&
        fallback?.state === "fresh" &&
        fallback.error === null &&
        fallback.value?.ready === true
      )
        return {
          state: "unknown",
          reason: "passive_backend_ready",
          dispatch: "allow",
        };
    }
    return value;
  };
  /** Public display retains unknown separately from hardware/service unavailability. */
  states() {
    return {
      qwenGpu0: this.readable("qwen-gpu0").state,
      qwenGpu1: this.readable("qwen-gpu1").state,
      image: this.readable("image").state,
    };
  }
  snapshot() {
    return this.cache.snapshot();
  }
  async poll() {
    if (this.stopped) return;
    // Expiry is published every tick, including while an abort-ignoring probe is hung.
    this.publish();
    await this.cache.poll();
    await Promise.all(
      [...this.readiness].map(async ([id, cache]) => {
        const state = this.readable(id);
        if (state.state === "unknown" && state.reason === "readiness_unknown")
          await cache.poll();
      }),
    );
  }
  start() {
    if (this.timer || this.stopped) return;
    void this.poll();
    this.timer = setInterval(
      () => void this.poll(),
      this.options.pollMs ?? 5000,
    );
    this.timer.unref();
  }
  stop() {
    this.stopped = true;
    clearInterval(this.timer);
    this.cache.stop();
    for (const cache of this.readiness.values()) cache.stop();
  }
}
