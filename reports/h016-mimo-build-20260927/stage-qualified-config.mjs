#!/usr/bin/env node
/** Prepare only: no image build, host install, service contact or activation.
 * node stage-qualified-config.mjs RELEASE_ROOT W1_MANIFEST EXPECTED_SHA256 NEW_STAGE
 */
import assert from 'node:assert/strict';
import {readFileSync,mkdirSync,writeFileSync,existsSync,realpathSync,lstatSync} from 'node:fs';
import {resolve,join} from 'node:path';
import {pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
if(process.argv.includes('--help')){console.log('Usage: node stage-qualified-config.mjs RELEASE_ROOT W1_MANIFEST EXPECTED_SHA256 NEW_STAGE\nRoot-reviewed qualified manifest required. Writes an isolated config/Containerfile proposal only. Persistent W1 owner adoption is required before activation.');process.exit(0);}
const [releaseArg,manifestArg,expected,stageArg]=process.argv.slice(2);assert(releaseArg&&manifestArg&&stageArg&&/^[a-f0-9]{64}$/.test(expected??''),'four arguments required');
const release=realpathSync(releaseArg),stage=resolve(stageArg),manifest=readFileSync(manifestArg);
assert.equal(createHash('sha256').update(manifest).digest('hex'),expected,'manifest hash differs from root review');
const {validateMimoIntegration}=await import(pathToFileURL(join(release,'server/dist/mimo-frontier.js')));
const {qualification,capacity,nativePins}=validateMimoIntegration(JSON.parse(manifest));
assert([131072,1048576].includes(qualification.identity.actualSlotContext),'managed migration tuple not reviewed; root source update required');
assert(qualification.identity.maxOutputTokens>=65536,'production policy requires qualified output ceiling65536');
assert(!existsSync(stage),'new empty staging path required');
const parent=realpathSync(resolve(stage,'..'));assert.equal(parent,resolve(stage,'..'));assert(!(lstatSync(parent).mode&0o022),'writable stage ancestry');
const active={model:'mimo-v2.6-pro-rl',mimoEnabled:true,mimoQualificationSha256:expected,mimoContextWindow:qualification.identity.actualSlotContext,mimoMaxOutputTokens:65536};
const candidate=JSON.parse(readFileSync(join(release,'config/mimo-candidate.json'),'utf8'));
Object.assign(candidate,{kind:'root_reviewed_mimo_candidate',enabled:true,qualified:true,downloadedHashesVerified:true,loadedTensorMetadataSha256:qualification.identity.loadedTensorMetadataSha256,loadedTokenizerSha256:qualification.identity.loadedTokenizerSha256,loadedTemplateSha256:qualification.identity.loadedTemplateSha256,configuredContext:capacity.configured,actualSlotContext:capacity.allocated,qualifiedContext:capacity.allocated,maxOutputTokens:65536,qualificationEvidenceSha256:qualification.evidenceSha256,serialCompletionQualified:true,activation:'STAGED ONLY: persistent W1 owner adoption, exact native settlement, fresh status and root paired activation remain required'});
mkdirSync(stage,{mode:0o700});mkdirSync(join(stage,'config'),{mode:0o700});
writeFileSync(join(stage,'config/active-frontier.json'),JSON.stringify(active,null,2)+'\n',{mode:0o600});
writeFileSync(join(stage,'config/mimo-candidate.json'),JSON.stringify(candidate,null,2)+'\n',{mode:0o600});
writeFileSync(join(stage,'mimo-qualification.json'),manifest,{mode:0o600});
writeFileSync(join(stage,'Containerfile'),'FROM sha256:6641df04cf4e8375029639a67c22da7c3ff4719d2b8e58748572f049de8fb022\nUSER root\nCOPY --chmod=0644 config/active-frontier.json /opt/ai-harness/config/active-frontier.json\nUSER 1000:1000\n',{mode:0o600});
const sha=p=>createHash('sha256').update(readFileSync(p)).digest('hex');
writeFileSync(join(stage,'STAGED.json'),JSON.stringify({activation:false,qualifiedManifestSha256:expected,activeConfigSha256:sha(join(stage,'config/active-frontier.json')),candidateSha256:sha(join(stage,'config/mimo-candidate.json')),selectedContext:active.mimoContextWindow,output:65536,requiredBeforeActivation:['persistent W1 owner adoption replaces trial auto-restore13:40','exact old-owner settlement and single frontier ownership','fresh node availability with canonical service mimo-v2.6-pro-rl','identical staged active-frontier bytes in host release and config-overlay image','protected /etc/ai-harness/mimo-qualification.json equals reviewed hash']},null,2)+'\n',{mode:0o600});
console.log(JSON.stringify({staged:stage,activation:false,activeConfigSha256:sha(join(stage,'config/active-frontier.json'))}));
