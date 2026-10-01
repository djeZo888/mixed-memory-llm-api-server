/** Independent selection from separate protected capture files. Root freezes
 * paths, original bytes' hashes and selectors; producer projections are ignored. */
import {createHash} from 'node:crypto';
const sha=v=>createHash('sha256').update(v).digest('hex');
const select=(v,path)=>{if(!Array.isArray(path)||path.some(k=>typeof k!=='string'&& !Number.isSafeInteger(k)))throw Error('root_frozen_capture_selector_required');for(const k of path){if(v===null||!Object.hasOwn(v,k))throw Error('actual_capture_selector_absent');v=v[k];}return v;};
const canonical=v=>Array.isArray(v)?v.map(canonical):v&&typeof v==='object'?Object.fromEntries(Object.keys(v).sort().map(k=>[k,canonical(v[k])])):v;
function capture(actual,expected){if(!actual||actual.path!==expected.path||typeof actual.utf8!=='string'||sha(actual.utf8)!==expected.sha256||actual.sha256!==expected.sha256)throw Error('separate_original_capture_file_bytes_required');const value=JSON.parse(actual.utf8);return value;}
function rows(value,spec){const raw=select(value,spec.rowsPath);if(!Array.isArray(raw))throw Error('actual_capture_rows_not_array');return raw.map(row=>{const result={};for(const [key,path]of Object.entries(spec.fields))result[key]=select(row,path);return result;});}
export function verifySeparateArtifactCaptures(packet,expected){
 if(expected.proofVersion!=='separate-raw-files-v2'||!packet?.captures||!expected.captures)throw Error('independent_separate_raw_artifact_capture_contract_required');
 const specs=expected.captures,manifest=capture(packet.captures.manifest,specs.manifest),first=capture(packet.captures.pass71,specs.pass71),supplement=capture(packet.captures.pass3,specs.pass3),current=capture(packet.captures.current,specs.current);
 if(new Set(Object.values(packet.captures).map(c=>c.path)).size!==4)throw Error('independent_capture_files_must_be_distinct');
 if(select(manifest,specs.manifest.repoIdPath)!==expected.repoId||select(manifest,specs.manifest.revisionPath)!==expected.revision||!/^[a-f0-9]{40}$/.test(expected.revision))throw Error('original_installed_manifest_source_revision');
 const declared=rows(manifest,specs.manifest),a=rows(first,specs.pass71),b=rows(supplement,specs.pass3);
 if(a.length!==71||b.length!==3||select(first,specs.pass71.exitPath)!==0||select(supplement,specs.pass3.exitPath)!==0)throw Error('actual_separate_71_and_3_passes_required');
 const observed=[...a,...b];if(new Set(observed.map(v=>v.name)).size!==74||declared.length!==81)throw Error('actual_artifact_inventory_counts');
 for(const actual of observed){const source=declared.filter(v=>v.name===actual.name);if(source.length!==1||actual.bytes!==source[0].bytes||actual.sha256!==source[0].sha256||!Number.isSafeInteger(actual.bytes)||actual.bytes<0||!/^[a-f0-9]{64}$/.test(actual.sha256))throw Error('observed_artifact_not_in_original_manifest');actual.role=source[0].role;actual.sourceRevision=expected.revision;}
 if(observed.filter(v=>v.role==='weight').length!==66||['chat_template.jinja','merges.txt','tokenizer.json','tokenizer_config.json','vocab.json'].some(name=>!observed.some(v=>v.name===name&&v.role==='tokenizer')))throw Error('all_declared_weight_and_tokenizer_bytes_required');
 const identity=select(current,specs.current.ownerPath),mount=select(current,specs.current.mountPath),stats=rows(current,specs.current);
 if(select(current,specs.current.modelRevisionPath)!==null||select(current,specs.current.tokenizerRevisionPath)!==null||identity.containerId!==expected.containerId||identity.startTicks!==expected.startTicks||identity.bootId!==expected.bootId||identity.uid!==expected.uid||mount.source!==expected.mountSource||mount.destination!==expected.mountDestination||mount.readOnly!==true)throw Error('actual_current_owner_mount_and_native_null');
 for(const prior of observed){const found=stats.filter(s=>s.name===prior.name);if(found.length!==1)throw Error('current_artifact_stat_missing_or_duplicate');const now=found[0];if(now.path!==expected.mountSource+'/'+prior.name||now.bytes!==prior.bytes||now.dev!==prior.dev||now.ino!==prior.ino||now.mtimeNs!==prior.mtimeNs||now.uid!==identity.uid||now.nlink!==1||now.type!=='regular-file'||!Number.isSafeInteger(now.ino)||!Number.isSafeInteger(now.dev))throw Error('current_mounted_file_differs_from_actual_hash_pass');}
 const manifestStat=select(current,specs.current.manifestStatPath);if(manifestStat.path!==specs.manifest.path||manifestStat.sha256!==specs.manifest.sha256||manifestStat.uid!==identity.uid||manifestStat.type!=='regular-protected-file'||manifestStat.nlink!==1||!Number.isSafeInteger(manifestStat.ino))throw Error('current_protected_installed_manifest_identity');
 const inventory=observed.map(v=>({name:v.name,role:v.role,bytes:v.bytes,sha256:v.sha256,sourceRevision:v.sourceRevision}));
 const digest=sha(JSON.stringify(inventory));if(digest!==expected.artifactInventorySha256)throw Error('root_frozen_selected_artifact_inventory_changed');
 return {inventory,identity,manifestSha256:specs.manifest.sha256,nativeModelRevision:null,nativeTokenizerRevision:null,currentCaptureSha256:specs.current.sha256};
}
/** Actual A retained Linux file/command shape; no invented process UID/ticks.
 * Manifest owner is protected root; model owner is actual container birth/PID. */
