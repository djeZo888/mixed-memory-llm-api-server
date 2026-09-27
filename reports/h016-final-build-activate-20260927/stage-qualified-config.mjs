#!/usr/bin/env node
/** Prepare only: no image build, host install, service contact or activation.
 * node stage-qualified-config.mjs RELEASE_ROOT W1_MANIFEST EXPECTED_SHA256 NEW_STAGE REVIEWED_PROFILE_MODULE
 */
import assert from 'node:assert/strict';
import {readFileSync,mkdirSync,writeFileSync,existsSync,realpathSync,lstatSync} from 'node:fs';
import {resolve,join} from 'node:path';
import {pathToFileURL} from 'node:url';
import {validateCapacity,PROFILE_SHA256} from './driver/preflight.mjs';
import {createHash} from 'node:crypto';
if(process.argv.includes('--help')){console.log('Usage: node stage-qualified-config.mjs RELEASE_ROOT W1_MANIFEST EXPECTED_SHA256 NEW_STAGE REVIEWED_PROFILE_MODULE\nRoot-reviewed qualified manifest required. Writes an isolated config/Containerfile proposal only. Current clean W1 production owner is required before activation.');process.exit(0);}
const [releaseArg,manifestArg,expected,stageArg,profileArg]=process.argv.slice(2);assert(releaseArg&&manifestArg&&stageArg&&profileArg&&/^[a-f0-9]{64}$/.test(expected??''),'five arguments required');
const release=realpathSync(releaseArg),stage=resolve(stageArg);
assert.equal(manifestArg,'/etc/sova-qualification/mimo.json');
const {validateMimoIntegration,readMimoEvidence}=await import(pathToFileURL(join(release,'server/dist/mimo-frontier.js')));
const protectedReceipt=readMimoEvidence(manifestArg),manifest=protectedReceipt.text;
assert.equal(createHash('sha256').update(manifest).digest('hex'),expected,'manifest hash differs from root review');
const receipt=protectedReceipt.value,validated=validateMimoIntegration(receipt);
const {qualification,capacity,nativePins}=validated;
validateCapacity(receipt,validated);
const profile=readFileSync(profileArg);assert.equal(createHash('sha256').update(profile).digest('hex'),PROFILE_SHA256);
assert(qualification.identity.maxOutputTokens>=65536,'production policy requires qualified output ceiling65536');
assert(!existsSync(stage),'new empty staging path required');
const parent=realpathSync(resolve(stage,'..'));assert.equal(parent,resolve(stage,'..'));assert(!(lstatSync(parent).mode&0o022),'writable stage ancestry');
const active={model:'mimo-v2.6-pro-rl',mimoEnabled:true,mimoQualificationSha256:expected,mimoContextWindow:qualification.identity.actualSlotContext,mimoMaxOutputTokens:65536};
const candidate=JSON.parse(readFileSync(join(release,'config/mimo-candidate.json'),'utf8'));
Object.assign(candidate,{kind:'root_reviewed_mimo_candidate',defaultFrontier:'mimo-v2.6-pro-rl',enabled:true,qualified:true,downloadedHashesVerified:true,loadedTensorMetadataSha256:qualification.identity.loadedTensorMetadataSha256,loadedTokenizerSha256:qualification.identity.loadedTokenizerSha256,loadedTemplateSha256:qualification.identity.loadedTemplateSha256,configuredContext:capacity.configured,actualSlotContext:capacity.allocated,qualifiedContext:capacity.allocated,maxOutputTokens:65536,qualificationEvidenceSha256:qualification.evidenceSha256,serialCompletionQualified:true,activation:'STAGED ONLY: current clean W1 production owner, exact native settlement, fresh status and root paired activation remain required'});
mkdirSync(stage,{mode:0o700});mkdirSync(join(stage,'config'),{mode:0o700});
writeFileSync(join(stage,'config/active-frontier.json'),JSON.stringify(active,null,2)+'\n',{mode:0o600});
writeFileSync(join(stage,'config/mimo-candidate.json'),JSON.stringify(candidate,null,2)+'\n',{mode:0o600});
writeFileSync(join(stage,'mimo-qualification.json'),manifest,{mode:0o600});
// assemble-final.py adds the verified retained compile14 payload, then these bytes.
const sha=p=>createHash('sha256').update(readFileSync(p)).digest('hex');
writeFileSync(join(stage,'STAGED.json'),JSON.stringify({activation:false,profileSha256:PROFILE_SHA256,qualifiedManifestSha256:expected,activeConfigSha256:sha(join(stage,'config/active-frontier.json')),candidateSha256:sha(join(stage,'config/mimo-candidate.json')),selectedContext:active.mimoContextWindow,output:65536,requiredBeforeActivation:['current clean W1 production owner and exact final protected runtime/source closure','exact old-owner settlement and single frontier ownership','fresh node availability with canonical service mimo-v2.6-pro-rl','identical staged active-frontier bytes in host release and config-overlay image','protected /etc/sova-qualification/mimo.json equals reviewed hash']},null,2)+'\n',{mode:0o600});
console.log(JSON.stringify({staged:stage,activation:false,activeConfigSha256:sha(join(stage,'config/active-frontier.json'))}));
