/** Trusted host composition. No environment flag or chat payload qualifies a runtime. */
import { codexReceiptProvenance, type CodexReceiptPolicy } from "./codex-receipts.js";
import type { CodexReadOriginalProbe, CodexTextOnlyPolicy } from "./codex-probe.js";
import { admissionContext, admissionReason, emitAdmission, type QwenAdmissionContext, type QwenAdmissionObserver } from "./codex-admission.js";
import { CODEX_PIN, type CodexRuntime } from "./codex-engine.js";
import { loadCodexResumeInstructions } from "./codex-instructions.js";
import { CODEX_MODEL_POLICY, createRootlessCodexLauncher } from "./codex-launcher.js";
import { createCodexQwenCounter, type QwenCountQualification } from "./codex-qwen.js";
import type { Gateway, GatewayOptions } from "./gateway.js";

export interface CodexHostQualification {
  onNativeThread?:CodexRuntime["onNativeThread"];
  beforeNativeAction?:CodexRuntime["beforeNativeAction"];
  onNativeChildObserved?:CodexRuntime["onNativeChildObserved"];
  nativeMetadataAuthority?: GatewayOptions["nativeMetadataAuthority"];
  onNativeOperation?: GatewayOptions["onNativeOperation"];
  retentionTurnKind?:CodexRuntime["retentionTurnKind"];
  ordinaryMemoryAdmission?: CodexRuntime["ordinaryMemoryAdmission"];
  protocolQualified: true;
  /** Disabled until root reviews actual Linux receipt-channel acceptance. */
  nativeReceiptPolicy?: CodexReceiptPolicy;
  parentArtifactScope?: CodexRuntime["parentArtifactScope"];
  registerCheckpointArtifact?: CodexRuntime["registerCheckpointArtifact"];
  onCheckpointArtifactSettled?: CodexRuntime["onCheckpointArtifactSettled"];
  textOnlyPolicy?: (sessionId: string) => CodexTextOnlyPolicy | undefined;
  authorizeNativeTurn?: CodexRuntime["authorizeNativeTurn"];
  authorizeOriginalRead?: CodexRuntime["authorizeOriginalRead"];
  onNativeThreadPolicy?: CodexRuntime["onNativeThreadPolicy"];
  readOriginalProbe?: (sessionId: string) => CodexReadOriginalProbe | undefined;
  onNativeLaunchReceipt?: CodexRuntime["onNativeLaunchReceipt"];
  onNativeSettlementReceipt?: CodexRuntime["onNativeSettlementReceipt"];
  onOriginalReadSettled?: CodexRuntime["onOriginalReadSettled"];
  rootlessQualified: true;
  /** Revalidates deployed model/runtime/template/allocation and current instance each call. */
  verifyLane(alias: string, context?: QwenAdmissionContext): Promise<QwenCountQualification>;
  onAdmissionDiagnostic?: QwenAdmissionObserver;
  outputLimit?: number;
  /** MiMo protocol/live qualification is separate from Qwen/rootless proof. */
  frontierResponsesQualified?: true;
  /** Temporary trusted exact session/run acceptance; never inferred from request body. */
  frontierAcceptance?: (sessionId: string) => boolean;
  onResponsesDiagnostic?: NonNullable<GatewayOptions["responses"]>["onDiagnostic"];
  qualifiedAliases?: readonly string[];
  /** Explicit independent specialist ownership gate, never inferred from protocol PASS. */
  imageJobsQualified?: true;
  /** Temporary exact-session/run acceptance; never changes advertised capability. */
  imageAcceptance?: (sessionId: string) => boolean;
  nativeDelegationQualified?: true;
  onResponsesError?: NonNullable<GatewayOptions["responses"]>["onError"];
  capabilities?: CodexRuntime['capabilities'];
}
/** Trusted receipt-run forces text-only even when an ordinary session has image acceptance. */
export function imageGateForCodexLaunch(input: {sessionId: string; receiptRunId?: string}, qualification?: CodexHostQualification): boolean {
  if (input.receiptRunId) return false;
  return qualification?.imageJobsQualified === true || qualification?.imageAcceptance?.(input.sessionId) === true;
}
export function composeCodexHost(launcherPath: string, gateway: () => Gateway | undefined,
  qualification?: CodexHostQualification) {
  if (qualification && (qualification.protocolQualified !== true || qualification.rootlessQualified !== true || typeof qualification.verifyLane !== "function"))
    throw Error("Codex requires reviewed protocol/rootless/current-instance qualification");
  if (qualification?.outputLimit !== undefined && (!Number.isSafeInteger(qualification.outputLimit) || qualification.outputLimit < 1 || qualification.outputLimit > 65536))
    throw Error("Invalid trusted Codex output reservation");
  if (qualification?.readOriginalProbe && qualification.nativeReceiptPolicy?.linuxTransportQualified !== true) throw Error("Original probes require reviewed Linux receipt transport");
  if (qualification?.ordinaryMemoryAdmission && !qualification.nativeReceiptPolicy) throw Error("Ordinary memory requires genuine native receipt transport");
  if (qualification?.textOnlyPolicy && (!qualification.nativeReceiptPolicy || !qualification.authorizeNativeTurn)) throw Error("Text-only policy requires receipt transport and observed native admission");
  if (qualification?.readOriginalProbe && (!qualification.textOnlyPolicy || !qualification.authorizeOriginalRead)) throw Error("Original probes disabled: native model tool/sandbox scope is unqualified");
  if (qualification?.parentArtifactScope && (!qualification.textOnlyPolicy || !qualification.nativeReceiptPolicy || !qualification.registerCheckpointArtifact)) throw Error("Parent artifacts require bounded policy, genuine receipts and actual registration");
  const settlementObservation = new AbortController();
  const runtime: CodexRuntime = {
    onNativeThread:qualification?.onNativeThread,
    beforeNativeAction:qualification?.beforeNativeAction,
    onNativeChildObserved:qualification?.onNativeChildObserved,
    retentionTurnKind:qualification?.retentionTurnKind,
    ordinaryMemoryAdmission: qualification?.ordinaryMemoryAdmission ? async (input,signal) => {
      if (!codexReceiptProvenance(input.launchReceipt)) throw Error("Ordinary memory lacks genuine current launch receipt");
      await qualification.ordinaryMemoryAdmission!(input,signal);
    } : undefined,
    pin: CODEX_PIN, protocolQualified: !!qualification,
    nativeReceiptsRequired: !!qualification?.nativeReceiptPolicy,
    parentArtifactScope: qualification?.parentArtifactScope,
    registerCheckpointArtifact: qualification?.registerCheckpointArtifact ? async (input, signal) => {
      if (!codexReceiptProvenance(input.launchReceipt)) throw Error("Artifact scope lacks genuine transport receipt");
      return qualification.registerCheckpointArtifact!(input, signal);
    } : undefined,
    onCheckpointArtifactSettled: qualification?.onCheckpointArtifactSettled,
    textOnlyPolicy: qualification?.textOnlyPolicy,
    authorizeNativeTurn: qualification?.authorizeNativeTurn ? async input => {
      if (!codexReceiptProvenance(input.launchReceipt)) throw Error("Native turn lacks genuine transport receipt");
      await qualification.authorizeNativeTurn!(input);
    } : undefined,
    authorizeOriginalRead: qualification?.authorizeOriginalRead ? async (input, signal) => {
      if (!codexReceiptProvenance(input.launchReceipt)) throw Error("Original scope lacks genuine transport receipt");
      await qualification.authorizeOriginalRead!(input, signal);
    } : undefined,
    onNativeThreadPolicy: qualification?.onNativeThreadPolicy,
    readOriginalProbe: qualification?.readOriginalProbe,
    onNativeLaunchReceipt: qualification?.onNativeLaunchReceipt,
    onNativeSettlementReceipt: qualification?.onNativeSettlementReceipt,
    onOriginalReadSettled: qualification?.onOriginalReadSettled,
    modelPolicyVersion: CODEX_MODEL_POLICY, model: "qwen3.8-27b", provider: "sova",
    gatewayUrl: "http://10.0.2.2:8081/v1", contextLimit: 480000,
    imageToolEnabled: qualification?.imageJobsQualified === true,
    delegationEnabled: qualification?.nativeDelegationQualified === true,
    maxChildren: qualification?.retentionTurnKind ? 1 : 4,
    qualifiedChildModels: (qualification?.frontierResponsesQualified === true || !!qualification?.frontierAcceptance) ? ["qwen3.8-27b", "mimo-v2.6-pro-rl"] : ["qwen3.8-27b"],
    capabilities: qualification?.capabilities,
    loadResumeInstructions: qualification ? () => loadCodexResumeInstructions(launcherPath) : undefined,
    launchRootless: input => createRootlessCodexLauncher(launcherPath, qualification?.nativeReceiptPolicy)({ ...input, imageJobsQualified: imageGateForCodexLaunch(input, qualification) }),
    revokeGatewaySession: id => { const g = gateway(); if (!g) throw Error("Gateway unavailable"); g.revokeSession(id); },
    // Native teardown can finish before the accepted provider request drains.
    // Observe the durable session ledger; this never releases native/image ownership.
    confirmGatewaySettlement: async query => (await gateway()?.observeSettlement(query, settlementObservation.signal)) === true,
  };
  return { runtime,
    // Stop only after broker/recovery owners have settled; stopping is not settlement proof.
    stopSettlementObservation: () => settlementObservation.abort(),
    responses: qualification ? { enabled: true, outputLimit: qualification.outputLimit, qualifiedAliases: qualification.qualifiedAliases,
    frontierQualified: qualification.frontierResponsesQualified, frontierAcceptance: qualification.frontierAcceptance,
    onError: qualification.onResponsesError, onDiagnostic: qualification.onResponsesDiagnostic,
    onAdmissionDiagnostic: qualification.onAdmissionDiagnostic,
    currentAliases: async (context: QwenAdmissionContext = admissionContext("admission")) => {
      const aliases = qualification.qualifiedAliases ?? ["qwen3.8-27b-gpu0", "qwen3.8-27b"];
      const results = await Promise.allSettled(aliases.map(async alias => {
        const start = performance.now();
        try {
          const result = await qualification.verifyLane(alias, context);
          if (result.alias !== alias) throw new Error("Unqualified lane alias");
          emitAdmission(qualification.onAdmissionDiagnostic, { schema: 1, ...context, lane: alias, step: "lane", outcome: "pass", reason: "ok", elapsedMs: performance.now() - start });
          return result;
        } catch (error) {
          emitAdmission(qualification.onAdmissionDiagnostic, { schema: 1, ...context, lane: alias, step: "lane", outcome: "reject", reason: admissionReason(error), elapsedMs: performance.now() - start });
          throw error;
        }
      }));
      return aliases.filter((alias, index) => results[index]?.status === "fulfilled" &&
        (results[index] as PromiseFulfilledResult<QwenCountQualification>).value.alias === alias);
    },
    countQwen: createCodexQwenCounter(qualification.verifyLane, qualification.onAdmissionDiagnostic) } : undefined };
}
