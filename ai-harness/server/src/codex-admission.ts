/** Static content-free admission diagnostics; never serialize caught errors. */
import { randomUUID } from "node:crypto";
import { ApiError } from "./errors.js";
export const QWEN_ADMISSION_REASONS = ["ok", "transport", "unexpected", "receipt_policy", "control_schema", "selected_profile", "runtime_state", "storage_state", "generation", "runtime_identity", "freshness", "operation_pending", "endpoint_policy", "owner_ready", "node_schema", "boot_identity", "service_identity", "hardware_state", "token_capacity", "native_profile", "identity_changed", "tokenizer", "count_profile", "cancelled"] as const;
export type QwenAdmissionReason = typeof QWEN_ADMISSION_REASONS[number];
export interface QwenAdmissionContext { requestId: string; phase: "admission" | "count" }
export interface QwenAdmissionDiagnostic extends QwenAdmissionContext {
  schema: 1; lane: string;
  step: "control_before" | "node_before" | "native" | "control_after" | "node_after" | "lane" | "tokenize" | "capacity";
  outcome: "pass" | "reject"; reason: QwenAdmissionReason; elapsedMs: number;
}
export type QwenAdmissionObserver = (event: QwenAdmissionDiagnostic) => void;
export class QwenAdmissionError extends ApiError {
  constructor(readonly reason: QwenAdmissionReason) {
    super(503, "codex_qwen_identity_unqualified", "Current Qwen identity or native allocation is not qualified");
  }
}
export const admissionContext = (phase: QwenAdmissionContext["phase"]): QwenAdmissionContext => ({ requestId: randomUUID(), phase });
export const admissionReason = (error: unknown): QwenAdmissionReason => error instanceof QwenAdmissionError && QWEN_ADMISSION_REASONS.includes(error.reason) ? error.reason : "unexpected";
export function emitAdmission(observer: QwenAdmissionObserver | undefined, event: QwenAdmissionDiagnostic): void {
  try { observer?.(event); } catch { /* Observation cannot change admission or ownership. */ }
}
