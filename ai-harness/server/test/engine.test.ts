import test from "node:test";
import assert from "node:assert/strict";
import {
  mkdtemp,
  mkdir,
  readFile,
  rm,
  stat,
  symlink,
  writeFile,
} from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { randomBytes } from "node:crypto";
import { setTimeout as delay } from "node:timers/promises";
import {
  createEngine,
  EngineSettlementError,
  NATIVE_PERMISSION_POLICY,
  scopedPath,
  workspacePermission,
  workspaceShellPermission,
} from "../src/engine.js";
import type { EngineOptions, EngineUpdate } from "../src/contracts.js";

const launcher = fileURLToPath(
  new URL("./fixtures/engine-agent.mjs", import.meta.url),
);
async function harness(
  t: test.TestContext,
  config: Record<string, unknown> = {},
  nativeSessionId?: string,
) {
  const root = await mkdtemp(join(tmpdir(), "h001-acp-"));
  const profileDir = join(root, "profile");
  const workspace = join(root, "workspace");
  await mkdir(profileDir);
  await mkdir(workspace);
  await writeFile(join(profileDir, "fixture.json"), JSON.stringify(config));
  const updates: EngineUpdate[] = [];
  const nativeIds: string[] = [];
  let exits = 0;
  const token = randomBytes(32).toString("hex");
  const stderrPath = join(root, "engine.log");
  const engine = createEngine({
    launcher,
    sessionId: "public-chat",
    profileDir,
    workspace,
    nativeSessionId,
    gatewayUrl: "http://127.0.0.1:8081/v1",
    gatewayToken: token,
    stderrPath,
    shutdownTimeouts:
      config.shutdownTimeouts as EngineOptions["shutdownTimeouts"],
    onExit: () => {
      exits++;
    },
    onNativeSessionId: (value) => nativeIds.push(value),
    onUpdate: (value) => updates.push(value),
  });
  t.after(async () => {
    await engine.close().catch(() => undefined);
    await rm(root, { recursive: true, force: true });
  });
  return {
    engine,
    root,
    profileDir,
    workspace,
    updates,
    nativeIds,
    token,
    stderrPath,
    exits: () => exits,
    calls: async () =>
      JSON.parse(await readFile(join(profileDir, "calls.json"), "utf8")) as {
        method: string;
        [key: string]: any;
      }[],
  };
}

test("official SDK subprocess initialize/new/prompt updates and private launcher environment", async (t) => {
  const h = await harness(t);
  process.env.AI_HARNESS_TEST_SECRET = "ephemeral-test-only";
  process.env.AI_HARNESS_INFERENCE_KEY_FILE = "/not-read-by-fixture";
  try {
    await h.engine.start();
  } finally {
    delete process.env.AI_HARNESS_TEST_SECRET;
    delete process.env.AI_HARNESS_INFERENCE_KEY_FILE;
  }
  await h.engine.prompt("updates");
  assert.deepEqual(h.nativeIds, ["native-fixture-session"]);
  assert.deepEqual(
    h.updates.filter((value) => value.type === "text"),
    [{ type: "text", text: "fixture response" }],
  );
  assert.ok(!JSON.stringify(h.updates).includes("private reasoning"));
  assert.ok(
    h.updates.some(
      (value) =>
        value.type === "context" && value.used === 12345 && value.estimated,
    ),
  );
  assert.ok(
    h.updates.some(
      (value) => value.type === "progress" && value.detail?.length === 2048,
    ),
  );
  const calls = await h.calls();
  const launch = calls.find((call) => call.method === "launch")!;
  assert.equal(launch.upstreamKeyFileInherited, false);
  assert.equal(launch.inheritedSecret, false);
  assert.equal(launch.gatewayPresent, true);
  assert.equal(launch.nodeOptionsInherited, false);
  const init = calls.find((call) => call.method === "initialize")!;
  assert.equal(init.params.clientCapabilities.terminal, false);
  assert.deepEqual(init.params.clientCapabilities.fs, {
    readTextFile: false,
    writeTextFile: false,
  });
  await h.engine.close();
  const log = await readFile(h.stderrPath, "utf8");
  assert.ok(log.includes("[REDACTED]"));
  assert.ok(!log.includes(h.token));
});

