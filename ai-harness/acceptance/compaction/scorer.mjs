import {verifyChildLineage} from './child-lineage.mjs';
import { verifyObservedModelScope } from './model-scope.mjs';
import { createHash } from 'node:crypto';
import { readFile } from 'node:fs/promises';

export const sha256 = (bytes) => createHash('sha256').update(bytes).digest('hex');
// Logical manifests share E's recursive sorted-key JSON contract. Arrays and
// strings retain their exact order/bytes. sha256(raw) never canonicalizes bytes.
export const stableJson = (value) => JSON.stringify(canonical(value));
const canonical = (value) => Array.isArray(value) ? value.map(canonical) :
  value !== null && typeof value === 'object' ? Object.fromEntries(Object.keys(value).sort().map((key) => [key, canonical(value[key])])) : value;
export const actionIdFor = (runId, cycle, operation) => `h039-${sha256(runId).slice(0, 24)}-c${cycle}-${operation}`;
export const loadJson = async (path) => JSON.parse(await readFile(path, 'utf8'));
const object = (v) => v !== null && typeof v === 'object' && !Array.isArray(v);
const same = (a, b) => stableJson(a) === stableJson(b);
const exactKeys = (v, keys) => object(v) && same(Object.keys(v).sort(), [...keys].sort());
export const logicalManifestFormat = 'h040-sorted-json-v1';
export const collectorRequiredFiles = [
  ...['adapter', 'bootstrap', 'checkpoint', 'dispatch-guard', 'probe', 'projection', 'source-closure'].map((name) => `ai-harness/acceptance/compaction/native-adapter/${name}.ts`),
  ...['app', 'broker', 'codex-connection', 'codex-engine', 'codex-launcher', 'codex-provider', 'codex-responses', 'errors', 'files', 'gateway', 'store'].map((name) => `ai-harness/server/src/${name}.ts`),
  'ai-harness/server/package.json', 'ai-harness/server/package-lock.json',
];
export function validateCollectorManifest(bytes) {
  try {
    const manifest = JSON.parse(bytes);
    return manifest.format === 'h040-collector-closure-v1' && manifest.sourceRevision === '064c6b8c737f5b41d171fdda80bd9ef10ad06eb3' &&
      object(manifest.files) && collectorRequiredFiles.every((name) => Object.hasOwn(manifest.files, name)) &&
      Object.entries(manifest.files).every(([name, hash]) => name.startsWith('ai-harness/') && !name.split('/').includes('..') && /^[a-f0-9]{64}$/.test(hash));
  } catch { return false; }
}

// Narrow text-only pinned Responses input support. Other native items remain
// unqualified, rather than being stripped or converted by an adapter.
export function normalizeNativeInput(input) {
  if (!Array.isArray(input)) throw new Error('Typed Responses input array required');
  return input.map((item) => {
    const allowed = ['type', 'id', 'role', 'content', 'phase', 'status'];
    if (!object(item) || item.type !== 'message' || Object.keys(item).some((k) => !allowed.includes(k)) ||
      !['system', 'developer', 'user', 'assistant'].includes(item.role) || !Array.isArray(item.content)) throw new Error('Unqualified native history item');
    const text = item.content.map((part) => {
      if (!object(part) || Object.keys(part).some((k) => !['type', 'text', 'annotations'].includes(k)) ||
        !['input_text', 'output_text'].includes(part.type) || typeof part.text !== 'string' || (part.annotations !== undefined && !same(part.annotations, []))) throw new Error('Unqualified native text part');
      return part.text;
    }).join('');
    const result = { role: item.role, content: text };
    // Retain these fields in the approved manifest; do not silently drop carriers.
    for (const key of ['id', 'phase', 'status']) if (Object.hasOwn(item, key)) result[key] = item[key];
    return result;
  });
}

// Pinned native metadata is read at the captured HTTP boundary, before the
// production translator drops it. A host operation window never supplies this.
export function extractNativeCompactionWindow(captures, expected) {
  if (![expected?.parentThreadId, expected?.nativeTurnId, expected?.actionId].every((v) => typeof v === 'string' && v.length > 0))
    return { status: 'NOT_TESTED', errors: ['independent-native-compaction-request-owner-absent'] };
  if (!Array.isArray(captures) || !captures.length || captures.some((c) => typeof c.firstRequestUtf8 !== 'string'))
    return { status: 'NOT_TESTED', errors: ['actual-native-compaction-request-bytes-absent'] };
  try {
    const windows = captures.map((capture) => {
      if (capture.capturedBy !== 'host' || capture.nativeThreadId !== expected.parentThreadId || capture.nativeTurnId !== expected.nativeTurnId ||
        typeof capture.requestId !== 'string' || !capture.requestId || typeof capture.runId !== 'string' || !capture.runId ||
        capture.actionId !== expected.actionId || capture.captureSha256 !== sha256(capture.firstRequestUtf8) ||
        typeof capture.normalizedRequestUtf8 !== 'string' || capture.normalizedSha256 !== sha256(capture.normalizedRequestUtf8)) throw new Error('Native request capture ownership mismatch');
      const request = JSON.parse(capture.firstRequestUtf8), metadata = request.client_metadata;
      if (typeof metadata?.['x-codex-turn-metadata'] !== 'string') return null;
      const native = JSON.parse(metadata['x-codex-turn-metadata']);
      if (!Number.isSafeInteger(native.window_number) || native.window_number < 0 || native.window_id !== `${expected.parentThreadId}:${native.window_number}` ||
        native.thread_id !== expected.parentThreadId || native.turn_id !== expected.nativeTurnId || typeof native.context_window_id !== 'string' || !native.context_window_id ||
        native.request_kind !== 'compaction' || !same(native.compaction, { trigger: 'manual', reason: 'user_requested', implementation: 'responses', phase: 'standalone_turn', strategy: 'memento' }) ||
        (metadata['x-codex-window-id'] !== undefined && metadata['x-codex-window-id'] !== native.window_id) ||
        (metadata.thread_id !== undefined && metadata.thread_id !== native.thread_id) || (metadata.turn_id !== undefined && metadata.turn_id !== native.turn_id))
        throw new Error('Native metadata identity, provenance or trigger mismatch');
      return { nativeWindowId: native.window_id, nativeWindowNumber: native.window_number, contextWindowId: native.context_window_id };
    });
    if (windows.some((w) => w === null)) return { status: 'NOT_TESTED', errors: ['canonical-native-window-metadata-absent'] };
    if (windows.some((w) => !same(w, windows[0]))) throw new Error('Compaction native window ambiguous');
    return { status: 'PASS', errors: [], ...windows[0], captures: captures.map((c) => ({ requestId: c.requestId, sha256: c.captureSha256, normalizedSha256: c.normalizedSha256 })) };
  } catch { return { status: 'FAIL', errors: ['native-compaction-request-window-turn-trigger-or-capture-binding'] }; }
}

