import test from 'node:test';
import assert from 'node:assert/strict';
import { cpSync, existsSync, linkSync, lstatSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, realpathSync, rmSync, symlinkSync, unlinkSync, writeFileSync } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { configureProfile, localConfig, MODEL, MODEL_REF, REQUEST_TIMEOUT_MS, SHARED_SLOT_INSTRUCTIONS, CURATED_SKILLS, SKILLS_SOURCE, SEARXNG_URL, IMAGE_TIMEOUT_MS, localMcpConfig, FRONTIER_INSTRUCTIONS, frontierAgentMarkdown } from './configure-profile.mjs';

const reviewedSource = realpathSync(existsSync(SKILLS_SOURCE) ? SKILLS_SOURCE : fileURLToPath(new URL('../../skills', import.meta.url)));
const configure = env => configureProfile(env, reviewedSource);

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
  assert.equal(config.permissionMode, 'default');
  assert.deepEqual(config.skills.external, { enabled: false });
  assert.equal(config.minimax_api, undefined);
  assert.equal(config.beta.mcodeTools, false);
  assert.equal(config.beta.browserUseTooling, true);
  assert.equal(config.promptConfig.autoUpdate, false);
  assert.equal(config.telemetry.enabled, false);
  assert.deepEqual(config.agents.default.builtinTools, []);
  assert.deepEqual(config.agents.default.skills, ['code-review']);
  assert.equal(config.agents.default.features.webSearch, false);
  assert.equal(config.agents.default.features.mavis, false);
  assert.deepEqual(config.mcpToolSearch, { enabled: false });
  assert.equal(config.configSelection, undefined);
  assert.equal(config.agents.default.features.delegation, true);
  // Native skill, spawn/append and browser are not valid base allowlist IDs.
  for (const featureTool of ['skill', 'task', 'task_append', 'browser']) {
    assert.equal(config.agents.default.tools.includes(featureTool), false);
  }
});

test('CLI emits no environment-derived token, path or raw exception on rejection', () => {
  const profile = realpathSync(mkdtempSync(path.join(os.tmpdir(), 'h001-profile-')));
  const cli = fileURLToPath(new URL('./configure-profile.mjs', import.meta.url));
  const token = 'synthetic-private-marker-no-log';
  const base = { ...fixture, AI_HARNESS_GATEWAY_TOKEN: token, MINIMAX_DATA_DIR: profile, HOME: path.join(profile, 'home') };
  try {
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
    configure(env);
    const target = path.join(profile, 'config.yaml');
    const instructions = path.join(profile, 'AGENTS.md');
    assert.equal(lstatSync(instructions).mode & 0o777, 0o600);
    assert.equal(readFileSync(instructions, 'utf8'), SHARED_SLOT_INSTRUCTIONS + FRONTIER_INSTRUCTIONS);
    writeFileSync(instructions, `${SHARED_SLOT_INSTRUCTIONS}\nPreserve this user instruction.\n`);
    assert.equal(lstatSync(target).mode & 0o777, 0o600);
    const first = JSON.parse(readFileSync(target, 'utf8'));
    assert.equal(first.custom_provider.harness.options.apiKey, fixture.AI_HARNESS_GATEWAY_TOKEN);
    configure({ ...env, AI_HARNESS_GATEWAY_TOKEN: 'second-fixture-authorization' });
    const second = JSON.parse(readFileSync(target, 'utf8'));
    assert.equal(second.custom_provider.harness.options.apiKey, 'second-fixture-authorization');
    const mcp = JSON.parse(readFileSync(path.join(profile, 'mcp.json'), 'utf8'));
    assert.equal(mcp.mcpServers.image.env.AI_HARNESS_GATEWAY_TOKEN, 'second-fixture-authorization');
    assert.equal(lstatSync(path.join(profile, 'mcp.json')).mode & 0o777, 0o600);
    assert.equal(readFileSync(instructions, 'utf8'), `${SHARED_SLOT_INSTRUCTIONS}\nPreserve this user instruction.\n\n${FRONTIER_INSTRUCTIONS}`);
    assert.equal(readFileSync(path.join(profile, 'history-fixture.json'), 'utf8'), '{"preserved":true}\n');
  } finally { rmSync(profile, { recursive: true, force: true }); }
});

test('rejects a symlink at the native global instructions path', () => {
  const profile = realpathSync(mkdtempSync(path.join(os.tmpdir(), 'h001-profile-')));
  const env = { ...fixture, MINIMAX_DATA_DIR: profile, HOME: path.join(profile, 'home') };
  try {
    symlinkSync('/tmp/unused-h001-instructions-target', path.join(profile, 'AGENTS.md'));
    assert.throws(() => configure(env), /unsafe AGENTS\.md target/u);
  } finally { rmSync(profile, { recursive: true, force: true }); }
});

