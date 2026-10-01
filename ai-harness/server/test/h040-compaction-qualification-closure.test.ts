import assert from 'node:assert/strict';
import test from 'node:test';
import { readFile } from 'node:fs/promises';
import { fixture, makeRecord, verifyOwnedClose } from '../../acceptance/compaction/controller.mjs';
import { metadata, measured, validateRecord, validateShape } from '../../acceptance/compaction/evidence.mjs';
import { activeFacts, actionIdFor, scoreRecall, sha256 } from '../../acceptance/compaction/scorer.mjs';
import { summarizeQualification } from '../../acceptance/compaction/qualification.mjs';

// Offline record fixtures exercise the native-label aggregation branch only.
// Every identity, receipt and clock below is synthetic test data, not observed
// native evidence, sandbox attestation, model output or live qualification.
// No adapter is imported or invoked; production configuration stays disabled.
const packet = await fixture();
const schema = JSON.parse(await readFile(new URL('../../acceptance/compaction/qualification.schema.json', import.meta.url), 'utf8'));
const runId = 'synthetic-qualification-closure';
const parent = 'synthetic-parent';
const hash = sha256('SYNTHETIC aggregation fixture, not a native receipt');
const originals = { beforeSha256: hash, afterSha256: hash, recoverable: true, receiptSha256: hash };
const runtime = { name: 'codex', version: metadata('0.158.0'),
  sourceRevision: metadata('064c6b8c737f5b41d171fdda80bd9ef10ad06eb3'), binarySha256: metadata(hash),
  model: metadata('synthetic-model'), modelRevision: metadata('synthetic-revision'),
  tokenizerRevision: metadata('synthetic-tokenizer'), promptRevision: 'kpm-technical-v1' };

// Independent full-profile contract: three recall/retrieval/continuation cycles,
// then both cold boundaries and a clean child observation at cycle three.
const required = [
  [1, 'summary-only'], [1, 'durable-retrieval'], [1, 'continuation'],
  [2, 'summary-only'], [2, 'durable-retrieval'], [2, 'continuation'],
  [3, 'summary-only'], [3, 'durable-retrieval'], [3, 'continuation'],
  [3, 'cold-resume'], [3, 'cold-resume-after-continuation'], [3, 'child-context'],
] as const;

function passingObservations(qualification = 'native') {
  assert.equal(packet.config.enabled, false);
  return required.map(([cycle, mode]) => {
    const actionId = actionIdFor(runId, cycle, mode);
    const thread = `synthetic-${mode}-${cycle}`, turn = `${thread}-turn`;
    const compactAction = actionIdFor(runId, cycle, 'compact');
    const compact = { actionId: compactAction, nativeThreadId: parent,
      operationWindowId: 'synthetic-operation-window', verifierNativeWindowId: `${parent}:${cycle}`,
      trigger: { type: 'manual', evidence: [{ kind: 'manual-action', ref: 'synthetic-private-receipt', sha256: hash,
        runId, actionId: compactAction, nativeThreadId: parent }] } };
    const recallMode = ['summary-only', 'durable-retrieval', 'cold-resume'].includes(mode);
    const answer = { answers: Object.fromEntries(activeFacts(packet.truth, cycle).map((f: any) => [f.id, { value: f.current.value }])) };
    const grade = recallMode ? scoreRecall(packet.truth, cycle, answer) : { status: 'PASS', errors: [] };
    const artifacts = ['continuation', 'cold-resume-after-continuation'].includes(mode)
      ? { 'sensor-policy.json': { synthetic: 'accepted policy bytes' }, 'engineering-calculation.json': { synthetic: 'accepted calculation bytes' } } : undefined;
    const record = makeRecord({ packet, runId, cycle, mode, qualification, runtime,
      observation: { outcome: 'completed', actionId, nativeThreadId: thread, nativeTurnId: turn, artifacts,
        durationMs: measured(17, 'synthetic-fixture-clock', hash),
        isolation: { captureSha256: hash, nativeThreadId: thread, nativeTurnId: turn, parentNativeThreadId: parent, actionId },
        settlement: { state: 'released', receiptSha256: hash, automaticReplay: false } },
      compactionObservation: compact, originals, grade,
      isolation: { status: 'PASS', errors: [], firstRequestSha256: hash, inputManifestSha256: hash, scopeReceiptSha256: hash },
      ...(mode === 'durable-retrieval' ? { retrieval: { used: true, callIds: [`synthetic-read-${cycle}`],
        sourceIds: packet.corpus.records.filter((r: any) => r.cycle <= cycle).map((r: any) => r.id), traceSha256: hash } } : {}) });
    assert.deepEqual(validateRecord(record), []);
    assert.equal(record.status, 'PASS', `${cycle}:${mode}`);
    return record;
  });
}