function stateReceiptProof(state) {
  if (typeof state?.receiptUtf8 !== 'string') return { status: 'NOT_TESTED', errors: ['raw-owned-persisted-state-receipt-absent'] };
  try {
    const receipt = JSON.parse(state.receiptUtf8);
    if (receipt.source !== 'owned-native-persisted-state' || !receipt.captureId || !receipt.sessionId || !receipt.sourceRef ||
      receipt.nativeThreadId !== state.nativeThreadId || receipt.stateSha256 !== sha256(state.stateUtf8) || receipt.bytes !== Buffer.byteLength(state.stateUtf8) ||
      !Number.isFinite(Date.parse(receipt.observedAt)) || state.receiptSha256 !== sha256(state.receiptUtf8)) throw new Error('State capture receipt mismatch');
    return { status: 'PASS', errors: [] };
  } catch { return { status: 'FAIL', errors: ['owned-persisted-state-raw-receipt-binding'] }; }
}

export function extractCheckpoint(checkpoint, expected) {
  const baseline = expected.baseline;
  if (!checkpoint || typeof checkpoint.stateUtf8 !== 'string' || typeof checkpoint.compactedRecordUtf8 !== 'string' ||
    typeof checkpoint.bindingReceiptUtf8 !== 'string' || typeof checkpoint.settledOperationUtf8 !== 'string' ||
    !baseline || typeof baseline.stateUtf8 !== 'string' ||
    ![expected.parentThreadId, expected.actionId, expected.nativeTurnId, expected.windowId].every((v) => typeof v === 'string' && v.length > 0) ||
    !/^[a-f0-9]{64}$/.test(expected.contextSha256 ?? ''))
    return { status: 'NOT_TESTED', errors: ['full-state-baseline-owned-record-or-settled-operation-absent'] };
  const fresh = expected.summaryRepresentation === 'persisted-message-only';
  if (!fresh && !['system', 'developer', 'user', 'assistant'].includes(expected.summaryRole)) return { status: 'NOT_TESTED', errors: ['pinned-native-summary-role-unqualified'] };
  let nativeWindow;
  if (expected.requireNativeMetadata) {
    for (const state of [baseline, checkpoint]) { const proof = stateReceiptProof(state); if (proof.status !== 'PASS') return proof; }
    nativeWindow = extractNativeCompactionWindow(expected.compactionRequests, expected);
    if (nativeWindow.status !== 'PASS') return nativeWindow;
  }
  try {
    const binding = JSON.parse(checkpoint.bindingReceiptUtf8), settled = JSON.parse(checkpoint.settledOperationUtf8);
    const stateHash = sha256(checkpoint.stateUtf8), recordHash = sha256(checkpoint.compactedRecordUtf8);
    if (baseline.capturedBy !== 'host' || baseline.nativeThreadId !== expected.parentThreadId ||
      baseline.stateSha256 !== sha256(baseline.stateUtf8) || !/^[a-f0-9]{64}$/.test(baseline.receiptSha256 ?? '') ||
      checkpoint.capturedBy !== 'host' || checkpoint.stateSha256 !== stateHash || stateHash !== expected.contextSha256 ||
      checkpoint.nativeThreadId !== expected.parentThreadId || !checkpoint.stateUtf8.startsWith(baseline.stateUtf8) ||
      !checkpoint.stateUtf8.endsWith('\n') || !baseline.stateUtf8.endsWith('\n')) throw new Error('Full-state or baseline ownership mismatch');
    const lines = checkpoint.stateUtf8.slice(0, -1).split('\n');
    const records = lines.map((line) => JSON.parse(line));
    const baselineRecords = baseline.stateUtf8.slice(0, -1).split('\n').length;
    const metas = records.filter((record) => record.type === 'session_meta');
    if (records[0]?.type !== 'session_meta' || metas.length !== 1 || metas[0].payload?.id !== expected.parentThreadId)
      throw new Error('Persisted native session ownership mismatch');
    const suffix = records.slice(baselineRecords);
    // Pinned reconstruction can undo a compaction. No rollback selector is
    // qualified here; reject rather than call a reverted append surviving.
    if (suffix.some((record) => /rollback|rolled[_ -]?back|revert/i.test(String(record.type)) ||
      /rollback|rolled[_ -]?back|revert/i.test(String(record.payload?.type)))) throw new Error('Rollback reconstruction unqualified');
    if (suffix.filter((record) => record.type === 'compacted').length !== 1) throw new Error('Owned post-baseline compaction ambiguous');
    const index = records.findLastIndex((record) => record.type === 'compacted');
    if (index < baselineRecords || lines[index] + '\n' !== checkpoint.compactedRecordUtf8 ||
      checkpoint.compactedRecordSha256 !== recordHash) throw new Error('Selected record is not latest surviving post-baseline compaction');
    if (binding.source !== 'native-rollout-record-owner' || binding.nativeThreadId !== expected.parentThreadId ||
      binding.compactionActionId !== expected.actionId || binding.nativeTurnId !== expected.nativeTurnId ||
      binding.windowId !== expected.windowId || binding.recordSha256 !== recordHash || binding.stateSha256 !== stateHash ||
      typeof binding.recordId !== 'string' || !binding.recordId || typeof binding.sourceRef !== 'string' || !binding.sourceRef || checkpoint.bindingReceiptSha256 !== sha256(checkpoint.bindingReceiptUtf8)) throw new Error('Record owner mismatch');
    if (expected.requireNativeMetadata && (binding.operationWindowId !== expected.windowId || binding.windowIdProvenance !== 'host-operation-window' ||
      binding.nativeWindowId !== nativeWindow.nativeWindowId || settled.operationWindowId !== expected.windowId || settled.windowIdProvenance !== 'host-operation-window' ||
      settled.nativeWindowId !== nativeWindow.nativeWindowId || !same(settled.nativeRequestCaptures, nativeWindow.captures))) throw new Error('Native and host operation windows differ');
    const timestamp = Date.parse(records[index].timestamp), started = Date.parse(settled.startedAt), completed = Date.parse(settled.completedAt);
    if (settled.source !== 'native-compaction-settlement' || settled.status !== 'completed' || settled.settlement !== 'released' ||
      settled.nativeThreadId !== expected.parentThreadId || settled.actionId !== expected.actionId || settled.nativeTurnId !== expected.nativeTurnId ||
      settled.windowId !== expected.windowId || settled.baselineStateSha256 !== baseline.stateSha256 || settled.postStateSha256 !== stateHash ||
      settled.recordSha256 !== recordHash || !settled.compactionId || !Number.isFinite(timestamp) || !Number.isFinite(started) || !Number.isFinite(completed) ||
      started > timestamp || timestamp > completed || checkpoint.settledOperationSha256 !== sha256(checkpoint.settledOperationUtf8)) throw new Error('Actual settled operation/window/turn binding mismatch');
    const record = records[index];
    if (!object(record.payload) || typeof record.payload.message !== 'string' || !record.payload.message.trim()) throw new Error('Invalid native summary');
    // NEVER project replacement_history: pinned native may retain original user text there.
    const messages = fresh ? undefined : [{ role: expected.summaryRole, content: record.payload.message }];
    if (checkpoint.messages !== undefined && !same(checkpoint.messages, messages)) throw new Error('Independent adapter messages rejected');
    return { status: 'PASS', errors: [], summaryText: record.payload.message, messages, stateSha256: stateHash, compactedRecordSha256: recordHash,
      nativeWindowId: nativeWindow?.nativeWindowId ?? null };
  } catch { return { status: 'FAIL', errors: ['full-state-baseline-latest-record-or-settlement-binding'] }; }
}

