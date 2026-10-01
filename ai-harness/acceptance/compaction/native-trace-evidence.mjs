/** ORIGINAL pinned064c stderr TRACE consumer. No native qualification brand is
 * created here. Stdout/stderr sequence numbers are never merged by arrival. */
import {createHash} from 'node:crypto';
const sha=b=>createHash('sha256').update(b).digest('hex');
const integer=v=>Number.isSafeInteger(v)&&v>=0;
const canonical=v=>Array.isArray(v)?v.map(canonical):v&&typeof v==='object'?Object.fromEntries(Object.keys(v).sort().map(k=>[k,canonical(v[k])])):v;
const equal=(a,b)=>JSON.stringify(canonical(a))===JSON.stringify(canonical(b));
const option=(v,name)=>{if(v==='None')return null;const m=typeof v==='string'&&/^Some\((\d+)\)$/.exec(v);if(!m||!integer(Number(m[1])))throw Error('native_trace_exact_debug_option_'+name);return Number(m[1]);};
export function traceSchemaForMode(mode){
 if(mode==='off')return null;
 if(mode==='post-sampling-token-usage-v1')return 'codex-native-trace-v1';
 if(mode==='post-sampling-token-usage-v2')return 'codex-native-trace-v2';
 throw Error('explicit_known_native_trace_mode_required');
}
export function verifyTraceSchemaMode(schema,mode){
 if(schema!==traceSchemaForMode(mode))throw Error('actual_trace_schema_selected_mode_mismatch');
 return {schema,mode};
}
const date=v=>{const n=typeof v==='string'?Date.parse(v):NaN;if(!Number.isFinite(n))throw Error('native_trace_finite_timestamp_required');return n;};
/** Native JSON preserves fractional UTC precision. Do not round two source
 * events into one millisecond or fill a native i64 with fractional host time. */
export function nativeTimestampNs(value){
 const m=typeof value==='string'&&/^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(?:\.(\d{1,9}))?Z$/.exec(value);
 if(!m)throw Error('original_native_UTC_precision_required');const whole=Date.parse(m[1]+'Z');
 if(!Number.isSafeInteger(whole)||whole<0||new Date(whole).toISOString().slice(0,19)!==m[1])throw Error('invalid_native_UTC_date');
 return BigInt(whole)*1000000n+BigInt((m[2]??'').padEnd(9,'0')||'0');
}
/** Read the original JSON number token at an exact path. Parsed numeric equality
 * alone would accept exponent/fraction spellings and duplicate carrier keys. */
function originalIntegerLiteral(bytes,path){
 const tokens=bytes.match(/"(?:[^"\\]|\\.)*"|-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?|true|false|null|[{}\[\]:,]/g)??[];
 let i=0,found;
 const visit=(keys)=>{const t=tokens[i++];
  if(t==='{'){const seen=new Set();if(tokens[i]==='}'){i++;return;}
   for(;;){const k=JSON.parse(tokens[i++]);if(typeof k!=='string'||seen.has(k)||tokens[i++]!==':')throw Error('original_JSON_duplicate_or_invalid_key');seen.add(k);visit([...keys,k]);const next=tokens[i++];if(next==='}')break;if(next!==',')throw Error('original_JSON_structure');}
  }else if(t==='['){let n=0;if(tokens[i]===']'){i++;return;}for(;;){visit([...keys,String(n++)]);const next=tokens[i++];if(next===']')break;if(next!==',')throw Error('original_JSON_structure');}}
  else if(equal(keys,path)){if(!/^(0|[1-9]\d*)$/.test(t))throw Error('original_native_startedAtMs_integer_literal_required');found=t;}
 };
 visit([]);if(i!==tokens.length||found===undefined)throw Error('original_native_startedAtMs_integer_literal_required');return Number(found);
}
/** Original V2 native integer epoch-ms, source-copied before compact request.
 * Its host observedAt and pipe-arrival order provide no native timestamp. */
