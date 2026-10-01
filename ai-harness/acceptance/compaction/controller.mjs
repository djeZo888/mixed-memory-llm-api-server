import { mkdir, writeFile, chmod, readFile, realpath, stat, readdir } from 'node:fs/promises';
import { dirname, resolve, join, relative, isAbsolute } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { randomUUID } from 'node:crypto';
import { activeFacts, actionIdFor, extractCheckpoint, deriveFreshProjection, validateCollectorManifest, logicalManifestFormat, loadJson, sha256, stableJson, validateCorpus, scoreRecall, verifyRetrieval, verifyProbeSeparation, verifySummaryIsolation, durableHoldouts, verifyDurableHoldout, verifyCleanChild, verifyColdResume, continuationRequest, scoreContinuation, captureAcceptedArtifactBaseline, verifyAcceptedContinuationResume } from './scorer.mjs';
import { absent, metadata, unknownMeasurement, measured, validateRecord } from './evidence.mjs';
import { summarizeQualification } from './qualification.mjs';

const here = dirname(fileURLToPath(import.meta.url));
const repo = resolve(here, '../../..');
const missing = (field) => absent(`${field} not exposed by this observation`);
const id = (value, field) => typeof value === 'string' && value ? metadata(value) : missing(field);
const hashPattern = /^[a-f0-9]{64}$/;
export const projectionTranslatorFiles = ['src/codex-responses.ts', 'src/codex-provider.ts', 'src/errors.ts', 'dist/codex-responses.js', 'dist/codex-provider.js', 'dist/errors.js'];
const outcomeStatus = (outcome) => ['failed', 'cancelled', 'interrupted'].includes(outcome) ? 'FAIL' : 'NOT_TESTED';

export async function fixture() {
  const [corpus, truth, config] = await Promise.all([
    loadJson(join(here, 'fixtures/conversation.json')),
    loadJson(join(here, 'fixtures/ground-truth.json')),
    loadJson(join(here, 'config.json')),
  ]);
  const errors = validateCorpus(corpus, truth);
  if (errors.length) throw new Error(`Invalid corpus: ${errors.join(',')}`);
  const paths = { corpus: 'fixtures/conversation.json', truth: 'fixtures/ground-truth.json', controller: 'controller.mjs', scorer: 'scorer.mjs', evidence: 'evidence.mjs', schema: 'evidence.schema.json', config: 'config.json', qualification: 'qualification.mjs', qualificationSchema: 'qualification.schema.json' };
  const sourceHashes = Object.fromEntries(await Promise.all(Object.entries(paths).map(async ([k, v]) => [k, sha256(await readFile(join(here, v)))])));
  return { corpus, truth, config, sourceHashes };
}

export function recallRequest(truth, cycle, mode) {
  return {
    task: mode === 'summary-only'
      ? 'Recall the accepted project state from the qualified compacted context only. Tools, original records, files, network and the answer key are unavailable. Return the JSON envelope only. Do not guess missing permissions or completed tests.'
      : 'Recover the accepted project state from scoped original records. Cite current authoritative record IDs, not superseded decisions. Return the JSON envelope only. The scorer answer key is unavailable.',
    output: { answers: Object.fromEntries(activeFacts(truth, cycle).map((f) => [f.id, mode === 'summary-only' ? { value: 'EXACT_STRING_OR_UNKNOWN' } : { value: 'EXACT_STRING_OR_UNKNOWN', sourceIds: ['ORIGINAL_RECORD_ID'] }])) },
    questions: activeFacts(truth, cycle).map((f) => ({ id: f.id, question: f.query })),
  };
}

export function actionPlan(config) {
  if (config.profile === 'h040-summary-stage-v1') return { schemaVersion: 1, enabled: config.enabled, profile: config.profile,
    runtime: config.runtime, maximumNativeActions: 9,
    steps: ['runtime', 'open', 'append-cycle-one', 'independent-originals-and-baseline', 'one-manual-compact', 'originals', 'isolated-summary-only', 'originals', 'close'],
    facts: 56, critical: 49, noncritical: 7, fullNativeAcceptance: 'NOT_TESTED',
    omittedMandatoryDimensions: ['cycles-two-and-three', 'durable-retrieval', 'continuation', 'cold-resume', 'clean-child'] };
  return {
    schemaVersion: 1, enabled: config.enabled, runtime: config.runtime,
    adapterInterface: 'h039-compaction-adapter-v1', liveExecution: 'requires external root-reviewed adapter and enabled reviewed config',
    sourceAndAnswerSeparation: 'scorer-private and source-steward must never be mounted in any model workspace',
    steps: config.cycles.flatMap((cycle) => [
      { cycle, action: 'append-conversation-delta', tools: [] },
      { cycle, action: 'compact', trigger: 'manual', actionIdPattern: 'h039-<SHA256(runId) first 24 hex>-cN-compact; all action IDs use legal bounded requireId bytes' },
      { cycle, action: 'summary-only', context: 'qualified-fork-of-compacted-context', tools: [], files: [], mergeProbeAnswer: false },
      { cycle, action: 'durable-retrieval', context: 'separate-qualified-holdout-projection-of-same-compacted-context', deliberatelyOmitted: ['schema', ...(cycle >= 2 ? ['temperature_range'] : []), ...(cycle >= 3 ? ['manifest_format'] : [])], tools: ['scoped.read_original_records'], mergeProbeAnswer: false },
      ...(cycle === 3 ? [{ cycle: 3, action: 'cold-resume-and-summary-only-before-continuation', checkpoint: 'current-cycle-3-compacted-state', requires: 'actual restart, persisted history capture and no replay' }] : []),
      { cycle, action: 'continuation', context: 'original-thread-no-probe-answers', outputs: ['sensor-policy.json', 'engineering-calculation.json'] },
    ]).concat([{ cycle: 3, action: 'cold-resume-after-accepted-continuation', requires: 'independent latest continued full state, actual owned application restart and unchanged captured artifact bytes; mandatory for H040 full native acceptance' },
      { cycle: 3, action: 'clean-child-first-request-capture', requires: 'captured parent sentinel placement plus independently approved minimal child input; nonce probe' }]),
    faultMatrix: ['empty-summary', 'truncated-summary', 'invalid-summary', 'timeout', 'cancelled', 'process-death', 'duplicate-action', 'restart', 'missing-usage', 'boundary-admission', 'unattributed-auto-trigger'],
  };
}

