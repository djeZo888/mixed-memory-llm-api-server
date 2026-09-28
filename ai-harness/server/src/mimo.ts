/** MiMo protocol adapter; production candidate remains disabled. No queue, selection, URL or credentials.
 * Only the existing shared frontier owner may eventually supply transport and
 * authenticated observations. Static config and native count integers attest
 * neither loaded identity nor allocation. See the H014 qualification gates. */
import { createHash } from 'node:crypto';
import type { FrontierRequestState } from './frontier.js';

export const MIMO_MODEL = 'mimo-v2.6-pro-rl';
export const MIMO_RUNTIME = '7ac59a6e3ad851cd41af00f678effab0598ba9a8';
export const MIMO_ARTIFACT_REVISION = 'ba4eabb78b6c51ffd873ec73b9e12b0f64aced5d';
export const MIMO_ARTIFACT_MANIFEST_SHA256 = '6ac4242ac5d4df5b083b133062c78b792f1fdc7716d32c0e0000122e3263744b';
const MAX_BODY = 16 * 1024 * 1024;
const MAX_STREAM = 32 * 1024 * 1024;
const MAX_EVENT = 1024 * 1024;
type Obj = Record<string, unknown>;
export class MimoError extends Error {
  constructor(public readonly code: string, public readonly rule?: string) { super(code); }
}
function fail(code = 'mimo_invalid_request', rule?: string): never { throw new MimoError(code, rule); }
function object(v: unknown): v is Obj {
  return !!v && typeof v === 'object' && !Array.isArray(v) &&
    [Object.prototype, null].includes(Object.getPrototypeOf(v));
}
function fields(v: unknown, allowed: readonly string[], rule = "object_fields"): asserts v is Obj {
  if (!object(v) || Object.keys(v).some(k => !allowed.includes(k))) fail("mimo_invalid_request", rule);
}
function uint(v: unknown): v is number { return Number.isSafeInteger(v) && Number(v) >= 0; }
function positive(v: unknown): v is number { return uint(v) && v > 0; }
function token(v: unknown): v is string {
  return typeof v === 'string' && v.length > 0 && v.length <= 256 && !/[\x00-\x20\x7f]/.test(v);
}
function name(v: unknown): v is string {
  return typeof v === 'string' && /^[a-zA-Z0-9_-]{1,128}$/.test(v);
}
const sha = (s: string) => createHash('sha256').update(s).digest('hex');
const digest = (v: unknown): v is string => typeof v === 'string' && /^[a-f0-9]{64}$/.test(v);
/** Bounded JSON clone rejects coercion, getters, cycles, nonfinite values and
 * unsafe integer values (including nested schemas/arguments). */
