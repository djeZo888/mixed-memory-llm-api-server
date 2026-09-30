import assert from "node:assert/strict";
import test from "node:test";
import { mkdtemp, rm, writeFile, readFile, cp, mkdir, symlink } from "node:fs/promises";
import { execFileSync } from "node:child_process";
import { fileURLToPath, pathToFileURL } from "node:url";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createApp } from "../src/app.js";
import { loadNewChatEngine } from "../src/system-registry.js";
import { CODEX_PIN } from "../src/codex-engine.js";
import { CODEX_MODEL_POLICY } from "../src/codex-launcher.js";

const inert = () => ({ async start() {}, async prompt() {}, async cancel() {}, async close() {} });
for (const qualified of [true, false]) {
  test(`SOURCE_FIXTURE central Codex new-chat default with qualification ${qualified} preserves old sessions and explicit MiniMax`, async t => {
    const dataDir = await mkdtemp(join(tmpdir(), "h037-default-"));
    const fixture = await createApp({ dataDir, allowedOrigins: ["http://localhost"],
      launcher: "/fixture/not-executed", gatewayUrl: "http://127.0.0.1:1/v1", issueToken: () => "fixture", revokeToken: () => {},
      engineFactory: inert, ...(qualified ? { codexEngineFactory: inert } : {}),
      enginePolicy: { codex: { enabled: qualified, protocolQualified: qualified, engineVersion: CODEX_PIN.version, modelPolicyVersion: CODEX_MODEL_POLICY } },
    });
    t.after(async () => { await fixture.app.close(); await rm(dataDir, { recursive: true, force: true }); });
    const oldMini = await fixture.broker.createSession(undefined, "minimax");
    const oldCodex = fixture.store.createSession(undefined, "codex", { engineVersion: CODEX_PIN.version, modelPolicyVersion: CODEX_MODEL_POLICY });
    fixture.store.setNative(oldMini.id, "original-minimax", "minimax");
    fixture.store.setNative(oldCodex.id, "original-codex", "codex");
    fixture.store.setNativeState(oldCodex.id, "codex", { ownership: "idle", activeTurnId: null, eventCursor: 37 });
    fixture.store.addMessage(oldMini.id, "user", "retained MiniMax history");
    fixture.store.addMessage(oldCodex.id, "assistant", "retained Codex history");
    const original = [oldMini.id, oldCodex.id].map(id => fixture.store.snapshot(id));
    const file = join(fixture.files.workspace(oldCodex.workspaceId), "retained.txt");
    await fixture.files.prepare(oldCodex.id, oldCodex.workspaceId);
    await writeFile(file, "original file bytes");
    const headers = { host: "localhost" };
    assert.equal(loadNewChatEngine(), "codex");
    const health = (await fixture.app.inject({ url: "/api/health", headers })).json();
    assert.equal(health.engines.default, "codex");
    assert.equal(health.engines.codex.available, qualified);
    const created = await fixture.app.inject({ method: "POST", url: "/api/sessions", headers, payload: {} });
    assert.equal(created.statusCode, qualified ? 200 : 409);
    if (qualified) assert.equal(created.json().session.engineKind, "codex");
    const alternate = await fixture.app.inject({ method: "POST", url: "/api/sessions", headers, payload: { engineKind: "minimax" } });
    assert.equal(alternate.statusCode, 200); assert.equal(alternate.json().session.engineKind, "minimax");
    for (const [index, id] of [oldMini.id, oldCodex.id].entries())
      assert.deepEqual({ ...fixture.store.snapshot(id), environment: original[index]!.environment }, original[index]);
    assert.equal(fixture.store.getSession(oldCodex.id).nativeSessionId, "original-codex");
    assert.equal(fixture.store.getSession(oldMini.id).nativeSessionId, "original-minimax");
    assert.equal(fixture.store.getSession(oldCodex.id).nativeState.eventCursor, 37);
    assert.equal(await readFile(file, "utf8"), "original file bytes");
  });
}
test("SOURCE_FIXTURE new-chat default and other status catalog survive a missing optional frontier selection", async t => {
  const root = await mkdtemp(join(tmpdir(), "h037-no-frontier-"));
  t.after(() => rm(root, { recursive: true, force: true }));
  const harness = fileURLToPath(new URL("../../", import.meta.url));
  await cp(join(harness, "server/src"), join(root, "server/src"), { recursive: true });
  await cp(join(harness, "server/package.json"), join(root, "server/package.json"));
  await symlink(join(harness, "server/node_modules"), join(root, "server/node_modules"));
  await mkdir(join(root, "config"));
  await cp(join(harness, "config/system-registry.json"), join(root, "config/system-registry.json"));
  const source = pathToFileURL(join(root, "server/src/system-registry.ts")).href;
  const code = `const m=await import(${JSON.stringify(source)}); if(m.loadNewChatEngine()!=="codex") throw Error("default changed"); const r=m.loadSystemRegistry(); if(r.selected_frontier!==undefined || !r.services.some(s=>s.id==="qwen-gpu0")) throw Error("optional dependency affected catalog");`;
  execFileSync(process.execPath, ["--import", join(harness, "server/node_modules/tsx/dist/loader.mjs"), "--input-type=module", "--eval", code], { cwd: root, timeout: 5000 });
});
