/** Finite root-signed normal-parent generation acceptance. Never global evidence. */
import {createHash,createHmac,timingSafeEqual} from 'node:crypto';
import {constants,openSync,closeSync,fstatSync,lstatSync,realpathSync,readFileSync,writeFileSync} from 'node:fs';
import {dirname,isAbsolute,join} from 'node:path';
import {canonicalJson} from './codex-canonical.js';
import {codexReceiptSourceProfile,observeCodexProducer,type CodexReceiptIdentity} from './codex-receipts.js';
import {assertOrdinaryProtectedPaths,type CodexOrdinaryGenerationAuthority} from './codex-ordinary-entry.js';
const uuid=(v:unknown):v is string=>typeof v==='string'&&/^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/.test(v);
const sha=(v:string)=>createHash('sha256').update(v).digest('hex');
function privateDirectory(path:string){
 const uid=process.getuid?.();
 if(!isAbsolute(path)||realpathSync(path)!==path)throw Error('Unsafe generation acceptance path');
 for(let p=path;;p=dirname(p)){const s=lstatSync(p);if(!s.isDirectory()||s.isSymbolicLink()||![0,uid].includes(s.uid)||(s.mode&(p===path?0o077:0o022)))throw Error('Unsafe generation acceptance ancestry');if(p===dirname(p))break;}
 if(lstatSync(path).uid!==uid)throw Error('Generation acceptance directory owner mismatch');
}
function privateBytes(path:string,max:number){
 privateDirectory(dirname(path));if(realpathSync(path)!==path)throw Error('Unsafe generation acceptance alias');
 const fd=openSync(path,constants.O_RDONLY|constants.O_NOFOLLOW);
 try{const st=fstatSync(fd);if(!st.isFile()||st.uid!==process.getuid?.()||st.nlink!==1||(st.mode&0o777)!==0o600||st.size<1||st.size>max)throw Error('Unsafe generation acceptance file');const raw=readFileSync(fd);if(raw.length!==st.size)throw Error('Changing generation acceptance file');return raw;}finally{closeSync(fd);}
}
export interface CodexGenerationAcceptanceTicket {
 schema:'codex-normal-generation-acceptance-v1';reviewedBy:'root';id:string;sessionId:string;
 issuedAtMs:number;expiresAtMs:number;maxNativeRuns:1;maxImageJobs:1;operation:'generation';size:'1920x1080';
 authority:CodexOrdinaryGenerationAuthority;owner:CodexReceiptIdentity;
}
/** Pure signature/scope validation; production additionally rechecks executing sources and owner. */
export function validateCodexGenerationAcceptance(envelope:any,key:Buffer,authority:CodexOrdinaryGenerationAuthority,owner:CodexReceiptIdentity,now=Date.now()):CodexGenerationAcceptanceTicket {
 if(key.length!==32||!envelope||Object.keys(envelope).sort().join()!=='body,seal'||typeof envelope.seal!=='string'||!/^[a-f0-9]{64}$/.test(envelope.seal)||!timingSafeEqual(Buffer.from(envelope.seal,'hex'),createHmac('sha256',key).update(canonicalJson(envelope.body)).digest()))throw Error('Unsigned generation acceptance');
 const b=envelope.body;
 if(!authority||Object.keys(authority).sort().join()!=='currentSourceSha256,profile,receiptSourcesSha256,sourceCommit'||!/^[a-f0-9]{40}$/.test(authority.sourceCommit)||![authority.currentSourceSha256,authority.receiptSourcesSha256].every(v=>/^[a-f0-9]{64}$/.test(v))||!owner||Object.keys(owner).sort().join()!=='bootId,cgroupPath,pid,startTicks,uid'||!Number.isSafeInteger(owner.pid)||owner.pid<1||!Number.isSafeInteger(owner.uid)||owner.uid<1||!/^\d+$/.test(owner.startTicks)||!uuid(owner.bootId)||typeof owner.cgroupPath!=='string'||!owner.cgroupPath.startsWith('/')||!Number.isSafeInteger(now))throw Error('Malformed generation source/owner authority');
 if(!b||Object.keys(b).sort().join()!==['schema','reviewedBy','id','sessionId','issuedAtMs','expiresAtMs','maxNativeRuns','maxImageJobs','operation','size','authority','owner'].sort().join()||b.schema!=='codex-normal-generation-acceptance-v1'||b.reviewedBy!=='root'||!uuid(b.id)||!uuid(b.sessionId)||!Number.isSafeInteger(b.issuedAtMs)||!Number.isSafeInteger(b.expiresAtMs)||b.issuedAtMs>now||b.expiresAtMs<=now||b.expiresAtMs<=b.issuedAtMs||b.expiresAtMs-b.issuedAtMs>30*60*1000||b.maxNativeRuns!==1||b.maxImageJobs!==1||b.operation!=='generation'||b.size!=='1920x1080'||!['generation','technical-generation'].includes(authority.profile)||canonicalJson(b.authority)!==canonicalJson(authority)||canonicalJson(b.owner)!==canonicalJson(owner))throw Error('Invalid generation acceptance scope');
 return Object.freeze(b);
}
export function createHostGenerationAcceptance(policy:string,keyPath:string,source:{authority:CodexOrdinaryGenerationAuthority;assertCurrent():void;assertNativeReceipt(receipt:Parameters<typeof assertOrdinaryProtectedPaths>[0]):void},activeRunId:(sessionId:string)=>string|undefined,now:()=>number=Date.now,owner:()=>CodexReceiptIdentity=()=>observeCodexProducer(process.pid,process.pid,process.getuid?.()!)) {
 const key=privateBytes(keyPath,32);if(key.length!==32)throw Error('Invalid existing ordinary approval key');
 const read=()=>{source.assertCurrent();return validateCodexGenerationAcceptance(JSON.parse(privateBytes(policy,16384).toString('utf8')),key,source.authority,owner(),now());};
 privateDirectory(dirname(policy));
 // An absent packet grants nothing. Root can sign the exact new session and
 // current app PID after startup, before enqueueing its controlling UI turn.
 if(lstatSync(policy,{throwIfNoEntry:false}))read(); // Present invalid policy fails closed.
 let target:string|undefined;
 let bound:{ticket:CodexGenerationAcceptanceTicket;runId:string;revoked:boolean;job?:{requestId:string;bodySha256:string}}|undefined;
 let consumed=false,launched=false,receiptAccepted=false,closed=false;
 const eligible=(sessionId:string)=>{
  if(closed||!bound||bound.revoked||bound.ticket.sessionId!==sessionId)return false;
  try{if(canonicalJson(read())!==canonicalJson(bound.ticket)){bound.revoked=true;return false;}return activeRunId(sessionId)===bound.runId;}catch{bound.revoked=true;return false;}
 };
 return {
  onRunAccepted(sessionId:string,runId:string){
   if(consumed||!uuid(runId))return;
   try{const ticket=read();if(ticket.sessionId!==sessionId)return;consumed=true;
    target=join(dirname(policy),ticket.id);privateDirectory(target!);writeFileSync(join(target!,'binding.json'),JSON.stringify({schema:1,ticket,runId,boundAtMs:now(),settlementClaim:false})+'\n',{flag:'wx',mode:0o600});
    bound={ticket,runId,revoked:false};
   }catch{/* No grant on failure, and a consumed ticket cannot retry. */}
  },
  generation:eligible,
  // Creation expiry/native completion never releases or requalifies the single
  // already claimed broker job. Its existing deadlines/ownership/settlement win.
  generationJob(sessionId:string){
   if(closed||!receiptAccepted||!bound?.job||bound.ticket.sessionId!==sessionId)return false;
   try{source.assertCurrent();return canonicalJson(owner())===canonicalJson(bound.ticket.owner);}catch{return false;}
  },
  authorizeLaunch(sessionId:string){
   if(launched||!eligible(sessionId))return false;
   try{privateDirectory(target!);writeFileSync(join(target!,'native-launch-claim.json'),JSON.stringify({runId:bound!.runId,claimedAtMs:now(),settlementClaim:false})+'\n',{flag:'wx',mode:0o600});launched=true;return true;}catch{bound!.revoked=true;return false;}
  },
  authorizeJob(sessionId:string,body:unknown){
   if(!receiptAccepted||!eligible(sessionId)||!body||typeof body!=='object'||Array.isArray(body))return false;
   const b=body as Record<string,unknown>;
   if(Object.keys(b).some(k=>!['requestId','operation','prompt','size','seed','references'].includes(k))||!uuid(b.requestId)||b.operation!=='generation'||(b.size!==undefined&&b.size!=='1920x1080')||(b.references!==undefined&&(!Array.isArray(b.references)||b.references.length!==0))||typeof b.prompt!=='string'||!b.prompt.trim())return false;
   const claim={requestId:b.requestId,bodySha256:sha(canonicalJson(b))};
   if(bound!.job)return canonicalJson(bound!.job)===canonicalJson(claim);
   try{privateDirectory(target!);writeFileSync(join(target!,'job-claim.json'),JSON.stringify({...claim,runId:bound!.runId,claimedAtMs:now(),settlementClaim:false})+'\n',{flag:'wx',mode:0o600});bound!.job=claim;return true;}catch{bound!.revoked=true;return false;}
  },
  assertLaunch(receipt:Parameters<typeof assertOrdinaryProtectedPaths>[0]){
   try{
    if(!launched||!eligible(receipt.sessionId)||!reviewedCodexSourceFlags(receipt.sources)?.generation)throw Error('Generation acceptance lost or mismatched before native receipt');
    source.assertNativeReceipt(receipt);assertOrdinaryProtectedPaths(receipt,[policy,keyPath,target!]);
    privateDirectory(target!);writeFileSync(join(target!,'native-receipt-binding.json'),JSON.stringify({runId:bound!.runId,nativeReceiptRunId:receipt.runId,nonce:receipt.nonce,sourcesSha256:sha(canonicalJson(receipt.sources)),acceptedAtMs:now(),settlementClaim:false})+'\n',{flag:'wx',mode:0o600});receiptAccepted=true;
   }catch(error){if(bound)bound.revoked=true;throw error;}
  },
  onRunFinished(sessionId:string,runId:string){if(bound?.ticket.sessionId===sessionId&&bound.runId===runId)bound.revoked=true;},
  close(){closed=true;if(bound)bound.revoked=true;},
 };
}
/** Reviewed source superset may contain an unavailable feature; no feature is granted here. */
export function reviewedCodexSourceFlags(sources:Readonly<Record<string,string>>|undefined){
 if(sources&&Object.values(sources).every(v=>/^[a-f0-9]{64}$/.test(v)))for(const technical of [false,true])for(const generation of [false,true])if(Object.keys(sources).sort().join()===[...codexReceiptSourceProfile(technical,generation)].sort().join())return {technical,generation};
 return undefined;
}
