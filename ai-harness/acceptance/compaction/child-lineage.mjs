import {createHash} from 'node:crypto';
const sha=s=>createHash('sha256').update(s).digest('hex');
/** Independent pinned protocol parser. Exact bytes are retained outside mounts;
 * metadata ancestry alone is never a compiled-input or native PASS claim. */
export function verifyChildLineage(proof,expected) {
 if(!proof||typeof proof.requestUtf8!=='string'||typeof proof.responseUtf8!=='string')return {status:'NOT_TESTED',errors:['awaited-owned-native-child-read-absent']};
 try {
  if(proof.requestSha256!==sha(proof.requestUtf8)||proof.responseSha256!==sha(proof.responseUtf8))throw Error();
  const q=JSON.parse(proof.requestUtf8),r=JSON.parse(proof.responseUtf8),t=r.result?.thread;
  if(q.method!=='thread/read'||q.params?.threadId!==expected.childId||q.params?.includeTurns!==false||Object.keys(q.params).sort().join()!=='includeTurns,threadId'||q.id!==r.id||r.error||!t||t.id!==expected.childId||t.id===expected.parentId||t.parentThreadId!==expected.parentId||t.forkedFromId!==null||t.modelProvider!=='sova'||(t.model!==null&&t.model!=='qwen3.8-27b')||(t.model===null&&expected.providerModel!=='qwen3.8-27b')||t.cliVersion!=='0.158.0'||!Array.isArray(t.turns)||t.turns.length!==0||t.source?.subAgent?.thread_spawn?.parent_thread_id!==expected.parentId||t.source.subAgent.thread_spawn.depth!==1||!Array.isArray(t.environments)||t.environments.length!==0)throw Error();
  if(!Number.isSafeInteger(proof.requestSequence)||!Number.isSafeInteger(proof.responseSequence)||proof.requestSequence>=proof.responseSequence||!Number.isFinite(Date.parse(expected.firstDispatchAt))||!Number.isFinite(Date.parse(proof.observedAt))||Date.parse(proof.observedAt)>Date.parse(expected.firstDispatchAt))throw Error();
  return {status:'PASS',errors:[],requestSha256:proof.requestSha256,responseSha256:proof.responseSha256};
 }catch{return {status:'FAIL',errors:['native-child-raw-read-lineage-or-order-binding']};}
}
/** Pinned native child metadata has snake-case IDs; conflicting carriers deny.
 * This is captured identity, not a source of generated attestations. */
export function childRequestMetadata(body,parentId,parentTurnId){
 const c=body?.client_metadata;if(!c||typeof c!=='object')throw Error('child_native_metadata_absent');
 if(typeof c['x-codex-turn-metadata']!=='string')throw Error('canonical_child_metadata_required');const carriers=[];if(c['x-codex-turn-metadata']!==undefined){if(typeof c['x-codex-turn-metadata']!=='string'||Buffer.byteLength(c['x-codex-turn-metadata'])>8192)throw Error('child_native_metadata_invalid');carriers.push(JSON.parse(c['x-codex-turn-metadata']));}
 if(['thread_id','turn_id','parent_thread_id','parent_turn_id','root_turn_id','request_kind'].some(k=>c[k]!==undefined))carriers.push(c);if(!carriers.length)throw Error('child_native_metadata_absent');
 const canonical=carriers[0];if(canonical.request_kind!=='turn'||canonical.subagent_kind!=='thread_spawn'||(c['x-openai-subagent']!==undefined&&c['x-openai-subagent']!=='collab_spawn')||(c['x-codex-parent-thread-id']!==undefined&&c['x-codex-parent-thread-id']!==parentId)||(c.subagent_kind!==undefined&&c.subagent_kind!=='thread_spawn'))throw Error('child_canonical_kind_or_parent_alias_conflict');const keys=['thread_id','turn_id','parent_thread_id','parent_turn_id','root_turn_id'],out={};
 for(const key of keys){if(typeof canonical[key]!=='string'||!canonical[key])throw Error('canonical_child_identity_required');const values=carriers.filter(v=>v[key]!==undefined).map(v=>v[key]);if(!values.length||values.some(v=>typeof v!=='string'||!v||v!==values[0]))throw Error('child_native_identity_missing_or_conflicting');out[key]=values[0];}
 const kinds=carriers.filter(v=>v.request_kind!==undefined).map(v=>v.request_kind);if(!kinds.length||kinds.some(v=>v!=='turn')||out.parent_thread_id!==parentId||out.parent_turn_id!==parentTurnId||out.root_turn_id!==parentTurnId||out.thread_id===parentId)throw Error('child_native_parent_turn_or_request_kind_mismatch');return out;
}

/** Bind only reviewed placeholders to independently observed native IDs. The
 * request being graded is never used as the expected envelope. */
export function bindChildEnvelope(template,ids){
 const bindings={'@h041:child-thread-id':ids.childId,'@h041:child-turn-id':ids.childTurnId,'@h041:parent-thread-id':ids.parentId,'@h041:parent-turn-id':ids.parentTurnId,'@h041:root-turn-id':ids.parentTurnId};
 if(Object.values(bindings).some(v=>typeof v!=='string'||!v))throw Error('independent_child_native_bindings_absent');
 const walk=v=>typeof v==='string'?(bindings[v]??v):Array.isArray(v)?v.map(walk):v&&typeof v==='object'?Object.fromEntries(Object.entries(v).map(([k,x])=>[k,walk(x)])):v;
 const result=walk(structuredClone(template)),carrier=result.client_metadata?.['x-codex-turn-metadata'];
 if(typeof carrier!=='string')throw Error('reviewed_canonical_child_envelope_required');
 result.client_metadata['x-codex-turn-metadata']=JSON.stringify(walk(JSON.parse(carrier)));
 if(JSON.stringify(result).includes('@h041:')||JSON.stringify(result).includes('@h040:'))throw Error('unreviewed_child_placeholder');
 childRequestMetadata(result,ids.parentId,ids.parentTurnId);return result;
}
