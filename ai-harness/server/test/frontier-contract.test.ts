import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { countFrontier, frontierBody, frontierConfiguration, FRONTIER_MODEL, FRONTIER_REVISION, type FrontierOptions } from '../src/frontier.js';

const configured = (contextWindow: number, qualified = true) => ({
  model: FRONTIER_MODEL, contextWindow, maxOutputTokens: 65536, qualified,
  tokenizerRevision: FRONTIER_REVISION, templateRevision: FRONTIER_REVISION,
});

test('H013 frontier candidate stays unqualified; exact capacities and output ceiling remain closed', () => {
  const candidate = JSON.parse(readFileSync(new URL('../../config/frontier.json', import.meta.url), 'utf8'));
  assert.equal(candidate.contextWindow, 1048576);
  assert.equal(candidate.qualified, false);
  assert.equal(frontierConfiguration(candidate), undefined);
  for (const capacity of [128000, 256000, 480000, 1048576]) {
    assert.equal(frontierConfiguration(configured(capacity))?.contextWindow, capacity);
    assert.equal(frontierConfiguration(configured(capacity, false)), undefined);
  }
  for (const capacity of [0, 1048575, 1048577, 1000000, NaN]) {
    assert.equal(frontierConfiguration(configured(capacity)), undefined);
  }
  assert.equal(frontierConfiguration({ ...configured(1048576), maxOutputTokens: 65537 }), undefined);
  const request = { model: FRONTIER_MODEL, messages: [{ role: 'user', content: 'fixture' }] };
  assert.equal(frontierBody(request).max_tokens, 65536);
  assert.equal(frontierBody({ ...request, max_tokens: 65537 }).max_tokens, 65536);
});

test('H013 1M exact-token accounting retains P-7/P-2, output65536 and mismatch refusal without network', async (t) => {
  const options: FrontierOptions = { contextWindow: 1048576, tokenizerRevision: FRONTIER_REVISION,
    templateRevision: FRONTIER_REVISION, upstreamKey: 'fixture', onRequestState() {} };
  let count = 0, capacity = 1048576, fetches = 0;
  t.mock.method(globalThis, 'fetch', async () => {
    fetches++;
    return new Response(JSON.stringify({ count, context_limit: capacity,
      tokenizer_revision: FRONTIER_REVISION, template_revision: FRONTIER_REVISION }));
  });
  const run = (input: number, output: number) => {
    count = input;
    return countFrontier(options, { max_tokens: output }, 'fixture', new AbortController().signal);
  };
  assert.deepEqual(await run(1048569, 5), { promptTokens: 1048569, reservedOutput: 5 });
  await assert.rejects(run(1048570, 1), { code: 'frontier_context_full' });
  await assert.rejects(run(1048569, 6), { code: 'frontier_context_full' });
  assert.deepEqual(await run(983038, 65536), { promptTokens: 983038, reservedOutput: 65536 });
  await assert.rejects(run(983039, 65536), { code: 'frontier_context_full' });
  await assert.rejects(run(1, 65537), { code: 'frontier_context_full' });
  capacity = 480000;
  await assert.rejects(run(100, 1), { code: 'frontier_tokenizer_unavailable' });
  const historical = { ...options, contextWindow: 480000 as const };
  count = 479993;
  assert.deepEqual(await countFrontier(historical, { max_tokens: 5 }, 'fixture', new AbortController().signal),
    { promptTokens: 479993, reservedOutput: 5 });
  await assert.rejects(countFrontier(historical, { max_tokens: 6 }, 'fixture', new AbortController().signal),
    { code: 'frontier_context_full' });
  const before = fetches;
  await assert.rejects(countFrontier({ ...options, contextWindow: 1048575 as never }, { max_tokens: 1 }, 'fixture', new AbortController().signal), { code: 'frontier_unqualified' });
  assert.equal(fetches, before);
});
