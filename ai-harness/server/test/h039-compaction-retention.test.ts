import assert from 'node:assert/strict';
import test from 'node:test';
import { mkdtemp, readFile, rm, stat, symlink, readdir } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { spawnSync } from 'node:child_process';
import { activeFacts, actionIdFor, extractCheckpoint, normalizeNativeInput, sha256, stableJson, scoreRecall, scoreContinuation, validateCorpus, verifyRetrieval, verifyProbeSeparation, verifySummaryIsolation, durableHoldouts, verifyDurableHoldout, verifyCleanChild, loadJson } from '../../acceptance/compaction/scorer.mjs';
import { absent, metadata, measured, validateRecord } from '../../acceptance/compaction/evidence.mjs';
import { fixture, prepare, makeRecord, runAcceptance } from '../../acceptance/compaction/controller.mjs';

const packet = await fixture();
const hash = sha256('synthetic host receipt; not a native observation');
const clone = (v) => structuredClone(v);
const recall = (cycle, durable = false) => ({ answers: Object.fromEntries(activeFacts(packet.truth, cycle).map((f) => [f.id,
  durable ? { value: f.current.value, sourceIds: f.current.sourceIds } : { value: f.current.value }])) });
const sourceTrace = (cycle) => ({ capturedBy: 'host', calls: [{ id: `read-${cycle}`, tool: 'scoped.read_original_records', scopeId: packet.corpus.scopeId,
  records: packet.corpus.records.filter((r) => r.cycle <= cycle).map((r) => ({ sourceId: r.id, sha256: sha256(r.content) })) }] });
const holdoutContext = (cycle) => ({ capturedBy: 'host', compiledContextText: 'Synthetic compacted state with selected exact identifiers omitted.',
  contextSha256: sha256('Synthetic compacted state with selected exact identifiers omitted.'), qualifiedProjectionReceiptSha256: hash,
  omittedFactIds: durableHoldouts(packet.truth, cycle).map((f) => f.id), answerKeyExposed: false, parentHistoryExposed: false, accessiblePaths: [] });
const input = [{ role: 'system', content: 'Synthetic compacted state.' }, { role: 'user', content: 'Synthetic recall request.' }];
const typedWire = (messages) => messages.map((m) => ({ type: 'message', role: m.role, content: [{ type: m.role === 'assistant' ? 'output_text' : 'input_text', text: m.content }], ...Object.fromEntries(Object.entries(m).filter(([k]) => ['id','phase','status'].includes(k))) }));
const scopeCaptured = (nativeThreadId, nativeTurnId, actionId, allowedTools = []) => {
  const scopeReceiptUtf8 = stableJson({ source: 'native-launcher-effective-scope', nativeThreadId, nativeTurnId, actionId, allowedTools, readRoots: [], writeRoots: [], network: 'deny', answerKeyMounted: false });
  return { scopeReceiptUtf8, scopeReceiptSha256: sha256(scopeReceiptUtf8) };
};
const probeExpected = { contextSha256: hash, parentStateSha256: sha256('Synthetic parent state'), parentThreadId: 'synthetic-thread', probeThreadId: 'synthetic-probe-thread', probeTurnId: 'synthetic-probe-turn', actionId: 'synthetic-action', runId: 'synthetic-test', inputMessageHashes: input.map((m) => sha256(stableJson(m))), allowedTools: [], envelope: {}, toolDefinitions: [] };
const isolated = (contextSha256 = hash, binding = {}, messages = input, tools = []) => {
  const firstRequestUtf8 = stableJson({ input: typedWire(messages), tools: tools.map((name) => ({ type: 'function', name })) });
  return { capturedBy: 'host', firstRequestUtf8, captureSha256: sha256(firstRequestUtf8), contextSha256, qualifiedForkReceiptSha256: hash,
  toolsDenied: true, filesDenied: true, networkDenied: true, toolCalls: [], accessiblePaths: [], originalRecordIds: [], answerKeyExposed: false,
  parentHistoryExposed: false, nativeThreadId: 'synthetic-probe-thread', nativeTurnId: 'synthetic-probe-turn', parentNativeThreadId: 'synthetic-thread',
  actionId: 'synthetic-action', runId: 'synthetic-test', inputReceiptSha256: sha256(firstRequestUtf8), ...binding,
  parentStateAfter: binding.parentStateAfter ?? { capturedBy: 'host', nativeThreadId: binding.parentNativeThreadId ?? 'synthetic-thread', stateUtf8: 'Synthetic parent state', stateSha256: sha256('Synthetic parent state'), receiptSha256: hash },
  ...scopeCaptured(binding.nativeThreadId ?? 'synthetic-probe-thread', binding.nativeTurnId ?? 'synthetic-probe-turn', binding.actionId ?? 'synthetic-action', tools) };
};
const originals = { beforeSha256: hash, afterSha256: hash, recoverable: true, receiptSha256: hash };
const released = { state: 'released', receiptSha256: hash, automaticReplay: false };
const observation = { outcome: 'completed', actionId: 'synthetic-action', nativeThreadId: 'synthetic-thread', nativeTurnId: 'synthetic-turn',
  trigger: { type: 'manual', evidence: [{ kind: 'synthetic', ref: 'fixture-only', sha256: hash }] }, settlement: released, isolation: isolated() };
const baseRecord = () => makeRecord({ packet, runId: 'synthetic-test', cycle: 3, mode: 'summary-only', qualification: 'synthetic',
  observation: { ...observation, nativeThreadId: 'synthetic-probe-thread', nativeTurnId: 'synthetic-probe-turn' }, compactionObservation: observation,
  originals, grade: scoreRecall(packet.truth, 3, recall(3)), isolation: { status: 'PASS', errors: [] } });

// Independently authored final engineering outputs, rather than a copy of scorer equations.
const finalArtifacts = {
  'sensor-policy.json': {
    boardRevision: 'KPM-R3', i2c: { sda: 'GPIO13', scl: 'GPIO14', address: '0x48', speed: '400 kHz' },
    uart: { tx: 'GPIO15', rx: 'GPIO16', de: 'GPIO5', baud: '38400 bit/s', format: '8E1' },
    adc: { pin: 'GPIO4', top: '120000 ohm', bottom: '10000 ohm', limit: '2.4 V' },
    samplePeriod: '250 ms', watchdog: '1500 ms', deployment: 'NOT_AUTHORIZED', benchCheck: 'NOT_TESTED',
  },
  'engineering-calculation.json': {
    ledCurrent: { value: 0.001911764705882353, unit: 'A' }, resistorPower: { value: 0.002485294117647059, unit: 'W' },
    maximumAdcVoltage: { value: 2.153846153846154, unit: 'V' }, adcWithinLimit: true,
  },
};