export function nativeCompactionStart(frame,threadId,turnId){
 const p=frame?.value?.params;if(frame?.direction!=='from-native'||frame.value?.method!=='item/started'||p?.item?.type!=='contextCompaction'||p.threadId!==threadId||p.turnId!==turnId||(typeof p.item.id!=='string'||!p.item.id)||!Number.isSafeInteger(p.startedAtMs)||p.startedAtMs<0||typeof frame.bytesUtf8!=='string'||sha(frame.bytesUtf8)!==frame.sha256||!equal(JSON.parse(frame.bytesUtf8),frame.value))throw Error('actual_original_native_contextCompaction_startedAtMs_required');
 if(originalIntegerLiteral(frame.bytesUtf8,['params','startedAtMs'])!==p.startedAtMs)throw Error('original_native_startedAtMs_literal_mismatch');
 return {itemId:p.item.id,startedAtMs:p.startedAtMs,nativeNs:BigInt(p.startedAtMs)*1000000n,frameSha256:frame.sha256};
}
function originalTraceLine(lineUtf8){if(typeof lineUtf8!=='string'||!lineUtf8.endsWith('\n')||lineUtf8.slice(0,-1).includes('\n')||Buffer.from(lineUtf8).toString('utf8')!==lineUtf8)throw Error('original_single_utf8_trace_line_required');return JSON.parse(lineUtf8);}
function nativeTaskIdentity(raw){
 const spans=[...(Array.isArray(raw.spans)?raw.spans:[]),...(raw.span?[raw.span]:[])],tasks=spans.filter(s=>s?.name==='turn');
 if(!tasks.length||tasks.some(s=>typeof s['thread.id']!=='string'||typeof s['turn.id']!=='string'||s['thread.id']!==tasks[0]['thread.id']||s['turn.id']!==tasks[0]['turn.id'])||!tasks[0]['thread.id']||!tasks[0]['turn.id'])throw Error('actual_parent_task_span_thread_and_turn_required');
 return {nativeThreadId:tasks[0]['thread.id'],nativeTurnId:tasks[0]['turn.id']};
}
/** Source-reviewed proposed JSON selector. Actual installed formatter readiness
 * must freeze these exact carriers before this can contribute native evidence. */
export function parseAutoCallTrace(lineUtf8){
 const raw=originalTraceLine(lineUtf8),span=raw.span,identity=nativeTaskIdentity(raw);
 if(raw.target!=='codex_core::session::turn'||raw.level!=='TRACE'||raw.fields?.message!=='new'||span?.name!=='run_auto_compact'||typeof span.reason!=='string'||!span.reason||typeof span.phase!=='string'||!span.phase)throw Error('actual_pinned_ContextLimit_MidTurn_auto_call_NEW_required');
 nativeTimestampNs(raw.timestamp);return {raw,lineUtf8,lineSha256:sha(lineUtf8),...identity,autoCallNativeUtc:raw.timestamp};
}
/** Native timestamp-only route is deliberately strict. Same-ms ordering needs
 * the actual source-reviewed run_auto_compact span from the same stderr stream;
 * it cannot be resolved by host arrival or a fabricated clock wrapper. */
