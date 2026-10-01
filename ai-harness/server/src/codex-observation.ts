/** Opaque host observation. Plain callback JSON cannot mint protected native evidence. */
import {codexReceiptProvenance,getCodexReceiptUtf8,isHistoricalCodexReceipt,type CodexNativeLaunchReceipt,type CodexNativeSettlementReceipt} from "./codex-receipts.js";
export type CodexLifecycleEvent =
 {kind:"launch";receipt:CodexNativeLaunchReceipt}|{kind:"settlement";receipt:CodexNativeSettlementReceipt}|
 {kind:"thread";threadId:string;rolloutPath:string|null;method:"thread/start"|"thread/resume"}|
 {kind:"gateway_settled";threadId:string|null;activeTurnId:string|null;lastSettledTurnId?:string|null}|
 {kind:"compaction";threadId:string;turnId:string;compactionId:string;status:"start"|"completed"|"failed"}|
 {kind:"checkpoint_artifact";checkpointId:string;threadId:string;turnId:string;callId:string;name:string;artifactId:string;sha256:string};
export type CodexNativeObservation=CodexLifecycleEvent & {readonly observation:"genuine-host-observation"};
const observations=new WeakMap<CodexNativeObservation,CodexNativeLaunchReceipt>();
export function observeCodexLifecycle(event:CodexLifecycleEvent,launch:CodexNativeLaunchReceipt):CodexNativeObservation {
 if(!codexReceiptProvenance(launch)||!getCodexReceiptUtf8(launch)||isHistoricalCodexReceipt(launch))throw Error("Observation lacks genuine current native launch");
 if(event.kind==="settlement"&&(!getCodexReceiptUtf8(event.receipt)||event.receipt.nonce!==launch.nonce||event.receipt.containerId!==launch.container.id))throw Error("Observation settlement mismatch");
 const observation=Object.freeze({...event,observation:"genuine-host-observation" as const});observations.set(observation,launch);return observation;
}
export function validateCodexObservation(observation:CodexNativeObservation,sessionId:string){const launch=observations.get(observation);if(!launch||launch.sessionId!==sessionId)throw Error("Untrusted serialized native observation");return launch;}
