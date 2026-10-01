import { createHash } from 'node:crypto';
import { readFile } from 'node:fs/promises';

export const sha256 = (bytes) => createHash('sha256').update(bytes).digest('hex');
export const stableJson = (value) => JSON.stringify(value);
export const actionIdFor = (runId, cycle, operation) => `h039-${sha256(runId).slice(0, 24)}-c${cycle}-${operation}`;
export const loadJson = async (path) => JSON.parse(await readFile(path, 'utf8'));
const object = (v) => v !== null && typeof v === 'object' && !Array.isArray(v);
const same = (a, b) => stableJson(a) === stableJson(b);
const exactKeys = (v, keys) => object(v) && same(Object.keys(v).sort(), [...keys].sort());

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

export function extractCheckpoint(checkpoint, expected) {
  const baseline = expected.baseline;
  if (!checkpoint || typeof checkpoint.stateUtf8 !== 'string' || typeof checkpoint.compactedRecordUtf8 !== 'string' ||
    typeof checkpoint.bindingReceiptUtf8 !== 'string' || typeof checkpoint.settledOperationUtf8 !== 'string' ||
    !baseline || typeof baseline.stateUtf8 !== 'string' || !expected.nativeTurnId || !expected.windowId)
    return { status: 'NOT_TESTED', errors: ['full-state-baseline-owned-record-or-settled-operation-absent'] };
  if (!['system', 'developer', 'user', 'assistant'].includes(expected.summaryRole)) return { status: 'NOT_TESTED', errors: ['pinned-native-summary-role-unqualified'] };
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
    const index = records.findLastIndex((record) => record.type === 'compacted');
    const baselineRecords = baseline.stateUtf8.slice(0, -1).split('\n').length;
    if (index < baselineRecords || lines[index] + '\n' !== checkpoint.compactedRecordUtf8 ||
      checkpoint.compactedRecordSha256 !== recordHash) throw new Error('Selected record is not latest surviving post-baseline compaction');
    if (binding.source !== 'native-rollout-record-owner' || binding.nativeThreadId !== expected.parentThreadId ||
      binding.compactionActionId !== expected.actionId || binding.nativeTurnId !== expected.nativeTurnId ||
      binding.windowId !== expected.windowId || binding.recordSha256 !== recordHash || binding.stateSha256 !== stateHash ||
      !binding.recordId || !binding.sourceRef || checkpoint.bindingReceiptSha256 !== sha256(checkpoint.bindingReceiptUtf8)) throw new Error('Record owner mismatch');
    const timestamp = Date.parse(records[index].timestamp), started = Date.parse(settled.startedAt), completed = Date.parse(settled.completedAt);
    if (settled.source !== 'native-compaction-settlement' || settled.status !== 'completed' || settled.settlement !== 'released' ||
      settled.nativeThreadId !== expected.parentThreadId || settled.actionId !== expected.actionId || settled.nativeTurnId !== expected.nativeTurnId ||
      settled.windowId !== expected.windowId || settled.baselineStateSha256 !== baseline.stateSha256 || settled.postStateSha256 !== stateHash ||
      settled.recordSha256 !== recordHash || !settled.compactionId || !Number.isFinite(timestamp) || !Number.isFinite(started) || !Number.isFinite(completed) ||
      started > timestamp || timestamp > completed || checkpoint.settledOperationSha256 !== sha256(checkpoint.settledOperationUtf8)) throw new Error('Actual settled operation/window/turn binding mismatch');
    const record = records[index];
    if (!object(record.payload) || typeof record.payload.message !== 'string' || !record.payload.message.trim()) throw new Error('Invalid native summary');
    // NEVER project replacement_history: pinned native may retain original user text there.
    const messages = [{ role: expected.summaryRole, content: record.payload.message }];
    if (checkpoint.messages !== undefined && !same(checkpoint.messages, messages)) throw new Error('Independent adapter messages rejected');
    return { status: 'PASS', errors: [], messages, stateSha256: stateHash, compactedRecordSha256: recordHash };
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

function scopeProof(probe, threadId, turnId, actionId, tools) {
  if (typeof probe.scopeReceiptUtf8 !== 'string') return { status: 'NOT_TESTED', errors: ['effective-native-scope-receipt-absent'] };
  let scope;
  try { scope = JSON.parse(probe.scopeReceiptUtf8); } catch { return { status: 'FAIL', errors: ['invalid-scope-receipt'] }; }
  const valid = scope.source === 'native-launcher-effective-scope' && scope.nativeThreadId === threadId && scope.nativeTurnId === turnId &&
    scope.actionId === actionId && same(scope.allowedTools, tools) && same(scope.readRoots, []) && same(scope.writeRoots, []) &&
    scope.network === 'deny' && scope.answerKeyMounted === false && probe.scopeReceiptSha256 === sha256(probe.scopeReceiptUtf8);
  return { status: valid ? 'PASS' : 'FAIL', errors: valid ? [] : ['scope-receipt-binding'], scopeReceiptSha256: sha256(probe.scopeReceiptUtf8) };
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
  const scope = scopeProof(probe, expected.probeThreadId, expected.probeTurnId, expected.actionId, expected.allowedTools ?? []);
  if (scope.status !== 'PASS') return { ...scope, status: errors.length ? 'FAIL' : scope.status, errors: [...errors, ...scope.errors] };
  const parent = probe.parentStateAfter;
  if (!parent || typeof parent.stateUtf8 !== 'string' || !expected.parentStateSha256) return { status: errors.length ? 'FAIL' : 'NOT_TESTED', errors: [...errors, 'post-probe-parent-checkpoint-capture-absent'] };
  if (parent.capturedBy !== 'host' || parent.nativeThreadId !== expected.parentThreadId ||
    parent.stateSha256 !== sha256(parent.stateUtf8) || parent.stateSha256 !== expected.parentStateSha256 ||
    !/^[a-f0-9]{64}$/.test(parent.receiptSha256 ?? '')) errors.push('probe-answer-contaminated-parent');
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
  if (probe.filesDenied !== true || probe.networkDenied !== true ||
    !Array.isArray(probe.accessiblePaths) || probe.accessiblePaths.length ||
    probe.answerKeyExposed !== false || probe.parentHistoryExposed !== false) errors.push('probe-source-contamination');
  if (probe.capturedBy !== 'host' || !/^[a-f0-9]{64}$/.test(probe.captureSha256 ?? '') ||
    probe.contextSha256 !== expected.contextSha256 || !probe.qualifiedForkReceiptSha256 ||
    !/^[a-f0-9]{64}$/.test(probe.qualifiedForkReceiptSha256)) errors.push('unqualified-summary-context');
  return { status: errors.length ? 'FAIL' : 'PASS', errors, firstRequestSha256: sha256(probe.firstRequestUtf8),
    inputManifestSha256: sha256(stableJson(expected.inputMessageHashes)), scopeReceiptSha256: scope.scopeReceiptSha256 };
}

export function verifySummaryIsolation(probe, expected) {
  const separation = verifyProbeSeparation(probe, expected);
  if (separation.status !== 'PASS') return separation;
  const errors = [];
  if (probe.toolsDenied !== true || probe.filesDenied !== true || probe.networkDenied !== true ||
    !Array.isArray(probe.toolCalls) || probe.toolCalls.length ||
    !Array.isArray(probe.accessiblePaths) || probe.accessiblePaths.length ||
    !Array.isArray(probe.originalRecordIds) || probe.originalRecordIds.length ||
    probe.answerKeyExposed !== false || probe.parentHistoryExposed !== false) errors.push('summary-contamination');
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
export function verifyDurableHoldout(truth, cycle, evidence) {
  if (!evidence) return { status: 'NOT_TESTED', errors: ['durable-holdout-context-capture-absent'] };
  const errors = [];
  const holdouts = durableHoldouts(truth, cycle);
  if (evidence.capturedBy !== 'host' || typeof evidence.compiledContextText !== 'string' ||
    evidence.contextSha256 !== sha256(evidence.compiledContextText ?? '') ||
    !/^[a-f0-9]{64}$/.test(evidence.qualifiedProjectionReceiptSha256 ?? '')) errors.push('unqualified-holdout-context');
  if (!same(evidence.omittedFactIds, holdouts.map((f) => f.id)) ||
    holdouts.some((f) => typeof evidence.compiledContextText === 'string' && evidence.compiledContextText.includes(f.value))) errors.push('holdout-value-present');
  if (evidence.answerKeyExposed !== false || evidence.parentHistoryExposed !== false ||
    !Array.isArray(evidence.accessiblePaths) || evidence.accessiblePaths.length) errors.push('holdout-source-contamination');
  return { status: errors.length ? 'FAIL' : 'PASS', errors };
}

// First-request capture is private. An ID difference alone is deliberately insufficient.
export function verifyCleanChild(probe, approved = {}) {
  if (!probe || !Array.isArray(probe.compiledMessages)) return { status: 'NOT_TESTED', errors: ['child-first-request-capture-absent'] };
  if (!Array.isArray(approved.messageHashes) || !approved.messageHashes.length || !approved.parentCanary || !approved.childNonce) return { status: 'NOT_TESTED', errors: ['independent-minimal-brief-manifest-absent'] };
  const placement = probe.parentPlacement;
  if (!placement || typeof placement.stateUtf8 !== 'string') return { status: 'NOT_TESTED', errors: ['parent-canary-placement-not-captured'] };
  if (typeof probe.firstRequestUtf8 !== 'string') return { status: 'NOT_TESTED', errors: ['child-provider-request-bytes-absent'] };
  const scope = scopeProof(probe, probe.childId, probe.nativeTurnId, probe.actionId, []);
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
  if (!Array.isArray(probe.tools) || probe.tools.length || !Array.isArray(probe.accessiblePaths) || probe.accessiblePaths.length) errors.push('child-retrieval-leak');
  if (!exactKeys(probe.reply, ['childNonce', 'parentCanary']) || probe.reply.childNonce !== approved.childNonce || probe.reply.parentCanary !== 'UNKNOWN') errors.push('child-negative-control');
  return { status: errors.length ? 'FAIL' : 'PASS', errors, firstRequestMessageHashes: hashes,
    firstRequestSha256: sha256(probe.firstRequestUtf8), inputManifestSha256: sha256(stableJson(approved.messageHashes)), scopeReceiptSha256: scope.scopeReceiptSha256 };
}

export function verifyColdResume(evidence, checkpoint) {
  if (!evidence || typeof evidence.afterStateUtf8 !== 'string' || !checkpoint) return { status: 'NOT_TESTED', errors: ['actual-restart-and-persisted-history-capture-absent'] };
  const errors = [];
  if (evidence.capturedBy !== 'host' || !evidence.beforeProcessId || !evidence.afterProcessId || evidence.beforeProcessId === evidence.afterProcessId ||
    evidence.nativeThreadId !== checkpoint.nativeThreadId || evidence.beforeStateSha256 !== checkpoint.stateSha256 ||
    sha256(evidence.afterStateUtf8) !== checkpoint.stateSha256 || !Array.isArray(evidence.replayedActionIds) || evidence.replayedActionIds.length ||
    !/^[a-f0-9]{64}$/.test(evidence.receiptSha256 ?? '')) errors.push('restart-or-no-replay-unproven');
  return { status: errors.length ? 'FAIL' : 'PASS', errors };
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
