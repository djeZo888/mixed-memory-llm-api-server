import {AUTHORIZATIONS} from '../authorization.mjs';
import * as actualProbeApi from '../../../server/src/codex-probe.js';
const reviewedApi:Record<string,unknown>=actualProbeApi;
export const FULL_RETENTION_TASKS=Object.freeze(['H041-COMPACTION-DELIVERY-03','H041-COMPACTION-DELIVERY-04','H041-COMPACTION-DELIVERY-05','H043','H044']);
export const ORDINARY_TASKS=Object.freeze(['H041-COMPACTION-DELIVERY-04','H041-COMPACTION-DELIVERY-05','H043','H044']);
/** Contract proposal only. R owns the implementation; this consumer candidate
 * cannot activate an absent/unreviewed producer by discovering export names.
 * A successor must pin root's exact closed declaration, implementation, source
 * mode and branded policy/handoff graph before changing this explicit barrier. */
export const H044_PRODUCER_CONTRACT=Object.freeze({
 window:'CODEX_H044_WINDOW',ordinary:'createCodexH044Policy',parent:'createCodexH044RetentionParentPolicy',
 collaborationVersionField:'collaborationVersion',adoptionAuthorization:'h044',sourceActivation:'CLOSED',
 startsUtc:AUTHORIZATIONS.H044.startsUtc,capUtc:AUTHORIZATIONS.H044.capUtc,settlementReserveMs:120000,
});
export function assertH044ProducerSourceActivation(task:string){
 if(task==='H044')throw Error('actual_root_reviewed_R_H044_declaration_implementation_and_brands_required');
}
/** Select named source-frozen A capabilities only. The entry supplies the actual
 * imported namespace; caller factories and copied windows cannot redirect it.
 * H043 full retention additionally needs A's sealed handoff interface review. */
export function selectPolicyFactories(api:Record<string,any>,task:string,full:boolean){
 const names=task==='H044'?[H044_PRODUCER_CONTRACT.ordinary,H044_PRODUCER_CONTRACT.parent,H044_PRODUCER_CONTRACT.adoptionAuthorization,H044_PRODUCER_CONTRACT.window]:task==='H043'?['createCodexH043Policy','createCodexH043RetentionParentPolicy','h043','CODEX_H043_WINDOW']:task==='H041-COMPACTION-DELIVERY-05'?['createCodexDelivery05Policy','createCodexRetentionParent05Policy','delivery05','CODEX_H041_DELIVERY05_WINDOW']:task==='H041-COMPACTION-DELIVERY-04'?['createCodexDelivery04Policy','createCodexRetentionParent04Policy','delivery04','CODEX_H041_DELIVERY04_WINDOW']:task==='H041-COMPACTION-DELIVERY-03'?['createCodexDeliveryPolicy','createCodexRetentionParentPolicy','delivery03','CODEX_H041_DELIVERY_WINDOW']:task==='H041-COMPACTION-CONTINUATION-02'?['createCodexContinuationPolicy',null,'continuation02','CODEX_H041_CONTINUATION_WINDOW']:task==='H041'?['createCodexTextOnlyPolicy',null,null,'CODEX_H041_WINDOW']:null;
 if(!names)throw Error('separate_source_frozen_authority_factory_required');
 assertH044ProducerSourceActivation(task);
 const [ordinary,parent,adoptionAuthorization,windowName]=names,frozen=AUTHORIZATIONS[task as keyof typeof AUTHORIZATIONS],window=api[windowName!];
 if(!frozen||!window||window!==reviewedApi[windowName!]||window.startAtMs!==Date.parse(frozen.startsUtc)||window.expiresAtMs!==Date.parse(frozen.capUtc)||window.settlementReserveMs!==120000||typeof api[ordinary!]!=='function'||api[ordinary!]!==reviewedApi[ordinary!]||(full&&(!parent||typeof api[parent]!=='function'||api[parent]!==reviewedApi[parent]||!adoptionAuthorization)))throw Error('actual_A_source_frozen_policy_exports_required');
 // Preserve the historical consumer barrier; the producer now has h043, but
 // this phase does not adopt a new historical handoff activation review.
 if(task==='H043'&&full)throw Error('actual_reviewed_A_H043_handoff_authorization_unavailable');
 return {factory:api[ordinary!],parentFactory:parent?api[parent]:undefined,adoptionAuthorization};
}
/** The observed collaboration version stays bound to the selected parent.
 * Historical source factories retain their original input contracts. */
export function createSelectedRetentionParentPolicy(selected:ReturnType<typeof selectPolicyFactories>,task:string,fields:Record<string,unknown>,observedCollaborationVersion:unknown){
 if(observedCollaborationVersion!=='v1'&&observedCollaborationVersion!=='v2')throw Error('actual_observed_collaboration_version_required');
 const actual=selectPolicyFactories(actualProbeApi,task,true);
 if(selected.factory!==actual.factory||selected.parentFactory!==actual.parentFactory||selected.adoptionAuthorization!==actual.adoptionAuthorization)throw Error('actual_selected_A_retention_parent_factory_required');
 if(typeof selected.parentFactory!=='function')throw Error('actual_A_retention_parent_policy_export_required');
 const policy=selected.parentFactory({...fields,collaborationVersion:observedCollaborationVersion});
 actualProbeApi.assertCodexTextOnlyPolicy(policy,String(fields.sessionId));
 if(policy.window!==reviewedApi[task==='H044'?H044_PRODUCER_CONTRACT.window:task==='H043'?'CODEX_H043_WINDOW':task==='H041-COMPACTION-DELIVERY-05'?'CODEX_H041_DELIVERY05_WINDOW':task==='H041-COMPACTION-DELIVERY-04'?'CODEX_H041_DELIVERY04_WINDOW':'CODEX_H041_DELIVERY_WINDOW']||policy.mode!=='retention-parent'||policy.collaborationVersion!==observedCollaborationVersion||policy.runId!==fields.runId||policy.configSha256!==fields.configSha256||policy.modelCatalogSha256!==fields.modelCatalogSha256)throw Error('actual_retention_parent_collaboration_version_mismatch');
 return policy;
}