test('rejects config symlink and a home outside the isolated profile', () => {
  const profile = realpathSync(mkdtempSync(path.join(os.tmpdir(), 'h001-profile-')));
  const env = { ...fixture, MINIMAX_DATA_DIR: profile, HOME: path.join(profile, 'home') };
  try {
    assert.throws(() => configure({ ...env, HOME: '/tmp' }));
    symlinkSync('/tmp/unused-h001-target', path.join(profile, 'config.yaml'));
    assert.throws(() => configure(env));
  } finally { rmSync(profile, { recursive: true, force: true }); }
});


test('profile MCP uses the literal private endpoint and direct reviewed stdio adapter', () => {
  assert.deepEqual(localMcpConfig(fixture), { mcpServers: { searxng: {
    command: 'node', args: ['/opt/ai-harness/tools/search/searxng-mcp.mjs'],
    env: { AI_HARNESS_SEARXNG_URL: 'http://10.0.2.2:8082' }, timeout: 20000,
  }, image: {
    command: 'node', args: ['/opt/ai-harness/tools/image/image-mcp.mjs'],
    env: { AI_HARNESS_GATEWAY_URL: fixture.AI_HARNESS_GATEWAY_URL, AI_HARNESS_GATEWAY_TOKEN: fixture.AI_HARNESS_GATEWAY_TOKEN },
    timeout: 3_000_000,
  } } });
  assert.equal(IMAGE_TIMEOUT_MS, 3_000_000);
  assert.equal(SEARXNG_URL, 'http://10.0.2.2:8082');
});

test('seeds exactly six skills and license, validates reuse and refreshes private MCP', () => {
  const profile = realpathSync(mkdtempSync(path.join(os.tmpdir(), 'h001-skills-')));
  const env = { ...fixture, MINIMAX_DATA_DIR: profile, HOME: path.join(profile, 'home'), AI_HARNESS_SEARXNG_URL: 'https://ignored.invalid' };
  try {
    configure(env);
    const target = path.join(profile, 'skills');
    assert.deepEqual(readdirSync(target).sort(), [...CURATED_SKILLS, 'LICENSE-MIT.txt'].sort());
    for (const name of CURATED_SKILLS) {
      assert.equal(lstatSync(path.join(target, name)).mode & 0o777, 0o700);
      assert.equal(readFileSync(path.join(target, name, 'SKILL.md'), 'utf8'), readFileSync(path.join(reviewedSource, name, 'SKILL.md'), 'utf8'));
    }
    const original = lstatSync(path.join(target, 'pdf', 'SKILL.md'));
    const mcpPath = path.join(profile, 'mcp.json');
    assert.equal(lstatSync(mcpPath).mode & 0o777, 0o600);
    assert.deepEqual(JSON.parse(readFileSync(mcpPath)), localMcpConfig(fixture));
    writeFileSync(mcpPath, '{}');
    configure(env);
    assert.deepEqual(JSON.parse(readFileSync(mcpPath)), localMcpConfig(fixture));
    assert.equal(lstatSync(path.join(target, 'pdf', 'SKILL.md')).ino, original.ino);
    assert.equal(readdirSync(profile).some(name => name.startsWith('.skills-')), false);
  } finally { rmSync(profile, { recursive: true, force: true }); }
});

test('rejects skill roots, nested links, hardlinks, extra or changed entries on reuse', () => {
  const cases = [
    (root, profile) => { rmSync(root, { recursive: true }); symlinkSync(reviewedSource, root); },
    root => { const p = path.join(root, 'pdf'); rmSync(p, { recursive: true }); symlinkSync(path.join(reviewedSource, 'pdf'), p); },
    root => { const p = path.join(root, 'pdf', 'SKILL.md'); rmSync(p); symlinkSync(path.join(reviewedSource, 'pdf', 'SKILL.md'), p); },
    (root, profile) => { const p = path.join(root, 'pdf', 'SKILL.md'); linkSync(p, path.join(profile, 'hardlinked-skill')); },
    root => mkdirSync(path.join(root, 'unreviewed')),
    root => writeFileSync(path.join(root, 'pdf', 'SKILL.md'), 'unreviewed content'),
    root => rmSync(path.join(root, 'LICENSE-MIT.txt')),
  ];
  for (const mutate of cases) {
    const profile = realpathSync(mkdtempSync(path.join(os.tmpdir(), 'h001-skills-')));
    const env = { ...fixture, MINIMAX_DATA_DIR: profile, HOME: path.join(profile, 'home') };
    try {
      configure(env);
      mutate(path.join(profile, 'skills'), profile);
      assert.throws(() => configure(env));
    } finally { rmSync(profile, { recursive: true, force: true }); }
  }
});

test('rejects MCP symlinks and hardlinks without touching their destination', () => {
  for (const kind of ['symlink', 'hardlink']) {
    const profile = realpathSync(mkdtempSync(path.join(os.tmpdir(), 'h001-mcp-')));
    const env = { ...fixture, MINIMAX_DATA_DIR: profile, HOME: path.join(profile, 'home') };
    try {
      const original = path.join(profile, 'preserved.json');
      writeFileSync(original, 'preserved');
      (kind === 'symlink' ? symlinkSync : linkSync)(original, path.join(profile, 'mcp.json'));
      assert.throws(() => configure(env), /unsafe mcp/u);
      assert.equal(readFileSync(original, 'utf8'), 'preserved');
    } finally { rmSync(profile, { recursive: true, force: true }); }
  }
});

