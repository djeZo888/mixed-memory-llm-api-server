import type { CodexCapabilities } from "./codex-capabilities.js";
import type { EngineFactory, EngineKind, EngineOptions } from "./contracts.js";
import { ApiError } from "./errors.js";

/** Host deployment input only. No request body can populate this policy. */
export interface EnginePolicy {
  codex?: {
    capabilities?: Partial<CodexCapabilities>;
    delegationEnabled?: boolean;
    imageToolEnabled?: boolean;
    imageGenerationEnabled?: boolean;
    /** Descriptive external specialist capability, never native pixel permission. */
    technicalVisionAvailable?: boolean;
    enabled: boolean;
    protocolQualified: boolean;
    engineVersion: string;
    modelPolicyVersion: string;
  };
}
export function codexAvailable(
  policy?: EnginePolicy,
  factory?: EngineFactory,
): boolean {
  const codex = policy?.codex;
  return !!(
    codex?.enabled === true &&
    codex.protocolQualified === true &&
    codex.engineVersion &&
    codex.modelPolicyVersion &&
    factory
  );
}
export function assertEngineAvailable(
  kind: unknown,
  policy?: EnginePolicy,
  factory?: EngineFactory,
): asserts kind is EngineKind {
  if (kind !== "minimax" && kind !== "codex")
    throw new ApiError(400, "unknown_engine", "Unknown engine kind");
  if (kind === "minimax") throw new ApiError(409, "historical_chat_read_only", "This saved chat is read-only. Start a new chat to continue; your history and files are preserved.");
  if (kind === "codex" && !codexAvailable(policy, factory))
    throw new ApiError(
      409,
      "codex_preview_unavailable",
      "Chat is temporarily unavailable while its service is being checked.",
    );
}
export function createEngineRouter(
  minimax: EngineFactory,
  codex?: EngineFactory,
  policy?: EnginePolicy,
): EngineFactory {
  return (options: EngineOptions) => {
    const kind = options.engineKind ?? "codex";
    assertEngineAvailable(kind, policy, codex);
    if (kind === "minimax") return minimax(options);
    if (
      options.engineVersion !== policy!.codex!.engineVersion ||
      options.modelPolicyVersion !== policy!.codex!.modelPolicyVersion
    )
      throw new ApiError(
        409,
        "engine_policy_mismatch",
        "Native session requires its reviewed engine and model policy",
      );
    if (options.nativeState?.ownership !== "idle")
      throw new ApiError(
        409,
        "engine_settlement_unknown",
        "Native work requires settlement review before resume",
      );
    return codex!(options);
  };
}
