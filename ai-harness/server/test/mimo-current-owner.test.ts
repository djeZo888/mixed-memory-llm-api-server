import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {mimoOwnerStamp,createCurrentMimoProvider} from '../src/mimo-current-owner.js';
import {MIMO_MODEL,MIMO_RUNTIME,MIMO_ARTIFACT_REVISION,MIMO_ARTIFACT_MANIFEST_SHA256,type MimoQualification} from '../src/mimo.js';
const now=1790616000000,hash='a'.repeat(64),template='fixture template',templateHash=createHash('sha256').update(template).digest('hex');
const proof=():MimoQualification=>({qualified:true,evidenceSha256:hash,identity:{model:MIMO_MODEL,runtimeRevision:MIMO_RUNTIME,runtimeBuildSha256:hash,artifactRevision:MIMO_ARTIFACT_REVISION,artifactManifestSha256:MIMO_ARTIFACT_MANIFEST_SHA256,loadedTensorMetadataSha256:hash,loadedTokenizerSha256:hash,loadedTemplateSha256:templateHash,serverInstance:'historical-instance',serverGeneration:'historical-generation',actualSlotContext:950000,maxOutputTokens:65536,parallel:1,contextShift:false,speculative:false,mtp:false,multimodal:false,assistantPrefill:false,jinja:true,kvUnified:true,swaFull:false},checks:{artifactBytes:true,nativePrecision:true,allocation:true,reserves:true,templateAndTokenizer:true,textArrayRendering:true,admissionBound:{basis:'pinned-source-s-minus-one',arithmeticFixtures:true,shortNativeCountUsageMatch:true},generationCeiling:{requestedMaxTokens:65536,requestedCeilingAccepted:true,largestCompletedOutputTokens:20},reasoningAndTools:true,singleOwner:true}});
const envelope={state:'ok',freshness:'fresh',age_ms:0,observed_at:new Date(now).toISOString()};
function node(generation=1){return {schema_version:1,node_id:'ai-vm',boot_id:'17ac5d50-a6a4-4df1-8f9e-7bfc3db5f125',...envelope,services:[{...envelope,service_id:MIMO_MODEL,generation,ready:true,hardware_latched:false,availability:'available',reason:null,model_alias:MIMO_MODEL,deployment_id:'mimo-v2.6-pro-rl-950000-mxfp4',configured_context_tokens:950000,max_output_tokens:65536,required_gpu_uuids:['GPU-69acfa26-8b60-61b5-702d-aee252c163cc']}]} ;}
const pins={buildInfo:'fixture-build',modelPath:'/models/fixture',chatTemplateSha256:templateHash,toolTemplateSha256:null};
const props={model_alias:MIMO_MODEL,build_info:pins.buildInfo,model_path:pins.modelPath,is_sleeping:false,total_slots:1,default_generation_settings:{n_ctx:950000},chat_template:template,modalities:{vision:false,video:false,audio:false}};
const slots=[{id:0,n_ctx:950000,speculative:false,is_processing:false}];
test('current capsule rebinds only ephemeral receipt identity and rejects a restart within owned work',async()=>{
 let generation=1;const seen:string[]=[];const current=createCurrentMimoProvider(proof(),pins,'inference',async()=>'control',async(url,key)=>{seen.push(url);assert.equal(key,url.endsWith('/node/status')?'control':'inference');return url.endsWith('/node/status')?node(generation):url.endsWith('/props')?props:slots;},()=>now);
 const first=await current(new AbortController().signal);assert.notEqual(first.qualification.identity.serverInstance,'historical-instance');assert.equal(first.qualification.evidenceSha256,proof().evidenceSha256);assert.equal(first.qualification.identity.loadedTensorMetadataSha256,hash);assert.equal((await first.observe(new AbortController().signal)).serverInstance,first.qualification.identity.serverInstance);
 generation++;await assert.rejects(first.observe(new AbortController().signal));const next=await current(new AbortController().signal);assert.notEqual(next.qualification.identity.serverInstance,first.qualification.identity.serverInstance);assert.ok(seen.some(x=>x==='http://10.156.100.60:30012/props'));
});
test('changed owner across native props/slots invalidates current capsule before count',async()=>{
 let generation=1;const current=createCurrentMimoProvider(proof(),pins,'i',async()=>'c',async url=>{if(url.endsWith('/node/status'))return node(generation);if(url.endsWith('/props')){generation++;return props;}return slots;},()=>now);await assert.rejects(current(new AbortController().signal));
});
test('unknown/stale/held/changed capacity and physical GPU never qualify from a static receipt',()=>{
 for(const patch of [{hardware_latched:null},{hardware_latched:true},{ready:false},{availability:'unknown'},{configured_context_tokens:480000},{max_output_tokens:131072},{required_gpu_uuids:['GPU-other']},{reason:'software_quarantine'},{generation:null}]){const v=node();Object.assign(v.services[0],patch);assert.throws(()=>mimoOwnerStamp(v,950000,now));}
 const v=node();v.boot_id='invalid';assert.throws(()=>mimoOwnerStamp(v,950000,now));const stale=node();stale.age_ms=15001;assert.throws(()=>mimoOwnerStamp(stale,950000,now));
});