// Only these independently approved placeholders can vary with captured native
// identities. Other metadata, instructions and unknown fields remain literal.
export function bindReviewedEnvelope(template, { probeThreadId, probeTurnId }) {
  const envelope = structuredClone(template);
  const bindings = { thread_id: ['@h040:probe-native-thread-id', probeThreadId],
    turn_id: ['@h040:probe-native-turn-id', probeTurnId], root_turn_id: ['@h040:probe-native-turn-id', probeTurnId] };
  for (const [key, [placeholder, value]] of Object.entries(bindings)) {
    if (envelope?.client_metadata?.[key] === placeholder) {
      if (typeof value !== 'string' || !value) throw new Error('Captured native identity absent for reviewed metadata binding');
      envelope.client_metadata[key] = value;
    }
  }
  if (stableJson(envelope)?.includes('@h040:')) throw new Error('Unsupported reviewed metadata placeholder');
  return envelope;
}

function freezeConfig(value) {
  if (value && typeof value === 'object') { for (const v of Object.values(value)) freezeConfig(v); Object.freeze(value); }
  return value;
}
export function settlementReserve(config, qualification) {
  const reserve = qualification === 'native' ? config.review?.nativeSettlementReserveMs ?? 75000 : config.syntheticSettlementReserveMs ?? 5000;
  if (!Number.isInteger(reserve) || reserve < (qualification === 'native' ? 75000 : 1) || reserve > 120000 ||
    (qualification === 'native' && config.nativeSettlementReserveMs !== undefined && config.nativeSettlementReserveMs !== reserve))
    throw new Error('Unreviewed or insufficient settlement reserve');
  return reserve;
}

// Consistency over actual retained close bytes from the trusted owner. It does
// not turn a producer's declared fields into native host attestation.
export function verifyOwnedClose(result, expected) {
  if (![expected?.runId, expected?.operationWindowId].every((v) => typeof v === 'string' && v.length > 0) || !Array.isArray(expected.observedSettlements))
    return { status: 'NOT_TESTED', errors: ['independent-owned-run-close-bindings-absent'] };
  if (typeof result?.closeReceiptUtf8 !== 'string') return { status: 'NOT_TESTED', errors: ['actual-owned-run-close-receipt-absent'] };
  try {
    const receipt = JSON.parse(result.closeReceiptUtf8);
    if (receipt.source !== 'native-acceptance-run-close' || receipt.runId !== expected.runId || receipt.operationWindowId !== expected.operationWindowId ||
      receipt.status !== 'released' || receipt.allOwnedWorkSettled !== true || !Array.isArray(receipt.nativeSettlementReceiptSha256s) ||
      !receipt.nativeSettlementReceiptSha256s.length || receipt.nativeSettlementReceiptSha256s.some((h) => !hashPattern.test(h)) ||
      !Array.isArray(receipt.gatewaySettlementReceiptSha256s) || !receipt.gatewaySettlementReceiptSha256s.length ||
      receipt.gatewaySettlementReceiptSha256s.some((h) => !hashPattern.test(h)) || !Array.isArray(receipt.unconfirmedOwnedActions) || receipt.unconfirmedOwnedActions.length ||
      !Array.isArray(receipt.settledOwnedActions) || expected.observedSettlements.some((s) => !receipt.settledOwnedActions.some((r) => stableJson(r) === stableJson(s))) ||
      result.closeReceiptSha256 !== sha256(result.closeReceiptUtf8) || result.outcome !== 'closed' || result.settlement?.state !== 'released' ||
      result.settlement.receiptSha256 !== sha256(result.closeReceiptUtf8) || result.settlement.automaticReplay !== false)
      throw new Error('Owned close proof mismatch');
    return { status: 'PASS', errors: [] };
  } catch { return { status: 'FAIL', errors: ['owned-close-receipt-or-observed-settlement-binding'] }; }
}

// Resolve existing ancestors to reject outputs through symlinks into the repository.
// Output directories are new, private and exclusive; a prior run is never replayed.
export async function privateDirectory(path) {
  const target = resolve(path);
  let ancestor = target;
  while (true) {
    try { await stat(ancestor); break; } catch (error) {
      if (error.code !== 'ENOENT') throw error;
      if (ancestor === dirname(ancestor)) throw error;
      ancestor = dirname(ancestor);
    }
  }
  const resolvedTarget = resolve(await realpath(ancestor), relative(ancestor, target));
  const distance = relative(await realpath(repo), resolvedTarget);
  if (distance === '' || (!distance.startsWith('..' + '/') && distance !== '..' && !isAbsolute(distance))) throw new Error('Private output must be outside the repository');
  await mkdir(target, { mode: 0o700 });
  await chmod(target, 0o700);
  return target;
}

const privateJson = (path, value) => writeFile(path, stableJson(value) + '\n', { flag: 'wx', mode: 0o600 });

export async function prepare(path) {
  const packet = await fixture();
  const out = await privateDirectory(path);
  for (const child of ['scorer-private', 'source-steward', 'model-input']) await mkdir(join(out, child), { mode: 0o700 });
  await privateJson(join(out, 'scorer-private/ground-truth.json'), packet.truth);
  await privateJson(join(out, 'source-steward/original-records.json'), packet.corpus);
  await privateJson(join(out, 'controller-plan.json'), actionPlan(packet.config));
  await privateJson(join(out, 'source-hashes.json'), packet.sourceHashes);
  for (const cycle of packet.config.cycles) {
    const dir = join(out, 'model-input', `cycle-${cycle}`);
    await mkdir(dir, { mode: 0o700 });
    await privateJson(join(dir, 'conversation-delta.json'), packet.corpus.records.filter((r) => r.cycle === cycle));
    await privateJson(join(dir, 'summary-recall-request.json'), recallRequest(packet.truth, cycle, 'summary-only'));
    await privateJson(join(dir, 'durable-recall-request.json'), recallRequest(packet.truth, cycle, 'durable-retrieval'));
    await privateJson(join(dir, 'continuation-request.json'), continuationRequest());
  }
  return { status: 'PASS', qualification: 'source-preparation-only', out, facts: packet.truth.facts.length,
    nativeAcceptance: 'NOT_TESTED', warning: 'Only conversation deltas enter the main thread. Recall requests enter isolated probes. No answer key or source-steward directory enters a model workspace.' };
}

