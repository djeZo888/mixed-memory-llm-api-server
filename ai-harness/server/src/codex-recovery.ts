/** Ordinary host recovery composition. No generation, prompt replay, or default activation. */
import {CodexEngine,CODEX_PIN,type CodexRuntime} from "./codex-engine.js";
import type {Store} from "./store.js";import type {Files} from "./files.js";import type {Gateway} from "./gateway.js";import type {AppOptions} from "./app.js";import type {FreshParentRecoveryEvidence} from "./session-checkpoint.js";
export function createCodexRecoveryHost(host:{store:Store;files:Files;runtime:CodexRuntime;gateway:()=>Pick<Gateway,"issueToken"|"revokeToken"|"observeNoGeneration">|undefined;launcher:string;dispatchHeld:()=>boolean}):NonNullable<AppOptions["memoryRecoveryHost"]>{
 return async input=>{
  input.signal.throwIfAborted();
  const {store,files,runtime}=host,session=store.getSession(input.sessionId),g=host.gateway();
  if(!g?.observeNoGeneration||!runtime.nativeReceiptsRequired||!runtime.ordinaryMemoryAdmission||session.engineKind!=="codex"||session.engineVersion!==CODEX_PIN.version||session.modelPolicyVersion!==runtime.modelPolicyVersion||session.nativeState.ownership!=="idle"||session.nativeState.activeTurnId!==null||store.isQuarantined(session.workspaceId)||host.dispatchHeld())throw Error("Ordinary recovery owner is unavailable");
  if(!store.db.prepare("SELECT id FROM h041_session_checkpoints WHERE session_id=? AND id=? AND status='recovery_required'").get(input.sessionId,input.checkpointId)||!store.db.prepare("SELECT id FROM h041_checkpoint_recoveries WHERE session_id=? AND checkpoint_id=?").get(input.sessionId,input.checkpointId))throw Error("Exact human-acknowledged recovery required");
  if(store.db.prepare("SELECT id FROM runs WHERE workspace_id=? AND status IN ('queued','running','cancelling') LIMIT 1").get(session.workspaceId))throw Error("Workspace still has queued/active owner");
  store.assertWorkspaceRecovery(input.reservation,input.sessionId,input.checkpointId);let token:string|undefined;
  try{
   await files.prepare(input.sessionId,session.workspaceId);input.signal.throwIfAborted();const observed:Partial<FreshParentRecoveryEvidence>={};token=g.issueToken(input.sessionId,"codex");
   const result=await g.observeNoGeneration(input.sessionId,async()=>{
    // Construction belongs inside token lifetime: even a constructor fault revokes it.
    const engine=new CodexEngine({sessionId:input.sessionId,engineKind:session.engineKind,engineVersion:session.engineVersion,modelPolicyVersion:session.modelPolicyVersion,nativeState:structuredClone(session.nativeState),profileDir:files.profile(input.sessionId),workspace:files.workspace(session.workspaceId),launcher:host.launcher,gatewayUrl:runtime.gatewayUrl,gatewayToken:token!,stderrPath:files.log(input.sessionId),sessionMemory:input.memory,dispatchHeld:host.dispatchHeld,onNativeSessionId:()=>{},onNativeState:state=>store.setNativeState(input.sessionId,"codex",state),onUpdate:()=>{},onNativeLifecycle:event=>{if(["launch","thread","settlement","gateway_settled"].includes(event.kind))Object.assign(observed,{[event.kind==="gateway_settled"?"gateway":event.kind]:event});}},runtime);
    const abort=()=>{void engine.close().catch(()=>store.quarantine(session.workspaceId,"Recovery abort cleanup unknown"));};input.signal.addEventListener("abort",abort,{once:true});
    try{input.signal.throwIfAborted();await engine.start();input.signal.throwIfAborted();await engine.close();}catch(error){try{await engine.close();}catch{store.quarantine(session.workspaceId,"Fresh recovery cleanup unknown");}throw error;}finally{input.signal.removeEventListener("abort",abort);}return observed;
   });
   if(!result.value.launch||!result.value.thread||!result.value.settlement||!result.value.gateway)throw Error("Fresh recovery lifecycle observations incomplete");
   return {...result.value,noGeneration:result.proof} as FreshParentRecoveryEvidence;
  }finally{if(token!==undefined)g.revokeToken(token);}
 };
}
