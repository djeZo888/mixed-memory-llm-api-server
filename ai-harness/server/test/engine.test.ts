import test from "node:test";
import assert from "node:assert/strict";
import {
  mkdtemp,
  mkdir,
  readFile,
  realpath,
  rm,
  stat,
  symlink,
  writeFile,
} from "node:fs/promises";
import { tmpdir, userInfo } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { randomBytes } from "node:crypto";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { setTimeout as delay } from "node:timers/promises";
import {
  createEngine,
  EngineSettlementError,
  EngineCleanupError,
  NATIVE_PERMISSION_POLICY,
  scopedPath,
  workspacePermission,
  nativeShellInput,
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
  await mkdir(profileDir, { mode: 0o700 });
  await mkdir(join(profileDir, "state"), { mode: 0o700 });
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
    h.updates.filter((value) => value.type === "text" && value.channel !== "thought").map(v => ({ type: v.type, text: v.type === "text" ? v.text : "" })),
    [{ type: "text", text: "fixture response" }],
  );
  assert.ok(h.updates.some(v => v.type === "text" && v.channel === "thought" && v.text.includes("private reasoning")), "actual emitted thoughts are preserved separately");
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
  assert.equal(launch.home, await realpath(userInfo().homedir));
  assert.equal(launch.dataDir, undefined);
  const sent = calls.find((c) => c.method === "prompt")!.params.prompt;
  assert.match(sent[0].text, /public research/);
  assert.equal(sent.at(-1).text, "updates");
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

