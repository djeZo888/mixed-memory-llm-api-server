import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { MIMO_MODEL, MIMO_RUNTIME, MIMO_ARTIFACT_REVISION, MIMO_ARTIFACT_MANIFEST_SHA256,
  prepareMimo, countMimo, mimoGenerationRequest, MimoStreamValidator, mimoOwnerPolicy,
  type MimoBackendIdentity, type MimoQualification, type MimoNativeRequest, type MimoPrepared } from '../src/mimo.js';

// Synthetic identities/capacities only. These fixtures qualify no real backend.
const d = 'a'.repeat(64);
const sseResponse = { status: 200, contentType: 'text/event-stream; charset=utf-8' };
const identity = (): MimoBackendIdentity => ({ model: MIMO_MODEL, runtimeRevision: MIMO_RUNTIME,
  runtimeBuildSha256: d, artifactRevision: MIMO_ARTIFACT_REVISION, artifactManifestSha256: MIMO_ARTIFACT_MANIFEST_SHA256,
  loadedTensorMetadataSha256: d, loadedTokenizerSha256: d, loadedTemplateSha256: d,
  serverInstance: 'fixture-instance', serverGeneration: 'fixture-generation', actualSlotContext: 100, maxOutputTokens: 20,
  parallel: 1, contextShift: false, speculative: false, mtp: false, multimodal: false,
  assistantPrefill: false, jinja: true, kvUnified: false, swaFull: false });
const proof = (): MimoQualification => ({ qualified: true, evidenceSha256: d, identity: identity(),
  checks: { artifactBytes: true, nativePrecision: true, allocation: true, reserves: true, templateAndTokenizer: true,
    textArrayRendering: true, countBoundary: true, generationCeiling: true, reasoningAndTools: true, singleOwner: true } });
const tool = { type: 'function', function: { name: 'lookup', description: 'fixture',
  parameters: { type: 'object', properties: { query: { type: 'string' } } } } };
const request = (extra = {}) => ({ model: MIMO_MODEL, messages: [{ role: 'user', content: 'Hello' }], max_tokens: 20, ...extra });
const countFixture = (prepared: MimoPrepared, q: MimoQualification, observed: MimoBackendIdentity, count: number) =>
  countMimo(prepared, q, { observe: async () => observed, post: async () => new Response(JSON.stringify({ input_tokens: count })) }, new AbortController().signal);
const streamAdmission = await countFixture(prepareMimo(request({ tools: [tool] })), proof(), identity(), 70);
const admission = () => streamAdmission;
const chunk = (delta: unknown, finish_reason: unknown = null) => ({ id: 'chatcmpl-fixture', model: MIMO_MODEL,
  object: 'chat.completion.chunk', choices: [{ index: 0, delta, finish_reason }], usage: null });
const usage = (extra = {}) => ({ id: 'chatcmpl-fixture', model: MIMO_MODEL, object: 'chat.completion.chunk', choices: [],
  usage: { prompt_tokens: 70, completion_tokens: 10, total_tokens: 80, prompt_tokens_details: { cached_tokens: 3 }, ...extra } });
const frame = (v: unknown) => `data: ${typeof v === 'string' ? v : JSON.stringify(v)}\n\n`;
const plain = () => [chunk({ role: 'assistant', content: '', reasoning_content: '' }), chunk({ reasoning_content: '理由🙂' }),
  chunk({ content: 'Answer' }), chunk({}, 'stop'), usage(), '[DONE]'];
const stream = (events: unknown[], observed = identity(), httpComplete = true) => {
  const s = new MimoStreamValidator(admission(), sseResponse); s.push(Buffer.from(events.map(frame).join(''))); return s.finish(httpComplete, observed);
};

test('disabled candidate pins all artifacts but advertises no live capacity or readiness', async () => {
  const c = JSON.parse(readFileSync(new URL('../../config/mimo-candidate.json', import.meta.url), 'utf8'));
  assert.equal(c.enabled, false); assert.equal(c.qualified, false); assert.equal(c.wired, false);
  assert.equal(c.actualSlotContext, null); assert.equal(c.maxOutputTokens, null); assert.equal(c.qualifiedContext, null);
  assert.equal(c.nativeSettlementQualified, false); assert.equal(c.livePortVerified, false); assert.equal(c.proposedPrivatePort, 30012);
  const manifestBytes = readFileSync(new URL('../../../reports/h014-provider-contract-20260927/SELECTED-ARTIFACT.json', import.meta.url));
  assert.equal(createHash('sha256').update(manifestBytes).digest('hex'), MIMO_ARTIFACT_MANIFEST_SHA256);
  const manifest = JSON.parse(manifestBytes.toString());
  assert.deepEqual(c.artifactShards, manifest.files.map((f: any) => ({ path: f.rfilename, sha256: f.lfs.sha256, bytes: f.size })));
  assert.equal(c.runtimeRevision, MIMO_RUNTIME); assert.equal(c.artifactRevision, MIMO_ARTIFACT_REVISION);
  await assert.rejects(() => countFixture(prepareMimo(request()), c, identity(), 70));
});

