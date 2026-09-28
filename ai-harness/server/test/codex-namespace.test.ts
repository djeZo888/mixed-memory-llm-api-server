import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { translateResponses, ResponsesStream } from '../src/codex-responses.js';
const fixture = () => JSON.parse(readFileSync(new URL('./fixtures/codex/native-namespace.json', import.meta.url),'utf8'));
test('actual pinned native namespace history and returned calls preserve the tuple', () => {
 const b=fixture(), t=translateResponses(b); const mapped='sova_ns_14_multi_agent_v1_spawn_agent';
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
 for(const mutate of [(b:any)=>b.tools.push(b.tools.find((t:any)=>t.type==='namespace')),(b:any)=>b.tools.find((t:any)=>t.type==='namespace').tools.push({type:'namespace',name:'nested'}),(b:any)=>b.tools[0].name='sova_ns_14_multi_agent_v1_spawn_agent',(b:any)=>b.input[0].namespace='unqualified']) {
  const b=fixture();mutate(b);assert.throws(()=>translateResponses(b));
 }
});
test('actual Linux MCP namespace catalog and calls retain scoped identities',()=>{
 const b=JSON.parse(readFileSync(new URL('./fixtures/codex/native-mcp-namespaces.json',import.meta.url),'utf8'));
 for(const ns of b.tools) for(const f of ns.tools){
  const request=structuredClone(b);request.input.push({type:'function_call',call_id:'mcp-call',namespace:ns.name,name:f.name,arguments:'{}'},{type:'function_call_output',call_id:'mcp-call',output:'fixture result'});
  const t=translateResponses(request),mapped=`sova_ns_${ns.name.length}_${ns.name}_${f.name}`;
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
  const mapped=`sova_ns_10_mcp__image_${name}`;
  assert.ok(t.body.tools.some((v:any)=>v.function.name===mapped));
  const call=t.body.messages.find((v:any)=>v.tool_calls?.[0]?.id==='owned-'+name);assert.equal(call.tool_calls[0].function.name,mapped);
  const result=t.body.messages.find((v:any)=>v.tool_call_id==='owned-'+name);assert.match(result.content,/owned-job/);
  const frames:string[]=[];const stream=new ResponsesStream(t,x=>frames.push(x));
  for(const v of [{choices:[{delta:{tool_calls:[{index:0,id:'returned-'+name,type:'function',function:{name:mapped,arguments:'{}'}}]},finish_reason:'tool_calls'}]},{choices:[],usage:{prompt_tokens:12,completion_tokens:2}}])stream.push(Buffer.from(`data: ${JSON.stringify(v)}\n\n`));stream.push(Buffer.from('data: [DONE]\n\n'));stream.end();
  const item=frames.map(v=>JSON.parse(v.split('\ndata: ')[1]!)).find(v=>v.type==='response.output_item.done').item;
  assert.equal(item.namespace,'mcp__image');assert.equal(item.name,name);assert.equal(item.call_id,'returned-'+name);
 }
});