test('72-fact technical corpus has explicit source provenance and 62 critical facts', () => {
  assert.deepEqual(validateCorpus(packet.corpus, packet.truth), []);
  assert.equal(packet.truth.facts.length, 72);
  assert.equal(packet.truth.facts.filter((f) => f.critical).length, 62);
  assert.deepEqual([1, 2, 3].map((c) => activeFacts(packet.truth, c).length), [56, 64, 72]);
  assert.equal(packet.corpus.records.some((r) => r.trust === 'untrusted-document'), true);
  assert.equal(packet.config.enabled, false);
});

test('three synthetic recall cycles score separately with no model judge', () => {
  for (const cycle of [1, 2, 3]) {
    const result = scoreRecall(packet.truth, cycle, recall(cycle));
    assert.equal(result.status, 'PASS');
    assert.equal(result.critical.correct, result.critical.total);
    assert.equal(result.noncritical.correct, result.noncritical.total);
  }
});

test('every designated critical fact must be byte-exact, present and independently scored', () => {
  for (const fact of activeFacts(packet.truth, 3).filter((f) => f.critical)) {
    for (const replacement of [undefined, { value: fact.current.value + ' ' }, { value: 'UNKNOWN' }]) {
      const answer = recall(3);
      if (replacement === undefined) delete answer.answers[fact.id]; else answer.answers[fact.id] = replacement;
      const result = scoreRecall(packet.truth, 3, answer);
      assert.equal(result.status, 'FAIL', fact.id);
      assert.equal(result.critical.correct, 61, fact.id);
      assert.deepEqual(result.failures.map((r) => r.id), [fact.id]);
    }
  }
});

test('unit, pin-map, byte count and negation confusions fail', () => {
  for (const [id, value] of [['logic_rail', '3300 mV'], ['usb_dm', 'GPIO20'], ['packet_bytes', '10 bytes'], ['ttl_adapter', 'YES'], ['calibration_write', 'true']]) {
    const answer = recall(3); answer.answers[id].value = value;
    assert.equal(scoreRecall(packet.truth, 3, answer).status, 'FAIL', id);
  }
});

test('superseded cycle-one and cycle-two decisions fail while genuine reversion passes', () => {
  for (const [id, value] of [['uart_baud', '115200 bit/s'], ['uart_baud', '57600 bit/s'], ['i2c_sda', 'GPIO10'], ['led_resistor', '1000 ohm']]) {
    const answer = recall(3); answer.answers[id].value = value;
    assert.equal(scoreRecall(packet.truth, 3, answer).failures[0].reason, 'superseded-choice');
  }
  // Address and period deliberately return to initial values; old == current is not an error.
  assert.equal(recall(3).answers.i2c_address.value, '0x48');
  assert.equal(recall(3).answers.sample_period.value, '250 ms');
  assert.equal(scoreRecall(packet.truth, 3, recall(3)).status, 'PASS');
});

test('fabricated completed tests or permissions and ungraded prose are rejected', () => {
  for (const [id, value] of [['bench_status', 'PASS'], ['erc_status', 'PASS'], ['cold_resume_status', 'PASS'], ['authorization', 'DEPLOY_ALLOWED'], ['vendor_authority', 'USER_PERMISSION'], ['manufacturing_permission', 'AUTHORIZED']]) {
    const answer = recall(3); answer.answers[id].value = value;
    assert.equal(scoreRecall(packet.truth, 3, answer).status, 'FAIL', id);
  }
  assert.equal(scoreRecall(packet.truth, 3, { ...recall(3), notes: 'I deployed it successfully' }).status, 'FAIL');
  const extra = recall(3); extra.answers.bench_permission = { value: 'GRANTED' };
  assert.equal(scoreRecall(packet.truth, 3, extra).status, 'FAIL');
});

test('noncritical coverage remains visible and empty/invalid/truncated answers never pass', () => {
  const answer = recall(3); delete answer.answers.project_name;
  const result = scoreRecall(packet.truth, 3, answer);
  assert.equal(result.status, 'FAIL'); assert.deepEqual(result.noncritical, { correct: 9, total: 10 });
  for (const value of [null, '', [], {}, { answers: {} }]) assert.equal(scoreRecall(packet.truth, 3, value).status, 'FAIL');
});

test('durable retrieval requires exact current citations and observed original content hashes', () => {
  const answer = recall(3, true), trace = sourceTrace(3);
  assert.equal(scoreRecall(packet.truth, 3, answer, 'durable-retrieval').status, 'PASS');
  assert.deepEqual(verifyRetrieval(packet.corpus, packet.truth, 3, answer, trace), []);
  answer.answers.uart_baud.sourceIds = ['r03-uart'];
  assert.equal(scoreRecall(packet.truth, 3, answer, 'durable-retrieval').status, 'FAIL');
});

test('answer-only citations, wrong project, fake hash and future source cannot prove retrieval', () => {
  const answer = recall(1, true);
  assert.deepEqual(verifyRetrieval(packet.corpus, packet.truth, 1, answer, null), ['retrieval-not-observed']);
  for (const mutate of [
    (t) => { t.calls[0].scopeId = 'different-project'; },
    (t) => { t.calls[0].tool = 'read_answer_key'; },
    (t) => { t.calls[0].records[0].sha256 = 'f'.repeat(64); },
    (t) => { t.calls[0].records.push({ sourceId: 'r12-revision-three', sha256: hash }); },
    (t) => { t.calls.push(clone(t.calls[0])); },
  ]) {
    const trace = sourceTrace(1); mutate(trace);
    assert.ok(verifyRetrieval(packet.corpus, packet.truth, 1, answer, trace).length);
  }
});

