/** Host gateway ledger observation; not a caller-supplied no-generation boolean. */
import type {RequestOwnership} from "./gateway-ownership.js";
import type {CodexNativeLaunchReceipt,CodexNativeSettlementReceipt} from "./codex-receipts.js";
export interface GatewayNoGenerationProof {readonly sessionId:string;readonly startedAtMs:number;readonly endedAtMs:number}
const proofs=new WeakSet<GatewayNoGenerationProof>();
export async function observeGatewayNoGeneration<T>(sessionId:string,snapshot:()=>RequestOwnership[],work:()=>Promise<T>):Promise<{value:T;proof:GatewayNoGenerationProof}> {
 const before=snapshot();if(before.some(r=>r.sessionId!==sessionId||r.state!=="settled"))throw Error("Prior gateway work remains unsettled");
 const startedAtMs=Date.now(),value=await work(),after=snapshot();
 if(after.some(r=>r.sessionId!==sessionId||r.state!=="settled")||JSON.stringify(before.map(r=>r.id).sort())!==JSON.stringify(after.map(r=>r.id).sort()))throw Error("Provider operation occurred during no-generation recovery");
 const proof=Object.freeze({sessionId,startedAtMs,endedAtMs:Date.now()});proofs.add(proof);return {value,proof};
}
export function validateGatewayNoGeneration(proof:GatewayNoGenerationProof,sessionId:string,launch:CodexNativeLaunchReceipt,settlement:CodexNativeSettlementReceipt){
 if(!proofs.has(proof)||proof.sessionId!==sessionId||launch.checkedAtMs<proof.startedAtMs||settlement.checkedAtMs>proof.endedAtMs||settlement.checkedAtMs<launch.checkedAtMs)throw Error("Fresh parent lacks actual bounded gateway no-generation observation");
}
