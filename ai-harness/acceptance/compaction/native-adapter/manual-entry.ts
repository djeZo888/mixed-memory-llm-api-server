/** Actual controller-to-whole-application caller. No import-time side effects.
 * The A carrier owns its canonical lease/guardian; E never clears a STOP hold.
 * Native capability still comes only from independently qualified entry/worker. */
import {fileURLToPath} from 'node:url';import {resolve,join} from 'node:path';import {readFile,realpath,readdir} from 'node:fs/promises';
import {fixture,runAcceptance,privateDirectory,projectionTranslatorFiles} from '../controller.mjs';import {validateRecord} from '../evidence.mjs';import {validateCollectorManifest} from '../scorer.mjs';
import {loadReviewedEntry} from './entry.js';import {translateResponses} from '../../../server/src/codex-responses.js';
import {privateFile,durableFile} from './checkpoint.js';import {sha256,stableJson,reviewSnapshot} from './projection.js';import {reviewedAuthorization} from '../authorization.mjs';
export function requireStageReceipt(bytes:string,expectedSha256:string){
 if(sha256(bytes)!==expectedSha256)throw Error('exact_root_reviewed_stage_bytes_required');const r=JSON.parse(bytes);
 if(r.qualification!=='native'||r.profile!=='h041-summary-stage-v1'||r.observedStatus!=='PASS'||r.actionCount!==9||!Array.isArray(r.records)||r.records.length!==1||r.records[0].qualification!=='native'||r.records[0].status!=='PASS'||r.records[0].mode!=='summary-only'||r.records[0].cycle!==1||validateRecord(r.records[0]).length)throw Error('actual_nine_action_native_stage_scope_required');
 // Full mandatory dimensions remain NOT_TESTED for the partial stage.
 if(r.nativeAcceptance!=='NOT_TESTED'||r.semanticAcceptance!=='NOT_TESTED')throw Error('partial_stage_cannot_claim_full_native_PASS');return r;
}
export async function verifyManualCallerFiles(config:any,repository:string){
 const a=reviewedAuthorization(config.review);if(config.enabled!==true||config.review?.approvedBy!=='root'||config.review.actor!=='worker1'||Date.now()>=a.dispatchCutoffAt||!['stage','full'].includes(config.phase))throw Error('root_reviewed_manual_caller_disabled');
 const controllerBytes=await privateFile(config.controllerConfigPath),adapterBytes=await privateFile(config.adapterConfigPath);if(sha256(controllerBytes)!==config.review.controllerConfigSha256||sha256(adapterBytes)!==config.review.adapterConfigSha256)throw Error('exact_frozen_controller_and_adapter_configuration_required');
 const controller=reviewSnapshot(JSON.parse(controllerBytes.toString('utf8'))),adapter=reviewSnapshot(JSON.parse(adapterBytes.toString('utf8'))),profile=config.phase==='stage'?'h041-summary-stage-v1':'h041-full-retention-v1';
 if(controller.profile!==profile||adapter.profile!==profile||controller.maximumNativeActions!==(config.phase==='stage'?9:39)||controller.review.candidateCommit!==config.review.candidateCommit||adapter.bootstrap.review.candidateCommit!==config.review.candidateCommit||stableJson(controller.review.authorization)!==stableJson(config.review.authorization)||stableJson(adapter.bootstrap.review.authorization)!==stableJson(config.review.authorization)||controller.review.nativeSettlementReserveMs!==120000||adapter.bootstrap.review.nativeSettlementReserveMs!==120000)throw Error('same_frozen_manual_profile_source_window_reserve_required');
 const closureUtf8=controller.review.freshProjectionSpec?.collectorManifestUtf8;if(!validateCollectorManifest(closureUtf8))throw Error('actual_controller_collector_closure_required');const closure=JSON.parse(closureUtf8);
 for(const directory of ['ai-harness/server/src','ai-harness/acceptance/compaction/native-adapter'])for(const file of await readdir(join(repository,directory),{recursive:true}))if(/\.(?:ts|json|js|mjs)$/.test(file)&&!Object.hasOwn(closure.files,`${directory}/${file}`))throw Error('controller_executed_source_sibling_omitted');
 for(const [file,hash] of Object.entries(closure.files))if(await realpath(join(repository,file))!==join(repository,file)||sha256(await readFile(join(repository,file)))!==hash)throw Error('actual_controller_source_closure_changed');
 for(const file of projectionTranslatorFiles)if(controller.review.translatorHashes?.[file]!==sha256(await readFile(join(repository,'ai-harness/server',file))))throw Error('actual_controller_translator_closure_changed');
 if(config.phase==='full')requireStageReceipt((await privateFile(config.stageReceiptPath)).toString('utf8'),config.review.stageReceiptSha256);
 return {controller,adapter};
}
export async function runReviewedManualEntry(path:string,signal:AbortSignal){
 const config=reviewSnapshot(JSON.parse((await privateFile(path)).toString('utf8'))),repository=resolve(fileURLToPath(new URL('../../../..',import.meta.url))),{controller}=await verifyManualCallerFiles(config,repository);signal.throwIfAborted();
 const packet=await fixture();packet.config=controller;packet.sourceHashes.config=sha256(await privateFile(config.controllerConfigPath));const out=await privateDirectory(config.outputPath);
 const adapter=await loadReviewedEntry(config.adapterConfigPath);let completed=false;
 try{signal.throwIfAborted();const result=await runAcceptance({packet,adapter,qualification:'native',signal,normalizeResponses:translateResponses,sink:{private:(name:string,value:any)=>durableFile(join(out,`private-${name}.json`),stableJson(value)),record:(value:any)=>durableFile(join(out,`${value.cycle}-${value.mode}-${crypto.randomUUID()}.evidence.json`),stableJson(value))}});completed=true;await durableFile(join(out,'RESULTS.json'),stableJson(result));if(config.phase==='stage'?result.observedStatus!=='PASS':result.status!=='PASS')throw Error('native_manual_qualification_failed_no_retry');return result;}
 finally{if(!completed)await adapter.close({}).catch(()=>undefined);}
}
if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url)){if(process.argv.length!==3)throw Error('exact_private_manual_config_argument_required');const abort=new AbortController();process.once('SIGTERM',()=>abort.abort());process.once('SIGINT',()=>abort.abort());await runReviewedManualEntry(process.argv[2],abort.signal);}
export default Object.freeze({enabled:false,capabilities:[],nativeAcceptance:'NOT_TESTED'});
