import assert from "node:assert/strict";
import test, { type TestContext } from "node:test";
import { mkdtempSync, readFileSync, readdirSync, rmSync, statSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { DatabaseSync } from "node:sqlite";
import { Store } from "../src/store.js";
import { GatewayOwnershipLedger } from "../src/gateway-ownership.js";
import { recoverySnapshot } from "../src/recovery-snapshot.js";
import { readOnlyPreflight, runRecovery } from "../src/interrupted-recovery.js";
import { fixtureProof } from "./recovery-proof-fixture.js";

function fixture(t: TestContext) {
  const dir = mkdtempSync(join(tmpdir(), "h036-preflight-"));
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  const proof = fixtureProof();
  proof.database.path = join(dir, "harness.sqlite");
  const store = new Store(proof.database.path);
  const session = store.createSession(proof.target.workspaceId, "codex");
  const unrelated = store.createSession(undefined, "codex");
  const run = store.createRun(session, "message", "retained original prompt", []);
  proof.target.sessionId = session.id;
  proof.target.runId = run.id;
  for (const item of [session, unrelated]) {
    store.setNative(item.id, item.id === session.id ? proof.target.threadId : "unrelated-native-thread", "codex");
    store.setNativeState(item.id, "codex", {
      activeTurnId: item.id === session.id ? proof.target.turnId : "unrelated-turn", eventCursor: 17, ownership: "uncertain",
    });
    store.quarantine(item.workspaceId, "restart_during_run");
    store.setStatus(item.id, "interrupted");
    store.emit(item.id, "error", { code: "interrupted", message: "retained restart evidence" });
  }
  store.updateRun(run.id, "interrupted");
  new GatewayOwnershipLedger(store.db);
  const accepted = proof.provider.requests[0]!;
  store.db.prepare("INSERT INTO h021_gateway_requests VALUES(?,?,?,?)").run(accepted.id, session.id, "accepted", JSON.stringify({
    id: accepted.id, sessionId: session.id, state: "accepted", lane: accepted.lane,
    updatedAt: accepted.acceptedAt, accounting: { inputTokens: 92607, reservedOutputTokens: 65536 },
  }));
  // Any accidental normal Store startup would mutate this unrelated uncertain
  // owner and hit these sentinels. Preflight must only read the snapshot.
  store.db.exec(`CREATE TRIGGER reject_preflight_restart_event BEFORE INSERT ON events
    BEGIN SELECT RAISE(ABORT,'unexpected Store startup event write'); END;
    CREATE TRIGGER reject_preflight_owner_write BEFORE UPDATE ON h021_session_engines
    BEGIN SELECT RAISE(ABORT,'unexpected Store startup owner write'); END;`);
  proof.database.snapshotSha256 = recoverySnapshot(store.db, proof.target).sha256;
  const priorUnrelated = JSON.stringify({
    owner: store.db.prepare("SELECT * FROM h021_session_engines WHERE session_id=?").get(unrelated.id),
    events: store.db.prepare("SELECT * FROM events WHERE session_id=? ORDER BY id").all(unrelated.id),
    quarantine: store.db.prepare("SELECT * FROM quarantined_workspaces WHERE id=?").get(unrelated.workspaceId),
  });
  store.close();
  const st = statSync(proof.database.path);
  Object.assign(proof.database, { uid: st.uid, dev: st.dev, ino: st.ino });
  return { dir, proof, unrelated, priorUnrelated };
}

function bytes(directory: string) {
  return new Map(readdirSync(directory).sort().map(name => [name, readFileSync(join(directory, name))]));
}
function assertUnchanged(directory: string, before: Map<string, Buffer>) {
  assert.deepEqual(readdirSync(directory).sort(), [...before.keys()]);
  for (const [name, contents] of before) assert.deepEqual(readFileSync(join(directory, name)), contents, `${name} changed`);
}

test("actual CLI preflight of closed WAL database creates no source sidecars or startup writes, even on refusal", t => {
  const f = fixture(t);
  assert.deepEqual(readdirSync(f.dir), ["harness.sqlite"]);
  const before = bytes(f.dir);
  assert.deepEqual(readOnlyPreflight(f.proof), { snapshotSha256: f.proof.database.snapshotSha256 });
  assertUnchanged(f.dir, before);
  const wrongHash = structuredClone(f.proof);
  wrongHash.database.snapshotSha256 = "f".repeat(64);
  assert.throws(() => readOnlyPreflight(wrongHash), /snapshot changed/);
  assertUnchanged(f.dir, before);
  const wrongTurn = structuredClone(f.proof);
  wrongTurn.target.turnId = "foreign-turn";
  assert.throws(() => readOnlyPreflight(wrongTurn), /identity\/state mismatch/);
  assertUnchanged(f.dir, before);
  // Read the original only after the byte/no-sidecar assertions; this test's
  // SQLite connection itself may now create WAL shared-memory files.
  const db = new DatabaseSync(f.proof.database.path, { readOnly: true });
  try {
    assert.equal(JSON.stringify({
      owner: db.prepare("SELECT * FROM h021_session_engines WHERE session_id=?").get(f.unrelated.id),
      events: db.prepare("SELECT * FROM events WHERE session_id=? ORDER BY id").all(f.unrelated.id),
      quarantine: db.prepare("SELECT * FROM quarantined_workspaces WHERE id=?").get(f.unrelated.workspaceId),
    }), f.priorUnrelated);
  } finally { db.close(); }
});

test("actual preflight includes uncheckpointed WAL frames and rejects stale proof without changing source DB/WAL/SHM", t => {
  const f = fixture(t);
  const db = new DatabaseSync(f.proof.database.path);
  t.after(() => db.close());
  db.exec("PRAGMA wal_autocheckpoint=0");
  const baseBytes = readFileSync(f.proof.database.path);
  const stale = structuredClone(f.proof);
  db.prepare("UPDATE sessions SET title=? WHERE id=?").run("only present in uncheckpointed WAL", f.unrelated.id);
  assert.deepEqual(readFileSync(f.proof.database.path), baseBytes);
  assert.ok(statSync(`${f.proof.database.path}-wal`).size > 32);
  f.proof.database.snapshotSha256 = recoverySnapshot(db, f.proof.target).sha256;
  assert.notEqual(f.proof.database.snapshotSha256, stale.database.snapshotSha256);
  const before = bytes(f.dir);
  assert.deepEqual(readOnlyPreflight(f.proof), { snapshotSha256: f.proof.database.snapshotSha256 });
  assertUnchanged(f.dir, before);
  assert.throws(() => readOnlyPreflight(stale), /snapshot changed/);
  assertUnchanged(f.dir, before);
  assert.equal(db.prepare("SELECT title FROM sessions WHERE id=?").get(f.unrelated.id)!.title, "only present in uncheckpointed WAL");
});

test("preflight rejects accepted request timestamp/lane drift and never calls an operator boundary", t => {
  const f = fixture(t), before = bytes(f.dir);
  for (const change of ["time", "lane", "request"] as const) {
    const proof = structuredClone(f.proof);
    if (change === "time") proof.provider.requests[0]!.acceptedAt = "2026-09-29T23:31:11.733Z";
    if (change === "lane") proof.provider.requests[0]!.lane = "other-lane";
    if (change === "request") proof.provider.requests[0]!.id = "foreign-request";
    assert.throws(() => readOnlyPreflight(proof), /request.*(required|binding changed)/);
    assertUnchanged(f.dir, before);
  }
});

test("CLI rejects generic reset, clear, force and malformed arguments before reading files or host state", () => {
  for (const args of [[], ["reset"], ["clear"], ["force"], ["apply"], ["reset", "--proof", "/missing", "--session", "any"], ["preflight", "--proof", "/missing", "--all", "any"]])
    assert.throws(() => runRecovery(args), /Usage: interrupted-recovery/);
});
