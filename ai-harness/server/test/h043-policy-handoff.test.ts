/** Synthetic host-authority/SQLite/private-file fixtures. No Linux transport or native PASS. */
import test,{mock,type TestContext} from "node:test";
import assert from "node:assert/strict";
import {mkdtempSync,realpathSync,mkdirSync,writeFileSync,readFileSync,chmodSync,rmSync} from "node:fs";
import {tmpdir} from "node:os";
import {join} from "node:path";
import {createHash,createHmac,randomBytes} from "node:crypto";
import {Store} from "../src/store.js";
import {receiptFixture} from "./helpers/codex-receipt-fixture.js";
import {adoptCodexPolicyHandoff,retainCodexPolicyHandoff,type AdoptCodexPolicyHandoffInput} from "../src/codex-policy-handoff.js";
import {revalidateRetainedCodexReceipts} from "../src/codex-receipts.js";
import {canonicalJson} from "../src/codex-canonical.js";
import {CODEX_H041_DELIVERY04_WINDOW,createCodexDelivery04Policy,createCodexRetentionParent04Policy,assertCodexTextOnlyPolicy,CODEX_PARENT_ARTIFACT_SPEC,createCodexTextOnlyPolicy,createCodexContinuationPolicy,createCodexDeliveryPolicy,createCodexRetentionParentPolicy,CODEX_H041_DELIVERY_WINDOW,CODEX_H041_WINDOW,CODEX_H041_CONTINUATION_WINDOW,codexPolicyOwnsSettledThread,codexPolicyOwner,validateCodexPolicyFreshLaunch,stageCodexPolicyAdoption} from "../src/codex-probe.js";
import {validateSessionRestartOwnership} from "../src/session-checkpoint.js";
// Explicit historical clock for SOURCE fixtures; production expiry remains enforced.
mock.timers.enable({apis:["Date"],now:CODEX_H043_WINDOW.startAtMs+60_000});
const sha=(b:string|Uint8Array)=>createHash("sha256").update(b).digest("hex");
function fixture(t:TestContext,collaborationVersion?:"v1"|"v2") {
 const root=realpathSync(mkdtempSync(join(tmpdir(),"h041-handoff-"))),directory=join(root,"handoff"),profile=join(root,"profile"),workspace=join(root,"workspace");for(const p of [directory,profile,workspace,join(profile,"codex-home"),join(profile,"codex-home","sessions")])mkdirSync(p,{mode:0o700});
 const store=new Store(join(root,"harness.sqlite"));chmodSync(store.databasePath,0o600);const session=store.createSession(undefined,"codex"),run=store.createRun(session,"message","synthetic",[]);store.setNative(session.id,"thread-1","codex");store.setNativeState(session.id,"codex",{ownership:"idle",activeTurnId:null,eventCursor:1});store.checkpoints.prepare(session.id,run.id,"message","thread-1");store.checkpoints.finish(session.id,run.id,"completed");store.updateRun(run.id,"completed");
 const f=receiptFixture(),uid=process.getuid!(),gid=process.getgid!(),prefix=`user.slice/user-${uid}.slice/user@${uid}.service/aiharnesstasks.slice`;
 Object.assign(f.binding,{uid,gid,sessionId:session.id,profileDir:profile,workspace});Object.assign(f.producer,{uid,cgroupPath:"/"+prefix+"/fixture.scope"});Object.assign(f.rawLaunch,{sessionId:session.id,producer:f.producer});Object.assign(f.rawLaunch.egress,{uid,cgroupPath:prefix});Object.assign(f.rawLaunch.container,{profileDir:profile,workspace,workdir:workspace,user:`${uid}:${gid}`});
 for(const m of f.rawLaunch.container.mounts){if(m.source==="/task/profile"){m.source=profile;m.destination=profile;}else if(m.source==="/task/workspace"){m.source=workspace;m.destination=workspace;}if(m.destination.startsWith("/task/profile/"))m.destination=profile+m.destination.slice("/task/profile".length);}
 Object.assign(f.rawSettlement,{sessionId:session.id,producer:f.producer});
 const evidenceKey=randomBytes(32);writeFileSync(store.databasePath+".h041-native-evidence.key",evidenceKey,{mode:0o600});
 const signed=(event:any)=>{const receipt=event.receipt;const payload={sessionId:session.id,runId:run.id,event:{...event,observation:"genuine-host-observation"},launchRawSha256:sha(JSON.stringify(f.rawLaunch)),launchValidation:{binding:f.binding,observedProducer:f.producer,validatedAtMs:f.now},...(receipt?{receiptRawSha256:sha(JSON.stringify(receipt)),receiptUtf8:JSON.stringify(receipt)}:{})};store.db.prepare("INSERT INTO h041_checkpoint_native_evidence VALUES(?,?,?,?)").run(session.id,run.id,event.kind,JSON.stringify({payload,seal:createHmac("sha256",evidenceKey).update(JSON.stringify(payload)).digest("hex")}));};
 const checkpoints=[];for(const [name,index] of [["recall.json",1],["state.json",2]] as const){const id="artifact-"+index,digest=sha("{}");store.saveFile({id,sessionId:session.id,kind:"artifact",path:id,name,mimeType:"application/json",size:2,runId:run.id});store.memory.retain(session.id,"file",id,Buffer.from("{}"));const record={checkpointId:"cp",threadId:"thread-1",turnId:"turn-1",callId:"call-"+index,name,artifactId:id,sha256:digest};checkpoints.push(record);signed({kind:"checkpoint_artifact",...record});}
 for(const [kind,receipt] of [["launch",f.rawLaunch],["settlement",f.rawSettlement]] as const)signed({kind,receipt});
 const rolloutPath=join(profile,"codex-home","sessions","rollout.jsonl"),rawRollout=JSON.stringify({type:"session_meta",payload:{id:"thread-1",cli_version:"0.158.0",model_provider:"sova",dynamic_tools:JSON.parse(canonicalJson([CODEX_PARENT_ARTIFACT_SPEC]))}})+"\n";writeFileSync(rolloutPath,rawRollout,{mode:0o600});
 signed({kind:"thread",threadId:"thread-1",rolloutPath,method:"thread/start"});signed({kind:"gateway_settled",threadId:"thread-1",activeTurnId:null,lastSettledTurnId:"turn-1"});
 const proof=store.checkpoints.issueRestartOwnership({sessionId:session.id,runId:run.id,checkpointId:"cp",threadId:"thread-1"});
 const source=join(root,"source.js");writeFileSync(source,"synthetic source closure",{mode:0o600});const sourceClosure={[source]:sha(readFileSync(source))},keyPath=join(root,"handoff.key"),key=randomBytes(32);writeFileSync(keyPath,key,{mode:0o600});
 const fields={sessionId:session.id,runId:f.binding.runId,configSha256:"b".repeat(64),modelCatalogSha256:"b".repeat(64)};const policy=collaborationVersion?createCodexH043RetentionParentPolicy({...fields,collaborationVersion}):createCodexH043Policy({...fields,mode:"parent-artifacts"});
 const stat=awaitlessStat(rolloutPath),body={schema:"codex-policy-handoff-v1",sessionId:session.id,threadId:"thread-1",checkpointId:"cp",policy,settledTurnId:"turn-1",checkpoints:checkpoints.map(({threadId,...c})=>c),validation:{binding:f.binding,observedProducer:f.producer,validatedAtMs:f.now},launch:{sha256:sha(JSON.stringify(f.rawLaunch)),originalPath:"/original/private/launch.json"},settlement:{sha256:sha(JSON.stringify(f.rawSettlement)),originalPath:"/original/private/settlement.json"},rollout:{path:rolloutPath,sha256:sha(rawRollout),bytes:Buffer.byteLength(rawRollout),device:stat.dev,inode:stat.ino},sourceClosure,ownership:validateSessionRestartOwnership(proof)};
 // Synthetic sealed producer equivalent: source test owns the private key. This does NOT emulate genuine live OOB transport.
 writeFileSync(join(directory,"launch.raw.json"),JSON.stringify(f.rawLaunch),{mode:0o600});writeFileSync(join(directory,"settlement.raw.json"),JSON.stringify(f.rawSettlement),{mode:0o600});const path=join(directory,"handoff.json");
 const seal=()=>{writeFileSync(path,JSON.stringify({body,seal:createHmac("sha256",key).update(JSON.stringify(body)).digest("hex")})+"\n",{mode:0o600});return sha(readFileSync(path));};
 const input:AdoptCodexPolicyHandoffInput={path,sha256:seal(),keyPath,sessionId:session.id,threadId:"thread-1",checkpointId:"cp",runId:"new-run",configSha256:"b".repeat(64),modelCatalogSha256:"b".repeat(64),sourceClosure,ownership:proof,authorization:"h043"};
 t.after(()=>{store.close();rmSync(root,{recursive:true,force:true});});return {input,body,store,session,run,source,rolloutPath,seal,f};
}
import {statSync as awaitlessStat} from "node:fs";

