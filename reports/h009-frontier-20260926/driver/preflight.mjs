import assert from 'node:assert/strict';
import {readFileSync,lstatSync,realpathSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
import {join,resolve,dirname} from 'node:path';
import {sha} from './guards.mjs';
export const SOURCE='296ae49e44eb250773223885b843994e2c5b9bcc';
export const IMAGE='c328dac0e6ede1dfb890a0657ebafd6f6fd4a1f2281f4e1c664ab95db7dcaa20';
export const REV='eb9eb208eb0d988989d07a6a12d0fdeb5f52574a';
export const ALIAS='localhost/ai-harness-engine:0.0.2-ae65651df5f9';
export const RELEASE=`/opt/ai-harness/releases/${SOURCE}/ai-harness`;
export const TASKROOT='/home/user/ai-harness-build/H009-FRONTIER-20260926';
export const RUNROOT=TASKROOT+'/live-acceptance-01';
export const KEY='/home/user/.config/ai-harness/inference-key';
// Hash-bound public evidence is not a credential. Both classes retain canonical,
// regular-file, single-link and trusted-owner checks. No group/world writes.
export function evidenceFile(file, expectedSha) {
  checkedFile(file, false);
  assert.match(expectedSha, /^[a-f0-9]{64}$/, 'invalid evidence digest: '+file);
  assert.equal(sha(readFileSync(file)), expectedSha, 'evidence digest mismatch: '+file);
  return file;
}
export function checkedFile(file, isPrivate) {
  const label=isPrivate ? 'private file' : 'public evidence '+file;
  assert.equal(realpathSync(file),file,'noncanonical '+label);
  const s=lstatSync(file);
  assert(s.isFile() && s.nlink===1 && [0,process.getuid()].includes(s.uid), 'unsafe type/link/owner: '+label);
  assert(!(s.mode & (isPrivate ? 0o077 : 0o022)), 'unsafe permissions: '+label);
  for(let p=dirname(file);;p=dirname(p)) {
    const d=lstatSync(p);
    assert(d.isDirectory() && !d.isSymbolicLink() && [0,process.getuid()].includes(d.uid) && !(d.mode&0o022), 'unsafe ancestry: '+label);
    if(dirname(p)===p)break;
  }
  return file;
}
export const privateFile=file=>checkedFile(file,true);
export const podman=(...args)=>execFileSync('/usr/bin/podman',['--remote=false',...args],{encoding:'utf8',timeout:30000,env:{HOME:'/home/user',PATH:'/usr/bin:/bin',XDG_RUNTIME_DIR:'/run/user/1000'}}).trim();
export function checkPromoted() {
  assert.equal(process.platform,'linux');assert.equal(process.getuid(),1000);
  const task=TASKROOT;
  for(const p of ['/home/user','/home/user/ai-harness-build',task]){
    const s=lstatSync(p);assert.equal(realpathSync(p),p);assert(s.isDirectory()&&s.uid===1000&&!(s.mode&0o022),'unsafe task ancestry');
  }
  const free=execFileSync('/usr/bin/df',['-B1','--output=avail',task],{encoding:'utf8',timeout:10000}).trim().split(/\s+/).at(-1);
  assert(Number(free)>21474836480,'reviewed harness 20GiB free-space floor');
  for(const unit of ['ai-harness.service','ai-harness-searxng.service']) {
    assert.equal(execFileSync('/usr/bin/systemctl',['--user','show',unit,'-p','ActiveState','--value'],{encoding:'utf8',timeout:10000}).trim(),'inactive');
    assert.equal(execFileSync('/usr/bin/systemctl',['--user','show',unit,'-p','MainPID','--value'],{encoding:'utf8',timeout:10000}).trim(),'0');
  }
  const info=JSON.parse(podman('image','inspect',ALIAS))[0];
  assert.equal(info.Id.replace(/^sha256:/,''),IMAGE,'production alias is not exact candidate; do not retag here');
  assert.equal(info.Labels['org.opencontainers.image.revision'],'ae65651df5f97ae1085ab4e19964f4b78c769a4e');
  assert.equal(info.Labels['org.opencontainers.image.ai-harness.patchset'],'e487935b3d6efce51216b8755cbd712912c30c7d45f6a9e5e293f0f998f89a65');
  const unit=readFileSync('/home/user/.config/systemd/user/ai-harness.service','utf8');
  assert(unit.includes(RELEASE+'/') && unit.includes('--frontier-key-file '+KEY),'paired unit source/credential missing');
  assert.equal(realpathSync(RELEASE),RELEASE);
  const config=JSON.parse(readFileSync(join(RELEASE,'config/frontier.json')));
  assert(config.qualified===true && config.contextWindow===480000 && config.maxOutputTokens===65536);
  assert(config.tokenizerRevision===REV && config.templateRevision===REV);
  privateFile(KEY); // metadata only until live command is separately admitted
  return {image:IMAGE,source:SOURCE,uppers:'inactive',context:480000,profileOutput:65536};
}
export function checkGate(file,expectedSha,driverDir) {
  privateFile(file);const raw=readFileSync(file,'utf8');assert.equal(sha(raw),expectedSha,'gate digest differs from coordinator dispatch');
  const g=JSON.parse(raw);assert.equal(g.authorization,'ROOT_APPROVED_H009_ISOLATED_LIVE');
  assert(g.source===SOURCE && g.image===IMAGE && g.maxInput===16384 && g.maxOutput===2048 && g.wallSeconds===1200);
  assert(g.promotionComplete===true && g.uppersStopped===true && g.privateCredentialMatch===true);
  assert(g.worker1LaneReleased===true && g.liveInferenceAuthorized===true && g.existingPassiveObserverAuthorized===true);
  assert(g.flashBackendReadyForBoundedAcceptance===true && g.nativePoolReadbackAccepted===true && g.roleArrayToolParityAccepted===true);
  assert(g.noReplay===true && g.noQuarantineClear===true);
  const now=Date.now(),expiry=Date.parse(g.expiresUtc),issued=Date.parse(g.issuedUtc);
  assert(Number.isFinite(issued)&&issued<=now&&now-issued<7200000&&Number.isFinite(expiry)&&expiry>now&&expiry<=Date.parse('2026-09-26T21:52:27Z'));
  assert(g.inputTokensMax===479993 && g.inputPlusOutputMax===479998 && g.contextLimit===480000 && g.revision===REV);
  for(const [name,hash] of Object.entries(g.driverSha256??{})) {
    assert(/^[a-zA-Z0-9_.-]+$/.test(name));evidenceFile(join(driverDir,name),hash);
  }
  for(const name of ['live.mjs','preflight-cli.mjs','guards.mjs','preflight.mjs','prompts.json','supervise.py','edge.mjs','check.mjs','policy-a.txt','policy-b.txt'])assert(g.driverSha256?.[name],'missing reviewed driver hash');
  assert(Array.isArray(g.receipts)&&g.receipts.length>=1,'fresh backend readiness and lane handoff required');
  for(const r of g.receipts){assert(r.path.startsWith(TASKROOT+'/'),'receipt outside H009 task: '+r.path);evidenceFile(r.path,r.sha256);}
  assert(g.qwenExistingIdentityHealthAccepted===true,'reuse existing Qwen identity/health evidence; no new qualification');
  return g;
}
export function nodeCredentialPath() {
  // Read only installed LoadCredential path metadata; never start the stopped unit.
  const setting=execFileSync('/usr/bin/systemctl',['--user','show','ai-harness.service','-p','LoadCredential','--value'],{encoding:'utf8',timeout:10000}).trim();
  const matches=[...setting.matchAll(/(?:^|\s)node-control-key:(\/[^\s;]+)/g)];
  assert.equal(matches.length,1,'existing node observer LoadCredential source unavailable');
  return privateFile(matches[0][1]);
}
export function checkArtifacts(manifest) {
  for(const line of manifest.serverArtifactsManifest.selectedEntries) {
    const [hash,name]=line.split(/\s+/);assert.equal(sha(readFileSync(join(RELEASE,name),'utf8')),hash,'compiled source differs: '+name);
  }
}

export function preflight(args, driverDir, metadataOnly=false) {
  const gate=checkGate(resolve(args['--gate']),args['--gate-sha256'],driverDir);
  evidenceFile(resolve(args['--activation-manifest']),'9d6182c51212e3eb348d398e41b2ace4edb07e8a321974f695d34c7ae554a689');
  const manifest=JSON.parse(readFileSync(args['--activation-manifest'],'utf8'));
  checkArtifacts(manifest);
  evidenceFile(join(RELEASE,'deploy/run-engine.sh'),gate.launcherSha256);
  evidenceFile(join(RELEASE,'deploy/engine/configure-profile.mjs'),gate.configureProfileSha256);
  privateFile(KEY);
  const observerCredential=nodeCredentialPath();
  const promoted=metadataOnly ? null : checkPromoted();
  return {gate,promoted,observerCredential};
}
