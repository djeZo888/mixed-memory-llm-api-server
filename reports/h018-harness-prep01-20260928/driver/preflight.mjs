/** H009 preflight adapted to prepared H018 release; every contact follows the root gate. */
import assert from 'node:assert/strict';
import {readFileSync,lstatSync,realpathSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
import {pathToFileURL} from 'node:url';
import {join,resolve,dirname} from 'node:path';
import {sha} from './guards.mjs';
export let SOURCE;
export let IMAGE;
export const REV='7ac59a6e3ad851cd41af00f678effab0598ba9a8';
export let RELEASE;
export const TASKROOT='/home/user/ai-harness-build/H018-HARNESS-PREP01-20260928';
export const RUNROOT=TASKROOT+'/live-acceptance-01';
export const KEY='/home/user/.config/ai-harness/inference-key';
const BASE='46feffff8fe00e5993a8e0d35f5a7932f82ee43ef91d87759f568c3a6029dc1e';
const TAG='localhost/ai-harness-engine:0.0.2-ae65651df5f9';
export const PROFILE_SHA256='1767aec74793b161b07feeee9e8dc97c3a4ffc9970c5c8f532bbf443b9f8ea1c';
export const ADMIT_UTC='2026-09-28T00:59:30Z';
export const MIN_WORK_SECONDS=720;
export const SETTLE_UTC='2026-09-28T01:14:30Z'; // 30s systemd stop grace before fixed01:15
export function assertAdmission(now=Date.now()) { assert(now<=Date.parse(ADMIT_UTC),'late actual app admission'); }
// Existing qualification validator verifies native identity, precision, reserves and evidence.
// Root/W1 records target/fallback reason in its existing capacity report.
export function validateCapacity(receipt,validated) {
 const {qualification,capacity}=validated,context=qualification.identity.actualSlotContext;
 assert([1000192,1000000,950000,917504].includes(context),'usable props/slot must be reviewed1000192,1000000,decimal950000 or reserve-failure917504');
 assert.equal(capacity.configured,context);assert.equal(capacity.allocated,context);
 assert(Number.isSafeInteger(capacity.occupiedTested)&&capacity.occupiedTested>0&&capacity.occupiedTested<context);
 assert.equal(qualification.identity.maxOutputTokens,65536);
 return context;
}
let reviewed,validateIntegration,readEvidence;
export function checkedFile(file,isPrivate){
 assert.equal(realpathSync(file),file,'noncanonical file');const s=lstatSync(file);
 assert(s.isFile()&&s.nlink===1&&[0,process.getuid()].includes(s.uid),'unsafe type/link/owner');
 assert(!(s.mode&(isPrivate?0o077:0o022)),'unsafe permissions');
 for(let p=dirname(file);;p=dirname(p)){const d=lstatSync(p);assert(d.isDirectory()&&!d.isSymbolicLink()&&[0,process.getuid()].includes(d.uid)&&!(d.mode&0o022),'unsafe ancestry');if(p==='/')break;}
 return file;
}
export const privateFile=f=>checkedFile(f,true);
export function evidenceFile(f,d){checkedFile(f,false);assert.match(d,/^[a-f0-9]{64}$/);assert.equal(sha(readFileSync(f)),d,'digest mismatch');return f;}
export const podman=(...args)=>execFileSync('/usr/bin/podman',['--remote=false',...args],{encoding:'utf8',timeout:30000,env:{HOME:'/home/user',PATH:'/usr/bin:/bin',XDG_RUNTIME_DIR:'/run/user/1000'}}).trim();
export function checkPromoted(){
 assert(reviewed,'root gate first');assert.equal(process.platform,'linux');assert.equal(process.getuid(),1000);
 assert(Date.now()<Date.parse(SETTLE_UTC),'absolute settlement deadline');
 assert.equal(execFileSync('systemctl',['--user','show','ai-harness.service','-p','ActiveState','--value'],{encoding:'utf8',timeout:5000}).trim(),'inactive');
 assert.equal(execFileSync('systemctl',['--user','show','ai-harness.service','-p','MainPID','--value'],{encoding:'utf8',timeout:5000}).trim(),'0');
 const info=JSON.parse(podman('image','inspect',TAG))[0];assert.equal(info.Id.replace(/^sha256:/,''),IMAGE);
 assert.equal(info.Labels['org.opencontainers.image.ai-harness.source'],SOURCE);
 assert.equal(info.Labels['org.opencontainers.image.ai-harness.patchset'],'38d7b6a7978e5e95e69db790cf2e3465a0e33ddd27124b1b7af387518e9722bf');
 assert.equal(info.Labels['org.opencontainers.image.ai-harness.native-source'],'b948889814648ad761f40a18260ddbe6351c6bbf');
 const base=JSON.parse(podman('image','inspect',BASE))[0];assert.deepEqual(info.RootFS.Layers.slice(0,-1),base.RootFS.Layers);
 const unit=readFileSync('/home/user/.config/systemd/user/ai-harness.service','utf8');assert(unit.includes(RELEASE+'/'));
 for(const [file,hash]of Object.entries(reviewed.releaseSha256))evidenceFile(join(RELEASE,file),hash);
 const active=JSON.parse(readFileSync(join(RELEASE,'config/active-frontier.json')));assert.equal(active.model,'mimo-v2.6-pro-rl');assert.equal(active.mimoContextWindow,reviewed.context);assert.equal(active.mimoMaxOutputTokens,65536);assert.equal(active.mimoQualificationSha256,reviewed.qualificationSha256);
 evidenceFile('/etc/sova-qualification/mimo.json',reviewed.qualificationSha256);
 const protectedReceipt=readEvidence('/etc/sova-qualification/mimo.json');
 assert.equal(sha(protectedReceipt.text),reviewed.qualificationSha256);
 const receipt=protectedReceipt.value;
 assert.equal(validateCapacity(receipt,validateIntegration(receipt)),reviewed.context);
 assert.equal(active.mimoEnabled,true);
 const candidate=JSON.parse(readFileSync(join(RELEASE,'config/mimo-candidate.json')));
 assert(candidate.enabled&&candidate.qualified&&candidate.model===active.model);
 assert.equal(candidate.actualSlotContext,reviewed.context);assert.equal(candidate.configuredContext,reviewed.context);
 evidenceFile(join(RELEASE,'deploy/engine/configure-profile.mjs'),PROFILE_SHA256);
 const imageConfig=podman('run','--rm','--pull=never','--http-proxy=false','--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges','--entrypoint','cat',IMAGE,'/opt/ai-harness/config/active-frontier.json');
 assert.equal(imageConfig,readFileSync(join(RELEASE,'config/active-frontier.json'),'utf8').trim());
 const free=execFileSync('df',['-B1','--output=avail',TASKROOT],{encoding:'utf8',timeout:5000}).trim().split(/\s+/).at(-1);assert(Number(free)>21474836480);
 const imageProfile=podman('run','--rm','--pull=never','--http-proxy=false','--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges','--entrypoint','sha256sum',IMAGE,'/opt/ai-harness/engine/configure-profile.mjs');
 assert.equal(imageProfile.split(/\s+/)[0],PROFILE_SHA256);
 return {source:SOURCE,image:IMAGE,context:reviewed.context,capacity:receipt.capacity,profileOutput:65536,uppers:'inactive'};
}
export async function preflight(args,driverDir){
 assert.equal(process.platform,'linux');assert(process.env.INVOCATION_ID,'independent Linux systemd owner required');assertAdmission();
 const file=resolve(args['--gate']);privateFile(file);evidenceFile(file,args['--gate-sha256']);const g=JSON.parse(readFileSync(file));
 assert.equal(g.authorization,'ROOT_GO_H018_NATIVE_APP_ACCEPTANCE');assert.match(g.source,/^[a-f0-9]{40}$/);SOURCE=g.source;RELEASE=`/opt/ai-harness/releases/${SOURCE}-h018-prep01/ai-harness`;assert.match(g.image,/^[a-f0-9]{64}$/);assert.notEqual(g.image,BASE);
 for(const k of ['worker1LaneReleased','liveInferenceAuthorized','productionOwnerCurrent','full17Qualified','strictNestedSchemasQualified','serialCompletionQualified','ceiling65536Accepted','nativePropsSlotsReviewed','nodeDTOReviewed','noReplay','noQuarantineClear','existingPassiveObserverAuthorized'])assert.equal(g[k],true,k);
 assert.match(g.ownerSha256,/^[a-f0-9]{64}$/); // current protected W1 production closure, reviewed in existing gate; no stale winner pin
 assert.equal(g.toolsSha256,'80e7a1e12e073ac57638e86638cf571158711ff821c96605135627777ce44e8c');
 assert.equal(g.maxInput,16383);assert.equal(g.maxOutput,65536);assert.equal(g.wallSeconds,1380);
 // Current root review + current W1 lane handoff is the source gate. No rolling JSON expiry.
 assert(Number.isFinite(Date.parse(g.issuedUtc))&&Date.parse(g.issuedUtc)<=Date.now());
 assert([1000192,1000000,950000,917504].includes(g.context));
 for(const name of ['live.mjs','preflight-cli.mjs','guards.mjs','preflight.mjs','prompts.json','supervise.py','edge.mjs','check.mjs','policy-a.txt','policy-b.txt'])evidenceFile(join(driverDir,name),g.driverSha256?.[name]);
 assert(g.receipts?.length>=2);for(const r of g.receipts){assert(r.path.startsWith(TASKROOT+'/'));evidenceFile(r.path,r.sha256);}
 evidenceFile(resolve(args['--activation-manifest']),g.activationManifestSha256);
 assert(g.releaseSha256?.['server/dist/active-frontier.js']==='3a4b7f6a2563fd1c123cc14532fdd29c1ba3613544c87f7a3056b17bfefa0c35');
 for(const name of ['deploy/run-engine.sh','deploy/engine/configure-profile.mjs','config/active-frontier.json','config/mimo-candidate.json'])assert.match(g.releaseSha256[name],/^[a-f0-9]{64}$/);
 assert.equal(g.releaseSha256['deploy/engine/configure-profile.mjs'],PROFILE_SHA256);
 assert.equal(g.releaseSha256['deploy/run-engine.sh'],'b315d97a14d76ac617222fd074d046f0e9c04575d81317fb50a17d357c5092d1');
 assert.equal(g.releaseSha256['server/dist/gateway.js'],'6757fc31c791e132fd408f416a12b032994f5a96914fb6086bbb4833baa528de','reviewed status/timeout artifact missing');
 assert.equal(g.releaseSha256['server/dist/system-registry.js'],'8938652968cd69a621395e98eda5c21e9128114bad06023be70c769af683cb1b','reviewed status/timeout artifact missing');
 assert.equal(g.releaseSha256['config/system-registry.json'],'a2d69b9ba6ddba922b9ec128ce2a7cf89e16602154d47fafc5376dd3f1bf5ddc','reviewed status/timeout artifact missing');
 ({validateMimoIntegration:validateIntegration,readMimoEvidence:readEvidence}=await import(pathToFileURL(join(RELEASE,'server/dist/mimo-frontier.js'))));
 reviewed=g;IMAGE=g.image;const promoted=checkPromoted();assertAdmission();
 privateFile(KEY);const observerCredential=privateFile('/home/user/.config/ai-harness/node-control-key');
 return {gate:g,promoted,observerCredential};
}