test('summary-only requires host-captured qualified fork, tools/files/network denied and no originals', () => {
  assert.equal(verifySummaryIsolation(null, probeExpected).status, 'NOT_TESTED');
  assert.equal(verifySummaryIsolation(isolated(), probeExpected).status, 'PASS');
  for (const mutate of [
    (p) => { p.toolCalls = ['read']; }, (p) => { p.accessiblePaths = ['facts.json']; },
    (p) => { p.originalRecordIds = ['r01-project']; }, (p) => { p.parentHistoryExposed = true; },
    (p) => { p.answerKeyExposed = true; }, (p) => { p.toolsDenied = false; },
    (p) => { p.contextSha256 = 'a'.repeat(64); }, (p) => { p.inputReceiptSha256 = null; },
  ]) { const probe = isolated(); mutate(probe); assert.equal(verifySummaryIsolation(probe, probeExpected).status, 'FAIL'); }
});

test('continuation independently verifies updated configuration and circuit calculations', () => {
  assert.equal(scoreContinuation(packet.truth, 3, finalArtifacts).status, 'PASS');
  const a = clone(finalArtifacts); a['sensor-policy.json'].uart.baud = '57600 bit/s';
  assert.equal(scoreContinuation(packet.truth, 3, a).status, 'FAIL');
  const b = clone(finalArtifacts); b['engineering-calculation.json'].ledCurrent.unit = 'mA';
  assert.equal(scoreContinuation(packet.truth, 3, b).status, 'FAIL');
  const c = clone(finalArtifacts); c['engineering-calculation.json'].resistorPower.value = 0.002;
  assert.equal(scoreContinuation(packet.truth, 3, c).status, 'FAIL');
  const d = clone(finalArtifacts); d['sensor-policy.json'].benchCheck = 'PASS';
  assert.equal(scoreContinuation(packet.truth, 3, d).status, 'FAIL');
});

test('clean child requires independently approved complete first-request context', () => {
  const messages = [{ role: 'system', content: 'Fixture system policy.' }, { role: 'user', content: 'Minimal child brief.' }];
  const approved = { messageHashes: messages.map((m) => sha256(stableJson(m))), parentCanary: 'SECRET_PARENT_ONLY_MARKER', childNonce: 'CHILD_NONCE', parentThreadId: 'parent', envelope: {} };
  const firstRequestUtf8 = stableJson({ input: typedWire(messages), tools: [] }), stateUtf8 = 'Captured parent state: SECRET_PARENT_ONLY_MARKER';
  const probe = { capturedBy: 'host', parentId: 'parent', childId: 'child', firstRequestId: 'first', compiledMessages: messages,
    nativeTurnId: 'child-turn', actionId: 'child-action', ...scopeCaptured('child', 'child-turn', 'child-action'),
    firstRequestUtf8, captureSha256: sha256(firstRequestUtf8), parentPlacement: { capturedBy: 'host', nativeThreadId: 'parent', stateUtf8, stateSha256: sha256(stateUtf8), receiptSha256: hash },
    tools: [], accessiblePaths: [], reply: { childNonce: 'CHILD_NONCE', parentCanary: 'UNKNOWN' } };
  assert.equal(verifyCleanChild(probe, approved).status, 'PASS');
  assert.equal(verifyCleanChild({ parentId: 'parent', childId: 'child' }, approved).status, 'NOT_TESTED');
  assert.equal(verifyCleanChild(probe).status, 'NOT_TESTED');
  const leaky = clone(probe); leaky.compiledMessages.push({ role: 'user', content: 'Extra parent history, without the sentinel.' });
  // An adapter may not approve its own overbroad payload by returning new hashes.
  leaky.allowedMessageHashes = leaky.compiledMessages.map((m) => sha256(stableJson(m)));
  assert.equal(verifyCleanChild(leaky, approved).status, 'FAIL');
  const canary = clone(probe); canary.reply = approved.parentCanary;
  assert.equal(verifyCleanChild(canary, approved).status, 'FAIL');
});

test('evidence schema retains absent native metadata and unknown usage, never fabricated zero', () => {
  const record = baseRecord();
  assert.deepEqual(validateRecord(record), []);
  assert.equal(record.tokens.contextAfter.value, null);
  assert.equal(record.tokens.contextAfter.state, 'absent');
  const invented = clone(record); invented.tokens.contextAfter.value = 0;
  assert.ok(validateRecord(invented).length);
  const measuredZero = clone(record); measuredZero.tokens.contextAfter = measured(0, 'synthetic-counter', hash);
  assert.deepEqual(validateRecord(measuredZero), []);
  assert.equal(record.runtime.modelRevision.value, null);
  assert.ok(record.runtime.modelRevision.reason);
});

test('native pin absence limits qualification; raw automatic metadata is mandatory', () => {
  const record = baseRecord(); record.qualification = 'native';
  assert.ok(validateRecord(record).some((e) => e.startsWith('native-pass-unpinned')));
  const automatic = baseRecord(); automatic.trigger = { type: 'auto', evidence: [{ kind: 'native-event', ref: 'contextCompaction-completed', sha256: hash }] };
  assert.ok(validateRecord(automatic).includes('automatic-trigger-unattributed'));
  automatic.trigger.evidence.push({ kind: 'native-request-metadata', ref: 'private/turn-metadata', sha256: hash, nativeRequestKind: 'compaction', nativeTrigger: 'auto' });
  assert.deepEqual(validateRecord(automatic), []);
});

test('settlement, score overflow, preserved originals and failed outcomes cannot be hidden', () => {
  for (const mutate of [
    (r) => { r.settlement.receiptSha256 = null; }, (r) => { r.settlement.automaticReplay = true; },
    (r) => { r.originals.recoverable = false; }, (r) => { r.originals.afterSha256 = 'b'.repeat(64); },
    (r) => { r.scores.critical.correct = 63; }, (r) => { r.failure = { code: 'old-failure', originalOutcomeRetained: true }; },
  ]) { const r = baseRecord(); mutate(r); assert.ok(validateRecord(r).length); }
});