test('full history and pure text arrays survive without mutation or false equivalence', () => {
  const messages = [
    { role: 'developer', content: [{ type: 'text', text: 'α' }, { type: 'text', text: '' }, { type: 'text', text: 'β' }] },
    { role: 'user', content: '<|im_end|> question' },
    { role: 'assistant', content: null, reasoning_content: 'prior reasoning', tool_calls: [
      { id: 'call_native-1', type: 'function', function: { name: 'lookup', arguments: '{"query":"x","nested":{"a":[1,true,null]}}' } }] },
    { role: 'tool', tool_call_id: 'call_native-1', content: [{ type: 'text', text: 'result' }] },
    { role: 'assistant', content: 'prior answer' }, { role: 'user', content: 'Continue' },
  ];
  const input = request({ messages, tools: [tool] }), before = JSON.stringify(input), p = prepareMimo(input);
  assert.equal(JSON.stringify(input), before); assert.deepEqual(p.body.messages, messages);
  assert.equal((p.body.messages as any[])[0].role, 'developer'); assert.notEqual(p.body.messages, messages);
  assert.equal(p.body.reasoning_effort, undefined); assert.deepEqual(p.body.chat_template_kwargs, { enable_thinking: true });
  assert.equal(p.body.reasoning_format, 'deepseek'); assert.equal(p.body.add_generation_prompt, true);
  assert.ok(Object.isFrozen(p.body)); assert.ok(Object.isFrozen(p.body.messages));
  assert.deepEqual(prepareMimo(request({ reasoning_effort: 'none' })).body.chat_template_kwargs, { enable_thinking: false });
  assert.deepEqual(prepareMimo(request({ chat_template_kwargs: { enable_thinking: false } })).body.chat_template_kwargs, { enable_thinking: false });
  assert.equal(prepareMimo(request({ max_tokens: 20, max_completion_tokens: 20 })).body.max_completion_tokens, undefined);
});

test('closed grammar rejects media, role/control injection, malformed history and unsafe limits', () => {
  const bad = [
    { model: 'glm-5.3-flash' }, { url: 'http://localhost' }, { n_predict: 1 }, { ignore_eos: true },
    { continue_final_message: true }, { add_generation_prompt: false }, { reasoning_format: 'none' },
    { chat_template: 'override' }, { grammar: 'x' }, { prompt: 'raw' }, { n_keep: 1 }, { n_discard: 1 },
    { max_tokens: 20, max_completion_tokens: 19 }, { max_tokens: 0 }, { max_tokens: -1 }, { max_tokens: 0.5 },
    { max_tokens: NaN }, { max_tokens: Infinity }, { max_tokens: Number.MAX_SAFE_INTEGER + 1 }, { max_tokens: 2147483648 },
    { max_tokens: undefined }, { n: 2 }, { parallel_tool_calls: true }, { tool_choice: 'required' },
    { tool_choice: { type: 'function', function: { name: 'lookup' } } }, { stream: false },
    { stream_options: { include_usage: false } }, { temperature: NaN }, { temperature: 3 }, { top_p: Infinity },
    { reasoning_effort: 'high' }, { chat_template_kwargs: { clear_thinking: true } },
    { reasoning_effort: 'none', chat_template_kwargs: { enable_thinking: true } },
    { stop: [''] }, { stop: [5] },
    ...[
      { role: 'system', content: null }, { role: 'assistant', content: null, tool_calls: [] },
      { role: 'assistant', content: null }, { role: 'evil', content: 'x' },
      { role: 'user', content: [{ type: 'image_url', image_url: { url: 'data:x' } }] },
      { role: 'user', content: [{ type: 'text', text: 'ok', image_url: 'x' }] },
      { role: 'user', content: [{ type: 'text', text: ['nested'] }] },
      { role: 'user', content: 'x', reasoning_content: 'x' },
      { role: 'tool', content: 'orphan', tool_call_id: 'unknown' },
      { role: 'assistant', content: null, tool_calls: [{ id: 'x', type: 'function', function: { name: 'lookup', arguments: '{' } }] },
    ].map(m => ({ messages: [m] })),
  ];
  for (const input of bad) assert.throws(() => prepareMimo(request(input)), JSON.stringify(input));
  const getter = Object.defineProperty({}, 'model', { enumerable: true, get() { throw Error('must not read accessor'); } });
  assert.throws(() => prepareMimo(getter), { code: 'mimo_invalid_request' });
  const sparse: any[] = new Array(1); Object.assign(sparse, { extra: 'not index zero' });
  assert.throws(() => prepareMimo(request({ messages: sparse })));
  const accessor: any[] = ['x']; Object.defineProperty(accessor, '0', { get() { throw Error('must not read array getter'); } });
  assert.throws(() => prepareMimo(request({ messages: accessor })), { code: 'mimo_invalid_request' });
  const schemaData = JSON.parse('{"type":"object","properties":{"__proto__":{"type":"string"},"constructor":{"type":"string"}}}');
  const withData = prepareMimo(request({ tools: [{ type: 'function', function: { name: 'lookup', parameters: schemaData } }] }));
  assert.deepEqual((withData.body.tools as any[])[0].function.parameters, schemaData);
  const cyclic: any = {}; cyclic.self = cyclic;
  assert.throws(() => prepareMimo(request({ tools: [{ ...tool, function: { ...tool.function, parameters: cyclic } }] })));
  assert.throws(() => prepareMimo(request({ messages: [{ role: 'user', content: 'x'.repeat(16 * 1024 * 1024 + 1) }] })), { code: 'mimo_body_limit' });
});

