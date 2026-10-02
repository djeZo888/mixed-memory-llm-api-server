import test from 'node:test';
import assert from 'node:assert/strict';
import {fileURLToPath} from 'node:url';
import {Client} from '../../image/node_modules/@modelcontextprotocol/sdk/dist/esm/client/index.js';
import {StdioClientTransport} from '../../image/node_modules/@modelcontextprotocol/sdk/dist/esm/client/stdio.js';
import {configuredToken,analyzeInput,createTechnicalVisionClient} from '../technical-vision.mjs';
const token='private-fixture-token';
const journal=(handle,requestId,state='completed',settled=true)=>({handle,originalRunId:'original-run',requestId,revision:2,state,settled,terminalDelivered:settled,response:envelope(handle,state,settled).response});
const envelope=(handle,state,settled)=>({handle,response:{content:[{type:'text',text:JSON.stringify({handle,job:{state,settled},observation:settled?'settled':'pending'})}]}});
test('fixed authenticated normal gateway rejects owner/endpoint/raw pixel/traversal arguments',async()=>{
 for(const input of [{requestId:'r',source:{workspacePath:'../secret'}},{requestId:'r',source:{fileId:'f'},owner:{}},{requestId:'r',source:{fileId:'f'},pages:[1,2]},{requestId:'r',source:{url:'http://other'}}])assert.equal(analyzeInput.safeParse(input).success,false);
 assert.throws(()=>configuredToken({AI_HARNESS_GATEWAY_TOKEN:token,AI_HARNESS_GATEWAY_URL:'http://other'}));
 const calls=[],client=createTechnicalVisionClient({token,fetchImpl:async(url,options)=>{calls.push({url,options});return new Response(JSON.stringify(url.endsWith('/journal')?journal('h','r'):envelope('h','completed',true)),{status:200});}});
 const r=await client.analyze({requestId:'r',source:{fileId:'f'}});assert.equal(r.handle,'h');assert.equal(calls.length,2);assert.equal(calls[0].url,'http://10.0.2.2:8081/v1/technical-vision-jobs');assert.equal(calls[0].options.headers.authorization,'Bearer '+token);assert.equal(calls[0].options.redirect,'error');assert.deepEqual(JSON.parse(calls[0].options.body),{requestId:'r',source:{fileId:'f'}});
});
test('pending normal job is finitely followed by original handle, no resubmit/creative route',async()=>{
 const calls=[],client=createTechnicalVisionClient({token,fetchImpl:async(url,options)=>{calls.push({url,options});return new Response(JSON.stringify(url.endsWith('/journal')?journal('original','same',calls.length===2?'queued':'completed',calls.length>2):envelope('original','queued',false)),{status:200});}});
 const r=await client.analyze({requestId:'same',source:{fileId:'file'}});assert.equal(JSON.parse(r.response.content[0].text).job.settled,true);assert.deepEqual(calls.map(c=>c.url),['http://10.0.2.2:8081/v1/technical-vision-jobs','http://10.0.2.2:8081/v1/technical-vision-jobs/original/journal','http://10.0.2.2:8081/v1/technical-vision-jobs/original/status','http://10.0.2.2:8081/v1/technical-vision-jobs/original/journal']);assert.deepEqual(JSON.parse(calls[1].options.body),{});
 for(const action of ['status','lookup','cancel'])await client.followup(action,{handle:'original'});assert.deepEqual(calls.slice(4).map(c=>c.url.split('/').at(-1)),['status','journal','lookup','journal','cancel','journal']);
});
test('foreign handle response, native pixel claim, token leak and HTTP errors stay closed',async()=>{
 for(const body of [{available:true,nativeCodexPixels:true},{available:true,nativeCodexPixels:false,reason:token}]){const client=createTechnicalVisionClient({token,fetchImpl:async()=>new Response(JSON.stringify(body))});await assert.rejects(client.capabilities({query:'capabilities'}));}
 const client=createTechnicalVisionClient({token,fetchImpl:async()=>new Response('{}',{status:404})});await assert.rejects(client.followup('status',{handle:'foreign'}),e=>e.code==='not_found');
});
test('actual trusted stdio initialize/list advertises only technical tools without inference',async()=>{
 const transport=new StdioClientTransport({command:process.execPath,args:[fileURLToPath(new URL('../technical-vision-mcp.mjs',import.meta.url))],env:{PATH:'/usr/bin:/bin',AI_HARNESS_GATEWAY_TOKEN:token},stderr:'pipe'}),client=new Client({name:'source-fixture',version:'1'});
 try{await client.connect(transport);const list=await client.listTools();assert.deepEqual(list.tools.map(t=>t.name).sort(),['technical_image_analyze','technical_vision_cancel','technical_vision_capabilities','technical_vision_lookup','technical_vision_status']);assert.equal(list.tools.some(t=>t.name.startsWith('image_')),false);}finally{await client.close();await transport.close();}
});

test('cancellation ACK and aborted observer cannot replace original remote journal settlement',async()=>{
 const calls=[],controller=new AbortController(),client=createTechnicalVisionClient({token,fetchImpl:async(url,options)=>{
   calls.push(url);assert.ok(options.signal instanceof AbortSignal);
   return new Response(JSON.stringify(url.endsWith('/journal')?journal('original','same','cancelling',false):envelope('original','completed',true)));
 }});
 const result=await client.followup('cancel',{handle:'original'},controller.signal);
 assert.equal(result.response.isError,true);assert.equal(result.journal.originalRunId,'original-run');assert.equal(result.journal.settled,false);
 assert.equal(JSON.parse(result.response.content[0].text).settled,false);assert.equal(calls.length,2);
 controller.abort();await assert.rejects(client.analyze({requestId:'same',source:{fileId:'f'}},controller.signal),e=>e.code==='observation_unknown');
});
test('journal original run/request drift is refused after normal original-handle status',async()=>{
 let reads=0;const client=createTechnicalVisionClient({token,fetchImpl:async url=>new Response(JSON.stringify(url.endsWith('/journal')?{...journal('original','same','running',false),originalRunId:++reads===1?'original-run':'foreign'}:envelope('original','running',false)))});
 const result=await client.analyze({requestId:'same',source:{fileId:'f'}});
 assert.equal(result.response.isError,true);assert.equal(JSON.parse(result.response.content[0].text).settlement,'unknown');
});
