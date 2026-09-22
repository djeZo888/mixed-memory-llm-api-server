import { constants, closeSync, fstatSync, lstatSync, mkdirSync, mkdtempSync, openSync, readFileSync, readdirSync, realpathSync, renameSync, rmSync, unlinkSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

export const CURATED_SKILLS = Object.freeze(['technical-research', 'code-investigation', 'calculations', 'technical-testing', 'pdf']);
export const SKILLS_SOURCE = '/opt/ai-harness/skills';
export const SEARXNG_URL = 'http://10.0.2.2:8082';

export const MODEL = 'qwen3.8-27b';
export const MODEL_REF = `custom_provider:harness/${MODEL}`;
export const REQUEST_TIMEOUT_MS = 151 * 60 * 1000;
export const SHARED_SLOT_INSTRUCTIONS = 'Two shared inference slots serve all chats and agents. Delegate independent tasks when useful; excess inference requests are queued.\n';

export function localConfig(env) {
  if (env.AI_HARNESS_GATEWAY_URL !== 'http://10.0.2.2:8081/v1') {
    throw new Error('Expected the reviewed rootless gateway URL.');
  }
  const token = env.AI_HARNESS_GATEWAY_TOKEN;
  if (typeof token !== 'string' || token.length < 16 || token.length > 4096 || /[\u0000-\u001f\u007f]/u.test(token)) {
    throw new Error('Missing or invalid ephemeral gateway authorization.');
  }
  if (!/^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/u.test(env.AI_HARNESS_SESSION_ID ?? '')) {
    throw new Error('Missing or invalid harness session ID.');
  }
  return {
    defaultModel: MODEL_REF,
    defaultLightModel: MODEL_REF,
    defaultModelContextWindow: 480000,
    custom_provider: {
      harness: {
        kind: 'custom', name: 'Local Qwen gateway', enabled: true,
        api: 'openai-completions',
        options: { baseURL: env.AI_HARNESS_GATEWAY_URL, apiKey: token, timeout: REQUEST_TIMEOUT_MS },
        models: {
          [MODEL]: {
            id: MODEL, name: MODEL, enabled: true, tool_call: true,
            limit: { context: 480000, output: 65536 },
            modalities: { input: ['text', 'image'], output: ['text'] },
            capabilities: { support_image: true },
          },
        },
      },
    },
    // The container is the process boundary; retain native task/delegation tools.
    permissionMode: 'default',
    agents: { default: {
      tools: ['read', 'write', 'edit', 'bash', 'task_query', 'task_output', 'task_stop', 'grep', 'glob', 'todowrite', 'web_fetch'],
      builtinTools: [],
      skills: ['code-review'],
      features: { delegation: true, webSearch: false, mavis: false },
    } },
    // Keep the one reviewed MCP search tool directly exposed. Browser and
    // delegation capabilities remain native feature-owned tools.
    mcpToolSearch: { enabled: false },
    beta: { browserUseTooling: true, mcodeTools: false, codexOAuth: false, cuMode: false, asr: false },
    asr: { enabled: false },
    promptConfig: { autoUpdate: false },
    telemetry: { enabled: false, metrics: false, diagnostics: false },
    browser: { chromePath: '/usr/bin/chromium' },
    // Zero disables the native producer-active backstop. The server owns
    // explicit cancellation and its separate queue/active inference budgets.
    agentStop: { debounceMs: 500, maxActiveSpanMs: 0 },
    skills: { external: { enabled: false } },
  };
}

export function localMcpConfig() {
  return { mcpServers: { searxng: {
    command: 'node',
    args: ['/opt/ai-harness/tools/search/searxng-mcp.mjs'],
    // The profile MCP reader passes these strings literally; no ${VAR} expansion.
    env: { AI_HARNESS_SEARXNG_URL: SEARXNG_URL },
    timeout: 20000,
  } } };
}

function statIfPresent(target) {
  try { return lstatSync(target); }
  catch (error) { if (error.code === 'ENOENT') return null; throw error; }
}

function safeDirectory(target, owned = false) {
  const stat = lstatSync(target);
  if (!stat.isDirectory() || realpathSync(target) !== target ||
      (owned && (stat.uid !== process.getuid() || (stat.mode & 0o022) !== 0))) {
    throw new Error('Refusing an unsafe skills directory.');
  }
}

function safeRead(target, owned = false) {
  // O_NOFOLLOW closes the final-component symlink race between check and read.
  const fd = openSync(target, constants.O_RDONLY | constants.O_NOFOLLOW);
  try {
    const stat = fstatSync(fd);
    if (!stat.isFile() || stat.nlink !== 1 ||
        (owned && (stat.uid !== process.getuid() || (stat.mode & 0o022) !== 0))) {
      throw new Error('Refusing an unsafe skills file.');
    }
    return readFileSync(fd);
  } finally { closeSync(fd); }
}

function skillTree(source, destination, copy) {
  safeDirectory(source);
  safeDirectory(destination, true);
  const names = readdirSync(source).sort();
  if (!copy && JSON.stringify(readdirSync(destination).sort()) !== JSON.stringify(names)) {
    throw new Error('Existing skills do not match the reviewed image roster.');
  }
  for (const name of names) {
    const original = path.join(source, name);
    const target = path.join(destination, name);
    const stat = lstatSync(original);
    if (stat.isDirectory()) {
      if (copy) mkdirSync(target, { mode: 0o700 });
      skillTree(original, target, copy);
    } else if (stat.isFile()) {
      const content = safeRead(original);
      if (copy) writeFileSync(target, content, { mode: 0o600, flag: 'wx' });
      else if (!safeRead(target, true).equals(content)) {
        throw new Error('Existing skills differ from the reviewed image contents.');
      }
    } else throw new Error('Refusing a non-regular reviewed skills entry.');
  }
}

export function seedReviewedSkills(profile, source = SKILLS_SOURCE) {
  if (!path.isAbsolute(source)) throw new Error('Reviewed skills source must be absolute.');
  safeDirectory(source);
  const expected = [...CURATED_SKILLS, 'LICENSE-MIT.txt'].sort();
  if (JSON.stringify(readdirSync(source).sort()) !== JSON.stringify(expected)) {
    throw new Error('Packaged skills must contain exactly the reviewed roster and license.');
  }
  for (const name of CURATED_SKILLS) {
    safeDirectory(path.join(source, name));
    safeRead(path.join(source, name, 'SKILL.md'));
  }
  safeRead(path.join(source, 'LICENSE-MIT.txt'));
  const target = path.join(profile, 'skills');
  if (statIfPresent(target)) {
    skillTree(source, target, false);
    return;
  }
  // Publish only a complete private copy. Interrupted partial staging is never
  // a discoverable global skill root, and later starts validate instead of merge.
  const staging = mkdtempSync(path.join(profile, '.skills-'));
  try {
    skillTree(source, staging, true);
    if (statIfPresent(target)) throw new Error('Skills appeared during initialization.');
    renameSync(staging, target);
  } finally { rmSync(staging, { recursive: true, force: true }); }
}

function writePrivateJson(profile, name, value) {
  const target = path.join(profile, name);
  const existing = statIfPresent(target);
  if (existing && (!existing.isFile() || existing.uid !== process.getuid() || existing.nlink !== 1)) {
    throw new Error(`Refusing an unsafe ${name} target.`);
  }
  const temporary = path.join(profile, `.${name}-${process.pid}.tmp`);
  try {
    writeFileSync(temporary, `${JSON.stringify(value, null, 2)}\n`, { mode: 0o600, flag: 'wx' });
    renameSync(temporary, target);
  } finally {
    try { unlinkSync(temporary); } catch (error) { if (error.code !== 'ENOENT') throw error; }
  }
}

export function configureProfile(env, skillsSource = SKILLS_SOURCE) {
  const profile = env.MINIMAX_DATA_DIR;
  if (!profile || !path.isAbsolute(profile) || profile === '/' || realpathSync(profile) !== profile) {
    throw new Error('MINIMAX_DATA_DIR must be a canonical isolated absolute directory.');
  }
  if (env.HOME !== path.join(profile, 'home')) throw new Error('HOME must be the isolated profile/home directory.');
  const stat = lstatSync(profile);
  if (!stat.isDirectory() || stat.uid !== process.getuid()) throw new Error('Profile must be owned by the engine user.');
  const config = localConfig(env);
  mkdirSync(env.HOME, { recursive: true, mode: 0o700 });
  if (realpathSync(env.HOME) !== env.HOME) throw new Error('Profile home must not be a symlink.');
  // The pinned native GlobalInstructions reader uses dataDir/AGENTS.md, not a
  // config.yaml prompt field. Seed once and preserve later user instructions.
  const instructions = path.join(profile, 'AGENTS.md');
  try {
    const existing = lstatSync(instructions);
    if (!existing.isFile() || existing.uid !== process.getuid() || existing.nlink !== 1) {
      throw new Error('Refusing an unsafe AGENTS.md target.');
    }
  } catch (error) {
    if (error.code !== 'ENOENT') throw error;
    writeFileSync(instructions, SHARED_SLOT_INSTRUCTIONS, { mode: 0o600, flag: 'wx' });
  }
  seedReviewedSkills(profile, skillsSource);
  writePrivateJson(profile, 'mcp.json', localMcpConfig());
  // JSON is a YAML subset. Never print this ephemeral inference-only token.
  // Atomic replacement also makes every runner refresh a formerly expired token.
  writePrivateJson(profile, 'config.yaml', config);
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try { configureProfile(process.env); }
  // Filesystem errors can embed environment-derived paths. Never echo them or
  // the supplied environment: only the fixed failure category reaches logs.
  catch { process.stderr.write('Engine profile rejected: invalid or unsafe profile configuration.\n'); process.exitCode = 1; }
}