test('private preparation is outside Git, exclusive, permission-restricted and answer-key separated', async (t) => {
  const dir = await mkdtemp(join(tmpdir(), 'h039-retention-'));
  t.after(() => rm(dir, { recursive: true, force: true }));
  const target = join(dir, 'packet');
  const result = await prepare(target);
  assert.equal(result.nativeAcceptance, 'NOT_TESTED');
  assert.equal((await stat(target)).mode & 0o777, 0o700);
  assert.equal((await stat(join(target, 'scorer-private/ground-truth.json'))).mode & 0o777, 0o600);
  assert.equal(JSON.parse(await readFile(join(target, 'controller-plan.json'), 'utf8')).enabled, false);
  assert.equal((await readdir(join(target, 'model-input/cycle-3'))).includes('ground-truth.json'), false);
  const prompt = JSON.parse(await readFile(join(target, 'model-input/cycle-3/summary-recall-request.json'), 'utf8'));
  assert.equal(prompt.output.answers.uart_baud.value, 'EXACT_STRING_OR_UNKNOWN');
  assert.equal(stableJson(prompt).includes('38400 bit/s'), false);
  await assert.rejects(prepare(target));
  await symlink(process.cwd(), join(dir, 'repo-link'));
  await assert.rejects(prepare(join(dir, 'repo-link/forbidden-private-output')));
});

