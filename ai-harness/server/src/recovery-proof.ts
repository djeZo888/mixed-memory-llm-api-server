/** One root-reviewed offline interruption disposition. No remote observation or cleanup. */
import { createHash } from "node:crypto";
import { constants, closeSync, fstatSync, lstatSync, openSync, readFileSync, realpathSync } from "node:fs";
import path from "node:path";
import type { DatabaseSync } from "node:sqlite";
import type { RecoveryTarget } from "./recovery-snapshot.js";

export const ORIGINAL_RELEASE = "74507f64c1ea8e303e16d279703f307467b35618";
export const ORIGINAL_GATEWAY_SHA256 = "58b44e2e1a627000b378203a7fbc22e6dea7c18246ffb3a131f55a58f48ba886";
export const ORIGINAL_MAIN_SHA256 = "e6cf0a8506885a87d7b0289a3d5970ed6af1e9c14d70e9f0ebbdd2d93d70fe4a";
export const RECOVERY_LANE = "qwen3.8-27b-gpu0";
export const RECOVERY_ENDPOINT = "http://10.156.100.60:30002/v1";
export const sha256 = (value: string | Buffer) => createHash("sha256").update(value).digest("hex");
export interface EvidenceFile { path: string; sha256: string }
export interface CurrentFile extends EvidenceFile { uid: number; mode: number }
export interface RecoveryProof {
  schema: 1;
  operation: "release-one-interrupted-codex";
  recoveryId: string;
  issuedAt: string;
  expiresAt: string;
  target: RecoveryTarget;
  database: { path: string; uid: number; dev: number; ino: number; snapshotSha256: string };
  deployment: {
    sourceCommit: string; releasePath: string; config: CurrentFile; unit: CurrentFile;
    build: Record<string, CurrentFile>;
  };
  maintenance: { config: CurrentFile; responseStatus: 503; capture: EvidenceFile; observedAt: string; workers: { pid: number; startTicks: string }[] };
  harness: { oldBootId: string; newBootId: string; newBootStartedAt: string; capture: EvidenceFile };
  native: {
    containerId: string; imageId: string; uid: number; workspaceMount: string; threadHomeMount: string;
    lineage: EvidenceFile; cleanup: EvidenceFile;
    removedAt: string; absenceObservedAt: string;
    removeArgv: string[]; removeExit: 0; absenceArgv: string[]; absenceExit: 1;
  };
  provider: {
    originalSourceCommit: string; originalGateway: EvidenceFile; originalMain: EvidenceFile; originalConfig: EvidenceFile;
    upstreamMode: "DEFAULT_UPSTREAMS"; lane: string; endpoint: string;
    nodeAlias: "ai-vm"; oldSshHostKeySha256: string; newSshHostKeySha256: string;
    nodeAttestation: EvidenceFile; oldCapture: EvidenceFile; newCapture: EvidenceFile;
    oldBootId: string; newBootId: string; newBootStartedAt: string;
    runtimeBootId: string; runtimeStartedAt: string; runtimeInvocationId: string;
    replayPolicy: "volatile-no-durable-request-replay"; replayReview: EvidenceFile;
    requests: { id: string; acceptedAt: string; lane: string; endpoint: string }[];
  };
}

function check(value: unknown, reason: string): asserts value { if (!value) throw Error(`Recovery refused: ${reason}`); }
function keys(value: unknown, names: string, label: string): asserts value is Record<string, unknown> {
  check(value && typeof value === "object" && !Array.isArray(value), `${label} object`);
  check(Object.keys(value).sort().join(",") === names.split(" ").sort().join(","), `${label} closed schema`);
}
function text(value: unknown): asserts value is string { check(typeof value === "string" && value.length > 0 && value.length < 4096 && !/[\x00-\x1f\x7f]/.test(value), "invalid text"); }
function digest(value: unknown) { check(typeof value === "string" && /^[a-f0-9]{64}$/.test(value), "SHA256 required"); }
function uuid(value: unknown) { check(typeof value === "string" && /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/.test(value), "UUID required"); }
function date(value: unknown): number { text(value); const n = Date.parse(value); check(Number.isFinite(n) && /Z$/.test(value), "UTC timestamp required"); return n; }
function absolute(value: unknown) { text(value); check(path.isAbsolute(value) && path.normalize(value) === value, "canonical absolute path required"); }
function file(value: unknown) { keys(value, "path sha256", "evidence file"); absolute(value.path); digest(value.sha256); }
function currentFile(value: unknown, appUid: number) {
  keys(value, "path sha256 uid mode", "current deployment file"); absolute(value.path); digest(value.sha256);
  check(value.uid === 0 || value.uid === appUid, "current file owner");
  check(Number.isSafeInteger(value.mode) && Number(value.mode) >= 0 && Number(value.mode) <= 0o777 && (Number(value.mode) & 0o022) === 0, "current file permissions");
}
export const BUILD_NAMES = ["main", "store", "gateway-ownership", "interrupted-recovery", "recovery-proof", "recovery-snapshot"] as const;