export function activeFacts(truth, cycle) {
  if (![1, 2, 3].includes(cycle)) throw new Error('Cycle must be 1, 2 or 3');
  return truth.facts.filter((f) => f.introducedCycle <= cycle).map((fact) => ({
    ...fact, current: fact.versions.filter((v) => v.cycle <= cycle).at(-1),
  }));
}

export function validateCorpus(corpus, truth) {
  const errors = [];
  if (truth.facts.length < 50 || truth.facts.length > 100) errors.push('fact-count');
  if (new Set(truth.facts.map((f) => f.id)).size !== truth.facts.length) errors.push('duplicate-fact');
  const sources = new Map(corpus.records.map((r) => [r.id, r]));
  if (sources.size !== corpus.records.length) errors.push('duplicate-record');
  for (const fact of truth.facts) {
    if (!fact.query || !fact.versions.length || fact.versions[0].cycle !== fact.introducedCycle) errors.push(`fact-shape:${fact.id}`);
    let last = 0;
    for (const version of fact.versions) {
      if (![1, 2, 3].includes(version.cycle) || version.cycle <= last || typeof version.value !== 'string' || !version.value || !version.sourceIds.length) errors.push(`version:${fact.id}`);
      last = version.cycle;
      for (const id of version.sourceIds) {
        const r = sources.get(id);
        if (!r || r.cycle > version.cycle || !r.content.includes(version.value)) errors.push(`source:${fact.id}:${id}`);
      }
    }
  }
  return errors;
}

// Only typed, exact answers are scored. No prose judge, unit conversions or fuzzy matching.
// Prohibiting extra fields prevents ungraded prose from carrying invented permissions/tests.
export function scoreRecall(truth, cycle, answer, mode = 'summary-only') {
  if (!['summary-only', 'durable-retrieval'].includes(mode)) throw new Error('Invalid recall mode');
  const facts = activeFacts(truth, cycle);
  const errors = [];
  if (!exactKeys(answer, ['answers']) || !object(answer.answers)) errors.push('answer-envelope');
  const answers = object(answer?.answers) ? answer.answers : {};
  const known = new Set(facts.map((f) => f.id));
  for (const id of Object.keys(answers)) if (!known.has(id)) errors.push(`unknown-answer:${id}`);
  const results = facts.map((fact) => {
    const item = answers[fact.id];
    const keys = mode === 'summary-only' ? ['value'] : ['value', 'sourceIds'];
    const shape = exactKeys(item, keys);
    const correctValue = shape && typeof item.value === 'string' && item.value === fact.current.value;
    const cited = mode === 'summary-only' || (Array.isArray(item?.sourceIds) &&
      item.sourceIds.length > 0 && new Set(item.sourceIds).size === item.sourceIds.length &&
      item.sourceIds.every((s) => fact.current.sourceIds.includes(s)));
    const obsolete = fact.versions.some((v) => v.cycle < fact.current.cycle && v.value !== fact.current.value && v.value === item?.value);
    return { id: fact.id, critical: fact.critical, correct: correctValue && cited,
      reason: !shape ? 'missing-or-invalid' : obsolete ? 'superseded-choice' : !correctValue ? 'inexact-value' : !cited ? 'wrong-source' : null };
  });
  const count = (critical) => {
    const rows = results.filter((r) => r.critical === critical);
    return { correct: rows.filter((r) => r.correct).length, total: rows.length };
  };
  // This bounded corpus requires full coverage as well as every critical fact.
  return { status: errors.length || results.some((r) => !r.correct) ? 'FAIL' : 'PASS',
    critical: count(true), noncritical: count(false), errors,
    failures: results.filter((r) => !r.correct), mode, cycle };
}

export function verifyRetrieval(corpus, truth, cycle, answer, trace) {
  const errors = [];
  if (!object(trace) || trace.capturedBy !== 'host' || !Array.isArray(trace.calls) || !trace.calls.length) return ['retrieval-not-observed'];
  const records = new Map(corpus.records.filter((r) => r.cycle <= cycle).map((r) => [r.id, r]));
  const retrieved = new Set();
  const ids = new Set();
  for (const call of trace.calls) {
    if (!call.id || ids.has(call.id)) errors.push('retrieval-call-identity');
    ids.add(call.id);
    if (call.tool !== 'scoped.read_original_records' || call.scopeId !== corpus.scopeId || !Array.isArray(call.records) || !call.records.length) {
      errors.push('retrieval-scope-or-tool'); continue;
    }
    if (trace.format === 'h041-consumed-originals-v1') {
      try {
        const req=JSON.parse(call.serverCallUtf8), res=JSON.parse(call.responseUtf8), done=JSON.parse(call.completedItemUtf8), source=records.get(call.arguments?.reference);
        if (req.method!=='item/tool/call'||req.params.tool!=='read_original'||req.params.callId!==call.id||req.params.threadId!==call.threadId||req.params.turnId!==call.turnId||
            !same(req.params.arguments,call.arguments)||res.id!==req.id||res.result.success!==true||sha256(JSON.stringify(res.result))!==call.responseSha256||done.method!=='item/completed'||done.params.item.id!==call.id||done.params.item.success!==true||
            !source||call.arguments.offset!==0||call.arguments.limit<Buffer.byteLength(source.content)||res.result.contentItems.map(p=>p.text).join('')!==source.content) errors.push('native-original-consumption-raw-proof');
      } catch {errors.push('native-original-consumption-raw-proof');}
    }
    for (const proof of call.records) {
      const source = records.get(proof.sourceId);
      if (!source || proof.sha256 !== sha256(source.content)) errors.push('retrieval-source-hash');
      else retrieved.add(proof.sourceId);
    }
  }
  for (const fact of activeFacts(truth, cycle)) {
    const citations = answer?.answers?.[fact.id]?.sourceIds;
    if (!Array.isArray(citations) || !citations.length || citations.some((id) => !retrieved.has(id))) errors.push(`unobserved-citation:${fact.id}`);
  }
  return errors;
}

function scopeProof(probe, threadId, turnId, actionId, tools, expected = {}) {
  if (typeof probe?.scopeReceiptUtf8 === 'string') {
    try { if (JSON.parse(probe.scopeReceiptUtf8).source === 'h041-observed-model-scope') return verifyObservedModelScope(probe, { ...expected, probeThreadId: threadId, probeTurnId: turnId, actionId }); } catch {}
  }
  if (typeof probe.scopeReceiptUtf8 !== 'string') return { status: 'NOT_TESTED', errors: ['effective-native-scope-receipt-absent'] };
  let scope;
  try { scope = JSON.parse(probe.scopeReceiptUtf8); } catch { return { status: 'FAIL', errors: ['invalid-scope-receipt'] }; }
  const valid = scope.source === 'native-launcher-effective-scope' && scope.nativeThreadId === threadId && scope.nativeTurnId === turnId &&
    scope.actionId === actionId && same(scope.allowedTools, tools) && same(scope.readRoots, []) && same(scope.writeRoots, []) &&
    scope.network === 'deny' && scope.answerKeyMounted === false && probe.scopeReceiptSha256 === sha256(probe.scopeReceiptUtf8);
  return { status: valid ? 'PASS' : 'FAIL', errors: valid ? [] : ['scope-receipt-binding'], scopeReceiptSha256: sha256(probe.scopeReceiptUtf8) };
}

