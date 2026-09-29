import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { translateResponses, ResponsesStream } from '../src/codex-responses.js';
const fixture = () => JSON.parse(readFileSync(new URL('./fixtures/codex/native-namespace.json', import.meta.url),'utf8'));
test('actual pinned native namespace history and returned calls preserve the tuple', () => {
 const b=fixture(), t=translateResponses(b); const mapped='sova_ns_multi_agent_v1_spawn_agent';
 assert.ok(t.body.tools.some((v:any)=>v.function.name===mapped && v.function.description.includes("Tools for spawning and managing sub-agents.")));
 assert.equal(t.body.messages[1].tool_calls[0].function.name,mapped);
 const frames:string[]=[];const s=new ResponsesStream(t,x=>frames.push(x));
 const data=(v:any)=>s.push(Buffer.from(`data: ${JSON.stringify(v)}\n\n`));
 data({choices:[{index:0,delta:{tool_calls:[{index:0,id:'native-call',type:'function',function:{name:mapped,arguments:'{"message":"child"}'}}]},finish_reason:null}]});
 data({choices:[{index:0,delta:{},finish_reason:'tool_calls'}]});data({choices:[],usage:{prompt_tokens:10,completion_tokens:3,total_tokens:13}});s.push(Buffer.from('data: [DONE]\n\n'));s.end();
 const events=frames.map(v=>JSON.parse(v.split('\ndata: ')[1]!));const item=events.find(v=>v.type==='response.output_item.done').item;
 assert.equal(item.namespace,'multi_agent_v1');assert.equal(item.name,'spawn_agent');assert.equal(item.call_id,'native-call');
});
test('namespace unknown forms, duplicate tuples and reserved-name collisions fail closed',()=>{
 for(const mutate of [(b:any)=>b.tools.push(b.tools.find((t:any)=>t.type==='namespace')),(b:any)=>b.tools.find((t:any)=>t.type==='namespace').tools.push({type:'namespace',name:'nested'}),(b:any)=>b.tools[0].name='sova_ns_multi_agent_v1_spawn_agent',(b:any)=>b.input[0].namespace='unqualified']) {
  const b=fixture();mutate(b);assert.throws(()=>translateResponses(b));
 }
});
test('actual Linux MCP namespace catalog and calls retain scoped identities',()=>{
 const b=JSON.parse(readFileSync(new URL('./fixtures/codex/native-mcp-namespaces.json',import.meta.url),'utf8'));
 for(const ns of b.tools) for(const f of ns.tools){
  const request=structuredClone(b);request.input.push({type:'function_call',call_id:'mcp-call',namespace:ns.name,name:f.name,arguments:'{}'},{type:'function_call_output',call_id:'mcp-call',output:'fixture result'});
  const t=translateResponses(request),mapped=`sova_ns_${ns.name}_${f.name}`;
  assert.equal(t.body.messages.at(-2).tool_calls[0].function.name,mapped);
  const frames:string[]=[];const s=new ResponsesStream(t,x=>frames.push(x));
  for(const v of [{choices:[{delta:{tool_calls:[{index:0,id:'mcp-next',type:'function',function:{name:mapped,arguments:'{}'}}]},finish_reason:'tool_calls'}]},{choices:[],usage:{prompt_tokens:1,completion_tokens:1}}])s.push(Buffer.from(`data: ${JSON.stringify(v)}\n\n`));s.push(Buffer.from('data: [DONE]\n\n'));s.end();
  const item=frames.map(v=>JSON.parse(v.split('\ndata: ')[1]!)).find(v=>v.type==='response.output_item.done').item;assert.equal(item.namespace,ns.name);assert.equal(item.name,f.name);
 }
 const unsafe=structuredClone(b);unsafe.tools.find((t:any)=>t.name==='mcp__image').tools[0].name='image_unqualified';assert.throws(()=>translateResponses(unsafe));
});