for (const mode of ["resume", "load"])
  test(`native ${mode} restores without duplicating durable visible history`, async (t) => {
    const h = await harness(t, { restore: mode }, "persisted-native-id");
    await h.engine.start();
    assert.deepEqual(h.updates, []);
    assert.deepEqual(h.nativeIds, []);
    await h.engine.prompt("next turn");
    const calls = await h.calls();
    assert.equal(calls.filter((call) => call.method === mode).length, 1);
    assert.equal(calls.filter((call) => call.method === "new").length, 0);
    assert.equal(calls.filter((call) => call.method === "prompt").length, 1);
    assert.ok(!JSON.stringify(h.updates).includes("historical replay"));
  });

test("restoration and required delegation capabilities fail closed", async (t) => {
  const h = await harness(t, { restore: "none" }, "saved-id");
  await assert.rejects(h.engine.start(), /cannot safely restore/);
  assert.equal(
    (await h.calls()).filter(
      (call) => call.method === "new" || call.method === "prompt",
    ).length,
    0,
  );
  const unsupported = await harness(t, { noDelegation: true });
  await assert.rejects(
    unsupported.engine.start(),
    /delegation settlement capabilities/,
  );
});

test("workspace scoped permission requests allow safe local work and deny publication/traversal/symlinks", async (t) => {
  const h = await harness(t);
  await symlink(h.root, join(h.workspace, "link"));
  await h.engine.prompt("permissions");
  const results = (await h.calls()).filter(
    (call) => call.method === "permission_result",
  );
  assert.deepEqual(
    results.map((call) => call.result.outcome.optionId),
    ["yes", "no", "yes", "no", "no", "no"],
  );
});

test("cancellation sends real SDK cancel and stops delegation before returning", async (t) => {
  const h = await harness(t);
  await h.engine.start();
  const prompt = h.engine.prompt("wait");
  for (
    let i = 0;
    i < 50 && !(await h.calls()).some((call) => call.method === "prompt");
    i++
  )
    await delay(10);
  await h.engine.cancel();
  await prompt;
  const calls = await h.calls();
  assert.ok(calls.some((call) => call.method === "cancel"));
  assert.ok(
    calls.some((call) => call.method === "mcode/session/delegation/stop"),
  );
});

test("parent prompt completion retains workspace ownership until native children settle", async (t) => {
  const h = await harness(t);
  await h.engine.start();
  const start = Date.now();
  await h.engine.prompt("children");
  assert.ok(Date.now() - start >= 350);
  const updates = h.updates.filter(
    (value) => value.type === "progress" && value.kind === "subagent",
  );
  assert.deepEqual(
    updates.map((value) => (value.type === "progress" ? value.label : "")),
    ["worker: running", "worker: completed"],
  );
});

test("cancel after parent response stops still-running native children", async (t) => {
  const h = await harness(t);
  await h.engine.start();
  const prompt = h.engine.prompt("children-cancel");
  for (
    let i = 0;
    i < 50 &&
    !h.updates.some(
      (value) => value.type === "progress" && value.kind === "subagent",
    );
    i++
  )
    await delay(10);
  await h.engine.cancel();
  await prompt;
  assert.ok(
    h.updates.some(
      (value) => value.type === "progress" && value.label === "worker: stopped",
    ),
  );
});

test("invalid occupied context remains unknown, malformed child settlement is a failure", async (t) => {
  const h = await harness(t, { wrongContext: true });
  await h.engine.prompt("updates");
  assert.ok(
    h.updates.some((value) => value.type === "context" && value.used === null),
  );
  const malformed = await harness(t, { badSnapshot: true });
  await assert.rejects(
    malformed.engine.prompt("updates"),
    /settlement is unknown/,
  );
});

