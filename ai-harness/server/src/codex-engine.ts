import { CODEX_READ_ORIGINAL_SPEC, claimCodexReadOriginalProbe, readCodexOriginal, type CodexReadOriginalProbe, type CodexTextOnlyPolicy, assertCodexTextOnlyPolicy, codexTextOnlyThreadParams, type CodexParentArtifactScope, CODEX_PARENT_ARTIFACT_SPEC, claimCodexParentArtifactScope, reserveCodexParentArtifact, recordCodexPolicyThread, recordCodexPolicySettlement, codexPolicyOwnsSettledThread, recordCodexPolicyCheckpoint, recordCodexPolicySuccessfulTurn, recordCodexPolicySuccessfulCompaction, validateCodexPolicyFreshLaunch } from "./codex-probe.js";
import { isHistoricalCodexReceipt, isVerifiedCodexLaunchReceipt, isVerifiedCodexSettlementReceipt, type CodexNativeLaunchReceipt, type CodexNativeSettlementReceipt } from "./codex-receipts.js";
import { completedImageStatus } from "./image-status-consumption.js";
import type { CodexCapabilities } from "./codex-capabilities.js";
import { CodexChildren } from "./codex-children.js";
import { CodexSchemaErrorGuard, type CodexSchemaErrorFailure } from "./codex-schema-errors.js";
import { validateCodexResumeInstructions, type CodexResumeInstructions } from "./codex-instructions.js";
import { codexInput } from "./codex-input.js";
import { createHash } from "node:crypto";
import {observeCodexLifecycle,type CodexLifecycleEvent} from "./codex-observation.js";
import {codexReceiptProvenance} from "./codex-receipts.js";
import { CODEX_MEMORY_TOOLS, CODEX_MEMORY_CATALOG_SHA256, codexMemoryTool } from "./codex-memory.js";
import type { SessionMemoryBridge } from "./session-memory.js";
import { join, resolve } from "node:path";
import type { Readable, Writable } from "node:stream";
import type {
  Engine,
  EngineFactory,
  EngineOptions,
  NativeEngineState,
  MessageChannel,
} from "./contracts.js";
import {
  CodexConnection,
  CodexProtocolError,
  isRecord,
} from "./codex-connection.js";

/** Source/schema independently inspected from W1's rust-v0.158.0 distribution. */
export const CODEX_PIN = Object.freeze({
  version: "0.158.0",
  sourceRevision: "064c6b8c737f5b41d171fdda80bd9ef10ad06eb3",
  schemaSha256:
    "5742a9a7dd41a8b44dca3138f506e013620d4a93573c792b1e5881c053f169a7",
});
export interface RootlessCodexProcess {
  readonly stdin: Writable;
  readonly stdout: Readable;
  readonly exited: Promise<void>;
  readonly launchReceipt?: Promise<CodexNativeLaunchReceipt | undefined>;
  readonly settlementReceipt?: Promise<CodexNativeSettlementReceipt | undefined>;
  /** Must verify the exact owned container and all descendants are gone. PID exit is insufficient. */
  terminateAndConfirm(): Promise<boolean>;
}
export interface CodexRuntime {
  /** Default absent. Host observes current native/provider tool scope; no finite probe policy substitution. */
  ordinaryMemoryAdmission?(input: { sessionId: string; threadId: string; turnId: string; callId: string; tool: string; launchReceipt: CodexNativeLaunchReceipt }, signal: AbortSignal): Promise<void>;
  readonly pin: typeof CODEX_PIN;
  readonly protocolQualified: boolean;
  /** Trusted host-only opt-in; absent retains existing production chat behavior. */
  readonly nativeReceiptsRequired?: boolean;
  retentionTurnKind?(sessionId:string):"summary"|"artifacts"|"child";
  parentArtifactScope?(sessionId: string): CodexParentArtifactScope | undefined;
  registerCheckpointArtifact?(input: { scope: CodexParentArtifactScope; launchReceipt: CodexNativeLaunchReceipt; threadId: string; turnId: string; callId: string; name: string; jsonUtf8: string; sha256: string }, signal: AbortSignal): Promise<{ artifactId: string; sha256: string }>;
  onCheckpointArtifactSettled?(input: { runId: string; checkpointId: string; threadId: string; turnId: string; callId: string; name: string; artifactId: string; sha256: string; responseSha256: string }): void;
  textOnlyPolicy?(sessionId: string): CodexTextOnlyPolicy | undefined;
  authorizeNativeTurn?(input: { policy: CodexTextOnlyPolicy; launchReceipt: CodexNativeLaunchReceipt; threadId: string; params: Readonly<Record<string, unknown>>; method: "turn/start" | "thread/compact/start" }): Promise<void>;
  authorizeOriginalRead?(input: { policy: CodexTextOnlyPolicy; probe: CodexReadOriginalProbe; launchReceipt: CodexNativeLaunchReceipt; threadId: string; turnId: string; callId: string }, signal: AbortSignal): Promise<void>;
  onNativeThreadPolicy?(input: { policy: CodexTextOnlyPolicy; launchReceipt: CodexNativeLaunchReceipt; threadId: string; sandbox: Readonly<Record<string, unknown>>; requestedSettings: Readonly<Record<string, unknown>>; observedSettings: Readonly<Record<string, unknown>>; method: "thread/start" | "thread/resume" }): void;
  readOriginalProbe?(sessionId: string): CodexReadOriginalProbe | undefined;
  onNativeLaunchReceipt?(receipt: CodexNativeLaunchReceipt): void;
  onNativeSettlementReceipt?(receipt: CodexNativeSettlementReceipt): void;
  onOriginalReadSettled?(receipt: { checkpointId: string; runId: string; threadId: string; turnId: string; callId: string; arguments: Record<string, unknown>; success: boolean; responseSha256: string }): void;
  readonly capabilities?: Partial<CodexCapabilities>;
  readonly modelPolicyVersion: string;
  readonly model: string;
  readonly provider: string;
  readonly gatewayUrl: string;
  readonly contextLimit: 480000;
  /** Trusted host gate; child catalog and shared lineage must be reviewed first. */
  readonly delegationEnabled?: boolean;
  readonly imageToolEnabled?: boolean;
  readonly maxChildren?: number;
  /** Trusted host-reviewed child providers; absent keeps the Qwen-only boundary. */
  readonly qualifiedChildModels?: readonly string[];
  /** Cold parent resume only: exact reviewed catalog text from trusted host files.
   * Existing child sessions keep their original instruction provenance. */
  loadResumeInstructions?(): Promise<CodexResumeInstructions>;
  /** W1/root supplies a reviewed rootless launcher. No host spawn/default executable exists here.
   * It must use the pinned Linux image, isolated CODEX_HOME, read-only trusted provider/tool
   * config, clean environment, restricted egress, disabled hosted auth/search/plugins/retries,
   * and the existing task container boundary. stderr must be bounded and token-redacted.
   */
  launchRootless(input: {
    sessionId: string;
    profileDir: string;
    workspace: string;
    codexHome: string;
    gatewayUrl: string;
    gatewayToken: string;
    modelPolicyVersion: string;
    receiptRunId?: string;
  }): Promise<RootlessCodexProcess>;
  /** Revoke every scoped token belonging to this session before final settlement proof. */
  revokeGatewaySession(sessionId: string): void;
  /** Session/token lineage only, including accepted work after revocation; never global idleness. */
  confirmGatewaySettlement(input: {
    sessionId: string;
    gatewayToken: string;
    nativeThreadId?: string;
    activeTurnId: string | null;
  }): Promise<boolean>;
  requestTimeoutMs?: number;
  cancelTimeoutMs?: number;
}
function identifier(v: unknown): v is string {
  return (
    typeof v === "string" &&
    v.length > 0 &&
    v.length <= 512 &&
    !/[\x00-\x20\x7f]/.test(v)
  );
}
function fault(message: string, cleanupFailure?: "native_cleanup_unconfirmed" | "gateway_settlement_unconfirmed"): never {
  throw Object.assign(new CodexProtocolError(message), cleanupFailure ? { cleanupFailure } : {});
}

