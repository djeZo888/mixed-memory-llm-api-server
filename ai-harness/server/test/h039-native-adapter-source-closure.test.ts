import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readFile, realpath, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { sourceClosure } from '../../acceptance/compaction/native-adapter/source-closure.js';
import { sha256 } from '../../acceptance/compaction/native-adapter/projection.js';

test('source closure independently hashes actual imported runtime siblings and pinned dependencies', async t => {
  const repository = resolve(fileURLToPath(new URL('../../../', import.meta.url)));
  const directory = await realpath(await mkdtemp(join(tmpdir(), 'h039-native-adapter-closure-')));
  t.after(() => rm(directory, { recursive: true, force: true }));
  const receipt = join(directory, 'receipt.json'); await writeFile(receipt, '{}', { mode: 0o600 });
  const files = await sourceClosure(repository, join(repository, 'ai-harness/deploy/run-codex.sh'), receipt);
  for (const name of ['codex-connection.ts', 'codex-responses.ts', 'gateway.ts', 'message-limits.ts', 'broker.ts', 'protected-credential.ts']) {
    const path = join(repository, 'ai-harness/server/src', name);
    assert.equal(files[path], sha256(await readFile(path)));
  }
  assert.equal(files[join(repository, 'ai-harness/server/package-lock.json')], sha256(await readFile(join(repository, 'ai-harness/server/package-lock.json'))));
  assert.equal(files[join(repository, 'ai-harness/acceptance/compaction/native-adapter/source-closure.ts')], sha256(await readFile(join(repository, 'ai-harness/acceptance/compaction/native-adapter/source-closure.ts'))));
  assert.ok(Object.keys(files).length > 100);
});
