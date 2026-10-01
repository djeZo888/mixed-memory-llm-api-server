/** Trusted negative qualification seam. It can reject once, never grant continuity/permissions. */
import type {NativeReplacementCommitInput,NativeReplacementCommitVerifier} from "./broker.js";
export function createCodexReplacementRejection(scope:{sessionId:string;runId:string;checkpointId:string}):NativeReplacementCommitVerifier {
 const owned=Object.freeze({...scope});let consumed=false;
 for(const value of Object.values(owned))if(typeof value!=="string"||!value||value.length>128)throw Error("Exact replacement rejection scope required");
 return async(input:NativeReplacementCommitInput)=>{
  if(input.sessionId!==owned.sessionId||input.runId!==owned.runId||input.checkpoint.id!==owned.checkpointId)return;
  if(consumed)throw Error("Replacement verification rejection already consumed");
  if(input.checkpoint.compactions.some(c=>c.status==="completed")){consumed=true;throw Error("Owned replacement verification rejected");}
 };
}
