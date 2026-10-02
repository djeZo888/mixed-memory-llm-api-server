import {AUTHORIZATIONS} from '../authorization.mjs';
import * as actualProbeApi from '../../../server/src/codex-probe.js';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
const reviewedApi:Record<string,unknown>=actualProbeApi;
export const FULL_RETENTION_TASKS=Object.freeze(['H041-COMPACTION-DELIVERY-03','H041-COMPACTION-DELIVERY-04','H041-COMPACTION-DELIVERY-05','H043','H044']);
export const ORDINARY_TASKS=Object.freeze(['H041-COMPACTION-DELIVERY-04','H041-COMPACTION-DELIVERY-05','H043','H044']);
/** Final closed R03 operative graph. The original R01 evidence stays separate;
 * current-source admission does not rewrite a baseline release or grant native
 * qualification, operation flags, or finite GO. */
export const H044_PRODUCER_CONTRACT=Object.freeze({
 window:'CODEX_H044_WINDOW',ordinary:'createCodexH044Policy',parent:'createCodexH044RetentionParentPolicy',
 collaborationVersionField:'collaborationVersion',adoptionAuthorization:'h044',sourceActivation:'EXACT_CLOSED_SOURCE_REVIEW',
 closedContractSha256:'91512d4cd15759c40daef015646617f2737e6c87a10ce6499d5e2f02e7e8ef9f',
 closedSourceCommit:'86fcd6d84381cb9c44caad75eb9785d3b0ec11bd',reportHead:'f2edde8fd8c1c12b7efa4691a340d93e5eaa3367',
 rootReviewSha256:'2e597654a5ae7b6c50393f741d9dee864178a956ed1b42284678d897913dc6ee',
 baselineEvidence:Object.freeze({contractSha256:'f7f9228e9b6a3a2ce6bfa6a0c7b9508e3f68fd32d2c3744660190c9b858e340f',rootReviewSha256:'e255f7f4271a707351647aa7ae34ed9d6fd1b948c01ed2264d35c437e2c09b35'}),
 // Actual final R03 emitted declarations; receipt/launcher add generation fields.
 declarationSha256:Object.freeze({probe:'581a5bd3b3aa7100955ef274dba565b115d5caf872fd401bba09c8540a0377e8',handoff:'602f15495f74a7f762031ef274b9ef4bce3c77d944a00d61f82ce3735f019f31',receipts:'202bc26fb087a32064ec3e11d2778c99714bfd6764d07945f2f0d8db61e9cc60',launcher:'ad583c151bd63bda4c2a47575510dbe20970658438edb885e8c27865a68fcf77'}),
 // Original four declarations remain independent immutable baseline evidence.
 baselineDeclarationSha256:Object.freeze({probe:'581a5bd3b3aa7100955ef274dba565b115d5caf872fd401bba09c8540a0377e8',handoff:'602f15495f74a7f762031ef274b9ef4bce3c77d944a00d61f82ce3735f019f31',receipts:'bcf97a9b95953cd694e925da6acfe3afc913ec3c2d95e0fd5e1935fc1b0422ca',launcher:'d926c9a1545b57b956f80937c1a710ac9b30f3a432d7f6dfd25baa947daaea64'}),
 startsUtc:AUTHORIZATIONS.H044.startsUtc,capUtc:AUTHORIZATIONS.H044.capUtc,settlementReserveMs:120000,
});
/** Immutable historical R01 baseline evidence; never current admission. */
export const H044_R01_BASELINE_SOURCE_HASHES=Object.freeze({
 'ai-harness/server/src/codex-probe.ts':'47b545710c0261fb4c745c3b29a2f534289506db4c690fe5cfedee877af204cb',
 'ai-harness/server/src/codex-policy-handoff.ts':'ff48673debb5c6b3e2af6fc19150dd4f970bd1bcf6426fbb5844bae4353f474a',
 'ai-harness/server/src/codex-launcher.ts':'2b9f61cc68c4203242bf69c4b5f9f4a9cd5763993acf18aea552d6f71af3be30',
 'ai-harness/server/src/codex-receipts.ts':'1cc31ee3ac95eb9701dd0f1a657e5ac32f479419e7f0c7d96c574eea77bb9408',
 'ai-harness/server/src/codex-instructions.ts':'8e4925203c9236d504ec1ca30d7f08f031d8a7930dd1cd1ec515090d793b61e9',
 'ai-harness/deploy/engine/codex_receipts.py':'45bf47c2bd1ad9bb0f7112d7eaf78c94332d69f28cb978ba5f66bd3115b01780',
 'ai-harness/deploy/run-codex.sh':'12c778bd380ae5f961b888a5915a9c81186a32eef61f034cdfd467f82ee83b9a',
});
/** Necessary selected R03 closure: ten actually imported server modules plus
 * the Codex launcher, receipt producer and invoked overlay validator. The
 * unrelated run-engine launcher is reviewed evidence, not this Codex gate.
 * Installed-build and authenticated ordinary-source closure guards independently
 * verify the complete executing graph and preserve the original release. */