// A separately reviewed representation for a fresh native thread. This derives
// E's one-user-message wrapper ourselves from verified persisted bytes and the
// independently approved query/policy. Adapter-declared messages are not input.
export function deriveFreshProjection({ extraction, request, spec, envelope, toolDefinitions, normalizeResponses }) {
  if (extraction?.status !== 'PASS') return extraction ?? { status: 'NOT_TESTED', errors: ['verified-persisted-summary-absent'] };
  if (!spec || spec.format !== 'h040-fresh-persisted-message-v1' || typeof spec.frozenPolicy !== 'string' ||
    !spec.frozenPolicy.trim() || !Array.isArray(spec.prefixInput) || !/^[a-f0-9]{64}$/.test(spec.collectorSourceSha256 ?? '') ||
    typeof spec.collectorManifestUtf8 !== 'string' || !validateCollectorManifest(spec.collectorManifestUtf8) || sha256(spec.collectorManifestUtf8) !== spec.collectorSourceSha256 ||
    typeof normalizeResponses !== 'function' || !object(envelope) || typeof envelope.instructions !== 'string' ||
    envelope.model !== 'qwen3.8-27b' || !Array.isArray(toolDefinitions)) return { status: 'NOT_TESTED', errors: ['independently-frozen-fresh-projection-or-translator-absent'] };
  try {
    const prefix = normalizeNativeInput(spec.prefixInput);
    if (prefix.some((message) => !['system', 'developer'].includes(message.role)) || typeof extraction.summaryText !== 'string')
      throw new Error('Unapproved projection scaffolding');
    const summary = extraction.summaryText;
    const userText = stableJson({ policy: spec.frozenPolicy, persistedCompactedMessage: summary, questions: request });
    const input = [...structuredClone(spec.prefixInput), { type: 'message', role: 'user', content: [{ type: 'input_text', text: userText }] }];
    const messages = normalizeNativeInput(input);
    const raw = { ...structuredClone(envelope), input, tools: structuredClone(toolDefinitions) };
    // Invoke the production translator, including Qwen instruction adaptation;
    // no second implementation of that adaptation is an acceptance authority.
    const normalizedRequest = normalizeResponses(raw).body;
    return { status: 'PASS', errors: [], inputMessageHashes: messages.map((m) => sha256(stableJson(m))),
      freshProjection: { input, normalizedRequest, collectorSourceSha256: spec.collectorSourceSha256,
        collectorManifestUtf8: spec.collectorManifestUtf8,
        summarySha256: sha256(summary), querySha256: sha256(stableJson(request)), policySha256: sha256(spec.frozenPolicy),
        compactedRecordSha256: extraction.compactedRecordSha256 } };
  } catch { return { status: 'FAIL', errors: ['frozen-fresh-projection-invalid-or-translation-rejected'] }; }
}

function verifyFreshProjectionCapture(probe, expected) {
  const p = expected.freshProjection;
  if (![expected.windowId, expected.runId, expected.actionId, expected.parentThreadId, expected.probeThreadId, expected.probeTurnId].every((v) => typeof v === 'string' && v.length > 0) ||
    ![expected.contextSha256, expected.parentStateSha256, expected.settlementReceiptSha256, p?.compactedRecordSha256, p?.summarySha256,
      p?.querySha256, p?.policySha256, p?.collectorSourceSha256].every((v) => /^[a-f0-9]{64}$/.test(v ?? '')) ||
    !Array.isArray(expected.inputMessageHashes) || !expected.inputMessageHashes.length || expected.inputMessageHashes.some((v) => !/^[a-f0-9]{64}$/.test(v)) ||
    !object(p?.normalizedRequest) || !Array.isArray(p?.input) || !object(expected.envelope) || typeof p.collectorManifestUtf8 !== 'string')
    return { status: 'NOT_TESTED', errors: ['independent-fresh-projection-bindings-absent'] };
  if (expected.contextSha256 !== expected.parentStateSha256) return { status: 'FAIL', errors: ['fresh-projection-full-state-hash-mismatch'] };
  if (typeof probe.projectionReceiptUtf8 !== 'string' || typeof probe.normalizedRequestUtf8 !== 'string' ||
    typeof probe.probeSettledOperationUtf8 !== 'string' || typeof probe.collectorManifestUtf8 !== 'string')
    return { status: 'NOT_TESTED', errors: ['raw-fresh-projection-or-normalized-capture-absent'] };
  try {
    const receipt = JSON.parse(probe.projectionReceiptUtf8), request = JSON.parse(probe.firstRequestUtf8), settled = JSON.parse(probe.probeSettledOperationUtf8);
    const wantedSettlement = { source: 'native-probe-settlement', runId: expected.runId, actionId: expected.actionId, windowId: expected.windowId,
      parentNativeThreadId: expected.parentThreadId, nativeThreadId: expected.probeThreadId, nativeTurnId: expected.probeTurnId,
      parentStateSha256: expected.parentStateSha256, status: 'completed', settlement: 'released',
      nativeProcessGone: true, gatewaySettled: true, firstRequestSha256: sha256(probe.firstRequestUtf8),
      normalizedRequestSha256: sha256(probe.normalizedRequestUtf8), startedAt: settled.startedAt, completedAt: settled.completedAt };
    if (!same(settled, wantedSettlement) || !Number.isFinite(Date.parse(settled.startedAt)) || !Number.isFinite(Date.parse(settled.completedAt)) ||
      Date.parse(settled.startedAt) > Date.parse(settled.completedAt) || probe.probeSettledOperationSha256 !== sha256(probe.probeSettledOperationUtf8) ||
      expected.settlementReceiptSha256 !== probe.probeSettledOperationSha256) throw new Error('Owned probe settlement missing or mismatched');
    const wanted = { source: 'native-fresh-persisted-message-projection', logicalManifestFormat,
      runId: expected.runId, actionId: expected.actionId, windowId: expected.windowId,
      parentNativeThreadId: expected.parentThreadId, nativeThreadId: expected.probeThreadId, nativeTurnId: expected.probeTurnId,
      parentStateSha256: expected.parentStateSha256, compactedRecordSha256: p.compactedRecordSha256,
      summarySha256: p.summarySha256, querySha256: p.querySha256, policySha256: p.policySha256,
      collectorSourceSha256: p.collectorSourceSha256, firstRequestSha256: sha256(probe.firstRequestUtf8),
      normalizedRequestSha256: sha256(probe.normalizedRequestUtf8), scopeReceiptSha256: probe.scopeReceiptSha256,
      inputManifestSha256: sha256(stableJson(expected.inputMessageHashes)), envelopeSha256: sha256(stableJson(expected.envelope)),
      settledOperationSha256: probe.probeSettledOperationSha256 };
    if (!same(receipt, wanted) || probe.projectionReceiptSha256 !== sha256(probe.projectionReceiptUtf8) ||
      probe.collectorManifestUtf8 !== p.collectorManifestUtf8 || sha256(probe.collectorManifestUtf8) !== p.collectorSourceSha256 ||
      probe.normalizedSha256 !== sha256(probe.normalizedRequestUtf8) || !same(request.input, p.input) ||
      !same(JSON.parse(probe.normalizedRequestUtf8), p.normalizedRequest)) throw new Error('Fresh capture mismatch');
    return { status: 'PASS', errors: [] };
  } catch { return { status: 'FAIL', errors: ['fresh-projection-full-request-normalization-or-receipt-binding'] }; }
}

