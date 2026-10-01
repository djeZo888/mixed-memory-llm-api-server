/** Private host receipt channel. Neither native stdio nor caller JSON is an attestation. */
import { constants, openSync, closeSync, fstatSync, readFileSync, lstatSync, mkdirSync, mkdtempSync, writeFileSync, realpathSync } from "node:fs";
import { createHash, randomBytes } from "node:crypto";
import { join, dirname, resolve, sep } from "node:path";
import { assertAuthenticatedCodexHandoff, type AuthenticatedCodexHandoff } from "./codex-policy-handoff.js";
export const CODEX_RECEIPT_SOURCES = ["run-codex.sh", "engine/task-egress.py", "engine/redact-acp.py", "engine/codex_receipts.py", "engine/codex_native_trace.py", "security/chromium-seccomp.json", "codex/config.toml", "codex/models.json"] as const;
export const CODEX_TECHNICAL_RECEIPT_SOURCES = [...CODEX_RECEIPT_SOURCES, "../tools/technical-vision/technical-vision-mcp.mjs", "../tools/technical-vision/technical-vision.mjs"] as const;
const sourceProfile = (technical = false) => technical ? CODEX_TECHNICAL_RECEIPT_SOURCES : CODEX_RECEIPT_SOURCES;
export interface CodexReceiptPolicy {
  /** Root-reviewed actual Linux systemd-scope/file-channel acceptance, absent by default. */
  readonly linuxTransportQualified: true;
  readonly sourceSha256: Readonly<Record<string, string>>;
}
export interface CodexReceiptIdentity { pid: number; startTicks: string; uid: number; bootId: string; cgroupPath: string }
export interface CodexNativeLaunchReceipt {
  schema: "codex-launch-v1"; nonce: string; runId: string; sessionId: string; checkedAtMs: number;
  producer: CodexReceiptIdentity; sources: Record<string, string>;
  egress: { bootId: string; uid: number; cgroupPath: string; cgroupInode: number; nftSha256: string; checkedBoottime: number; receiptSha256: string };
  /** Physical inspection only; never a model-facing empty-roots/tool-denial proof. */
  container: { id: string; name: string; imageId: string; imageRevision: string; imagePatchset: string; pid: number; pidStartTicks: string; rootless: true; user: string; network: string; capDrop: string[]; securityOpt: string[]; readOnly: true; privileged: false; mounts: { source: string; destination: string; rw: boolean; type: string }[]; additionalMounts: { source: string; destination: string; rw: boolean; type: string }[]; workdir: string; profileDir: string; workspace: string };
}
export interface CodexNativeSettlementReceipt {
  schema: "codex-settlement-v1"; nonce: string; runId: string; sessionId: string; checkedAtMs: number;
  producer: CodexReceiptIdentity; containerName: string; containerId: string | null;
  engineExitStatus: number | null; requestedStop: boolean; cliReaped: boolean;
  rmExit: number | null; existsExit: number | null; pipesJoined: boolean; cleanupOk: boolean;
}
const transportReadObjects = new WeakSet<object>();
const rawReceiptBytes = new WeakMap<object, string>();
const receiptProvenance = new WeakMap<object, Readonly<{ rawPath: string; rawSha256: string }>>();
/** Exact protected OOB bytes. Synthetic validator objects never have transport provenance. */
export function getCodexReceiptUtf8(receipt: CodexNativeLaunchReceipt | CodexNativeSettlementReceipt): string | undefined { return transportReadObjects.has(receipt) && (isVerifiedCodexLaunchReceipt(receipt) || isVerifiedCodexSettlementReceipt(receipt)) ? rawReceiptBytes.get(receipt) : undefined; }
export function codexReceiptProvenance(receipt: CodexNativeLaunchReceipt | CodexNativeSettlementReceipt) { return transportReadObjects.has(receipt) && (isVerifiedCodexLaunchReceipt(receipt) || isVerifiedCodexSettlementReceipt(receipt)) ? receiptProvenance.get(receipt) : undefined; }
/** Raw failure provenance is PRIVATE diagnostic data; it is never a verified
 * launch/settlement receipt. Existing qualification getters remain strict. */
