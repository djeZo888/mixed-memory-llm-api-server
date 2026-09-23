import { createHash } from "node:crypto";
import type { Store, Run, StoredSession } from "./store.js";
import { Files } from "./files.js";
import type {
  Engine,
  EngineFactory,
  EngineUpdate,
  Context,
  Status,
  MessagePhase,
  Activity,
} from "./contracts.js";
import { CONTEXT_LIMIT } from "./contracts.js";
import { ApiError } from "./errors.js";
export interface BrokerOptions {
  store: Store;
  files: Files;
  engineFactory: EngineFactory;
  launcher: string;
  gatewayUrl: string;
  issueToken: (sessionId: string) => string;
  revokeToken: (token: string) => void;
  maxQueued?: number;
  cancelImages?: (sessionId: string) => void;
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
  constructor(readonly options: BrokerOptions) {
    this.store = options.store;
    this.files = options.files;
  }
  currentImageRun(sessionId: string) {
    const active = [...this.active.values()].find(
      (a) => a.run.sessionId === sessionId && !a.cancelled,
    );
    return active
      ? { runId: active.run.id, workspaceId: active.run.workspaceId }
      : undefined;
  }
  async createSession(workspaceId?: string) {
    const s = this.store.createSession(workspaceId);
    await this.files.prepare(s.id, s.workspaceId);
    return this.store.publicSession(s);
  }
  enqueue(
    sessionId: string,
    kind: Run["kind"],
    text: string,
    attachmentIds: string[] = [],
    imageReferences: string[] = [],
  ): string {
    const s = this.store.getSession(sessionId);
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
        f.kind !== "artifact" ||
        f.sessionId !== sessionId ||
        !["image/png", "image/jpeg"].includes(f.mimeType)
      )
        throw new ApiError(
          400,
          "invalid_image_reference",
          "Image artifact does not belong to this chat",
        );
    }
    const run = this.store.createRun(s, kind, text, attachmentIds);
    if (imageReferences.length)
      this.store.db
        .prepare("INSERT INTO h003_run_image_refs VALUES(?,?)")
        .run(run.id, JSON.stringify(imageReferences));
    this.store.touchContext(s.id, run.id);
    if (kind === "message") {
      const message = this.store.addMessage(
        s.id,
        "user",
        text,
        run.id,
        attachmentIds,
      );
      this.store.emit(s.id, "message", { message }, run.id);
      if (s.title === "New chat")
        this.store.setTitle(s.id, text.trim() || "Attachment");
    }
    const queue = this.queues.get(s.workspaceId) ?? [];
    queue.push(run);
    this.queues.set(s.workspaceId, queue);
    if (![...this.active.values()].some((a) => a.run.sessionId === s.id))
      this.store.setStatus(s.id, "queued", run.id);
    this.store.emit(
      s.id,
      "progress",
      { kind: "queue", label: "Waiting for workspace" },
      run.id,
    );
    queueMicrotask(() => this.pump(s.workspaceId));
    return run.id;
  }
  private pump(workspaceId: string) {
    if (this.closing || this.active.has(workspaceId)) return;
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
  private async runner(
    s: StoredSession,
    onUpdate: (update: EngineUpdate) => void,
  ) {
    // Update callbacks are per turn; an existing runner reads a mutable dispatcher.
    let runner = this.runners.get(s.id) as
      | (Runner & { update: (u: EngineUpdate) => void })
      | undefined;
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
    entry.engine = this.options.engineFactory({
      sessionId: s.id,
      profileDir: this.files.profile(s.id),
      workspace: this.files.workspace(s.workspaceId),
      nativeSessionId: s.nativeSessionId,
      launcher: this.options.launcher,
      gatewayUrl: this.options.gatewayUrl,
      gatewayToken: token,
      stderrPath: this.files.log(s.id),
      onExit: () => this.options.revokeToken(token),
      onNativeSessionId: (id) => this.store.setNative(s.id, id),
      onUpdate: (u) => entry.update(u),
    });
    this.runners.set(s.id, entry);
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
    let success = false;
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
        if (u.type === "text") {
          if (!u.text) return;
          const thought = u.channel === "thought";
          if (!thought) summary += u.text;
          const id = messageId(u.nativeMessageId, thought);
          const phase = phases.get(id) ?? {
            phase: (thought
              ? "thinking"
              : "unclassified") as MessagePhase["phase"],
            ...(u.nativeMessageId
              ? { nativeMessageId: u.nativeMessageId }
              : {}),
            streamState: "streaming" as const,
          };
          this.store.appendDelta(s.id, id, u.text, run.id, phase);
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
        } else if (u.type === "artifact") {
          artifactJobs.push(
            this.register(s.id, u.path, run.id, u.name, u.mimeType),
          );
        }
      };
      if (this.closing)
        throw new Error("Server is shutting down before engine launch");
      const engine = await this.runner(s, update);
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
      else {
        const attachments = await this.files.attachments(
          s.id,
          run.attachmentIds,
        );
        const imageRefRow = this.store.db
          .prepare("SELECT data FROM h003_run_image_refs WHERE run_id=?")
          .get(run.id);
        const imagePaths = await this.files.imageReferences(
          s.id,
          imageRefRow ? JSON.parse(String(imageRefRow.data)) : [],
        );
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
            promptOutcome = await engine.prompt(
              handoff
                ? `Context from the prior chat (same workspace):\n${handoff.summary}\n\nCurrent user request:\n${requestText}`
                : requestText,
              attachments,
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
        const next = await this.createSession(s.workspaceId);
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
      this.store.settleRun(
        run.id,
        active.cancelled ? "cancelled" : "completed",
        active.cancelled ? undefined : finalCandidate,
      );
      success = true;
    } catch (error) {
      this.store.quarantine(run.workspaceId, "engine_settlement_unconfirmed");
      this.store.markContextStale(run.sessionId, run.id);
      const backgroundUnknown =
        !!error &&
        typeof error === "object" &&
        "code" in error &&
        error.code === "engine_settlement_unknown";
      failureStatus = backgroundUnknown ? "interrupted" : "failed";
      this.store.updateRun(run.id, failureStatus);
      const emitFailure = () =>
        this.store.emit(
          run.sessionId,
          "error",
          {
            code: backgroundUnknown
              ? "engine_settlement_unknown"
              : "engine_failed",
            message: backgroundUnknown
              ? "Native completion could not be confirmed; process cleanup is being verified. The run was not accepted as completed."
              : "Engine request failed; partial history is retained and cleanup is being verified. The prompt was not replayed.",
          },
          run.id,
        );
      // Capture Stop intent at a prompt failure or a known cancel-settlement
      // failure, before cleanup can admit a later Stop for an unrelated error.
      const cancellationRace =
        promptRejectedDuringCancellation ||
        (error instanceof CancellationSettlementError &&
          error.requestedAtFailure);
      if (!cancellationRace) emitFailure();
      try {
        cleanupConfirmed = await this.closeRunner(run.sessionId);
      } catch {
        cleanupConfirmed = false;
      }
      // Exact launcher/container cleanup completes requested Stop even if the
      // concurrent ACP cancel RPC rejects or times out. Unconfirmed cleanup
      // retains the error and quarantine; gateway draining is independent.
      if (cancellationRace && !cleanupConfirmed) emitFailure();
      if (cleanupConfirmed) {
        this.store.releaseQuarantineAfterVerifiedCleanup(run.workspaceId);
        if (active.cancelled) {
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
            message:
              "Workspace remains quarantined until process cleanup is confirmed",
          },
          run.id,
        );
    } finally {
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
    if (!this.closing) this.options.cancelImages?.(id);
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
    const active = [...this.active.values()];
    await Promise.all(active.map((a) => this.cancel(a.run.sessionId)));
    // Deliver launcher shutdown now; waiting for an unresponsive prompt first
    // would prevent PREP's bounded exact-container cleanup from ever starting.
    await Promise.all(
      [...this.runners.keys()].map(async (id) => {
        try {
          await this.closeRunner(id);
        } catch {
          this.store.quarantine(
            this.store.getSession(id, true).workspaceId,
            "shutdown_settlement_unknown",
          );
        }
      }),
    );
    await Promise.all(active.map((a) => a.settled));
  }
}