export function parseExactIntegers(text){return JSON.parse(text.replace(/"(?:[^"\\]|\\.)*"|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?/g,token=>token[0]==='"'||!/^[-]?\d+$/.test(token)||Number.isSafeInteger(Number(token))?token:JSON.stringify(token)));}
const same=(a,b)=>JSON.stringify(canonical(a))===JSON.stringify(canonical(b));
export function verifyRetainedLinuxArtifactFiles(packet,expected){
 if(expected.proofVersion!=='retained-linux-files-v1'||!packet?.files)throw Error('actual_retained_linux_producer_files_required');
 const values={};
 for(const name of ['manifest','model','pass71','pass3']){
  const f=packet.files[name],e=expected.files?.[name];
  if(!f||!e||f.outputPath!==e.outputPath||f.receiptPath!==e.receiptPath||f.scriptPath!==e.scriptPath||sha(f.outputUtf8)!==e.outputSha256||sha(f.receiptUtf8)!==e.receiptSha256||sha(f.scriptUtf8)!==e.scriptSha256)throw Error('actual_separate_command_source_and_output_bytes');
  const command=JSON.parse(f.receiptUtf8);if(command.exit!==0||command.logSHA256!==e.outputSha256||command.stdinSHA256!==e.scriptSha256||!same(command.argv,e.argv)||!Number.isFinite(Date.parse(command.startedUtc))||Date.parse(command.finishedUtc)<Date.parse(command.startedUtc))throw Error('actual_retained_readback_command_receipt');
  values[name]=parseExactIntegers(f.outputUtf8);
 }
 const {manifest:captured,model,pass71,pass3}=values,bytes=Buffer.from(captured.manifest?.rawBase64??'','base64');
 if(bytes.toString('base64')!==captured.manifest.rawBase64||sha(bytes)!==expected.manifestSha256||captured.path!==expected.manifestPath||captured.manifest.origin!=='MANIFEST_SOURCE_REVISION'||captured.manifest.sha256!==sha(bytes))throw Error('actual_original_installed_manifest_bytes');
 const installed=JSON.parse(bytes.toString('utf8'));if(installed.repo_id!==expected.repoId||installed.revision!==expected.revision||installed.artifact_count!==81||installed.weight_count!==66)throw Error('original_installed_source_identity');
 const stat=captured.manifest.stat;if(stat.st_uid!==0||stat.st_nlink!==1||(stat.st_mode&0o170000)!==0o100000||(stat.st_mode&0o022)!==0||stat.st_size!==bytes.length||!Number.isSafeInteger(stat.st_ino)||!Number.isSafeInteger(stat.st_dev))throw Error('actual_protected_root_owned_manifest_stat');
 const owner={containerId:captured.container.id,imageId:captured.container.image,pid:captured.container.pid,startedAt:captured.container.startedAt,bootId:captured.bootId};
 if(!same(owner,expected.owner)||captured.container.running!==true||model.bootId!==owner.bootId||model.container.id!==owner.containerId||model.container.imageId!==owner.imageId||model.container.pid!==owner.pid||model.container.startedAt!==owner.startedAt||pass3.container.id!==owner.containerId||pass3.container.pid!==owner.pid||pass3.container.startedAt!==owner.startedAt)throw Error('actual_same_container_birth_owner_across_captures');
 const mount=captured.container.mount;if(mount.Source!==expected.mountSource||mount.Destination!==expected.mountDestination||mount.RW!==false||captured.modelRoot.dev!==captured.modelRoot.boundDev||captured.modelRoot.ino!==captured.modelRoot.boundIno||pass3.hostModelRootStat.st_dev!==captured.modelRoot.dev||pass3.hostModelRootStat.st_ino!==captured.modelRoot.ino||pass3.containerBoundModelRootStat.st_dev!==captured.modelRoot.dev||pass3.containerBoundModelRootStat.st_ino!==captured.modelRoot.ino)throw Error('actual_read_only_same_model_root_mount');
 const fields=model.nativeMetadata?.['/get_server_info']?.fields;if(model.nativeMetadata?.['/get_server_info']?.http!==200||fields?.revision!==null||fields.tokenizer_revision!==null||fields.model_path!==mount.Destination||fields.tokenizer_path!==mount.Destination||fields.context_length!==480000||fields.served_model_name!=='qwen3.8-27b')throw Error('actual_model_native_null_metadata');
 if(pass71.status!=='PASS'||pass71.files?.length!==71||pass71.expectedFiles!==71||!same(pass71.beforeIdentity,pass71.afterIdentity)||pass71.beforeIdentity.containerId!==owner.containerId||pass71.beforeIdentity.pid!==owner.pid||pass71.beforeIdentity.startedAt!==owner.startedAt||pass71.beforeIdentity.modelsMount.source!==mount.Source||pass71.beforeIdentity.modelsMount.destination!==mount.Destination||pass71.beforeIdentity.modelsMount.rw!==false||pass3.extraFiles?.length!==3)throw Error('actual_retained_71_plus_3_file_passes');
 // The stat-only command binds its exact71 expected dictionary in its original
 // script. Parse that restricted Python JSON-shaped literal without executing it.
 const script=packet.files.pass3.scriptUtf8,match=script.match(/expected=(\{[^\n]+\});result/ )??script.match(/expected=(\{[^\n]+\})\n/);
 const literal=match?.[1];if(!literal||/[\\]|\b(?:True|False|None)\b/.test(literal))throw Error('actual_stat_recheck_expected_dictionary_missing');
 const stats=parseExactIntegers(literal.replaceAll("'",'"'));
 if(Object.keys(stats).length!==71||pass3.modelFileStatsMatchOriginal71Pass!==true)throw Error('executed_source_bound_stat_recheck_failed');
 const observed=[];
 for(const row of pass71.files){if(!same(row.before,row.after)||!same(row.before,stats[row.name]))throw Error('original_hash_pass_stat_recheck_binding');observed.push({name:row.name,bytes:row.before.st_size,sha256:row.sha256});}
 for(const row of pass3.extraFiles){if(row.present!==true||row.bytes!==row.stat?.st_size)throw Error('actual_three_small_files_incomplete');observed.push({name:row.name,bytes:row.bytes,sha256:row.sha256});}
 if(new Set(observed.map(v=>v.name)).size!==74)throw Error('actual_separate_file_inventory_duplicates');
 for(const v of observed){const matches=installed.artifacts.filter(a=>a.path===v.name);if(matches.length!==1||matches[0].size_bytes!==v.bytes||matches[0].sha256!==v.sha256||matches[0].revision!==expected.revision)throw Error('actual_hash_file_not_selected_original_manifest_row');v.role=matches[0].role;v.sourceRevision=expected.revision;}
 if(observed.filter(v=>v.role==='weight').length!==66||['chat_template.jinja','merges.txt','tokenizer.json','tokenizer_config.json','vocab.json'].some(name=>!observed.some(v=>v.name===name&&v.role==='tokenizer')))throw Error('all_weight_and_tokenizer_original_source_rows');
 const inventory=observed.map(v=>({name:v.name,role:v.role,bytes:v.bytes,sha256:v.sha256,sourceRevision:v.sourceRevision}));if(sha(JSON.stringify(inventory))!==expected.artifactInventorySha256)throw Error('root_frozen_actual_selected_inventory_sha');
 return {inventory,identity:owner,manifestSha256:sha(bytes),nativeModelRevision:null,nativeTokenizerRevision:null,loadedBytesLimit:'File-content/stat/mount/birth correlation only; runtime loaded-weight-byte introspection remains NOT_TESTED'};
}
/** Fresh stat-only bridge to the reused original71+3 content passes. Root must
 * freeze THIS separate observation's bytes; historical current files do not
 * grant freshness. No weight rehash or revision fabrication. */
export function verifyFreshArtifactOwner(packet,expected,freshExpected,route,now=Date.now()){
 const frozen=packet.files.current,e=freshExpected;if(!frozen||!e||frozen.outputPath!==e.outputPath||frozen.receiptPath!==e.receiptPath||frozen.scriptPath!==e.scriptPath||sha(frozen.outputUtf8)!==e.outputSha256||sha(frozen.receiptUtf8)!==e.receiptSha256||sha(frozen.scriptUtf8)!==e.scriptSha256)throw Error('fresh_original_stat_command_bytes_required');
 const command=JSON.parse(frozen.receiptUtf8),v=parseExactIntegers(frozen.outputUtf8),at=Date.parse(command.finishedUtc);if(command.exit!==0||command.logSHA256!==e.outputSha256||command.stdinSHA256!==e.scriptSha256||!same(command.argv,e.argv)||now-at<0||now-at>60000||Date.parse(command.startedUtc)>at||v.source!=='current-model-owner-stat-observation'||v.nativeModelRevision!==null||v.nativeTokenizerRevision!==null)throw Error('actual_fresh_current_owner_stat_receipt');
 const old=verifyRetainedLinuxArtifactFiles(packet,expected),manifest=parseExactIntegers(packet.files.manifest.outputUtf8),pass71=parseExactIntegers(packet.files.pass71.outputUtf8),pass3=parseExactIntegers(packet.files.pass3.outputUtf8);
 if(!same(v.owner,old.identity)||!same(v.owner,route.artifactOwner)||v.routeInstanceId!==route.instanceId||v.manifest.path!==expected.manifestPath||v.manifest.sha256!==old.manifestSha256||!same(v.manifest.stat,manifest.manifest.stat)||v.mount.source!==expected.mountSource||v.mount.destination!==expected.mountDestination||v.mount.readOnly!==true||v.modelRoot.dev!==manifest.modelRoot.dev||v.modelRoot.ino!==manifest.modelRoot.ino||v.modelRoot.boundDev!==v.modelRoot.dev||v.modelRoot.boundIno!==v.modelRoot.ino||!Array.isArray(v.files)||v.files.length!==74)throw Error('fresh_route_installed_manifest_owner_mount_binding');
 const baseline=[...pass71.files.map(r=>({name:r.name,stat:r.after})),...pass3.extraFiles.map(r=>({name:r.name,stat:r.stat}))];for(const prior of baseline){const matches=v.files.filter(r=>r.name===prior.name);if(matches.length!==1||!same(Object.fromEntries(Object.keys(prior.stat).map(k=>[k,matches[0].stat[k]])),prior.stat))throw Error('fresh_actual_artifact_stat_differs_from_original_hash_pass');}
 return {status:'SOURCE_VALID',nativeAcceptance:'NOT_TESTED',owner:v.owner,routeInstanceId:v.routeInstanceId,currentObservationSha256:e.outputSha256,observedAt:command.finishedUtc};
}
