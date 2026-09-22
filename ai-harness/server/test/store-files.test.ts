import assert from "node:assert/strict";
import test, { type TestContext } from "node:test";
import {
  mkdtemp,
  realpath,
  rm,
  writeFile,
  readFile,
  mkdir,
  symlink,
  link,
  readdir,
} from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { Readable } from "node:stream";
import { Store } from "../src/store.js";
import { Files, MAX_UPLOAD, safeName } from "../src/files.js";
import { requireId } from "../src/errors.js";

async function setup(t: TestContext) {
  const root = await realpath(
    await mkdtemp(path.join(tmpdir(), "h001-files-test-")),
  );
  const store = new Store(path.join(root, "fixture.sqlite")),
    files = new Files(root, store);
  await files.init();
  const session = store.createSession();
  await files.prepare(session.id, session.workspaceId);
  t.after(async () => {
    store.close();
    await rm(root, { recursive: true, force: true });
  });
  return {
    root,
    store,
    files,
    session,
    workspace: files.workspace(session.workspaceId),
  };
}
const unsafe = (error: unknown) =>
  !!error &&
  typeof error === "object" &&
  "code" in error &&
  error.code === "unsafe_path";

test("restart marks queued/running/cancelling work interrupted and quarantined without replay", async (t) => {
  const root = await realpath(
      await mkdtemp(path.join(tmpdir(), "h001-restart-test-")),
    ),
    db = path.join(root, "fixture.sqlite");
  t.after(() => rm(root, { recursive: true, force: true }));
  const store = new Store(db),
    ids: string[] = [];
  for (const status of ["queued", "running", "cancelling"]) {
    const s = store.createSession(),
      run = store.createRun(
        s,
        "message",
        "do not repeat tool side effects",
        [],
      );
    ids.push(s.id);
    store.updateRun(run.id, status);
    store.setStatus(s.id, status as "queued");
    store.addMessage(s.id, "user", "preserve original");
    store.addMessage(s.id, "assistant", "preserve partial answer");
    store.setNative(s.id, `native-${status}`);
    store.setContext(s.id, {
      used: 321,
      limit: 480000,
      estimated: false,
      stale: false,
      updatedAt: new Date().toISOString(),
      source: "fixture",
    });
  }
  store.requestDelete(ids[2]!);
  store.close();
  const reopened = new Store(db);
  try {
    assert.deepEqual(
      reopened.db
        .prepare("SELECT status FROM runs ORDER BY rowid")
        .all()
        .map((r) => r.status),
      ["interrupted", "interrupted", "interrupted"],
    );
    for (const id of ids) {
      const s = reopened.getSession(id);
      assert.equal(s.status, "interrupted");
      assert.equal(s.context?.used, 321);
      assert.equal(s.context?.stale, true);
      assert.ok(s.nativeSessionId);
      assert.ok(reopened.isQuarantined(s.workspaceId));
      assert.deepEqual(
        reopened.messages(id).map((m) => m.content),
        ["preserve original", "preserve partial answer"],
      );
      assert.equal(reopened.allEvents(id).at(-1)?.data.code, "interrupted");
    }
    assert.equal(reopened.listSessions().length, 3);
    assert.equal(reopened.getSession(ids[2]!).deleteRequested, true);
    const before = reopened.allEvents(ids[0]!).length;
    reopened.close();
    const twice = new Store(db);
    try {
      assert.equal(twice.allEvents(ids[0]!).length, before);
    } finally {
      twice.close();
    }
  } catch (error) {
    try {
      reopened.close();
    } catch {}
    throw error;
  }
});

test("events have independent monotonic per-session ids and durable pagination", async (t) => {
  const { store, session } = await setup(t),
    second = store.createSession();
  for (let i = 0; i < 1050; i++)
    store.emit(session.id, "progress", { kind: "fixture", label: String(i) });
  assert.equal(
    store.emit(second.id, "progress", { kind: "fixture", label: "independent" })
      .id,
    1,
  );
  assert.equal(store.allEvents(session.id).length, 1050);
  assert.deepEqual(
    store.replay(session.id, 1048).map((e) => e.id),
    [1049, 1050],
  );
  assert.equal(store.replay(session.id, 0, 2).length, 2);
});

test("assistant delta commits text and event together and notifies snapshot observers only after commit", async (t) => {
  const { store, session } = await setup(t);
  const run = store.createRun(session, "message", "transaction fixture", []);
  const message = store.addMessage(
    session.id,
    "assistant",
    "Original. ",
    run.id,
  );
  const observations: ReturnType<Store["snapshot"]>[] = [];
  store.events.on(session.id, () => {
    observations.push(store.snapshot(session.id));
  });
  store.db.exec(
    "CREATE TRIGGER reject_fixture_delta BEFORE INSERT ON events WHEN NEW.type='assistant_delta' BEGIN SELECT RAISE(ABORT, 'fixture event insert failure'); END;",
  );
  assert.throws(
    () => store.appendDelta(session.id, message.id, "Must roll back.", run.id),
    /fixture event insert failure/,
  );
  assert.equal(store.message(message.id).content, "Original. ");
  assert.equal(store.allEvents(session.id).length, 0);
  assert.equal(
    observations.length,
    0,
    "failed persistence cannot reach a live subscriber",
  );
  store.db.exec("DROP TRIGGER reject_fixture_delta");
  const event = store.appendDelta(session.id, message.id, "Committed.", run.id);
  assert.equal(event.id, 1);
  assert.equal(
    observations.length,
    1,
    "subscriber can open a snapshot transaction after commit",
  );
  assert.equal(observations[0]!.messages[0]!.content, "Original. Committed.");
  assert.deepEqual(observations[0]!.events, [event]);
  assert.equal(store.message(message.id).content, "Original. Committed.");
});

