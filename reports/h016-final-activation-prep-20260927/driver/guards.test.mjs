import test from 'node:test';import assert from 'node:assert/strict';
import {createGuards,sha,FLASH} from './guards.mjs';
test('full actual tools/output preserved; malformed roster and oversized input close admission',async()=>{
 const tools=Array.from({length:17},(_,i)=>({type:'function',function:{name:'fixture'+i,parameters:{type:'object',properties:{}}}}));
 const rows=[];let captured;
 const h=createGuards({record:r=>rows.push(r),capture:(o,e)=>{captured=e;assert.deepEqual(o,e);},persist:r=>rows.push(r),getMode:()=> 'full-live',resolveSession:()=> 'fixture',toolsSha256:sha(tools)});
 const body={model:FLASH,max_tokens:65536,tools};
 await h.preValidation({routeOptions:{url:'/frontier/v1/chat/completions'},body});
 assert.equal(captured,body);assert.equal(body.tools.length,17);assert.equal(body.max_tokens,65536);
 await assert.rejects(h.preValidation({routeOptions:{url:'/frontier/v1/chat/completions'},body:{...body,tools:tools.slice(1)}}));
 await assert.rejects(h.preValidation({routeOptions:{url:'/frontier/v1/chat/completions'},body:{...body,max_tokens:2048}}));
 h.onRequestState({state:'active',promptTokens:9461,reservedOutput:65536});
 assert.throws(()=>h.onRequestState({state:'active',promptTokens:16384,reservedOutput:65536}));
});
