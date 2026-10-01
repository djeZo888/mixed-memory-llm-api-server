import { randomUUID } from 'node:crypto';
import { join } from 'node:path';
import { OwnedApplicationRunner,type RunnerInput } from './process-runner.js';
import { durableFile } from './checkpoint.js';
import { sha256,stableJson } from './projection.js';
import { isQualifiedEntry,STAGE_CAPABILITIES,FULL_CAPABILITIES,type EntryQualification } from './qualification.js';
/** Parent owns oracle/checkpoints/baselines; child owns the entire temporary app.
 * Accepted artifact baselines never come from after-restart bytes. */
export function applicationProxy(input:RunnerInput,qualification:EntryQualification) {
  const runner=new OwnedApplicationRunner(input),observedSettlements:any[]=[];
  let ready=false,started=false,runId:string|undefined,session:any;
  const invoke=async(method:string,args:any={})=>{
    if(!ready)throw Error('actual_worker_capability_qualification_required');
    if(!started){await runner.start(args.signal);started=true;}
    const {signal,...wire}=args;
    const result=await runner.call(method,wire,signal);
    const extra=result?.ownedSettlements??[];
    for(const receipt of [...extra,...(result?.settlement?.state==='released'&&result.actionId&&result.nativeThreadId&&result.nativeTurnId?[{actionId:result.actionId,nativeThreadId:result.nativeThreadId,nativeTurnId:result.nativeTurnId,settlementReceiptSha256:result.settlement.receiptSha256}]:[])]) {
      if(observedSettlements.some(s=>s.actionId===receipt.actionId))throw Error('owned_proxy_duplicate_action');observedSettlements.push(receipt);
    }
    return result;
  };
  const restart=async(args:any)=>{
    if(!started||!runId||args.session?.sessionId!==session?.sessionId)throw Error('owned_application_parent_required');
    const startedAt=new Date().toISOString();
    const baseline=structuredClone(args.acceptedContinuation),checkpoint=structuredClone(args.checkpoint);
    const resumed=await runner.restart({checkpoint,acceptedContinuation:baseline,runId,actionId:args.actionId,windowId:input.review.authorization.windowId,observedSettlements:structuredClone(observedSettlements)},args.signal);
    const process=JSON.parse(resumed.processRestartReceiptUtf8),afterState=JSON.parse(resumed.parentState.receiptUtf8);
    const beforeHostId=resumed.beforeHostId,afterHostId=resumed.afterHostId;
    if(!beforeHostId||!afterHostId||beforeHostId===afterHostId||afterState.stateSha256!==checkpoint.stateSha256)throw Error('actual_restarted_host_state_capture_required');
    const restartReceiptUtf8=stableJson({source:'native-owned-host-cold-resume',format:'h041-actual-process-restart-v1',runId,actionId:args.actionId,windowId:input.review.authorization.windowId,nativeThreadId:checkpoint.nativeThreadId,checkpointStateSha256:checkpoint.stateSha256,beforeHostId,afterHostId,beforeApplicationProcessId:resumed.beforeProcessId,afterApplicationProcessId:resumed.afterProcessId,oldApplicationExitConfirmed:process.oldExit.code===0&&process.oldExit.signal===null,oldGatewaySettled:true,noActionReplay:resumed.replayedActionIds.length===0,capturedAfterRestart:true,processRestartReceiptUtf8:resumed.processRestartReceiptUtf8,processRestartReceiptSha256:resumed.processRestartReceiptSha256,afterParentStateReceiptUtf8:resumed.parentState.receiptUtf8,afterParentStateReceiptSha256:resumed.parentState.receiptSha256,...(baseline?{acceptedContinuationActionId:baseline.actionId,acceptedArtifactHashes:baseline.artifactHashes}: {})});
    const restartEvidence={capturedBy:'host',nativeThreadId:checkpoint.nativeThreadId,beforeProcessId:resumed.beforeProcessId,afterProcessId:resumed.afterProcessId,beforeStateSha256:checkpoint.stateSha256,afterStateUtf8:resumed.afterStateUtf8,replayedActionIds:resumed.replayedActionIds,restartReceiptUtf8,restartReceiptSha256:sha256(restartReceiptUtf8),receiptSha256:sha256(restartReceiptUtf8)};
    await durableFile(join(input.hostPrivate,`${randomUUID()}-restart-lifecycle.json`),restartReceiptUtf8);
    return {resumed,restartEvidence,baseline,checkpoint,startedAt};
  };
  const approvedCapabilities=[...(qualification.profile==='h041-full-retention-v1'?FULL_CAPABILITIES:STAGE_CAPABILITIES)];
  return {interfaceVersion:'h039-compaction-adapter-v1',kind:'native',get enabled(){return ready;},get capabilities(){return ready?[...approvedCapabilities]:[];},
    qualifyWorker:async()=>{
      if(!isQualifiedEntry(qualification))throw Error('genuine_entry_qualification_required');
      if(ready||started)throw Error('owned_worker_qualification_duplicate');
      try{await runner.start();started=true;const actual=await runner.call('qualification');
        if(actual?.enabled!==true||actual.profile!==qualification.profile||actual.qualificationSha256!==qualification.qualificationSha256||stableJson(actual.capabilities)!==stableJson(approvedCapabilities))throw Error('actual_supported_worker_capabilities_required');
        ready=true;
      }catch(error){if(started)await runner.shutdownAndConfirm().catch(()=>undefined);throw error;}
    },
    runtime:async()=>({name:'codex',...qualification.runtime,promptRevision:'kpm-technical-v1'}),
    open:async(args:any)=>{runId=args.runId;session=await invoke('open',args);return session;},
    append:(args:any)=>invoke('append',args),originals:(args:any)=>invoke('originals',args),compact:(args:any)=>invoke('compact',args),probe:(args:any)=>invoke('probe',args),continue:(args:any)=>invoke('continue',args),childContext:(args:any)=>invoke('childContext',args),cleanChild:(args:any)=>invoke('childContext',args),
    coldResume:async(args:any)=>{const {restartEvidence}=await restart(args);const result=await invoke('probe',{...args,runId,mode:'summary-only',contextSha256:args.checkpoint.stateSha256});return {...result,restartEvidence};},
    resumeAcceptedContinuation:async(args:any)=>{
      const {restartEvidence,baseline,checkpoint,resumed,startedAt}=await restart(args);
      const capture=await invoke('captureAcceptedArtifacts',{acceptedContinuation:baseline,checkpoint,signal:args.signal});
      const artifactReceiptUtf8=stableJson({source:'native-owned-workspace-artifacts',runId,sessionId:session.sessionId,actionId:args.actionId,windowId:input.review.authorization.windowId,nativeThreadId:checkpoint.nativeThreadId,afterHostId:resumed.afterHostId,acceptedArtifactReceiptSha256:baseline.artifactBaseline.artifactReceiptSha256,acceptedArtifactReceiptBytes:baseline.artifactBaseline.artifactReceiptBytes,acceptedStoreRunId:baseline.artifactBaseline.storeRunId,acceptedContinuationActionId:baseline.actionId,checkpointStateSha256:checkpoint.stateSha256,captureId:randomUUID(),artifactUtf8:capture.artifactUtf8});
      await durableFile(join(input.hostPrivate,`${randomUUID()}-restarted-artifacts.json`),artifactReceiptUtf8);
      // This is a no-generation restart observation, not a fabricated native turn.
      const durationReceiptUtf8=stableJson({source:'host-application-restart-operation-observation',startedAt,completedAt:new Date().toISOString(),restartReceiptSha256:restartEvidence.receiptSha256,artifactReceiptSha256:sha256(artifactReceiptUtf8)});
      await durableFile(join(input.hostPrivate,`${randomUUID()}-restart-duration.json`),durationReceiptUtf8);
      return {outcome:'completed',durationMs:{state:'measured',value:Date.parse(JSON.parse(durationReceiptUtf8).completedAt)-Date.parse(startedAt),source:'host-application-restart-operation-observation',receiptSha256:sha256(durationReceiptUtf8),reason:null},actionId:args.actionId,nativeThreadId:checkpoint.nativeThreadId,nativeTurnId:null,restartEvidence,artifacts:capture.artifacts,artifactReceiptUtf8,artifactReceiptSha256:sha256(artifactReceiptUtf8),parentState:capture.parentState,settlement:{state:'released',receiptSha256:restartEvidence.receiptSha256,automaticReplay:false}};
    },
    close:async(args:any)=>{if(!started)throw Error('actual_owned_application_absent');try{return await invoke('close',args);}finally{const exit=await runner.shutdownAndConfirm();if(exit.code!==0||exit.signal!==null)throw Error('actual_owned_application_exit_failed');}}
  };
}