test('required actual qualified identity, exact P+O=S-1 boundary and no output shrinking', async () => {
  const p = prepareMimo(request());
  assert.equal((await countFixture(p, proof(), identity(), 79)).promptTokens, 79);
  await assert.rejects(() => countFixture(p, proof(), identity(), 80), { code: 'mimo_context_full' });
  await assert.rejects(() => countFixture(p, proof(), identity(), 100), { code: 'mimo_context_full' });
  await assert.rejects(() => countFixture(p, proof(), identity(), Number.MAX_SAFE_INTEGER), { code: 'mimo_context_full' });
  await assert.rejects(() => countFixture(p, proof(), identity(), NaN));
  await assert.rejects(() => countFixture(prepareMimo(request({ max_tokens: 21 })), proof(), identity(), 0));
  assert.equal(p.outputTokens, 20);
  for (const change of [{ qualified: false }, { evidenceSha256: null }, { checks: {} }, { identity: null }])
    await assert.rejects(() => countFixture(p, { ...proof(), ...change } as any, identity(), 70));
  for (const change of [{ actualSlotContext: null }, { maxOutputTokens: null }, { serverGeneration: '' },
    { runtimeRevision: 'other' }, { artifactManifestSha256: 'b'.repeat(64) }, { parallel: 2 }, { contextShift: true },
    { assistantPrefill: true }, { jinja: false }, { speculative: true }, { kvUnified: null }, { multimodal: true }]) {
    const q = proof(); Object.assign(q.identity, change);
    await assert.rejects(() => countFixture(p, q, q.identity, 70));
  }
  const a = await countFixture(p, proof(), identity(), 79);
  assert.throws(() => mimoGenerationRequest(a, { ...identity(), serverGeneration: 'reloaded' }), { code: 'mimo_identity_mismatch' });
  assert.throws(() => mimoGenerationRequest({ ...a }, identity()), { code: 'mimo_missing_admission' });
});

test('native count POST uses byte-identical full canonical generation body and strict integer response', async () => {
  const p = prepareMimo(request({ tools: [tool], messages: [{ role: 'developer', content: [{ type: 'text', text: 'rules' }] }, { role: 'user', content: 'x' }] }));
  const sent: MimoNativeRequest[] = []; let observations = 0;
  const transport = { observe: async () => { observations++; return identity(); }, post: async (r: MimoNativeRequest) => {
    sent.push(r); return new Response('{"input_tokens":79}'); } };
  const a = await countMimo(p, proof(), transport, new AbortController().signal);
  assert.equal(observations, 2); assert.equal(sent.length, 1); assert.equal(sent[0].method, 'POST');
  assert.equal(sent[0].path, '/v1/chat/completions/input_tokens');
  const dispatch = mimoGenerationRequest(a, identity());
  assert.equal(dispatch.body, sent[0].body); assert.equal(sent[0].body, p.json);
  assert.equal(dispatch.path, '/v1/chat/completions');
  assert.throws(() => mimoGenerationRequest(a, identity()), { code: 'mimo_admission_consumed' });
  for (const body of ['{"input_tokens":"79"}', '{"input_tokens":-1}', '{"input_tokens":1.5}', '{"count":79}',
    '{"input_tokens":9007199254740992}', '{"input_tokens":1e999}', '{"input_tokens":7.9e1}', '{"input_tokens":79,"input_tokens":78}', '{"input_tokens":79,"model":"fake"}', '{}', 'broken', ' '.repeat(16385)]) {
    await assert.rejects(countMimo(p, proof(), { ...transport, post: async () => new Response(body) }, new AbortController().signal));
  }
  await assert.rejects(countMimo(p, proof(), { ...transport, post: async () => new Response('', { status: 503 }) }, new AbortController().signal));
  let calls = 0;
  await assert.rejects(countMimo(p, proof(), { ...transport, observe: async () => ({ ...identity(), serverGeneration: calls++ ? 'new' : 'fixture-generation' }) }, new AbortController().signal), { code: 'mimo_identity_mismatch' });
  const before = sent.length;
  await assert.rejects(countMimo(p, { ...proof(), qualified: false } as any, transport, new AbortController().signal));
  assert.equal(sent.length, before);
});

