/** Private host receipt channel. Neither native stdio nor caller JSON is an attestation. */
import { constants, openSync, closeSync, fstatSync, readFileSync, lstatSync, mkdirSync, mkdtempSync, writeFileSync, realpathSync } from "node:fs";
import { createHash, randomBytes } from "node:crypto";
import { join, dirname, resolve, sep } from "node:path";
import { assertAuthenticatedCodexHandoff, type AuthenticatedCodexHandoff } from "./codex-policy-handoff.js";
export const CODEX_RECEIPT_SOURCES = ["run-codex.sh", "engine/task-egress.py", "engine/redact-acp.py", "engine/codex_receipts.py", "security/chromium-seccomp.json", "codex/config.toml", "codex/models.json"] as const;
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
export interface CodexReceiptBinding { nonce: string; runId: string; sessionId: string; startedAtMs: number; uid: number; profileDir: string; workspace: string; deploymentDir: string; imageJobsQualified: boolean; gid: number; sources: Record<string, string> }
function identity(v: unknown): v is CodexReceiptIdentity {
  return object(v) && exact(v, ["pid", "startTicks", "uid", "bootId", "cgroupPath"]) && Number.isSafeInteger(v.pid) && v.pid > 0 && Number.isSafeInteger(v.uid) && v.uid > 0 && typeof v.startTicks === "string" && /^\d+$/.test(v.startTicks) && typeof v.bootId === "string" && /^[0-9a-f-]{36}$/.test(v.bootId) && typeof v.cgroupPath === "string" && v.cgroupPath.length < 1024;
}
function common(v: Record<string, any>, binding: CodexReceiptBinding, now: number) {
  return v.nonce === binding.nonce && hex(v.nonce) && v.runId === binding.runId && v.sessionId === binding.sessionId && Number.isSafeInteger(v.checkedAtMs) && v.checkedAtMs >= binding.startedAtMs && v.checkedAtMs <= now + 1000 && identity(v.producer) && v.producer.uid === binding.uid;
}
export function validateCodexLaunchReceipt(value: unknown, binding: CodexReceiptBinding, observedProducer: CodexReceiptIdentity, now = Date.now()): CodexNativeLaunchReceipt {
  if (!object(value) || !exact(value, ["schema", "nonce", "runId", "sessionId", "checkedAtMs", "producer", "sources", "egress", "container"]) || value.schema !== "codex-launch-v1" || !common(value, binding, now) || now - value.checkedAtMs > 15000 || JSON.stringify(value.producer) !== JSON.stringify(observedProducer) || !object(value.sources) || Object.keys(value.sources).sort().join() !== Object.keys(binding.sources).sort().join() || Object.entries(binding.sources).some(([k,v]) => value.sources[k] !== v)) throw Error("Untrusted native launch receipt");
  const e = value.egress, c = value.container;
  const prefix = `user.slice/user-${binding.uid}.slice/user@${binding.uid}.service/aiharnesstasks.slice`;
  if (!exact(e, ["bootId", "uid", "cgroupPath", "cgroupInode", "nftSha256", "checkedBoottime", "receiptSha256"]) || e.bootId !== value.producer.bootId || e.uid !== binding.uid || e.cgroupPath !== prefix || !Number.isSafeInteger(e.cgroupInode) || e.cgroupInode < 1 || !hex(e.nftSha256) || !hex(e.receiptSha256) || !Number.isFinite(e.checkedBoottime) || !value.producer.cgroupPath.startsWith('/'+prefix+'/')) throw Error("Invalid launch egress receipt");
  if (!exact(c, ["id", "name", "imageId", "imageRevision", "imagePatchset", "pid", "pidStartTicks", "rootless", "user", "network", "capDrop", "securityOpt", "readOnly", "privileged", "mounts", "additionalMounts", "workdir", "profileDir", "workspace"]) || !hex(c.id) || typeof c.name !== "string" || !/^ai-harness-[0-9a-f]{32}$/.test(c.name) || c.imageId.replace(/^sha256:/,'') !== 'd8841743002e16de1f9269a850a2f06a73055688befec4c309778ca8a4c11aad' || c.imageRevision !== '064c6b8c737f5b41d171fdda80bd9ef10ad06eb3' || c.imagePatchset !== 'dd0ff12a651db4cc8521cddb8e5094c5a197ca87cef6b7ec797343da67d9f1ec' || !Number.isSafeInteger(c.pid) || c.pid < 1 || !/^\d+$/.test(c.pidStartTicks) || c.rootless !== true || c.user !== `${binding.uid}:${binding.gid}` || c.network !== 'slirp4netns:allow_host_loopback=true' || JSON.stringify(c.capDrop) !== '["ALL"]' || !Array.isArray(c.securityOpt) || !c.securityOpt.includes('no-new-privileges') || !c.securityOpt.some((x: unknown) => typeof x === 'string' && x.startsWith('seccomp=')) || c.readOnly !== true || c.privileged !== false || c.profileDir !== binding.profileDir || c.workspace !== binding.workspace || c.workdir !== binding.workspace || !Array.isArray(c.mounts) || c.mounts.length !== 7 || c.mounts.some((m: unknown) => !object(m) || !exact(m, ['source','destination','rw','type']) || typeof m.source !== 'string' || typeof m.destination !== 'string' || typeof m.rw !== 'boolean' || m.type !== 'bind') || c.mounts.filter((m: any) => m.rw).length !== 2 || !c.mounts.some((m: any) => m.source === binding.profileDir && m.destination === binding.profileDir && m.rw) || !c.mounts.some((m: any) => m.source === binding.workspace && m.destination === binding.workspace && m.rw)) throw Error("Invalid actual native container receipt");
  const ro = (source: string, destination: string) => ({ source, destination, rw: false, type: 'bind' });
  if (!Array.isArray(c.additionalMounts) || c.additionalMounts.length > 3 || c.additionalMounts.some((m: unknown) => !object(m) || !exact(m, ['source','destination','rw','type']) || m.source !== '' || m.type !== 'tmpfs' || m.rw !== true || !['/tmp','/run','/var/tmp'].includes(m.destination)) || new Set(c.additionalMounts.map((m: any) => m.destination)).size !== c.additionalMounts.length) throw Error('Unexpected additional native mount receipt');
  const expectedMounts = [{source:binding.profileDir,destination:binding.profileDir,rw:true,type:'bind'}, {source:binding.workspace,destination:binding.workspace,rw:true,type:'bind'}, ro(join(dirname(binding.deploymentDir),'tools/image/image-mcp.mjs'),'/opt/ai-harness/tools/image/image-mcp.mjs'),ro(join(dirname(binding.deploymentDir),'tools/image/image.mjs'),'/opt/ai-harness/tools/image/image.mjs'),ro(join(binding.deploymentDir,'codex',binding.imageJobsQualified?'config-image-jobs.toml':'config.toml'),join(binding.profileDir,'codex-home/config.toml')),ro(join(binding.deploymentDir,'codex/models.json'),'/opt/sova/codex/models.json'),ro(join(binding.deploymentDir,'codex/skills/sova-local-tools'),join(binding.profileDir,'codex-home/skills/sova-local-tools'))];
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
export function createCodexReceiptChannel(input: { sessionId: string; runId: string; profileDir: string; workspace: string; launcherPath: string; imageJobsQualified?: boolean }, policy: CodexReceiptPolicy) {
  const uid = process.getuid?.(); if (process.platform !== 'linux' || !uid || policy.linuxTransportQualified !== true) throw Error('Native receipt transport unqualified');
  const deployment = resolve(input.launcherPath,'..'); const sources: Record<string,string> = {};
  if (Object.keys(policy.sourceSha256).sort().join() !== [...CODEX_RECEIPT_SOURCES].sort().join()) throw Error('Incomplete reviewed receipt source closure');
  for (const relative of CODEX_RECEIPT_SOURCES) { const path=join(deployment,relative), info=lstatSync(path); if (!info.isFile() || info.isSymbolicLink() || info.mode & 0o022 || ![0,uid].includes(info.uid) || realpathSync(path)!==path) throw Error('Unsafe receipt source'); for (let parent=dirname(path); parent!==dirname(deployment); parent=dirname(parent)) { const s=lstatSync(parent); if (!s.isDirectory() || s.isSymbolicLink() || s.mode&0o022 || ![0,uid].includes(s.uid)) throw Error('Unsafe receipt source ancestry'); } const actual=digest(readFileSync(path)); if (!hex(policy.sourceSha256[relative]) || actual!==policy.sourceSha256[relative]) throw Error('Receipt source hash mismatch'); sources[relative]=actual; }
  const root=`/run/user/${uid}/ai-harness-codex-receipts`; if (![input.profileDir,input.workspace].every(p => p!==root && !root.startsWith(p+sep) && !p.startsWith(root+sep) && !deployment.startsWith(p+sep) && p!==deployment)) throw Error('Receipt/source channel overlaps model mount');
  try { mkdirSync(root,{mode:0o700}); } catch (e) { if ((e as NodeJS.ErrnoException).code!=='EEXIST') throw e; } protectedDirectory(root,uid);
  const directory=mkdtempSync(join(root,'run-'));protectedDirectory(directory,uid);
  const binding: CodexReceiptBinding={nonce:randomBytes(32).toString('hex'),runId:input.runId,sessionId:input.sessionId,startedAtMs:Date.now(),uid,profileDir:input.profileDir,workspace:input.workspace,deploymentDir:deployment,imageJobsQualified:input.imageJobsQualified===true,gid:process.getgid!(),sources};
  writeFileSync(join(directory,'request.json'),JSON.stringify(binding),{flag:'wx',mode:0o600});
  return { directory, binding, async wait(name: 'launch'|'settlement', timeoutMs: number, ended: ()=>boolean): Promise<unknown|undefined> {
    const deadline=Date.now()+timeoutMs;
    while (Date.now()<deadline) { try { protectedDirectory(directory,uid); const ready=lstatSync(join(directory,name+'.ready')); if (!ready.isFile() || ready.isSymbolicLink() || ready.uid!==uid || (ready.mode&0o777)!==0o600 || ready.nlink!==1 || ready.size!==0) return undefined; const value = readCodexReceiptFile(join(directory,name+'.json'),uid); if (object(value)) transportReadObjects.add(value); return value; } catch(e) { if ((e as NodeJS.ErrnoException).code!=='ENOENT') return undefined; } if (ended()) return undefined; await new Promise<void>(r=>{const t=setTimeout(r,25);t.unref();}); } return undefined;
  } };
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
      const timer = setTimeout(expire, input.cleanupBudgetMs ?? 45000); timer.unref();
      try { if (!input.hasExited()) input.terminate(); const receipt = await settlementReceipt; return receipt?.cleanupOk === true; }
      catch { expire(); return false; }
      finally { clearTimeout(timer); }
    })();
  } };
}
