import test from 'node:test';
import assert from 'node:assert/strict';
import {Client} from '@modelcontextprotocol/sdk/client/index.js';
import {InMemoryTransport} from '@modelcontextprotocol/sdk/inMemory.js';
import {createImageServer} from '../image-mcp.mjs';
import {createImageClient} from '../image.mjs';
test('actual MCP generation profile never advertises or executes edit; useful original job followups remain',async()=>{
 let calls=0;const image=createImageClient({profile:'generation-only',token:'private-fixture-token',fetchImpl:async()=>{calls++;throw Error('No external action');}}),server=createImageServer(image),client=new Client({name:'source-fixture',version:'1'}),[left,right]=InMemoryTransport.createLinkedPair();
 try{await server.connect(right);await client.connect(left);const names=(await client.listTools()).tools.map(t=>t.name).sort();assert.deepEqual(names,['image_cancel','image_capabilities','image_generate','image_lookup','image_status']);
 const r=await client.callTool({name:'image_edit',arguments:{prompt:'edit',references:[{fileId:'owned'}]}});assert.equal(r.isError,true);assert.equal(calls,0);
 await assert.rejects(image.invoke('edit',{prompt:'edit'}),e=>e.code==='OPERATION_UNQUALIFIED');assert.equal(calls,0);
 }finally{await client.close();await server.close();}
});
