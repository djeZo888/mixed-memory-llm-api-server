import { closeSync, constants, fsyncSync, openSync, writeSync, readFileSync, fstatSync } from 'node:fs';
import { dirname, join } from 'node:path';
import type { GatewayOptions } from '../../../server/src/gateway.js';
import type { ProviderBoundaryCapture } from '../../../server/src/provider-diagnostics.js';
import { translateResponses } from '../../../server/src/codex-responses.js';
import { identifier, sha256, stableJson } from './projection.js';

type Counter = NonNullable<GatewayOptions['responses']>['countQwen'];
export interface ProbeManifest {
  /** Entire compiled native input, including approved frozen environment/policy.
   * Raw native fixture/installed-binary qualification must establish this later.
   */
  input: unknown[]; instructions: string; userText: string; contextSha256: string;
  /** All raw fields except input/tools; only the three explicit native-ID placeholders are supported. */
  envelope: Record<string, unknown>;
}
export interface RequestScope {
  sessionId: string; actionId: string; runId: string; mode: 'main' | 'summary-only';
  parentNativeThreadId?: string; expiresAt: number; signal: AbortSignal;
  identity(): { nativeThreadId?: string; nativeTurnId?: string; activeRunId?: string };
  manifest?: ProbeManifest;
}
interface Captured { scope: RequestScope; raw: Buffer; normalized?: Buffer; claimed: boolean; nativeThreadId?: string; nativeTurnId?: string }
function durableBytes(file: string, bytes: Buffer) {
  const fd = openSync(file, constants.O_WRONLY | constants.O_CREAT | constants.O_EXCL | constants.O_NOFOLLOW, 0o600);
  try {
    for (let offset = 0; offset < bytes.length;) { const count = writeSync(fd, bytes, offset, bytes.length - offset); if (!count) throw Error('capture_incomplete'); offset += count; }
    fsyncSync(fd);
  } finally { closeSync(fd); }
  const directory = openSync(dirname(file), constants.O_RDONLY);
  try { fsyncSync(directory); } finally { closeSync(directory); }
}

/** Diagnostics are capture only: gateway catches their exceptions. All rejection
 * happens in the awaited countQwen callback before gateway provider dispatch.
 */
