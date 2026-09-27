import { constants, closeSync, fstatSync, lstatSync, mkdirSync, mkdtempSync, openSync, readFileSync, readdirSync, realpathSync, renameSync, rmSync, unlinkSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';

export const CURATED_SKILLS = Object.freeze(['technical-research', 'code-investigation', 'calculations', 'technical-testing', 'pdf', 'image']);
export const SKILLS_SOURCE = '/opt/ai-harness/skills';
export const SEARXNG_URL = 'http://10.0.2.2:8082';
export const IMAGE_TIMEOUT_MS = 50 * 60 * 1000;

export const FRONTIER_CONTEXT = 1048576; // H013 reviewed native PASS; deploy only with the matching ready 1M backend.
const PRIOR_FRONTIER_AGENT_SHA256 = 'ac773137a850439b9109bc22080071d46d60b8758ad9660d15981f7a7c761dfe';
export const FRONTIER_MODEL = 'glm-5.3-flash';
export const FRONTIER_INSTRUCTIONS = 'Qwen is the default coordinator and ordinary coding/agentic worker. Select task(agent_name=frontier) for deep research, multi-document analysis, hard reasoning or independent diagnosis. Exceptional stuck coding needs explicit justification and Qwen verification. Frontier shares the workspace: code changes must be foreground or explicitly disjoint ownership. Use native task ownership, cancellation and result reuse. Neither model is presumed universally superior.\n';
export const FRONTIER_SLOT_POLICY = 'Managed slot clarification: the two shared inference slots above are Qwen slots. Frontier GLM-5.3-Flash has one separate inference slot and queue. Flash model input is text-only; use browser/search/PDF text or OCR and approved image generation/edit MCP tools. Main Qwen vision is unchanged.\n';
export const MODEL = 'qwen3.8-27b';
export const MODEL_REF = `custom_provider:harness/${MODEL}`;
export const REQUEST_TIMEOUT_MS = 151 * 60 * 1000;
export const MIMO_REQUEST_TIMEOUT_MS = 511 * 60 * 1000;
export const SHARED_SLOT_INSTRUCTIONS = 'Two shared inference slots serve all chats and agents. Delegate independent tasks when useful; excess inference requests are queued.\n';

export const DEFAULT_FRONTIER_PROFILE = Object.freeze({ model: FRONTIER_MODEL, contextWindow: FRONTIER_CONTEXT, maxOutputTokens: 65536 });
// Exact managed bytes only; support is not capacity qualification or selection.
export const MIMO_MANAGED_CONTEXTS = Object.freeze([131072, 917504, 1000000, 1048576]);
export function selectedFrontierProfile(selection) {
  if (selection?.model === FRONTIER_MODEL) return DEFAULT_FRONTIER_PROFILE;
  if (selection?.model !== 'mimo-v2.6-pro-rl' || selection.mimoEnabled !== true ||
      typeof selection.mimoQualificationSha256 !== 'string' || !/^[a-f0-9]{64}$/.test(selection.mimoQualificationSha256) ||
      !Number.isSafeInteger(selection.mimoContextWindow) || selection.mimoContextWindow < 2 || selection.mimoContextWindow > 1048576 ||
      !Number.isSafeInteger(selection.mimoMaxOutputTokens) || selection.mimoMaxOutputTokens < 1 || selection.mimoMaxOutputTokens > 65536 || selection.mimoMaxOutputTokens >= selection.mimoContextWindow) throw Error('Unqualified active frontier profile');
  return Object.freeze({ model: selection.model, contextWindow: selection.mimoContextWindow, maxOutputTokens: selection.mimoMaxOutputTokens });
}
export function frontierSlotPolicy(frontier = DEFAULT_FRONTIER_PROFILE) {
  return frontier.model === FRONTIER_MODEL ? FRONTIER_SLOT_POLICY : 'Managed slot clarification: the two shared inference slots above are Qwen slots. Frontier MiMo-V2.6-Pro-RL occupies the single swappable frontier slot and queue; GLM is retained for rollback, with no concurrent GLM/MiMo capacity. MiMo input is text-only; use browser/search/PDF text or OCR and approved image generation/edit MCP tools. Main Qwen vision is unchanged.\n';
}
export function localConfig(env, frontier = DEFAULT_FRONTIER_PROFILE) {
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
      frontier: {
        kind: 'custom', name: 'Local frontier gateway', enabled: true,
        api: 'openai-completions',
        options: { baseURL: 'http://10.0.2.2:8081/frontier/v1', apiKey: token, timeout: frontier.model === 'mimo-v2.6-pro-rl' ? MIMO_REQUEST_TIMEOUT_MS : REQUEST_TIMEOUT_MS },
        models: { [frontier.model]: { id: frontier.model, name: frontier.model === FRONTIER_MODEL ? 'GLM-5.3-Flash' : 'MiMo V2.6 Pro-RL', enabled: true,
          tool_call: true, reasoning: true,
          limit: { context: frontier.contextWindow, output: frontier.maxOutputTokens },
          ...(frontier.model === FRONTIER_MODEL ? { thinking: { effortOptions: ['high'], defaultEffort: 'high' } } : {}),
          modalities: { input: ['text'], output: ['text'] },
        } },
      },
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
    // Keep the reviewed MCP search and image tools directly exposed. Browser and
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

export function localMcpConfig(env) {
  // Validate the same session bearer as text; never forward backend credentials
  // or caller/session identity to the image adapter. Native children use this
  // profile's configured MCP inventory under their existing capability ceiling.
  localConfig(env);
  return { mcpServers: { searxng: {
    command: 'node',
    args: ['/opt/ai-harness/tools/search/searxng-mcp.mjs'],
    // The profile MCP reader passes these strings literally; no ${VAR} expansion.
    env: { AI_HARNESS_SEARXNG_URL: SEARXNG_URL },
    timeout: 20000,
  }, image: {
    command: 'node',
    args: ['/opt/ai-harness/tools/image/image-mcp.mjs'],
    env: {
      AI_HARNESS_GATEWAY_URL: 'http://10.0.2.2:8081/v1',
      AI_HARNESS_GATEWAY_TOKEN: env.AI_HARNESS_GATEWAY_TOKEN,
    },
    timeout: IMAGE_TIMEOUT_MS,
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

function skillTree(source, destination, copy, omit = []) {
  safeDirectory(source);
  safeDirectory(destination, true);
  const names = readdirSync(source).filter(name => !omit.includes(name)).sort();
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
    // Upgrade only the exact prior reviewed roster. Verify every old byte and
    // ownership before adding the new skill; never replace user-modified files.
    const prior = expected.filter(name => name !== 'image');
    if (JSON.stringify(readdirSync(target).sort()) === JSON.stringify(prior)) {
      skillTree(source, target, false, ['image']);
      const staging = mkdtempSync(path.join(profile, '.skills-'));
      try {
        skillTree(path.join(source, 'image'), staging, true);
        if (statIfPresent(path.join(target, 'image'))) throw new Error('Image skill appeared during initialization.');
        renameSync(staging, path.join(target, 'image'));
      } finally { rmSync(staging, { recursive: true, force: true }); }
    }
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

export function frontierAgentMarkdown(frontier = DEFAULT_FRONTIER_PROFILE) {
  return `---
name: frontier
description: Deep research, multi-document analysis, hard reasoning and independent diagnosis; selective escalation from Qwen.
model: custom_provider:frontier/${frontier.model}
${frontier.model === FRONTIER_MODEL ? 'effort: high\n' : ''}disallowedTools: [task, task_append]
x-mavis:
  contextWindow: ${frontier.contextWindow}
  maxOutputTokens: ${frontier.maxOutputTokens}
---
${FRONTIER_INSTRUCTIONS}
Use the normal approved tools, research, browser, search, PDF, code and image capabilities. Do not delegate recursively. Report uncertainty and evidence; reuse completed results.
`;
}
function isManagedFrontierAgent(bytes) {
  if (createHash('sha256').update(bytes).digest('hex') === PRIOR_FRONTIER_AGENT_SHA256 || bytes.equals(Buffer.from(frontierAgentMarkdown()))) return true;
  // Only these explicitly reviewed generated profiles are eligible for a
  // future capacity switch/rollback. Arbitrary numeric edits are user content.
  return MIMO_MANAGED_CONTEXTS.some(contextWindow => bytes.equals(Buffer.from(
    frontierAgentMarkdown({ model: 'mimo-v2.6-pro-rl', contextWindow, maxOutputTokens: 65536 }),
  )));
}
export function seedFrontierAgent(profile, frontier = DEFAULT_FRONTIER_PROFILE) {
  safeDirectory(profile, true);
  const agents = path.join(profile, 'agents');
  if (!statIfPresent(agents)) mkdirSync(agents, { mode: 0o700 });
  safeDirectory(agents, true);
  const directory = path.join(agents, 'frontier');
  const target = path.join(directory, 'agent.md');
  const content = Buffer.from(frontierAgentMarkdown(frontier));
  if (statIfPresent(directory)) {
    safeDirectory(directory, true);
    const previous = safeRead(target, true);
    if (previous.equals(content)) return;
    // Only exact reviewed managed tuples (including the old 480K hash) qualify. Custom bytes,
    // unsafe ownership/modes, links and extra profile content are never adopted.
    if (!isManagedFrontierAgent(previous)) {
      throw new Error('Existing frontier agent differs; explicit migration required.');
    }
    const staging = mkdtempSync(path.join(agents, '.frontier-migrate-'));
    try {
      const replacement = path.join(staging, 'agent.md');
      writeFileSync(replacement, content, { mode: 0o600, flag: 'wx' });
      safeDirectory(profile, true); safeDirectory(agents, true); safeDirectory(directory, true);
      if (!safeRead(target, true).equals(previous)) throw new Error('Frontier agent changed during migration.');
      renameSync(replacement, target);
    } finally { rmSync(staging, { recursive: true, force: true }); }
    return;
  }
  const staging = mkdtempSync(path.join(agents, '.frontier-'));
  try {
    writeFileSync(path.join(staging, 'agent.md'), content, { mode: 0o600, flag: 'wx' });
    if (statIfPresent(directory)) throw new Error('Frontier agent appeared during initialization.');
    renameSync(staging, directory);
  } finally { rmSync(staging, { recursive: true, force: true }); }
}

export function configureProfile(env, skillsSource = SKILLS_SOURCE, frontier = DEFAULT_FRONTIER_PROFILE) {
  const profile = env.MINIMAX_DATA_DIR;
  if (!profile || !path.isAbsolute(profile) || profile === '/' || realpathSync(profile) !== profile) {
    throw new Error('MINIMAX_DATA_DIR must be a canonical isolated absolute directory.');
  }
  if (env.HOME !== path.join(profile, 'home')) throw new Error('HOME must be the isolated profile/home directory.');
  const stat = lstatSync(profile);
  if (!stat.isDirectory() || stat.uid !== process.getuid()) throw new Error('Profile must be owned by the engine user.');
  const config = localConfig(env, frontier);
  const slotPolicy = frontierSlotPolicy(frontier);
  mkdirSync(env.HOME, { recursive: true, mode: 0o700 });
  if (realpathSync(env.HOME) !== env.HOME) throw new Error('Profile home must not be a symlink.');
  // Reject custom frontier conflicts before changing managed global policy.
  seedFrontierAgent(profile, frontier);
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
    writeFileSync(instructions, SHARED_SLOT_INSTRUCTIONS + FRONTIER_INSTRUCTIONS + slotPolicy, { mode: 0o600, flag: 'wx' });
  }
  // Upgrade the instruction surface by appending a managed policy. Existing user
  // text stays byte-for-byte intact; a refreshed runner can discover frontier.
  const originalInstructions = safeRead(instructions, true).toString('utf8');
  // Replace only the exact managed slot paragraph; preserve surrounding user text.
  const previousInstructions = originalInstructions.replace(frontierSlotPolicy(frontier.model === FRONTIER_MODEL ? { model: 'mimo-v2.6-pro-rl' } : DEFAULT_FRONTIER_PROFILE), slotPolicy);
  const additions = [FRONTIER_INSTRUCTIONS, slotPolicy].filter(policy => !previousInstructions.includes(policy)).join('');
  if (additions || previousInstructions !== originalInstructions) {
    const staging = path.join(profile, `.AGENTS-${process.pid}.tmp`);
    try {
      writeFileSync(staging, previousInstructions + (additions ? '\n' + additions : ''), { mode: 0o600, flag: 'wx' });
      renameSync(staging, instructions);
    } finally { try { unlinkSync(staging); } catch (error) { if (error.code !== 'ENOENT') throw error; } }
  }
  seedReviewedSkills(profile, skillsSource);
  writePrivateJson(profile, 'mcp.json', localMcpConfig(env));
  // JSON is a YAML subset. Never print this ephemeral session gateway token.
  // Atomic replacement also makes every runner refresh a formerly expired token.
  writePrivateJson(profile, 'config.yaml', config);
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try { configureProfile(process.env, SKILLS_SOURCE, selectedFrontierProfile(JSON.parse(readFileSync('/opt/ai-harness/config/active-frontier.json', 'utf8')))); }
  // Filesystem errors can embed environment-derived paths. Never echo them or
  // the supplied environment: only the fixed failure category reaches logs.
  catch { process.stderr.write('Engine profile rejected: invalid or unsafe profile configuration.\n'); process.exitCode = 1; }
}
