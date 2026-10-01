import { createHash } from "node:crypto";
/** Ordinary tools add retrieval without replacing operational instructions or other tools. */
export const CODEX_MEMORY_TOOLS = Object.freeze([
  { type: "function", name: "read_original", description: "Read this session's owned original ID at UTF-8 byte offsets. No paths or URLs.", inputSchema: { type: "object", properties: { reference: {type:"string"}, offset: {type:"integer",minimum:0}, limit: {type:"integer",minimum:1,maximum:8192} }, required:["reference","offset","limit"], additionalProperties:false } },
  { type: "function", name: "search_originals", description: "Bounded literal text search in this session's retained originals. No regular expressions or paths.", inputSchema: {type:"object",properties:{query:{type:"string",maxLength:256},after:{type:"integer",minimum:0},limit:{type:"integer",minimum:1,maximum:32}},required:["query"],additionalProperties:false} },
  { type: "function", name: "propose_session_state", description: "Save a proposed state for human review. Cannot accept state, grant permissions, or certify checks.", inputSchema:{type:"object",properties:{json:{type:"string",description:"AcceptedStateDraft JSON: objective, constraints, decisions, pending, checks. Check claim is unverified."}},required:["json"],additionalProperties:false} },
]);
export const CODEX_MEMORY_CATALOG_SHA256 = createHash("sha256").update(JSON.stringify(CODEX_MEMORY_TOOLS)).digest("hex");
export const codexMemoryTool = (tool: unknown): tool is string => typeof tool === "string" && CODEX_MEMORY_TOOLS.some(t => t.name === tool);