export class DispatchGuard {
  private scopes = new Map<string, RequestScope>();
  private captures = new Map<string, Captured>();
  private failures = new Set<string>();
  private bytes = 0;
  constructor(private directory: string, private now: () => number = Date.now, private maxBytes = 64 * 1024 * 1024) {}
  register(scope: RequestScope) {
    if (this.scopes.has(scope.sessionId) || !identifier(scope.sessionId) || !identifier(scope.actionId) ||
        !identifier(scope.runId) || !Number.isFinite(scope.expiresAt) || scope.expiresAt <= this.now() ||
        scope.expiresAt - this.now() > 120000 || scope.signal.aborted) throw Error('scope_invalid_or_duplicate');
    if (scope.mode === 'summary-only') {
      const m = scope.manifest;
      if (!m || !m.envelope || typeof m.envelope !== 'object' || Array.isArray(m.envelope) || m.envelope.instructions !== m.instructions ||
          Object.hasOwn(m.envelope, 'input') || Object.hasOwn(m.envelope, 'tools') || !Array.isArray(m.input) || !m.input.length || typeof m.instructions !== 'string' ||
          !/^[a-f0-9]{64}$/.test(m.contextSha256) || !m.userText || !identifier(scope.parentNativeThreadId)) throw Error('reviewed_compiled_manifest_missing');
      normalizeNativeInput(m.input);
      const users = m.input.filter((x: any) => x?.role === 'user');
      if (users.length !== 1 || (users[0] as any).type !== 'message' ||
          stableJson((users[0] as any).content) !== stableJson([{ type: 'input_text', text: m.userText }]) ||
          m.input.some((x: any) => x?.type !== 'message' || !['system', 'developer', 'user'].includes(x.role) ||
            !Array.isArray(x.content) || x.content.some((c: any) => c?.type !== 'input_text' || typeof c.text !== 'string'))) throw Error('manifest_contains_history_or_nontext');
    }
    // Defensive snapshots: the controller cannot mutate a manifest after review.
    this.scopes.set(scope.sessionId, { ...scope, manifest: scope.manifest ? structuredClone(scope.manifest) : undefined });
  }
  retire(sessionId: string) { this.scopes.delete(sessionId); }
  private active(scope: RequestScope) {
    if (this.scopes.get(scope.sessionId) !== scope || scope.signal.aborted || this.now() >= scope.expiresAt || this.failures.has(scope.sessionId)) throw Error('scope_closed_expired_or_capture_failed');
  }
  capture = (event: ProviderBoundaryCapture) => {
    const scope = this.scopes.get(event.sessionId);
    if (!scope) return;
    try {
      this.active(scope);
      if (!identifier(event.requestId) || event.model !== 'qwen3.8-27b' || this.bytes + event.bytes.length > this.maxBytes) throw Error('capture_identity_or_limit');
      const current = this.captures.get(event.requestId);
      if (event.phase === 'pre_normalization') {
        if (current) throw Error('duplicate_first_request_capture');
        const raw = Buffer.from(event.bytes);
        durableBytes(join(this.directory, `${event.requestId}-pre.bin`), raw);
        this.captures.set(event.requestId, { scope, raw, claimed: false });
      } else if (event.phase === 'normalized_request') {
        if (!current?.claimed || current.scope !== scope || !current.normalized || !current.normalized.equals(event.bytes)) throw Error('normalized_capture_mismatch');
        // Already durable before counting; this compares independent actual
        // gateway dispatch serialization with the retained bytes.
      } else return; // Bulky SSE is not needed to attest the dispatch input.
      this.bytes += event.bytes.length;
    } catch { this.failures.add(event.sessionId); } // Count gate reads this failure; no diagnostic rejection claim.
  };
  wrap(counter: Counter): Counter {
    return async (body, lane, key, signal, context) => {
      const requestId = context?.requestId, capture = requestId ? this.captures.get(requestId) : undefined;
      if (!capture || capture.claimed) throw Error('request_capture_missing_or_duplicate');
      const scope = capture.scope;
      this.active(scope);
      if (signal.aborted) throw Error('dispatch_cancelled');
      const raw = JSON.parse(capture.raw.toString('utf8'));
      const native = scope.identity();
      if (scope.mode === 'main' && native.activeRunId !== scope.runId) throw Error('actual_active_run_identity_mismatch');
      if (!identifier(native.nativeThreadId) || !identifier(native.nativeTurnId) ||
          raw.client_metadata?.thread_id !== native.nativeThreadId || raw.client_metadata?.turn_id !== native.nativeTurnId ||
          (raw.client_metadata.root_turn_id !== undefined && raw.client_metadata.root_turn_id !== native.nativeTurnId)) throw Error('first_request_native_identity_mismatch');
      if (stableJson(body.tools) !== '[]' || stableJson(raw.tools) !== '[]') throw Error('stage_actual_tools_must_be_empty_before_dispatch');
      if (scope.mode === 'summary-only') {
        const m = scope.manifest!;
        if (native.nativeThreadId === scope.parentNativeThreadId || [...this.captures.values()].some(c => c !== capture && c.scope.sessionId === scope.sessionId)) throw Error('probe_identity_or_extra_request');
        if (stableJson(body.tools) !== '[]' || stableJson(raw.tools) !== '[]' ||
            stableJson(raw.input) !== stableJson(m.input) || (raw.instructions ?? '') !== m.instructions ||
            stableJson(Object.fromEntries(Object.entries(raw).filter(([k]) => !['input', 'tools'].includes(k)))) !==
            stableJson(bindReviewedEnvelope(m.envelope, native.nativeThreadId, native.nativeTurnId))) throw Error('summary_input_or_actual_tools_mismatch');
      }
      // Verify both byte captures against the real production translator, not a
      // mirror parser. Nothing is rewritten; tokenizer still brackets admission.
      const expected = { ...translateResponses(raw).body, model: lane.alias };
      if (stableJson(expected) !== stableJson(body)) throw Error('compiled_translation_mismatch');
      capture.claimed = true;
      capture.nativeThreadId = native.nativeThreadId; capture.nativeTurnId = native.nativeTurnId;
      capture.normalized = Buffer.from(JSON.stringify(body));
      durableBytes(join(this.directory, `${requestId}-normalized.bin`), capture.normalized);
      const count = await counter(body, lane, key, signal, context);
      this.active(scope);
      if (signal.aborted) throw Error('dispatch_cancelled_after_count');
      return count;
    };
  }
  receipt(sessionId: string) {
    const entries = [...this.captures.entries()].filter(([, c]) => c.scope.sessionId === sessionId);
    if (entries.length !== 1 || !entries[0][1].claimed || this.failures.has(sessionId)) throw Error('probe_capture_unavailable');
    return this.entryReceipt(entries[0]);
  }
  requests(sessionId: string) {
    if (this.failures.has(sessionId)) throw Error('request_capture_failed');
    return [...this.captures.entries()].filter(([, c]) => c.scope.sessionId === sessionId && c.claimed).map(c => this.entryReceipt(c));
  }
  private entryReceipt([requestId, c]: [string, Captured]) {
    for (const [label, expected] of [['pre', c.raw], ['normalized', c.normalized]] as const) {
      if (!expected) throw Error('actual_capture_missing');
      const fd = openSync(join(this.directory, `${requestId}-${label}.bin`), constants.O_RDONLY | constants.O_NOFOLLOW);
      try {
        const st = fstatSync(fd);
        if (!st.isFile() || st.nlink !== 1 || st.uid !== process.getuid?.() || st.size !== expected.length || !readFileSync(fd).equals(expected)) throw Error('retained_capture_replaced_or_changed');
      } finally { closeSync(fd); }
    }
    return { requestId, sessionId: c.scope.sessionId, actionId: c.scope.actionId, runId: c.scope.runId,
      nativeThreadId: c.nativeThreadId, nativeTurnId: c.nativeTurnId,
      parentNativeThreadId: c.scope.parentNativeThreadId, contextSha256: c.scope.manifest?.contextSha256,
      firstRequestUtf8: c.raw.toString('utf8'), captureSha256: sha256(c.raw),
      normalizedRequestUtf8: c.normalized!.toString('utf8'), normalizedSha256: sha256(c.normalized!),
      capturedBy: 'host', actualTools: JSON.parse(c.normalized!.toString('utf8')).tools };
  }
}

