import { createCodexAutomaticRoute, isCodexRouteFollowup, type CodexAutomaticIntent } from "./codex-automatic-routing.js";
import {boundedRecoveryObservation,type CodexRecoveryObservers} from "./codex-recovery-observation.js";
import { nativeMedia } from "./codex-input.js";
import { createHash, randomUUID } from "node:crypto";
import type { Store, Run, StoredSession } from "./store.js";
import { Files } from "./files.js";
import type {
  Engine,
  EngineKind,
  EngineFactory,
  EngineUpdate,
  Context,
  Status,
  MessagePhase,
  Activity,
} from "./contracts.js";
import { CONTEXT_LIMIT } from "./contracts.js";
import { assertEngineAvailable, createEngineRouter, type EnginePolicy } from "./engine-router.js";
import { ApiError } from "./errors.js";
export interface NativeReplacementCommitInput {readonly sessionId:string;readonly runId:string;readonly checkpoint:Readonly<import("./session-checkpoint.js").SessionCheckpointRecord>}
export type NativeReplacementCommitVerifier=(input:NativeReplacementCommitInput)=>Promise<void>;
export interface BrokerOptions extends CodexRecoveryObservers {
  technicalVisionAvailable?: () => boolean;
  technicalVisionContext?: (sessionId: string, runId: string, fileIds: string[]) => Promise<string>;
  cancelTechnicalVision?: (sessionId: string) => Promise<void>;
  /** Trusted host source seam only, absent by default; never accepted from API/model input. */
  beforeNativeReplacementCommit?:NativeReplacementCommitVerifier;
  store: Store;
  files: Files;
  engineFactory: EngineFactory;
  codexEngineFactory?: EngineFactory;
  codexGatewayUrl?: string;
  enginePolicy?: EnginePolicy;
  launcher: string;
  gatewayUrl: string;
  issueToken: (sessionId: string) => string;
  revokeToken: (token: string) => void;
  maxQueued?: number;
  /** Protected durable host gate; never supplied by browser/task requests. */
  dispatchHeld?: () => boolean;
  /** Awaited protected task challenge in the actual product process. */
  onNewOwnedSession?: (input:{sessionId:string;workspaceId:string;engineKind:EngineKind})=>Promise<void>;
  beforeDispatchAdmission?: (input:{sessionId:string;requestId:string;phase:'enqueue'|'queued-start'},signal:AbortSignal)=>Promise<void>;
  cancelImages?: (sessionId: string) => void;
  /** Read-only app state, refreshed immediately before a user-requested turn. */
  imageContext?: (sessionId: string, currentRunId: string) => string;
  /** Trusted exact-session/run gate; ordinary capability stays independently qualified. */
  imageAcceptance?: (sessionId: string) => boolean;
  /** Trusted unbound ticket permits reference staging only, never image dispatch. */
  imageReferenceAcceptance?: (sessionId: string) => boolean;
  /** Trusted one-shot scope binder, after durable enqueue and before dispatch. */
  onRunAccepted?: (sessionId: string, runId: string) => void;
  /** Revoke owned acceptance after any attempt; completion is not settlement proof. */
  onRunFinished?: (sessionId: string, runId: string) => void;
  validateCodexImageReferences?: (sessionId: string, count: number) => Promise<void>;
}
interface Runner {
  engine: Engine;
  token: string;
  closePromise?: Promise<boolean>;
}
interface Active {
  run: Run;
  cancelled: boolean;
  settled: Promise<void>;
  cancelPromise?: Promise<void>;
  cancelFailed?: boolean;
  cleanupPromise?: Promise<boolean>;
}
// Only known cancellation-settlement failures carry this tag. Unrelated errors
// after a prompt must remain visible even when Stop has also been requested.
class CancellationSettlementError extends Error {
  constructor(
    readonly requestedAtFailure: boolean,
    options?: ErrorOptions,
  ) {
    super("Cancellation settlement was not confirmed", options);
  }
}
export class Broker {
  readonly store: Store;
  readonly files: Files;
  private queues = new Map<string, Run[]>();
  private active = new Map<string, Active>();
  private runners = new Map<string, Runner>();
  private closing = false;
  private recoveries = new Map<string,{abort:AbortController;settled:Promise<void>}>();
  private admissionPending = new Map<string,{abort:AbortController;settled:Promise<void>}>();
  constructor(readonly options: BrokerOptions) {
    this.store = options.store;
    this.files = options.files;
  }
  dispatchImpact() {
    return {
      active: this.active.size,
      queued: [...this.queues.values()].reduce((n, q) => n + q.length, 0),
    };
  }
  async admitEnqueue(sessionId:string,requestId:string){
    if(this.closing)throw new ApiError(503,'shutting_down','Server is shutting down');
    this.store.getSession(sessionId); // Ownership lookup before challenge.
    const abort=new AbortController(),key='enqueue:'+requestId;
    const settled=Promise.resolve().then(()=>this.options.beforeDispatchAdmission?.({sessionId,requestId,phase:'enqueue'},abort.signal));
    this.admissionPending.set(key,{abort,settled});try{await settled;}finally{this.admissionPending.delete(key);}
    if(this.closing||this.options.dispatchHeld?.())throw new ApiError(503,'dispatch_frozen','Protected dispatch is held');
  }
  notifyDispatchChanged() {
    if (!this.options.dispatchHeld?.())
      for (const workspace of this.queues.keys()) this.pump(workspace);
  }
  private async waitForDispatch(active?: Active) {
    while (this.options.dispatchHeld?.() && !this.closing && !active?.cancelled)
      await new Promise<void>((resolve) => {
        const timer = setTimeout(resolve, 100);
        timer.unref();
      });
    if (this.closing || active?.cancelled)
      throw new Error("Dispatch cancelled while frozen");
  }
  async recoverMemory(sessionId: string, checkpointId: string, host: NonNullable<import("./app.js").AppOptions["memoryRecoveryHost"]>) {
    const session=this.store.getSession(sessionId);
    if(this.closing || this.options.dispatchHeld?.() || this.active.has(session.workspaceId) || this.queues.get(session.workspaceId)?.length)
      throw new ApiError(409,"memory_recovery_busy","Workspace has active work");
    const reservation=this.store.reserveWorkspaceRecovery(sessionId,checkpointId); let verified=false;
    const abort=new AbortController();let finished!:()=>void;const settled=new Promise<void>(r=>{finished=r;});this.recoveries.set(reservation.id,{abort,settled});
    try {
      const evidence=await host({sessionId,checkpointId,memory:this.store.memory.bridge(sessionId),reservation,signal:abort.signal});
      const assertCommitOwner=()=>{
        abort.signal.throwIfAborted();
        const current=this.store.getSession(sessionId);
        this.store.assertWorkspaceRecovery(reservation,sessionId,checkpointId);
        if(this.closing||this.options.dispatchHeld?.()||this.store.isQuarantined(current.workspaceId)||current.nativeState.ownership!=="idle"||current.nativeState.activeTurnId!==null||this.active.has(current.workspaceId)||this.queues.get(current.workspaceId)?.length||this.store.db.prepare("SELECT id FROM runs WHERE workspace_id=? AND status IN ('queued','running','cancelling') LIMIT 1").get(current.workspaceId))throw Error("Recovery commit owner unavailable");
      };
      assertCommitOwner();
      if(this.options.beforeNativeRecovery)await boundedRecoveryObservation(abort.signal,signal=>this.options.beforeNativeRecovery!(Object.freeze({sessionId,checkpointId,stage:"before-commit"}),signal));
      // No await between final exact ownership recheck and synchronous Store CAS.
      assertCommitOwner();
      const result=this.store.checkpoints.recoverWithFreshParent(sessionId,checkpointId,evidence);
      verified=true; return result;
    } finally {
      try{this.store.finishWorkspaceRecovery(reservation,verified);}finally{this.recoveries.delete(reservation.id);finished();}
      queueMicrotask(()=>this.pump(session.workspaceId));
    }
  }
  currentTechnicalVisionRun(sessionId: string) {
    const active = [...this.active.values()].find(a => a.run.sessionId === sessionId && a.run.kind === "message" && !a.cancelled && this.store.db.prepare("SELECT status FROM runs WHERE id=?").get(a.run.id)?.status === "running");
    return active ? { sessionId, workspaceId: active.run.workspaceId, runId: active.run.id } : undefined;
  }
  currentImageRun(sessionId: string) {
    const active = [...this.active.values()].find(
      (a) => a.run.sessionId === sessionId && !a.cancelled,
    );
    return active
      ? { runId: active.run.id, workspaceId: active.run.workspaceId }
      : undefined;
  }
  async createSession(workspaceId?: string, engineKind: EngineKind = "codex") {
    assertEngineAvailable(engineKind, this.options.enginePolicy, this.options.codexEngineFactory);
    const s = this.store.createSession(workspaceId, engineKind, engineKind === "codex" ? this.options.enginePolicy!.codex : {});
    await this.files.prepare(s.id, s.workspaceId);
    await this.options.onNewOwnedSession?.({sessionId:s.id,workspaceId:s.workspaceId,engineKind:s.engineKind});
    return this.store.publicSession(s);
  }
  enqueue(
    sessionId: string,
    kind: Run["kind"],
    text: string,
    attachmentIds: string[] = [],
    imageReferences: string[] = [],
    compactionActionId?: string,
    submissionId?: string,
    handoffEngineKind?: EngineKind,
  ): string {
    const s = this.store.getSession(sessionId);
    if (kind === "compact") {
      if (!compactionActionId)
        throw new ApiError(
          400, "invalid_action", "Context compaction requires an action ID",
        );
      // Retrieving a durable action never redispatches it, even after a restart
      // changed the original run to interrupted or disabled the engine policy.
      const existing = this.store.compactionRun(s.id, compactionActionId);
      if (existing) return existing;
    }
    const admit = (s: StoredSession) => {
      if(this.store.workspaceRecoveryBlocked(s.workspaceId)) throw new ApiError(409,"memory_recovery_busy","Workspace has an active or unresolved recovery owner");
      if (s.engineKind === "codex") this.store.memory.bridge(s.id).assertContinuationAllowed();
      assertEngineAvailable(s.engineKind, this.options.enginePolicy, this.options.codexEngineFactory);
      if (kind === "handoff")
        assertEngineAvailable(handoffEngineKind ?? s.engineKind, this.options.enginePolicy, this.options.codexEngineFactory);
      if (kind === "compact") {
        if (s.engineKind !== "codex")
          throw new ApiError(
            409, "compaction_unavailable",
            "Manual context compaction is available for Codex chats only",
          );
        if (!s.nativeSessionId)
          throw new ApiError(
            409, "compaction_empty",
            "Start a Codex conversation before compacting its context",
          );
        const pending = [
          ...(this.queues.get(s.workspaceId) ?? []),
          ...[...this.active.values()].map((active) => active.run),
        ];
        if (pending.some((run) => run.sessionId === s.id && run.kind === "compact"))
          throw new ApiError(
            409, "compaction_pending",
            "This chat already has a pending context compaction",
          );
      }
      if (s.engineKind === "codex" && imageReferences.length && !this.options.enginePolicy?.codex?.imageToolEnabled && this.options.imageAcceptance?.(sessionId) !== true && this.options.imageReferenceAcceptance?.(sessionId) !== true)
        throw new ApiError(400,"codex_image_tool_unavailable","Codex image specialist is not qualified");
      if (this.options.dispatchHeld?.())
        throw new ApiError(
          503,
          "dispatch_frozen",
          "New work is paused for a confirmed administrative operation",
        );
      if (this.closing)
        throw new ApiError(503, "shutting_down", "Server is shutting down");
      if (s.deleteRequested)
        throw new ApiError(409, "deleting", "Session is deleting");
      if (this.store.isQuarantined(s.workspaceId))
        throw new ApiError(
          409,
          "workspace_quarantined",
          "Workspace requires operator settlement review after an interrupted engine",
        );
      if (
        [...this.queues.values()].reduce((n, q) => n + q.length, 0) >=
        (this.options.maxQueued ?? 100)
      )
        throw new ApiError(429, "queue_full", "Run queue is full");
      for (const id of attachmentIds) {
        const f = this.store.file(id);
        if (s.engineKind === "codex" && nativeMedia(f.mimeType) && !(this.options.technicalVisionAvailable?.() && ["image/png", "image/jpeg"].includes(f.mimeType)))
          throw new ApiError(400,"codex_media_unsupported","Codex native media is not qualified; use an available image specialist");
        if (f.kind !== "attachment" || f.sessionId !== sessionId)
          throw new ApiError(
            400,
            "invalid_attachment",
            "Attachment does not belong to this chat",
          );
      }
      for (const id of imageReferences) {
        const f = this.store.file(id);
        if (
          (f.kind !== "artifact" && !(s.engineKind === "codex" && f.kind === "attachment")) ||
          f.sessionId !== sessionId ||
          !["image/png", "image/jpeg"].includes(f.mimeType)
        )
          throw new ApiError(
            400,
            "invalid_image_reference",
            "Image artifact does not belong to this chat",
          );
      }
      return ![...this.active.values()].some((a) => a.run.sessionId === s.id);
    };
    if (kind === "message") {
      // Legacy callers without IDs explicitly create a fresh submission each time.
      const result = this.store.createMessageSubmission(s.id, submissionId ?? randomUUID(),
        { text, attachmentIds, imageReferences }, admit);
      if (!result.created) return result.runId;
      this.queueRun(s, result.run);
      return result.runId;
    }
    admit(s);
    const run = this.store.createRun(s, kind, text, attachmentIds, compactionActionId,
      kind === "handoff" ? handoffEngineKind ?? s.engineKind : undefined);
    if (imageReferences.length)
      this.store.db
        .prepare("INSERT INTO h003_run_image_refs VALUES(?,?)")
        .run(run.id, JSON.stringify(imageReferences));
    this.store.touchContext(s.id, run.id);
    if (![...this.active.values()].some((a) => a.run.sessionId === s.id))
      this.store.setStatus(s.id, "queued", run.id);
    this.store.emit(
      s.id,
      "progress",
      { kind: "queue", label: "Waiting for workspace" },
      run.id,
    );
    this.queueRun(s, run);
    return run.id;
  }
  private queueRun(s: StoredSession, run: Run) {
    const queue = this.queues.get(s.workspaceId) ?? [];
    queue.push(run);
    this.queues.set(s.workspaceId, queue);
    try { this.options.onRunAccepted?.(s.id, run.id); } catch { /* Optional acceptance must fail closed without cancelling ordinary work. */ }
    queueMicrotask(() => this.pump(s.workspaceId));
  }
  private pump(workspaceId: string, admittedRun?:string) {
    if(this.options.beforeDispatchAdmission&&!admittedRun){
      const run=this.queues.get(workspaceId)?.[0];
      if(!run||this.closing||this.active.has(workspaceId)||this.admissionPending.has(workspaceId))return;
      const abort=new AbortController();let settled:Promise<void>;
      settled=Promise.resolve().then(async()=>{try{await this.options.beforeDispatchAdmission!({sessionId:run.sessionId,requestId:run.id,phase:'queued-start'},abort.signal);
        if(!this.closing&&!abort.signal.aborted&&this.queues.get(workspaceId)?.[0]===run&&!this.options.dispatchHeld?.())this.pump(workspaceId,run.id);
      }catch{/* No native start; queued owner is retained until Stop or fresh reviewed admission. */}finally{this.admissionPending.delete(workspaceId);}});
      this.admissionPending.set(workspaceId,{abort,settled});return;
    }
    if (
      this.closing ||
      this.options.dispatchHeld?.() ||
      this.active.has(workspaceId) ||
      this.store.workspaceRecoveryBlocked(workspaceId)
    )
      return;
    const queue = this.queues.get(workspaceId);
    const run = queue?.shift();
    if (!run) return;
    if (this.store.isQuarantined(workspaceId)) {
      this.store.updateRun(run.id, "interrupted");
      this.store.setStatus(run.sessionId, "interrupted", run.id);
      this.store.emit(
        run.sessionId,
        "error",
        {
          code: "workspace_quarantined",
          message: "Workspace is blocked pending operator settlement review",
        },
        run.id,
      );
      this.store.emit(run.sessionId, "done", { runId: run.id }, run.id);
      queueMicrotask(() => this.pump(workspaceId));
      return;
    }
    const active: Active = {
      run,
      cancelled: false,
      settled: Promise.resolve(),
    };
    this.active.set(workspaceId, active);
    active.settled = this.execute(active)
      .catch(() => {
        this.store.quarantine(workspaceId, "broker_failure");
      })
      .finally(() => {
        this.active.delete(workspaceId);
        queueMicrotask(() => this.pump(workspaceId));
      });
  }
  private automaticRoute(s:StoredSession,run:Run) {
    if(s.engineKind!=="codex"||run.kind!=="message")return undefined;
  let priorIntent: CodexAutomaticIntent | undefined;
  // Read the saved one-parent history; repeated follow-ups do not lose the original route.
  for(const previous of this.store.db.prepare("SELECT text, attachment_ids FROM runs WHERE session_id=? AND kind='message' AND status='completed' AND id<>? ORDER BY created_at DESC,rowid DESC").iterate(s.id,run.id) as Iterable<{text:string;attachment_ids:string}>) {
    const previousImages = (JSON.parse(previous.attachment_ids) as string[]).some(id=>{try{return ["image/png","image/jpeg","application/pdf"].includes(this.store.file(id).mimeType);}catch{return false;}});
    const previousRoute=createCodexAutomaticRoute({text:previous.text,hasImages:previousImages});
    if(previousRoute.intent === "ordinary" && isCodexRouteFollowup(previous.text))continue;
    priorIntent=previousRoute.intent;break;
  }
    const hasImages=run.attachmentIds.some(id=>{try{return ["image/png","image/jpeg","application/pdf"].includes(this.store.file(id).mimeType);}catch{return false;}});
    return createCodexAutomaticRoute({text:run.text,hasImages,previous:priorIntent});
  }
  private async runner(
    s: StoredSession,
    onUpdate: (update: EngineUpdate) => void,
    run: Run,
  ) {
    // Update callbacks are per turn; an existing runner reads a mutable dispatcher.
    let runner = this.runners.get(s.id) as
      (Runner & { update: (u: EngineUpdate) => void }) | undefined;
    if (runner) {
      runner.update = onUpdate;
      return runner.engine;
    }
    await this.files.prepare(s.id, s.workspaceId);
    if (this.closing)
      throw new Error("Server is shutting down before engine launch");
    const token = this.options.issueToken(s.id);
    const entry = {
      token,
      engine: null as unknown as Engine,
      update: onUpdate,
    };
    const factory = createEngineRouter(this.options.engineFactory, this.options.codexEngineFactory, this.options.enginePolicy);
    try {
    entry.engine = factory({
      sessionId: s.id,
      engineKind: s.engineKind,
      engineVersion: s.engineVersion,
      modelPolicyVersion: s.modelPolicyVersion,
      nativeState: s.nativeState,
      ...(this.options.enginePolicy?.codex?.imageGenerationEnabled===true ? {nativeAutomaticRoute:this.automaticRoute(s,run)}:{}),
      onNativeState: (state) => this.store.setNativeState(s.id, s.engineKind, state),
      dispatchHeld: this.options.dispatchHeld,
      profileDir: this.files.profile(s.id),
      workspace: this.files.workspace(s.workspaceId),
      onNativeLifecycle: e => this.store.checkpoints.recordNativeObservation(s.id,run.id,e),
      nativeSessionId: s.nativeSessionId,
      ...(s.engineKind === "codex" ? { sessionMemory: this.store.memory.bridge(s.id) } : {}),
      launcher: this.options.launcher,
      gatewayUrl: s.engineKind === "codex" ? this.options.codexGatewayUrl ?? this.options.gatewayUrl : this.options.gatewayUrl,
      gatewayToken: token,
      stderrPath: this.files.log(s.id),
      onExit: () => this.options.revokeToken(token),
      onNativeSessionId: (id) => this.store.setNative(s.id, id, s.engineKind),
      onUpdate: (u) => entry.update(u),
    });
    } catch (error) { this.options.revokeToken(token); throw error; }
    this.runners.set(s.id, entry);
    await this.waitForDispatch();
    await entry.engine.start();
    return entry.engine;
  }
  private async execute(active: Active) {
    const run = active.run;
    let assistantId: string | undefined;
    const assistantIds = new Set<string>();
    let finalCandidate: { messageId: string; phase: MessagePhase } | undefined;
    const phases = new Map<string, MessagePhase>();
    const messageId = (native: string | undefined, thought = false) =>
      "m_" +
      createHash("sha256")
        .update(
          JSON.stringify([
            run.id,
            native ?? "legacy",
            thought ? "thought" : "text",
          ]),
        )
        .digest("hex");
    let summary = "";
    const summaryParts = new Map<string, string>();
    let success = false;
    let verificationRejected = false;
    let cleanupConfirmed = false;
    let promptRejectedDuringCancellation = false;
    let failureStatus: Status = "failed";
    const artifactJobs: Promise<unknown>[] = [];
    try {
      const s = this.store.getSession(run.sessionId);
      this.store.updateRun(run.id, "running");
      this.store.setStatus(s.id, "running", run.id);
      this.store.markContextStale(s.id, run.id);
      const before = new Map(
        (await this.files.discover(s.id)).map((f) => [
          f.path,
          `${f.size}:${f.mtime}`,
        ]),
      );
      const update = (u: EngineUpdate) => {
        if (this.active.get(s.workspaceId) !== active) return;
        if (u.type === "tool_original") {
          const owner = this.store.getSession(s.id);
          if (owner.engineKind !== "codex" || owner.nativeSessionId !== u.nativeThreadId || owner.nativeState.activeTurnId !== u.nativeTurnId)
            throw Error("Unowned terminal original");
          this.store.memory.retain(s.id,"tool",`${run.id}:tool:${u.nativeItemId}`,Buffer.from(u.rawUtf8),u.nativeTruncated ? "native_truncated" : "complete");
          if (u.outputUtf8 !== undefined) this.store.memory.retain(s.id,"tool",`${run.id}:output:${u.nativeItemId}`,Buffer.from(u.outputUtf8),u.nativeTruncated ? "native_truncated" : "complete");
        } else if (u.type === "text") {
          if (!u.text && !u.replace) return;
          const thought = u.channel === "thought";
          const id = messageId(u.nativeMessageId, thought);
          if (!thought) {
            summaryParts.set(id, u.replace ? u.text : (summaryParts.get(id) ?? "") + u.text);
            summary = [...summaryParts.values()].join("");
          }
          const phase = phases.get(id) ?? {
            phase: (thought
              ? "thinking"
              : "unclassified") as MessagePhase["phase"],
            ...(u.nativeMessageId
              ? { nativeMessageId: u.nativeMessageId }
              : {}),
            streamState: "streaming" as const,
          };
          this.store.appendDelta(s.id, id, u.text, run.id, phase, u.replace);
          assistantIds.add(id);
          if (!thought) assistantId = id;
        } else if (u.type === "phase") {
          const id = messageId(u.nativeMessageId);
          const phase: MessagePhase = {
            phase:
              u.channel === "final"
                ? "final"
                : u.channel === "commentary"
                  ? "intermediate"
                  : "unclassified",
            nativeMessageId: u.nativeMessageId,
            ...(u.nativeTurnId ? { nativeTurnId: u.nativeTurnId } : {}),
            streamState: u.streamState ?? "completed",
          };
          if (u.channel === "final") {
            finalCandidate = { messageId: id, phase };
            phase.phase = "unclassified";
            // Keep a distinct candidate copy until the final app cancellation check.
            finalCandidate.phase = { ...phase, phase: "final" };
          }
          phases.set(id, phase);
          this.store.setMessagePhase(s.id, id, run.id, phase);
          const thoughtId = messageId(u.nativeMessageId, true);
          const thoughtPhase: MessagePhase = { ...phase, phase: "thinking" };
          phases.set(thoughtId, thoughtPhase);
          this.store.setMessagePhase(s.id, thoughtId, run.id, thoughtPhase);
        } else if (u.type === "progress") {
          const { type, ...data } = u;
          this.store.emit(
            s.id,
            "progress",
            {
              ...data,
              kind: u.kind.slice(0, 100),
              label: u.label.slice(0, 300),
              ...(u.toolActivityId
                ? { toolActivityId: `${run.id}:${u.toolActivityId}` }
                : {}),
            },
            run.id,
          );
          if (u.subagents) this.store.setSubagents(s.id, run.id, u.subagents);
          const nativeActivityId = u.toolCallId ?? u.subagentId;
          if (
            nativeActivityId &&
            (u.kind === "tool" || u.kind === "subagent")
          ) {
            const statuses: Record<string, Activity["status"]> = {
              queued: "pending",
              pending: "pending",
              running: "in_progress",
              in_progress: "in_progress",
              completed: "completed",
              failed: "failed",
              stopped: "cancelled",
              cancelled: "cancelled",
            };
            this.store.upsertActivity(s.id, {
              id: `${u.kind}:${nativeActivityId}`,
              runId: run.id,
              kind: u.kind,
              name: u.name ?? (u.kind === "subagent" ? "Subagent" : "Tool"),
              status: statuses[u.status ?? ""] ?? "unknown",
              summary: u.label,
              updatedAt: u.updatedAt ?? new Date().toISOString(),
              ...(u.detail !== undefined ? { detail: u.detail } : {}),
              ...(u.command !== undefined ? { command: u.command } : {}),
              ...(u.url !== undefined ? { url: u.url } : {}),
              ...(u.startedAt ? { startedAt: u.startedAt } : {}),
              ...(u.completedAt ? { finishedAt: u.completedAt } : {}),
              ...(u.toolCallId ? { toolCallId: u.toolCallId } : {}),
              ...(u.subagentId ? { childSessionId: u.subagentId } : {}),
              ...(u.parentSessionId
                ? { parentSessionId: u.parentSessionId }
                : {}),
              ...(u.backgroundTaskId
                ? { backgroundTaskId: u.backgroundTaskId }
                : {}),
            });
          }
          if (u.kind === "compaction")
            this.store.setStatus(s.id, "compacting", run.id);
        } else if (u.type === "compaction") {
          if (s.engineKind === "codex") this.store.checkpoints.observeCompaction(s.id,run.id,u.compactionId,u.status);
          const label =
            u.status === "start"
              ? "Compaction started"
              : u.status === "completed"
                ? "Compaction completed"
                : "Compaction failed";
          const counts = [
            u.tokensBefore === undefined
              ? undefined
              : `Tokens before: ${u.tokensBefore}`,
            u.tokensAfter === undefined
              ? undefined
              : `Tokens after: ${u.tokensAfter}`,
          ]
            .filter(Boolean)
            .join("; ");
          this.store.emit(
            s.id,
            "progress",
            {
              kind: "compaction",
              label,
              taskId: u.compactionId,
              ...(counts ? { detail: counts } : {}),
            },
            run.id,
          );
          this.store.markContextStale(s.id, run.id);
          if (!active.cancelled && !this.store.getSession(s.id).deleteRequested)
            this.store.setStatus(
              s.id,
              u.status === "start" ? "compacting" : "running",
              run.id,
            );
          if (u.status === "failed")
            this.store.emit(
              s.id,
              "error",
              {
                code: "compaction_failed",
                message: "Native engine reported compaction failure",
              },
              run.id,
            );
        } else if (u.type === "context") {
          const valid =
            u.used === null || (Number.isSafeInteger(u.used) && u.used >= 0);
          if (valid) {
            const context: Context = {
              used: u.used,
              limit: CONTEXT_LIMIT,
              estimated: u.estimated,
              stale: u.used === null,
              updatedAt: new Date().toISOString(),
              source: u.source,
            };
            this.store.setContext(s.id, context, run.id);
          }
        } else if (u.type === "image_status_result") {
          if (s.engineKind === "codex" && !active.cancelled && !this.closing)
            this.store.recordImageStatusConsumption(s.id, run.id, u);
        } else if (u.type === "artifact") {
          artifactJobs.push(
            this.register(s.id, u.path, run.id, u.name, u.mimeType),
          );
        }
      };
      if (this.closing)
        throw new Error("Server is shutting down before engine launch");
      if (s.engineKind === "codex") this.store.checkpoints.prepare(s.id,run.id,run.kind,s.nativeSessionId);
      const engine = await this.runner(s, update, run);
      const cancelBeforePrompt = async () => {
        try {
          await engine.cancel();
        } catch (error) {
          throw new CancellationSettlementError(active.cancelled, {
            cause: error,
          });
        }
      };
      if (active.cancelled) await cancelBeforePrompt();
      else if (run.kind === "compact") {
        try {
          await this.waitForDispatch(active);
          if (!engine.compact)
            throw new ApiError(
              409, "compaction_unavailable",
              "This engine does not support manual context compaction",
            );
          this.store.setStatus(s.id, "compacting", run.id);
          if ((await engine.compact()) === "cancelled") active.cancelled = true;
        } catch (error) {
          promptRejectedDuringCancellation = active.cancelled;
          throw error;
        }
      } else {
        const preparedAttachments = await this.files.attachments(s.id, run.attachmentIds);
        const technicalContext = run.kind === "message" ? await this.options.technicalVisionContext?.(s.id, run.id, run.attachmentIds) ?? "" : "";
        // Specialist pixels never enter native Codex's unsupported media path.
        const attachments = s.engineKind === "codex" && this.options.technicalVisionAvailable?.()
          ? preparedAttachments.filter(a => !["image/png", "image/jpeg"].includes(a.mimeType)) : preparedAttachments;
        const imageRefRow = this.store.db
          .prepare("SELECT data FROM h003_run_image_refs WHERE run_id=?")
          .get(run.id);
        const imageReferenceIds: string[] = imageRefRow ? JSON.parse(String(imageRefRow.data)) : [];
        if (s.engineKind === "codex" && imageReferenceIds.length) {
          if ((!this.options.enginePolicy?.codex?.imageToolEnabled && this.options.imageAcceptance?.(s.id) !== true) || !this.options.validateCodexImageReferences)
            throw new ApiError(400,"codex_image_tool_unavailable","Codex image specialist is not qualified");
          await this.options.validateCodexImageReferences(s.id, imageReferenceIds.length);
        }
        const imagePaths = await this.files.imageReferences(s.id, imageReferenceIds, s.engineKind === "codex");
        if (active.cancelled) await cancelBeforePrompt();
        else {
          const handoff = this.store.db
            .prepare(
              "SELECT summary FROM handoffs WHERE session_id=? AND delivered=0",
            )
            .get(s.id) as { summary: string } | undefined;
          const requestText =
            run.kind === "handoff"
              ? "Create a factual handoff summary for a new chat continuing this project in the same workspace. Summarize the user goal, completed work, current files and validation, unresolved issues and constraints, and precise next steps. Do not perform new work or change files; reply with the summary only."
              : run.text +
                (imagePaths.length
                  ? `\n\nUser-selected image references (workspace-relative paths):\n${imagePaths.map((p) => JSON.stringify(p)).join("\n")}\nUse these owned files for image tools when requested.`
                  : "");
          let promptOutcome: Awaited<ReturnType<Engine["prompt"]>>;
          try {
            await this.waitForDispatch(active);
            const currentImageContext = [this.options.imageContext?.(s.id, run.id) ?? "", technicalContext].filter(Boolean).join("\n\n");
            // Saved job state precedes the controlling request. Preserve the
            // original request/references and historical handoff verbatim.
            const priorContext = handoff
              ? `Context from the prior chat (same workspace):\n${handoff.summary}\n\n`
              : "";
            const routing=this.automaticRoute(s,run);
            promptOutcome = await engine.prompt(
              (s.engineKind === "codex" ? this.store.memory.bridge(s.id).continuationText() : "") + priorContext + (currentImageContext
                ? `${currentImageContext}\n\nCurrent user request (run ${run.id}):\n${requestText}`
                : `${handoff ? "Current user request:\n" : ""}${requestText}`),
              attachments,
              routing,
            );
          } catch (error) {
            promptRejectedDuringCancellation = active.cancelled;
            throw error;
          }
          if (promptOutcome === "cancelled") active.cancelled = true;
          if (handoff && !active.cancelled)
            this.store.db
              .prepare("UPDATE handoffs SET delivered=1 WHERE session_id=?")
              .run(s.id);
        }
      }
      await active.cancelPromise;
      if (active.cancelFailed)
        throw new CancellationSettlementError(active.cancelled);
      if(s.engineKind==="codex"&&this.options.beforeNativeReplacementCommit){
        const checkpoint=this.store.checkpoints.status(s.id).find(c=>c.runId===run.id);
        if(checkpoint?.compactions.some(c=>c.status==="completed")){
          try{await this.options.beforeNativeReplacementCommit(Object.freeze({sessionId:s.id,runId:run.id,checkpoint:Object.freeze(structuredClone(checkpoint))}));}
          catch{verificationRejected=true;this.store.checkpoints.rejectReplacementVerification(s.id,run.id,checkpoint.id);throw Object.assign(new Error("Native replacement verification rejected"),{code:"native_replacement_verification_failed"});}
        }
      }
      await Promise.all(artifactJobs);
      for (const assistantId of assistantIds)
        this.store.emit(
          s.id,
          "message",
          { message: this.store.message(assistantId) },
          run.id,
        );
      if (run.kind === "handoff" && !active.cancelled) {
        if (!summary.trim())
          throw new Error("Engine produced no handoff summary");
        // Only the factual summary and existing workspace cross this boundary.
        // createSession supplies fresh engine policy/profile/native state.
        const next = await this.createSession(s.workspaceId, run.handoffEngineKind ?? s.engineKind);
        this.store.setTitle(next.id, `Continue: ${s.title}`);
        this.store.touchContext(next.id);
        const m = this.store.addMessage(
          next.id,
          "assistant",
          `Handoff from previous chat:\n\n${summary}`,
        );
        this.store.emit(next.id, "message", { message: m });
        // The new engine receives this durable summary once on its first real prompt.
        this.store.db
          .prepare("INSERT INTO handoffs(session_id,summary) VALUES(?,?)")
          .run(next.id, summary);
        this.store.emit(s.id, "handoff", { newSessionId: next.id }, run.id);
      }
      for (const f of await this.files.discover(s.id))
        if (before.get(f.path) !== `${f.size}:${f.mtime}`)
          await this.register(s.id, f.path, run.id);
      // Cancellation can arrive during artifact discovery or handoff persistence.
      // Confirm its settlement again immediately before releasing this workspace.
      await active.cancelPromise;
      if (active.cancelFailed)
        throw new CancellationSettlementError(active.cancelled);
      // Initial Codex preview proves exact container cleanup per turn; the next
      // follow-up creates a new scoped runner and resumes the persisted thread.
      if (s.engineKind === "codex" && !(await this.closeRunner(s.id)))
        throw Object.assign(new Error("Codex cleanup unconfirmed"), { code: "engine_settlement_unknown" });
      this.store.settleRun(
        run.id,
        active.cancelled ? "cancelled" : "completed",
        active.cancelled ? undefined : finalCandidate,
      );
      if (s.engineKind === "codex") {
        this.store.memory.indexHistory(s.id);
        this.store.checkpoints.finish(s.id,run.id,active.cancelled ? "cancelled" : "completed");
      }
      success = true;
    } catch (error) {
      // Stop can reject the native prompt before its accepted inference drains.
      // Keep Codex cancelling and the active workspace locked until cleanup proves
      // durable settlement or fails. Other engines keep their existing behavior.
      const cancellationRace =
        promptRejectedDuringCancellation ||
        (error instanceof CancellationSettlementError &&
          error.requestedAtFailure);
      const observingCodexStop =
        this.store.getSession(run.sessionId, true).engineKind === "codex" && cancellationRace;
      if (!observingCodexStop)
        this.store.quarantine(run.workspaceId, "engine_settlement_unconfirmed");
      this.store.markContextStale(run.sessionId, run.id);
      const backgroundUnknown =
        !!error &&
        typeof error === "object" &&
        "code" in error &&
        error.code === "engine_settlement_unknown";
      failureStatus = backgroundUnknown ? "interrupted" : "failed";
      if (!observingCodexStop) this.store.updateRun(run.id, failureStatus);
      const emitFailure = () =>
        this.store.emit(
          run.sessionId,
          "error",
          {
            code: backgroundUnknown
              ? "engine_settlement_unknown"
              : run.kind === "compact"
                ? "compaction_failed"
                : "engine_failed",
            message: backgroundUnknown
              ? "Native completion could not be confirmed; process cleanup is being verified. The run was not accepted as completed."
              : run.kind === "compact"
                ? "Context compaction failed; visible history and files are retained and cleanup is being verified. Compaction was not replayed."
                : "Engine request failed; partial history is retained and cleanup is being verified. The prompt was not replayed.",
          },
          run.id,
        );
      if (!cancellationRace) emitFailure();
      let cleanupFailure: "native_cleanup_unconfirmed" | "gateway_settlement_unconfirmed" | undefined;
      try {
        cleanupConfirmed = await this.closeRunner(run.sessionId);
      } catch (cleanupError) {
        cleanupConfirmed = false;
        // Only these static proof reasons may reach the UI; never raw native errors.
        if (cleanupError && typeof cleanupError === "object" && "cleanupFailure" in cleanupError &&
            (cleanupError.cleanupFailure === "native_cleanup_unconfirmed" ||
             cleanupError.cleanupFailure === "gateway_settlement_unconfirmed"))
          cleanupFailure = cleanupError.cleanupFailure;
      }
      if (observingCodexStop && !cleanupConfirmed) {
        this.store.quarantine(run.workspaceId, "engine_settlement_unconfirmed");
        this.store.updateRun(run.id, failureStatus);
      }
      // Exact launcher/container cleanup completes requested Stop even if the
      // concurrent ACP cancel RPC rejects or times out. Unconfirmed cleanup
      // retains the error and quarantine; gateway draining is independent.
      if (cancellationRace && !cleanupConfirmed) emitFailure();
      if (cleanupConfirmed) {
        this.store.releaseQuarantineAfterVerifiedCleanup(run.workspaceId);
        if (active.cancelled && !verificationRejected) {
          this.store.updateRun(run.id, "cancelled");
          failureStatus = "idle";
        }
        this.store.emit(
          run.sessionId,
          "progress",
          {
            kind: "cleanup",
            label:
              "Owned engine container cleanup confirmed; interrupted work was not replayed",
          },
          run.id,
        );
      } else
        this.store.emit(
          run.sessionId,
          "error",
          {
            code: "engine_cleanup_unknown",
            ...(cleanupFailure ? { cleanupFailure } : {}),
            message:
              "Workspace remains quarantined until process cleanup is confirmed",
          },
          run.id,
        );
    } finally {
      if(verificationRejected){this.store.updateRun(run.id,"failed");failureStatus="failed";}
      if (!success && this.store.db.prepare("SELECT id FROM h041_session_checkpoints WHERE session_id=? AND run_id=?").get(run.sessionId,run.id))
        this.store.checkpoints.finish(run.sessionId,run.id,active.cancelled && !verificationRejected ? "cancelled" : "failed");
      if (!success)
        for (const assistantId of assistantIds)
          this.store.emit(
            run.sessionId,
            "message",
            { message: this.store.message(assistantId) },
            run.id,
          );
      const s = this.store.getSession(run.sessionId, true);
      const pending = (this.queues.get(run.workspaceId) ?? []).some(
        (r) => r.sessionId === s.id,
      );
      if (s.deleteRequested && (success || cleanupConfirmed)) {
        try {
          await this.closeRunner(s.id);
          this.store.finishDelete(s.id);
        } catch {
          this.store.quarantine(s.workspaceId, "close_unconfirmed");
          this.store.setStatus(s.id, "interrupted", run.id);
        }
      } else
        this.store.setStatus(
          s.id,
          success ? (pending ? "queued" : "idle") : failureStatus,
          run.id,
        );
      this.store.emit(s.id, "done", { runId: run.id }, run.id);
      try { this.options.onRunFinished?.(s.id, run.id); } catch { /* Scope manager remains responsible for fail-closed expiry. */ }
    }
  }
  private async register(
    id: string,
    file: string,
    runId: string,
    name?: string,
    mime?: string,
    messageId?: string,
  ) {
    try {
      const f = await this.files.registerArtifact(
        id,
        file,
        name,
        mime,
        runId,
        messageId,
      );
      this.store.emit(
        id,
        "artifact",
        { artifact: this.store.publicFile(f) },
        runId,
      );
      this.store.emitRun(runId);
    } catch {
      this.store.emit(
        id,
        "progress",
        {
          kind: "artifact",
          label: "An unsafe or oversized file was excluded from downloads",
        },
        runId,
      );
    }
  }
  private async closeRunner(id: string): Promise<boolean> {
    const active = [...this.active.values()].find(
      (a) => a.run.sessionId === id,
    );
    const runner = this.runners.get(id);
    if (!runner) return active?.cleanupPromise ?? false;
    runner.closePromise ??= runner.engine
      .close()
      .then(() => true)
      .finally(() => {
        this.options.revokeToken(runner.token);
        if (this.runners.get(id) === runner) this.runners.delete(id);
      });
    if (active) active.cleanupPromise = runner.closePromise;
    return runner.closePromise;
  }
  async cancel(id: string) {
    const s = this.store.getSession(id);
    const queue = this.queues.get(s.workspaceId) ?? [];
    this.queues.set(
      s.workspaceId,
      queue.filter((r) => {
        if (r.sessionId !== id) return true;
        this.store.updateRun(r.id, "cancelled");
        this.store.emit(id, "done", { runId: r.id }, r.id);
        return false;
      }),
    );
    const active = this.active.get(s.workspaceId);
    if (active?.run.sessionId === id) {
      active.cancelled = true;
      this.store.updateRun(active.run.id, "cancelling");
      if (!s.deleteRequested)
        this.store.setStatus(id, "cancelling", active.run.id);
      const runner = this.runners.get(id);
      if (runner && !active.cancelPromise)
        active.cancelPromise = runner.engine.cancel().catch(() => {
          active.cancelFailed = true;
        });
    } else if (!s.deleteRequested && !this.store.isQuarantined(s.workspaceId))
      this.store.setStatus(id, "idle");
    // Mark the creator cancelled before awaiting specialist observation/cancellation.
    if (!this.closing) { this.options.cancelImages?.(id); await this.options.cancelTechnicalVision?.(id); }
  }
  async delete(id: string): Promise<"deleting" | "deleted"> {
    const s = this.store.getSession(id);
    this.store.requestDelete(id);
    await this.cancel(id);
    if (
      this.active.get(s.workspaceId)?.run.sessionId === id ||
      this.store.isQuarantined(s.workspaceId)
    )
      return "deleting";
    try {
      await this.closeRunner(id);
      this.store.finishDelete(id);
      return "deleted";
    } catch {
      this.store.quarantine(s.workspaceId, "close_unconfirmed");
      return "deleting";
    }
  }
  async idle(): Promise<void> {
    for (;;) {
      await new Promise((r) => setTimeout(r, 5));
      const active = [...this.active.values()];
      if (!active.length && ![...this.queues.values()].some((q) => q.length))
        return;
      await Promise.all(active.map((a) => a.settled));
    }
  }
  private closePromise?: Promise<void>;
  close(): Promise<void> {
    this.closePromise ??= this.shutdown();
    return this.closePromise;
  }
  private async shutdown() {
    this.closing = true;
    const admissions=[...this.admissionPending.values()];for(const a of admissions)a.abort.abort(new Error("Admission cancelled by shutdown"));
    const recoveries=[...this.recoveries.values()];for(const r of recoveries)r.abort.abort(new Error("Recovery cancelled by shutdown"));
    const active = [...this.active.values()];
    const cancellations = active.map((a) => this.cancel(a.run.sessionId));
    // Deliver launcher shutdown now; waiting for an unresponsive prompt first
    // would prevent PREP's bounded exact-container cleanup from ever starting.
    const runnerClosures = [...this.runners.keys()].map(async (id) => {
        try {
          await this.closeRunner(id);
        } catch {
          this.store.quarantine(
            this.store.getSession(id, true).workspaceId,
            "shutdown_settlement_unknown",
          );
        }
      });
    // Begin Stop for every owner before waiting on any slow recovery/runner.
    await Promise.all([...recoveries.map(r=>r.settled),...admissions.map(a=>a.settled.catch(()=>undefined)), ...cancellations, ...runnerClosures, ...active.map(a=>a.settled)]);
  }
}