export function verifyNativeStartedAtTraceJoin({schema,mode,lines,autoCalls,startFrame,metadata,operation,gateway,producer,resolvedConfig}){
 verifyTraceSchemaMode(schema,mode);
 if(schema===null)throw Error('off_trace_cannot_qualify_automatic');
 const v2=schema==='codex-native-trace-v2';
 if(v2&&!Array.isArray(autoCalls))throw Error('V2_actual_autoCalls_array_required');
 if(!v2&&autoCalls!==undefined&&(!Array.isArray(autoCalls)||autoCalls.length))throw Error('V1_cannot_borrow_V2_AUTO_calls');
 if(!Array.isArray(lines)||!lines.length)throw Error('actual_numeric_trace_lines_required');
 if(!producer?.launchNonce||!producer.processId||metadata?.compaction?.trigger!=='auto'||metadata.compaction.reason!=='context_limit'||metadata.compaction.implementation!=='responses'||metadata.compaction.phase!=='mid_turn'||metadata.request_kind!=='compaction'||metadata.thread_id!==operation?.nativeThreadId||metadata.turn_id!==operation.nativeTurnId||metadata.window_id!==`${metadata.thread_id}:${metadata.window_number}`)throw Error('native_trace_canonical_owned_auto_identity');
 if(operation.method!=='turn/start'||operation.request?.value?.method!=='turn/start'||operation.request.value.params?.threadId!==operation.nativeThreadId||operation.ack?.value?.result?.turn?.id!==operation.nativeTurnId||operation.completed?.value?.params?.turn?.status!=='completed'||!operation.cleanup?.confirmed||!operation.gateway?.confirmed||operation.gateway.nativeThreadId!==operation.nativeThreadId||operation.gateway.nativeTurnId!==operation.nativeTurnId||gateway?.nativeThreadId!==operation.nativeThreadId||gateway.nativeTurnId!==operation.nativeTurnId||gateway.windowId!==metadata.window_id||gateway.contextWindowId!==metadata.context_window_id||gateway.state!=='settled'||typeof gateway.requestId!=='string'||!gateway.requestId)throw Error('actual_owned_RPC_gateway_and_cleanup_required');
 if(resolvedConfig?.contextWindow!==480000||resolvedConfig.autoCompactTokenLimit!==400000||resolvedConfig.maxOutputTokens!==65536||resolvedConfig.effectiveScope!=='total'||resolvedConfig.tokenBudgetEnabled!==false||resolvedConfig.fallbackBufferTokens!==0||resolvedConfig.postTurnPercent!==0)throw Error('independent_protected_effective_native_config_required');
 const start=nativeCompactionStart(startFrame,operation.nativeThreadId,operation.nativeTurnId);
 // Validate every original numeric record before any owner or causal selection.
 const all=lines.map(x=>{const p=parsePostSamplingTrace(x.lineUtf8);nativeTimestampNs(p.raw.timestamp);
  if(v2||p.raw.spans||p.raw.span){const identity=nativeTaskIdentity(p.raw);if(identity.nativeThreadId!==operation.nativeThreadId||identity.nativeTurnId!==operation.nativeTurnId||p.nativeTurnId!==identity.nativeTurnId)throw Error('actual_same_parent_task_ancestry_required');}
  if(p.nativeTurnId!==operation.nativeTurnId)throw Error('actual_same_owned_numeric_turn_required');
  if(x.lineSha256!==undefined&&x.lineSha256!==p.lineSha256)throw Error('original_numeric_trace_digest');
  return {...p,sequence:x.stderrSequence};
 });
 if(v2){
  const calls=autoCalls.map(x=>{const p=parseAutoCallTrace(x.lineUtf8);if(p.nativeThreadId!==operation.nativeThreadId||p.nativeTurnId!==operation.nativeTurnId)throw Error('actual_same_owned_AUTO_call_required');if(x.lineSha256!==undefined&&x.lineSha256!==p.lineSha256)throw Error('original_AUTO_trace_digest');return {...p,sequence:x.stderrSequence};});
  if(calls.length!==1||!integer(calls[0].sequence)||calls[0].sequence<1||!all.length)throw Error('unique_actual_same_owned_AUTO_call_required');
  const call=calls[0];if(call.raw.span.reason!=='ContextLimit'||call.raw.span.phase!=='MidTurn')throw Error('actual_ContextLimit_MidTurn_AUTO_call_required');const ordered=[...all,...calls].sort((a,b)=>a.sequence-b.sequence);let sequence=0,at=-1n;
  for(const event of ordered){const timestamp=nativeTimestampNs(event.raw.timestamp);if(!integer(event.sequence)||event.sequence<=sequence||timestamp<at)throw Error('same_stderr_sequence_and_native_clock_nonregression');const identity=nativeTaskIdentity(event.raw);if(identity.nativeThreadId!==operation.nativeThreadId||identity.nativeTurnId!==operation.nativeTurnId||event.nativeTurnId!==operation.nativeTurnId)throw Error('actual_same_parent_task_ancestry_required');sequence=event.sequence;at=timestamp;}
  const before=all.filter(x=>x.sequence<call.sequence).sort((a,b)=>a.sequence-b.sequence);if(!before.length)throw Error('actual_success_gate_before_AUTO_call_required');const gate=verifyPostSamplingGate(before.at(-1).lineUtf8),callNs=nativeTimestampNs(call.autoCallNativeUtc);
  if(callNs>=start.nativeNs+1000000n)throw Error('AUTO_call_after_actual_native_item_bucket');
  return {status:'SOURCE_VALID',nativeAcceptance:'NOT_TESTED',schema,mode,lineSha256:gate.lineSha256,totalUsageTokens:gate.totalUsageTokens,phase:'mid_turn',autoCallNativeUtc:call.autoCallNativeUtc,autoCallSha256:call.lineSha256,startedAtMs:start.startedAtMs,startFrameSha256:start.frameSha256};
 }
 let sequence=0,instant=-1n;for(const event of all){const at=nativeTimestampNs(event.raw.timestamp);if(!integer(event.sequence)||event.sequence<=sequence||at<instant)throw Error('original_same_turn_trace_sequence_clock_nonregression');sequence=event.sequence;instant=at;}
 if(all.some(event=>{const at=nativeTimestampNs(event.raw.timestamp);return at>=start.nativeNs&&at<start.nativeNs+1000000n;}))throw Error('same_ms_or_after_native_start_requires_actual_auto_call_span');
 const before=all.filter(event=>nativeTimestampNs(event.raw.timestamp)<start.nativeNs);if(!before.length)throw Error('actual_latest_pre_start_gate_required');
 const gate=verifyPostSamplingGate(before.at(-1).lineUtf8);
 return {status:'SOURCE_VALID',nativeAcceptance:'NOT_TESTED',schema,mode,lineSha256:gate.lineSha256,totalUsageTokens:gate.totalUsageTokens,phase:'mid_turn',startedAtMs:start.startedAtMs,startFrameSha256:start.frameSha256};
}
export function parsePostSamplingTrace(lineUtf8){
 if(typeof lineUtf8!=='string'||!lineUtf8.endsWith('\n')||lineUtf8.slice(0,-1).includes('\n')||Buffer.from(lineUtf8).toString('utf8')!==lineUtf8)throw Error('original_single_utf8_trace_line_required');
 const raw=JSON.parse(lineUtf8),f=raw.fields;
 if(raw.target!=='codex_core::session::turn'||raw.level!=='TRACE'||f?.message!=='post sampling token usage'||typeof f.turn_id!=='string'||!f.turn_id)throw Error('pinned_post_sampling_explicit_turn_trace_required');
 const nativeAt=date(raw.timestamp);option(f.auto_compact_window_prefill_tokens,'prefill');
 for(const k of ['total_usage_tokens','auto_compact_scope_tokens'])if(!integer(f[k])||originalIntegerLiteral(lineUtf8,['fields',k])!==f[k])throw Error('native_trace_actual_integer_'+k);
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
 const selected=lines.map(x=>{const p=parsePostSamplingTrace(x.lineUtf8);if(p.nativeTurnId!==operation.nativeTurnId)throw Error('actual_same_owned_numeric_turn_required');if(p.raw.spans||p.raw.span){const task=nativeTaskIdentity(p.raw);if(task.nativeThreadId!==operation.nativeThreadId||task.nativeTurnId!==operation.nativeTurnId)throw Error('actual_same_parent_task_ancestry_required');}return p;}).filter(x=>x.nativeAt>=before&&x.nativeAt<after);
 if(selected.length!==1)throw Error('single_unambiguous_actual_turn_trace_gate_required');
 const gate=verifyPostSamplingGate(selected[0].lineUtf8);
 return {status:'SOURCE_VALID',nativeAcceptance:'NOT_TESTED',lineSha256:gate.lineSha256,totalUsageTokens:gate.totalUsageTokens,phase:'mid_turn'};
}
export default Object.freeze({enabled:false,capabilities:[],nativeAcceptance:'NOT_TESTED'});
/** Independent consumer of A's exact codex-native-trace-v1 ORIGINAL receipt,
 * event files and separately retained original launch/settlement. Expected
 * source/receipt hashes are frozen by root AFTER genuine prior regular sampling. */