test("safe identifiers and filenames never carry traversal or executable header characters", () => {
  for (const value of [
    "..",
    "../x",
    "/tmp",
    "a/b",
    "a\\b",
    "a.b",
    "",
    "x\0y",
    "x".repeat(81),
  ])
    assert.throws(() => requireId(value));
  assert.equal(requireId("UUID_123-valid"), "UUID_123-valid");
  assert.equal(safeName("..\\folder\\..\\evil\r\nname.txt"), "evil__name.txt");
  assert.equal(safeName("../../.hidden.txt"), "hidden.txt");
  assert.equal(safeName(".."), "file");
  assert.equal(safeName("x".repeat(1000)).length, 150);
});

test("upload is streamed/bounded, removes partial file and metadata on size failure", async (t) => {
  const { files, store, session, root } = await setup(t);
  assert.equal(
    MAX_UPLOAD,
    50 * 1024 * 1024,
    "approved coordination cap is 50 MiB",
  );
  const f = await files.upload(
    session.id,
    "../../sample.txt",
    "text/plain",
    Readable.from(["a", "b", "c"]),
  );
  assert.equal(f.name, "sample.txt");
  assert.equal(f.size, 3);
  assert.equal(
    await readFile(path.join(root, "uploads", f.path), "utf8"),
    "abc",
  );
  const chunk = Buffer.alloc(1024 * 1024, 120);
  async function* oversized() {
    for (let i = 0; i <= MAX_UPLOAD / chunk.length; i++) yield chunk;
  }
  await assert.rejects(
    files.upload(
      session.id,
      "oversized.txt",
      "text/plain",
      Readable.from(oversized()),
    ),
    (error: unknown) =>
      !!error &&
      typeof error === "object" &&
      "statusCode" in error &&
      error.statusCode === 413,
  );
  assert.equal(store.files(session.id, "attachment").length, 1);
  assert.equal((await readdir(path.join(root, "uploads"))).length, 1);
  assert.equal((await files.attachments(session.id, [f.id])).length, 1);
  assert.equal(
    (await files.attachments(session.id, [f.id])).length,
    1,
    "multiple prompts may reuse one upload",
  );
});

test("registered artifacts are snapshots; traversal, symlinks, hidden paths and hardlinks fail closed", async (t) => {
  const { root, files, session, workspace } = await setup(t);
  await mkdir(path.join(workspace, "nested"));
  await writeFile(
    path.join(workspace, "nested", "safe.txt"),
    "immutable original",
  );
  const f = await files.registerArtifact(session.id, "nested/safe.txt");
  await writeFile(path.join(workspace, "nested", "safe.txt"), "mutated");
  const snapshot = await files.download(f.id);
  let text = "";
  for await (const chunk of snapshot.stream) text += chunk;
  assert.equal(text, "immutable original");
  await writeFile(path.join(root, "outside.txt"), "must never publish");
  await symlink(
    path.join(root, "outside.txt"),
    path.join(workspace, "linked.txt"),
  );
  await symlink(path.join(root), path.join(workspace, "linked-parent"));
  await link(
    path.join(root, "outside.txt"),
    path.join(workspace, "hardlinked.txt"),
  );
  await writeFile(path.join(workspace, ".hidden"), "private");
  for (const candidate of [
    "../outside.txt",
    path.join(root, "outside.txt"),
    "linked.txt",
    "linked-parent/outside.txt",
    "hardlinked.txt",
    ".hidden",
  ])
    await assert.rejects(
      files.registerArtifact(session.id, candidate),
      unsafe,
      candidate,
    );
  const candidate = path.join(root, "artifacts", f.id);
  await rm(candidate);
  await symlink(path.join(root, "outside.txt"), candidate);
  await assert.rejects(files.download(f.id), unsafe);
});

test("space and Unicode filenames remain safe through attachment projection and artifact snapshots", async (t) => {
  const { files, session, workspace } = await setup(t);
  const upload = await files.upload(
    session.id,
    "načrt prostora 東京.txt",
    "text/plain",
    Readable.from(["Unicode filename fixture"]),
  );
  assert.equal(upload.name, "na_rt prostora __.txt");
  const projected = await files.attachments(session.id, [upload.id]);
  assert.ok(projected[0]!.path.startsWith(workspace + path.sep));
  assert.ok(projected[0]!.path.includes(" "));
  assert.equal(
    await readFile(projected[0]!.path, "utf8"),
    "Unicode filename fixture",
  );
  const source = path.join(workspace, "izhod 東京 spaces.txt");
  await writeFile(source, "Unicode path snapshot");
  const artifact = await files.registerArtifact(session.id, source);
  assert.equal(artifact.name, "izhod __ spaces.txt");
  const download = await files.download(artifact.id);
  let body = "";
  for await (const chunk of download.stream) body += chunk;
  assert.equal(body, "Unicode path snapshot");
});

test("attachment projection rejects cross-chat IDs and workspace upload directory symlinks", async (t) => {
  const { root, files, store, session, workspace } = await setup(t),
    other = store.createSession();
  await files.prepare(other.id, other.workspaceId);
  const f = await files.upload(
    session.id,
    "file.txt",
    "text/plain",
    Readable.from(["safe"]),
  );
  await assert.rejects(
    files.attachments(other.id, [f.id]),
    (error: unknown) =>
      !!error &&
      typeof error === "object" &&
      "code" in error &&
      error.code === "invalid_attachment",
  );
  await symlink(root, path.join(workspace, ".uploads"));
  await assert.rejects(files.attachments(session.id, [f.id]));
});
