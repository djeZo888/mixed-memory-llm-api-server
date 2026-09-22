import test, { after } from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { copyFileSync, mkdirSync, mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { stripTypeScriptTypes } from 'node:module';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

// Offline source/behavior fixture. No package installation, model or SDK call.
// AI_HARNESS_MINIMAX_SOURCE must point at the pristine reviewed extraction.
const source = process.env.AI_HARNESS_MINIMAX_SOURCE;
assert.ok(source && path.isAbsolute(source), 'Set AI_HARNESS_MINIMAX_SOURCE to the pristine pinned source');
const deploy = fileURLToPath(new URL('../', import.meta.url));
const pins = JSON.parse(readFileSync(path.join(deploy, 'engine/pins.json'), 'utf8'));
const patch = pins.requestBudgetPatch;
const sha256 = (value) => createHash('sha256').update(value).digest('hex');
const copy = mkdtempSync(path.join(os.tmpdir(), 'h001-provider-check-'));
after(() => rmSync(copy, { recursive: true, force: true }));
for (const identity of patch.files) {
  const original = path.join(source, identity.path);
  assert.equal(sha256(readFileSync(original)), identity.originalSha256, `Pristine identity: ${identity.path}`);
  mkdirSync(path.dirname(path.join(copy, identity.path)), { recursive: true });
  copyFileSync(original, path.join(copy, identity.path));
}
const patchPath = path.join(deploy, patch.path);
assert.equal(sha256(readFileSync(patchPath)), patch.sha256);
for (const args of [['apply', '--check', patchPath], ['apply', patchPath]]) {
  const result = spawnSync('git', args, { cwd: copy, encoding: 'utf8' });
  assert.equal(result.status, 0, result.stderr);
}
const readPatched = (relative) => readFileSync(path.join(copy, relative), 'utf8');
const constant = (text, name) => {
  const match = text.match(new RegExp(`(?:export )?const ${name} = ([\\d_* ]+);`));
  assert.ok(match, `Missing numeric constant ${name}`);
  return Function(`return ${match[1]}`)();
};
const defaultsPath = 'packages/agent-core/src/pi-turn-runner/defaults.ts';
const titlePath = 'packages/local-runtime-v2/src/service/session-system/sessions/title/session-title-service.ts';
const archivePath = 'packages/local-runtime-v2/src/service/session-system/sessions/root/archived-root-title.ts';
const providerPath = 'third_party/pi-mono/packages/ai/src/providers/openai-completions.ts';
// Titles are explicitly outside this patch. Preserve upstream nonfatal bounds.
for (const relative of [titlePath, archivePath]) {
  mkdirSync(path.dirname(path.join(copy, relative)), { recursive: true });
  copyFileSync(path.join(source, relative), path.join(copy, relative));
}

test('patch applies only to main/provider sources and leaves titles byte-identical', () => {
  assert.deepEqual(patch.files.map((entry) => entry.path).sort(), [defaultsPath, providerPath].sort());
  const patchText = readFileSync(patchPath, 'utf8');
  assert.equal(patchText.includes(titlePath), false);
  assert.equal(patchText.includes(archivePath), false);
  for (const identity of patch.files) {
    assert.equal(sha256(readFileSync(path.join(copy, identity.path))), identity.patchedSha256);
    assert.equal(sha256(readFileSync(path.join(source, identity.path))), identity.originalSha256);
  }
  for (const relative of [titlePath, archivePath]) {
    assert.equal(readPatched(relative), readFileSync(path.join(source, relative), 'utf8'));
  }
});

test('main budget is 151 min and native titles retain 10000/15000 ms and narrow outputs', () => {
  assert.equal(constant(readPatched(defaultsPath), 'LLM_REQUEST_TIMEOUT_MS'), 9_060_000);
  assert.equal(constant(readPatched(titlePath), 'TITLE_TIMEOUT_MS'), 10_000);
  assert.equal(constant(readPatched(archivePath), 'ARCHIVE_TITLE_TIMEOUT_MS'), 15_000);
  assert.equal(constant(readPatched(titlePath), 'TITLE_MAX_TOKENS'), 1_000);
  assert.equal(constant(readPatched(archivePath), 'ARCHIVE_TITLE_MAX_TOKENS'), 1_024);
});

test('actual provider request-options expression covers unwrapped auxiliaries and retains cancellation/no retries', () => {
  const match = readPatched(providerPath).match(/const requestOptions = (\{[\s\S]*?\n\t\t\t\});/u);
  assert.ok(match);
  const optionsFor = Function('options', `return (${match[1]})`);
  assert.deepEqual(optionsFor(undefined), { timeout: 9_060_000, maxRetries: 0 });
  assert.deepEqual(optionsFor({ maxTokens: 1000 }), { timeout: 9_060_000, maxRetries: 0 });
  for (const timeoutMs of [10_000, 15_000]) {
    assert.equal(optionsFor({ timeoutMs }).timeout, timeoutMs);
  }
  const signal = new AbortController().signal;
  const explicit = optionsFor({ signal, timeoutMs: 9_060_001, maxRetries: 0 });
  assert.equal(explicit.signal, signal);
  assert.equal(explicit.timeout, 9_060_001);
  assert.equal(explicit.maxRetries, 0);
});

test('native titles pass original short SDK/AbortSignal bounds and preserve auxiliary outputs', async () => {
  const relative = 'packages/local-runtime-v2/src/service/session-system/sessions/title/title-model-completion.ts';
  const js = stripTypeScriptTypes(readFileSync(path.join(source, relative), 'utf8'));
  const { completeTitleModelResponse } = await import(`data:text/javascript;base64,${Buffer.from(js).toString('base64')}`);
  const originalTimeout = AbortSignal.timeout;
  const timeouts = [];
  AbortSignal.timeout = (ms) => { timeouts.push(ms); return originalTimeout(ms); };
  try {
    for (const [relativePath, timeoutName, tokensName] of [
      [titlePath, 'TITLE_TIMEOUT_MS', 'TITLE_MAX_TOKENS'],
      [archivePath, 'ARCHIVE_TITLE_TIMEOUT_MS', 'ARCHIVE_TITLE_MAX_TOKENS'],
    ]) {
      let captured;
      const native = readPatched(relativePath);
      const timeoutMs = constant(native, timeoutName);
      const maxTokens = constant(native, tokensName);
      await completeTitleModelResponse({
        buildAgentConfig: async () => ({}),
        resolveModel: async () => ({ model: { id: 'qwen3.8-27b' }, apiKey: 'synthetic-ephemeral-only' }),
        stream: (_model, _context, options) => {
          captured = options;
          return { result: async () => ({ stopReason: 'stop', content: [] }) };
        },
        nowMs: () => 0,
      }, { session: { sessionId: 'fixture' }, turnId: 'title-fixture', systemPrompt: 'fixture', userPrompt: 'fixture', timeoutMs, maxTokens });
      assert.equal(captured.timeoutMs, timeoutMs);
      assert.equal(captured.maxTokens, maxTokens);
      assert.equal(captured.signal.aborted, false);
    }
    assert.deepEqual(timeouts, [10_000, 15_000]);
  } finally { AbortSignal.timeout = originalTimeout; }
});

test('native vision schema and capability gates match profile configuration', () => {
  const modelRef = readFileSync(path.join(source, 'packages/local-runtime-v2/src/service/model-system/resolution/model-ref.ts'), 'utf8');
  assert.match(modelRef, /modalities\.includes\('image'\) \|\| modelConfig\?\.capabilities\?\.support_image === true/u);
  const catalog = readFileSync(path.join(source, 'packages/local-runtime-v2/src/service/turn-system/agent-host/assembly/local-turn-tool-catalog.ts'), 'utf8');
  assert.match(catalog, /DELEGATION_TOOL_NAMES = new Set\(\['task', 'task_append'\]\)/u);
  assert.match(catalog, /DELEGATION_TOOL_NAMES\.has\(toolName\)\) return ceiling\.features\.delegation/u);
  const browser = readFileSync(path.join(source, 'packages/tui/src/runtime/browser-provider.ts'), 'utf8');
  assert.match(browser, /config\.beta\?\.browserUseTooling !== true/u);
});