import {CODEX_H043_WINDOW,createCodexH043Policy,createCodexH043RetentionParentPolicy} from '../src/codex-probe.js';
import {reconstructCodexPolicyHandoffPolicy} from '../src/codex-policy-handoff.js';
for(const collaborationVersion of [undefined,'v1','v2'] as const)test(`H043 genuine factory reconstruction and sealed synthetic adoption ${collaborationVersion??'parent'}`,t=>{
 const f=fixture(t,collaborationVersion),original=readFileSync(join(f.input.path,'..','launch.raw.json')),p=adoptCodexPolicyHandoff(f.input);assert.equal(p.window,CODEX_H043_WINDOW);assert.equal(p.mode,collaborationVersion?'retention-parent':'parent-artifacts');assert.equal(p.collaborationVersion,collaborationVersion);assert.equal(codexPolicyOwner(p)!.pendingFreshLaunch,true);assert.deepEqual(readFileSync(join(f.input.path,'..','launch.raw.json')),original);assert.throws(()=>validateCodexPolicyFreshLaunch(p,f.f.launch));assert.throws(()=>adoptCodexPolicyHandoff(f.input));
});
for(const kind of ['seal','raw_receipt','rollout','source','foreign','quarantine','recovery','ownership_json','chronology','authorization','collaboration','expired'] as const)test(`H043 original guard rejects ${kind}`,t=>{
 const f=fixture(t,'v2');
 if(kind==='seal')writeFileSync(f.input.path,readFileSync(f.input.path,'utf8').replace('"seal":"','"seal":"0'));
 if(kind==='raw_receipt')writeFileSync(join(f.input.path,'..','launch.raw.json'),'{}');
 if(kind==='rollout')writeFileSync(f.rolloutPath,'changed');if(kind==='source')writeFileSync(f.source,'changed');if(kind==='foreign')f.input.sessionId='foreign';if(kind==='quarantine')f.store.quarantine(f.session.workspaceId,'uncertain');if(kind==='recovery')f.store.db.prepare("UPDATE h041_session_checkpoints SET status='recovery_required'").run();if(kind==='ownership_json')f.input.ownership=structuredClone(f.input.ownership);if(kind==='chronology'){f.body.validation.validatedAtMs+=20000;f.input.sha256=f.seal();}if(kind==='authorization')f.input.authorization='unknown' as never;
 if(kind==='collaboration'){(f.body.policy as any)={...f.body.policy,collaborationVersion:'post-sampling-token-usage-v2'};f.input.sha256=f.seal();}
 if(kind==='expired')mock.timers.setTime(CODEX_H043_WINDOW.expiresAtMs);
 try{assert.throws(()=>adoptCodexPolicyHandoff(f.input));}finally{mock.timers.setTime(CODEX_H043_WINDOW.startAtMs+60_000);}
});
test('H043 handoff factory dispatch rejects unknown, keeps historical source windows unchanged',()=>{
 const fields={sessionId:'s',runId:'r',configSha256:'b'.repeat(64),modelCatalogSha256:'b'.repeat(64)};
 for(const [authorization,window] of [['continuation02',CODEX_H041_CONTINUATION_WINDOW],['delivery03',CODEX_H041_DELIVERY_WINDOW],['delivery04',CODEX_H041_DELIVERY04_WINDOW],['h043',CODEX_H043_WINDOW]] as const)assert.equal(reconstructCodexPolicyHandoffPolicy({...fields,mode:'parent-artifacts',authorization}).window,window);
 for(const patch of [{authorization:'unknown'},{mode:'retention-parent'},{mode:'parent-artifacts',collaborationVersion:'v2'}])assert.throws(()=>reconstructCodexPolicyHandoffPolicy({...fields,mode:'parent-artifacts',authorization:'h043',...patch} as any));
});
