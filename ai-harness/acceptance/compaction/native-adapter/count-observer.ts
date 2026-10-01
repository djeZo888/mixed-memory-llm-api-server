import type {GatewayOptions} from '../../../server/src/gateway.js';
import {join} from 'node:path';
import {durableFile} from './checkpoint.js';
import {identifier,sha256,stableJson} from './projection.js';
type Counter=NonNullable<GatewayOptions['responses']>['countQwen'];
/** Capture the actual qualified callback's complete translated input/result while
 * dispatch is held. Diagnostics cannot supply counts; callers cannot insert IDs. */
export class NativeCountObserver {
 private pending=new Set<string>();
 private entries=new Map<string,Readonly<Record<string,any>>>();
 constructor(private directory:string){}
 wrap(counter:Counter):Counter{return async(body,lane,key,signal,context)=>{
  const requestId=context?.requestId;if(!identifier(requestId)||(this.entries.has(requestId)||this.pending.has(requestId))||signal.aborted||lane.alias!=='qwen3.8-27b')throw Error('actual_unique_count_admission_required');
  this.pending.add(requestId);try{
  const requestUtf8=JSON.stringify(body),startedAt=new Date().toISOString(),result=await counter(body,lane,key,signal,context);
  if(signal.aborted||stableJson(body)!==stableJson(JSON.parse(requestUtf8))||!Number.isSafeInteger(result.inputTokens)||result.inputTokens<0||result.contextWindow!==480000||body.max_tokens!==65536)throw Error('actual_complete_input_count_result_required');
  const receiptUtf8=stableJson({source:'host-qualified-qwen-count-callback',requestId,lane:lane.alias,phase:context!.phase,startedAt,completedAt:new Date().toISOString(),requestUtf8,requestSha256:sha256(requestUtf8),resultUtf8:JSON.stringify(result),inputTokens:result.inputTokens,contextWindow:result.contextWindow,maxOutput:body.max_tokens});
  await durableFile(join(this.directory,`${requestId}-qualified-count.json`),receiptUtf8);
  this.entries.set(requestId,Object.freeze({requestId,input:result.inputTokens,contextWindow:result.contextWindow,maxOutput:body.max_tokens,receiptUtf8,receiptSha256:sha256(receiptUtf8)}));return result;
  }finally{this.pending.delete(requestId);}
 };}
 async retainVerifiedEvent(event:any,signal:AbortSignal){const requestId=event.context?.requestId;if(!identifier(requestId)||this.entries.has(requestId)||signal.aborted||event.lane!=='qwen3.8-27b'||sha256(JSON.stringify(event.body))!==event.bodySha256||!Number.isSafeInteger(event.result?.inputTokens)||event.result.contextWindow!==480000||event.body.max_tokens!==65536)throw Error('actual_A_verified_count_event_required');const completedAt=new Date().toISOString(),requestUtf8=JSON.stringify(event.body),receiptUtf8=stableJson({source:'host-qualified-qwen-count-callback',requestId,lane:event.lane,phase:event.context.phase,startedAt:completedAt,completedAt,requestUtf8,requestSha256:event.bodySha256,resultUtf8:JSON.stringify(event.result),inputTokens:event.result.inputTokens,contextWindow:event.result.contextWindow,maxOutput:event.body.max_tokens});await durableFile(join(this.directory,`${requestId}-qualified-count.json`),receiptUtf8);if(signal.aborted)throw Error('actual_count_capture_cancelled');this.entries.set(requestId,Object.freeze({requestId,input:event.result.inputTokens,contextWindow:event.result.contextWindow,maxOutput:event.body.max_tokens,receiptUtf8,receiptSha256:sha256(receiptUtf8)}));}
 receipts(ids:readonly string[]){if(new Set(ids).size!==ids.length)throw Error('count_request_ids_duplicate');return ids.map(id=>{const value=this.entries.get(id);if(!value)throw Error('actual_count_capture_absent');return structuredClone(value);});}
}
