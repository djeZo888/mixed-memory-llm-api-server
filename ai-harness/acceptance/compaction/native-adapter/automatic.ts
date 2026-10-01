/** Separate ordinary automatic attribution. Never changes the manual suite. */
import {isQualifiedEntry} from './qualification.js';
import { randomUUID } from 'node:crypto';
import { join } from 'node:path';
interface AutomaticHost {evidence:any;qualification:any;counts:any;application:any;observer:any;guard:any;gateway:any;layout:any;withCaptureHold:any;}
import type {ParentState} from './collector.js';
import {automaticMetadata} from '../automatic-evidence.mjs';
import {NativeCollector,nativeCompactionMetadata} from './collector.js';
import {durableFile} from './checkpoint.js';
import {sha256,stableJson,extractPersistedSummary} from './projection.js';
export async function collectOrdinaryAutomatic(host:AutomaticHost,input:{sessionId:string;storeRunId:string;operationId:string;baseline:ParentState;summaryPrefix:string}) {
  if(!host.evidence||!isQualifiedEntry(host.qualification)||!host.counts)throw Error('actual_qualified_ordinary_producer_required');
  const run=host.application.store.runSnapshot(input.storeRunId),session=host.application.store.getSession(input.sessionId),op=host.observer.operation(input.sessionId);
  const actualRun=host.application.store.db.prepare('SELECT session_id FROM runs WHERE id=?').get(input.storeRunId);
  if(actualRun?.session_id!==input.sessionId||run.status!=='completed'||session.nativeSessionId!==input.baseline.nativeThreadId||op.method!=='turn/start'||op.nativeThreadId!==input.baseline.nativeThreadId)throw Error('actual_ordinary_turn_and_baseline_required');
  const frames=host.observer.frames(input.sessionId),captures=host.guard.requests(input.sessionId).filter((c:any)=>c.runId===input.storeRunId),automatic=captures.filter((c:any)=>{const m=nativeCompactionMetadata(JSON.parse(c.firstRequestUtf8));return m?.request_kind==='compaction'&&m.compaction?.trigger==='auto';});
  for(const capture of automatic)automaticMetadata(JSON.parse(capture.firstRequestUtf8),op.nativeThreadId,op.nativeTurnId);
  if(!automatic.length)throw Error('genuine_automatic_metadata_not_observed_no_retry');
  const starts=frames.filter((f:any)=>f.direction==='from-native'&&f.value.method==='item/started'&&(f.value.params as any)?.item?.type==='contextCompaction'),ends=frames.filter((f:any)=>f.direction==='from-native'&&f.value.method==='item/completed'&&(f.value.params as any)?.item?.type==='contextCompaction');
  if(starts.length!==1||ends.length!==1)throw Error('single_actual_automatic_compaction_required');
  const start=starts[0],end=ends[0],p=start.value.params as any,e=end.value.params as any;
  if(p.threadId!==op.nativeThreadId||e.threadId!==op.nativeThreadId||p.turnId!==op.nativeTurnId||e.turnId!==op.nativeTurnId||p.item.id!==e.item.id||start.sequence>=end.sequence)throw Error('automatic_canonical_lifecycle_mismatch');
  const collector=new NativeCollector({store:host.application.store,files:host.application.files,gateway:host.gateway,observer:host.observer,guard:host.guard,hostPrivate:host.layout.hostPrivate,withCaptureHold:host.withCaptureHold});
  const after=await collector.captureState(input.sessionId,'ordinary-auto-actual-persisted-full-state');
  const selected=extractPersistedSummary(Buffer.from(after.stateUtf8),{nativeThreadId:op.nativeThreadId,nativeTurnId:op.nativeTurnId,actionId:input.operationId,beforeBytes:Buffer.byteLength(input.baseline.stateUtf8),beforeSha256:input.baseline.stateSha256,dispatchedAt:start.observedAt,settledAt:op.gateway.observedAt,summaryPrefix:input.summaryPrefix});
  const ledger=host.application.store.db.prepare('SELECT id,session_id,state,record FROM h021_gateway_requests WHERE session_id=?').all(input.sessionId).filter((r:any)=>automatic.some((c:any)=>c.requestId===r.id));
  if(ledger.length!==automatic.length||ledger.some((r:any)=>r.state!=='settled')||host.gateway.sessionWork(input.sessionId).length)throw Error('automatic_owned_gateway_settlement_unconfirmed');
  const producer=host.evidence.parentProducer(input.sessionId);
  const automaticReceiptUtf8=stableJson({source:'h041-owned-ordinary-automatic-compaction',operationId:input.operationId,storeRunId:input.storeRunId,sessionId:input.sessionId,nativeThreadId:op.nativeThreadId,nativeTurnId:op.nativeTurnId,windowId:automaticMetadata(JSON.parse(automatic[0].firstRequestUtf8),op.nativeThreadId,op.nativeTurnId).window_id,
    beforeState:input.baseline,afterState:after,selectedMessageSha256:sha256(selected.message),summaryPrefixSha256:sha256(input.summaryPrefix),requests:automatic,nativeUsageFramesUtf8:stableJson(frames.filter((f:any)=>f.direction==='from-native'&&f.value.method==='thread/tokenUsage/updated')),nativeOperationUtf8:stableJson(op),nativeOperationSha256:sha256(stableJson(op)),nativeFramesUtf8:stableJson(frames),producer,gatewayRecords:ledger.map((r:any)=>String(r.record)),counts:host.counts.receipts(automatic.map((c:any)=>c.requestId)),startedAt:start.observedAt,completedAt:op.gateway.observedAt,automaticReplay:false});
  await durableFile(join(host.layout.hostPrivate,`${randomUUID()}-ordinary-automatic.json`),automaticReceiptUtf8);
  return {automaticReceiptUtf8,automaticReceiptSha256:sha256(automaticReceiptUtf8),nativeAcceptance:'NOT_TESTED',limitation:'Collection alone does not qualify ordinary entry, trusted state, retention or admitted near-threshold counts.'};
}
