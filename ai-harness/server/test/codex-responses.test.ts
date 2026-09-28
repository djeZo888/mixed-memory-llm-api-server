import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { translateResponses, ResponsesStream, validPatch } from "../src/codex-responses.js";
const captures=JSON.parse(readFileSync(new URL("./fixtures/codex/native-requests.json",import.meta.url),"utf8"));
const request=()=>structuredClone(captures[0].body);
const parse=(s:string)=>s.split("\n").filter(l=>l.startsWith("data: ")).map(l=>JSON.parse(l.slice(6)));
const chunk=(v:unknown)=>Buffer.from(`data: ${JSON.stringify(v)}\n\n`);
test("real pinned macOS CLI first and second request preserve instructions and history",()=>{
 for(const capture of captures){const t=translateResponses(capture.body);assert.equal(t.body.max_tokens,65536);assert.equal(t.body.messages[0].role,"system");assert.equal(t.body.messages[1].role,"developer");assert.equal(t.tools.get("apply_patch")?.custom,true);assert.equal(t.body.messages.length,capture.body.input.length+1);}
 const second=translateResponses(captures[1].body);assert.ok(second.body.messages.some((m:any)=>m.role==="assistant"&&m.content==="Fixture complete."));
});
test("unsupported fields, media, encrypted state, arbitrary grammar and settings fail before dispatch",()=>{
 for(const change of [(b:any)=>b.previous_response_id="resp_x",(b:any)=>b.input.push({type:"reasoning",encrypted_content:"not-real"}),(b:any)=>b.input[0].content=[{type:"input_image",image_url:"x"}],(b:any)=>b.reasoning={effort:"high"},(b:any)=>b.tools.find((t:any)=>t.type==="custom").format.definition="start: ANY",(b:any)=>b.max_output_tokens=65537,(b:any)=>b.temperature=.2]){const b=request();change(b);assert.throws(()=>translateResponses(b));}
});
test("two unique calls/results and second turn preserve IDs and custom text exactly",()=>{
 const b=request();const patch="*** Begin Patch\n*** Add File: example.txt\n+one\n*** End Patch\n";
 b.input.push({type:"function_call",call_id:"call_A",name:"get_goal",arguments:"{}"},{type:"custom_tool_call",call_id:"call_B",name:"apply_patch",input:patch},{type:"function_call_output",call_id:"call_A",output:"no goal"},{type:"custom_tool_call_output",call_id:"call_B",output:[{type:"input_text",text:"done"}]},{type:"message",role:"user",content:[{type:"input_text",text:"Continue"}]});
 const t=translateResponses(b);const calls=t.body.messages.find((m:any)=>m.tool_calls)?.tool_calls;assert.deepEqual(calls.map((c:any)=>c.id),["call_A","call_B"]);assert.equal(JSON.parse(calls[1].function.arguments).input,patch);assert.deepEqual(t.body.messages.filter((m:any)=>m.role==="tool").map((m:any)=>m.tool_call_id),["call_A","call_B"]);
 b.input.at(-2).call_id="call_A";assert.throws(()=>translateResponses(b));
});
test("SSE text Unicode deltas, ordered completion and actual usage",()=>{
 let wire="";const s=new ResponsesStream(translateResponses(request()),x=>wire+=x);
 const bytes=chunk({choices:[{index:0,delta:{content:"žHello"},finish_reason:null}]});for(const byte of bytes)s.push(Buffer.from([byte]));
 s.push(chunk({choices:[{index:0,delta:{},finish_reason:"stop"}]}));s.push(chunk({choices:[],usage:{prompt_tokens:42,completion_tokens:3,prompt_tokens_details:{cached_tokens:7}}}));s.push(Buffer.from("data: [DONE]\n\n"));s.end();const e=parse(wire);assert.equal(e[0].type,"response.created");assert.deepEqual(e.map(x=>x.sequence_number),e.map((_,i)=>i));assert.equal(e.at(-1).type,"response.completed");assert.equal(e.at(-1).response.output[0].content[0].text,"žHello");assert.equal(e.at(-1).response.usage.input_tokens,42);assert.equal(e.at(-1).response.output[0].phase,undefined);
});
test("SSE distinct function and custom tool deltas reconstruct losslessly",()=>{
 let wire="";const s=new ResponsesStream(translateResponses(request()),x=>wire+=x);const patch="*** Begin Patch\n*** Add File: a.txt\n+a\n*** End Patch\n";
 s.push(chunk({choices:[{delta:{tool_calls:[{index:0,id:"call1",type:"function",function:{name:"get_goal",arguments:"{"}},{index:1,id:"call2",type:"function",function:{name:"apply_patch",arguments:JSON.stringify({input:patch})}}]}}]}));
 s.push(chunk({choices:[{delta:{tool_calls:[{index:0,function:{arguments:"}"}}]}}]}));s.push(chunk({choices:[{delta:{},finish_reason:"tool_calls"}]}));s.push(chunk({choices:[],usage:{prompt_tokens:50,completion_tokens:20}}));s.push(Buffer.from("data: [DONE]\n\n"));s.end();const e=parse(wire),out=e.at(-1).response.output;assert.deepEqual(out.map((x:any)=>x.call_id),["call1","call2"]);assert.equal(out[1].type,"custom_tool_call");assert.equal(out[1].input,patch);assert.equal(out[0].arguments,"{}");
});
test("truncated/no-usage/real unqualified reasoning never pretends terminal success",()=>{
 for(const chunks of [[{choices:[{delta:{content:"partial"}}]}],[{choices:[{delta:{},finish_reason:"stop"}]}],[{choices:[{delta:{reasoning_content:"unqualified"}}]}]]){const s=new ResponsesStream(translateResponses(request()),()=>{});assert.throws(()=>{chunks.forEach(c=>s.push(chunk(c)));s.push(Buffer.from("data: [DONE]\n\n"));s.end();});}
});
test("pinned patch grammar validates hunks and rejects arbitrary custom syntax",()=>{
 assert.ok(validPatch("*** Begin Patch\n*** Update File: a\n@@ old\n-x\n+y\n*** End of File\n*** End Patch\n"));
 for(const p of ["", "*** Begin Patch\n*** Add File: a\n*** End Patch\n", "*** Begin Patch\n*** Update File: a\n*** End of File\n*** End Patch\n"])assert.equal(validPatch(p),false);
});
test("valid final delta+finish, trailing SSE whitespace and empty reasoning remain supported",()=>{
 let wire="";const s=new ResponsesStream(translateResponses(request()),x=>wire+=x);s.push(chunk({choices:[{delta:{content:"final",reasoning_content:null},finish_reason:"stop"}]}));s.push(chunk({choices:[],usage:{prompt_tokens:1,completion_tokens:1}}));s.push(Buffer.from("data: [DONE]\n"));s.push(Buffer.from("\n\r\n"));s.end();assert.equal(parse(wire).at(-1).response.output[0].content[0].text,"final");assert.throws(()=>s.push(Buffer.from("data: {}\n")));
 const b=request();b.model="__proto__";assert.throws(()=>translateResponses(b));
});
test("interleaved parallel tool/result ordering rejects before generating invalid chat",()=>{
 const b=request();b.input.push({type:"function_call",call_id:"a",name:"get_goal",arguments:"{}"},{type:"function_call",call_id:"b",name:"get_goal",arguments:"{}"},{type:"function_call_output",call_id:"a",output:"ok"},{type:"function_call",call_id:"c",name:"get_goal",arguments:"{}"});assert.throws(()=>translateResponses(b));
});
test("all actual native five-request tool/edit/read/continuation captures translate without dropping results",()=>{
 const all=JSON.parse(readFileSync(new URL('./fixtures/codex/native-tool-continuation.json',import.meta.url),'utf8'));assert.equal(all.length,5);all.forEach((b:any)=>assert.doesNotThrow(()=>translateResponses(b)));const last=translateResponses(all.at(-1));assert.ok(last.body.messages.some((m:any)=>m.role==='tool'&&m.tool_call_id==='call_native_read'&&m.content.includes('native followup read PASS')));assert.equal(last.body.reasoning_effort,'none');assert.equal(translateResponses(request(),1024).body.max_tokens,1024);
});