/** Controlled offline-qualified subset. Each turn closes its exact rootless container before
 * returning, then waits for session-owned gateway settlement. Thread state stays in task home.
 * No background native process or terminal is accepted as settled from an interrupt ACK.
 */
export class CodexEngine implements Engine {
  private child?: RootlessCodexProcess;
  private scopeStopTimer?: ReturnType<typeof setTimeout>;
  private textPolicy?: CodexTextOnlyPolicy;
  private artifactScope?: CodexParentArtifactScope;
  private probe?: CodexReadOriginalProbe;
  private memory?: SessionMemoryBridge;
  private retentionAction?:"summary"|"artifacts"|"child";
  private launchReceipt?: CodexNativeLaunchReceipt;
  private probeReads = 0;
  private probeBytes = 0;
  private probeCalls = new Map<string, { startSnapshot: string; snapshot: string; arguments: Record<string, unknown>; requestKey?: string; response?: Record<string, unknown>; artifact?: { name: string; artifactId: string; sha256: string }; serialized: boolean }>();
  private children: CodexChildren;
  private compacting = new Set<string>();
  private compactRequested = false;
  private compactObserved = false;
  private launchAttempted = false;
  private connection?: CodexConnection;
  private launchPromise?: Promise<void>;
  private cleanupPromise?: Promise<void>;
  private closing = false;
  private stopping = false;
  private stopped = false;
  private failed?: Error;
  private nativeId?: string;
  private cursor: number;
  private turnId: string | null = null;
  private active = false;
  private cancelRequested = false;
  private schemaErrors = new CodexSchemaErrorGuard();
  private schemaStop?: Promise<void>;
  private schemaError?: Error;
  private terminal?: {
    promise: Promise<"completed" | "cancelled">;
    resolve: (v: "completed" | "cancelled") => void;
    reject: (e: Error) => void;
  };
  private completedTurn?: { id: string; status: string; snapshot: string; finalMessageId?: string };
  private lastSummaryAgentMessageId?: string;
  private items = new Map<
    string,
    {
      type: string;
      completed?: string;
      text?: string;
      channel?: MessageChannel;
    }
  >();
  constructor(
    private readonly options: EngineOptions,
    private readonly runtime: CodexRuntime,
  ) {
    this.children = new CodexChildren(
      () => this.nativeId,
      options.onUpdate,
      runtime.maxChildren ?? 4,
      runtime.qualifiedChildModels ?? ["qwen3.8-27b"],
      (failure, threadId, turnId) => this.stopRepeatedSchemaError(failure, threadId, turnId),
    );
    this.nativeId = options.nativeSessionId;
    this.cursor = options.nativeState?.eventCursor ?? 0;
    const policy = runtime.textOnlyPolicy?.(options.sessionId);
    if (policy) {
      assertCodexTextOnlyPolicy(policy, options.sessionId);
      if (!runtime.nativeReceiptsRequired || (this.nativeId && !codexPolicyOwnsSettledThread(policy, this.nativeId)) || (runtime.delegationEnabled && policy.mode!=="retention-parent") || runtime.imageToolEnabled || !runtime.authorizeNativeTurn) fault("Text-only policy requires fresh receipt-qualified ownership and admission hook");
      if(policy.mode==="retention-parent"&&(!runtime.delegationEnabled||runtime.maxChildren!==1||!runtime.retentionTurnKind))fault("Retention parent lacks separately reviewed depth-one child/action admission");
      this.textPolicy = policy;
      this.scopeStopTimer = setTimeout(() => {
        this.fail(new CodexProtocolError("H041 dispatch window expired; exact cleanup required"));
        void this.close().catch(() => undefined);
      }, policy.window.expiresAtMs - policy.window.settlementReserveMs - Date.now());
      this.scopeStopTimer.unref();
    }
    const artifactScope = runtime.parentArtifactScope?.(options.sessionId);
    if (artifactScope) {
      if (!policy || !["parent-artifacts","retention-parent"].includes(policy.mode) || artifactScope.runId !== policy.runId || !runtime.registerCheckpointArtifact || (this.nativeId && !codexPolicyOwnsSettledThread(policy, this.nativeId))) fault("Parent artifact scope requires fresh reviewed owned policy");
      claimCodexParentArtifactScope(artifactScope, options.sessionId); this.artifactScope=artifactScope;
    }
    if (policy && ["parent-artifacts","retention-parent"].includes(policy.mode) && !artifactScope) fault("Parent artifact policy lacks bounded scope");
    const probe = runtime.readOriginalProbe?.(options.sessionId);
    if (probe) {
      if (!runtime.nativeReceiptsRequired || this.nativeId || runtime.delegationEnabled || runtime.imageToolEnabled) fault("Isolated original probe requires fresh receipt-qualified text-only ownership");
      if (!policy || policy.mode !== "read-original" || policy.runId !== probe.runId || !runtime.authorizeOriginalRead) fault("Original probe requires reviewed text-only scope admission");
      claimCodexReadOriginalProbe(probe, options.sessionId); this.probe = probe;
    }
    if (!policy && runtime.ordinaryMemoryAdmission && runtime.nativeReceiptsRequired && options.sessionMemory) {
      if (options.sessionMemory.sessionId !== options.sessionId) fault("Foreign ordinary memory bridge");
      if (!this.nativeId || options.sessionMemory.catalog(this.nativeId) === CODEX_MEMORY_CATALOG_SHA256) this.memory = options.sessionMemory;
    }
    if (
      options.engineKind !== "codex" ||
      options.engineVersion !== CODEX_PIN.version ||
      options.modelPolicyVersion !== runtime.modelPolicyVersion ||
      !options.onNativeState ||
      options.nativeState?.ownership !== "idle" ||
      runtime.protocolQualified !== true ||
      runtime.pin.version !== CODEX_PIN.version ||
      runtime.pin.sourceRevision !== CODEX_PIN.sourceRevision ||
      runtime.pin.schemaSha256 !== CODEX_PIN.schemaSha256 ||
      runtime.model !== "qwen3.8-27b" ||
      !identifier(runtime.provider) ||
      runtime.provider !== "sova" ||
      runtime.contextLimit !== 480000 ||
      runtime.gatewayUrl !== options.gatewayUrl ||
      runtime.gatewayUrl !== "http://10.0.2.2:8081/v1" ||
      typeof runtime.launchRootless !== "function" ||
      typeof runtime.revokeGatewaySession !== "function" ||
      typeof runtime.confirmGatewaySettlement !== "function"
    )
      fault(
        "Codex runtime policy, rootless launcher, pin or settlement capability is unqualified",
      );
  }
  private state(
    ownership: NativeEngineState["ownership"],
    activeTurnId = this.turnId,
  ) {
    this.options.onNativeState!({
      ownership,
      activeTurnId,
      eventCursor: this.cursor,
    });
  }
  private fail(error: Error) {
    if (this.stopping || this.failed) return;
    this.failed = error;
    for (const compactionId of this.compacting)
      this.options.onUpdate({
        type: "compaction",
        compactionId,
        status: "failed",
      });
    if (this.compactRequested && !this.compactObserved)
      this.options.onUpdate({
        type: "compaction",
        compactionId: "requested-compaction",
        status: "failed",
      });
    this.compacting.clear();
    try {
      this.state("uncertain");
    } catch {
      /* Predispatch ownership remains non-idle on persistence failure. */
    }
    this.terminal?.reject(error);
  }
  async start() {
    if (this.launchPromise) return this.launchPromise;
    if (this.closing || this.stopped || this.failed)
      fault("Codex engine is closed or uncertain");
    // Persist uncertainty before launching or sending any potentially effectful request.
    this.state("uncertain", null);
    this.launchPromise = this.launch();
    return this.launchPromise;
  }
  private async launch() {
    const o = this.options,
      r = this.runtime;
    if (this.textPolicy) assertCodexTextOnlyPolicy(this.textPolicy, o.sessionId);
    if (o.dispatchHeld?.()) fault("Codex launch blocked by dispatch freeze");
    const codexHome = join(resolve(o.profileDir), "codex-home");
    this.launchAttempted = true;
    this.child = await r.launchRootless({
      sessionId: o.sessionId,
      profileDir: o.profileDir,
      workspace: o.workspace,
      codexHome,
      gatewayUrl: o.gatewayUrl,
      gatewayToken: o.gatewayToken,
      modelPolicyVersion: r.modelPolicyVersion,
      ...(this.textPolicy ? { receiptRunId: this.textPolicy.runId } : {}),
    });
    if (this.closing) fault("Codex closed during launch");
    if (r.nativeReceiptsRequired) {
      const receipt = await this.child.launchReceipt;
      if (!isVerifiedCodexLaunchReceipt(receipt) || isHistoricalCodexReceipt(receipt) || receipt.sessionId !== o.sessionId || receipt.container.profileDir !== o.profileDir || receipt.container.workspace !== o.workspace || (this.textPolicy && (receipt.runId !== this.textPolicy.runId || receipt.sources["codex/config.toml"] !== this.textPolicy.configSha256 || receipt.sources["codex/models.json"] !== this.textPolicy.modelCatalogSha256))) fault("Trusted native launch receipt unavailable");
      if (this.closing || this.failed) fault("Codex closed during receipt validation");
      this.launchReceipt = receipt; r.onNativeLaunchReceipt?.(receipt);this.observeLifecycle({kind:"launch",receipt});
      if (this.textPolicy) validateCodexPolicyFreshLaunch(this.textPolicy,receipt);
    }
    this.connection = new CodexConnection(
      this.child.stdout,
      this.child.stdin,
      (method, params) => this.notification(method, params),
      (error) => this.fail(error),
      r.requestTimeoutMs,
      this.memory ? (request,signal) => this.memoryRequest(request,signal) : this.probe || this.artifactScope ? (request, signal) => this.artifactScope ? this.artifactRequest(request, signal) : this.originalRequest(request, signal) : undefined,
    );
    void this.child.exited.then(
      () =>
        this.connection?.fail(
          new CodexProtocolError(
            "App Server process exited; no request replay",
          ),
        ),
      () =>
        this.connection?.fail(
          new CodexProtocolError("App Server process ownership lost"),
        ),
    );
    const initialized = await this.connection.request("initialize", {
      clientInfo: { name: "sova", title: "Sova", version: "0.0.3" },
      capabilities: { experimentalApi: !!this.textPolicy || !!this.memory, requestAttestation: false },
    });
    if (
      !isRecord(initialized) ||
      initialized.codexHome !== codexHome ||
      initialized.platformOs !== "linux" ||
      initialized.platformFamily !== "unix" ||
      typeof initialized.userAgent !== "string" ||
      !initialized.userAgent.includes(CODEX_PIN.version)
    )
      fault(
        "App Server initialization does not attest expected Linux version and isolated home",
      );
    this.connection.initialized();
    const params = {
      model: r.model,
      modelProvider: r.provider,
      cwd: o.workspace,
      approvalPolicy: "never",
      // Read-only is a bounded probe setting, not proof of empty native read
      // roots or disabled tools. Host admission remains disabled pending scope.
      sandbox: this.probe ? "read-only" : "danger-full-access",
      ...(this.textPolicy ? codexTextOnlyThreadParams(this.textPolicy, this.nativeId ? "thread/resume" : "thread/start") : {}),
    };
    const resumeInstructions = !this.textPolicy && this.nativeId && r.loadResumeInstructions
      ? validateCodexResumeInstructions(await r.loadResumeInstructions())
      : undefined;
    const optionsNativeId = this.nativeId;
    const result = await this.connection.request(
      this.nativeId ? "thread/resume" : "thread/start",
      this.nativeId
        // Native resume still restores persisted context; its response need not
        // rehydrate the entire transcript already retained in Sova's store.
        ? { ...params, threadId: this.nativeId, excludeTurns: true, ...(resumeInstructions ? { baseInstructions: resumeInstructions.text } : {}) }
        : { ...params, ephemeral: !!this.textPolicy && !["text-only-parent", "parent-artifacts","retention-parent"].includes(this.textPolicy.mode), ...(this.memory ? {dynamicTools:CODEX_MEMORY_TOOLS} : this.probe ? { baseInstructions: this.probe.baseInstructions, dynamicTools: [CODEX_READ_ORIGINAL_SPEC] } : this.artifactScope ? {dynamicTools:[CODEX_PARENT_ARTIFACT_SPEC]} : {}) },
    );
    if (
      !isRecord(result) ||
      !isRecord(result.thread) ||
      !identifier(result.thread.id) ||
      result.model !== r.model ||
      result.modelProvider !== r.provider ||
      result.cwd !== o.workspace ||
      result.approvalPolicy !== "never" ||
      (this.textPolicy && (!isRecord(result.sandbox) || result.sandbox.type !== "readOnly")) ||
      (this.nativeId && result.thread.id !== this.nativeId) ||
      (this.textPolicy && !optionsNativeId && (!Array.isArray(result.thread.environments) || result.thread.environments.length !== 0))
    )
      fault("Native thread identity or trusted model policy mismatch");
    // History returned by resume is never appended to Sova's original message store.
    this.nativeId = result.thread.id;
    if (this.memory && !optionsNativeId) this.memory.bindCatalog(this.nativeId,CODEX_MEMORY_CATALOG_SHA256);
    if (this.textPolicy) {
      recordCodexPolicyThread(this.textPolicy, this.nativeId, this.launchReceipt!,typeof result.thread.path === "string" ? result.thread.path : undefined);
      assertCodexTextOnlyPolicy(this.textPolicy, o.sessionId);
      r.onNativeThreadPolicy?.({ policy: this.textPolicy, launchReceipt: this.launchReceipt!, threadId: this.nativeId, sandbox: Object.freeze(structuredClone(result.sandbox as Record<string, unknown>)), requestedSettings: Object.freeze(structuredClone(params)), observedSettings: Object.freeze({model:result.model, modelProvider:result.modelProvider,cwd:result.cwd,approvalPolicy:result.approvalPolicy,activePermissionProfile:structuredClone(result.activePermissionProfile ?? null),environments:structuredClone(result.thread.environments ?? null)}), method: this.nativeId === optionsNativeId ? "thread/resume" : "thread/start" });
    }
    o.onNativeSessionId(this.nativeId);
    this.observeLifecycle({kind:"thread",threadId:this.nativeId,rolloutPath:typeof result.thread.path==="string"?result.thread.path:null,method:optionsNativeId?"thread/resume":"thread/start"});
    if (resumeInstructions) o.onUpdate({
      type: "progress",
      kind: "instruction_refresh",
      label: "Resumed this native chat with the reviewed current instructions; original history retained.",
      detail: JSON.stringify({ nativeThreadId: this.nativeId, source: "cold_thread_resume.baseInstructions",
        instructionsSha256: resumeInstructions.sha256, toolPolicySha256: resumeInstructions.toolPolicySha256,
        modelPolicyVersion: r.modelPolicyVersion, existingChildrenRefreshed: false }),
    });
    this.state("idle", null);
  }
  async prompt(
    text: string,
    attachments: { path: string; mimeType: string; name: string }[] = [],
  ): Promise<"completed" | "cancelled"> {
    if (this.textPolicy && attachments.length) fault("Text-only policy cannot accept attachments");
    const input = await codexInput(text, this.options.workspace, attachments);
    if (this.active || this.stopped || this.closing || this.failed)
      fault("Codex engine cannot accept this prompt");
    await this.start();
    // Startup is shared and asynchronous; another caller may have claimed this engine.
    if (this.active || this.stopped || this.closing || this.failed)
      fault("Codex engine cannot accept this prompt");
    if (this.options.dispatchHeld?.())
      fault("Codex prompt blocked by dispatch freeze");
    this.active = true;
    this.state("uncertain", null);
    let yes!: (v: "completed" | "cancelled") => void, no!: (e: Error) => void;
    const promise = new Promise<"completed" | "cancelled">(
      (resolve, reject) => {
        yes = resolve;
        no = reject;
      },
    );
    // Errors can arrive before the turn/start response; attach a handler immediately.
    void promise.catch(() => undefined);
    this.terminal = { promise, resolve: yes, reject: no };
    try {
      const turnParams = {
        threadId: this.nativeId,
        input,
        ...(this.textPolicy ? { environments: [] } : {}),
      };
      if (this.textPolicy) {
        if(this.textPolicy.mode==="retention-parent"){this.retentionAction=this.runtime.retentionTurnKind!(this.options.sessionId);if(!["summary","artifacts","child"].includes(this.retentionAction))fault("Unqualified retention action");}
        assertCodexTextOnlyPolicy(this.textPolicy, this.options.sessionId);
        await this.runtime.authorizeNativeTurn!({ policy: this.textPolicy, launchReceipt: this.launchReceipt!, threadId: this.nativeId!, params: Object.freeze(structuredClone(turnParams)), method:"turn/start" });
        assertCodexTextOnlyPolicy(this.textPolicy, this.options.sessionId);
        if (this.closing || this.cancelRequested || this.failed) fault("Scoped turn cancelled before native dispatch");
      }
      const result = await this.connection!.request("turn/start", turnParams);
      if (!isRecord(result) || !isRecord(result.turn))
        fault("Invalid turn/start result");
      this.adoptTurn(result.turn.id);
      const outcome = await promise;
      if (this.schemaStop) {
        await this.schemaStop;
        throw this.schemaError!;
      }
      if (this.failed) throw this.failed;
      await this.cleanup();
      if (outcome === "completed" && !this.cancelRequested && this.textPolicy && this.completedTurn) recordCodexPolicySuccessfulTurn(this.textPolicy,this.completedTurn.id);
      // An absent native phase is not a reasoning/final split. Only the last
      // matching completed agent message in the successful owned turn summary
      // can become the run final, after native descendants and gateway settle.
      if (this.failed) throw this.failed;
      if (outcome === "completed" && !this.cancelRequested && this.completedTurn?.finalMessageId)
        this.options.onUpdate({
          type: "phase",
          nativeMessageId: this.completedTurn.finalMessageId,
          nativeTurnId: this.completedTurn.id,
          channel: "final",
          streamState: "completed",
          phaseSource: "codex.completed_agent_message+settled_root_turn",
        });
      return outcome;
    } catch (error) {
      if (this.schemaStop) {
        // A bounded tool failure is an ordinary failed run only after both
        // settlement proofs. A cleanup error takes precedence and stays uncertain.
        await this.schemaStop;
        throw this.schemaError!;
      }
      this.fail(
        error instanceof Error
          ? error
          : new CodexProtocolError("Native turn failed"),
      );
      throw error;
    } finally {
      this.active = false;
    }
  }
  /** Host-only supported operation. Never forwarded from browser RPC. */
  async compact(): Promise<"completed" | "cancelled"> {
    if (this.active || this.stopped || this.closing || this.failed)
      fault("Codex cannot compact now");
    await this.start();
    // Recheck after shared startup before installing a terminal or dispatching.
    if (this.active || this.stopped || this.closing || this.failed)
      fault("Codex cannot compact now");
    if (this.options.dispatchHeld?.())
      fault("Codex compaction blocked by dispatch freeze");
    this.active = true;
    this.compactRequested = true;
    this.state("uncertain", null);
    this.options.onUpdate({
      type: "context",
      used: null,
      estimated: false,
      source: "codex.compaction.awaiting-usage",
    });
    const promise = new Promise<"completed" | "cancelled">(
      (resolve, reject) => {
        this.terminal = { promise: undefined as never, resolve, reject };
      },
    );
    this.terminal!.promise = promise;
    void promise.catch(() => undefined);
    try {
      const compactParams={threadId:this.nativeId};
      if (this.textPolicy) {
        assertCodexTextOnlyPolicy(this.textPolicy,this.options.sessionId);
        await this.runtime.authorizeNativeTurn!({policy:this.textPolicy,launchReceipt:this.launchReceipt!,threadId:this.nativeId!,params:Object.freeze(compactParams),method:"thread/compact/start"});
        assertCodexTextOnlyPolicy(this.textPolicy,this.options.sessionId);
        if (this.closing || this.cancelRequested || this.failed) fault("Scoped compaction cancelled before dispatch");
      }
      await this.connection!.request("thread/compact/start", compactParams);
      const result = await promise;
      if (this.failed) throw this.failed;
      await this.cleanup();
      if(result==="completed"&&!this.cancelRequested&&this.textPolicy&&this.completedTurn)recordCodexPolicySuccessfulCompaction(this.textPolicy,this.completedTurn.id,[...this.items.entries()].filter(([,v])=>v.type==="contextCompaction"&&v.completed).map(([id])=>id));
      return result;
    } catch (error) {
      this.fail(
        error instanceof Error
          ? error
          : new CodexProtocolError("Native compaction failed"),
      );
      throw error;
    } finally {
      this.active = false;
    }
  }
  private adoptTurn(id: unknown) {
    if (!identifier(id) || (this.turnId && id !== this.turnId))
      fault("Unexpected native turn identity");
    if (!this.active) fault("Unsolicited native turn");
    this.turnId = id;
    this.state("active");
  }
  private stopRepeatedSchemaError(failure: CodexSchemaErrorFailure, threadId: string, turnId: string) {
    if (this.schemaStop || this.cancelRequested || !this.active || !this.turnId || this.completedTurn) return;
    this.cancelRequested = true;
    this.schemaError = Object.assign(new Error(
      `Native tool ${failure.server}/${failure.tool} repeated the same invalid arguments ${failure.callIds.length} times; correct the arguments before retrying.`,
    ), { code: "native_tool_schema_repetition" });
    // Keep the original call results in Activity and native history. This is a
    // separate actionable failure receipt, not a replacement tool result.
    this.options.onUpdate({
      type: "progress",
      kind: "tool_schema_error",
      label: `Stopped after ${failure.callIds.length} identical tool input errors. Correct the tool arguments before retrying.`,
      name: failure.tool,
      status: "failed",
      ...(threadId === this.nativeId ? {} : { subagentId: threadId, parentSessionId: this.nativeId }),
      detail: JSON.stringify({ threadId, turnId, ...failure }),
    });
    this.schemaStop = (async () => {
      try {
        // The root interruption scopes the stop; confirmed container cleanup
        // below also stops all owned children and drains provider lineage.
        await this.cancel();
      } catch {
        // An ACK, rejection or timeout cannot prove settlement. Cleanup can.
      }
      await this.cleanup();
    })();
    void this.schemaStop.then(
      () => this.terminal?.reject(this.schemaError!),
      error => this.terminal?.reject(error),
    );
  }
  async cancel() {
    this.cancelRequested = true;
    if (!this.active) {
      await this.close();
      return;
    }
    // turn/started may race the RPC response; never send an unscoped interruption.
    if (!this.turnId)
      fault("Turn identity unknown during cancellation; cleanup required");
    await this.connection!.request("turn/interrupt", {
      threadId: this.nativeId,
      turnId: this.turnId,
    });
    let timer: ReturnType<typeof setTimeout> | undefined;
    try {
      await Promise.race([
        this.terminal!.promise,
        new Promise<never>((_, reject) => {
          timer = setTimeout(
            () =>
              reject(
                new CodexProtocolError(
                  "Interrupt acknowledged but native terminal state is unknown",
                ),
              ),
            this.runtime.cancelTimeoutMs ?? 15000,
          );
        }),
      ]);
      await this.cleanup();
    } finally {
      clearTimeout(timer);
    }
  }
  async close() {
    this.closing = true;
    if (this.launchPromise) await this.launchPromise.catch(() => undefined);
    if (this.active && !this.completedTurn)
      this.terminal?.reject(
        new CodexProtocolError("Native turn interrupted by process cleanup"),
      );
    await this.cleanup();
  }
  private cleanup() {
    if (this.cleanupPromise) return this.cleanupPromise;
    this.cleanupPromise = (async () => {
      clearTimeout(this.scopeStopTimer);
      this.stopping = true;
      this.connection?.cancelServerRequests();
      this.state("uncertain");
      // A rejected launcher can have created a container before losing its handle.
      // Absence of a returned process is not a no-process attestation.
      let nativeSettled = !this.launchAttempted;
      if (this.child) {
        try { nativeSettled = await this.child.terminateAndConfirm(); }
        catch { nativeSettled = false; }
      }
      if (this.runtime.nativeReceiptsRequired && this.child && nativeSettled) {
        const receipt = await this.child.settlementReceipt;
        if (!isVerifiedCodexSettlementReceipt(receipt) || !this.launchReceipt || receipt.nonce !== this.launchReceipt.nonce || receipt.containerId !== this.launchReceipt.container.id || !receipt.cleanupOk) nativeSettled = false;
        else { if (this.textPolicy) recordCodexPolicySettlement(this.textPolicy, receipt); this.runtime.onNativeSettlementReceipt?.(receipt);this.observeLifecycle({kind:"settlement",receipt}); }
      }
      // Stop producers, revoke this runner capability, then prove all retained lineage drained.
      if (nativeSettled) this.children.interruptedAfterCleanup();
      this.runtime.revokeGatewaySession(this.options.sessionId);
      this.options.onExit?.();
      // An unconfirmed producer cannot safely enter an extended drain observation.
      if (!nativeSettled)
        fault("Native container cleanup is unconfirmed", "native_cleanup_unconfirmed");
      const gatewaySettled = await this.runtime.confirmGatewaySettlement({
        sessionId: this.options.sessionId,
        gatewayToken: this.options.gatewayToken,
        nativeThreadId: this.nativeId,
        activeTurnId: this.turnId,
      });
      if (!gatewaySettled)
        fault("Owned gateway settlement is unconfirmed", "gateway_settlement_unconfirmed");
      this.observeLifecycle({kind:"gateway_settled",threadId:this.nativeId??null,activeTurnId:this.turnId});
      this.stopped = true;
      this.turnId = null;
      this.state("idle", null);
    })();
    return this.cleanupPromise;
  }
  private observeLifecycle(event:CodexLifecycleEvent) {
    if(this.launchReceipt&&codexReceiptProvenance(this.launchReceipt))this.options.onNativeLifecycle?.(observeCodexLifecycle(event,this.launchReceipt));
  }
  private async artifactRequest(request: import("./codex-connection.js").CodexServerRequest, signal: AbortSignal): Promise<Record<string, unknown>> {
    const p=request.params, scope=this.artifactScope, policy=this.textPolicy;
    if(policy?.mode==="retention-parent"&&this.retentionAction!=="artifacts")fault("Artifact operation outside approved retention action");
    if (!scope || !policy || !this.launchReceipt || !this.runtime.registerCheckpointArtifact || !this.active || this.closing || this.stopping || this.cancelRequested || this.completedTurn || signal.aborted || !["arguments,callId,namespace,threadId,tool,turnId","arguments,callId,threadId,tool,turnId"].includes(Object.keys(p).sort().join()) || p.threadId!==this.nativeId || p.turnId!==this.turnId || p.namespace!=null || p.tool!=="write_checkpoint_artifact" || !identifier(p.callId)) fault("Unowned native artifact request");
    const call=this.probeCalls.get(p.callId); if (!call || call.requestKey || call.snapshot!==JSON.stringify(p.arguments)) fault("Artifact request lacks canonical owned start");
    call.requestKey=typeof request.id+":"+request.id;
    assertCodexTextOnlyPolicy(policy,this.options.sessionId);
    const artifact=reserveCodexParentArtifact(scope,p.arguments);
    const registered=await this.runtime.registerCheckpointArtifact({scope,launchReceipt:this.launchReceipt,threadId:this.nativeId!,turnId:this.turnId!,callId:p.callId,...artifact},signal);
    assertCodexTextOnlyPolicy(policy,this.options.sessionId);
    if (signal.aborted || this.closing || this.stopping || this.cancelRequested || this.completedTurn) throw Error("Artifact registration cancelled");
    if (!registered || Object.keys(registered).sort().join()!=="artifactId,sha256" || !identifier(registered.artifactId) || registered.sha256!==artifact.sha256) fault("Artifact registration lacks actual matching file digest");
    call.artifact={name:artifact.name,artifactId:registered.artifactId,sha256:artifact.sha256};
    const response={contentItems:[{type:"inputText",text:JSON.stringify(call.artifact)}],success:true};call.response=response;return response;
  }
  private async originalRequest(request: import("./codex-connection.js").CodexServerRequest, signal: AbortSignal): Promise<Record<string, unknown>> {
    const p = request.params;
    if (!this.probe || !this.active || this.closing || this.stopping || this.cancelRequested || this.completedTurn || signal.aborted || !["arguments,callId,namespace,threadId,tool,turnId", "arguments,callId,threadId,tool,turnId"].includes(Object.keys(p).sort().join()) || p.threadId !== this.nativeId || p.turnId !== this.turnId || p.namespace != null || p.tool !== "read_original" || !identifier(p.callId)) fault("Unowned native original request");
    const call = this.probeCalls.get(p.callId);
    if (!call || call.requestKey || call.snapshot !== JSON.stringify(p.arguments) || ++this.probeReads > 16) fault("Original request lacks owned canonical start");
    call.requestKey = typeof request.id + ":" + request.id;
    let text: string, success = true;
    if (!this.textPolicy || !this.launchReceipt || !this.runtime.authorizeOriginalRead) fault("Original admission unavailable");
    assertCodexTextOnlyPolicy(this.textPolicy, this.options.sessionId);
    await this.runtime.authorizeOriginalRead({ policy: this.textPolicy, probe: this.probe, launchReceipt: this.launchReceipt, threadId: this.nativeId!, turnId: this.turnId!, callId: p.callId }, signal);
    assertCodexTextOnlyPolicy(this.textPolicy, this.options.sessionId);
    if (signal.aborted || this.closing || this.stopping || this.cancelRequested || this.completedTurn) throw Error("Original admission cancelled");
    try { text = await readCodexOriginal(this.probe, p.arguments, signal); }
    catch { if (signal.aborted) throw new Error("Original read cancelled"); text = "Original excerpt unavailable within this frozen scope"; success = false; }
    assertCodexTextOnlyPolicy(this.textPolicy, this.options.sessionId);
    if (signal.aborted || this.closing || this.stopping || this.cancelRequested || this.completedTurn) throw new Error("Original result cancelled");
    if ((this.probeBytes += Buffer.byteLength(text)) > 65536) fault("Original read budget exceeded");
    const response = { contentItems: [{ type: "inputText", text }], success }; call.response = response; return response;
  }
  private async memoryRequest(request: import("./codex-connection.js").CodexServerRequest, signal: AbortSignal): Promise<Record<string,unknown>> {
    const p = request.params, memory = this.memory;
    if (!memory || !this.launchReceipt || !this.runtime.ordinaryMemoryAdmission || !this.active || this.closing || this.stopping || this.cancelRequested || this.completedTurn || signal.aborted || !["arguments,callId,namespace,threadId,tool,turnId","arguments,callId,threadId,tool,turnId"].includes(Object.keys(p).sort().join()) || p.threadId !== this.nativeId || p.turnId !== this.turnId || p.namespace != null || !codexMemoryTool(p.tool) || !identifier(p.callId)) fault("Unowned ordinary memory request");
    const call = this.probeCalls.get(p.callId);
    if (!call || call.requestKey || call.snapshot !== JSON.stringify(p.arguments) || ++this.probeReads > 16) fault("Ordinary memory request lacks canonical owned start");
    call.requestKey = typeof request.id+":"+request.id;
    await this.runtime.ordinaryMemoryAdmission({sessionId:this.options.sessionId,threadId:this.nativeId!,turnId:this.turnId!,callId:p.callId,tool:p.tool,launchReceipt:this.launchReceipt},signal);
    if (signal.aborted || this.closing || this.stopping || this.cancelRequested || this.completedTurn) throw Error("Memory read cancelled");
    memory.assertContinuationAllowed(); let result: unknown, success = true;
    try {
      const a = p.arguments; if (!isRecord(a)) throw Error("Invalid memory arguments");
      if (p.tool === "read_original") { if (Object.keys(a).sort().join() !== "limit,offset,reference" || typeof a.reference !== "string" || typeof a.offset !== "number" || typeof a.limit !== "number") throw Error("Invalid read arguments"); result=memory.read(a.reference,a.offset,a.limit); }
      else if (p.tool === "search_originals") { if (Object.keys(a).some(k => !["query","after","limit"].includes(k)) || typeof a.query !== "string" || (a.after !== undefined && typeof a.after !== "number") || (a.limit !== undefined && typeof a.limit !== "number")) throw Error("Invalid search arguments"); result=memory.search(a.query,{after:a.after as number|undefined,limit:a.limit as number|undefined}); }
      else { if (Object.keys(a).join() !== "json" || typeof a.json !== "string" || Buffer.byteLength(a.json)>16384) throw Error("Invalid state proposal"); result=memory.propose(JSON.parse(a.json)); }
    } catch { result={error:"Owned original or proposal unavailable within bounds"}; success=false; }
    await Promise.resolve();
    if (signal.aborted || this.closing || this.stopping || this.cancelRequested || this.completedTurn) throw Error("Memory result cancelled");
    const text=JSON.stringify(result); if ((this.probeBytes+=Buffer.byteLength(text))>65536) fault("Memory response budget exceeded");
    const response={contentItems:[{type:"inputText",text}],success}; call.response=response; return response;
  }
  private notification(method: string, p: Record<string, unknown>) {
    if (this.stopping) return;
    if (method === "sova/serverResponseWritten") {
      const call = [...this.probeCalls.values()].find(c => c.requestKey === p.requestKey);
      if (!call?.response) fault("Unowned dynamic response serialization"); call.serialized = true; return;
    }
    if (method === "sova/unsupportedRequest") {
      this.options.onUpdate({
        type: "progress",
        kind: "unsupported",
        label:
          "Native approval, input or tool request unavailable in Codex preview",
      });
      return;
    }
    if (method === "thread/started") {
      if (!isRecord(p.thread)) fault("Invalid native thread");
      if (this.nativeId && p.thread.id !== this.nativeId) {
        if (!this.runtime.delegationEnabled)
          fault("Native delegation unavailable");
        this.children.thread(p.thread);
      }
      return;
    }
    if (method === "thread/status/changed") return;
    if (this.children.owns(p.threadId)) {
      this.children.notification(method, p);
      this.cursor++;
      this.state("active");
      return;
    }
    if (method === "thread/tokenUsage/updated") {
      if (p.threadId !== this.nativeId)
        fault("Notification for an unowned native thread");
      if (
        !identifier(p.turnId) ||
        !isRecord(p.tokenUsage) ||
        !isRecord(p.tokenUsage.last) ||
        !Number.isSafeInteger(p.tokenUsage.last.totalTokens) ||
        Number(p.tokenUsage.last.totalTokens) < 0 ||
        p.tokenUsage.modelContextWindow !== this.runtime.contextLimit
      )
        fault("Invalid or unqualified native context usage");
      // Pinned thread/resume replays historical usage before turn/start. It is
      // neither a new turn nor proof of active ownership. Await current usage
      // instead of attributing the restored snapshot to the follow-up request.
      const current = this.active && !!this.turnId && p.turnId === this.turnId;
      this.options.onUpdate({
        type: "context",
        used: current ? Number(p.tokenUsage.last.totalTokens) : null,
        estimated: true,
        source: current
          ? "codex.latest-request.totalTokens"
          : "codex.restored-usage.awaiting-current-request",
      });
      this.cursor++;
      return;
    }
    if (method === "error" && p.willRetry === true) {
      // Pinned StreamError is an intermediate native retry, not terminal failure.
      // Preserve ownership and the pending operation; never replay its RPC here.
      if (p.threadId !== this.nativeId || !this.active || !this.turnId ||
          p.turnId !== this.turnId || this.completedTurn ||
          !isRecord(p.error) || typeof p.error.message !== "string")
        fault("Invalid or unowned native retry notification");
      this.options.onUpdate({
        type: "progress",
        kind: "native_retry",
        label: "Native request retrying; awaiting terminal state",
      });
      this.cursor++;
      return;
    }
    const relevant =
      method.startsWith("turn/") ||
      method.startsWith("item/");
    if (!relevant) {
      if (
        [
          "error",
          "model/rerouted",
          "account/updated",
          "configWarning",
        ].includes(method)
      )
        fault("Native configuration, provider or turn error");
      return;
    }
    if (p.threadId !== this.nativeId)
      fault("Notification for an unowned native thread");
    if (method === "turn/started" || method === "turn/completed") {
      if (!isRecord(p.turn)) fault("Invalid native turn");
      if (method === "turn/completed" && this.completedTurn) {
        if (
          p.turn.id !== this.completedTurn.id ||
          p.turn.status !== this.completedTurn.status ||
          JSON.stringify(p.turn) !== this.completedTurn.snapshot
        )
          fault("Conflicting duplicate terminal event");
        return;
      }
      this.adoptTurn(p.turn.id);
      if (method === "turn/completed") {
        if (
          p.turn.status === "completed" &&
          this.compactRequested &&
          !this.compactObserved
        )
          fault("Compaction completed without canonical item evidence");
        if (
          !["completed", "interrupted", "failed"].includes(
            String(p.turn.status),
          )
        )
          fault("Nonterminal completion event");
        if (
          p.turn.status === "completed" &&
          ([...this.items.values()].some((item) => !item.completed) ||
            this.children.unfinished)
        )
          fault(
            "Native items or descendants are incomplete; completion cannot be accepted",
          );
        if (p.turn.status === "completed" && p.turn.error != null)
          fault("Successful native turn contains an error");
        let finalMessageId: string | undefined;
        if (p.turn.status === "completed" && !this.cancelRequested && p.turn.itemsView === "summary") {
          // Pinned 0.158.0 emits exactly its last completed agent message here,
          // not all turn items (bespoke_event_handling.rs / thread_state.rs).
          // Match completion order as well as content; a valid earlier subset
          // or reordered list must never become the final answer.
          if (!Array.isArray(p.turn.items) || p.turn.items.length !== 1)
            fault("Invalid native terminal summary");
          const last = p.turn.items[0];
          if (!isRecord(last) || !identifier(last.id) || last.type !== "agentMessage" ||
              last.id !== this.lastSummaryAgentMessageId)
            fault("Terminal native summary is not the last completed owned message");
          const local = this.items.get(last.id);
          if (!local?.completed || last.text !== local.text ||
              (last.phase ?? null) !== (JSON.parse(local.completed).phase ?? null))
            fault("Terminal native message does not match completed owned item");
          // Explicit phases remain authoritative. Earlier unclassified messages
          // stay unclassified; content and task_complete text are never guessed.
          if (last.phase == null &&
              ![...this.items.values()].some(item => item.channel === "final"))
            finalMessageId = last.id;
        }
        if (p.turn.status !== "completed") {
          for (const compactionId of this.compacting)
            this.options.onUpdate({
              type: "compaction",
              compactionId,
              status: "failed",
            });
          this.compacting.clear();
        }
        this.completedTurn = {
          id: this.turnId!,
          status: String(p.turn.status),
          snapshot: JSON.stringify(p.turn),
          finalMessageId,
        };
        if (p.turn.status === "failed")
          this.terminal!.reject(
            new CodexProtocolError("Native turn failed; no replay"),
          );
        else
          this.terminal!.resolve(
            p.turn.status === "interrupted" || this.cancelRequested
              ? "cancelled"
              : "completed",
          );
      }
    } else {
      if (
        !this.active ||
        !this.turnId ||
        p.turnId !== this.turnId ||
        this.completedTurn
      )
        fault("Out-of-order native item event");
      if (method === "item/started" || method === "item/completed")
        this.item(method, p.item);
      else if (method === "item/agentMessage/delta") {
        if (
          !identifier(p.itemId) ||
          this.items.get(p.itemId)?.type !== "agentMessage" ||
          this.items.get(p.itemId)?.completed ||
          typeof p.delta !== "string"
        )
          fault("Out-of-order native message delta");
        const item = this.items.get(p.itemId)!;
        item.text = (item.text ?? "") + p.delta;
        this.options.onUpdate({
          type: "text",
          text: p.delta,
          nativeMessageId: p.itemId,
          channel: item.channel ?? "unknown",
          phaseSource: "codex.item.phase",
        });
      }
    }
    this.cursor++;
    this.state("active");
  }
  private item(method: string, value: unknown) {
    if (
      !isRecord(value) ||
      !identifier(value.id) ||
      typeof value.type !== "string"
    )
      fault("Invalid native item");
    if (this.textPolicy && !["userMessage", "agentMessage", "reasoning", "contextCompaction", ...(this.probe || this.artifactScope ? ["dynamicToolCall"] : []),...(this.textPolicy.mode==="retention-parent"?["collabAgentToolCall","subAgentActivity"]:[])].includes(value.type)) fault("Observed tool violates trusted text-only policy");
    const complete = method === "item/completed",
      previous = this.items.get(value.id);
    if (previous?.type !== undefined && previous.type !== value.type)
      fault("Native item changed type");
    if (complete && previous?.completed) {
      if (previous.completed !== JSON.stringify(value))
        fault("Conflicting duplicate item");
      return;
    }
    if (!complete && previous) {
      if (value.type === "dynamicToolCall" && (this.probeCalls.get(value.id)?.startSnapshot !== JSON.stringify(value) || value.namespace != null || (this.memory ? !codexMemoryTool(value.tool) : value.tool !== (this.probe ? "read_original" : "write_checkpoint_artifact")) || value.status !== "inProgress")) fault("Conflicting dynamic tool start");
      return;
    }
    if (complete && !previous) fault("Native item completed before start");
    if (!previous && this.items.size >= 10000)
      fault("Native item count exceeds preview limit");
    this.items.set(value.id, {
      ...previous,
      type: value.type,
      completed: complete ? JSON.stringify(value) : undefined,
    });
    if (value.type === "agentMessage") {
      const channel: MessageChannel =
        value.phase === "commentary"
          ? "commentary"
          : value.phase === "final_answer"
            ? "final"
            : "unknown";
      if (
        value.phase != null &&
        !["commentary", "final_answer"].includes(String(value.phase))
      )
        fault("Unsupported native phase");
      const state = this.items.get(value.id)!;
      state.channel = channel;
      if (complete) {
        if (typeof value.text !== "string")
          fault("Invalid native message text");
        const streamed = state.text ?? "";
        if (value.text.startsWith(streamed)) {
          const tail = value.text.slice(streamed.length);
          if (tail)
            this.options.onUpdate({
              type: "text",
              text: tail,
              nativeMessageId: value.id,
              channel,
              phaseSource: "codex.item.phase",
            });
        } else
          this.options.onUpdate({
            type: "text",
            text: value.text,
            replace: true,
            nativeMessageId: value.id,
            channel,
            phaseSource: "codex.item.phase",
          });
        state.text = value.text;
        // Exact pinned TurnSummary predicate: a completed nonempty message with
        // absent/final phase. Explicit commentary never replaces its candidate.
        if (channel !== "commentary" && value.text.trim())
          this.lastSummaryAgentMessageId = value.id;
      }
      this.options.onUpdate({
        type: "phase",
        nativeMessageId: value.id,
        channel,
        nativeTurnId: this.turnId!,
        streamState: complete ? "completed" : "streaming",
        phaseSource: "codex.item.phase",
      });
    } else if (value.type === "collabAgentToolCall") {
      if(this.textPolicy?.mode==="retention-parent"&&this.retentionAction!=="child")fault("Native child outside approved retention action");
      if (!this.runtime.delegationEnabled)
        fault("Native delegation unavailable");
      this.children.item(value, complete);
    } else if (value.type === "subAgentActivity") {
      if (!this.runtime.delegationEnabled)
        fault("Native delegation unavailable");
      this.children.activity(value);
    } else if (value.type === "dynamicToolCall") {
      if ((!this.probe && !this.artifactScope && !this.memory) || (this.memory ? !codexMemoryTool(value.tool) : value.tool !== (this.probe ? "read_original" : "write_checkpoint_artifact")) || value.namespace != null || !isRecord(value.arguments)) fault("Unowned canonical dynamic tool");
      const call = this.probeCalls.get(value.id);
      if (!complete) {
        if (value.status !== "inProgress" || call) fault("Invalid dynamic tool start");
        this.probeCalls.set(value.id, { startSnapshot: JSON.stringify(value), snapshot: JSON.stringify(value.arguments), arguments: structuredClone(value.arguments), serialized: false });
      } else {
        if (!call?.serialized || !call.response || call.snapshot !== JSON.stringify(value.arguments) || value.success !== call.response.success || value.status !== (value.success ? "completed" : "failed") || JSON.stringify(value.contentItems) !== JSON.stringify(call.response.contentItems)) fault("Dynamic tool completion lacks actual owned response");
        if (this.memory) this.memory.recordConsumption({threadId:this.nativeId!,turnId:this.turnId!,callId:value.id,tool:String(value.tool),success:value.success as boolean,responseSha256:createHash("sha256").update(JSON.stringify(call.response)).digest("hex")});
        else if (this.probe) this.runtime.onOriginalReadSettled?.({ checkpointId: this.probe.checkpointId, runId: this.probe.runId, threadId: this.nativeId!, turnId: this.turnId!, callId: value.id, arguments: call.arguments, success: value.success as boolean, responseSha256: createHash("sha256").update(JSON.stringify(call.response)).digest("hex") });
        else if (this.artifactScope && call.artifact && value.success) {
          recordCodexPolicyCheckpoint(this.textPolicy!,this.nativeId!,{checkpointId:this.artifactScope.checkpointId,turnId:this.turnId!,callId:value.id,...call.artifact});
          this.observeLifecycle({kind:"checkpoint_artifact",checkpointId:this.artifactScope.checkpointId,threadId:this.nativeId!,turnId:this.turnId!,callId:value.id,...call.artifact});
          this.runtime.onCheckpointArtifactSettled?.({runId:this.artifactScope.runId,checkpointId:this.artifactScope.checkpointId,threadId:this.nativeId!,turnId:this.turnId!,callId:value.id,...call.artifact,responseSha256:createHash("sha256").update(JSON.stringify(call.response)).digest("hex")});
        }
      }
    } else if (value.type === "contextCompaction") {
      this.observeLifecycle({kind:"compaction",threadId:this.nativeId!,turnId:this.turnId!,compactionId:value.id,status:complete?"completed":"start"});
      this.compactObserved = true;
      if (complete) this.compacting.delete(value.id);
      else this.compacting.add(value.id);
      this.options.onUpdate({
        type: "compaction",
        compactionId: value.id,
        status: complete ? "completed" : "start",
      });
      this.options.onUpdate({
        type: "context",
        used: null,
        estimated: false,
        source: "codex.compaction.awaiting-usage",
      });
    } else if (
      ["commandExecution", "fileChange", "mcpToolCall"].includes(value.type)
    ) {
      if (
        complete &&
        !["completed", "failed", "declined"].includes(String(value.status))
      )
        fault("Native tool completion is not terminal");
      const consumed = complete ? completedImageStatus(value) : undefined;
      if (complete) this.options.onUpdate({ type: "tool_original", nativeThreadId: this.nativeId!, nativeTurnId: this.turnId!, nativeItemId: value.id, toolType: value.type,
        rawUtf8: JSON.stringify(value), ...(value.type === "commandExecution" && typeof value.aggregatedOutput === "string" ? { outputUtf8: value.aggregatedOutput } : {}) });
      if (consumed) this.options.onUpdate({ type: "image_status_result", ...consumed });
      const command =
        value.type === "commandExecution" && typeof value.command === "string"
          ? value.command.slice(0, 8192)
          : undefined;
      const args = isRecord(value.arguments) ? value.arguments : undefined;
      const url =
        args && typeof args.url === "string" && /^https?:\/\//.test(args.url)
          ? args.url.slice(0, 2048)
          : undefined;
      const detail =
        value.type === "commandExecution"
          ? JSON.stringify({
              cwd: value.cwd,
              processId: value.processId,
              output: value.aggregatedOutput,
              exitCode: value.exitCode,
            })
          : value.type === "fileChange"
            ? JSON.stringify(value.changes)
            : JSON.stringify({
                server: value.server,
                arguments: value.arguments,
                result: value.result,
                error: value.error,
              });
      this.options.onUpdate({
        type: "progress",
        kind: "tool",
        label:
          command ?? (typeof value.tool === "string" ? value.tool : value.type),
        toolCallId: value.id,
        toolActivityId: value.id,
        name: typeof value.tool === "string" ? value.tool : value.type,
        command,
        url,
        detail: detail?.slice(0, 8192),
        status: complete
          ? value.status === "declined"
            ? "cancelled"
            : String(value.status)
          : "in_progress",
      });
    } else if (value.type === "reasoning") {
      // Schema presence alone does not verify the local provider's reasoning contract.
      // No reasoning text or encrypted state is synthesized or exposed in this preview.
    } else if (value.type !== "userMessage")
      fault(`Native item capability unavailable: ${value.type}`);
    const schemaFailure = this.schemaErrors.observe(value, complete);
    if (schemaFailure) this.stopRepeatedSchemaError(schemaFailure, this.nativeId!, this.turnId!);
  }
}
export const codexEngineFactory =
  (runtime: CodexRuntime): EngineFactory =>
  (options) =>
    new CodexEngine(options, runtime);