export function verifyProbeSeparation(probe, expected = {}) {
  if (!probe) return { status: 'NOT_TESTED', errors: ['compiled-input-and-sandbox-evidence-absent'] };
  if (expected.checkpointValidation && expected.checkpointValidation.status !== 'PASS') return { status: expected.checkpointValidation.status, errors: expected.checkpointValidation.errors };
  const errors = [];
  if (!expected.parentThreadId || !expected.probeThreadId || !expected.probeTurnId ||
    !expected.actionId || !expected.runId) return { status: 'NOT_TESTED', errors: ['independent-native-request-identity-absent'] };
  if (probe.nativeThreadId !== expected.probeThreadId || probe.nativeTurnId !== expected.probeTurnId ||
    probe.nativeThreadId === expected.parentThreadId || probe.parentNativeThreadId !== expected.parentThreadId ||
    probe.actionId !== expected.actionId || probe.runId !== expected.runId) errors.push('probe-identity-binding');
  if (typeof probe.firstRequestUtf8 !== 'string' || !Array.isArray(expected.inputMessageHashes)) return {
    status: errors.length ? 'FAIL' : 'NOT_TESTED', errors: [...errors, 'independent-first-request-bytes-or-manifest-absent'] };
  const scope = scopeProof(probe, expected.probeThreadId, expected.probeTurnId, expected.actionId, expected.allowedTools ?? [], expected);
  if (scope.status !== 'PASS') return { ...scope, status: errors.length ? 'FAIL' : scope.status, errors: [...errors, ...scope.errors] };
  const parent = probe.parentStateAfter;
  if (!parent || typeof parent.stateUtf8 !== 'string' || !expected.parentStateSha256) return { status: errors.length ? 'FAIL' : 'NOT_TESTED', errors: [...errors, 'post-probe-parent-checkpoint-capture-absent'] };
  if (parent.capturedBy !== 'host' || parent.nativeThreadId !== expected.parentThreadId ||
    parent.stateSha256 !== sha256(parent.stateUtf8) || parent.stateSha256 !== expected.parentStateSha256 ||
    !/^[a-f0-9]{64}$/.test(parent.receiptSha256 ?? '')) errors.push('probe-answer-contaminated-parent');
  if (expected.freshProjection) {
    const proof = stateReceiptProof(parent);
    if (proof.status !== 'PASS') return { status: errors.length ? 'FAIL' : proof.status, errors: [...errors, ...proof.errors] };
  }
  let request;
  try { request = JSON.parse(probe.firstRequestUtf8); } catch { errors.push('invalid-first-request'); }
  if (probe.captureSha256 !== sha256(probe.firstRequestUtf8)) errors.push('first-request-hash');
  if (!object(expected.envelope) || !Array.isArray(expected.toolDefinitions)) return { status: errors.length ? 'FAIL' : 'NOT_TESTED', errors: [...errors, 'independent-frozen-request-envelope-absent'] };
  // All fields besides input/tools are bound, including instructions, metadata,
  // history links and every future/unknown field. Nothing is silently ignored.
  const envelope = object(request) ? Object.fromEntries(Object.entries(request).filter(([k]) => !['input', 'tools'].includes(k))) : null;
  if (!exactKeys(envelope, Object.keys(expected.envelope)) || Object.entries(expected.envelope).some(([k, v]) => !same(envelope?.[k], v))) errors.push('unapproved-request-envelope');
  try {
    const input = normalizeNativeInput(request?.input);
    if (!same(input.map((m) => sha256(stableJson(m))), expected.inputMessageHashes)) errors.push('unexpected-probe-input');
  } catch { errors.push('unqualified-typed-native-input'); }
  if (!same(request?.tools, expected.toolDefinitions)) errors.push('unapproved-tool-definition');
  const tools = Array.isArray(request?.tools) ? request.tools.map((t) => t?.name ?? t?.function?.name) : null;
  if (!same(tools, expected.allowedTools ?? [])) errors.push('unexpected-probe-tools');
  if (scope.observedModelScope ? probe.networkPolicy !== 'gateway-only' || !same(probe.modelFileTools, []) :
    probe.filesDenied !== true || probe.networkDenied !== true || !Array.isArray(probe.accessiblePaths) || probe.accessiblePaths.length ||
    probe.answerKeyExposed !== false || probe.parentHistoryExposed !== false) errors.push('probe-source-contamination');
  if (probe.capturedBy !== 'host' || !/^[a-f0-9]{64}$/.test(probe.captureSha256 ?? '') ||
    probe.contextSha256 !== expected.contextSha256) errors.push('unqualified-summary-context');
  if (expected.freshProjection) {
    const projection = verifyFreshProjectionCapture(probe, expected);
    if (projection.status !== 'PASS') return { status: errors.length ? 'FAIL' : projection.status, errors: [...errors, ...projection.errors] };
  } else if (!/^[a-f0-9]{64}$/.test(probe.qualifiedForkReceiptSha256 ?? '')) errors.push('unqualified-summary-context');
  return { status: errors.length ? 'FAIL' : 'PASS', errors, firstRequestSha256: sha256(probe.firstRequestUtf8),
    inputManifestSha256: sha256(stableJson(expected.inputMessageHashes)), scopeReceiptSha256: scope.scopeReceiptSha256 };
}

export function verifySummaryIsolation(probe, expected) {
  const separation = verifyProbeSeparation(probe, expected);
  if (separation.status !== 'PASS') return separation;
  const errors = [];
  const observedScope = (() => { try { return JSON.parse(probe.scopeReceiptUtf8).source === 'h041-observed-model-scope'; } catch { return false; } })();
  if (probe.toolsDenied !== true || (!observedScope && (probe.filesDenied !== true || probe.networkDenied !== true)) ||
    !Array.isArray(probe.toolCalls) || probe.toolCalls.length ||
    (!observedScope && (!Array.isArray(probe.accessiblePaths) || probe.accessiblePaths.length)) ||
    !Array.isArray(probe.originalRecordIds) || probe.originalRecordIds.length ||
    (!observedScope && (probe.answerKeyExposed !== false || probe.parentHistoryExposed !== false))) errors.push('summary-contamination');
  if (probe.inputReceiptSha256 !== sha256(probe.firstRequestUtf8)) errors.push('probe-input-receipt-mismatch');
  return { ...separation, status: errors.length ? 'FAIL' : 'PASS', errors };
}

