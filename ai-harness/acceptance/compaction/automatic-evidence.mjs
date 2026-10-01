/** Independent pinned064c AUTO parser. Source validation cannot mint native PASS. */
import {createHash} from 'node:crypto';
const sha=s=>createHash('sha256').update(s).digest('hex');
export function automaticMetadata(raw,threadId,turnId){
 const carrier=raw?.client_metadata,encoded=carrier?.['x-codex-turn-metadata'];if(typeof encoded!=='string')throw Error('canonical_automatic_metadata_absent');
 const m=JSON.parse(encoded),c=m.compaction;
 if(m.request_kind!=='compaction'||m.thread_id!==threadId||m.turn_id!==turnId||!Number.isSafeInteger(m.window_number)||m.window_number<0||m.window_id!==`${threadId}:${m.window_number}`||typeof m.context_window_id!=='string'||!m.context_window_id||!c||Object.keys(c).sort().join()!=='implementation,phase,reason,strategy,trigger'||c.trigger!=='auto'||c.reason!=='context_limit'||c.implementation!=='responses'||!['pre_turn','mid_turn','post_turn'].includes(c.phase)||c.strategy!=='memento')throw Error('canonical_automatic_identity_and_full_operation_tuple');
 for(const [alias,key] of [['thread_id','thread_id'],['turn_id','turn_id'],['x-codex-window-id','window_id'],['context_window_id','context_window_id']])if(carrier[alias]!==undefined&&carrier[alias]!==m[key])throw Error('automatic_raw_alias_conflict');return m;
}
export function automaticFrames(frames,threadId,turnId){
 if(!Array.isArray(frames)||!frames.length)throw Error('actual_automatic_frames_absent');let prior=-1;
 for(const f of frames){if(!Number.isSafeInteger(f.sequence)||f.sequence<=prior||sha(f.bytesUtf8)!==f.sha256||JSON.stringify(JSON.parse(f.bytesUtf8))!==JSON.stringify(f.value)||!['to-native','from-native'].includes(f.direction)||!Number.isFinite(Date.parse(f.observedAt)))throw Error('automatic_frame_bytes_sequence');prior=f.sequence;}
 const outgoing=frames.filter(f=>f.direction==='to-native');if(outgoing.some(f=>f.value.method==='thread/compact/start'))throw Error('manual_rpc_cannot_qualify_auto');
 const calls=outgoing.filter(f=>f.value.method==='turn/start');if(calls.length!==1||calls[0].value.params?.threadId!==threadId||calls[0].value.id===undefined)throw Error('exact_owned_ordinary_turn_start_required');
 const acknowledgments=frames.filter(f=>f.direction==='from-native'&&f.value.id===calls[0].value.id);
 if(acknowledgments.length!==1||acknowledgments[0].value.error||acknowledgments[0].value.result?.turn?.id!==turnId||acknowledgments[0].sequence<=calls[0].sequence)throw Error('exact_owned_ordinary_turn_ack_required');
 const scoped=(method)=>frames.filter(f=>f.direction==='from-native'&&f.value.method===method&&f.value.params?.threadId===threadId);
 const turnStarts=scoped('turn/started').filter(f=>f.value.params?.turn?.id===turnId),terminals=scoped('turn/completed').filter(f=>f.value.params?.turn?.id===turnId),starts=scoped('item/started').filter(f=>f.value.params?.item?.type==='contextCompaction'),ends=scoped('item/completed').filter(f=>f.value.params?.item?.type==='contextCompaction');
 if(turnStarts.length!==1||terminals.length!==1||terminals[0].value.params.turn.status!=='completed'||starts.length!==1||ends.length!==1||starts[0].value.params.turnId!==turnId||ends[0].value.params.turnId!==turnId||starts[0].value.params.item.id!==ends[0].value.params.item.id||calls[0].sequence>=turnStarts[0].sequence||turnStarts[0].sequence>=starts[0].sequence||starts[0].sequence>=ends[0].sequence||ends[0].sequence>=terminals[0].sequence||acknowledgments[0].sequence>=terminals[0].sequence)throw Error('automatic_owned_lifecycle_and_terminal_order');
 // Native ACK may arrive before or after TurnStarted; no invented ordering.
 return {start:starts[0],end:ends[0],turnStart:turnStarts[0],terminal:terminals[0]};
}
/** Exact400k remains unavailable without independently retained actual resolved
 * configuration + pinned native active-context producer bytes. A new prompt's
 * gateway count alone cannot substitute for the pre-turn native baseline. */
export function automaticThreshold(r,expected,metadata){
 const bytes=r.activeContextReceiptUtf8;
 if(typeof bytes!=='string'||!expected.activeContextReceiptSha256||!expected.runtimeQualificationSha256)return {status:'NOT_TESTED',errors:['actual_resolved_config_and_native_active_context_producer_unavailable']};
 if(sha(bytes)!==expected.activeContextReceiptSha256||sha(bytes)!==r.activeContextReceiptSha256)throw Error('actual_native_active_context_bytes_not_independently_bound');
 const e=JSON.parse(bytes),c=e.resolvedConfig;
 if(e.source!=='pinned-native-active-context-observation'||e.nativeThreadId!==r.nativeThreadId||e.nativeTurnId!==r.nativeTurnId||e.beforeStateSha256!==r.beforeState.stateSha256||e.runtimeQualificationSha256!==expected.runtimeQualificationSha256||e.sourceRevision!=='064c6b8c737f5b41d171fdda80bd9ef10ad06eb3'||e.phase!==metadata.compaction.phase||c?.contextWindow!==480000||c.autoCompactTokenLimit!==400000||c.maxOutputTokens!==65536||c.effectiveScope!=='total'||c.effectiveBudget!==400000||c.effectiveBudget!==Math.min(c.autoCompactTokenLimit,Math.floor(c.contextWindow*.9))||!Number.isSafeInteger(c.usableContextWindow)||c.usableContextWindow<=400000||c.postTurnPercent!==0||metadata.compaction.phase==='post_turn')throw Error('exact_400k_configuration_scope_and_cause_not_observed');
 if(typeof e.nativeUsageFrameUtf8!=='string'||sha(e.nativeUsageFrameUtf8)!==e.nativeUsageFrameSha256||typeof e.historyEstimateUtf8!=='string'||sha(e.historyEstimateUtf8)!==e.historyEstimateSha256)throw Error('native_active_context_raw_inputs_absent');
 const usage=JSON.parse(e.nativeUsageFrameUtf8),h=JSON.parse(e.historyEstimateUtf8),last=usage.params?.tokenUsage?.last?.totalTokens;
 if(usage.method!=='thread/tokenUsage/updated'||usage.params.threadId!==r.nativeThreadId||usage.params.tokenUsage.modelContextWindow!==480000||!Number.isSafeInteger(last)||last<0||h.source!=='pinned-history-active-context-estimate'||h.stateSha256!==r.beforeState.stateSha256||!Number.isSafeInteger(h.afterLastModelOutputTokens)||h.afterLastModelOutputTokens<0||e.activeUsage!==last+h.afterLastModelOutputTokens||e.activeUsage<400000||e.activeUsage>=c.usableContextWindow||metadata.compaction.phase==='mid_turn'&&e.needsFollowUp!==true)throw Error('native_usage_does_not_distinguish_400k_from_hard_cap');
 return {status:'SOURCE_VALID',errors:[],effectiveBudget:400000,nativeAcceptance:'NOT_TESTED'};
}