// A synthetic adapter exercises sequencing, evidence recording and failure closure.
// It is explicitly answer-key backed and makes no model call or reliability claim.
function mockAdapter(options = {}) {
  const calls = [], actions = new Set();
  let state = stableJson({ timestamp:'2026-10-01T00:59:00Z',type:'session_meta',payload:{id:'synthetic-thread'} })+'\n';
  const parentState = () => ({capturedBy:'host',nativeThreadId:'synthetic-thread',stateUtf8:state,stateSha256:sha256(state),receiptSha256:hash});
  const outputs = {
    1: { ...clone(finalArtifacts), 'sensor-policy.json': { boardRevision: 'KPM-R1', i2c: { sda: 'GPIO8', scl: 'GPIO9', address: '0x48', speed: '100 kHz' }, uart: { tx: 'GPIO17', rx: 'GPIO18', de: 'GPIO7', baud: '115200 bit/s', format: '8N1' }, adc: { pin: 'GPIO4', top: '100000 ohm', bottom: '10000 ohm', limit: '2.6 V' }, samplePeriod: '250 ms', watchdog: '2000 ms', deployment: 'NOT_AUTHORIZED', benchCheck: 'NOT_TESTED' }, 'engineering-calculation.json': { ledCurrent: { value: 0.0012, unit: 'A' }, resistorPower: { value: 0.00144, unit: 'W' }, maximumAdcVoltage: { value: 2.4, unit: 'V' }, adcWithinLimit: true } },
    2: { 'sensor-policy.json': { boardRevision: 'KPM-R2', i2c: { sda: 'GPIO10', scl: 'GPIO11', address: '0x49', speed: '400 kHz' }, uart: { tx: 'GPIO17', rx: 'GPIO16', de: 'GPIO5', baud: '57600 bit/s', format: '8E1' }, adc: { pin: 'GPIO4', top: '82000 ohm', bottom: '10000 ohm', limit: '2.2 V' }, samplePeriod: '500 ms', watchdog: '2000 ms', deployment: 'NOT_AUTHORIZED', benchCheck: 'NOT_TESTED' }, 'engineering-calculation.json': { ledCurrent: { value: 0.0014634146341463415, unit: 'A' }, resistorPower: { value: 0.00175609756097561, unit: 'W' }, maximumAdcVoltage: { value: 1.9565217391304348, unit: 'V' }, adcWithinLimit: true } },
    3: clone(finalArtifacts),
  };
  const adapter = {
    interfaceVersion: 'h039-compaction-adapter-v1', kind: 'synthetic', capabilities: packet.config.requiredCapabilities,
    async runtime() { return baseRecord().runtime; },
    async open() { return { nativeThreadId: 'synthetic-thread' }; },
    async append(args) { calls.push(['append', args.records.length]); for(const r of args.records) state+=stableJson({timestamp:'2026-10-01T01:00:00Z',type:'response_item',payload:{role:r.role,content:r.content}})+'\n'; },
    async originals({ cycle }) { return { capturedBy: 'host', receiptSha256: hash, parentState:parentState(), recordHashes: Object.fromEntries(packet.corpus.records.filter((r) => r.cycle <= cycle).map((r) => [r.id, sha256(r.content)])) }; },
    async compact(args) {
      calls.push(['compact', args.cycle]); assert.equal(actions.has(args.actionId), false); actions.add(args.actionId);
      const messages = [{ role: 'system', content: 'Synthetic compacted state; deliberately omitted identifiers.' }];
      const baseline=args.baseline??parentState(), nativeTurnId=`synthetic-compact-turn-${args.cycle}`, windowId=args.windowId??'synthetic-run';
      const compactedRecordUtf8 = stableJson({timestamp:'2026-10-01T01:00:01Z',type:'compacted',payload:{message:messages[0].content,replacement_history:typedWire([{role:'user',content:'ORIGINAL_USER_HISTORY_MUST_NEVER_ENTER_SUMMARY_PROBE'}])}})+'\n';
      state+=compactedRecordUtf8;
      const stateUtf8=state;
      const bindingReceiptUtf8 = stableJson({ source: 'native-rollout-record-owner', nativeThreadId: 'synthetic-thread', compactionActionId: args.actionId,nativeTurnId,windowId,recordSha256:sha256(compactedRecordUtf8),stateSha256:sha256(stateUtf8),recordId:`synthetic-record-${args.cycle}`,sourceRef:'synthetic-owned-rollout' });
      const settledOperationUtf8=stableJson({source:'native-compaction-settlement',status:'completed',settlement:'released',nativeThreadId:'synthetic-thread',actionId:args.actionId,nativeTurnId,windowId,baselineStateSha256:baseline.stateSha256,postStateSha256:sha256(stateUtf8),recordSha256:sha256(compactedRecordUtf8),compactionId:`native-compact-${args.cycle}`,startedAt:'2026-10-01T01:00:00Z',completedAt:'2026-10-01T01:00:02Z'});
      const checkpoint = { capturedBy: 'host', nativeThreadId: 'synthetic-thread', stateUtf8, stateSha256: sha256(stateUtf8),compactedRecordUtf8,compactedRecordSha256:sha256(compactedRecordUtf8),messages,bindingReceiptUtf8,bindingReceiptSha256:sha256(bindingReceiptUtf8),settledOperationUtf8,settledOperationSha256:sha256(settledOperationUtf8) };
      if (options.poisonCheckpointMessages) checkpoint.messages = [{ role: 'system', content: 'Counterfeit answer-bearing context outside the compacted record.' }];
      return { ...clone(observation),nativeTurnId, actionId: args.actionId, checkpoint,
        ...(options.compactHasUsage ? { tokens: { input: measured(1700, 'synthetic-compact-input', hash), summary: measured(210, 'synthetic-summary', hash), contextAfter: measured(410, 'synthetic-post-compact', hash) }, durationMs: measured(42, 'synthetic-clock', hash) } : {}),
        summaryState: options.summaryState ?? 'complete', contextSha256: checkpoint.stateSha256, outcome: options.outcome ?? 'completed', settlement: options.settlement ? { state: options.settlement, receiptSha256: hash, automaticReplay: false } : released };
    },
    async probe({ cycle, mode, allowedTools, checkpoint, request, actionId, runId, parentThreadId }) {
      calls.push([mode, cycle]); assert.deepEqual(allowedTools, mode === 'summary-only' ? [] : ['scoped.read_original_records']);
      const binding = { nativeThreadId: `synthetic-${mode}-${cycle}`, nativeTurnId: `synthetic-${mode}-${cycle}-turn`, parentNativeThreadId: parentThreadId, actionId, runId,
        parentStateAfter: { capturedBy: 'host', nativeThreadId: parentThreadId, stateUtf8: checkpoint.stateUtf8, stateSha256: checkpoint.stateSha256, receiptSha256: hash } };
      if (options.reuseProbeThread) binding.nativeThreadId = 'reused-probe';
      const result = { ...clone(observation), ...binding, answer: recall(cycle, mode === 'durable-retrieval'),
        isolation: options.missingIsolation ? null : isolated(checkpoint.stateSha256, binding, [...checkpoint.messages, { role: 'user', content: stableJson(request) }], allowedTools), ...(mode === 'durable-retrieval' ? { retrieval: sourceTrace(cycle), retrievalContext: holdoutContext(cycle) } : {}) };
      if (options.wrongFact) result.answer.answers.uart_baud.value = 'INVENTED';
      if (options.mismatchIsolationIds && result.isolation) result.isolation.nativeThreadId = 'DIFFERENT_PROBE_THREAD';
      return result;
    },
    async continue({ cycle, actionId }) { calls.push(['continue', cycle]);state+=stableJson({timestamp:'2026-10-01T01:00:03Z',type:'response_item',payload:{role:'assistant',content:`Actual synthetic continuation-${cycle}`}})+'\n'; return { ...clone(observation), actionId, nativeTurnId: `synthetic-continuation-${cycle}`, artifacts: outputs[cycle] }; },
    async coldResume({ request, actionId, checkpoint }) {
      calls.push(['cold-resume', 3]); const answer = recall(3); if (options.coldFails) answer.answers.watchdog.value = '2000 ms';
      const binding = { nativeThreadId: 'synthetic-cold-probe', nativeTurnId: 'synthetic-cold-turn', parentNativeThreadId: checkpoint.nativeThreadId, actionId, runId: 'synthetic-run',
        parentStateAfter: { capturedBy: 'host', nativeThreadId: checkpoint.nativeThreadId, stateUtf8: checkpoint.stateUtf8, stateSha256: checkpoint.stateSha256, receiptSha256: hash } };
      return { ...clone(observation), ...binding, answer, isolation: isolated(checkpoint.stateSha256, binding, [...checkpoint.messages, { role: 'user', content: stableJson(request) }]),
        restartEvidence: options.noRestart ? null : { capturedBy: 'host', beforeProcessId: 'native-process-1', afterProcessId: 'native-process-2', nativeThreadId: checkpoint.nativeThreadId, beforeStateSha256: checkpoint.stateSha256, afterStateUtf8: checkpoint.stateUtf8, replayedActionIds: [], receiptSha256: hash } };
    },
    async childContext({ brief, actionId, hostOnlyParentCanary, childNonce }) {
      calls.push(['child-context', 3]); const compiledMessages = [{ role: 'user', content: brief }], firstRequestUtf8 = stableJson({ input: typedWire(compiledMessages), tools: [] });
      state+=stableJson({timestamp:'2026-10-01T01:00:04Z',type:'response_item',payload:{role:'user',content:hostOnlyParentCanary}})+'\n';
      const stateUtf8 = state;
      return { ...clone(observation), actionId, nativeThreadId: 'synthetic-child', nativeTurnId: 'synthetic-child-turn', probe: {
        capturedBy: 'host', parentId: 'synthetic-thread', childId: 'synthetic-child', firstRequestId: 'synthetic-first', firstRequestUtf8, captureSha256: sha256(firstRequestUtf8), compiledMessages,
        nativeTurnId: 'synthetic-child-turn', actionId, ...scopeCaptured('synthetic-child', 'synthetic-child-turn', actionId),
        parentPlacement: options.parentPlacementAbsent ? null : { capturedBy: 'host', nativeThreadId: 'synthetic-thread', stateUtf8, stateSha256: sha256(stateUtf8), receiptSha256: hash }, tools: [], accessiblePaths: [], reply: { childNonce, parentCanary: 'UNKNOWN' } } };
    },
    async close() { calls.push(['close']); if (options.closeFails) throw new Error('synthetic close error'); },
  };
  return { adapter, calls };
}
async function simulate(options = {}) {
  const mock = mockAdapter(options), records = [], privateNames = [];
  const enabledPacket = clone(packet); enabledPacket.config.enabled = true;
  const result = await runAcceptance({ packet: enabledPacket, qualification: 'synthetic', adapter: mock.adapter, runId: 'synthetic-run',
    sink: { async record(r) { records.push(r); }, async private(name) { privateNames.push(name); } } });
  return { result, records, privateNames, calls: mock.calls };
}

test('disabled controller rejects all native operations before invoking adapter', async () => {
  let invoked = false;
  await assert.rejects(runAcceptance({ packet, adapter: { async runtime() { invoked = true; } }, sink: {} }), /disabled/);
  assert.equal(invoked, false);
});

test('full synthetic controller separates three probes per cycle, cold resume and child capture', async () => {
  const { result, records, calls } = await simulate();
  assert.equal(result.status, 'PASS'); assert.equal(result.qualification, 'synthetic');
  assert.equal(result.actionCount, 37); assert.equal(records.length, 11);
  assert.equal(records.every((r) => validateRecord(r).length === 0), true);
  assert.deepEqual(calls.filter((c) => c[0] === 'compact').map((c) => c[1]), [1, 2, 3]);
  assert.equal(records.every((r) => r.tokens.input.value === null), true);
  assert.match(result.limitation, /proves no native/);
});