export function durableHoldouts(truth, cycle) {
  return activeFacts(truth, cycle).filter((f) => ['schema', 'temperature_range', 'manifest_format'].includes(f.id))
    .map((f) => ({ id: f.id, value: f.current.value }));
}

// This is a separate qualified probe branch, leaving the original continuing
// thread and the summary-only probe unchanged. These fields are host evidence,
// never model-produced assertions or answer-file duplicates.
export function verifyDurableHoldout(truth, cycle, evidence, expected) {
  const observed = typeof evidence?.scopeReceiptUtf8 === 'string' && (()=>{try{return JSON.parse(evidence.scopeReceiptUtf8).source==='h041-observed-model-scope';}catch{return false;}})();
  if (observed) {
    const scope=verifyObservedModelScope(evidence,expected);if(scope.status!=='PASS')return scope;
    try {if(evidence.compiledContextText!==stableJson(JSON.parse(evidence.firstRequestUtf8)))return {status:'FAIL',errors:['whole_holdout_request_not_bound']};}catch{return {status:'FAIL',errors:['holdout_raw_request_invalid']};}
  }
  if (!evidence) return { status: 'NOT_TESTED', errors: ['durable-holdout-context-capture-absent'] };
  const errors = [];
  const holdouts = durableHoldouts(truth, cycle);
  if (evidence.capturedBy !== 'host' || typeof evidence.compiledContextText !== 'string' ||
    evidence.contextSha256 !== sha256(evidence.compiledContextText ?? '') ||
    !/^[a-f0-9]{64}$/.test(evidence.qualifiedProjectionReceiptSha256 ?? '')) errors.push('unqualified-holdout-context');
  if (!same(evidence.omittedFactIds, holdouts.map((f) => f.id)) ||
    holdouts.some((f) => typeof evidence.compiledContextText === 'string' && evidence.compiledContextText.includes(f.value))) errors.push('holdout-value-present');
  if (!observed && (evidence.answerKeyExposed !== false || evidence.parentHistoryExposed !== false ||
    !Array.isArray(evidence.accessiblePaths) || evidence.accessiblePaths.length)) errors.push('holdout-source-contamination');
  return { status: errors.length ? 'FAIL' : 'PASS', errors };
}

// First-request capture is private. An ID difference alone is deliberately insufficient.
export function verifyCleanChild(probe, approved = {}) {
  if (!probe || !Array.isArray(probe.compiledMessages)) return { status: 'NOT_TESTED', errors: ['child-first-request-capture-absent'] };
  if (!Array.isArray(approved.messageHashes) || !approved.messageHashes.length || !approved.parentCanary || !approved.childNonce) return { status: 'NOT_TESTED', errors: ['independent-minimal-brief-manifest-absent'] };
  if(approved.requireNativeDelegation){const lineage=verifyChildLineage(probe.nativeLineage,{parentId:approved.parentThreadId,childId:probe.childId,firstDispatchAt:probe.firstDispatchAt});if(lineage.status!=='PASS')return lineage;}
  const placement = probe.parentPlacement;
  if (!placement || typeof placement.stateUtf8 !== 'string') return { status: 'NOT_TESTED', errors: ['parent-canary-placement-not-captured'] };
  if (typeof probe.firstRequestUtf8 !== 'string') return { status: 'NOT_TESTED', errors: ['child-provider-request-bytes-absent'] };
  const scope = scopeProof(probe, probe.childId, probe.nativeTurnId, probe.actionId, [], { ...approved, probeThreadId: probe.childId, probeTurnId: probe.nativeTurnId, actionId: probe.actionId });
  if (scope.status !== 'PASS') return scope;
  const errors = [];
  let wire;
  try { wire = JSON.parse(probe.firstRequestUtf8); } catch { errors.push('invalid-child-first-request'); }
  try {
    const messages = normalizeNativeInput(wire?.input);
    const envelope = Object.fromEntries(Object.entries(wire).filter(([k]) => !['input', 'tools'].includes(k)));
    if (!object(approved.envelope)) return { status: 'NOT_TESTED', errors: ['independent-child-request-envelope-absent'] };
    if (probe.captureSha256 !== sha256(probe.firstRequestUtf8) || !same(messages, probe.compiledMessages) || !same(wire.tools, []) ||
      !exactKeys(envelope, Object.keys(approved.envelope)) || Object.entries(approved.envelope).some(([k,v]) => !same(envelope[k],v))) errors.push('child-provider-request-binding');
  } catch { errors.push('unqualified-child-native-input'); }
  if (placement.capturedBy !== 'host' || placement.nativeThreadId !== approved.parentThreadId ||
    placement.stateSha256 !== sha256(placement.stateUtf8) || !placement.stateUtf8.includes(approved.parentCanary) ||
    !/^[a-f0-9]{64}$/.test(placement.receiptSha256 ?? '')) errors.push('parent-canary-placement-invalid');
  if (probe.capturedBy !== 'host' || !probe.firstRequestId || probe.parentId !== approved.parentThreadId || !probe.childId || probe.parentId === probe.childId) errors.push('child-identity');
  if (!probe.compiledMessages.length) errors.push('minimal-brief-manifest-absent');
  const hashes = probe.compiledMessages.map((m) => sha256(stableJson(m)));
  if (!same(hashes, approved.messageHashes)) errors.push('unexpected-child-context');
  if (probe.compiledMessages.some((m) => stableJson(m).includes(approved.parentCanary)) || stableJson(probe.reply).includes(approved.parentCanary)) errors.push('parent-canary-leak');
  if (!Array.isArray(probe.tools) || probe.tools.length || (!scope.observedModelScope && (!Array.isArray(probe.accessiblePaths) || probe.accessiblePaths.length))) errors.push('child-retrieval-leak');
  if (!exactKeys(probe.reply, ['childNonce', 'parentCanary']) || probe.reply.childNonce !== approved.childNonce || probe.reply.parentCanary !== 'UNKNOWN') errors.push('child-negative-control');
  return { status: errors.length ? 'FAIL' : 'PASS', errors, firstRequestMessageHashes: hashes,
    firstRequestSha256: sha256(probe.firstRequestUtf8), inputManifestSha256: sha256(stableJson(approved.messageHashes)), scopeReceiptSha256: scope.scopeReceiptSha256 };
}