export function getCodexLaunchFailureDiagnostic(value:unknown){
 if(!object(value)||!transportReadObjects.has(value)||value.schema!=="codex-launch-failure-v1")return undefined;
 return Object.freeze({value,rawUtf8:rawReceiptBytes.get(value),provenance:receiptProvenance.get(value),nativeQualified:false as const});
}
const verifiedLaunch = new WeakSet<object>(), verifiedSettlement = new WeakSet<object>();
const validationRecords = new WeakMap<object, Readonly<{binding:CodexReceiptBinding;observedProducer:CodexReceiptIdentity;validatedAtMs:number}>>();
const historicalReceipts = new WeakSet<object>();
export function codexReceiptValidation(receipt: CodexNativeLaunchReceipt) { return validationRecords.get(receipt); }
export function isHistoricalCodexReceipt(receipt: object) { return historicalReceipts.has(receipt); }
export const isVerifiedCodexLaunchReceipt = (v: unknown): v is CodexNativeLaunchReceipt => !!v && typeof v === "object" && verifiedLaunch.has(v);
export const isVerifiedCodexSettlementReceipt = (v: unknown): v is CodexNativeSettlementReceipt => !!v && typeof v === "object" && verifiedSettlement.has(v);
const hex = (v: unknown, n = 64) => typeof v === "string" && new RegExp(`^[0-9a-f]{${n}}$`).test(v);
const object = (v: unknown): v is Record<string, any> => !!v && typeof v === "object" && !Array.isArray(v);
const exact = (v: unknown, keys: string[]) => object(v) && Object.keys(v).sort().join() === keys.sort().join();
const digest = (v: Uint8Array) => createHash("sha256").update(v).digest("hex");
export type CodexNativeTraceMode="off"|"post-sampling-token-usage-v1"|"post-sampling-token-usage-v2";
export type CodexNativeTraceSchema=null|"codex-native-trace-v1"|"codex-native-trace-v2";
export const CODEX_NATIVE_TRACE_MODES=Object.freeze(["off","post-sampling-token-usage-v1","post-sampling-token-usage-v2"] as const);
export function codexTraceSchemaForMode(mode:CodexNativeTraceMode|undefined):CodexNativeTraceSchema {
 if(mode===undefined||mode==="off")return null;
 if(mode==="post-sampling-token-usage-v1")return "codex-native-trace-v1";
 if(mode==="post-sampling-token-usage-v2")return "codex-native-trace-v2";
 throw Error("Fixed trusted native trace mode required");
}
export function codexTraceEnvironment(mode:Exclude<CodexNativeTraceMode,"off">) {
 const schema=codexTraceSchemaForMode(mode);if(schema===null)throw Error("Off trace has no native environment");
 return {RUST_LOG:schema==="codex-native-trace-v2"?"off,codex_core::session::turn=trace,codex_core::tasks=info":"off,codex_core::session::turn=trace",LOG_FORMAT:"json"};
}
export interface CodexReceiptBinding { nonce: string; runId: string; sessionId: string; startedAtMs: number; uid: number; profileDir: string; workspace: string; deploymentDir: string; imageJobsQualified: boolean; technicalVisionQualified?: true; gid: number; sources: Record<string, string>; nativeTraceMode?: CodexNativeTraceMode }
function identity(v: unknown): v is CodexReceiptIdentity {
  return object(v) && exact(v, ["pid", "startTicks", "uid", "bootId", "cgroupPath"]) && Number.isSafeInteger(v.pid) && v.pid > 0 && Number.isSafeInteger(v.uid) && v.uid > 0 && typeof v.startTicks === "string" && /^\d+$/.test(v.startTicks) && typeof v.bootId === "string" && /^[0-9a-f-]{36}$/.test(v.bootId) && typeof v.cgroupPath === "string" && v.cgroupPath.length < 1024;
}
function common(v: Record<string, any>, binding: CodexReceiptBinding, now: number) {
  return v.nonce === binding.nonce && hex(v.nonce) && v.runId === binding.runId && v.sessionId === binding.sessionId && Number.isSafeInteger(v.checkedAtMs) && v.checkedAtMs >= binding.startedAtMs && v.checkedAtMs <= now + 1000 && identity(v.producer) && v.producer.uid === binding.uid;
}
export function validateCodexLaunchReceipt(value: unknown, binding: CodexReceiptBinding, observedProducer: CodexReceiptIdentity, now = Date.now()): CodexNativeLaunchReceipt {
  if ((binding.technicalVisionQualified !== undefined && binding.technicalVisionQualified !== true) || Object.keys(binding.sources).sort().join() !== [...sourceProfile(binding.technicalVisionQualified === true)].sort().join()) throw Error("Unbound exact native source profile");
  if (!object(value) || !exact(value, ["schema", "nonce", "runId", "sessionId", "checkedAtMs", "producer", "sources", "egress", "container"]) || value.schema !== "codex-launch-v1" || !common(value, binding, now) || now - value.checkedAtMs > 15000 || JSON.stringify(value.producer) !== JSON.stringify(observedProducer) || !object(value.sources) || Object.keys(value.sources).sort().join() !== Object.keys(binding.sources).sort().join() || Object.entries(binding.sources).some(([k,v]) => value.sources[k] !== v)) throw Error("Untrusted native launch receipt");
  const e = value.egress, c = value.container;
  const prefix = `user.slice/user-${binding.uid}.slice/user@${binding.uid}.service/aiharnesstasks.slice`;
  if (!exact(e, ["bootId", "uid", "cgroupPath", "cgroupInode", "nftSha256", "checkedBoottime", "receiptSha256"]) || e.bootId !== value.producer.bootId || e.uid !== binding.uid || e.cgroupPath !== prefix || !Number.isSafeInteger(e.cgroupInode) || e.cgroupInode < 1 || !hex(e.nftSha256) || !hex(e.receiptSha256) || !Number.isFinite(e.checkedBoottime) || !value.producer.cgroupPath.startsWith('/'+prefix+'/')) throw Error("Invalid launch egress receipt");
  if (!exact(c, ["id", "name", "imageId", "imageRevision", "imagePatchset", "pid", "pidStartTicks", "rootless", "user", "network", "capDrop", "securityOpt", "readOnly", "privileged", "mounts", "additionalMounts", "workdir", "profileDir", "workspace"]) || !hex(c.id) || typeof c.name !== "string" || !/^ai-harness-[0-9a-f]{32}$/.test(c.name) || c.imageId.replace(/^sha256:/,'') !== 'd8841743002e16de1f9269a850a2f06a73055688befec4c309778ca8a4c11aad' || c.imageRevision !== '064c6b8c737f5b41d171fdda80bd9ef10ad06eb3' || c.imagePatchset !== 'dd0ff12a651db4cc8521cddb8e5094c5a197ca87cef6b7ec797343da67d9f1ec' || !Number.isSafeInteger(c.pid) || c.pid < 1 || !/^\d+$/.test(c.pidStartTicks) || c.rootless !== true || c.user !== `${binding.uid}:${binding.gid}` || c.network !== 'slirp4netns:allow_host_loopback=true' || JSON.stringify(c.capDrop) !== '["ALL"]' || !Array.isArray(c.securityOpt) || !c.securityOpt.includes('no-new-privileges') || !c.securityOpt.some((x: unknown) => typeof x === 'string' && x.startsWith('seccomp=')) || c.readOnly !== true || c.privileged !== false || c.profileDir !== binding.profileDir || c.workspace !== binding.workspace || c.workdir !== binding.workspace || !Array.isArray(c.mounts) || c.mounts.length !== (binding.technicalVisionQualified === true ? 9 : 7) || c.mounts.some((m: unknown) => !object(m) || !exact(m, ['source','destination','rw','type']) || typeof m.source !== 'string' || typeof m.destination !== 'string' || typeof m.rw !== 'boolean' || m.type !== 'bind') || c.mounts.filter((m: any) => m.rw).length !== 2 || !c.mounts.some((m: any) => m.source === binding.profileDir && m.destination === binding.profileDir && m.rw) || !c.mounts.some((m: any) => m.source === binding.workspace && m.destination === binding.workspace && m.rw)) throw Error("Invalid actual native container receipt");
  const ro = (source: string, destination: string) => ({ source, destination, rw: false, type: 'bind' });
  if (!Array.isArray(c.additionalMounts) || c.additionalMounts.length > 3 || c.additionalMounts.some((m: unknown) => !object(m) || !exact(m, ['source','destination','rw','type']) || m.source !== '' || m.type !== 'tmpfs' || m.rw !== true || !['/tmp','/run','/var/tmp'].includes(m.destination)) || new Set(c.additionalMounts.map((m: any) => m.destination)).size !== c.additionalMounts.length) throw Error('Unexpected additional native mount receipt');
  const expectedMounts = [{source:binding.profileDir,destination:binding.profileDir,rw:true,type:'bind'}, {source:binding.workspace,destination:binding.workspace,rw:true,type:'bind'}, ro(join(dirname(binding.deploymentDir),'tools/image/image-mcp.mjs'),'/opt/ai-harness/tools/image/image-mcp.mjs'),ro(join(dirname(binding.deploymentDir),'tools/image/image.mjs'),'/opt/ai-harness/tools/image/image.mjs'),ro(join(binding.deploymentDir,'codex',binding.imageJobsQualified?'config-image-jobs.toml':'config.toml'),join(binding.profileDir,'codex-home/config.toml')),ro(join(binding.deploymentDir,'codex/models.json'),'/opt/sova/codex/models.json'),ro(join(binding.deploymentDir,'codex/skills/sova-local-tools'),join(binding.profileDir,'codex-home/skills/sova-local-tools')), ...(binding.technicalVisionQualified === true ? [ro(join(dirname(binding.deploymentDir),'tools/technical-vision/technical-vision-mcp.mjs'),'/opt/ai-harness/tools/technical-vision/technical-vision-mcp.mjs'),ro(join(dirname(binding.deploymentDir),'tools/technical-vision/technical-vision.mjs'),'/opt/ai-harness/tools/technical-vision/technical-vision.mjs')] : [])];
  const sortMounts = (ms: any[]) => ms.slice().sort((a,b)=>(a.source+':'+a.destination).localeCompare(b.source+':'+b.destination));
  if (JSON.stringify(sortMounts(c.mounts)) !== JSON.stringify(sortMounts(expectedMounts)) || JSON.stringify(c.securityOpt.slice().sort()) !== JSON.stringify(['no-new-privileges','seccomp='+join(binding.deploymentDir,'security/chromium-seccomp.json')].sort())) throw Error('Actual native mount/security policy mismatch');
  freeze(value); verifiedLaunch.add(value); const validation={binding:structuredClone(binding),observedProducer:structuredClone(observedProducer),validatedAtMs:now}; freeze(validation); validationRecords.set(value,validation); return value as CodexNativeLaunchReceipt;
}
export function validateCodexSettlementReceipt(value: unknown, binding: CodexReceiptBinding, launch: CodexNativeLaunchReceipt, now = Date.now()): CodexNativeSettlementReceipt {
  if (!object(value) || !isVerifiedCodexLaunchReceipt(launch) || !exact(value, ["schema","nonce","runId","sessionId","checkedAtMs","producer","containerName","containerId","engineExitStatus","requestedStop","cliReaped","rmExit","existsExit","pipesJoined","cleanupOk"]) || value.schema !== 'codex-settlement-v1' || !common(value,binding,now) || value.checkedAtMs < launch.checkedAtMs || JSON.stringify(value.producer) !== JSON.stringify(launch.producer) || value.containerName !== launch.container.name || value.containerId !== launch.container.id || !(value.engineExitStatus === null || Number.isSafeInteger(value.engineExitStatus)) || ['requestedStop','cliReaped','pipesJoined','cleanupOk'].some(k => typeof value[k] !== 'boolean') || ['rmExit','existsExit'].some(k => !(value[k] === null || Number.isSafeInteger(value[k]))) || value.cleanupOk !== (value.cliReaped && value.rmExit === 0 && value.existsExit === 1 && value.pipesJoined)) throw Error("Untrusted native settlement receipt");
  freeze(value); verifiedSettlement.add(value); return value as CodexNativeSettlementReceipt;
}
function freeze(value: any) { if (value && typeof value === 'object') { for (const child of Object.values(value)) freeze(child); Object.freeze(value); } }
function protectedDirectory(path: string, uid: number) {
  const s = lstatSync(path); if (!s.isDirectory() || s.isSymbolicLink() || s.uid !== uid || (s.mode & 0o777) !== 0o700 || realpathSync(path) !== path) throw Error("Unsafe native receipt directory");
}
export function readCodexReceiptFile(path: string, uid: number): unknown {
  const fd = openSync(path, constants.O_RDONLY | constants.O_NOFOLLOW);
  try { const s = fstatSync(fd); if (!s.isFile() || s.uid !== uid || (s.mode & 0o777) !== 0o600 || s.nlink !== 1 || s.size < 2 || s.size > 32768) throw Error("Unsafe native receipt file"); const b = readFileSync(fd); if (b.length !== s.size) throw Error("Changing native receipt file"); const raw = new TextDecoder("utf-8", { fatal: true }).decode(b); const parsed: unknown = JSON.parse(raw); freeze(parsed); if (object(parsed)) { rawReceiptBytes.set(parsed, raw); receiptProvenance.set(parsed, Object.freeze({ rawPath: path, rawSha256: digest(b) })); } return parsed; } finally { closeSync(fd); }
}
export function observeCodexProducer(pid: number, childPid: number, uid: number): CodexReceiptIdentity {
  const bootId = readFileSync('/proc/sys/kernel/random/boot_id','utf8').trim();
  const stat = (p: number) => { const s = readFileSync(`/proc/${p}/stat`,'utf8'); const f = s.slice(s.lastIndexOf(')')+2).split(' '); return { ppid: Number(f[1]), start: f[19]! }; };
  let ancestor = pid; const seen = new Set<number>();
  for (let i=0;i<32 && ancestor !== childPid;i++) { if (ancestor < 1 || seen.has(ancestor)) throw Error('Unowned receipt producer'); seen.add(ancestor); ancestor=stat(ancestor).ppid; }
  if (ancestor !== childPid) throw Error('Unowned receipt producer');
  const before = stat(pid); const status = readFileSync(`/proc/${pid}/status`,'utf8'); const ids = status.match(/^Uid:\s+(\d+)\s+(\d+)/m); if (!ids || Number(ids[1]) !== uid || Number(ids[2]) !== uid) throw Error('Receipt producer UID mismatch');
  const cg = readFileSync(`/proc/${pid}/cgroup`,'utf8').trim(); if (!cg.startsWith('0::/') || cg.includes('\n') || stat(pid).start !== before.start) throw Error('Receipt producer identity changed');
  return { pid, startTicks: before.start, uid, bootId, cgroupPath: cg.slice(3) };
}
/** Historical only. Caller must first authenticate the host-sealed handoff; never a current PID proof. */
export function revalidateRetainedCodexReceipts(input: {
  launchPath:string;settlementPath:string;launchSha256:string;settlementSha256:string;
  binding:CodexReceiptBinding;observedProducer:CodexReceiptIdentity;originalValidatedAtMs:number;
},cap:AuthenticatedCodexHandoff) {
  assertAuthenticatedCodexHandoff(cap,"receipts",input);
  const launchValue=readCodexReceiptFile(input.launchPath,input.binding.uid), settlementValue=readCodexReceiptFile(input.settlementPath,input.binding.uid);
  if (!object(launchValue) || !object(settlementValue) || receiptProvenance.get(launchValue)?.rawSha256!==input.launchSha256 || receiptProvenance.get(settlementValue)?.rawSha256!==input.settlementSha256 || !Number.isSafeInteger(input.originalValidatedAtMs) || input.originalValidatedAtMs < launchValue.checkedAtMs || input.originalValidatedAtMs > launchValue.checkedAtMs+15000) throw Error("Changed original native receipt or validation chronology");
  const launch=validateCodexLaunchReceipt(launchValue,input.binding,input.observedProducer,input.originalValidatedAtMs);
  const settlement=validateCodexSettlementReceipt(settlementValue,input.binding,launch,settlementValue.checkedAtMs);
  if (!settlement.cleanupOk) throw Error("Historical native parent did not settle");
  transportReadObjects.add(launch);transportReadObjects.add(settlement);historicalReceipts.add(launch);historicalReceipts.add(settlement);
  return {launch,settlement};
}
export function createCodexReceiptChannel(input: { sessionId: string; runId: string; profileDir: string; workspace: string; launcherPath: string; imageJobsQualified?: boolean; technicalVisionQualified?: boolean; nativeTraceMode?: CodexNativeTraceMode }, policy: CodexReceiptPolicy) {
  const traceSchema=codexTraceSchemaForMode(input.nativeTraceMode);
  const uid = process.getuid?.(); if (process.platform !== 'linux' || !uid || policy.linuxTransportQualified !== true) throw Error('Native receipt transport unqualified');
  const deployment = resolve(input.launcherPath,'..'); const sources: Record<string,string> = {};
  if (Object.keys(policy.sourceSha256).sort().join() !== [...sourceProfile(input.technicalVisionQualified === true)].sort().join()) throw Error('Incomplete reviewed receipt source closure');
  Object.assign(sources,assertCodexReceiptSourceClosure(deployment,policy.sourceSha256,uid,input.technicalVisionQualified === true));
  const root=`/run/user/${uid}/ai-harness-codex-receipts`; if (![input.profileDir,input.workspace].every(p => p!==root && !root.startsWith(p+sep) && !p.startsWith(root+sep) && !deployment.startsWith(p+sep) && p!==deployment)) throw Error('Receipt/source channel overlaps model mount');
  try { mkdirSync(root,{mode:0o700}); } catch (e) { if ((e as NodeJS.ErrnoException).code!=='EEXIST') throw e; } protectedDirectory(root,uid);
  const directory=mkdtempSync(join(root,'run-'));protectedDirectory(directory,uid);
  const binding: CodexReceiptBinding={nonce:randomBytes(32).toString('hex'),runId:input.runId,sessionId:input.sessionId,startedAtMs:Date.now(),uid,profileDir:input.profileDir,workspace:input.workspace,deploymentDir:deployment,imageJobsQualified:input.imageJobsQualified===true,...(input.technicalVisionQualified === true ? {technicalVisionQualified:true as const}:{}),gid:process.getgid!(),sources,...(traceSchema?{nativeTraceMode:input.nativeTraceMode}:{})};
  writeFileSync(join(directory,'request.json'),JSON.stringify(binding),{flag:'wx',mode:0o600});
  return { directory, binding, wait: (name:'launch'|'settlement'|'trace'|'failure',timeoutMs:number,ended:()=>boolean)=>waitCodexReceiptFile(directory,uid,name,timeoutMs,ended) };
}
/** A bounded owned wait MUST keep Node alive until it settles. Neither a missing
 * file nor an ended child becomes a native qualification/cleanup attestation. */
