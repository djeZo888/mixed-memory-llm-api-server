import assert from "node:assert/strict";
import test from "node:test";
import { mkdtemp, realpath, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createApp } from "../src/app.js";
const codexPolicy = {
  enabled: true,
  protocolQualified: true,
  engineVersion: "fixture",
  modelPolicyVersion: "fixture",
};
test("engine-aware preview rollback keeps Codex history/files readable, rejects its followup and runs MiniMax", async (t) => {
  const dataDir = await realpath(
    await mkdtemp(join(tmpdir(), "h021-rollback-")),
  );
  let codexCalls = 0,
    minimaxCalls = 0;
  const base = {
    dataDir,
    allowedOrigins: ["http://localhost"],
    launcher: "/unused",
    gatewayUrl: "http://fixture.invalid",
    issueToken: () => "fixture",
    revokeToken() {},
    engineFactory: () => ({
      async start() {},
      async prompt() {
        minimaxCalls++;
      },
      async cancel() {},
      async close() {},
    }),
    codexEngineFactory: () => ({
      async start() {},
      async prompt() {
        codexCalls++;
      },
      async cancel() {},
      async close() {},
    }),
  };
  let app = await createApp({ ...base, enginePolicy: { codex: codexPolicy } });
  const session = await app.broker.createSession(undefined, "codex");
  const stored = app.store.getSession(session.id);
  app.store.addMessage(session.id, "user", "Original Codex history");
  await writeFile(
    join(app.files.workspace(stored.workspaceId), "result.txt"),
    "Original artifact",
  );
  const artifact = await app.files.registerArtifact(
    session.id,
    "result.txt",
    "result.txt",
    "text/plain",
  );
  await app.app.close();
  app = await createApp({
    ...base,
    enginePolicy: { codex: { ...codexPolicy, enabled: false } },
  });
  t.after(async () => {
    await app.app.close();
    await rm(dataDir, { recursive: true, force: true });
  });
  const inject = (url: string, payload?: any) =>
    app.app.inject({
      headers: { host: "localhost" },
      method: payload ? "POST" : "GET",
      url,
      payload,
    });
  const history = await inject(`/api/sessions/${session.id}`);
  assert.equal(history.statusCode, 200);
  assert.equal(history.json().session.engineKind, "codex");
  assert.equal(history.json().messages[0].content, "Original Codex history");
  const download = await inject(`/api/artifacts/${artifact.id}/download`);
  assert.equal(download.statusCode, 200);
  assert.equal(download.body, "Original artifact");
  const followup = await inject(`/api/sessions/${session.id}/messages`, {
    text: "resume",
  });
  assert.equal(followup.statusCode, 409);
  assert.equal(followup.json().error.code, "codex_preview_unavailable");
  assert.equal(codexCalls, 0);
  const mini = (await inject("/api/sessions", {})).json().session;
  assert.equal(mini.engineKind, "minimax");
  assert.equal(
    (await inject(`/api/sessions/${mini.id}/messages`, { text: "run" }))
      .statusCode,
    202,
  );
  for (let i = 0; i < 100 && !minimaxCalls; i++)
    await new Promise((r) => setTimeout(r, 5));
  assert.equal(minimaxCalls, 1);
});
