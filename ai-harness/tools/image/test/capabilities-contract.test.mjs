import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { z } from 'zod';
import { capabilitiesInput } from '../image.mjs';

test('actual image capabilities schema matches captured MCP declaration and rejects namespace keys', () => {
  const tools=JSON.parse(readFileSync(new URL('../../../server/test/fixtures/codex/image-mcp-tools.json',import.meta.url),'utf8'));
  const actual=z.toJSONSchema(capabilitiesInput,{target:'draft-7'});
  assert.deepEqual(actual,tools.find(tool=>tool.name==='image_capabilities').inputSchema);
  assert.deepEqual(capabilitiesInput.parse({}),{});
  for(const key of ['__ns','ns','namespace']){
    const input={[key]:'10'},before=structuredClone(input),result=capabilitiesInput.safeParse(input);
    assert.equal(result.success,false);assert.equal(result.error.issues[0].code,'unrecognized_keys');
    assert.deepEqual(result.error.issues[0].keys,[key]);assert.deepEqual(input,before);
  }
});
