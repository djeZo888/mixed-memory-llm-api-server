import test from "node:test";
import assert from "node:assert/strict";
import { chmod, copyFile, cp, mkdir, mkdtemp, readFile, realpath, rm, symlink, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { CODEX_RESUME_INSTRUCTIONS_SHA256, loadCodexResumeInstructions, validateCodexResumeInstructions } from "../src/codex-instructions.js";
import { CODEX_TOOL_POLICY_SHA256 } from "../src/codex-launcher.js";

const launcher = fileURLToPath(new URL("../../deploy/run-codex.sh", import.meta.url));
async function fixture(action: (path: string) => Promise<void>) {
  const directory = await realpath(await mkdtemp(join(tmpdir(), "codex-instructions-")));
  try {
    const deploy = join(directory, "deploy");
    await mkdir(deploy);
    await copyFile(launcher, join(deploy, "run-codex.sh"));
    await cp(join(dirname(launcher), "codex"), join(deploy, "codex"), { recursive: true });
    await action(join(deploy, "run-codex.sh"));
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
}

test("trusted resume instructions exactly match the mounted reviewed Qwen catalog", async () => {
  const loaded = await loadCodexResumeInstructions(launcher);
  const catalog = JSON.parse(await readFile(join(dirname(launcher), "codex/models.json"), "utf8"));
  assert.equal(loaded.text, catalog.models.find((model: any) => model.slug === "qwen3.8-27b").model_messages.instructions_template);
  assert.equal(loaded.sha256, CODEX_RESUME_INSTRUCTIONS_SHA256);
  assert.equal(loaded.toolPolicySha256, CODEX_TOOL_POLICY_SHA256);
  assert.equal(Object.isFrozen(loaded), true);
});

test("resume instruction loader rejects policy tampering, even outside the catalog", async () => {
  for (const name of ["models.json", "config.toml", "config-image-jobs.toml", "requirements.toml", "browser-mcp.mjs", "skills/sova-local-tools/SKILL.md"]) {
    await fixture(async path => {
      const file = join(dirname(path), "codex", name);
      await writeFile(file, Buffer.concat([await readFile(file), Buffer.from("\n")]));
      await assert.rejects(loadCodexResumeInstructions(path), /Untrusted Codex resume instruction policy/);
    });
  }
});

test("resume instruction loader rejects missing and oversized policy files", async () => {
  await fixture(async path => {
    await rm(join(dirname(path), "codex/models.json"));
    await assert.rejects(loadCodexResumeInstructions(path), /Untrusted/);
  });
  await fixture(async path => {
    await writeFile(join(dirname(path), "codex/models.json"), Buffer.alloc(131073));
    await assert.rejects(loadCodexResumeInstructions(path), /Untrusted/);
  });
});

test("resume instruction loader rejects symlinked files and policy directories", async () => {
  for (const relative of ["run-codex.sh", "codex/models.json", "codex/skills/sova-local-tools"]) {
    await fixture(async path => {
      const target = join(dirname(path), relative);
      await rm(target, { recursive: true, force: true });
      await symlink(join(dirname(launcher), relative), target);
      await assert.rejects(loadCodexResumeInstructions(path), /Untrusted/);
    });
  }
});

test("resume instruction loader rejects writable policy files and directories", async () => {
  for (const relative of ["run-codex.sh", "codex/models.json", "codex", "codex/skills"]) {
    await fixture(async path => {
      await chmod(join(dirname(path), relative), relative.endsWith(".json") || relative.endsWith(".sh") ? 0o666 : 0o777);
      await assert.rejects(loadCodexResumeInstructions(path), /Untrusted/);
    });
  }
});

test("resume instruction loader requires the fixed absolute canonical launcher path", async () => {
  for (const path of ["deploy/run-codex.sh", launcher.replace("run-codex.sh", "other.sh"), launcher.replace("/deploy/", "/deploy/../deploy/")]) {
    await assert.rejects(loadCodexResumeInstructions(path), /Untrusted/);
  }
});

test("engine boundary validates the actual text, template pin and full policy pin", async () => {
  const loaded = await loadCodexResumeInstructions(launcher);
  assert.deepEqual(validateCodexResumeInstructions(loaded), loaded);
  for (const invalid of [null, {}, { ...loaded, text: loaded.text.slice(0, -1) + "x" }, { ...loaded, sha256: "0".repeat(64) }, { ...loaded, toolPolicySha256: "0".repeat(64) }]) {
    assert.throws(() => validateCodexResumeInstructions(invalid), /Untrusted/);
  }
});
