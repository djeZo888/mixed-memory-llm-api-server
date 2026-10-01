import type { ParentState } from './collector.js';
import type { ProbeManifest } from './dispatch-guard.js';
import { sha256, stableJson } from './projection.js';
export interface ParentProjectionSpec { format:'h041-persisted-parent-input-v1'; prefixInput:unknown[]; envelope:Record<string,unknown>; compactionPrompt:string }
/** Approval is derived before enqueue from an independently captured settled
 * rollout, never from the incoming request under review. Replacement history
 * is permitted only here in the original parent, never in a fresh probe. */
export function parentManifest(state:ParentState,text:string,kind:'message'|'compact',spec:ParentProjectionSpec):ProbeManifest {
  if(state.capturedBy!=='host'||sha256(state.stateUtf8)!==state.stateSha256||spec?.format!=='h041-persisted-parent-input-v1'||!Array.isArray(spec.prefixInput)||typeof spec.envelope.instructions!=='string')throw Error('independently_reviewed_parent_projection_required');
  let history:unknown[]=[];
  for(const line of state.stateUtf8.trimEnd().split('\n')){
    const record=JSON.parse(line);
    if(record.type==='response_item')history.push(record.payload);
    else if(record.type==='compacted'){
      if(!Array.isArray(record.payload?.replacement_history)||!record.payload.replacement_history.length)throw Error('parent_replacement_constructor_not_qualified');
      history=structuredClone(record.payload.replacement_history);
    }
  }
  for(const item of [...spec.prefixInput,...history]){
    if(!item||typeof item!=='object'||!['message','function_call','function_call_output','reasoning'].includes(String((item as any).type)))throw Error('unqualified_parent_history_item');
  }
  const userText=kind==='compact'?spec.compactionPrompt:text;
  if(!userText)throw Error('frozen_parent_action_text_required');
  return {input:[...structuredClone(spec.prefixInput),...history,{type:'message',role:'user',content:[{type:'input_text',text:userText}]}],instructions:spec.envelope.instructions as string,userText,contextSha256:state.stateSha256,envelope:structuredClone(spec.envelope)};
}
