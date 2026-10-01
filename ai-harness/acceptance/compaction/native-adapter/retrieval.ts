import { projectionReceipts } from './projection-receipt.js';
import { randomUUID } from 'node:crypto';
import { join } from 'node:path';
import { CodexEngine } from '../../../server/src/codex-engine.js';
import { createCodexReadOriginalProbe } from '../../../server/src/codex-probe.js';
import type { TemporaryHost } from './bootstrap.js';
import type { ProbeManifest } from './dispatch-guard.js';
import { emptyProbeMounts, durableFile } from './checkpoint.js';
import { sha256, stableJson } from './projection.js';
/** Genuine A canonical start/server-call/written/completed consumption -> B trace.
 * Full record citation is granted only for an actually returned complete record. */
export function consumedOriginalTrace(input: {frames: any[]; settled: any[]; originals: {reference:string;bytes:Uint8Array}[]; scopeId:string; checkpointId:string; threadId:string; turnId:string; runId:string}) {
  const calls = input.settled.filter(r => r.runId === input.runId && r.checkpointId === input.checkpointId && r.threadId === input.threadId && r.turnId === input.turnId).map(r => {
    const request = input.frames.find(f => f.direction === 'from-native' && f.value.method === 'item/tool/call' && f.value.params?.callId === r.callId);
    const response = request && input.frames.find(f => f.direction === 'to-native' && f.value.id === request.value.id && f.value.result);
    const completed = input.frames.find(f => f.direction === 'from-native' && f.value.method === 'item/completed' && f.value.params?.item?.id === r.callId);
    const source = input.originals.find(o => o.reference === r.arguments.reference);
    const text = response?.value.result.contentItems?.map((x:any) => x.text ?? '').join('');
    if (!request || !response || !completed || !source || !r.success || request.value.params.threadId !== input.threadId || request.value.params.turnId !== input.turnId || request.value.params.tool !== 'read_original' ||
        stableJson(request.value.params.arguments) !== stableJson(r.arguments) || sha256(JSON.stringify(response.value.result)) !== r.responseSha256 || completed.value.params.item.success !== true ||
        r.arguments.offset !== 0 || r.arguments.limit < source.bytes.byteLength || text !== Buffer.from(source.bytes).toString('utf8')) throw Error('original_full_record_consumption_not_proven');
    return { id:r.callId,tool:'scoped.read_original_records',nativeTool:'read_original',scopeId:input.scopeId,checkpointId:input.checkpointId,threadId:input.threadId,turnId:input.turnId,
      arguments:r.arguments,records:[{sourceId:source.reference,sha256:sha256(source.bytes)}],serverCallUtf8:request.bytesUtf8,responseUtf8:response.bytesUtf8,completedItemUtf8:completed.bytesUtf8,responseSha256:r.responseSha256 };
  });
  if (!calls.length || new Set(calls.map(c => c.id)).size !== calls.length) throw Error('genuine_original_consumption_trace_absent_or_duplicate');
  return {capturedBy:'host',format:'h041-consumed-originals-v1',calls};
}
export async function retrievalProbe(h: TemporaryHost, input: {parentNativeThreadId:string;runId:string;actionId:string;windowId:string;scopeId:string;checkpointId:string;originals:{reference:string;bytes:Uint8Array}[];summary:string;frozenPolicy:string;manifest:ProbeManifest;signal:AbortSignal;omittedFactIds:string[];contextSha256:string;compactedRecordSha256:string;collectorSourceSha256:string;collectorManifestUtf8:string;request:unknown}) {
  if (!h.evidence || !h.qualification || h.launchHeld() || input.signal.aborted) throw Error('qualified_scoped_retrieval_unavailable');
  const sessionId = randomUUID(), mounts = await emptyProbeMounts(h.layout.dataDir,[h.layout.hostPrivate]);
  const probe = createCodexReadOriginalProbe({sessionId,runId:input.runId,checkpointId:input.checkpointId,baseInstructions:input.frozenPolicy,originals:input.originals});
  h.originalProbes.set(sessionId,probe);
  let threadId: string | undefined, turnId: string | undefined, engine: CodexEngine | undefined, outcome: unknown, failure: unknown;
  const token = h.gateway.issueToken(sessionId,'codex'), abort = new AbortController(), signal = AbortSignal.any([input.signal,abort.signal,AbortSignal.timeout(Math.max(1,Math.min(120000,h.dispatchCutoffAt-Date.now())))]);
  let done!:()=>void; const finished = new Promise<void>(r=>{done=r;});
  h.directProbes.set(sessionId,{abort:()=>abort.abort(),finished});
  const cancel = () => {h.gateway.revokeSession(sessionId); void engine?.cancel().catch(()=>undefined);}; signal.addEventListener('abort',cancel,{once:true});
  try {
    const p = h.qualification.scopePolicies['read-original'];
    h.guard.register({sessionId,runId:input.runId,actionId:input.actionId,mode:'durable-retrieval',parentNativeThreadId:input.parentNativeThreadId,manifest:input.manifest,validateFollowup:body=>validateOriginalFollowup(body,input.manifest.input,h.observer.frames(sessionId),h.originalSettlements),toolPolicy:{rawTools:p.rawTools,normalizedTools:p.normalizedTools,envelope:input.manifest.envelope},signal,expiresAt:Math.min(h.dispatchCutoffAt,Date.now()+120000),identity:()=>({nativeThreadId:threadId,nativeTurnId:turnId})});
    engine = new CodexEngine({sessionId,engineKind:'codex',engineVersion:'0.158.0',modelPolicyVersion:h.host.runtime.modelPolicyVersion,nativeState:{ownership:'idle',activeTurnId:null,eventCursor:0},
      profileDir:mounts.profileDir,workspace:mounts.workspace,launcher:h.launcherPath,gatewayUrl:h.host.runtime.gatewayUrl,gatewayToken:token,stderrPath:join(mounts.profileDir,'stderr.log'),
      dispatchHeld:()=>signal.aborted || h.launchHeld(),onNativeSessionId:id=>{threadId=id;},onNativeState:state=>{turnId=state.activeTurnId ?? turnId;},onUpdate:()=>{}},h.host.runtime);
    outcome = await engine.prompt(input.manifest.userText);
  } catch (error) { failure=error; }
  finally {
    try {h.gateway.revokeSession(sessionId);await engine?.close();} catch(error) {failure ??= error;}
    h.originalProbes.delete(sessionId);signal.removeEventListener('abort',cancel);h.guard.retire(sessionId);h.directProbes.delete(sessionId);done();
  }
  if (failure || outcome !== 'completed' || !threadId || !turnId || !h.observer.settled(sessionId)) throw Error('retrieval_failed_output_retained_no_replay');
  const op = h.observer.operation(sessionId), frames = h.observer.frames(sessionId), capture = h.guard.requests(sessionId)[0];
  const final = (op.completed.value.params as any).turn.items?.findLast((item:any) => item.type === 'agentMessage' && item.phase !== 'commentary');
  if (!final?.text || !capture) throw Error('retrieval_final_answer_or_first_capture_absent');
  const retrieval = consumedOriginalTrace({frames,settled:h.originalSettlements,originals:input.originals,scopeId:input.scopeId,checkpointId:input.checkpointId,threadId,turnId,runId:input.runId});
  const receiptUtf8 = stableJson({source:'native-owned-retrieval-settlement',sessionId,runId:input.runId,actionId:input.actionId,nativeThreadId:threadId,nativeTurnId:turnId,windowId:input.windowId,traceReceiptSha256:op.traceReceiptSha256,retrieval});
  await durableFile(join(h.layout.hostPrivate,`${sessionId}-retrieval.json`),receiptUtf8);
  const first = JSON.parse(capture.firstRequestUtf8), compiledContextText=stableJson(first);
  const projection = projectionReceipts(input,capture,op);
  await durableFile(join(h.layout.hostPrivate,`${sessionId}-probe-settlement.json`),projection.probeSettledOperationUtf8);
  await durableFile(join(h.layout.hostPrivate,`${sessionId}-projection.json`),projection.projectionReceiptUtf8);
  return {outcome:'completed',durationMs:{state:'measured',value:Date.parse(op.gateway.observedAt)-Date.parse(op.request.observedAt),source:'host-native-probe-operation-observation',receiptSha256:projection.probeSettledOperationSha256,reason:null},requests:h.guard.requests(sessionId),settlementReceiptUtf8:projection.probeSettledOperationUtf8,sessionId,runId:input.runId,actionId:input.actionId,nativeThreadId:threadId,nativeTurnId:turnId,answer:JSON.parse(final.text),retrieval,
    isolation:{...capture,...projection,toolsDenied:false,modelFileTools:[],networkPolicy:'gateway-only'},
    retrievalContext:{...capture,capturedBy:'host',compiledContextText,contextSha256:sha256(compiledContextText),omittedFactIds:input.omittedFactIds,qualifiedProjectionReceiptSha256:sha256(receiptUtf8),networkPolicy:'gateway-only',modelFileTools:[]},
    settlement:{state:'released',receiptSha256:projection.probeSettledOperationSha256,automaticReplay:false}};
}

