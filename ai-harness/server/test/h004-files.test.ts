import assert from "node:assert/strict";
import test, { type TestContext } from "node:test";
import {
  mkdtemp,
  mkdir,
  realpath,
  rm,
  writeFile,
  readFile,
  symlink,
} from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { Readable } from "node:stream";
import { execFileSync } from "node:child_process";
import { createApp } from "../src/app.js";
import type { Artifact } from "../src/contracts.js";

async function fixture(t: TestContext) {
  const root = await realpath(
    await mkdtemp(path.join(tmpdir(), "h004-files-")),
  );
  const h = await createApp({
    dataDir: root,
    allowedOrigins: ["http://localhost"],
    launcher: "/not-executed",
    gatewayUrl: "http://127.0.0.1:1/v1",
    issueToken: () => "fixture-token",
    revokeToken: () => {},
    engineFactory: () => ({
      async start() {},
      async prompt() {},
      async cancel() {},
      async close() {},
    }),
  });
  t.after(async () => {
    await h.app.close();
    await rm(root, { recursive: true, force: true });
  });
  const session = h.store.getSession((await h.broker.createSession()).id);
  const request = (url: string) =>
    h.app.inject({ url, headers: { host: "localhost" } });
  const upload = (name: string, body: string, sessionId = session.id) =>
    h.files.upload(sessionId, name, "text/plain", Readable.from([body]));
  const output = async (
    runId: string,
    name: string,
    body: string,
    messageId?: string,
  ) => {
    await writeFile(
      path.join(h.files.workspace(session.workspaceId), name),
      body,
    );
    return h.files.registerArtifact(
      session.id,
      name,
      undefined,
      "text/plain",
      runId,
      messageId,
    );
  };
  const archive = async (url: string) => {
    const result = await request(url);
    assert.equal(result.statusCode, 200);
    const filename = path.join(root, "fixture.zip");
    await writeFile(filename, result.rawPayload);
    return JSON.parse(
      execFileSync(
        "python3",
        [
          "-c",
          "import zipfile,json,sys; z=zipfile.ZipFile(sys.argv[1]); print(json.dumps({'ok':z.testzip() is None,'files':{i.filename:z.read(i).decode() for i in z.infolist()}}))",
          filename,
        ],
        { encoding: "utf8" },
      ),
    );
  };
  return { ...h, root, session, request, upload, output, archive };
}

test("H004 reply ZIPs select persisted inputs and outputs, message ZIPs select only their uploads", async (t) => {
  const h = await fixture(t),
    s = h.session;
  const input = await h.upload("../duplicate.txt", "input one");
  const second = await h.upload("duplicate.txt", "input two");
  const unused = await h.upload("unused.txt", "unsubmitted");
  const run = h.store.createRun(s, "message", "fixture", [input.id, second.id]);
  const user = h.store.addMessage(s.id, "user", "fixture", run.id, [
    input.id,
    second.id,
  ]);
  const final = h.store.addMessage(
    s.id,
    "assistant",
    "fixture answer",
    run.id,
    [],
    undefined,
    { phase: "final" },
  );
  const generated = await h.output(
    run.id,
    "duplicate.txt",
    "output one",
    final.id,
  );
  const next = h.store.createRun(s, "message", "next", [input.id]);
  h.store.addMessage(s.id, "user", "next", next.id, [input.id]);
  await h.output(next.id, "other.txt", "other reply");
  const snapshots = h.store.snapshot(s.id);
  const publicRun = snapshots.runs.find((r) => r.id === run.id)!;
  assert.deepEqual(publicRun.attachmentIds, [input.id, second.id]);
  assert.deepEqual(publicRun.artifactIds, [generated.id]);
  assert.equal(
    publicRun.zipUrl,
    undefined,
    "legacy artifacts-only threshold remains unchanged",
  );
  const combined = await h.archive(publicRun.filesZipUrl!);
  assert.equal(combined.ok, true);
  assert.deepEqual(Object.values(combined.files), [
    "output one",
    "input one",
    "input two",
  ]);
  assert.deepEqual(Object.keys(combined.files), [
    "1-duplicate.txt",
    "2-duplicate.txt",
    "3-duplicate.txt",
  ]);
  const uploads = await h.archive(h.store.message(user.id).zipUrl!);
  assert.deepEqual(Object.values(uploads.files), ["input one", "input two"]);
  assert.equal(uploads.ok, true);
  assert.equal(
    h.store.file(input.id).runId,
    null,
    "reused uploads retain many-to-many membership",
  );
  assert.ok(!JSON.stringify(combined.files).includes("unsubmitted"));
  assert.equal(
    await readFile(path.join(h.root, "artifacts", generated.path), "utf8"),
    "output one",
  );
  assert.equal(
    await readFile(path.join(h.root, "uploads", input.path), "utf8"),
    "input one",
  );
  const unownedRun = h.store.createRun(s, "message", "empty", []);
  assert.equal(
    (await h.request(`/api/sessions/${s.id}/runs/${unownedRun.id}/files.zip`))
      .statusCode,
    404,
  );
  assert.ok(unused.id);
});