/** Root owns the complete normalized attestation and archives. Hostname/booleans alone never suffice. */
export function parseRecoveryProof(value: unknown): RecoveryProof {
  keys(value, "schema operation recoveryId issuedAt expiresAt target database deployment maintenance harness native provider", "proof");
  check(value.schema === 1 && value.operation === "release-one-interrupted-codex", "operation");
  uuid(value.recoveryId); date(value.issuedAt); date(value.expiresAt);
  keys(value.target, "sessionId runId workspaceId threadId turnId requestIds", "target");
  for (const name of ["sessionId", "runId", "workspaceId", "threadId", "turnId"]) uuid(value.target[name]);
  check(Array.isArray(value.target.requestIds) && value.target.requestIds.length > 0 && value.target.requestIds.length <= 32, "explicit request IDs");
  value.target.requestIds.forEach(uuid);
  check(new Set(value.target.requestIds).size === value.target.requestIds.length, "duplicate request ID");
  keys(value.database, "path uid dev ino snapshotSha256", "database"); absolute(value.database.path); digest(value.database.snapshotSha256);
  for (const name of ["uid", "dev", "ino"]) check(Number.isSafeInteger(value.database[name]) && Number(value.database[name]) >= 0, "database identity");
  check(Number(value.database.uid) > 0, "existing non-root app UID required");
  keys(value.deployment, "sourceCommit releasePath config unit build", "deployment");
  check(typeof value.deployment.sourceCommit === "string" && /^[a-f0-9]{40}$/.test(value.deployment.sourceCommit), "current source commit");
  absolute(value.deployment.releasePath); currentFile(value.deployment.config, Number(value.database.uid)); currentFile(value.deployment.unit, Number(value.database.uid));
  keys(value.deployment.build, BUILD_NAMES.join(" "), "semantic build");
  for (const name of BUILD_NAMES) { currentFile(value.deployment.build[name], Number(value.database.uid)); const f = value.deployment.build[name] as unknown as EvidenceFile; check(f.path === path.join(String(value.deployment.releasePath), "server/dist", `${name}.js`), "build outside exact release"); }
  keys(value.maintenance, "config responseStatus capture observedAt workers", "maintenance"); currentFile(value.maintenance.config, Number(value.database.uid)); file(value.maintenance.capture); check(value.maintenance.responseStatus === 503, "maintenance must be 503");
  const maintenanceConfig = value.maintenance.config as unknown as CurrentFile;
  check(maintenanceConfig.path.startsWith("/etc/nginx/") && maintenanceConfig.uid === 0, "current nginx configuration required");
  check(date(value.maintenance.observedAt) <= date(value.issuedAt) && date(value.issuedAt) - date(value.maintenance.observedAt) <= 5 * 60_000, "fresh served maintenance capture required");
  check(Array.isArray(value.maintenance.workers) && value.maintenance.workers.length > 0 && value.maintenance.workers.length <= 64, "current nginx worker generation required");
  for (const worker of value.maintenance.workers) { keys(worker, "pid startTicks", "nginx worker"); check(Number.isSafeInteger(worker.pid) && Number(worker.pid) > 1 && typeof worker.startTicks === "string" && /^[1-9][0-9]*$/.test(worker.startTicks), "nginx worker identity"); }
  check(new Set(value.maintenance.workers.map(worker => worker.pid)).size === value.maintenance.workers.length, "duplicate nginx worker");
  keys(value.harness, "oldBootId newBootId newBootStartedAt capture", "harness"); uuid(value.harness.oldBootId); uuid(value.harness.newBootId); date(value.harness.newBootStartedAt); file(value.harness.capture);
  check(value.harness.oldBootId !== value.harness.newBootId, "same harness boot");
  keys(value.native, "containerId imageId uid workspaceMount threadHomeMount lineage cleanup removedAt absenceObservedAt removeArgv removeExit absenceArgv absenceExit", "native");
  digest(value.native.containerId); check(typeof value.native.imageId === "string" && /^sha256:[a-f0-9]{64}$/.test(value.native.imageId), "exact native image digest required"); absolute(value.native.workspaceMount); absolute(value.native.threadHomeMount); file(value.native.lineage); file(value.native.cleanup);
  check(value.native.uid === value.database.uid, "native UID mismatch");
  check(path.basename(String(value.native.workspaceMount)) === value.target.workspaceId, "workspace mount lineage");
  check(value.native.workspaceMount !== value.native.threadHomeMount, "native history mount required");
  check(JSON.stringify(value.native.removeArgv) === JSON.stringify(["podman", "rm", "-f", value.native.containerId]) && value.native.removeExit === 0, "exact supported removal required");
  check(JSON.stringify(value.native.absenceArgv) === JSON.stringify(["podman", "container", "exists", value.native.containerId]) && value.native.absenceExit === 1, "exact container absence required; PID0 is insufficient");
  check(date(value.native.removedAt) >= date(value.harness.newBootStartedAt) && date(value.native.absenceObservedAt) >= date(value.native.removedAt), "native cleanup chronology");
  keys(value.provider, "originalSourceCommit originalGateway originalMain originalConfig upstreamMode lane endpoint nodeAlias oldSshHostKeySha256 newSshHostKeySha256 nodeAttestation oldCapture newCapture oldBootId newBootId newBootStartedAt runtimeBootId runtimeStartedAt runtimeInvocationId replayPolicy replayReview requests", "provider");
  check(value.provider.originalSourceCommit === ORIGINAL_RELEASE && value.provider.upstreamMode === "DEFAULT_UPSTREAMS", "reviewed original source/config closure");
  for (const name of ["originalGateway", "originalMain", "originalConfig", "nodeAttestation", "oldCapture", "newCapture", "replayReview"]) file(value.provider[name]);
  check((value.provider.originalGateway as unknown as EvidenceFile).sha256 === ORIGINAL_GATEWAY_SHA256 &&
    (value.provider.originalMain as unknown as EvidenceFile).sha256 === ORIGINAL_MAIN_SHA256, "original reviewed gateway/main source hashes");
  check(value.provider.lane === RECOVERY_LANE && value.provider.endpoint === RECOVERY_ENDPOINT && value.provider.nodeAlias === "ai-vm", "fixed endpoint/node/lane lineage");
  digest(value.provider.oldSshHostKeySha256); digest(value.provider.newSshHostKeySha256);
  check(value.provider.oldSshHostKeySha256 === value.provider.newSshHostKeySha256, "authenticated same-machine host key required");
  uuid(value.provider.oldBootId); uuid(value.provider.newBootId); uuid(value.provider.runtimeBootId);
  check(typeof value.provider.runtimeInvocationId === "string" && /^[a-f0-9]{32}$/.test(value.provider.runtimeInvocationId), "exact systemd InvocationID required");
  check(value.provider.oldBootId !== value.provider.newBootId && value.provider.runtimeBootId === value.provider.newBootId, "new provider boot and fresh runtime required");
  check(date(value.provider.runtimeStartedAt) >= date(value.provider.newBootStartedAt), "runtime predates reboot");
  check(value.provider.replayPolicy === "volatile-no-durable-request-replay", "reviewed absence of durable replay required");
  check(Array.isArray(value.provider.requests) && value.provider.requests.length === value.target.requestIds.length, "exact affected requests");
  const requestIds: string[] = [];
  for (const request of value.provider.requests) {
    keys(request, "id acceptedAt lane endpoint", "request"); uuid(request.id); date(request.acceptedAt);
    check(request.lane === value.provider.lane && request.endpoint === value.provider.endpoint, "request endpoint/lane");
    check(date(request.acceptedAt) < date(value.provider.newBootStartedAt) && date(request.acceptedAt) < date(value.harness.newBootStartedAt), "request after reboot");
    requestIds.push(String(request.id));
  }
  check(JSON.stringify(requestIds.sort()) === JSON.stringify([...value.target.requestIds].sort()), "request set mismatch");
  check(date(value.issuedAt) >= Math.max(date(value.native.absenceObservedAt), date(value.provider.runtimeStartedAt)), "proof predates physical evidence");
  check(date(value.expiresAt) > date(value.issuedAt) && date(value.expiresAt) - date(value.issuedAt) <= 15 * 60_000, "bounded current authorization required");
  return value as unknown as RecoveryProof;
}