function jsonCopy(value: unknown): unknown {
  let nodes = 0, bytes = 0;
  const visit = (v: unknown, depth: number): unknown => {
    if (++nodes > 100000 || depth > 32) fail('mimo_body_limit');
    if (v === null || typeof v === 'boolean') return v;
    if (typeof v === 'string') {
      bytes += Buffer.byteLength(v); if (bytes > MAX_BODY) fail('mimo_body_limit'); return v;
    }
    if (typeof v === 'number') {
      if (!Number.isFinite(v) || (Number.isInteger(v) && !Number.isSafeInteger(v))) fail();
      return v;
    }
    if (Array.isArray(v)) {
      if (v.length > 100000 || Object.keys(v).length !== v.length) fail();
      const entries = Object.getOwnPropertyDescriptors(v);
      if (Object.getOwnPropertySymbols(v).length || Object.keys(entries).length !== v.length + 1) fail();
      const out: unknown[] = [];
      for (let i = 0; i < v.length; i++) {
        const entry = entries[String(i)];
        if (!entry || !entry.enumerable || !('value' in entry)) fail();
        out.push(visit(entry.value, depth + 1));
      }
      return out;
    }
    if (!object(v) || Object.getOwnPropertySymbols(v).length) fail();
    const out: Obj = {};
    for (const [k, desc] of Object.entries(Object.getOwnPropertyDescriptors(v))) {
      if (!desc.enumerable || !('value' in desc)) fail();
      bytes += Buffer.byteLength(k); if (bytes > MAX_BODY) fail('mimo_body_limit');
      // Schema/argument keys are data, including constructor/__proto__.
      // Defining an own property avoids invoking Object.prototype setters.
      Object.defineProperty(out, k, { value: visit(desc.value, depth + 1), enumerable: true, writable: true, configurable: true });
    }
    return out;
  };
  const result = visit(value, 0);
  if (Buffer.byteLength(JSON.stringify(result)) > MAX_BODY) fail('mimo_body_limit');
  return result;
}
function freeze<T>(v: T): Readonly<T> {
  if (v && typeof v === 'object') {
    for (const child of Object.values(v)) freeze(child);
    Object.freeze(v);
  }
  return v;
}
function argsObject(value: unknown): void {
  const parsed = typeof value === 'string' ? JSON.parse(value) : value;
  if (!object(parsed)) fail('mimo_invalid_tool_arguments');
  jsonCopy(parsed);
}
export interface MimoPrepared {
  readonly body: Readonly<Obj>;
  readonly json: string;
  readonly sha256: string;
  readonly outputTokens: number;
  readonly toolNames: readonly string[];
}
const preparedSet = new WeakSet<object>();
export function prepareMimo(value: unknown): MimoPrepared {
  const b = jsonCopy(value);
  fields(b, ['model', 'messages', 'tools', 'tool_choice', 'parallel_tool_calls', 'n',
    'stream', 'stream_options', 'max_tokens', 'max_completion_tokens', 'temperature',
    'top_p', 'stop', 'reasoning_effort', 'chat_template_kwargs', 'store'], 'request_fields');
  if (b.store !== undefined && b.store !== false) fail('mimo_invalid_request', 'store_false_required');
  delete b.store;
  if (b.model !== MIMO_MODEL || !Array.isArray(b.messages) || !b.messages.length || b.messages.length > 4096) fail('mimo_invalid_request', 'model_messages');
  const pending = new Set<string>(), seen = new Set<string>();
  for (const m of b.messages) {
    fields(m, ['role', 'content', 'name', 'tool_calls', 'tool_call_id', 'reasoning_content'], 'message_fields');
    if (typeof m.role !== 'string' || !['system', 'developer', 'user', 'assistant', 'tool'].includes(m.role)) fail('mimo_invalid_request', 'message_role');
    if (m.name !== undefined && !name(m.name)) fail('mimo_invalid_request', 'message_name');
    if (m.reasoning_content !== undefined && (m.role !== 'assistant' || typeof m.reasoning_content !== 'string')) fail('mimo_invalid_request', 'assistant_reasoning_content');
    if (m.role === 'tool') {
      if (!token(m.tool_call_id) || !pending.delete(m.tool_call_id)) fail('mimo_tool_history');
    } else if (m.tool_call_id !== undefined || pending.size) fail('mimo_tool_history');
    if (m.tool_calls !== undefined) {
      if (m.role !== 'assistant' || !Array.isArray(m.tool_calls) || !m.tool_calls.length || m.tool_calls.length > 128) fail('mimo_invalid_request', 'assistant_tool_calls');
      for (const call of m.tool_calls) {
        fields(call, ['id', 'type', 'function'], 'history_call_fields'); fields(call.function, ['name', 'arguments'], 'history_function_fields');
        if (!token(call.id) || seen.has(call.id) || call.type !== 'function' || !name(call.function.name)) fail('mimo_tool_history');
        try { argsObject(call.function.arguments); } catch { fail('mimo_invalid_tool_arguments'); }
        pending.add(call.id); seen.add(call.id);
      }
    }
    if (!(typeof m.content === 'string' ||
      (m.content === null && m.role === 'assistant' && Array.isArray(m.tool_calls)) ||
      (Array.isArray(m.content) && m.content.length <= 4096 && m.content.every(p => {
        fields(p, ['type', 'text'], 'message_text_part_fields'); return p.type === 'text' && typeof p.text === 'string';
      })))) fail('mimo_invalid_request', 'message_content_shape');
  }
  if (pending.size) fail('mimo_tool_history');
  const toolNames: string[] = [];
  if (b.tools !== undefined) {
    if (!Array.isArray(b.tools) || b.tools.length > 128) fail('mimo_invalid_request', 'tools_roster');
    for (const t of b.tools) {
      fields(t, ['type', 'function'], 'tool_fields'); fields(t.function, ['name', 'description', 'parameters', 'strict'], 'tool_function_fields');
      if (t.type !== 'function' || !name(t.function.name) || toolNames.includes(t.function.name) ||
        (t.function.description !== undefined && typeof t.function.description !== 'string') ||
        (t.function.strict !== undefined && typeof t.function.strict !== 'boolean') || !object(t.function.parameters)) fail('mimo_invalid_request', 'tool_schema');
      toolNames.push(t.function.name);
    }
  }
  const a = b.max_tokens, c = b.max_completion_tokens;
  if ((a !== undefined && c !== undefined && a !== c) || !positive(a ?? c) ||
    (a !== undefined && !positive(a)) || (c !== undefined && !positive(c))) fail('mimo_output_limit');
  const output = Number(a ?? c);
  // Native int32 constraint, NOT a qualified provider ceiling.
  if (output > 2147483647) fail('mimo_output_limit');
  if (b.n !== undefined && b.n !== 1) fail('mimo_invalid_request', 'single_choice_required');
  if (b.tool_choice !== undefined && b.tool_choice !== 'auto') fail('mimo_invalid_request', 'auto_tool_choice_required');
  if (b.parallel_tool_calls !== undefined && b.parallel_tool_calls !== false) fail('mimo_invalid_request', 'serial_tool_calls_required');
  if (b.stream !== undefined && b.stream !== true) fail('mimo_invalid_request', 'stream_required');
  if (b.stream_options !== undefined) {
    fields(b.stream_options, ['include_usage'], 'stream_options_fields'); if (b.stream_options.include_usage !== true) fail('mimo_invalid_request', 'usage_required');
  }
  for (const [key, low, high] of [['temperature', 0, 2], ['top_p', 0, 1]] as const) {
    if (b[key] !== undefined && (typeof b[key] !== 'number' || b[key] < low || b[key] > high)) fail();
  }
  if (b.stop !== undefined && !(typeof b.stop === 'string' && b.stop.length > 0 && b.stop.length <= 4096) &&
    !(Array.isArray(b.stop) && b.stop.length > 0 && b.stop.length <= 16 && b.stop.every(s => typeof s === 'string' && s.length > 0 && s.length <= 4096))) fail();
  // Only explicit off is accepted as an effort value. No invented high/low mapping.
  if (b.reasoning_effort !== undefined && b.reasoning_effort !== 'none') fail('mimo_invalid_request', 'reasoning_effort_contract');
  let thinking = b.reasoning_effort !== 'none';
  if (b.chat_template_kwargs !== undefined) {
    fields(b.chat_template_kwargs, ['enable_thinking'], 'thinking_fields');
    if (typeof b.chat_template_kwargs.enable_thinking !== 'boolean' ||
      (b.reasoning_effort === 'none' && b.chat_template_kwargs.enable_thinking)) fail('mimo_invalid_request', 'thinking_conflict');
    thinking = b.chat_template_kwargs.enable_thinking;
  }
  delete b.max_completion_tokens; delete b.reasoning_effort;
  // Preserve developer and text-array input. The pinned native parser maps the
  // role and template capabilities; stored history is never rewritten here.
  Object.assign(b, { max_tokens: output, n: 1, stream: true, stream_options: { include_usage: true },
    tool_choice: 'auto', parallel_tool_calls: false, chat_template_kwargs: { enable_thinking: thinking },
    reasoning_format: 'deepseek', add_generation_prompt: true });
  // --no-prefill-assistant is a required observed runtime flag below.
  const json = JSON.stringify(b);
  if (Buffer.byteLength(json) > MAX_BODY) fail('mimo_body_limit');
  const prepared = freeze({ body: b, json, sha256: sha(json), outputTokens: output, toolNames });
  preparedSet.add(prepared); return prepared;
}

