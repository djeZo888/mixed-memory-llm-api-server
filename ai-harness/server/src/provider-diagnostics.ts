/** Host-only, explicitly owned acceptance capture. Never enabled by chat/env. */
import { constants, openSync, closeSync, writeFileSync, lstatSync, fstatSync, writeSync, realpathSync } from "node:fs";
import { join, isAbsolute, dirname } from "node:path";
import { createHash } from "node:crypto";

export interface ProviderBoundaryCapture {
  requestId: string; sessionId: string; model: string; lane?: string;
  phase: "pre_normalization" | "normalized_request" | "provider_sse" | "responses_sse";
  bytes: Buffer;
}
export interface ProviderFailure {
  requestId: string; sessionId: string; model: string;
  phase: "validation" | "counting";
  code: string; rule?: string;
}
const uuid = (v: unknown): v is string => typeof v === "string" && /^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/i.test(v);
const phases = new Set(["pre_normalization", "normalized_request", "provider_sse", "responses_sse"]);
const models = new Set(["qwen3.8-27b", "mimo-v2.6-pro-rl", "glm-5.3-flash"]);

/** Caller supplies an existing private directory outside task mounts and an
 * exact session owner. Raw bytes stay private; index publishes hashes only.
 * Total bytes/events are bounded across the whole selected acceptance. */
export function createOwnedProviderCapture(directory: string, sessionId: string, maxBytes = 64 * 1024 * 1024) {
  if (!uuid(sessionId) || !isAbsolute(directory) || realpathSync(directory) !== directory ||
      !Number.isSafeInteger(maxBytes) || maxBytes < 1 || maxBytes > 128 * 1024 * 1024) throw Error("Invalid private capture policy");
  const uid = process.getuid?.(), initial = lstatSync(directory);
  if (!initial.isDirectory() || initial.uid !== uid || (initial.mode & 0o077)) throw Error("Unsafe private capture directory");
  for (let p = dirname(directory);; p = dirname(p)) {
    const s = lstatSync(p);
    if (!s.isDirectory() || (s.mode & 0o022) || ![0, uid].includes(s.uid)) throw Error("Unsafe capture ancestry");
    if (p === dirname(p)) break;
  }
  const flags = constants.O_WRONLY | constants.O_CREAT | constants.O_EXCL | constants.O_NOFOLLOW;
  const index = openSync(join(directory, "capture-index.jsonl"), flags, 0o600);
  let size = 0, sequence = 0, closed = false, limited = false;
  const append = (value: unknown) => writeFileSync(index, JSON.stringify(value) + "\n");
  return {
    capture(event: ProviderBoundaryCapture) {
      if (closed || event.sessionId !== sessionId || !uuid(event.requestId) || !models.has(event.model) || !phases.has(event.phase)) return;
      if (sequence >= 8192 || size + event.bytes.length > maxBytes) {
        if (!limited) { append({ kind: "capture_limit", complete: false }); limited = true; }
        return;
      }
      const current = lstatSync(directory);
      if (current.ino !== initial.ino || current.dev !== initial.dev || current.uid !== uid || (current.mode & 0o077)) throw Error("Changed capture directory");
      const file = `${String(sequence++).padStart(5, "0")}-${event.requestId}-${event.phase}.bin`;
      const fd = openSync(join(directory, file), flags, 0o600);
      try {
        const st = fstatSync(fd);
        if (!st.isFile() || st.nlink !== 1 || st.uid !== uid) throw Error("Unsafe capture file");
        let written = 0;
        while (written < event.bytes.length) {
          const n = writeSync(fd, event.bytes, written, event.bytes.length - written);
          if (!n) throw Error("Incomplete private capture");
          written += n;
        }
      } finally { closeSync(fd); }
      size += event.bytes.length;
      append({ file, requestId: event.requestId, sessionId, model: event.model, phase: event.phase,
        bytes: event.bytes.length, sha256: createHash("sha256").update(event.bytes).digest("hex") });
    },
    close() { if (!closed) { closed = true; closeSync(index); } },
  };
}
