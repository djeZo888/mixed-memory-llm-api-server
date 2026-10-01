/** Actual production Store startup repair, checked by the read-only Python verifier.
 * Synthetic local source fixtures only: no carrier, native launch or authority use.
 */
import test from "node:test";
import assert from "node:assert/strict";
import { DatabaseSync } from "node:sqlite";
import { spawnSync } from "node:child_process";
import { createHash, randomUUID } from "node:crypto";
import { chmodSync, copyFileSync, lstatSync, mkdirSync, mkdtempSync, readFileSync, realpathSync, writeFileSync } from "node:fs";
import { hostname } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { Store } from "../src/store.js";
import type { AcceptedStateDraft } from "../src/session-memory.js";

const serverRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = resolve(serverRoot, "../..");
const outputRoot = realpathSync(resolve(repoRoot, "../output"));
const adminRoot = resolve(repoRoot, "ai-harness/deploy/admin");
const privateChat = "H042_PRIVATE_CHAT_SENTINEL_4.8µA_do_NOT_replay";
const privatePrompt = "H042_PRIVATE_PROMPT_SENTINEL_preserve_480000";
const digest = (value: string | Uint8Array) => createHash("sha256").update(value).digest("hex");
type SQLRow = Record<string, string | number | bigint | null | Uint8Array>;
type SnapshotRow = { rowid: number; fields: Record<string, string>; [key: string]: unknown };
type SnapshotTable = { columns: string[]; primaryKey: string[]; order: string[]; rows: Record<string, SnapshotRow> };
type RetainedSnapshot = Record<string, SnapshotTable>;
type Mutation = { name: string; change: (db: DatabaseSync) => void };

// Importing this module does not create a carrier. Only the two pure, offline
// retained-record functions are invoked; Python bytecode remains disabled.
const pythonProgram = String.raw`
import json,os,sys
sys.path.insert(0,sys.argv[1])
from qualification_carrier_host import retained_record_snapshot,verify_retained_records
from qualification_carrier import CarrierError
def save(path,value):
 with open(path,'x',encoding='utf-8') as stream:
  os.fchmod(stream.fileno(),0o600)
  json.dump(value,stream,sort_keys=True,separators=(',',':'))
mode=sys.argv[2]
if mode=='snapshot':
 value=retained_record_snapshot(sys.argv[3]);save(sys.argv[4],value)
 print(json.dumps({'mode':mode,'tables':len(value)}))
elif mode=='verify':
 with open(sys.argv[3]) as stream:before=json.load(stream)
 with open(sys.argv[4]) as stream:after=json.load(stream)
 delta=verify_retained_records(before,after);save(sys.argv[5],delta)
 print(json.dumps({'mode':mode,'accepted':True,'deltaCount':len(delta)}))
elif mode=='reject-copies':
 with open(sys.argv[3]) as stream:before=json.load(stream)
 with open(sys.argv[4]) as stream:cases=json.load(stream)
 result=[]
 for case in cases:
  try:
   verify_retained_records(before,retained_record_snapshot(case['database']))
  except CarrierError as error:
   result.append({'name':case['name'],'rejected':True,'error':str(error)})
  else:
   result.append({'name':case['name'],'rejected':False})
 save(sys.argv[5],result)
 print(json.dumps({'mode':mode,'cases':len(result),'rejected':sum(r['rejected'] for r in result)}))
else:raise RuntimeError('unknown bounded test operation')
`;

function protectedStore(database: string) {
  const prior = process.umask(0o077);
  try {
    const store = new Store(database);
    for (const suffix of ["", "-wal", "-shm"]) {
      try { chmodSync(database + suffix, 0o600); } catch (error) {
        if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
      }
    }
    return store;
  } finally { process.umask(prior); }
}

function runPython(root: string, name: string, args: string[]) {
  const argv = ["python3", "-B", "-c", pythonProgram, adminRoot, ...args];
  const startedAt = new Date().toISOString();
  const result = spawnSync(argv[0], argv.slice(1), {
    cwd: serverRoot, encoding: "utf8", timeout: 10000,
    env: { ...process.env, PYTHONDONTWRITEBYTECODE: "1" }, maxBuffer: 4 * 1024 * 1024,
  });
  const finishedAt = new Date().toISOString();
  const log = `${result.stdout ?? ""}${result.stderr ?? ""}${result.error ? String(result.error) + "\n" : ""}`;
  writeFileSync(join(root, `${name}.log`), log, { mode: 0o600, flag: "wx" });
  writeFileSync(join(root, `${name}.receipt.json`), JSON.stringify({
    host: hostname(), cwd: serverRoot, argv, startedAt, finishedAt,
    exit: result.status, signal: result.signal, logSHA256: digest(log),
  }, null, 2) + "\n", { mode: 0o600, flag: "wx" });
  assert.equal(Number.isInteger(result.status), true, `${name}: no actual child integer exit`);
  assert.equal(result.status, 0, `${name}: ${log}`);
}

function rows(db: DatabaseSync, table: string): SQLRow[] {
  return db.prepare(`SELECT rowid AS retained_rowid,* FROM "${table}" ORDER BY rowid`).all() as SQLRow[];
}

