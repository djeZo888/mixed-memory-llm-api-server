import {childRequestMetadata} from './child-lineage.mjs';
import { createHash } from 'node:crypto';
const sha = s => createHash('sha256').update(s).digest('hex');
const same = (a,b) => JSON.stringify(a) === JSON.stringify(b);
const keys = ['actionId','nativeThreadId','nativeTurnId','settlementReceiptSha256'];
export function verifyObservedOwnedClose(result, expected) {
  if (!expected?.receiptSources || typeof result?.closeReceiptUtf8 !== 'string') return { status: 'NOT_TESTED', errors: ['independent-native-close-source-pins-or-raw-bytes-absent'] };
  try {
    const r = JSON.parse(result.closeReceiptUtf8);
    if (r.source !== 'native-acceptance-run-close' || r.format !== 'h041-owned-close-v1' || r.runId !== expected.runId || r.operationWindowId !== expected.operationWindowId ||
        r.status !== 'released' || !Array.isArray(r.producers) || !r.producers.length || !Array.isArray(r.settledOwnedActions) ||
        !Array.isArray(r.outstandingOwnedActions) || r.outstandingOwnedActions.length || !Array.isArray(r.unconfirmedOwnedActions) || r.unconfirmedOwnedActions.length ||
        result.closeReceiptSha256 !== sha(result.closeReceiptUtf8) || result.outcome !== 'closed' || result.settlement?.state !== 'released' || result.settlement.receiptSha256 !== sha(result.closeReceiptUtf8) || result.settlement.automaticReplay !== false) throw Error('close binding');
    const byNonce = new Map(), sessions = new Set();
    for (const p of r.producers) {
      if (typeof p.launchReceiptUtf8 !== 'string' || typeof p.settlementReceiptUtf8 !== 'string') throw Error('raw producer absent');
      const l = JSON.parse(p.launchReceiptUtf8), s = JSON.parse(p.settlementReceiptUtf8);
      if (l.schema !== 'codex-launch-v1' || s.schema !== 'codex-settlement-v1' || !/^[a-f0-9]{64}$/.test(l.nonce) || byNonce.has(l.nonce) || !l.sessionId || !l.runId ||
          JSON.stringify(Object.entries(l.sources).sort()) !== JSON.stringify(Object.entries(expected.receiptSources).sort()) || l.container?.imageRevision !== '064c6b8c737f5b41d171fdda80bd9ef10ad06eb3' ||
          s.nonce !== l.nonce || s.runId !== l.runId || s.sessionId !== l.sessionId || !same(s.producer,l.producer) || s.containerId !== l.container?.id || s.containerName !== l.container?.name ||
          s.checkedAtMs < l.checkedAtMs || !s.cliReaped || s.rmExit !== 0 || s.existsExit !== 1 || !s.pipesJoined || !s.cleanupOk) throw Error('actual native producer settlement mismatch');
      byNonce.set(l.nonce,p); sessions.add(l.sessionId);
    }
    const ids = new Set(), projected = [];
    for (const a of r.settledOwnedActions) {
      if (!a.actionId || ids.has(a.actionId) || !a.nativeThreadId || !a.nativeTurnId || a.windowId !== expected.operationWindowId || !sessions.has(a.sessionId) || !/^[a-f0-9]{64}$/.test(a.settlementReceiptSha256)) throw Error('foreign/duplicate action');
      ids.add(a.actionId);
      const launch = JSON.parse(a.nativeLaunchReceiptUtf8), producer = byNonce.get(launch.nonce);
      if (!producer || producer.launchReceiptUtf8 !== a.nativeLaunchReceiptUtf8 || producer.settlementReceiptUtf8 !== a.nativeSettlementReceiptUtf8 || launch.sessionId !== a.sessionId) throw Error('unmatched producer');
      const gateway = JSON.parse(a.gatewayReceiptUtf8);
      if(a.delegatedParentActionId){const parent=r.settledOwnedActions.find(x=>x.actionId===a.delegatedParentActionId);if(!parent||parent.sessionId!==a.sessionId||parent.nativeLaunchReceiptUtf8!==a.nativeLaunchReceiptUtf8||parent.nativeSettlementReceiptUtf8!==a.nativeSettlementReceiptUtf8)throw Error('actual same producer parent settlement');const metadata=childRequestMetadata(JSON.parse(a.firstRequestUtf8),parent.nativeThreadId,parent.nativeTurnId);if(metadata.thread_id!==a.nativeThreadId||metadata.turn_id!==a.nativeTurnId||gateway.authenticationParentThreadId!==parent.nativeThreadId||gateway.authenticationParentTurnId!==parent.nativeTurnId)throw Error('actual child authenticated parent mapping');}
      if (typeof a.operationSettlementUtf8 !== 'string' || sha(a.operationSettlementUtf8) !== a.settlementReceiptSha256 || !Array.isArray(a.requestIds) || !a.requestIds.length || new Set(a.requestIds).size !== a.requestIds.length || typeof a.operationFramesUtf8 !== 'string') throw Error('actual action request/settlement bytes absent');
      const frames=JSON.parse(a.operationFramesUtf8);
      if (!frames.some(f=>f.direction==='from-native' && f.value?.method==='turn/completed' && f.value.params?.threadId===a.nativeThreadId && f.value.params?.turn?.id===a.nativeTurnId && f.value.params.turn.status==='completed') || frames.some(f=>sha(f.bytesUtf8)!==f.sha256 || !same(JSON.parse(f.bytesUtf8),f.value))) throw Error('actual native turn trace mismatch');
      if (gateway.source !== 'owned-durable-gateway-ledger-observation' || gateway.sessionId !== a.sessionId || gateway.nativeThreadId !== a.nativeThreadId || gateway.nativeTurnId !== a.nativeTurnId ||
          !Array.isArray(gateway.outstanding) || gateway.outstanding.length || !Array.isArray(gateway.records) || !gateway.records.length) throw Error('unconfirmed gateway lineage');
      const requestIds = new Set();
      for (const raw of gateway.records) {
        if (typeof raw !== 'string') throw Error('gateway raw bytes absent'); const record = JSON.parse(raw);
        if (!record.id || requestIds.has(record.id) || record.sessionId !== a.sessionId || record.state !== 'settled' || !Number.isFinite(Date.parse(record.updatedAt))) throw Error('gateway stored row mismatch');
        requestIds.add(record.id);
      }
      if (a.requestIds.length !== requestIds.size || a.requestIds.some(id=>!requestIds.has(id))) throw Error('action/current gateway request mismatch');
      projected.push(Object.fromEntries(keys.map(k => [k,a[k]])));
    }
    const canonical = xs => xs.slice().sort((a,b) => a.actionId.localeCompare(b.actionId)).map(x => Object.fromEntries(keys.map(k => [k,x[k]])));
    if (!Array.isArray(expected.observedSettlements) || new Set(expected.observedSettlements.map(s => s.actionId)).size !== expected.observedSettlements.length || !same(canonical(projected),canonical(expected.observedSettlements))) throw Error('exhaustive action map mismatch');
    return { status: 'PASS', errors: [] };
  } catch { return { status: 'FAIL', errors: ['owned-close-exhaustive-actions-or-actual-native-gateway-receipt-content'] }; }
}
