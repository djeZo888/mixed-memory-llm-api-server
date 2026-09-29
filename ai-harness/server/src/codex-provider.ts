/** Reviewed protocol/budget policy, independent of current runtime admission.
 * These descriptors never grant live routing or qualify occupied context. */
import { ApiError } from "./errors.js";

export interface CodexProviderContract {
  readonly model: "qwen3.8-27b" | "mimo-v2.6-pro-rl";
  readonly contextWindow: 480000;
  readonly maxOutputTokens: 65536;
  readonly autoCompactTokenLimit: 400000;
  readonly reasoning: "none" | "mimo-plaintext";
  readonly parallelToolCalls: boolean;
  readonly tokenizer: "qwen-native-tokenize" | "mimo-native-input-tokens";
}
const QWEN: CodexProviderContract = Object.freeze({ model: "qwen3.8-27b", contextWindow: 480000,
  maxOutputTokens: 65536, autoCompactTokenLimit: 400000, reasoning: "none",
  parallelToolCalls: true, tokenizer: "qwen-native-tokenize" });
const MIMO: CodexProviderContract = Object.freeze({ model: "mimo-v2.6-pro-rl", contextWindow: 480000,
  maxOutputTokens: 65536, autoCompactTokenLimit: 400000, reasoning: "mimo-plaintext",
  parallelToolCalls: false, tokenizer: "mimo-native-input-tokens" });

export function codexProvider(model: unknown): CodexProviderContract {
  if (model === QWEN.model) return QWEN;
  if (model === MIMO.model) return MIMO;
  throw new ApiError(400, "codex_provider_unqualified", "Unsupported local Codex provider");
}

const record = (value: unknown): value is Record<string, unknown> =>
  !!value && typeof value === "object" && !Array.isArray(value);
const exactKeys = (value: Record<string, unknown>, keys: readonly string[]) =>
  Object.keys(value).length === keys.length && keys.every(key => Object.hasOwn(value, key));

/** H034: the pinned Qwen AUTO grammar leaves strict:false arguments unconstrained.
 * Enforce only the reviewed, explicit read-only capability query contract. Empty
 * schemas and all other tools retain their declared policy. This never rewrites
 * schemas, optional fields, generated arguments, or tool results.
 */
export function codexFunctionStrict(provider: CodexProviderContract,
  identity: { namespace?: string; originalName?: string },
  parameters: Record<string, unknown>, declaredStrict: boolean): boolean {
  if (declaredStrict || provider.model !== "qwen3.8-27b" ||
      identity.namespace !== "mcp__image" || identity.originalName !== "image_capabilities")
    return declaredStrict;
  // The native declaration may retain MCP's exact draft-07 dialect marker.
  const keys = ["type", "properties", "required", "additionalProperties"];
  const shape = exactKeys(parameters, keys) ||
    (exactKeys(parameters, [...keys, "$schema"]) && parameters.$schema === "http://json-schema.org/draft-07/schema#");
  if (!shape ||
      parameters.type !== "object" || parameters.additionalProperties !== false ||
      !Array.isArray(parameters.required) || parameters.required.length !== 1 || parameters.required[0] !== "query" ||
      !record(parameters.properties) || !exactKeys(parameters.properties, ["query"])) return false;
  const query = parameters.properties.query;
  return record(query) && exactKeys(query, ["type", "enum"]) && query.type === "string" &&
    Array.isArray(query.enum) && query.enum.length === 1 && query.enum[0] === "capabilities";
}
