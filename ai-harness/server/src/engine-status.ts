/** Passive application-health evidence, independent of model/node observations. */
import { request } from "node:http";
import type { Observation } from "./observer-cache.js";
import type { RegistryService, SystemRegistry } from "./system-registry.js";
import { validateSystemRegistry } from "./system-registry.js";

const object = (v: unknown): Record<string, unknown> | null =>
  v !== null && typeof v === "object" && !Array.isArray(v) ? v as Record<string, unknown> : null;
const text = (v: unknown, max = 120) => typeof v === "string" && v.length > 0 && v.length <= max && !/[\x00-\x1f\x7f]/.test(v) ? v : null;
const bool = (v: unknown) => typeof v === "boolean" ? v : null;
const capabilityNames = ["nativeDelegation", "compaction", "attachments", "nativeMedia", "search", "browser", "pdf", "image", "coding", "frontier"] as const;
const flagNames = ["text", "media", "steering", "delegation", "frontier", "reasoning"] as const;
const qualifications = ["source", "scripted_fixture", "native_fixture", "live", "not_tested"];
export function sanitizeEngineHealth(raw: unknown, receivedAt = new Date().toISOString()) {
  const root = object(raw), engines = object(root?.engines);
  if (root?.status !== "ok" || !engines) throw Error("Application engine health unavailable");
  const observed = (id: "minimax" | "codex") => {
    const e = object(engines[id]);
    if (!e) return null;
    const details = object(e.capabilityDetails), flags = object(e.capabilities);
    return {
      version: text(e.version),
      // Existing health version is a deployment-policy value, never a process probe.
      version_evidence: "app-deployment-policy" as const,
      configured: bool(e.configured), enabled: bool(e.available), preview: bool(e.preview),
      readiness: e.readiness === "not-probed" || e.readiness === "disabled" ? e.readiness : "unknown",
      protocol_qualified: bool(e.protocolQualified), image_tool_enabled: bool(e.imageToolEnabled),
      capability_flags: Object.fromEntries(flagNames.filter(n => bool(flags?.[n]) !== null).map(n => [n, bool(flags?.[n])])),
      capabilities: Object.fromEntries(capabilityNames.filter(n => object(details?.[n])).map(n => {
        const c = object(details![n])!;
        return [n, { supported: bool(c.supported), qualification: qualifications.includes(String(c.qualification)) ? c.qualification : "unknown", reason: text(c.reason, 500) }];
      })),
    };
  };
  return {
    received_at: receivedAt,
    default_engine: engines.default === "minimax" || engines.default === "codex" ? engines.default : null,
    engines: { minimax: observed("minimax"), codex: observed("codex") },
  };
}
export type EngineHealth = ReturnType<typeof sanitizeEngineHealth>;

export function projectEngines(service: RegistryService, cached?: Observation<EngineHealth>) {
  const fresh = cached?.state === "fresh" && !cached.error;
  const freshness = !cached?.value ? "unknown" : fresh ? "fresh" : "stale";
  return (service.engines ?? []).map(config => {
    const observed = cached?.value?.engines[config.id] ?? null;
    const versionStatus = !observed?.version || !config.expected_version ? "unknown"
      : observed.version === config.expected_version ? "matched" : "mismatch";
    const state = cached?.error ? "unavailable" : !cached?.value ? "unavailable"
      : !fresh ? "stale" : !observed ? "missing" : versionStatus === "mismatch" ? "mismatch" : "observed";
    const usable = state === "observed";
    return {
      engine_id: config.id, display_name: config.display_name, service_id: service.id, node_id: service.node_id,
      configured: config,
      evidence_source: "configured-app-health" as const,
      state, freshness, age_ms: cached?.ageMs ?? null,
      observed_at: cached?.value?.received_at ?? null,
      reason: cached?.error ?? (!cached?.value ? "not_observed" : !observed ? "engine_not_reported" : versionStatus === "mismatch" ? "deployment_version_mismatch" : null),
      version_status: versionStatus,
      observed,
      default_engine: fresh ? cached?.value?.default_engine ?? null : null,
      selection_enabled: state === "mismatch" ? false : usable ? observed!.enabled : null,
      protocol_qualified: usable ? observed!.protocol_qualified : null,
      // No native startup probe is performed by this passive endpoint.
      ready: null,
      independently_restartable: false,
      actions: [] as string[],
    };
  });
}

/** Fixed trusted endpoint reference, no URL from the browser or observation body.
 * No credential needed; only bounded GET /api/health, no redirect or retry. */
export function appHealthObserver(registry: SystemRegistry) {
  const service = validateSystemRegistry(registry).services.find(s => s.id === "harness" && s.node_id === "ai-harness" && s.endpoint_ref === "harness-local");
  if (!service?.engines?.length || !service.engine_health) throw Error("Configured harness engine catalog required");
  const endpoint = service.engine_health;
  return { status: (signal: AbortSignal) => new Promise<unknown>((resolve, reject) => {
    const req = request({ hostname: endpoint.hostname, port: endpoint.port, path: endpoint.path, method: "GET", signal, agent: false, headers: { Host: endpoint.host_header, Accept: "application/json", "Cache-Control": "no-cache" } }, res => {
      let bytes = 0; const chunks: Buffer[] = [];
      const fail = () => { reject(Error("Application health unavailable")); res.destroy(); req.destroy(); };
      if (res.statusCode !== 200) { fail(); return; }
      res.on("data", (chunk: Buffer) => { bytes += chunk.length; if (bytes > 64 * 1024) fail(); else chunks.push(chunk); });
      res.on("error", fail);
      res.on("end", () => { try { resolve(JSON.parse(Buffer.concat(chunks).toString("utf8"))); } catch { fail(); } });
    });
    req.on("error", () => reject(Error("Application health unavailable")));
    req.end();
  }) };
}