/** Trusted, root-reviewed W1 evidence input, never loaded from candidate config
 * or supplied by the request. Digest references immutable archived evidence;
 * this module cannot authenticate a receipt or attest GPU allocation itself. */
export interface MimoBackendIdentity {
  model: typeof MIMO_MODEL;
  runtimeRevision: typeof MIMO_RUNTIME;
  runtimeBuildSha256: string;
  artifactRevision: typeof MIMO_ARTIFACT_REVISION;
  artifactManifestSha256: typeof MIMO_ARTIFACT_MANIFEST_SHA256;
  loadedTensorMetadataSha256: string;
  loadedTokenizerSha256: string;
  loadedTemplateSha256: string;
  serverInstance: string;
  serverGeneration: string;
  actualSlotContext: number;
  maxOutputTokens: number;
  parallel: 1;
  contextShift: false;
  speculative: false;
  mtp: false;
  multimodal: false;
  assistantPrefill: false;
  jinja: true;
  kvUnified: boolean;
  swaFull: false;
}
export interface MimoQualification {
  qualified: true;
  evidenceSha256: string;
  identity: MimoBackendIdentity;
  checks: { artifactBytes: true; nativePrecision: true; allocation: true; reserves: true;
    templateAndTokenizer: true; textArrayRendering: true;
    admissionBound: { basis: "pinned-source-s-minus-one"; arithmeticFixtures: true; shortNativeCountUsageMatch: true };
    generationCeiling: { requestedMaxTokens: number; requestedCeilingAccepted: true; largestCompletedOutputTokens: number };
    reasoningAndTools: true; singleOwner: true };
}
export function validateMimoQualification(value: MimoQualification): MimoQualification {
  const q = jsonCopy(value) as unknown as MimoQualification;
  const i = q?.identity, c = q?.checks;
  if (q?.qualified !== true || !digest(q.evidenceSha256) || !object(i) || !object(c) ||
    ['artifactBytes', 'nativePrecision', 'allocation', 'reserves', 'templateAndTokenizer',
      'textArrayRendering', 'reasoningAndTools', 'singleOwner'].some(k => (c as unknown as Obj)[k] !== true) ||
    i.model !== MIMO_MODEL || i.runtimeRevision !== MIMO_RUNTIME || i.artifactRevision !== MIMO_ARTIFACT_REVISION ||
    i.artifactManifestSha256 !== MIMO_ARTIFACT_MANIFEST_SHA256 ||
    ['runtimeBuildSha256', 'loadedTensorMetadataSha256', 'loadedTokenizerSha256', 'loadedTemplateSha256'].some(k => !digest(i[k])) ||
    !token(i.serverInstance) || !token(i.serverGeneration) || !positive(i.actualSlotContext) || i.actualSlotContext < 2 ||
    !positive(i.maxOutputTokens) || i.maxOutputTokens > 2147483647 || i.maxOutputTokens >= i.actualSlotContext ||
    !object(c.admissionBound) || c.admissionBound.basis !== "pinned-source-s-minus-one" || c.admissionBound.arithmeticFixtures !== true || c.admissionBound.shortNativeCountUsageMatch !== true ||
    !object(c.generationCeiling) || c.generationCeiling.requestedMaxTokens !== Math.min(65536, i.maxOutputTokens) || c.generationCeiling.requestedCeilingAccepted !== true ||
    !positive(c.generationCeiling.largestCompletedOutputTokens) || c.generationCeiling.largestCompletedOutputTokens > c.generationCeiling.requestedMaxTokens ||
    i.parallel !== 1 || i.contextShift !== false || i.speculative !== false || i.mtp !== false || i.multimodal !== false ||
    i.assistantPrefill !== false || i.jinja !== true || typeof i.kvUnified !== 'boolean' || i.swaFull !== false) fail('mimo_unqualified');
  return freeze(q);
}
function identityKey(identity: MimoBackendIdentity): string {
  return JSON.stringify(Object.entries(identity).sort(([a], [b]) => a.localeCompare(b)));
}
function match(q: MimoQualification, observed: MimoBackendIdentity): void {
  if (!observed || identityKey(q.identity) !== identityKey(observed)) fail('mimo_identity_mismatch');
}
export interface MimoNativeRequest {
  readonly method: 'POST';
  readonly path: '/v1/chat/completions/input_tokens' | '/v1/chat/completions';
  readonly body: string;
  readonly signal?: AbortSignal;
}
export interface MimoCountTransport {
  /** Fresh authenticated observation under existing frontier ownership. */
  observe(signal: AbortSignal): Promise<MimoBackendIdentity>;
  /** Future fixed protected transport; never use caller URL or credentials. */
  post(request: MimoNativeRequest): Promise<Response>;
}
export interface MimoAdmission {
  readonly prepared: MimoPrepared;
  readonly qualification: MimoQualification;
  readonly promptTokens: number;
}
const admissions = new WeakSet<object>();
const dispatchedAdmissions = new WeakSet<object>();
function admitMimo(prepared: MimoPrepared, proof: MimoQualification, observed: MimoBackendIdentity, promptTokens: number): MimoAdmission {
  if (!preparedSet.has(prepared)) fail('mimo_uncanonical_body');
  const q = validateMimoQualification(proof); match(q, observed);
  const { actualSlotContext: s, maxOutputTokens: ceiling } = q.identity;
  const o = prepared.outputTokens;
  if (!uint(promptTokens) || o > ceiling || promptTokens >= s || o > s - 1 - promptTokens) fail('mimo_context_full');
  const a = freeze({ prepared, qualification: q, promptTokens }); admissions.add(a); return a;
}
function withinSignal<T>(operation: () => Promise<T>, signal: AbortSignal): Promise<T> {
  signal.throwIfAborted();
  return new Promise<T>((resolve, reject) => {
    const abort = () => reject(signal.reason);
    signal.addEventListener('abort', abort, { once: true });
    Promise.resolve().then(() => { signal.throwIfAborted(); return operation(); }).then(
      value => { signal.removeEventListener('abort', abort); resolve(value); },
      error => { signal.removeEventListener('abort', abort); reject(error); },
    );
  });
}
export async function countMimo(prepared: MimoPrepared, proof: MimoQualification, transport: MimoCountTransport, signal: AbortSignal): Promise<MimoAdmission> {
  if (!preparedSet.has(prepared)) fail('mimo_uncanonical_body');
  const q = validateMimoQualification(proof);
  if (prepared.outputTokens > q.identity.maxOutputTokens) fail('mimo_output_limit');
  const boundedSignal = AbortSignal.any([signal, AbortSignal.timeout(15000)]);
  match(q, await withinSignal(() => transport.observe(boundedSignal), boundedSignal));
  const response = await withinSignal(() => transport.post({ method: 'POST', path: '/v1/chat/completions/input_tokens', body: prepared.json, signal: boundedSignal }), boundedSignal);
  if (response.status !== 200 || !response.body) { void response.body?.cancel().catch(() => {}); fail('mimo_count_unavailable'); }
  const reader = response.body.getReader(), decoder = new TextDecoder('utf-8', { fatal: true });
  let text = '', bytes = 0;
  try {
    for (;;) {
      const r = await withinSignal(() => reader.read(), boundedSignal); if (r.done) break;
      bytes += r.value.byteLength; if (bytes > 16384) fail('mimo_count_malformed');
      text += decoder.decode(r.value, { stream: true });
    }
    text += decoder.decode();
  } finally { void reader.cancel().catch(() => {}); }
  let v: unknown; try { v = JSON.parse(text); } catch { fail('mimo_count_malformed'); }
  // The pinned endpoint returns one integer field. Require that exact JSON
  // grammar too, so duplicate keys or exponent/fraction spellings cannot hide
  // a different count behind JSON.parse's last-key-wins/coercion behavior.
  if (!/^\s*\{\s*"input_tokens"\s*:\s*(?:0|[1-9][0-9]*)\s*\}\s*$/.test(text) ||
    !object(v) || Object.keys(v).length !== 1 || !uint(v.input_tokens)) fail('mimo_count_malformed');
  match(q, await withinSignal(() => transport.observe(boundedSignal), boundedSignal));
  return admitMimo(prepared, q, q.identity, v.input_tokens);
}
export function mimoGenerationRequest(admission: MimoAdmission, observed: MimoBackendIdentity): MimoNativeRequest {
  if (!admissions.has(admission)) fail('mimo_missing_admission');
  match(admission.qualification, observed);
  if (dispatchedAdmissions.has(admission)) fail('mimo_admission_consumed');
  dispatchedAdmissions.add(admission);
  return Object.freeze({ method: 'POST', path: '/v1/chat/completions', body: admission.prepared.json });
}

