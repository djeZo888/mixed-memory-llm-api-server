/** Reviewed protocol/budget policy, independent of current runtime admission.
 * These descriptors never grant live routing or qualify occupied context. */
import { ApiError } from "./errors.js";

export interface CodexProviderContract {
  readonly model: "qwen3.8-27b" | "mimo-v2.6-pro-rl";
  readonly contextWindow: 480000 | 950000;
  readonly maxOutputTokens: 65536;
  readonly autoCompactTokenLimit: 400000 | 880000;
  readonly reasoning: "none" | "mimo-plaintext";
  readonly parallelToolCalls: boolean;
  readonly tokenizer: "qwen-native-tokenize" | "mimo-native-input-tokens";
}
const QWEN: CodexProviderContract = Object.freeze({ model: "qwen3.8-27b", contextWindow: 480000,
  maxOutputTokens: 65536, autoCompactTokenLimit: 400000, reasoning: "none",
  parallelToolCalls: true, tokenizer: "qwen-native-tokenize" });
const MIMO: CodexProviderContract = Object.freeze({ model: "mimo-v2.6-pro-rl", contextWindow: 950000,
  maxOutputTokens: 65536, autoCompactTokenLimit: 880000, reasoning: "mimo-plaintext",
  parallelToolCalls: false, tokenizer: "mimo-native-input-tokens" });

export function codexProvider(model: unknown): CodexProviderContract {
  if (model === QWEN.model) return QWEN;
  if (model === MIMO.model) return MIMO;
  throw new ApiError(400, "codex_provider_unqualified", "Unsupported local Codex provider");
}
