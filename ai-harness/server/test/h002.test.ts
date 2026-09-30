import assert from "node:assert/strict";
import test, { type TestContext } from "node:test";
import {
  mkdtemp,
  realpath,
  rm,
  writeFile,
  symlink,
  readFile,
} from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { DatabaseSync } from "node:sqlite";
import { Readable } from "node:stream";
import { execFileSync } from "node:child_process";
import { Store } from "../src/store.js";
import { createApp } from "../src/app.js";
import { localeClock, environment, clockInstruction } from "../src/locale.js";
import type { EngineFactory } from "../src/contracts.js";
import { MAX_ZIP_BYTES, MAX_ZIP_FILES } from "../src/zip.js";

async function setup(t: TestContext, engineFactory?: EngineFactory) {
  const root = await realpath(
    await mkdtemp(path.join(tmpdir(), "h002-fixture-")),
  );
  const h = await createApp({
    dataDir: root,
    allowedOrigins: ["http://localhost"],
    launcher: "/not-executed",
    gatewayUrl: "http://127.0.0.1:1/v1",
    issueToken: () => "fixture-token",
    revokeToken: () => {},
    engineFactory:
      engineFactory ??
      (() => ({
        async start() {},
        async prompt() {},
        async cancel() {},
        async close() {},
      })),
  });
  t.after(async () => {
    await h.app.close();
    await rm(root, { recursive: true, force: true });
  });
  const session = await h.broker.createSession();
  return {
    ...h,
    root,
    session,
    request: (url: string) =>
      h.app.inject({ url, headers: { host: "localhost" } }),
  };
}

test("H002 old database gets companion metadata only, immutable originals, proven historical file and activity association", async (t) => {
  const root = await realpath(
    await mkdtemp(path.join(tmpdir(), "h002-legacy-")),
  );
  t.after(() => rm(root, { recursive: true, force: true }));
  const dbpath = path.join(root, "old.sqlite");
  const db = new DatabaseSync(dbpath);
  db.exec(`CREATE TABLE sessions(id TEXT PRIMARY KEY,title TEXT,created_at TEXT,updated_at TEXT,status TEXT,context TEXT,workspace_id TEXT,native_session_id TEXT,deleted INTEGER DEFAULT 0,delete_requested INTEGER DEFAULT 0);
    CREATE TABLE messages(id TEXT PRIMARY KEY,session_id TEXT,role TEXT,content TEXT,created_at TEXT,run_id TEXT,attachment_ids TEXT);
    CREATE TABLE files(id TEXT PRIMARY KEY,session_id TEXT,kind TEXT,path TEXT,name TEXT,mime_type TEXT,size INTEGER,UNIQUE(session_id,kind,path));
    CREATE TABLE runs(id TEXT PRIMARY KEY,session_id TEXT,workspace_id TEXT,kind TEXT,text TEXT,attachment_ids TEXT,status TEXT,created_at TEXT,updated_at TEXT);
    CREATE TABLE events(session_id TEXT,id INTEGER,type TEXT,run_id TEXT,created_at TEXT,data TEXT,PRIMARY KEY(session_id,id));`);
  const context = {
    used: null,
    limit: 480000,
    estimated: false,
    stale: true,
    updatedAt: "2026-01-01T00:00:00Z",
  };
  db.prepare("INSERT INTO sessions VALUES(?,?,?,?,?,?,?,?,?,?)").run(
    "s",
    "retained",
    "time",
    "time",
    "idle",
    JSON.stringify(context),
    "w",
    "native",
    0,
    0,
  );
  db.prepare("INSERT INTO messages VALUES(?,?,?,?,?,?,?)").run(
    "m",
    "s",
    "assistant",
    "Merged original planning and answer.",
    "time",
    "r",
    "[]",
  );
  db.prepare("INSERT INTO runs VALUES(?,?,?,?,?,?,?,?,?)").run(
    "r",
    "s",
    "w",
    "message",
    "synthetic",
    "[]",
    "completed",
    "time",
    "time",
  );
  db.prepare("INSERT INTO files VALUES(?,?,?,?,?,?,?)").run(
    "f",
    "s",
    "artifact",
    "f",
    "legacy.svg",
    "image/svg+xml",
    7,
  );
  db.prepare("INSERT INTO events VALUES(?,?,?,?,?,?)").run(
    "s",
    1,
    "artifact",
    "r",
    "time",
    JSON.stringify({ artifact: { id: "f" } }),
  );
  db.prepare("INSERT INTO events VALUES(?,?,?,?,?,?)").run(
    "s",
    2,
    "progress",
    "r",
    "time",
    JSON.stringify({
      kind: "tool",
      taskId: "native-tool",
      label: "retained label",
      detail: "retained detail",
    }),
  );
  db.close();
  const store = new Store(dbpath);
  try {
    const snap = store.snapshot("s");
    assert.equal(
      snap.messages[0].content,
      "Merged original planning and answer.",
    );
    assert.equal(snap.messages[0].phase, "unclassified");
    assert.deepEqual(snap.session.context, context);
    assert.equal(snap.artifacts[0].runId, "r");
    assert.equal(snap.activities[0].runId, "r");
    assert.equal(snap.activities[0].status, "unknown");
    assert.equal(snap.activities[0].command, undefined);
    assert.equal(snap.events.length, 2);
    assert.equal(snap.watermark, 2);
    assert.equal(
      store.db.prepare("PRAGMA table_info(messages)").all().length,
      7,
    );
    assert.equal(store.db.prepare("PRAGMA table_info(files)").all().length, 7);
    store.db
      .prepare("INSERT INTO messages VALUES(?,?,?,?,?,?,?)")
      .run(
        "rollback-message",
        "s",
        "user",
        "Old release still writes.",
        "later",
        "r",
        "[]",
      );
    store.db
      .prepare("INSERT INTO files VALUES(?,?,?,?,?,?,?)")
      .run(
        "rollback-file",
        "s",
        "artifact",
        "newfile",
        "new.txt",
        "text/plain",
        1,
      );
    assert.equal(store.message("rollback-message").phase, "unclassified");
    assert.equal(store.file("rollback-file").runId, null);
  } finally {
    store.close();
  }
});