test('image generation and edit preserve namespace, call IDs and multi-turn tool results',()=>{
 const b=JSON.parse(readFileSync(new URL('./fixtures/codex/native-mcp-namespaces.json',import.meta.url),'utf8'));
 const ns=b.tools.find((t:any)=>t.name==='mcp__image');
 for(const name of ['image_generate','image_edit']){
  const tool=JSON.parse(readFileSync(new URL('./fixtures/codex/image-mcp-tools.json',import.meta.url),'utf8')).find((t:any)=>t.name===name);
  ns.tools.push({type:'function',name,description:tool.description,strict:false,parameters:tool.inputSchema});
  b.input.push({type:'function_call',call_id:'owned-'+name,namespace:ns.name,name,arguments:JSON.stringify({prompt:'fixture',...(name==='image_edit'?{references:[{fileId:'opaque-owned-file'}]}:{})})},{type:'function_call_output',call_id:'owned-'+name,output:JSON.stringify({job:{id:'owned-job',state:'completed'},artifactId:'opaque-artifact'})});
 }
 const t=translateResponses(b);
 for(const name of ['image_generate','image_edit']){
  const mapped=`sova_ns_mcp__image_${name}`;
  assert.ok(t.body.tools.some((v:any)=>v.function.name===mapped));
  const call=t.body.messages.find((v:any)=>v.tool_calls?.[0]?.id==='owned-'+name);assert.equal(call.tool_calls[0].function.name,mapped);
  const result=t.body.messages.find((v:any)=>v.tool_call_id==='owned-'+name);assert.match(result.content,/owned-job/);
  const frames:string[]=[];const stream=new ResponsesStream(t,x=>frames.push(x));
  for(const v of [{choices:[{delta:{tool_calls:[{index:0,id:'returned-'+name,type:'function',function:{name:mapped,arguments:'{}'}}]},finish_reason:'tool_calls'}]},{choices:[],usage:{prompt_tokens:12,completion_tokens:2}}])stream.push(Buffer.from(`data: ${JSON.stringify(v)}\n\n`));stream.push(Buffer.from('data: [DONE]\n\n'));stream.end();
  const item=frames.map(v=>JSON.parse(v.split('\ndata: ')[1]!)).find(v=>v.type==='response.output_item.done').item;
  assert.equal(item.namespace,'mcp__image');assert.equal(item.name,name);assert.equal(item.call_id,'returned-'+name);
 }
});

test('aliases are stable, collision checked and bounded across the qualified catalogs',()=>{
 const b=JSON.parse(readFileSync(new URL('./fixtures/codex/native-mcp-namespaces.json',import.meta.url),'utf8'));
 b.tools.push(...fixture().tools.filter((t:any)=>t.type==='namespace'));
 const image=b.tools.find((t:any)=>t.name==='mcp__image');
 for(const tool of JSON.parse(readFileSync(new URL('./fixtures/codex/image-mcp-tools.json',import.meta.url),'utf8'))){
  if(tool.name!=='image_capabilities')image.tools.push({type:'function',name:tool.name,description:tool.description,strict:false,parameters:tool.inputSchema});
 }
 const t=translateResponses(b),names=[...t.tools.keys()];
 assert.equal(new Set(names).size,names.length);
 assert.ok(names.every(name=>/^[A-Za-z0-9_-]{1,64}$/.test(name)));
 assert.ok(names.every(name=>!/^sova_ns_\d+_/.test(name)));
 const reordered=structuredClone(b);reordered.tools.reverse();
 assert.deepEqual([...translateResponses(reordered).tools].sort(),[...t.tools].sort());
 for(const mutate of [
  (r:any)=>r.tools.push({type:'function',name:names[0],description:'collision',strict:false,parameters:{}}),
  (r:any)=>r.tools[0].tools.push(r.tools[0].tools[0]),
  (r:any)=>r.tools[0].name='mcp__image_invalid',
  (r:any)=>r.tools[0].name='x'.repeat(65),
  (r:any)=>r.tools.push({type:'function',name:'x'.repeat(65),description:'too long',strict:false,parameters:{}}),
  (r:any)=>r.tools[0].tools[0].name='x'.repeat(65),
 ]){const r=structuredClone(b);mutate(r);assert.throws(()=>translateResponses(r));}
});

