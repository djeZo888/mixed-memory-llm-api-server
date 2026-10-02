/** Root-reviewed host entry. Browser/model JSON and configuration booleans cannot activate it. */
import {constants,openSync,closeSync,fstatSync,lstatSync,realpathSync,readFileSync} from "node:fs";
import {dirname,isAbsolute,sep,join,resolve} from "node:path";
import {createHash,createHmac,timingSafeEqual} from "node:crypto";
import {canonicalJson} from "./codex-canonical.js";
import {CODEX_RECEIPT_SOURCES,codexReceiptSourceProfile,assertCodexReceiptSourceClosure,codexReceiptValidation,validateCodexLaunchReceipt,validateCodexSettlementReceipt,codexReceiptProvenance,isHistoricalCodexReceipt,type CodexReceiptBinding,type CodexReceiptIdentity,type CodexNativeLaunchReceipt,type CodexReceiptPolicy} from "./codex-receipts.js";
import {createCodexMetadataAuthority,type CodexMetadataAuthority} from "./codex-turn-metadata.js";
import type {CodexHostQualification} from "./codex-host.js";
export interface CodexOrdinaryEntryBody {
 schema:"codex-ordinary-entry-v1";approvalId:string;sourceCommit:string;
 files:Readonly<Record<string,string>>;receiptSources:Readonly<Record<string,string>>;
 qualification:{launchPath:string;settlementPath:string;launchSha256:string;settlementSha256:string;binding:CodexReceiptBinding;observedProducer:CodexReceiptIdentity;validatedAtMs:number;protocolAckPath:string;protocolAckSha256:string;legacyTransportPath?:string;legacyTransportSha256?:string;rawProtocolPath?:string;rawProtocolSha256?:string;binaryPath:string;binarySha256:string;binaryVersion:"0.158.0";upstream:"064c6b8c737f5b41d171fdda80bd9ef10ad06eb3"};
}
const sha=(b:Uint8Array|string)=>createHash("sha256").update(b).digest("hex");
function privateBytes(path:string,max:number){
 if(!isAbsolute(path)||realpathSync(path)!==path)throw Error("Ordinary entry path is not canonical");const parent=lstatSync(dirname(path));if(!parent.isDirectory()||parent.uid!==process.getuid?.()||(parent.mode&0o077)!==0)throw Error("Ordinary entry parent is not private");
 const fd=openSync(path,constants.O_RDONLY|constants.O_NOFOLLOW);try{const st=fstatSync(fd);if(!st.isFile()||st.uid!==process.getuid?.()||st.nlink!==1||(st.mode&0o777)!==0o600||st.size<1||st.size>max)throw Error("Unsafe ordinary entry file");const bytes=readFileSync(fd);if(bytes.length!==st.size)throw Error("Changing ordinary entry file");return bytes;}finally{closeSync(fd);}
}
function verifyFiles(files:Readonly<Record<string,string>>){if(!files||typeof files!=="object"||Array.isArray(files)||Object.keys(files).length<8||Object.keys(files).length>512)throw Error("Incomplete ordinary source/build closure");for(const [path,digest]of Object.entries(files)){if(!isAbsolute(path)||realpathSync(path)!==path||!/^[a-f0-9]{64}$/.test(digest)||!lstatSync(path).isFile()||sha(readFileSync(path))!==digest)throw Error("Ordinary source/build closure changed");}}
export function assertOrdinaryProtectedPaths(launch:CodexNativeLaunchReceipt,paths:readonly string[]){for(const p of paths)for(const m of [...launch.container.mounts,...launch.container.additionalMounts])if(m.type==="bind"&&isAbsolute(m.source)&&(p===m.source||p.startsWith(m.source+sep)))throw Error("Ordinary approval/evidence is model-mounted");}
/** Explicit complete retained-ID proof. Null usage/count is never rewritten as zero. */
export function assertOrdinaryNoGenerationObservation(ack:unknown, legacy:unknown, expected:{launchSha256:string;settlementSha256:string;rawProtocolSha256:string}){
 const a=ack as any,v=legacy as any;
 if(a?.providerRequests!==null||v?.status!=="PASS"||v.validatedInitialize!==true||v.validatedThread!==true||v.requestedStop!==true||v.cleanupOk!==true||!Number.isInteger(v.engineExitStatus)||v.receipts?.launch?.sha256!==expected.launchSha256||v.receipts?.settlement?.sha256!==expected.settlementSha256||v.rawProtocolSHA256!==expected.rawProtocolSha256)throw Error("Missing actual legacy no-new-request transport proof");
 const before=v.gatewayBefore,after=v.gatewayAfter;
 if(before?.schema!=="legacy-gateway-retained-id-observation-v1"||after?.schema!==before.schema||!Array.isArray(before.requestIds)||new Set(before.requestIds).size!==before.requestIds.length||before.requestIds.some((id:unknown)=>typeof id!=="string")||!before.identity||!before.retainedRecords||!before.counts||!before.nativeOwners)throw Error("Incomplete retained gateway observation");
 for(const key of ["identity","requestIds","retainedRecords","counts","nativeOwners"])if(canonicalJson(before[key])!==canonicalJson(after[key]))throw Error("Legacy gateway owner or retained admission changed");
}