test("H002 multi-channel first delta creation is atomic; watermark reconnect has no duplicate text or phantom row", () => {
  const store = new Store(":memory:");
  try {
    const session = store.createSession(),
      run = store.createRun(session, "message", "synthetic", []);
    store.db.exec(
      "CREATE TRIGGER reject_delta BEFORE INSERT ON events WHEN NEW.type='assistant_delta' BEGIN SELECT RAISE(ABORT,'failure'); END;",
    );
    assert.throws(() =>
      store.appendDelta(session.id, "thought", "should rollback", run.id, {
        phase: "thinking",
        nativeMessageId: "native",
      }),
    );
    assert.equal(store.messages(session.id).length, 0);
    store.db.exec("DROP TRIGGER reject_delta");
    store.appendDelta(session.id, "thought", "emitted", run.id, {
      phase: "thinking",
      nativeMessageId: "native",
      streamState: "streaming",
    });
    store.appendDelta(session.id, "visible", "first", run.id, {
      phase: "unclassified",
      nativeMessageId: "native",
      streamState: "streaming",
    });
    const snapshot = store.snapshot(session.id);
    store.appendDelta(session.id, "visible", " second", run.id, {
      phase: "unclassified",
      nativeMessageId: "native",
      streamState: "streaming",
    });
    const reconnect = store.replay(session.id, snapshot.watermark);
    assert.equal(reconnect.length, 1);
    assert.equal(reconnect[0].data.text, " second");
    assert.equal(
      snapshot.messages.find((m) => m.id === "visible")!.content,
      "first",
    );
    assert.equal(store.message("visible").content, "first second");
    assert.equal(store.message("thought").phase, "thinking");
  } finally {
    store.close();
  }
});