test('complete stream handles arbitrary byte splits, empty fragments, usage-only frame and HTTP drain', () => {
  const s = new MimoStreamValidator(admission(), sseResponse), bytes = Buffer.from(plain().map(frame).join('').replaceAll('\n', '\r\n'));
  for (const b of bytes) s.push(Uint8Array.of(b));
  const result = s.finish(true, identity());
  assert.equal(result.reasoning, '理由🙂'); assert.equal(result.content, 'Answer');
  assert.equal(result.finishReason, 'stop'); assert.equal(result.responseId, 'chatcmpl-fixture');
  assert.equal(result.usage.cached_tokens, 3); assert.equal(result.nativeSettled, false);
  assert.throws(() => s.finish(true, identity()));
  assert.throws(() => stream(plain(), identity(), false));
  assert.throws(() => stream(plain(), { ...identity(), loadedTokenizerSha256: 'b'.repeat(64) }));
});

const toolStream = () => [
  chunk({ role: 'assistant', content: '', reasoning_content: '' }),
  chunk({ reasoning_content: 'Need lookup. ', content: 'Checking ', tool_calls: [{ index: 0, id: 'call_actual_7', type: 'function', function: { name: 'look', arguments: '{"query":' } }] }),
  chunk({ content: 'now.', reasoning_content: '', tool_calls: [{ index: 0, function: { name: 'up', arguments: '"α","nested":{"items":[1,true,null]}}' } }] }),
  chunk({}, 'tool_calls'), usage(), '[DONE]',
];
test('mixed reasoning/content/tool deltas assemble native IDs/names/arguments only after complete drain', () => {
  const result = stream(toolStream());
  assert.equal(result.content, 'Checking now.'); assert.equal(result.reasoning, 'Need lookup. ');
  assert.equal(result.finishReason, 'tool_calls');
  assert.deepEqual(result.toolCalls, [{ id: 'call_actual_7', type: 'function', function: { name: 'lookup', arguments: '{"query":"α","nested":{"items":[1,true,null]}}' } }]);
  const partial = new MimoStreamValidator(admission(), sseResponse); partial.push(Buffer.from(toolStream().slice(0, 3).map(frame).join('')));
  assert.throws(() => partial.finish(false, identity()));
});

