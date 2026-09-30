import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import { chmodSync, lstatSync, mkdtempSync, realpathSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { DatabaseSync } from "node:sqlite";
import test from "node:test";
import {
  evidenceFiles, parseRecoveryProof, readRootProtected, verifyEvidenceFiles, verifyLocalBoundary, verifyRequestBinding,
  type LocalBoundary, type RecoveryProof,
} from "../src/recovery-proof.js";
import { fixtureBoundary, fixtureEvidenceBytes, fixtureProof } from "./recovery-proof-fixture.js";

test("whole-node proof validates exact trusted source shape without an old provider PID or container", () => {
  const proof = fixtureProof();
  assert.equal("pid" in proof.provider, false);
  assert.equal("containerId" in proof.provider, false);
  assert.equal(parseRecoveryProof(proof), proof);
  assert.doesNotThrow(() => verifyLocalBoundary(proof, fixtureBoundary(proof)));
  assert.doesNotThrow(() => verifyEvidenceFiles(proof, fixtureEvidenceBytes, item => fixtureEvidenceBytes(item.path)));
});

const invalidProofCases: [string, (proof: RecoveryProof) => void, RegExp][] = [
  ["same harness boot", p => { p.harness.newBootId = p.harness.oldBootId; }, /same harness boot/],
  ["same provider boot", p => { p.provider.newBootId = p.provider.oldBootId; p.provider.runtimeBootId = p.provider.oldBootId; }, /new provider boot/],
  ["runtime from old provider boot", p => { p.provider.runtimeBootId = p.provider.oldBootId; }, /new provider boot/],
  ["runtime predates reboot", p => { p.provider.runtimeStartedAt = "2026-09-29T01:00:00.000Z"; }, /runtime predates reboot/],
  ["hyphenated UUID instead of actual systemd InvocationID", p => { p.provider.runtimeInvocationId = randomUUID(); }, /InvocationID|invocation/],
  ["truncated systemd InvocationID", p => { p.provider.runtimeInvocationId = "a".repeat(31); }, /InvocationID|invocation/],
  ["nonhex systemd InvocationID", p => { p.provider.runtimeInvocationId = "g".repeat(32); }, /InvocationID|invocation/],
  ["request after provider reboot", p => { p.provider.requests[0]!.acceptedAt = "2026-09-30T01:36:00.000Z"; }, /request after reboot/],
  ["request exactly at reboot", p => { p.provider.requests[0]!.acceptedAt = p.provider.newBootStartedAt; }, /request after reboot/],
  ["request after harness reboot", p => { p.provider.requests[0]!.acceptedAt = "2026-09-30T01:32:00.000Z"; }, /request after reboot/],
  ["changed original release", p => { p.provider.originalSourceCommit = "f".repeat(40); }, /original source\/config closure/],
  ["changed original gateway source", p => { p.provider.originalGateway.sha256 = "f".repeat(64); }, /original reviewed gateway\/main source hashes/],
  ["changed original main source", p => { p.provider.originalMain.sha256 = "f".repeat(64); }, /original reviewed gateway\/main source hashes/],
  ["upstream override", p => { (p.provider as any).upstreamMode = "OVERRIDE"; }, /original source\/config closure/],
  ["changed provider endpoint", p => { p.provider.endpoint = "http://other-node:30002/v1"; }, /endpoint\/node\/lane/],
  ["changed provider lane", p => { p.provider.lane = "different-lane"; }, /endpoint\/node\/lane/],
  ["hostname alone", p => { p.provider.oldSshHostKeySha256 = "ai-vm"; }, /SHA256 required/],
  ["different authenticated machine", p => { p.provider.newSshHostKeySha256 = "f".repeat(64); }, /same-machine host key/],
  ["changed node alias", p => { (p.provider as any).nodeAlias = "other-vm"; }, /endpoint\/node\/lane/],
  ["changed request endpoint", p => { p.provider.requests[0]!.endpoint = "http://other-node/v1"; }, /request endpoint\/lane/],
  ["changed request lane", p => { p.provider.requests[0]!.lane = "different-lane"; }, /request endpoint\/lane/],
  ["other affected request", p => { p.provider.requests[0]!.id = randomUUID(); }, /request set mismatch/],
  ["missing affected request", p => { p.provider.requests = []; }, /exact affected requests/],
  ["duplicate target request", p => { p.target.requestIds.push(p.target.requestIds[0]!); }, /duplicate request ID/],
  ["root app uid", p => { p.database.uid = 0; }, /non-root app UID/],
  ["other native uid", p => { p.native.uid++; }, /native UID mismatch/],
  ["native mutable image tag instead of digest", p => { p.native.imageId = "codex:latest"; }, /image/],
  ["native truncated image digest", p => { p.native.imageId = `sha256:${"a".repeat(63)}`; }, /image/],
  ["native malformed image digest", p => { p.native.imageId = `sha256:${"g".repeat(64)}`; }, /image/],
  ["other workspace mount", p => { p.native.workspaceMount = `/opt/workspaces/${randomUUID()}`; }, /workspace mount lineage/],
  ["history shares workspace mount", p => { p.native.threadHomeMount = p.native.workspaceMount; }, /native history mount/],
  ["created PID0 is not absence", p => { (p.native as any).absenceExit = 0; }, /exact container absence/],
  ["removal failed", p => { (p.native as any).removeExit = 1; }, /exact supported removal/],
  ["bulk cleanup", p => { p.native.removeArgv = ["podman", "container", "prune", "-f"]; }, /exact supported removal/],
  ["removal targets another container", p => { p.native.removeArgv[3] = "b".repeat(64); }, /exact supported removal/],
  ["absence targets another container", p => { p.native.absenceArgv[3] = "b".repeat(64); }, /exact container absence/],
  ["absence precedes removal", p => { p.native.absenceObservedAt = "2026-09-30T01:49:59.000Z"; }, /native cleanup chronology/],
  ["cleanup on old harness boot", p => { p.native.removedAt = "2026-09-29T23:00:00.000Z"; }, /native cleanup chronology/],
  ["maintenance open", p => { (p.maintenance as any).responseStatus = 200; }, /maintenance must be 503/],
  ["maintenance config outside nginx", p => { p.maintenance.config.path = "/opt/h036-test/maintenance.conf"; }, /current nginx configuration required/],
  ["app-owned maintenance config", p => { p.maintenance.config.uid = p.database.uid; }, /current nginx configuration required/],
  ["maintenance capture older than five minutes", p => { p.maintenance.observedAt = "2026-09-30T01:54:59.999Z"; }, /maintenance/],
  ["maintenance capture after proof", p => { p.maintenance.observedAt = "2026-09-30T02:00:00.001Z"; }, /maintenance/],
  ["no maintenance worker generation", p => { p.maintenance.workers = []; }, /maintenance|worker/],
  ["duplicate maintenance worker PID", p => { p.maintenance.workers.push({ ...p.maintenance.workers[0]! }); }, /maintenance|worker/],
  ["zero maintenance worker PID", p => { p.maintenance.workers[0]!.pid = 0; }, /maintenance|worker/],
  ["noninteger maintenance worker PID", p => { p.maintenance.workers[0]!.pid = 1.5; }, /maintenance|worker/],
  ["missing maintenance start ticks", p => { delete (p.maintenance.workers[0] as any).startTicks; }, /maintenance|worker/],
  ["nonnumeric maintenance start ticks", p => { p.maintenance.workers[0]!.startTicks = "unknown"; }, /maintenance|worker/],
  ["bare worker success authority", p => { (p.maintenance.workers[0] as any).success = true; }, /maintenance|worker/],
  ["unbounded authorization", p => { p.expiresAt = "2026-10-01T02:00:00.000Z"; }, /bounded current authorization/],
  ["proof predates evidence", p => { p.issuedAt = "2026-09-30T01:49:00.000Z"; p.maintenance.observedAt = p.issuedAt; }, /proof predates physical evidence/],
  ["build outside deployed release", p => { p.deployment.build.main!.path = "/opt/other/server/dist/main.js"; }, /build outside exact release/],
  ["unrelated current config owner", p => { p.deployment.config.uid = 2002; }, /current file owner/],
  ["group-writable current unit", p => { p.deployment.unit.mode = 0o664; }, /current file permissions/],
  ["world-writable current build", p => { p.deployment.build.main!.mode = 0o646; }, /current file permissions/],
  ["durable replay possible", p => { (p.provider as any).replayPolicy = "unknown"; }, /absence of durable replay/],
  ["bare success authority", p => { (p as any).success = true; }, /proof closed schema/],
  ["PID0 success authority", p => { (p.native as any).pid = 0; }, /native closed schema/],
];
for (const [name, mutate, expected] of invalidProofCases) test(`proof refuses ${name}`, () => {
  const proof = fixtureProof(); mutate(proof); assert.throws(() => parseRecoveryProof(proof), expected);
});

for (const [section, names] of Object.entries({
  provider: ["endpoint", "nodeAlias", "oldSshHostKeySha256", "newSshHostKeySha256", "nodeAttestation", "oldBootId", "newBootId", "newBootStartedAt", "runtimeBootId", "runtimeStartedAt", "runtimeInvocationId", "originalGateway", "originalMain", "originalConfig", "replayReview"],
  native: ["containerId", "imageId", "workspaceMount", "threadHomeMount", "lineage", "cleanup", "absenceArgv", "absenceExit"],
  harness: ["oldBootId", "newBootId", "newBootStartedAt", "capture"],
  maintenance: ["config", "capture", "responseStatus", "observedAt", "workers"],
})) {
  for (const name of names) test(`closed proof refuses missing ${section}.${name}`, () => {
    const proof = fixtureProof(); delete (proof as any)[section][name];
    assert.throws(() => parseRecoveryProof(proof), new RegExp(`${section} closed schema`));
  });
}

const invalidBoundaryCases: [string, (boundary: LocalBoundary) => void, RegExp][] = [
  ["root invocation", b => { b.uid = 0; }, /existing app user/],
  ["another app user", b => { b.uid++; }, /existing app user/],
  ["root-owned database", b => { b.database.uid = 0; }, /existing app user/],
  ["replaced database inode", b => { b.database.ino++; }, /database replaced/],
  ["replaced database device", b => { b.database.dev++; }, /database replaced/],
  ["unexpected current harness boot", b => { b.bootId = randomUUID(); }, /harness boot drift/],
  ["expired proof", b => { b.now = Date.parse("2026-09-30T02:11:00.000Z"); }, /stale or future authorization/],
  ["future proof", b => { b.now = Date.parse("2026-09-30T01:59:59.999Z"); }, /stale or future authorization/],
  ["active service", b => { b.service.ActiveState = "active"; }, /stopped and masked/],
  ["running service substate", b => { b.service.SubState = "running"; }, /stopped and masked/],
  ["live service PID", b => { b.service.MainPID = "12345"; }, /stopped and masked/],
  ["unmasked service", b => { b.service.LoadState = "loaded"; }, /stopped and masked/],
  ["another database user", b => { b.databaseUsers = [12345]; }, /database open/],
  ["missing maintenance worker", b => { b.maintenanceWorkers.pop(); }, /maintenance|worker/],
  ["extra maintenance worker", b => { b.maintenanceWorkers.push({ pid: 9876, startTicks: "481518" }); }, /maintenance|worker/],
  ["replaced maintenance worker PID", b => { b.maintenanceWorkers[0]!.pid++; }, /maintenance|worker/],
  ["reused maintenance worker PID", b => { b.maintenanceWorkers[0]!.startTicks = "999999"; }, /maintenance|worker/],
];
for (const [name, mutate, expected] of invalidBoundaryCases) test(`local boundary refuses ${name}`, () => {
  const proof = fixtureProof(); const boundary = fixtureBoundary(proof); mutate(boundary);
  assert.throws(() => verifyLocalBoundary(proof, boundary), expected);
});

test("all archived and deployed files, including original config, must match exact protected bytes", () => {
  const proof = fixtureProof();
  for (const item of evidenceFiles(proof)) {
    assert.throws(() => verifyEvidenceFiles(proof, p => p === item.path ? Buffer.from("replaced") : fixtureEvidenceBytes(p), value => fixtureEvidenceBytes(value.path)), /evidence hash drift/, item.path);
  }
  for (const item of [proof.deployment.config, proof.deployment.unit, ...Object.values(proof.deployment.build), proof.maintenance.config]) {
    assert.throws(() => verifyEvidenceFiles(proof, fixtureEvidenceBytes, value => value.path === item.path ? Buffer.from("replaced") : fixtureEvidenceBytes(value.path)), /current deployment hash drift/, item.path);
  }
  proof.provider.originalConfig.sha256 = "f".repeat(64);
  assert.throws(() => verifyEvidenceFiles(proof, fixtureEvidenceBytes, item => fixtureEvidenceBytes(item.path)), /evidence hash drift/);
});

test("maintenance worker comparison accepts the exact generation in any enumeration order", () => {
  const proof = fixtureProof(); const boundary = fixtureBoundary(proof);
  boundary.maintenanceWorkers.reverse();
  assert.doesNotThrow(() => verifyLocalBoundary(proof, boundary));
});

test("maintenance worker comparison uses named fields independently of JSON property order", () => {
  const proof = fixtureProof(); const boundary = fixtureBoundary(proof);
  boundary.maintenanceWorkers = boundary.maintenanceWorkers.map(worker => ({ startTicks: worker.startTicks, pid: worker.pid }));
  assert.doesNotThrow(() => verifyLocalBoundary(proof, boundary));
});

test("original accepted timestamp, session, lane and state must bind to retained ledger bytes", () => {
  const proof = fixtureProof(); const request = proof.provider.requests[0]!;
  const db = new DatabaseSync(":memory:");
  try {
    db.exec("CREATE TABLE h021_gateway_requests (id TEXT PRIMARY KEY, session_id TEXT, state TEXT, record TEXT)");
    const record = { id: request.id, sessionId: proof.target.sessionId, lane: request.lane, state: "accepted", updatedAt: request.acceptedAt };
    const write = (value: object, state = "accepted", sessionId = proof.target.sessionId) => db.prepare("INSERT OR REPLACE INTO h021_gateway_requests VALUES (?,?,?,?)").run(request.id, sessionId, state, JSON.stringify(value));
    write(record); assert.doesNotThrow(() => verifyRequestBinding(db, proof));
    for (const mutation of [
      { ...record, updatedAt: undefined }, { ...record, updatedAt: "2026-09-29T23:31:11.000Z" },
      { ...record, id: randomUUID() }, { ...record, sessionId: randomUUID() },
      { ...record, lane: "other-lane" }, { ...record, state: "settled" },
    ]) { write(mutation); assert.throws(() => verifyRequestBinding(db, proof), /accepted request time\/lane binding changed/); }
    write(record, "uncertain"); assert.throws(() => verifyRequestBinding(db, proof), /original accepted request/);
    write(record, "accepted", randomUUID()); assert.throws(() => verifyRequestBinding(db, proof), /original accepted request/);
    db.exec("DELETE FROM h021_gateway_requests"); assert.throws(() => verifyRequestBinding(db, proof), /original accepted request/);
  } finally { db.close(); }
});

test("protected file reader refuses app-user-controlled ancestry and symlink delegation", () => {
  const dir = realpathSync(mkdtempSync(path.join(os.tmpdir(), "h036-proof-")));
  try {
    const filePath = path.join(dir, "proof.json"); writeFileSync(filePath, "{}", { mode: 0o600 });
    const link = path.join(dir, "proof-link.json"); symlinkSync(filePath, link);
    assert.throws(() => readRootProtected(link), /symlink in protected path/);
    // On app-user test runs this is an actual app-owned proof. On root-run CI,
    // the world-writable temporary ancestry independently remains forbidden.
    assert.equal(lstatSync(filePath).uid, process.getuid!());
    assert.throws(() => readRootProtected(filePath), /unprotected evidence directory|root-owned protected/);
    chmodSync(dir, 0o777);
    assert.throws(() => readRootProtected(filePath), /unprotected evidence directory/);
  } finally { rmSync(dir, { recursive: true, force: true }); }
});
