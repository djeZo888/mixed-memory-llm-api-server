/** Host-reviewed workflow evidence, never current readiness or a task entitlement.
 * Only root-owned files in /etc/sova-qualification can open global specialists.
 * Missing/invalid evidence keeps the ordinary Codex preview and scoped tickets.
 */
import { createHash } from "node:crypto";
import { isDeepStrictEqual } from "node:util";
import { CODEX_PIN } from "./codex-engine.js";
import { CODEX_MODEL_POLICY, CODEX_TOOL_POLICY_SHA256 } from "./codex-launcher.js";
import { codexProvider } from "./codex-provider.js";
import { QWEN_CODEX_PIN } from "./codex-qwen.js";
import { QWEN_SOURCE_PIN, QWEN_OWNER_POLICY } from "./codex-production.js";
import { MIMO_RUNTIME, MIMO_ARTIFACT_REVISION, MIMO_ARTIFACT_MANIFEST_SHA256 } from "./mimo.js";
import { readMimoEvidence } from "./mimo-frontier.js";
import type { CodexCapabilities } from "./codex-capabilities.js";

export const CODEX_SPECIALIST_DIRECTORY = "/etc/sova-qualification";
export const CODEX_SPECIALIST_PINS = {
  engine: CODEX_PIN,
  policy: CODEX_MODEL_POLICY,
  toolPolicySha256: CODEX_TOOL_POLICY_SHA256,
  qwen: { ...QWEN_CODEX_PIN, ...QWEN_SOURCE_PIN, ownerPolicy: QWEN_OWNER_POLICY, profile: codexProvider("qwen3.8-27b") },
  frontier: { profile: codexProvider("mimo-v2.6-pro-rl"), runtimeRevision: MIMO_RUNTIME,
    artifactRevision: MIMO_ARTIFACT_REVISION, artifactManifestSha256: MIMO_ARTIFACT_MANIFEST_SHA256,
    templateSha256: "16b2dac352c6cf1aef8b0a976618c76deb28c5bf3aba4c8b788fb846aa3769a4" },
  image: { model: "qwen-image-2.1", modelRevision: "790c92633540aa0cb11d9abf19eb46d861714758",
    runtimeRevision: "0cd8be351d0825488f4b81c8931167bbab618eca",
    // configs/runtimes/h005-runtime-binding.json distinguishes the tested native
    // platform manifest/config from its parent; a parent-only receipt is stale.
    runtimeImage: "sha256:50a3bfd20fc931f05fc5fc919b0445abbce30d5c7716424d697a7ab6708c08ef",
    runtimeImageIdDomain: "oci_platform_manifest",
    runtimeConfigDigest: "sha256:3f6178faa74c4a9bcb95ed4304dbee57473efa8913a793e067014af4a98281ad",
    parentImageReference: "sha256:dafbccb763cff6a6aa3777c7c0a8cc185d838bd4b9f61bec8007f57f2c7233f8",
    maximumGenerationSize: "1920x1080", maximumReferences: 2 },
} as const;
const workflows = {
  image: ["generation", "followup_edit", "child"],
  frontier: ["tool_continuation", "codex_child", "minimax_delegation"],
} as const;
type Specialist = keyof typeof workflows;
export interface CodexSpecialistQualification {
  imageJobsQualified: boolean;
  frontierResponsesQualified: boolean;
  capabilities: Pick<CodexCapabilities, "image" | "frontier">;
}
const closed = (): CodexSpecialistQualification => ({
  imageJobsQualified: false, frontierResponsesQualified: false,
  capabilities: {
    image: { supported: false, qualification: "not_tested", reason: "Protected live Codex image generation/edit/child evidence is absent or invalid" },
    frontier: { supported: false, qualification: "not_tested", reason: "Protected live MiMo tool-continuation and Codex/MiniMax delegation evidence is absent or invalid; 950000 is configured capacity" },
  },
});
const fail = (): never => { throw Error("Invalid protected Codex specialist qualification"); };
function fields(v: any, expected: readonly string[]) {
  if (!v || typeof v !== "object" || Array.isArray(v) || !isDeepStrictEqual(Object.keys(v).sort(), [...expected].sort())) fail();
}
const digest = (v: unknown): v is string => typeof v === "string" && /^[a-f0-9]{64}$/.test(v);
const uuid = (v: unknown): v is string => typeof v === "string" && /^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/.test(v);
const fileName = (v: unknown): v is string => typeof v === "string" && /^[a-zA-Z0-9][a-zA-Z0-9_-]{0,95}\.json$/.test(v);
const sha = (text: string) => createHash("sha256").update(text).digest("hex");
/** Pure validation seam. Production supplies only the protected fixed-directory reader. */
export function validateCodexSpecialists(record: any, readEvidence: (name: string) => { text: string; value: any }, now = Date.now()): CodexSpecialistQualification {
  fields(record, ["schema", "kind", "pins", "image", "frontier"]);
  if (record.schema !== 1 || record.kind !== "reviewed-codex-specialists" || !isDeepStrictEqual(record.pins, CODEX_SPECIALIST_PINS)) fail();
  const result = closed();
  for (const capability of ["image", "frontier"] as Specialist[]) {
    const ref = record[capability];
    if (ref === null) continue;
    fields(ref, ["file", "sha256"]);
    if (!fileName(ref.file) || !digest(ref.sha256)) fail();
    const evidence = readEvidence(ref.file), value = evidence.value;
    if (sha(evidence.text) !== ref.sha256) fail();
    fields(value, ["schema", "kind", "capability", "pins", "reviewedAt", "workflows"]);
    if (value.schema !== 1 || value.kind !== "retained-live-specialist-acceptance" || value.capability !== capability ||
        !isDeepStrictEqual(value.pins, CODEX_SPECIALIST_PINS) || typeof value.reviewedAt !== "string" ||
        !Number.isFinite(Date.parse(value.reviewedAt)) || Date.parse(value.reviewedAt) > now) fail();
    fields(value.workflows, workflows[capability]);
    for (const workflow of workflows[capability]) {
      const run = value.workflows[workflow];
      fields(run, ["result", "sessionId", "runId", "transcriptSha256", "settlementSha256"]);
      if (run.result !== "PASS" || !uuid(run.sessionId) || !uuid(run.runId) ||
          !digest(run.transcriptSha256) || !digest(run.settlementSha256)) fail();
    }
    result[capability === "image" ? "imageJobsQualified" : "frontierResponsesQualified"] = true;
    result.capabilities[capability] = { supported: true, qualification: "live", reason:
      capability === "image"
        ? `Reviewed retained live generation, follow-up edit and child evidence ${ref.sha256}; current image readiness is checked separately`
        : `Reviewed retained live MiMo tool continuation and Codex/MiniMax delegation evidence ${ref.sha256}; current backend readiness is checked separately; 950000 is configured capacity` };
  }
  return result;
}
export function loadCodexSpecialists(file?: string): CodexSpecialistQualification {
  if (!file) return closed();
  try {
    // Fixed root path is outside all task/workspace mounts. readMimoEvidence
    // rejects symlinks, hardlinks, writable/non-root ancestry and oversized files.
    const prefix = CODEX_SPECIALIST_DIRECTORY + "/";
    if (!file.startsWith(prefix) || !fileName(file.slice(prefix.length))) return closed();
    return validateCodexSpecialists(readMimoEvidence(file).value,
      name => readMimoEvidence(prefix + name));
  } catch { return closed(); }
}