test("attachments use bounded registered workspace paths; outside and symlink paths fail", async (t) => {
  const h = await harness(t);
  await writeFile(join(h.workspace, "input.txt"), "fixture");
  await h.engine.prompt("read attachment", [
    {
      path: join(h.workspace, "input.txt"),
      name: "input.txt",
      mimeType: "text/plain",
    },
  ]);
  const calls = await h.calls();
  const prompt = calls.find((call) => call.method === "prompt")!;
  assert.match(prompt.params.prompt[0].text, /Attached workspace files/);
  await assert.rejects(
    h.engine.prompt("bad", [
      {
        path: join(h.root, "outside.txt"),
        name: "bad",
        mimeType: "text/plain",
      },
    ]),
    /outside workspace/,
  );
  await symlink(h.root, join(h.workspace, "link"));
  await assert.rejects(
    scopedPath(h.workspace, join(h.workspace, "link", "new.txt"), true),
    /Symlink/,
  );
  const permission = {
    sessionId: "x",
    toolCall: {
      toolCallId: "x",
      title: "write",
      kind: "edit" as const,
      rawInput: { path: "new.txt" },
    },
    options: [],
  };
  assert.equal(
    await workspacePermission(h.workspace, permission),
    false,
    "display title does not grant tool authority",
  );
});

test("saved bypass mode cannot override confirmed default permission mode", async (t) => {
  const h = await harness(t, { badPolicy: true });
  await assert.rejects(
    h.engine.start(),
    /did not confirm default permission mode/,
  );
  assert.equal(
    (await h.calls()).filter((call) => call.method === "prompt").length,
    0,
  );
});

test("transport loss revokes runner authorization and close refuses unconfirmed workspace settlement", async (t) => {
  const h = await harness(t);
  await h.engine.start();
  await assert.rejects(h.engine.prompt("crash"));
  for (let i = 0; i < 50 && h.exits() === 0; i++) await delay(10);
  assert.equal(h.exits(), 1);
  await assert.rejects(h.engine.close(), /workspace settlement is unknown/);
  await assert.rejects(h.engine.close(), /workspace settlement is unknown/);
});

test("malformed post-cancel child snapshot makes close fail rather than claim settlement", async (t) => {
  const h = await harness(t, { badSnapshot: true });
  await assert.rejects(h.engine.prompt("children"), /settlement is unknown/);
  await assert.rejects(h.engine.close(), /workspace settlement is unknown/);
});

test("cancellation during initialization does not issue a prompt; later explicit turn remains usable", async (t) => {
  const h = await harness(t, { initDelay: 100 });
  const pending = h.engine.prompt("should not execute");
  await delay(20);
  await h.engine.cancel();
  await pending;
  assert.equal(
    (await h.calls()).filter((call) => call.method === "prompt").length,
    0,
  );
  await h.engine.prompt("explicit next turn");
  assert.equal(
    (await h.calls()).filter((call) => call.method === "prompt").length,
    1,
  );
});

test("concurrent prompts are rejected before initialization completes", async (t) => {
  const h = await harness(t, { initDelay: 50 });
  const pending = h.engine.prompt("one");
  await assert.rejects(h.engine.prompt("two"), /already active/);
  await pending;
  assert.equal(
    (await h.calls()).filter((call) => call.method === "prompt").length,
    1,
  );
});

test("runner token split across assistant chunks cannot enter durable message projection", async (t) => {
  const h = await harness(t);
  await h.engine.prompt("token-output");
  const text = h.updates
    .filter((value) => value.type === "text")
    .map((value) => (value.type === "text" ? value.text : ""))
    .join("");
  assert.equal(text, "[REDACTED]fixture response");
  assert.ok(!JSON.stringify(h.updates).includes(h.token));
});

