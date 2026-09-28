/** Source-qualified nonthinking Qwen counter; host identity proof remains required.
 * Mirrors scripts/benchmark/accounting.py (no benchmark is invoked or polled).
 */
import type { GatewayUpstream } from "./gateway.js";
import { ApiError } from "./errors.js";
export const QWEN_CODEX_PIN = Object.freeze({modelRevision:"017b9c7af6b5689d5dd426a76e0bc077eb5ca20a",runtimeRevision:"0bcd822377da7b5718e674eaf9c870d349424dd1",templateSha256:"c3cf9e34abf4f9e36c2d72165aa9c132d3e2a725b6c2586aaa3a8af9d7a81041",contextWindow:480000 as const});
export interface QwenCountQualification { alias:string; modelRevision:string;runtimeRevision:string;templateSha256:string;contextWindow:number;instanceId:string; }
export function createCodexQwenCounter(verifyLane:(alias:string)=>Promise<QwenCountQualification>){
  return async(body:Readonly<Record<string,unknown>>,lane:GatewayUpstream,key:string,signal:AbortSignal):Promise<{inputTokens:number;contextWindow:480000}>=>{
    const verify=async()=>{const q=await verifyLane(lane.alias);if(!q.instanceId||q.alias!==lane.alias||q.modelRevision!==QWEN_CODEX_PIN.modelRevision||q.runtimeRevision!==QWEN_CODEX_PIN.runtimeRevision||q.templateSha256!==QWEN_CODEX_PIN.templateSha256||q.contextWindow!==480000)throw new ApiError(503,"codex_qwen_identity_unqualified","Qwen tokenizer/template/runtime allocation not qualified");return q;};
    const before=await verify();if(body.model!==lane.alias||body.reasoning_effort!=="none")throw new ApiError(400,"codex_qwen_profile","Expected explicit Qwen nonthinking profile");
    // Strip ONLY generation transport fields. Preserve history, tools, template,
    // sampling/output reservation and final served alias identically to inference.
    const countBody=Object.fromEntries(Object.entries(body).filter(([k])=>!["stream","stream_options"].includes(k)));
    const response=await fetch(lane.url.replace(/\/$/,"")+"/tokenize",{method:"POST",redirect:"error",headers:{authorization:`Bearer ${key}`,"content-type":"application/json"},body:JSON.stringify(countBody),signal:AbortSignal.any([signal,AbortSignal.timeout(15000)])});
    if(!response.ok||!response.body){await response.body?.cancel();throw new ApiError(503,"codex_qwen_count_unavailable","Qwen native token count unavailable");}
    const reader=response.body.getReader();let bytes=0;const chunks:Uint8Array[]=[];
    try{for(;;){const r=await reader.read();if(r.done)break;bytes+=r.value.byteLength;if(bytes>16*1024*1024)throw Error("Count response exceeds bound");chunks.push(r.value);}}finally{await reader.cancel().catch(()=>{});}
    let v:any;try{v=JSON.parse(Buffer.concat(chunks).toString("utf8"));}catch{throw new ApiError(503,"codex_qwen_count_invalid","Invalid native count");}
    if(!Number.isSafeInteger(v.max_model_len)||v.max_model_len<1||!Array.isArray(v.tokens)||!v.tokens.length||v.tokens.length>480000||!Number.isSafeInteger(v.count)||v.count!==v.tokens.length||v.tokens.some((n:unknown)=>!Number.isSafeInteger(n)||Number(n)<0||Number(n)>=2**31))throw new ApiError(503,"codex_qwen_count_invalid","Native token IDs/count unavailable");
    const after=await verify();if(after.instanceId!==before.instanceId)throw new ApiError(503,"codex_qwen_identity_changed","Qwen instance changed during count");
    return {inputTokens:v.count,contextWindow:480000};
  };
}
