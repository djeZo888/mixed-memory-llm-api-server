import { lstat, readdir, readFile, realpath } from 'node:fs/promises';
import { join, relative } from 'node:path';
import { sha256, stableJson } from './projection.js';

/** Includes every runtime source sibling rather than maintaining an incomplete
 * hand-written import list. Dependencies are separately pinned by package/lock
 * and image; source hashing alone does not qualify installed dependency bytes.
 */
export async function sourceClosure(repository: string, launcherPath: string, qwenReceiptPath: string) {
  if (await realpath(repository) !== repository) throw Error('source_repository_noncanonical');
  const files: Record<string, string> = {};
  let count = 0;
  async function visit(path: string, all = false) {
    const stat = await lstat(path);
    if (++count > 8192 || stat.isSymbolicLink()) throw Error('source_closure_unsafe_or_limit');
    if (stat.isDirectory()) { for (const name of (await readdir(path)).sort()) await visit(join(path, name), all); }
    else if (stat.isFile() && (all || /\.(?:ts|js|json|mjs|mts)$/.test(path))) {
      if (stat.size > 4 * 1024 * 1024 || stat.nlink !== 1) throw Error('source_closure_file_unsafe');
      files[path] = sha256(await readFile(path));
    }
  }
  await visit(join(repository, 'ai-harness/server/src'));
  // Includes the B controller/verifier and every local executable/data dependency.
  await visit(join(repository, 'ai-harness/acceptance/compaction'));
  await visit(join(repository, 'ai-harness/server/package.json'), true);
  await visit(join(repository, 'ai-harness/server/package-lock.json'), true);
  await visit(join(repository, 'ai-harness/deploy/engine'), true);
  await visit(join(repository, 'ai-harness/deploy/codex'), true);
  await visit(join(repository, 'ai-harness/deploy/security'), true);
  await visit(join(repository, 'ai-harness/tools/image'), true);
  await visit(launcherPath, true); await visit(qwenReceiptPath, true);
  return files;
}

/** B's portable logical closure, distinct from byte-exact runtime captures and
 * from the separate protected launcher/provider receipt review tuple. */
export function collectorManifest(files: Record<string, string>, repository: string) {
  return stableJson({ format: 'h040-collector-closure-v1', sourceRevision: '064c6b8c737f5b41d171fdda80bd9ef10ad06eb3',
    files: Object.fromEntries(Object.entries(files).map(([path, hash]) => [relative(repository, path), hash]).filter(([path]) => path.startsWith('ai-harness/') && !path.split('/').includes('..'))) });
}
