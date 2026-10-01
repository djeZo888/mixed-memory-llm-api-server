import assert from 'node:assert/strict';
import test from 'node:test';
import { actionIdFor, activeFacts, scoreContinuation, sha256, stableJson } from '../../acceptance/compaction/scorer.mjs';
import { fixture, runAcceptance, actionPlan, settlementReserve, verifyOwnedClose } from '../../acceptance/compaction/controller.mjs';

const packet = await fixture(), hash = sha256('SYNTHETIC controller host boundary'), runId = 'synthetic-full-h040';
const parent = 'synthetic-parent';
const clone = structuredClone;
const typed = (m: any) => ({ type: 'message', role: m.role, content: [{ type: m.role === 'assistant' ? 'output_text' : 'input_text', text: m.content }] });
const scope = (thread: string, turn: string, action: string, tools: string[] = []) => {
  const scopeReceiptUtf8 = JSON.stringify({ source: 'native-launcher-effective-scope', nativeThreadId: thread, nativeTurnId: turn,
    actionId: action, allowedTools: tools, readRoots: [], writeRoots: [], network: 'deny', answerKeyMounted: false });
  return { scopeReceiptUtf8, scopeReceiptSha256: sha256(scopeReceiptUtf8) };
};

// Independent engineering expectations. This adapter is explicitly SYNTHETIC
// and answer-key backed. It tests controller sequencing, not actual inference,
// artifacts, application restarts, sandbox enforcement or native qualification.
const outputs: Record<number, any> = {
  1: {
    'sensor-policy.json': { boardRevision: 'KPM-R1', i2c: { sda: 'GPIO8', scl: 'GPIO9', address: '0x48', speed: '100 kHz' },
      uart: { tx: 'GPIO17', rx: 'GPIO18', de: 'GPIO7', baud: '115200 bit/s', format: '8N1' },
      adc: { pin: 'GPIO4', top: '100000 ohm', bottom: '10000 ohm', limit: '2.6 V' }, samplePeriod: '250 ms', watchdog: '2000 ms', deployment: 'NOT_AUTHORIZED', benchCheck: 'NOT_TESTED' },
    'engineering-calculation.json': { ledCurrent: { value: .0012, unit: 'A' }, resistorPower: { value: .00144, unit: 'W' }, maximumAdcVoltage: { value: 2.4, unit: 'V' }, adcWithinLimit: true },
  },
  2: {
    'sensor-policy.json': { boardRevision: 'KPM-R2', i2c: { sda: 'GPIO10', scl: 'GPIO11', address: '0x49', speed: '400 kHz' },
      uart: { tx: 'GPIO17', rx: 'GPIO16', de: 'GPIO5', baud: '57600 bit/s', format: '8E1' },
      adc: { pin: 'GPIO4', top: '82000 ohm', bottom: '10000 ohm', limit: '2.2 V' }, samplePeriod: '500 ms', watchdog: '2000 ms', deployment: 'NOT_AUTHORIZED', benchCheck: 'NOT_TESTED' },
    'engineering-calculation.json': { ledCurrent: { value: .0014634146341463415, unit: 'A' }, resistorPower: { value: .00175609756097561, unit: 'W' }, maximumAdcVoltage: { value: 1.9565217391304348, unit: 'V' }, adcWithinLimit: true },
  },
  3: {
    'sensor-policy.json': { boardRevision: 'KPM-R3', i2c: { sda: 'GPIO13', scl: 'GPIO14', address: '0x48', speed: '400 kHz' },
      uart: { tx: 'GPIO15', rx: 'GPIO16', de: 'GPIO5', baud: '38400 bit/s', format: '8E1' },
      adc: { pin: 'GPIO4', top: '120000 ohm', bottom: '10000 ohm', limit: '2.4 V' }, samplePeriod: '250 ms', watchdog: '1500 ms', deployment: 'NOT_AUTHORIZED', benchCheck: 'NOT_TESTED' },
    'engineering-calculation.json': { ledCurrent: { value: .001911764705882353, unit: 'A' }, resistorPower: { value: .002485294117647059, unit: 'W' }, maximumAdcVoltage: { value: 2.153846153846154, unit: 'V' }, adcWithinLimit: true },
  },
};
function syntheticAdapter(options: any = {}) {
  const calls: string[] = [];
  let state = JSON.stringify({ type: 'session_meta', payload: { id: parent } }) + '\n';
  const capture = () => {
    const receiptUtf8 = JSON.stringify({ source: 'owned-native-persisted-state', captureId: 'synthetic-state-capture', sessionId: 'synthetic-session', sourceRef: 'profile/synthetic-rollout',
      nativeThreadId: parent, stateSha256: sha256(state), bytes: Buffer.byteLength(state), observedAt: '2026-10-01T02:32:00Z' });
    return { capturedBy: 'host', nativeThreadId: parent, stateUtf8: state, stateSha256: sha256(state), receiptUtf8, receiptSha256: sha256(receiptUtf8) };
  };
  const settled = { state: 'released', receiptSha256: hash, automaticReplay: false };
  const common = (actionId: string, turn: string, thread = parent) => ({ outcome: 'completed', actionId, nativeThreadId: thread, nativeTurnId: turn, settlement: settled });
  const answer = (cycle: number, durable = false) => ({ answers: Object.fromEntries(activeFacts(packet.truth, cycle).map((f: any) => [f.id,
    durable ? { value: f.current.value, sourceIds: f.current.sourceIds } : { value: f.current.value }])) });
  const isolation = (checkpoint: any, request: any, cycle: number, mode: string, actionId: string, tools: string[] = []) => {
    const thread = `synthetic-${mode}-${cycle}`, turn = `${thread}-turn`;
    const firstRequestUtf8 = JSON.stringify({ input: [...checkpoint.messages, { role: 'user', content: stableJson(request) }].map(typed), tools: tools.map(name => ({ type: 'function', name })) });
    return { capturedBy: 'host', nativeThreadId: thread, nativeTurnId: turn, parentNativeThreadId: parent, runId, actionId,
      firstRequestUtf8, captureSha256: sha256(firstRequestUtf8), inputReceiptSha256: sha256(firstRequestUtf8), contextSha256: checkpoint.stateSha256,
      qualifiedForkReceiptSha256: hash, ...scope(thread, turn, actionId, tools), parentStateAfter: capture(),
      toolsDenied: true, filesDenied: true, networkDenied: true, accessiblePaths: [], originalRecordIds: [], toolCalls: [], answerKeyExposed: false, parentHistoryExposed: false };
  };
  const adapter: any = { interfaceVersion: 'h039-compaction-adapter-v1', kind: 'synthetic', capabilities: [...packet.config.requiredCapabilities, 'cold-resume-after-continuation'],
    async runtime() { return undefined; }, async open() { return { sessionId: 'synthetic-session', nativeThreadId: parent }; },
    async append({ records }: any) { for (const r of records) state += JSON.stringify({ type: 'response_item', payload: typed({ role: r.role, content: r.content }) }) + '\n'; },
    async originals({ cycle }: any) { return { capturedBy: 'host', parentState: capture(), receiptSha256: hash,
      recordHashes: Object.fromEntries(packet.corpus.records.filter((r: any) => r.cycle <= cycle).map((r: any) => [r.id, sha256(r.content)])) }; },
    async compact({ cycle, actionId, baseline, windowId }: any) {
      calls.push(`compact-${cycle}`);
      const compactedRecordUtf8 = JSON.stringify({ timestamp: '2026-10-01T02:31:01Z', type: 'compacted', payload: { message: 'Synthetic summary; source data boundary only.' } }) + '\n';
      state += compactedRecordUtf8;
      const checkpoint: any = { ...capture(), compactedRecordUtf8, compactedRecordSha256: sha256(compactedRecordUtf8), messages: [{ role: 'system', content: 'Synthetic summary; source data boundary only.' }] };
      const turn = `synthetic-compact-${cycle}`;
      checkpoint.bindingReceiptUtf8 = JSON.stringify({ source: 'native-rollout-record-owner', nativeThreadId: parent, compactionActionId: actionId,
        nativeTurnId: turn, windowId, recordSha256: checkpoint.compactedRecordSha256, stateSha256: checkpoint.stateSha256, recordId: `synthetic-record-${cycle}`, sourceRef: 'synthetic-source' });
      checkpoint.bindingReceiptSha256 = sha256(checkpoint.bindingReceiptUtf8);
      checkpoint.settledOperationUtf8 = JSON.stringify({ source: 'native-compaction-settlement', status: 'completed', settlement: 'released', nativeThreadId: parent,
        actionId, nativeTurnId: turn, windowId, baselineStateSha256: baseline.stateSha256, postStateSha256: checkpoint.stateSha256,
        recordSha256: checkpoint.compactedRecordSha256, compactionId: `synthetic-owned-compact-${cycle}`, startedAt: '2026-10-01T02:31:00Z', completedAt: '2026-10-01T02:31:02Z' });
      checkpoint.settledOperationSha256 = sha256(checkpoint.settledOperationUtf8);
      return { ...common(actionId, turn), summaryState: 'complete', contextSha256: checkpoint.stateSha256, checkpoint };
    },
    async probe({ cycle, mode, actionId, checkpoint, request, allowedTools, hostOnlyHoldouts }: any) {
      const proof = isolation(checkpoint, request, cycle, mode, actionId, allowedTools), compiledContextText = 'Synthetic context with exact holdout identifiers absent.';
      return { ...common(actionId, proof.nativeTurnId, proof.nativeThreadId), answer: answer(cycle, mode === 'durable-retrieval'), isolation: proof,
        ...(mode === 'durable-retrieval' ? { retrievalContext: { capturedBy: 'host', compiledContextText, contextSha256: sha256(compiledContextText),
          qualifiedProjectionReceiptSha256: hash, omittedFactIds: hostOnlyHoldouts.map((h: any) => h.id), answerKeyExposed: false, parentHistoryExposed: false, accessiblePaths: [] },
        retrieval: { capturedBy: 'host', calls: [{ id: `synthetic-source-read-${cycle}`, tool: 'scoped.read_original_records', scopeId: packet.corpus.scopeId,
          records: packet.corpus.records.filter((r: any) => r.cycle <= cycle).map((r: any) => ({ sourceId: r.id, sha256: sha256(r.content) })) }] } } : {}) };
    },
    async continue({ cycle, actionId }: any) { calls.push(`continue-${cycle}`); state += JSON.stringify({ type: 'response_item', payload: typed({ role: 'assistant', content: `SYNTHETIC_ACCEPTED_CONTINUATION_${cycle}` }) }) + '\n';
      const storeRunId = `synthetic-store-continuation-${cycle}`;
      const artifactReceiptUtf8 = JSON.stringify({ source: 'owned-store-registered-continuation-artifacts', sessionId: 'synthetic-session', runId: storeRunId,
        artifacts: Object.entries(outputs[cycle]).map(([name, value]) => ({ name, runId: storeRunId, artifactId: `synthetic-artifact-${name}`,
          messageId: 'synthetic-artifact-message', captureId: `synthetic-original-${name}`, sha256: sha256(JSON.stringify(value)), bytes: Buffer.byteLength(JSON.stringify(value), 'utf8') })) });
      return { ...common(actionId, `synthetic-continue-${cycle}`), sessionId: 'synthetic-session', runId: storeRunId,
        parentState: capture(), artifacts: clone(outputs[cycle]), artifactReceiptUtf8: options.missingOriginal ? undefined : artifactReceiptUtf8,
        artifactReceiptSha256: sha256(artifactReceiptUtf8) }; },
    async coldResume({ request, actionId, checkpoint }: any) { calls.push('baseline-cold'); const proof = isolation(checkpoint, request, 3, 'cold', actionId);
      return { ...common(actionId, proof.nativeTurnId, proof.nativeThreadId), isolation: proof, answer: answer(3), restartEvidence: {
        capturedBy: 'host', beforeProcessId: 'synthetic-baseline-app-1', afterProcessId: 'synthetic-baseline-app-2', nativeThreadId: parent,
        beforeStateSha256: checkpoint.stateSha256, afterStateUtf8: state, replayedActionIds: [], receiptSha256: hash } }; },
    async resumeAcceptedContinuation({ actionId, checkpoint, acceptedContinuation, windowId }: any) {
      calls.push('latest-continuation-cold'); assert.ok(checkpoint.stateUtf8.includes('SYNTHETIC_ACCEPTED_CONTINUATION_3'));
      assert.equal(acceptedContinuation.actionId, actionIdFor(runId, 3, 'continuation'));
      const restartReceiptUtf8 = JSON.stringify({ source: 'native-owned-host-cold-resume', runId, actionId, windowId, nativeThreadId: parent,
        checkpointStateSha256: checkpoint.stateSha256, beforeHostId: 'synthetic-owned-host-1', afterHostId: 'synthetic-owned-host-2',
        beforeApplicationProcessId: 'synthetic-app-1', afterApplicationProcessId: 'synthetic-app-2', oldApplicationExitConfirmed: true,
        oldGatewaySettled: true, noActionReplay: true, capturedAfterRestart: true, acceptedContinuationActionId: acceptedContinuation.actionId,
        acceptedArtifactHashes: acceptedContinuation.artifactHashes });
      const artifacts = clone(outputs[3]); if (options.staleArtifact) artifacts['sensor-policy.json'].watchdog = '2000 ms';
      const baseline = acceptedContinuation.artifactBaseline;
      const artifactReceiptUtf8 = JSON.stringify({ source: 'native-owned-workspace-artifacts', runId, sessionId: 'synthetic-session', nativeThreadId: parent, actionId, windowId,
        acceptedArtifactReceiptSha256: baseline?.artifactReceiptSha256, acceptedArtifactReceiptBytes: baseline?.artifactReceiptBytes,
        acceptedStoreRunId: baseline?.storeRunId, acceptedContinuationActionId: acceptedContinuation.actionId,
        checkpointStateSha256: checkpoint.stateSha256, captureId: 'synthetic-restarted-artifact-capture',
        afterHostId: 'synthetic-owned-host-2', artifactUtf8: Object.fromEntries(Object.entries(artifacts).map(([name, value]) => [name, JSON.stringify(value)])) });
      if (options.mutateBaseline) baseline.artifacts['sensor-policy.json'].sha256 = sha256('synthetic-adapter-substitution');
      return { ...common(actionId, 'synthetic-restart-operation'), artifacts, artifactReceiptUtf8: options.missingArtifacts ? undefined : artifactReceiptUtf8,
        artifactReceiptSha256: sha256(artifactReceiptUtf8), restartEvidence: { capturedBy: 'host', beforeProcessId: 'synthetic-app-1', afterProcessId: 'synthetic-app-2',
          nativeThreadId: parent, beforeStateSha256: checkpoint.stateSha256, afterStateUtf8: state, replayedActionIds: [], receiptSha256: hash,
          restartReceiptUtf8, restartReceiptSha256: sha256(restartReceiptUtf8) } };
    },
    async childContext({ brief, hostOnlyParentCanary, childNonce, actionId }: any) {
      calls.push('child'); state += JSON.stringify({ type: 'response_item', payload: typed({ role: 'user', content: hostOnlyParentCanary }) }) + '\n';
      const compiledMessages = [{ role: 'user', content: brief }], firstRequestUtf8 = JSON.stringify({ input: compiledMessages.map(typed), tools: [] });
      return { ...common(actionId, 'synthetic-child-turn', 'synthetic-child'), probe: { capturedBy: 'host', parentId: parent, childId: 'synthetic-child', firstRequestId: 'synthetic-first',
        nativeTurnId: 'synthetic-child-turn', actionId, compiledMessages, firstRequestUtf8, captureSha256: sha256(firstRequestUtf8),
        ...scope('synthetic-child', 'synthetic-child-turn', actionId), parentPlacement: capture(), tools: [], accessiblePaths: [], reply: { childNonce, parentCanary: 'UNKNOWN' } } };
    },
    async close() { calls.push('close'); } };
  return { adapter, calls };
}
async function simulate(options = {}) {
  const input = clone(packet); input.config.enabled = true; input.config.profile = 'h040-full-retention-v1'; input.config.maximumNativeActions = 39;
  const f = syntheticAdapter(options);
  const result = await runAcceptance({ packet: input, adapter: f.adapter, qualification: 'synthetic', runId,
    sink: { async private() {}, async record() {} } });
  return { ...f, result };
}
test('H040 full sequencing checks both cold boundaries and preserves latest accepted continuation before child', async () => {
  const { calls, result } = await simulate();
  assert.equal(result.status, 'PASS'); assert.equal(result.actionCount, 39); assert.equal(result.records.length, 12);
  assert.ok(calls.indexOf('baseline-cold') < calls.indexOf('continue-3'));
  assert.ok(calls.indexOf('continue-3') < calls.indexOf('latest-continuation-cold')); assert.ok(calls.indexOf('latest-continuation-cold') < calls.indexOf('child'));
  assert.equal(calls.at(-1), 'close'); assert.equal(result.nativeAcceptance, 'NOT_TESTED'); assert.equal(result.semanticAcceptance, 'NOT_TESTED');
  for (const d of Object.values(result.dimensions) as any[]) { assert.equal(d.actualStatus, 'PASS'); assert.equal(d.nativeStatus, 'NOT_TESTED'); }
});
test('stale resumed artifact fails and absent actual bytes remain NOT_TESTED before child, without retry', async () => {
  for (const [options, expected] of [[{ staleArtifact: true }, 'FAIL'], [{ missingArtifacts: true }, 'NOT_TESTED'], [{ missingOriginal: true }, 'NOT_TESTED']] as const) {
    const { calls, result } = await simulate(options);
    assert.equal(result.status, expected); assert.equal(calls.includes('child'), false);
    assert.equal(calls.filter(c => c === 'latest-continuation-cold').length, 1); assert.equal(calls.at(-1), 'close');
    assert.equal(result.records.at(-1).mode, 'cold-resume-after-continuation');
  }
});
test('adapter resume arguments cannot mutate the retained independent original artifact baseline', async () => {
  const reversed = clone(outputs[3]);
  reversed['sensor-policy.json'] = Object.fromEntries(Object.entries(reversed['sensor-policy.json']).reverse());
  assert.equal(scoreContinuation(packet.truth, 3, reversed).status, 'PASS');
  const { result } = await simulate({ mutateBaseline: true });
  assert.equal(result.status, 'PASS');
  assert.equal(result.nativeAcceptance, 'NOT_TESTED');
});
test('stage configuration has one manual cycle and does not silently downgrade the full profile', async () => {
  const stage = { ...packet.config, profile: 'h040-summary-stage-v1', cycles: [1], maximumNativeActions: 9 };
  const plan = actionPlan(stage); assert.equal(plan.facts, 56); assert.equal(plan.critical, 49); assert.equal(plan.fullNativeAcceptance, 'NOT_TESTED');
  const bad = clone(packet); bad.config.enabled = true; bad.config.cycles = [1];
  await assert.rejects(runAcceptance({ packet: bad, adapter: syntheticAdapter().adapter, qualification: 'synthetic', sink: {} }), /policy change/);
});
test('native review cannot exceed H040 authority or reinterpret an unreviewed profile', async () => {
  const input = clone(packet); input.config.enabled = true;
  input.config.review = { approvedBy: 'root', candidateCommit: 'a'.repeat(40), adapterSha256: hash, notAfterUtc: '2026-10-01T04:26:11Z' };
  let invoked = false;
  const adapter = { interfaceVersion: 'h039-compaction-adapter-v1', kind: 'native', async runtime() { invoked = true; } };
  await assert.rejects(runAcceptance({ packet: input, adapter, sink: {} }), /H040 execution window/);
  assert.equal(invoked, false);
});
test('native reserve defaults to 75 seconds and cannot be weakened by an unreviewed config', () => {
  assert.equal(settlementReserve({}, 'native'), 75000);
  assert.throws(() => settlementReserve({ review: { nativeSettlementReserveMs: 5000 } }, 'native'), /reserve/);
  assert.throws(() => settlementReserve({ nativeSettlementReserveMs: 1000 }, 'native'), /reserve/);
  assert.equal(settlementReserve({ nativeSettlementReserveMs: 90000, review: { nativeSettlementReserveMs: 90000 } }, 'native'), 90000);
  assert.equal(settlementReserve({ syntheticSettlementReserveMs: 5 }, 'synthetic'), 5);
});
test('frozen reserve/deadline blocks dispatch at 74 seconds remaining and reserves owned close', async () => {
  const input = clone(packet); input.config.enabled = true; input.config.syntheticSettlementReserveMs = 75000;
  const now = Date.now, initial = now(); let advanced = false, appended = false;
  input.config.review = { notAfterUtc: new Date(initial + 80000).toISOString() };
  const f = syntheticAdapter(), open = f.adapter.open;
  f.adapter.open = async () => { const result = await open(); advanced = true;
    // Mutating the caller's original config cannot change the frozen authority.
    input.config.syntheticSettlementReserveMs = 1; input.config.review.notAfterUtc = new Date(initial + 9999999).toISOString(); return result; };
  f.adapter.append = async () => { appended = true; };
  Date.now = () => initial + (advanced ? 6000 : 0);
  try {
    const result = await runAcceptance({ packet: input, adapter: f.adapter, qualification: 'synthetic', runId, sink: { async private() {}, async record() {} } });
    assert.equal(result.status, 'FAIL'); assert.equal(appended, false); assert.equal(result.settlementReserveMs, 75000); assert.equal(f.calls.at(-1), 'close');
  } finally { Date.now = now; }
});
test('owned timeout aborts the current method before shared close and never retries it', async () => {
  const input = clone(packet); input.config.enabled = true; input.config.deadlineMs = 5;
  const f = syntheticAdapter(); let aborted = false, appends = 0;
  f.adapter.append = ({ signal }: any) => { appends++; return new Promise((_resolve, reject) => signal.addEventListener('abort', () => { aborted = true; reject(Error('synthetic abort')); }, { once: true })); };
  f.adapter.close = async () => { assert.equal(aborted, true); f.calls.push('close'); };
  const keepAlive = setTimeout(() => {}, 100);
  try {
    const result = await runAcceptance({ packet: input, adapter: f.adapter, qualification: 'synthetic', runId, sink: { async private() {}, async record() {} } });
    assert.equal(result.status, 'FAIL'); assert.equal(appends, 1); assert.equal(f.calls.at(-1), 'close');
  } finally { clearTimeout(keepAlive); }
});
test('absent close receipt and absent independent bindings cannot prove native release', () => {
  assert.equal(verifyOwnedClose(undefined, { runId, operationWindowId: 'owned-window', observedSettlements: [] }).status, 'NOT_TESTED');
  assert.equal(verifyOwnedClose({ closeReceiptUtf8: '{}' }, { observedSettlements: [] }).status, 'NOT_TESTED');
});