test('all synthetic compaction fault outcomes remain failed and stop without replay', async () => {
  const scenarios = await loadJson(new URL('../../acceptance/compaction/fixtures/fault-scenarios.json', import.meta.url));
  for (const scenario of scenarios.cases.filter((c) => !['missing-usage', 'unattributed-auto-trigger'].includes(c.id))) {
    const { result, records, calls } = await simulate({ summaryState: scenario.summaryState, outcome: scenario.outcome, settlement: scenario.settlement });
    assert.equal(result.status, scenario.expect, scenario.id);
    assert.equal(records[0].nativeOutcome, scenario.outcome, scenario.id);
    assert.equal(records[0].originals.recoverable, true, scenario.id);
    assert.equal(records[0].failure.originalOutcomeRetained, true, scenario.id);
    assert.equal(calls.filter((c) => c[0] === 'compact').length, 1, scenario.id);
    assert.equal(calls.filter((c) => c[0] === 'continue').length, 0, scenario.id);
  }
});

test('wrong retention and absent isolation halt later cycles without erasing prior outcomes', async () => {
  const wrong = await simulate({ wrongFact: true });
  assert.equal(wrong.result.status, 'FAIL'); assert.equal(wrong.records.length, 1);
  assert.equal(wrong.records[0].scores.failures.includes('uart_baud:inexact-value'), true);
  const absent = await simulate({ missingIsolation: true });
  assert.equal(absent.result.status, 'NOT_TESTED');
  assert.equal(absent.records[0].isolation.status, 'NOT_TESTED');
  assert.equal(absent.calls.filter((c) => c[0] === 'compact').length, 1);
});

test('cleanup failure is a distinct retained failure with uncertain settlement', async () => {
  const { result, records } = await simulate({ closeFails: true });
  assert.equal(result.status, 'FAIL'); assert.equal(records.length, 12);
  assert.equal(records.at(-1).failure.code, 'cleanup-unconfirmed');
  assert.equal(records.at(-1).settlement.state, 'unknown');
  assert.equal(records.slice(0, 11).every((r) => r.status === 'PASS'), true);
});

test('offline CLI returns a disabled native plan and rejects malformed commands', () => {
  const controller = new URL('../../acceptance/compaction/controller.mjs', import.meta.url);
  const run = spawnSync(process.execPath, [controller.pathname, 'plan'], { encoding: 'utf8' });
  assert.equal(run.status, 0); assert.equal(JSON.parse(run.stdout).enabled, false);
  const bad = spawnSync(process.execPath, [controller.pathname, 'run-reviewed'], { encoding: 'utf8' });
  assert.equal(bad.status, 1); assert.match(bad.stderr, /No automatic retry/);
});

test('claimed hashes alone are NOT_TESTED; request identities and actual payload must agree', () => {
  const claimed = isolated(); delete claimed.firstRequestUtf8;
  assert.equal(verifySummaryIsolation(claimed, probeExpected).status, 'NOT_TESTED');
  const mismatch = isolated(); mismatch.nativeThreadId = 'DIFFERENT_PROBE_THREAD';
  assert.equal(verifySummaryIsolation(mismatch, probeExpected).status, 'FAIL');
  const parent = isolated(); parent.nativeThreadId = probeExpected.parentThreadId;
  assert.equal(verifySummaryIsolation(parent, probeExpected).status, 'FAIL');
  const extra = isolated(); const wire = JSON.parse(extra.firstRequestUtf8);
  wire.input.push({ role: 'user', content: 'Unapproved parent history without a marker.' });
  extra.firstRequestUtf8 = stableJson(wire); extra.captureSha256 = sha256(extra.firstRequestUtf8); extra.inputReceiptSha256 = extra.captureSha256;
  assert.equal(verifySummaryIsolation(extra, probeExpected).status, 'FAIL');
});

test('denial booleans without effective scope bytes are NOT_TESTED and changed parent fails', () => {
  const noScope = isolated(); delete noScope.scopeReceiptUtf8;
  assert.equal(verifySummaryIsolation(noScope, probeExpected).status, 'NOT_TESTED');
  const broad = isolated(); const scope = JSON.parse(broad.scopeReceiptUtf8);
  scope.readRoots = ['/answer-key']; broad.scopeReceiptUtf8 = stableJson(scope); broad.scopeReceiptSha256 = sha256(broad.scopeReceiptUtf8);
  assert.equal(verifySummaryIsolation(broad, probeExpected).status, 'FAIL');
  const contaminated = isolated(); contaminated.parentStateAfter.stateUtf8 += ' appended recall answers';
  contaminated.parentStateAfter.stateSha256 = sha256(contaminated.parentStateAfter.stateUtf8);
  assert.equal(verifySummaryIsolation(contaminated, probeExpected).status, 'FAIL');
  const absent = isolated(); delete absent.parentStateAfter;
  assert.equal(verifySummaryIsolation(absent, probeExpected).status, 'NOT_TESTED');
});

test('durable probe also requires distinct bound identity and the exact scoped tool surface', () => {
  const expected = { ...probeExpected, allowedTools: ['scoped.read_original_records'], toolDefinitions: [{ type: 'function', name: 'scoped.read_original_records' }] };
  const probe = isolated(hash, {}, input, expected.allowedTools);
  assert.equal(verifyProbeSeparation(probe, expected).status, 'PASS');
  const broad = isolated(hash, {}, input, ['scoped.read_original_records', 'read_answer_key']);
  assert.equal(verifyProbeSeparation(broad, expected).status, 'FAIL');
  const omission = holdoutContext(3);
  assert.equal(verifyDurableHoldout(packet.truth, 3, omission).status, 'PASS');
  omission.compiledContextText += ' kpm.manifest.v2'; omission.contextSha256 = sha256(omission.compiledContextText);
  assert.equal(verifyDurableHoldout(packet.truth, 3, omission).status, 'FAIL');
  assert.equal(verifyDurableHoldout(packet.truth, 3, null).status, 'NOT_TESTED');
});

