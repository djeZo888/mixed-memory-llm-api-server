import { z } from '../image/node_modules/zod/index.js';
export const GATEWAY = 'http://10.0.2.2:8081/v1';
const id = z.string().regex(/^[a-zA-Z0-9_-]{1,80}$/);
const relative = z.string().min(1).max(1000).refine(v => !/[\\:%?#\p{Cc}\p{Cf}]/u.test(v) && !v.startsWith('/') && v.split('/').every(p=>p && p!=='.' && p!=='..' && p!=='~'));
const page = z.number().int().min(1).max(10000);
export const analyzeInput = z.object({requestId:id,source:z.union([z.object({fileId:id}).strict(),z.object({workspacePath:relative}).strict()]),pages:z.array(page).min(1).max(1).optional(),crops:z.array(z.object({id,page,x:z.number().int().min(0),y:z.number().int().min(0),width:z.number().int().min(1),height:z.number().int().min(1)}).strict()).max(8).optional(),question:z.string().min(1).max(4000).optional()}).strict();
export const handleInput = z.object({handle:id}).strict();
export const capabilitiesInput = z.object({query:z.literal('capabilities')}).strict();
export function configuredToken(env) {
  const token=env.AI_HARNESS_GATEWAY_TOKEN;
  if ((env.AI_HARNESS_GATEWAY_URL!==undefined && env.AI_HARNESS_GATEWAY_URL!==GATEWAY) || typeof token!=='string' || token.length<16 || token.length>4096 || /[\p{Cc}\p{Cf}]/u.test(token))throw Error('Invalid session gateway configuration');
  return token;
}
export class VisionToolError extends Error {constructor(code){super('Technical image analysis could not be completed. Retain the original request and job handle; do not resubmit uncertain work.');this.code=code;}}
export function createTechnicalVisionClient({token,fetchImpl=fetch}) {
  configuredToken({AI_HARNESS_GATEWAY_TOKEN:token});
  async function call(path,body,signal) {
    if(signal?.aborted)throw new VisionToolError('observation_unknown');
    let response;
    try {response=await fetchImpl(GATEWAY+path,{method:body===undefined?'GET':'POST',headers:{authorization:`Bearer ${token}`,...(body===undefined?{}:{'content-type':'application/json'})},...(body===undefined?{}:{body:JSON.stringify(body)}),redirect:'error',signal:AbortSignal.any([signal??new AbortController().signal,AbortSignal.timeout(35000)])});}catch{throw new VisionToolError('observation_unknown');}
    if(!response.ok)throw new VisionToolError(response.status===404?'not_found':response.status===403?'ownership_rejected':'unavailable');
    if(!response.body)throw new VisionToolError('invalid_response');
    const reader=response.body.getReader(), chunks=[];let bytes=0;
    try {while(true){const chunk=await reader.read();if(chunk.done)break;bytes+=chunk.value.byteLength;if(bytes>1048576+16384)throw new VisionToolError('invalid_response');chunks.push(chunk.value);}}finally{await reader.cancel().catch(()=>{});}
    let raw;try{raw=new TextDecoder('utf-8',{fatal:true}).decode(Buffer.concat(chunks));}catch{throw new VisionToolError('invalid_response');}if(raw.includes(token))throw new VisionToolError('invalid_response');
    let value;try{value=JSON.parse(raw);}catch{throw new VisionToolError('invalid_response');}
    if(path==='/technical-vision-capabilities') {
      if(typeof value?.available!=='boolean' || value.nativeCodexPixels!==false)throw new VisionToolError('invalid_response');
      return {available:value.available,nativeCodexPixels:false,qualification:value.qualification,caps:value.caps,formats:value.formats,pdf:value.pdf,reason:value.reason};
    }
    if(path.endsWith('/journal')) {
      if(!handleInput.safeParse({handle:value?.handle}).success || typeof value.originalRunId!=='string' || !id.safeParse(value.requestId).success || !Number.isSafeInteger(value.revision) || value.revision<0 || typeof value.state!=='string' || typeof value.settled!=='boolean' || typeof value.terminalDelivered!=='boolean')throw new VisionToolError('invalid_response');
      if(value.response && (!Array.isArray(value.response.content) || value.response.content.length!==1 || value.response.content[0].type!=='text' || typeof value.response.content[0].text!=='string'))throw new VisionToolError('invalid_response');
      return {handle:value.handle,originalRunId:value.originalRunId,requestId:value.requestId,revision:value.revision,state:value.state,settled:value.settled,terminalDelivered:value.terminalDelivered,...(value.response?{response:value.response}:{})};
    }
    if(!handleInput.safeParse({handle:value?.handle}).success || !Array.isArray(value.response?.content) || value.response.content.length!==1 || value.response.content[0].type!=='text' || typeof value.response.content[0].text!=='string')throw new VisionToolError('invalid_response');
    return {handle:value.handle,response:{...(value.response.isError?{isError:true}:{}),content:[{type:'text',text:value.response.content[0].text}]}};
  }
  const rawFollowup=(action,input,signal)=>{if(!['status','lookup','cancel'].includes(action))throw new VisionToolError('invalid_request');const {handle}=handleInput.parse(input);return call(`/technical-vision-jobs/${handle}/${action}`,{},signal);};
  const journalStatus=(handle,signal)=>call(`/technical-vision-jobs/${handle}/journal`,{},signal);
  const observed = (result,journal) => {
    if(result.handle!==journal.handle)throw new VisionToolError('invalid_response');
    if(journal.settled && journal.terminalDelivered && ['completed','failed','cancelled','interrupted'].includes(journal.state) && journal.response)
      return {handle:journal.handle,journal,response:{...journal.response,...(journal.state!=='completed'?{isError:true}:{})}};
    return {handle:result.handle,journal,response:{isError:true,content:[{type:'text',text:JSON.stringify({handle:journal.handle,originalRunId:journal.originalRunId,requestId:journal.requestId,revision:journal.revision,state:journal.state,settled:false,terminalDelivered:journal.terminalDelivered,instruction:'Original remote work remains unsettled. Preserve this handle and use status/lookup; no OCR completion or resubmission.'})}]}};
  };
  const followup=async(action,input,signal)=>{const r=await rawFollowup(action,input,signal);return observed(r,await journalStatus(r.handle,signal));};
  async function analyze(input,signal) {
    const parsed=analyzeInput.parse(input);
    let result=await call('/technical-vision-jobs',parsed,signal);
    let journal=await journalStatus(result.handle,signal);
    const originalRunId=journal.originalRunId,requestId=journal.requestId;
    if(requestId!==parsed.requestId)return observed(result,{...journal,settled:false});
    // Finite observation of the original handle only. No repeat submission/new owner.
    const originalHandle=result.handle,deadline=Date.now()+20000;
    for(let reads=0;reads<8 && Date.now()<deadline;reads++) {
      if(journal.settled && journal.terminalDelivered)return observed(result,journal);
      if(signal?.aborted)throw new VisionToolError('observation_unknown');
      const observing=AbortSignal.any([signal??new AbortController().signal,AbortSignal.timeout(Math.max(1,deadline-Date.now()))]);
      await new Promise((resolve,reject)=>{const timer=setTimeout(done,1000);function done(){observing.removeEventListener('abort',abort);resolve();}function abort(){clearTimeout(timer);reject(new VisionToolError('observation_unknown'));}if(observing.aborted)abort();else observing.addEventListener('abort',abort,{once:true});});
      try{result=await rawFollowup('status',{handle:originalHandle},observing);journal=await journalStatus(originalHandle,observing);if(journal.originalRunId!==originalRunId || journal.requestId!==requestId)throw new VisionToolError('invalid_response');}catch(error){const prior=JSON.parse(result.response.content[0].text);result.response={isError:true,content:[{type:'text',text:JSON.stringify({...prior,observationError:{code:error instanceof VisionToolError?error.code:'observation_unknown',message:'Status observation ended; original pending work is retained.'},settlement:'unknown'})}]};return result;}
      if(result.handle!==originalHandle)throw new VisionToolError('invalid_response');
    }
    return observed(result,journal); // Pending/unknown is explicitly not OCR completion.
  }
  return {capabilities:(input,signal)=>{capabilitiesInput.parse(input);return call('/technical-vision-capabilities',undefined,signal);},analyze,followup};
}
