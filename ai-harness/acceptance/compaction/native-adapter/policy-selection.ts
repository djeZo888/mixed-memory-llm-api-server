import {AUTHORIZATIONS} from '../authorization.mjs';
/** Select named source-frozen A capabilities only. No caller factory/window and
 * no redirect of an older authorization into a newer one. */
export function selectPolicyFactories(api:Record<string,any>,task:string,full:boolean){
 const names=task==='H041-COMPACTION-DELIVERY-05'?['createCodexDelivery05Policy','createCodexRetentionParent05Policy','delivery05','CODEX_H041_DELIVERY05_WINDOW']:task==='H041-COMPACTION-DELIVERY-04'?['createCodexDelivery04Policy','createCodexRetentionParent04Policy','delivery04','CODEX_H041_DELIVERY04_WINDOW']:task==='H041-COMPACTION-DELIVERY-03'?['createCodexDeliveryPolicy','createCodexRetentionParentPolicy','delivery03','CODEX_H041_DELIVERY_WINDOW']:task==='H041-COMPACTION-CONTINUATION-02'?['createCodexContinuationPolicy',null,'continuation02','CODEX_H041_CONTINUATION_WINDOW']:task==='H041'?['createCodexTextOnlyPolicy',null,null,'CODEX_H041_WINDOW']:null;
 if(!names)throw Error('separate_source_frozen_authority_factory_required');
 const [ordinary,parent,adoptionAuthorization,windowName]=names,frozen=AUTHORIZATIONS[task as keyof typeof AUTHORIZATIONS],window=api[windowName!];
 if(!frozen||!window||window.startAtMs!==Date.parse(frozen.startsUtc)||window.expiresAtMs!==Date.parse(frozen.capUtc)||window.settlementReserveMs!==120000||typeof api[ordinary!]!=='function'||(full&&(!parent||typeof api[parent]!=='function'||!adoptionAuthorization)))throw Error('actual_A_source_frozen_policy_exports_required');
 return {factory:api[ordinary!],parentFactory:parent?api[parent]:undefined,adoptionAuthorization};
}
