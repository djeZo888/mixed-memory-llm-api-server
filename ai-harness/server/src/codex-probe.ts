/** Host-only immutable original scope. Never construct from a chat/request payload. */
import { codexReceiptProvenance, isVerifiedCodexSettlementReceipt, isHistoricalCodexReceipt, type CodexNativeLaunchReceipt, type CodexNativeSettlementReceipt } from "./codex-receipts.js";
import { createHash } from "node:crypto";
import { assertAuthenticatedCodexHandoff, type AuthenticatedCodexHandoff } from "./codex-policy-handoff.js";
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
export const CODEX_H041_CONTINUATION_WINDOW = Object.freeze({ startAtMs: Date.parse("2026-10-01T09:11:06.096969Z"), expiresAtMs: Date.parse("2026-10-01T11:11:06.096969Z"), settlementReserveMs: 120000 });
export const CODEX_H041_DELIVERY_WINDOW=Object.freeze({startAtMs:Date.parse("2026-10-01T10:07:11.972488Z"),expiresAtMs:Date.parse("2026-10-01T13:07:11.972488Z"),settlementReserveMs:120000});
/** Separate DELIVERY05 authority from root frozen14:30:02; old windows immutable. */
export const CODEX_H041_DELIVERY05_WINDOW=Object.freeze({startAtMs:Date.parse("2026-10-01T14:30:02.674394Z"),expiresAtMs:Date.parse("2026-10-01T18:30:02.674394Z"),settlementReserveMs:120000});
/** Separate DELIVERY04 source-frozen authority; never redirects original/02/03 callers. */
export const CODEX_H041_DELIVERY04_WINDOW=Object.freeze({startAtMs:Date.parse("2026-10-01T11:26:45.729698Z"),expiresAtMs:Date.parse("2026-10-01T15:26:45.729698Z"),settlementReserveMs:120000});
/** H042 source capability only; operational admission/lease and fresh root GO remain mandatory. */
export const CODEX_H042_WINDOW = Object.freeze({ startAtMs: Date.parse("2026-10-01T17:44:17Z"), expiresAtMs: Date.parse("2026-10-01T20:29:17Z"), settlementReserveMs: 120000 });
/** H043 SOURCE capability only; no staging/native/generation authority. */
export const CODEX_H043_WINDOW = Object.freeze({ startAtMs: Date.parse("2026-10-01T21:19:33Z"), expiresAtMs: Date.parse("2026-10-02T00:04:33Z"), settlementReserveMs: 120000 });
export interface CodexTextOnlyPolicy {
  readonly sessionId: string; readonly runId: string;
  readonly mode: "summary-only" | "text-only-parent" | "read-original" | "parent-artifacts" | "retention-parent";
  readonly collaborationVersion?:"v1"|"v2";
  readonly configSha256: string; readonly modelCatalogSha256: string;
  readonly window: typeof CODEX_H041_WINDOW;
}
const policies = new WeakSet<object>();
function buildCodexTextOnlyPolicy(input: Omit<CodexTextOnlyPolicy, "window">, authorization: typeof CODEX_H041_WINDOW,collaborationVersion?:"v1"|"v2"): CodexTextOnlyPolicy {
  if (authorization!==CODEX_H041_WINDOW && authorization!==CODEX_H041_CONTINUATION_WINDOW && authorization!==CODEX_H041_DELIVERY_WINDOW && authorization!==CODEX_H041_DELIVERY04_WINDOW && authorization!==CODEX_H041_DELIVERY05_WINDOW && authorization!==CODEX_H042_WINDOW && authorization!==CODEX_H043_WINDOW) throw Error("Untrusted source authorization window");
  if (!id(input.sessionId) || !id(input.runId) || !(collaborationVersion?["retention-parent"]:["summary-only", "text-only-parent", "read-original", "parent-artifacts"]).includes(input.mode) || ![input.configSha256, input.modelCatalogSha256].every(v => typeof v === "string" && /^[a-f0-9]{64}$/.test(v)) || Object.keys(input).sort().join() !== "configSha256,mode,modelCatalogSha256,runId,sessionId") throw Error("Invalid trusted text-only policy");
  const policy = freeze({ ...input, window: authorization,...(collaborationVersion?{collaborationVersion}:{}) }); policies.add(policy); return policy;
}
export function createCodexTextOnlyPolicy(input: Omit<CodexTextOnlyPolicy,"window">) { return buildCodexTextOnlyPolicy(input,CODEX_H041_WINDOW); }
export function createCodexContinuationPolicy(input: Omit<CodexTextOnlyPolicy,"window">) { return buildCodexTextOnlyPolicy(input,CODEX_H041_CONTINUATION_WINDOW); }
export function createCodexDeliveryPolicy(input:Omit<CodexTextOnlyPolicy,"window"|"collaborationVersion">){return buildCodexTextOnlyPolicy(input,CODEX_H041_DELIVERY_WINDOW);}
export function createCodexRetentionParentPolicy(input:Omit<CodexTextOnlyPolicy,"window"|"mode">&{collaborationVersion:"v1"|"v2"}){
 if(input.collaborationVersion!=="v1"&&input.collaborationVersion!=="v2")throw Error("Observed native collaboration version required");
 const {collaborationVersion,...fields}=input;return buildCodexTextOnlyPolicy({...fields,mode:"retention-parent"},CODEX_H041_DELIVERY_WINDOW,collaborationVersion);
}
export function createCodexDelivery04Policy(input:Omit<CodexTextOnlyPolicy,"window"|"collaborationVersion">){return buildCodexTextOnlyPolicy(input,CODEX_H041_DELIVERY04_WINDOW);}
export function createCodexRetentionParent04Policy(input:Omit<CodexTextOnlyPolicy,"window"|"mode">&{collaborationVersion:"v1"|"v2"}){
 if(input.collaborationVersion!=="v1"&&input.collaborationVersion!=="v2")throw Error("Observed native collaboration version required");
 const {collaborationVersion,...fields}=input;return buildCodexTextOnlyPolicy({...fields,mode:"retention-parent"},CODEX_H041_DELIVERY04_WINDOW,collaborationVersion);
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
  for (const key of ["shell_tool", "view_image", "sleep_tool", "apps", "plugins", "tool_suggest", "code_mode", "code_mode_only", "multi_agent", "multi_agent_v2", "request_permissions_tool", "current_time_reminder", "token_budget", "deferred_executor", "send_message_to_user_async", "goals", "memories", "context_management", "image_generation", "standalone_web_search", "enable_mcp_apps"]) config["features." + key] = false;
  // The reviewed mounted config has exactly these three MCP servers. Its digest
  // and the model catalog digest are bound to the producer's launch closure.
  for (const name of ["search", "browser", "image"]) config["mcp_servers." + name + ".enabled"] = false;
  if(policy.mode==="retention-parent"){config["agents.enabled"]=true;config["agents.max_depth"]=1;config["agents.max_concurrent_threads_per_session"]=1;config["features.multi_agent"]=true;config["features.multi_agent_v2"]=policy.collaborationVersion==="v2";}
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

export interface CodexPolicyOwner { threadId: string; launch: CodexNativeLaunchReceipt; settlement?: CodexNativeSettlementReceipt; rolloutPath?: string; settledTurnId?: string; settledCompaction?:{turnId:string;compactionIds:string[]};checkpoints: {checkpointId:string;turnId:string;callId:string;name:string;artifactId:string;sha256:string}[]; pendingFreshLaunch?: boolean }
const ownedThreads = new WeakMap<CodexTextOnlyPolicy, CodexPolicyOwner>();
export function codexPolicyOwner(policy: CodexTextOnlyPolicy) { const owner=ownedThreads.get(policy);return owner?freeze({...owner,checkpoints:owner.checkpoints.map(c=>({...c}))}):undefined; }
export function recordCodexPolicyThread(policy: CodexTextOnlyPolicy, threadId: string, launch: CodexNativeLaunchReceipt, rolloutPath?:string) {
  if (!codexReceiptProvenance(launch) || launch.sessionId!==policy.sessionId || launch.runId!==policy.runId || !id(threadId)) return;
  const old=ownedThreads.get(policy); if (old && old.threadId!==threadId) throw Error("Policy changed owned native thread");
  ownedThreads.set(policy,{threadId,launch,rolloutPath:rolloutPath ?? old?.rolloutPath,checkpoints:old?.checkpoints ?? []});
}
/** Called only after the real canonical artifact completion and registrar digest match. */
export function recordCodexPolicyCheckpoint(policy:CodexTextOnlyPolicy,threadId:string,input:CodexPolicyOwner["checkpoints"][number]) {
  const owner=ownedThreads.get(policy); if (!owner || !codexReceiptProvenance(owner.launch)) return;
  if (owner.threadId!==threadId || !["parent-artifacts","retention-parent"].includes(policy.mode)) throw Error("Unowned consumed parent checkpoint");
  if (owner.checkpoints.some(c=>c.callId===input.callId || (c.checkpointId===input.checkpointId && c.name===input.name))) throw Error("Replayed consumed checkpoint"); owner.checkpoints.push(Object.freeze({...input}));
}
export function recordCodexPolicySuccessfulTurn(policy:CodexTextOnlyPolicy,turnId:string) {
  const owner=ownedThreads.get(policy); if (owner?.settlement && owner.settlement.cleanupOk && id(turnId)) owner.settledTurnId=turnId;
}
export function recordCodexPolicySuccessfulCompaction(policy:CodexTextOnlyPolicy,turnId:string,compactionIds:string[]) {
  const owner=ownedThreads.get(policy);if(owner?.settlement&&owner.settlement.cleanupOk&&id(turnId)&&compactionIds.length&&compactionIds.every(id)){owner.settledTurnId=turnId;owner.settledCompaction={turnId,compactionIds:[...compactionIds]};}
}
/** Host-sealed historical ownership alone never authorizes dispatch. Engine checks a NEW launch before resume. */
export function stageCodexPolicyAdoption(policy:CodexTextOnlyPolicy,owner:CodexPolicyOwner,cap:AuthenticatedCodexHandoff) {
  assertAuthenticatedCodexHandoff(cap,"owner",{threadId:owner.threadId,checkpoints:owner.checkpoints,settledTurnId:owner.settledTurnId,settledCompaction:owner.settledCompaction});
  if (!policies.has(policy) || !owner.settlement || !isHistoricalCodexReceipt(owner.launch) || !codexReceiptProvenance(owner.launch) || (!owner.checkpoints.length&&!owner.settledCompaction) || owner.launch.sessionId!==policy.sessionId) throw Error("Invalid historical policy adoption");
  ownedThreads.set(policy,{...owner,pendingFreshLaunch:true});
}
export function validateCodexPolicyFreshLaunch(policy:CodexTextOnlyPolicy,launch:CodexNativeLaunchReceipt) {
  const owner=ownedThreads.get(policy); if (!owner?.pendingFreshLaunch) return;
  if (!codexReceiptProvenance(launch) || isHistoricalCodexReceipt(launch) || launch.nonce===owner.launch.nonce || launch.sessionId!==policy.sessionId || launch.runId!==policy.runId || launch.container.profileDir!==owner.launch.container.profileDir || launch.container.workspace!==owner.launch.container.workspace || launch.sources["codex/config.toml"]!==policy.configSha256 || launch.sources["codex/models.json"]!==policy.modelCatalogSha256 || JSON.stringify(launch.sources)!==JSON.stringify(owner.launch.sources)) throw Error("Fresh adopted launch/source scope mismatch");
  owner.pendingFreshLaunch=false;
}
export function recordCodexPolicySettlement(policy: CodexTextOnlyPolicy, receipt: CodexNativeSettlementReceipt) {
  const owner=ownedThreads.get(policy);
  if (owner && isVerifiedCodexSettlementReceipt(receipt) && codexReceiptProvenance(receipt) && receipt.cleanupOk && receipt.nonce===owner.launch.nonce && receipt.containerId===owner.launch.container.id) owner.settlement=receipt;
}
export function codexPolicyOwnsSettledThread(policy: CodexTextOnlyPolicy, threadId: string): boolean {
  const owner=ownedThreads.get(policy); return ["text-only-parent","parent-artifacts","retention-parent"].includes(policy.mode) && !!owner?.settlement && owner.threadId===threadId;
}

export function createCodexDelivery05Policy(input:Omit<CodexTextOnlyPolicy,"window"|"collaborationVersion">){return buildCodexTextOnlyPolicy(input,CODEX_H041_DELIVERY05_WINDOW);}
export function createCodexRetentionParent05Policy(input:Omit<CodexTextOnlyPolicy,"window"|"mode">&{collaborationVersion:"v1"|"v2"}){if(input.collaborationVersion!=="v1"&&input.collaborationVersion!=="v2")throw Error("Observed native collaboration version required");const {collaborationVersion,...fields}=input;return buildCodexTextOnlyPolicy({...fields,mode:"retention-parent"},CODEX_H041_DELIVERY05_WINDOW,collaborationVersion);}

/** New bounded H042 source entry. Does not issue launch, generation, or native qualification authority. */
export function createCodexH042Policy(input: Omit<CodexTextOnlyPolicy, "window" | "collaborationVersion">) { return buildCodexTextOnlyPolicy(input, CODEX_H042_WINDOW); }

/** Observed collaboration version is independent of trace mode. Source only. */
export function createCodexH043RetentionParentPolicy(input:Omit<CodexTextOnlyPolicy,"window"|"mode">&{collaborationVersion:"v1"|"v2"}) {
 if(input.collaborationVersion!=="v1"&&input.collaborationVersion!=="v2")throw Error("Observed native collaboration version required");
 const {collaborationVersion,...fields}=input;return buildCodexTextOnlyPolicy({...fields,mode:"retention-parent"},CODEX_H043_WINDOW,collaborationVersion);
}

/** Distinct finite H043 entry; all prior policy factories retain their original windows. */
export function createCodexH043Policy(input: Omit<CodexTextOnlyPolicy, "window" | "collaborationVersion">) { return buildCodexTextOnlyPolicy(input, CODEX_H043_WINDOW); }