export function verifyColdResume(evidence, checkpoint, expected = {}) {
  if (!evidence || typeof evidence.afterStateUtf8 !== 'string' || typeof checkpoint?.stateUtf8 !== 'string') return { status: 'NOT_TESTED', errors: ['actual-restart-and-persisted-history-capture-absent'] };
  const errors = [];
  if (checkpoint.capturedBy !== 'host' || checkpoint.stateSha256 !== sha256(checkpoint.stateUtf8) ||
    evidence.capturedBy !== 'host' || !evidence.beforeProcessId || !evidence.afterProcessId || evidence.beforeProcessId === evidence.afterProcessId ||
    evidence.nativeThreadId !== checkpoint.nativeThreadId || evidence.beforeStateSha256 !== checkpoint.stateSha256 ||
    sha256(evidence.afterStateUtf8) !== checkpoint.stateSha256 || !Array.isArray(evidence.replayedActionIds) || evidence.replayedActionIds.length ||
    !/^[a-f0-9]{64}$/.test(evidence.receiptSha256 ?? '')) errors.push('restart-or-no-replay-unproven');
  if (expected.requireHostRestart) {
    const stateProof = stateReceiptProof(checkpoint);
    if (stateProof.status !== 'PASS') return { status: errors.length ? 'FAIL' : stateProof.status, errors: [...errors, ...stateProof.errors] };
    if (![expected.runId, expected.actionId, expected.windowId].every((v) => typeof v === 'string' && v.length > 0)) return { status: errors.length ? 'FAIL' : 'NOT_TESTED', errors: [...errors, 'independent-restart-operation-window-absent'] };
    if (typeof evidence.restartReceiptUtf8 !== 'string') return { status: errors.length ? 'FAIL' : 'NOT_TESTED', errors: [...errors, 'actual-owned-application-restart-receipt-absent'] };
    try {
      const r = JSON.parse(evidence.restartReceiptUtf8);
      if(expected.requireActualProcess&&r.format!=='h041-actual-process-restart-v1')errors.push('actual-os-process-restart-format-required');
      if(r.format==='h041-actual-process-restart-v1') {
        const process=JSON.parse(r.processRestartReceiptUtf8),state=JSON.parse(r.afterParentStateReceiptUtf8);
        const identity=p=>`${p.bootId}:${p.pid}:${p.startTicks}`;
        if(sha256(r.processRestartReceiptUtf8)!==r.processRestartReceiptSha256||sha256(r.afterParentStateReceiptUtf8)!==r.afterParentStateReceiptSha256||process.source!=='owned-application-process-restart'||process.runId!==expected.runId||process.actionId!==expected.actionId||process.windowId!==expected.windowId||process.oldExit?.code!==0||process.oldExit?.signal!==null||process.before?.source!=='linux-proc'||process.after?.source!=='linux-proc'||identity(process.before)!==evidence.beforeProcessId||identity(process.after)!==evidence.afterProcessId||state.source!=='owned-native-persisted-state'||state.nativeThreadId!==checkpoint.nativeThreadId||state.stateSha256!==checkpoint.stateSha256||process.checkpointStateSha256!==checkpoint.stateSha256)errors.push('actual-process-and-after-state-producer-binding');
        const oldClose=JSON.parse(process.oldCloseReceiptUtf8);
        if(oldClose.source!=='native-acceptance-run-close'||oldClose.status!=='released'||oldClose.runId!==expected.runId||oldClose.operationWindowId!==expected.windowId||oldClose.outstandingOwnedActions?.length!==0||oldClose.unconfirmedOwnedActions?.length!==0||!oldClose.producers?.length)errors.push('actual-old-producer-settlement-absent');
      }
      if (r.source !== 'native-owned-host-cold-resume' || r.runId !== expected.runId || r.actionId !== expected.actionId || r.windowId !== expected.windowId ||
        r.nativeThreadId !== checkpoint.nativeThreadId || r.checkpointStateSha256 !== checkpoint.stateSha256 ||
        !r.beforeHostId || !r.afterHostId || r.beforeHostId === r.afterHostId ||
        r.beforeApplicationProcessId !== evidence.beforeProcessId || r.afterApplicationProcessId !== evidence.afterProcessId ||
        r.oldApplicationExitConfirmed !== true || r.oldGatewaySettled !== true || r.noActionReplay !== true || r.capturedAfterRestart !== true ||
        evidence.restartReceiptSha256 !== sha256(evidence.restartReceiptUtf8)) errors.push('application-restart-lifecycle-binding');
    } catch { errors.push('invalid-application-restart-receipt'); }
  }
  return { status: errors.length ? 'FAIL' : 'PASS', errors };
}

// Retain the original E collector's byte-domain receipt independently of the
// semantic JSON hashes. Binding values come from the owned operation and the
// independently captured latest checkpoint, never from after-restart bytes.
export function captureAcceptedArtifactBaseline(observation, checkpoint, expected) {
  if (typeof observation?.artifactReceiptUtf8 !== 'string' || !observation.artifactReceiptSha256 ||
    ![expected?.runId, expected?.sessionId, expected?.actionId, expected?.nativeThreadId, observation.runId].every((v) => typeof v === 'string' && v.length))
    return { status: 'NOT_TESTED', errors: ['original-owned-artifact-receipt-or-bindings-absent'] };
  const state = stateReceiptProof(checkpoint);
  if (state.status !== 'PASS') return state;
  try {
    const receipt = JSON.parse(observation.artifactReceiptUtf8);
    if (receipt.source !== 'owned-store-registered-continuation-artifacts' || receipt.sessionId !== expected.sessionId ||
      receipt.runId !== observation.runId || observation.sessionId !== expected.sessionId || observation.actionId !== expected.actionId ||
      observation.nativeThreadId !== expected.nativeThreadId || checkpoint.nativeThreadId !== expected.nativeThreadId ||
      observation.parentState?.stateSha256 !== checkpoint.stateSha256 || observation.artifactReceiptSha256 !== sha256(observation.artifactReceiptUtf8) ||
      !Array.isArray(receipt.artifacts) || receipt.artifacts.length !== 2) throw new Error('Original artifact ownership mismatch');
    const artifacts = Object.fromEntries(receipt.artifacts.map((r) => [r.name, r]));
    if (!exactKeys(artifacts, ['sensor-policy.json', 'engineering-calculation.json']) || receipt.artifacts.some((r) =>
      r.runId !== observation.runId || ![r.artifactId, r.messageId, r.captureId].every((v) => typeof v === 'string' && v.length) ||
      !Number.isSafeInteger(r.bytes) || r.bytes < 1 || r.bytes > 1048576 || !/^[a-f0-9]{64}$/.test(r.sha256 ?? '')))
      throw new Error('Original raw artifact receipt mismatch');
    return { status: 'PASS', errors: [], baseline: { acceptanceRunId: expected.runId, sessionId: expected.sessionId,
      storeRunId: observation.runId, actionId: expected.actionId, nativeThreadId: expected.nativeThreadId,
      checkpointStateSha256: checkpoint.stateSha256, artifactReceiptUtf8: observation.artifactReceiptUtf8,
      artifactReceiptSha256: observation.artifactReceiptSha256, artifactReceiptBytes: Buffer.byteLength(observation.artifactReceiptUtf8, 'utf8'), artifacts } };
  } catch { return { status: 'FAIL', errors: ['original-continuation-artifact-receipt-binding'] }; }
}

