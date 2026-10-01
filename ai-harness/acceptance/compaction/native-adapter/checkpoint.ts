import { constants } from 'node:fs';
import { chmod, lstat, mkdir, open, readdir, realpath, readFile } from 'node:fs/promises';
import { dirname, isAbsolute, join, relative, resolve } from 'node:path';
import { randomUUID } from 'node:crypto';
import { sha256, stableJson } from './projection.js';

export const within = (parent: string, child: string) => { const d = relative(parent, child); return d === '' || (!d.startsWith('../') && d !== '..' && !isAbsolute(d)); };
export async function canonicalDirectory(path: string) {
  if (!isAbsolute(path) || resolve(path) !== path || await realpath(path) !== path) throw Error('noncanonical_directory');
  const info = await lstat(path);
  if (!info.isDirectory() || info.isSymbolicLink() || info.uid !== process.getuid?.() || (info.mode & 0o077)) throw Error('directory_not_private_owned');
  return path;
}
export async function privateFile(path: string) {
  const fd = await open(path, constants.O_RDONLY | constants.O_NOFOLLOW);
  try {
    const st = await fd.stat();
    if (!st.isFile() || st.nlink !== 1 || st.uid !== process.getuid?.() || (st.mode & 0o077) || st.size > 64 * 1024 * 1024) throw Error('unsafe_private_file');
    return await fd.readFile();
  } finally { await fd.close(); }
}
export async function fsyncDirectory(directory: string) {
  const handle = await open(directory, constants.O_RDONLY);
  try { await handle.sync(); } finally { await handle.close(); }
}
export async function durableFile(path: string, bytes: Buffer | string) {
  const fd = await open(path, constants.O_WRONLY | constants.O_CREAT | constants.O_EXCL | constants.O_NOFOLLOW, 0o600);
  try { await fd.writeFile(bytes); await fd.sync(); } finally { await fd.close(); }
  await fsyncDirectory(dirname(path));
}
/** Fresh sibling mounts and host state. No scorer, originals, checkpoint or
 * controller source is beneath either path exposed to native Codex.
 */
export async function createLayout(base: string, forbidden: readonly string[]) {
  await canonicalDirectory(base);
  for (const p of forbidden) {
    const actual = await realpath(p);
    if (within(actual, base) || within(base, actual)) throw Error('private_base_overlaps_protected_source');
  }
  const root = join(base, `h039-native-adapter-${randomUUID()}`);
  await mkdir(root, { mode: 0o700 });
  const hostPrivate = join(root, 'host-private'), dataDir = join(root, 'app-data');
  for (const p of [hostPrivate, dataDir]) await mkdir(p, { mode: 0o700 });
  return { root, hostPrivate, dataDir };
}
export async function emptyProbeMounts(root: string, forbidden: readonly string[]) {
  await canonicalDirectory(root);
  const parent = join(root, `probe-${randomUUID()}`);
  await mkdir(parent, { mode: 0o700 });
  const profileDir = join(parent, 'profile'), workspace = join(parent, 'workspace');
  for (const p of [profileDir, workspace]) {
    await mkdir(p, { mode: 0o700 });
    await canonicalDirectory(p);
    if ((await readdir(p)).length) throw Error('probe_mount_not_empty');
    for (const protectedPath of forbidden) if (within(p, protectedPath) || within(protectedPath, p)) throw Error('probe_mount_contains_host_source');
  }
  return { profileDir, workspace };
}

/** Bounded, fsynced snapshot under caller-proved no-writer/settlement. Every
 * regular file is copied, including original rollout and file bytes. SQLite
 * export is supplied separately via Store.db VACUUM INTO while writes are held.
 * This is recovery evidence, never an automatic or atomic rollback facility.
 */