/** No symlink, writable parent, root-writable delegation, or app-owned proof accepted. */
export function readRootProtected(filePath: string): Buffer {
  absolute(filePath); check(realpathSync(filePath) === filePath, "symlink in protected path");
  let parent = path.dirname(filePath);
  for (;;) { const st = lstatSync(parent); check(st.isDirectory() && st.uid === 0 && (st.mode & 0o022) === 0, "unprotected evidence directory"); if (parent === "/") break; parent = path.dirname(parent); }
  const fd = openSync(filePath, constants.O_RDONLY | constants.O_NOFOLLOW);
  try { const st = fstatSync(fd); check(st.isFile() && st.uid === 0 && st.nlink === 1 && (st.mode & 0o022) === 0 && st.size <= 16 * 1024 * 1024, "root-owned protected regular evidence required"); return readFileSync(fd); } finally { closeSync(fd); }
}
export function evidenceFiles(proof: RecoveryProof): EvidenceFile[] {
  return [proof.maintenance.capture, proof.harness.capture, proof.native.lineage, proof.native.cleanup,
    proof.provider.originalGateway, proof.provider.originalMain, proof.provider.originalConfig, proof.provider.nodeAttestation, proof.provider.oldCapture, proof.provider.newCapture, proof.provider.replayReview];
}
export function readCurrentFile(item: CurrentFile, appUid: number): Buffer {
  absolute(item.path); check(realpathSync(item.path) === item.path, "symlink in current deployment");
  let parent = path.dirname(item.path);
  for (;;) { const st = lstatSync(parent); check(st.isDirectory() && [0, appUid].includes(st.uid) && (st.mode & 0o022) === 0, "unsafe current deployment directory"); if (parent === "/") break; parent = path.dirname(parent); }
  const fd = openSync(item.path, constants.O_RDONLY | constants.O_NOFOLLOW);
  try { const st = fstatSync(fd); check(st.isFile() && st.nlink === 1 && st.uid === item.uid && (st.mode & 0o777) === item.mode && st.size <= 16 * 1024 * 1024, "current deployment metadata drift"); return readFileSync(fd); } finally { closeSync(fd); }
}
export function verifyEvidenceFiles(proof: RecoveryProof, read: (p: string) => Buffer = readRootProtected, current: (item: CurrentFile, appUid: number) => Buffer = readCurrentFile) {
  for (const item of evidenceFiles(proof)) check(sha256(read(item.path)) === item.sha256, "archived/current source or evidence hash drift");
  for (const item of [proof.deployment.config, proof.deployment.unit, ...Object.values(proof.deployment.build), proof.maintenance.config]) check(sha256(current(item, proof.database.uid)) === item.sha256, "current deployment hash drift");
}
export function verifyRequestBinding(db: DatabaseSync, proof: RecoveryProof) {
  for (const request of proof.provider.requests) {
    const row = db.prepare("SELECT session_id,state,record FROM h021_gateway_requests WHERE id=?").get(request.id);
    check(row && row.session_id === proof.target.sessionId && row.state === "accepted", "original accepted request required");
    const record = JSON.parse(String(row.record));
    check(record.id === request.id && record.sessionId === proof.target.sessionId && record.state === "accepted" && record.lane === request.lane && record.updatedAt === request.acceptedAt, "accepted request time/lane binding changed");
  }
}

