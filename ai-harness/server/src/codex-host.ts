/** Trusted host composition. No environment flag or chat payload qualifies a runtime. */
import { CODEX_PIN, type CodexRuntime } from "./codex-engine.js";
import { CODEX_MODEL_POLICY, createRootlessCodexLauncher } from "./codex-launcher.js";
import { createCodexQwenCounter, type QwenCountQualification } from "./codex-qwen.js";
import type { Gateway } from "./gateway.js";

export interface CodexHostQualification {
  protocolQualified: true;
  rootlessQualified: true;
  /** Revalidates deployed model/runtime/template/allocation and current instance each call. */
  verifyLane(alias: string): Promise<QwenCountQualification>;
  outputLimit?: number;
}
export function composeCodexHost(launcherPath: string, gateway: () => Gateway | undefined,
  qualification?: CodexHostQualification) {
  if (qualification && (qualification.protocolQualified !== true || qualification.rootlessQualified !== true || typeof qualification.verifyLane !== "function"))
    throw Error("Codex requires reviewed protocol/rootless/current-instance qualification");
  if (qualification?.outputLimit !== undefined && (!Number.isSafeInteger(qualification.outputLimit) || qualification.outputLimit < 1 || qualification.outputLimit > 65536))
    throw Error("Invalid trusted Codex output reservation");
  const runtime: CodexRuntime = {
    pin: CODEX_PIN, protocolQualified: !!qualification,
    modelPolicyVersion: CODEX_MODEL_POLICY, model: "qwen3.8-27b", provider: "sova",
    gatewayUrl: "http://10.0.2.2:8081/v1", contextLimit: 480000,
    launchRootless: createRootlessCodexLauncher(launcherPath),
    revokeGatewaySession: id => { const g = gateway(); if (!g) throw Error("Gateway unavailable"); g.revokeSession(id); },
    confirmGatewaySettlement: async query => (await gateway()?.confirmSettlement(query)) === true,
  };
  return { runtime, responses: qualification ? { enabled: true, outputLimit: qualification.outputLimit,
    countQwen: createCodexQwenCounter(qualification.verifyLane) } : undefined };
}
