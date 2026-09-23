#!/usr/bin/env node
/** Offline renderer -> child freeze -> provider payload regression; no turn or request.
 * Usage: node native-worker-boundary.mjs [NATIVE_BUNDLE] [DISCOVERED_CATALOG.json]
 * MAVIS_BUILTIN_AGENTS_V2_DIR selects source assets for a local offline checkout.
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { createHash } from 'node:crypto';
import { localConfig } from '../engine/configure-profile.mjs';
if (process.argv.includes('--help')) {
  console.log('Usage: node native-worker-boundary.mjs [BUNDLE=/opt/minimax/native-probes.mjs] [DISCOVERED_CATALOG.json]');
  process.exit(0);
}
let networkAttempts = 0, toolExecutions = 0;
const denyNetwork = async () => { networkAttempts++; throw Error('FORBIDDEN_NETWORK'); };
globalThis.fetch = denyNetwork;
const native = await import(pathToFileURL(resolve(process.argv[2] ?? '/opt/minimax/native-probes.mjs')));
const catalogBytes = readFileSync(process.argv[3] ?? new URL('./fixtures/native-image-mcp-catalog.json', import.meta.url));
const retained = JSON.parse(catalogBytes);
const discovered = retained.nativeMcpCatalog.map(tool => ({ ...tool, toolName: tool.name }));
const imageNames = ['image_capabilities', 'image_generate', 'image_edit'].map(name => `mcp__image__${name}`);
for (const name of imageNames) assert(discovered.some(tool => tool.nativeName === name), `missing retained schema ${name}`);
const noExecute = { execute() { toolExecutions++; throw Error('FORBIDDEN_TOOL_EXECUTION'); } };
const mcp = new native.LocalMcpService(() => '/offline/nonexistent-profile');
const sources = {
  nativeTools: native.LOCAL_BASE_TOOL_DEFS.map(def => ({ def, impl: noExecute })),
  mcpEntries: mcp.runtimeToolsFromNative(discovered).map((tool, i) => ({
    tool: { ...tool, impl: noExecute }, source: discovered[i].source, serverName: discovered[i].server,
  })),
  threadGoalTools: [], cuRuntimeAvailable: false,
};
// Pure config construction with fixture credentials; no host environment or config read.
const config = localConfig({ AI_HARNESS_GATEWAY_URL: 'http://10.0.2.2:8081/v1',
  AI_HARNESS_GATEWAY_TOKEN: 'offline-fixture-placeholder', AI_HARNESS_SESSION_ID: 'offline-fixture' });
const limits = config.custom_provider.harness.models['qwen3.8-27b'].limit;
assert.deepEqual(limits, { context: 480000, output: 65536 });
const catalog = new native.BuiltinAgentCatalog();
const model = { api: 'openai-completions', provider: 'custom_provider:harness', id: 'qwen3.8-27b',
  name: 'offline schema fixture', baseUrl: 'http://127.0.0.1:1/v1', reasoning: true, input: ['text', 'image'],
  cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 }, contextWindow: limits.context, maxTokens: limits.output };
function profileFacts(profile, selection = profile.configSelection) {
  const trustedBuiltin = native.isTrustedBuiltinCreationSource(profile.creationSource) && profile.provenance.source !== 'custom';
  return { capabilityCeiling: profile.capabilityCeiling, trustedBuiltin, surface: profile.surface,
    ...(trustedBuiltin ? { canonicalRole: profile.canonicalViewName } : {}), configSelection: selection };
}
async function providerPayload(profile, selection) {
  const assembled = native.buildLocalTurnToolCatalog({ sessionId: 'offline-fixture', sources,
    llmModel: model, modelCapabilities: { support_image: true }, agentProfile: profileFacts(profile, selection),
    config: config.mcpToolSearch, env: {} });
  const tools = native.newTools('/offline/workspace', assembled.tools, {}, { disableBuiltinFallback: true });
  let payload;
  const stream = native.streamOpenAICompletions(model, { systemPrompt: 'Offline capture.',
    messages: [{ role: 'user', content: 'Capture schemas only.', timestamp: 0 }], tools }, {
    apiKey: 'offline-placeholder', maxTokens: limits.output, fetch: denyNetwork,
    onPayload(value) { payload = value; throw Error('OFFLINE_CAPTURE_COMPLETE'); },
  });
  const result = await stream.result();
  assert(payload, 'provider payload not captured');
  assert.equal(result.stopReason, 'error');
  assert.match(result.errorMessage ?? '', /OFFLINE_CAPTURE_COMPLETE/);
  assert.equal(payload.max_completion_tokens ?? payload.max_tokens, 65536);
  for (const { function: tool } of payload.tools ?? []) {
    if (!tool.name.startsWith('mcp__')) continue;
    const original = discovered.find(item => item.nativeName === tool.name);
    assert(original, `unexpected MCP schema ${tool.name}`);
    assert.deepEqual(tool.parameters, original.inputSchema, `${tool.name}: provider schema changed`);
  }
  return { names: (payload.tools ?? []).map(tool => tool.function.name),
    schemas: (payload.tools ?? []).filter(tool => tool.function.name.startsWith('mcp__')).map(({ function: tool }) => ({
      name: tool.name, properties: Object.keys(tool.parameters.properties ?? {}),
      sha256: createHash('sha256').update(JSON.stringify(tool.parameters)).digest('hex'),
    })) };
}
async function freeze(renderProfile) {
  let coordinator;
  native.bindTaskAgentBindingCapture({ agentService: { renderProfile }, product: {
    preparation: { configBuilder: { config: () => ({ ...config, dataDir: '/offline/profile' }),
      skills: { listRuntimeSkills: async () => ({ skills: [{ name: 'image', sourceType: 2 }] }) } } },
    toolSources: { resolve: async () => sources }, turnRuntimeFacts: { snapshot: () => ({ cuModeActive: false }) },
  }, turnCapabilities: { acquire: async () => ({ release() {} }) },
  sessionSystem: { sessions: { records: { bindTaskAgentBindingCapture(value) { coordinator = value; } } } },
  options: { runtimeOwnerKind: 'tui', capabilityProfile: 'cli' },
  }, { plugin: { ready: async () => {} }, mcp: { ready: async () => {} } }, {});
  // This public recovery seam shares freezeSelectorCapabilities with new-task capture.
  return async name => (await coordinator.captureFrozenDefinition({ agentName: name,
    parent: { sessionId: 'offline-parent', workspaceDir: '/offline/workspace', appMode: 'coding' },
  })).taskAgentBinding.definition.capabilities;
}
const reports = [];
for (const scenario of [{ name: 'mavis' }, { name: 'worker' }, { name: 'explore' }, { name: 'verifier' }, { name: 'worker', custom: true }]) {
  const surface = scenario.name === 'mavis' ? 'cli' : 'task-child';
  const definition = await catalog.readDefinition(scenario.name);
  const managed = await native.buildBuiltinCanonicalBaseline({ catalog, definition });
  const { renderer, assertProfile } = rendererFor(native, catalog, scenario.name, config.agents.default, managed, scenario.custom);
  const renderProfile = input => native.renderAgentProfile(renderer, input);
  const profile = await renderProfile({ exactOwnerName: scenario.name, surface, promptProfile: 'tui', appMode: 'coding' });
  assertProfile(profile);
  const beforeFreeze = await providerPayload(profile);
  const frozen = surface === 'task-child' ? await (await freeze(renderProfile))(scenario.name) : undefined;
  const afterFreeze = frozen ? await providerPayload(profile, frozen) : beforeFreeze;
  const names = afterFreeze.names;
  if (scenario.custom) {
    assert.equal(profile.creationSource, 'manual');
    assert.deepEqual(beforeFreeze.names, ['read']); assert.deepEqual(names, ['read']);
    assert.deepEqual(frozen.mcpServers, []);
  } else if (['mavis', 'worker'].includes(scenario.name)) {
    for (const name of [...imageNames, 'mcp__searxng__searxng_search', 'skill']) {
      assert(beforeFreeze.names.includes(name), `${scenario.name}: ${name} absent BEFORE freeze`);
      assert(names.includes(name), `${scenario.name}: ${name} absent AFTER freeze`);
      if (frozen) assert(frozen.tools.includes(name), `${name} absent from frozen tools`);
    }
  } else {
    for (const tool of ['write', 'edit', 'task', 'task_append', 'ask_user', 'todowrite']) assert(!names.includes(tool));
    assert(!names.some(name => name.startsWith('mcp__')));
    assert.deepEqual(frozen.mcpServers, []);
  }
  reports.push({ role: scenario.name, source: profile.creationSource, provenance: profile.provenance.source,
    beforeFreeze: beforeFreeze.names, afterFreeze: names, mcpSchemas: afterFreeze.schemas });
}
// Minimal retained restriction projection: no owned IDs, prompt bodies or raw traces.
const oldTools = ['read', 'write', 'edit', 'bash', 'grep', 'glob', 'web_fetch', 'task_query', 'task_output', 'task_stop'];
const frozenProfile = await native.renderFrozenAgentProfile({ catalog }, {
  exactOwnerName: 'worker', surface: 'task-child', promptProfile: 'tui', capabilities: config.agents.default,
}, { definitionVersion: 2, exactOwnerName: 'worker', systemPrompt: 'Offline retained restriction.',
  capabilities: { tools: oldTools, disallowedTools: [], mcpServers: [], skills: ['image'], extensionSkills: ['image'] } });
const frozenPayload = await providerPayload(frozenProfile);
assert.deepEqual(frozenPayload.names, oldTools);
assert.equal(networkAttempts, 0); assert.equal(toolExecutions, 0);
console.log(JSON.stringify({ result: 'PASS', evidence: 'SYNTHETIC OFFLINE; not historical request payloads',
  sourceRevision: native.probeSourceRevision, agentProfileSha256: native.probeAgentProfileSha256,
  discoveredCatalogSha256: createHash('sha256').update(catalogBytes).digest('hex'),
  contextWindow: limits.context, maxOutputTokens: limits.output, networkAttempts, toolExecutions,
  limits: ['in-memory storage; production context resolver/renderer', 'injected retained discovered MCP schemas; no transport/startup',
    'captureFrozenDefinition shares new-task freeze but skips model reselection', 'provider onPayload aborts before request; browser injection omitted'],
  reports, retainedFrozen: frozenPayload.names }, null, 2));


// Storage is an in-memory fixture; identity resolution and both renderers are
// production code. In particular, a manual row named worker is not a builtin.
function rendererFor(native, catalog, role, capabilities, managed, custom = false) {
  const name = typeof role === 'string' ? role : role.name;
  if (custom) assert.equal(name, 'worker');
  const meta = {
    name, agentRole: name === 'mavis' ? 'primary' : 'worker',
    creationSource: custom ? 'manual' : 'builtin', greetingSent: false,
    createdAtMs: 0, updatedAtMs: 0,
  };
  const reads = { builtin: 0, custom: 0 };
  const repository = {
    get: async owner => owner === name ? meta : undefined,
    getBuiltinCanonicalConfig: async owner => {
      assert.equal(owner, name); reads.builtin++; return managed;
    },
    getCanonicalConfig: async owner => {
      assert.equal(owner, name); reads.custom++;
      return { name, systemPrompt: 'Offline custom selector fixture.', tools: ['read'], mcpServers: [] };
    },
    getAgentDir: () => '/offline/nonexistent-agent-directory',
  };
  const renderer = {
    repository, catalog,
    resolveContext: async input => {
      const context = await native.resolveAgentProfileRenderContext(
        { ...input, capabilities: input.capabilities ?? capabilities },
        {
          repository,
          requireMeta: async owner => { assert.equal(owner, name); return meta; },
          resolveExecutionTarget: async owner => owner,
          definitionFor: owner => catalog.readDefinition(owner),
          isBuiltin: row => native.isTrustedBuiltinCreationSource(row.creationSource),
          resolveBuiltinReadAgentNames: async owner => [owner],
        },
      );
      assert.equal(context.exactOwnerName, name);
      assert.equal(context.canonicalBuiltin, !custom);
      return context;
    },
  };
  function assertProfile(profile) {
    assert.equal(profile.exactOwnerName, name);
    assert.equal(profile.creationSource, custom ? 'manual' : 'builtin');
    assert.equal(profile.provenance.source, custom ? 'custom' : 'builtin');
    if (custom) {
      assert.deepEqual(profile.configSelection.tools, ['read']);
      assert.deepEqual(profile.configSelection.mcpServers, []);
      assert.equal(reads.builtin, 0);
      assert(reads.custom > 0, 'custom renderer must read the custom canonical source');
    } else {
      assert.equal(reads.custom, 0);
      assert(reads.builtin > 0, 'builtin renderer must read the builtin canonical source');
    }
  }
  return { renderer, assertProfile };
}