/** First approved projection + only actually consumed native dynamic records. */
export function validateOriginalFollowup(input: unknown, prefix: unknown[], frames: any[], settled: any[]) {
  if (!Array.isArray(input) || stableJson(input.slice(0,prefix.length)) !== stableJson(prefix)) throw Error('retrieval_projection_prefix_changed');
  const suffix=input.slice(prefix.length), pending=new Set<string>(), consumed=new Set<string>();
  for(const item of suffix) {
    if(item?.type==='function_call') {
      if(Object.keys(item).some(k=>!['type','id','call_id','name','arguments','status'].includes(k)) || item.name!=='read_original'||pending.has(item.call_id)||consumed.has(item.call_id))throw Error('foreign_original_history_call');
      const request=frames.find(f=>f.direction==='from-native'&&f.value.method==='item/tool/call'&&f.value.params?.callId===item.call_id);
      if(!request||item.arguments!==JSON.stringify(request.value.params.arguments)||!settled.some(s=>s.callId===item.call_id&&s.success))throw Error('unconsumed_original_history_call');pending.add(item.call_id);
    } else if(item?.type==='function_call_output') {
      if(Object.keys(item).some(k=>!['type','id','call_id','output','status'].includes(k))||!pending.delete(item.call_id))throw Error('unmatched_original_history_result');
      const req=frames.find(f=>f.direction==='from-native'&&f.value.method==='item/tool/call'&&f.value.params?.callId===item.call_id);
      const response=req&&frames.find(f=>f.direction==='to-native'&&f.value.id===req.value.id&&f.value.result);
      const output=Array.isArray(item.output)?item.output.map((p:any)=>{if(p.type!=='input_text'||Object.keys(p).some(k=>!['type','text'].includes(k)))throw Error('unqualified_original_output');return p.text;}).join(''):item.output;
      if(!response||output!==response.value.result.contentItems.map((p:any)=>p.text).join(''))throw Error('original_result_history_changed');consumed.add(item.call_id);
    } else if(item?.type==='message'&&item.role==='assistant') {
      const text=item.content?.map((p:any)=>p.text).join('');
      if(!frames.some(f=>f.direction==='from-native'&&f.value.method==='item/completed'&&f.value.params?.item?.type==='agentMessage'&&f.value.params.item.text===text))throw Error('unobserved_assistant_history');
    } else throw Error('unqualified_retrieval_followup_history');
  }
  if(pending.size||!consumed.size)throw Error('original_result_history_incomplete');
}
