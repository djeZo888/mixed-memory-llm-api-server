import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import * as fs from 'node:fs/promises';
import { readFileSync, mkdtempSync, mkdirSync, copyFileSync, rmSync, realpathSync } from 'node:fs';
import { stripTypeScriptTypes } from 'node:module';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import os from 'node:os';
import path from 'node:path';

// Exercise exact patched helpers with real filesystem operations. This is not
// a Chrome execution test; native non-root Chromium is a separate Linux gate.
const source = process.env.AI_HARNESS_MINIMAX_SOURCE;
assert.ok(source && path.isAbsolute(source), 'Set AI_HARNESS_MINIMAX_SOURCE to pristine ae65651d source');
const files = [
  ['packages/agent-tools/src/desktop/local-browser.ts', 'ee9f680ae82f16f900d607e55009c35e6549b1565428004c1dcbe2794076dc52'],
  ['packages/tui/src/runtime/browser/headless-chrome-provider.ts', '324f261ac24e9aa94d9a2299e8b4db1cf03e552f99757513bec9e4e733e54b96'],
  ['packages/tui/src/runtime/browser/headless-chrome-transport.ts', '2d72e96d68f87d365b5a0670e5ca45addfb72d6d3e878b42b20d68b78ebb810e'],
];
const patch = fileURLToPath(new URL('../patches/0006-browser-workspace-downloads.patch', import.meta.url));
const copied = mkdtempSync(path.join(os.tmpdir(), 'h001-browser-source-'));
let compactSource, provider, transport;
try {
  for (const [name, hash] of files) {
    assert.equal(createHash('sha256').update(readFileSync(path.join(source, name))).digest('hex'), hash);
    mkdirSync(path.dirname(path.join(copied, name)), { recursive: true });
    copyFileSync(path.join(source, name), path.join(copied, name));
  }
  for (const args of [['apply', '--check', patch], ['apply', patch]]) {
    const applied = spawnSync('git', args, { cwd: copied, encoding: 'utf8' });
    assert.equal(applied.status, 0, applied.stderr);
  }
  [compactSource, provider, transport] = files.map(([name]) => readFileSync(path.join(copied, name), 'utf8'));
} finally { rmSync(copied, { recursive: true, force: true }); }
const extract = (value, start, end) => {
  assert.ok(value.includes(start) && value.includes(end));
  return stripTypeScriptTypes(value.slice(value.indexOf(start), value.indexOf(end))).replaceAll('export ', '');
};
const helpers = extract(transport, '// ai-harness downloads:', '// ai-harness downloads end.');
const { ensureWorkspaceBrowserDownloadDirectory: ensure, completedWorkspaceBrowserDownloadPath: completed } = Function(
  'realpath', 'relative', 'join', 'mkdir', 'lstat', 'chmod', 'readdir',
  `${helpers}; return { ensureWorkspaceBrowserDownloadDirectory, completedWorkspaceBrowserDownloadPath };`,
)(fs.realpath, path.relative, path.join, fs.mkdir, fs.lstat, fs.chmod, fs.readdir);
const sessionCode = extract(provider, 'export function safeSessionId(', '/** Remove the exact persistent roots');
const { safeSessionId, resolveHeadlessSessionLaunchOptions: resolveOptions, exposeWorkspaceBrowserDownload: expose } = Function(
  'createHash', 'join', 'isRecord', 'completedWorkspaceBrowserDownloadPath',
  `${sessionCode}; return { safeSessionId, resolveHeadlessSessionLaunchOptions, exposeWorkspaceBrowserDownload };`,
)(createHash, path.join, (value) => value !== null && typeof value === 'object' && !Array.isArray(value), completed);
const compactCode = extract(compactSource, 'function boundedBrowserDownload(', 'function boundedWriteTarget(');
const compact = Function('isRecord', `${compactCode}; return boundedBrowserDownload;`)(
  (value) => value !== null && typeof value === 'object' && !Array.isArray(value),
);
const guid = 'f17a9f11-2211-4333-8444-555555555555';
const guid2 = 'f17a9f11-2211-4333-8444-666666666666';

