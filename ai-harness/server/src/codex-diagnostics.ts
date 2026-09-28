import {
  closeSync, constants, fchmodSync, fstatSync, ftruncateSync, lstatSync,
  openSync, readSync, writeSync,
} from "node:fs";
import { dirname, resolve } from "node:path";
import type { GatewayOptions } from "./gateway.js";

type ResponsesErrorHandler = NonNullable<NonNullable<GatewayOptions["responses"]>["onError"]>;
const MAX_BYTES = 64 * 1024;
// Exact static outputs of the reviewed responsesFailureCode contract. Do not
// serialize the supplied event or error: either may acquire sensitive fields.
const CODES = new Set([
  "data_after_terminal", "sse_frame_too_large", "duplicate_terminal",
  "invalid_upstream_chunk", "invalid_usage", "invalid_token_details",
  "expected_single_choice", "invalid_choice_index", "unqualified_reasoning_field",
  "data_after_finish", "unsupported_output_media", "output_bound_exceeded",
  "invalid_tool_deltas", "invalid_tool_index_type", "changed_call_id",
  "aggregate_tool_bound_exceeded", "tool_bound_exceeded", "duplicate_finish",
  "missing_finish_usage", "tool_finish_mismatch", "invalid_tool_identity",
  "invalid_custom_tool_input", "truncated_or_repeated_responses_stream",
  "invalid_json", "unqualified_output",
]);
const LANES = new Set(["qwen3.8-27b-gpu0", "qwen3.8-27b-gpu1", "qwen3.8-27b", "mimo-v2.6-pro-rl"]);
const ownerId = (value: unknown): string | null => typeof value === "string"
  && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value) ? value : null;

/** Host-owned existing directory, one writer; no directory creation or symlink traversal. */
function checkDirectory(path: string): void {
  const uid = process.getuid?.();
  let directory = dirname(path);
  const parent = lstatSync(directory);
  if (!parent.isDirectory() || (parent.mode & 0o022) !== 0 || parent.uid !== uid)
    throw new Error("Unsafe diagnostics directory");
  for (;;) {
    if (!lstatSync(directory).isDirectory()) throw new Error("Unsafe diagnostics path");
    const next = dirname(directory);
    if (next === directory) return;
    directory = next;
  }
}

function protectedFile(path: string): number {
  const fd = openSync(path, constants.O_RDWR | constants.O_CREAT | constants.O_NOFOLLOW | constants.O_NONBLOCK, 0o600);
  try {
    const stat = fstatSync(fd);
    if (!stat.isFile() || stat.nlink !== 1 || stat.uid !== process.getuid?.())
      throw new Error("Unsafe diagnostics file");
    fchmodSync(fd, 0o600);
    return fd;
  } catch (error) {
    closeSync(fd);
    throw error;
  }
}

function writeAll(fd: number, bytes: Buffer, position: number): void {
  let offset = 0;
  while (offset < bytes.length) {
    const written = writeSync(fd, bytes, offset, bytes.length - offset, position + offset);
    if (written === 0) throw new Error("Diagnostics write incomplete");
    offset += written;
  }
}

/**
 * Best-effort local JSONL. Each file is at most 64 KiB, with one .1 rotation.
 * The host supplies a protected absolute path outside task workspaces. Logger
 * failures are deliberately isolated from request admission/settlement.
 */
export function createResponsesDiagnostics(path: string): ResponsesErrorHandler {
  const destination = resolve(path);
  return event => {
    let fd: number | undefined;
    try {
      const { phase, requestId, sessionId, lane, code } = event;
      if (phase !== "stream" && phase !== "terminal") return;
      const line = Buffer.from(JSON.stringify({
        time: new Date().toISOString(),
        requestId: ownerId(requestId),
        sessionId: ownerId(sessionId),
        lane: LANES.has(lane) ? lane : null,
        phase,
        code: CODES.has(code) ? code : "unqualified_output",
      }) + "\n");
      checkDirectory(destination);
      fd = protectedFile(destination);
      let size = fstatSync(fd).size;
      // An oversized inherited file is not copied into the bounded rotation.
      if (size > MAX_BYTES) { ftruncateSync(fd, 0); size = 0; }
      if (size + line.length > MAX_BYTES) {
        const previous = protectedFile(destination + ".1");
        try {
          const bytes = Buffer.alloc(size);
          let read = 0;
          while (read < size) {
            const count = readSync(fd, bytes, read, size - read, read);
            if (count === 0) throw new Error("Diagnostics read incomplete");
            read += count;
          }
          ftruncateSync(previous, 0);
          writeAll(previous, bytes, 0);
          ftruncateSync(fd, 0);
          size = 0;
        } finally { closeSync(previous); }
      }
      writeAll(fd, line, size);
    } catch { /* Never affect gateway ownership or disclose logging failures. */ }
    finally { if (fd !== undefined) { try { closeSync(fd); } catch { /* best effort */ } } }
  };
}
