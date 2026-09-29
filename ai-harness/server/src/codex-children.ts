import type { EngineUpdate, SubagentSummary } from "./contracts.js";
import { CodexProtocolError, isRecord } from "./codex-connection.js";
import { CodexSchemaErrorGuard, type CodexSchemaErrorFailure } from "./codex-schema-errors.js";
const statuses = new Set([
  "pendingInit",
  "running",
  "interrupted",
  "completed",
  "errored",
  "shutdown",
  "notFound",
]);
const tools = new Set([
  "spawnAgent",
  "sendInput",
  "resumeAgent",
  "wait",
  "closeAgent",
  "sendMessage",
  "followupTask",
  "interruptAgent",
  "listAgents",
]);
const terminal = new Set(["completed", "errored", "interrupted", "shutdown"]);
const id = (v: unknown): v is string =>
  typeof v === "string" && !!v && v.length <= 512 && !/[\x00-\x20\x7f]/.test(v);
/** Pinned collabAgentToolCall states, never inferred from a tool's own completion. */
export class CodexChildren {
  private children = new Map<string, string>();
  private models = new Map<string, string>();
  private turns = new Map<
    string,
    {
      id: string;
      terminal: boolean;
      terminalStatus?: string;
      schemaErrors: CodexSchemaErrorGuard;
      items: Map<
        string,
        { type: string; completed: boolean; snapshot?: string }
      >;
    }
  >();
  constructor(
    private parent: () => string | undefined,
    private emit: (u: EngineUpdate) => void,
    private max = 4,
    private qualifiedModels: readonly string[] = ["qwen3.8-27b"],
    private onSchemaError?: (failure: CodexSchemaErrorFailure, threadId: string, turnId: string) => void,
  ) {
    if (!Number.isSafeInteger(max) || max < 1 || max > 4)
      throw new CodexProtocolError("Invalid child bound");
    if (!qualifiedModels.includes("qwen3.8-27b") || new Set(qualifiedModels).size !== qualifiedModels.length ||
        qualifiedModels.some(model => !["qwen3.8-27b", "mimo-v2.6-pro-rl"].includes(model)))
      throw new CodexProtocolError("Invalid qualified child model policy");
    this.qualifiedModels = Object.freeze([...qualifiedModels]);
  }
  owns(thread: unknown): thread is string {
    return typeof thread === "string" && this.children.has(thread);
  }
  private state(thread: string, status: string, detail?: string) {
    if (!id(thread) || thread === this.parent() || !statuses.has(status))
      throw new CodexProtocolError("Invalid child identity or status");
    if (!this.children.has(thread) && this.children.size >= this.max)
      throw new CodexProtocolError("Native child bound exceeded");
    const turn = this.turns.get(thread);
    if (
      status === "completed" &&
      turn &&
      [...turn.items.values()].some((item) => !item.completed)
    )
      throw new CodexProtocolError("Native child has incomplete items");
    this.children.set(thread, status);
    const mapped =
      status === "completed" && turn && !turn.terminal
        ? "in_progress"
        : status === "completed"
          ? "completed"
          : status === "errored"
            ? "failed"
            : ["interrupted", "shutdown"].includes(status)
              ? "cancelled"
              : status === "notFound"
                ? "unknown"
                : "in_progress";
    this.emit({
      type: "progress",
      kind: "subagent",
      label: `Native child ${mapped}`,
      name: this.models.get(thread) === "mimo-v2.6-pro-rl" ? "MiMo child" : "Qwen child",
      subagentId: thread,
      parentSessionId: this.parent(),
      status: mapped,
      detail,
      subagents: this.summary(),
    });
  }
  thread(value: unknown) {
    if (
      !isRecord(value) ||
      value.parentThreadId !== this.parent() ||
      value.modelProvider !== "sova" ||
      !this.qualifiedModels.includes(String(value.model)) ||
      !id(value.id)
    )
      throw new CodexProtocolError("Unowned or unqualified child thread");
    this.bindModel(value.id, String(value.model));
    this.state(value.id, "pendingInit");
  }
  private bindModel(thread: string, model: string) {
    if (!this.qualifiedModels.includes(model) || (this.models.has(thread) && this.models.get(thread) !== model))
      throw new CodexProtocolError("Changed or unqualified child model");
    this.models.set(thread, model);
  }
  item(value: Record<string, unknown>, complete: boolean) {
    if (
      value.senderThreadId !== this.parent() ||
      !tools.has(String(value.tool)) ||
      !Array.isArray(value.receiverThreadIds) ||
      !isRecord(value.agentsStates) ||
      !["inProgress", "completed", "failed", "interrupted"].includes(
        String(value.status),
      ) ||
      (complete && value.status === "inProgress") ||
      (value.model != null &&
        value.model !== "" &&
        !this.qualifiedModels.includes(String(value.model)))
    )
      throw new CodexProtocolError("Unqualified native collaboration event");
    if (
      complete &&
      value.tool === "spawnAgent" &&
      value.status === "completed" &&
      !this.qualifiedModels.includes(String(value.model))
    )
      throw new CodexProtocolError("Spawned child model is unqualified");
    for (const thread of value.receiverThreadIds) {
      if (!id(thread)) throw new CodexProtocolError("Invalid child identity");
      if (value.tool === "spawnAgent" && typeof value.model === "string" && value.model)
        this.bindModel(thread, value.model);
      if (!this.owns(thread)) {
        if (value.tool !== "spawnAgent")
          throw new CodexProtocolError("Unknown native child");
        this.state(thread, "pendingInit");
      }
    }
    for (const [thread, state] of Object.entries(value.agentsStates)) {
      if (
        !this.owns(thread) ||
        !isRecord(state) ||
        !statuses.has(String(state.status))
      )
        throw new CodexProtocolError("Unowned child state");
      this.state(thread, String(state.status));
    }
  }
  activity(value: Record<string, unknown>) {
    if (
      !this.owns(value.agentThreadId) ||
      typeof value.agentPath !== "string" ||
      !["started", "interacted", "interrupted", "completed"].includes(
        String(value.kind),
      )
    )
      throw new CodexProtocolError("Unowned native child activity");
    // Activity alone does not identify turn/error outcome. Only interruption is terminal here.
    if (value.kind === "interrupted")
      this.state(value.agentThreadId, "interrupted");
    else if (value.kind === "started")
      this.state(value.agentThreadId, "running");
  }
  notification(method: string, p: Record<string, unknown>) {
    if (!this.owns(p.threadId))
      throw new CodexProtocolError("Unowned child notification");
    if (method === "turn/started") {
      if (!isRecord(p.turn) || !id(p.turn.id))
        throw new CodexProtocolError("Invalid child turn identity");
      const previous = this.turns.get(p.threadId);
      if (previous && !previous.terminal && previous.id !== p.turn.id)
        throw new CodexProtocolError("Overlapping child turn");
      if (previous?.id === p.turn.id) {
        if (previous.terminal)
          throw new CodexProtocolError("Replayed child turn");
        return;
      }
      this.turns.set(p.threadId, {
        id: p.turn.id,
        terminal: false,
        schemaErrors: new CodexSchemaErrorGuard(),
        items: new Map(),
      });
      this.state(p.threadId, "running");
    }
    if (method === "turn/completed") {
      const turn = this.turns.get(p.threadId);
      if (
        !isRecord(p.turn) ||
        !turn ||
        p.turn.id !== turn.id ||
        !["completed", "failed", "interrupted"].includes(String(p.turn.status))
      )
        throw new CodexProtocolError("Invalid child terminal");
      if (turn.terminal) {
        if (turn.terminalStatus !== p.turn.status)
          throw new CodexProtocolError("Conflicting child terminal");
        return;
      }
      turn.terminal = true;
      turn.terminalStatus = String(p.turn.status);
      this.state(
        p.threadId,
        p.turn.status === "failed" ? "errored" : String(p.turn.status),
      );
    }
    if (method === "item/started" || method === "item/completed") {
      const turn = this.turns.get(p.threadId),
        item = p.item;
      if (
        !turn ||
        turn.terminal ||
        p.turnId !== turn.id ||
        !isRecord(item) ||
        !id(item.id) ||
        typeof item.type !== "string"
      )
        throw new CodexProtocolError("Out-of-order child item");
      if (
        item.type === "collabAgentToolCall" ||
        item.type === "subAgentActivity"
      )
        throw new CodexProtocolError(
          "Nested delegation unavailable under depth-one policy",
        );
      const previous = turn.items.get(item.id),
        complete = method === "item/completed";
      if (
        ![
          "userMessage",
          "agentMessage",
          "reasoning",
          "commandExecution",
          "fileChange",
          "mcpToolCall",
          "contextCompaction",
        ].includes(item.type)
      )
        throw new CodexProtocolError("Unsupported child item");
      if (
        complete &&
        ["commandExecution", "fileChange", "mcpToolCall"].includes(item.type) &&
        !["completed", "failed", "declined"].includes(String(item.status))
      )
        throw new CodexProtocolError("Child tool completion is not terminal");
      if (complete && previous?.completed) {
        if (previous.snapshot !== JSON.stringify(item))
          throw new CodexProtocolError("Conflicting child item completion");
        return;
      }
      if (
        (complete && !previous) ||
        (previous && previous.type !== item.type) ||
        (!complete && previous?.completed)
      )
        throw new CodexProtocolError("Invalid child item lifecycle");
      if (!previous && turn.items.size >= 10000)
        throw new CodexProtocolError("Child item bound exceeded");
      turn.items.set(item.id, {
        type: item.type,
        completed: complete,
        snapshot: complete ? JSON.stringify(item) : undefined,
      });
      // Only validated events in this owned child turn reach its own guard.
      // Completed duplicates returned above cannot count as another attempt.
      const schemaFailure = turn.schemaErrors.observe(item, complete);
      if (schemaFailure) this.onSchemaError?.(schemaFailure, p.threadId, turn.id);
    }
    // Child prose stays private; the schema callback contains only matched MCP calls.
  }
  private isActive(thread: string, status: string) {
    return !terminal.has(status) || this.turns.get(thread)?.terminal === false;
  }
  get unfinished() {
    return [...this.children].some(([thread, status]) =>
      this.isActive(thread, status),
    );
  }
  interruptedAfterCleanup() {
    for (const [thread, status] of this.children)
      if (this.isActive(thread, status)) {
        const turn = this.turns.get(thread);
        if (turn) {
          turn.terminal = true;
          turn.terminalStatus = "interrupted";
        }
        this.state(
          thread,
          "interrupted",
          "Interrupted by confirmed native process cleanup; gateway settlement checked separately.",
        );
      }
  }
  summary(): SubagentSummary {
    const values = [...this.children];
    return {
      known: true,
      active: values.filter(([thread, s]) => this.isActive(thread, s)).length,
      completed: values.filter(
        ([thread, s]) => s === "completed" && !this.isActive(thread, s),
      ).length,
      failed: values.filter(
        ([thread, s]) => s === "errored" && !this.isActive(thread, s),
      ).length,
      cancelled: values.filter(
        ([thread, s]) =>
          ["interrupted", "shutdown"].includes(s) && !this.isActive(thread, s),
      ).length,
    };
  }
}
