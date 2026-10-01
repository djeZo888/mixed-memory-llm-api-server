/** H039 candidate contract. No registration, native pixels or production readiness is implied. */
export const TECHNICAL_VISION_VERSION = 1 as const;
export const TECHNICAL_VISION_LIMITS = Object.freeze({
  sourceBytes: 25 * 1024 * 1024,
  pageCount: 4,
  cropCount: 8,
  pagePixels: 16_000_000,
  edge: 4096,
  responseBytes: 1024 * 1024,
  records: 1024,
});
export type TechnicalVisionSource = { fileId: string } | { workspacePath: string };
export interface TechnicalVisionBox { x: number; y: number; width: number; height: number }
export interface TechnicalVisionCrop extends TechnicalVisionBox { id: string; page: number }
export interface TechnicalVisionInput {
  requestId: string;
  source: TechnicalVisionSource;
  /** PDF pages are one-based and explicit. Raster images have page 1. */
  pages?: number[];
  /** Top-left origin, in oriented whole-page pixels; no implicit resizing. */
  crops?: TechnicalVisionCrop[];
  question?: string;
}
export interface TechnicalVisionOwner { sessionId: string; workspaceId: string; runId: string }
export interface TechnicalVisionPage {
  page: number;
  width: number;
  height: number;
  originalWidth: number;
  originalHeight: number;
  orientation: number;
  pdf?: { widthPoints: number; heightPoints: number; rotation: 0 | 90 | 180 | 270 };
}
export interface TechnicalVisionManifest {
  reference: TechnicalVisionSource;
  sha256: string;
  mediaType: "image/png" | "image/jpeg" | "application/pdf";
  coordinateSpace: "oriented_page_pixels";
  pages: TechnicalVisionPage[];
  crops: TechnicalVisionCrop[];
}
/** Bytes remain exclusively on the host/service boundary, never in a tool response. */
export interface TechnicalVisionPrepared {
  manifest: TechnicalVisionManifest;
  images: { page: number; png: Buffer; sha256: string }[];
}
export interface TechnicalVisionIdentity {
  serviceId: string;
  generation: number;
  mode: "mock" | "live";
  interpreter: { model: "Qwen/Qwen3.5-9B"; revision: string; precision: "BF16" };
  parser: { model: "PaddlePaddle/PaddleOCR-VL-1.6"; revision: string };
}
export interface TechnicalVisionEvidence {
  id: string;
  page: number;
  cropId?: string;
  box: TechnicalVisionBox;
}
interface Grounded { id: string; evidenceIds: string[] }
export interface TechnicalVisionResult {
  schemaVersion: 1;
  service: TechnicalVisionIdentity;
  source: TechnicalVisionManifest;
  description: string;
  evidence: TechnicalVisionEvidence[];
  /** Literal parser/visible source facts. Numeric conversions do not belong here. */
  extraction: {
    text: (Grounded & { kind: "label" | "reference_designator" | "value" | "unit" | "pin" | "dimension" | "text"; exactText: string })[];
    tables: (Grounded & { cells: { row: number; column: number; exactText: string; evidenceIds: string[] }[] })[];
    formulas: (Grounded & { exactText: string })[];
    layout: (Grounded & { kind: string })[];
  };
  observations: {
    components: (Grounded & { kind: string; labelIds: string[]; valueIds: string[]; unitIds: string[]; pinLabelIds: string[] })[];
    relationships: (Grounded & { kind: "spatial" | "visible_connection" | "crossing" | "junction" | "other"; from: string; to: string; description: string })[];
  };
  uncertainties: { id: string; description: string; evidenceIds: string[]; affectedIds: string[] }[];
  derivedConclusions: { id: string; description: string; basisIds: string[]; evidenceIds: string[]; uncertaintyIds: string[] }[];
  /** Even a passing OCR result cannot assert electrical net reconstruction qualification. */
  electricalNetReconstruction: "not_qualified";
}
export type TechnicalVisionState = "queued" | "running" | "cancelling" | "completed" | "failed" | "cancelled" | "interrupted";
export interface TechnicalVisionJob {
  schemaVersion: 1;
  jobId: string;
  requestId: string;
  owner: TechnicalVisionOwner;
  service: TechnicalVisionIdentity;
  source: TechnicalVisionManifest;
  state: TechnicalVisionState;
  /** A terminal result is usable only after the service certifies owned execution settled. */
  settled: boolean;
  cancelRequested: boolean;
  queuePosition?: number;
  result?: TechnicalVisionResult;
  error?: { code: string; message: string };
}
export type TechnicalVisionErrorCode = "invalid_request" | "invalid_source" | "source_too_large" | "source_changed" | "unavailable" | "timeout" | "observation_cancelled" | "invalid_evidence" | "invalid_response" | "idempotency_conflict" | "queue_full" | "not_found";
const messages: Record<TechnicalVisionErrorCode, string> = {
  invalid_request: "Invalid technical vision request",
  invalid_source: "Source is not an owned supported image or PDF page reference",
  source_too_large: "Technical vision source exceeds the bounded profile",
  source_changed: "Technical vision source changed during preparation",
  unavailable: "Technical vision service or PDF renderer is unavailable",
  timeout: "Technical vision observation timed out; an admitted job may still be active",
  observation_cancelled: "Technical vision observation ended; this does not cancel admitted work",
  invalid_evidence: "Technical vision evidence does not match its source or references",
  invalid_response: "Technical vision service returned an invalid contract",
  idempotency_conflict: "Request identifier was already used for different work",
  queue_full: "Technical vision service queue is full",
  not_found: "Technical vision job was not found in the owned scope",
};
export class TechnicalVisionError extends Error {
  constructor(readonly code: TechnicalVisionErrorCode) { super(messages[code]); }
}

const idSchema = { type: "string", pattern: "^[a-zA-Z0-9_-]{1,80}$" };
const pageSchema = { type: "integer", minimum: 1, maximum: 10000 };
export const technicalVisionSourceSchema = {
  oneOf: [
    { type: "object", additionalProperties: false, required: ["fileId"], properties: { fileId: idSchema } },
    { type: "object", additionalProperties: false, required: ["workspacePath"], properties: { workspacePath: { type: "string", minLength: 1, maxLength: 1000, description: "Canonical relative path in the host-bound workspace; no URLs, symlinks or parent traversal" } } },
  ],
};
export const technicalVisionInputSchema = {
  type: "object", additionalProperties: false, required: ["requestId", "source"],
  properties: {
    requestId: idSchema,
    source: technicalVisionSourceSchema,
    pages: { type: "array", minItems: 1, maxItems: 4, uniqueItems: true, items: pageSchema },
    crops: { type: "array", maxItems: 8, items: { type: "object", additionalProperties: false, required: ["id", "page", "x", "y", "width", "height"], properties: {
      id: idSchema, page: pageSchema, x: { type: "integer", minimum: 0 }, y: { type: "integer", minimum: 0 }, width: { type: "integer", minimum: 1 }, height: { type: "integer", minimum: 1 },
    } } },
    question: { type: "string", minLength: 1, maxLength: 4000 },
  },
} as const;
