#!/usr/bin/env node
/** Bundle read-only native inspection/browser exports from the exact patched build.
 * Usage: node build-native-probes.mjs SOURCE_ROOT /opt/minimax/native-probes.mjs
 * Kept separate from release build and dependency installation for cache reuse.
 */
import { readFileSync, existsSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { resolve, join, relative } from 'node:path';
import { pathToFileURL } from 'node:url';
import { execFileSync } from 'node:child_process';
if (process.argv.includes('--help')) {
  console.log('Usage: node build-native-probes.mjs SOURCE_ROOT OUTPUT.mjs');
  process.exit(0);
}
const [rootArg, outputArg] = process.argv.slice(2);
if (!rootArg || !outputArg) throw Error('SOURCE_ROOT and OUTPUT.mjs are required');
const root = resolve(rootArg), outfile = resolve(outputArg);
const require = createRequire(join(root, 'package.json'));
const { build } = require('esbuild');
const { createTuiBundleModuleLocationConfig } = await import(pathToFileURL(join(root, 'scripts/lib/tui-npm-bundle-profile.mjs')));
const { cliExternalModules } = await import(pathToFileURL(join(root, 'scripts/lib/cli-release.mjs')));
const metadata = JSON.parse(readFileSync(join(root, 'release/extraction.json'), 'utf8'));
const packages = new Map(metadata.packageRoots.map(directory => {
  const manifest = JSON.parse(readFileSync(join(root, directory, 'package.json'), 'utf8'));
  return [manifest.name, { directory, manifest }];
}));
const sourcePlugin = { name: 'native-probe-reviewed-workspace-sources', setup(bundler) {
  bundler.onResolve({ filter: /^[^./]/ }, ({ path: specifier }) => {
    const parts = specifier.split('/');
    const name = specifier.startsWith('@') ? parts.slice(0, 2).join('/') : parts[0];
    const pkg = packages.get(name);
    if (!pkg) return;
    const subpath = specifier === name ? '.' : `.${specifier.slice(name.length)}`;
    const exported = pkg.manifest.exports?.[subpath] ?? (subpath === '.' ? pkg.manifest.exports : undefined);
    const target = (typeof exported === 'string' ? exported : exported?.types ?? exported?.import ?? exported?.default) ?? (subpath === '.' ? pkg.manifest.types : undefined);
    if (typeof target !== 'string' || !target.startsWith('./')) throw Error(`Unmapped workspace export: ${specifier}`);
    const directory = join(root, pkg.directory);
    const source = resolve(directory, target.replace(/^\.\/dist\//, './src/').replace(/\.d\.ts$/, '.ts').replace(/\.js$/, '.ts'));
    if (relative(directory, source).startsWith('..') || !existsSync(source)) throw Error(`Missing workspace source: ${specifier}`);
    return { path: source };
  });
}};
const exports = [
  ['HeadlessChromeBrowserProvider, safeSessionId, resolveHeadlessSessionLaunchOptions', 'packages/tui/src/runtime/browser/headless-chrome-provider.ts'],
  ['buildLocalBrowserRuntimeTools', 'packages/agent-tools/src/desktop/local-browser.ts'],
  ['createEmbeddedRuntimeHost', 'packages/tui/src/runtime/embedded-host.ts'],
  ['TuiRuntimeAdapter', 'packages/tui/src/runtime/adapter.ts'],
  ['loadTuiRuntimeConfig', 'packages/tui/src/headless/config.ts'],
  ['createTuiBrowserProvider', 'packages/tui/src/runtime/browser-provider.ts'],
  ['getSkillService', 'packages/local-runtime/src/skills/skill-service.ts'],
  ['resolveAgentCapabilities, AGENT_BUILTIN_MCP_TOOL_IDS', 'packages/config/src/agent-capabilities.ts'],
  ['BuiltinAgentCatalog, resolveCanonicalCapabilities', 'packages/local-runtime-v2/src/service/agent/builtin/catalog.ts'],
  ['applyBuiltinSubagentTaskChildCeiling, toCapabilityCeiling', 'packages/local-runtime-v2/src/service/agent/domain/validation.ts'],
  ['filterLocalTurnCapabilityInventory', 'packages/local-runtime-v2/src/service/turn-system/agent-host/assembly/local-turn-tool-catalog.ts'],
  ['LOCAL_BASE_TOOL_DEFS', 'packages/agent-tools/src/desktop/builtin-defs.ts'],
  ['LocalBrowserUseService', 'packages/local-runtime-v2/src/service/browser-use/browser-use.service.ts'],
];
const location = createTuiBundleModuleLocationConfig();
const patchedRevision = execFileSync('git', ['rev-parse', 'HEAD'], { cwd: root, encoding: 'utf8' }).trim();
const result = await build({
  absWorkingDir: root,
  stdin: { contents: exports.map(([names, path]) => `export { ${names} } from ${JSON.stringify('./' + path)};`).join('\n') + `\nexport const probeSourceRevision = ${JSON.stringify(patchedRevision)};`, resolveDir: root, sourcefile: 'ai-harness-native-probe-entry.mjs' },
  outfile, external: cliExternalModules, bundle: true, format: 'esm', platform: 'node', target: 'node22',
  banner: { js: location.banner }, plugins: [sourcePlugin], metafile: true,
  define: { ...location.define, __CLI_VERSION__: '"0.5.1"', __CLI_CHANNEL__: '"source"', __IS_NPM_BUILD__: 'true', __BUILD_PROFILE__: '"tui"', __TUI_BUILD_ENV__: '"prod"', __TUI_BUILD_VARIANT__: '"standard"', __TUI_NPM_DIST_TAG__: '"latest"' },
});
writeFileSync(outfile + '.metafile.json', JSON.stringify(result.metafile, null, 2) + '\n');
console.log(JSON.stringify({ output: outfile, patchedRevision, sourceInputs: Object.keys(result.metafile.inputs).length }));