export const H044_REVIEWED_SOURCE_HASHES=Object.freeze({
 'ai-harness/server/src/codex-probe.ts':'47b545710c0261fb4c745c3b29a2f534289506db4c690fe5cfedee877af204cb',
 'ai-harness/server/src/codex-policy-handoff.ts':'ff48673debb5c6b3e2af6fc19150dd4f970bd1bcf6426fbb5844bae4353f474a',
 'ai-harness/server/src/codex-launcher.ts':'0a15c726d38717db69c349d6f5090b51191d17c7bce42f6937167e558ff850d9',
 'ai-harness/server/src/codex-receipts.ts':'330ee02308ea186d5fccd282e49d72d2440461c7f31e467a8d0e78a51800db36',
 'ai-harness/server/src/codex-instructions.ts':'bc70d23276c987787e33c96f47835c99f1b249580930aa021675ebfda06cfa30',
 'ai-harness/server/src/codex-automatic-routing.ts':'c7d98a5568c69da1c3ea0f38dffa7af6f9ec913a945513ad80e14fbc8ea71687',
 'ai-harness/server/src/codex-children.ts':'076ac3f37fee383d8531f46917e059c62d2160d3e67494d9ca4981baf60daae7',
 'ai-harness/server/src/codex-host.ts':'b2f461012e5d6db6da109c941474fe21d8ed8a89c55179ced6f89ea50f5fa838',
 'ai-harness/server/src/codex-ordinary-entry.ts':'9ab7d50a11db5c1a3311bff7912571fbae7db09f323950a7d6394591d3569b9a',
 'ai-harness/server/src/codex-specialist-qualification.ts':'c14f001d5cf0ae38fe92caa6052e7c85669b4fd1e717ad666d8ee6832d7e6228',
 'ai-harness/deploy/engine/codex_receipts.py':'e84fc4ac7b77ea6244ceef8d6de2266cba744fdc100e1f8f2de171e96a6ceef9',
 'ai-harness/deploy/run-codex.sh':'9b309d36bcbd6a8e6622400b580728f10c56c1dbcfc1d60fc9d6f437db609a71',
 'ai-harness/deploy/engine/validate-image-overlays.py':'45c5048bfa2c60193a23895e1870a6d813835b29bc3ec4efd9223ea6d87a6b6f',
});
/** Also exported for source tests. Production never accepts a caller hash graph. */
export function verifyH044ReviewedSourceHashes(hashes:Record<string,string>){
 if(Object.keys(hashes).sort().join()!==Object.keys(H044_REVIEWED_SOURCE_HASHES).sort().join()||Object.entries(H044_REVIEWED_SOURCE_HASHES).some(([p,h])=>hashes[p]!==h))throw Error('actual_root_reviewed_R_H044_source_graph_changed');
}
export function assertH044ProducerSourceActivation(task:string){
 if(task!=='H044')return;
 const hashes=Object.fromEntries(Object.keys(H044_REVIEWED_SOURCE_HASHES).map(path=>[path,createHash('sha256').update(readFileSync(fileURLToPath(new URL('../../../../'+path,import.meta.url)))).digest('hex')]));
 verifyH044ReviewedSourceHashes(hashes);
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
 // Closed H044 declaration excludes mode and checks exact input keys. Older
 // factories tolerated it before overwriting; keep their historical contract.
 const {mode,...parentFields}=fields;
 if(task==='H044'&&mode!==undefined&&!['summary-only','text-only-parent','retention-parent'].includes(String(mode)))throw Error('actual_retention_parent_mode_required');
 const policy=selected.parentFactory({... (task==='H044'?parentFields:fields),collaborationVersion:observedCollaborationVersion});
 actualProbeApi.assertCodexTextOnlyPolicy(policy,String(fields.sessionId));
 if(policy.window!==reviewedApi[task==='H044'?H044_PRODUCER_CONTRACT.window:task==='H043'?'CODEX_H043_WINDOW':task==='H041-COMPACTION-DELIVERY-05'?'CODEX_H041_DELIVERY05_WINDOW':task==='H041-COMPACTION-DELIVERY-04'?'CODEX_H041_DELIVERY04_WINDOW':'CODEX_H041_DELIVERY_WINDOW']||policy.mode!=='retention-parent'||policy.collaborationVersion!==observedCollaborationVersion||policy.runId!==fields.runId||policy.configSha256!==fields.configSha256||policy.modelCatalogSha256!==fields.modelCatalogSha256)throw Error('actual_retention_parent_collaboration_version_mismatch');
 return policy;
}