/** Identical logical contract to B; unknown carriers are rejected, never stripped. */
export function normalizeNativeInput(input: unknown): Record<string, unknown>[] {
  if (!Array.isArray(input)) throw Error('typed_native_input_required');
  return input.map((item: any) => {
    if (!item || typeof item !== 'object' || item.type !== 'message' ||
        Object.keys(item).some(k => !['type', 'id', 'role', 'content', 'phase', 'status'].includes(k)) ||
        !['system', 'developer', 'user', 'assistant'].includes(item.role) || !Array.isArray(item.content)) throw Error('unqualified_native_history');
    const text = item.content.map((p: any) => {
      if (!p || typeof p !== 'object' || Object.keys(p).some(k => !['type', 'text', 'annotations'].includes(k)) ||
          !['input_text', 'output_text'].includes(p.type) || typeof p.text !== 'string' ||
          (p.annotations !== undefined && stableJson(p.annotations) !== '[]')) throw Error('unqualified_native_text');
      return p.text;
    }).join('');
    const result: Record<string, unknown> = { role: item.role, content: text };
    for (const key of ['id', 'phase', 'status']) if (Object.hasOwn(item, key)) result[key] = item[key];
    return result;
  });
}
export function bindReviewedEnvelope(template: Record<string, unknown>, nativeThreadId: string, nativeTurnId: string) {
  const envelope: any = structuredClone(template);
  const bindings = { thread_id: ['@h040:probe-native-thread-id', nativeThreadId],
    turn_id: ['@h040:probe-native-turn-id', nativeTurnId], root_turn_id: ['@h040:probe-native-turn-id', nativeTurnId] };
  for (const [key, [placeholder, actual]] of Object.entries(bindings)) {
    if (envelope.client_metadata?.[key] === placeholder) envelope.client_metadata[key] = actual;
  }
  if (stableJson(envelope).includes('@h040:')) throw Error('unreviewed_metadata_placeholder');
  return envelope;
}
