import assert from "node:assert/strict";
import test, { type TestContext } from "node:test";
import { mkdtemp, realpath, readFile, readdir, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { Readable } from "node:stream";
import { Store } from "../src/store.js";
import { Files } from "../src/files.js";

async function setup(t: TestContext) {
  const root = await realpath(
    await mkdtemp(path.join(tmpdir(), "h002-save-file-")),
  );
  const store = new Store(path.join(root, "fixture.sqlite"));
  const files = new Files(root, store);
  await files.init();
  const session = store.createSession();
  t.after(async () => {
    store.close();
    await rm(root, { recursive: true, force: true });
  });
  return { root, store, files, session };
}

function rows(store: Store) {
  return ["files", "h002_file_names", "h002_file_refs"].map((table) =>
    store.db.prepare(`SELECT * FROM ${table} ORDER BY rowid`).all(),
  );
}

for (const nested of [false, true]) {
  for (const table of ["h002_file_names", "h002_file_refs"]) {
    test(`saveFile rolls back new rows on ${table} failure (nested=${nested})`, async (t) => {
      const { root, store, files, session } = await setup(t);
      store.db.exec(`CREATE TRIGGER reject_companion AFTER INSERT ON ${table}
        BEGIN SELECT RAISE(ABORT, 'injected companion failure'); END`);
      if (nested) store.db.exec("BEGIN IMMEDIATE");
      store.db
        .prepare("UPDATE sessions SET title=? WHERE id=?")
        .run("caller change", session.id);
      const before = rows(store);
      await assert.rejects(
        files.upload(
          session.id,
          "načrt.txt",
          "text/plain",
          Readable.from(["new bytes"]),
        ),
        /injected companion failure/,
      );
      assert.deepEqual(
        rows(store),
        before,
        "no base or companion rows survive",
      );
      assert.deepEqual(await readdir(path.join(root, "uploads")), []);
      assert.equal(store.getSession(session.id).title, "caller change");
      if (nested) store.db.exec("COMMIT");
      store.db.exec("DROP TRIGGER reject_companion");
      const saved = await files.upload(
        session.id,
        "retry.txt",
        "text/plain",
        Readable.from(["retry"]),
      );
      assert.equal(
        store.file(saved.id).name,
        "retry.txt",
        "connection remains usable",
      );
    });
  }

  test(`saveFile preserves existing file and all metadata on update failure (nested=${nested})`, async (t) => {
    const { root, store, files, session } = await setup(t);
    const original = await files.upload(
      session.id,
      "original 東京.txt",
      "text/plain",
      Readable.from(["original bytes"]),
    );
    const before = rows(store);
    store.db
      .exec(`CREATE TRIGGER reject_companion AFTER INSERT ON h002_file_names
      BEGIN SELECT RAISE(ABORT, 'injected companion failure'); END`);
    if (nested) store.db.exec("BEGIN IMMEDIATE");
    store.db
      .prepare("UPDATE sessions SET title=? WHERE id=?")
      .run("caller change", session.id);
    assert.throws(
      () =>
        store.saveFile({
          ...original,
          id: "replacement-id",
          name: "changed.txt",
          mimeType: "image/png",
          size: 999,
          runId: "changed-run",
          messageId: "changed-message",
        }),
      /injected companion failure/,
    );
    assert.deepEqual(
      rows(store),
      before,
      "base update and companion replacement roll back",
    );
    assert.equal(
      await readFile(path.join(root, "uploads", original.path), "utf8"),
      "original bytes",
    );
    assert.equal(store.getSession(session.id).title, "caller change");
    if (nested) store.db.exec("COMMIT");
    store.db.exec("DROP TRIGGER reject_companion");
    const saved = store.saveFile({ ...original, name: "renamed.txt" });
    assert.equal(saved.id, original.id);
    assert.equal(saved.name, "renamed.txt");
  });
}

test("successful saveFile does not commit an enclosing caller transaction", async (t) => {
  const { store, session } = await setup(t);
  const before = rows(store);
  store.db.exec("BEGIN IMMEDIATE");
  store.saveFile({
    id: "nested-file",
    sessionId: session.id,
    kind: "artifact",
    path: "fixture.txt",
    name: "fixture.txt",
    mimeType: "text/plain",
    size: 3,
    runId: "fixture-run",
    messageId: "fixture-message",
  });
  assert.equal(store.file("nested-file").runId, "fixture-run");
  store.db.exec("ROLLBACK");
  assert.deepEqual(rows(store), before);
});
