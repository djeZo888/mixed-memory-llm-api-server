/** Static content-free admission diagnostics; never serialize caught errors. */
import { randomUUID } from "node:crypto";
import { ApiError } from "./errors.js";
export const QWEN_ADMISSION_REASONS = ["ok", "transport", "unexpected", "receipt_policy", "control_schema", "selected_profile", "runtime_state", "storage_state", "generation", "runtime_identity", "freshness", "operation_pending", "endpoint_policy", "owner_ready", "node_schema", "boot_identity", "service_identity", "hardware_state", "token_capacity", "native_profile", "identity_changed", "tokenizer", "count_profile", "cancelled"] as const;
export type QwenAdmissionReason = typeof QWEN_ADMISSION_REASONS[number];
export const QWEN_TRANSPORT_KINDS = ["http_status", "invalid_json", "response_limit", "response_stream", "connection", "timeout", "cancelled"] as const;
// Pinned control/core.py SAFE_CODES plus control/http.py's fixed rejection codes.
// Never copy an arbitrary remote string, response body or caught error message.
export const QWEN_CONTROL_ERROR_CODES = new Set([
  "catalog_unavailable", "credential_separation_unverified", "invalid_request", "unknown_route", "method_not_allowed", "unknown_deployment",
  "target_unavailable", "target_required", "target_mismatch", "already_running", "lifecycle_busy", "stale_state", "interruption_ack_required",
  "idempotency_conflict", "storage_unavailable", "owner_unavailable", "production_adapter_unavailable", "package_admission_unavailable",
  "journal_unavailable", "journal_corrupt", "journal_full", "admission_timeout", "observation_unavailable", "preflight_failed", "stop_not_proven", "start_failed",
  "transition_failed", "deadline_exceeded", "service_interrupted", "recovery_identity_unavailable", "service_closed", "operation_unknown",
  "concurrent_current_host_memory_unavailable", "concurrent_current_host_memory_insufficient", "concurrent_current_gpu_memory_unavailable", "concurrent_current_gpu_memory_insufficient",
  "concurrent_native_capacity_unavailable", "concurrent_native_capacity_mismatch", "concurrent_native_metadata_unavailable", "concurrent_native_metadata_auth_failed",
  "concurrent_memory_admission_timeout", "concurrent_resident_identity_invalid", "concurrent_resident_cgroup_unavailable", "concurrent_resident_memory_unavailable",
  "concurrent_resident_swap_detected", "concurrent_resident_cgroup_changed", "concurrent_resident_identity_changed",
  "service_unavailable", "invalid_json", "request_limit", "invalid_headers", "unauthorized", "browser_control_forbidden", "unsupported_protocol",
  "unsupported_transfer_encoding", "expectation_failed", "length_required", "invalid_content_length", "body_limit", "unexpected_body", "json_required",
]);
export interface QwenTransportDiagnostic {
  kind: typeof QWEN_TRANSPORT_KINDS[number]; httpStatus?: number; controlCode?: string;
}
export function projectQwenTransport(value: QwenTransportDiagnostic | undefined): QwenTransportDiagnostic | undefined {
  if (!value || !QWEN_TRANSPORT_KINDS.includes(value.kind)) return;
  return { kind: value.kind,
    ...(Number.isInteger(value.httpStatus) && value.httpStatus! >= 100 && value.httpStatus! <= 599 ? { httpStatus: value.httpStatus } : {}),
    ...(typeof value.controlCode === "string" && QWEN_CONTROL_ERROR_CODES.has(value.controlCode) ? { controlCode: value.controlCode } : {}) };
}
/** Bounded predicate evidence only; never include a remote body or free-form reason. */
export interface QwenHardwareDiagnostic {
  hardwareLatched: boolean | null | "missing" | "invalid";
  gpuUuidMatch: boolean;
  expectedGpuUuid: string | null;
  requiredGpuUuids: string[] | null;
  nodeSchema: number | null;
  nodeAgeMs: number | null;
  serviceAgeMs: number | null;
  serviceGeneration: number | null;
  bootId: string | null;
  hardwareValidationAgeMs: number | null;
  hardwareValidatedBootId: string | null;
  hardwareValidatedGpuUuids: string[] | null;
}
export function projectQwenHardware(value: QwenHardwareDiagnostic | undefined): QwenHardwareDiagnostic | undefined {
  if (!value) return;
  const gpu = (v: unknown): v is string => typeof v === "string" && /^GPU-[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/.test(v);
  const uuids = (v: unknown): string[] | null => Array.isArray(v) && v.length <= 8 && v.every(gpu) ? [...v] : null;
  const boot = (v: unknown): string | null => typeof v === "string" && /^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/.test(v) ? v : null;
  const number = (v: unknown): number | null => typeof v === "number" && Number.isFinite(v) && v >= 0 && v <= Number.MAX_SAFE_INTEGER ? v : null;
  return { hardwareLatched: value.hardwareLatched === true || value.hardwareLatched === false || value.hardwareLatched === null || value.hardwareLatched === "missing" ? value.hardwareLatched : "invalid",
    gpuUuidMatch: value.gpuUuidMatch === true, expectedGpuUuid: gpu(value.expectedGpuUuid) ? value.expectedGpuUuid : null,
    requiredGpuUuids: uuids(value.requiredGpuUuids), nodeSchema: number(value.nodeSchema), nodeAgeMs: number(value.nodeAgeMs),
    serviceAgeMs: number(value.serviceAgeMs), serviceGeneration: number(value.serviceGeneration), bootId: boot(value.bootId),
    hardwareValidationAgeMs: number(value.hardwareValidationAgeMs), hardwareValidatedBootId: boot(value.hardwareValidatedBootId),
    hardwareValidatedGpuUuids: uuids(value.hardwareValidatedGpuUuids) };
}
export interface QwenAdmissionContext { requestId: string; phase: "admission" | "count" }
export interface QwenAdmissionDiagnostic extends QwenAdmissionContext {
  schema: 1; lane: string;
  step: "control_before" | "node_before" | "native" | "control_after" | "node_after" | "lane" | "tokenize" | "capacity";
  outcome: "pass" | "reject"; reason: QwenAdmissionReason; elapsedMs: number; transport?: QwenTransportDiagnostic; hardware?: QwenHardwareDiagnostic;
}
export type QwenAdmissionObserver = (event: QwenAdmissionDiagnostic) => void;
export class QwenAdmissionError extends ApiError {
  constructor(readonly reason: QwenAdmissionReason, readonly transport?: QwenTransportDiagnostic, readonly hardware?: QwenHardwareDiagnostic) {
    super(503, "codex_qwen_identity_unqualified", "Current Qwen identity or native allocation is not qualified");
  }
}
export const admissionContext = (phase: QwenAdmissionContext["phase"]): QwenAdmissionContext => ({ requestId: randomUUID(), phase });
export const admissionReason = (error: unknown): QwenAdmissionReason => error instanceof QwenAdmissionError && QWEN_ADMISSION_REASONS.includes(error.reason) ? error.reason : "unexpected";
export const admissionTransport = (error: unknown): QwenTransportDiagnostic | undefined => error instanceof QwenAdmissionError && error.reason === "transport" ? projectQwenTransport(error.transport) : undefined;
export const admissionHardware = (error: unknown): QwenHardwareDiagnostic | undefined => error instanceof QwenAdmissionError && error.reason === "hardware_state" ? projectQwenHardware(error.hardware) : undefined;
export function emitAdmission(observer: QwenAdmissionObserver | undefined, event: QwenAdmissionDiagnostic): void {
  try { observer?.(event); } catch { /* Observation cannot change admission or ownership. */ }
}
