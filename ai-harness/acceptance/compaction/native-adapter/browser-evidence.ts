import {sha256,stableJson,identifier} from './projection.js';
/** Whitelist CDP event fields at ingestion: cookies/auth/request headers are
 * excluded before any persistence. Actual browser network IDs remain observed. */
export function projectBrowserNetwork(method:string,event:any,origin:string,sessionId:string){
 if(!identifier(sessionId))throw Error('browser_owned_session_required');
 const path=`/api/sessions/${encodeURIComponent(sessionId)}/events`;
 if(method==='Network.requestWillBeSent'){
  const url=new URL(event.request?.url);if(url.origin!==new URL(origin).origin||url.pathname!==path)return undefined;
  if(event.request.method!=='GET'||!/^\?after=\d+$/.test(url.search)||typeof event.requestId!=='string')throw Error('browser_sse_request_unqualified');
  return {method,requestId:event.requestId,path:url.pathname+url.search,requestMethod:'GET',timestamp:event.timestamp};
 }
 if(method==='Network.eventSourceMessageReceived'){
  if(typeof event.requestId!=='string'||typeof event.eventId!=='string'||typeof event.eventName!=='string'||typeof event.data!=='string'||Buffer.byteLength(event.data)>1024*1024)throw Error('browser_sse_message_unqualified');
  const value=JSON.parse(event.data);if(value.sessionId!==sessionId)return undefined;
  return {method,requestId:event.requestId,eventId:event.eventId,eventName:event.eventName,data:event.data,timestamp:event.timestamp};
 }
 return undefined;
}
export function verifyBrowserReconnectReceipt(receiptUtf8:string,sessionId:string){
 try{const r=JSON.parse(receiptUtf8);if(r.source!=='owned-protected-browser-sse-reconnect'||r.sessionId!==sessionId||!Array.isArray(r.events))throw Error();
  const requests=r.events.filter((e:any)=>e.method==='Network.requestWillBeSent'),messages=r.events.filter((e:any)=>e.method==='Network.eventSourceMessageReceived');if(requests.length!==2||requests[0].requestId===requests[1].requestId||requests.some((q:any)=>q.requestMethod!=='GET'||q.path.split('?')[0]!==`/api/sessions/${encodeURIComponent(sessionId)}/events`))throw Error();
  let cursor=Number(requests[0].path.split('?after=')[1]);if(!Number.isSafeInteger(cursor)||cursor<0)throw Error();
  for(let index=0;index<2;index++){const q=requests[index];if(Number(q.path.split('?after=')[1])!==cursor)throw Error();const frames=messages.filter((m:any)=>m.requestId===q.requestId);if(!frames.length)throw Error();for(const frame of frames){const e=JSON.parse(frame.data);if(e.sessionId!==sessionId||e.id!==Number(frame.eventId)||e.id<=cursor||e.type!==frame.eventName||frame.timestamp<q.timestamp)throw Error();cursor=e.id;}}
  return {status:'SOURCE_VALID',receiptSha256:sha256(receiptUtf8),cursor,nativeAcceptance:'NOT_TESTED'};
 }catch{return {status:'FAIL',errors:['actual-browser-sse-network-identity-cursor-binding'],nativeAcceptance:'NOT_TESTED'};}
}
export function verifyBrowserHumanReceipt(receiptUtf8:string,sessionId:string,proposalId:string,expectedVersion:string|null){
 try{const r=JSON.parse(receiptUtf8),body=JSON.parse(r.requestBodyUtf8);if(r.source!=='owned-protected-browser-memory-review'||r.sessionId!==sessionId||r.requestPath!==`/api/sessions/${encodeURIComponent(sessionId)}/memory/accept`||r.method!=='POST'||r.status!==200||body.proposalId!==proposalId||body.expectedVersion!==expectedVersion||Object.keys(body).sort().join()!=='expectedVersion,proposalId'||typeof r.actionReceiptUtf8!=='string')throw Error();const click=JSON.parse(r.actionReceiptUtf8);if(click.action!=='click'||click.role!=='button'||click.name!=='Accept reviewed proposal'||!Number.isFinite(click.observedAtMs))throw Error();if(r.requestId!==r.responseRequestId||typeof r.requestId!=='string'||!Array.isArray(click.cdpCalls)||click.cdpCalls.length<2)throw Error();const calls=click.cdpCalls.slice(-2).map((c:any)=>{if(sha256(c.requestUtf8)!==c.requestSha256||typeof c.responseUtf8!=='string')throw Error();const q=JSON.parse(c.requestUtf8),a=JSON.parse(c.responseUtf8);if(q.id!==a.id||a.error||q.method!=='Input.dispatchMouseEvent'||q.params.button!=='left'||q.params.clickCount!==1)throw Error();return q.params;});if(calls[0].type!=='mousePressed'||calls[1].type!=='mouseReleased'||calls[0].x!==calls[1].x||calls[0].y!==calls[1].y||!Number.isFinite(calls[0].x)||!Number.isFinite(calls[0].y))throw Error();return {status:'SOURCE_VALID',receiptSha256:sha256(receiptUtf8),nativeAcceptance:'NOT_TESTED'};
 }catch{return {status:'FAIL',errors:['actual-protected-human-browser-review-binding'],nativeAcceptance:'NOT_TESTED'};}
}