export async function waitCodexReceiptFile(directory:string,uid:number,name:'launch'|'settlement'|'trace'|'failure',timeoutMs:number,ended:()=>boolean):Promise<unknown|undefined>{
 if(!Number.isSafeInteger(timeoutMs)||timeoutMs<1||timeoutMs>120000||!['launch','settlement','trace','failure'].includes(name))throw Error('Invalid bounded receipt wait');
 const deadline=performance.now()+timeoutMs;
 while(performance.now()<deadline){
  try{protectedDirectory(directory,uid);const ready=lstatSync(join(directory,name+'.ready'));if(!ready.isFile()||ready.isSymbolicLink()||ready.uid!==uid||(ready.mode&0o777)!==0o600||ready.nlink!==1||ready.size!==0)return undefined;const value=readCodexReceiptFile(join(directory,name+'.json'),uid);if(object(value))transportReadObjects.add(value);return value;}
  catch(error){if((error as NodeJS.ErrnoException).code!=='ENOENT')return undefined;}
  if(ended())return undefined;
  await new Promise<void>(resolve=>setTimeout(resolve,Math.min(25,Math.max(1,deadline-performance.now()))));
 }
 return undefined;
}

/** Shares one cleanup and receipt promise. No settlement age limit while the owner is active. */
export function createCodexReceiptLifecycle(input: {
  launchReceipt: Promise<CodexNativeLaunchReceipt | undefined>;
  exited: Promise<void>; hasExited(): boolean; terminate(): void;
  lookup(launch: CodexNativeLaunchReceipt): Promise<CodexNativeSettlementReceipt | undefined>;
  cleanupBudgetMs?: number;
}) {
  let expire!: () => void;
  const expiry = new Promise<undefined>(r => { expire = () => r(undefined); });
  const observed = (async () => {
    const launch = await input.launchReceipt.catch(() => undefined);
    // A missing launch proof is not a no-process attestation. Retain the
    // bounded Stop/exit wait for the existing supervisor to reap and clean up.
    await input.exited;
    if (!isVerifiedCodexLaunchReceipt(launch)) return undefined;
    const receipt = await input.lookup(launch);
    return isVerifiedCodexSettlementReceipt(receipt) && receipt.nonce === launch.nonce && receipt.containerId === launch.container.id ? receipt : undefined;
  })().catch(() => undefined);
  const settlementReceipt = Promise.race([observed, expiry]);
  let cleanup: Promise<boolean> | undefined;
  return { settlementReceipt, confirm() {
    return cleanup ??= (async () => {
      const timer = setTimeout(expire, input.cleanupBudgetMs ?? 45000);
      try { if (!input.hasExited()) input.terminate(); const receipt = await settlementReceipt; return receipt?.cleanupOk === true; }
      catch { expire(); return false; }
      finally { clearTimeout(timer); }
    })();
  } };
}

