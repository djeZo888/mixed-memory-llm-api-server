#!/usr/bin/env node
/** Inference-free native probes, run as the final image's ordinary user.
 * Usage: node native-integration.mjs [browser|roster] [BUNDLE]
 * Requires an isolated initialized MINIMAX_DATA_DIR and canonical workspace cwd.
 * browser uses an exclusively owned IPv4 loopback fixture, never a public URL.
 * roster initializes native runtime and lists skills/MCP; never starts a turn.
 */
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { readFile, readdir, realpath, lstat } from 'node:fs/promises';
import { join, resolve, relative, isAbsolute } from 'node:path';
import { pathToFileURL } from 'node:url';
import { createHash, randomUUID } from 'node:crypto';
if (process.argv.includes('--help')) {
  console.log('Usage: node native-integration.mjs [browser|roster] [BUNDLE=/opt/minimax/native-probes.mjs]');
  process.exit(0);
}
const mode = process.argv[2] ?? 'browser';
assert(['browser', 'roster'].includes(mode), 'unknown mode');
assert(process.getuid() !== 0, 'native probe must run as ordinary user');
assert(process.env.MINIMAX_DATA_DIR, 'isolated initialized MINIMAX_DATA_DIR required');
const { configureProfile } = await import('/opt/ai-harness/engine/configure-profile.mjs');
configureProfile({ ...process.env, AI_HARNESS_GATEWAY_URL: 'http://10.0.2.2:8081/v1',
  AI_HARNESS_GATEWAY_TOKEN: randomUUID(), AI_HARNESS_SESSION_ID: 'h001-native-probe' });
