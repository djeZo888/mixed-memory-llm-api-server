/** Opt-in trusted host capture. Raw bodies stay outside logs/model mounts.
 * These observations grant no runtime, permission, ownership or native qualification. */
import {createHash} from "node:crypto";
import type {OwnedCodexProcess,CodexLaunchInput} from "./codex-launcher.js";
import type {QwenAdmissionContext} from "./codex-admission.js";
export interface CodexVerifiedCountObservation {
 readonly body:Readonly<Record<string,unknown>>;
 readonly context:Readonly<QwenAdmissionContext>;
 readonly lane:string;
 readonly result:Readonly<{inputTokens:number;contextWindow:480000}>;
 readonly bodySha256:string;
}
export interface CodexRawProcessObservation {
 readonly sessionId:string;
 /** Actual retained owned process; this reference/sequence is not native proof. */
 readonly process:OwnedCodexProcess;
 readonly direction:"input"|"output";
 readonly sequence:number;
 readonly bytes:Buffer;
 readonly sha256:string;
}
export interface CodexHostObservations {
 /** Synchronous bounded capture. Promise return/throw fails closed. Never mutate producer streams. */
 onRawNative?(event:CodexRawProcessObservation):void;
 onNativeProcess?(event:{readonly sessionId:string;readonly process:OwnedCodexProcess}):void;
 /** Awaited after native count and full instance bracket verify, before inference admission. */
 onVerifiedCount?(event:CodexVerifiedCountObservation,signal:AbortSignal):void|Promise<void>;
 maxRawBytesPerProcess?:number;
 maxCountBodyBytes?:number;
}
const digest=(b:Uint8Array|string)=>createHash("sha256").update(b).digest("hex");
export function observeOwnedCodexProcess(process:OwnedCodexProcess,input:Pick<CodexLaunchInput,"sessionId">,observer:CodexHostObservations):OwnedCodexProcess {
 const max=observer.maxRawBytesPerProcess??64*1024*1024;
 if(!Number.isSafeInteger(max)||max<1||max>64*1024*1024)throw Error("Invalid native observation bound");
 let bytes=0,sequence=0,failure:Error|undefined,reject!:(error:Error)=>void;
 const observationFailure=new Promise<never>((_,no)=>{reject=no;});void observationFailure.catch(()=>undefined);
 const fail=()=>{if(!failure){failure=new Error("Trusted native observation failed");reject(failure);void process.terminateAndConfirm().catch(()=>undefined);}return failure;};
 const synchronous=(call:()=>unknown)=>{try{const value=call();if(value&&typeof (value as Promise<unknown>).then==="function"){void Promise.resolve(value).catch(()=>undefined);throw Error("Non-synchronous native observer");}}catch{throw fail();}};
 const capture=(direction:"input"|"output",chunk:unknown,encoding?:BufferEncoding)=>{
  if(failure)throw failure;
  if(direction==="output"&&!Buffer.isBuffer(chunk))throw fail();
  const raw=typeof chunk==="string"?Buffer.from(chunk,encoding):Buffer.isBuffer(chunk)||chunk instanceof Uint8Array?Buffer.from(chunk):undefined;
  if(!raw||raw.length>1024*1024||(bytes+=raw.length)>max)throw fail();
  synchronous(()=>observer.onRawNative?.(Object.freeze({sessionId:input.sessionId,process,direction,sequence:++sequence,bytes:raw,sha256:digest(raw)})));
 };
 // Intercept actual writes/raw pushes without a data listener: no early flow or lost ACK bytes.
 const write=process.stdin.write;
 process.stdin.write=function(chunk:any,encoding?:BufferEncoding|((error?:Error|null)=>void),callback?:(error?:Error|null)=>void){capture("input",chunk,typeof encoding==="string"?encoding:undefined);const bound=write.bind(this);return typeof encoding==="string"?bound(chunk,encoding,callback):bound(chunk,encoding);};
 const push=process.stdout.push;
 process.stdout.push=function(chunk:any,encoding?:BufferEncoding){if(chunk!==null)try{capture("output",chunk);}catch{return false;}return push.call(this,chunk,encoding);};
 process.observationFailure=observationFailure;
 try{synchronous(()=>observer.onNativeProcess?.(Object.freeze({sessionId:input.sessionId,process})));}catch{throw fail();}
 return process;
}
export function immutableCountObservation(bodyUtf8:string,context:QwenAdmissionContext,lane:string,result:{inputTokens:number;contextWindow:480000}):CodexVerifiedCountObservation {
 const freeze=(value:any):any=>{if(value&&typeof value==="object"){for(const v of Object.values(value))freeze(v);Object.freeze(value);}return value;};
 return Object.freeze({body:freeze(JSON.parse(bodyUtf8)),context:Object.freeze({...context}),lane,result:Object.freeze({...result}),bodySha256:digest(bodyUtf8)});
}
