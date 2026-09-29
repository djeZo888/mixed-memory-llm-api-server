import { completedImageStatus } from "./image-status-consumption.js";
import type { CodexCapabilities } from "./codex-capabilities.js";
import { CodexChildren } from "./codex-children.js";
import { CodexSchemaErrorGuard, type CodexSchemaErrorFailure } from "./codex-schema-errors.js";
import { validateCodexResumeInstructions, type CodexResumeInstructions } from "./codex-instructions.js";
import { codexInput } from "./codex-input.js";
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
  /** Must verify the exact owned container and all descendants are gone. PID exit is insufficient. */
  terminateAndConfirm(): Promise<boolean>;
}
export interface CodexRuntime {
  readonly pin: typeof CODEX_PIN;
  readonly protocolQualified: boolean;
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
    });
    if (this.closing) fault("Codex closed during launch");
    this.connection = new CodexConnection(
      this.child.stdout,
      this.child.stdin,
      (method, params) => this.notification(method, params),
      (error) => this.fail(error),
      r.requestTimeoutMs,
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
      capabilities: { experimentalApi: false, requestAttestation: false },
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
      sandbox: "danger-full-access",
    };
    const resumeInstructions = this.nativeId && r.loadResumeInstructions
      ? validateCodexResumeInstructions(await r.loadResumeInstructions())
      : undefined;
    const result = await this.connection.request(
      this.nativeId ? "thread/resume" : "thread/start",
      this.nativeId
        ? { ...params, threadId: this.nativeId, ...(resumeInstructions ? { baseInstructions: resumeInstructions.text } : {}) }
        : { ...params, ephemeral: false },
    );
    if (
      !isRecord(result) ||
      !isRecord(result.thread) ||
      !identifier(result.thread.id) ||
      result.model !== r.model ||
      result.modelProvider !== r.provider ||
      result.cwd !== o.workspace ||
      result.approvalPolicy !== "never" ||
      (this.nativeId && result.thread.id !== this.nativeId)
    )
      fault("Native thread identity or trusted model policy mismatch");
    // History returned by resume is never appended to Sova's original message store.
    this.nativeId = result.thread.id;
    o.onNativeSessionId(this.nativeId);
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
    const input = await codexInput(text, this.options.workspace, attachments);
    if (this.active || this.stopped || this.closing || this.failed)
      fault("Codex engine cannot accept this prompt");
    await this.start();
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
      const result = await this.connection!.request("turn/start", {
        threadId: this.nativeId,
        input,
      });
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
      await this.connection!.request("thread/compact/start", {
        threadId: this.nativeId,
      });
      const result = await promise;
      if (this.failed) throw this.failed;
      await this.cleanup();
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
      this.stopping = true;
      this.state("uncertain");
      // A rejected launcher can have created a container before losing its handle.
      // Absence of a returned process is not a no-process attestation.
      let nativeSettled = !this.launchAttempted;
      if (this.child) {
        try { nativeSettled = await this.child.terminateAndConfirm(); }
        catch { nativeSettled = false; }
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
      this.stopped = true;
      this.turnId = null;
      this.state("idle", null);
    })();
    return this.cleanupPromise;
  }
  private notification(method: string, p: Record<string, unknown>) {
    if (this.stopping) return;
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
    const complete = method === "item/completed",
      previous = this.items.get(value.id);
    if (previous?.type !== undefined && previous.type !== value.type)
      fault("Native item changed type");
    if (complete && previous?.completed) {
      if (previous.completed !== JSON.stringify(value))
        fault("Conflicting duplicate item");
      return;
    }
    if (!complete && previous) return;
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
      if (!this.runtime.delegationEnabled)
        fault("Native delegation unavailable");
      this.children.item(value, complete);
    } else if (value.type === "subAgentActivity") {
      if (!this.runtime.delegationEnabled)
        fault("Native delegation unavailable");
      this.children.activity(value);
    } else if (value.type === "contextCompaction") {
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