export function verifyRetainedTrace(packet,expected){
 for(const key of ['traceReceipt','launchReceipt','settlementReceipt'])if(typeof packet[key+'Utf8']!=='string'||sha(packet[key+'Utf8'])!==packet[key+'Sha256'])throw Error('original_native_trace_'+key+'_digest');
 const t=JSON.parse(packet.traceReceiptUtf8),l=JSON.parse(packet.launchReceiptUtf8),s=JSON.parse(packet.settlementReceiptUtf8),v2=t.schema==='codex-native-trace-v2';
 verifyTraceSchemaMode(t.schema,t.mode);
 if(packet.selectedMode!==undefined)verifyTraceSchemaMode(t.schema,packet.selectedMode);
 const selectedMode=expected.mode??(v2?undefined:'post-sampling-token-usage-v1');
 verifyTraceSchemaMode(t.schema,selectedMode);
 const mode=t.mode,environment={RUST_LOG:v2?'off,codex_core::session::turn=trace,codex_core::tasks=info':'off,codex_core::session::turn=trace',LOG_FORMAT:'json'};
 if(expected.traceReceiptSha256!==packet.traceReceiptSha256||expected.launchReceiptSha256!==packet.launchReceiptSha256||expected.settlementReceiptSha256!==packet.settlementReceiptSha256||l.schema!=='codex-launch-v1'||s.schema!=='codex-settlement-v1'||!['codex-native-trace-v1','codex-native-trace-v2'].includes(t.schema)||t.nonce!==l.nonce||s.nonce!==l.nonce||t.runId!==l.runId||s.runId!==l.runId||t.sessionId!==expected.sessionId||l.sessionId!==t.sessionId||s.sessionId!==t.sessionId||t.containerId!==l.container?.id||s.containerId!==l.container.id||s.containerName!==l.container.name||t.mode!==mode||t.complete!==true||t.cleanupOk!==true||s.cleanupOk!==true||s.cliReaped!==true||s.pipesJoined!==true||s.rmExit!==0||s.existsExit!==1||t.engineExitStatus!==s.engineExitStatus||t.requestedStop!==s.requestedStop||!equal(t.environment,environment)||l.container.imageRevision!=='064c6b8c737f5b41d171fdda80bd9ef10ad06eb3')throw Error('actual_original_A_trace_launch_settlement_binding');
 if(!equal(t.producer,l.producer)||!equal(s.producer,l.producer)||!equal(t.sources,l.sources)||!equal(l.sources,expected.receiptSources)||!Array.isArray(t.events)||!Array.isArray(packet.events)||!t.events.length||t.events.length!==packet.events.length||t.events.length>64||!integer(t.stderrBytes)||t.stderrBytes>16*1024*1024||!/^[a-f0-9]{64}$/.test(t.stderrSHA256)||!/^[a-f0-9]{64}$/.test(t.stderrChain))throw Error('same_original_owned_trace_source_and_complete_stream');
 let sequence=0,end=0;const lines=[],autoCalls=[];
 for(const [i,event] of t.events.entries()){const bytes=packet.events[i].lineUtf8;if(v2&&!['postSampling','autoCompactNew'].includes(event.kind))throw Error('exact_V2_original_event_kind_required');const p=v2&&event.kind==='autoCompactNew'?parseAutoCallTrace(bytes):parsePostSamplingTrace(bytes);if(v2){const identity=nativeTaskIdentity(p.raw);if(event.threadId!==identity.nativeThreadId||event.turnId!==identity.nativeTurnId||p.nativeTurnId!==identity.nativeTurnId)throw Error('actual_V2_original_task_ancestry_projection');}if(event.file!==`trace-event-${String(i).padStart(4,'0')}.raw`||event.sha256!==p.lineSha256||event.bytes!==Buffer.byteLength(bytes)||!integer(event.stderrSequence)||event.stderrSequence<=sequence||!integer(event.stderrOffset)||event.stderrOffset<end||event.stderrOffset+event.bytes>t.stderrBytes||!/^[a-f0-9]{64}$/.test(event.chain)||event.turnId!==p.nativeTurnId||event.nativeTimestamp!==p.raw.timestamp||!integer(event.observedAtMs)||!integer(event.observedMonotonicNs))throw Error('original_trace_event_index_bytes_offsets_turn');sequence=event.stderrSequence;end=event.stderrOffset+event.bytes;(v2&&event.kind==='autoCompactNew'?autoCalls:lines).push({...p,stderrSequence:sequence,stderrOffset:event.stderrOffset});}
 return {status:'SOURCE_VALID',nativeAcceptance:'NOT_TESTED',schema:t.schema,mode:t.mode,selectedMode,lines,autoCalls,producer:{launchNonce:l.nonce,processId:`${l.producer.bootId}:${l.producer.pid}:${l.producer.startTicks}`},receiptSha256:packet.traceReceiptSha256};
}