export interface LocalBoundary {
  uid: number; bootId: string; now: number; database: { dev: number; ino: number; uid: number };
  service: { LoadState: string; ActiveState: string; SubState: string; MainPID: string };
  databaseUsers: number[];
  maintenanceWorkers: { pid: number; startTicks: string }[];
}
export function verifyLocalBoundary(proof: RecoveryProof, observed: LocalBoundary) {
  check(observed.uid > 0 && observed.uid === proof.database.uid && observed.database.uid === observed.uid, "run as existing app user, never root");
  check(observed.database.dev === proof.database.dev && observed.database.ino === proof.database.ino, "database replaced");
  check(observed.bootId === proof.harness.newBootId, "current harness boot drift");
  check(observed.now >= Date.parse(proof.issuedAt) && observed.now <= Date.parse(proof.expiresAt), "stale or future authorization");
  check(JSON.stringify(observed.service) === JSON.stringify({ LoadState: "masked", ActiveState: "inactive", SubState: "dead", MainPID: "0" }), "app must be stopped and masked for offline exclusivity");
  check(observed.databaseUsers.length === 0, "database open in another process");
  const workerKey = (workers: LocalBoundary["maintenanceWorkers"]) => JSON.stringify([...workers].sort((a, b) => a.pid - b.pid).map(worker => [worker.pid, worker.startTicks]));
  check(workerKey(observed.maintenanceWorkers) === workerKey(proof.maintenance.workers), "served maintenance worker generation changed");
}
