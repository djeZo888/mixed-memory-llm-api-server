/** ORIGINAL pinned064c stderr TRACE consumer. No native qualification brand is
 * created here. Stdout/stderr sequence numbers are never merged by arrival. */
import {createHash} from 'node:crypto';
const sha=b=>createHash('sha256').update(b).digest('hex');
const integer=v=>Number.isSafeInteger(v)&&v>=0;
const option=(v,name)=>{if(v==='None')return null;const m=typeof v==='string'&&/^Some\((\d+)\)$/.exec(v);if(!m||!integer(Number(m[1])))throw Error('native_trace_exact_debug_option_'+name);return Number(m[1]);};
const date=v=>{const n=typeof v==='string'?Date.parse(v):NaN;if(!Number.isFinite(n))throw Error('native_trace_finite_timestamp_required');return n;};
export function parsePostSamplingTrace(lineUtf8){
 if(typeof lineUtf8!=='string'||!lineUtf8.endsWith('\n')||lineUtf8.slice(0,-1).includes('\n')||Buffer.from(lineUtf8).toString('utf8')!==lineUtf8)throw Error('original_single_utf8_trace_line_required');
 const raw=JSON.parse(lineUtf8),f=raw.fields;
 if(raw.target!=='codex_core::session::turn'||raw.level!=='TRACE'||f?.message!=='post sampling token usage'||typeof f.turn_id!=='string'||!f.turn_id)throw Error('pinned_post_sampling_explicit_turn_trace_required');
 const nativeAt=date(raw.timestamp);option(f.auto_compact_window_prefill_tokens,'prefill');
 for(const k of ['total_usage_tokens','auto_compact_scope_tokens'])if(!integer(f[k]))throw Error('native_trace_actual_integer_'+k);
 for(const k of ['full_context_window_limit_reached','token_limit_reached','model_needs_follow_up','has_pending_input','needs_follow_up'])if(typeof f[k]!=='boolean')throw Error('native_trace_actual_boolean_'+k);
 if(!['Total','Prefill'].includes(f.auto_compact_limit_scope))throw Error('native_trace_exact_scope_enum');
 return {raw,lineUtf8,lineSha256:sha(lineUtf8),nativeAt,nativeTurnId:f.turn_id,totalUsageTokens:f.total_usage_tokens,scopeTokens:f.auto_compact_scope_tokens,scope:f.auto_compact_limit_scope,autoLimit:option(f.auto_compact_scope_limit,'auto'),fullLimit:option(f.full_context_window_limit,'full')};
}
export function verifyPostSamplingGate(lineUtf8,phase='mid_turn'){
 const p=parsePostSamplingTrace(lineUtf8),f=p.raw.fields;
 if(phase!=='mid_turn'||p.scope!=='Total'||p.scopeTokens!==p.totalUsageTokens||p.autoLimit!==400000||p.fullLimit!==480000||p.totalUsageTokens<400000||p.totalUsageTokens>=480000||f.full_context_window_limit_reached!==false||f.token_limit_reached!==true||f.needs_follow_up!==true)throw Error('actual_native_400k_total_mid_turn_gate_required');
 return {...p,status:'SOURCE_VALID',nativeAcceptance:'NOT_TESTED'};
}
/** A supplies an independently source-resolved native clock-domain bracket.
 * Host pipe arrival timestamps cannot be passed as native clock timestamps.
 * All original selected lines are considered: ambiguous attribution denies. */
export function verifyTraceCausalJoin(input){
 const {lines,metadata,operation,gateway,clock,producer,resolvedConfig}=input;
 if(!Array.isArray(lines)||!lines.length||metadata?.compaction?.trigger!=='auto'||metadata.compaction.reason!=='context_limit'||metadata.compaction.implementation!=='responses'||metadata.compaction.phase!=='mid_turn'||metadata.request_kind!=='compaction'||metadata.thread_id!==operation?.nativeThreadId||metadata.turn_id!==operation.nativeTurnId||metadata.window_id!==`${metadata.thread_id}:${metadata.window_number}`)throw Error('native_trace_canonical_owned_auto_identity');
 if(operation.method!=='turn/start'||operation.request?.value?.method!=='turn/start'||operation.request.value.params?.threadId!==operation.nativeThreadId||operation.ack?.value?.result?.turn?.id!==operation.nativeTurnId||operation.completed?.value?.params?.turn?.status!=='completed'||!operation.cleanup?.confirmed||!operation.gateway?.confirmed||operation.gateway.nativeThreadId!==operation.nativeThreadId||operation.gateway.nativeTurnId!==operation.nativeTurnId)throw Error('native_trace_actual_owned_rpc_ack_cleanup_gateway');
 if(!producer||producer.launchNonce!==clock?.launchNonce||producer.processId!==clock?.processId||clock.source!=='source-resolved-native-clock-causal-bracket'||clock.clockDomain!=='native-rust-systemtime'||clock.threadId!==operation.nativeThreadId||clock.turnId!==operation.nativeTurnId||clock.requestId!==gateway?.requestId||clock.windowId!==metadata.window_id||clock.contextWindowId!==metadata.context_window_id||gateway.nativeThreadId!==operation.nativeThreadId||gateway.nativeTurnId!==operation.nativeTurnId||gateway.windowId!==metadata.window_id||gateway.contextWindowId!==metadata.context_window_id||gateway.state!=='settled')throw Error('independent_same_native_process_clock_and_gateway_join_required');
 const before=date(clock.samplingCompletedNativeUtc),after=date(clock.compactionStartedNativeUtc);if(before>=after||clock.sourceControlFlow!=='064c-turn.rs:post-sampling-before-mid-turn-auto')throw Error('ambiguous_separate_pipe_causal_order');
 if(resolvedConfig?.contextWindow!==480000||resolvedConfig.autoCompactTokenLimit!==400000||resolvedConfig.maxOutputTokens!==65536||resolvedConfig.effectiveScope!=='total'||resolvedConfig.tokenBudgetEnabled!==false||resolvedConfig.fallbackBufferTokens!==0||resolvedConfig.postTurnPercent!==0)throw Error('independent_protected_effective_native_config_required');
 const selected=lines.map(x=>parsePostSamplingTrace(x.lineUtf8)).filter(x=>x.nativeTurnId===operation.nativeTurnId&&x.nativeAt>=before&&x.nativeAt<after);
 if(selected.length!==1)throw Error('single_unambiguous_actual_turn_trace_gate_required');
 const gate=verifyPostSamplingGate(selected[0].lineUtf8);
 return {status:'SOURCE_VALID',nativeAcceptance:'NOT_TESTED',lineSha256:gate.lineSha256,totalUsageTokens:gate.totalUsageTokens,phase:'mid_turn'};
}
export default Object.freeze({enabled:false,capabilities:[],nativeAcceptance:'NOT_TESTED'});