/** Separate capture receipt; genuine launch/settlement are mandatory and never
 * inferred from this JSON. Original selected stderr lives only in host channel. */
export interface CodexNativeTraceEvent {
 file:string;sha256:string;bytes:number;stderrSequence:number;stderrOffset:number;chain:string;turnId:string;nativeTimestamp:unknown;observedAtMs:number;observedMonotonicNs:number;
}
export interface CodexNativeTraceV2Event extends CodexNativeTraceEvent {kind:"postSampling"|"autoCompactNew";threadId:string;}
interface CodexNativeTraceReceiptBase {
 nonce:string;sessionId:string;runId:string;producer:CodexReceiptIdentity;containerId:string;environment:{RUST_LOG:string;LOG_FORMAT:string};sources:Record<string,string>;
 stderrBytes:number;stderrSHA256:string;stderrChain:string;complete:true;cleanupOk:boolean;engineExitStatus:number|null;requestedStop:boolean;
}
export type CodexNativeTraceReceipt=CodexNativeTraceReceiptBase & (
 {schema:"codex-native-trace-v1";mode:"post-sampling-token-usage-v1";events:ReadonlyArray<CodexNativeTraceEvent>} |
 {schema:"codex-native-trace-v2";mode:"post-sampling-token-usage-v2";events:ReadonlyArray<CodexNativeTraceV2Event>;autoCalls:ReadonlyArray<CodexNativeTraceV2Event>}
);
export interface CodexOriginalTraceLine {lineUtf8:string;stderrSequence:number;lineSha256:string;}
interface CapturedTraceEvent {bytes:Buffer;parsed:Readonly<Record<string,unknown>>;stderrSequence:number;lineSha256:string;kind:"postSampling"|"autoCompactNew";}
const verifiedTrace=new WeakSet<object>();
const traceLines=new WeakMap<object,ReadonlyArray<Readonly<CapturedTraceEvent>>>();
/** Validate literal task ancestry without selecting away foreign numeric events. */
function traceTaskIdentity(parsed:Record<string,any>) {
 if(parsed.spans!==undefined&&!Array.isArray(parsed.spans))throw Error("Invalid original task ancestry");
 const tasks=[...(parsed.spans??[]),...(parsed.span?[parsed.span]:[])].filter(s=>object(s)&&s.name==="turn");
 if(!tasks.length||tasks.some(s=>typeof s["thread.id"]!=="string"||!s["thread.id"]||typeof s["turn.id"]!=="string"||!s["turn.id"]||s["thread.id"]!==tasks[0]["thread.id"]||s["turn.id"]!==tasks[0]["turn.id"]))throw Error("Invalid original task ancestry");
 return {threadId:tasks[0]["thread.id"],turnId:tasks[0]["turn.id"]};
}
export function validateCodexTraceReceipt(value:unknown,binding:CodexReceiptBinding,launch:CodexNativeLaunchReceipt,settlement:CodexNativeSettlementReceipt):CodexNativeTraceReceipt {
 const schema=codexTraceSchemaForMode(binding.nativeTraceMode),v2=schema==="codex-native-trace-v2";
 const keys=["schema","nonce","sessionId","runId","mode","producer","containerId","environment","sources","events","stderrBytes","stderrSHA256","stderrChain","complete","cleanupOk","engineExitStatus","requestedStop",...(v2?["autoCalls"]:[])];
 if(!object(value)||!transportReadObjects.has(value)||!isVerifiedCodexLaunchReceipt(launch)||!isVerifiedCodexSettlementReceipt(settlement)||isHistoricalCodexReceipt(launch)||isHistoricalCodexReceipt(settlement)||!codexReceiptProvenance(launch)||!codexReceiptProvenance(settlement)||schema===null||!exact(value,keys)||value.schema!==schema||value.mode!==binding.nativeTraceMode||value.nonce!==binding.nonce||value.nonce!==launch.nonce||value.sessionId!==binding.sessionId||value.sessionId!==launch.sessionId||value.runId!==binding.runId||value.runId!==launch.runId||settlement.nonce!==launch.nonce||settlement.sessionId!==launch.sessionId||settlement.runId!==launch.runId||settlement.containerId!==launch.container.id||settlement.containerName!==launch.container.name||JSON.stringify(settlement.producer)!==JSON.stringify(launch.producer)||JSON.stringify(value.producer)!==JSON.stringify(launch.producer)||value.containerId!==launch.container.id||JSON.stringify(value.sources)!==JSON.stringify(launch.sources)||JSON.stringify(value.sources)!==JSON.stringify(binding.sources)||JSON.stringify(value.environment)!==JSON.stringify(codexTraceEnvironment(value.mode))||value.complete!==true||value.cleanupOk!==settlement.cleanupOk||value.engineExitStatus!==settlement.engineExitStatus||value.requestedStop!==settlement.requestedStop||!Number.isSafeInteger(value.stderrBytes)||value.stderrBytes<0||value.stderrBytes>16*1024*1024||!hex(value.stderrSHA256)||!hex(value.stderrChain)||!Array.isArray(value.events)||value.events.length>64||(v2&&(!Array.isArray(value.autoCalls)||JSON.stringify(value.autoCalls)!==JSON.stringify(value.events.filter((e:any)=>e.kind==="autoCompactNew")))))throw Error("Unbound native trace capture");
 const directory=dirname(receiptProvenance.get(value)!.rawPath),lines:Array<Readonly<CapturedTraceEvent>>=[];let lastSequence=0,lastEnd=0;
 for(const [index,event] of value.events.entries()){
  if(!exact(event,["file","sha256","bytes","stderrSequence","stderrOffset","chain","turnId","nativeTimestamp","observedAtMs","observedMonotonicNs",...(v2?["kind","threadId"]:[])])||event.file!==`trace-event-${String(index).padStart(4,"0")}.raw`||!hex(event.sha256)||!hex(event.chain)||!Number.isSafeInteger(event.bytes)||event.bytes<2||event.bytes>65536||!Number.isSafeInteger(event.stderrSequence)||event.stderrSequence<=lastSequence||!Number.isSafeInteger(event.stderrOffset)||event.stderrOffset<lastEnd||event.stderrOffset+event.bytes>value.stderrBytes||typeof event.turnId!=="string"||event.turnId.length<1||event.turnId.length>512||!Number.isSafeInteger(event.observedAtMs)||!Number.isSafeInteger(event.observedMonotonicNs)||(v2&&(!["postSampling","autoCompactNew"].includes(event.kind)||typeof event.threadId!=="string"||!event.threadId)))throw Error("Invalid native trace index");
  const path=join(directory,event.file),fd=openSync(path,constants.O_RDONLY|constants.O_NOFOLLOW);let raw:Buffer;
  try{const info=fstatSync(fd);if(!info.isFile()||info.uid!==binding.uid||(info.mode&0o777)!==0o600||info.nlink!==1||info.size!==event.bytes)throw Error("Unsafe original native trace");raw=readFileSync(fd);const after=fstatSync(fd);if(raw.length!==event.bytes||after.size!==info.size||after.mtimeMs!==info.mtimeMs||after.ctimeMs!==info.ctimeMs||digest(raw)!==event.sha256||raw.at(-1)!==10||raw.subarray(0,-1).includes(10))throw Error("Changed original native trace");}finally{closeSync(fd);}
  const parsed=JSON.parse(new TextDecoder("utf-8",{fatal:true}).decode(raw)),kind=v2?event.kind:"postSampling";
  if(!object(parsed)||parsed.target!=="codex_core::session::turn"||parsed.level!=="TRACE"||!object(parsed.fields)||JSON.stringify(parsed.timestamp??null)!==JSON.stringify(event.nativeTimestamp))throw Error("Original trace selector mismatch");
  if(kind==="postSampling"?(parsed.fields.message!=="post sampling token usage"||parsed.fields.turn_id!==event.turnId):(parsed.fields.message!=="new"||!object(parsed.span)||parsed.span.name!=="run_auto_compact"||typeof parsed.span.reason!=="string"||!parsed.span.reason||typeof parsed.span.phase!=="string"||!parsed.span.phase))throw Error("Original trace selector mismatch");
  if(v2){const task=traceTaskIdentity(parsed);if(task.threadId!==event.threadId||task.turnId!==event.turnId||typeof parsed.timestamp!=="string"||!parsed.timestamp)throw Error("Original V2 task/timestamp mismatch");}
  freeze(parsed);lines.push(Object.freeze({bytes:raw,parsed,stderrSequence:event.stderrSequence,lineSha256:event.sha256,kind}));lastSequence=event.stderrSequence;lastEnd=event.stderrOffset+event.bytes;
 }
 freeze(value);verifiedTrace.add(value);traceLines.set(value,Object.freeze(lines));return value as CodexNativeTraceReceipt;
}
export const isVerifiedCodexTraceReceipt=(v:unknown):v is CodexNativeTraceReceipt=>!!v&&typeof v==="object"&&verifiedTrace.has(v);
export function getCodexTraceUtf8(value:CodexNativeTraceReceipt){return verifiedTrace.has(value)?rawReceiptBytes.get(value):undefined;}
/** All original events, including every numeric record and every AUTO NEW. */
export function getCodexTraceEvents(value:CodexNativeTraceReceipt){return verifiedTrace.has(value)?traceLines.get(value)?.map(v=>Object.freeze({...v,bytes:Buffer.from(v.bytes)})):undefined;}
export function getCodexTraceAutoCalls(value:Extract<CodexNativeTraceReceipt,{schema:"codex-native-trace-v2"}>):CodexOriginalTraceLine[]|undefined {
 if(!isVerifiedCodexTraceReceipt(value)||value.schema!=="codex-native-trace-v2"||value.mode!=="post-sampling-token-usage-v2")return undefined;
 return getCodexTraceEvents(value)?.filter(e=>e.kind==="autoCompactNew").map(e=>({lineUtf8:e.bytes.toString("utf8"),stderrSequence:e.stderrSequence,lineSha256:e.lineSha256}));
}
/** Genuine transport projection. Causal/native acceptance still requires E's joins. */
export function getCodexRetainedTraceEvidence(value:CodexNativeTraceReceipt,selectedMode:Exclude<CodexNativeTraceMode,"off">) {
 if(!isVerifiedCodexTraceReceipt(value))throw Error("Missing original producer trace");
 if(value.mode!==selectedMode||value.schema!==codexTraceSchemaForMode(selectedMode))throw Error("Selected root trace mode mismatch");
 const events=getCodexTraceEvents(value),raw=getCodexTraceUtf8(value);if(!events||!raw)throw Error("Missing original trace bytes");
 const original=(e:CapturedTraceEvent):CodexOriginalTraceLine=>({lineUtf8:e.bytes.toString("utf8"),stderrSequence:e.stderrSequence,lineSha256:e.lineSha256});
 const lines=events.filter(e=>e.kind==="postSampling").map(original),autoCalls=events.filter(e=>e.kind==="autoCompactNew").map(original);
 const common={status:"SOURCE_VALID" as const,nativeAcceptance:"NOT_TESTED" as const,lines,producer:{launchNonce:value.nonce,processId:`${value.producer.bootId}:${value.producer.pid}:${value.producer.startTicks}`},receiptSha256:digest(Buffer.from(raw))};
 if(value.schema==="codex-native-trace-v2")return {...common,schema:value.schema,mode:value.mode,selectedMode:value.mode,autoCalls};
 return {...common,schema:value.schema,mode:value.mode,selectedMode:value.mode,autoCalls};
}

