/** Host gateway ledger observation; not a caller-supplied no-generation boolean. */
import type {GatewayAdmissionObservation} from "./gateway-ownership.js";
import type {CodexNativeLaunchReceipt,CodexNativeSettlementReceipt} from "./codex-receipts.js";
export interface GatewayNoGenerationProof {readonly sessionId:string;readonly startedAtMs:number;readonly endedAtMs:number;readonly ownerId:string;readonly admissionSequence:number}
const proofs=new WeakSet<GatewayNoGenerationProof>();
export async function observeGatewayNoGeneration<T>(sessionId:string,snapshot:()=>GatewayAdmissionObservation,work:()=>Promise<T>):Promise<{value:T;proof:GatewayNoGenerationProof}> {
 const before=snapshot();if(before.sessionId!==sessionId||!before.ready||!before.settled)throw Error("Prior gateway work remains unsettled");
 const startedAtMs=Date.now(),value=await work(),after=snapshot();
 if(after.sessionId!==sessionId||!after.ready||!after.settled||before.ownerId!==after.ownerId||before.sequence!==after.sequence)throw Error("Provider operation occurred during no-generation recovery");
 const proof=Object.freeze({sessionId,startedAtMs,endedAtMs:Date.now(),ownerId:before.ownerId,admissionSequence:before.sequence});proofs.add(proof);return {value,proof};
}
export function validateGatewayNoGeneration(proof:GatewayNoGenerationProof,sessionId:string,launch:CodexNativeLaunchReceipt,settlement:CodexNativeSettlementReceipt){
 if(!proofs.has(proof)||proof.sessionId!==sessionId||launch.checkedAtMs<proof.startedAtMs||settlement.checkedAtMs>proof.endedAtMs||settlement.checkedAtMs<launch.checkedAtMs)throw Error("Fresh parent lacks actual bounded gateway no-generation observation");
}
