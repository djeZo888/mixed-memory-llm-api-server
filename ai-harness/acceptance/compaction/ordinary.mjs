/** Supplemental production evidence validation. No model/HTTP/VM invocation.
 * SOURCE_VALID is deliberately distinct from native PASS/live authorization. */
import {createHash} from 'node:crypto';
import {verifyObservedOwnedClose} from './owned-close-verifier.mjs';
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
  const windows=new Set(),ids=new Set();
  for(const c of r.requests){const raw=JSON.parse(c.firstRequestUtf8),normalized=JSON.parse(c.normalizedRequestUtf8),m=JSON.parse(raw.client_metadata['x-codex-turn-metadata']);
   if(!c.requestId||ids.has(c.requestId)||sha(c.firstRequestUtf8)!==c.captureSha256||sha(c.normalizedRequestUtf8)!==c.normalizedSha256||raw.client_metadata.thread_id!==r.nativeThreadId||raw.client_metadata.turn_id!==r.nativeTurnId||m.request_kind!=='compaction'||m.compaction?.trigger!=='auto'||typeof m.window_id!=='string'||!m.window_id.startsWith(r.nativeThreadId+':')||!/^\d+$/.test(m.window_id.slice(r.nativeThreadId.length+1))||raw.client_metadata['x-codex-window-id']!==undefined&&raw.client_metadata['x-codex-window-id']!==m.window_id||normalized.model!=='qwen3.8-27b')throw Error('authenticated-raw-auto-native-metadata');ids.add(c.requestId);windows.add(m.window_id);
  }
  if(windows.size!==1||r.gatewayRecords.length!==ids.size)throw Error('automatic-window-request-ambiguity');
  for(const bytes of r.gatewayRecords){const g=JSON.parse(bytes);if(!ids.delete(g.id)||g.sessionId!==r.sessionId||g.state!=='settled')throw Error('automatic-current-gateway-ledger');}
  const frames=JSON.parse(r.nativeFramesUtf8);
  if(frames.some(f=>sha(f.bytesUtf8)!==f.sha256||!same(JSON.parse(f.bytesUtf8),f.value)))throw Error('automatic-frame-bytes');
  const terminal=frames.filter(f=>f.direction==='from-native'&&f.value.method==='turn/completed'&&f.value.params?.threadId===r.nativeThreadId&&f.value.params?.turn?.id===r.nativeTurnId&&f.value.params.turn.status==='completed');
  const starts=frames.filter(f=>f.value.method==='item/started'&&f.value.params?.item?.type==='contextCompaction'),ends=frames.filter(f=>f.value.method==='item/completed'&&f.value.params?.item?.type==='contextCompaction');
  if(terminal.length!==1||starts.length!==1||ends.length!==1||starts[0].sequence>=ends[0].sequence||starts[0].value.params.item.id!==ends[0].value.params.item.id||starts[0].value.params.threadId!==r.nativeThreadId||ends[0].value.params.threadId!==r.nativeThreadId||ends[0].value.params.turnId!==r.nativeTurnId)throw Error('automatic-canonical-terminal');
  const record=after.stateUtf8.trimEnd().split('\n').map(JSON.parse).filter(x=>x.type==='compacted').at(-1);
  if(typeof record?.payload?.message!=='string'||!record.payload.message.startsWith(expected.summaryPrefix)||sha(record.payload.message)!==r.selectedMessageSha256)throw Error('automatic-latest-persisted-summary');
  const countQualified=Array.isArray(r.counts)&&r.counts.length&&r.counts.every(c=>Number.isSafeInteger(c.input)&&c.input>0&&c.contextWindow===480000&&c.maxOutput===65536&&c.input+65536<=480000&&typeof c.receiptUtf8==='string'&&JSON.parse(c.receiptUtf8).inputTokens===c.input);
  return {status:'SOURCE_VALID',errors:[],nativeAcceptance:'NOT_TESTED',trigger:'auto',durationMs:Date.parse(r.completedAt)-Date.parse(r.startedAt),countQualification:countQualified?'SOURCE_VALID':'NOT_TESTED',limitation:'Raw source validation is not installed transport/model/ordinary qualification.'};
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
