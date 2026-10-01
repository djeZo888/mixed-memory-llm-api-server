/** Trusted normal-product recovery seams. No request/model fields enable these hooks. */
import type {FreshParentRecoveryEvidence} from "./session-checkpoint.js";
export interface CodexRecoveryScope {readonly sessionId:string;readonly checkpointId:string}
export interface CodexRecoveryObservers {
 onNativeRecoveryObserved?:(input:CodexRecoveryScope & {readonly evidence:Readonly<FreshParentRecoveryEvidence>},signal:AbortSignal)=>void|Promise<void>;
 beforeNativeRecovery?:(input:CodexRecoveryScope & {readonly stage:"before-launch"|"before-commit"},signal:AbortSignal)=>void|Promise<void>;
}
/** The observer receives a live abort signal, and cannot hold an owner indefinitely. */
export async function boundedRecoveryObservation(signal:AbortSignal,work:(signal:AbortSignal)=>void|Promise<void>):Promise<void>{
 signal.throwIfAborted();const child=new AbortController();let reject!: (error:unknown)=>void;
 const interrupted=new Promise<never>((_,r)=>{reject=r;});
 const abort=()=>{child.abort(signal.reason);reject(signal.reason??Error("Recovery observation aborted"));};
 signal.addEventListener("abort",abort,{once:true});
 const timer=setTimeout(()=>{const error=Error("Trusted recovery observation timed out");child.abort(error);reject(error);},5000);
 try {await Promise.race([Promise.resolve().then(()=>work(child.signal)),interrupted]);signal.throwIfAborted();child.signal.throwIfAborted();}
 finally {clearTimeout(timer);signal.removeEventListener("abort",abort);child.abort(Error("Recovery observation settled"));}
}
