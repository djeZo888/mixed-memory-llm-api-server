// Current normal SSE protocol; unknown event carriers fail closed.
const eventTypes=['message','assistant_delta','progress','context','state','artifact','image_job','run','activity','subagents','error','done','handoff'];
import {randomUUID} from 'node:crypto';
import {join} from 'node:path';
import {durableFile} from './checkpoint.js';
import {identifier,sha256,stableJson} from './projection.js';
/** Protected browser/normal API transport only. Authentication remains in the
 * host-supplied fetch/browser context; headers, cookies and keys are not captured. */
export interface OrdinaryTransport {request(path:string,init:{method:'GET'|'POST';bodyUtf8?:string;signal:AbortSignal}):Promise<{status:number;bodyBytes:Uint8Array}>;}
export class OrdinaryClient {
 constructor(readonly sessionId:string,private transport:OrdinaryTransport,private directory:string){if(!identifier(sessionId))throw Error('owned_ordinary_session_required');}
 async request(suffix:string,method:'GET'|'POST',body:unknown,signal:AbortSignal,expectedStatus:number|number[]=200){
  if(signal.aborted||!/^\/(memory(?:\/|$)|compact$|messages$|events\?after=\d+$)/.test(suffix)||suffix.includes('..')||suffix.includes('#'))throw Error('bounded_owned_ordinary_route_required');
  const path=`/api/sessions/${encodeURIComponent(this.sessionId)}${suffix}`,bodyUtf8=body===undefined?undefined:JSON.stringify(body),startedAt=new Date().toISOString(),result=await this.transport.request(path,{method,bodyUtf8,signal});
  if(!(result.bodyBytes instanceof Uint8Array)||result.bodyBytes.byteLength>32*1024*1024)throw Error('ordinary_response_utf8_or_bound');
  const responseUtf8=new TextDecoder('utf-8',{fatal:true}).decode(result.bodyBytes);
  const receiptUtf8=stableJson({source:'owned-protected-ordinary-http-response',sessionId:this.sessionId,path,method,requestBodyUtf8:bodyUtf8??null,status:result.status,responseUtf8,startedAt,completedAt:new Date().toISOString()});
  const receiptId=randomUUID();await durableFile(join(this.directory,`${receiptId}-ordinary-http.json`),receiptUtf8);
  if(signal.aborted||!(Array.isArray(expectedStatus)?expectedStatus:[expectedStatus]).includes(result.status))throw Error('ordinary_http_status_or_cancellation_no_retry');
  return {value:JSON.parse(responseUtf8),receiptId,receiptUtf8,receiptSha256:sha256(receiptUtf8)};
 }
 async readOriginal(descriptor:any,signal:AbortSignal){
  if(!identifier(descriptor?.id)||descriptor.availability!=='complete'||!Number.isSafeInteger(descriptor.bytes)||descriptor.bytes<1||descriptor.bytes>16*1024*1024||!/^[a-f0-9]{64}$/.test(descriptor.sha256))throw Error('actual_owned_original_descriptor_required');
  let offset=0;const chunks:Buffer[]=[],receipts:string[]=[];
  while(offset<descriptor.bytes){const r=await this.request(`/memory/originals/${encodeURIComponent(descriptor.id)}?offset=${offset}&limit=${Math.min(8192,descriptor.bytes-offset)}`,'GET',undefined,signal),v=r.value,b=Buffer.from(v.text);
   if(v.reference.id!==descriptor.id||v.reference.sha256!==descriptor.sha256||v.reference.bytes!==descriptor.bytes||v.offset!==offset||!Number.isSafeInteger(v.nextOffset)||v.nextOffset<=offset||v.nextOffset>descriptor.bytes||b.length!==v.nextOffset-offset)throw Error('owned_original_response_interval_changed');chunks.push(b);receipts.push(r.receiptSha256);offset=v.nextOffset;
  }
  const bytes=Buffer.concat(chunks);if(bytes.length!==descriptor.bytes||sha256(bytes)!==descriptor.sha256)throw Error('owned_original_full_bytes_hash_changed');return {id:descriptor.id,sha256:sha256(bytes),bytes:bytes.length,receiptSha256s:receipts};
 }
 async searchLiteral(query:string,reference:string,signal:AbortSignal){
  if(!query||Buffer.byteLength(query)>256||!identifier(reference))throw Error('bounded_literal_search_required');
  return this.request('/memory/search','POST',{query,reference,limit:16},signal);
 }
}
/** Independent SSE framing used only for captured normal browser/API evidence.
 * Disconnect closes HTTP streaming; it never sends /cancel or replays a turn. */
export function parseOrdinarySse(bytes:Buffer,sessionId:string,after:number){
 if(!identifier(sessionId)||!Number.isSafeInteger(after)||after<0||bytes.length>8*1024*1024)throw Error('ordinary_sse_scope_or_bound');const text=new TextDecoder('utf-8',{fatal:true}).decode(bytes),events:any[]=[];let cursor=after;
 for(const block of text.replaceAll('\r\n','\n').split('\n\n')){
  if(!block||block.split('\n').every(l=>!l||l.startsWith(':')))continue;
  if(!block.endsWith('\n')&&!text.endsWith('\n\n')&&block===text.split('\n\n').at(-1))throw Error('ordinary_sse_incomplete_frame');
  const lines=block.split('\n'),ids=lines.filter(l=>l.startsWith('id: ')),kinds=lines.filter(l=>l.startsWith('event: ')),data=lines.filter(l=>l.startsWith('data: '));
  if(ids.length!==1||kinds.length!==1||data.length!==1||lines.some(l=>!['id: ','event: ','data: ',':'].some(p=>l.startsWith(p))))throw Error('ordinary_sse_unqualified_carrier');
  const event=JSON.parse(data[0].slice(6)),id=Number(ids[0].slice(4));if(!Number.isSafeInteger(id)||id<=cursor||event.id!==id||event.sessionId!==sessionId||event.type!==kinds[0].slice(7)||!eventTypes.includes(event.type)||!event.data||typeof event.data!=='object')throw Error('ordinary_sse_identity_cursor_or_type');cursor=id;events.push(event);
 }
 return {events,cursor,bytesSha256:sha256(bytes)};
}

/** Host-authenticated fetch supplied by reviewed composition. No credentials
 * are read or manufactured by this helper. */
export function protectedFetchTransport(origin:string,authenticatedFetch:typeof fetch=fetch):OrdinaryTransport{
 const base=new URL(origin);if(base.protocol!=='https:'||base.username||base.password||base.pathname!=='/'||base.search||base.hash)throw Error('reviewed_protected_normal_origin_required');
 return {request:async(path,init)=>{if(!path.startsWith('/api/sessions/'))throw Error('owned_ordinary_path_required');const response=await authenticatedFetch(new URL(path,base),{method:init.method,signal:init.signal,redirect:'error',cache:'no-store',...(init.bodyUtf8===undefined?{}:{headers:{'content-type':'application/json'},body:init.bodyUtf8})});const length=response.headers.get('content-length');if(length&&Number(length)>32*1024*1024)throw Error('ordinary_response_bound');const chunks:Uint8Array[]=[];let bytes=0;for await(const chunk of response.body!){bytes+=chunk.byteLength;if(bytes>32*1024*1024)throw Error('ordinary_response_bound');chunks.push(chunk);}return {status:response.status,bodyBytes:Buffer.concat(chunks)};}};
}