test("trusted host HOME ignores ambient spoofing while reviewed launcher confines native HOME to profile", async (t) => {
  const h = await harness(t);
  const nativeState = join(h.profileDir, "state");
  const nativeHome = join(nativeState, "home");
  const hostHome = await realpath(userInfo().homedir);
  const ambient = {
    HOME: nativeHome,
    MINIMAX_DATA_DIR: "/fixture/untrusted-state",
    HTTPS_PROXY: "http://fixture.invalid:1",
    SSH_AUTH_SOCK: "/fixture/untrusted-agent",
    CONTAINER_HOST: "unix:///fixture/untrusted-podman",
  };
  const previous = Object.fromEntries(Object.keys(ambient).map((key) => [key, process.env[key]]));
  Object.assign(process.env, ambient);
  try {
    await h.engine.start();
  } finally {
    for (const [key, value] of Object.entries(previous)) {
      if (value === undefined) delete process.env[key];
      else process.env[key] = value;
    }
  }
  const launch = (await h.calls()).find((call) => call.method === "launch")!;
  assert.equal(launch.home, hostHome);
  assert.notEqual(launch.home, nativeHome);
  assert.equal(launch.dataDir, undefined);
  assert.equal(launch.proxyInherited, false);
  assert.equal(launch.authSocketInherited, false);
  assert.equal(launch.containerHostInherited, false);
  for (const privatePath of [nativeState, nativeHome, join(nativeState, "permission.json")]) {
    const info = await stat(privatePath);
    assert.equal(info.uid, process.getuid!());
    assert.equal(info.mode & 0o077, 0, privatePath);
  }
  assert.equal(hostHome === h.profileDir || hostHome.startsWith(h.profileDir + "/"), false);

  // Inspect the actual reviewed launcher contract without starting Podman,
  // touching an image or invoking the native engine.
  const source = await readFile(new URL("../../deploy/run-engine.sh", import.meta.url), "utf8");
  assert.ok(source.includes('host_home=$(cd -- "$HOME" && pwd -P)'));
  assert.ok(source.includes('export PATH=/usr/bin:/bin HOME="$host_home"'));
  assert.ok(source.includes("container_data=$profile_dir/state"));
  assert.ok(source.includes("container_home=$container_data/home"));
  const invocation = source.slice(source.indexOf('exec "$python_bin"'));
  assert.deepEqual([...invocation.matchAll(/--volume\s+"([^"]+)"/g)].map((match) => match[1]), [
    "$profile_dir:$profile_dir:rw,rprivate",
    "$workspace:$workspace:rw,rprivate",
  ]);
  assert.ok(invocation.includes('--env "HOME=$container_home" --env "MINIMAX_DATA_DIR=$container_data"'));
  assert.equal(/--(?:mount|env-file)\b/.test(invocation), false);
  assert.equal(invocation.includes("$host_home"), false);

  // Run the unchanged launcher with a fake Podman executable. The fake reports
  // pinned metadata and records arguments; it cannot start any container.
  const mockBin = join(h.root, "mock-bin");
  await mkdir(mockBin);
  const pins = JSON.parse(await readFile(new URL("../../deploy/patches/identity.json", import.meta.url), "utf8"));
  await writeFile(join(mockBin, "podman"), `#!${process.execPath}
import { writeFileSync } from "node:fs";
const argv = process.argv.slice(2);
if (argv[0] !== "--remote=false") process.exit(90);
if (argv[1] === "info") console.log("true");
else if (argv[1] === "image" && argv[2] === "inspect") console.log("sha256:${"a".repeat(64)}|ae65651df5f97ae1085ab4e19964f4b78c769a4e|${pins.patchSetSha256}");
else if (argv[1] === "run") writeFileSync(new URL("./invocation.json", import.meta.url), JSON.stringify({argv, home:process.env.HOME, dataDir:process.env.MINIMAX_DATA_DIR}));
else if (argv[1] === "rm") process.exit(0);
else if (argv[1] === "container" && argv[2] === "exists") process.exit(1);
else process.exit(91);
`, { mode: 0o700 });
  const canonicalProfile = await realpath(h.profileDir);
  const canonicalWorkspace = await realpath(h.workspace);
  const realLauncher = fileURLToPath(new URL("../../deploy/run-engine.sh", import.meta.url));
  const launcherArgs = [realLauncher, "--profile-dir", canonicalProfile, "--workspace", canonicalWorkspace];
  const launcherEnv = {
    PATH: `${mockBin}:/usr/bin:/bin`, HOME: launch.home,
    AI_HARNESS_GATEWAY_TOKEN: h.token, AI_HARNESS_SESSION_ID: "fixture-home",
    AI_HARNESS_GATEWAY_URL: "http://10.0.2.2:8081/v1",
  };
  await promisify(execFile)("/bin/bash", launcherArgs, { env: launcherEnv, timeout: 5000 });
  const invoked = JSON.parse(await readFile(join(mockBin, "invocation.json"), "utf8"));
  assert.equal(invoked.home, hostHome);
  assert.equal(invoked.dataDir, undefined);
  const values = (flag: string) => (invoked.argv as string[]).flatMap((value, index, all) => value === flag ? [all[index + 1]] : []);
  assert.deepEqual(values("--volume"), [
    `${canonicalProfile}:${canonicalProfile}:rw,rprivate`,
    `${canonicalWorkspace}:${canonicalWorkspace}:rw,rprivate`,
  ]);
  assert.ok(values("--env").includes(`HOME=${canonicalProfile}/state/home`));
  assert.ok(values("--env").includes(`MINIMAX_DATA_DIR=${canonicalProfile}/state`));
  await assert.rejects(promisify(execFile)("/bin/bash", launcherArgs, {
    env: { ...launcherEnv, HOME: await realpath(nativeHome) }, timeout: 5000,
  }), (error: unknown) => {
    assert.match(String((error as { stderr: string }).stderr), /cannot expose the user home or an ancestor/);
    return true;
  });
  assert.equal(await h.engine.prompt("ordinary startup follow-up"), "completed");
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
  await assert.rejects(unsupported.engine.start(), /settlement capabilities/);
});

test("workspace scoped permission requests allow native shell and deny unmanaged send/traversal/symlinks", async (t) => {
  const h = await harness(t);
  await symlink(h.root, join(h.workspace, "link"));
  await h.engine.prompt("permissions");
  const results = (await h.calls()).filter(
    (call) => call.method === "permission_result",
  );
  assert.deepEqual(
    results.map((call) => call.result.outcome.optionId),
    ["yes", "no", "yes", "yes", "no", "no"],
  );
});

test("cancellation sends real SDK cancel and requires fresh native settlement", async (t) => {
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
    calls.some((call) => call.method === "mcode/session/settlement/get"),
  );
});