export async function checkpoint(input: {
  hostPrivate: string; sources: Record<string, string>; binding: Record<string, unknown>;
  settled: () => Promise<boolean>; databaseExport?: (path: string) => Promise<void>;
}) {
  await canonicalDirectory(input.hostPrivate);
  if (!await input.settled()) throw Error('checkpoint_owned_work_unsettled');
  const destination = join(input.hostPrivate, `checkpoint-${randomUUID()}`);
  await mkdir(destination, { mode: 0o700 });
  const hashes: Record<string, string> = {};
  let bytes = 0, entries = 0;
  async function copy(source: string, target: string, label: string) {
    const st = await lstat(source);
    if (++entries > 8192 || st.isSymbolicLink() || st.uid !== process.getuid?.()) throw Error('checkpoint_source_unsafe_or_limit');
    if (st.isDirectory()) {
      await mkdir(target, { mode: 0o700 });
      for (const name of (await readdir(source)).sort()) await copy(join(source, name), join(target, name), `${label}/${name}`);
      await fsyncDirectory(target);
    } else {
      if (!st.isFile() || st.nlink !== 1 || (bytes += st.size) > 64 * 1024 * 1024) throw Error('checkpoint_file_unsafe_or_limit');
      const handle = await open(source, constants.O_RDONLY | constants.O_NOFOLLOW);
      let value: Buffer;
      try {
        const opened = await handle.stat();
        if (opened.ino !== st.ino || opened.dev !== st.dev) throw Error('checkpoint_source_changed');
        value = await handle.readFile();
        const end = await handle.stat();
        if (end.size !== st.size || end.mtimeMs !== st.mtimeMs || value.length !== st.size) throw Error('checkpoint_source_changed');
      } finally { await handle.close(); }
      await durableFile(target, value);
      hashes[label] = sha256(value);
    }
  }
  try {
    for (const [name, source] of Object.entries(input.sources)) {
      if (!/^[a-z-]+$/.test(name)) throw Error('invalid_checkpoint_label');
      await canonicalDirectory(source);
      if (within(source, destination) || within(destination, source)) throw Error('checkpoint_overlaps_source');
      await copy(source, join(destination, name), name);
    }
    if (input.databaseExport) {
      const file = join(destination, 'store.sqlite');
      await input.databaseExport(file); await chmod(file, 0o600);
      const handle = await open(file, constants.O_RDONLY | constants.O_NOFOLLOW);
      try { await handle.sync(); hashes['store.sqlite'] = sha256(await handle.readFile()); } finally { await handle.close(); }
    }
    if (!await input.settled()) throw Error('checkpoint_settlement_changed');
    // Re-hash sources independently after all copies, detecting a changing suffix.
    const verified = new Set<string>();
    async function verify(source: string, label: string) {
      const st = await lstat(source);
      if (st.isSymbolicLink()) throw Error('checkpoint_source_changed');
      if (st.isDirectory()) { for (const n of (await readdir(source)).sort()) await verify(join(source, n), `${label}/${n}`); }
      else {
        if (!st.isFile() || st.nlink !== 1 || hashes[label] !== sha256(await readFile(source))) throw Error('checkpoint_source_changed');
        verified.add(label);
      }
    }
    for (const [name, source] of Object.entries(input.sources)) await verify(source, name);
    if (Object.keys(hashes).filter(k => k !== 'store.sqlite').some(k => !verified.has(k))) throw Error('checkpoint_source_deleted');
    const manifest = { schema: 1, checkpointId: destination.split('/').at(-1), binding: input.binding,
      files: hashes, capturedAt: new Date().toISOString(), recovery: 'no-writer-reviewed-reconciliation-only', atomicRollback: false };
    const receipt = stableJson(manifest);
    await durableFile(join(destination, 'manifest.json'), receipt + '\n');
    await fsyncDirectory(destination); await fsyncDirectory(input.hostPrivate);
    return { ...manifest, receiptSha256: sha256(receipt), directory: destination };
  } catch {
    // Partial bytes remain as failed evidence; never delete them or replay compaction.
    await durableFile(join(destination, 'FAILED'), 'checkpoint_not_accepted\n').catch(() => undefined);
    throw Error('checkpoint_failed_preserved');
  }
}
