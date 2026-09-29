import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { ResponsesStream, translateResponses } from '../src/codex-responses.js';

// Retains the complete field/type/order topology of the real H030 compact
// pre-normalization request. All instructions, content, arguments and IDs are
// synthetic; full actual capture remains private. No dummy current tools.
const captured = JSON.parse(readFileSync(new URL('./fixtures/codex/native-compaction-history.json', import.meta.url), 'utf8'));
const request = () => ({ model: 'qwen3.8-27b', instructions: 'Summarize retained history.', input: [] as any[],
  tools: [] as any[], tool_choice: 'auto', parallel_tool_calls: false, reasoning: {}, store: false, stream: true,
  include: ['reasoning.encrypted_content'] });
const call = (name = 'retired_reader', arguments_ = '{ "value": 1 }') =>
  ({ type: 'function_call', id: 'item_old', call_id: 'call_old', name, arguments: arguments_ });
const output = (callId = 'call_old') => ({ type: 'function_call_output', call_id: callId, output: 'retained result\n' });
const custom = (name = 'retired_writer', input = 'exact custom text\n') =>
  ({ type: 'custom_tool_call', id: 'item_custom', call_id: 'call_custom', name, input });
const customOutput = () => ({ type: 'custom_tool_call_output', call_id: 'call_custom', output: [{ type: 'input_text', text: 'retained custom result\n' }] });
const calls = (translated: ReturnType<typeof translateResponses>) => translated.body.messages.flatMap((m: any) => m.tool_calls ?? []);
const chunk = (v: unknown) => Buffer.from(`data: ${JSON.stringify(v)}\n\n`);
const contractRejected = (fn: () => unknown) => assert.throws(fn, (e: any) => e.code === 'unsupported_responses_contract');

test('native compact memento tools[] retains all five historical exec calls/results without declaring them', () => {
  const b = structuredClone(captured), original = structuredClone(b);
  assert.equal(b.tools.length, 0);
  assert.deepEqual(b.input.map((i: any) => i.type), [
    'message', 'message', 'message', 'function_call', 'function_call_output',
    'function_call', 'function_call_output', 'function_call', 'function_call_output',
    'message', 'message', 'function_call', 'function_call_output',
    'function_call', 'function_call_output', 'message', 'message',
  ]);
  const t = translateResponses(b);
  assert.deepEqual(t.body.tools, []);
  assert.equal(t.tools.size, 0);
  const historyCalls = b.input.filter((i: any) => i.type === 'function_call');
  assert.equal(historyCalls.length, 5);
  assert.deepEqual(calls(t), historyCalls.map((i: any) => ({ id: i.call_id, type: 'function', function: { name: i.name, arguments: i.arguments } })));
  assert.deepEqual(t.body.messages.filter((m: any) => m.role === 'tool'), b.input.filter((i: any) => i.type === 'function_call_output').map((i: any) => ({ role: 'tool', tool_call_id: i.call_id, content: i.output })));
  assert.deepEqual(b, original, 'translation must not rewrite the client memento');
});

test('retired historical function and custom identity/type/bytes survive opposite current declarations', () => {
  const b = request();
  const args = ' { "__ns": "unchanged", "ns": "retained", "__v": 2, "x": "\\u017e" }\n';
  const text = 'arbitrary retired custom input\r\n\tž\n';
  b.tools = [
    { type: 'custom', name: 'retired_reader', description: 'Current custom tool', format: { type: 'text' } },
    { type: 'function', name: 'retired_writer', description: 'Current function tool', strict: true, parameters: { type: 'object', properties: {} } },
  ];
  b.input = [call('retired_reader', args), custom('retired_writer', text), output(), customOutput()];
  const t = translateResponses(b), mapped = calls(t);
  assert.equal(mapped[0].function.arguments, args);
  assert.equal(mapped[0].function.name, 'retired_reader');
  assert.equal(mapped[1].function.arguments, JSON.stringify({ input: text }));
  assert.equal(JSON.parse(mapped[1].function.arguments).input, text);
  assert.equal(mapped[1].function.name, 'retired_writer');
  assert.deepEqual(mapped.map((c: any) => c.id), ['call_old', 'call_custom']);
  assert.equal(t.tools.get('retired_reader')?.custom, true, 'new output follows current custom declaration');
  assert.equal(t.tools.get('retired_writer')?.custom, false, 'new output follows current function declaration');
});