test("immediate Stop before root admission accepts only fresh exhaustive cancellation and permits a later ordinary prompt", async (t) => {
  async function stopBeforeAdmission(
    h: Awaited<ReturnType<typeof harness>>,
    rejects = false,
  ) {
    const pending = h.engine.prompt("early-stop");
    const outcome = rejects
      ? assert.rejects(pending, EngineSettlementError)
      : pending.then((value) => assert.equal(value, "cancelled"));
    for (let i = 0; i < 100; i++) {
      if ((await h.calls()).some((call) => call.method === "before-root-admission"))
        break;
      await delay(5);
    }
    assert.ok((await h.calls()).some((call) => call.method === "before-root-admission"));
    // Invalid prompt/fresh receipts can also make cancel fail; neither path may
    // transform an invalid terminal proof into successful completion.
    if (rejects) await h.engine.cancel().catch((error) => assert.ok(error instanceof EngineSettlementError));
    else await h.engine.cancel();
    await outcome;
  }

  const h = await harness(t);
  await h.engine.start();
  await stopBeforeAdmission(h);
  assert.deepEqual(h.updates.filter(v => v.type === "text"), [], "no native root turn was admitted");
  assert.equal(await h.engine.prompt("ordinary follow-up"), "completed");
  const calls = await h.calls();
  assert.equal(calls.filter((call) => call.method === "prompt").length, 2);
  assert.ok(calls.some((call) => call.method === "cancel"));
  for (const runId of ["run-1", "run-2"])
    assert.ok(calls.some((call) => call.method === "mcode/session/settlement/get" && call.params.runId === runId && typeof call.params.instanceId === "string"));

  for (const field of ["promptReceipt", "freshReceipt"])
    for (const mode of ["unknown", "nonexhaustive", "null-run", "stale", "foreign", "wrong-first", "duplicate"])
      await t.test(`${field} ${mode} stays rejected with no admitted turn`, async (st) => {
        const invalid = await harness(st, { [field]: mode });
        await invalid.engine.start();
        await stopBeforeAdmission(invalid, true);
      });

  await t.test("fresh run mismatch and replay of an earlier cancelled run stay rejected", async (st) => {
    const mismatch = await harness(st, { freshReceipt: "run" });
    await mismatch.engine.start();
    await stopBeforeAdmission(mismatch, true);
    const replay = await harness(st, { repeatRunId: true });
    await replay.engine.start();
    await stopBeforeAdmission(replay);
    await assert.rejects(replay.engine.prompt("ordinary follow-up"), EngineSettlementError);
  });
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
  assert.match(prompt.params.prompt.at(-1).text, /Attached workspace files/);
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
  await assert.rejects(h.engine.close(), EngineCleanupError);
  await assert.rejects(h.engine.close(), EngineCleanupError);
});

test("unknown native settlement preserves failure while verified launcher cleanup succeeds", async (t) => {
  const h = await harness(t, { badSnapshot: true });
  await assert.rejects(h.engine.prompt("children"), /settlement is unknown/);
  await h.engine.close();
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
    .filter((value) => value.type === "text" && value.channel !== "thought")
    .map((value) => (value.type === "text" ? value.text : ""))
    .join("");
  assert.equal(text, "[REDACTED]fixture response");
  assert.ok(!JSON.stringify(h.updates).includes(h.token));
});

test("native global rules seed exact fail-closed policy before the engine launch", async (t) => {
  const h = await harness(t);
  await writeFile(
    join(h.profileDir, "state", "permission.json"),
    JSON.stringify({ allow: ["bash"] }),
  );
  await h.engine.start();
  const policyPath = join(h.profileDir, "state", "permission.json");
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
  await symlink(target, join(h.profileDir, "state", "permission.json"));
  await assert.rejects(
    h.engine.start(),
    /Unsafe native permission policy path/,
  );
  assert.equal(await readFile(target, "utf8"), "keep");
  await assert.rejects(readFile(join(h.profileDir, "calls.json")), {
    code: "ENOENT",
  });
});

