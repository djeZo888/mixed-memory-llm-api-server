import test from 'node:test';
import assert from 'node:assert/strict';
import { extractPersistedSummary, sha256, summaryThreadParams, summaryProbeText } from '../../acceptance/compaction/native-adapter/projection.js';
import adapter, { createNativeAdapter } from '../../acceptance/compaction/native-adapter/adapter.js';
import { bootstrap } from '../../acceptance/compaction/native-adapter/bootstrap.js';

const before = Buffer.from(JSON.stringify({ timestamp: '2026-10-01T01:10:00Z', type: 'session_meta', payload: { id: 'parent-source-fixture' } }) + '\n' +
  JSON.stringify({ timestamp: '2026-10-01T01:10:01Z', type: 'response_item', payload: { role: 'user', content: [{ text: 'ORIGINAL_ONLY_SENTINEL' }] } }) + '\n');
const binding = { nativeThreadId: 'parent-source-fixture', nativeTurnId: 'compact-fixture', actionId: 'compact-action-fixture',
  beforeBytes: before.length, beforeSha256: sha256(before), dispatchedAt: '2026-10-01T01:10:02Z', settledAt: '2026-10-01T01:10:04Z', summaryPrefix: 'SOURCE_FIXTURE_PREFIX\n' };
const compact = (message: unknown, timestamp = '2026-10-01T01:10:03Z') => Buffer.from(JSON.stringify({ timestamp, type: 'compacted',
  payload: { message: typeof message === 'string' && message.trim() && !message.includes('\0') ? binding.summaryPrefix + message : message,
    replacement_history: [{ role: 'user', content: 'REPLACEMENT_ORIGINAL_SENTINEL' }] } }) + '\n');

test('persisted summary excludes native replacement history and original user text', () => {
  const result = extractPersistedSummary(Buffer.concat([before, compact('Accepted current facts')]), binding);
  const probe = summaryProbeText(result.message, 'Frozen policy', { questions: ['fixture question'] });
  assert.equal(result.contextSha256, sha256(binding.summaryPrefix + 'Accepted current facts'));
  assert.doesNotMatch(probe, /ORIGINAL_ONLY_SENTINEL|REPLACEMENT_ORIGINAL_SENTINEL/);
  assert.doesNotMatch(JSON.stringify(result), /replacement_history/);
});
test('empty, ambiguous, unmatched, truncated or damaged summaries fail', () => {
  for (const message of ['', ' ', null, {}, '\0bad']) assert.throws(() => extractPersistedSummary(Buffer.concat([before, compact(message)]), binding));
  assert.throws(() => extractPersistedSummary(Buffer.concat([before, compact('one'), compact('two')]), binding), /ambiguous/);
  assert.throws(() => extractPersistedSummary(Buffer.concat([before, compact('outside', '2026-10-01T00:00:00Z')]), binding), /unmatched/);
  const valid = Buffer.concat([before, compact('facts')]);
  assert.throws(() => extractPersistedSummary(valid.subarray(0, valid.length - 1), binding), /flush/);
  assert.throws(() => extractPersistedSummary(valid, { ...binding, nativeThreadId: 'other-parent' }), /thread_mismatch/);
  assert.throws(() => extractPersistedSummary(valid, { ...binding, beforeSha256: sha256('changed') }), /prefix/);
  assert.throws(() => extractPersistedSummary(before, binding));
  const rollback = Buffer.from(JSON.stringify({ type: 'event_msg', payload: { type: 'thread_rolled_back', num_turns: 1 } }) + '\n');
  assert.throws(() => extractPersistedSummary(Buffer.concat([valid, rollback]), binding), /rollback/);
  const prefixOnly = Buffer.from(JSON.stringify({ timestamp: '2026-10-01T01:10:03Z', type: 'compacted', payload: { message: binding.summaryPrefix } }) + '\n');
  assert.throws(() => extractPersistedSummary(Buffer.concat([before, prefixOnly]), binding), /prefix_only/);
  assert.throws(() => extractPersistedSummary(valid, { ...binding, summaryPrefix: '' }), /prefix_unavailable/);
});
test('no-tools probe fields are explicit; import cannot start a native app', async () => {
  const params = summaryThreadParams('/isolated/empty-workspace', 'Frozen policy');
  assert.equal(params.sandbox, 'read-only'); assert.equal(params.approvalPolicy, 'never');
  assert.deepEqual(params.environments, []); assert.equal(params.ephemeral, false);
  for (const [key, value] of Object.entries(params.config)) assert.equal(value, key === 'project_doc_max_bytes' ? 0 : false);
  assert.equal(adapter.enabled, false); assert.deepEqual(adapter.capabilities, []);
  assert.equal((await adapter.runtime()).binarySha256.value, null);
  await assert.rejects(adapter.open({ signal: new AbortController().signal }), /disabled/);
  await assert.rejects(createNativeAdapter().coldResume(), /unqualified/);
  await assert.rejects(bootstrap({ review: { enabled: false } } as any), /review/);
});