function originalProof(corpus, cycle, before, after) {
  const manifest = Object.fromEntries(corpus.records.filter((r) => r.cycle <= cycle).map((r) => [r.id, sha256(r.content)]));
  const digest = sha256(stableJson(manifest));
  const matches = (observation) => observation?.capturedBy === 'host' &&
    stableJson(observation.recordHashes) === stableJson(manifest) && hashPattern.test(observation.receiptSha256 ?? '');
  const beforeOk = matches(before), afterOk = matches(after);
  return { beforeSha256: digest, afterSha256: afterOk ? digest : null,
    recoverable: beforeOk && afterOk ? true : null, receiptSha256: afterOk ? after.receiptSha256 : null };
}

export function makeRecord({ packet, runId, cycle, mode, qualification, runtime, observation = {}, compactionObservation, originals, grade, isolation, retrieval }) {
  const compact = compactionObservation ?? observation;
  const missingTokens = () => ({ input: unknownMeasurement('native input usage not emitted'), summary: unknownMeasurement('native summary usage not emitted'), contextAfter: unknownMeasurement('post-action usage awaiting measurement') });
  let status = grade?.status ?? outcomeStatus(observation.outcome);
  const limitations = [];
  if (observation.outcome !== 'completed' && status !== 'FAIL') status = outcomeStatus(observation.outcome);
  if (mode === 'summary-only' || mode === 'cold-resume') {
    if (!isolation || isolation.status === 'NOT_TESTED') { status = status === 'FAIL' ? status : 'NOT_TESTED'; limitations.push('summary isolation evidence absent'); }
    else if (isolation.status === 'FAIL') status = 'FAIL';
  }
  const scores = grade?.critical ? { critical: grade.critical, noncritical: grade.noncritical,
    failures: [...grade.failures.map((f) => `${f.id}:${f.reason}`), ...grade.errors] } : null;
  const record = {
    schemaVersion: 2, logicalManifestFormat, suiteId: packet.config.suiteId, runId, qualification, status, mode, cycle,
    operationWindowId: id(compact.operationWindowId, 'host operation window ID'),
    nativeCompactionWindowId: id(compact.verifierNativeWindowId, 'captured native compaction window ID'),
    runtime: runtime ?? { name: 'codex', version: missing('runtime version'), sourceRevision: missing('source revision'), binarySha256: missing('binary SHA'), model: missing('actual model'), modelRevision: missing('model revision'), tokenizerRevision: missing('tokenizer revision'), promptRevision: 'kpm-technical-v1' },
    sourceHashes: packet.sourceHashes,
    actionId: id(observation.actionId, 'action ID'), nativeThreadId: id(observation.nativeThreadId, 'native thread ID'), nativeTurnId: id(observation.nativeTurnId, 'native turn ID'),
    compactionActionId: id(compact.actionId, 'compaction action ID'), compactionNativeThreadId: id(compact.nativeThreadId, 'compaction thread ID'),
    compactionTokens: compact.tokens ?? missingTokens(), compactionDurationMs: compact.durationMs ?? unknownMeasurement('compaction duration not measured'),
    trigger: compact.trigger ?? { type: 'unknown', evidence: [] },
    tokens: observation.tokens ?? missingTokens(),
    durationMs: observation.durationMs ?? unknownMeasurement('duration not measured'),
    nativeOutcome: observation.outcome ?? 'unknown', scores,
    checks: { status: grade?.status ?? 'NOT_TESTED', errors: [...(grade?.errors ?? []), ...(isolation?.errors ?? [])] },
    artifactHashes: Object.fromEntries(Object.entries(observation.artifacts ?? {}).map(([key, value]) => [key, sha256(stableJson(value))])),
    retrieval: retrieval ?? { used: ['summary-only', 'cold-resume'].includes(mode) ? false : null, callIds: [], sourceIds: [], traceSha256: null },
    isolation: { status: isolation?.status ?? 'NOT_APPLICABLE', receiptSha256: observation.isolation?.captureSha256 ?? null,
      firstRequestSha256: isolation?.firstRequestSha256 ?? null, inputManifestSha256: isolation?.inputManifestSha256 ?? null,
      scopeReceiptSha256: isolation?.scopeReceiptSha256 ?? null,
      nativeThreadId: observation.isolation?.nativeThreadId ?? null, nativeTurnId: observation.isolation?.nativeTurnId ?? null,
      parentNativeThreadId: observation.isolation?.parentNativeThreadId ?? null, actionId: observation.isolation?.actionId ?? null },
    originals, settlement: observation.settlement ?? { state: 'unknown', receiptSha256: null, automaticReplay: false },
    failure: observation.failure ? { code: observation.failure, originalOutcomeRetained: true } : null, limitations,
  };
  // Missing native pins/settlement/retained originals limit qualification, never become a zero or invented success.
  const errors = validateRecord(record);
  if (record.status === 'PASS' && errors.length) {
    record.status = 'NOT_TESTED'; record.limitations.push(...errors);
  }
  const shapeErrors = validateRecord(record);
  if (shapeErrors.length) throw new Error(`Invalid evidence record: ${shapeErrors.join(',')}`);
  return structuredClone(record);
}