test('captured image schema and raw function arguments survive alias response and reconstructed history unchanged',()=>{
 const b=JSON.parse(readFileSync(new URL('./fixtures/codex/native-mcp-namespaces.json',import.meta.url),'utf8'));
 const nativeTool=b.tools.find((t:any)=>t.name==='mcp__image').tools[0];
 const t=translateResponses(b),alias='sova_ns_mcp__image_image_capabilities';
 const declaration=t.body.tools.find((v:any)=>v.function.name===alias).function;
 assert.deepEqual(declaration.parameters,nativeTool.parameters);
 assert.deepEqual(declaration.parameters,{type:'object',properties:{},additionalProperties:false});
 assert.equal(declaration.strict,false); // Native strict flag stays as captured; MCP validation stays strict.
 for(const args of ['{}','{"references":"[]"}','{"skill":"sova-local-tools"}','{"__v":1}',' { "__ns" : "10" }\n','{"ns":"10"}','{"ns":"\\u0031\\u0030"}']){
  const frames:string[]=[];const stream=new ResponsesStream(t,x=>frames.push(x));
  const chunks=[args.slice(0,2),args.slice(2)];
  for(const [index,chunk] of chunks.entries())stream.push(Buffer.from(`data: ${JSON.stringify({choices:[{delta:{tool_calls:[{index:0,...(index===0?{id:'cap-call',type:'function',function:{name:alias,arguments:chunk}}:{function:{arguments:chunk}})}]},finish_reason:null}]})}\n\n`));
  for(const data of [{choices:[{delta:{},finish_reason:'tool_calls'}]},{choices:[],usage:{prompt_tokens:1,completion_tokens:1}}])stream.push(Buffer.from(`data: ${JSON.stringify(data)}\n\n`));
  stream.push(Buffer.from('data: [DONE]\n\n'));stream.end();
  const events=frames.map(v=>JSON.parse(v.split('\ndata: ')[1]!));const item=events.find(v=>v.type==='response.output_item.done').item;
  assert.equal(item.namespace,'mcp__image');assert.equal(item.name,'image_capabilities');assert.equal(item.arguments,args);assert.equal(item.call_id,'cap-call');
  assert.equal(events.find(v=>v.type==='response.function_call_arguments.done').arguments,args);
  const result='MCP error -32602: fixture rejection; retained exactly';
  const next=structuredClone(b);next.input.push(item,{type:'function_call_output',call_id:item.call_id,output:result});
  const history=translateResponses(next).body.messages;
  assert.equal(history.at(-2).tool_calls[0].function.name,alias);assert.equal(history.at(-2).tool_calls[0].function.arguments,args);
  assert.equal(history.at(-1).content,result);assert.equal(history.at(-1).tool_call_id,'cap-call');
 }
});

test('read-only image_status preserves exact job arguments and results in pinned namespace transport', () => {
 const b=JSON.parse(readFileSync(new URL('./fixtures/codex/native-mcp-namespaces.json',import.meta.url),'utf8'));
 const image=b.tools.find((v:any)=>v.name==='mcp__image');
 image.tools.push({type:'function',name:'image_status',description:'Read an existing owned image job',strict:false,parameters:{type:'object',properties:{jobId:{type:'string'}},required:['jobId'],additionalProperties:false}});
 const arguments_=' { "jobId" : "existing-job" }\n', result='{"job":{"id":"existing-job","state":"running","cancelRequested":false}}';
 b.input.push({type:'function_call',call_id:'status-read',namespace:'mcp__image',name:'image_status',arguments:arguments_},{type:'function_call_output',call_id:'status-read',output:result});
 const t=translateResponses(b), alias='sova_ns_mcp__image_image_status';
 assert.ok(t.body.tools.some((v:any)=>v.function.name===alias));
 assert.equal(t.body.messages.at(-2).tool_calls[0].function.arguments,arguments_);
 assert.equal(t.body.messages.at(-1).content,result);
 const frames:string[]=[], stream=new ResponsesStream(t,x=>frames.push(x));
 for(const data of [{choices:[{delta:{tool_calls:[{index:0,id:'status-next',type:'function',function:{name:alias,arguments:arguments_}}]},finish_reason:'tool_calls'}]},{choices:[],usage:{prompt_tokens:1,completion_tokens:1}}])stream.push(Buffer.from(`data: ${JSON.stringify(data)}\n\n`));
 stream.push(Buffer.from('data: [DONE]\n\n'));stream.end();
 const item=frames.map(v=>JSON.parse(v.split('\ndata: ')[1]!)).find(v=>v.type==='response.output_item.done').item;
 assert.equal(item.namespace,'mcp__image');assert.equal(item.name,'image_status');assert.equal(item.arguments,arguments_);
});
