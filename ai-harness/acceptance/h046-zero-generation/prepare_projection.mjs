/** Read-only projection check; root approval/signing/publication are separate. */
import {readFileSync,writeFileSync} from 'node:fs';
import {pathToFileURL} from 'node:url';
import {join} from 'node:path';
import {createHash} from 'node:crypto';
const sha=b=>createHash('sha256').update(b).digest('hex');
const need=(v,m)=>{if(!v)throw Error(m);};
const [inputPath,proofDir,approvalId,outputPath]=process.argv.slice(2);
try{
 need(inputPath&&proofDir&&approvalId&&outputPath,'INPUT PROOF_DIR ROOT_APPROVAL_ID OUTPUT required');
 const input=JSON.parse(readFileSync(inputPath,'utf8')),carrier=JSON.parse(readFileSync(join(proofDir,'carrier-result.json'),'utf8')),driver=JSON.parse(readFileSync(join(proofDir,'driver-result.json'),'utf8'));
 need(driver.status==='ACTUAL_NO_GENERATION_PROOF_ROOT_REVIEW_REQUIRED'&&driver.actualWaitExit===0&&carrier.status==='CARRIER_PROTOCOL_VALID'&&carrier.launchCurrentProvenance===true&&carrier.settlementCurrentProvenance===true&&carrier.projection,'Missing actual original current-producer/closure evidence');
 const q=carrier.projection;for(const [path,digest]of [['launchPath','launchSha256'],['settlementPath','settlementSha256'],['protocolAckPath','protocolAckSha256'],['legacyTransportPath','legacyTransportSha256'],['rawProtocolPath','rawProtocolSha256'],['binaryPath','binarySha256']])need(sha(readFileSync(q[path]))===q[digest],'Original evidence changed');
 const {assertOrdinaryNoGenerationObservation}=await import(pathToFileURL(join(input.serverDir,'dist/codex-ordinary-entry.js')));
 const ack=JSON.parse(readFileSync(q.protocolAckPath,'utf8')),legacy=JSON.parse(readFileSync(q.legacyTransportPath,'utf8'));assertOrdinaryNoGenerationObservation(ack,legacy,q);
 need(ack.threadStart.thread.id===carrier.nativeThreadId,'Actual ACK/thread projection mismatch');
 // This projection cannot recreate WeakSet provenance. Root's later HMAC is its
 // evidence review decision, exactly as documented by the existing loader.
 const body={schema:'codex-ordinary-entry-v1',approvalId,sourceCommit:input.appSourceCommit,files:input.ordinaryFiles,receiptSources:input.receiptSources,qualification:q};
 const raw=JSON.stringify({status:'UNSIGNED_ROOT_REVIEW_REQUIRED',body});writeFileSync(outputPath,raw,{flag:'wx',mode:0o600});console.log('UNSIGNED_ORIGINAL_PROJECTION_PREPARED');
}catch(error){console.error(String(error.message));process.exitCode=1;}
