import {
  TECHNICAL_VISION_LIMITS as L, TechnicalVisionError,
  type TechnicalVisionInput, type TechnicalVisionSource, type TechnicalVisionBox,
  type TechnicalVisionManifest, type TechnicalVisionIdentity, type TechnicalVisionOwner,
  type TechnicalVisionResult, type TechnicalVisionJob,
} from "./technical-vision-contracts.js";

type Obj = Record<string, any>;
function fail(code: "invalid_request" | "invalid_evidence" | "invalid_response" = "invalid_response"): never { throw new TechnicalVisionError(code); }
function obj(v: unknown, required: string[], optional: string[] = []): Obj {
  if (!v || typeof v !== "object" || Array.isArray(v) || Object.getPrototypeOf(v) !== Object.prototype) fail();
  const o = v as Obj;
  if (required.some(k => !Object.hasOwn(o, k)) || Object.keys(o).some(k => ![...required, ...optional].includes(k))) fail();
  return o;
}
function str(v: unknown, max = 8192): string {
  if (typeof v !== "string" || !v.length || v.length > max || /[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]/.test(v) || /data:(?:image|application)\/[^;]+;base64,/i.test(v)) fail();
  return v;
}
function id(v: unknown): string { if (typeof v !== "string" || !/^[a-zA-Z0-9_-]{1,80}$/.test(v)) fail(); return v; }
function integer(v: unknown, min = 0, max = Number.MAX_SAFE_INTEGER): number { if (!Number.isSafeInteger(v) || Number(v) < min || Number(v) > max) fail(); return Number(v); }
function list(v: unknown, max: number = L.records): any[] { if (!Array.isArray(v) || v.length > max) fail(); return v; }
function ids(v: unknown, minimum = 0): string[] { const a = list(v).map(id); if (a.length < minimum || new Set(a).size !== a.length) fail(); return a; }
function enumeration(v: unknown, choices: readonly string[]) { if (!choices.includes(String(v))) fail(); }
export function technicalVisionEqual(a: unknown, b: unknown): boolean {
  if (a === b) return true;
  if (!a || !b || typeof a !== "object" || typeof b !== "object") return false;
  const aa = a as Obj, bb = b as Obj;
  return Array.isArray(a) === Array.isArray(b) && Object.keys(aa).length === Object.keys(bb).length && Object.keys(aa).every(k => Object.hasOwn(bb, k) && technicalVisionEqual(aa[k], bb[k]));
}
export function validateTechnicalVisionSource(v: unknown): TechnicalVisionSource {
  const o = obj(v, [], ["fileId", "workspacePath"]);
  if (Object.keys(o).length !== 1) fail();
  if (Object.hasOwn(o, "fileId")) id(o.fileId);
  else {
    const p = str(o.workspacePath, 1000);
    if (/^[\\/]|[:\\%?#\r\n\t]/.test(p) || p.split("/").some(s => !s || s === "." || s === "..") || p.split("/").length > 32) fail();
  }
  return structuredClone(o) as TechnicalVisionSource;
}
export function validateTechnicalVisionBox(v: unknown): TechnicalVisionBox {
  const b = obj(v, ["x", "y", "width", "height"]);
  integer(b.x); integer(b.y); integer(b.width, 1); integer(b.height, 1);
  return b as TechnicalVisionBox;
}
export function contains(outer: TechnicalVisionBox, inner: TechnicalVisionBox): boolean {
  return inner.x >= outer.x && inner.y >= outer.y && inner.x + inner.width <= outer.x + outer.width && inner.y + inner.height <= outer.y + outer.height;
}
export function validateTechnicalVisionInput(v: unknown): TechnicalVisionInput {
  try {
    const o = obj(v, ["requestId", "source"], ["pages", "crops", "question"]);
    id(o.requestId); validateTechnicalVisionSource(o.source);
    if (o.pages !== undefined) {
      const pages = list(o.pages, L.pageCount); if (!pages.length || new Set(pages).size !== pages.length) fail();
      pages.forEach(p => integer(p, 1, 10000));
    }
    if (o.crops !== undefined) {
      const crops = list(o.crops, L.cropCount), seen = new Set<string>();
      for (const c of crops) {
        obj(c, ["id", "page", "x", "y", "width", "height"]); id(c.id); integer(c.page, 1, 10000);
        validateTechnicalVisionBox({ x: c.x, y: c.y, width: c.width, height: c.height });
        if (seen.has(c.id) || (o.pages && !o.pages.includes(c.page))) fail(); seen.add(c.id);
      }
    }
    if (o.question !== undefined) str(o.question, 4000);
    return structuredClone(o) as TechnicalVisionInput;
  } catch { fail("invalid_request"); }
}
export function validateTechnicalVisionOwner(v: unknown): TechnicalVisionOwner {
  const o = obj(v, ["sessionId", "workspaceId", "runId"]); Object.values(o).forEach(id); return o as TechnicalVisionOwner;
}
export function validateTechnicalVisionIdentity(v: unknown): TechnicalVisionIdentity {
  const s = obj(v, ["serviceId", "generation", "mode", "interpreter", "parser"]);
  id(s.serviceId); integer(s.generation); enumeration(s.mode, ["mock", "live"]);
  const i = obj(s.interpreter, ["model", "revision", "precision"]), p = obj(s.parser, ["model", "revision"]);
  if (i.model !== "Qwen/Qwen3.5-9B" || i.precision !== "BF16" || p.model !== "PaddlePaddle/PaddleOCR-VL-1.6") fail();
  for (const model of [i, p]) {
    str(model.revision, 128);
    if (s.mode === "live" && !/^[a-f0-9]{40}$/.test(model.revision)) fail();
  }
  if (s.mode === "mock" && s.generation !== 0) fail();
  return s as TechnicalVisionIdentity;
}
export function validateTechnicalVisionManifest(v: unknown): TechnicalVisionManifest {
  const s = obj(v, ["reference", "sha256", "mediaType", "coordinateSpace", "pages", "crops"]);
  validateTechnicalVisionSource(s.reference);
  if (typeof s.sha256 !== "string" || !/^[a-f0-9]{64}$/.test(s.sha256) || s.coordinateSpace !== "oriented_page_pixels") fail();
  enumeration(s.mediaType, ["image/png", "image/jpeg", "application/pdf"]);
  const pages = list(s.pages, L.pageCount), seen = new Set<number>(); if (!pages.length) fail();
  for (const p of pages) {
    obj(p, ["page", "width", "height", "originalWidth", "originalHeight", "orientation"], ["pdf"]);
    integer(p.page, 1, 10000); integer(p.width, 1, L.edge); integer(p.height, 1, L.edge);
    integer(p.originalWidth, 1, L.edge); integer(p.originalHeight, 1, L.edge); integer(p.orientation, 1, 8);
    if (p.width * p.height > L.pagePixels || seen.has(p.page)) fail(); seen.add(p.page);
    const swap = p.orientation >= 5;
    if (p.width !== (swap ? p.originalHeight : p.originalWidth) || p.height !== (swap ? p.originalWidth : p.originalHeight)) fail();
    if (s.mediaType === "application/pdf") {
      const pdf = obj(p.pdf, ["widthPoints", "heightPoints", "rotation"]);
      for (const dim of [pdf.widthPoints, pdf.heightPoints]) if (typeof dim !== "number" || !Number.isFinite(dim) || dim <= 0 || dim > 100000) fail();
      if (![0, 90, 180, 270].includes(pdf.rotation)) fail();
    } else if (p.pdf !== undefined || p.page !== 1 || pages.length !== 1) fail();
  }
  const seenCrops = new Set<string>();
  for (const c of list(s.crops, L.cropCount)) {
    obj(c, ["id", "page", "x", "y", "width", "height"]); id(c.id); integer(c.page, 1, 10000);
    const box = validateTechnicalVisionBox({ x: c.x, y: c.y, width: c.width, height: c.height });
    const page = pages.find(p => p.page === c.page);
    if (!page || seenCrops.has(c.id) || !contains({ x: 0, y: 0, width: page.width, height: page.height }, box)) fail();
    seenCrops.add(c.id);
  }
  return s as TechnicalVisionManifest;
}
export function validateTechnicalVisionResult(v: unknown, source: TechnicalVisionManifest, service: TechnicalVisionIdentity): TechnicalVisionResult {
  try {
    const r = obj(v, ["schemaVersion", "service", "source", "description", "evidence", "extraction", "observations", "uncertainties", "derivedConclusions", "electricalNetReconstruction"]);
    if (r.schemaVersion !== 1 || r.electricalNetReconstruction !== "not_qualified") fail();
    validateTechnicalVisionManifest(r.source); validateTechnicalVisionIdentity(r.service);
    if (!technicalVisionEqual(source, r.source) || !technicalVisionEqual(service, r.service)) fail(); str(r.description, 65536);
    const all = new Map<string, string>(), evidence = new Set<string>();
    const register = (v: unknown, kind: string) => { const key = id(v); if (all.has(key)) fail(); all.set(key, kind); return key; };
    for (const e of list(r.evidence)) {
      obj(e, ["id", "page", "box"], ["cropId"]); evidence.add(register(e.id, "evidence")); integer(e.page, 1, 10000);
      const box = validateTechnicalVisionBox(e.box), page = source.pages.find(p => p.page === e.page);
      if (!page || !contains({ x: 0, y: 0, width: page.width, height: page.height }, box)) fail();
      if (e.cropId !== undefined) { id(e.cropId); const c = source.crops.find(c => c.id === e.cropId && c.page === e.page); if (!c || !contains(c, box)) fail(); }
    }
    const evidenceRefs = (a: unknown, minimum = 1) => { for (const key of ids(a, minimum)) if (!evidence.has(key)) fail(); };
    const grounded = (o: Obj, kind: string) => { register(o.id, kind); evidenceRefs(o.evidenceIds); };
    const ex = obj(r.extraction, ["text", "tables", "formulas", "layout"]);
    for (const t of list(ex.text)) { obj(t, ["id", "kind", "exactText", "evidenceIds"]); enumeration(t.kind, ["label", "reference_designator", "value", "unit", "pin", "dimension", "text"]); str(t.exactText); grounded(t, t.kind); }
    for (const t of list(ex.tables)) {
      obj(t, ["id", "cells", "evidenceIds"]); grounded(t, "table"); const cells = list(t.cells), seen = new Set<string>(); if (!cells.length) fail();
      for (const c of cells) { obj(c, ["row", "column", "exactText", "evidenceIds"]); integer(c.row, 0, 10000); integer(c.column, 0, 10000); str(c.exactText); evidenceRefs(c.evidenceIds); const key = `${c.row}:${c.column}`; if (seen.has(key)) fail(); seen.add(key); }
    }
    for (const f of list(ex.formulas)) { obj(f, ["id", "exactText", "evidenceIds"]); str(f.exactText); grounded(f, "formula"); }
    for (const l of list(ex.layout)) { obj(l, ["id", "kind", "evidenceIds"]); str(l.kind, 128); grounded(l, "layout"); }
    const ob = obj(r.observations, ["components", "relationships"]);
    for (const c of list(ob.components)) { obj(c, ["id", "kind", "labelIds", "valueIds", "unitIds", "pinLabelIds", "evidenceIds"]); str(c.kind, 128); grounded(c, "component"); ids(c.labelIds); ids(c.valueIds); ids(c.unitIds); ids(c.pinLabelIds); }
    for (const rel of list(ob.relationships)) { obj(rel, ["id", "kind", "from", "to", "description", "evidenceIds"]); enumeration(rel.kind, ["spatial", "visible_connection", "crossing", "junction", "other"]); id(rel.from); id(rel.to); str(rel.description); grounded(rel, "relationship"); }
    for (const u of list(r.uncertainties)) { obj(u, ["id", "description", "evidenceIds", "affectedIds"]); register(u.id, "uncertainty"); str(u.description); evidenceRefs(u.evidenceIds, 0); ids(u.affectedIds); }
    for (const d of list(r.derivedConclusions)) { obj(d, ["id", "description", "basisIds", "evidenceIds", "uncertaintyIds"]); register(d.id, "derived"); str(d.description); ids(d.basisIds, 1); evidenceRefs(d.evidenceIds, 0); ids(d.uncertaintyIds); }
    const refs = (a: string[], kinds?: string[]) => { for (const key of a) if (!all.has(key) || (kinds && !kinds.includes(all.get(key)!))) fail(); };
    for (const c of ob.components) { refs(c.labelIds, ["label", "reference_designator"]); refs(c.valueIds, ["value", "dimension"]); refs(c.unitIds, ["unit"]); refs(c.pinLabelIds, ["pin"]); }
    for (const rel of ob.relationships) refs([rel.from, rel.to], ["component"]);
    for (const u of r.uncertainties) refs(u.affectedIds);
    for (const d of r.derivedConclusions) { refs(d.basisIds, ["label", "reference_designator", "value", "unit", "pin", "dimension", "text", "component", "relationship", "table", "formula", "layout", "evidence"]); refs(d.uncertaintyIds, ["uncertainty"]); }
    return structuredClone(r) as TechnicalVisionResult;
  } catch { fail("invalid_evidence"); }
}
export function validateTechnicalVisionJob(v: unknown, owner: TechnicalVisionOwner, service: TechnicalVisionIdentity, expected?: { jobId?: string; requestId?: string; source?: TechnicalVisionManifest }): TechnicalVisionJob {
  const j = obj(v, ["schemaVersion", "jobId", "requestId", "owner", "service", "source", "state", "settled", "cancelRequested"], ["queuePosition", "result", "error"]);
  id(j.jobId); id(j.requestId); validateTechnicalVisionOwner(j.owner); validateTechnicalVisionIdentity(j.service); validateTechnicalVisionManifest(j.source);
  if (j.schemaVersion !== 1 || !technicalVisionEqual(owner, j.owner) || !technicalVisionEqual(service, j.service) || (expected?.jobId && j.jobId !== expected.jobId) || (expected?.requestId && j.requestId !== expected.requestId) || (expected?.source && !technicalVisionEqual(expected.source, j.source))) fail();
  enumeration(j.state, ["queued", "running", "cancelling", "completed", "failed", "cancelled", "interrupted"]);
  if (typeof j.settled !== "boolean" || typeof j.cancelRequested !== "boolean") fail();
  const terminal = ["completed", "failed", "cancelled", "interrupted"].includes(j.state);
  if (!terminal && j.settled) fail();
  if (["completed", "failed", "cancelled"].includes(j.state) && !j.settled) fail();
  if (["cancelled", "cancelling"].includes(j.state) && !j.cancelRequested) fail();
  if (j.state === "completed" && j.cancelRequested) fail();
  if (j.queuePosition !== undefined) { integer(j.queuePosition, 1, 10000); if (j.state !== "queued") fail(); }
  if (j.state === "completed") { if (j.error !== undefined) fail(); validateTechnicalVisionResult(j.result, j.source, j.service); }
  else if (j.result !== undefined) fail();
  if (j.error !== undefined) { obj(j.error, ["code", "message"]); enumeration(j.error.code, ["analysis_failed", "cancelled", "interrupted", "source_invalid"]); str(j.error.message, 1000); }
  if (["failed", "interrupted"].includes(j.state) && !j.error) fail();
  // Discard service-supplied diagnostic text; it must never reflect host paths or credentials.
  const out = structuredClone(j) as TechnicalVisionJob;
  if (out.error) out.error.message = "Technical vision job did not complete; inspect protected service diagnostics";
  return out;
}
