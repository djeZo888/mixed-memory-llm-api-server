import type {CodexRuntime} from '../../../server/src/codex-engine.js';
import type {TemporaryHost} from './bootstrap.js';
import {privateFile,durableFile,within} from './checkpoint.js';
import {normalizeNativeInput,type RequestScope} from './dispatch-guard.js';
import {sha256,stableJson,identifier} from './projection.js';
import {verifyChildLineage} from '../child-lineage.mjs';
import {join} from 'node:path';

/** One live owned parent action. No new native connection/thread is manufactured.
 * onNativeThread and beforeNativeAction are A's awaited callbacks. */
export class DelegatedChildProducer {
 private pending=new Map<string,any>();
 private threads=new Map<string,Parameters<NonNullable<CodexRuntime['onNativeThread']>>[0]>();
 observe:NonNullable<CodexRuntime['onNativeThread']>=async input=>{this.threads.set(input.sessionId,input);};
 arm:NonNullable<CodexRuntime['beforeNativeAction']>=async input=>{
  const p=this.pending.get(input.sessionId);if(!p)return;
  const t=this.threads.get(input.sessionId),h:TemporaryHost=p.host,parent=h.guard.activeScope(input.sessionId);
  if(!t||input.method!=='turn/start'||t.threadId!==input.threadId||input.threadId!==p.state.nativeThreadId||t.launchReceipt!==input.launchReceipt||parent?.purpose!=='child'||!t.rolloutPath)throw Error('same_live_owned_retention_parent_before_spawn_required');
  p.rolloutPath=t.rolloutPath;
  h.guard.armDelegatedChild(input.sessionId,{parentNativeThreadId:input.threadId,readAndScope:async(childId,metadata)=>{
   if(p.childId||(p.spawnReceiver&&p.spawnReceiver!==childId)||p.signal.aborted)throw Error('one_owned_child_only');
   const ready=(frames:any[])=>frames.some(f=>f.direction==='from-native'&&f.value.method==='turn/started'&&f.value.params?.threadId===childId&&f.value.params.turn?.id===metadata.turn_id)&&frames.some(f=>f.direction==='from-native'&&f.value.method==='item/started'&&f.value.params?.threadId===input.threadId&&f.value.params?.turnId===metadata.parent_turn_id&&f.value.params.item?.tool==='spawnAgent'&&f.value.params.item?.prompt===p.brief);
   const before=await h.observer.waitFrames(input.sessionId,ready,p.signal,parent.expiresAt),spawn=before.filter(f=>f.direction==='from-native'&&f.value.method==='item/started'&&(f.value.params as any)?.threadId===input.threadId&&(f.value.params as any)?.turnId===metadata.parent_turn_id&&(f.value.params as any)?.item?.tool==='spawnAgent'&&(f.value.params as any)?.item?.type==='collabAgentToolCall'&&(f.value.params as any)?.item?.prompt===p.brief);
   const childStarts=before.filter(f=>f.direction==='from-native'&&f.value.method==='turn/started'&&(f.value.params as any)?.threadId===childId&&(f.value.params as any)?.turn?.id===metadata.turn_id);
   if(spawn.length!==1||childStarts.length!==1||metadata.parent_turn_id!==parent.identity().nativeTurnId)throw Error('actual_parent_spawn_and_child_turn_before_dispatch_required');
   const thread=await input.readChildThread(childId),frames=h.observer.frames(input.sessionId);
   const q=frames.filter(f=>f.direction==='to-native'&&f.value.method==='thread/read'&&(f.value.params as any)?.threadId===childId&&(f.value.params as any)?.includeTurns===false).at(-1),r=q&&frames.find(f=>f.direction==='from-native'&&f.value.id===q.value.id&&f.value.result);
   if(!q||!r||stableJson((r.value.result as any).thread)!==stableJson(thread))throw Error('actual_awaited_child_raw_read_required');
   const firstDispatchAt=new Date().toISOString(),lineage={requestUtf8:q.bytesUtf8,responseUtf8:r.bytesUtf8,requestSha256:q.sha256,responseSha256:r.sha256,requestSequence:q.sequence,responseSequence:r.sequence,observedAt:r.observedAt};
   if(verifyChildLineage(lineage,{parentId:input.threadId,childId,firstDispatchAt}).status!=='PASS')throw Error('actual_child_lineage_rejected');
   p.childId=childId;p.childTurnId=metadata.turn_id;p.parentTurnId=metadata.parent_turn_id;p.firstDispatchAt=firstDispatchAt;p.lineage=lineage;p.spawnCallId=(spawn[0].value.params as any).item.id;
   const spec=p.review.childProjectionSpec;if(!spec||!Array.isArray(spec.prefixInput)||!spec.envelope)throw Error('independently_frozen_child_projection_required');
   const scope:RequestScope={sessionId:childId,authenticationSessionId:input.sessionId,actionId:p.actionId,runId:p.runId,mode:'clean-child',parentNativeThreadId:input.threadId,nativeRootTurnId:p.parentTurnId,signal:p.signal,expiresAt:parent.expiresAt,delegatedProof:{lineage,spawnCallId:p.spawnCallId,parentTurnId:p.parentTurnId,brief:p.brief,firstDispatchAt},identity:()=>({nativeThreadId:childId,nativeTurnId:p.childTurnId}),manifest:{input:[...structuredClone(spec.prefixInput),{type:'message',role:'user',content:[{type:'input_text',text:p.brief}]}],instructions:spec.envelope.instructions,userText:p.brief,contextSha256:p.state.stateSha256,envelope:structuredClone(spec.envelope)}};
   return {lineage,scope};
  }});
 };
 /** Parent tool continuation is independently read from the actual owned rollout,
  * while the gateway holds dispatch. This is a live input observation, never a
  * no-writer checkpoint or rollback claim. Unpersisted/ambiguous views deny. */
 async followup(sessionId:string,input:unknown,prefix:unknown[]){
  const p=this.pending.get(sessionId),t=this.threads.get(sessionId);if(!p||!t?.rolloutPath||!Array.isArray(input)||stableJson(input.slice(0,prefix.length))!==stableJson(prefix))throw Error('owned_collaboration_projection_required');
  const parentScope=p.host.guard.activeScope(sessionId);if(!parentScope||parentScope.purpose!=='child')throw Error('live_parent_followup_scope_required');
  const observed=await p.host.observer.waitFrames(sessionId,(frames:any[])=>frames.some(f=>f.direction==='from-native'&&f.value.method==='item/completed'&&f.value.params?.threadId===p.state.nativeThreadId&&f.value.params.item?.tool==='spawnAgent'&&f.value.params.item.prompt===p.brief&&f.value.params.item.receiverThreadIds?.length===1),p.signal,parentScope.expiresAt);
  const spawn=observed.filter((f:any)=>f.direction==='from-native'&&f.value.method==='item/completed'&&f.value.params?.threadId===p.state.nativeThreadId&&f.value.params.item?.tool==='spawnAgent'&&f.value.params.item.prompt===p.brief);if(spawn.length!==1||spawn[0].value.params.item.receiverThreadIds?.length!==1)throw Error('actual_single_spawn_receiver_required');
  const candidate=spawn[0].value.params.item.receiverThreadIds[0];if(!identifier(candidate)||candidate===p.state.nativeThreadId||(p.childId&&p.childId!==candidate))throw Error('spawn_receiver_child_scope_conflict');p.spawnReceiver=candidate;if(p.parentTurnId&&p.parentTurnId!==spawn[0].value.params.turnId)throw Error('spawn_parent_turn_changed');p.parentTurnId=spawn[0].value.params.turnId;
  const root=p.host.application.files.profile(sessionId);if(!within(root,t.rolloutPath))throw Error('owned_parent_rollout_path_required');await p.host.application.files.assertNoLinks(root);
  const bytes=await privateFile(t.rolloutPath),again=await privateFile(t.rolloutPath);if(!bytes.equals(again)||bytes.at(-1)!==10||!Buffer.from(bytes.toString('utf8')).equals(bytes))throw Error('live_parent_projection_unstable');
  let history:any[]=[];const records=bytes.toString('utf8').trimEnd().split('\n').map(l=>JSON.parse(l));if(records.filter(r=>r.type==='session_meta').length!==1||records.find(r=>r.type==='session_meta').payload.id!==p.state.nativeThreadId)throw Error('live_parent_source_identity_mismatch');
  if(records.some(r=>/rollback|revert/i.test(String(r.type))))throw Error('live_parent_rollback_unqualified');
  for(const record of records){if(record.type==='response_item')history.push(record.payload);else if(record.type==='compacted'){if(!Array.isArray(record.payload?.replacement_history))throw Error('live_parent_replacement_unqualified');history=record.payload.replacement_history;}}
  const compiled=[...p.parentPrefix,...history];if(stableJson(compiled)!==stableJson(input))throw Error('actual_persisted_parent_followup_mismatch');
  const tail=input.slice(prefix.length);if(!tail.length||tail.some((v:any)=>!['function_call','function_call_output','message','reasoning'].includes(v.type)))throw Error('unqualified_collaboration_followup');
  const frames=p.host.observer.frames(sessionId);
  for(const v of tail as any[])if(v.type==='function_call'){
   const names=p.review.retentionParentPolicy.collaborationToolNames;if(!names||!Object.values(names).includes(v.name)||!frames.some((f:any)=>f.direction==='from-native'&&f.value.method==='item/completed'&&f.value.params?.threadId===p.state.nativeThreadId&&f.value.params?.turnId===p.parentTurnId&&f.value.params?.item?.type==='collabAgentToolCall'&&f.value.params.item.id===v.call_id&&names[String(f.value.params.item.tool)]===v.name))throw Error('unobserved_native_collaboration_call');
  }
  await durableFile(join(p.host.layout.hostPrivate,`${p.actionId}-followup-${sha256(bytes)}-${Date.now()}.jsonl`),bytes);
 }
 async run(input:any){
  const {host:h,parentId,collector,signal,actionId,brief,hostOnlyParentCanary,childNonce,runParent,review,runId,parentPrefix}=input;
  if(!identifier(actionId)||!identifier(runId)||typeof hostOnlyParentCanary!=='string'||!hostOnlyParentCanary||typeof childNonce!=='string'||!childNonce||signal.aborted||typeof brief!=='string'||!brief.includes(childNonce)||brief.includes(hostOnlyParentCanary)||!review.retentionParentPolicy?.childPolicy||this.pending.has(parentId))throw Error('root_frozen_genuine_child_contract_required');
  const placed=await runParent(`Keep this marker private to the parent: ${hostOnlyParentCanary}`,`${actionId}-placement`,'append'),state=await collector.captureState(parentId,'native-child-parent-only-canary');if(!state.stateUtf8.includes(hostOnlyParentCanary))throw Error('actual_parent_canary_placement_absent');
  const p={host:h,state,signal,actionId,brief,review,runId,parentPrefix};this.pending.set(parentId,p);
  try{
   const args=review.retentionParentPolicy.collaborationVersion==='v1'?{message:brief,fork_context:false}:{message:brief,task_name:'retention_child',fork_turns:'none'};
   const parent=await runParent(`Use the installed spawn_agent exactly once with ${JSON.stringify(args)}. Await its completion and close that owned child. Do not pass parent context or tools.`,`${actionId}-parent`,'child');
   const actual:any=p;if(!actual.childId)throw Error('native_spawn_first_request_not_observed');
   const frames=h.observer.frames(parentId),terminal=frames.filter((f:any)=>f.direction==='from-native'&&f.value.method==='turn/completed'&&f.value.params?.threadId===actual.childId&&f.value.params?.turn?.id===actual.childTurnId&&f.value.params.turn.status==='completed'&&f.value.params.turn.error==null);
   const completedSpawn=frames.filter((f:any)=>f.direction==='from-native'&&f.value.method==='item/completed'&&f.value.params?.item?.id===actual.spawnCallId&&f.value.params.item.receiverThreadIds?.length===1&&f.value.params.item.receiverThreadIds[0]===actual.childId);
   const messages=frames.filter((f:any)=>f.direction==='from-native'&&f.value.method==='item/completed'&&f.value.params?.threadId===actual.childId&&f.value.params?.turnId===actual.childTurnId&&f.value.params.item?.type==='agentMessage');
   if(terminal.length!==1||completedSpawn.length!==1||messages.length!==1||!h.observer.settled(parentId))throw Error('actual_child_completion_parent_gateway_cleanup_required');
   const capture=h.guard.receipt(actual.childId),reply=JSON.parse(String((messages[0].value.params as any).item.text));
   const settlementReceiptUtf8=stableJson({source:'owned-native-delegated-child-settlement',actionId,nativeThreadId:actual.childId,nativeTurnId:actual.childTurnId,parentNativeThreadId:state.nativeThreadId,parentTurnId:actual.parentTurnId,parentSettlementReceiptSha256:parent.settlement.receiptSha256,childCompletionUtf8:terminal[0].bytesUtf8,requestId:capture.requestId,authenticationSessionId:parentId});
   await durableFile(join(h.layout.hostPrivate,`${actionId}-child-settlement.json`),settlementReceiptUtf8);
   const started=frames.find((f:any)=>f.direction==='from-native'&&f.value.method==='turn/started'&&f.value.params?.threadId===actual.childId&&f.value.params.turn?.id===actual.childTurnId)!;
   const durationReceiptUtf8=stableJson({source:'host-native-delegated-operation-observation',nativeThreadId:actual.childId,nativeTurnId:actual.childTurnId,actionId,startedAt:started.observedAt,completedAt:parent.settledAt,childCompletionSha256:terminal[0].sha256,parentSettlementReceiptSha256:parent.settlement.receiptSha256});
   if(!Number.isFinite(Date.parse(parent.settledAt))||Date.parse(parent.settledAt)<Date.parse(started.observedAt))throw Error('actual_child_duration_observation_required');
   await durableFile(join(h.layout.hostPrivate,`${actionId}-duration.json`),durationReceiptUtf8);
   const result={actionId,nativeThreadId:actual.childId,nativeTurnId:actual.childTurnId,requests:[capture],outcome:'completed',tokens:parent.tokens,durationMs:{state:'measured',value:Date.parse(parent.settledAt)-Date.parse(started.observedAt),source:'host-native-delegated-operation-observation',receiptSha256:sha256(durationReceiptUtf8),reason:null},settlementReceiptUtf8,settlement:{state:'released',receiptSha256:sha256(settlementReceiptUtf8),automaticReplay:false}};
   await h.evidence!.delegatedOperation(result,parent,parentId,review.authorization.windowId,h.application.store,h.gateway,h.observer);
   return {...result,ownedSettlements:[placed,parent].map(v=>({actionId:v.actionId,nativeThreadId:v.nativeThreadId,nativeTurnId:v.nativeTurnId,settlementReceiptSha256:v.settlement.receiptSha256})),probe:{...capture,capturedBy:'host',parentId:state.nativeThreadId,parentTurnId:actual.parentTurnId,childId:actual.childId,nativeLineage:actual.lineage,firstDispatchAt:actual.firstDispatchAt,firstRequestId:capture.requestId,compiledMessages:normalizeNativeInput(JSON.parse(capture.firstRequestUtf8).input),reply,tools:capture.actualTools,parentPlacement:state}};
  }finally{const actual:any=p;if(actual.childId)h.guard.retire(actual.childId);this.pending.delete(parentId);this.threads.delete(parentId);}
 }
}
