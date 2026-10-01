import { sha256, stableJson } from './projection.js';
export interface ConsumedToolBinding {tool:'read_original'|'write_checkpoint_artifact';threadId:string;turnId:string;runId:string;checkpointId?:string;frames:any[];settled:any[]}
/** Retained bytes and canonical completion independently bound to one owned turn. */
export function consumedTool(binding:ConsumedToolBinding,callId:string) {
  const settled=binding.settled.filter(s=>s.callId===callId&&s.runId===binding.runId&&s.threadId===binding.threadId&&s.turnId===binding.turnId&&(!binding.checkpointId||s.checkpointId===binding.checkpointId));
  const requests=binding.frames.filter(f=>f.direction==='from-native'&&f.value.method==='item/tool/call'&&f.value.params?.callId===callId);
  const completed=binding.frames.filter(f=>f.direction==='from-native'&&f.value.method==='item/completed'&&f.value.params?.item?.id===callId);
  const started=binding.frames.filter(f=>f.direction==='from-native'&&f.value.method==='item/started'&&f.value.params?.item?.id===callId);
  if(settled.length!==1||requests.length!==1||completed.length!==1||started.length!==1)throw Error('exact_consumed_tool_lifecycle_required');
  const request=requests[0],p=request.value.params,s=settled[0],end=completed[0].value.params,start=started[0].value.params;
  const responses=binding.frames.filter(f=>f.direction==='to-native'&&f.value.id===request.value.id&&f.value.result&&!f.value.error);
  if(responses.length!==1||p.threadId!==binding.threadId||p.turnId!==binding.turnId||p.tool!==binding.tool||p.namespace!=null||start.threadId!==binding.threadId||end.threadId!==binding.threadId||start.turnId!==binding.turnId||end.turnId!==binding.turnId||start.item.type!=='dynamicToolCall'||end.item.type!=='dynamicToolCall'||end.item.tool!==binding.tool||end.item.success!==true||end.item.status!=='completed'||stableJson(end.item.arguments)!==stableJson(p.arguments)||sha256(JSON.stringify(responses[0].value.result))!==s.responseSha256)throw Error('consumed_tool_native_ownership_or_response_mismatch');
  for(const f of [started[0],request,responses[0],completed[0]])if(typeof f.bytesUtf8!=='string'||sha256(f.bytesUtf8)!==f.sha256||stableJson(JSON.parse(f.bytesUtf8))!==stableJson(f.value))throw Error('actual_consumed_tool_bytes_required');
  if(!(started[0].sequence<request.sequence&&request.sequence<responses[0].sequence&&responses[0].sequence<completed[0].sequence))throw Error('consumed_tool_order_mismatch');
  if(binding.tool==='read_original'&&(!s.success||stableJson(s.arguments)!==stableJson(p.arguments)))throw Error('consumed_original_binding_mismatch');
  if(binding.tool==='write_checkpoint_artifact'&&(p.arguments.name!==s.name||sha256(p.arguments.json)!==s.sha256||!s.artifactId))throw Error('consumed_artifact_binding_mismatch');
  return {settled:s,request,response:responses[0],completed:completed[0],started:started[0]};
}
/** A frozen first projection followed only by actually consumed current-turn
 * calls/results and observed assistant messages. No foreign/history carriers. */
export function validateConsumedFollowup(input:unknown,prefix:unknown[],binding:ConsumedToolBinding) {
  if(!Array.isArray(input)||stableJson(input.slice(0,prefix.length))!==stableJson(prefix))throw Error('owned_projection_prefix_changed');
  const pending=new Set<string>(),seen=new Set<string>();
  for(const item of input.slice(prefix.length)) {
    if(item?.type==='function_call') {
      if(Object.keys(item).some(k=>!['type','id','call_id','name','arguments','status'].includes(k))||item.name!==binding.tool||typeof item.call_id!=='string'||pending.has(item.call_id)||seen.has(item.call_id))throw Error('foreign_owned_history_call');
      const c=consumedTool(binding,item.call_id);
      if(item.arguments!==JSON.stringify(c.request.value.params.arguments))throw Error('consumed_call_arguments_changed');pending.add(item.call_id);
    } else if(item?.type==='function_call_output') {
      if(Object.keys(item).some(k=>!['type','id','call_id','output','status'].includes(k))||!pending.delete(item.call_id))throw Error('unmatched_owned_history_result');
      const c=consumedTool(binding,item.call_id),content=c.response.value.result.contentItems;
      const output=Array.isArray(item.output)?item.output.map((p:any)=>{if(p.type!=='input_text'||Object.keys(p).some(k=>!['type','text'].includes(k))||typeof p.text!=='string')throw Error('unqualified_owned_output');return p.text;}).join(''):item.output;
      if(!Array.isArray(content)||content.some((p:any)=>p.type!=='inputText'||typeof p.text!=='string')||output!==content.map((p:any)=>p.text).join(''))throw Error('consumed_result_history_changed');seen.add(item.call_id);
    } else if(item?.type==='message'&&item.role==='assistant') {
      if(Object.keys(item).some(k=>!['type','id','role','content','phase','status'].includes(k))||!Array.isArray(item.content)||item.content.some((p:any)=>p.type!=='output_text'||Object.keys(p).some(k=>!['type','text','annotations'].includes(k))||(p.annotations?.length??0)!==0))throw Error('unqualified_assistant_carrier');
      const text=item.content.map((p:any)=>p.text).join('');
      if(!binding.frames.some(f=>f.direction==='from-native'&&f.value.method==='item/completed'&&f.value.params?.threadId===binding.threadId&&f.value.params?.turnId===binding.turnId&&f.value.params?.item?.type==='agentMessage'&&f.value.params.item.text===text))throw Error('unobserved_owned_assistant_history');
    } else throw Error('unqualified_owned_followup_history');
  }
  if(pending.size||!seen.size)throw Error('consumed_result_history_incomplete');
}