function reviewGate(packet, adapter, qualification, normalizeResponses) {
  const config = packet.config;
  settlementReserve(config, qualification);
  const stage = config.profile === 'h040-summary-stage-v1';
  const fresh = !!config.review?.freshProjectionSpec;
  if (!config.enabled) throw new Error('Native controller disabled; preparation is not live authorization');
  if (adapter.interfaceVersion !== 'h039-compaction-adapter-v1' || adapter.kind !== qualification) throw new Error('Adapter identity mismatch');
  if (qualification === 'native') {
    if (!config.review || config.review.approvedBy !== 'root' || !/^[a-f0-9]{40}$/.test(config.review.candidateCommit ?? '') || !hashPattern.test(config.review.adapterSha256 ?? '')) throw new Error('Root-reviewed candidate/adapter required');
    if (!Number.isFinite(Date.parse(config.review.notAfterUtc)) || Date.now() >= Date.parse(config.review.notAfterUtc) || Date.parse(config.review.notAfterUtc) > Date.parse('2026-10-01T04:26:10Z')) throw new Error('Reviewed H040 execution window absent, expired or exceeds authority');
    for (const key of Object.keys(packet.sourceHashes).filter((k) => k !== 'config')) if (config.review.sourceHashes?.[key] !== packet.sourceHashes[key]) throw new Error('Reviewed source hashes mismatch');
    if (!stage && (!Array.isArray(config.review.childSystemMessageHashes) || config.review.childSystemMessageHashes.some((h) => !hashPattern.test(h)))) throw new Error('Reviewed child system-message manifest absent');
    if (!config.review.responseEnvelope || typeof config.review.responseEnvelope.instructions !== 'string' ||
      config.review.responseEnvelope.model !== config.review.runtimePins?.model ||
      (!fresh && !['system', 'developer', 'user', 'assistant'].includes(config.review.checkpointSummaryRole)) ||
      !Array.isArray(config.review.durableToolDefinitions)) throw new Error('Native frozen request/persisted-summary contract unqualified');
    if (fresh && (typeof normalizeResponses !== 'function' || config.review.freshProjectionSpec.format !== 'h040-fresh-persisted-message-v1' ||
      !hashPattern.test(config.review.freshProjectionSpec.collectorSourceSha256 ?? '') ||
      !validateCollectorManifest(config.review.freshProjectionSpec.collectorManifestUtf8) ||
      sha256(config.review.freshProjectionSpec.collectorManifestUtf8) !== config.review.freshProjectionSpec.collectorSourceSha256 ||
      projectionTranslatorFiles.some((file) => !hashPattern.test(config.review.translatorHashes?.[file] ?? '')))) throw new Error('Fresh projection source/translator unqualified');
  }
  if (config.profile && !stage && !['h039-full-retention-v1', 'h040-full-retention-v1'].includes(config.profile)) throw new Error('Unreviewed acceptance profile');
  if (qualification === 'native' && !stage && (config.profile !== 'h040-full-retention-v1' || config.maximumNativeActions !== 39)) throw new Error('H040 full native profile and bounded 39-call budget required');
  if (qualification === 'native' && stage && config.maximumNativeActions !== 9) throw new Error('Bounded 9-call native stage budget required');
  if (config.runtime.version !== '0.158.0' || config.runtime.sourceRevision !== '064c6b8c737f5b41d171fdda80bd9ef10ad06eb3' || config.runtime.contextWindow !== 480000 || config.runtime.autoCompactTokenLimit !== 400000 || config.runtime.maxOutputTokens !== 65536 || stableJson(config.cycles) !== (stage ? '[1]' : '[1,2,3]') || config.trigger !== 'manual' || config.automaticCase.enabled) throw new Error('Unreviewed runtime/policy change');
  const capabilities = [fresh ? 'qualified-fresh-persisted-message-projection' : 'qualified-summary-fork', 'host-captured-probe-input', 'tools-and-files-denied-for-summary', 'settlement-receipts',
    ...(!stage ? ['scoped-original-record-retrieval', 'qualified-durable-holdout-projection', 'cold-resume', ...(qualification === 'native' ? ['cold-resume-after-continuation', 'clean-child-context'] : [])] : [])];
  for (const capability of capabilities) if (!adapter.capabilities?.includes(capability)) throw new Error(`Unqualified adapter capability: ${capability}`);
  if (!Number.isInteger(config.maximumNativeActions) || config.maximumNativeActions < 1 || config.maximumNativeActions > (stage ? 9 : 39) || !Number.isInteger(config.deadlineMs) || config.deadlineMs < 1 || config.deadlineMs > 120000) throw new Error('Invalid action/deadline budget');
}