export type MimoOwnerEvent = 'queued_cancel' | 'consumer_detached' | 'transport_complete' |
  'timeout' | 'active_abort' | 'early_eof' | 'native_5xx' | 'cancel_uncertain' | 'protocol_failure';
/** Policy mapping only, deliberately not connected to a second queue or ledger.
 * Even transport success cannot release the owner without future W1 settlement. */
export function mimoOwnerPolicy(event: MimoOwnerEvent): {
  state: FrontierRequestState; holdOwner: boolean; replay: false; canSwitch: false;
} {
  if (event === 'queued_cancel') return { state: 'cancelled', holdOwner: false, replay: false, canSwitch: false };
  return { state: event === 'consumer_detached' || event === 'transport_complete' ? 'active' : 'quarantined',
    holdOwner: true, replay: false, canSwitch: false };
}

export interface MimoStreamResult {
  responseId: string;
  model: typeof MIMO_MODEL;
  reasoning: string;
  content: string;
  toolCalls: ReadonlyArray<{ id: string; type: 'function'; function: { name: string; arguments: string } }>;
  finishReason: 'stop' | 'length' | 'tool_calls';
  usage: Readonly<{ prompt_tokens: number; completion_tokens: number; total_tokens: number; cached_tokens?: number }>;
  transportComplete: true;
  nativeSettled: false;
}
/** Incremental fatal-UTF8 SSE validation; no tool-call output until full drain.
 * Caller must keep draining a detached consumer under the shared owner timeout. */
