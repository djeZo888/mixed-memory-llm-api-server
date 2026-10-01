/** Root-reviewed host entry. Browser/model JSON and configuration booleans cannot activate it. */
import {constants,openSync,closeSync,fstatSync,lstatSync,realpathSync,readFileSync} from "node:fs";
import {dirname,isAbsolute,sep,join,resolve} from "node:path";
import {createHash,createHmac,timingSafeEqual} from "node:crypto";
import {canonicalJson} from "./codex-canonical.js";
import {CODEX_RECEIPT_SOURCES,validateCodexLaunchReceipt,validateCodexSettlementReceipt,codexReceiptProvenance,isHistoricalCodexReceipt,type CodexReceiptBinding,type CodexReceiptIdentity,type CodexNativeLaunchReceipt,type CodexReceiptPolicy} from "./codex-receipts.js";
import {createCodexMetadataAuthority,type CodexMetadataAuthority} from "./codex-turn-metadata.js";
import type {CodexHostQualification} from "./codex-host.js";
export interface CodexOrdinaryEntryBody {
 schema:"codex-ordinary-entry-v1";approvalId:string;sourceCommit:string;
 files:Readonly<Record<string,string>>;receiptSources:Readonly<Record<string,string>>;
 qualification:{launchPath:string;settlementPath:string;launchSha256:string;settlementSha256:string;binding:CodexReceiptBinding;observedProducer:CodexReceiptIdentity;validatedAtMs:number;protocolAckPath:string;protocolAckSha256:string;binaryPath:string;binarySha256:string;binaryVersion:"0.158.0";upstream:"064c6b8c737f5b41d171fdda80bd9ef10ad06eb3"};
}
const sha=(b:Uint8Array|string)=>createHash("sha256").update(b).digest("hex");
function privateBytes(path:string,max:number){
 if(!isAbsolute(path)||realpathSync(path)!==path)throw Error("Ordinary entry path is not canonical");const parent=lstatSync(dirname(path));if(!parent.isDirectory()||parent.uid!==process.getuid?.()||(parent.mode&0o077)!==0)throw Error("Ordinary entry parent is not private");
 const fd=openSync(path,constants.O_RDONLY|constants.O_NOFOLLOW);try{const st=fstatSync(fd);if(!st.isFile()||st.uid!==process.getuid?.()||st.nlink!==1||(st.mode&0o777)!==0o600||st.size<1||st.size>max)throw Error("Unsafe ordinary entry file");const bytes=readFileSync(fd);if(bytes.length!==st.size)throw Error("Changing ordinary entry file");return bytes;}finally{closeSync(fd);}
}
function verifyFiles(files:Readonly<Record<string,string>>){if(!files||typeof files!=="object"||Array.isArray(files)||Object.keys(files).length<8||Object.keys(files).length>512)throw Error("Incomplete ordinary source/build closure");for(const [path,digest]of Object.entries(files)){if(!isAbsolute(path)||realpathSync(path)!==path||!/^[a-f0-9]{64}$/.test(digest)||!lstatSync(path).isFile()||sha(readFileSync(path))!==digest)throw Error("Ordinary source/build closure changed");}}
export function assertOrdinaryProtectedPaths(launch:CodexNativeLaunchReceipt,paths:readonly string[]){for(const p of paths)for(const m of [...launch.container.mounts,...launch.container.additionalMounts])if(m.type==="bind"&&isAbsolute(m.source)&&(p===m.source||p.startsWith(m.source+sep)))throw Error("Ordinary approval/evidence is model-mounted");}
export interface CodexOrdinaryEntry {readonly approvalId:string;readonly nativeReceiptPolicy:CodexReceiptPolicy;assertCurrent(launch:CodexNativeLaunchReceipt):void;hooks:Pick<CodexHostQualification,"ordinaryMemoryAdmission"|"onNativeThread"|"nativeMetadataAuthority"|"onNativeSettlementReceipt">}
/** HMAC approval is root's concrete qualification decision over ORIGINAL evidence, not a native PASS from this loader. */
export function loadCodexOrdinaryEntry(path:string|undefined,keyPath:string|undefined,runtime?:{serverDir:string;deploymentDir:string}):CodexOrdinaryEntry|undefined{
 if(!path&&!keyPath)return undefined;if(!path||!keyPath)throw Error("Ordinary entry requires protected approval and key");
 const raw=privateBytes(path,262144),key=privateBytes(keyPath,32);if(key.length!==32)throw Error("Invalid ordinary entry key");const v=JSON.parse(new TextDecoder("utf-8",{fatal:true}).decode(raw));
 if(Object.keys(v).sort().join()!=="body,seal"||typeof v.seal!=="string"||!/^[a-f0-9]{64}$/.test(v.seal)||!timingSafeEqual(Buffer.from(v.seal,"hex"),createHmac("sha256",key).update(canonicalJson(v.body)).digest()))throw Error("Untrusted ordinary entry approval");
 const b=v.body as CodexOrdinaryEntryBody,q=b.qualification;
 if(b.schema!=="codex-ordinary-entry-v1"||typeof b.approvalId!=="string"||! /^[A-Za-z0-9._:-]{1,128}$/.test(b.approvalId)||! /^[a-f0-9]{40}$/.test(b.sourceCommit)||q?.binaryVersion!=="0.158.0"||q.upstream!=="064c6b8c737f5b41d171fdda80bd9ef10ad06eb3"||! /^[a-f0-9]{64}$/.test(q.binarySha256)||Object.keys(b.receiptSources).sort().join()!==[...CODEX_RECEIPT_SOURCES].sort().join())throw Error("Invalid ordinary pinned qualification closure");
 verifyFiles(b.files);if(!runtime)throw Error("Actual ordinary executing release paths required");
 const required=new Set<string>(),walk=(file:string)=>{if(required.has(file))return;if(realpathSync(file)!==file)throw Error("Moving ordinary executable alias");required.add(file);const raw=readFileSync(file,"utf8");for(const match of raw.matchAll(/(?:from\s*|import\s*\()?["'](\.\.?\/[^"']+\.js)["']/g)){const dependency=resolve(dirname(file),match[1]);if(!dependency.startsWith(runtime.serverDir+sep))throw Error("Ordinary executable dependency escapes release");walk(dependency);}};
 walk(join(runtime.serverDir,"dist/main.js"));walk(join(runtime.serverDir,"dist/codex-preview-main.js"));for(const file of [...required])required.add(file.replace(sep+"dist"+sep,sep+"src"+sep).replace(/\.js$/,".ts"));required.add(join(runtime.serverDir,"package-lock.json"));for(const name of CODEX_RECEIPT_SOURCES)required.add(join(runtime.deploymentDir,name));for(const file of required)if(!Object.hasOwn(b.files,file)||sha(readFileSync(file))!==b.files[file])throw Error("Ordinary entry omits actual executing source/build/helper graph");
 for(const name of CODEX_RECEIPT_SOURCES)if(q.binding.sources[name]!==b.receiptSources[name])throw Error("Ordinary helper/config closure mismatch");
 const lr=privateBytes(q.launchPath,32768),sr=privateBytes(q.settlementPath,32768),ack=privateBytes(q.protocolAckPath,65536);if(sha(lr)!==q.launchSha256||sha(sr)!==q.settlementSha256||sha(ack)!==q.protocolAckSha256)throw Error("Original qualification evidence changed");
 const launch=validateCodexLaunchReceipt(JSON.parse(lr.toString("utf8")),q.binding,q.observedProducer,q.validatedAtMs),settlementRaw=JSON.parse(sr.toString("utf8"));const settlement=validateCodexSettlementReceipt(settlementRaw,q.binding,launch,settlementRaw.checkedAtMs);
 const a=JSON.parse(ack.toString("utf8"));if(!settlement.cleanupOk||a.schema!=="codex-zero-generation-acks-v1"||a.launchNonce!==launch.nonce||a.initialize?.codexHome!==q.binding.profileDir+"/codex-home"||a.initialize?.platformOs!=="linux"||typeof a.initialize?.userAgent!=="string"||!a.initialize.userAgent.includes("0.158.0")||typeof a.threadStart?.thread?.id!=="string"||a.threadStart?.model!=="qwen3.8-27b"||a.threadStart?.modelProvider!=="sova"||a.threadStart?.cwd!==q.binding.workspace||a.providerRequests!==0)throw Error("Qualification lacks reviewed actual no-generation protocol evidence");
 if(sha(privateBytes(q.binaryPath,512*1024*1024))!==q.binarySha256)throw Error("Retained actual native binary bytes changed");
 const protectedPaths=[path,keyPath,q.launchPath,q.settlementPath,q.protocolAckPath,q.binaryPath];let current=new Map<string,{threadId:string;launch:CodexNativeLaunchReceipt;abort:AbortController;authority:CodexMetadataAuthority}>();
 const assertCurrent=(receipt:CodexNativeLaunchReceipt)=>{verifyFiles(b.files);if(!codexReceiptProvenance(receipt)||isHistoricalCodexReceipt(receipt)||receipt.container.imageId!==launch.container.imageId||canonicalJson(receipt.sources)!==canonicalJson(b.receiptSources))throw Error("Current ordinary launch is not genuinely qualified");assertOrdinaryProtectedPaths(receipt,protectedPaths);};
 const hooks:CodexOrdinaryEntry["hooks"]={
  onNativeThread:async input=>{assertCurrent(input.launchReceipt);if(input.observedSettings.model!=="qwen3.8-27b"||input.observedSettings.modelProvider!=="sova"||input.observedSettings.cwd!==input.launchReceipt.container.workspace)throw Error("Ordinary native thread ACK mismatch");current.get(input.sessionId)?.abort.abort();const abort=new AbortController();current.set(input.sessionId,{threadId:input.threadId,launch:input.launchReceipt,abort,authority:createCodexMetadataAuthority({sessionId:input.sessionId,threadId:input.threadId,launchReceipt:input.launchReceipt,signal:abort.signal})});},
  ordinaryMemoryAdmission:async(input,signal)=>{assertCurrent(input.launchReceipt);const c=current.get(input.sessionId);if(signal.aborted||!c||c.abort.signal.aborted||c.threadId!==input.threadId||c.launch!==input.launchReceipt)throw Error("Ordinary retrieval is not owned by current native ACK");},
  // This binds lifetime/thread and records native-reported metadata. Same-token operational tools can still forge headers; semantic/authorship acceptance remains NOT_TESTED.
  nativeMetadataAuthority:input=>current.get(input.sessionId)?.authority,
  onNativeSettlementReceipt:receipt=>{const c=current.get(receipt.sessionId);if(c&&c.launch.nonce===receipt.nonce){c.abort.abort();current.delete(receipt.sessionId);}}
 };
 return Object.freeze({approvalId:b.approvalId,nativeReceiptPolicy:Object.freeze({linuxTransportQualified:true as const,sourceSha256:Object.freeze({...b.receiptSources})}),assertCurrent,hooks});
}
