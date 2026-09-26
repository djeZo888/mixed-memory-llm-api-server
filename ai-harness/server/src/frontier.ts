/** Fixed frontier contract. Tokenization is backend-rendered, never o200k. */
import { ApiError } from "./errors.js";
export const FRONTIER_REVISION = "eb9eb208eb0d988989d07a6a12d0fdeb5f52574a";
// Root-frozen source evidence: SGLang-KT tp_worker.py267-271,
// scheduler.py1395 and utils.py101 at this exact revision (Flash pin above).
// With context/pool 480000: input <=479993, input+requested output <=479998.
// Actual pool/readback remains a backend activation gate.
export const FRONTIER_RUNTIME_REVISION =
  "541ddc37cbc92c60dc748db5ff1a2aad0b069a80";
export const FRONTIER_INPUT_MARGIN = 7;
export const FRONTIER_TOTAL_MARGIN = 2;
export const FRONTIER_MODEL = "glm-5.3-flash";
export const FRONTIER_URL = "http://10.156.100.60:30010/v1";
export type FrontierRequestState =
  "queued" | "active" | "settled" | "cancelled" | "quarantined" | "rejected";
export interface FrontierRecord {
  id: string;
  sessionId: string;
  state: FrontierRequestState;
  model: typeof FRONTIER_MODEL;
  contextWindow: number;
  promptTokens?: number;
  reservedOutput?: number;
  updatedAt: string;
}
export interface FrontierOptions {
  contextWindow: 128000 | 256000 | 480000;
  tokenizerRevision: string;
  templateRevision: string;
  upstreamKey: string | (() => string | Promise<string>);
  /** Loopback-only fixture seam; deployment has no configurable URL. */
  fixtureUrl?: string;
  countTimeoutMs?: number;
  fixtureQueueTimeoutMs?: number;
  onRequestState: (record: FrontierRecord) => void;
}
export function frontierUrl(options: FrontierOptions): string {
  if (!options.fixtureUrl) {
    if (options.fixtureQueueTimeoutMs !== undefined)
      throw Error("Queue clock override requires loopback fixture");
    return FRONTIER_URL;
  }
  const u = new URL(options.fixtureUrl);
  if (
    u.protocol !== "http:" ||
    u.hostname !== "127.0.0.1" ||
    u.username ||
    u.password ||
    u.search ||
    u.hash
  )
    throw Error("Invalid frontier fixture URL");
  return u.href.replace(/\/$/, "");
}
/** Closed text-only message grammar: unknown/nested content blocks never reach
 * tokenization. Tool schemas/arguments remain data, not model media inputs. */