test("H002 exact attachment names/downloads, safe image headers, run ZIP content/ownership/escape/bounds", async (t) => {
  const h = await setup(t);
  const s = h.store.getSession(h.session.id);
  const run = h.store.createRun(s, "message", "synthetic", []);
  const f = await h.files.upload(
    s.id,
    "načrt prostora 東京.txt",
    "text/plain",
    Readable.from(["uploaded synthetic"]),
  );
  h.store.addMessage(s.id, "user", "with file", run.id, [f.id]);
  const download = await h.request(`/api/attachments/${f.id}/download`);
  assert.equal(download.statusCode, 200);
  assert.equal(download.body, "uploaded synthetic");
  assert.match(
    download.headers["content-disposition"]!,
    /filename\*=UTF-8''na%C4%8Drt%20prostora%20%E6%9D%B1%E4%BA%AC.txt/,
  );
  assert.equal(
    h.store.snapshot(s.id).messages[0].attachments![0].name,
    "načrt prostora 東京.txt",
  );
  const workspace = h.files.workspace(s.workspaceId);
  await writeFile(
    path.join(workspace, "one.svg"),
    '<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
  );
  await writeFile(path.join(workspace, "two.txt"), "second synthetic");
  const a = await h.files.registerArtifact(
    s.id,
    "one.svg",
    "duplicate.svg",
    undefined,
    run.id,
  );
  const b = await h.files.registerArtifact(
    s.id,
    "two.txt",
    "duplicate.svg",
    undefined,
    run.id,
  );
  const preview = await h.request(`/api/files/${a.id}/preview`);
  assert.equal(preview.statusCode, 200);
  assert.match(preview.headers["content-type"]!, /^image\/svg\+xml/);
  assert.match(
    preview.headers["content-security-policy"]!,
    /sandbox; default-src 'none'; script-src 'none'/,
  );
  assert.equal(preview.headers["x-content-type-options"], "nosniff");
  const before = h.store.files(s.id, "artifact").length;
  await h.request(`/api/files/${a.id}/preview`);
  assert.equal(h.store.files(s.id, "artifact").length, before);
  const snap = h.store.snapshot(s.id);
  assert.equal(snap.runs[0].artifactIds.length, 2);
  assert.ok(snap.runs[0].zipUrl);
  const zip = await h.request(snap.runs[0].zipUrl!);
  assert.equal(zip.statusCode, 200);
  assert.match(zip.headers["content-type"]!, /application\/zip/);
  const archive = path.join(h.root, "fixture.zip");
  await writeFile(archive, zip.rawPayload);
  const listing = JSON.parse(
    execFileSync(
      "python3",
      [
        "-c",
        "import zipfile,json,sys; z=zipfile.ZipFile(sys.argv[1]); print(json.dumps({'names':z.namelist(),'ok':z.testzip() is None,'sizes':[i.file_size for i in z.infolist()]}))",
        archive,
      ],
      { encoding: "utf8" },
    ),
  );
  assert.deepEqual(listing.names, ["1-duplicate.svg", "2-duplicate.svg"]);
  assert.equal(listing.ok, true);
  const other = h.store.createSession();
  assert.equal(
    (await h.request(`/api/sessions/${other.id}/runs/${run.id}/artifacts.zip`))
      .statusCode,
    404,
  );
  assert.equal(
    (
      await h.request(
        `/api/sessions/${s.id}/runs/${run.id}/artifacts.zip?path=../../x`,
      )
    ).statusCode,
    400,
  );
  h.store.db
    .prepare("UPDATE files SET size=? WHERE id=?")
    .run(MAX_ZIP_BYTES + 1, a.id);
  assert.equal((await h.request(snap.runs[0].zipUrl!)).statusCode, 413);
  h.store.db.prepare("UPDATE files SET size=? WHERE id=?").run(1, a.id);
  await rm(path.join(h.root, "artifacts", b.id));
  await symlink(
    path.join(workspace, "two.txt"),
    path.join(h.root, "artifacts", b.id),
  );
  assert.equal((await h.request(snap.runs[0].zipUrl!)).statusCode, 400);
  h.store.db
    .prepare("UPDATE files SET path=? WHERE id=?")
    .run("../two.txt", a.id);
  assert.equal(
    (await h.request(`/api/artifacts/${a.id}/download`)).statusCode,
    400,
  );
  assert.equal(MAX_ZIP_FILES, 100);
  for (let i = 0; i <= MAX_ZIP_FILES; i++)
    h.store.saveFile({
      id: `bound-${i}`,
      sessionId: s.id,
      kind: "artifact",
      path: `bound-${i}`,
      name: "../escape.txt",
      mimeType: "text/plain",
      size: 1,
      runId: run.id,
    });
  assert.equal((await h.request(snap.runs[0].zipUrl!)).statusCode, 413);
});

test("H002 final promotion waits for app settlement; Stop during artifact discovery keeps every message nonfinal", async (t) => {
  let notify = () => {};
  const reached = new Promise<void>((r) => {
    notify = r;
  });
  let release = () => {};
  const barrier = new Promise<void>((r) => {
    release = r;
  });
  const h = await setup(t, (opts) => ({
    async start() {},
    async prompt() {
      opts.onUpdate({
        type: "text",
        text: "Candidate answer",
        nativeMessageId: "n",
      });
      opts.onUpdate({
        type: "phase",
        nativeMessageId: "n",
        nativeTurnId: "t",
        channel: "final",
        phaseSource: "fixture-native",
        streamState: "completed",
      });
    },
    async cancel() {},
    async close() {},
  }));
  let discoveries = 0;
  const original = h.files.discover.bind(h.files);
  h.files.discover = async (id) => {
    if (++discoveries === 2) {
      notify();
      await barrier;
    }
    return original(id);
  };
  const run = h.broker.enqueue(h.session.id, "message", "synthetic");
  await reached;
  assert.ok(h.store.messages(h.session.id).every((m) => m.phase !== "final"));
  await h.broker.cancel(h.session.id);
  release();
  await h.broker.idle();
  assert.equal(h.store.runSnapshot(run).status, "cancelled");
  assert.equal(h.store.runSnapshot(run).finalMessageId, null);
  assert.ok(
    h.store
      .allEvents(h.session.id)
      .every(
        (e) =>
          e.type !== "message" || (e.data.message as any).phase !== "final",
      ),
  );
});

