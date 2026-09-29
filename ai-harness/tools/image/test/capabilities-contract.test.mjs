import test from 'node:test';
import assert from 'node:assert/strict';
import { z } from 'zod';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { InMemoryTransport } from '@modelcontextprotocol/sdk/inMemory.js';
import { capabilitiesInput, createImageClient, GATEWAY } from '../image.mjs';
import { createImageServer } from '../image-mcp.mjs';

test('capabilities contract requires the explicit enum query and rejects all undeclared fields', () => {
  const actual=z.toJSONSchema(capabilitiesInput,{target:'draft-7'});
  assert.deepEqual(actual,{ $schema: 'http://json-schema.org/draft-07/schema#', type: 'object',
    properties: { query: { type: 'string', enum: ['capabilities'] } }, required: ['query'], additionalProperties: false });
  assert.deepEqual(capabilitiesInput.parse({ query:'capabilities' }),{ query:'capabilities' });
  for(const key of ['prompt','__ns','ns','namespace','references','approved','size']){
    const input={query:'capabilities',[key]:'10'},before=structuredClone(input),result=capabilitiesInput.safeParse(input);
    assert.equal(result.success,false);assert.equal(result.error.issues[0].code,'unrecognized_keys');
    assert.deepEqual(result.error.issues[0].keys,[key]);assert.deepEqual(input,before);
  }
  for(const input of [{}, {query:'generation'}, {query:''}, {query:null}, {query:1}])
    assert.equal(capabilitiesInput.safeParse(input).success,false);
});

test('handler rejects legacy or invalid requests before transport and exact query only reads metadata', async () => {
  const calls=[];
  const client=createImageClient({ token:'fixture-session-bearer-only', fetchImpl:async (url,options)=>{
    calls.push({url,...options});
    return new Response(JSON.stringify({profiles:[]}),{headers:{'Content-Type':'application/json'}});
  }});
  for(const input of [undefined,{}, {query:'wrong'}, {query:'capabilities',prompt:'1024x576'}]) {
    await assert.rejects(client.capabilities(input),{code:'INVALID_INPUT',
      message:'image_capabilities requires exactly {"query":"capabilities"}; no other arguments are accepted. This reads service metadata only.'});
  }
  assert.equal(calls.length,0);
  assert.deepEqual(await client.capabilities({query:'capabilities'}),{profiles:[]});
  assert.equal(calls.length,1);assert.equal(calls[0].method,'GET');
  assert.equal(calls[0].url,`${GATEWAY}/image-capabilities`);assert.equal(calls[0].body,undefined);
});

test('actual SDK list and call contract exposes enum and rejects legacy requests without invoking client', async () => {
  const calls=[];
  const server=createImageServer({capabilities:async input=>{calls.push(structuredClone(input));return {profiles:[]};},
    invoke:async()=>{throw new Error('No creative tool should run');}});
  const client=new Client({name:'offline-capability-contract',version:'1'});
  const [left,right]=InMemoryTransport.createLinkedPair();
  await server.connect(right);await client.connect(left);
  try {
    const descriptor=(await client.listTools()).tools.find(tool=>tool.name==='image_capabilities');
    assert.deepEqual(descriptor.inputSchema,z.toJSONSchema(capabilitiesInput,{target:'draft-7'}));
    assert.equal(descriptor.annotations.readOnlyHint,true);
    assert.match(descriptor.description,/does not generate or edit/);
    for(const input of [{},{query:'wrong'},{query:'capabilities',prompt:'1024x576'}]) {
      const failed=await client.callTool({name:'image_capabilities',arguments:input});
      assert.equal(failed.isError,true);
      assert.match(failed.content[0].text,/Input validation error/);
      assert.match(failed.content[0].text,/query|prompt/);
    }
    assert.equal(calls.length,0);
    const result=await client.callTool({name:'image_capabilities',arguments:{query:'capabilities'}});
    assert.ok(!result.isError);assert.deepEqual(calls,[{query:'capabilities'}]);
    assert.deepEqual(JSON.parse(result.content[0].text),{profiles:[]});
  } finally {await client.close();await server.close();}
});
