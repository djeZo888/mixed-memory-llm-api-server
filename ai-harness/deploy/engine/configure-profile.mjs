import { lstatSync, mkdirSync, realpathSync, renameSync, unlinkSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

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
      skills: ['code-review', 'init'],
      features: { delegation: true, webSearch: false, mavis: false },
    } },
    // Native webSearch/media require managed services. Reviewed SearXNG MCP and
    // local PDF skill are separate mounts supplied by the tools task.
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

export function configureProfile(env) {
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
  const target = path.join(profile, 'config.yaml');
  try {
    const existing = lstatSync(target);
    if (!existing.isFile() || existing.uid !== process.getuid() || existing.nlink !== 1) {
      throw new Error('Refusing an unsafe config.yaml target.');
    }
  } catch (error) {
    if (error.code !== 'ENOENT') throw error;
  }
  // JSON is a YAML subset. Never print this ephemeral inference-only token.
  // Atomic replacement also makes every runner refresh a formerly expired token.
  const temporary = path.join(profile, `.config-${process.pid}.tmp`);
  try {
    writeFileSync(temporary, `${JSON.stringify(config, null, 2)}\n`, { mode: 0o600, flag: 'wx' });
    renameSync(temporary, target);
  } finally {
    try { unlinkSync(temporary); } catch (error) { if (error.code !== 'ENOENT') throw error; }
  }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try { configureProfile(process.env); }
  // Filesystem errors can embed environment-derived paths. Never echo them or
  // the supplied environment: only the fixed failure category reaches logs.
  catch { process.stderr.write('Engine profile rejected: invalid or unsafe profile configuration.\n'); process.exitCode = 1; }
}
