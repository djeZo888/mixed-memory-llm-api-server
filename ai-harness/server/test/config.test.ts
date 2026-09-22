import test from "node:test";
import assert from "node:assert/strict";
import {
  mkdtemp,
  realpath,
  writeFile,
  chmod,
  symlink,
  link,
  rm,
} from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { readProtectedCredential } from "../src/main.js";

test("explicit credential loader reads only synthetic protected regular file and rejects unsafe identities", async (t) => {
  const root = await realpath(await mkdtemp(join(tmpdir(), "h001-config-")));
  t.after(() => rm(root, { recursive: true, force: true }));
  const file = join(root, "fixture.key");
  await writeFile(file, "synthetic-fixture-only\n", { mode: 0o600 });
  assert.equal(await readProtectedCredential(file), "synthetic-fixture-only");
  await chmod(file, 0o644);
  await assert.rejects(readProtectedCredential(file), /protected/);
  await chmod(file, 0o600);
  await symlink(file, join(root, "link"));
  await assert.rejects(readProtectedCredential(join(root, "link")), /Unsafe/);
  await link(file, join(root, "hardlink"));
  await assert.rejects(readProtectedCredential(file), /protected/);
  await rm(join(root, "hardlink"));
  await writeFile(file, "invalid credential with spaces", { mode: 0o600 });
  await assert.rejects(readProtectedCredential(file), /Invalid/);
  await writeFile(file, "x".repeat(8193), { mode: 0o600 });
  await assert.rejects(readProtectedCredential(file), /identity/);
});

test("a second app cannot reinterpret the live owner runs as a crash", async (t) => {
  const { createApp } = await import("../src/app.js");
  const root = await realpath(await mkdtemp(join(tmpdir(), "h001-owner-")));
  t.after(() => rm(root, { recursive: true, force: true }));
  const options = {
    dataDir: root,
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
  };
  const first = await createApp(options);
  try {
    const session = await first.broker.createSession();
    const s = first.store.getSession(session.id);
    const run = first.store.createRun(s, "message", "owned work", []);
    first.store.updateRun(run.id, "running");
    await assert.rejects(createApp(options), /Another server owns/);
    assert.equal(first.store.isQuarantined(s.workspaceId), false);
    first.store.updateRun(run.id, "completed");
  } finally {
    await first.app.close();
  }
  const second = await createApp(options);
  await second.app.close();
});

test("failed app initialization releases ownership for a corrected retry", async (t) => {
  const { createApp } = await import("../src/app.js");
  const root = await realpath(
    await mkdtemp(join(tmpdir(), "h001-init-retry-")),
  );
  t.after(() => rm(root, { recursive: true, force: true }));
  const options = {
    dataDir: root,
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
  };
  await symlink(root, join(root, "uploads"));
  await assert.rejects(createApp(options), /Symbolic links/);
  await rm(join(root, "uploads"));
  const app = await createApp(options);
  await app.app.close();
});