test("H002 successful run publishes atomic final/message/file/run snapshots and complete queued cancellation updates", async (t) => {
  const h = await setup(t, (opts) => ({
    async start() {},
    async prompt() {
      await writeFile(
        path.join(opts.workspace, "answer.svg"),
        '<svg xmlns="http://www.w3.org/2000/svg"/>',
      );
      opts.onUpdate({
        type: "progress",
        kind: "tool",
        label: "bash running",
        toolCallId: "tool",
        name: "bash",
        status: "in_progress",
        command: "echo fixture",
      });
      opts.onUpdate({
        type: "progress",
        kind: "tool",
        label: "bash completed",
        toolCallId: "tool",
        name: "bash",
        status: "completed",
      });
      opts.onUpdate({
        type: "text",
        text: "Actual answer",
        nativeMessageId: "n",
      });
      opts.onUpdate({
        type: "phase",
        nativeMessageId: "n",
        nativeTurnId: "t",
        channel: "final",
        phaseSource: "fixture-native",
        streamState: "completed",
      });
    },
    async cancel() {},
    async close() {},
  }));
  const id = h.broker.enqueue(h.session.id, "message", "synthetic");
  await h.broker.idle();
  const run = h.store.runSnapshot(id);
  assert.equal(run.status, "completed");
  assert.equal(h.store.activities(h.session.id).length, 1);
  assert.equal(h.store.activities(h.session.id)[0].status, "completed");
  assert.equal(h.store.activities(h.session.id)[0].command, "echo fixture");
  assert.equal(run.artifactIds.length, 1);
  assert.equal(h.store.file(run.artifactIds[0]).messageId, run.finalMessageId);
  assert.equal(h.store.message(run.finalMessageId!).phase, "final");
  const events = h.store.allEvents(h.session.id);
  assert.ok(
    events.some(
      (e) => e.type === "run" && (e.data.run as any).status === "completed",
    ),
  );
  const a = h.broker.enqueue(h.session.id, "message", "queued a"),
    b = h.broker.enqueue(h.session.id, "message", "queued b");
  await h.broker.cancel(h.session.id);
  await h.broker.idle();
  for (const id of [a, b])
    assert.ok(
      h.store
        .allEvents(h.session.id)
        .some(
          (e) =>
            e.type === "run" &&
            e.runId === id &&
            (e.data.run as any).status === "cancelled",
        ),
    );
});

test("H002 empty zero is restricted to untouched sessions; clock uses Ljubljana DST and fresh instants", async (t) => {
  const h = await setup(t);
  assert.equal(h.store.getSession(h.session.id).context!.source, "empty");
  assert.equal(h.store.getSession(h.session.id).context!.used, 0);
  h.broker.enqueue(h.session.id, "message", "synthetic");
  assert.equal(h.store.getSession(h.session.id).context!.used, null);
  await h.broker.idle();
  assert.match(
    localeClock(new Date("2026-01-01T00:00:00Z")).localTime,
    /01:00:00 GMT\+1/,
  );
  assert.match(
    localeClock(new Date("2026-07-01T00:00:00Z")).localTime,
    /02:00:00 GMT\+2/,
  );
  assert.match(
    localeClock(new Date("2026-03-29T01:00:00Z")).localTime,
    /03:00:00 GMT\+2/,
  );
  assert.match(
    localeClock(new Date("2026-10-25T01:00:00Z")).localTime,
    /02:00:00 GMT\+1/,
  );
  assert.notEqual(environment(new Date(0)).now, environment(new Date(1)).now);
  assert.match(
    clockInstruction(new Date("2030-05-04T10:11:12Z")),
    /2030-05-04T10:11:12.000Z/,
  );
});

test("H002 Unicode names have safe old-release headers and exact companion display names", async (t) => {
  const h = await setup(t);
  const s = h.store.getSession(h.session.id),
    run = h.store.createRun(s, "message", "synthetic", []);
  await writeFile(
    path.join(h.files.workspace(s.workspaceId), "source.svg"),
    '<svg xmlns="http://www.w3.org/2000/svg"/>',
  );
  const artifact = await h.files.registerArtifact(
    s.id,
    "source.svg",
    "načrt prostora 東京.svg",
    undefined,
    run.id,
  );
  const raw = h.store.db
    .prepare("SELECT name FROM files WHERE id=?")
    .get(artifact.id)!;
  assert.equal(raw.name, "na_rt prostora __.svg");
  assert.match(`attachment; filename="${raw.name}"`, /^[\x20-\x7e]+$/);
  assert.equal(h.store.file(artifact.id).name, "načrt prostora 東京.svg");
  const response = await h.request(`/api/artifacts/${artifact.id}/download`);
  assert.equal(response.statusCode, 200);
  assert.match(
    response.headers["content-disposition"]!,
    /filename\*=UTF-8''na%C4%8Drt%20prostora%20%E6%9D%B1%E4%BA%AC.svg/,
  );
});
