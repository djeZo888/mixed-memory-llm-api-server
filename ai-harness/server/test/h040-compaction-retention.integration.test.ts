import assert from 'node:assert/strict';
import test from 'node:test';
import { mkdtemp, readFile, rm, readdir } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { resolve, join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { translateResponses } from '../src/codex-responses.js';
import { activeFacts, actionIdFor, collectorRequiredFiles, deriveFreshProjection, extractCheckpoint, logicalManifestFormat,
  sha256, stableJson, verifySummaryIsolation, verifyColdResume, captureAcceptedArtifactBaseline, verifyAcceptedContinuationResume } from '../../acceptance/compaction/scorer.mjs';
import { fixture, bindReviewedEnvelope, makeRecord, recallRequest, runAcceptance } from '../../acceptance/compaction/controller.mjs';
import { validateRecord, validateShape } from '../../acceptance/compaction/evidence.mjs';
import { summarizeQualification } from '../../acceptance/compaction/qualification.mjs';

// Actual E modules and actual production translation. Host/protocol inputs and
// receipts below are explicitly SYNTHETIC, with no native process, launch,
// sandbox attestation, network, provider, or inference. They test interoperability
// and rejection boundaries, not native fidelity. An optional read-only sibling
// root allows the same tests against E's finite candidate without cross-editing.
const eRoot = process.env.H040_E_SOURCE_ROOT ?? resolve(import.meta.dirname, '../../acceptance/compaction/native-adapter');
const eProjection = await import(pathToFileURL(join(eRoot, 'projection.ts')).href);
const { DispatchGuard } = await import(pathToFileURL(join(eRoot, 'dispatch-guard.ts')).href);
const { createNativeAdapter } = await import(pathToFileURL(join(eRoot, 'adapter.ts')).href);
const packet = await fixture();
const syntheticHash = sha256('SYNTHETIC host/protocol boundary only');
const clone = structuredClone;
const runId = '00000000-0000-4000-8000-000000000041' as const, windowId = 'h040-synthetic-window';
const parent = 'synthetic-parent', probeThreadId = 'synthetic-probe', probeTurnId = 'synthetic-probe-turn';
const policy = 'Recall supplied state only; do not infer permissions or completed checks.';
const summary = 'SUMMARY_PREFIX\nTechnical state: logic rail 3.3 V; bench check unfinished. Preserve superseding corrections.';
const typed = (role: string, text: string) => ({ type: 'message', role, content: [{ type: 'input_text', text }] });
const capturedState = (bytes: string) => {
  const receiptUtf8 = JSON.stringify({ source: 'owned-native-persisted-state', captureId: 'synthetic-capture', sessionId: 'synthetic-host-session', sourceRef: 'profile/synthetic.jsonl',
    nativeThreadId: parent, stateSha256: sha256(bytes), bytes: Buffer.byteLength(bytes), observedAt: '2026-10-01T02:31:00Z' });
  return { capturedBy: 'host', nativeThreadId: parent, stateUtf8: bytes, stateSha256: sha256(bytes), receiptUtf8, receiptSha256: sha256(receiptUtf8) };
};

function persisted() {
  const baseline = capturedState(JSON.stringify({ timestamp: '2026-10-01T02:30:00Z', type: 'session_meta', payload: { id: parent } }) + '\n' +
    JSON.stringify({ timestamp: '2026-10-01T02:30:01Z', type: 'response_item', payload: typed('user', 'ORIGINAL_HISTORY_MARKER_NOT_ALLOWED_IN_PROBE') }) + '\n');
  const compactedRecordUtf8 = JSON.stringify({ timestamp: '2026-10-01T02:30:03Z', type: 'compacted', payload: {
    message: summary, replacement_history: [typed('user', 'ORIGINAL_HISTORY_MARKER_NOT_ALLOWED_IN_PROBE')] } }) + '\n';
  const actionId = actionIdFor(runId, 1, 'compact'), nativeTurnId = 'synthetic-compact-turn';
  const checkpoint: any = { ...capturedState(baseline.stateUtf8 + compactedRecordUtf8), compactedRecordUtf8, compactedRecordSha256: sha256(compactedRecordUtf8) };
  const expected: any = { contextSha256: checkpoint.stateSha256, parentThreadId: parent, actionId, nativeTurnId, windowId,
    baseline, summaryRepresentation: 'persisted-message-only' };
  rebind(checkpoint, expected);
  return { baseline, checkpoint, expected };
}
function rebind(checkpoint: any, expected: any) {
  checkpoint.stateSha256 = sha256(checkpoint.stateUtf8); expected.contextSha256 = checkpoint.stateSha256;
  checkpoint.bindingReceiptUtf8 = JSON.stringify({ source: 'native-rollout-record-owner', nativeThreadId: parent,
    compactionActionId: expected.actionId, nativeTurnId: expected.nativeTurnId, windowId, recordSha256: checkpoint.compactedRecordSha256,
    stateSha256: checkpoint.stateSha256, recordId: 'synthetic-selected-record', sourceRef: 'synthetic-owned-rollout' });
  checkpoint.bindingReceiptSha256 = sha256(checkpoint.bindingReceiptUtf8);
  checkpoint.settledOperationUtf8 = JSON.stringify({ source: 'native-compaction-settlement', status: 'completed', settlement: 'released',
    nativeThreadId: parent, actionId: expected.actionId, nativeTurnId: expected.nativeTurnId, windowId,
    baselineStateSha256: expected.baseline.stateSha256, postStateSha256: checkpoint.stateSha256, recordSha256: checkpoint.compactedRecordSha256,
    compactionId: 'synthetic-owned-compact-item', startedAt: '2026-10-01T02:30:02Z', completedAt: '2026-10-01T02:30:04Z' });
  checkpoint.settledOperationSha256 = sha256(checkpoint.settledOperationUtf8);
}
const envelopeTemplate = { model: 'qwen3.8-27b', instructions: policy, stream: true, store: false, tool_choice: 'auto', parallel_tool_calls: false,
  include: ['reasoning.encrypted_content'], max_output_tokens: 65536,
  client_metadata: { thread_id: '@h040:probe-native-thread-id', turn_id: '@h040:probe-native-turn-id', root_turn_id: '@h040:probe-native-turn-id' } };
async function frozenSpec() {
  const nativePrefix = 'ai-harness/acceptance/compaction/native-adapter/';
  const nativeFiles = (await readdir(eRoot, { recursive: true })).filter((f: string) => /\.(ts|json)$/.test(f)).map((f: string) => nativePrefix + f);
  const serverRoot = resolve(import.meta.dirname, '../src');
  const serverFiles = (await readdir(serverRoot, { recursive: true })).filter((f: string) => f.endsWith('.ts')).map((f: string) => 'ai-harness/server/src/' + f);
  const files = Object.fromEntries(await Promise.all([...new Set([...collectorRequiredFiles, ...nativeFiles, ...serverFiles])].map(async file => [file,
    sha256(await readFile(file.startsWith(nativePrefix) ? join(eRoot, file.slice(nativePrefix.length)) : resolve(import.meta.dirname, '../../..', file)))])));
  const collectorManifestUtf8 = JSON.stringify({ format: 'h040-collector-closure-v1', sourceRevision: packet.config.runtime.sourceRevision, files });
  return { format: 'h040-fresh-persisted-message-v1', frozenPolicy: policy,
    prefixInput: [typed('developer', 'Synthetic frozen native environment: no original records, tools, or answer files.')],
    collectorManifestUtf8, collectorSourceSha256: sha256(collectorManifestUtf8) };
}
async function projected() {
  const p = persisted(), request = recallRequest(packet.truth, 1, 'summary-only');
  const envelope = bindReviewedEnvelope(envelopeTemplate, { probeThreadId, probeTurnId });
  const spec = await frozenSpec(), extraction = extractCheckpoint(p.checkpoint, p.expected);
  assert.ok('summaryText' in extraction);
  const derived = deriveFreshProjection({ extraction, request, spec, envelope, toolDefinitions: [], normalizeResponses: translateResponses });
  assert.equal(derived.status, 'PASS');
  return { ...p, request, spec, extraction, derived, envelope,
    expectedProbe: { ...derived, contextSha256: p.checkpoint.stateSha256, parentStateSha256: p.checkpoint.stateSha256,
      parentThreadId: parent, probeThreadId, probeTurnId, runId, windowId, actionId: actionIdFor(runId, 1, 'summary-only'),
      inputMessageHashes: derived.inputMessageHashes, checkpointValidation: extraction, envelope, toolDefinitions: [], allowedTools: [] } };
}
async function collected(t: any, mutate?: (raw: any) => void) {
  const p = await projected(), directory = await mkdtemp(join(tmpdir(), 'h040-b-real-e-collector-'));
  t.after(() => rm(directory, { recursive: true, force: true }));
  const raw = { ...clone(p.envelope), input: clone(p.derived.freshProjection.input), tools: [] };
  const userText = eProjection.summaryProbeText(p.extraction.summaryText, policy, p.request);
  const guard = new DispatchGuard(directory);
  guard.register({ sessionId: 'synthetic-host-session', actionId: p.expectedProbe.actionId, runId, mode: 'summary-only',
    parentNativeThreadId: parent, expiresAt: Date.now() + 10000, signal: new AbortController().signal,
    identity: () => ({ nativeThreadId: probeThreadId, nativeTurnId: probeTurnId }),
    manifest: { input: clone(raw.input), instructions: policy, userText, contextSha256: p.checkpoint.stateSha256, envelope: clone(p.envelope) } });
  mutate?.(raw);
  const bytes = Buffer.from(JSON.stringify(raw, null, 2) + '\n');
  guard.capture({ sessionId: 'synthetic-host-session', requestId: 'synthetic-provider-request', model: 'qwen3.8-27b', phase: 'pre_normalization', bytes });
  let counts = 0;
  const body = translateResponses(raw).body;
  const dispatch = guard.wrap(async () => { counts++; return { inputTokens: 123, contextWindow: 480000 }; });
  await dispatch(body, { alias: 'qwen3.8-27b' }, 'unused-synthetic-key', new AbortController().signal, { requestId: 'synthetic-provider-request' });
  guard.capture({ sessionId: 'synthetic-host-session', requestId: 'synthetic-provider-request', model: 'qwen3.8-27b', phase: 'normalized_request', bytes: Buffer.from(JSON.stringify(body)) });
  const capture = guard.receipt('synthetic-host-session');
  assert.equal(counts, 1);
  assert.equal(capture.captureSha256, sha256(await readFile(join(directory, 'synthetic-provider-request-pre.bin'))));
  assert.equal(capture.normalizedSha256, sha256(await readFile(join(directory, 'synthetic-provider-request-normalized.bin'))));
  return { ...p, capture, counts, directory };
}

// This augmentation is a hypothetical source contract, NEVER an attestation.
// The real E guard supplies request bytes above; synthetic host/protocol records
// supply otherwise unavailable launcher/settlement/parent captures explicitly.
function syntheticContractCapture(p: any) {
  const scopeReceiptUtf8 = JSON.stringify({ source: 'native-launcher-effective-scope', nativeThreadId: probeThreadId, nativeTurnId: probeTurnId,
    actionId: p.expectedProbe.actionId, allowedTools: [], readRoots: [], writeRoots: [], network: 'deny', answerKeyMounted: false });
  const probe: any = { ...p.capture, collectorManifestUtf8: p.spec.collectorManifestUtf8, scopeReceiptUtf8, scopeReceiptSha256: sha256(scopeReceiptUtf8),
    filesDenied: true, networkDenied: true, toolsDenied: true, toolCalls: [], originalRecordIds: [], accessiblePaths: [],
    answerKeyExposed: false, parentHistoryExposed: false, inputReceiptSha256: p.capture.captureSha256,
    parentStateAfter: clone(p.checkpoint), contextSha256: p.checkpoint.stateSha256 };
  probe.probeSettledOperationUtf8 = JSON.stringify({ source: 'native-probe-settlement', runId, actionId: p.expectedProbe.actionId, windowId,
    parentNativeThreadId: parent, nativeThreadId: probeThreadId, nativeTurnId: probeTurnId, parentStateSha256: p.checkpoint.stateSha256,
    status: 'completed', settlement: 'released', nativeProcessGone: true, gatewaySettled: true,
    firstRequestSha256: probe.captureSha256, normalizedRequestSha256: probe.normalizedSha256,
    startedAt: '2026-10-01T02:30:05Z', completedAt: '2026-10-01T02:30:06Z' });
  probe.probeSettledOperationSha256 = sha256(probe.probeSettledOperationUtf8);
  p.expectedProbe.settlementReceiptSha256 = probe.probeSettledOperationSha256;
  probe.projectionReceiptUtf8 = JSON.stringify({ source: 'native-fresh-persisted-message-projection', logicalManifestFormat,
    runId, actionId: p.expectedProbe.actionId, windowId, parentNativeThreadId: parent, nativeThreadId: probeThreadId, nativeTurnId: probeTurnId,
    parentStateSha256: p.checkpoint.stateSha256, compactedRecordSha256: p.checkpoint.compactedRecordSha256,
    summarySha256: sha256(summary), querySha256: sha256(stableJson(p.request)), policySha256: sha256(policy),
    collectorSourceSha256: p.spec.collectorSourceSha256, firstRequestSha256: probe.captureSha256, normalizedRequestSha256: probe.normalizedSha256,
    scopeReceiptSha256: probe.scopeReceiptSha256, inputManifestSha256: sha256(stableJson(p.derived.inputMessageHashes)),
    envelopeSha256: sha256(stableJson(p.envelope)), settledOperationSha256: probe.probeSettledOperationSha256 });
  probe.projectionReceiptSha256 = sha256(probe.projectionReceiptUtf8);
  return probe;
}

test('B/E logical JSON agrees across key order; raw hashes and H039 archive domains remain distinct', () => {
  const a = { z: 1, a: [{ z: 'Ω\n', a: 2 }] }, b = { a: [{ a: 2, z: 'Ω\n' }], z: 1 };
  assert.equal(stableJson(a), eProjection.stableJson(a)); assert.equal(stableJson(a), stableJson(b));
  assert.notEqual(sha256(JSON.stringify(a)), sha256(JSON.stringify(b)));
  const archive = { schemaVersion: 1, logicalManifestFormat: 'h039-insertion-json-v1' };
  assert.ok(validateRecord(archive).length);
});
test('real E persisted-summary extraction does not substitute summary SHA for B full-state SHA', () => {
  const p = persisted();
  const e = eProjection.extractPersistedSummary(Buffer.from(p.checkpoint.stateUtf8), { nativeThreadId: parent, nativeTurnId: p.expected.nativeTurnId,
    actionId: p.expected.actionId, beforeBytes: Buffer.byteLength(p.baseline.stateUtf8), beforeSha256: p.baseline.stateSha256,
    dispatchedAt: '2026-10-01T02:30:02Z', settledAt: '2026-10-01T02:30:04Z', summaryPrefix: 'SUMMARY_PREFIX\n' });
  const extraction = extractCheckpoint(p.checkpoint, p.expected); assert.ok('summaryText' in extraction);
  assert.equal(e.message, extraction.summaryText);
  assert.equal(e.rolloutSha256, p.checkpoint.stateSha256); assert.notEqual(e.contextSha256, p.checkpoint.stateSha256);
  assert.equal(extractCheckpoint(p.checkpoint, { ...p.expected, contextSha256: e.contextSha256 }).status, 'FAIL');
  assert.equal(extractCheckpoint({ contextSha256: e.contextSha256 }, p.expected).status, 'NOT_TESTED');
});
test('rollback/revert suffixes, foreign/duplicate session_meta and extra compactions reject even with rebound hashes', () => {
  for (const mutate of [
    (p: any) => { p.checkpoint.stateUtf8 += JSON.stringify({ type: 'event_msg', payload: { type: 'thread_rollback' } }) + '\n'; },
    (p: any) => { p.checkpoint.stateUtf8 += JSON.stringify({ type: 'reverted', payload: {} }) + '\n'; },
    (p: any) => { p.checkpoint.stateUtf8 += JSON.stringify({ type: 'session_meta', payload: { id: parent } }) + '\n'; },
    (p: any) => { p.checkpoint.stateUtf8 += p.checkpoint.compactedRecordUtf8; },
    (p: any) => { p.baseline.stateUtf8 = p.baseline.stateUtf8.replace(parent, 'foreign-native-owner'); p.baseline.stateSha256 = sha256(p.baseline.stateUtf8);
      p.checkpoint.stateUtf8 = p.baseline.stateUtf8 + p.checkpoint.compactedRecordUtf8; },
  ]) {
    const p = persisted(); mutate(p); rebind(p.checkpoint, p.expected);
    assert.equal(extractCheckpoint(p.checkpoint, p.expected).status, 'FAIL');
    assert.throws(() => eProjection.extractPersistedSummary(Buffer.from(p.checkpoint.stateUtf8), { nativeThreadId: parent, nativeTurnId: p.expected.nativeTurnId,
      actionId: p.expected.actionId, beforeBytes: Buffer.byteLength(p.baseline.stateUtf8), beforeSha256: p.baseline.stateSha256,
      dispatchedAt: '2026-10-01T02:30:02Z', settledAt: '2026-10-01T02:30:04Z', summaryPrefix: 'SUMMARY_PREFIX\n' }));
  }
});
test('exact persisted payload plus query/policy derives E wrapper without replacement history or oracle answers', async () => {
  const p = await projected();
  const last = p.derived.freshProjection.input.at(-1).content[0].text;
  assert.equal(last, eProjection.summaryProbeText(summary, policy, p.request));
  assert.equal(last.includes('ORIGINAL_HISTORY_MARKER_NOT_ALLOWED_IN_PROBE'), false);
  assert.equal(last.includes('38400 bit/s'), false); assert.equal(last.includes('SCORER_ONLY_NEVER_MODEL_INPUT'), false);
  assert.equal(p.extraction.messages, undefined);
  const poisoned = clone(p.checkpoint); poisoned.messages = [{ role: 'system', content: 'opaque declared summary' }];
  assert.equal(extractCheckpoint(poisoned, p.expected).status, 'FAIL');
});
test('real E collector raw/normalized captures satisfy only the explicitly synthetic host contract', async t => {
  const p = await collected(t);
  assert.equal(verifySummaryIsolation(p.capture, p.expectedProbe).status, 'NOT_TESTED'); // actual launcher scope absent
  const probe = syntheticContractCapture(p);
  const result = verifySummaryIsolation(probe, p.expectedProbe);
  assert.equal(result.status, 'PASS'); assert.equal(result.firstRequestSha256, p.capture.captureSha256);
  assert.deepEqual(JSON.parse(p.capture.normalizedRequestUtf8), p.derived.freshProjection.normalizedRequest);
  assert.match(p.capture.normalizedRequestUtf8, /Sova Qwen policy adaptation/);
  assert.equal((await readdir(p.directory)).length, 2);
});
test('same missing binding on expected and captured receipts never passes through JSON omission', async t => {
  const p = await collected(t), original = syntheticContractCapture(p);
  for (const field of ['windowId', 'parentStateSha256', 'settlementReceiptSha256', 'runId', 'actionId']) {
    const expected = clone(p.expectedProbe), probe = clone(original);
    delete expected[field]; const receipt = JSON.parse(probe.projectionReceiptUtf8); delete receipt[field];
    probe.projectionReceiptUtf8 = JSON.stringify(receipt); probe.projectionReceiptSha256 = sha256(probe.projectionReceiptUtf8);
    assert.notEqual(verifySummaryIsolation(probe, expected).status, 'PASS', field);
  }
  for (const field of ['compactedRecordSha256', 'summarySha256', 'querySha256', 'policySha256', 'collectorSourceSha256']) {
    const expected = clone(p.expectedProbe), probe = clone(original); delete expected.freshProjection[field];
    const receipt = JSON.parse(probe.projectionReceiptUtf8); delete receipt[field]; probe.projectionReceiptUtf8 = JSON.stringify(receipt);
    probe.projectionReceiptSha256 = sha256(probe.projectionReceiptUtf8);
    assert.equal(verifySummaryIsolation(probe, expected).status, 'NOT_TESTED', field);
  }
});
test('missing raw proof stays NOT_TESTED; changed state/record/constructor/settlement/normalized envelope fails', async t => {
  const p = await collected(t), original = syntheticContractCapture(p);
  for (const field of ['projectionReceiptUtf8', 'probeSettledOperationUtf8', 'normalizedRequestUtf8', 'collectorManifestUtf8', 'scopeReceiptUtf8', 'parentStateAfter']) {
    const probe = clone(original); delete probe[field]; assert.equal(verifySummaryIsolation(probe, p.expectedProbe).status, 'NOT_TESTED', field);
  }
  for (const mutate of [
    (p: any) => { p.parentStateAfter.stateUtf8 += 'replayed-answer'; p.parentStateAfter.stateSha256 = sha256(p.parentStateAfter.stateUtf8); },
    (p: any) => { const r = JSON.parse(p.projectionReceiptUtf8); r.compactedRecordSha256 = syntheticHash; p.projectionReceiptUtf8 = JSON.stringify(r); p.projectionReceiptSha256 = sha256(p.projectionReceiptUtf8); },
    (p: any) => { p.collectorManifestUtf8 += ' '; },
    (p: any) => { const r = JSON.parse(p.probeSettledOperationUtf8); r.settlement = 'settled'; p.probeSettledOperationUtf8 = JSON.stringify(r); p.probeSettledOperationSha256 = sha256(p.probeSettledOperationUtf8); },
    (p: any) => { const r = JSON.parse(p.normalizedRequestUtf8); r.messages[0].content += ' hidden parent history'; p.normalizedRequestUtf8 = JSON.stringify(r); p.normalizedSha256 = sha256(p.normalizedRequestUtf8); },
  ]) { const probe = clone(original); mutate(probe); assert.equal(verifySummaryIsolation(probe, p.expectedProbe).status, 'FAIL'); }
});
test('real E dispatch guard rejects changed instructions, added original history and native identity before counting', async t => {
  for (const mutate of [
    (r: any) => { r.instructions += ' leaked answer'; }, (r: any) => { r.input.push(typed('user', 'original history without canary')); },
    (r: any) => { r.client_metadata.turn_id = 'foreign-turn'; },
  ]) await assert.rejects(collected(t, mutate));
});
test('frozen full envelope and compiled carriers cannot be replaced by adapter declarations', async t => {
  const p = await collected(t), original = syntheticContractCapture(p);
  for (const mutate of [
    (r: any) => { r.instructions += ' hidden instruction'; }, (r: any) => { r.client_metadata.extra = 'parent-data'; },
    (r: any) => { r.previous_response_id = 'parent-response'; }, (r: any) => { r.input[0].id = 'unapproved-carrier'; },
    (r: any) => { r.tools = [{ type: 'function', name: 'read_answer_key', description: 'hidden answer' }]; },
  ]) {
    const probe = clone(original), r = JSON.parse(probe.firstRequestUtf8); mutate(r); probe.firstRequestUtf8 = JSON.stringify(r);
    probe.captureSha256 = sha256(probe.firstRequestUtf8); probe.inputReceiptSha256 = probe.captureSha256;
    assert.equal(verifySummaryIsolation(probe, p.expectedProbe).status, 'FAIL');
  }
  assert.throws(() => bindReviewedEnvelope({ instructions: '@h040:unapproved-variable' }, { probeThreadId, probeTurnId }));
});
test('real E disabled adapter advertises no fabricated native capabilities or runtime observations', async () => {
  const adapter = createNativeAdapter(), runtime = await adapter.runtime();
  assert.equal(adapter.enabled, false); assert.deepEqual(adapter.capabilities, []);
  for (const key of ['version', 'sourceRevision', 'binarySha256', 'model', 'modelRevision', 'tokenizerRevision']) {
    assert.equal(runtime[key].value, null); assert.ok(runtime[key].reason);
  }
  await assert.rejects(adapter.open({ signal: AbortSignal.abort() }));
  await assert.rejects(runAcceptance({ packet, adapter, sink: {}, normalizeResponses: undefined }), /disabled/);
});

function acceptedResume() {
  const p = persisted(), continued = p.checkpoint.stateUtf8 + JSON.stringify({ type: 'response_item', payload: typed('assistant', 'Accepted latest technical continuation') }) + '\n';
  const checkpoint = capturedState(continued), artifacts = { 'sensor-policy.json': { watchdog: '1500 ms', deployment: 'NOT_AUTHORIZED' }, 'engineering-calculation.json': { unit: 'V', value: 2.153846153846154 } };
  const artifactHashes = Object.fromEntries(Object.entries(artifacts).map(([key, value]) => [key, sha256(stableJson(value))]));
  const originalUtf8 = Object.fromEntries(Object.entries(artifacts).map(([key, value]) => [key, JSON.stringify(value, null, 2) + '\n']));
  const continuationActionId = actionIdFor(runId, 3, 'continuation');
  const originalReceiptUtf8 = JSON.stringify({ source: 'owned-store-registered-continuation-artifacts', sessionId: 'synthetic-store-session', runId: 'synthetic-store-continuation-run',
    artifacts: Object.entries(originalUtf8).map(([name, bytes]) => ({ artifactId: `synthetic-artifact-${name}`, messageId: 'synthetic-message', captureId: `synthetic-original-${name}`,
      name, runId: 'synthetic-store-continuation-run', sha256: sha256(bytes), bytes: Buffer.byteLength(bytes, 'utf8') })) });
  const baseline = captureAcceptedArtifactBaseline({ artifactReceiptUtf8: originalReceiptUtf8, artifactReceiptSha256: sha256(originalReceiptUtf8),
    sessionId: 'synthetic-store-session', runId: 'synthetic-store-continuation-run', actionId: continuationActionId, nativeThreadId: parent, parentState: checkpoint },
    checkpoint, { runId, sessionId: 'synthetic-store-session', actionId: continuationActionId, nativeThreadId: parent });
  assert.equal(baseline.status, 'PASS'); assert.ok('baseline' in baseline);
  const actionId = actionIdFor(runId, 3, 'cold-resume-after-continuation'), accepted = { checkpoint, artifactHashes, actionId: continuationActionId, artifactBaseline: baseline.baseline };
  const restartReceiptUtf8 = JSON.stringify({ source: 'native-owned-host-cold-resume', runId, actionId, windowId, nativeThreadId: parent,
    checkpointStateSha256: checkpoint.stateSha256, beforeHostId: 'synthetic-application-1', afterHostId: 'synthetic-application-2',
    beforeApplicationProcessId: 'synthetic-app-pid-1', afterApplicationProcessId: 'synthetic-app-pid-2', oldApplicationExitConfirmed: true,
    oldGatewaySettled: true, noActionReplay: true, capturedAfterRestart: true, acceptedContinuationActionId: accepted.actionId, acceptedArtifactHashes: artifactHashes });
  const restartEvidence = { capturedBy: 'host', beforeProcessId: 'synthetic-app-pid-1', afterProcessId: 'synthetic-app-pid-2',
    nativeThreadId: parent, beforeStateSha256: checkpoint.stateSha256, afterStateUtf8: checkpoint.stateUtf8, replayedActionIds: [], receiptSha256: syntheticHash,
    restartReceiptUtf8, restartReceiptSha256: sha256(restartReceiptUtf8) };
  const artifactReceiptUtf8 = JSON.stringify({ source: 'native-owned-workspace-artifacts', runId, sessionId: 'synthetic-store-session', nativeThreadId: parent, actionId, windowId, afterHostId: 'synthetic-application-2',
    acceptedArtifactReceiptSha256: baseline.baseline.artifactReceiptSha256, acceptedArtifactReceiptBytes: baseline.baseline.artifactReceiptBytes,
    acceptedStoreRunId: baseline.baseline.storeRunId, acceptedContinuationActionId: continuationActionId, checkpointStateSha256: checkpoint.stateSha256,
    captureId: 'synthetic-after-restart-capture', artifactUtf8: originalUtf8 });
  return { accepted, expected: { runId, actionId, windowId }, result: { artifacts, restartEvidence, artifactReceiptUtf8, artifactReceiptSha256: sha256(artifactReceiptUtf8) }, compacted: p.checkpoint };
}
test('after-continuation cold resume binds actual application lifecycle and latest artifact bytes, not earlier summary checkpoint', () => {
  const p = acceptedResume();
  assert.equal(verifyAcceptedContinuationResume(p.result, p.accepted, p.expected).status, 'PASS');
  assert.notEqual(p.accepted.checkpoint.stateSha256, p.compacted.stateSha256);
  const old = clone(p.accepted); old.checkpoint = p.compacted;
  assert.equal(verifyAcceptedContinuationResume(p.result, old, p.expected).status, 'FAIL');
  const routine: Omit<typeof p.result, 'restartEvidence'> & { restartEvidence: Omit<typeof p.result.restartEvidence, 'restartReceiptUtf8'> & { restartReceiptUtf8?: string } } = clone(p.result); delete routine.restartEvidence.restartReceiptUtf8;
  assert.equal(verifyAcceptedContinuationResume(routine, p.accepted, p.expected).status, 'NOT_TESTED');
  const missing: Omit<typeof p.result, 'artifactReceiptUtf8'> & { artifactReceiptUtf8?: string } = clone(p.result); delete missing.artifactReceiptUtf8;
  assert.equal(verifyAcceptedContinuationResume(missing, p.accepted, p.expected).status, 'NOT_TESTED');
  const changed = clone(p.result); changed.artifacts['sensor-policy.json'].deployment = 'AUTHORIZED';
  assert.equal(verifyAcceptedContinuationResume(changed, p.accepted, p.expected).status, 'FAIL');
  const sameHost = clone(p.result), lifecycle = JSON.parse(sameHost.restartEvidence.restartReceiptUtf8);
  lifecycle.afterHostId = lifecycle.beforeHostId; sameHost.restartEvidence.restartReceiptUtf8 = JSON.stringify(lifecycle);
  sameHost.restartEvidence.restartReceiptSha256 = sha256(sameHost.restartEvidence.restartReceiptUtf8);
  assert.equal(verifyAcceptedContinuationResume(sameHost, p.accepted, p.expected).status, 'FAIL');
  assert.equal(verifyColdResume(p.result.restartEvidence, p.accepted.checkpoint, { ...p.expected, requireHostRestart: true }).status, 'PASS');
});
test('accepted continuation preserves original raw bytes separately from property-order-indifferent semantic hashes', () => {
  const p = acceptedResume();
  assert.equal(verifyAcceptedContinuationResume(p.result, p.accepted, p.expected).status, 'PASS');
  const missing = clone(p.accepted); delete missing.artifactBaseline;
  assert.equal(verifyAcceptedContinuationResume(p.result, missing, p.expected).status, 'NOT_TESTED');
  for (const rewrite of [(bytes: string) => JSON.stringify(JSON.parse(bytes)),
    (bytes: string) => JSON.stringify(Object.fromEntries(Object.entries(JSON.parse(bytes)).reverse()), null, 2) + '\n']) {
    const changed = clone(p.result), capture = JSON.parse(changed.artifactReceiptUtf8);
    const name = 'sensor-policy.json', before = capture.artifactUtf8[name];
    capture.artifactUtf8[name] = rewrite(before);
    assert.notEqual(capture.artifactUtf8[name], before);
    assert.equal(sha256(stableJson(JSON.parse(capture.artifactUtf8[name]))), p.accepted.artifactHashes[name]);
    changed.artifacts[name] = JSON.parse(capture.artifactUtf8[name]);
    changed.artifactReceiptUtf8 = JSON.stringify(capture); changed.artifactReceiptSha256 = sha256(changed.artifactReceiptUtf8);
    assert.equal(verifyAcceptedContinuationResume(changed, p.accepted, p.expected).status, 'FAIL');
  }
  for (const key of ['artifactReceiptSha256', 'artifactReceiptBytes', 'storeRunId', 'actionId', 'nativeThreadId', 'checkpointStateSha256']) {
    const altered = clone(p.accepted); altered.artifactBaseline[key] = key === 'artifactReceiptBytes' ? 1 : 'synthetic-substitution';
    assert.equal(verifyAcceptedContinuationResume(p.result, altered, p.expected).status, 'FAIL', key);
  }
});
test('per-dimension evidence keeps synthetic/partial actual PASS distinct from native qualification', async () => {
  const answer = { answers: Object.fromEntries(activeFacts(packet.truth, 1).map((f: any) => [f.id, { value: f.current.value }])) };
  const { scoreRecall } = await import('../../acceptance/compaction/scorer.mjs');
  const record = makeRecord({ packet, runId, cycle: 1, mode: 'summary-only', qualification: 'synthetic',
    observation: { outcome: 'completed', actionId: actionIdFor(runId, 1, 'summary-only'), nativeThreadId: probeThreadId, nativeTurnId: probeTurnId,
      isolation: { captureSha256: syntheticHash }, settlement: { state: 'released', receiptSha256: syntheticHash, automaticReplay: false } },
    originals: { beforeSha256: syntheticHash, afterSha256: syntheticHash, recoverable: true, receiptSha256: syntheticHash },
    grade: scoreRecall(packet.truth, 1, answer), isolation: { status: 'PASS', errors: [] }, runtime: undefined, compactionObservation: undefined, retrieval: undefined });
  const q = summarizeQualification([record], packet.truth), schema = JSON.parse(await readFile(new URL('../../acceptance/compaction/qualification.schema.json', import.meta.url), 'utf8'));
  assert.deepEqual(validateShape(q, schema), []);
  assert.equal(q.dimensions.criticalFacts.actualStatus, 'PASS'); assert.equal(q.dimensions.criticalFacts.nativeStatus, 'NOT_TESTED');
  assert.deepEqual(q.dimensions.criticalFacts.observations[0].exactFacts, { correct: 49, total: 49 });
  assert.deepEqual(q.dimensions.criticalFacts.missingCycles, [2, 3]);
  for (const name of ['corrections', 'supersededChoices', 'continuation', 'coldResumeAfterContinuation', 'durableRetrieval', 'cleanChild']) assert.equal(q.dimensions[name].nativeStatus, 'NOT_TESTED');
  assert.equal(q.nativeAcceptance, 'NOT_TESTED'); assert.equal(q.semanticAcceptance, 'NOT_TESTED');
  const duplicate = summarizeQualification([record, clone(record)], packet.truth); assert.equal(duplicate.dimensions.criticalFacts.actualStatus, 'FAIL');
});

test('one-cycle stage invokes the real E collector with synthetic host data and cannot qualify the full suite', async t => {
  const p = await collected(t), probe = syntheticContractCapture(p), inputPacket = clone(packet), calls: string[] = [], records: any[] = [];
  inputPacket.config = { ...inputPacket.config, enabled: true, profile: 'h040-summary-stage-v1', cycles: [1], maximumNativeActions: 9,
    review: { freshProjectionSpec: p.spec, responseEnvelope: envelopeTemplate, durableToolDefinitions: [], windowId } };
  const originalRecordHashes = Object.fromEntries(packet.corpus.records.filter((r: any) => r.cycle === 1).map((r: any) => [r.id, sha256(r.content)]));
  let state = p.baseline;
  const common = { outcome: 'completed', settlement: { state: 'released', receiptSha256: p.expectedProbe.settlementReceiptSha256, automaticReplay: false } };
  const adapter: any = { interfaceVersion: 'h039-compaction-adapter-v1', kind: 'synthetic',
    capabilities: ['qualified-fresh-persisted-message-projection', 'host-captured-probe-input', 'tools-and-files-denied-for-summary', 'settlement-receipts'],
    async runtime() { calls.push('runtime'); return undefined; }, async open() { calls.push('open'); return { nativeThreadId: parent }; },
    async append() { calls.push('append'); },
    async originals() { calls.push('originals'); return { capturedBy: 'host', recordHashes: originalRecordHashes, parentState: state, receiptSha256: syntheticHash }; },
    async compact({ actionId }: any) { calls.push('compact'); state = p.checkpoint; return { ...common, actionId, nativeThreadId: parent,
      nativeTurnId: p.expected.nativeTurnId, summaryState: 'complete', contextSha256: p.checkpoint.stateSha256, checkpoint: p.checkpoint }; },
    async probe({ request, actionId }: any) { calls.push('probe'); assert.deepEqual(request, p.request); assert.equal(actionId, p.expectedProbe.actionId);
      // Explicit answer-key-backed synthetic response, never supplied to E's
      // constructor/request/normalized input or mounted as a model answer file.
      return { ...common, actionId, nativeThreadId: probeThreadId, nativeTurnId: probeTurnId, isolation: probe,
        answer: { answers: Object.fromEntries(activeFacts(packet.truth, 1).map((f: any) => [f.id, { value: f.current.value }])) } }; },
    async close() { calls.push('close'); } };
  const result = await runAcceptance({ packet: inputPacket, adapter, qualification: 'synthetic', runId, normalizeResponses: translateResponses,
    sink: { async record(r: any) { records.push(r); }, async private() {} } });
  assert.equal(result.observedStatus, 'PASS'); assert.equal(result.nativeAcceptance, 'NOT_TESTED'); assert.equal(result.semanticAcceptance, 'NOT_TESTED');
  assert.equal(result.actionCount, 9); assert.equal(records.length, 1); assert.equal(records[0].qualification, 'synthetic');
  assert.deepEqual(calls, ['runtime', 'open', 'append', 'originals', 'compact', 'originals', 'probe', 'originals', 'close']);
  assert.equal(result.dimensions.criticalFacts.actualStatus, 'PASS'); assert.equal(result.dimensions.continuation.nativeStatus, 'NOT_TESTED');
  const weak = clone(inputPacket); let invoked = false;
  const weakAdapter = { ...adapter, async compact(args: any) { const c = await adapter.compact(args); c.checkpoint = { ...c.checkpoint, settledOperationUtf8: undefined }; return c; },
    async probe() { invoked = true; throw Error('must not dispatch'); } };
  state = p.baseline;
  const stopped = await runAcceptance({ packet: weak, adapter: weakAdapter, qualification: 'synthetic', runId, normalizeResponses: translateResponses,
    sink: { async record() {}, async private() {} } });
  assert.equal(stopped.status, 'NOT_TESTED'); assert.equal(invoked, false);
});
