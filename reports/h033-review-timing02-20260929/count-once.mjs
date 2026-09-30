// Task-local, one invocation per granted before/after case. Run via SSH stdin;
// no remote file writes. Coordinator must read INBOX and record an exclusive
// local intent before invoking. Never run without W2's idle/ready/source grant.
// argv[2]: base64 JSON binding described in COUNT-PLAN.md. No keys in arguments.
import { readFileSync, readlinkSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { createHash, randomUUID } from 'node:crypto';
import { pathToFileURL } from 'node:url';

const sha = bytes => createHash('sha256').update(bytes).digest('hex');
const emit = value => process.stdout.write(JSON.stringify({ utc: new Date().toISOString(), ...value }) + '\n');
const requireThat = (ok, code) => { if (!ok) throw new Error(code); };
const hardCutoff = Date.parse('2026-09-29T15:45:00Z');
const body = { model: 'qwen3.8-27b-gpu0', messages: [{ role: 'user', content: 'Reply with OK.' }],
  reasoning_effort: 'none', tools: [], max_tokens: 64, stream: false };
const bodySha256 = sha(JSON.stringify(body));
const countBodySha256 = sha(JSON.stringify(Object.fromEntries(Object.entries(body).filter(([key]) => key !== 'stream'))));
const modules = ['codex-production.js', 'codex-qwen.js', 'codex-admission.js', 'protected-credential.js', 'errors.js'];
let timer, started, counterInvocations = 0, finished = false;
const events = [], requestId = randomUUID();
const finish = (outcome, code, extra = {}) => {
  if (finished) return;
  finished = true;
  const stages = {};
  for (const event of events) {
    const group = stages[event.step] ??= { count: 0, elapsedMs: [], outcomes: [] };
    group.count++; group.elapsedMs.push(event.elapsedMs); group.outcomes.push(event.outcome);
  }
  emit({ kind: 'result', requestId, outcome, code, counterInvocations,
    elapsedMs: started === undefined ? null : performance.now() - started,
    stages, generationRequests: 0, retries: 0, ...extra });
};
try {
  const binding = JSON.parse(Buffer.from(process.argv[2] ?? '', 'base64').toString('utf8'));
  requireThat(binding.task === 'H033-REVIEW-TIMING02' && binding.idleReadyGrant === true &&
    ['before', 'after'].includes(binding.case) && /^[a-f0-9]{64}$/.test(binding.inboxSha256), 'grant_required');
  const until = Math.min(hardCutoff, Date.parse(binding.expiresUtc));
  requireThat(Number.isFinite(until) && until - Date.now() >= 120000, 'grant_window_too_short');
  requireThat(/^[a-f0-9]{40}$/.test(binding.source) && binding.bodySha256 === bodySha256, 'binding_invalid');
  if (binding.case === 'before') requireThat(binding.source === 'c863d4984f4a75c237b6de97b7ce40b8570fca81', 'baseline_source_mismatch');
  else requireThat(binding.source !== 'c863d4984f4a75c237b6de97b7ce40b8570fca81' &&
    /^[a-f0-9]{64}$/.test(binding.beforeResultSha256), 'after_requires_successful_before');
  timer = setTimeout(() => { finish('FAIL', 'process_timeout'); process.exit(2); }, 120000);
  const mainPid = () => Number(execFileSync('systemctl', ['--user', 'show', 'ai-harness.service', '-p', 'MainPID', '--value'], { timeout: 5000 }).toString().trim());
  const pid = mainPid();
  requireThat(Number.isSafeInteger(pid) && pid > 0, 'app_not_running');
  const cwd = readlinkSync(`/proc/${pid}/cwd`);
  requireThat(cwd === binding.serverDir && cwd.includes(binding.source), 'running_source_mismatch');
  const env = Object.fromEntries(readFileSync(`/proc/${pid}/environ`, 'utf8').split('\0').filter(s => s.includes('=')).map(s => [s.slice(0, s.indexOf('=')), s.slice(s.indexOf('=') + 1)]));
  const argv = readFileSync(`/proc/${pid}/cmdline`, 'utf8').split('\0');
  const manifestRaw = readFileSync(binding.sourceManifestPath), manifest = JSON.parse(manifestRaw);
  const buildRaw = readFileSync(binding.buildReceiptPath), build = JSON.parse(buildRaw);
  requireThat(sha(buildRaw) === binding.buildReceiptSha256 && manifest.source === binding.source &&
    build.sourceHead === binding.source && manifest.buildReceiptSha256 === binding.buildReceiptSha256, 'source_build_binding_mismatch');
  const sourceHashes = {};
  for (const name of modules) {
    const key = 'ai-harness/server/src/' + name.replace(/\.js$/, '.ts');
    requireThat(/^[a-f0-9]{64}$/.test(build.sourceHashes?.[key]) && manifest.sourceHashes?.[key] === build.sourceHashes[key], 'source_receipt_mismatch');
    sourceHashes[key] = build.sourceHashes[key];
  }
  const compiledHashes = Object.fromEntries(modules.map(name => [name, sha(readFileSync(cwd + '/dist/' + name))]));
  for (const [name, digest] of Object.entries(compiledHashes)) requireThat(digest === build.files?.['server/dist/' + name], 'compiled_binding_mismatch');
  const receiptRaw = readFileSync(argv[2]);
  requireThat(sha(receiptRaw) === binding.receiptSha256, 'receipt_binding_mismatch');
  const { createProductionQwenVerifier, loadQwenReceipt } = await import(pathToFileURL(cwd + '/dist/codex-production.js').href);
  const { createCodexQwenCounter } = await import(pathToFileURL(cwd + '/dist/codex-qwen.js').href);
  const { readProtectedCredential } = await import(pathToFileURL(cwd + '/dist/protected-credential.js').href);
  const receipt = await loadQwenReceipt(argv[2]);
  const credentials = { inferenceKey: await readProtectedCredential(env.AI_HARNESS_INFERENCE_KEY_FILE),
    controlKey: await readProtectedCredential(env.AI_HARNESS_NODE_CONTROL_KEY_FILE) };
  const observer = event => {
    const safe = { step: event.step, phase: event.phase, outcome: event.outcome, reason: event.reason, elapsedMs: event.elapsedMs };
    events.push(safe); emit({ kind: 'stage', requestId, ...safe });
  };
  // Defaults retain actual transport, full identity/hardware/freshness/capacity
  // checks, endpoints, count parsing and timeout. No separate readiness sweep.
  const verify = createProductionQwenVerifier(receipt, credentials, undefined, undefined, observer);
  requireThat((typeof verify.withVerifiedLane === 'function') === (binding.case === 'after'), 'counter_revision_mismatch');
  const counter = createCodexQwenCounter(verify, observer);
  const lane = { alias: body.model, url: receipt.lanes[body.model].nativeBaseUrl };
  emit({ kind: 'binding', requestId, case: binding.case, source: binding.source,
    inboxSha256: binding.inboxSha256, buildReceiptSha256: sha(buildRaw), sourceManifestSha256: sha(manifestRaw),
    receiptSha256: sha(receiptRaw), sourceHashes, compiledHashes, bodySha256, countBodySha256,
    endpoint: new URL(lane.url.replace(/\/$/, '') + '/tokenize').pathname, body,
    beforeResultSha256: binding.beforeResultSha256 ?? null });
  requireThat(Date.now() + 90000 < until, 'grant_expired_before_count');
  started = performance.now(); counterInvocations = 1;
  const result = await counter(body, lane, credentials.inferenceKey, AbortSignal.timeout(90000), { requestId, phase: 'count' });
  const counterElapsedMs = performance.now() - started;
  requireThat(mainPid() === pid && readlinkSync(`/proc/${pid}/cwd`) === cwd &&
    sha(readFileSync(binding.sourceManifestPath)) === sha(manifestRaw) &&
    sha(readFileSync(argv[2])) === sha(receiptRaw), 'app_changed_during_count');
  for (const [name, digest] of Object.entries(compiledHashes)) requireThat(sha(readFileSync(cwd + '/dist/' + name)) === digest, 'compiled_changed_during_count');
  finish('PASS', 'ok', { counterElapsedMs, result, countPostRequests: 1 });
} catch (error) {
  // Preserve errors via safe codes only, never remote messages/config/credentials.
  const candidate = error?.code ?? error?.message;
  const code = typeof candidate === 'string' && /^[a-z][a-z0-9_]{0,79}$/.test(candidate) ? candidate : 'count_or_binding_failed';
  finish('FAIL', code, { countPostRequests: null }); process.exitCode = 1;
} finally { clearTimeout(timer); }
