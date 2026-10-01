/** Host-only immutable original scope. Never construct from a chat/request payload. */
import { createHash } from "node:crypto";
export interface CodexReadOriginalProbe {
  readonly sessionId: string;
  readonly runId: string;
  readonly checkpointId: string;
  readonly baseInstructions: string;
  readonly references: readonly { readonly reference: string; readonly bytes: number; readonly sha256: string }[];
}
const scopes = new WeakMap<CodexReadOriginalProbe, { claimed: boolean; originals: Map<string, Uint8Array> }>();
const id = (v: string) => typeof v === "string" && /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(v);
const freeze = <T>(value: T): T => { if (value && typeof value === "object") { Object.values(value).forEach(freeze); Object.freeze(value); } return value; };
export const CODEX_READ_ORIGINAL_SPEC = freeze({ type: "function", name: "read_original",
  description: "Read a bounded UTF-8 excerpt from this probe's frozen original checkpoint.",
  inputSchema: { type: "object", properties: { reference: { type: "string" }, offset: { type: "integer", minimum: 0 }, limit: { type: "integer", minimum: 1, maximum: 8192 } }, required: ["reference", "offset", "limit"], additionalProperties: false } });
export function createCodexReadOriginalProbe(input: {
  sessionId: string; runId: string; checkpointId: string; baseInstructions: string;
  originals: readonly { reference: string; bytes: Uint8Array }[];
}): CodexReadOriginalProbe {
  if (![input.sessionId, input.runId, input.checkpointId].every(id) || typeof input.baseInstructions !== "string" || Buffer.byteLength(input.baseInstructions) > 65536 || !Array.isArray(input.originals) || input.originals.length < 1 || input.originals.length > 32)
    throw Error("Invalid trusted original scope");
  const originals = new Map<string, Uint8Array>(); let total = 0;
  const references = input.originals.map(entry => {
    if (!id(entry.reference) || originals.has(entry.reference) || !(entry.bytes instanceof Uint8Array) || (total += entry.bytes.byteLength) > 64 * 1024 * 1024)
      throw Error("Invalid trusted original reference");
    const bytes = Uint8Array.from(entry.bytes); originals.set(entry.reference, bytes);
    return Object.freeze({ reference: entry.reference, bytes: bytes.byteLength, sha256: createHash("sha256").update(bytes).digest("hex") });
  });
  const probe = Object.freeze({ sessionId: input.sessionId, runId: input.runId, checkpointId: input.checkpointId, baseInstructions: input.baseInstructions, references: Object.freeze(references) });
  scopes.set(probe, { originals, claimed: false }); return probe;
}
export function claimCodexReadOriginalProbe(probe: CodexReadOriginalProbe, sessionId: string) {
  const scope = scopes.get(probe);
  if (!scope || scope.claimed || probe.sessionId !== sessionId) throw Error("Unowned or reused original scope");
  scope.claimed = true;
}
export async function readCodexOriginal(probe: CodexReadOriginalProbe, args: unknown, signal: AbortSignal): Promise<string> {
  const scope = scopes.get(probe);
  if (!scope?.claimed || signal.aborted || !args || typeof args !== "object" || Array.isArray(args)) throw Error("Original read unavailable");
  const a = args as Record<string, unknown>;
  if (Object.keys(a).sort().join() !== "limit,offset,reference" || typeof a.reference !== "string" || !Number.isSafeInteger(a.offset) || !Number.isSafeInteger(a.limit) || (a.offset as number) < 0 || (a.limit as number) < 1 || (a.limit as number) > 8192) throw Error("Invalid bounded original read");
  const bytes = scope.originals.get(a.reference);
  if (!bytes || (a.offset as number) > bytes.byteLength) throw Error("Original reference unavailable");
  // Copy first, yield once so cancellation cannot publish a late read result.
  const slice = bytes.slice(a.offset as number, Math.min(bytes.byteLength, (a.offset as number) + (a.limit as number)));
  await Promise.resolve();
  if (signal.aborted) throw Error("Original read cancelled");
  return new TextDecoder("utf-8", { fatal: true }).decode(slice);
}
