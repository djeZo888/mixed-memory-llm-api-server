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
  private parentTurnId?: string;
  private currentTurns = new Map<string, string>();
  private currentTargets = new Map<string,{callId:string;snapshot:string}>();
  private seenTurns = new Map<string,Set<string>>();
  beginParentTurn() { this.parentTurnId=undefined; this.currentTurns.clear(); this.currentTargets.clear(); }
  bindParentTurn(turnId:string) {
    if (!id(turnId) || (this.parentTurnId && this.parentTurnId!==turnId)) throw new CodexProtocolError("Changed controlling parent turn");
    this.parentTurnId=turnId;
  }
  /** Called only after the controlling parent's item lifecycle is validated. */
  bindParentCollaboration(turnId:string,value:Record<string,unknown>,complete:boolean) {
    if (!this.parentTurnId || turnId!==this.parentTurnId) throw new CodexProtocolError("Foreign parent collaboration");
    if (complete && value.status==="completed" && ["spawnAgent","sendInput","resumeAgent","sendMessage","followupTask"].includes(String(value.tool)))
      for (const target of value.receiverThreadIds as string[]) this.currentTargets.set(target,{callId:String(value.id),snapshot:JSON.stringify(value)});
  }
  currentTerminalEvidence(model:string,verified:ReadonlySet<string>) {
    if(!this.parentTurnId)return [];
    return [...this.currentTurns].filter(([thread,turnId]) => {
      const turn=this.turns.get(thread);
      return verified.has(thread) && this.currentTargets.has(thread) && this.models.get(thread)===model && turn?.id===turnId && turn.terminalStatus==="completed" && [...turn.items.values()].every(item=>item.completed);
    }).map(([childThreadId,childTurnId])=>Object.freeze({parentTurnId:this.parentTurnId!,childThreadId,childTurnId,dispatchCallId:this.currentTargets.get(childThreadId)!.callId,dispatchSnapshot:this.currentTargets.get(childThreadId)!.snapshot,terminalSnapshot:this.turns.get(childThreadId)!.terminalSnapshot!}));
  }
  completedCurrentModel(model:string,verified:ReadonlySet<string>):boolean {return this.currentTerminalEvidence(model,verified).length>0;}
  private children = new Map<string, string>();
  private models = new Map<string, string>();
  // Call bookkeeping only: an unowned close target never becomes a child.
  private unownedCloses = new Map<string, { sender: string; receiver: string }>();
  private turns = new Map<
    string,
    {
      id: string;
      terminal: boolean;
      terminalStatus?: string;
      terminalSnapshot?: string;
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
    const pendingClose = typeof value.id === "string" ? this.unownedCloses.get(value.id) : undefined;
    if (pendingClose || (value.tool === "closeAgent" && value.receiverThreadIds.some(thread => !this.owns(thread)))) {
      const receiver = value.receiverThreadIds[0];
      // Pinned native close items have no prompt/model/error payload. The item
      // ID is the call ID; only its exact failed/notFound completion is benign.
      if (value.type !== "collabAgentToolCall" || !id(value.id) ||
          value.tool !== "closeAgent" || value.receiverThreadIds.length !== 1 ||
          !id(receiver) || receiver === this.parent() || this.owns(receiver) ||
          value.prompt !== null || value.model !== null || value.reasoningEffort !== null ||
          Object.keys(value).some(key => ![
            "type", "id", "tool", "status", "senderThreadId", "receiverThreadIds",
            "prompt", "model", "reasoningEffort", "agentsStates",
          ].includes(key)) ||
          (pendingClose && (pendingClose.receiver !== receiver || pendingClose.sender !== value.senderThreadId)))
        throw new CodexProtocolError("Invalid unowned native close binding");
      const states = Object.entries(value.agentsStates);
      if (!complete) {
        if (value.status !== "inProgress" || states.length !== 0)
          throw new CodexProtocolError("Invalid unowned native close start");
        if (!pendingClose && this.unownedCloses.size >= this.max)
          throw new CodexProtocolError("Unowned native close bound exceeded");
        this.unownedCloses.set(value.id, { sender: String(value.senderThreadId), receiver });
      } else {
        const state = states[0]?.[1];
        if (!pendingClose || value.status !== "failed" || states.length !== 1 ||
            states[0][0] !== receiver || !isRecord(state) ||
            state.status !== "notFound" || state.message !== null ||
            Object.keys(state).some(key => key !== "status" && key !== "message"))
          throw new CodexProtocolError("Unconfirmed unowned native close outcome");
        this.unownedCloses.delete(value.id);
      }
      return;
    }
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
      const seen=this.seenTurns.get(p.threadId)??new Set<string>();
      if(seen.has(p.turn.id)||seen.size>=10000)throw new CodexProtocolError("Replayed or excessive child turns");
      seen.add(p.turn.id);this.seenTurns.set(p.threadId,seen);
      if (this.parentTurnId) this.currentTurns.set(p.threadId,p.turn.id);
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
        if (turn.terminalStatus !== p.turn.status || turn.terminalSnapshot!==JSON.stringify(p.turn))
          throw new CodexProtocolError("Conflicting child terminal");
        return;
      }
      if(p.turn.status==="completed" && p.turn.error!=null)throw new CodexProtocolError("Successful child terminal contains error");
      turn.terminalSnapshot=JSON.stringify(p.turn);
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
    return this.unownedCloses.size > 0 || [...this.children].some(([thread, status]) =>
      this.isActive(thread, status),
    );
  }
  interruptedAfterCleanup() {
    this.unownedCloses.clear();
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
  /** Actual owned terminal turn and validated model, never collaboration ACK alone. */
  completedModel(model: string, verified?: ReadonlySet<string>): boolean {
    return [...this.children].some(([thread,status]) => status === "completed" && (!verified || verified.has(thread)) && this.models.get(thread) === model && this.turns.get(thread)?.terminalStatus === "completed" && [...this.turns.get(thread)!.items.values()].every(item=>item.completed));
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
