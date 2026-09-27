/** Thin H009 wire hook: preserve actual full tools and production output ceiling. */
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
export const FLASH='mimo-v2.6-pro-rl'; // compatibility name for unchanged H009 hook
export const RETAIN_FLASH=Object.freeze(['read','write','edit','bash','grep','glob']);
export const sha=v=>createHash('sha256').update(typeof v==='string'||Buffer.isBuffer(v)?v:JSON.stringify(v)).digest('hex');
export function createGuards({record,capture,persist,getMode,resolveSession,toolsSha256}) {
 return {
  async preValidation(req) {
   const route=req.routeOptions.url;
   if(!['/frontier/v1/chat/completions','/v1/chat/completions'].includes(route))return;
   const frontier=route.startsWith('/frontier/'),original=structuredClone(req.body);
   assert.equal(getMode(),'full-live','closed admission');
   if(frontier){
    assert.equal(original.model,FLASH);
    assert.equal(original.max_tokens??original.max_completion_tokens,65536);
    assert.equal(original.tools?.length,17,'actual full production roster required');
    assert.equal(sha(original.tools),toolsSha256,'frozen production tool schemas changed');
   }
   const metadata={requestId:req.id,sessionId:resolveSession(req),route,mode:frontier?'full-live':'qwen',retained:(original.tools??[]).map(t=>t.function.name),removed:[],originalToolsSha256:sha(original.tools??[]),effectiveToolsSha256:sha(original.tools??[])};
   capture(original,req.body,metadata);record({event:'pre-count',...metadata});
  },
  onRequestState(r) {
   persist(r);record({event:'frontier-state',...r});
   if(r.state==='active'){
    assert.equal(getMode(),'full-live');
    assert(Number.isSafeInteger(r.promptTokens)&&r.promptTokens>0&&r.promptTokens<16384,'small input admission only');
    assert.equal(r.reservedOutput,65536,'requested ceiling is not completed output proof');
   }
  }
 };
}