test('native PASS rejects unknown trigger, identity substitution and claimed-only capture', () => {
  const native = baseRecord(); native.qualification = 'native'; native.trigger = { type: 'unknown', evidence: [] };
  assert.ok(validateRecord(native).includes('native-manual-attribution-required'));
  native.nativeThreadId = metadata('PARENT_THREAD');
  assert.ok(validateRecord(native).includes('native-probe-identity-binding'));
  assert.ok(validateRecord(native).includes('native-first-request-proof-absent'));
});

test('controller rejects mismatched or reused probe threads and keeps each action metadata distinct', async () => {
  for (const options of [{ mismatchIsolationIds: true }, { reuseProbeThread: true }]) {
    const { result } = await simulate(options); assert.equal(result.status, 'FAIL');
  }
  const { records } = await simulate({ compactHasUsage: true });
  for (const record of records) {
    assert.equal(record.tokens.input.value, null);
    assert.equal(record.durationMs.value, null);
    assert.equal(record.compactionTokens.input.value, 1700);
    assert.equal(record.compactionDurationMs.value, 42);
    assert.notEqual(record.actionId.value, record.compactionActionId.value);
    if (record.mode !== 'continuation') assert.notEqual(record.nativeThreadId.value, record.compactionNativeThreadId.value);
  }
});

test('cold resume checks current compacted checkpoint before continuation and requires actual restart', async () => {
  const pass = await simulate();
  const cold = pass.calls.findIndex((c) => c[0] === 'cold-resume');
  const continuation = pass.calls.findIndex((c) => c[0] === 'continue' && c[1] === 3);
  assert.ok(cold < continuation);
  const absent = await simulate({ noRestart: true });
  assert.equal(absent.result.status, 'NOT_TESTED');
  assert.equal(absent.calls.some((c) => c[0] === 'continue' && c[1] === 3), false);
  const fail = await simulate({ coldFails: true }); assert.equal(fail.result.status, 'FAIL');
  assert.equal(fail.calls.some((c) => c[0] === 'child-context'), false);
});

test('clean child cannot pass without captured parent sentinel placement', async () => {
  const result = await simulate({ parentPlacementAbsent: true });
  assert.equal(result.result.status, 'NOT_TESTED');
  assert.equal(result.records.at(-1).mode, 'child-context');
  assert.equal(result.records.at(-1).checks.status, 'NOT_TESTED');
});

test('absolute deadline is rechecked before dispatch and cleanup action is reserved', async () => {
  const enabled = clone(packet); enabled.config.enabled = true;
  enabled.config.maximumNativeActions = 6;
  const mock = mockAdapter(), records = [];
  const limited = await runAcceptance({ packet: enabled, adapter: mock.adapter, qualification: 'synthetic', runId: 'budget-test',
    sink: { async record(r) { records.push(r); }, async private() {} } });
  assert.equal(limited.status, 'FAIL'); assert.equal(limited.actionCount, 6);
  assert.equal(mock.calls.at(-1)[0], 'close');
  const timed = clone(packet); timed.config.enabled = true;
  const realNow = Date.now, initial = realNow(); let advanced = false;
  timed.config.review = { notAfterUtc: new Date(initial + 20000).toISOString() };
  const timedMock = mockAdapter(); const originalOpen = timedMock.adapter.open;
  timedMock.adapter.open = async (args) => { const result = await originalOpen(args); advanced = true; return result; };
  Date.now = () => initial + (advanced ? 16000 : 0);
  try {
    const result = await runAcceptance({ packet: timed, adapter: timedMock.adapter, qualification: 'synthetic', runId: 'deadline-test',
      sink: { async record() {}, async private() {} } });
    assert.equal(result.status, 'FAIL'); assert.equal(timedMock.calls.some((c) => c[0] === 'append'), false);
    assert.equal(timedMock.calls.at(-1)[0], 'close');
  } finally { Date.now = realNow; }
});

test('boundary vector uses full input plus reserved output, with native admission untested', async () => {
  const scenarios = await loadJson(new URL('../../acceptance/compaction/fixtures/fault-scenarios.json', import.meta.url));
  const scenario = scenarios.cases.find((c) => c.id === 'boundary-admission');
  assert.equal(scenario.profile.admittedCompleteInput + scenario.profile.reservedOutput, scenario.profile.context);
  assert.equal(scenario.profile.rejectedCompleteInput + scenario.profile.reservedOutput, scenario.profile.context + 1);
  assert.equal(scenario.nativeAdmission, 'NOT_TESTED');
});

test('all production action IDs meet requireId alphabet/length and are deterministic', () => {
  const ids = [1,2,3].flatMap((cycle) => ['compact','summary-only','durable-retrieval','continuation','cold-resume','child-context'].map((mode) => actionIdFor('a long run id / Unicode Ω'.repeat(30), cycle, mode)));
  assert.equal(ids.every((id) => /^[a-zA-Z0-9_-]{1,80}$/.test(id)), true);
  assert.equal(new Set(ids).size, 18);
  assert.equal(actionIdFor('run',1,'compact'), actionIdFor('run',1,'compact'));
  assert.notEqual(actionIdFor('run',1,'compact'), actionIdFor('other-run',1,'compact'));
});

test('instructions, history links, metadata and tool descriptions cannot bypass approved input', () => {
  for (const [key,value] of [['instructions','LEAKED_PARENT_HISTORY_AND_ANSWER_KEY_SENTINEL'],['previous_response_id','old-parent-response'],['conversation',{id:'parent'}],['client_metadata',{hidden:'answer key'}]]) {
    const probe = isolated(); const request = JSON.parse(probe.firstRequestUtf8); request[key] = value;
    probe.firstRequestUtf8 = stableJson(request); probe.captureSha256 = sha256(probe.firstRequestUtf8); probe.inputReceiptSha256 = probe.captureSha256;
    assert.equal(verifySummaryIsolation(probe, probeExpected).status, 'FAIL', key);
  }
  const expected = { ...probeExpected, allowedTools:['scoped.read_original_records'], toolDefinitions:[{type:'function',name:'scoped.read_original_records'}] };
  const probe = isolated(hash,{},input,expected.allowedTools); const wire = JSON.parse(probe.firstRequestUtf8);
  wire.tools[0].description = 'LEAKED_ANSWER_KEY'; probe.firstRequestUtf8 = stableJson(wire); probe.captureSha256 = sha256(probe.firstRequestUtf8);
  assert.equal(verifyProbeSeparation(probe, expected).status,'FAIL');
});