test("native global rules seed exact fail-closed policy before the engine launch", async (t) => {
  const h = await harness(t);
  await writeFile(
    join(h.profileDir, "permission.json"),
    JSON.stringify({ allow: ["bash"] }),
  );
  await h.engine.start();
  const policyPath = join(h.profileDir, "permission.json");
  assert.deepEqual(
    JSON.parse(await readFile(policyPath, "utf8")),
    NATIVE_PERMISSION_POLICY,
  );
  assert.equal((await stat(policyPath)).mode & 0o777, 0o600);
  assert.ok(NATIVE_PERMISSION_POLICY.ask.includes("bash"));
  assert.ok(NATIVE_PERMISSION_POLICY.deny.includes("website_deploy"));
  assert.ok(!NATIVE_PERMISSION_POLICY.deny.includes("task" as never));
});

test("symlinked native policy fails before launch and cannot overwrite the target", async (t) => {
  const h = await harness(t);
  const target = join(h.root, "outside-policy.json");
  await writeFile(target, "keep");
  await symlink(target, join(h.profileDir, "permission.json"));
  await assert.rejects(
    h.engine.start(),
    /Unsafe native permission policy path/,
  );
  assert.equal(await readFile(target, "utf8"), "keep");
  await assert.rejects(readFile(join(h.profileDir, "calls.json")), {
    code: "ENOENT",
  });
});

test("real native background marker keeps workspace quarantined after children finish", async (t) => {
  const h = await harness(t);
  await h.engine.start();
  await assert.rejects(
    h.engine.prompt("background"),
    (error: unknown) =>
      error instanceof EngineSettlementError &&
      error.code === "engine_settlement_unknown",
  );
  await assert.rejects(
    h.engine.close(),
    /background delivery settlement is unknown/,
  );
  assert.equal(h.exits(), 1);
});

test("approved container-local code and build commands pass; publishing, escapes and unknown shell fail closed", async (t) => {
  const h = await harness(t);
  await mkdir(join(h.workspace, "src"));
  await writeFile(join(h.workspace, "src", "test ž.py"), "print(1)");
  const allowed = [
    "npm test",
    "npm ci",
    "npm install typescript",
    "npm run build",
    "python3 -m pip install pytest",
    "python3 -c 'print(1 + 2)'",
    "node -e 'console.log(1 + 2)'",
    "python3 -m pytest",
    'cd src && python3 "test ž.py"',
    "g++ main.cpp -o ./app && ./app",
    "cmake -S . -B build; cmake --build build",
  ];
  for (const command of allowed)
    assert.equal(
      await workspaceShellPermission(h.workspace, command),
      true,
      command,
    );
  const denied = [
    "npm publish",
    "npm run deploy",
    "git push origin main",
    "gh pr create",
    "ssh example.com",
    "curl -X POST https://example.com",
    "python3 ../../escape.py",
    "cd /etc && node app.js",
    "npm test | sh",
    "npm test > /tmp/out",
    'node -e "console.log(process.env.SECRET)"',
    `python3 -c 'import requests; requests.post("https://example.com")'`,
    "npm --prefix /tmp test",
    "unknown-command",
    "npm test && git push",
    "npm test $(whoami)",
  ];
  for (const command of denied)
    assert.equal(
      await workspaceShellPermission(h.workspace, command).catch(() => false),
      false,
      command,
    );
  await symlink(h.root, join(h.workspace, "escape.py"));
  assert.equal(
    await workspaceShellPermission(h.workspace, "python3 escape.py").catch(
      () => false,
    ),
    false,
  );
});

test("official SDK compaction notifications preserve fast ordered transitions, dedupe and reject malformed/foreign payloads", async (t) => {
  const h = await harness(t);
  await h.engine.prompt("compaction");
  assert.deepEqual(
    h.updates.filter((event) => event.type === "compaction"),
    [
      {
        type: "compaction",
        compactionId: "cmp-1",
        status: "start",
        tokensBefore: 420000,
      },
      {
        type: "compaction",
        compactionId: "cmp-1",
        status: "completed",
        tokensBefore: 420000,
        tokensAfter: 12000,
      },
      {
        type: "compaction",
        compactionId: "cmp-2",
        status: "start",
        tokensBefore: 420000,
      },
      {
        type: "compaction",
        compactionId: "cmp-2",
        status: "failed",
        tokensBefore: 420000,
      },
    ],
  );
  assert.deepEqual(
    h.updates
      .filter((event) => event.type === "context")
      .map((event) => (event.type === "context" ? event.used : undefined)),
    [12345],
  );
  const plain = await harness(t);
  await plain.engine.prompt("updates");
  assert.equal(
    plain.updates.filter((event) => event.type === "compaction").length,
    0,
  );
});

