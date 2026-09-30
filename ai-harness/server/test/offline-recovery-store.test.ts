import assert from "node:assert/strict";
import test, { type TestContext } from "node:test";
import { mkdtempSync, mkdirSync, readFileSync, readdirSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { DatabaseSync } from "node:sqlite";
import { PassThrough } from "node:stream";
import { Store } from "../src/store.js";
import { recoverySnapshot, recoveryDatabaseSha256, type RecoveryTarget } from "../src/recovery-snapshot.js";
import { GatewayOwnership, GatewayOwnershipLedger } from "../src/gateway-ownership.js";
import { createApp } from "../src/app.js";
import { codexDeployment } from "../src/codex-deployment.js";
import { CODEX_PIN, type CodexRuntime } from "../src/codex-engine.js";
import { CODEX_MODEL_POLICY } from "../src/codex-launcher.js";

function fixture(t: TestContext) {
  const dir = mkdtempSync(join(tmpdir(), "h036-offline-"));
  const databasePath = join(dir, "harness.sqlite");
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  const setup = new Store(databasePath);
  const targetSession = setup.createSession(undefined, "codex", { engineVersion: CODEX_PIN.version, modelPolicyVersion: CODEX_MODEL_POLICY });
  const unrelated = setup.createSession(undefined, "codex");
  const sessions = [targetSession, unrelated];
  const ownership = new GatewayOwnership(new GatewayOwnershipLedger(setup.db).options());
  let target!: RecoveryTarget;
  for (const [i, session] of sessions.entries()) {
    mkdirSync(join(dir, "workspaces", session.workspaceId), { recursive: true });
    const run = setup.createRun(session, "message", `original-private-prompt-${i}`, []);
    setup.updateRun(run.id, "running");
    setup.addMessage(session.id, "user", `retained-history-${i}`, run.id);
    setup.setNative(session.id, `thread-${i}`, "codex");
    setup.setNativeState(session.id, "codex", { activeTurnId: `turn-${i}`, eventCursor: 7 + i, ownership: "active" });
    const request = ownership.begin(session.id);
    ownership.transition(request, "accepted", "qwen3.8-27b-gpu0");
    ownership.account(request, { inputTokens: 92607, reservedOutputTokens: 65536 });
    if (i === 0) target = { sessionId: session.id, runId: run.id, workspaceId: session.workspaceId, threadId: "thread-0", turnId: "turn-0", requestIds: [request.id] };
  }
  setup.quarantine("historical-extra-workspace", "retained unrelated reason");
  writeFileSync(join(dir, "retained-power.txt"), "immutable original artifact 0.825 W");
  setup.close();
  // Actual normal startup records interrupted/uncertain state; no invented success.
  new Store(databasePath).close();
  const store = new Store(databasePath, undefined, { mode: "offline-recovery" });
  t.after(() => store.close());
  const input = () => ({ target, snapshotSha256: recoverySnapshot(store.db, target).sha256,
    recoveryId: "fixture-recovery", proofSha256: "a".repeat(64), evidence: { sourceFixtureOnly: "protected proof validated by CLI in separate tests" } });
  const unrelatedRows = () => JSON.stringify({
    session: store.db.prepare("SELECT * FROM sessions WHERE id=?").get(unrelated.id),
    runs: store.db.prepare("SELECT * FROM runs WHERE session_id=?").all(unrelated.id),
    events: store.db.prepare("SELECT * FROM events WHERE session_id=? ORDER BY id").all(unrelated.id),
    owner: store.db.prepare("SELECT * FROM h021_session_engines WHERE session_id=?").get(unrelated.id),
    quarantine: store.db.prepare("SELECT * FROM quarantined_workspaces WHERE id!=? ORDER BY id").all(target.workspaceId),
    request: store.db.prepare("SELECT * FROM h021_gateway_requests WHERE session_id=?").all(unrelated.id),
  });
  return { dir, databasePath, store, target, unrelated, input, unrelatedRows };
}

test("read-only snapshot and offline Store open preserve every logical row and DB bytes; default startup still records uncertainty", t => {
  const f = fixture(t);
  const before = recoveryDatabaseSha256(f.store.db);
  const files = new Map(readdirSync(f.dir).filter(name => name !== "workspaces").map(name => [name, readFileSync(join(f.dir, name))]));
  const db = new DatabaseSync(f.databasePath, { readOnly: true });
  db.exec("BEGIN");
  assert.equal(recoverySnapshot(db, f.target).sha256, before);
  assert.throws(() => recoverySnapshot(db, { ...f.target, turnId: "wrong" }), /mismatch/);
  db.exec("ROLLBACK"); db.close();
  new Store(f.databasePath, undefined, { mode: "offline-recovery" }).close();
  assert.equal(recoveryDatabaseSha256(f.store.db), before);
  for (const [name, bytes] of files) assert.deepEqual(readFileSync(join(f.dir, name)), bytes);
  const count = f.store.allEvents(f.unrelated.id).length;
  new Store(f.databasePath).close();
  assert.ok(f.store.allEvents(f.unrelated.id).length > count);
  assert.equal(f.store.getSession(f.unrelated.id).nativeState.ownership, "uncertain");
  assert.equal(f.store.isQuarantined(f.unrelated.workspaceId), true);
});

test("atomic release changes only target disposition, preserves original requests/usage/run/history/artifact and unrelated uncertainty", t => {
  const f = fixture(t);
  const unrelated = f.unrelatedRows();
  const original = JSON.stringify({
    runs: f.store.db.prepare("SELECT * FROM runs").all(), messages: f.store.db.prepare("SELECT * FROM messages").all(),
    files: f.store.db.prepare("SELECT * FROM files").all(), requests: f.store.db.prepare("SELECT * FROM h021_gateway_requests").all(),
    sessions: f.store.db.prepare("SELECT * FROM sessions").all(),
  });
  const oldEvents = f.store.allEvents(f.target.sessionId);
  const artifact = readFileSync(join(f.dir, "retained-power.txt"));
  f.store.events.on(f.target.sessionId, () => { throw Error("subscriber failure after commit"); });
  const record = f.store.applyPhysicalRelease(f.input());
  assert.equal(record.outcome, "interrupted_unknown");
  assert.equal(record.priorOwnership.active_turn_id, f.target.turnId);
  assert.deepEqual(f.store.getSession(f.target.sessionId).nativeState, { ownership: "idle", activeTurnId: null, eventCursor: 7 });
  assert.equal(f.store.getSession(f.target.sessionId).nativeSessionId, f.target.threadId);
  assert.equal(f.store.isQuarantined(f.target.workspaceId), false);
  assert.equal(f.unrelatedRows(), unrelated);
  assert.equal(JSON.stringify({
    runs: f.store.db.prepare("SELECT * FROM runs").all(), messages: f.store.db.prepare("SELECT * FROM messages").all(),
    files: f.store.db.prepare("SELECT * FROM files").all(), requests: f.store.db.prepare("SELECT * FROM h021_gateway_requests").all(),
    sessions: f.store.db.prepare("SELECT * FROM sessions").all(),
  }), original);
  const events = f.store.allEvents(f.target.sessionId);
  assert.deepEqual(events.slice(0, oldEvents.length), oldEvents);
  assert.deepEqual(events.slice(oldEvents.length).map(e => [e.type, e.data.outcome]), [["progress", "interrupted_unknown"], ["done", "interrupted_unknown"]]);
  assert.deepEqual(readFileSync(join(f.dir, "retained-power.txt")), artifact);
});

test("changed unrelated snapshot fails before any mutation; duplicate refuses without duplicate audit", t => {
  const f = fixture(t), input = f.input();
  f.store.setTitle(f.unrelated.id, "new unrelated title");
  const before = recoveryDatabaseSha256(f.store.db);
  assert.throws(() => f.store.applyPhysicalRelease(input), /snapshot changed/);
  assert.equal(recoveryDatabaseSha256(f.store.db), before);
  const fresh = f.input();
  f.store.applyPhysicalRelease(fresh);
  const after = recoveryDatabaseSha256(f.store.db);
  assert.throws(() => f.store.applyPhysicalRelease(fresh), /already recorded/);
  assert.equal(recoveryDatabaseSha256(f.store.db), after);
});

test("event write failure rolls back owner, quarantine, disposition tables and all events", t => {
  const f = fixture(t);
  f.store.db.exec("CREATE TRIGGER reject_recovery_done BEFORE INSERT ON events WHEN NEW.type='done' BEGIN SELECT RAISE(ABORT,'fixture write failure'); END;");
  const input = f.input(), before = recoveryDatabaseSha256(f.store.db);
  assert.throws(() => f.store.applyPhysicalRelease(input), /fixture write failure/);
  assert.equal(recoveryDatabaseSha256(f.store.db), before);
  assert.equal(f.store.isQuarantined(f.target.workspaceId), true);
  assert.equal(f.store.getSession(f.target.sessionId).nativeState.ownership, "uncertain");
  assert.equal(f.store.db.prepare("SELECT name FROM sqlite_schema WHERE name='h036_physical_releases'").get(), undefined);
});

test("exact request identities, replacement run, pending images and target identity all fail closed", t => {
  const f = fixture(t), before = recoveryDatabaseSha256(f.store.db);
  for (const target of [{ ...f.target, requestIds: [] }, { ...f.target, requestIds: ["another-request"] }, { ...f.target, workspaceId: "different-workspace" }, { ...f.target, threadId: "different-thread" }])
    assert.throws(() => recoverySnapshot(f.store.db, target));
  assert.equal(recoveryDatabaseSha256(f.store.db), before);
  f.store.db.exec("BEGIN");
  f.store.db.prepare("UPDATE runs SET status='queued' WHERE session_id=?").run(f.target.sessionId);
  assert.throws(() => recoverySnapshot(f.store.db, f.target), /mismatch/);
  f.store.db.exec("ROLLBACK");
  f.store.db.exec("CREATE TABLE h003_image_jobs(id TEXT PRIMARY KEY,session_id TEXT,request_id TEXT,data TEXT)");
  const imageJob = { id: "image", sessionId: f.target.sessionId, requestId: "image-request", state: "running" };
  f.store.db.prepare("INSERT INTO h003_image_jobs VALUES(?,?,?,?)").run("image", f.target.sessionId, "image-request", JSON.stringify({ job: imageJob }));
  assert.throws(() => recoverySnapshot(f.store.db, f.target), /image work/);
  f.store.db.prepare("UPDATE h003_image_jobs SET data=?").run(JSON.stringify({ job: { ...imageJob, state: "completed" } }));
  assert.doesNotThrow(() => recoverySnapshot(f.store.db, f.target));
  f.store.db.prepare("UPDATE h003_image_jobs SET data=?").run(JSON.stringify({ state: "completed" }));
  assert.throws(() => recoverySnapshot(f.store.db, f.target), /image work/);
});

test("ledger restart recognizes committed physical release, preserves unknown accepted bytes, and keeps unrelated requests blocked", t => {
  const f = fixture(t);
  const ledger = new GatewayOwnershipLedger(f.store.db);
  assert.equal(new GatewayOwnership(ledger.options()).confirm({ sessionId: f.target.sessionId }), false);
  f.store.applyPhysicalRelease(f.input());
  const restarted = new GatewayOwnership(ledger.options());
  assert.equal(restarted.confirm({ sessionId: f.target.sessionId }), true);
  assert.equal(restarted.confirm({ sessionId: f.unrelated.id }), false);
  assert.equal(f.store.db.prepare("SELECT state FROM h021_gateway_requests WHERE id=?").get(f.target.requestIds[0]!)!.state, "accepted");
  const request = restarted.begin(f.target.sessionId);
  assert.notEqual(request.id, f.target.requestIds[0]);
  assert.equal(restarted.confirm({ sessionId: f.target.sessionId }), false);
  restarted.transition(request, "settled");
  assert.equal(restarted.confirm({ sessionId: f.target.sessionId }), true);
  assert.throws(() => ledger.options().onRequestState({ id: f.target.requestIds[0]!, sessionId: f.target.sessionId, state: "settled", updatedAt: new Date().toISOString() }), /cannot be rewritten/);
});

test("corrupt release map, changed original request bytes and missing audit cannot release a ledger owner", t => {
  const f = fixture(t);
  f.store.applyPhysicalRelease(f.input());
  for (const sql of ["UPDATE h036_released_requests SET original_record='{}'", "UPDATE h021_gateway_requests SET record=json_set(record,'$.accounting.inputTokens',1)", "UPDATE sessions SET native_session_id='foreign-thread'", "DELETE FROM events WHERE type='done'"]) {
    f.store.db.exec("BEGIN"); f.store.db.exec(sql);
    assert.equal(new GatewayOwnership(new GatewayOwnershipLedger(f.store.db).options()).confirm({ sessionId: f.target.sessionId }), false);
    f.store.db.exec("ROLLBACK");
  }
  f.store.db.exec("BEGIN");
  f.store.db.prepare("UPDATE h021_gateway_requests SET state='uncertain' WHERE id=?").run(f.target.requestIds[0]!);
  assert.throws(() => new GatewayOwnershipLedger(f.store.db).options(), /row binding/);
  f.store.db.exec("ROLLBACK");
});

test("ledger loading never parses or rewrites unrelated retained settled records", t => {
  const f = fixture(t);
  const historical = { id: "historical-settled", session_id: "historical-session", state: "settled", record: "opaque retained legacy record, intentionally not JSON" };
  f.store.db.prepare("INSERT INTO h021_gateway_requests VALUES(?,?,?,?)")
    .run(historical.id, historical.session_id, historical.state, historical.record);
  f.store.applyPhysicalRelease(f.input());
  const restarted = new GatewayOwnership(new GatewayOwnershipLedger(f.store.db).options());
  assert.equal(restarted.confirm({ sessionId: f.target.sessionId }), true);
  assert.equal(restarted.confirm({ sessionId: f.unrelated.id }), false);
  assert.deepEqual({ ...f.store.db.prepare("SELECT * FROM h021_gateway_requests WHERE id=?").get(historical.id) }, historical);
});

test("ordinary new explicit turn is blocked before valid release and resumes exact retained native history once, without old request replay", async t => {
  const f = fixture(t);
  let launches = 0;
  const methods: { method: string; params?: { threadId?: string; input?: unknown } }[] = [];
  const runtime: CodexRuntime = {
    pin: CODEX_PIN, protocolQualified: true, modelPolicyVersion: CODEX_MODEL_POLICY,
    model: "qwen3.8-27b", provider: "sova", contextLimit: 480000, gatewayUrl: "http://10.0.2.2:8081/v1",
    async launchRootless(input) {
      launches++;
      const stdin = new PassThrough(), stdout = new PassThrough();
      const emit = (value: unknown) => stdout.write(JSON.stringify(value) + "\n");
      stdin.on("data", data => {
        const r = JSON.parse(data.toString()); methods.push(r);
        if (r.method === "initialize") emit({ id: r.id, result: { userAgent: `codex/${CODEX_PIN.version}`, codexHome: input.codexHome, platformOs: "linux", platformFamily: "unix" } });
        if (r.method === "thread/resume") emit({ id: r.id, result: { thread: { id: f.target.threadId }, model: "qwen3.8-27b", modelProvider: "sova", cwd: input.workspace, approvalPolicy: "never" } });
        if (r.method === "turn/start") {
          emit({ id: r.id, result: { turn: { id: "new-explicit-turn" } } });
          emit({ method: "turn/completed", params: { threadId: f.target.threadId, turn: { id: "new-explicit-turn", status: "completed" } } });
        }
      });
      return { stdin, stdout, exited: new Promise<void>(() => {}), async terminateAndConfirm() { return true; } };
    },
    revokeGatewaySession() {}, async confirmGatewaySettlement() { return true; },
  };
  const app = await createApp({ dataDir: f.dir, allowedOrigins: ["http://localhost"], launcher: "/never",
    gatewayUrl: "http://fixture.invalid/v1", engineFactory: () => { throw Error("Wrong engine"); },
    issueToken: () => "fixture-token", revokeToken() {}, ...codexDeployment({ enablePreview: true, runtime }) });
  t.after(() => app.app.close());
  assert.throws(() => app.broker.enqueue(f.target.sessionId, "message", "new explicit followup"), /operator settlement/);
  assert.equal(launches, 0);
  // Fixtures invoke Store directly; production CLI requires stopped-app proof.
  f.store.applyPhysicalRelease(f.input());
  assert.equal(launches, 0);
  const next = app.broker.enqueue(f.target.sessionId, "message", "new explicit followup");
  await app.broker.idle();
  assert.equal(launches, 1, JSON.stringify(app.store.allEvents(f.target.sessionId).filter(e => e.type === "error")));
  assert.deepEqual(methods.filter(r => r.method.startsWith("thread/")).map(r => [r.method, r.params?.threadId]), [["thread/resume", f.target.threadId]]);
  assert.equal(methods.filter(r => r.method === "turn/start").length, 1);
  assert.equal(JSON.stringify(methods).includes("original-private-prompt"), false);
  assert.notEqual(next, f.target.runId);
  assert.equal(app.store.runSnapshot(f.target.runId).status, "interrupted");
  assert.equal(app.store.getSession(f.target.sessionId).nativeSessionId, f.target.threadId);
  assert.equal(app.store.messages(f.target.sessionId).filter(m => m.role === "user").length, 2);
});
