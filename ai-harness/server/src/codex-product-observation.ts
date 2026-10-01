/** Trusted normal-entry observer composition; cannot replace policy/counter/launcher. */
import type {CodexHostQualification} from "./codex-host.js";
import type {CodexOrdinaryEntry} from "./codex-ordinary-entry.js";
import type {CodexRecoveryObservers} from "./codex-recovery-observation.js";
import type {NativeReplacementCommitVerifier} from "./broker.js";
import type {QualificationTaskAdmission} from './qualification-task-admission.js';
export interface CodexProductObservers extends CodexRecoveryObservers, Pick<CodexHostQualification,"observations"|"onNativeLaunchReceipt"|"onNativeSettlementReceipt"|"onNativeThread"|"beforeNativeAction"|"onNativeChildObserved"|"onNativeOperation"|"nativeTraceMode"|"onNativeTraceReceipt"> {
 beforeNativeReplacementCommit?:NativeReplacementCommitVerifier;
 taskAdmission?:QualificationTaskAdmission;
}
export function composeCodexProductObservers(base:CodexHostQualification,ordinary:CodexOrdinaryEntry|undefined,observer:CodexProductObservers={}):CodexHostQualification {
 const result={...base,...(ordinary?{nativeReceiptPolicy:ordinary.nativeReceiptPolicy,...ordinary.hooks}:{})};
 if(observer.nativeTraceMode!==undefined&&observer.nativeTraceMode!=="post-sampling-token-usage-v1")throw Error("Fixed trusted native trace mode required");
 result.nativeTraceMode=observer.nativeTraceMode??base.nativeTraceMode;
 result.observations=observer.observations??base.observations;
 for(const key of ["onNativeThread","beforeNativeAction"] as const){const prior=result[key],next=observer[key];if(next)result[key]=async(input:any)=>{await prior?.(input);await next(input);};}
 for(const key of ["onNativeLaunchReceipt","onNativeSettlementReceipt","onNativeChildObserved","onNativeOperation","onNativeTraceReceipt"] as const){const prior=result[key],next=observer[key];if(next)result[key]=(input:any)=>{prior?.(input);next(input);};}
 // Existing operational/metadata authority comes only from the qualified ordinary entry.
 return result;
}
