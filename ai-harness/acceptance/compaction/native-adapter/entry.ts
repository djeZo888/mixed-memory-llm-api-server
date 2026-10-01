/** Root-owned private entry loader. Import has no launch, socket or credential side effect. */
import { createCodexTextOnlyPolicy, createCodexParentArtifactScope, type CodexTextOnlyPolicy } from '../../../server/src/codex-probe.js';
import { getCodexReceiptUtf8 } from '../../../server/src/codex-receipts.js';
import * as probeApi from '../../../server/src/codex-probe.js';
import * as receiptApi from '../../../server/src/codex-receipts.js';
import {selectPolicyFactories} from './policy-selection.js';
import {DelegatedChildProducer} from './delegated-child.js';
import {carrierForConfig} from './carrier-admission.js';
import {isQualificationTaskAdmission,type QualificationTaskAdmission} from '../../../server/src/qualification-task-admission.js';
import {selectRestartCheckpoint} from './restart-selection.js';
import { mkdir } from 'node:fs/promises';
import { join } from 'node:path';
import { randomUUID,randomBytes } from 'node:crypto';
import { durableFile,privateFile } from './checkpoint.js';
import { sha256, stableJson, reviewSnapshot } from './projection.js';
import { createNativeAdapter, createQualifiedNativeAdapter, type AdapterInput } from './adapter.js';
import { qualifyEntry } from './qualification.js';
import type { BootstrapHooks } from './bootstrap.js';
import type { CodexHostQualification } from '../../../server/src/codex-host.js';
import { createArtifactSink } from './artifact-sink.js';
export async function loadReviewedLocalEntry(configPath: string,restart?:import('./restart.js').RestartTicket) {
  const config = JSON.parse((await privateFile(configPath)).toString('utf8'));
  if (stableJson(config.bootstrap) !== stableJson(config.adapterInput?.bootstrap)) throw Error('entry_and_adapter_bootstrap_tuple_must_match');
  const qualified = await qualifyEntry(config,restart);
  const carrier=config.carrier?await carrierForConfig(configPath):undefined;
  const task=config.bootstrap.review.authorization.task;
  const selected=selectPolicyFactories(probeApi,task,qualified.profile==='h041-full-retention-v1'),factory=selected.factory;
  if(typeof factory!=='function')throw Error('separately_branded_frozen_authority_policy_unavailable');
  const handoffApi=qualified.profile==='h041-full-retention-v1'?await import(new URL('../../../server/src/codex-policy-handoff.js',import.meta.url).href):undefined;
  if(handoffApi&&(!handoffApi.retainCodexPolicyHandoff||!handoffApi.adoptCodexPolicyHandoff))throw Error('actual_sealed_A_durable_handoff_exports_required');
  const delegated=new DelegatedChildProducer();
  const policies = new Map<string,CodexTextOnlyPolicy>();
  let sink: ReturnType<typeof createArtifactSink> | undefined;
  const hooks: BootstrapHooks = {
    qualification: qualified,
    carrier,
    delegatedChild:input=>delegated.run({...input,review:config.bootstrap.review,parentPrefix:config.adapterInput.parentProjectionSpec.prefixInput}),
    evidence: { receiptUtf8: getCodexReceiptUtf8 },
    retainPolicy: async input=>{
      if(!handoffApi)throw Error('durable_policy_handoff_unavailable');
      const keyPath=config.policyHandoffKeyPath,directory=join(input.hostPrivate,`policy-handoff-${randomUUID()}`);if(typeof keyPath!=='string')throw Error('root_provisioned_private_handoff_key_required');await mkdir(directory,{mode:0o700});
      const store=input.application.store,selected=selectRestartCheckpoint(store,input.sessionId,input.nativeThreadId,input.expectedCheckpoint,input.acceptedContinuation);
      const {checkpointId,purpose,storeRunId}=selected,ownership=store.checkpoints.issueRestartOwnership({sessionId:input.sessionId,runId:storeRunId,checkpointId,threadId:input.nativeThreadId,purpose});
      const handoff=await handoffApi.retainCodexPolicyHandoff({policy:policies.get(input.sessionId),checkpointId,directory,keyPath,sourceClosure:config.bootstrap.review.files,ownership,purpose});
      return {...handoff,storeRunId,purpose};
    },
    adoptPolicy: async input=>{
      if(!handoffApi)throw Error('durable_policy_adoption_unavailable');
      const ownership=input.application.store.checkpoints.issueRestartOwnership({sessionId:input.sessionId,runId:input.handoff.storeRunId,checkpointId:input.handoff.checkpointId,threadId:input.nativeThreadId,purpose:input.handoff.purpose});
      const policy=await handoffApi.adoptCodexPolicyHandoff({ownership,purpose:input.handoff.purpose,authorization:selected.adoptionAuthorization,path:input.handoff.path,sha256:input.handoff.sha256,keyPath:config.policyHandoffKeyPath,sessionId:input.sessionId,threadId:input.nativeThreadId,checkpointId:input.handoff.checkpointId,runId:randomUUID(),configSha256:config.bootstrap.review.mountedConfigSha256,modelCatalogSha256:config.bootstrap.review.modelCatalogSha256,sourceClosure:config.bootstrap.review.files});policies.set(input.sessionId,policy);
    },
    configureHost(base, context) {
      const extra: CodexHostQualification = {
        ...base, nativeReceiptPolicy: {linuxTransportQualified:true,sourceSha256:qualified.receiptSources},
        textOnlyPolicy: (sessionId: string) => {
          if (policies.has(sessionId)) return policies.get(sessionId);
          const scope = context.guard.activeScope(sessionId);
          const mode = scope?.mode === 'durable-retrieval' ? 'read-original' : ['summary-only','clean-child'].includes(scope?.mode ?? '') ? 'summary-only' : qualified.profile === 'h041-full-retention-v1' ? 'parent-artifacts' : 'text-only-parent';
          const fields={sessionId,runId:scope?.mode === 'durable-retrieval' ? scope.runId : config.bootstrap.review.authorization.windowId,mode,configSha256:config.bootstrap.review.mountedConfigSha256,modelCatalogSha256:config.bootstrap.review.modelCatalogSha256};
          const policy=mode==='parent-artifacts'?selected.parentFactory!({...fields,collaborationVersion:config.bootstrap.review.retentionParentPolicy?.collaborationVersion}):factory(fields);
          policies.set(sessionId,policy); return policy;
        },
        authorizeNativeTurn: async ({policy,launchReceipt,threadId,params,method}) => {
          const scope = context.guard.activeScope(policy.sessionId);
          if (!scope || !getCodexReceiptUtf8(launchReceipt) || params.threadId !== threadId || launchReceipt.runId !== policy.runId || scope.signal.aborted || Date.now() >= scope.expiresAt ||
              (method === 'thread/compact/start' ? Object.keys(params).join() !== 'threadId' : typeof (params.input as any)?.[0]?.text !== 'string')) throw Error('actual_native_turn_scope_required');
        },
        ...(qualified.profile === 'h041-full-retention-v1' ? {
          nativeDelegationQualified:true,
          onNativeThread:delegated.observe,beforeNativeAction:delegated.arm,
          retentionTurnKind:sessionId=>{const scope=context.guard.activeScope(sessionId);if(!scope)return 'summary';return scope.purpose==='child'?'child':scope.purpose==='continuation'?'artifacts':'summary';},
          parentArtifactScope: (sessionId: string) => {
            if(!['parent-artifacts','retention-parent'].includes(policies.get(sessionId)?.mode??''))return undefined;
            const actual=context.application(),active=context.guard.activeScope(sessionId);
            const checkpoint=active&&actual&&(actual.store as any).checkpoints?.status(sessionId).filter((c:any)=>c.runId===active.runId).at(-1);
            if(active&&!checkpoint?.id)throw Error('actual_parent_artifact_store_checkpoint_required');
            return createCodexParentArtifactScope({sessionId,runId:policies.get(sessionId)?.runId??config.bootstrap.review.authorization.windowId,checkpointId:checkpoint?.id??sessionId,names:['sensor-policy.json','engineering-calculation.json'],maxBytes:65536});
          },
          registerCheckpointArtifact: async (input,signal) => {
            const app = context.application(), scope = context.guard.activeScope(input.scope.sessionId);
            if (!app || (scope?.mode !== 'parent-artifacts' || scope.purpose !== 'continuation') || !getCodexReceiptUtf8(input.launchReceipt)) throw Error('artifact_policy_not_owned');
            sink ??= createArtifactSink(app.store,app.files);
            const result = await sink({sessionId:input.scope.sessionId,runId:scope.runId,threadId:input.threadId,turnId:input.turnId,callId:input.callId,name:input.name,jsonUtf8:input.jsonUtf8},signal);
            return {artifactId:result.artifactId,sha256:result.sha256};
          },
          onCheckpointArtifactSettled: input => context.artifactSettlements.push(input),
          readOriginalProbe: sessionId => context.originalProbes.get(sessionId),
          authorizeOriginalRead: async ({policy,launchReceipt,threadId,turnId,probe},signal) => {
            const capture = context.guard.firstReceipt(policy.sessionId);
            if (signal.aborted || context.originalProbes.get(policy.sessionId) !== probe || !getCodexReceiptUtf8(launchReceipt) || capture.nativeThreadId !== threadId || capture.nativeTurnId !== turnId || !(capture as any).scopeReceiptSha256) throw Error('actual_scoped_original_read_not_admitted');
          },
          onOriginalReadSettled: input => context.originalSettlements.push(input),
        } : {}),
      };
      // New fields must be consumed by A's actual runtime; bootstrap checks the
      // policy function on the resulting runtime, so ignored options fail closed.
      (context.guard as any).delegatedFollowup=(sessionId:string,input:unknown,prefix:unknown[])=>delegated.followup(sessionId,input,prefix);
      return extra;
    },
  };
  return createQualifiedNativeAdapter(reviewSnapshot(config.adapterInput as AdapterInput),hooks);
}
export async function loadReviewedEntry(configPath:string) {
  const config=JSON.parse((await privateFile(configPath)).toString('utf8')),qualification=await qualifyEntry(config);
  const {canonicalDirectory}=await import('./checkpoint.js');await canonicalDirectory(config.runnerPrivate);
  const workerPath=new URL('./application-worker.js',import.meta.url).pathname;
  const {readFile}=await import('node:fs/promises'),{applicationProxy}=await import('./application-proxy.js');
  const manifest=JSON.parse((await privateFile(config.sourceBuildManifestPath)).toString('utf8'));
  const expected=manifest.runtimeFiles['ai-harness/acceptance/compaction/native-adapter/application-worker.js'];
  if(!expected||sha256(await readFile(workerPath))!==expected)throw Error('actual_reviewed_application_worker_build_required');
  const proxy=applicationProxy({workerPath,workerSha256:expected,configPath,configSha256:sha256(await privateFile(configPath)),hostPrivate:config.runnerPrivate,review:config.bootstrap.review},qualification);
  return qualifyOwnedEntry(proxy);
}
export async function qualifyOwnedEntry<T extends {qualifyWorker():Promise<unknown>;shutdown():Promise<unknown>}>(proxy:T):Promise<T>{
  try{await proxy.qualifyWorker();return proxy;}catch(failure){try{await proxy.shutdown();}catch(cleanup){throw new AggregateError([failure,cleanup],'entry_qualification_and_owned_cleanup_failed');}throw failure;}
}
/** The brand is checked in this process; the application worker independently
 * reloads the same protected packet. No secret or boolean crosses IPC. */
export async function loadReviewedCarrierEntry(configPath:string,admission:QualificationTaskAdmission) {
  if(!isQualificationTaskAdmission(admission))throw Error('actual_A_carrier_admission_required');
  await carrierForConfig(configPath,admission);
  return loadReviewedEntry(configPath);
}
export default createNativeAdapter();