test('protocol failures never produce completed tools or silently accept truncated/mismatched output', () => {
  const bad: unknown[][] = [
    plain().slice(0, -1), plain().filter((_, i) => i !== 3), plain().filter((_, i) => i !== 4),
    [chunk({}, 'stop'), '[DONE]', usage()], [...plain(), chunk({ content: 'late' })],
    [chunk({ content: 'x' }), { ...chunk({}, 'stop'), id: 'chatcmpl-other' }, usage(), '[DONE]'],
    [{ ...chunk({}, 'stop'), model: 'glm-5.3-flash' }, usage(), '[DONE]'],
    [{ ...chunk({}, 'stop'), error: { message: 'native error' } }, usage(), '[DONE]'],
    [{ ...chunk({ content: 'x' }), system_fingerprint: 'build-a' }, { ...chunk({}, 'stop'), system_fingerprint: 'build-b' }, usage(), '[DONE]'],
    [chunk({}, 'stop'), { ...usage(), id: 'chatcmpl-other' }, '[DONE]'],
    [chunk({}, 'stop'), usage({ prompt_tokens: 69, total_tokens: 79 }), '[DONE]'],
    [chunk({}, 'stop'), usage({ completion_tokens: 21, total_tokens: 91 }), '[DONE]'],
    [chunk({}, 'stop'), usage({ total_tokens: 81 }), '[DONE]'],
    [chunk({}, 'stop'), usage({ completion_tokens: 1.5, total_tokens: 71.5 }), '[DONE]'],
    [chunk({}, 'stop'), usage({ prompt_tokens_details: { cached_tokens: 71 } }), '[DONE]'],
    [chunk({}, 'other'), usage(), '[DONE]'],
    [chunk({ content: 1 }), chunk({}, 'stop'), usage(), '[DONE]'],
    [chunk({ refusal: 'unsupported' }), chunk({}, 'stop'), usage(), '[DONE]'],
    [chunk({}, 'tool_calls'), usage(), '[DONE]'],
    ...['{', '[]', 'null', '{"a":NaN}'].map(arguments_ => [chunk({ tool_calls: [{ index: 0, id: 'native-id', type: 'function', function: { name: 'lookup', arguments: arguments_ } }] }), chunk({}, 'tool_calls'), usage(), '[DONE]']),
    ...['stop', 'length'].map(reason => [...toolStream().slice(0, 3), chunk({}, reason), usage(), '[DONE]']),
    [chunk({ tool_calls: [{ index: 0, id: 'a', type: 'function', function: { name: 'lookup', arguments: '{}' } }] }), chunk({ tool_calls: [{ index: 0, id: 'b' }] }, 'tool_calls'), usage(), '[DONE]'],
    [chunk({ tool_calls: [{ index: 1, id: 'a', type: 'function', function: { name: 'lookup', arguments: '{}' } }] }), chunk({}, 'tool_calls'), usage(), '[DONE]'],
    [chunk({ tool_calls: [{ index: 0, id: 'a', type: 'function', function: { name: 'unknown', arguments: '{}' } }] }), chunk({}, 'tool_calls'), usage(), '[DONE]'],
  ];
  for (const events of bad) assert.throws(() => stream(events), { code: 'mimo_stream_invalid' });
  const invalidUtf8 = new MimoStreamValidator(admission(), sseResponse); assert.throws(() => invalidUtf8.push(Uint8Array.of(0xff)));
  const malformed = new MimoStreamValidator(admission(), sseResponse); assert.throws(() => malformed.push(Buffer.from('data: {\n\n')));
  const noDelimiter = new MimoStreamValidator(admission(), sseResponse); noDelimiter.push(Buffer.from(plain().map(frame).join('').trimEnd()));
  assert.throws(() => noDelimiter.finish(true, identity()));
  assert.equal(stream([chunk({ content: 'bounded answer' }, 'length'), usage(), '[DONE]']).finishReason, 'length');
});

test('ambiguity holds existing owner without replay/switch; transport completion does not prove settlement', () => {
  for (const event of ['timeout', 'active_abort', 'early_eof', 'native_5xx', 'cancel_uncertain', 'protocol_failure'] as const)
    assert.deepEqual(mimoOwnerPolicy(event), { state: 'quarantined', holdOwner: true, replay: false, canSwitch: false });
  for (const event of ['transport_complete', 'consumer_detached'] as const)
    assert.deepEqual(mimoOwnerPolicy(event), { state: 'active', holdOwner: true, replay: false, canSwitch: false });
  assert.equal(mimoOwnerPolicy('queued_cancel').holdOwner, false);
});


test('count aborts bounded observation, post and stalled body without retry; bad SSE envelopes fail closed', async () => {
  for (const phase of ['observe', 'post', 'body']) {
    const controller = new AbortController(); let posts = 0;
    const transport = {
      observe: async () => phase === 'observe' ? new Promise<MimoBackendIdentity>(() => {}) : identity(),
      post: async () => {
        posts++;
        if (phase === 'post') return new Promise<Response>(() => {});
        return new Response(new ReadableStream<Uint8Array>({ start() {} }));
      },
    };
    const pending = countMimo(prepareMimo(request()), proof(), transport, controller.signal);
    const timer = setTimeout(() => controller.abort(new Error('fixture abort')), 5);
    try { await assert.rejects(pending, /fixture abort/); } finally { clearTimeout(timer); }
    assert.equal(posts, phase === 'observe' ? 0 : 1);
    assert.equal(mimoOwnerPolicy('cancel_uncertain').holdOwner, true);
  }
  for (const response of [{ status: 503, contentType: 'text/event-stream' }, { status: 200, contentType: 'application/json' }])
    assert.throws(() => new MimoStreamValidator(admission(), response), { code: 'mimo_stream_invalid' });
});
