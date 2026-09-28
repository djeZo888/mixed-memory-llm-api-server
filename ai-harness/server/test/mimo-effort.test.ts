import test from 'node:test';
import assert from 'node:assert/strict';
import { MIMO_MODEL, prepareMimo } from '../src/mimo.js';

const request = (extra = {}) => ({ model: MIMO_MODEL, max_completion_tokens: 65536,
  messages: [{ role: 'user', content: 'small fixture' }], ...extra });

test('MiniMax medium explicitly maps to MiMo thinking on and preserves strict tools and raw history', () => {
  const argumentsText = '{ "command": "printf 42", "extra": null }';
  const messages = [{ role: 'user', content: 'small fixture' },
    { role: 'assistant', content: null, tool_calls: [{ id: 'call_original', type: 'function',
      function: { name: 'bash', arguments: argumentsText } }] },
    { role: 'tool', tool_call_id: 'call_original', content: '42' }];
  const tools = [{ type: 'function', function: { name: 'bash', strict: true,
    parameters: { type: 'object', additionalProperties: false,
      properties: { command: { type: 'string' }, extra: { type: 'null' } }, required: ['command', 'extra'] } } }];
  const input = request({ reasoning_effort: 'medium', messages, tools, store: false });
  const original = JSON.stringify(input), prepared = prepareMimo(input);
  assert.equal(JSON.stringify(input), original);
  assert.deepEqual(prepared.thinking, { requestedEffort: 'medium', enableThinking: true });
  assert.ok(Object.isFrozen(prepared.thinking));
  assert.deepEqual(prepared.body.chat_template_kwargs, { enable_thinking: true });
  assert.equal(prepared.body.reasoning_effort, undefined);
  assert.equal(prepared.body.parallel_tool_calls, false);
  assert.equal(prepared.body.max_tokens, 65536);
  assert.deepEqual(prepared.body.tools, tools);
  assert.deepEqual(prepared.body.messages, messages);
});

test('unknown effort, conflicting switches and parallel requests still fail closed', () => {
  for (const reasoning_effort of ['low', 'high', 'xhigh', 'MEDIUM', '', 0, true, null])
    assert.throws(() => prepareMimo(request({ reasoning_effort })), { rule: 'reasoning_effort_contract' });
  for (const [reasoning_effort, enable_thinking] of [['none', true], ['medium', false]])
    assert.throws(() => prepareMimo(request({ reasoning_effort, chat_template_kwargs: { enable_thinking } })), { rule: 'thinking_conflict' });
  assert.throws(() => prepareMimo(request({ reasoning_effort: 'medium', parallel_tool_calls: true })), { rule: 'serial_tool_calls_required' });
  assert.deepEqual(prepareMimo(request({ reasoning_effort: 'none' })).thinking, { requestedEffort: 'none', enableThinking: false });
  assert.deepEqual(prepareMimo(request()).thinking, { requestedEffort: null, enableThinking: true });
  assert.deepEqual(prepareMimo(request({ chat_template_kwargs: { enable_thinking: false } })).thinking,
    { requestedEffort: null, enableThinking: false });
});