export type CodexOrdinarySourceProfile="ordinary"|"technical"|"generation"|"technical-generation";
export interface CodexOrdinaryCurrentSourceBody {
 schema:"codex-ordinary-current-sources-v1";reviewedBy:"root";reviewedAt:string;
 baselineApprovalSha256:string;baselineApprovalId:string;sourceCommit:string;
 serverDir:string;deploymentDir:string;profile:CodexOrdinarySourceProfile;
 files:Readonly<Record<string,string>>;receiptSources:Readonly<Record<string,string>>;
}
const profileFlags=(profile:CodexOrdinarySourceProfile)=>({technical:profile==="technical"||profile==="technical-generation",generation:profile==="generation"||profile==="technical-generation"});
function verifyCurrentFiles(files:Readonly<Record<string,string>>) {
 verifyFiles(files);
 for(const path of Object.keys(files)){
  const s=lstatSync(path);if(s.isSymbolicLink()||s.nlink!==1||s.mode&0o022||![0,process.getuid?.()].includes(s.uid))throw Error("Unsafe current ordinary source");
  for(let parent=dirname(path);;parent=dirname(parent)){const st=lstatSync(parent);if(!st.isDirectory()||st.isSymbolicLink()||st.mode&0o022||![0,process.getuid?.()].includes(st.uid))throw Error("Unsafe current ordinary source ancestry");if(parent===dirname(parent))break;}
 }
}
/** Fixed protected sidecar authenticates current source only; it grants NO operation. */
export function loadCodexOrdinaryCurrentSources(path:string,key:Buffer,baselineRaw:Buffer,baselineApprovalId:string,runtime:{serverDir:string;deploymentDir:string}):CodexOrdinaryCurrentSourceBody {
 if(key.length!==32)throw Error("Invalid current ordinary approval key");
 for(let parent=dirname(path);;parent=dirname(parent)){const s=lstatSync(parent);if(!s.isDirectory()||s.isSymbolicLink()||s.mode&0o022||![0,process.getuid?.()].includes(s.uid))throw Error("Unsafe current ordinary approval ancestry");if(parent===dirname(parent))break;}
 const raw=privateBytes(path,262144),v=JSON.parse(new TextDecoder("utf-8",{fatal:true}).decode(raw));
 if(Object.keys(v).sort().join()!=="body,seal"||typeof v.seal!=="string"||!/^[a-f0-9]{64}$/.test(v.seal)||!timingSafeEqual(Buffer.from(v.seal,"hex"),createHmac("sha256",key).update(canonicalJson(v.body)).digest()))throw Error("Untrusted current ordinary source approval");
 const b=v.body as CodexOrdinaryCurrentSourceBody;
 if(!b||Object.keys(b).sort().join()!==["schema","reviewedBy","reviewedAt","baselineApprovalSha256","baselineApprovalId","sourceCommit","serverDir","deploymentDir","profile","files","receiptSources"].sort().join()||b.schema!=="codex-ordinary-current-sources-v1"||b.reviewedBy!=="root"||!Number.isFinite(Date.parse(b.reviewedAt))||Date.parse(b.reviewedAt)>Date.now()||b.baselineApprovalSha256!==sha(baselineRaw)||b.baselineApprovalId!==baselineApprovalId||!/^[a-f0-9]{40}$/.test(b.sourceCommit)||b.serverDir!==runtime.serverDir||b.deploymentDir!==runtime.deploymentDir||!["ordinary","technical","generation","technical-generation"].includes(b.profile))throw Error("Invalid current ordinary source binding");
 verifyCurrentFiles(b.files);const flags=profileFlags(b.profile);assertCodexReceiptSourceClosure(runtime.deploymentDir,b.receiptSources,process.getuid?.(),flags.technical,flags.generation);
 return Object.freeze({...b,files:Object.freeze({...b.files}),receiptSources:Object.freeze({...b.receiptSources})});
}
export interface CodexOrdinaryEntry {readonly approvalId:string;readonly nativeReceiptPolicy:CodexReceiptPolicy;assertCurrent(launch:CodexNativeLaunchReceipt):void;hooks:Pick<CodexHostQualification,"ordinaryMemoryAdmission"|"onNativeThread"|"nativeMetadataAuthority"|"onNativeSettlementReceipt">}
/** HMAC approval is root's concrete qualification decision over ORIGINAL evidence, not a native PASS from this loader. */
export function loadCodexOrdinaryEntry(path:string|undefined,keyPath:string|undefined,runtime?:{serverDir:string;deploymentDir:string}):CodexOrdinaryEntry|undefined{
 if(!path&&!keyPath)return undefined;if(!path||!keyPath)throw Error("Ordinary entry requires protected approval and key");
 const raw=privateBytes(path,262144),key=privateBytes(keyPath,32);if(key.length!==32)throw Error("Invalid ordinary entry key");const v=JSON.parse(new TextDecoder("utf-8",{fatal:true}).decode(raw));
 if(Object.keys(v).sort().join()!=="body,seal"||typeof v.seal!=="string"||!/^[a-f0-9]{64}$/.test(v.seal)||!timingSafeEqual(Buffer.from(v.seal,"hex"),createHmac("sha256",key).update(canonicalJson(v.body)).digest()))throw Error("Untrusted ordinary entry approval");
 const b=v.body as CodexOrdinaryEntryBody,q=b.qualification;
 if(b.schema!=="codex-ordinary-entry-v1"||typeof b.approvalId!=="string"||! /^[A-Za-z0-9._:-]{1,128}$/.test(b.approvalId)||! /^[a-f0-9]{40}$/.test(b.sourceCommit)||q?.binaryVersion!=="0.158.0"||q.upstream!=="064c6b8c737f5b41d171fdda80bd9ef10ad06eb3"||! /^[a-f0-9]{64}$/.test(q.binarySha256)||Object.keys(b.receiptSources).sort().join()!==[...CODEX_RECEIPT_SOURCES].sort().join())throw Error("Invalid ordinary pinned qualification closure");
 verifyFiles(b.files);if(!runtime)throw Error("Actual ordinary executing release paths required");
 const sourcePath=path+".sources.json";let sourceExists=false;try{lstatSync(sourcePath);sourceExists=true;}catch(error){if((error as NodeJS.ErrnoException).code!=="ENOENT")throw error;}
 const sourceApproval=sourceExists?loadCodexOrdinaryCurrentSources(sourcePath,key,raw,b.approvalId,runtime):undefined;
 const currentFiles=sourceApproval?.files??b.files,currentSources=sourceApproval?.receiptSources??b.receiptSources,flags=sourceApproval?profileFlags(sourceApproval.profile):{technical:false,generation:false};
 const required=new Set<string>(),walk=(file:string)=>{if(required.has(file))return;if(realpathSync(file)!==file)throw Error("Moving ordinary executable alias");required.add(file);const raw=readFileSync(file,"utf8");for(const match of raw.matchAll(/(?:from\s*|import\s*\()?["'](\.\.?\/[^"']+\.js)["']/g)){const dependency=resolve(dirname(file),match[1]);if(!dependency.startsWith(runtime.serverDir+sep))throw Error("Ordinary executable dependency escapes release");walk(dependency);}};
 walk(join(runtime.serverDir,"dist/main.js"));walk(join(runtime.serverDir,"dist/codex-preview-main.js"));for(const file of [...required])required.add(file.replace(sep+"dist"+sep,sep+"src"+sep).replace(/\.js$/,".ts"));required.add(join(runtime.serverDir,"package-lock.json"));for(const name of codexReceiptSourceProfile(flags.technical,flags.generation))required.add(join(runtime.deploymentDir,name));if(sourceApproval)required.add(join(runtime.deploymentDir,"engine/validate-image-overlays.py"));for(const file of required)if(!Object.hasOwn(currentFiles,file)||sha(readFileSync(file))!==currentFiles[file])throw Error("Ordinary entry omits actual executing source/build/helper graph");
 for(const name of CODEX_RECEIPT_SOURCES)if(q.binding.sources[name]!==b.receiptSources[name])throw Error("Original ordinary helper/config closure mismatch");
 if(sourceApproval && Object.keys(currentFiles).sort().join()!==[...required].sort().join())throw Error("Unexpected current ordinary source graph");
 if(!sourceApproval)for(const name of CODEX_RECEIPT_SOURCES)if(sha(readFileSync(join(runtime.deploymentDir,name)))!==b.receiptSources[name])throw Error("Ordinary helper/config closure mismatch");
 const lr=privateBytes(q.launchPath,32768),sr=privateBytes(q.settlementPath,32768),ack=privateBytes(q.protocolAckPath,65536);if(sha(lr)!==q.launchSha256||sha(sr)!==q.settlementSha256||sha(ack)!==q.protocolAckSha256)throw Error("Original qualification evidence changed");
 const launch=validateCodexLaunchReceipt(JSON.parse(lr.toString("utf8")),q.binding,q.observedProducer,q.validatedAtMs),settlementRaw=JSON.parse(sr.toString("utf8"));const settlement=validateCodexSettlementReceipt(settlementRaw,q.binding,launch,settlementRaw.checkedAtMs);
 const a=JSON.parse(ack.toString("utf8"));if(!settlement.cleanupOk||a.schema!=="codex-zero-generation-acks-v1"||a.launchNonce!==launch.nonce||a.initialize?.codexHome!==q.binding.profileDir+"/codex-home"||a.initialize?.platformOs!=="linux"||typeof a.initialize?.userAgent!=="string"||!a.initialize.userAgent.includes("0.158.0")||typeof a.threadStart?.thread?.id!=="string"||a.threadStart?.model!=="qwen3.8-27b"||a.threadStart?.modelProvider!=="sova"||a.threadStart?.cwd!==q.binding.workspace)throw Error("Qualification lacks reviewed actual no-generation protocol evidence");
 if(a.providerRequests!==0){
  if(!q.legacyTransportPath||!q.legacyTransportSha256||!q.rawProtocolPath||!q.rawProtocolSha256)throw Error("Complete original legacy transport evidence required for unknown count");
  const legacy=privateBytes(q.legacyTransportPath,8*1024*1024),protocol=privateBytes(q.rawProtocolPath,2*1024*1024);
  if(sha(legacy)!==q.legacyTransportSha256||sha(protocol)!==q.rawProtocolSha256)throw Error("Original legacy transport evidence changed");
  assertOrdinaryNoGenerationObservation(a,JSON.parse(new TextDecoder("utf-8",{fatal:true}).decode(legacy)),{launchSha256:q.launchSha256,settlementSha256:q.settlementSha256,rawProtocolSha256:q.rawProtocolSha256});
 }
 if(sha(privateBytes(q.binaryPath,512*1024*1024))!==q.binarySha256)throw Error("Retained actual native binary bytes changed");
 const protectedPaths=[path,keyPath,...(sourceApproval?[sourcePath]:[]),q.launchPath,q.settlementPath,q.protocolAckPath,q.binaryPath,...(q.legacyTransportPath?[q.legacyTransportPath]:[]),...(q.rawProtocolPath?[q.rawProtocolPath]:[])];let current=new Map<string,{threadId:string;launch:CodexNativeLaunchReceipt;abort:AbortController;authority:CodexMetadataAuthority}>();
 const assertCurrent=(receipt:CodexNativeLaunchReceipt)=>{
  verifyFiles(b.files);if(sourceApproval)verifyCurrentFiles(currentFiles);
  const actual=codexReceiptValidation(receipt)?.binding;
  if(!codexReceiptProvenance(receipt)||isHistoricalCodexReceipt(receipt)||!actual||receipt.container.imageId!==launch.container.imageId||actual.deploymentDir!==runtime.deploymentDir||actual.uid!==q.binding.uid||actual.gid!==q.binding.gid||sourceApproval&&actual.imageJobsQualified!==false||actual.technicalVisionQualified===true&&!flags.technical||actual.imageGenerationQualified===true&&!flags.generation)throw Error("Current ordinary launch is not genuinely qualified");
  const expected=Object.fromEntries(codexReceiptSourceProfile(actual.technicalVisionQualified===true,actual.imageGenerationQualified===true).map(name=>[name,currentSources[name]]));
  if(canonicalJson(receipt.sources)!==canonicalJson(expected)||canonicalJson(actual.sources)!==canonicalJson(expected))throw Error("Current ordinary mounted source profile mismatch");
  if(sourceApproval){const again=loadCodexOrdinaryCurrentSources(sourcePath,key,raw,b.approvalId,runtime);if(canonicalJson(again)!==canonicalJson(sourceApproval))throw Error("Current ordinary source approval changed");}
  assertOrdinaryProtectedPaths(receipt,protectedPaths);
 };
 const hooks:CodexOrdinaryEntry["hooks"]={
  onNativeThread:async input=>{assertCurrent(input.launchReceipt);if(input.launchReceipt.sessionId!==input.sessionId||input.observedSettings.model!=="qwen3.8-27b"||input.observedSettings.modelProvider!=="sova"||input.observedSettings.cwd!==input.launchReceipt.container.workspace)throw Error("Ordinary native thread ACK mismatch");current.get(input.sessionId)?.abort.abort();const abort=new AbortController();current.set(input.sessionId,{threadId:input.threadId,launch:input.launchReceipt,abort,authority:createCodexMetadataAuthority({sessionId:input.sessionId,threadId:input.threadId,launchReceipt:input.launchReceipt,signal:abort.signal})});},
  ordinaryMemoryAdmission:async(input,signal)=>{assertCurrent(input.launchReceipt);const c=current.get(input.sessionId);if(signal.aborted||!c||c.abort.signal.aborted||c.threadId!==input.threadId||c.launch!==input.launchReceipt)throw Error("Ordinary retrieval is not owned by current native ACK");},
  // This binds lifetime/thread and records native-reported metadata. Same-token operational tools can still forge headers; semantic/authorship acceptance remains NOT_TESTED.
  nativeMetadataAuthority:input=>current.get(input.sessionId)?.authority,
  onNativeSettlementReceipt:receipt=>{const c=current.get(receipt.sessionId);if(c&&c.launch.nonce===receipt.nonce){c.abort.abort();current.delete(receipt.sessionId);}}
 };
 return Object.freeze({approvalId:b.approvalId,nativeReceiptPolicy:Object.freeze({linuxTransportQualified:true as const,sourceSha256:Object.freeze({...currentSources})}),assertCurrent,hooks});
}
