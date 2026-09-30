import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { translateResponses, ResponsesStream } from '../src/codex-responses.js';

const read = (relative: string) => readFileSync(new URL(relative, import.meta.url), 'utf8');
const retained = JSON.parse(read('./fixtures/codex/h032-pdf-tool-outcomes.json'));
const captured = JSON.parse(read('./fixtures/codex/native-requests.json'));
const sha = (text: string) => createHash('sha256').update(text).digest('hex');

test('retained H032 outputs keep the actual failed operation, no-match and successful create distinct', () => {
  const [failedOperation, noMatch] = retained.tools;
  assert.equal(failedOperation.commandExitCode, 0);
  assert.match(failedOperation.outputExcerpt, /error: the following arguments are required: --output/);
  assert.equal(noMatch.commandExitCode, 1);
  assert.equal(noMatch.outputExcerpt, '');
  assert.equal(noMatch.reviewedInterpretation, 'search_no_match');
  const succeeded = retained.tools.find((t: any) => t.reviewedInterpretation === 'later_create_succeeded');
  assert.equal(JSON.parse(succeeded.outputExcerpt).ok, true);
  assert.ok(Date.parse(succeeded.outputObservedUtc) > Date.parse(failedOperation.outputObservedUtc));
  assert.equal(retained.terminal.runStatus, 'completed');
  assert.equal(retained.terminal.numericExtractionCitationArtifactAndRenderPassed, true);
  assert.equal(retained.terminal.failureDisclosurePassed, false);
  assert.equal(retained.terminal.nativeFinalPhase, 'absent');
  assert.equal(retained.terminal.appFinalPhase, 'unclassified');
  for (const result of retained.adapterTestInput.input.filter((i: any) => i.type === 'function_call_output')) {
    const actual = retained.tools.find((t: any) => t.toolCallId === result.call_id);
    assert.equal(sha(result.output), actual.nativeOutputSha256);
    assert.equal(Buffer.byteLength(result.output), actual.nativeOutputBytes);
  }
});

test('both provider adapters preserve observed errors and recovery bytes with original tool IDs', () => {
  for (const model of ['qwen3.8-27b', 'mimo-v2.6-pro-rl']) {
    const request = structuredClone(captured[0].body);
    request.model = model;
    request.parallel_tool_calls = false;
    request.input.push(...structuredClone(retained.adapterTestInput.input));
    const before = JSON.stringify(request);
    const translated = translateResponses(request);
    const outputs = retained.adapterTestInput.input.filter((item: any) => item.type === 'function_call_output');
    for (const output of outputs) {
      const actual = translated.body.messages.find((item: any) => item.role === 'tool' && item.tool_call_id === output.call_id);
      assert.equal(actual.content, output.output);
    }
    assert.equal(JSON.stringify(request), before);
    // No injected rescue prompt, replacement result or transport retry.
    assert.equal(translated.body.messages.filter((item: any) => item.role === 'tool').length, outputs.length);
  }
});

test('reporting correction does not rewrite an observed denial or invent a final phase', () => {
  const text = retained.terminal.finalDenialExcerpt;
  const request = structuredClone(captured[0].body);
  let wire = '';
  const stream = new ResponsesStream(translateResponses(request), data => { wire += data; });
  stream.push(Buffer.from(`data: ${JSON.stringify({ choices: [{ delta: { content: text }, finish_reason: 'stop' }], usage: { prompt_tokens: 1, completion_tokens: 1 } })}\n\n`));
  stream.push(Buffer.from('data: [DONE]\n\n'));
  stream.end();
  const events = wire.split('\n').filter(line => line.startsWith('data: ')).map(line => JSON.parse(line.slice(6)));
  const final = events.at(-1).response.output.find((item: any) => item.type === 'message');
  assert.equal(final.content[0].text, text);
  assert.equal(final.phase, undefined);
});

test('ordinary PDF and mounted Codex guidance require actual errors plus successful recovery without changing task outcome', () => {
  const catalog = JSON.parse(read('../../deploy/codex/models.json'));
  const sources = [read('../../skills/pdf/SKILL.md'), read('../../deploy/codex/skills/sova-local-tools/SKILL.md'),
    read('../../deploy/codex/sova-overlay.md'), ...catalog.models.map((m: any) => m.model_messages.instructions_template)];
  for (const source of sources) {
    assert.match(source, /actual tool outputs|actual outputs/);
    assert.match(source, /shell exit of zero/);
    assert.match(source, /successful recovery/);
    assert.match(source, /no matches/);
    assert.match(source, /not.*(?:whole task|overall task).*failed|Do not label the whole task\nfailed/);
    assert.match(source, /phase.*(?:metadata|unknown)|phase or terminal metadata/);
    assert.match(source, /separate tool calls or stop the shell on a failed step/);
  }
  // These are guidance/provenance assertions, not a prediction of the next model final.
  const instructions = sources.join('\n');
  assert.doesNotMatch(instructions, /call_830b3590893b400984d2672d|source_summary_page1\.pdf|250\s*mA|3\.3\s*V/);
});
