import { createHash } from 'node:crypto';

export const sha256 = (value: string | Uint8Array) => createHash('sha256').update(value).digest('hex');
export const stableJson = (value: unknown): string => JSON.stringify(canonical(value));
function canonical(value: any): any {
  if (Array.isArray(value)) return value.map(canonical);
  if (value && typeof value === 'object') return Object.fromEntries(Object.keys(value).sort().map(k => [k, canonical(value[k])]));
  return value;
}
export const identifier = (value: unknown): value is string => typeof value === 'string' && /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,511}$/.test(value);
export function requireIdentity(value: unknown): asserts value is string {
  if (!identifier(value)) throw Error('native_identity_unavailable');
}
export interface CompactionBinding {
  nativeThreadId: string; nativeTurnId: string; actionId: string;
  beforeBytes: number; beforeSha256: string; dispatchedAt: string; settledAt: string;
  /** Exact pinned native summary prefix, supplied only after source review. */
  summaryPrefix: string;
}
/** Only a newly persisted, unambiguous compacted.message is projected. Native
 * replacement_history retains original user text and is deliberately never read.
 * A caller must independently prove terminal item evidence and owned settlement.
 */
export function extractPersistedSummary(rollout: Buffer, binding: CompactionBinding) {
  if (!Buffer.from(rollout.toString('utf8')).equals(rollout)) throw Error('rollout_invalid_utf8');
  for (const id of [binding.nativeThreadId, binding.nativeTurnId, binding.actionId]) requireIdentity(id);
  if (!Number.isSafeInteger(binding.beforeBytes) || binding.beforeBytes <= 0 || binding.beforeBytes >= rollout.length ||
      sha256(rollout.subarray(0, binding.beforeBytes)) !== binding.beforeSha256 ||
      rollout[binding.beforeBytes - 1] !== 10 || rollout.at(-1) !== 10) throw Error('rollout_prefix_or_flush_mismatch');
  const start = Date.parse(binding.dispatchedAt), end = Date.parse(binding.settledAt);
  if (!Number.isFinite(start) || !Number.isFinite(end) || start > end) throw Error('compaction_time_unavailable');
  let records: any[];
  try { records = rollout.toString('utf8').trimEnd().split('\n').map(line => JSON.parse(line)); }
  catch { throw Error('rollout_invalid_jsonl'); }
  const metas = records.filter(r => r.type === 'session_meta');
  if (metas.length !== 1 || metas[0].payload?.id !== binding.nativeThreadId) throw Error('rollout_thread_mismatch');
  const suffix: any[] = rollout.subarray(binding.beforeBytes).toString('utf8').trimEnd().split('\n').map(line => JSON.parse(line));
  const fresh = suffix.filter(r => r.type === 'compacted');
  if (fresh.length !== 1) throw Error('summary_ambiguous_or_absent');
  // Native rollback/revert changes which checkpoint survives reconstruction.
  // That selector is not qualified here; fail closed instead of projecting an
  // append that has been undone or claiming that a byte-prefix proves context.
  if (suffix.some(r => /rollback|rolled[_ -]?back|revert/i.test(String(r.type)) || /rollback|rolled[_ -]?back|revert/i.test(String(r.payload?.type)))) throw Error('rollout_revert_or_rollback_unqualified');
  const compacted = fresh[0], at = Date.parse(compacted.timestamp);
  const message = compacted.payload?.message;
  if (!Number.isFinite(at) || at < start || at > end || typeof message !== 'string' || !message.trim() ||
      Buffer.byteLength(message) > 4 * 1024 * 1024 || message.includes('\0')) throw Error('summary_empty_invalid_or_unmatched');
  if (typeof binding.summaryPrefix !== 'string' || !binding.summaryPrefix.trim()) throw Error('pinned_summary_prefix_unavailable');
  if (!message.startsWith(binding.summaryPrefix) || !message.slice(binding.summaryPrefix.length).trim()) throw Error('summary_prefix_only_or_unmatched');
  return Object.freeze({ message, contextSha256: sha256(message), rolloutSha256: sha256(rollout),
    compactedAt: compacted.timestamp, ...binding, projection: 'persisted-message-only' as const });
}

/** SOURCE-supported fields from the exact pinned audit. Installed native binary
 * support is NOT_TESTED. No fork/resume operation is used for summary isolation.
 */
export function summaryThreadParams(workspace: string, frozenPolicy: string) {
  const disabled = ['shell_tool', 'view_image', 'code_mode', 'code_mode_only', 'deferred_executor',
    'request_permissions_tool', 'token_budget', 'current_time_reminder', 'sleep_tool', 'send_message_to_user_async'];
  return { model: 'qwen3.8-27b', modelProvider: 'sova', cwd: workspace,
    approvalPolicy: 'never', sandbox: 'read-only', ephemeral: false, environments: [], baseInstructions: frozenPolicy,
    config: { 'agents.enabled': false, ...Object.fromEntries(disabled.map(k => [`features.${k}`, false])),
      'tools.experimental_request_user_input.enabled': false, 'tools.update_plan.enabled': false,
      'mcp_servers.search.enabled': false, 'mcp_servers.browser.enabled': false, 'mcp_servers.image.enabled': false,
      'memories.use_memories': false, 'memories.generate_memories': false, project_doc_max_bytes: 0 } };
}
export function summaryProbeText(summary: string, frozenPolicy: string, request: unknown) {
  if (!summary.trim() || !frozenPolicy.trim()) throw Error('empty_projection_or_policy');
  return stableJson({ policy: frozenPolicy, persistedCompactedMessage: summary, questions: request });
}