test("native foreground bash auto-promotion also prevents unproven workspace settlement", async (t) => {
  const h = await harness(t);
  await assert.rejects(
    h.engine.prompt("bash-background"),
    EngineSettlementError,
  );
  await assert.rejects(
    h.engine.close(),
    /background delivery settlement is unknown/,
  );
});

test("reviewed container assets allow reads without host existence, never mutations or sibling escapes", async (t) => {
  const h = await harness(t);
  const permission = (name: string, path: string) => ({
    sessionId: "native",
    toolCall: {
      toolCallId: "asset",
      title: name,
      name,
      locations: [{ path }],
      rawInput: name === "edit" ? { file_path: path } : { path },
    },
    options: [],
  });
  for (const name of ["read", "grep", "glob"]) {
    assert.equal(
      await workspacePermission(
        h.workspace,
        permission(name, "/opt/ai-harness/skills/example/SKILL.md"),
      ),
      true,
    );
    assert.equal(
      await workspacePermission(
        h.workspace,
        permission(name, "/opt/ai-harness/tools/example.py"),
      ),
      true,
    );
    assert.equal(
      await workspacePermission(
        h.workspace,
        permission(name, "/opt/ai-harness/skills-extra/secret"),
      ),
      false,
    );
    assert.equal(
      await workspacePermission(
        h.workspace,
        permission(name, "/opt/ai-harness/skills/../../secret"),
      ),
      false,
    );
  }
  for (const name of ["write", "edit"])
    assert.equal(
      await workspacePermission(
        h.workspace,
        permission(name, "/opt/ai-harness/tools/example.py"),
      ),
      false,
    );
});

test("launcher receives TERM after ACP stage and gets cleanup grace before successful close", async (t) => {
  const h = await harness(t, {
    ignoreStop: true,
    shutdownDelay: 50,
    shutdownTimeouts: { acpMs: 25, launcherMs: 250, killMs: 100 },
  });
  await h.engine.start();
  const start = Date.now();
  await h.engine.close();
  assert.ok(Date.now() - start >= 70);
  const calls = await h.calls();
  assert.ok(
    calls.findIndex((call) => call.method === "cancel") <
      calls.findIndex((call) => call.method === "signal"),
  );
  assert.equal(calls.find((call) => call.method === "cleanup")?.verified, true);
});

test("nonzero launcher exit and forced kill cannot claim verified cleanup", async (t) => {
  const nonzero = await harness(t, {
    exitCode: 17,
    shutdownTimeouts: { acpMs: 25, launcherMs: 100, killMs: 100 },
  });
  await nonzero.engine.start();
  await assert.rejects(nonzero.engine.close(), /cleanup is unconfirmed/);
  const stuck = await harness(t, {
    ignoreTerm: true,
    shutdownTimeouts: { acpMs: 25, launcherMs: 30, killMs: 100 },
  });
  await stuck.engine.start();
  const start = Date.now();
  await assert.rejects(stuck.engine.close(), /cleanup is unconfirmed/);
  assert.ok(Date.now() - start < 1000);
});

test("closing during asynchronous startup prevents any later launcher spawn", async (t) => {
  const h = await harness(t);
  const starting = h.engine.start();
  const rejected = assert.rejects(starting, /closed/);
  await h.engine.close();
  await rejected;
  await assert.rejects(readFile(join(h.profileDir, "calls.json")), {
    code: "ENOENT",
  });
  await assert.rejects(h.engine.start(), /closed/);
});