function textMessages(value: unknown): boolean {
  const object = (v: unknown): v is Record<string, unknown> =>
    !!v && typeof v === "object" && !Array.isArray(v);
  const keys = (v: Record<string, unknown>, allowed: string[]) =>
    Object.keys(v).every((k) => allowed.includes(k));
  return (
    Array.isArray(value) &&
    value.every((message) => {
      if (
        !object(message) ||
        !keys(message, [
          "role",
          "content",
          "name",
          "tool_calls",
          "tool_call_id",
          "reasoning_content",
        ]) ||
        typeof message.role !== "string" ||
        !["system", "developer", "user", "assistant", "tool"].includes(
          message.role,
        )
      )
        return false;
      for (const key of ["name", "tool_call_id", "reasoning_content"])
        if (message[key] !== undefined && typeof message[key] !== "string")
          return false;
      const content = message.content;
      if (!(
        typeof content === "string" ||
        (content == null &&
          message.role === "assistant" &&
          Array.isArray(message.tool_calls)) ||
        (Array.isArray(content) &&
          content.every(
            (block) =>
              object(block) &&
              keys(block, ["type", "text"]) &&
              block.type === "text" &&
              typeof block.text === "string",
          ))
      ))
        return false;
      if (
        message.tool_calls !== undefined &&
        (message.role !== "assistant" ||
          !Array.isArray(message.tool_calls) ||
          !message.tool_calls.every(
            (call) =>
              object(call) &&
              keys(call, ["id", "type", "function"]) &&
              typeof call.id === "string" &&
              call.type === "function" &&
              object(call.function) &&
              keys(call.function, ["name", "arguments"]) &&
              typeof call.function.name === "string" &&
              (typeof call.function.arguments === "string" ||
                object(call.function.arguments)),
          ))
      )
        return false;
      return true;
    })
  );
}
export function frontierBody(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value))
    throw new ApiError(400, "invalid_request", "Expected object");
  const b = value as Record<string, unknown>;
  // Pin all template-affecting inputs. No caller URL, provider, template or model overrides.
  const allowed = new Set([
    "model",
    "messages",
    "tools",
    "tool_choice",
    "parallel_tool_calls",
    "stream",
    "stream_options",
    "max_tokens",
    "max_completion_tokens",
    "temperature",
    "top_p",
    "stop",
    "reasoning_effort",
    "chat_template_kwargs",
    "store",
    "prompt_cache_key",
    "prompt_cache_retention",
  ]);
  if (
    Object.keys(b).some((k) => !allowed.has(k)) ||
    b.model !== FRONTIER_MODEL ||
    !textMessages(b.messages) ||
    (b.chat_template_kwargs !== undefined &&
      JSON.stringify(b.chat_template_kwargs) !== '{"clear_thinking":true}') ||
    (b.stream !== undefined && typeof b.stream !== "boolean")
  )
    throw new ApiError(
      400,
      "invalid_frontier_request",
      "Frontier accepts supported text-only messages",
    );
  if (b.store !== undefined && b.store !== false)
    throw new ApiError(
      400,
      "invalid_frontier_request",
      "Frontier storage is disabled",
    );
  const a = b.max_tokens,
    c = b.max_completion_tokens;
  if (
    (a !== undefined && c !== undefined && a !== c) ||
    [a, c].some(
      (x) => x !== undefined && (!Number.isSafeInteger(x) || Number(x) < 1),
    )
  )
    throw new ApiError(
      400,
      "invalid_output_limit",
      "Invalid frontier output limit",
    );
  const result = {
    ...b,
    max_tokens: Math.min(Number(a ?? c ?? 65536), 65536),
    reasoning_effort: "high",
    chat_template_kwargs: { clear_thinking: true },
  };
  delete (result as Record<string, unknown>).max_completion_tokens;
  delete (result as Record<string, unknown>).prompt_cache_key;
  delete (result as Record<string, unknown>).prompt_cache_retention;
  delete (result as Record<string, unknown>).store;
  return result;
}
export async function countFrontier(
  options: FrontierOptions,
  body: Record<string, unknown>,
  key: string,
  signal: AbortSignal,
) {
  if (
    ![128000, 256000, 480000].includes(options.contextWindow) ||
    options.tokenizerRevision !== FRONTIER_REVISION ||
    options.templateRevision !== FRONTIER_REVISION
  )
    throw new ApiError(
      503,
      "frontier_unqualified",
      "Frontier tokenizer qualification is unavailable",
    );
  try {
    const response = await fetch(`${frontierUrl(options)}/tokenize`, {
      method: "POST",
      redirect: "error",
      headers: {
        authorization: `Bearer ${key}`,
        "content-type": "application/json",
      },
      body: JSON.stringify(body),
      signal: AbortSignal.any([
        signal,
        AbortSignal.timeout(options.countTimeoutMs ?? 15000),
      ]),
    });
    if (!response.ok || !response.body) {
      await response.body?.cancel();
      throw Error("count unavailable");
    }
    const reader = response.body.getReader();
    let text = "";
    let bytes = 0;
    try {
      for (;;) {
        const r = await reader.read();
        if (r.done) break;
        bytes += r.value.byteLength;
        if (bytes > 16384) throw Error("oversized count");
        text += Buffer.from(r.value).toString("utf8");
      }
    } finally {
      await reader.cancel().catch(() => {});
    }
    const v = JSON.parse(text);
    if (
      v.tokenizer_revision !== options.tokenizerRevision ||
      v.template_revision !== options.templateRevision ||
      v.context_limit !== options.contextWindow ||
      !Number.isSafeInteger(v.count) ||
      v.count < 0
    )
      throw Error("count identity mismatch");
    // The frozen count includes every rendered history/tool/template prefix.
    // max_tokens reserves all future reasoning + answer tokens. Retain the
    // pinned native input/total margins even though the template is exact.
    // Reject overflow rather than mutate the payload after it has been counted.
    const output = Number(body.max_tokens);
    if (
      !Number.isSafeInteger(output) ||
      output < 1 ||
      output > 65536 ||
      v.count > options.contextWindow - FRONTIER_INPUT_MARGIN ||
      v.count + output > options.contextWindow - FRONTIER_TOTAL_MARGIN
    )
      throw new ApiError(
        413,
        "frontier_context_full",
        "Rendered frontier input and reserved output exceed configured context",
      );
    return { promptTokens: v.count as number, reservedOutput: output };
  } catch (error) {
    if (error instanceof ApiError) throw error;
    throw new ApiError(
      503,
      "frontier_tokenizer_unavailable",
      "Exact frontier token accounting unavailable",
    );
  }
}

export type FrontierConfiguration = Pick<
  FrontierOptions,
  "contextWindow" | "tokenizerRevision" | "templateRevision"
>;
/** Invalid or unqualified source config disables only the frontier route. */
export function frontierConfiguration(
  value: unknown,
): FrontierConfiguration | undefined {
  if (!value || typeof value !== "object" || Array.isArray(value)) return;
  const v = value as Record<string, unknown>;
  if (
    v.qualified !== true ||
    v.model !== FRONTIER_MODEL ||
    typeof v.contextWindow !== "number" ||
    ![128000, 256000, 480000].includes(v.contextWindow) ||
    v.maxOutputTokens !== 65536 ||
    v.tokenizerRevision !== FRONTIER_REVISION ||
    v.templateRevision !== FRONTIER_REVISION
  )
    return;
  return {
    contextWindow: v.contextWindow as FrontierOptions["contextWindow"],
    tokenizerRevision: FRONTIER_REVISION,
    templateRevision: FRONTIER_REVISION,
  };
}