test('rejects unexpected packaged skills before publishing a profile roster', () => {
  const profile = realpathSync(mkdtempSync(path.join(os.tmpdir(), 'h001-source-')));
  const source = path.join(profile, 'packaged-source');
  const env = { ...fixture, MINIMAX_DATA_DIR: profile, HOME: path.join(profile, 'home') };
  try {
    cpSync(reviewedSource, source, { recursive: true });
    mkdirSync(path.join(source, 'unreviewed'));
    assert.throws(() => configureProfile(env, source), /exactly the reviewed roster/u);
    assert.equal(existsSync(path.join(profile, 'skills')), false);
  } finally { rmSync(profile, { recursive: true, force: true }); }
});

test('installed CLI succeeds silently with packaged skills', { skip: !existsSync(SKILLS_SOURCE) }, () => {
  const profile = realpathSync(mkdtempSync(path.join(os.tmpdir(), 'h001-cli-')));
  const cli = fileURLToPath(new URL('./configure-profile.mjs', import.meta.url));
  try {
    const result = spawnSync(process.execPath, [cli], { env: { ...fixture, MINIMAX_DATA_DIR: profile, HOME: path.join(profile, 'home') }, encoding: 'utf8' });
    assert.equal(result.status, 0);
    assert.equal(result.stdout, '');
    assert.equal(result.stderr, '');
  } finally { rmSync(profile, { recursive: true, force: true }); }
});


test('upgrades only the exact prior reviewed skills without replacing originals or history', () => {
  const profile = realpathSync(mkdtempSync(path.join(os.tmpdir(), 'h003-skills-')));
  const env = { ...fixture, MINIMAX_DATA_DIR: profile, HOME: path.join(profile, 'home') };
  try {
    configure(env);
    const skills = path.join(profile, 'skills');
    rmSync(path.join(skills, 'image'), { recursive: true });
    const original = lstatSync(path.join(skills, 'pdf', 'SKILL.md')).ino;
    writeFileSync(path.join(profile, 'history-fixture.json'), 'preserved');
    configure(env);
    assert.equal(lstatSync(path.join(skills, 'pdf', 'SKILL.md')).ino, original);
    assert.equal(readFileSync(path.join(profile, 'history-fixture.json'), 'utf8'), 'preserved');
    assert.equal(readFileSync(path.join(skills, 'image', 'SKILL.md'), 'utf8'), readFileSync(path.join(reviewedSource, 'image', 'SKILL.md'), 'utf8'));
    rmSync(path.join(skills, 'image'), { recursive: true });
    writeFileSync(path.join(skills, 'pdf', 'SKILL.md'), 'customized');
    assert.throws(() => configure(env), /reviewed image contents/);
    assert.equal(existsSync(path.join(skills, 'image')), false);
    assert.equal(readFileSync(path.join(skills, 'pdf', 'SKILL.md'), 'utf8'), 'customized');
  } finally { rmSync(profile, { recursive: true, force: true }); }
});


test('managed frontier custom agent uses native model/limits and preserves tools/MCP inheritance', () => {
  const config = localConfig(fixture);
  assert.deepEqual(Object.keys(config.agents), ['default']);
  assert.equal(config.custom_provider.frontier.options.baseURL, 'http://10.0.2.2:8081/frontier/v1');
  assert.equal(config.custom_provider.frontier.options.timeout, REQUEST_TIMEOUT_MS);
  const markdown = frontierAgentMarkdown();
  assert.match(markdown, /model: custom_provider:frontier\/glm-5.3-flash/);
  assert.match(markdown, /disallowedTools: \[task, task_append\]/);
  assert.match(markdown, /effort: high/);
  assert.doesNotMatch(markdown, /^tools:|^mcpServers:|^skills:/m);
});

test('managed frontier seed preserves custom conflict and rejects symlink escapes', () => {
  const profile = realpathSync(mkdtempSync(path.join(os.tmpdir(), 'h008-profile-')));
  const env = { ...fixture, MINIMAX_DATA_DIR: profile, HOME: path.join(profile, 'home') };
  try {
    configure(env);
    const agent = path.join(profile, 'agents/frontier/agent.md');
    assert.equal(readFileSync(agent, 'utf8'), frontierAgentMarkdown());
    assert.equal(lstatSync(agent).mode & 0o777, 0o600);
    writeFileSync(agent, 'User-owned custom frontier.');
    assert.throws(() => configure(env), /explicit migration required/);
    assert.equal(readFileSync(agent, 'utf8'), 'User-owned custom frontier.');
    unlinkSync(agent); symlinkSync('/tmp/unused-h008-agent-target', agent);
    assert.throws(() => configure(env));
  } finally { rmSync(profile, { recursive: true, force: true }); }
});
