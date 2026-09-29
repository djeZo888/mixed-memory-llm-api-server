import { createHash } from "node:crypto";
import { constants } from "node:fs";
import { lstat, open, realpath } from "node:fs/promises";
import { dirname, isAbsolute, join, resolve } from "node:path";
import { CODEX_TOOL_POLICY_SHA256 } from "./codex-launcher.js";

export const CODEX_RESUME_INSTRUCTIONS_SHA256 = "f7bb7510b3df3546210fee7e6d305f86df9e45c971186088dc6c157977dbecc7";
export interface CodexResumeInstructions {
  readonly text: string;
  readonly sha256: string;
  readonly toolPolicySha256: string;
}
const policyFiles = ["config.toml", "config-image-jobs.toml", "requirements.toml", "models.json", "browser-mcp.mjs", "skills/sova-local-tools/SKILL.md"];
const maximumFileBytes = 131072;
function fail(): never { throw Error("Untrusted Codex resume instruction policy"); }
const trustedOwner = (uid: number) => uid === 0 || uid === process.getuid?.();
const record = (value: unknown): value is Record<string, unknown> => !!value && typeof value === "object" && !Array.isArray(value);

export function validateCodexResumeInstructions(value: unknown): CodexResumeInstructions {
  if (!record(value) || typeof value.text !== "string" ||
      value.sha256 !== CODEX_RESUME_INSTRUCTIONS_SHA256 || value.toolPolicySha256 !== CODEX_TOOL_POLICY_SHA256 ||
      createHash("sha256").update(value.text).digest("hex") !== CODEX_RESUME_INSTRUCTIONS_SHA256) fail();
  return Object.freeze({ text: value.text, sha256: CODEX_RESUME_INSTRUCTIONS_SHA256, toolPolicySha256: CODEX_TOOL_POLICY_SHA256 });
}

async function readTrustedFile(path: string): Promise<Buffer> {
  const handle = await open(path, constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK);
  try {
    const stat = await handle.stat();
    if (!stat.isFile() || stat.nlink !== 1 || !trustedOwner(stat.uid) || (stat.mode & 0o022) !== 0 || stat.size < 1 || stat.size > maximumFileBytes) fail();
    const bytes = Buffer.alloc(maximumFileBytes + 1);
    let length = 0;
    while (length < bytes.length) {
      const result = await handle.read(bytes, length, bytes.length - length, length);
      if (result.bytesRead === 0) break;
      length += result.bytesRead;
    }
    if (length !== stat.size || length > maximumFileBytes) fail();
    return bytes.subarray(0, length);
  } finally {
    await handle.close();
  }
}

export async function loadCodexResumeInstructions(launcherPath: string): Promise<CodexResumeInstructions> {
  try {
    if (!isAbsolute(launcherPath) || resolve(launcherPath) !== launcherPath || !launcherPath.endsWith("/deploy/run-codex.sh") || await realpath(launcherPath) !== launcherPath) fail();
    const deployDirectory = dirname(launcherPath);
    for (const relative of ["", "codex", "codex/skills", "codex/skills/sova-local-tools"]) {
      const stat = await lstat(join(deployDirectory, relative));
      if (!stat.isDirectory() || stat.isSymbolicLink() || !trustedOwner(stat.uid) || (stat.mode & 0o022) !== 0) fail();
    }
    await readTrustedFile(launcherPath);
    const policyDirectory = join(deployDirectory, "codex");
    const files: Buffer[] = [];
    for (const name of policyFiles) files.push(await readTrustedFile(join(policyDirectory, name)));
    const toolPolicySha256 = createHash("sha256").update(Buffer.concat(files)).digest("hex");
    if (toolPolicySha256 !== CODEX_TOOL_POLICY_SHA256) fail();
    const catalog: unknown = JSON.parse(files[policyFiles.indexOf("models.json")]!.toString("utf8"));
    if (!record(catalog) || !Array.isArray(catalog.models)) fail();
    const models = catalog.models.filter((model: unknown) => record(model) && model.slug === "qwen3.8-27b");
    if (models.length !== 1) fail();
    const model: unknown = models[0];
    if (!record(model) || !record(model.model_messages)) fail();
    return validateCodexResumeInstructions({ text: model.model_messages.instructions_template, sha256: CODEX_RESUME_INSTRUCTIONS_SHA256, toolPolicySha256 });
  } catch {
    return fail();
  }
}
