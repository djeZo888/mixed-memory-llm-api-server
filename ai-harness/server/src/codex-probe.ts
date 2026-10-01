/** Host-only immutable original scope. Never construct from a chat/request payload. */
import { codexReceiptProvenance, isVerifiedCodexSettlementReceipt, type CodexNativeLaunchReceipt, type CodexNativeSettlementReceipt } from "./codex-receipts.js";
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

/** Trusted H041 source entry. This capability is not native qualification. */
export const CODEX_H041_WINDOW = Object.freeze({ startAtMs: Date.parse("2026-10-01T08:05:07Z"), expiresAtMs: Date.parse("2026-10-01T10:05:07Z"), settlementReserveMs: 120000 });
export interface CodexTextOnlyPolicy {
  readonly sessionId: string; readonly runId: string;
  readonly mode: "summary-only" | "text-only-parent" | "read-original" | "parent-artifacts";
  readonly configSha256: string; readonly modelCatalogSha256: string;
  readonly window: typeof CODEX_H041_WINDOW;
}
const policies = new WeakSet<object>();
export function createCodexTextOnlyPolicy(input: Omit<CodexTextOnlyPolicy, "window">): CodexTextOnlyPolicy {
  if (!id(input.sessionId) || !id(input.runId) || !["summary-only", "text-only-parent", "read-original", "parent-artifacts"].includes(input.mode) || ![input.configSha256, input.modelCatalogSha256].every(v => typeof v === "string" && /^[a-f0-9]{64}$/.test(v)) || Object.keys(input).sort().join() !== "configSha256,mode,modelCatalogSha256,runId,sessionId") throw Error("Invalid trusted text-only policy");
  const policy = freeze({ ...input, window: CODEX_H041_WINDOW }); policies.add(policy); return policy;
}
export function assertCodexTextOnlyPolicy(policy: CodexTextOnlyPolicy, sessionId = policy.sessionId, now = Date.now(), dispatch = true): void {
  if (!policies.has(policy) || policy.sessionId !== sessionId || now < policy.window.startAtMs || now >= policy.window.expiresAtMs - (dispatch ? policy.window.settlementReserveMs : 0)) throw Error("Unowned or expired H041 text-only policy");
}
/** These are consumed config keys in 064c. Environment omission also suppresses
 * apply_patch; feature flags alone do not. An observed provider tools gate is
 * still mandatory: model-catalog unconditional tools are not disabled by flags. */
export function codexTextOnlyThreadParams(policy: CodexTextOnlyPolicy, method: "thread/start" | "thread/resume" = "thread/start") {
  assertCodexTextOnlyPolicy(policy);
  const config: Record<string, unknown> = { "agents.enabled": false, "tools.update_plan.enabled": false, "tools.experimental_request_user_input.enabled": false, "web_search": "disabled" };
  for (const key of ["shell_tool", "view_image", "sleep_tool", "apps", "plugins", "tool_suggest", "tool_search", "code_mode", "code_mode_only", "multi_agent", "multi_agent_v2", "request_permissions_tool", "current_time_reminder", "token_budget", "deferred_executor", "send_message_to_user_async", "goals", "memories", "context_management", "image_generation", "standalone_web_search", "enable_mcp_apps"]) config["features." + key] = false;
  // The reviewed mounted config has exactly these three MCP servers. Its digest
  // and the model catalog digest are bound to the producer's launch closure.
  for (const name of ["search", "browser", "image"]) config["mcp_servers." + name + ".enabled"] = false;
  return { sandbox: "read-only", ...(method === "thread/start" ? { environments: [] } : {}), config };
}

