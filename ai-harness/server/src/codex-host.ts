/** Trusted host composition. No environment flag or chat payload qualifies a runtime. */
import { CODEX_PIN, type CodexRuntime } from "./codex-engine.js";
import { CODEX_MODEL_POLICY, createRootlessCodexLauncher } from "./codex-launcher.js";
import { createCodexQwenCounter, type QwenCountQualification } from "./codex-qwen.js";
import type { Gateway, GatewayOptions } from "./gateway.js";

export interface CodexHostQualification {
  protocolQualified: true;
  rootlessQualified: true;
  /** Revalidates deployed model/runtime/template/allocation and current instance each call. */
  verifyLane(alias: string): Promise<QwenCountQualification>;
  outputLimit?: number;
  /** MiMo protocol/live qualification is separate from Qwen/rootless proof. */
  frontierResponsesQualified?: true;
  onResponsesDiagnostic?: NonNullable<GatewayOptions["responses"]>["onDiagnostic"];
  qualifiedAliases?: readonly string[];
  /** Explicit independent specialist ownership gate, never inferred from protocol PASS. */
  imageJobsQualified?: true;
  nativeDelegationQualified?: true;
  onResponsesError?: NonNullable<GatewayOptions["responses"]>["onError"];
  capabilities?: CodexRuntime['capabilities'];
}
export function composeCodexHost(launcherPath: string, gateway: () => Gateway | undefined,
  qualification?: CodexHostQualification) {
  if (qualification && (qualification.protocolQualified !== true || qualification.rootlessQualified !== true || typeof qualification.verifyLane !== "function"))
    throw Error("Codex requires reviewed protocol/rootless/current-instance qualification");
  if (qualification?.outputLimit !== undefined && (!Number.isSafeInteger(qualification.outputLimit) || qualification.outputLimit < 1 || qualification.outputLimit > 65536))
    throw Error("Invalid trusted Codex output reservation");
  const settlementObservation = new AbortController();
  const runtime: CodexRuntime = {
    pin: CODEX_PIN, protocolQualified: !!qualification,
    modelPolicyVersion: CODEX_MODEL_POLICY, model: "qwen3.8-27b", provider: "sova",
    gatewayUrl: "http://10.0.2.2:8081/v1", contextLimit: 480000,
    imageToolEnabled: qualification?.imageJobsQualified === true,
    delegationEnabled: qualification?.nativeDelegationQualified === true,
    maxChildren: 4,
    qualifiedChildModels: qualification?.frontierResponsesQualified === true ? ["qwen3.8-27b", "mimo-v2.6-pro-rl"] : ["qwen3.8-27b"],
    capabilities: qualification?.capabilities,
    launchRootless: input => createRootlessCodexLauncher(launcherPath)({ ...input, imageJobsQualified: qualification?.imageJobsQualified === true }),
    revokeGatewaySession: id => { const g = gateway(); if (!g) throw Error("Gateway unavailable"); g.revokeSession(id); },
    // Native teardown can finish before the accepted provider request drains.
    // Observe the durable session ledger; this never releases native/image ownership.
    confirmGatewaySettlement: async query => (await gateway()?.observeSettlement(query, settlementObservation.signal)) === true,
  };
  return { runtime,
    // Invoke before broker.close(): stopping observation is not settlement proof.
    stopSettlementObservation: () => settlementObservation.abort(),
    responses: qualification ? { enabled: true, outputLimit: qualification.outputLimit, qualifiedAliases: qualification.qualifiedAliases,
    frontierQualified: qualification.frontierResponsesQualified,
    onError: qualification.onResponsesError, onDiagnostic: qualification.onResponsesDiagnostic,
    currentAliases: async () => {
      const aliases = qualification.qualifiedAliases ?? ["qwen3.8-27b-gpu0", "qwen3.8-27b"];
      const results = await Promise.allSettled(aliases.map(alias => qualification.verifyLane(alias)));
      return aliases.filter((alias, index) => results[index]?.status === "fulfilled" &&
        (results[index] as PromiseFulfilledResult<QwenCountQualification>).value.alias === alias);
    },
    countQwen: createCodexQwenCounter(qualification.verifyLane) } : undefined };
}