function draft(original: { id: string; sha256: string | null }): AcceptedStateDraft {
  return {
    objective: "Retain originals and pinned 480000/400000/65536; source only",
    constraints: [{ id: "pins", text: "Do not change runtime pins", negated: true, permissionBoundary: true, sources: [{ id: original.id, sha256: original.sha256! }] }],
    decisions: [{ id: "route", text: "Preserve original route", status: "current", sources: [] }],
    pending: [{ id: "native", text: "Native carrier remains NOT_TESTED", owner: "root", status: "blocked", sources: [] }],
    checks: [{ id: "source", claim: "unknown", sources: [] }],
  };
}

function richFixture(store: Store, root: string) {
  const codex = () => store.createSession(undefined, "codex", { engineVersion: "0.158.0", modelPolicyVersion: "064c6b8c737f5b41d171fdda80bd9ef10ad06eb3" });
  const queued = codex(), running = codex(), cancelling = codex();
  const ownerOnly = codex(), uncertainOnly = codex(), idle = codex();
  const minimax = store.createSession(undefined, "minimax", { engineVersion: "retained-minimax", modelPolicyVersion: "retained-policy" });
  const sessions = [queued, running, cancelling, ownerOnly, uncertainOnly, idle, minimax];
  for (const [index, session] of sessions.entries()) {
    store.setTitle(session.id, `Retained source fixture ${index}`);
    store.setNative(session.id, `original-native-thread-${index}`, session.engineKind);
    const context = {
      used: 12345 + index, limit: 480000 as const, estimated: false, stale: session.id === cancelling.id,
      source: "native", updatedAt: "2026-10-01T18:00:00.000Z",
      retainedExtension: { permissions: ["source_only"], nested: { value: privateChat, zero: 0, empty: null } },
    };
    store.setContext(session.id, context);
    store.emit(session.id, "progress", { label: "Prior immutable source event", retained: privateChat });
  }
  const attachments = [0, 1].map(index => store.saveFile({
    id: randomUUID(), sessionId: queued.id, kind: "attachment", path: `attachments/owned-${index}.txt`,
    name: `owned-${index}.txt`, mimeType: "text/plain", size: Buffer.byteLength(privateChat), sourcePath: join(root, `source-${index}.txt`),
  }));
  for (const [index, attachment] of attachments.entries()) {
    writeFileSync(join(root, `source-${index}.txt`), privateChat, { mode: 0o600, flag: "wx" });
    store.memory.retain(queued.id, "file", attachment.id, Buffer.from(privateChat));
  }
  const q = store.createRun(queued, "message", privatePrompt, attachments.map(file => file.id));
  const q2 = store.createRun(queued, "handoff", privatePrompt + " second queued", [], undefined, "minimax");
  const r = store.createRun(running, "message", privatePrompt + " running", []);
  const c = store.createRun(cancelling, "compact", privatePrompt + " cancelling", [], "retained-compaction-action");
  const done = store.createRun(idle, "message", "completed control", []);
  const failed = store.createRun(minimax, "message", "failed control", []);
  const userMessage = store.addMessage(queued.id, "user", privateChat, q.id, attachments.map(file => file.id));
  store.addMessage(queued.id, "assistant", privateChat + " older final", q.id, [], randomUUID(), { phase: "final", nativeMessageId: "native-old-message", nativeTurnId: "native-old-turn" });
  const finalMessage = store.addMessage(queued.id, "assistant", privateChat + " last final", q.id, [], randomUUID(), { phase: "final", nativeMessageId: "native-last-message", nativeTurnId: "native-last-turn" });
  const artifacts = [0, 1].map(index => store.saveFile({
    id: randomUUID(), sessionId: queued.id, kind: "artifact", path: `artifacts/result-${index}.txt`,
    name: `result-${index}.txt`, mimeType: "text/plain", size: 11 + index, runId: q.id, messageId: finalMessage.id,
  }));
  store.setSubagents(queued.id, q.id, { known: true, active: 1, completed: 2, failed: 1, cancelled: 0, updatedAt: "2026-10-01T18:01:00.000Z" });
  const original = store.memory.retain(queued.id, "message", userMessage.id, Buffer.from(privateChat));
  const accepted1 = store.memory.acceptHuman(queued.id, store.memory.propose(queued.id, draft(original)).id, null);
  const accepted2 = store.memory.acceptHuman(queued.id, store.memory.propose(queued.id, draft(original)).id, accepted1.id);
  store.memory.bridge(queued.id).bindCatalog("original-native-thread-0", digest("original-catalog"));
  store.memory.bridge(queued.id).recordConsumption({ threadId: "original-native-thread-0", turnId: "retained-turn", callId: "retained-call", tool: "original_lookup", responseSha256: digest(privateChat), success: true });
  const prepared = store.checkpoints.prepare(queued.id, q.id, "message", "original-native-thread-0");
  const secondPrepared = store.checkpoints.prepare(queued.id, q2.id, "handoff", "original-native-thread-0");
  const replacement = store.checkpoints.prepare(running.id, r.id, "message", "original-native-thread-1");
  store.checkpoints.observeCompaction(running.id, r.id, "retained-replacement", "start");
  // This real production API creates identical keyless prior rows. Their rowids
  // and multiplicity must survive; a content-hash identity would collapse them.
  store.checkpoints.observeCompaction(running.id, r.id, "retained-replacement", "start");
  store.checkpoints.observeCompaction(running.id, r.id, "retained-replacement", "completed");
  const cancellingPrepared = store.checkpoints.prepare(cancelling.id, c.id, "compact", "original-native-thread-2");
  const settled = store.checkpoints.prepare(idle.id, done.id, "message", "original-native-thread-5");
  store.checkpoints.finish(idle.id, done.id, "completed");
  const alreadyRecovery = store.checkpoints.prepare(minimax.id, failed.id, "message", "original-native-thread-6");
  store.checkpoints.finish(minimax.id, failed.id, "failed");
  store.checkpoints.recordNativeEvidence(queued.id, q.id, "native_operation", { retained: privateChat, nativeThreadId: "original-native-thread-0", sequence: 1 });
  store.checkpoints.recordNativeEvidence(queued.id, q.id, "native_operation", { retained: privateChat, nativeThreadId: "original-native-thread-0", sequence: 1 });
  store.checkpoints.recordNativeEvidence(queued.id, q.id, "native_operation", { retained: privateChat, nativeThreadId: "original-native-thread-0", sequence: 2 });
  store.updateRun(r.id, "running");
  store.updateRun(c.id, "cancelling");
  store.updateRun(done.id, "completed");
  store.updateRun(failed.id, "failed");
  store.setStatus(queued.id, "queued");
  store.setStatus(running.id, "running");
  store.setStatus(cancelling.id, "cancelling");
  for (const session of [queued, running, cancelling, ownerOnly])
    store.setNativeState(session.id, "codex", { ownership: "active", activeTurnId: `original-turn-${session.id}`, eventCursor: 41 });
  store.setNativeState(uncertainOnly.id, "codex", { ownership: "uncertain", activeTurnId: "original-uncertain-turn", eventCursor: 52 });
  store.setNativeState(minimax.id, "minimax", { ownership: "active", activeTurnId: "unrelated-minimax-turn", eventCursor: 63 });
  store.quarantine(queued.workspaceId, "existing_unsettled_owner");
  store.quarantine(minimax.workspaceId, "unrelated_retained_quarantine");
  return { sessions, queued, running, cancelling, ownerOnly, uncertainOnly, idle, minimax,
    q, q2, r, c, done, failed, userMessage, finalMessage, attachments, artifacts, original, accepted1, accepted2,
    prepared, secondPrepared, replacement, cancellingPrepared, settled, alreadyRecovery };
}

