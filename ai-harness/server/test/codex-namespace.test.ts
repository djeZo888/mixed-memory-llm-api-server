import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { translateResponses, ResponsesStream } from '../src/codex-responses.js';
const fixture = () => JSON.parse(readFileSync(new URL('./fixtures/codex/native-namespace.json', import.meta.url),'utf8'));
test('actual pinned native namespace history and returned calls preserve the tuple', () => {
 const b=fixture(), t=translateResponses(b); const mapped='sova_ns_14_multi_agent_v1_spawn_agent';
 assert.ok(t.body.tools.some((v:any)=>v.function.name===mapped));
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