const dataDir = await realpath(process.env.MINIMAX_DATA_DIR);
const workspace = await realpath(process.cwd());
const native = await import(pathToFileURL(resolve(process.argv[3] ?? '/opt/minimax/native-probes.mjs')));
const timeout = setTimeout(() => { console.error('Native probe exceeded 100 second deadline'); process.exit(124); }, 100_000);
const report = { mode, uid: process.getuid(), sourceRevision: native.probeSourceRevision, generationRequests: 0 };
function strings(value) {
  if (typeof value === 'string') return value;
  if (Array.isArray(value)) return value.map(strings).join('\n');
  if (value && typeof value === 'object') return Object.values(value).map(strings).join('\n');
  return '';
}
async function chromiumArgs() {
  const results = [];
  for (const name of await readdir('/proc')) {
    if (!/^\d+$/.test(name)) continue;
    try {
      const args = (await readFile(`/proc/${name}/cmdline`, 'utf8')).split('\0').filter(Boolean);
      if (!/chromium$/.test(args[0] ?? '')) continue;
      assert(!args.includes('--no-sandbox'), 'native Chromium disabled sandbox');
      assert(!args.includes('--disable-setuid-sandbox'), 'native Chromium disabled setuid sandbox');
      results.push({ pid: Number(name), processType: args.find(x => x.startsWith('--type=')) ?? 'browser', sandboxDisablingFlags: [] });
    } catch (error) { if (error.code !== 'ENOENT' && error.code !== 'EACCES') throw error; }
  }
  assert(results.length, 'native Chromium process was not observed');
  return results;
}
async function browser() {
  const sessionId = 'h001-native-' + randomUUID();
  const provider = new native.HeadlessChromeBrowserProvider({ dataDir, chromePath: '/usr/bin/chromium' });
  const tools = native.buildLocalBrowserRuntimeTools(provider, { exposure: 'compact' });
  const browser = tools.find(tool => tool.def.name === 'browser');
  assert(browser, 'native compact browser tool absent');
  const ctx = { sessionId, turnId: 'inference-free-fixture', cwd: workspace, loadedSkills: new Set(['control-in-app-browser']) };
  // A real one-page PDF fixture; xref offsets are produced rather than guessed.
  const objects = ['<< /Type /Catalog /Pages 2 0 R >>', '<< /Type /Pages /Kids [3 0 R] /Count 1 >>', '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 200] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>', '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>'];
  const stream = 'BT /F1 14 Tf 30 120 Td (Native browser PDF fixture 42) Tj ET';
  objects.push(`<< /Length ${Buffer.byteLength(stream)} >>\nstream\n${stream}\nendstream`);
  let pdf = '%PDF-1.4\n'; const offsets = [0];
  objects.forEach((object, i) => { offsets.push(Buffer.byteLength(pdf)); pdf += `${i + 1} 0 obj\n${object}\nendobj\n`; });
  const xref = Buffer.byteLength(pdf);
  pdf += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n` + offsets.slice(1).map(n => `${String(n).padStart(10, '0')} 00000 n \n`).join('') + `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`;
  const pdfBytes = Buffer.from(pdf);
  let pdfRequests = 0;
  const server = createServer((request, response) => {
    if (request.method !== 'GET') { response.writeHead(405).end(); return; }
    if (request.url === '/fixture.pdf') {
      pdfRequests++;
      response.writeHead(200, { 'Content-Type': 'application/pdf', 'Content-Disposition': 'attachment; filename="fixture.pdf"', 'Content-Length': pdfBytes.length }); response.end(pdfBytes); return;
    }
    if (request.url !== '/') { response.writeHead(404).end(); return; }
    response.writeHead(200, { 'Content-Type': 'text/html' });
    response.end('<!doctype html><title>Native fixture</title><p id="result">pending</p><a href="/fixture.pdf" download="fixture.pdf" style="position:absolute;left:20px;top:80px;width:200px;height:40px;display:block">Download fixture</a><script>document.getElementById("result").textContent="dom-js-ok:"+(6*7)</script>');
  });
  await new Promise((yes, no) => { server.once('error', no); server.listen(0, '127.0.0.1', yes); });
  try {
    const url = `http://127.0.0.1:${server.address().port}/`;
    await provider.execute(ctx, 'navigate', { url });
    const dom = await provider.execute(ctx, 'get_dom', {});
    assert(strings(dom).includes('dom-js-ok:42'), 'native JS DOM fixture did not execute');
    report.dom = 'dom-js-ok:42';
    report.chromiumProcesses = await chromiumArgs();
    report.downloads = [];
    // Same suggested name twice must yield distinct, correctly attributed files.
    for (let i = 0; i < 2; i++) {
      const result = await browser.impl.execute(ctx, { action: 'click', input: { position: { x: 100, y: 100 } } });
      assert(!result.isError, `native compact click failed: ${strings(result)}`);
      const output = JSON.parse(result.text);
      const download = output.download ?? output.result?.download;
      assert(download?.state === 'completed', 'native compact output must observe completed download');
      const file = download.filePath;
      assert(typeof file === 'string' && !isAbsolute(file) && file.startsWith(`downloads/browser/${native.safeSessionId(sessionId)}/`), 'completed path missing or outside session boundary');
      const absolute = join(workspace, file);
      assert(!(await lstat(absolute)).isSymbolicLink(), 'download destination is a symlink');
      assert.equal(relative(workspace, await realpath(absolute)), file, 'download escapes canonical workspace');
      const bytes = await readFile(absolute);
      assert(bytes.equals(pdfBytes), 'download bytes do not match served PDF');
      report.downloads.push({ filePath: file, bytes: bytes.length, sha256: createHash('sha256').update(bytes).digest('hex') });
    }
    assert.notEqual(report.downloads[0].filePath, report.downloads[1].filePath, 'duplicate suggested names reused path');
    assert.equal(pdfRequests, 2);
    // The native tool intentionally admits only HTTP(S). Inspect Chrome's
    // internal sandbox page through the SAME provider-owned native transport,
    // without changing the tool URL policy or launching a second browser.
    // `private` is a TypeScript field at this pinned revision, not an ECMAScript
    // #private slot. Fail closed if this exact internal shape changes.
    assert(provider.browsers instanceof Map, 'pinned native browser ownership map changed');
    const ownedBrowser = await provider.browsers.get(sessionId);
    assert(ownedBrowser && typeof ownedBrowser.createPage === 'function', 'provider-owned native browser unavailable');
    const sandboxPage = await ownedBrowser.createPage('chrome://sandbox');
    let text;
    try {
      await sandboxPage.waitForReady(10_000);
      const deadline = Date.now() + 5_000;
      do {
        const sandbox = await sandboxPage.transport.evaluate('document.body?.innerText ?? ""');
        assert(typeof sandbox === 'string', 'native sandbox page did not return text');
        text = sandbox.replace(/\s+/g, ' ');
        if (text.includes('Seccomp-BPF sandbox')) break;
        await new Promise(done => setTimeout(done, 100));
      } while (Date.now() < deadline);
      report.sandboxStatusText = text;

    } finally { await sandboxPage.close(); }
    const namespace = /Layer 1 Sandbox\s+Namespace/i.test(text) && /PID namespaces\s+Yes/i.test(text) && /Network namespaces\s+Yes/i.test(text);
    const legacy = /(?:Namespace|SUID) sandbox\s+Yes/i.test(text);
    assert((namespace || legacy) && /Seccomp-BPF sandbox\s+Yes/i.test(text), 'native Chromium did not confirm sandbox layers');
    report.sandbox = { layer1: namespace ? 'Namespace' : 'Namespace/SUID', seccompBpf: true };
    report.compactBrowserTool = browser.def.name;
    report.pdfRequests = pdfRequests;
  } finally {
    await provider.dispose();
    await new Promise(resolve => server.close(resolve));
  }
  // Normal browser close must preserve the produced workspace artifact.
  for (const item of report.downloads ?? []) assert((await readFile(join(workspace, item.filePath))).equals(pdfBytes));
}
async function roster() {
  const config = await native.loadTuiRuntimeConfig(join(dataDir, 'config.yaml'), { dataDir });
  const provider = native.createTuiBrowserProvider(dataDir, config);
  assert(provider, 'native browser feature is unavailable');
  let host;
  try {
    host = await native.createEmbeddedRuntimeHost({ dataDir, defaultWorkspaceDir: workspace, appVersion: '0.5.1', configGetter: () => config, configSource: 'explicit', browserAdapter: provider, startupExecutionPolicy: 'quarantined', authContextGetter: () => undefined, promptMode: 'tui' });
    const adapter = new native.TuiRuntimeAdapter(host.cliService, { workspaceDir: workspace });
    // The inspection adapter lists registry inventory and does not apply the
    // per-agent standalone builtin whitelist. Do not mistake it for disclosure.
    const inventory = await adapter.listSkills(undefined, undefined, workspace);
    report.registryInventoryNames = (inventory.skills ?? []).map(skill => skill.name).sort();
    const capabilities = native.resolveAgentCapabilities(config.agents?.default);
    assert.deepEqual(capabilities.skills, ['code-review']);
    assert.deepEqual(capabilities.builtinTools, []);
    assert.equal(capabilities.features.webSearch, false);
    assert.equal(capabilities.features.delegation, true);
    // Resolve packaged builtin definitions, including their stricter role
    // overrides. Canonical resolution intersects selectors and feature gates;
    // the generic default/override merger would incorrectly widen these roles.
    const catalog = new native.BuiltinAgentCatalog();
    const definitions = await catalog.listDefinitions();
    assert.deepEqual(definitions.map(def => def.name).sort(), ['explore', 'mavis', 'verifier', 'worker']);
    const curated = ['technical-research', 'code-investigation', 'calculations', 'technical-testing', 'pdf'];
    report.roles = [];
    for (const definition of definitions) {
      const surface = definition.name === 'mavis' ? 'cli' : 'task-child';
      const roleCapabilities = native.applyBuiltinSubagentTaskChildCeiling({
        capabilities: native.resolveCanonicalCapabilities(capabilities, definition.capabilityOverride),
        canonicalBuiltin: true, canonicalViewName: definition.name, surface,
      });
      const expectedBuiltin = ['mavis', 'worker'].includes(definition.name) ? ['code-review'] : [];
      assert.deepEqual(roleCapabilities.skills, expectedBuiltin, `${definition.name} builtin whitelist widened`);
      assert.deepEqual(roleCapabilities.builtinTools, [], `${definition.name} Matrix tools widened`);
      assert.equal(roleCapabilities.features.webSearch, false, `${definition.name} managed search widened`);
      assert.equal(roleCapabilities.features.mavis, false, `${definition.name} mavis widened`);
      assert.equal(roleCapabilities.features.delegation, definition.name === 'mavis');
      // Same native service and builtinSkillNames selector used by
      // local-agent-config-builder.createExecutionScope -> loadPromptLayers.
      const result = await native.getSkillService().listRuntimeSkills({
        agentName: definition.name, workspaceDir: workspace,
        builtinSkillNames: roleCapabilities.skills,
      });
      const skills = (result.skills ?? []).map(skill => ({ name: skill.name, sourceKind: skill.sourceKind, locationUri: skill.locationUri }));
      const actual = new Set(skills.map(skill => skill.name));
      const expected = [...curated, ...expectedBuiltin];
      for (const name of expected) assert(actual.has(name), `${definition.name} missing native skill ${name}`);
      for (const name of actual) assert([...expected, 'control-in-app-browser'].includes(name), `${definition.name} unexpected native skill ${name}`);
      const pdfSkill = skills.find(skill => skill.name === 'pdf');
      assert(pdfSkill?.locationUri?.includes(dataDir + '/skills/pdf/'), `${definition.name} PDF skill is not curated profile copy`);
      report.roles.push({ name: definition.name, surface, capabilities: roleCapabilities, skills,
        skillSelection: { builtinSkillNames: roleCapabilities.skills, configSelectionSkills: 'absent' } });
    }
    const mainRole = report.roles.find(role => role.name === 'mavis');
    report.skills = mainRole.skills;
    report.skillSelection = mainRole.skillSelection;
    // Use native feature admission and injection without starting a model turn.
    // Image registration/compression hooks cannot execute during this probe.
    const noImageOperation = () => { throw Error('roster probe attempted image operation'); };
    const browserUse = new native.LocalBrowserUseService({ adapter: provider,
      activationMode: 'explicit-config', toolExposure: 'compact',
      readConfig: () => ({ browserUseToolingEnabled: config.beta?.browserUseTooling }),
      compressScreenshot: noImageOperation, registerGeneratedAsset: noImageOperation,
    });
    try {
      const descriptor = browserUse.builtinSkillDescriptor();
      assert.equal(descriptor?.name, 'control-in-app-browser');
      const admission = browserUse.resolveTurnCapability({
        sessionId: 'native-roster-only', turnId: 'native-roster-only',
        surface: 'cli', workspaceRoot: workspace, baseTools: [],
      });
      assert.equal(admission.controlAuthorized, true);
      assert.equal(admission.requiredSkill?.name, 'control-in-app-browser');
      assert(admission.tools.some(tool => tool.def.name === 'browser'));
      report.browserFeatureAdmission = { skill: descriptor.name,
        tools: admission.tools.map(tool => tool.def.name), controlAuthorized: true };
      // Exercise the exact pure native catalog filter with native definitions
      // and the actual browser feature tools. These throwing implementations
      // are inspection sentinels, not a claim of executing a turn or tool.
      const neverExecute = { execute() { throw Error('roster inspection attempted tool execution'); } };
      const nativeTools = native.LOCAL_BASE_TOOL_DEFS.map(def => ({ def, impl: neverExecute }));
      const entry = (name, source, serverName) => ({
        tool: { def: { name }, impl: neverExecute }, source,
        ...(serverName ? { serverName } : {}),
      });
      const mcpEntries = [
        ...[...native.AGENT_BUILTIN_MCP_TOOL_IDS, 'web_search'].map(name => entry(name, 'builtin-matrix')),
        entry('mcp__searxng__searxng_search', 'configured', 'searxng'),
      ];
      for (const role of report.roles) {
        const filtered = native.filterLocalTurnCapabilityInventory({
          sources: { nativeTools: [...nativeTools, ...admission.tools], mcpEntries,
            threadGoalTools: [], cuRuntimeAvailable: false },
          agentProfile: { capabilityCeiling: native.toCapabilityCeiling(role.capabilities),
            canonicalRole: role.name, trustedBuiltin: true, surface: role.surface },
          modelCapabilities: { support_image: true },
        });
        const toolNames = filtered.nativeTools.map(tool => tool.def.name).sort();
        assert(toolNames.includes('skill'), `${role.name} native skill loader filtered out`);
        assert(toolNames.includes('browser'), `${role.name} native browser filtered out`);
        assert(!toolNames.includes('mavis'), `${role.name} mavis unexpectedly available`);
        assert(!toolNames.includes('website_deploy'), `${role.name} publishing unexpectedly available`);
        for (const tool of ['task', 'task_append']) assert.equal(toolNames.includes(tool), role.name === 'mavis');
        assert(!filtered.mcpEntries.some(item => item.source === 'builtin-matrix'), `${role.name} Matrix tool widened`);
        const configuredMcpNames = filtered.mcpEntries.map(item => item.tool.def.name).sort();
        const expectedMcp = ['mavis', 'worker'].includes(role.name) ? ['mcp__searxng__searxng_search'] : [];
        assert.deepEqual(configuredMcpNames, expectedMcp);
        role.nativeDefinitionFilter = { toolNames, configuredMcpNames,
          evidence: 'Native pure filter executed on native base definitions, browser admission tools and non-executable MCP name sentinels; no turn or tool execution.' };
      }
    } finally { browserUse.close(); }
    const servers = await adapter.listMcpServers();
    // Retain only capability metadata; never command environments/credentials.
    report.mcp = servers.map(server => ({ name: server.name, status: server.status, tools: (server.tools ?? []).map(tool => typeof tool === 'string' ? tool : tool.name) }));
    report.nativeBrowserCapabilities = provider.getCapabilities();
    report.limits = ['Main and delegated builtin role capability resolution, native skill selectors, browser feature admission and native definition filters executed without a turn. Final assembled live per-turn tool schema roster and delegated execution remain unmeasured.', 'Pinned canonical explore/verifier policy suppresses configured SearXNG MCP; mavis/worker retain it. All four roles retain the five curated global skills.'];
  } finally {
    if (host) await host.apiHost.close();
    await provider.close();
  }
}
try {
  await (mode === 'browser' ? browser() : roster());
  console.log(JSON.stringify({ ok: true, ...report }));
} catch (error) {
  console.error(JSON.stringify({ ok: false, ...report, error: error.message }));
  process.exitCode = 1;
} finally { clearTimeout(timeout); }
