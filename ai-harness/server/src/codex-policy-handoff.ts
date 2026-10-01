/** Host-private durable adoption. HMAC key, handoff and raw receipts stay outside every model mount. */
import { constants, openSync, closeSync, fstatSync, readFileSync, lstatSync, realpathSync, writeFileSync } from "node:fs";
import { createHash, createHmac, timingSafeEqual } from "node:crypto";
import { dirname, join, sep } from "node:path";
import { canonicalJson } from "./codex-canonical.js";
import { validateSessionRestartOwnership,correlateSessionRestartOwnership,claimSessionRestartOwnership, type SessionRestartOwnershipProof } from "./session-checkpoint.js";
import { codexReceiptProvenance, codexReceiptValidation, getCodexReceiptUtf8, revalidateRetainedCodexReceipts, type CodexReceiptBinding, type CodexReceiptIdentity } from "./codex-receipts.js";
import { assertCodexTextOnlyPolicy, codexPolicyOwner, createCodexContinuationPolicy,createCodexDeliveryPolicy,createCodexRetentionParentPolicy,createCodexDelivery04Policy,createCodexRetentionParent04Policy,createCodexDelivery05Policy,createCodexRetentionParent05Policy, createCodexH043Policy,createCodexH043RetentionParentPolicy,stageCodexPolicyAdoption, CODEX_PARENT_ARTIFACT_SPEC, type CodexTextOnlyPolicy, type CodexPolicyOwner } from "./codex-probe.js";
const sha=(b:Uint8Array|string)=>createHash("sha256").update(b).digest("hex");
function protectedRead(path:string,max:number):Buffer {
  if(realpathSync(path)!==path)throw Error("Noncanonical handoff path");
  const fd=openSync(path,constants.O_RDONLY|constants.O_NOFOLLOW|constants.O_NONBLOCK);
  try{const before=fstatSync(fd);if(!before.isFile()||before.nlink!==1||before.uid!==process.getuid?.()||(before.mode&0o777)!==0o600||before.size<1||before.size>max)throw Error("Unsafe private handoff file");const bytes=readFileSync(fd),after=fstatSync(fd);if(bytes.length!==before.size||after.size!==before.size||after.mtimeMs!==before.mtimeMs||after.ctimeMs!==before.ctimeMs)throw Error("Changing handoff file");return bytes;}finally{closeSync(fd);}
}
function protectedDirectory(path:string) { const s=lstatSync(path);if(realpathSync(path)!==path||!s.isDirectory()||s.isSymbolicLink()||s.uid!==process.getuid?.()||(s.mode&0o777)!==0o700)throw Error("Unsafe private handoff directory"); }
function outsideMounts(path:string,owner:CodexPolicyOwner) {
  for(const m of [...owner.launch.container.mounts,...owner.launch.container.additionalMounts]) for(const root of [m.source,m.destination])
    if(root&&(path===root||path.startsWith(root+sep)||root.startsWith(path+sep)))throw Error("Handoff overlaps model mount");
}
function rollout(path:string,owner:Pick<CodexPolicyOwner,"threadId"|"launch">,mode:CodexTextOnlyPolicy["mode"]) {
  const root=join(owner.launch.container.profileDir,"codex-home");
  if(!["sessions","archived_sessions"].some(n=>path.startsWith(join(root,n)+sep)))throw Error("Unowned native rollout path");
  const bytes=protectedRead(path,64*1024*1024),newline=bytes.indexOf(10);
  if(newline<1||newline>65536)throw Error("Missing bounded native session metadata");
  const meta=JSON.parse(new TextDecoder("utf-8",{fatal:true}).decode(bytes.subarray(0,newline)));
  if(meta.type!=="session_meta"||meta.payload?.id!==owner.threadId||meta.payload?.cli_version!=="0.158.0"||meta.payload?.model_provider!=="sova"||canonicalJson(meta.payload?.dynamic_tools??[])!==canonicalJson(["parent-artifacts","retention-parent"].includes(mode)?[CODEX_PARENT_ARTIFACT_SPEC]:[]))throw Error("Native rollout identity/catalog mismatch");
  const s=lstatSync(path);return {path,sha256:sha(bytes),bytes:bytes.length,device:s.dev,inode:s.ino};
}
function verifyClosure(closure:Readonly<Record<string,string>>) {
  if(!Object.keys(closure).length||Object.keys(closure).length>256)throw Error("Missing host source/build closure");
  for(const [path,digest] of Object.entries(closure)) {const s=lstatSync(path);if(realpathSync(path)!==path||!s.isFile()||s.isSymbolicLink()||s.mode&0o022||![0,process.getuid?.()].includes(s.uid)||! /^[a-f0-9]{64}$/.test(digest)||sha(readFileSync(path))!==digest)throw Error("Host source/build closure changed");}
}
interface HandoffBody {
  schema:"codex-policy-handoff-v1";sessionId:string;threadId:string;checkpointId:string;
  policy:CodexTextOnlyPolicy;settledTurnId:string;checkpoints:CodexPolicyOwner["checkpoints"];
  validation:{binding:CodexReceiptBinding;observedProducer:CodexReceiptIdentity;validatedAtMs:number};
  launch:{sha256:string;originalPath:string};settlement:{sha256:string;originalPath:string};
  rollout:ReturnType<typeof rollout>;sourceClosure:Readonly<Record<string,string>>;
  ownership:string;purpose:"accepted-continuation"|"settled-compaction";settledCompaction?:CodexPolicyOwner["settledCompaction"];
}
declare const handoffBrand:unique symbol;
export interface AuthenticatedCodexHandoff {readonly [handoffBrand]:true}
const authenticated=new WeakMap<AuthenticatedCodexHandoff,{body:HandoffBody;directory:string;runId:string}>();
/** No public minting API. Only the fully authenticated sealed reader below creates this capability. */
export function assertAuthenticatedCodexHandoff(cap:AuthenticatedCodexHandoff,target:"receipts"|"owner",value:unknown) {
  const authority=authenticated.get(cap);if(!authority)throw Error("Missing authenticated protected handoff capability");
  const b=authority.body;
  const expected=target==="receipts"?{launchPath:join(authority.directory,"launch.raw.json"),settlementPath:join(authority.directory,"settlement.raw.json"),launchSha256:b.launch.sha256,settlementSha256:b.settlement.sha256,binding:b.validation.binding,observedProducer:b.validation.observedProducer,originalValidatedAtMs:b.validation.validatedAtMs}:{threadId:b.threadId,checkpoints:b.checkpoints,settledTurnId:b.settledTurnId,settledCompaction:b.settledCompaction};
  if(canonicalJson(value)!==canonicalJson(expected))throw Error("Authenticated handoff binding changed");
}
export interface CodexPolicyHandoffInput { policy:CodexTextOnlyPolicy;checkpointId:string;directory:string;keyPath:string;sourceClosure:Readonly<Record<string,string>>;ownership:SessionRestartOwnershipProof;purpose?:"accepted-continuation"|"settled-compaction" }
/** No caller-supplied receipt JSON: only genuine engine-owned successful consumed parent is retainable. */
export function retainCodexPolicyHandoff(input:CodexPolicyHandoffInput) {
  assertCodexTextOnlyPolicy(input.policy,input.policy.sessionId,Date.now(),false);
  const owner=codexPolicyOwner(input.policy),validation=owner&&codexReceiptValidation(owner.launch);
  if(!owner?.settlement||!owner.settledTurnId||!owner.rolloutPath||!validation||(input.purpose==="settled-compaction"?!owner.settledCompaction:!["parent-artifacts","retention-parent"].includes(input.policy.mode)||owner.checkpoints.filter(c=>c.checkpointId===input.checkpointId&&c.turnId===owner.settledTurnId).length!==2))throw Error("Parent lacks actual settled consumed checkpoint");
  const launch=getCodexReceiptUtf8(owner.launch),settlement=getCodexReceiptUtf8(owner.settlement),lp=codexReceiptProvenance(owner.launch),sp=codexReceiptProvenance(owner.settlement);
  if(!launch||!settlement||!lp||!sp||sha(launch)!==lp.rawSha256||sha(settlement)!==sp.rawSha256)throw Error("Missing genuine ORIGINAL receipt bytes");
  protectedDirectory(input.directory);outsideMounts(input.directory,owner);outsideMounts(input.keyPath,owner);const key=protectedRead(input.keyPath,32);if(key.length!==32)throw Error("Invalid private handoff key");verifyClosure(input.sourceClosure);
  if(input.ownership.sessionId!==input.policy.sessionId||input.ownership.threadId!==owner.threadId||input.ownership.checkpointId!==input.checkpointId)throw Error("Foreign Store checkpoint authority");
  if((input.ownership.purpose??"accepted-continuation")!==(input.purpose??"accepted-continuation"))throw Error("Restart purpose differs from Store proof");
  const ownership=validateSessionRestartOwnership(input.ownership);correlateSessionRestartOwnership(input.ownership,owner);
  const body:HandoffBody={schema:"codex-policy-handoff-v1",sessionId:input.policy.sessionId,threadId:owner.threadId,checkpointId:input.checkpointId,policy:input.policy,settledTurnId:owner.settledTurnId,checkpoints:owner.checkpoints.filter(c=>c.checkpointId===input.checkpointId),validation,launch:{sha256:lp.rawSha256,originalPath:lp.rawPath},settlement:{sha256:sp.rawSha256,originalPath:sp.rawPath},rollout:rollout(owner.rolloutPath,owner,input.policy.mode),sourceClosure:input.sourceClosure,ownership,purpose:input.purpose??"accepted-continuation",settledCompaction:owner.settledCompaction};
  const raw=JSON.stringify(body),seal=createHmac("sha256",key).update(raw).digest("hex");
  writeFileSync(join(input.directory,"launch.raw.json"),launch,{flag:"wx",mode:0o600});writeFileSync(join(input.directory,"settlement.raw.json"),settlement,{flag:"wx",mode:0o600});
  const path=join(input.directory,"handoff.json"),bytes=JSON.stringify({body,seal})+"\n";writeFileSync(path,bytes,{flag:"wx",mode:0o600});return Object.freeze({path,sha256:sha(bytes),threadId:owner.threadId,checkpointId:input.checkpointId});
}
export type CodexPolicyHandoffAuthorization="continuation02"|"delivery03"|"delivery04"|"delivery05"|"h043";
/** Reconstruct a genuine branded source capability, never operational GO. */
export function reconstructCodexPolicyHandoffPolicy(input:{sessionId:string;runId:string;configSha256:string;modelCatalogSha256:string;mode:"parent-artifacts"|"text-only-parent"|"retention-parent";collaborationVersion?:"v1"|"v2";authorization?:CodexPolicyHandoffAuthorization}):CodexTextOnlyPolicy {
 if(Object.keys(input).some(k=>!["sessionId","runId","configSha256","modelCatalogSha256","mode","collaborationVersion","authorization"].includes(k)))throw Error("Unexpected handoff policy field");
 if(input.authorization!==undefined&&!["continuation02","delivery03","delivery04","delivery05","h043"].includes(input.authorization))throw Error("Unknown source-frozen adoption authorization");
 const fields={sessionId:input.sessionId,runId:input.runId,configSha256:input.configSha256,modelCatalogSha256:input.modelCatalogSha256};
 if(input.mode==="retention-parent"){
  if(input.collaborationVersion!=="v1"&&input.collaborationVersion!=="v2")throw Error("Observed native collaboration version required");
  const factory=input.authorization==="h043"?createCodexH043RetentionParentPolicy:input.authorization==="delivery05"?createCodexRetentionParent05Policy:input.authorization==="delivery04"?createCodexRetentionParent04Policy:createCodexRetentionParentPolicy;
  return factory({...fields,collaborationVersion:input.collaborationVersion});
 }
 if(!["parent-artifacts","text-only-parent"].includes(input.mode)||input.collaborationVersion!==undefined)throw Error("Invalid prior policy mode/collaboration");
 const factory=input.authorization==="h043"?createCodexH043Policy:input.authorization==="delivery05"?createCodexDelivery05Policy:input.authorization==="delivery04"?createCodexDelivery04Policy:input.authorization==="delivery03"?createCodexDeliveryPolicy:createCodexContinuationPolicy;
 return factory({...fields,mode:input.mode});
}
export interface AdoptCodexPolicyHandoffInput { path:string;sha256:string;keyPath:string;sessionId:string;threadId:string;checkpointId:string;runId:string;configSha256:string;modelCatalogSha256:string;sourceClosure:Readonly<Record<string,string>>;ownership:SessionRestartOwnershipProof;purpose?:"accepted-continuation"|"settled-compaction";authorization?:CodexPolicyHandoffAuthorization }
/** Stages historical ownership. CodexEngine.start still MUST validate a new genuine launch before resume. */
export function adoptCodexPolicyHandoff(input:AdoptCodexPolicyHandoffInput):CodexTextOnlyPolicy {
  if(input.authorization!==undefined&&input.authorization!=="continuation02"&&input.authorization!=="delivery03"&&input.authorization!=="delivery04"&&input.authorization!=="delivery05"&&input.authorization!=="h043")throw Error("Unknown source-frozen adoption authorization");
  protectedDirectory(dirname(input.path));const raw=protectedRead(input.path,131072);if(sha(raw)!==input.sha256)throw Error("Handoff hash changed");
  const value=JSON.parse(new TextDecoder("utf-8",{fatal:true}).decode(raw)),key=protectedRead(input.keyPath,32);
  if(Object.keys(value).sort().join()!=="body,seal"||key.length!==32||typeof value.seal!=="string"||!/^[a-f0-9]{64}$/.test(value.seal)||!timingSafeEqual(Buffer.from(value.seal,"hex"),createHmac("sha256",key).update(JSON.stringify(value.body)).digest()))throw Error("Untrusted host handoff seal");
  const b=value.body as HandoffBody;
  if(b.schema!=="codex-policy-handoff-v1"||b.sessionId!==input.sessionId||b.threadId!==input.threadId||b.checkpointId!==input.checkpointId||!(["parent-artifacts","text-only-parent","retention-parent"].includes(b.policy.mode))||b.policy.sessionId!==input.sessionId||b.policy.configSha256!==input.configSha256||b.policy.modelCatalogSha256!==input.modelCatalogSha256||canonicalJson(b.sourceClosure)!==canonicalJson(input.sourceClosure)||((b.purpose??"accepted-continuation")!==(input.purpose??"accepted-continuation"))||(b.purpose==="settled-compaction"?!b.settledCompaction:!["parent-artifacts","retention-parent"].includes(b.policy.mode)||b.checkpoints.length!==2||new Set(b.checkpoints.map(c=>c.name)).size!==2||b.checkpoints.some(c=>c.checkpointId!==input.checkpointId||c.turnId!==b.settledTurnId)))throw Error("Foreign/changed prior policy checkpoint");
  verifyClosure(input.sourceClosure);
  if((input.ownership.purpose??"accepted-continuation")!==(input.purpose??"accepted-continuation"))throw Error("Restart purpose differs from Store proof");
  if(input.ownership.sessionId!==input.sessionId||input.ownership.threadId!==input.threadId||input.ownership.checkpointId!==input.checkpointId||validateSessionRestartOwnership(input.ownership)!==b.ownership)throw Error("Changed/uncertain protected Store ownership");
  const cap={} as AuthenticatedCodexHandoff;authenticated.set(cap,{body:b,directory:dirname(input.path),runId:input.runId});
  const pair=revalidateRetainedCodexReceipts({launchPath:join(dirname(input.path),"launch.raw.json"),settlementPath:join(dirname(input.path),"settlement.raw.json"),launchSha256:b.launch.sha256,settlementSha256:b.settlement.sha256,binding:b.validation.binding,observedProducer:b.validation.observedProducer,originalValidatedAtMs:b.validation.validatedAtMs},cap);
  if(pair.launch.sessionId!==input.sessionId||pair.launch.runId!==b.policy.runId||pair.launch.sources["codex/config.toml"]!==input.configSha256||pair.launch.sources["codex/models.json"]!==input.modelCatalogSha256)throw Error("Original receipt policy mismatch");
  const owner:CodexPolicyOwner={threadId:b.threadId,launch:pair.launch,settlement:pair.settlement,rolloutPath:b.rollout.path,settledTurnId:b.settledTurnId,checkpoints:b.checkpoints,settledCompaction:b.settledCompaction};
  outsideMounts(dirname(input.path),owner);outsideMounts(input.keyPath,owner);
  correlateSessionRestartOwnership(input.ownership,owner);
  const current=rollout(b.rollout.path,owner,b.policy.mode);if(JSON.stringify(current)!==JSON.stringify(b.rollout))throw Error("Owned parent rollout changed after settled handoff");
  const policy=reconstructCodexPolicyHandoffPolicy({sessionId:input.sessionId,runId:input.runId,configSha256:input.configSha256,modelCatalogSha256:input.modelCatalogSha256,mode:b.policy.mode as "parent-artifacts"|"text-only-parent"|"retention-parent",collaborationVersion:b.policy.collaborationVersion,authorization:input.authorization});
  assertCodexTextOnlyPolicy(policy);
  // One-shot marker is host-only and survives application exit. Failed adoption is never replayed.
  claimSessionRestartOwnership(input.ownership,input.runId,input.sha256);
  writeFileSync(join(dirname(input.path),"adoption.claim"),JSON.stringify({sessionId:input.sessionId,threadId:input.threadId,runId:input.runId,claimedAt:new Date().toISOString()}),{flag:"wx",mode:0o600});
  stageCodexPolicyAdoption(policy,owner,cap);return policy;
}