export class MimoStreamValidator {
  private decoder = new TextDecoder('utf-8', { fatal: true });
  private buffer = '';
  private bytes = 0;
  private failed = false;
  private ended = false;
  private done = false;
  private responseId = '';
  private fingerprint?: string;
  private reasoning = '';
  private content = '';
  private finishReason?: MimoStreamResult['finishReason'];
  private usage?: MimoStreamResult['usage'];
  private calls = new Map<number, { id: string; type?: 'function'; name: string; arguments: string }>();
  constructor(private readonly admission: MimoAdmission, response: { status: number; contentType: string }) {
    if (!admissions.has(admission)) fail('mimo_missing_admission');
    if (response.status !== 200 || response.contentType.split(';')[0].trim().toLowerCase() !== 'text/event-stream') this.reject();
  }
  private reject(): never { this.failed = true; return fail('mimo_stream_invalid'); }
  push(bytes: Uint8Array): void {
    if (this.failed || this.ended) this.reject();
    try {
      this.bytes += bytes.byteLength; if (this.bytes > MAX_STREAM) this.reject();
      this.buffer += this.decoder.decode(bytes, { stream: true });
      this.frames();
      if (Buffer.byteLength(this.buffer) > MAX_EVENT) this.reject();
    } catch { this.reject(); }
  }
  private frames(): void {
    for (;;) {
      const boundary = /\r?\n\r?\n/.exec(this.buffer); if (!boundary) return;
      const event = this.buffer.slice(0, boundary.index);
      this.buffer = this.buffer.slice(boundary.index + boundary[0].length);
      if (Buffer.byteLength(event) > MAX_EVENT) this.reject();
      const data: string[] = [];
      for (const line of event.split(/\r?\n/)) {
        if (!line || line.startsWith(':')) continue;
        if (!line.startsWith('data:')) this.reject();
        data.push(line.slice(5).replace(/^ /, ''));
      }
      if (!data.length) continue;
      if (this.done) this.reject();
      const payload = data.join('\n');
      if (payload === '[DONE]') {
        if (!this.finishReason || !this.usage) this.reject();
        this.done = true; continue;
      }
      this.chunk(JSON.parse(payload));
    }
  }
  private chunk(v: unknown): void {
    fields(v, ['id', 'object', 'created', 'model', 'system_fingerprint', 'choices', 'usage', 'timings']);
    if ((v.created !== undefined && !uint(v.created)) ||
      (v.timings !== undefined && !object(v.timings))) this.reject();
    if (v.system_fingerprint !== undefined) {
      if (typeof v.system_fingerprint !== 'string' || v.system_fingerprint.length > 1024 ||
        (this.fingerprint !== undefined && this.fingerprint !== v.system_fingerprint)) this.reject();
      this.fingerprint = v.system_fingerprint;
    }
    if (!object(v) || v.object !== 'chat.completion.chunk' || v.model !== MIMO_MODEL ||
      !token(v.id) || !v.id.startsWith('chatcmpl-') || !Array.isArray(v.choices)) this.reject();
    if (this.responseId && this.responseId !== v.id) this.reject();
    this.responseId = v.id;
    if (this.usage) this.reject();
    if (v.choices.length === 0) {
      if (!this.finishReason || !object(v.usage)) this.reject();
      this.readUsage(v.usage); return;
    }
    if (v.choices.length !== 1 || this.finishReason || (v.usage !== undefined && v.usage !== null)) this.reject();
    const choice = v.choices[0];
    fields(choice, ['index', 'delta', 'finish_reason', 'logprobs']);
    if (choice.index !== 0 || (choice.logprobs !== undefined && choice.logprobs !== null)) this.reject();
    fields(choice.delta, ['role', 'content', 'reasoning_content', 'tool_calls']);
    const d = choice.delta;
    if (d.role !== undefined && d.role !== 'assistant') this.reject();
    for (const key of ['content', 'reasoning_content'] as const) {
      if (d[key] !== undefined && d[key] !== null && typeof d[key] !== 'string') this.reject();
    }
    this.content += (d.content as string | null | undefined) ?? '';
    this.reasoning += (d.reasoning_content as string | null | undefined) ?? '';
    if (d.tool_calls !== undefined) {
      if (!Array.isArray(d.tool_calls)) this.reject();
      for (const part of d.tool_calls) {
        fields(part, ['index', 'id', 'type', 'function']);
        // Initial policy has one non-parallel call. History may contain old batches.
        if (part.index !== 0 || (part.type !== undefined && part.type !== 'function')) this.reject();
        const call = this.calls.get(0) ?? { id: '', name: '', arguments: '' };
        if (part.id !== undefined) {
          if (!token(part.id) || (call.id && call.id !== part.id)) this.reject(); call.id = part.id;
        }
        if (part.type === 'function') call.type = 'function';
        if (part.function !== undefined) {
          fields(part.function, ['name', 'arguments']);
          for (const key of ['name', 'arguments'] as const) {
            if (part.function[key] !== undefined) {
              if (typeof part.function[key] !== 'string') this.reject(); call[key] += part.function[key];
            }
          }
        }
        this.calls.set(0, call);
      }
    }
    if (choice.finish_reason !== undefined && choice.finish_reason !== null) {
      if (typeof choice.finish_reason !== 'string' || !['stop', 'length', 'tool_calls'].includes(choice.finish_reason)) this.reject();
      this.finishReason = choice.finish_reason as MimoStreamResult['finishReason'];
    }
  }
  private readUsage(v: Obj): void {
    const p = v.prompt_tokens, c = v.completion_tokens, t = v.total_tokens;
    if (!uint(p) || !uint(c) || !uint(t) || p !== this.admission.promptTokens ||
      c > this.admission.prepared.outputTokens || c > this.admission.qualification.identity.maxOutputTokens ||
      !Number.isSafeInteger(p + c) || t !== p + c || t > this.admission.qualification.identity.actualSlotContext - 1) this.reject();
    let cached: number | undefined;
    if (v.prompt_tokens_details !== undefined) {
      if (!object(v.prompt_tokens_details) || !uint(v.prompt_tokens_details.cached_tokens) || v.prompt_tokens_details.cached_tokens > p) this.reject();
      cached = v.prompt_tokens_details.cached_tokens;
    }
    this.usage = { prompt_tokens: p, completion_tokens: c, total_tokens: t, ...(cached === undefined ? {} : { cached_tokens: cached }) };
  }
  finish(httpComplete: boolean, observed: MimoBackendIdentity): MimoStreamResult {
    if (this.failed || this.ended) this.reject();
    try {
      this.buffer += this.decoder.decode(); this.frames();
      if (!httpComplete || !this.done || this.buffer.trim() || !this.finishReason || !this.usage) this.reject();
      match(this.admission.qualification, observed);
      const toolCalls: MimoStreamResult['toolCalls'][number][] = [];
      for (const call of this.calls.values()) {
        if (!token(call.id) || call.type !== 'function' || !name(call.name) || !this.admission.prepared.toolNames.includes(call.name)) this.reject();
        argsObject(call.arguments);
        toolCalls.push({ id: call.id, type: 'function', function: { name: call.name, arguments: call.arguments } });
      }
      if ((toolCalls.length > 0) !== (this.finishReason === 'tool_calls')) this.reject();
      this.ended = true;
      return freeze({ responseId: this.responseId, model: MIMO_MODEL, reasoning: this.reasoning, content: this.content,
        toolCalls, finishReason: this.finishReason, usage: this.usage, transportComplete: true, nativeSettled: false });
    } catch { this.reject(); }
  }
}
