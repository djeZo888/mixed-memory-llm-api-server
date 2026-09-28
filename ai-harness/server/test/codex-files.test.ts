import assert from "node:assert/strict";
import test from "node:test";
import {
  mkdtemp,
  realpath,
  mkdir,
  writeFile,
  readFile,
  symlink,
  rm,
} from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { Readable } from "node:stream";
import { Store } from "../src/store.js";
import { Files } from "../src/files.js";
import { codexInput } from "../src/codex-input.js";
import { createApp } from "../src/app.js";
const policy = {
  codex: {
    enabled: true,
    protocolQualified: true,
    engineVersion: "fixture",
    modelPolicyVersion: "fixture",
  },
};

test("workspace file references preserve bytes, reject traversal/symlinks/hard media before native dispatch", async (t) => {
  const root = await realpath(await mkdtemp(join(tmpdir(), "h021-input-")));
  t.after(() => rm(root, { recursive: true, force: true }));
  const workspace = join(root, "workspace");
  await mkdir(workspace);
  await writeFile(join(workspace, "source.py"), "assert 2 + 2 == 4");
  await writeFile(join(root, "outside"), "secret");
  await symlink(join(root, "outside"), join(workspace, "linked"));
  const file = {
    path: join(workspace, "source.py"),
    name: "source.py",
    mimeType: "text/x-python",
  };
  const input = await codexInput("Review", workspace, [file]);
  assert.equal(input[0].type, "text");
  assert.match(input[0].text, /"path":"source.py"/);
  assert.doesNotMatch(input[0].text, /assert 2/);
  for (const path of [
    "../outside",
    join(root, "outside"),
    "source.py/../source.py",
    "linked",
    "a\0b",
    "..\\outside",
  ])
    await assert.rejects(codexInput("Review", workspace, [{ ...file, path }]));
  for (const mimeType of ["image/png", "audio/wav", "video/mp4"])
    await assert.rejects(
      codexInput("Review", workspace, [{ ...file, mimeType }]),
      /media is not qualified/,
    );
  assert.equal(await readFile(file.path, "utf8"), "assert 2 + 2 == 4");
});

test("same-workspace artifact/upload reuse retains originals and rejects cross-workspace IDs", async (t) => {
  const root = await realpath(await mkdtemp(join(tmpdir(), "h021-files-")));
  const store = new Store(join(root, "store.sqlite"));
  const files = new Files(join(root, "data"), store);
  await files.init();
  t.after(async () => {
    store.close();
    await rm(root, { recursive: true, force: true });
  });
  const a = store.createSession();
  const b = store.createSession(a.workspaceId, "codex", policy.codex);
  const other = store.createSession();
  await files.prepare(a.id, a.workspaceId);
  const upload = await files.upload(
    a.id,
    "evidence.txt",
    "text/plain",
    Readable.from(["immutable bytes"]),
  );
  const reused = await files.referenceAttachment(b.id, upload.id);
  assert.notEqual(reused.id, upload.id);
  assert.equal(reused.sessionId, b.id);
  const mapped = await files.attachments(b.id, [reused.id]);
  assert.equal(await readFile(mapped[0].path, "utf8"), "immutable bytes");
  await writeFile(
    join(files.workspace(a.workspaceId), "report.txt"),
    "artifact original",
  );
  const artifact = await files.registerArtifact(
    a.id,
    "report.txt",
    "report.txt",
    "text/plain",
  );
  const copy = await files.referenceAttachment(b.id, artifact.id);
  assert.equal(
    await readFile((await files.attachments(b.id, [copy.id]))[0].path, "utf8"),
    "artifact original",
  );
  assert.equal(
    await readFile(join(files.root, "artifacts", artifact.path), "utf8"),
    "artifact original",
  );
  await assert.rejects(
    files.referenceAttachment(other.id, artifact.id),
    /workspace/,
  );
  await assert.rejects(
    files.referenceAttachment(other.id, upload.id),
    /workspace/,
  );
  await assert.rejects(files.referenceAttachment(b.id, "../escape"));
  store.db
    .prepare("UPDATE files SET path=? WHERE id=?")
    .run("../outside", artifact.id);
  await assert.rejects(files.referenceAttachment(b.id, artifact.id), /path/);
});

