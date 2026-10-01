import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, readFile, readdir, rm, symlink, writeFile, chmod, realpath } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { Store } from '../src/store.js';
import { checkpoint, createLayout, emptyProbeMounts, canonicalDirectory } from '../../acceptance/compaction/native-adapter/checkpoint.js';
import { sha256, stableJson } from '../../acceptance/compaction/native-adapter/projection.js';

async function fixture(t: any) {
  const root = await realpath(await mkdtemp(join(tmpdir(), 'h039-native-adapter-checkpoint-')));
  const hostPrivate = join(root, 'host-private'), profile = join(root, 'profile'), workspace = join(root, 'workspace');
  for (const dir of [hostPrivate, profile, workspace]) await mkdir(dir, { mode: 0o700 });
  await writeFile(join(profile, 'rollout.jsonl'), 'ORIGINAL_ROLLOUT\n', { mode: 0o600 });
  await writeFile(join(workspace, 'engineering.json'), '{"fixture":true}\n', { mode: 0o600 });
  const store = new Store(join(root, 'fixture.sqlite'));
  t.after(async () => { store.close(); await rm(root, { recursive: true, force: true }); });
  return { root, hostPrivate, profile, workspace, store };
}
test('fsynced checkpoint preserves profile/store/files and is outside model mounts', async t => {
  const f = await fixture(t);
  const result = await checkpoint({ hostPrivate: f.hostPrivate, sources: { profile: f.profile, files: f.workspace },
    binding: { nativeThreadId: 'fixture-parent', nativeTurnId: 'fixture-last-continuation', actionId: 'fixture-action' },
    settled: async () => true, databaseExport: async file => { f.store.db.prepare('VACUUM INTO ?').run(file); } });
  assert.equal(result.atomicRollback, false);
  assert.equal(await readFile(join(result.directory, 'profile/rollout.jsonl'), 'utf8'), 'ORIGINAL_ROLLOUT\n');
  assert.equal(result.files['files/engineering.json'], sha256('{"fixture":true}\n'));
  const manifest = JSON.parse(await readFile(join(result.directory, 'manifest.json'), 'utf8'));
  assert.equal(result.receiptSha256, sha256(stableJson(manifest)));
  const mounts = await emptyProbeMounts(f.root, [f.hostPrivate]);
  assert.deepEqual(await readdir(mounts.workspace), []); assert.deepEqual(await readdir(mounts.profileDir), []);
  assert.ok(!mounts.workspace.startsWith(result.directory));
});
test('unsettled or changing source checkpoints cannot be accepted; failed bytes retained', async t => {
  const f = await fixture(t);
  await assert.rejects(checkpoint({ hostPrivate: f.hostPrivate, sources: { profile: f.profile }, binding: {}, settled: async () => false }), /unsettled/);
  await assert.rejects(checkpoint({ hostPrivate: f.hostPrivate, sources: { profile: f.profile }, binding: {},
    settled: async () => true, databaseExport: async file => { await writeFile(file, 'sqlite fixture'); await rm(join(f.profile, 'rollout.jsonl')); } }), /failed_preserved/);
  const failed = (await readdir(f.hostPrivate)).find(n => n.startsWith('checkpoint-'))!;
  assert.equal(await readFile(join(f.hostPrivate, failed, 'FAILED'), 'utf8'), 'checkpoint_not_accepted\n');
  assert.equal(await readFile(join(f.hostPrivate, failed, 'profile/rollout.jsonl'), 'utf8'), 'ORIGINAL_ROLLOUT\n');
});
test('source symlinks and protected ancestry are rejected without copying secrets', async t => {
  const f = await fixture(t);
  await symlink(join(f.workspace, 'engineering.json'), join(f.profile, 'private-link'));
  await assert.rejects(checkpoint({ hostPrivate: f.hostPrivate, sources: { profile: f.profile }, binding: {}, settled: async () => true }), /failed_preserved/);
  await assert.rejects(createLayout(f.profile, [f.root]), /overlaps/);
  const link = join(f.root, 'linked-root'); await symlink(f.profile, link);
  await assert.rejects(canonicalDirectory(link), /noncanonical/);
  await chmod(f.workspace, 0o755); await assert.rejects(canonicalDirectory(f.workspace), /private/);
});
