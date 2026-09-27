/** H009 preflight adapted to exact H016 release; every contact follows the root gate. */
import assert from 'node:assert/strict';
import {readFileSync,lstatSync,realpathSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
import {join,resolve,dirname} from 'node:path';
import {sha} from './guards.mjs';
export const SOURCE='df0702412b1a8f594db7d3211ca63f6aafe8a026';
export let IMAGE;
export const REV='7ac59a6e3ad851cd41af00f678effab0598ba9a8';
export const RELEASE=`/opt/ai-harness/releases/${SOURCE}-h016/ai-harness`;
export const TASKROOT='/home/user/ai-harness-build/H016-FINAL-INTEGRATION-20260927';
export const RUNROOT=TASKROOT+'/live-acceptance-01';
export const KEY='/home/user/.config/ai-harness/inference-key';
const BASE='6641df04cf4e8375029639a67c22da7c3ff4719d2b8e58748572f049de8fb022';
const TAG='localhost/ai-harness-engine:0.0.2-ae65651df5f9';
let reviewed;
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
 assert(Date.now()<Date.parse(reviewed.expiresUtc)-60000,'admission deadline');
 assert.equal(execFileSync('systemctl',['--user','show','ai-harness.service','-p','ActiveState','--value'],{encoding:'utf8',timeout:5000}).trim(),'inactive');
 assert.equal(execFileSync('systemctl',['--user','show','ai-harness.service','-p','MainPID','--value'],{encoding:'utf8',timeout:5000}).trim(),'0');
 const info=JSON.parse(podman('image','inspect',TAG))[0];assert.equal(info.Id.replace(/^sha256:/,''),IMAGE);
 const base=JSON.parse(podman('image','inspect',BASE))[0];assert.deepEqual(info.RootFS.Layers.slice(0,-1),base.RootFS.Layers);
 const unit=readFileSync('/home/user/.config/systemd/user/ai-harness.service','utf8');assert(unit.includes(RELEASE+'/'));
 for(const [file,hash]of Object.entries(reviewed.releaseSha256))evidenceFile(join(RELEASE,file),hash);
 const active=JSON.parse(readFileSync(join(RELEASE,'config/active-frontier.json')));assert.equal(active.model,'mimo-v2.6-pro-rl');assert.equal(active.mimoContextWindow,131072);assert.equal(active.mimoMaxOutputTokens,65536);assert.equal(active.mimoQualificationSha256,reviewed.qualificationSha256);
 evidenceFile('/etc/sova-qualification/mimo.json',reviewed.qualificationSha256);
 const imageConfig=podman('run','--rm','--pull=never','--http-proxy=false','--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges','--entrypoint','cat',IMAGE,'/opt/ai-harness/config/active-frontier.json');
 assert.equal(imageConfig,readFileSync(join(RELEASE,'config/active-frontier.json'),'utf8').trim());
 const free=execFileSync('df',['-B1','--output=avail',TASKROOT],{encoding:'utf8',timeout:5000}).trim().split(/\s+/).at(-1);assert(Number(free)>21474836480);
 return {source:SOURCE,image:IMAGE,context:131072,profileOutput:65536,uppers:'inactive'};
}
export function preflight(args,driverDir){
 assert.fail('HELD: final capacity/settings and profile tuple require separate root review; 131072 proposal superseded');
 const file=resolve(args['--gate']);privateFile(file);evidenceFile(file,args['--gate-sha256']);const g=JSON.parse(readFileSync(file));
 assert.equal(g.authorization,'ROOT_GO_H016_NATIVE_APP_ACCEPTANCE');assert.equal(g.source,SOURCE);assert.match(g.image,/^[a-f0-9]{64}$/);assert.notEqual(g.image,BASE);
 for(const k of ['worker1LaneReleased','liveInferenceAuthorized','productionOwnerCurrent','full17Qualified','strictNestedSchemasQualified','serialCompletionQualified','ceiling65536Accepted','nativePropsSlotsReviewed','nodeDTOReviewed','noReplay','noQuarantineClear','existingPassiveObserverAuthorized'])assert.equal(g[k],true,k);
 assert.equal(g.ownerSha256,'ee5d623f3334afba341e1539383ca672f7f4db096cf329adf1c69d2b871ec814');
 assert.equal(g.toolsSha256,'80e7a1e12e073ac57638e86638cf571158711ff821c96605135627777ce44e8c');
 assert.equal(g.maxInput,16383);assert.equal(g.maxOutput,65536);assert.equal(g.wallSeconds,600);
 const now=Date.now(),issued=Date.parse(g.issuedUtc),expiry=Date.parse(g.expiresUtc);
 assert(Number.isFinite(issued)&&issued<=now&&now-issued<300000&&expiry>now+120000&&expiry<=Date.parse('2026-09-27T17:38:08Z'));
 for(const name of ['live.mjs','preflight-cli.mjs','guards.mjs','preflight.mjs','prompts.json','supervise.py','edge.mjs','check.mjs','policy-a.txt','policy-b.txt'])evidenceFile(join(driverDir,name),g.driverSha256?.[name]);
 assert(g.receipts?.length>=2);for(const r of g.receipts){assert(r.path.startsWith(TASKROOT+'/'));evidenceFile(r.path,r.sha256);}
 evidenceFile(resolve(args['--activation-manifest']),g.activationManifestSha256);
 assert(g.releaseSha256?.['server/dist/active-frontier.js']==='3a4b7f6a2563fd1c123cc14532fdd29c1ba3613544c87f7a3056b17bfefa0c35');
 for(const name of ['deploy/run-engine.sh','deploy/engine/configure-profile.mjs','config/active-frontier.json','config/mimo-candidate.json'])assert.match(g.releaseSha256[name],/^[a-f0-9]{64}$/);
 reviewed=g;IMAGE=g.image;const promoted=checkPromoted();
 privateFile(KEY);const observerCredential=privateFile('/home/user/.config/ai-harness/node-control-key');
 return {gate:g,promoted,observerCredential};
}
