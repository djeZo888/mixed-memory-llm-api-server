import test from 'node:test';
import assert from 'node:assert/strict';
import { lstatSync, mkdtempSync, readFileSync, realpathSync, rmSync, symlinkSync, writeFileSync } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { configureProfile, localConfig, MODEL, MODEL_REF, REQUEST_TIMEOUT_MS } from './configure-profile.mjs';

const fixture = {
  AI_HARNESS_GATEWAY_URL: 'http://10.0.2.2:8081/v1',
  AI_HARNESS_GATEWAY_TOKEN: 'fixture-inference-only-authorization',
  AI_HARNESS_SESSION_ID: 'fixture-session',
};

test('custom main and auxiliary selection has explicit native limits, without managed credentials', () => {
  const config = localConfig(fixture);
  assert.equal(MODEL, 'qwen3.8-27b');
  assert.equal(MODEL_REF, 'custom_provider:harness/qwen3.8-27b');
  assert.equal(config.defaultModel, MODEL_REF);
  assert.equal(config.defaultLightModel, MODEL_REF);
  assert.equal(config.custom_provider.harness.api, 'openai-completions');
  assert.deepEqual(config.custom_provider.harness.models[MODEL].limit, { context: 480000, output: 65536 });
  assert.equal(REQUEST_TIMEOUT_MS, 9_060_000);
  assert.equal(config.custom_provider.harness.options.timeout, REQUEST_TIMEOUT_MS);
  assert.deepEqual(config.custom_provider.harness.models[MODEL].modalities, { input: ['text', 'image'], output: ['text'] });
  assert.equal(config.custom_provider.harness.models[MODEL].capabilities.support_image, true);
  assert.equal(config.agentStop.maxActiveSpanMs, 0);
  assert.equal(config.minimax_api, undefined);
  assert.equal(config.beta.mcodeTools, false);
  assert.equal(config.beta.browserUseTooling, true);
  assert.equal(config.promptConfig.autoUpdate, false);
  assert.equal(config.telemetry.enabled, false);
  assert.deepEqual(config.agents.default.builtinTools, []);
  assert.equal(config.agents.default.features.delegation, true);
  // Spawn/append and browser are feature-owned, not valid base allowlist IDs.
  for (const featureTool of ['task', 'task_append', 'browser']) {
    assert.equal(config.agents.default.tools.includes(featureTool), false);
  }
});

test('CLI emits no environment-derived token, path or raw exception on success or rejection', () => {
  const profile = realpathSync(mkdtempSync(path.join(os.tmpdir(), 'h001-profile-')));
  const cli = fileURLToPath(new URL('./configure-profile.mjs', import.meta.url));
  const token = 'synthetic-private-marker-no-log';
  const base = { ...fixture, AI_HARNESS_GATEWAY_TOKEN: token, MINIMAX_DATA_DIR: profile, HOME: path.join(profile, 'home') };
  try {
    const success = spawnSync(process.execPath, [cli], { env: base, encoding: 'utf8' });
    assert.equal(success.status, 0);
    assert.equal(success.stdout, '');
    assert.equal(success.stderr, '');
    const missingPath = path.join(profile, token);
    for (const changed of [
      { AI_HARNESS_GATEWAY_URL: `http://${token}.invalid/v1` },
      { AI_HARNESS_GATEWAY_TOKEN: `${token}\n` },
      { MINIMAX_DATA_DIR: missingPath, HOME: path.join(missingPath, 'home') },
    ]) {
      const result = spawnSync(process.execPath, [cli], { env: { ...base, ...changed }, encoding: 'utf8' });
      assert.equal(result.status, 1);
      assert.equal(result.stdout, '');
      assert.equal(result.stderr, 'Engine profile rejected: invalid or unsafe profile configuration.\n');
      assert.equal(result.stderr.includes(token), false);
    }
  } finally { rmSync(profile, { recursive: true, force: true }); }
});

test('refuses another gateway, malformed token and session ID', () => {
  for (const changed of [
    { AI_HARNESS_GATEWAY_URL: 'http://10.156.100.60:30002/v1' },
    { AI_HARNESS_GATEWAY_TOKEN: 'short' },
    { AI_HARNESS_GATEWAY_TOKEN: 'fixture-token-with\nnewline' },
    { AI_HARNESS_GATEWAY_TOKEN: 'fixture-token-with\ttab' },
    { AI_HARNESS_SESSION_ID: '../escape' },
  ]) assert.throws(() => localConfig({ ...fixture, ...changed }));
  assert.doesNotThrow(() => localConfig({ ...fixture, AI_HARNESS_SESSION_ID: 'session.with-dot_1' }));
});

test('writes private config and refreshes ephemeral authorization without changing history', () => {
  const profile = realpathSync(mkdtempSync(path.join(os.tmpdir(), 'h001-profile-')));
  const env = { ...fixture, MINIMAX_DATA_DIR: profile, HOME: path.join(profile, 'home') };
  try {
    writeFileSync(path.join(profile, 'history-fixture.json'), '{"preserved":true}\n');
    configureProfile(env);
    const target = path.join(profile, 'config.yaml');
    assert.equal(lstatSync(target).mode & 0o777, 0o600);
    const first = JSON.parse(readFileSync(target, 'utf8'));
    assert.equal(first.custom_provider.harness.options.apiKey, fixture.AI_HARNESS_GATEWAY_TOKEN);
    configureProfile({ ...env, AI_HARNESS_GATEWAY_TOKEN: 'second-fixture-authorization' });
    const second = JSON.parse(readFileSync(target, 'utf8'));
    assert.equal(second.custom_provider.harness.options.apiKey, 'second-fixture-authorization');
    assert.equal(readFileSync(path.join(profile, 'history-fixture.json'), 'utf8'), '{"preserved":true}\n');
  } finally { rmSync(profile, { recursive: true, force: true }); }
});

test('rejects config symlink and a home outside the isolated profile', () => {
  const profile = realpathSync(mkdtempSync(path.join(os.tmpdir(), 'h001-profile-')));
  const env = { ...fixture, MINIMAX_DATA_DIR: profile, HOME: path.join(profile, 'home') };
  try {
    assert.throws(() => configureProfile({ ...env, HOME: '/tmp' }));
    symlinkSync('/tmp/unused-h001-target', path.join(profile, 'config.yaml'));
    assert.throws(() => configureProfile(env));
  } finally { rmSync(profile, { recursive: true, force: true }); }
});
