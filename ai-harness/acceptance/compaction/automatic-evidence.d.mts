export function automaticMetadata(raw:any,threadId:string,turnId:string):any;
export function automaticFrames(frames:any[],threadId:string,turnId:string):any;
export function automaticThreshold(receipt:any,expected:any,metadata:any):AutomaticThresholdResult;
export function validateCollectorManifest(bytes:string):boolean;
/** Parsed source evidence only; never grants native automatic readiness. */
export interface AutomaticThresholdResult {status:'SOURCE_VALID'|'NOT_TESTED';nativeAcceptance?:'NOT_TESTED';schema?:'codex-native-trace-v1'|'codex-native-trace-v2';mode?:'post-sampling-token-usage-v1'|'post-sampling-token-usage-v2';errors?:string[];effectiveBudget?:number;startedAtMs?:number;startFrameSha256?:string;lineSha256?:string;totalUsageTokens?:number;phase?:string;autoCallNativeUtc?:string;autoCallSha256?:string;}
