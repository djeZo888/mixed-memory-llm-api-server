import { closeSync, constants, fsyncSync, openSync, writeSync } from 'node:fs';
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
}
export interface RequestScope {
  sessionId: string; actionId: string; runId: string; mode: 'main' | 'summary-only';
  parentNativeThreadId?: string; expiresAt: number; signal: AbortSignal;
  identity(): { nativeThreadId?: string; nativeTurnId?: string };
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
      if (!m || !Array.isArray(m.input) || !m.input.length || typeof m.instructions !== 'string' ||
          !/^[a-f0-9]{64}$/.test(m.contextSha256) || !m.userText || !identifier(scope.parentNativeThreadId)) throw Error('reviewed_compiled_manifest_missing');
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
      if (!identifier(native.nativeThreadId) || !identifier(native.nativeTurnId) ||
          raw.client_metadata?.thread_id !== native.nativeThreadId || raw.client_metadata?.turn_id !== native.nativeTurnId ||
          (raw.client_metadata.root_turn_id !== undefined && raw.client_metadata.root_turn_id !== native.nativeTurnId)) throw Error('first_request_native_identity_mismatch');
      if (scope.mode === 'summary-only') {
        const m = scope.manifest!;
        if (native.nativeThreadId === scope.parentNativeThreadId || [...this.captures.values()].some(c => c !== capture && c.scope.sessionId === scope.sessionId)) throw Error('probe_identity_or_extra_request');
        if (stableJson(body.tools) !== '[]' || stableJson(raw.tools) !== '[]' ||
            stableJson(raw.input) !== stableJson(m.input) || (raw.instructions ?? '') !== m.instructions) throw Error('summary_input_or_actual_tools_mismatch');
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
    return { requestId, sessionId: c.scope.sessionId, actionId: c.scope.actionId, runId: c.scope.runId,
      nativeThreadId: c.nativeThreadId, nativeTurnId: c.nativeTurnId,
      parentNativeThreadId: c.scope.parentNativeThreadId, contextSha256: c.scope.manifest?.contextSha256,
      firstRequestUtf8: c.raw.toString('utf8'), captureSha256: sha256(c.raw),
      normalizedRequestUtf8: c.normalized!.toString('utf8'), normalizedSha256: sha256(c.normalized!),
      capturedBy: 'host', actualTools: JSON.parse(c.normalized!.toString('utf8')).tools };
  }
}