test('verifier normalizes actual typed Responses text segments and preserves context carriers', () => {
  const wire = [{type:'message',role:'user',content:[{type:'input_text',text:'Voltage '},{type:'input_text',text:'3.3 V'}]}];
  assert.deepEqual(normalizeNativeInput(wire),[{role:'user',content:'Voltage 3.3 V'}]);
  wire[0].id = 'native-message-1';
  assert.deepEqual(normalizeNativeInput(wire),[{role:'user',content:'Voltage 3.3 V',id:'native-message-1'}]);
  assert.throws(()=>normalizeNativeInput([{role:'user',content:'adapter-synthesized legacy body'}]));
  assert.throws(()=>normalizeNativeInput([{type:'message',role:'user',content:[{type:'input_image',image_url:'hidden'}]}]));
  const probe = isolated(); const request = JSON.parse(probe.firstRequestUtf8); request.instructions='Frozen policy.';
  probe.firstRequestUtf8=stableJson(request); probe.captureSha256=sha256(probe.firstRequestUtf8); probe.inputReceiptSha256=probe.captureSha256;
  assert.equal(verifySummaryIsolation(probe,{...probeExpected,envelope:{instructions:'Frozen policy.'}}).status,'PASS');
});

test('checkpoint summary comes from exact owned compacted payload, never an independent adapter message', async () => {
  const mock=mockAdapter();
  const baseline=(await mock.adapter.originals({cycle:1})).parentState;
  const compact=await mock.adapter.compact({cycle:1,actionId:actionIdFor('record-test',1,'compact'),baseline,windowId:'record-test'});
  const expected={contextSha256:compact.contextSha256,parentThreadId:compact.nativeThreadId,actionId:compact.actionId,nativeTurnId:compact.nativeTurnId,windowId:'record-test',baseline,summaryRole:'system'};
  assert.equal(extractCheckpoint(compact.checkpoint,expected).status,'PASS');
  const poisoned=clone(compact.checkpoint); poisoned.messages=[{role:'system',content:'Counterfeit summary and answer key'}];
  assert.equal(extractCheckpoint(poisoned,expected).status,'FAIL');
  const wrongOwner=clone(compact.checkpoint); const binding=JSON.parse(wrongOwner.bindingReceiptUtf8); binding.nativeThreadId='foreign-thread';
  wrongOwner.bindingReceiptUtf8=stableJson(binding); wrongOwner.bindingReceiptSha256=sha256(wrongOwner.bindingReceiptUtf8);
  assert.equal(extractCheckpoint(wrongOwner,expected).status,'FAIL');
  const absent=clone(compact.checkpoint); delete absent.bindingReceiptUtf8;
  assert.equal(extractCheckpoint(absent,expected).status,'NOT_TESTED');
  const result=await simulate({poisonCheckpointMessages:true}); assert.equal(result.result.status,'FAIL');
});

test('summary projection never uses replacement_history containing original user answers', async () => {
  const mock=mockAdapter(), baseline=(await mock.adapter.originals({cycle:1})).parentState;
  const compact=await mock.adapter.compact({cycle:1,baseline,windowId:'projection-test',actionId:actionIdFor('projection-test',1,'compact')});
  const result=extractCheckpoint(compact.checkpoint,{baseline,windowId:'projection-test',nativeTurnId:compact.nativeTurnId,parentThreadId:compact.nativeThreadId,actionId:compact.actionId,contextSha256:compact.contextSha256,summaryRole:'system'});
  assert.equal(result.status,'PASS'); assert.equal(result.messages.length,1);
  assert.equal(stableJson(result.messages).includes('ORIGINAL_USER_HISTORY_MUST_NEVER_ENTER_SUMMARY_PROBE'),false);
  const record=JSON.parse(compact.checkpoint.compactedRecordUtf8);
  assert.ok(stableJson(record.payload.replacement_history).includes('ORIGINAL_USER_HISTORY_MUST_NEVER_ENTER_SUMMARY_PROBE'));
});

test('full persisted state, latest post-baseline record and settled window/turn are independently bound', async () => {
  const mock=mockAdapter(), baseline=(await mock.adapter.originals({cycle:1})).parentState;
  const compact=await mock.adapter.compact({cycle:1,baseline,windowId:'state-test',actionId:actionIdFor('state-test',1,'compact')});
  const expected={baseline,windowId:'state-test',nativeTurnId:compact.nativeTurnId,parentThreadId:compact.nativeThreadId,actionId:compact.actionId,contextSha256:compact.contextSha256,summaryRole:'system'};
  assert.notEqual(compact.checkpoint.stateSha256,compact.checkpoint.compactedRecordSha256);
  const appended=clone(compact.checkpoint); appended.stateUtf8+=stableJson({type:'response_item',payload:{role:'assistant',content:'REPLAYED_OR_RECALL_ANSWER'}})+'\n'; appended.stateSha256=sha256(appended.stateUtf8);
  assert.equal(extractCheckpoint(appended,expected).status,'FAIL');
  const noBaseline=extractCheckpoint(compact.checkpoint,{...expected,baseline:null}); assert.equal(noBaseline.status,'NOT_TESTED');
  const noSettlement=clone(compact.checkpoint); delete noSettlement.settledOperationUtf8;
  assert.equal(extractCheckpoint(noSettlement,expected).status,'NOT_TESTED');
  assert.equal(extractCheckpoint(compact.checkpoint,{...expected,baseline:{...baseline,stateUtf8:compact.checkpoint.stateUtf8,stateSha256:compact.checkpoint.stateSha256}}).status,'FAIL');
  assert.equal(extractCheckpoint(compact.checkpoint,{...expected,windowId:'foreign-window'}).status,'FAIL');
  assert.equal(extractCheckpoint(compact.checkpoint,{...expected,nativeTurnId:'foreign-turn'}).status,'FAIL');
  const proof=isolated(); proof.parentStateAfter.stateUtf8+='\nappended recall answer'; proof.parentStateAfter.stateSha256=sha256(proof.parentStateAfter.stateUtf8);
  assert.equal(verifySummaryIsolation(proof,probeExpected).status,'FAIL');
});
