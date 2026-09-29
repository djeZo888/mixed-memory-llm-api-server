import { createHash } from "node:crypto";
import { isRecord } from "./codex-connection.js";

export const CODEX_SCHEMA_ERROR_BOUND = 3;
const MAX_ACTIVE = 64;
const MAX_RECENT = 64;

export interface CodexSchemaErrorFailure {
  tool: string;
  server: string;
  callIds: string[];
  error: string;
  attempts: ReadonlyArray<Record<string, unknown>>;
}
interface Call {
  server: string;
  tool: string;
  argumentsHash: string;
  eligible: boolean;
}

function canonical(value: unknown, ancestors = new Set<object>()): string | undefined {
  if (value === null || typeof value === "boolean" || typeof value === "string")
    return JSON.stringify(value);
  if (typeof value === "number") return Number.isFinite(value) ? JSON.stringify(value) : undefined;
  if (typeof value !== "object" || ancestors.has(value) ||
      (!Array.isArray(value) && Object.getPrototypeOf(value) !== Object.prototype && Object.getPrototypeOf(value) !== null) ||
      Object.getOwnPropertySymbols(value).length) return undefined;
  ancestors.add(value);
  const entries: string[] = [];
  for (const key of Array.isArray(value) ? Array.from({ length: value.length }, (_, i) => String(i)) : Object.keys(value).sort()) {
    const encoded = canonical((value as Record<string, unknown>)[key], ancestors);
    if (encoded === undefined) return undefined;
    entries.push(Array.isArray(value) ? encoded : `${JSON.stringify(key)}:${encoded}`);
  }
  ancestors.delete(value);
  return Array.isArray(value) ? `[${entries.join(",")}]` : `{${entries.join(",")}}`;
}

function call(item: Record<string, unknown>): Call | undefined {
  if (typeof item.server !== "string" || !item.server || item.server.length > 512 ||
      typeof item.tool !== "string" || !item.tool || item.tool.length > 512) return undefined;
  let encoded: string | undefined;
  try { encoded = canonical(item.arguments); }
  catch { return undefined; }
  if (encoded === undefined) return undefined;
  return { server: item.server, tool: item.tool,
    argumentsHash: createHash("sha256").update(encoded).digest("hex"), eligible: true };
}

function same(left: Call, right: Call): boolean {
  return left.server === right.server && left.tool === right.tool &&
    left.argumentsHash === right.argumentsHash;
}

/** One instance per owned native turn. The caller validates thread/turn ownership,
 * lifecycle and unique event delivery before observing. Retained history and child
 * turns must never be replayed into this instance. Arguments are only fingerprinted;
 * neither model arguments nor the original stored tool/error trace are modified.
 */
export class CodexSchemaErrorGuard {
  private active = new Map<string, Call>();
  private recent = new Set<string>();
  private streak?: { call: Call; failure: CodexSchemaErrorFailure };
  private disabled = false;

  private reset() {
    this.streak = undefined;
    for (const pending of this.active.values()) pending.eligible = false;
  }

  observe(item: Record<string, unknown>, complete: boolean): CodexSchemaErrorFailure | undefined {
    if (this.disabled) return undefined;
    if (item.type === "agentMessage" || item.type === "reasoning") return undefined;
    if (item.type !== "mcpToolCall" || typeof item.id !== "string" ||
        !item.id || item.id.length > 512) {
      this.reset();
      return undefined;
    }
    // Defense against replayed recent completions, in addition to caller dedup.
    if (this.recent.has(item.id)) return undefined;
    const current = call(item);
    if (!complete) {
      const prior = this.active.get(item.id);
      if (prior) {
        if (!current || !same(prior, current)) this.reset();
        return undefined;
      }
      if (!current || item.status !== "inProgress") {
        this.reset();
        return undefined;
      }
      if (this.active.size) {
        this.reset();
        current.eligible = false;
      }
      if (this.active.size >= MAX_ACTIVE) {
        this.reset();
        this.active.clear();
        this.disabled = true;
        return undefined;
      }
      this.active.set(item.id, current);
      if (this.streak && !same(this.streak.call, current)) this.streak = undefined;
      return undefined;
    }
    const started = this.active.get(item.id);
    this.active.delete(item.id);
    this.recent.add(item.id);
    if (this.recent.size > MAX_RECENT) this.recent.delete(this.recent.values().next().value!);
    const result = item.result;
    if (!started?.eligible || !current || !same(started, current) || this.active.size ||
        item.status !== "failed" || item.error !== null || !isRecord(result) ||
        !Array.isArray(result.content) || result.content.length !== 1 ||
        !isRecord(result.content[0]) || result.content[0].type !== "text" ||
        typeof result.content[0].text !== "string") {
      this.reset();
      return undefined;
    }
    const error = result.content[0].text;
    const prefix = `MCP error -32602: Input validation error: Invalid arguments for tool ${current.tool}: `;
    if (!error.startsWith(prefix) || !error.slice(prefix.length).trim()) {
      this.reset();
      return undefined;
    }
    const previous = this.streak;
    const matches = previous && same(previous.call, current) && previous.failure.error === error;
    const callIds = matches ? [...previous.failure.callIds, item.id] : [item.id];
    const attempts = matches ? [...previous.failure.attempts, item] : [item];
    const failure = { server: current.server, tool: current.tool, callIds, error, attempts };
    // Never truncate or size-gate a deterministic error. Existing native frame
    // limits bound each item; at most three completed items are retained here.
    const saved = structuredClone(failure);
    this.streak = { call: current, failure: saved };
    if (callIds.length < CODEX_SCHEMA_ERROR_BOUND) return undefined;
    this.disabled = true;
    return saved;
  }
}