export function verifyAcceptedContinuationResume(result, accepted, expected) {
  if (!accepted?.checkpoint || !accepted.artifactHashes || !accepted.actionId)
    return { status: 'NOT_TESTED', errors: ['independently-accepted-latest-continuation-checkpoint-absent'] };
  if (accepted.artifactBaselineStatus?.status === 'FAIL') return accepted.artifactBaselineStatus;
  const baseline = accepted.artifactBaseline;
  if (!baseline) return { status: 'NOT_TESTED', errors: ['original-accepted-raw-artifact-baseline-absent'] };
  const original = captureAcceptedArtifactBaseline({ artifactReceiptUtf8: baseline.artifactReceiptUtf8,
    artifactReceiptSha256: baseline.artifactReceiptSha256, sessionId: baseline.sessionId, runId: baseline.storeRunId,
    actionId: accepted.actionId, nativeThreadId: accepted.checkpoint.nativeThreadId, parentState: accepted.checkpoint },
    accepted.checkpoint, { runId: expected.runId, sessionId: baseline.sessionId, actionId: accepted.actionId, nativeThreadId: accepted.checkpoint.nativeThreadId });
  if (original.status !== 'PASS') return original;
  if (!same(original.baseline, baseline)) return { status: 'FAIL', errors: ['accepted-original-artifact-baseline-substituted'] };
  const restart = verifyColdResume(result.restartEvidence, accepted.checkpoint, { ...expected, requireHostRestart: true });
  if (restart.status !== 'PASS') return restart;
  if (typeof result.artifactReceiptUtf8 !== 'string') return { status: 'NOT_TESTED', errors: ['actual-restarted-workspace-artifact-bytes-absent'] };
  try {
    const lifecycle = JSON.parse(result.restartEvidence.restartReceiptUtf8), capture = JSON.parse(result.artifactReceiptUtf8);
    if (lifecycle.acceptedContinuationActionId !== accepted.actionId || !same(lifecycle.acceptedArtifactHashes, accepted.artifactHashes) ||
      capture.source !== 'native-owned-workspace-artifacts' || capture.nativeThreadId !== accepted.checkpoint.nativeThreadId ||
      capture.runId !== expected.runId || capture.sessionId !== baseline.sessionId || capture.actionId !== expected.actionId ||
      capture.windowId !== expected.windowId || capture.afterHostId !== lifecycle.afterHostId ||
      capture.acceptedArtifactReceiptSha256 !== baseline.artifactReceiptSha256 || capture.acceptedArtifactReceiptBytes !== baseline.artifactReceiptBytes ||
      capture.acceptedStoreRunId !== baseline.storeRunId || capture.acceptedContinuationActionId !== accepted.actionId ||
      capture.checkpointStateSha256 !== accepted.checkpoint.stateSha256 || typeof capture.captureId !== 'string' || !capture.captureId ||
      result.artifactReceiptSha256 !== sha256(result.artifactReceiptUtf8) || !exactKeys(capture.artifactUtf8, ['sensor-policy.json', 'engineering-calculation.json']) ||
      !exactKeys(result.artifacts, ['sensor-policy.json', 'engineering-calculation.json'])) throw new Error('Continuation artifact ownership mismatch');
    for (const [name, bytes] of Object.entries(capture.artifactUtf8)) {
      if (typeof bytes !== 'string' || !same(JSON.parse(bytes), result.artifacts[name]) ||
        sha256(bytes) !== baseline.artifacts[name].sha256 || Buffer.byteLength(bytes, 'utf8') !== baseline.artifacts[name].bytes ||
        sha256(stableJson(JSON.parse(bytes))) !== accepted.artifactHashes[name]) throw new Error('Accepted artifact changed or substituted');
    }
    return { status: 'PASS', errors: [] };
  } catch { return { status: 'FAIL', errors: ['latest-continuation-resume-artifact-or-lifecycle-binding'] }; }
}

export function continuationRequest() {
  return {
    task: 'Create sensor-policy.json and engineering-calculation.json using the current accepted project state. Do not run a bench test or grant deployment. Configuration must use the most recent pin map and limits. Compute nominal LED branch current and resistor power, and divider voltage at maximum permitted input. Use all SI units shown below.',
    artifacts: {
      'sensor-policy.json': ['boardRevision', 'i2c:{sda,scl,address,speed}', 'uart:{tx,rx,de,baud,format}', 'adc:{pin,top,bottom,limit}', 'samplePeriod', 'watchdog', 'deployment', 'benchCheck'],
      'engineering-calculation.json': ['ledCurrent:{value,unit:A}', 'resistorPower:{value,unit:W}', 'maximumAdcVoltage:{value,unit:V}', 'adcWithinLimit:boolean'],
    },
  };
}

export function scoreContinuation(truth, cycle, artifacts) {
  const values = Object.fromEntries(activeFacts(truth, cycle).map((f) => [f.id, f.current.value]));
  const expectedPolicy = {
    boardRevision: values.board_revision,
    i2c: { sda: values.i2c_sda, scl: values.i2c_scl, address: values.i2c_address, speed: values.i2c_speed },
    uart: { tx: values.uart_tx, rx: values.uart_rx, de: values.uart_de, baud: values.uart_baud, format: values.uart_format },
    adc: { pin: values.adc_pin, top: values.divider_top, bottom: values.divider_bottom, limit: values.adc_limit },
    samplePeriod: values.sample_period, watchdog: values.watchdog,
    deployment: values.deployment_permission, benchCheck: values.bench_status,
  };
  // Decimal SI conversions and circuit equations are independent of the generated artifact.
  const number = (id) => Number(values[id].split(' ')[0]);
  const delta = number('logic_rail') - number('led_drop');
  const current = delta / number('led_resistor');
  const power = delta * delta / number('led_resistor');
  const adc = number('supply_max') * number('divider_bottom') / (number('divider_top') + number('divider_bottom'));
  const errors = [];
  if (!exactKeys(artifacts, ['sensor-policy.json', 'engineering-calculation.json'])) errors.push('artifact-envelope');
  const policy = artifacts?.['sensor-policy.json'];
  // Property order does not change the meaning of a JSON configuration.
  const canonical = (v) => Array.isArray(v) ? v.map(canonical) : object(v) ? Object.fromEntries(Object.keys(v).sort().map((k) => [k, canonical(v[k])])) : v;
  if (!same(canonical(policy), canonical(expectedPolicy))) errors.push('policy-state');
  const calculation = artifacts?.['engineering-calculation.json'];
  if (!exactKeys(calculation, ['ledCurrent', 'resistorPower', 'maximumAdcVoltage', 'adcWithinLimit'])) errors.push('calculation-shape');
  for (const [key, value, unit] of [['ledCurrent', current, 'A'], ['resistorPower', power, 'W'], ['maximumAdcVoltage', adc, 'V']]) {
    const actual = calculation?.[key];
    if (!exactKeys(actual, ['value', 'unit']) || actual.unit !== unit || !Number.isFinite(actual.value) || Math.abs(actual.value - value) > 1e-9) errors.push(`calculation:${key}`);
  }
  if (calculation?.adcWithinLimit !== (adc <= number('adc_limit'))) errors.push('adc-limit');
  return { status: errors.length ? 'FAIL' : 'PASS', errors, cycle, mode: 'continuation' };
}