/** Read-only exact source preflight; grants no transport qualification or lease. */
export function assertCodexReceiptSourceClosure(deployment:string,sourceSha256:Readonly<Record<string,string>>,uid=process.getuid?.(),technicalVisionQualified=false):Record<string,string>{if(uid===undefined)throw Error("Source owner unavailable");if(Object.keys(sourceSha256).sort().join()!==[...sourceProfile(technicalVisionQualified)].sort().join())throw Error("Incomplete reviewed receipt source closure");const policy={sourceSha256},sources:Record<string,string>={};
  for (const relative of sourceProfile(technicalVisionQualified)) { const path=join(deployment,relative), info=lstatSync(path); if (!info.isFile() || info.isSymbolicLink() || info.mode & 0o022 || ![0,uid].includes(info.uid) || realpathSync(path)!==path) throw Error('Unsafe receipt source'); for (let parent=dirname(path); parent!==dirname(deployment); parent=dirname(parent)) { const s=lstatSync(parent); if (!s.isDirectory() || s.isSymbolicLink() || s.mode&0o022 || ![0,uid].includes(s.uid)) throw Error('Unsafe receipt source ancestry'); } const actual=digest(readFileSync(path)); if (!hex(policy.sourceSha256[relative]) || actual!==policy.sourceSha256[relative]) throw Error('Receipt source hash mismatch'); sources[relative]=actual; }
return sources;}
