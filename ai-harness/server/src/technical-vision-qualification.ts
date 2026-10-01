/** Root-installed technical specialist acceptance. No issuer or fixture can grant live authority. */
import { createHash } from "node:crypto";
import { lstatSync, readFileSync, realpathSync } from "node:fs";
import { join, dirname } from "node:path";
import { isDeepStrictEqual } from "node:util";
import { readMimoEvidence } from "./mimo-frontier.js";
import { validateTechnicalVisionIdentity } from "./technical-vision-validation.js";
import type { TechnicalVisionIdentity } from "./technical-vision-contracts.js";
export const TECHNICAL_VISION_ACCEPTANCE_FILE = "/etc/sova-qualification/technical-vision.json";
export const TECHNICAL_VISION_ORIGIN = "http://10.156.100.60:18193";
export const TECHNICAL_VISION_KEY_FILE = "/etc/sova/technical-vision.key";
export const TECHNICAL_VISION_SOURCE_GRAPH = ["main", "app", "broker", "gateway", "technical-vision-host", "technical-vision-tool", "technical-vision-qualification", "technical-vision-client", "technical-vision-sources", "technical-vision-validation", "technical-vision-contracts", "technical-vision-schema", "technical-vision-lifecycle", "codex-capabilities", "engine-router", "contracts", "store", "files"] as const;
export const TECHNICAL_VISION_PINS = Object.freeze({ gpuUuid: "GPU-14c23cbc-12f0-9c61-0fda-7aaf80fbd1bf", qwenRevision: "c202236235762e1c871ad0ccb60c8ee5ba337b9a", paddleRevision: "c5630abae1d940eafe0697512a0325494b02ab42", precision: "BF16", qwenContext: 16384, paddleContext: 8192, output: 4096, concurrency: 1, pages: 1, pixels: 2097152, edge: 4096, crops: 8, deadlineSeconds: 120, origin: TECHNICAL_VISION_ORIGIN });
export interface TechnicalVisionQualification { readonly service: TechnicalVisionIdentity; readonly evidenceSha256: string; readonly expiresAt: string }
const issued = new WeakSet<object>();
export const isTechnicalVisionQualification = (v: unknown): v is TechnicalVisionQualification => !!v && typeof v === "object" && issued.has(v);
const digest = (v: unknown): v is string => typeof v === "string" && /^[a-f0-9]{64}$/.test(v);
const sha = (b: Buffer | string) => createHash("sha256").update(b).digest("hex");
function exact(v: any, keys: readonly string[]) { if (!v || typeof v !== "object" || Array.isArray(v) || !isDeepStrictEqual(Object.keys(v).sort(), [...keys].sort())) throw Error("Invalid technical vision acceptance"); }
function protectedSource(file: string) {
  if (realpathSync(file) !== file) throw Error("Unsafe executing source");
  for (let p = file;; p = dirname(p)) { const s = lstatSync(p); if (s.uid !== 0 || s.mode & 0o022 || (p === file ? !s.isFile() || s.nlink !== 1 : !s.isDirectory())) throw Error("Unsafe executing source"); if (p === "/") break; }
  return sha(readFileSync(file));
}
/** Only the fixed root-owned acceptance graph can enable production. Missing evidence closes availability. */
export function loadTechnicalVisionQualification(now = Date.now()): TechnicalVisionQualification | undefined {
  try {
    const { text, value: r } = readMimoEvidence(TECHNICAL_VISION_ACCEPTANCE_FILE);
    exact(r, ["schema", "kind", "service", "pins", "origin", "reviewedAt", "expiresAt", "sourceBindings", "evidence"]);
    const service = validateTechnicalVisionIdentity(r.service);
    if (r.schema !== 1 || r.kind !== "root-accepted-technical-vision" || !isDeepStrictEqual(r.pins, TECHNICAL_VISION_PINS) || service.mode !== "live" || service.generation < 1 || r.origin !== TECHNICAL_VISION_ORIGIN || service.interpreter.revision !== "c202236235762e1c871ad0ccb60c8ee5ba337b9a" || service.parser.revision !== "c5630abae1d940eafe0697512a0325494b02ab42" || !Number.isFinite(Date.parse(r.reviewedAt)) || Date.parse(r.reviewedAt) > now || !Number.isFinite(Date.parse(r.expiresAt)) || Date.parse(r.expiresAt) <= now || Date.parse(r.expiresAt) - Date.parse(r.reviewedAt) > 24 * 3600000) return undefined;
    exact(r.sourceBindings, TECHNICAL_VISION_SOURCE_GRAPH);
    for (const module of TECHNICAL_VISION_SOURCE_GRAPH) if (!digest(r.sourceBindings[module]) || protectedSource(join(import.meta.dirname, module + ".js")) !== r.sourceBindings[module]) return undefined;
    exact(r.evidence, ["runtime", "source", "owner", "ingress", "imageOCR"]);
    const sourceGraphSha256 = sha(JSON.stringify(r.sourceBindings));
    let ownerReceiptSha256: string | undefined;
    for (const kind of ["runtime", "source", "owner", "ingress", "imageOCR"]) {
      const ref = r.evidence[kind]; exact(ref, ["file", "sha256"]);
      if (!/^[a-zA-Z0-9_-]{1,80}\.json$/.test(ref.file) || !digest(ref.sha256)) return undefined;
      const e = readMimoEvidence("/etc/sova-qualification/" + ref.file);
      exact(e.value, ["schema", "kind", "result", "service", "sourceGraphSha256", "ownerReceiptSha256", "transcriptSha256", "settlementSha256"]);
      if (sha(e.text) !== ref.sha256 || e.value.schema !== 1 || e.value.kind !== "live-technical-vision-" + kind || e.value.result !== "PASS" || !isDeepStrictEqual(e.value.service, service) || e.value.sourceGraphSha256 !== sourceGraphSha256 || ownerReceiptSha256 && e.value.ownerReceiptSha256 !== ownerReceiptSha256 || !["sourceGraphSha256", "ownerReceiptSha256", "transcriptSha256", "settlementSha256"].every(k => digest(e.value[k]))) return undefined;
      ownerReceiptSha256 ??= e.value.ownerReceiptSha256;
    }
    const q = Object.freeze({ service: structuredClone(service), evidenceSha256: sha(text), expiresAt: r.expiresAt }); issued.add(q); return q;
  } catch { return undefined; }
}
