/** Allowlisted native metadata. Authentication alone does not prove a native process authored a header. */
import { createHash } from "node:crypto";
import { codexReceiptProvenance, isHistoricalCodexReceipt, type CodexNativeLaunchReceipt } from "./codex-receipts.js";
export interface CodexTurnMetadata {
  request_kind:"turn"|"prewarm"|"compaction"|"memory";thread_id?:string;turn_id?:string;window_id?:string;
  compaction?:{trigger:"auto"|"manual";reason:string;phase:string;implementation:string;strategy:string};
}
export function parseCodexTurnMetadata(raw:unknown):CodexTurnMetadata|undefined {
  if(typeof raw!=="string"||Buffer.byteLength(raw)>8192)return undefined;
  let v:unknown;try{v=JSON.parse(raw);}catch{return undefined;}
  if(!v||typeof v!=="object"||Array.isArray(v))return undefined;const a=v as Record<string,unknown>;
  if(typeof a.request_kind!=="string"||!["turn","prewarm","compaction","memory"].includes(a.request_kind))return undefined;
  const out:CodexTurnMetadata={request_kind:a.request_kind as CodexTurnMetadata["request_kind"]};
  for(const key of ["thread_id","turn_id","window_id"] as const)if(a[key]!==undefined){if(typeof a[key]!=="string"||! /^[A-Za-z0-9._:-]{1,128}$/.test(a[key]))return undefined;out[key]=a[key];}
  if(out.request_kind!=="memory"&&!out.thread_id)return undefined;
  if(out.request_kind==="compaction"){
    const c=a.compaction;if(!c||typeof c!=="object"||Array.isArray(c))return undefined;const r=c as Record<string,unknown>;
    const enums={trigger:["auto","manual"],reason:["user_requested","context_limit","model_downshift","comp_hash_changed"],phase:["standalone_turn","pre_turn","mid_turn","post_turn"],implementation:["responses","responses_compaction_v2"],strategy:["memento","prefix_compaction"]};
    if(Object.keys(r).sort().join()!==Object.keys(enums).sort().join()||Object.entries(enums).some(([key,values])=>typeof r[key]!=="string"||!values.includes(r[key] as string)))return undefined;
    out.compaction=Object.freeze({...r}) as CodexTurnMetadata["compaction"];
  }else if(a.compaction!==undefined)return undefined;
  return Object.freeze(out);
}
export interface CodexMetadataAuthority {readonly sessionId:string;readonly threadId:string}
const authorities=new WeakMap<CodexMetadataAuthority,{launch:CodexNativeLaunchReceipt;signal:AbortSignal}>();
/** Trusted host observer only, after actual thread ACK/Store ownership verification. */
export function createCodexMetadataAuthority(input:{sessionId:string;threadId:string;launchReceipt:CodexNativeLaunchReceipt;signal:AbortSignal}) {
  if(!codexReceiptProvenance(input.launchReceipt)||isHistoricalCodexReceipt(input.launchReceipt)||input.launchReceipt.sessionId!==input.sessionId||input.signal.aborted||! /^[A-Za-z0-9._:-]{1,128}$/.test(input.threadId))throw Error("Metadata lacks genuine current native ownership");
  const authority=Object.freeze({sessionId:input.sessionId,threadId:input.threadId});authorities.set(authority,{launch:input.launchReceipt,signal:input.signal});return authority;
}
export function validateCodexMetadataAuthority(authority:CodexMetadataAuthority,sessionId:string,metadata:CodexTurnMetadata) {
  const owner=authorities.get(authority);if(!owner||owner.signal.aborted||authority.sessionId!==sessionId||metadata.thread_id!==authority.threadId)throw Error("Foreign/unqualified native metadata owner");
  return Object.freeze({source:"host_observed_native_report" as const,launchRawSha256:codexReceiptProvenance(owner.launch)!.rawSha256,metadataSha256:createHash("sha256").update(JSON.stringify(metadata)).digest("hex")});
}
export interface CodexNativeOperationReceipt {requestId:string;sessionId:string;model:string;lane?:string;phase:"received"|"accepted"|"settled"|"uncertain";metadata:CodexTurnMetadata;provenance:ReturnType<typeof validateCodexMetadataAuthority>;nativeSemanticAcceptance:"NOT_TESTED"}