test("H004 ZIPs reject cross-chat, invalid memberships, caller selection, unsafe paths and symlinks", async (t) => {
  const h = await fixture(t),
    s = h.session;
  const other = h.store.getSession((await h.broker.createSession()).id);
  const own = await h.upload("owned.txt", "owned");
  const foreign = await h.upload("foreign.txt", "foreign", other.id);
  const run = h.store.createRun(s, "message", "fixture", [own.id]);
  const message = h.store.addMessage(s.id, "user", "fixture", run.id, [own.id]);
  const output = await h.output(run.id, "output.txt", "output");
  const runUrl = `/api/sessions/${s.id}/runs/${run.id}/files.zip`;
  const messageUrl = `/api/sessions/${s.id}/messages/${message.id}/files.zip`;
  assert.equal(
    (await h.request(`/api/sessions/${other.id}/runs/${run.id}/files.zip`))
      .statusCode,
    404,
  );
  assert.equal(
    (
      await h.request(
        `/api/sessions/${other.id}/messages/${message.id}/files.zip`,
      )
    ).statusCode,
    404,
  );
  assert.equal(
    (await h.request(`${runUrl}?fileId=${foreign.id}`)).statusCode,
    400,
  );
  assert.equal(
    (await h.request(`${messageUrl}?path=../../outside`)).statusCode,
    400,
  );
  const origin = await h.app.inject({
    url: runUrl,
    headers: { host: "localhost", origin: "http://evil.invalid" },
  });
  assert.equal(origin.statusCode, 403);
  h.store.db
    .prepare("UPDATE runs SET attachment_ids=? WHERE id=?")
    .run(JSON.stringify([own.id, foreign.id]), run.id);
  assert.equal((await h.request(runUrl)).statusCode, 404);
  assert.equal(h.store.runSnapshot(run.id).filesZipUrl, undefined);
  h.store.db
    .prepare("UPDATE messages SET attachment_ids=? WHERE id=?")
    .run(JSON.stringify([own.id, foreign.id]), message.id);
  assert.equal((await h.request(messageUrl)).statusCode, 404);
  h.store.db
    .prepare("UPDATE runs SET attachment_ids=? WHERE id=?")
    .run(JSON.stringify([own.id, own.id]), run.id);
  assert.deepEqual(
    Object.values((await h.archive(runUrl)).files),
    ["output", "owned"],
    "one upload is archived only once",
  );
  h.store.db
    .prepare("UPDATE files SET path=? WHERE id=?")
    .run("../outside", own.id);
  assert.equal((await h.request(runUrl)).statusCode, 400);
  h.store.db
    .prepare("UPDATE files SET path=? WHERE id=?")
    .run(own.path, own.id);
  await rm(path.join(h.root, "uploads", own.path));
  await symlink(
    path.join(h.root, "artifacts", output.path),
    path.join(h.root, "uploads", own.path),
  );
  assert.equal((await h.request(runUrl)).statusCode, 400);
  h.store.db
    .prepare("UPDATE runs SET attachment_ids=? WHERE id=?")
    .run("[]", run.id);
  const foreignFinal = h.store.addMessage(
    other.id,
    "assistant",
    "foreign",
    undefined,
    [],
  );
  h.store.db
    .prepare("UPDATE h002_file_refs SET message_id=? WHERE file_id=?")
    .run(foreignFinal.id, output.id);
  assert.equal((await h.request(runUrl)).statusCode, 404);
});