test("authoritative background completion projects only root continuations and then permits release", async (t) => {
  const h = await harness(t);
  assert.equal(await h.engine.prompt("background"), "completed");
  const text = h.updates
    .filter((v) => v.type === "text" && v.channel !== "thought")
    .map((v) => (v.type === "text" ? v.text : ""))
    .join("");
  assert.equal(
    text,
    "fixture response root continuation one root continuation two",
  );
  const calls = await h.calls();
  const fresh = calls
    .filter((c) => c.method === "mcode/session/settlement/get")
    .at(-1)!;
  assert.equal(fresh.params.runId, "run-1");
  assert.match(fresh.params.instanceId, /^[0-9a-f-]{36}$/);
  await h.engine.close();
});

test("native bash schema admits authorized arbitrary code operations, with workspace cwd fixed natively", async (t) => {
  const h = await harness(t);
  for (const command of [
    "npm test",
    "bash build.sh | tee output.log",
    'printf "%s" "$(node script.js)"',
    "npm exec tsc",
    "python /opt/ai-harness/tools/render_pdf.py input.pdf",
    "npm publish",
  ]) {
    assert.equal(nativeShellInput({ command }), true);
    assert.equal(
      await workspacePermission(h.workspace, {
        sessionId: "native",
        toolCall: { toolCallId: "shell", name: "bash", rawInput: { command } },
        options: [],
      }),
      true,
    );
  }
  for (const input of [
    { command: 42 },
    { command: "pwd", cwd: "/etc" },
    { command: "pwd", workingDirectory: h.workspace },
    { command: "pwd", timeout: "5" },
    { command: "pwd", run_in_background: "true" },
    { command: "pwd", timeout: 2147484 },
  ])
    assert.equal(nativeShellInput(input), false);
  assert.equal(
    await workspacePermission(h.workspace, {
      sessionId: "native",
      toolCall: {
        toolCallId: "shell",
        name: "unknown_shell",
        rawInput: { command: "pwd" },
      },
      options: [],
    }),
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

test("native bash auto-promotion with exhaustive receipt completes normally", async (t) => {
  const h = await harness(t);
  assert.equal(await h.engine.prompt("bash-background"), "completed");
  await h.engine.close();
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

for (const mode of [
  "missing",
  "unknown",
  "running",
  "stale",
  "foreign",
  "duplicate",
  "empty-turns",
  "wrong-first",
  "null-run",
  "nonexhaustive",
  "reasons",
  "malformed",
]) {
  test(`original prompt receipt ${mode} cannot establish success`, async (t) => {
    const h = await harness(t, { promptReceipt: mode });
    await assert.rejects(h.engine.prompt("updates"), EngineSettlementError);
    await h.engine.close();
  });
}
for (const mode of [
  "missing",
  "unknown",
  "running",
  "stale",
  "foreign",
  "run",
  "duplicate",
  "empty-turns",
  "wrong-first",
  "null-run",
  "nonexhaustive",
  "reasons",
  "malformed",
]) {
  test(`fresh settlement receipt ${mode} cannot establish success`, async (t) => {
    const h = await harness(t, { freshReceipt: mode });
    await assert.rejects(h.engine.prompt("updates"), EngineSettlementError);
    assert.equal(
      (await h.calls()).filter((c) => c.method === "prompt").length,
      1,
    );
    await h.engine.close();
  });
}
test("missing completion capability and unknown restore fail before native prompt", async (t) => {
  const unsupported = await harness(t, { noSettlement: true });
  await assert.rejects(unsupported.engine.start(), /settlement/);
  for (const restore of ["load", "resume"]) {
    const h = await harness(t, { restore, restoreUnknown: true }, "restored");
    await assert.rejects(h.engine.prompt("never"), EngineSettlementError);
    assert.equal(
      (await h.calls()).filter((c) => c.method === "prompt").length,
      0,
    );
  }
});
test("native cancellation is returned distinctly without caller cancellation", async (t) => {
  const h = await harness(t, { nativeCancelled: true });
  assert.equal(await h.engine.prompt("updates"), "cancelled");
});
test("late root notifications and child text never append after completion", async (t) => {
  const h = await harness(t, { lateText: true });
  await h.engine.prompt("background");
  await delay(60);
  const text = h.updates
    .filter((v) => v.type === "text" && v.channel !== "thought")
    .map((v) => (v.type === "text" ? v.text : ""))
    .join("");
  assert.equal(
    text,
    "fixture response root continuation one root continuation two",
  );
});
for (const exitCode of [125, 143])
  test(`launcher exit ${exitCode} is not verified cleanup`, async (t) => {
    const h = await harness(t, {
      exitCode,
      shutdownTimeouts: { acpMs: 25, launcherMs: 100, killMs: 100 },
    });
    await h.engine.start();
    await assert.rejects(h.engine.close(), EngineCleanupError);
  });
test("cancel notification acknowledgement cannot substitute for fresh cancellation receipt", async (t) => {
  const h = await harness(t, { freshReceipt: "unknown" });
  await h.engine.start();
  const pending = h.engine.prompt("wait");
  const failed = assert.rejects(pending, EngineSettlementError);
  for (
    let i = 0;
    i < 50 && !(await h.calls()).some((c) => c.method === "prompt");
    i++
  )
    await delay(10);
  await assert.rejects(h.engine.cancel(), EngineSettlementError);
  await failed;
  await h.engine.close();
});
test("failed completion cannot be followed by native replay or another prompt", async (t) => {
  const h = await harness(t, { freshReceipt: "unknown" });
  await assert.rejects(h.engine.prompt("first"), EngineSettlementError);
  await assert.rejects(h.engine.prompt("second"), EngineSettlementError);
  assert.equal(
    (await h.calls()).filter((c) => c.method === "prompt").length,
    1,
  );
});

test("official SDK shell permissions admit scripts, pipelines, substitutions and reviewed helper paths", async (t) => {
  const h = await harness(t);
  await h.engine.prompt("shell-policy");
  const permissions = (await h.calls()).filter(
    (c) => c.method === "shell_permission",
  );
  assert.deepEqual(
    permissions.map((c) => c.result.outcome.optionId),
    ["yes", "yes", "yes", "yes", "yes", "no", "no", "no", "no"],
  );
});
test("private state symlink fails before launcher spawn", async (t) => {
  const h = await harness(t);
  await rm(join(h.profileDir, "state"), { recursive: true });
  await symlink(h.workspace, join(h.profileDir, "state"));
  await assert.rejects(h.engine.start(), /owned real directory/);
  await assert.rejects(readFile(join(h.profileDir, "calls.json")), {
    code: "ENOENT",
  });
});

test("new native session cannot admit an identity-less running receipt", async (t) => {
  const h = await harness(t, { initialRunning: true });
  await assert.rejects(h.engine.prompt("never"), EngineSettlementError);
  assert.equal(
    (await h.calls()).filter((c) => c.method === "prompt").length,
    0,
  );
});

test("H002 SDK metadata preserves channels, redacts interleaved tails, upserts actual tool input and gates final on last root", async (t) => {
  const h = await harness(t, { h002: true, snapshotComplete: true, earlierKindFinal: true });
  await h.engine.prompt("synthetic channel fixture");
  const texts = h.updates.filter(
    (u): u is Extract<EngineUpdate, { type: "text" }> => u.type === "text",
  );
  const joined = (id: string, channel: string) =>
    texts
      .filter((u) => u.nativeMessageId === id && u.channel === channel)
      .map((u) => u.text)
      .join("");
  assert.equal(joined("native-a", "thought"), "Emitted thought [REDACTED].");
  assert.equal(joined("native-a", "unknown"), "Planning [REDACTED].");
  assert.equal(joined("native-z", "unknown"), "Actual final answer.");
  assert.ok(!JSON.stringify(h.updates).includes(h.token));
  assert.deepEqual(
    h.updates
      .filter((u) => u.type === "phase" && u.channel === "final")
      .map((u) =>
        u.type === "phase" ? [u.nativeMessageId, u.nativeTurnId] : [],
      ),
    [["native-z", "run-1-last"]],
  );
  assert.ok(
    h.updates.some(
      (u) =>
        u.type === "phase" &&
        u.nativeMessageId === "native-a" &&
        u.channel === "commentary",
    ),
  );
  const tools = h.updates.filter(
    (u): u is Extract<EngineUpdate, { type: "progress" }> =>
      u.type === "progress" &&
      u.kind === "tool" &&
      u.toolCallId === "real-tool",
  );
  assert.equal(tools.length, 2);
  assert.equal(tools[0].toolActivityId, tools[1].toolActivityId);
  assert.equal(tools[1].status, "completed");
  assert.equal(tools[1].name, "bash");
  assert.equal(tools[1].command, tools[0].command);
  assert.ok(tools[1].command!.length <= 2048);
  assert.match(tools[1].url!, /\[REDACTED\]/);
  assert.ok(tools[1].completedAt);
  const browser = h.updates.find(
    (u) => u.type === "progress" && u.toolCallId === "browser-tool",
  );
  assert.ok(
    browser?.type === "progress" &&
      browser.url === "https://example.test/research?token=[REDACTED]" &&
      browser.detail?.includes("action: navigate"),
  );
  const launch = (await h.calls()).find((c) => c.method === "launch")!;
  assert.equal(launch.tz, "Europe/Ljubljana");
  assert.match(
    (await h.calls()).find((c) => c.method === "prompt")!.params.prompt[1].text,
    /Ljubljana, Slovenia/,
  );
});

for (const config of [
  { emptyLast: true },
  { omitMetadata: true },
  { nativeCancelled: true },
  { freshReceipt: "unknown" },
]) {
  test(`H002 no final with ${Object.keys(config)[0]}`, async (t) => {
    const h = await harness(t, { h002: true, ...config });
    if ("freshReceipt" in config)
      await assert.rejects(h.engine.prompt("synthetic"));
    else await h.engine.prompt("synthetic");
    assert.ok(
      !h.updates.some((u) => u.type === "phase" && u.channel === "final"),
    );
  });
}

test("H002 full child baseline counts new and changed unique members; old completed history excluded", async (t) => {
  const h = await harness(t, {
    h002: true,
    snapshotComplete: true,
    initialChildren: [
      {
        sessionId: "old",
        parentSessionId: "native-fixture-session",
        status: "completed",
      },
    ],
    childSequence: [
      [
        { sessionId: "old", parentSessionId: "$root", status: "completed" },
        { sessionId: "new", parentSessionId: "$root", status: "queued" },
      ],
      [
        { sessionId: "old", parentSessionId: "$root", status: "completed" },
        { sessionId: "new", parentSessionId: "$root", status: "running" },
      ],
      [
        { sessionId: "old", parentSessionId: "$root", status: "completed" },
        { sessionId: "new", parentSessionId: "$root", status: "completed" },
      ],
    ],
  });
  await h.engine.prompt("synthetic");
  const summaries = h.updates.flatMap((u) =>
    u.type === "progress" && u.subagents ? [u.subagents] : [],
  );
  assert.ok(
    summaries.some((s) => s.known && s.active === 1 && s.completed === 0),
  );
  assert.equal(summaries.at(-1)!.completed, 1);
  assert.equal(summaries.at(-1)!.active, 0);
  assert.ok(
    !h.updates.some((u) => u.type === "progress" && u.subagentId === "old"),
  );
  const start = h.updates.length;
  await h.engine.prompt("synthetic second");
  assert.ok(
    h.updates
      .slice(start)
      .some(
        (u) =>
          u.type === "progress" &&
          u.subagents?.known &&
          u.subagents.active === 0 &&
          u.subagents.completed === 0,
      ),
  );
});

test("H002 missing or truncated native child capability keeps counts explicitly unknown", async (t) => {
  const h = await harness(t, {
    h002: true,
    snapshotComplete: false,
    childSequence: [
      [{ sessionId: "new", parentSessionId: "$root", status: "running" }],
    ],
  });
  await h.engine.prompt("synthetic");
  assert.ok(
    h.updates.some(
      (u) =>
        u.type === "progress" &&
        u.subagentId === "new" &&
        u.status === "running",
    ),
  );
  assert.ok(
    h.updates.every(
      (u) =>
        u.type !== "progress" ||
        !u.subagents ||
        (!u.subagents.known && u.subagents.active === null),
    ),
  );
});
