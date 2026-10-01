export type NativeTraceMode='off'|'post-sampling-token-usage-v1'|'post-sampling-token-usage-v2';
export type NativeTraceSchema=null|'codex-native-trace-v1'|'codex-native-trace-v2';
export interface RetainedTraceEvidence {status:'SOURCE_VALID';nativeAcceptance:'NOT_TESTED';schema:Exclude<NativeTraceSchema,null>;mode:Exclude<NativeTraceMode,'off'>;selectedMode:Exclude<NativeTraceMode,'off'>;lines:any[];autoCalls:any[];producer:{launchNonce:string;processId:string};receiptSha256:string;}
export function traceSchemaForMode(mode:NativeTraceMode):NativeTraceSchema;
export function verifyTraceSchemaMode(schema:NativeTraceSchema,mode:NativeTraceMode):{schema:NativeTraceSchema;mode:NativeTraceMode};
export function nativeTimestampNs(value:string):bigint;
export function nativeCompactionStart(frame:any,threadId:string,turnId:string):{itemId:string;startedAtMs:number;nativeNs:bigint;frameSha256:string};
export function parsePostSamplingTrace(lineUtf8:string):any;
export function verifyPostSamplingGate(lineUtf8:string,phase?:string):any;
export function verifyTraceCausalJoin(input:any):any;
export function verifyRetainedTrace(packet:any,expected:any):RetainedTraceEvidence;
export function parseAutoCallTrace(lineUtf8:string):any;
export interface OriginalTraceLine {lineUtf8:string;stderrSequence:number;lineSha256?:string;}
export type NativeStartedAtTraceJoinInput = {
 startFrame:any;metadata:any;operation:any;gateway:any;producer:{launchNonce:string;processId:string};resolvedConfig:any;lines:OriginalTraceLine[];
} & ({schema:'codex-native-trace-v2';mode:'post-sampling-token-usage-v2';autoCalls:OriginalTraceLine[]}|{schema:'codex-native-trace-v1';mode:'post-sampling-token-usage-v1';autoCalls?:OriginalTraceLine[]});
export interface NativeStartedAtTraceJoinEvidence {status:'SOURCE_VALID';nativeAcceptance:'NOT_TESTED';schema:Exclude<NativeTraceSchema,null>;mode:Exclude<NativeTraceMode,'off'>;lineSha256:string;totalUsageTokens:number;phase:'mid_turn';startedAtMs:number;startFrameSha256:string;autoCallNativeUtc?:string;autoCallSha256?:string;}
export function verifyNativeStartedAtTraceJoin(input:NativeStartedAtTraceJoinInput):NativeStartedAtTraceJoinEvidence;
