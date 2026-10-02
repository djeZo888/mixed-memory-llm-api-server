import {readFileSync,lstatSync,realpathSync} from "node:fs";
import {dirname,join,resolve} from "node:path";
import {fileURLToPath} from "node:url";
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
    image: { supported: false, qualification: "not_tested", reason: "Retained H034 generation and fresh native child generation passed; protected full guarded-edit, approval and result-handoff evidence remains absent or invalid" },
    frontier: { supported: false, qualification: "not_tested", reason: `Protected live MiMo tool-continuation and Codex/MiniMax delegation evidence is absent or invalid; ${CODEX_SPECIALIST_PINS.frontier.profile.contextWindow} is configured capacity, not qualified occupied context` },
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
/** Explicit H035 compatibility review only, not a policy migration mechanism. */
const reviewedToolPolicy = {
  tested: "aee39eea7f559a2f1c1b34c2d99818be1bc4e79ea6dba2ca7ec4075c8e34a956",
  target: "4ab2f4935c2a90691b9abdd713b74e389922baeab2262ddc6d41a3b1ddd88b87",
  testedSource: "c863d4984f4a75c237b6de97b7ce40b8570fca81",
  targetSource: "dbcd579f8b5ee91ff86c4035bfe643d51e8cd3d1",
} as const;
// The historical review changed tool policy only; it never reviewed a capacity change.
const reviewedFrontierProfile = {
  ...codexProvider("mimo-v2.6-pro-rl"), contextWindow: 950000, autoCompactTokenLimit: 880000,
} as const;
type EvidenceReader = (name: string) => { text: string; value: any };
function referencedEvidence(ref: any, readEvidence: EvidenceReader) {
  fields(ref, ["file", "sha256"]);
  if (!fileName(ref.file) || !digest(ref.sha256)) fail();
  const evidence = readEvidence(ref.file);
  if (sha(evidence.text) !== ref.sha256) fail();
  return evidence.value;
}
function reviewedFrontierCompatibility(value: any, readEvidence: EvidenceReader, now: number): string {
  fields(value, ["schema", "kind", "capability", "pins", "sourceRevision", "reviewedAt", "workflows", "review"]);
  if (value.schema !== 2 || value.kind !== "retained-live-frontier-reviewed-compatibility" || value.capability !== "frontier" ||
      value.sourceRevision !== reviewedToolPolicy.testedSource || value.pins?.toolPolicySha256 !== reviewedToolPolicy.tested ||
      CODEX_SPECIALIST_PINS.toolPolicySha256 !== reviewedToolPolicy.target ||
      !isDeepStrictEqual(CODEX_SPECIALIST_PINS.frontier.profile, reviewedFrontierProfile) ||
      !isDeepStrictEqual(value.pins, { ...CODEX_SPECIALIST_PINS, toolPolicySha256: reviewedToolPolicy.tested })) fail();
  const review = referencedEvidence(value.review, readEvidence);
  fields(review, ["schema", "kind", "testedSourceRevision", "testedPins", "targetSourceRevision", "targetPins", "workflowsSha256", "reviewedAt", "reviewedBy"]);
  if (review.schema !== 1 || review.kind !== "reviewed-frontier-tool-policy-compatibility" ||
      review.testedSourceRevision !== value.sourceRevision || !isDeepStrictEqual(review.testedPins, value.pins) ||
      review.targetSourceRevision !== reviewedToolPolicy.targetSource ||
      !isDeepStrictEqual(review.targetPins, CODEX_SPECIALIST_PINS) ||
      !digest(review.workflowsSha256) || review.workflowsSha256 !== sha(JSON.stringify(value.workflows)) ||
      typeof review.reviewedBy !== "string" || !review.reviewedBy.trim() || review.reviewedBy.length > 200 ||
      typeof review.reviewedAt !== "string" || !Number.isFinite(Date.parse(review.reviewedAt)) ||
      Date.parse(review.reviewedAt) < Date.parse(value.reviewedAt) || Date.parse(review.reviewedAt) > now) fail();
  return `Reused live MiMo tool continuation and Codex/MiniMax delegation evidence tested on source ${value.sourceRevision} / tool policy ${value.pins.toolPolicySha256}; compatibility reviewed for target tool policy ${review.targetPins.toolPolicySha256}, reviewed implementation basis ${review.targetSourceRevision}, by ${review.reviewedBy} (${value.review.sha256}); no new target live execution; current backend readiness is checked separately; ${CODEX_SPECIALIST_PINS.frontier.profile.contextWindow} is configured capacity, not qualified occupied context`;
}
/** Pure validation seam. Production supplies only the protected fixed-directory reader. */
export function validateCodexSpecialists(record: any, readEvidence: EvidenceReader, now = Date.now()): CodexSpecialistQualification {
  fields(record, ["schema", "kind", "pins", "image", "frontier"]);
  if (record.schema !== 1 || record.kind !== "reviewed-codex-specialists" || !isDeepStrictEqual(record.pins, CODEX_SPECIALIST_PINS)) fail();
  const result = closed();
  for (const capability of ["image", "frontier"] as Specialist[]) {
    const ref = record[capability];
    if (ref === null) continue;
    const value = referencedEvidence(ref, readEvidence);
    let compatibilityReason: string | undefined;
    if (value?.schema === 2 && capability === "frontier") {
      compatibilityReason = reviewedFrontierCompatibility(value, readEvidence, now);
    } else {
      fields(value, ["schema", "kind", "capability", "pins", "reviewedAt", "workflows"]);
      if (value.schema !== 1 || value.kind !== "retained-live-specialist-acceptance" || value.capability !== capability ||
          !isDeepStrictEqual(value.pins, CODEX_SPECIALIST_PINS)) fail();
    }
    if (typeof value.reviewedAt !== "string" || !Number.isFinite(Date.parse(value.reviewedAt)) || Date.parse(value.reviewedAt) > now) fail();
    fields(value.workflows, workflows[capability]);
    for (const workflow of workflows[capability]) {
      const run = value.workflows[workflow];
      fields(run, ["result", "sessionId", "runId", "transcriptSha256", "settlementSha256"]);
      if (run.result !== "PASS" || !uuid(run.sessionId) || !uuid(run.runId) ||
          !digest(run.transcriptSha256) || !digest(run.settlementSha256)) fail();
    }
    result[capability === "image" ? "imageJobsQualified" : "frontierResponsesQualified"] = true;
    result.capabilities[capability] = { supported: true, qualification: "live", reason: compatibilityReason
      ? `${compatibilityReason}; retained evidence ${ref.sha256}` : capability === "image"
        ? `Reviewed retained live generation, follow-up edit and child evidence ${ref.sha256}; current image readiness is checked separately`
        : `Reviewed retained live MiMo tool continuation and Codex/MiniMax delegation evidence ${ref.sha256}; current backend readiness is checked separately; ${CODEX_SPECIALIST_PINS.frontier.profile.contextWindow} is configured capacity, not qualified occupied context` };
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

/** A separate current protected root review; old H038/MiniMax receipts cannot enter. */
export const CURRENT_CODEX_FRONTIER_PINS = Object.freeze({engine:CODEX_PIN,modelPolicy:CODEX_MODEL_POLICY,toolPolicySha256:CODEX_TOOL_POLICY_SHA256,parentModel:"qwen3.8-27b",childProvider:"sova",childProfile:codexProvider("mimo-v2.6-pro-rl")});
export function validateCurrentCodexFrontier(value: any, read: (name:string)=>{text:string;value:any}, now=Date.now()): boolean {
  const exact = (v:any, keys:string[]) => v && typeof v === "object" && !Array.isArray(v) && Object.keys(v).sort().join()===keys.sort().join();
  const digest = (v:any) => typeof v === "string" && /^[a-f0-9]{64}$/.test(v);
  if (!exact(value,["schema","kind","pins","sourceRevision","sourceClosure","reviewedBy","reviewedAt","workflows"]) || !value.sourceClosure || typeof value.sourceClosure!=="object" || Array.isArray(value.sourceClosure) || !Object.keys(value.sourceClosure).length || !Object.values(value.sourceClosure).every(digest) || value.schema!==1 || value.kind!=="current-native-codex-frontier-review" || value.reviewedBy!=="root" || !/^[a-f0-9]{40}$/.test(value.sourceRevision) || !isDeepStrictEqual(value.pins,CURRENT_CODEX_FRONTIER_PINS) || !Number.isFinite(Date.parse(value.reviewedAt)) || Date.parse(value.reviewedAt)>now || !exact(value.workflows,["responses","toolContinuation","automaticSelection"])) return false;
  let parent: string | undefined;
  for (const workflow of ["responses","toolContinuation","automaticSelection"]) {
    const ref=value.workflows[workflow];
    if(!exact(ref,["file","sha256"]) || !/^[a-zA-Z0-9][a-zA-Z0-9_-]{0,95}\.json$/.test(ref.file) || !digest(ref.sha256))return false;
    const evidence=read(ref.file), run=evidence.value;
    if(createHash("sha256").update(evidence.text).digest("hex")!==ref.sha256 || !exact(run,["schema","kind","workflow","result","harness","pins","sourceRevision","sessionId","parentThreadId","parentTurnId","childThreadId","childTurnId","dispatchEventSha256","childTerminalSha256","model","provider","nativeSemanticAcceptance","transcriptSha256","settlementSha256","currentOwnerReceiptSha256"]) || run.schema!==1 || run.kind!=="current-native-codex-frontier-workflow" || run.workflow!==workflow || run.result!=="PASS" || run.harness!=="codex" || run.nativeSemanticAcceptance!=="PASS" || !isDeepStrictEqual(run.pins,value.pins) || run.sourceRevision!==value.sourceRevision || !/^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/.test(run.sessionId) || typeof run.parentThreadId!=="string" || !run.parentThreadId || typeof run.childThreadId!=="string" || !run.childThreadId || run.childThreadId===run.parentThreadId || typeof run.parentTurnId!=="string" || !run.parentTurnId || typeof run.childTurnId!=="string" || !run.childTurnId || ![run.dispatchEventSha256,run.childTerminalSha256].every(digest) || run.model!=="mimo-v2.6-pro-rl" || run.provider!=="sova" || ![run.transcriptSha256,run.settlementSha256,run.currentOwnerReceiptSha256].every(digest))return false;
    const tuple=JSON.stringify([run.sessionId,run.parentThreadId]);if(parent && parent!==tuple)return false;parent=tuple;
  }
  return true;
}
export function loadCurrentCodexFrontier(file?:string): boolean {
  const prefix="/etc/sova-qualification/";
  if(!file?.startsWith(prefix) || !/^[a-zA-Z0-9][a-zA-Z0-9_-]{0,95}\.json$/.test(file.slice(prefix.length)))return false;
  try{
    const value=readMimoEvidence(file).value,server=dirname(fileURLToPath(import.meta.url)),deploy=resolve(server,"../../deploy");
    const expected=[...['main','broker','gateway','codex-host','codex-engine','codex-children','codex-child-metadata','codex-automatic-routing','codex-specialist-qualification'].map(name=>join(server,name+'.js')),join(deploy,'run-codex.sh'),join(deploy,'codex/config.toml'),join(deploy,'codex/models.json')];
    if(!value.sourceClosure || Object.keys(value.sourceClosure).sort().join()!==expected.sort().join())return false;
    for(const path of expected){const stat=lstatSync(path);if(!stat.isFile()||stat.isSymbolicLink()||stat.mode&0o022||![0,process.getuid?.()].includes(stat.uid)||realpathSync(path)!==path||createHash('sha256').update(readFileSync(path)).digest('hex')!==value.sourceClosure[path])return false;}
    return validateCurrentCodexFrontier(value,name=>readMimoEvidence(prefix+name));
  }catch{return false;}
}

/** Generation-only evidence is independent of the historical full image workflow.
 * This intentionally supplies NO full image/edits/creative-child enable flag. */
export interface CodexGenerationOnlyQualification {generationQualified:boolean;imageJobsQualified:false;imageEditQualified:false;creativeChildQualified:false}
const generationClosed=():CodexGenerationOnlyQualification=>({generationQualified:false,imageJobsQualified:false,imageEditQualified:false,creativeChildQualified:false});
export function validateCodexGenerationOnly(value:any,read:EvidenceReader,now=Date.now()):CodexGenerationOnlyQualification {
 const result=generationClosed();
 try {
  fields(value,["schema","kind","pins","sourceRevision","sourceClosure","reviewedBy","reviewedAt","normalJob","publicArtifact"]);
  if(value.schema!==1||value.kind!=="root-reviewed-generation-only"||value.reviewedBy!=="root"||!isDeepStrictEqual(value.pins,CODEX_SPECIALIST_PINS.image)||!/^[a-f0-9]{40}$/.test(value.sourceRevision)||!Number.isFinite(Date.parse(value.reviewedAt))||Date.parse(value.reviewedAt)>now)return result;
  if(!value.sourceClosure || typeof value.sourceClosure!=="object" || Array.isArray(value.sourceClosure) || !Object.keys(value.sourceClosure).length || !Object.values(value.sourceClosure).every(digest))return result;
  const job=referencedEvidence(value.normalJob,read),artifact=referencedEvidence(value.publicArtifact,read);
  if(job.kind!=="normal-live-image-job"||job.sourceOnly!==false||job.state!=="completed"||job.operation!=="generation"||job.model!=="qwen-image-2.1"||job.size!=="1920x1080"||!uuid(job.sessionId)||!uuid(job.runId)||!uuid(job.jobId)||!digest(job.currentOwnerReceiptSha256)||!digest(job.settlementSha256)||!isDeepStrictEqual(job.runtimeIdentity,CODEX_SPECIALIST_PINS.image)||artifact.kind!=="decoded-public-image-artifact"||artifact.jobId!==job.jobId||artifact.mimeType!=="image/png"||artifact.codec!=="png"||artifact.width!==1920||artifact.height!==1080||!digest(artifact.sha256)||artifact.sha256!==job.publicArtifactSha256||artifact.rawPreCropArtifact!=="NOT_CAPTURED"||artifact.geometryGuard!=="PASS"||artifact.codecGuard!=="PASS")return result;
  result.generationQualified=true;return result;
 }catch{return result;}
}
export function loadCodexGenerationOnly(file?:string):CodexGenerationOnlyQualification {
 if(!file?.startsWith(CODEX_SPECIALIST_DIRECTORY+"/")||!fileName(file.slice(CODEX_SPECIALIST_DIRECTORY.length+1)))return generationClosed();
 try{
  const value=readMimoEvidence(file).value,server=dirname(fileURLToPath(import.meta.url)),deploy=resolve(server,"../../deploy");
  const expected=[...['main','app','broker','gateway','image-broker','image-codec','image-files','image-upstream','image-contracts','codex-host','codex-engine','codex-launcher','codex-receipts','codex-specialist-qualification','codex-automatic-routing','codex-deployment','codex-capabilities','engine-router'].map(name=>join(server,name+'.js')),join(deploy,'run-codex.sh'),join(deploy,'engine/codex_receipts.py'),join(deploy,'codex/config-generation-only.toml'),join(deploy,'codex/models.json'),join(deploy,'codex/skills/sova-local-tools/SKILL.md'),resolve(deploy,'../tools/image/image-mcp.mjs'),resolve(deploy,'../tools/image/image.mjs')];
  if(!value.sourceClosure || Object.keys(value.sourceClosure).sort().join()!==expected.sort().join())return generationClosed();
  for(const path of expected){const stat=lstatSync(path);if(!stat.isFile()||stat.isSymbolicLink()||stat.mode&0o022||![0,process.getuid?.()].includes(stat.uid)||realpathSync(path)!==path||createHash('sha256').update(readFileSync(path)).digest('hex')!==value.sourceClosure[path])return generationClosed();}
  return validateCodexGenerationOnly(value,name=>readMimoEvidence(CODEX_SPECIALIST_DIRECTORY+"/"+name));
 }catch{return generationClosed();}
}