// Adapter implementations are an integration-owner task. No HTTP, RPC, VM or model
// connection is constructed by this module. Tests use an explicitly synthetic adapter.
export async function runAcceptance({ packet, adapter, qualification = 'native', sink, runId = randomUUID(), normalizeResponses }) {
  packet = { ...packet, config: freezeConfig(structuredClone(packet.config)) };
  reviewGate(packet, adapter, qualification, normalizeResponses);
  const stage = packet.config.profile === 'h040-summary-stage-v1';
  const authorizationDeadline = packet.config.review?.notAfterUtc ? Date.parse(packet.config.review.notAfterUtc) : null;
  const cleanupReserveMs = settlementReserve(packet.config, qualification);
  let count = 0, session, opened = false, currentCycle = 1, acceptedContinuation;
  const records = [];
  const probeThreads = new Set();
  const outstanding = new Set(), observedSettlements = [];
  const call = async (method, args = {}) => {
    if (count >= packet.config.maximumNativeActions - (method === 'close' ? 0 : 1)) throw new Error('Action budget exhausted; cleanup action reserved');
    let timeoutMs = packet.config.deadlineMs;
    if (authorizationDeadline !== null) {
      const remaining = authorizationDeadline - Date.now();
      if (!Number.isFinite(remaining) || remaining <= (method === 'close' ? 0 : cleanupReserveMs)) throw new Error('Absolute authorization deadline or settlement reserve reached; no dispatch');
      timeoutMs = Math.floor(Math.min(timeoutMs, remaining - (method === 'close' ? 0 : cleanupReserveMs)));
    }
    count++;
    const controller = new AbortController(), signal = AbortSignal.any([controller.signal, AbortSignal.timeout(timeoutMs)]);
    const owned = { method, controller }; outstanding.add(owned);
    const operation = Promise.resolve().then(() => adapter[method]({ ...args, signal })).then((result) => {
      if (method !== 'close' && result?.settlement?.state === 'released' && hashPattern.test(result.settlement.receiptSha256 ?? '') &&
        result.actionId && result.nativeThreadId && result.nativeTurnId) observedSettlements.push({ actionId: result.actionId, nativeThreadId: result.nativeThreadId,
        nativeTurnId: result.nativeTurnId, settlementReceiptSha256: result.settlement.receiptSha256 });
      return result;
    }).finally(() => outstanding.delete(owned));
    // The adapter must settle/quarantine its owned work after signal abort; no retry.
    return await Promise.race([
      operation,
      new Promise((_, reject) => {
        if (signal.aborted) reject(new Error('Adapter deadline elapsed'));
        else signal.addEventListener('abort', () => reject(new Error('Adapter deadline elapsed')), { once: true });
      }),
    ]);
  };
  const emit = async (record) => { await sink.record(record); records.push(record); };
  const expectedProbe = (result, request, mode, actionId, compact, cycle) => {
    const checkpoint = compact.checkpoint;
    let inputMessageHashes;
    const extraction = extractCheckpoint(checkpoint, { contextSha256: compact.contextSha256, parentThreadId: compact.nativeThreadId,
      actionId: compact.actionId, nativeTurnId: compact.nativeTurnId, windowId: packet.config.review?.windowId ?? runId,
      baseline: before?.parentState, summaryRole: packet.config.review?.checkpointSummaryRole ?? (qualification === 'synthetic' ? 'system' : undefined),
      summaryRepresentation: packet.config.review?.freshProjectionSpec ? 'persisted-message-only' : undefined,
      requireNativeMetadata: qualification === 'native', compactionRequests: compact.requests });
    const envelope = bindReviewedEnvelope(packet.config.review?.responseEnvelope ?? (qualification === 'synthetic' ? {} : undefined), {
      probeThreadId: result.nativeThreadId, probeTurnId: result.nativeTurnId });
    const toolDefinitions = mode === 'durable-retrieval' ? packet.config.review?.durableToolDefinitions ??
      (qualification === 'synthetic' ? [{ type: 'function', name: 'scoped.read_original_records' }] : undefined) : [];
    let fresh;
    if (packet.config.review?.freshProjectionSpec) {
      const projected = structuredClone(extraction);
      if (mode === 'durable-retrieval' && projected.status === 'PASS') for (const h of durableHoldouts(packet.truth, cycle))
        projected.summaryText = projected.summaryText.replaceAll(h.value, '[OMITTED_FOR_RETRIEVAL_PROBE]');
      fresh = deriveFreshProjection({ extraction: projected, request, spec: packet.config.review.freshProjectionSpec, envelope, toolDefinitions, normalizeResponses });
      inputMessageHashes = fresh.inputMessageHashes;
    } else if (extraction.status === 'PASS') {
      let messages = extraction.messages;
      if (mode === 'durable-retrieval') {
        let text = stableJson(messages);
        for (const h of durableHoldouts(packet.truth, cycle)) text = text.replaceAll(h.value, '[OMITTED_FOR_RETRIEVAL_PROBE]');
        messages = JSON.parse(text);
      }
      inputMessageHashes = [...messages, { role: 'user', content: stableJson(request) }].map((m) => sha256(stableJson(m)));
    }
    return { contextSha256: compact.contextSha256, parentThreadId: compact.nativeThreadId,
      probeThreadId: result.nativeThreadId, probeTurnId: result.nativeTurnId, runId, actionId, inputMessageHashes,
      parentStateSha256: checkpoint?.stateSha256,
      windowId: packet.config.review?.windowId ?? runId, settlementReceiptSha256: result.settlement?.receiptSha256,
      checkpointValidation: { status: fresh?.status ?? extraction.status, errors: fresh?.errors ?? extraction.errors },
      freshProjection: fresh?.freshProjection, envelope, toolDefinitions,
      allowedTools: mode === 'durable-retrieval' ? ['scoped.read_original_records'] : [] };
  };
  const uniqueProbe = (result, isolation) => {
    if (result.nativeThreadId && probeThreads.has(result.nativeThreadId)) return { status: 'FAIL', errors: [...isolation.errors, 'probe-thread-reused'] };
    if (result.nativeThreadId) probeThreads.add(result.nativeThreadId);
    return isolation;
  };
  let runtime, compact, before, after;
  try {
    runtime = await call('runtime');
    if (qualification === 'native') {
      // Refuse a mismatched or unidentified runner before opening an inference thread.
      const pins = packet.config.review.runtimePins;
      if (!pins || ['version', 'sourceRevision', 'binarySha256', 'model', 'modelRevision', 'tokenizerRevision'].some((k) => !pins[k] || runtime?.[k]?.value !== pins[k]) || pins.version !== packet.config.runtime.version || pins.sourceRevision !== packet.config.runtime.sourceRevision) throw new Error('Actual runtime/model pins do not match reviewed candidate');
    }
    opened = true;
    session = await call('open', { runId, config: structuredClone(packet.config) });
    if (!session?.nativeThreadId) throw new Error('Captured parent native identity absent after open');
    for (const cycle of packet.config.cycles) {
      currentCycle = cycle;
      await call('append', { session, records: packet.corpus.records.filter((r) => r.cycle === cycle) });
      before = await call('originals', { session, cycle });
      compact = await call('compact', { session, cycle, runId, windowId: packet.config.review?.windowId ?? runId,
        baseline: before?.parentState, actionId: actionIdFor(runId, cycle, 'compact') });
      after = await call('originals', { session, cycle });
      await sink.private(`${cycle}-compact`, compact);
      const originals = originalProof(packet.corpus, cycle, before, after);
      if (compact.outcome !== 'completed' || compact.summaryState !== 'complete' || !hashPattern.test(compact.contextSha256 ?? '') || compact.actionId !== actionIdFor(runId, cycle, 'compact') || compact.nativeThreadId !== session.nativeThreadId) {
        const observation = { ...compact, failure: compact.failure ?? (compact.actionId !== actionIdFor(runId, cycle, 'compact') ? 'action-identity-mismatch' : `summary-${compact.summaryState ?? 'unknown'}`) };
        await emit(makeRecord({ packet, runId, cycle, mode: 'fault', qualification, runtime, observation, originals, grade: { status: 'FAIL' } }));
        break;
      }
      const checkpointValidation = extractCheckpoint(compact.checkpoint, { contextSha256: compact.contextSha256, parentThreadId: compact.nativeThreadId,
        actionId: compact.actionId, nativeTurnId: compact.nativeTurnId, windowId: packet.config.review?.windowId ?? runId,
        baseline: before?.parentState, summaryRole: packet.config.review?.checkpointSummaryRole ?? (qualification === 'synthetic' ? 'system' : undefined),
        summaryRepresentation: packet.config.review?.freshProjectionSpec ? 'persisted-message-only' : undefined,
        requireNativeMetadata: qualification === 'native', compactionRequests: compact.requests });
      if (checkpointValidation.status !== 'PASS') {
        await emit(makeRecord({ packet, runId, cycle, mode: 'fault', qualification, runtime, observation: compact, originals, grade: checkpointValidation }));
        break;
      }
      compact = { ...compact, verifierNativeWindowId: checkpointValidation.nativeWindowId, operationWindowId: packet.config.review?.windowId ?? runId };
      let stop = false;
      // Each probe receives an independently checked fork. Answers never enter the parent.
      for (const mode of stage ? ['summary-only'] : ['summary-only', 'durable-retrieval', 'continuation']) {
        // Cold resume occurs before cycle-3 continuation: the compacted checkpoint is current.
        if (cycle === 3 && mode === 'continuation') {
          const request = recallRequest(packet.truth, 3, 'summary-only');
          const actionId = actionIdFor(runId, 3, 'cold-resume');
          const result = await call('coldResume', { session, cycle: 3, mode: 'summary-only', request, actionId, checkpoint: compact.checkpoint });
          await sink.private('cold-resume', result);
          let isolation = uniqueProbe(result, verifySummaryIsolation(result.isolation, expectedProbe(result, request, 'summary-only', actionId, compact, 3)));
          const restart = verifyColdResume(result.restartEvidence, compact.checkpoint, { requireHostRestart: qualification === 'native', runId, actionId, windowId: packet.config.review?.windowId ?? runId });
          let grade = scoreRecall(packet.truth, 3, result.answer);
          if (restart.status !== 'PASS') grade = { ...grade, status: grade.status === 'FAIL' ? 'FAIL' : restart.status, errors: [...grade.errors, ...restart.errors] };
          after = await call('originals', { session, cycle: 3 });
          const record = makeRecord({ packet, runId, cycle: 3, mode: 'cold-resume', qualification, runtime,
            observation: result, compactionObservation: compact, originals: originalProof(packet.corpus, 3, before, after), grade, isolation });
          await emit(record);
          if (record.status !== 'PASS') { stop = true; break; }
        }
        const request = mode === 'continuation' ? continuationRequest() : recallRequest(packet.truth, cycle, mode);
        const actionId = actionIdFor(runId, cycle, mode);
        const result = mode === 'continuation'
          ? await call('continue', { session, cycle, request, actionId })
          : await call('probe', { session, cycle, mode, actionId, runId, parentThreadId: compact.nativeThreadId, checkpoint: compact.checkpoint,
              contextSha256: compact.contextSha256, request, allowedTools: mode === 'summary-only' ? [] : ['scoped.read_original_records'],
              hostOnlyHoldouts: mode === 'durable-retrieval' ? durableHoldouts(packet.truth, cycle) : [] });
        await sink.private(`${cycle}-${mode}`, result);
        let grade = mode === 'continuation' ? scoreContinuation(packet.truth, cycle, result.artifacts) : scoreRecall(packet.truth, cycle, result.answer, mode);
        let isolation;
        if (mode !== 'continuation') {
          const expected = expectedProbe(result, request, mode, actionId, compact, cycle);
          isolation = uniqueProbe(result, mode === 'summary-only' ? verifySummaryIsolation(result.isolation, expected) : verifyProbeSeparation(result.isolation, expected));
        }
        if (result.actionId !== actionId) grade = { ...grade, status: 'FAIL', errors: [...grade.errors, 'action-identity-mismatch'] };
        if (mode === 'continuation' && result.nativeThreadId !== compact.nativeThreadId) grade = { ...grade, status: 'FAIL', errors: [...grade.errors, 'continuation-parent-identity-mismatch'] };
        if (mode === 'summary-only' && result.retrieval?.calls?.length) isolation = { status: 'FAIL', errors: [...isolation.errors, 'summary-retrieval-observed'] };
        let retrieval;
        if (mode === 'durable-retrieval') {
          const holdout = verifyDurableHoldout(packet.truth, cycle, result.retrievalContext);
          if (holdout.status !== 'PASS' || isolation.status !== 'PASS') grade = { ...grade,
            status: grade.status === 'FAIL' || holdout.status === 'FAIL' || isolation.status === 'FAIL' ? 'FAIL' : 'NOT_TESTED',
            errors: [...grade.errors, ...holdout.errors, ...isolation.errors] };
          const errors = verifyRetrieval(packet.corpus, packet.truth, cycle, result.answer, result.retrieval);
          if (errors.length) grade = { ...grade, status: 'FAIL', errors: [...grade.errors, ...errors] };
          const calls = result.retrieval?.calls ?? [];
          retrieval = { used: calls.length > 0, callIds: calls.map((c) => c.id), sourceIds: [...new Set(calls.flatMap((c) => (c.records ?? []).map((r) => r.sourceId)))],
            traceSha256: result.retrieval ? sha256(stableJson({ trace: result.retrieval, holdout: result.retrievalContext })) : null };
        }
        after = await call('originals', { session, cycle });
        const record = makeRecord({ packet, runId, cycle, mode, qualification, runtime, observation: result, compactionObservation: compact,
          originals: originalProof(packet.corpus, cycle, before, after), grade, isolation, retrieval });
        await emit(record);
        if (record.status !== 'PASS') { stop = true; break; }
        if (mode === 'continuation' && cycle === 3) {
          const baseline = captureAcceptedArtifactBaseline(result, after?.parentState, { runId, sessionId: session.sessionId,
            actionId, nativeThreadId: compact.nativeThreadId });
          acceptedContinuation = freezeConfig(structuredClone({ actionId, artifactHashes: record.artifactHashes, checkpoint: after?.parentState,
            artifacts: result.artifacts, artifactBaseline: baseline.baseline, artifactBaselineStatus: { status: baseline.status, errors: baseline.errors } }));
          await sink.private('accepted-continuation-original-artifact-baseline', acceptedContinuation);
        }
      }
      if (stop) break;
    }
    if (!stage && records.length === 10 && records.every((r) => r.status === 'PASS') && adapter.capabilities.includes('cold-resume-after-continuation')) {
      const actionId = actionIdFor(runId, 3, 'cold-resume-after-continuation');
      const result = await call('resumeAcceptedContinuation', { session, cycle: 3, runId, actionId, windowId: packet.config.review?.windowId ?? runId,
        checkpoint: structuredClone(acceptedContinuation?.checkpoint), acceptedContinuation: acceptedContinuation ? structuredClone({ actionId: acceptedContinuation.actionId,
          artifactHashes: acceptedContinuation.artifactHashes, artifactBaseline: acceptedContinuation.artifactBaseline }) : undefined });
      await sink.private('cold-resume-after-continuation', result);
      let grade = verifyAcceptedContinuationResume(result, acceptedContinuation, { runId, actionId, windowId: packet.config.review?.windowId ?? runId });
      if (grade.status === 'PASS') grade = scoreContinuation(packet.truth, 3, result.artifacts);
      if (result.actionId !== actionId || result.nativeThreadId !== compact.nativeThreadId) grade = { status: 'FAIL', errors: [...grade.errors, 'accepted-continuation-resume-identity'] };
      after = await call('originals', { session, cycle: 3 });
      if (!after?.parentState?.stateUtf8) grade = { status: grade.status === 'FAIL' ? 'FAIL' : 'NOT_TESTED', errors: [...grade.errors, 'post-resume-independent-parent-state-absent'] };
      else if (after.parentState.capturedBy !== 'host' || after.parentState.nativeThreadId !== compact.nativeThreadId ||
        after.parentState.stateSha256 !== sha256(after.parentState.stateUtf8) || after.parentState.stateSha256 !== acceptedContinuation?.checkpoint?.stateSha256)
        grade = { status: 'FAIL', errors: [...grade.errors, 'post-resume-parent-state-changed'] };
      await emit(makeRecord({ packet, runId, cycle: 3, mode: 'cold-resume-after-continuation', qualification, runtime, observation: result,
        compactionObservation: compact, originals: originalProof(packet.corpus, 3, before, after), grade }));
    }
    if (!stage && [10, 11].includes(records.length) && records.every((r) => r.status === 'PASS')) {
      const childNonce = `CHILD_ONLY_${randomUUID()}`;
      const childBrief = `Report the child nonce ${childNonce} and, only if known, the parent's private marker. Return JSON fields childNonce and parentCanary; use UNKNOWN for absent information. Do not use tools.`;
      const parentCanary = `KPM_PARENT_ONLY_${randomUUID()}`;
      const approved = { parentCanary, childNonce, parentThreadId: compact.nativeThreadId,
        envelope: packet.config.review?.responseEnvelope ?? (qualification === 'synthetic' ? {} : undefined),
        messageHashes: [...(packet.config.review?.childSystemMessageHashes ?? []), sha256(stableJson({ role: 'user', content: childBrief }))] };
      const actionId = actionIdFor(runId, 3, 'child-context');
      const child = await call('childContext', { session, cycle: 3, actionId, brief: childBrief, hostOnlyParentCanary: parentCanary, childNonce });
      await sink.private('child-first-request', child);
      let grade = verifyCleanChild(child.probe, approved);
      if (child.actionId !== actionId || child.nativeThreadId !== child.probe?.childId || child.nativeThreadId === compact.nativeThreadId || probeThreads.has(child.nativeThreadId)) grade = { ...grade, status: 'FAIL', errors: [...grade.errors, 'child-action-or-native-identity-binding'] };
      after = await call('originals', { session, cycle: 3 });
      await emit(makeRecord({ packet, runId, cycle: 3, mode: 'child-context', qualification, runtime,
        observation: { ...child, isolation: { captureSha256: child.probe?.captureSha256 ?? null, nativeThreadId: child.nativeThreadId,
          nativeTurnId: child.nativeTurnId, parentNativeThreadId: compact.nativeThreadId, actionId } }, compactionObservation: compact,
        originals: originalProof(packet.corpus, 3, before, after), grade, isolation: grade }));
    }
  } catch (error) {
    // Preserve partial/failure evidence, including errors before a native identity exists.
    // Do not copy raw adapter errors (which may contain credentials) into public evidence.
    await emit(makeRecord({ packet, runId, cycle: currentCycle, mode: 'fault', qualification, runtime,
      observation: { outcome: 'unknown', failure: 'controller-or-adapter-error' },
      originals: originalProof(packet.corpus, currentCycle, before, after), grade: { status: 'FAIL' } }));
    await sink.private('controller-error', { name: error.name, message: error.message });
  } finally {
    // Abort current owned calls before asking the adapter to await its shared
    // native/gateway cleanup promises. The controller never replays a method.
    for (const owned of outstanding) owned.controller.abort();
    if (opened) {
      try {
        const closed = await call('close', { session, runId, observedSettlements: structuredClone(observedSettlements) });
        if (qualification === 'native') {
          await sink.private('owned-close', closed ?? { observation: 'absent' });
          const proof = verifyOwnedClose(closed, { runId, operationWindowId: packet.config.review?.windowId ?? runId, observedSettlements });
          if (proof.status === 'NOT_TESTED') {
            await emit(makeRecord({ packet, runId, cycle: currentCycle, mode: 'fault', qualification, runtime,
              observation: { outcome: 'unknown', failure: 'cleanup-receipt-unqualified', settlement: { state: 'unknown', receiptSha256: null, automaticReplay: false } },
              originals: originalProof(packet.corpus, currentCycle, before, after), grade: proof }));
          } else if (proof.status !== 'PASS') throw new Error('Owned native close binding failed');
        }
      } catch {
        await emit(makeRecord({ packet, runId, cycle: currentCycle, mode: 'fault', qualification, runtime,
          observation: { outcome: 'unknown', failure: 'cleanup-unconfirmed', settlement: { state: 'unknown', receiptSha256: null, automaticReplay: false } },
          originals: originalProof(packet.corpus, currentCycle, before, after), grade: { status: 'FAIL' } }));
      }
    }
  }
  const dimensions = summarizeQualification(records, packet.truth);
  const expectedRecords = stage ? 1 : adapter.capabilities.includes('cold-resume-after-continuation') ? 12 : 11;
  const observedStatus = records.some((r) => r.status === 'FAIL') ? 'FAIL' : records.length === expectedRecords && records.every((r) => r.status === 'PASS') ? 'PASS' : 'NOT_TESTED';
  const status = qualification === 'native' && observedStatus === 'PASS' ? dimensions.nativeAcceptance : observedStatus;
  return { status, observedStatus, ...dimensions, settlementReserveMs: cleanupReserveMs, profile: packet.config.profile ?? 'h039-full-retention-v1', qualification, runId, actionCount: count, records,
    limitation: qualification === 'synthetic' ? 'Synthetic orchestration proves no native model retention, rollback or live reliability.' : 'A bounded native pass is scoped to these pinned runtime/model/source inputs.' };
}

