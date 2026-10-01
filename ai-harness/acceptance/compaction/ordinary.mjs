/** Supplemental production evidence validation. No model/HTTP/VM invocation.
 * SOURCE_VALID is deliberately distinct from native PASS/live authorization. */
import {createHash} from 'node:crypto';
import {automaticMetadata,automaticFrames,automaticThreshold} from './automatic-evidence.mjs';
const sha=s=>createHash('sha256').update(s).digest('hex'),hex=s=>typeof s==='string'&&/^[a-f0-9]{64}$/.test(s);
const same=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
export function verifyAutomaticCapture(observation,expected) {
 if(typeof observation?.automaticReceiptUtf8!=='string'||!expected?.summaryPrefix||!expected.receiptSources)return {status:'NOT_TESTED',errors:['actual-automatic-capture-or-independent-inputs-absent']};
 try {
  const r=JSON.parse(observation.automaticReceiptUtf8);
  if(r.source!=='h041-owned-ordinary-automatic-compaction'||sha(observation.automaticReceiptUtf8)!==observation.automaticReceiptSha256||r.sessionId!==expected.sessionId||r.nativeThreadId!==expected.nativeThreadId||r.storeRunId!==expected.storeRunId||r.operationId!==expected.operationId||r.automaticReplay!==false||!Array.isArray(r.requests)||!r.requests.length||!Array.isArray(r.gatewayRecords))throw Error('automatic-owned-operation-binding');
  const before=r.beforeState,after=r.afterState;
  if(before.capturedBy!=='host'||after.capturedBy!=='host'||before.nativeThreadId!==r.nativeThreadId||after.nativeThreadId!==r.nativeThreadId||sha(before.stateUtf8)!==before.stateSha256||sha(after.stateUtf8)!==after.stateSha256||!after.stateUtf8.startsWith(before.stateUtf8)||before.stateSha256!==expected.beforeStateSha256||r.summaryPrefixSha256!==sha(expected.summaryPrefix))throw Error('automatic-original-state-prefix-or-checkpoint');
  const producer=r.producer,l=JSON.parse(producer.launchReceiptUtf8),s=JSON.parse(producer.settlementReceiptUtf8);
  if(l.schema!=='codex-launch-v1'||l.sessionId!==r.sessionId||s.schema!=='codex-settlement-v1'||s.nonce!==l.nonce||s.containerId!==l.container.id||!s.cleanupOk||!s.cliReaped||!s.pipesJoined||s.rmExit!==0||s.existsExit!==1||!same(Object.entries(l.sources).sort(),Object.entries(expected.receiptSources).sort()))throw Error('automatic-actual-producer-settlement');
  const windows=new Set(),ids=new Set(),metadata=[];
  for(const c of r.requests){const raw=JSON.parse(c.firstRequestUtf8),normalized=JSON.parse(c.normalizedRequestUtf8),m=automaticMetadata(raw,r.nativeThreadId,r.nativeTurnId);
   if(!c.requestId||ids.has(c.requestId)||sha(c.firstRequestUtf8)!==c.captureSha256||sha(c.normalizedRequestUtf8)!==c.normalizedSha256||normalized.model!=='qwen3.8-27b'||normalized.max_tokens!==65536)throw Error('authenticated_raw_auto_native_metadata');ids.add(c.requestId);windows.add(m.window_id+':'+m.context_window_id);metadata.push(m);
  }
  if(windows.size!==1||r.gatewayRecords.length!==ids.size||metadata.some(m=>!same(m.compaction,metadata[0].compaction)))throw Error('automatic_window_request_ambiguity');
  for(const bytes of r.gatewayRecords){const g=JSON.parse(bytes);if(!ids.delete(g.id)||g.sessionId!==r.sessionId||g.state!=='settled')throw Error('automatic_current_gateway_ledger');}
  const frames=JSON.parse(r.nativeFramesUtf8),lifecycle=automaticFrames(frames,r.nativeThreadId,r.nativeTurnId);
  for(const capture of r.requests)if(capture.sessionId!==r.sessionId||capture.runId!==r.storeRunId||capture.nativeThreadId!==r.nativeThreadId||capture.nativeTurnId!==r.nativeTurnId)throw Error('automatic_current_owned_request_operation_binding');
  // Stdio notifications and gateway ingress have no cross-channel delivery
  // barrier. Retain times, but do not infer causality from their wall clocks.
  const record=after.stateUtf8.trimEnd().split('\n').map(JSON.parse).filter(x=>x.type==='compacted').at(-1);
  if(typeof record?.payload?.message!=='string'||!record.payload.message.startsWith(expected.summaryPrefix)||sha(record.payload.message)!==r.selectedMessageSha256)throw Error('automatic-latest-persisted-summary');
  if(!Array.isArray(r.counts)||r.counts.length!==r.requests.length)return {status:'NOT_TESTED',errors:['actual_complete_input_count_captures_absent'],nativeAcceptance:'NOT_TESTED'};
  const countIds=new Set();
  for(const c of r.counts){const capture=r.requests.find(q=>q.requestId===c.requestId),count=typeof c.receiptUtf8==='string'&&JSON.parse(c.receiptUtf8),result=count&&JSON.parse(count.resultUtf8),ledger=r.gatewayRecords.map(JSON.parse).find(g=>g.id===c.requestId);
   if(!capture||countIds.has(c.requestId)||c.receiptSha256!==sha(c.receiptUtf8)||count.source!=='host-qualified-qwen-count-callback'||count.phase!=='count'||count.requestId!==c.requestId||count.requestUtf8!==capture.normalizedRequestUtf8||count.requestSha256!==sha(count.requestUtf8)||count.inputTokens!==c.input||result.inputTokens!==c.input||result.contextWindow!==480000||count.contextWindow!==480000||count.maxOutput!==65536||c.contextWindow!==480000||c.maxOutput!==65536||!Number.isSafeInteger(c.input)||c.input<1||c.input+65536>480000||ledger.accounting?.inputTokens!==c.input||ledger.accounting?.reservedOutputTokens!==65536||!Number.isFinite(Date.parse(count.startedAt))||Date.parse(count.completedAt)<Date.parse(count.startedAt))throw Error('complete_input_count_request_and_durable_admission_binding');countIds.add(c.requestId);
  }

  const threshold=automaticThreshold(r,expected,metadata[0]);
  return {status:threshold.status,errors:threshold.errors,thresholdQualification:threshold.status,nativeAcceptance:'NOT_TESTED',trigger:'auto',durationMs:Date.parse(r.completedAt)-Date.parse(r.startedAt),countQualification:'SOURCE_VALID',limitation:'Raw source validation is not installed transport/model/ordinary qualification.'};
 }catch(error){return {status:'FAIL',errors:[error.message],nativeAcceptance:'NOT_TESTED'};}
}
export function ordinaryVerdict(packet) {
 const steps=Object.fromEntries((packet?.steps??[]).map(s=>[s.id,s]));
 const required=['O1','O2','O3','O4','O5','O6','O7','O8'];
 const missing=required.filter(id=>steps[id]?.status!=='PASS');
 // A controlled recovery PASS never erases the failed original native operation.
 const nativeFault=(packet?.steps??[]).some(s=>s.nativeOutcome==='failed'||s.nativeOutcome==='cancelled');
 return {nativeAcceptance:nativeFault?'FAIL':'NOT_TESTED',ordinaryNormalPathStatus:missing.some(id=>id!=='O7'&&id!=='O8')?'NOT_TESTED':'SOURCE_VALID',controlledRecoveryStatus:steps.O7?.status??'NOT_TESTED',automaticStatus:steps.O8?.status??'NOT_TESTED',missing,limitation:'Only the root-qualified actual ordinary runner may publish native PASS; this source packet validator cannot.'};
}
export function bindOriginalAliases(memory,records) {
 if(!memory||typeof memory.resolve!=='function'||typeof memory.read!=='function')throw Error('actual_production_original_descriptor_bridge_unavailable');
 return records.map(r=>{const descriptor=memory.resolve(r.sourceId);if(descriptor.id!==r.sourceId||descriptor.availability!=='complete'||!hex(descriptor.sha256)||!Number.isSafeInteger(descriptor.bytes)||!Number.isSafeInteger(r.offset)||!Number.isSafeInteger(r.bytes)||r.offset<0||r.bytes<1||r.offset+r.bytes>descriptor.bytes)throw Error('owned_original_alias_descriptor_invalid');let offset=r.offset,text='';while(offset<r.offset+r.bytes){const read=memory.read(descriptor.id,offset,Math.min(8192,r.offset+r.bytes-offset));if(read.reference.id!==descriptor.id||read.reference.sha256!==descriptor.sha256||read.offset!==offset||read.nextOffset<=offset||read.nextOffset>r.offset+r.bytes||Buffer.byteLength(read.text)!==read.nextOffset-offset)throw Error('original_alias_bounded_read_changed');text+=read.text;offset=read.nextOffset;}if(sha(text)!==r.sha256||Buffer.byteLength(text)!==r.bytes)throw Error('original_alias_exact_byte_interval_changed');return {alias:r.alias,sourceId:descriptor.id,sourceKey:descriptor.sourceKey,sourceSha256:descriptor.sha256,sourceBytes:descriptor.bytes,offset:r.offset,bytes:r.bytes,sha256:r.sha256};});
}
