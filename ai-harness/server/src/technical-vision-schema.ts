/** Reusable draft-07 wire schemas. Cross-record identity/geometry checks live in validation.ts. */
import { TECHNICAL_VISION_LIMITS as L, technicalVisionSourceSchema } from "./technical-vision-contracts.js";
type Schema = Record<string, unknown>;
const id: Schema = { type: "string", pattern: "^[a-zA-Z0-9_-]{1,80}$" };
const text: Schema = { type: "string", minLength: 1, maxLength: 8192 };
const description: Schema = { ...text, maxLength: 65536 };
const integer = (minimum = 0, maximum = Number.MAX_SAFE_INTEGER): Schema => ({ type: "integer", minimum, maximum });
const array = (items: Schema, minItems = 0, maxItems: number = L.records): Schema => ({ type: "array", items, minItems, maxItems });
const ids = (minItems = 0): Schema => ({ ...array(id, minItems), uniqueItems: true });
const object = (properties: Record<string, Schema>, optional: string[] = []): Schema => ({ type: "object", additionalProperties: false, properties, required: Object.keys(properties).filter(k => !optional.includes(k)) });
const boxProperties = { x: integer(), y: integer(), width: integer(1), height: integer(1) };
const crop = object({ id, page: integer(1, 10000), ...boxProperties });
export const technicalVisionOwnerSchema = object({ sessionId: id, workspaceId: id, runId: id });
export const technicalVisionIdentitySchema: Schema = {
  ...object({ serviceId: id, generation: integer(), mode: { enum: ["mock", "live"] },
    interpreter: object({ model: { const: "Qwen/Qwen3.5-9B" }, revision: { ...text, maxLength: 128 }, precision: { const: "BF16" } }),
    parser: object({ model: { const: "PaddlePaddle/PaddleOCR-VL-1.6" }, revision: { ...text, maxLength: 128 } }),
  }),
  allOf: [
    { if: { properties: { mode: { const: "mock" } } }, then: { properties: { generation: { const: 0 } } } },
    { if: { properties: { mode: { const: "live" } } }, then: { properties: {
      interpreter: { properties: { revision: { pattern: "^[a-f0-9]{40}$" } } }, parser: { properties: { revision: { pattern: "^[a-f0-9]{40}$" } } },
    } } },
  ],
};
export const technicalVisionManifestSchema = object({
  reference: technicalVisionSourceSchema,
  sha256: { type: "string", pattern: "^[a-f0-9]{64}$" }, mediaType: { enum: ["image/png", "image/jpeg", "application/pdf"] }, coordinateSpace: { const: "oriented_page_pixels" },
  pages: array(object({ page: integer(1, 10000), width: integer(1, L.edge), height: integer(1, L.edge), originalWidth: integer(1, L.edge), originalHeight: integer(1, L.edge), orientation: integer(1, 8),
    pdf: object({ widthPoints: { type: "number", exclusiveMinimum: 0, maximum: 100000 }, heightPoints: { type: "number", exclusiveMinimum: 0, maximum: 100000 }, rotation: { enum: [0, 90, 180, 270] } }),
  }, ["pdf"]), 1, L.pageCount),
  crops: array(crop, 0, L.cropCount),
});
const grounded = { id, evidenceIds: ids(1) };
export const technicalVisionResultSchema: Schema = {
  $schema: "http://json-schema.org/draft-07/schema#",
  ...object({
    schemaVersion: { const: 1 }, service: technicalVisionIdentitySchema, source: technicalVisionManifestSchema, description,
    evidence: array(object({ id, page: integer(1, 10000), cropId: id, box: object(boxProperties) }, ["cropId"])),
    extraction: object({
      text: array(object({ ...grounded, kind: { enum: ["label", "reference_designator", "value", "unit", "pin", "dimension", "text"] }, exactText: text })),
      tables: array(object({ ...grounded, cells: array(object({ row: integer(0, 10000), column: integer(0, 10000), exactText: text, evidenceIds: ids(1) }), 1) })),
      formulas: array(object({ ...grounded, exactText: text })), layout: array(object({ ...grounded, kind: { ...text, maxLength: 128 } })),
    }),
    observations: object({
      components: array(object({ ...grounded, kind: { ...text, maxLength: 128 }, labelIds: ids(), valueIds: ids(), unitIds: ids(), pinLabelIds: ids() })),
      relationships: array(object({ ...grounded, kind: { enum: ["spatial", "visible_connection", "crossing", "junction", "other"] }, from: id, to: id, description: text })),
    }),
    uncertainties: array(object({ id, description: text, evidenceIds: ids(), affectedIds: ids() })),
    derivedConclusions: array(object({ id, description: text, basisIds: ids(1), evidenceIds: ids(), uncertaintyIds: ids() })),
    electricalNetReconstruction: { const: "not_qualified" },
  }),
};
export const technicalVisionJobSchema: Schema = {
  ...object({ schemaVersion: { const: 1 }, jobId: id, requestId: id, owner: technicalVisionOwnerSchema, service: technicalVisionIdentitySchema, source: technicalVisionManifestSchema,
    state: { enum: ["queued", "running", "cancelling", "completed", "failed", "cancelled", "interrupted"] }, settled: { type: "boolean" }, cancelRequested: { type: "boolean" }, queuePosition: integer(1, 10000), result: technicalVisionResultSchema,
    error: object({ code: { enum: ["analysis_failed", "cancelled", "interrupted", "source_invalid"] }, message: { ...text, maxLength: 1000 } }),
  }, ["queuePosition", "result", "error"]),
  allOf: [
    { if: { properties: { state: { const: "completed" } } }, then: { required: ["result"], properties: { settled: { const: true }, cancelRequested: { const: false } }, not: { required: ["error"] } }, else: { not: { required: ["result"] } } },
    { if: { properties: { state: { enum: ["queued", "running", "cancelling"] } } }, then: { properties: { settled: { const: false } } } },
    { if: { properties: { state: { enum: ["failed", "cancelled"] } } }, then: { properties: { settled: { const: true } } } },
    { if: { properties: { state: { enum: ["failed", "interrupted"] } } }, then: { required: ["error"] } },
    { if: { properties: { state: { enum: ["cancelled", "cancelling"] } } }, then: { properties: { cancelRequested: { const: true } } } },
    { if: { required: ["queuePosition"] }, then: { properties: { state: { const: "queued" } } } },
  ],
};