async function main(args) {
  const [command, ...rest] = args;
  if (command === 'prepare' && rest.length === 1) return await prepare(rest[0]);
  if (command === 'plan' && rest.length <= 1) return actionPlan(rest.length ? await loadJson(rest[0]) : (await fixture()).config);
  if (command === 'validate-record' && rest.length === 1) {
    const errors = validateRecord(await loadJson(rest[0]));
    if (errors.length) process.exitCode = 1;
    return { status: errors.length ? 'FAIL' : 'PASS', errors, validationScope: 'schema-and-consistency-only', liveReliability: 'NOT_TESTED' };
  }
  if (command === 'score' && rest.length === 4) {
    const [mode, cycleText, answerPath, tracePath] = rest;
    const packet = await fixture(), cycle = Number(cycleText), answer = await loadJson(answerPath), trace = await loadJson(tracePath);
    let grade;
    if (mode === 'continuation') grade = scoreContinuation(packet.truth, cycle, answer);
    else {
      grade = scoreRecall(packet.truth, cycle, answer, mode);
      const isolation = mode === 'summary-only' ? verifySummaryIsolation(trace.isolation, trace.contextSha256) : null;
      const holdout = mode === 'durable-retrieval' ? verifyDurableHoldout(packet.truth, cycle, trace.retrievalContext) : null;
      const errors = mode === 'summary-only' ? isolation.errors : [...verifyRetrieval(packet.corpus, packet.truth, cycle, answer, trace), ...holdout.errors];
      if (errors.length) grade = { ...grade, status: (isolation?.status === 'NOT_TESTED' || holdout?.status === 'NOT_TESTED') && grade.status !== 'FAIL' ? 'NOT_TESTED' : 'FAIL', evidenceErrors: errors };
    }
    if (grade.status !== 'PASS') process.exitCode = 1;
    return { ...grade, qualification: 'offline-grading', nativeAcceptance: 'NOT_TESTED' };
  }
  if (command === 'run-reviewed' && rest.length === 3) {
    const [adapterPath, configPath, outPath] = rest;
    const packet = await fixture();
    packet.config = await loadJson(configPath);
    packet.sourceHashes.config = sha256(await readFile(configPath));
    if (packet.config.review?.adapterSha256 !== sha256(await readFile(adapterPath))) throw new Error('Adapter SHA does not match reviewed config');
    // Check the external configuration before importing any executable adapter.
    if (!packet.config.enabled || packet.config.review?.approvedBy !== 'root') throw new Error('Reviewed native execution is disabled');
    const out = await privateDirectory(outPath);
    let normalizeResponses;
    if (packet.config.review.freshProjectionSpec) {
      const closure = JSON.parse(packet.config.review.freshProjectionSpec.collectorManifestUtf8);
      if (!validateCollectorManifest(packet.config.review.freshProjectionSpec.collectorManifestUtf8)) throw new Error('Collector source closure manifest invalid');
      // Include every current constructor/server source sibling, so a handpicked
      // wrapper hash cannot hide an omitted runtime dependency. E's bootstrap
      // independently binds deployment/launcher/dependency artifacts as well.
      for (const directory of ['ai-harness/server/src', 'ai-harness/acceptance/compaction/native-adapter']) {
        for (const file of await readdir(join(repo, directory), { recursive: true })) if (/\.(?:ts|json|js|mjs)$/.test(file) && !Object.hasOwn(closure.files, `${directory}/${file}`))
          throw new Error('Collector runtime source dependency omitted');
      }
      for (const [file, hash] of Object.entries(closure.files)) if (await realpath(join(repo, file)) !== join(repo, file) || hash !== sha256(await readFile(join(repo, file))))
        throw new Error('Collector reviewed source closure mismatch');
      for (const file of projectionTranslatorFiles) if (packet.config.review.translatorHashes?.[file] !== sha256(await readFile(join(repo, 'ai-harness/server', file))))
        throw new Error('Reviewed production translator closure mismatch');
      normalizeResponses = (await import(pathToFileURL(join(repo, 'ai-harness/server/dist/codex-responses.js')).href)).translateResponses;
    }
    const adapter = (await import(pathToFileURL(resolve(adapterPath)).href)).default;
    const sink = { private: (name, value) => privateJson(join(out, `private-${name}.json`), value), record: (value) => privateJson(join(out, `${value.cycle}-${value.mode}-${randomUUID()}.evidence.json`), value) };
    const result = await runAcceptance({ packet, adapter, sink, normalizeResponses });
    await privateJson(join(out, 'RESULTS.json'), result);
    if (result.status !== 'PASS') process.exitCode = 1;
    return { status: result.status, observedStatus: result.observedStatus, nativeAcceptance: result.nativeAcceptance,
      semanticAcceptance: result.semanticAcceptance, profile: result.profile, qualification: result.qualification, runId: result.runId, actionCount: result.actionCount, out };
  }
  throw new Error('Usage: controller.mjs plan [CONFIG_JSON] | prepare NEW_PRIVATE_DIR | score MODE CYCLE ANSWER_JSON TRACE_JSON | validate-record RECORD_JSON | run-reviewed ADAPTER CONFIG NEW_PRIVATE_DIR');
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main(process.argv.slice(2)).then((value) => console.log(stableJson(value))).catch(() => {
    console.error('Controller failed; inspect private inputs/configuration. No automatic retry.'); process.exitCode = 1;
  });
}
