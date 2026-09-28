import assert from "node:assert/strict";
import test from "node:test";
import { mkdtemp, rm, writeFile, readFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { Store } from "../src/store.js";
import { createApp } from "../src/app.js";
import { createEngineRouter } from "../src/engine-router.js";
import type { EngineOptions } from "../src/contracts.js";

const policy = { codex: { enabled: true, protocolQualified: true, engineVersion: "fixture-pin", modelPolicyVersion: "fixture-policy" } };
const inert = () => ({ async start() {}, async prompt() {}, async cancel() {}, async close() {} });

test("legacy migration preserves IDs, original messages, events and file bytes; missing metadata later fails closed", async (t) => {
  const dir = await mkdtemp(join(tmpdir(), "h021-migration-"));
  t.after(() => rm(dir, { recursive: true, force: true }));
  const db = join(dir, "store.sqlite");
  let store = new Store(db);
  const legacy = store.createSession();
  store.setNative(legacy.id, "legacy-native-id");
  store.addMessage(legacy.id, "user", "original history");
  store.emit(legacy.id, "progress", { label: "legacy event" });
  const bytes = Buffer.from("immutable artifact");
  await writeFile(join(dir, "artifact.txt"), bytes);
  store.db.prepare("INSERT INTO files VALUES(?,?,?,?,?,?,?)").run("file", legacy.id, "artifact", "artifact.txt", "artifact.txt", "text/plain", bytes.length);
  const rows = JSON.stringify(store.db.prepare("SELECT * FROM sessions").all());
  const history = store.snapshot(legacy.id);
  store.db.exec("DROP TABLE h021_session_engines; DROP TABLE h021_migrations");
  store.close(); store = new Store(db);
  assert.equal(JSON.stringify(store.db.prepare("SELECT * FROM sessions").all()), rows);
  assert.equal(store.getSession(legacy.id).engineKind, "minimax");
  assert.equal(store.getSession(legacy.id).nativeSessionId, "legacy-native-id");
  assert.deepEqual({ ...store.snapshot(legacy.id), environment: history.environment }, history);
  assert.deepEqual(await readFile(join(dir, "artifact.txt")), bytes);
  assert.throws(() => store.setNative(legacy.id, "codex-thread", "codex"), /cannot change engine/);
  store.db.prepare("DELETE FROM h021_session_engines WHERE session_id=?").run(legacy.id);
  store.close(); store = new Store(db);
  assert.throws(() => store.getSession(legacy.id), /metadata requires operator review/);
  store.close();
});

test("restart retains native thread/turn and cursor, quarantines uncertain work without replay", async (t) => {
  const dir = await mkdtemp(join(tmpdir(), "h021-restart-"));
  t.after(() => rm(dir, { recursive: true, force: true }));
  const db = join(dir, "store.sqlite");
  let store = new Store(db);
  const s = store.createSession(undefined, "codex", policy.codex);
  store.setNative(s.id, "thread-fixture", "codex");
  store.setNativeState(s.id, "codex", { activeTurnId: "turn-fixture", eventCursor: 7, ownership: "active" });
  const run = store.createRun(s, "message", "never replay", []);
  store.updateRun(run.id, "running");
  store.addMessage(s.id, "user", "retain through compaction", run.id);
  store.close(); store = new Store(db);
  assert.deepEqual(store.getSession(s.id).nativeState, { activeTurnId: "turn-fixture", eventCursor: 7, ownership: "uncertain" });
  assert.equal(store.getSession(s.id).status, "interrupted");
  assert.equal(store.getSession(s.id).nativeSessionId, "thread-fixture");
  assert.equal(store.runs(s.id)[0]!.status, "interrupted");
  assert.ok(store.isQuarantined(s.workspaceId));
  assert.equal(store.messages(s.id)[0]!.content, "retain through compaction");
  assert.throws(() => store.setNativeState(s.id, "codex", { activeTurnId: null, eventCursor: 6, ownership: "idle" }), /Invalid native ownership/);
  store.db.prepare("UPDATE h021_session_engines SET engine_kind='unknown' WHERE session_id=?").run(s.id);
  assert.throws(() => store.getSession(s.id), /metadata requires operator review/);
  store.close();
});

test("router rejects cross-engine policy/uncertain resume and does not silently choose MiniMax", () => {
  let minimax = 0, codex = 0;
  const router = createEngineRouter(() => { minimax++; return inert(); }, () => { codex++; return inert(); }, policy);
  const options = { engineKind: "codex", engineVersion: "fixture-pin", modelPolicyVersion: "fixture-policy", nativeState: { activeTurnId: null, eventCursor: 0, ownership: "idle" } } as EngineOptions;
  router(options); assert.equal(codex, 1); assert.equal(minimax, 0);
  assert.throws(() => router({ ...options, engineVersion: "different" }), /reviewed engine/);
  assert.throws(() => router({ ...options, nativeState: { activeTurnId: "uncertain", eventCursor: 0, ownership: "uncertain" } }), /settlement review/);
  assert.throws(() => createEngineRouter(inert)(options), /awaits protocol/);
  assert.throws(() => router({ ...options, engineKind: "unknown" as never }), /Unknown engine/);
});

test("HTTP policy gate defaults to MiniMax; preview choice is new-chat-only; RPC/config/media rejected", async (t) => {
  const dataDir = await mkdtemp(join(tmpdir(), "h021-routes-"));
  const { app, store } = await createApp({ dataDir, allowedOrigins: ["http://localhost"], engineFactory: inert, launcher: "/unavailable", gatewayUrl: "http://fixture.invalid", issueToken: () => "fixture", revokeToken() {} });
  t.after(async () => { await app.close(); await rm(dataDir, { recursive: true, force: true }); });
  const inject = (method: "GET" | "POST", url: string, payload?: unknown) => app.inject({ method, url, payload: payload as object, headers: { host: "localhost" } });
  assert.equal((await inject("GET", "/api/health")).json().engines.codex.available, false);
  assert.equal((await inject("POST", "/api/sessions", { engineKind: "codex" })).statusCode, 409);
  assert.equal((await inject("POST", "/api/sessions", { engineKind: "other" })).statusCode, 400);
  const created = (await inject("POST", "/api/sessions", {})).json().session;
  assert.equal(created.engineKind, "minimax");
  assert.equal(store.getSession(created.id).engineKind, "minimax");
  assert.equal((await inject("POST", "/api/sessions", { launcher: "arbitrary" })).statusCode, 400);
  assert.equal((await inject("POST", `/api/sessions/${created.id}`, { engineKind: "codex" })).statusCode, 404);
  assert.equal((await inject("POST", "/api/codex/rpc", { method: "command/exec" })).statusCode, 404);
});