test("H004 historical aliases require an owned exact workspace link and unique direct-child catalog name", async (t) => {
  const h = await fixture(t),
    s = h.session;
  const run = h.store.createRun(s, "message", "fixture", []);
  const sourcePath = path.join(h.files.workspace(s.workspaceId), "chart.png");
  const content = `Before\n\n![Chart](${sourcePath})\n\nAfter`;
  const final = h.store.addMessage(
    s.id,
    "assistant",
    content,
    run.id,
    [],
    undefined,
    { phase: "final" },
  );
  const file = await h.output(
    run.id,
    "chart.png",
    "immutable fixture",
    final.id,
  );
  h.store.db
    .prepare("DELETE FROM h004_file_sources WHERE file_id=?")
    .run(file.id);
  const value = async () =>
    (await h.request(`/api/sessions/${s.id}`))
      .json()
      .artifacts.find((a: Artifact) => a.id === file.id) as Artifact;
  assert.deepEqual((await value()).referencePaths, [sourcePath]);
  assert.equal(
    h.store.message(final.id).content,
    content,
    "read-time aliases do not rewrite history",
  );
  await writeFile(sourcePath, "different fixture");
  assert.equal(
    (await value()).referencePaths,
    undefined,
    "same name and size with different bytes fails closed",
  );
  await rm(sourcePath);
  assert.equal(
    (await value()).referencePaths,
    undefined,
    "missing original does not imply identity",
  );
  await symlink(path.join(h.root, "artifacts", file.path), sourcePath);
  assert.equal(
    (await value()).referencePaths,
    undefined,
    "symlink source fails closed",
  );
  await rm(sourcePath);
  await writeFile(sourcePath, "immutable fixture");
  const oldEventCount = h.store.allEvents(s.id).length;
  h.store.snapshot(s.id);
  assert.equal(h.store.allEvents(s.id).length, oldEventCount);
  const badTargets = [
    `/another/workspace/chart.png`,
    `${h.files.workspace(s.workspaceId)}/subdir/chart.png`,
    `${h.files.workspace(s.workspaceId)}/../${s.workspaceId}/chart.png`,
    `chart.png`,
    `file://${sourcePath}`,
    `/etc/chart.png`,
  ];
  for (const target of badTargets) {
    h.store.db
      .prepare("UPDATE messages SET content=? WHERE id=?")
      .run(`![Chart](${target})`, final.id);
    assert.equal((await value()).referencePaths, undefined, target);
  }
  h.store.db
    .prepare("UPDATE messages SET content=? WHERE id=?")
    .run(content, final.id);
  await h.output(run.id, "chart.png", "second snapshot", final.id);
  assert.equal(
    (await value()).referencePaths,
    undefined,
    "ambiguous catalog filenames are not guessed",
  );
  const another = h.store.createRun(s, "message", "another", []);
  h.store.db
    .prepare("UPDATE h002_file_refs SET run_id=? WHERE file_id=?")
    .run(another.id, file.id);
  assert.equal(
    (await value()).referencePaths,
    undefined,
    "same-chat other-run text cannot authorize aliases",
  );
});

test("H004 new exact nested/renamed source aliases are atomic and managed aliases precede workspace-copy SSE", async (t) => {
  const h = await fixture(t),
    s = h.session;
  const run = h.store.createRun(s, "message", "fixture", []);
  const workspace = h.files.workspace(s.workspaceId);
  await mkdir(path.join(workspace, "nested"));
  const sourcePath = path.join(workspace, "nested", "source.png");
  await writeFile(sourcePath, "new immutable output");
  const final = h.store.addMessage(
    s.id,
    "assistant",
    `![new](${sourcePath})`,
    run.id,
    [],
    undefined,
    { phase: "final" },
  );
  const saved = await h.files.registerArtifact(
    s.id,
    "nested/source.png",
    "renamed.png",
    "image/png",
    run.id,
    final.id,
  );
  assert.equal(saved.sourcePath, "nested/source.png");
  assert.deepEqual(
    (h.store.publicFile(h.store.file(saved.id)) as Artifact).referencePaths,
    ["nested/source.png", sourcePath],
  );
  await rm(sourcePath);
  assert.deepEqual(
    (h.store.publicFile(h.store.file(saved.id)) as Artifact).referencePaths,
    ["nested/source.png", sourcePath],
    "new mapping is registered snapshot provenance, independent of workspace edits",
  );
  h.store.db.exec(
    "CREATE TRIGGER fail_source BEFORE INSERT ON h004_file_sources BEGIN SELECT RAISE(FAIL,'fixture'); END",
  );
  assert.throws(() =>
    h.store.saveFile({
      id: "atomic-failure",
      sessionId: s.id,
      kind: "artifact",
      path: "atomic-failure",
      name: "atomic.png",
      mimeType: "image/png",
      size: 1,
      sourcePath: "atomic.png",
      runId: run.id,
    }),
  );
  assert.equal(
    h.store.db.prepare("SELECT id FROM files WHERE id=?").get("atomic-failure"),
    undefined,
  );
  h.store.db.exec("DROP TRIGGER fail_source");
  const managed = h.store.saveFile({
    id: "managed",
    sessionId: s.id,
    kind: "artifact",
    path: "managed",
    name: "image-fixture-job.png",
    mimeType: "image/png",
    size: 1,
    runId: run.id,
    image: {
      jobId: "fixture-job",
      actualSize: "1024x1024",
      model: "fixture",
      seed: 1,
      sha256: "fixture",
    },
  });
  assert.equal(
    h.store.db
      .prepare("SELECT path FROM h003_image_outputs WHERE job_id=?")
      .get("fixture-job"),
    undefined,
  );
  h.store.emit(
    s.id,
    "artifact",
    { artifact: h.store.publicFile(managed) },
    run.id,
  );
  const event = h.store.allEvents(s.id).at(-1)!.data.artifact as Artifact;
  assert.deepEqual(event.referencePaths, ["image-fixture-job.png"]);
  assert.deepEqual(
    (h.store.publicFile(h.store.file(managed.id)) as Artifact).referencePaths,
    event.referencePaths,
  );
  h.store.db.prepare("UPDATE sessions SET deleted=1 WHERE id=?").run(s.id);
  assert.doesNotThrow(() => h.store.publicFile(managed), "late internal image publication survives soft deletion");
  assert.equal((await h.request(`/api/sessions/${s.id}`)).statusCode, 404);
  assert.equal((await h.request(`/api/artifacts/${managed.id}/download`)).statusCode, 404);
});