/** Separate bounded artifact capability. Never widens summary/read-original. */
export interface CodexParentArtifactScope {
  readonly sessionId: string; readonly runId: string; readonly checkpointId: string;
  readonly names: readonly [string, string]; readonly maxBytes: number;
}
const artifactScopes = new WeakMap<CodexParentArtifactScope, { claimed: boolean; names: Set<string> }>();
export function createCodexParentArtifactScope(input: CodexParentArtifactScope): CodexParentArtifactScope {
  if (![input.sessionId,input.runId,input.checkpointId].every(id) || !Array.isArray(input.names) || input.names.length !== 2 || new Set(input.names).size !== 2 || !input.names.every(n => /^[A-Za-z0-9][A-Za-z0-9_-]{0,63}\.json$/.test(n)) || !Number.isSafeInteger(input.maxBytes) || input.maxBytes < 2 || input.maxBytes > 65536 || Object.keys(input).sort().join() !== "checkpointId,maxBytes,names,runId,sessionId") throw Error("Invalid bounded parent artifact scope");
  const scope = freeze({ ...input, names: [...input.names] as [string,string] });
  artifactScopes.set(scope, {claimed:false,names:new Set()}); return scope;
}
export function claimCodexParentArtifactScope(scope: CodexParentArtifactScope, sessionId: string) {
  const state=artifactScopes.get(scope); if (!state || state.claimed || scope.sessionId!==sessionId) throw Error("Unowned or reused parent artifact scope"); state.claimed=true;
}
export function reserveCodexParentArtifact(scope: CodexParentArtifactScope, args: unknown): { name: string; jsonUtf8: string; sha256: string } {
  const state=artifactScopes.get(scope);
  if (!state?.claimed || !args || typeof args!=="object" || Array.isArray(args)) throw Error("Parent artifact unavailable");
  const a=args as Record<string,unknown>;
  if (Object.keys(a).sort().join()!=="json,name" || typeof a.name!=="string" || !scope.names.includes(a.name) || state.names.has(a.name) || typeof a.json!=="string" || Buffer.byteLength(a.json)>scope.maxBytes) throw Error("Invalid bounded parent artifact");
  const value: unknown=JSON.parse(a.json); if (!value || typeof value!=="object") throw Error("Parent artifact must contain JSON object or array");
  state.names.add(a.name); return Object.freeze({name:a.name,jsonUtf8:a.json,sha256:createHash("sha256").update(a.json).digest("hex")});
}
export const CODEX_PARENT_ARTIFACT_SPEC=freeze({type:"function",name:"write_checkpoint_artifact",description:"Register one of this owned checkpoint's two bounded JSON artifacts.",inputSchema:{type:"object",properties:{name:{type:"string"},json:{type:"string",description:"Complete JSON object or array encoded as UTF-8 text."}},required:["name","json"],additionalProperties:false}});

const ownedThreads = new WeakMap<CodexTextOnlyPolicy, { threadId: string; launch: CodexNativeLaunchReceipt; settlement?: CodexNativeSettlementReceipt }>();
export function recordCodexPolicyThread(policy: CodexTextOnlyPolicy, threadId: string, launch: CodexNativeLaunchReceipt) {
  if (!codexReceiptProvenance(launch) || launch.sessionId!==policy.sessionId || launch.runId!==policy.runId || !id(threadId)) return;
  const old=ownedThreads.get(policy); if (old && old.threadId!==threadId) throw Error("Policy changed owned native thread");
  ownedThreads.set(policy,{threadId,launch});
}
export function recordCodexPolicySettlement(policy: CodexTextOnlyPolicy, receipt: CodexNativeSettlementReceipt) {
  const owner=ownedThreads.get(policy);
  if (owner && isVerifiedCodexSettlementReceipt(receipt) && codexReceiptProvenance(receipt) && receipt.cleanupOk && receipt.nonce===owner.launch.nonce && receipt.containerId===owner.launch.container.id) owner.settlement=receipt;
}
export function codexPolicyOwnsSettledThread(policy: CodexTextOnlyPolicy, threadId: string): boolean {
  const owner=ownedThreads.get(policy); return ["text-only-parent","parent-artifacts"].includes(policy.mode) && !!owner?.settlement && owner.threadId===threadId;
}
