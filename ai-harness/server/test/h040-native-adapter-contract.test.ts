import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, readFile, realpath, rm, writeFile, symlink } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { Store } from '../src/store.js';
import { Files } from '../src/files.js';
import { collectContinuationArtifacts } from '../../acceptance/compaction/native-adapter/artifacts.js';
import { sourceClosure, collectorManifest } from '../../acceptance/compaction/native-adapter/source-closure.js';
import { reviewedExpiry, FIXED_POLICY, STAGE_POLICY } from '../../acceptance/compaction/native-adapter/bootstrap.js';
import { reviewSnapshot, sha256, stableJson, summaryProbeText, extractPersistedSummary } from '../../acceptance/compaction/native-adapter/projection.js';
import { normalizeNativeInput, bindReviewedEnvelope } from '../../acceptance/compaction/native-adapter/dispatch-guard.js';
import { createNativeAdapter } from '../../acceptance/compaction/native-adapter/adapter.js';
const b = await import(new URL('../../../../../B-retention-integration/repo/ai-harness/acceptance/compaction/scorer.mjs', import.meta.url).href);
const bc = await import(new URL('../../../../../B-retention-integration/repo/ai-harness/acceptance/compaction/controller.mjs', import.meta.url).href);
const prefix = JSON.parse(await readFile(new URL('../../../../native-prefix.json', import.meta.url), 'utf8')).text;
test('SYNTHETIC independently B-derived projection equals E exact constructor/typed manifest and metadata bindings', () => {
  const input = [{ type: 'message', id: 'developer-native-id', role: 'developer', phase: 'commentary', content: [{ type: 'input_text', text: 'frozen scaffold', annotations: [] }] }];
  assert.equal(b.stableJson({ z: { b: 2, a: 1 }, a: 'bytes\nunchanged' }), stableJson({ z: { b: 2, a: 1 }, a: 'bytes\nunchanged' }));
  assert.deepEqual(normalizeNativeInput(input), b.normalizeNativeInput(input));
  const envelope = { model: 'qwen3.8-27b', instructions: 'reviewed policy', client_metadata: { thread_id: '@h040:probe-native-thread-id', turn_id: '@h040:probe-native-turn-id', root_turn_id: '@h040:probe-native-turn-id' } };
  assert.deepEqual(bindReviewedEnvelope(envelope, 'actual-native-thread', 'actual-native-turn'), bc.bindReviewedEnvelope(envelope, { probeThreadId: 'actual-native-thread', probeTurnId: 'actual-native-turn' }));
  assert.equal(summaryProbeText('selected summary', 'frozen policy', { q: [2, 1], b: true }), b.stableJson({ policy: 'frozen policy', persistedCompactedMessage: 'selected summary', questions: { q: [2, 1], b: true } }));
  for (const bad of [{ ...input[0], extraHistory: 'old' }, { ...input[0], content: [{ type: 'input_text', text: 'x', annotations: ['hidden'] }] }]) {
    assert.throws(() => normalizeNativeInput([bad])); assert.throws(() => b.normalizeNativeInput([bad]));
  }
});
test('reviewed policy/projection/expected digests cannot mutate across open/probe async boundaries', async () => {
  const spec = { format: 'h040-fresh-persisted-message-v1', prefixInput: [], envelope: { instructions: 'approved', model: 'qwen3.8-27b' }, collectorManifestUtf8: 'closure' };
  const initial: any = { frozenPolicy: 'approved', compactionSummaryPrefix: prefix, projectionSpec: spec,
    bootstrap: { repository: '/synthetic', review: { enabled: false, approvedBy: 'root', candidateCommit: 'a'.repeat(40), notAfterUtc: '2026-10-01T04:26:10Z', policy: FIXED_POLICY,
      files: {}, projection: { format: spec.format, frozenPolicySha256: sha256('approved'), specSha256: sha256(stableJson(spec)), collectorSourceSha256: sha256('closure') } } } };
  const adapter = createNativeAdapter(initial), sealed = reviewSnapshot(initial);
  await assert.rejects(adapter.open({ runId: 'synthetic-suite-owner', signal: new AbortController().signal }), /root_concrete_review_required/);
  initial.frozenPolicy = 'changed after open'; initial.projectionSpec.envelope.instructions = 'unapproved'; initial.bootstrap.review.projection.specSha256 = sha256(stableJson(initial.projectionSpec));
  assert.equal(sealed.frozenPolicy, 'approved'); assert.equal(sealed.projectionSpec.envelope.instructions, 'approved');
  assert.throws(() => { sealed.projectionSpec.envelope.instructions = 'mutated'; }, TypeError);
  await assert.rejects(adapter.open({ runId: 'synthetic-suite-owner', signal: new AbortController().signal }), /duplicate/);
  assert.equal(adapter.enabled, false); assert.deepEqual(adapter.capabilities, []); assert.equal((await adapter.runtime()).binarySha256.value, null);
});
test('explicit H040 window is bounded by exact authority, no arbitrary future expiry', () => {
  const review: any = { settlementReserveMs: 180000, notAfterUtc: '2026-10-01T04:20:00Z', authorization: { task: 'H040', windowId: 'root-host-window', startsUtc: '2026-10-01T02:26:10Z', capUtc: '2026-10-01T04:26:10Z' } };
  assert.equal(reviewedExpiry(review, Date.parse('2026-10-01T03:00:00Z')), Date.parse(review.notAfterUtc));
  for (const bad of [{ ...review, settlementReserveMs: 5000 }, { ...review, notAfterUtc: '2026-10-02T04:26:10Z' }, { ...review, notAfterUtc: '2026-10-01T02:25:00Z' }, { ...review, authorization: { ...review.authorization, capUtc: '2026-10-02T04:26:10Z' } }]) assert.throws(() => reviewedExpiry(bad, Date.parse('2026-10-01T03:00:00Z')));
});
test('source audited prefix requires exact newline and a nonempty persisted suffix', () => {
  assert.equal(Buffer.byteLength(prefix), 399); assert.equal(sha256(prefix), 'e9b088e794a6bb9082ac053fcc760bd818d7e720ee4bcdc72c6e480de7b7cb0e');
  const before = Buffer.from('{"type":"session_meta","payload":{"id":"parent"}}\n'), now = new Date().toISOString();
  const binding = { nativeThreadId: 'parent', nativeTurnId: 'turn', actionId: 'action', beforeBytes: before.length, beforeSha256: sha256(before), dispatchedAt: now, settledAt: now, summaryPrefix: prefix };
  const state = (message: string) => Buffer.concat([before, Buffer.from(JSON.stringify({ timestamp: now, type: 'compacted', payload: { message, replacement_history: [{ content: 'DO_NOT_USE' }] } }) + '\n')]);
  assert.equal(extractPersistedSummary(state(prefix + '\nvalid suffix'), binding).message, prefix + '\nvalid suffix');
  assert.throws(() => extractPersistedSummary(state(prefix + 'missing separator'), binding)); assert.throws(() => extractPersistedSummary(state(prefix + '\n'), binding));
});
test('collector portable closure binds actual entire E/B runtime graph and matches B requirements', async t => {
  const repo = resolve(fileURLToPath(new URL('../../../', import.meta.url))), directory = await realpath(await mkdtemp(join(tmpdir(), 'h040-native-adapter-closure-')));
  t.after(() => rm(directory, { recursive: true, force: true })); const receipt = join(directory, 'receipt.json'); await writeFile(receipt, '{}', { mode: 0o600 });
  const files = await sourceClosure(repo, join(repo, 'ai-harness/deploy/run-codex.sh'), receipt), bytes = collectorManifest(files, repo), parsed = JSON.parse(bytes);
  assert.equal(b.validateCollectorManifest(bytes), true);
  for (const relative of ['ai-harness/acceptance/compaction/native-adapter/collector.ts', 'ai-harness/acceptance/compaction/native-adapter/native-observer.ts', 'ai-harness/acceptance/compaction/native-adapter/artifacts.ts', 'ai-harness/acceptance/compaction/scorer.mjs', 'ai-harness/server/src/gateway.ts']) assert.equal(parsed.files[relative], sha256(await readFile(join(repo, relative))));
  assert.ok(Object.keys(parsed.files).length > 100);
});
test('SYNTHETIC continuation reads actual immutable registered files and rejects foreign run/symlink', async t => {
  const root = await realpath(await mkdtemp(join(tmpdir(), 'h040-native-adapter-artifacts-'))), privateDir = join(root, 'private'); await mkdir(privateDir, { mode: 0o700 });
  const store = new Store(join(root, 'store.sqlite')), files = new Files(join(root, 'app'), store); await files.init(); const s = store.createSession(); await files.prepare(s.id, s.workspaceId);
  t.after(async () => { store.close(); await rm(root, { recursive: true, force: true }); });
  const run = store.createRun(s, 'message', 'synthetic continuation', []); store.updateRun(run.id, 'completed');
  for (const name of ['sensor-policy.json', 'engineering-calculation.json']) { await writeFile(join(files.workspace(s.workspaceId), name), JSON.stringify({ actualOutput: name }), { mode: 0o600 }); await files.registerArtifact(s.id, name, name, 'application/json', run.id); }
  const actual = await collectContinuationArtifacts(store, files, privateDir, s.id, run.id); assert.deepEqual(actual.artifacts['sensor-policy.json'], { actualOutput: 'sensor-policy.json' });
  assert.equal(actual.artifactReceiptSha256, sha256(actual.artifactReceiptUtf8)); const foreign = store.createSession(); await assert.rejects(collectContinuationArtifacts(store, files, privateDir, foreign.id, run.id));
  const artifact = store.artifactsForRun(s.id, run.id)[0], path = join(files.root, 'artifacts', artifact.path); await rm(path); await symlink(join(files.workspace(s.workspaceId), 'sensor-policy.json'), path);
  await assert.rejects(collectContinuationArtifacts(store, files, privateDir, s.id, run.id));
});

test('summary stage freezes its sole Qwen route and never qualifies child/image APIs', () => {
  assert.deepEqual(STAGE_POLICY.qualifiedAliases, ['qwen3.8-27b']); assert.equal(STAGE_POLICY.nativeDelegationQualified, false); assert.equal(STAGE_POLICY.imageJobsQualified, false);
  assert.throws(() => (STAGE_POLICY.qualifiedAliases as any).push('qwen3.8-27b-gpu0'), TypeError);
});