function cleanupFault(grade: any) {
  const record = makeRecord({ packet, runId, cycle: 3, mode: 'fault', qualification: 'native', runtime,
    observation: { outcome: 'unknown', failure: grade.status === 'FAIL' ? 'cleanup-unconfirmed' : 'cleanup-receipt-unqualified',
      settlement: { state: 'unknown', receiptSha256: null, automaticReplay: false } }, originals, grade });
  assert.deepEqual(validateRecord(record), []);
  return record;
}

function summary(records: any[]) {
  const result = summarizeQualification(records, packet.truth);
  assert.deepEqual(validateShape(result, schema), []);
  return result;
}

function expectAggregate(result: any, status: string) {
  assert.equal(result.nativeAcceptance, status);
  assert.equal(result.semanticAcceptance, status);
}

test('offline complete twelve native-label observations retain qualified aggregate PASS', () => {
  const records = passingObservations();
  assert.equal(records.length, 12);
  const result = summary(records);
  assert.equal(Object.keys(result.dimensions).length, 10);
  for (const dimension of Object.values(result.dimensions) as any[]) {
    assert.equal(dimension.nativeStatus, 'PASS');
    assert.deepEqual(dimension.missingCycles, []);
  }
  expectAggregate(result, 'PASS');
});

test('all twelve PASS observations plus actual close-verifier NOT_TESTED fault cannot aggregate PASS', () => {
  const proof = verifyOwnedClose(undefined, { runId, operationWindowId: 'synthetic-operation-window', observedSettlements: [] });
  assert.equal(proof.status, 'NOT_TESTED');
  const fault = cleanupFault(proof);
  assert.equal(fault.status, 'NOT_TESTED');
  const result = summary([...passingObservations(), fault]);
  for (const dimension of Object.values(result.dimensions) as any[]) assert.equal(dimension.nativeStatus, 'PASS');
  expectAggregate(result, 'NOT_TESTED');
});

test('unknown or absent native fault status is unqualified, without inventing FAIL or weakening record schema', () => {
  const fault = cleanupFault({ status: 'NOT_TESTED', errors: ['synthetic-cleanup-receipt-absent'] });
  for (const status of ['UNKNOWN', undefined, null]) {
    const unknown = { ...fault, status };
    assert.notDeepEqual(validateRecord(unknown), []); // Unknown is not a new schema status.
    expectAggregate(summary([...passingObservations(), unknown]), 'NOT_TESTED');
  }
  // Even a declared PASS cannot turn a fault observation into qualified cleanup.
  expectAggregate(summary([...passingObservations(), { ...fault, status: 'PASS' }]), 'NOT_TESTED');
});

test('actual close-verifier FAIL overrides unknown cleanup and otherwise passing dimensions', () => {
  const proof = verifyOwnedClose({ closeReceiptUtf8: '{}' },
    { runId, operationWindowId: 'synthetic-operation-window', observedSettlements: [] });
  assert.equal(proof.status, 'FAIL');
  const failed = cleanupFault(proof), unknown = cleanupFault({ status: 'NOT_TESTED', errors: [] });
  assert.equal(failed.status, 'FAIL');
  for (const faults of [[failed], [unknown, failed], [failed, unknown]])
    expectAggregate(summary([...passingObservations(), ...faults]), 'FAIL');
});

test('missing mandatory coverage and synthetic complete coverage cannot qualify native acceptance', () => {
  expectAggregate(summary(passingObservations().filter((r: any) => r.mode !== 'cold-resume-after-continuation')), 'NOT_TESTED');
  const synthetic = summary(passingObservations('synthetic'));
  for (const dimension of Object.values(synthetic.dimensions) as any[]) {
    assert.equal(dimension.actualStatus, 'PASS');
    assert.equal(dimension.nativeStatus, 'NOT_TESTED');
  }
  expectAggregate(synthetic, 'NOT_TESTED');
});
