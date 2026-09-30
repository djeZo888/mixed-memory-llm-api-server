/** Task-only wire guards. No profile, launcher, or product-source changes. */
import {createHash} from 'node:crypto';
export const INPUT = 16384, OUTPUT = 2048;
export const FLASH = 'glm-5.3-flash';
export const RETAIN_FLASH = Object.freeze(['read','write','edit','bash','grep','glob']);
export const RETAIN_QWEN = Object.freeze([...RETAIN_FLASH,'task','task_query','task_output','task_stop']);
export const sha = value => createHash('sha256').update(typeof value === 'string' || Buffer.isBuffer(value) ? value : JSON.stringify(value)).digest('hex');
function refusal(code) { const e = new Error(code); e.statusCode = 413; e.code = code; return e; }
export function capOutput(body) {
  if (!body || typeof body !== 'object' || Array.isArray(body)) throw refusal('fixture_invalid_body');
  const a = body.max_tokens, b = body.max_completion_tokens;
  if ((a !== undefined && b !== undefined && a !== b) || [a,b].some(n => n !== undefined && (!Number.isSafeInteger(n) || n < 1)))
    throw refusal('fixture_invalid_output');
  const original = a ?? b ?? 65536;
  const effective = Math.min(original, OUTPUT);
  // Both accepted spellings must be changed before frontierBody/countFrontier.
  if (a !== undefined || b === undefined) body.max_tokens = effective;
  if (b !== undefined) body.max_completion_tokens = effective;
  return {originalRequestedOutput: original, effectiveTestOutput: effective, includesReasoning: true};
}
export function assertCount(input, output) {
  if (!Number.isSafeInteger(input) || input < 0 || input > INPUT ||
      !Number.isSafeInteger(output) || output < 1 || output > OUTPUT) throw refusal('fixture_budget_exceeded');
}
export function project(body, retain) {
  const all = body.tools ?? [];
  if (!Array.isArray(all) || all.some(t => t.type !== 'function' || typeof t.function?.name !== 'string'))
    throw refusal('fixture_tool_shape');
  const names = all.map(t => t.function.name);
  if (new Set(names).size !== names.length) throw refusal('fixture_duplicate_tools');
  if (retain) body.tools = all.filter(t => retain.includes(t.function.name));
  return {retained: names.filter(n => !retain || retain.includes(n)), removed: names.filter(n => retain && !retain.includes(n)),
    originalToolsSha256: sha(all), effectiveToolsSha256: sha(body.tools ?? [])};
}
export function createGuards({record, capture, persist, getMode, resolveSession = () => null, onActive = () => {}}) {
  return {
    async preValidation(req) {
      const route = req.routeOptions.url;
      if (!['/frontier/v1/chat/completions','/v1/chat/completions'].includes(route)) return;
      const flash = route.startsWith('/frontier/');
      const original = structuredClone(req.body);
      const cap = capOutput(req.body);
      const mode = flash ? getMode() : 'qwen';
      if (flash && !['full-count-only','full-live','narrow-live'].includes(mode)) throw refusal('fixture_closed');
      const qwenTools=getMode()==='closed'?RETAIN_QWEN.filter(n=>n!=='task'):RETAIN_QWEN;
      const roster = project(req.body, flash && mode !== 'narrow-live' ? null : flash ? RETAIN_FLASH : qwenTools);
      // capture stores complete actual body only in task-private evidence, never headers/tokens.
      const metadata = {requestId: req.id, sessionId:resolveSession(req), route, mode, ...cap, ...roster,
        originalPayloadSha256: sha(original), effectivePayloadSha256: sha(req.body),
        roles: (req.body.messages ?? []).map(m => m.role)};
      capture(original, req.body, metadata);
      record({event:'pre-count', ...metadata});
    },
    onRequestState(r) {
      // Persist BEFORE a possible throw. Product catch emits rejected and releases exactly once.
      persist(r); record({event:'frontier-state', ...r});
      if (r.state === 'active') {
        assertCount(r.promptTokens, r.reservedOutput);
        if (getMode() === 'full-count-only') throw refusal('fixture_allocation_only');
        if (!['full-live','narrow-live'].includes(getMode())) throw refusal('fixture_closed');
        onActive(r);
      }
    },
  };
}