test('pinned browser workspace download contract', async (t) => {
  const originalCwd = process.cwd();
  const base = realpathSync(mkdtempSync(path.join(os.tmpdir(), 'h001-browser-downloads-')));
  let sequence = 0;
  async function workspace() {
    const cwd = path.join(base, `workspace-${sequence++}`);
    await fs.mkdir(cwd);
    process.chdir(cwd);
    return { cwd, directory: path.join(cwd, 'downloads', 'browser', safeSessionId('fixture')) };
  }
  try {
    await t.test('session IDs cannot escape and caller-supplied download directory cannot override workspace', async () => {
      const { cwd } = await workspace();
      const seen = new Set();
      for (const id of ['../escape', '/absolute', '..', 'a/b', 'a?b', '\\windows', '\u0000', '', 'x'.repeat(512)]) {
        const selected = resolveOptions({ dataDir: '/profile', downloadDir: '/unsafe' }, id);
        assert.match(safeSessionId(id), /^[a-zA-Z0-9._-]{1,64}-[a-f0-9]{16}$/u);
        assert.equal(selected.downloadDir, path.join(cwd, 'downloads', 'browser', safeSessionId(id)));
        assert.ok(!seen.has(selected.downloadDir)); seen.add(selected.downloadDir);
        await ensure(selected.downloadDir);
      }
      await assert.rejects(ensure(path.join(cwd, '..', 'outside')), /UNSAFE_BROWSER_DOWNLOAD_DIRECTORY/u);
      await assert.rejects(ensure(`${cwd}/downloads/browser/../escape`), /UNSAFE_BROWSER_DOWNLOAD_DIRECTORY/u);
    });
    await t.test('reject symlinks at every directory component and an unsafe destination', async () => {
      const outside = path.join(base, 'outside'); await fs.mkdir(outside);
      for (const depth of [0, 1, 2]) {
        const { cwd, directory } = await workspace();
        const parts = ['downloads', 'browser', safeSessionId('fixture')];
        const destination = path.join(cwd, ...parts.slice(0, depth + 1));
        await fs.mkdir(path.dirname(destination), { recursive: true });
        await fs.symlink(outside, destination);
        await assert.rejects(ensure(directory), /UNSAFE_BROWSER_DOWNLOAD_DIRECTORY/u);
      }
      const { directory } = await workspace(); await ensure(directory);
      await fs.writeFile(path.join(outside, guid), 'outside');
      await fs.symlink(path.join(outside, guid), path.join(directory, guid));
      await assert.rejects(ensure(directory), /UNSAFE_BROWSER_DOWNLOAD_DESTINATION/u);
      await assert.rejects(completed(directory, guid), /UNSAFE_BROWSER_DOWNLOAD_DESTINATION/u);
      assert.equal(await fs.readFile(path.join(outside, guid), 'utf8'), 'outside');
    });
    await t.test('reject hardlinks and directory destinations', async () => {
      const { directory } = await workspace(); await ensure(directory);
      const outsideFile = path.join(base, 'hardlink-source'); await fs.writeFile(outsideFile, 'fixture');
      await fs.link(outsideFile, path.join(directory, guid));
      await assert.rejects(ensure(directory), /UNSAFE_BROWSER_DOWNLOAD_DESTINATION/u);
      await fs.unlink(path.join(directory, guid)); await fs.mkdir(path.join(directory, guid));
      await assert.rejects(ensure(directory), /UNSAFE_BROWSER_DOWNLOAD_DESTINATION/u);
    });
    await t.test('completed GUID artifacts are relative, regular and collision independent', async () => {
      const { directory } = await workspace(); await ensure(directory);
      await fs.writeFile(path.join(directory, guid), '%PDF-1.7 first');
      await fs.writeFile(path.join(directory, guid2), '%PDF-1.7 second');
      for (const id of [guid, guid2]) {
        const result = await expose({ success: true, download: { state: 'completed', guid: id, fileName: 'same.pdf', filePath: '/untrusted/guess.pdf' } }, directory);
        assert.equal(result.download.filePath, `downloads/browser/${safeSessionId('fixture')}/${id}`);
        assert.equal(compact(result.download).filePath, result.download.filePath);
      }
      for (const id of ['../escape', '/absolute', 'invalid', undefined]) {
        await assert.rejects(completed(directory, id), /UNSAFE_BROWSER_DOWNLOAD_GUID/u);
      }
      await assert.rejects(completed(directory, '00000000-0000-0000-0000-000000000000'), /ENOENT/u);
      assert.equal((await fs.stat(directory)).mode & 0o777, 0o700);
    });
    await t.test('unfinished or unsafe results cannot expose paths in compact output', async () => {
      const { directory } = await workspace(); await ensure(directory);
      const valid = `downloads/browser/${safeSessionId('fixture')}/${guid}`;
      for (const state of ['inProgress', 'canceled', undefined]) {
        const value = { state, guid, filePath: valid, fileName: 'fixture.pdf' };
        assert.equal((await expose({ download: value }, directory)).download.filePath, undefined);
        assert.equal(compact(value).filePath, undefined);
      }
      for (const filePath of ['/tmp/file.pdf', '../escape', 'downloads/browser/../../escape', `${valid}/..`, `${valid}\n`, `downloads/browser/${safeSessionId('fixture')}/..`]) {
        assert.equal(compact({ state: 'completed', filePath }).filePath, undefined);
      }
    });
    await t.test('native wiring validates each action and launch; GUID policy fails closed; cleanup retains user downloads', async () => {
      assert.match(provider, /await ensureWorkspaceBrowserDownloadDirectory\(downloadDir\);\n    this\.markSessionActive/u);
      assert.match(provider, /const result = await exposeWorkspaceBrowserDownload\(/u);
      assert.match(transport, /await ensureWorkspaceBrowserDownloadDirectory\(downloadDir\);/u);
      assert.match(transport, /await this\.connection\.send\(\n      'Browser\.setDownloadBehavior',\n      \{ behavior: 'allowAndName', downloadPath: this\.downloadDir, eventsEnabled: true \},\n      undefined,\n      options,\n    \);/u);
      assert.doesNotMatch(transport, /'Page\.setDownloadBehavior'/u);
      const cleanup = extract(provider, 'export async function disposeHeadlessSessionStorage(', '/**\n * Accept both the compact TUI wait_for');
      const dispose = Function('resolveHeadlessSessionLaunchOptions', 'rm', `${cleanup}; return disposeHeadlessSessionStorage;`)(resolveOptions, fs.rm);
      const { cwd, directory } = await workspace(); await ensure(directory);
      await fs.writeFile(path.join(directory, guid), 'artifact');
      const profile = path.join(cwd, 'profile'); await fs.mkdir(profile);
      await dispose({ dataDir: profile }, 'fixture');
      assert.equal(await fs.readFile(path.join(directory, guid), 'utf8'), 'artifact');
      const sandbox = extract(transport, 'export function resolveChromeSandboxArgs(', '/** Create or repair');
      const args = Function(`${sandbox}; return resolveChromeSandboxArgs;`)();
      assert.deepEqual(args('linux', 1000), []);
    });
  } finally { process.chdir(originalCwd); await fs.rm(base, { recursive: true, force: true }); }
});