test("H042 actual production Store reopen obeys retained verifier and rejects independent tampered databases", async t => {
  const outputInfo = lstatSync(outputRoot);
  assert.equal(outputInfo.isDirectory(), true);
  assert.equal(outputInfo.mode & 0o077, 0);
  const root = realpathSync(mkdtempSync(join(outputRoot, "h042-retained-store-reopen-")));
  chmodSync(root, 0o700);
  const database = join(root, "production.sqlite");
  let store: Store | undefined = protectedStore(database);
  t.after(() => { try { store?.close(); } catch { /* already closed */ } });
  const fixture = richFixture(store, root);
  // Production currently creates nine run columns. An older retained error
  // field is seeded only after all production positional writers have finished;
  // the actual constructor repair must leave this additional evidence exact.
  // No createRun or other positional INSERT is invoked after this point.
  store.db.exec("ALTER TABLE runs ADD COLUMN error TEXT");
  for (const run of [fixture.q, fixture.q2, fixture.r, fixture.c, fixture.done, fixture.failed])
    store.db.prepare("UPDATE runs SET error=? WHERE id=?").run(`${privateChat}: retained error for ${run.id}`, run.id);
  const retainedRunErrors = store.db.prepare("SELECT id,error FROM runs ORDER BY rowid").all();
  const priorSessions = new Map(fixture.sessions.map(session => [session.id, store!.getSession(session.id)]));
  const priorEvents = new Map(fixture.sessions.map(session => [session.id, store!.allEvents(session.id)]));
  const priorTransitions = rows(store.db, "h041_checkpoint_transitions");
  const immutableTables = ["messages", "files", "h041_originals", "h041_memory_versions", "h041_memory_current", "h041_memory_proposals", "h041_native_catalog", "h041_memory_consumption", "h041_checkpoint_native_evidence", "h002_message_meta", "h002_file_refs", "h002_file_names", "h004_file_sources", "h002_subagents", "h024_compaction_actions", "h030_handoff_targets"];
  const immutableRows = new Map(immutableTables.map(table => [table, rows(store!.db, table)]));
  const beforePath = join(root, "before.snapshot.json");
  // Store is still open in WAL mode, so this uses the read-only SQLite/WAL
  // transaction rather than an inaccurate main-file-only snapshot.
  runPython(root, "snapshot-before", ["snapshot", database, beforePath]);
  store.close();
  store = undefined;
  store = protectedStore(database); // The only source of the positive repair.
  const afterPath = join(root, "after.snapshot.json"), deltaPath = join(root, "accepted.delta.json");
  runPython(root, "snapshot-after", ["snapshot", database, afterPath]);
  runPython(root, "verify-actual-reopen", ["verify", beforePath, afterPath, deltaPath]);
  const before = JSON.parse(readFileSync(beforePath, "utf8")) as RetainedSnapshot;
  const after = JSON.parse(readFileSync(afterPath, "utf8")) as RetainedSnapshot;
  const delta = JSON.parse(readFileSync(deltaPath, "utf8")) as { table: string; field: string }[];
  assert.ok(delta.length > 0);
  for (const table of ["runs", "sessions", "h021_session_engines", "quarantined_workspaces", "events", "h041_session_checkpoints", "h041_checkpoint_transitions"])
    assert.ok(delta.some(change => change.table === table), `missing typed repair delta for ${table}`);
  for (const snapshot of [before, after]) {
    assert.equal(JSON.stringify(snapshot).includes(privateChat), false, "snapshot exported private message/context/evidence body");
    assert.equal(JSON.stringify(snapshot).includes(privatePrompt), false, "snapshot exported original prompt");
  }
  const affected = [fixture.queued, fixture.running, fixture.cancelling, fixture.ownerOnly, fixture.uncertainOnly];
  for (const session of affected) {
    const prior = priorSessions.get(session.id)!, next = store.getSession(session.id);
    assert.equal(next.status, "interrupted");
    assert.deepEqual(next.context, { ...prior.context, stale: true });
    assert.deepEqual(next.nativeState, { ...prior.nativeState, ownership: "uncertain" });
    assert.equal(next.engineKind, prior.engineKind);
    assert.equal(next.engineVersion, prior.engineVersion);
    assert.equal(next.modelPolicyVersion, prior.modelPolicyVersion);
    assert.equal(next.nativeSessionId, prior.nativeSessionId);
    assert.equal(store.isQuarantined(next.workspaceId), true);
    assert.equal(store.db.prepare("SELECT reason FROM quarantined_workspaces WHERE id=?").get(next.workspaceId)!.reason, "restart_during_run");
    const events = store.allEvents(session.id), previous = priorEvents.get(session.id)!;
    assert.deepEqual(events.slice(0, previous.length), previous);
    const appended = events.slice(previous.length);
    const runIds = [fixture.q, fixture.q2, fixture.r, fixture.c].filter(run => run.sessionId === session.id).map(run => run.id);
    assert.deepEqual(appended.map(event => event.type), [...runIds.map(() => "run"), "state", "context", "error"]);
    assert.deepEqual(appended.slice(0, runIds.length).map(event => event.runId), runIds);
    assert.deepEqual(appended.slice(-3).map(event => event.runId), [undefined, undefined, undefined]);
    assert.deepEqual(appended.at(-3)!.data, { status: "interrupted" });
    assert.deepEqual(appended.at(-2)!.data, { context: next.context });
    assert.deepEqual(appended.at(-1)!.data, { code: "interrupted", message: "Server restarted; the run was interrupted and was not replayed" });
    for (const [index, event] of appended.entries()) assert.equal(event.id, previous.at(-1)!.id + index + 1);
  }
  for (const session of [fixture.idle, fixture.minimax]) {
    assert.deepEqual(store.getSession(session.id), priorSessions.get(session.id));
    assert.deepEqual(store.allEvents(session.id), priorEvents.get(session.id));
  }
  assert.equal(store.db.prepare("SELECT reason FROM quarantined_workspaces WHERE id=?").get(fixture.minimax.workspaceId)!.reason, "unrelated_retained_quarantine");
  for (const run of [fixture.q, fixture.q2, fixture.r, fixture.c]) assert.equal(store.runSnapshot(run.id).status, "interrupted");
  assert.equal(store.runSnapshot(fixture.done.id).status, "completed");
  assert.equal(store.runSnapshot(fixture.failed.id).status, "failed");
  assert.deepEqual(store.db.prepare("SELECT id,error FROM runs ORDER BY rowid").all(), retainedRunErrors);
  const richRun = store.runSnapshot(fixture.q.id);
  assert.deepEqual(richRun.attachmentIds, fixture.attachments.map(file => file.id));
  assert.deepEqual(richRun.artifactIds, fixture.artifacts.map(file => file.id));
  assert.equal(richRun.finalMessageId, fixture.finalMessage.id);
  assert.equal(richRun.filesZipUrl, `/api/sessions/${fixture.queued.id}/runs/${fixture.q.id}/files.zip`);
  assert.equal(richRun.zipUrl, `/api/sessions/${fixture.queued.id}/runs/${fixture.q.id}/artifacts.zip`);
  assert.equal(richRun.subagents.known, true);
  for (const checkpoint of [fixture.prepared, fixture.secondPrepared, fixture.replacement, fixture.cancellingPrepared]) {
    const body = JSON.parse(String(store.db.prepare("SELECT body FROM h041_session_checkpoints WHERE id=?").get(checkpoint.id)!.body));
    const prior = JSON.parse(String(priorTransitions.filter(row => row.run_id === checkpoint.runId).at(-1)!.body));
    assert.deepEqual(body, { ...prior, status: "recovery_required", outcome: "process_restart" });
  }
  const transitions = rows(store.db, "h041_checkpoint_transitions");
  assert.deepEqual(transitions.slice(0, priorTransitions.length), priorTransitions);
  assert.equal(transitions.length, priorTransitions.length + 4);
  const transitionTable = before.h041_checkpoint_transitions;
  assert.deepEqual(transitionTable.primaryKey, []);
  assert.equal(transitionTable.order.length, priorTransitions.length);
  assert.equal(new Set(transitionTable.order).size, priorTransitions.length);
  for (const [index, identity] of transitionTable.order.entries()) {
    assert.equal(identity, `rowid:${priorTransitions[index].retained_rowid}`);
    assert.equal(transitionTable.rows[identity].rowid, Number(priorTransitions[index].retained_rowid));
    assert.deepEqual(after.h041_checkpoint_transitions.rows[identity], transitionTable.rows[identity]);
  }
  assert.deepEqual(after.h041_checkpoint_transitions.order.slice(0, transitionTable.order.length), transitionTable.order);
  const duplicates = priorTransitions.filter(row => row.run_id === fixture.r.id);
  assert.equal(duplicates[1].body, duplicates[2].body);
  assert.notEqual(duplicates[1].retained_rowid, duplicates[2].retained_rowid);
  for (const table of immutableTables) assert.deepEqual(rows(store.db, table), immutableRows.get(table), `unrelated ${table} changed`);
  assert.equal(store.memory.read(fixture.queued.id, fixture.original.id, 0, 8192).text, privateChat);
  assert.equal(store.memory.current(fixture.queued.id)!.id, fixture.accepted2.id);
  // Settlement authority is deliberately never inferred from an accepted repair.
  assert.throws(() => store!.memory.bridge(fixture.queued.id).assertContinuationAllowed(), /uncertain/);
  const firstPriorEvent = priorEvents.get(fixture.queued.id)![0];
  const lastPriorEvent = priorEvents.get(fixture.queued.id)!.at(-1)!;
  const firstTransitionRowid = Number(priorTransitions[0].retained_rowid);
  const replacementTransitionRowid = Number(duplicates[0].retained_rowid);
  const nativeRows = rows(store.db, "h041_checkpoint_native_evidence");
  store.close();
  store = undefined;
  const mutations: Mutation[] = [];
  const sql = (name: string, statement: string, ...values: (string | number | null | Uint8Array)[]) =>
    mutations.push({ name, change: db => { const result = db.prepare(statement).run(...values); assert.ok(Number(result.changes) > 0, `ineffective ${name} fixture mutation`); } });
  const jsonChange = (name: string, table: string, column: string, idColumn: string, id: string | number, change: (body: Record<string, unknown>) => void) =>
    mutations.push({ name, change: db => {
      const body = JSON.parse(String(db.prepare(`SELECT ${column} FROM ${table} WHERE ${idColumn}=?`).get(id)![column]));
      change(body); db.prepare(`UPDATE ${table} SET ${column}=? WHERE ${idColumn}=?`).run(JSON.stringify(body), id);
    } });
  const duplicateJSONKey = (name: string, table: string, column: string, predicate: string, values: (string | number)[], key: string) =>
    mutations.push({ name, change: db => {
      const original = String(db.prepare(`SELECT ${column} FROM ${table} WHERE ${predicate}`).get(...values)![column]);
      assert.equal(original.startsWith("{"), true);
      assert.equal(Object.hasOwn(JSON.parse(original), key), true);
      const duplicate = `{${JSON.stringify(key)}:"forged",${original.slice(1)}`;
      // Ordinary JSON.parse sees the exact valid original payload because the
      // original occurrence is last. Rejection must come from duplicate keys.
      assert.deepEqual(JSON.parse(duplicate), JSON.parse(original));
      const result = db.prepare(`UPDATE ${table} SET ${column}=? WHERE ${predicate}`).run(duplicate, ...values);
      assert.equal(Number(result.changes), 1);
    } });
  mutations.push({ name: "original run primary key changed", change: db => {
    // Deliberately corrupt references only in this detached negative copy so
    // the retained verifier can reject identity loss. The production Store
    // fixture and its constructor never have foreign-key checks disabled.
    db.exec("PRAGMA foreign_keys=OFF");
    const result = db.prepare("UPDATE runs SET id=? WHERE id=?").run(randomUUID(), fixture.q.id);
    assert.equal(Number(result.changes), 1);
  } });
  sql("retained affected run error changed", "UPDATE runs SET error='arbitrary restart error' WHERE id=?", fixture.q.id);
  sql("retained unrelated run error changed", "UPDATE runs SET error='arbitrary restart error' WHERE id=?", fixture.done.id);
  sql("original run prompt changed", "UPDATE runs SET text=? WHERE id=?", "tampered prompt", fixture.q.id);
  sql("original run attachment list changed", "UPDATE runs SET attachment_ids='[]' WHERE id=?", fixture.q.id);
  for (const status of ["error", "failed", "cancelled", "completed", "queued"])
    sql(`interrupted run promoted to ${status}`, "UPDATE runs SET status=? WHERE id=?", status, fixture.q.id);
  sql("inactive completed run changed", "UPDATE runs SET status='interrupted' WHERE id=?", fixture.done.id);
  sql("native session ID changed", "UPDATE sessions SET native_session_id=? WHERE id=?", "forged-native-parent", fixture.queued.id);
  sql("session title changed", "UPDATE sessions SET title='forged title' WHERE id=?", fixture.queued.id);
  sql("session workspace changed", "UPDATE sessions SET workspace_id=? WHERE id=?", randomUUID(), fixture.queued.id);
  sql("session deletion flag changed", "UPDATE sessions SET deleted=1 WHERE id=?", fixture.queued.id);
  for (const status of ["idle", "failed", "running"])
    sql(`affected session promoted to ${status}`, "UPDATE sessions SET status=? WHERE id=?", status, fixture.queued.id);
  jsonChange("context unknown key added", "sessions", "context", "id", fixture.queued.id, body => { body.injected = true; });
  jsonChange("context used value changed", "sessions", "context", "id", fixture.queued.id, body => { body.used = 0; });
  jsonChange("context required key removed", "sessions", "context", "id", fixture.queued.id, body => { delete body.limit; });
  jsonChange("context stale cleared", "sessions", "context", "id", fixture.cancelling.id, body => { body.stale = false; });
  jsonChange("context private nested value changed", "sessions", "context", "id", fixture.queued.id, body => { (body.retainedExtension as Record<string, unknown>).nested = {}; });
  sql("Codex owner promoted to idle", "UPDATE h021_session_engines SET ownership='idle' WHERE session_id=?", fixture.ownerOnly.id);
  sql("Codex active turn cleared", "UPDATE h021_session_engines SET active_turn_id=NULL WHERE session_id=?", fixture.queued.id);
  sql("Codex event cursor changed", "UPDATE h021_session_engines SET event_cursor=999 WHERE session_id=?", fixture.queued.id);
  sql("Codex engine version changed", "UPDATE h021_session_engines SET engine_version='0.159.2' WHERE session_id=?", fixture.queued.id);
  sql("Codex model policy changed", "UPDATE h021_session_engines SET model_policy_version='forged-policy' WHERE session_id=?", fixture.queued.id);
  sql("Codex engine kind changed", "UPDATE h021_session_engines SET engine_kind='minimax' WHERE session_id=?", fixture.queued.id);
  sql("unrelated MiniMax owner changed", "UPDATE h021_session_engines SET ownership='uncertain' WHERE session_id=?", fixture.minimax.id);
  sql("message original text changed", "UPDATE messages SET content='forged body' WHERE id=?", fixture.userMessage.id);
  sql("message removed", "DELETE FROM messages WHERE id=?", fixture.userMessage.id);
  sql("file original path changed", "UPDATE files SET path='attachments/forged.txt' WHERE id=?", fixture.attachments[0].id);
  sql("file original size changed", "UPDATE files SET size=size+1 WHERE id=?", fixture.attachments[0].id);
  sql("original bytes changed", "UPDATE h041_originals SET body=? WHERE id=?", Buffer.from("forged original"), fixture.original.id);
  sql("original digest changed", "UPDATE h041_originals SET sha256=? WHERE id=?", digest("forged original"), fixture.original.id);
  sql("original row removed", "DELETE FROM h041_originals WHERE id=?", fixture.original.id);
  jsonChange("accepted state evidence changed", "h041_memory_versions", "body", "id", fixture.accepted2.id, body => { (body.state as Record<string, unknown>).objective = "forged objective"; });
  sql("accepted pointer rolled back", "UPDATE h041_memory_current SET version_id=? WHERE session_id=?", fixture.accepted1.id, fixture.queued.id);
  sql("native evidence body changed", "UPDATE h041_checkpoint_native_evidence SET body='{}' WHERE rowid=?", Number(nativeRows[0].retained_rowid));
  sql("native evidence kind changed", "UPDATE h041_checkpoint_native_evidence SET kind='launch' WHERE rowid=?", Number(nativeRows[0].retained_rowid));
  sql("native evidence removed", "DELETE FROM h041_checkpoint_native_evidence WHERE rowid=?", Number(nativeRows[0].retained_rowid));
  sql("native evidence duplicated", "INSERT INTO h041_checkpoint_native_evidence SELECT * FROM h041_checkpoint_native_evidence WHERE rowid=?", Number(nativeRows[0].retained_rowid));
  sql("native evidence genuine identity changed", "UPDATE h041_checkpoint_native_evidence SET rowid=rowid+1000 WHERE rowid=?", Number(nativeRows[0].retained_rowid));
  sql("original catalogue reference changed", "UPDATE h041_native_catalog SET sha256=? WHERE session_id=?", digest("forged catalog"), fixture.queued.id);
  sql("original consumption evidence changed", "UPDATE h041_memory_consumption SET body='{}' WHERE session_id=?", fixture.queued.id);
  sql("original file ownership reference changed", "UPDATE h002_file_refs SET run_id=? WHERE file_id=?", fixture.q2.id, fixture.artifacts[0].id);
  sql("original final-message native ID changed", "UPDATE h002_message_meta SET data=? WHERE message_id=?", JSON.stringify({ phase: "final", nativeMessageId: "forged-id" }), fixture.finalMessage.id);
  sql("original subagent evidence changed", "UPDATE h002_subagents SET data='{}' WHERE run_id=?", fixture.q.id);
  for (const key of ["injected", "acceptedVersionId", "nativeThreadId", "references", "compactions", "originalInventory", "nativeState"])
    jsonChange(`checkpoint ${key} evidence changed`, "h041_session_checkpoints", "body", "id", fixture.prepared.id, body => { body[key] = key === "injected" ? true : null; });
  jsonChange("checkpoint body key removed", "h041_session_checkpoints", "body", "id", fixture.prepared.id, body => { delete body.kind; });
  jsonChange("checkpoint success outcome substituted", "h041_session_checkpoints", "body", "id", fixture.prepared.id, body => { body.outcome = "completed"; });
  sql("checkpoint settled outcome substituted", "UPDATE h041_session_checkpoints SET status='settled' WHERE id=?", fixture.prepared.id);
  jsonChange("unrelated settled checkpoint changed", "h041_session_checkpoints", "body", "id", fixture.settled.id, body => { body.outcome = "process_restart"; });
  jsonChange("unrelated recovery checkpoint changed", "h041_session_checkpoints", "body", "id", fixture.alreadyRecovery.id, body => { body.extra = "forged"; });
  sql("derived quarantine arbitrary reason", "UPDATE quarantined_workspaces SET reason='forged_restart' WHERE id=?", fixture.queued.workspaceId);
  sql("derived quarantine removed", "DELETE FROM quarantined_workspaces WHERE id=?", fixture.running.workspaceId);
  sql("unrelated quarantine changed", "UPDATE quarantined_workspaces SET reason='restart_during_run' WHERE id=?", fixture.minimax.workspaceId);
  sql("unrelated quarantine removed", "DELETE FROM quarantined_workspaces WHERE id=?", fixture.minimax.workspaceId);
  sql("unrelated quarantine added", "INSERT INTO quarantined_workspaces VALUES(?,'restart_during_run')", fixture.idle.workspaceId);
  sql("unrelated session status changed", "UPDATE sessions SET status='interrupted' WHERE id=?", fixture.idle.id);
  sql("unrelated session timestamp changed", "UPDATE sessions SET updated_at='2026-10-01T19:00:00.000Z' WHERE id=?", fixture.idle.id);
  jsonChange("unrelated session context changed", "sessions", "context", "id", fixture.idle.id, body => { body.stale = true; });
  sql("prior event removed", "DELETE FROM events WHERE session_id=? AND id=?", fixture.queued.id, firstPriorEvent.id);
  sql("prior event arbitrary body", "UPDATE events SET data='{}' WHERE session_id=? AND id=?", fixture.queued.id, firstPriorEvent.id);
  sql("prior event type changed", "UPDATE events SET type='error' WHERE session_id=? AND id=?", fixture.queued.id, firstPriorEvent.id);
  mutations.push({ name: "prior events reordered", change: db => {
    const a = String(db.prepare("SELECT data FROM events WHERE session_id=? AND id=?").get(fixture.queued.id, firstPriorEvent.id)!.data);
    const b = String(db.prepare("SELECT data FROM events WHERE session_id=? AND id=?").get(fixture.queued.id, lastPriorEvent.id)!.data);
    assert.notEqual(a, b);
    db.prepare("UPDATE events SET data=? WHERE session_id=? AND id=?").run(b, fixture.queued.id, firstPriorEvent.id);
    db.prepare("UPDATE events SET data=? WHERE session_id=? AND id=?").run(a, fixture.queued.id, lastPriorEvent.id);
  } });
  sql("prior event duplicated as append", "INSERT INTO events SELECT session_id,(SELECT MAX(id)+1 FROM events WHERE session_id=?),type,run_id,created_at,data FROM events WHERE session_id=? AND id=?", fixture.queued.id, fixture.queued.id, firstPriorEvent.id);
  sql("required recovery run event missing", "DELETE FROM events WHERE session_id=? AND id=?", fixture.queued.id, lastPriorEvent.id + 1);
  sql("required recovery error event missing", "DELETE FROM events WHERE session_id=? AND type='error'", fixture.ownerOnly.id);
  sql("arbitrary recovery error body", "UPDATE events SET data=? WHERE session_id=? AND type='error'", JSON.stringify({ code: "interrupted", message: "arbitrary error" }), fixture.queued.id);
  sql("arbitrary appended recovery event", "INSERT INTO events SELECT ?,COALESCE(MAX(id),0)+1,'done',NULL,?,'{\"outcome\":\"success\"}' FROM events WHERE session_id=?", fixture.queued.id, new Date().toISOString(), fixture.queued.id);
  sql("unrelated session event append", "INSERT INTO events SELECT ?,COALESCE(MAX(id),0)+1,'state',NULL,?,'{\"status\":\"interrupted\"}' FROM events WHERE session_id=?", fixture.idle.id, new Date().toISOString(), fixture.idle.id);
  sql("prior checkpoint history removed", "DELETE FROM h041_checkpoint_transitions WHERE rowid=?", firstTransitionRowid);
  sql("prior checkpoint history duplicated", "INSERT INTO h041_checkpoint_transitions SELECT * FROM h041_checkpoint_transitions WHERE rowid=?", firstTransitionRowid);
  sql("prior checkpoint history identity changed", "UPDATE h041_checkpoint_transitions SET rowid=rowid+1000 WHERE rowid=?", firstTransitionRowid);
  sql("prior checkpoint history body changed", "UPDATE h041_checkpoint_transitions SET body='{}' WHERE rowid=?", firstTransitionRowid);
  mutations.push({ name: "prior keyless checkpoint history reordered", change: db => {
    db.prepare("UPDATE h041_checkpoint_transitions SET rowid=-1 WHERE rowid=?").run(firstTransitionRowid);
    db.prepare("UPDATE h041_checkpoint_transitions SET rowid=? WHERE rowid=?").run(firstTransitionRowid, replacementTransitionRowid);
    db.prepare("UPDATE h041_checkpoint_transitions SET rowid=? WHERE rowid=-1").run(replacementTransitionRowid);
  } });
  sql("required checkpoint transition removed", "DELETE FROM h041_checkpoint_transitions WHERE rowid=(SELECT MAX(rowid) FROM h041_checkpoint_transitions WHERE run_id=?)", fixture.q.id);
  sql("recovery transition duplicated", "INSERT INTO h041_checkpoint_transitions SELECT * FROM h041_checkpoint_transitions WHERE rowid=(SELECT MAX(rowid) FROM h041_checkpoint_transitions WHERE run_id=?)", fixture.q.id);
  sql("arbitrary appended checkpoint transition", "INSERT INTO h041_checkpoint_transitions VALUES(?,?,?)", fixture.queued.id, fixture.q.id, JSON.stringify({ status: "recovery_required", outcome: "process_restart", arbitrary: true }));
  jsonChange("appended checkpoint transition payload changed", "h041_checkpoint_transitions", "body", "rowid", priorTransitions.length + 1, body => { body.outcome = "completed"; });
  duplicateJSONKey("duplicate context JSON keys", "sessions", "context", "id=?", [fixture.queued.id], "stale");
  duplicateJSONKey("duplicate checkpoint JSON keys", "h041_session_checkpoints", "body", "id=?", [fixture.prepared.id], "status");
  duplicateJSONKey("duplicate recovery event JSON keys", "events", "data", "session_id=? AND type='error'", [fixture.queued.id], "code");
  sql("noncanonical recovery event JSON whitespace", "UPDATE events SET data=? WHERE session_id=? AND type='error'", '{"code": "interrupted", "message": "Server restarted; the run was interrupted and was not replayed"}', fixture.queued.id);
  sql("early recovery event timestamp", "UPDATE events SET created_at='2000-01-01T00:00:00.000Z' WHERE session_id=? AND type='error'", fixture.queued.id);
  sql("noncontiguous recovery event ID", "UPDATE events SET id=id+1000 WHERE session_id=? AND id=?", fixture.queued.id, lastPriorEvent.id + 1);
  sql("negative appended event rowid", "UPDATE events SET rowid=-1 WHERE session_id=? AND id=?", fixture.queued.id, lastPriorEvent.id + 1);
  sql("noncontiguous appended event rowid", "UPDATE events SET rowid=rowid+1000 WHERE session_id=? AND id=?", fixture.queued.id, lastPriorEvent.id + 1);
  sql("negative appended checkpoint rowid", "UPDATE h041_checkpoint_transitions SET rowid=-1 WHERE rowid=?", priorTransitions.length + 1);
  sql("noncontiguous appended checkpoint rowid", "UPDATE h041_checkpoint_transitions SET rowid=rowid+1000 WHERE rowid=?", priorTransitions.length + 1);
  sql("derived quarantine rowid changed", "UPDATE quarantined_workspaces SET rowid=rowid+1000 WHERE id=?", fixture.queued.workspaceId);
  mutations.push({ name: "unexpected table schema added", change: db => db.exec("CREATE TABLE injected_evidence(id TEXT PRIMARY KEY,body TEXT)") });
  mutations.push({ name: "unexpected column schema added", change: db => db.exec("ALTER TABLE runs ADD COLUMN injected_error TEXT") });
  mutations.push({ name: "unexpected index schema added", change: db => db.exec("CREATE INDEX injected_run_status ON runs(status)") });
  const copiesRoot = join(root, "independent-tampered-copies");
  mkdirSync(copiesRoot, { mode: 0o700 });
  const cases = mutations.map((mutation, index) => {
    const copy = join(copiesRoot, `${String(index).padStart(3, "0")}.sqlite`);
    copyFileSync(database, copy); chmodSync(copy, 0o600);
    const db = new DatabaseSync(copy);
    try { mutation.change(db); } finally { db.close(); }
    for (const suffix of ["", "-wal", "-shm"]) {
      try { chmodSync(copy + suffix, 0o600); } catch (error) { if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error; }
    }
    return { name: mutation.name, database: copy };
  });
  const casesPath = join(root, "tampered-cases.json"), rejectsPath = join(root, "rejections.json");
  writeFileSync(casesPath, JSON.stringify(cases), { mode: 0o600, flag: "wx" });
  runPython(root, "verify-independent-tampered-copies", ["reject-copies", beforePath, casesPath, rejectsPath]);
  const rejections = JSON.parse(readFileSync(rejectsPath, "utf8")) as { name: string; rejected: boolean; error?: string }[];
  assert.equal(rejections.length, mutations.length);
  for (const rejection of rejections) await t.test(rejection.name, () => {
    assert.equal(rejection.rejected, true, `retained verifier accepted ${rejection.name}`);
    assert.equal(typeof rejection.error, "string");
    assert.ok(rejection.error!.length > 0);
  });
  t.diagnostic(`Actual Store constructor repair accepted; ${mutations.length} independent tampered copies rejected. Protected fixture/child receipts retained at ${root}. Native carrier NOT_TESTED; default-disabled.`);
});