test("Codex attachment workflow persists two turns and replay/history without resubmission; native media is explicit", async (t) => {
  const dataDir = await realpath(
    await mkdtemp(join(tmpdir(), "h021-file-api-")),
  );
  let prompts = 0;
  const seen: any[] = [];
  const instance = await createApp({
    dataDir,
    allowedOrigins: ["http://localhost"],
    engineFactory: () => ({
      async start() {},
      async prompt() {},
      async cancel() {},
      async close() {},
    }),
    launcher: "/unused",
    gatewayUrl: "http://fixture.invalid",
    issueToken: () => "fake-token",
    revokeToken() {},
    enginePolicy: policy,
    codexEngineFactory: (options) => ({
      async start() {},
      async prompt(text, files) {
        prompts++;
        seen.push({ text, files });
        options.onUpdate({
          type: "compaction",
          compactionId: "fixture",
          status: "start",
        });
        options.onUpdate({
          type: "context",
          used: null,
          estimated: false,
          source: "codex.compaction.awaiting-usage",
        });
        options.onUpdate({
          type: "compaction",
          compactionId: "fixture",
          status: "completed",
        });
        options.onUpdate({ type: "text", text: "read", channel: "final" });
      },
      async cancel() {},
      async close() {},
    }),
  });
  t.after(async () => {
    await instance.app.close();
    await rm(dataDir, { recursive: true, force: true });
  });
  const created = await instance.app.inject({
    headers: { host: "localhost" },
    method: "POST",
    url: "/api/sessions",
    payload: { engineKind: "codex" },
  });
  const id = created.json().session.id;
  const upload = await instance.files.upload(
    id,
    "note.txt",
    "text/plain",
    Readable.from(["known fact 731"]),
  );
  for (let n = 0; n < 2; n++) {
    const reply = await instance.app.inject({
      headers: { host: "localhost" },
      method: "POST",
      url: `/api/sessions/${id}/messages`,
      payload: { text: `read ${n}`, attachmentIds: [upload.id] },
    });
    assert.equal(reply.statusCode, 202);
    for (
      let i = 0;
      i < 100 && instance.store.getSession(id).status !== "idle";
      i++
    )
      await new Promise((r) => setTimeout(r, 5));
  }
  const snap = await instance.app.inject({
    url: `/api/sessions/${id}`,
    headers: { host: "localhost" },
  });
  assert.equal(snap.statusCode, 200);
  assert.equal(prompts, 2);
  assert.equal(
    snap.json().messages.filter((m: any) => m.role === "user").length,
    2,
  );
  assert.ok(
    snap
      .json()
      .messages.filter((m: any) => m.role === "user")
      .every((m: any) => m.attachmentIds.includes(upload.id)),
  );
  assert.equal(seen.length, 2);
  const ref = await instance.app.inject({
    headers: { host: "localhost" },
    method: "POST",
    url: `/api/sessions/${id}/references`,
    payload: { fileId: upload.id },
  });
  assert.equal(ref.statusCode, 201);
  const media = await instance.files.upload(
    id,
    "image.png",
    "image/png",
    Readable.from(["fake"]),
  );
  const rejected = await instance.app.inject({
    headers: { host: "localhost" },
    method: "POST",
    url: `/api/sessions/${id}/messages`,
    payload: { text: "recognize", attachmentIds: [media.id] },
  });
  assert.equal(rejected.statusCode, 400);
  assert.equal(rejected.json().error.code, "codex_media_unsupported");
  assert.equal(prompts, 2);
});