test('undeclared arbitrary historical custom input is retained without applying current patch grammar', () => {
  const b = request(); const text = 'historical custom text, not a new patch request\r\n';
  b.input = [custom('retired_custom', text), customOutput()];
  const t = translateResponses(b);
  assert.equal(t.tools.size, 0);
  assert.equal(JSON.parse(calls(t)[0].function.arguments).input, text);
  assert.equal(t.body.messages.at(-1).content, 'retained custom result\n');
});

test('qualified native namespace history survives tools[] using only the fixed existing namespace mapping', () => {
  for (const [namespace, name] of [['mcp__image', 'image_capabilities'], ['mcp__search', 'searxng_search'], ['mcp__browser', 'browser_open'], ['multi_agent_v1', 'close_agent']]) {
    const b = request(), args = '{ "__ns": "preserve", "ns": "preserve", "__v": 7 }';
    b.input = [{ ...call(name, args), namespace }, output()];
    const t = translateResponses(b), mapped = calls(t)[0];
    assert.equal(mapped.function.name, `sova_ns_${namespace}_${name}`);
    assert.equal(mapped.function.arguments, args);
    assert.equal(mapped.id, 'call_old');
    assert.equal(t.tools.size, 0);
    assert.deepEqual(t.body.tools, []);
  }
});

test('unknown namespace members and reserved/invalid historical identities remain rejected with tools[]', () => {
  for (const change of [
    { namespace: 'unknown_namespace', name: 'reader' },
    { namespace: '__proto__', name: 'reader' },
    { namespace: 'mcp__image', name: 'unqualified_image_tool' },
    { name: 'sova_ns_mcp__image_image_capabilities' },
    { name: '' }, { name: 'bad.name' }, { name: 'x'.repeat(65) },
  ]) {
    const b = request(); b.input = [{ ...call(), ...change }, output()];
    contractRejected(() => translateResponses(b));
  }
  const b = request(); b.input = [{ ...custom('image_capabilities'), namespace: 'mcp__image' }, customOutput()];
  contractRejected(() => translateResponses(b));
});

test('retired history still rejects duplicate calls/results, unmatched results and mismatched result types', () => {
  for (const input of [
    [call(), call(), output()], [call(), output(), output()], [output()], [call()],
    [call(), { ...customOutput(), call_id: 'call_old' }],
    [custom(), { ...output(), call_id: 'call_custom' }],
    [call(), { ...call('another_reader'), call_id: 'call_second' }, output(), { ...call('third_reader'), call_id: 'call_third' }],
  ]) {
    const b = request(); b.input = input;
    contractRejected(() => translateResponses(b));
  }
});

test('historical presence never grants NEW generated tool permission when tools[] is empty', () => {
  for (const name of ['retired_reader', 'sova_ns_mcp__image_image_capabilities', 'brand_new_tool']) {
    const b = request(); b.input = [call(), output(), { ...call('image_capabilities'), namespace: 'mcp__image', call_id: 'call_image' }, output('call_image')];
    const t = translateResponses(b); let wire = '';
    assert.equal(t.tools.size, 0);
    const stream = new ResponsesStream(t, frame => { wire += frame; });
    assert.throws(() => {
      stream.push(chunk({ choices: [{ index: 0, delta: { tool_calls: [{ index: 0, id: 'call_new', type: 'function', function: { name, arguments: '{}' } }] }, finish_reason: 'tool_calls' }] }));
      stream.push(chunk({ choices: [], usage: { prompt_tokens: 10, completion_tokens: 2 } }));
      stream.push(Buffer.from('data: [DONE]\n\n')); stream.end();
    }, /Invalid tool identity/);
    assert.doesNotMatch(wire, /response\.completed|response\.output_item\.done/);
  }
});
