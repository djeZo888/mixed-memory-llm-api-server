import type { Readable, Writable } from "node:stream";

export type CodexMethod = "initialize" | "thread/start" | "thread/resume" | "turn/start" | "turn/interrupt";
const METHODS = new Set<string>(["initialize", "thread/start", "thread/resume", "turn/start", "turn/interrupt"]);
export const isRecord = (v: unknown): v is Record<string, unknown> =>
  !!v && typeof v === "object" && !Array.isArray(v);
export class CodexProtocolError extends Error {
  readonly code = "engine_settlement_unknown";
}
interface Pending {
  resolve: (result: unknown) => void;
  reject: (error: Error) => void;
  timer: ReturnType<typeof setTimeout>;
}

/** Private stdio only. This is deliberately not an RPC proxy or reconnect client. */
export class CodexConnection {
  private nextId = 1;
  private buffer = "";
  private pending = new Map<number, Pending>();
  private responses = new Map<number, string>();
  private failure?: Error;
  constructor(
    private readonly input: Readable,
    private readonly output: Writable,
    private readonly notification: (method: string, params: Record<string, unknown>) => void,
    private readonly failed: (error: Error) => void,
    private readonly timeoutMs = 15000,
  ) {
    input.setEncoding("utf8");
    input.on("data", (chunk: string) => this.receive(chunk));
    input.on("end", () => this.fail(new CodexProtocolError(this.buffer ? "Truncated App Server JSONL" : "App Server stream ended")));
    input.on("error", () => this.fail(new CodexProtocolError("App Server read failed")));
    output.on("error", () => this.fail(new CodexProtocolError("App Server write failed")));
  }
  request(method: CodexMethod, params: Record<string, unknown>): Promise<unknown> {
    if (!METHODS.has(method)) return Promise.reject(new CodexProtocolError("Unsupported App Server operation"));
    if (this.failure) return Promise.reject(this.failure);
    const id = this.nextId++;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => this.fail(new CodexProtocolError(`App Server ${method} response timed out; request will not be replayed`)), this.timeoutMs);
      this.pending.set(id, { resolve, reject, timer });
      this.write({ id, method, params });
    });
  }
  initialized() { this.write({ method: "initialized", params: {} }); }
  fail(error: Error) {
    if (this.failure) return;
    this.failure = error;
    for (const p of this.pending.values()) { clearTimeout(p.timer); p.reject(error); }
    this.pending.clear();
    this.failed(error);
  }
  private write(message: unknown) {
    if (this.failure) return;
    try { this.output.write(JSON.stringify(message) + "\n"); }
    catch { this.fail(new CodexProtocolError("App Server write failed")); }
  }
  private receive(chunk: string) {
    if (this.failure) return;
    this.buffer += chunk;
    if (Buffer.byteLength(this.buffer) > 4 * 1024 * 1024) {
      this.fail(new CodexProtocolError("App Server frame exceeds limit")); return;
    }
    let end: number;
    while (!this.failure && (end = this.buffer.indexOf("\n")) >= 0) {
      const line = this.buffer.slice(0, end); this.buffer = this.buffer.slice(end + 1);
      try { this.message(JSON.parse(line)); }
      catch { this.fail(new CodexProtocolError("Invalid or out-of-order App Server message")); }
    }
  }
  private message(value: unknown) {
    if (!isRecord(value)) throw new Error("Invalid frame");
    if (typeof value.method === "string") {
      if ("id" in value) {
        if (typeof value.id !== "number" && typeof value.id !== "string") throw new Error("Invalid request ID");
        // Requests for approvals, user input, elicitation, auth or dynamic tools are
        // never auto-approved and never forwarded to a browser or host executor.
        this.write({ id: value.id, error: { code: -32601, message: "Operation unavailable under Sova preview policy" } });
        this.notification("sova/unsupportedRequest", { method: value.method });
        throw new Error("Unsupported server request");
      }
      if (!isRecord(value.params)) throw new Error("Invalid notification");
      this.notification(value.method, value.params);
      return;
    }
    if (!Number.isSafeInteger(value.id) || !("result" in value || "error" in value) || ("result" in value && "error" in value))
      throw new Error("Invalid response");
    const id = value.id as number;
    const encoded = JSON.stringify(value);
    const previous = this.responses.get(id);
    if (previous !== undefined) { if (previous !== encoded) throw new Error("Conflicting duplicate response"); return; }
    const pending = this.pending.get(id);
    if (!pending) throw new Error("Unexpected response ID");
    clearTimeout(pending.timer); this.pending.delete(id); this.responses.set(id, encoded);
    if (this.responses.size > 256) this.responses.delete(this.responses.keys().next().value!);
    if ("error" in value) {
      pending.reject(new CodexProtocolError("App Server rejected the requested operation"));
      // A turn-start error may follow dispatch; make the entire connection unusable.
      this.fail(new CodexProtocolError("App Server request rejected; no automatic retry"));
    } else pending.resolve(value.result);
  }
}
