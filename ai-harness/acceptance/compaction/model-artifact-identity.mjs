/** Typed local artifact source identity. Never substitutes for NULL native revisions. */
import {createHash} from 'node:crypto';
const sha=s=>createHash('sha256').update(s).digest('hex');
export function verifyManifestSourceIdentity(receipt,expected){
 try{
 if(typeof receipt.producerReceiptUtf8!=='string'||sha(receipt.producerReceiptUtf8)!==receipt.producerReceiptSha256||receipt.producerReceiptSha256!==expected.producerReceiptSha256)throw Error('independently_bound_actual_artifact_producer_required');
 const r=JSON.parse(receipt.producerReceiptUtf8);
 if(r.source!=='protected-current-model-artifact-observation'||r.nativeModelRevision!==null||r.nativeTokenizerRevision!==null||r.manifest?.path!==expected.manifestPath||r.manifest.sha256!==expected.manifestSha256||r.manifest.type!=='regular-protected-file'||r.manifest.projection?.repoId!==expected.repoId||r.manifest.projection.revision!==expected.revision||!Number.isSafeInteger(r.manifest.ino)||!Number.isSafeInteger(r.manifest.uid)||r.manifest.uid!==r.owner.uid||r.owner.containerId!==expected.containerId||r.owner.startTicks!==expected.startTicks||r.owner.bootId!==expected.bootId||r.mount.source!==expected.mountSource||r.mount.destination!==expected.mountDestination||r.mount.readOnly!==true)throw Error('current_owner_protected_manifest_source_and_actual_mount');
 const rows=r.observedArtifacts;if(!Array.isArray(rows)||rows.length!==74||new Set(rows.map(v=>v.name)).size!==74||sha(JSON.stringify(rows.map(v=>({name:v.name,role:v.role,bytes:v.bytes,sha256:v.sha256,sourceRevision:v.sourceRevision}))))!==expected.artifactInventorySha256||rows.some(v=>!Number.isSafeInteger(v.bytes)||v.bytes<0||!/^[a-f0-9]{64}$/.test(v.sha256)||v.sourceRevision!==expected.revision))throw Error('actual_separate_71_plus_3_file_observations');
 if(rows.filter(v=>v.role==='weight').length!==66||['chat_template.jinja','merges.txt','tokenizer.json','tokenizer_config.json','vocab.json'].some(name=>!rows.some(v=>v.name===name&&v.role==='tokenizer')))throw Error('declared_weights_and_all_five_tokenizer_sources');
 return {status:'SOURCE_VALID',nativeAcceptance:'NOT_TESTED',nativeModelRevision:null,nativeTokenizerRevision:null,identity:{kind:'MANIFEST_SOURCE_REVISION',repoId:expected.repoId,revision:expected.revision,manifestSha256:expected.manifestSha256,artifactInventorySha256:expected.artifactInventorySha256,producerReceiptSha256:receipt.producerReceiptSha256},unassertedMetadataFiles:7,nativeLoadedWeightByteIntrospection:'NOT_TESTED'};
 }catch(e){return {status:'FAIL',errors:[e.message],nativeAcceptance:'NOT_TESTED'};}
}
