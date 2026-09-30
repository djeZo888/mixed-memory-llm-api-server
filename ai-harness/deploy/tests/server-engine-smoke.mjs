#!/usr/bin/env node
/** Actual SERVER adapter -> launcher -> native ACP, with zero generation.
 * Requires the approved built server engine module, ordinary Linux user and
 * final local engine image. Never starts the app or sends a prompt.
 */
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { createHash, randomBytes } from 'node:crypto';
import { mkdtemp, mkdir, readFile, realpath, rm, writeFile, lstat } from 'node:fs/promises';
import { join, resolve, isAbsolute } from 'node:path';
import { tmpdir } from 'node:os';
import { pathToFileURL } from 'node:url';
import { execFileSync } from 'node:child_process';

if (process.argv.includes('--help')) {
  console.log('Usage: node server-engine-smoke.mjs --server-module ABS/engine.js --launcher ABS/run-engine.sh --output ABS/new-receipt.json');
  process.exit(0);
}
const options = {};
for (let i = 2; i < process.argv.length; i += 2) {
  const key = process.argv[i];
  assert(['--server-module', '--launcher', '--output'].includes(key) && !options[key] && process.argv[i + 1], 'invalid or duplicate argument');
  options[key] = process.argv[i + 1];
}
for (const key of ['--server-module', '--launcher', '--output']) assert(isAbsolute(options[key] ?? ''), `${key} requires an absolute path`);
assert(process.platform === 'linux' && process.getuid() !== 0, 'requires ordinary Linux user');
process.umask(0o077);
const root = await realpath(await mkdtemp(join(tmpdir(), 'h001-server-native-')));
const profile = join(root, 'profile'), workspace = join(root, 'workspace');
await mkdir(profile, { mode: 0o700 }); await mkdir(workspace, { mode: 0o700 });
const token = randomBytes(32).toString('base64url');
const report = { scope: 'approved server adapter to real launcher ACP; no app activation or generation', generationRequestsSent: 0, checks: {}, httpRequests: 0 };
const podman = (...args) => execFileSync('/usr/bin/podman', ['--remote=false', ...args], { encoding: 'utf8', env: { HOME: process.env.HOME, PATH: '/usr/bin:/bin', XDG_RUNTIME_DIR: `/run/user/${process.getuid()}` }, timeout: 30_000 }).trim();
const server = createServer((_req, res) => { report.httpRequests++; res.writeHead(403).end(); });
let engine, container;
try {
  // Exclusive fixture refuses all traffic and proves initialize/new did not infer.
  await new Promise((yes, no) => { server.once('error', no); server.listen(8081, '127.0.0.1', yes); });
  const { createEngine } = await import(pathToFileURL(options['--server-module']));
  let nativeSessionId;
  engine = createEngine({ sessionId: 'h001-server-no-generation', profileDir: profile, workspace,
    launcher: options['--launcher'], gatewayUrl: 'http://10.0.2.2:8081/v1', gatewayToken: token,
    stderrPath: join(root, 'engine.stderr'), onNativeSessionId: value => { nativeSessionId = value; },
    onUpdate: update => { report.updateTypes ??= []; if (!report.updateTypes.includes(update.type)) report.updateTypes.push(update.type); if (update.type === 'text' && update.text) report.unexpectedText = true; },
  });
  await engine.start();
  assert(nativeSessionId, 'real server adapter failed to receive native session ID');
  report.nativeSessionId = nativeSessionId;
  report.serverModuleSha256 = createHash('sha256').update(await readFile(options['--server-module'])).digest('hex');
  for (const id of podman('ps', '--quiet', '--no-trunc').split('\n').filter(Boolean)) {
    const metadata = JSON.parse(podman('inspect', '--format', '{{json .Mounts}}', id));
    if (metadata.some(m => m.Source === profile && m.Destination === profile) && metadata.some(m => m.Source === workspace && m.Destination === workspace)) {
      assert(!container, 'multiple containers share this fixture'); container = id;
    }
  }
  assert(container, 'owned native container missing');
  report.containerId = container;
  const environment = JSON.parse(podman('exec', container, 'node', '-e', 'console.log(JSON.stringify({uid:process.getuid(),home:process.env.HOME,data:process.env.MINIMAX_DATA_DIR,cwd:process.cwd(),path:process.env.PATH}))'));
  assert.equal(environment.home, join(profile, 'state/home'));
  assert.equal(environment.data, join(profile, 'state'));
  assert.equal(environment.cwd, workspace);
  assert.equal(environment.uid, process.getuid());
  assert(environment.path.includes('/opt/ai-harness/tools/runtime/node_modules/.bin'));
  const permission = await lstat(join(profile, 'state/permission.json'));
  assert(permission.isFile() && !permission.isSymbolicLink() && permission.nlink === 1);
  report.checks.actualServerEnvironment = { ok: true, hostHome: process.env.HOME, containerHome: environment.home, nativeData: environment.data, permissionFile: 'state/permission.json' };
  const started = performance.now();
  await engine.close(); engine = undefined;
  assert.equal(podman('ps', '--all', '--quiet', '--filter', `id=${container}`), '');
  report.checks.close = { ok: true, containerAbsent: true, elapsedMs: Math.round(performance.now() - started) };
  assert.equal(report.httpRequests, 0, 'unexpected HTTP traffic during no-generation fixture');
  assert(!report.unexpectedText, 'unexpected generated text without a prompt');
  report.ok = true;
} catch (error) {
  report.ok = false; report.error = String(error.message).replaceAll(token, '[REDACTED]');
} finally {
  if (engine) {
    try { await engine.close(); } catch { report.cleanupFailed = true; }
  }
  if (container) {
    try { assert.equal(podman('ps', '--all', '--quiet', '--filter', `id=${container}`), ''); }
    catch { report.cleanupFailed = true; }
  }
  if (server.listening) await new Promise(yes => server.close(yes));
  if (report.cleanupFailed) { report.ok = false; report.preservedScratch = root; }
  else await rm(root, { recursive: true, force: false });
  await writeFile(options['--output'], JSON.stringify(report, null, 2) + '\n', { mode: 0o600, flag: 'wx' });
}
console.log(JSON.stringify(report));
process.exitCode = report.ok ? 0 : 1;
