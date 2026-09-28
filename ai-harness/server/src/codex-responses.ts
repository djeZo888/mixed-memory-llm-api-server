/** Narrow, stateless Responses compatibility for the reviewed Codex pin.
 * Every request still enters the existing gateway admission and transport.
 * Client-carried history only. Plaintext reasoning requires a verified provider contract.
 */
import { randomUUID, createHash } from "node:crypto";
import { StringDecoder } from "node:string_decoder";
import { ApiError } from "./errors.js";
import { codexProvider, type CodexProviderContract } from "./codex-provider.js";
export const CODEX_VERSION = "0.158.0";
export const CODEX_CONTEXT = { "qwen3.8-27b": 480000, "mimo-v2.6-pro-rl": 950000 } as const;
const object = (v: unknown): v is Record<string, any> => !!v && typeof v === "object" && !Array.isArray(v);
const reject = (message: string): never => { throw new ApiError(400, "unsupported_responses_contract", message); };
function fields(v: Record<string, any>, allowed: string[]) { if (Object.keys(v).some(k => !allowed.includes(k)))
    reject("Unsupported Responses field"); }
function string(v: unknown): string { if (typeof v !== "string")
    reject("Expected string"); return v as string; }
const uint = (v: unknown): v is number => Number.isSafeInteger(v) && Number(v) >= 0;
const NAMESPACE_TOOLS: Readonly<Record<string, readonly string[]>> = Object.freeze({
    multi_agent_v1: ["spawn_agent", "wait_agent", "send_input", "resume_agent", "close_agent"],
    mcp__browser: ["browser_open", "browser_download"],
    mcp__search: ["searxng_search"],
    mcp__image: ["image_capabilities", "image_generate", "image_edit"],
});
export interface ResponsesTranslation {
    body: Record<string, any>;
    provider: CodexProviderContract;
    tools: Map<string, {
        custom: boolean;
        grammar: boolean;
        namespace?: string;
        originalName?: string;
    }>;
}
export interface ResponsesFingerprint {
    bytes: number;
    sha256: string;
}
export interface ResponsesToolDiagnostic {
    /** Exact identity only when bounded and log-safe; the digest is always retained. */
    callId?: string;
    callIdSha256: string;
    transportName: string;
    name: string;
    namespace?: string;
    providerArguments: ResponsesFingerprint;
    responseArguments: ResponsesFingerprint;
    argumentShape: "object" | "array" | "scalar" | "invalid_json";
    /** Only declared schema keys and the three retained unexpected keys are exposed. */
    argumentKeys: string[];
    otherKeyCount: number;
}
export type ResponsesDiagnostic = {
    type: "provider_finish";
    responseId: string;
    model: string;
    finishReason: "stop" | "tool_calls" | "length" | "unsupported";
    finishReasonSha256: string;
} | {
    type: "response_terminal";
    responseId: string;
    model: string;
    finishReason: "stop" | "tool_calls" | "length";
    status: "completed" | "incomplete";
    messageId?: string;
    text: ResponsesFingerprint;
    reasoning?: ResponsesFingerprint;
    tools: ResponsesToolDiagnostic[];
    usage: { input_tokens: number; output_tokens: number; total_tokens: number };
};
const fingerprint = (value: string): ResponsesFingerprint => ({
    bytes: Buffer.byteLength(value), sha256: createHash("sha256").update(value).digest("hex"),
});
const diagnosticId = (value: string): string | undefined => /^[A-Za-z0-9_.:-]{1,256}$/.test(value) ? value : undefined;
// Exact upstream grammar hash; arbitrary grammars cannot be safely approximated.
const PATCH_GRAMMAR_SHA = "d6367f4826ed608c424b0a308f3d6163527df63c22513d089b91863552f8bfeb";
export function validPatch(text: string): boolean {
    const lines = text.split("\n");
    if (lines.at(-1) === "")
        lines.pop();
    if (lines.shift() !== "*** Begin Patch" || lines.pop() !== "*** End Patch" || !lines.length)
        return false;
    let i = 0, hunks = 0;
    while (i < lines.length) {
        const head = lines[i++]!;
        hunks++;
        if (/^\*\*\* Delete File: .+$/.test(head))
            continue;
        if (/^\*\*\* Add File: .+$/.test(head)) {
            const start = i;
            while (i < lines.length && lines[i]!.startsWith("+"))
                i++;
            if (i === start)
                return false;
        }
        else if (/^\*\*\* Update File: .+$/.test(head)) {
            if (/^\*\*\* Move to: .+$/.test(lines[i] ?? ""))
                i++;
            let changes = 0;
            while (i < lines.length && (/^(?:@@(?: .+)?|[+\- ].*)$/.test(lines[i]!))) {
                i++;
                changes++;
            }
            if (lines[i] === "*** End of File") {
                if (!changes)
                    return false;
                i++;
            }
        }
        else
            return false;
    }
    return hunks > 0;
}
export function translateResponses(value: unknown, outputLimit = 65536, selectedProvider?: CodexProviderContract): ResponsesTranslation {
    if (!Number.isSafeInteger(outputLimit) || outputLimit < 1 || outputLimit > 65536)
        throw Error("Invalid trusted Responses output limit");
    if (!object(value))
        reject("Expected Responses object");
    const b = value as Record<string, any>;
    fields(b, ["model", "instructions", "input", "tools", "tool_choice", "parallel_tool_calls", "reasoning", "store", "stream", "include", "prompt_cache_key", "client_metadata", "max_output_tokens"]);
    if (typeof b.model !== "string" || !Object.hasOwn(CODEX_CONTEXT, b.model))
        reject("Unsupported local model");
    const expectedProvider = codexProvider(b.model);
    const selected = selectedProvider ?? expectedProvider;
    if (Object.keys(expectedProvider).some(key =>
        selected[key as keyof CodexProviderContract] !== expectedProvider[key as keyof CodexProviderContract]))
        reject("Unqualified or mismatched provider contract");
    // Retain the immutable reviewed descriptor, not a caller-mutable policy object.
    const provider = expectedProvider;
    if (b.stream !== true || b.store !== false)
        reject("Only streaming stateless Responses are qualified");
    if (b.reasoning !== undefined && (!object(b.reasoning) || Object.keys(b.reasoning).length))
        reject("Reasoning settings lack a verified local contract");
    // 0.158.0 core/client.rs always requests this optional field. Availability is
    // acknowledged, never fabricated; actual encrypted input is rejected below.
    if (b.include !== undefined && JSON.stringify(b.include) !== '["reasoning.encrypted_content"]' && JSON.stringify(b.include) !== '[]')
        reject("Unsupported include");
    if (b.prompt_cache_key !== undefined)
        string(b.prompt_cache_key);
    if (b.client_metadata !== undefined && (!object(b.client_metadata) || Object.values(b.client_metadata).some(v => typeof v !== "string")))
        reject("Invalid metadata");
    if (b.tool_choice !== "auto" && b.tool_choice !== "none")
        reject("Unsupported tool choice");
    if (typeof b.parallel_tool_calls !== "boolean")
        reject("parallel_tool_calls required");
    if (!provider.parallelToolCalls && (b.parallel_tool_calls !== false || b.tool_choice !== "auto"))
        reject("Provider requires qualified serial auto tool semantics");
    const output = b.max_output_tokens ?? outputLimit;
    if (!uint(output) || output < 1 || output > outputLimit)
        reject("Output reservation must be 1..65536");
    const tools = new Map<string, {
        custom: boolean;
        grammar: boolean;
        namespace?: string;
        originalName?: string;
    }>();
    if (!Array.isArray(b.tools))
        reject("tools must be an array");
    const namespaced = new Map<string, { namespace: string; originalName: string }>();
    const expandedTools: any[] = [];
    const namespaceNames = new Set<string>();
    for (const t of b.tools) {
        if (!object(t)) reject("Invalid tool");
        if (t.type !== "namespace") {
            if (typeof t.name === "string" && t.name.startsWith("sova_ns_")) reject("Reserved namespace transport name");
            expandedTools.push(t); continue;
        }
        fields(t, ["type", "name", "description", "tools"]);
        // Only the actual captured pinned namespace is qualified. No custom/nested forms.
        if (!Object.hasOwn(NAMESPACE_TOOLS, t.name) || namespaceNames.has(t.name) || !Array.isArray(t.tools) || !t.tools.length)
            reject("Unsupported or duplicate namespace");
        string(t.description); namespaceNames.add(t.name);
        for (const inner of t.tools) {
            if (!object(inner) || inner.type !== "function" || !NAMESPACE_TOOLS[t.name]!.includes(inner.name))
                reject("Unsupported namespace tool");
            fields(inner, ["type", "name", "description", "strict", "parameters"]);
            // Aliases are looked up in the request-local map, never decoded. Keep the
            // qualified identity legible without an artificial numeric length marker.
            const name = `sova_ns_${t.name}_${inner.name}`;
            if (name.length > 64 || namespaced.has(name)) reject("Namespace transport collision or length");
            namespaced.set(name, { namespace: t.name, originalName: inner.name });
            expandedTools.push({ ...inner, name, description: `Namespace ${t.name} guidance: ${t.description}\n\n${string(inner.description)}` });
        }
    }
    const chatTools = expandedTools.map((t: any) => {
        if (!object(t))
            reject("Invalid tool");
        const name = string(t.name);
        if (!/^[A-Za-z0-9_-]{1,64}$/.test(name) || tools.has(name))
            reject("Invalid or duplicate tool name");
        if (t.type === "function") {
            fields(t, ["type", "name", "description", "strict", "parameters"]);
            if (!object(t.parameters) || typeof t.strict !== "boolean")
                reject("Invalid function schema");
            tools.set(name, { custom: false, grammar: false, ...namespaced.get(name) });
            return { type: "function", function: { name, description: string(t.description), parameters: t.parameters, strict: t.strict } };
        }
        if (t.type !== "custom")
            reject("Unsupported tool type");
        fields(t, ["type", "name", "description", "format"]);
        const f = t.format;
        let grammar = false;
        if (f !== undefined) {
            if (!object(f))
                reject("Invalid custom format");
            if (f.type === "text")
                fields(f, ["type"]);
            else if (f.type === "grammar" && f.syntax === "lark" && name === "apply_patch" && typeof f.definition === "string" && createHash("sha256").update(f.definition).digest("hex") === PATCH_GRAMMAR_SHA) {
                fields(f, ["type", "syntax", "definition"]);
                grammar = true;
            }
            else
                reject("Unsupported custom grammar");
        }
        tools.set(name, { custom: true, grammar });
        return { type: "function", function: { name, description: "Transport wrapper: put the exact custom tool text in the input string. " + string(t.description), strict: true, parameters: { type: "object", properties: { input: { type: "string" } }, required: ["input"], additionalProperties: false } } };
    });
    const messages: any[] = [];
    const calls = new Map<string, {
        name: string;
        custom: boolean;
    }>();
    const pending = new Set<string>();
    let pendingReasoning: string | undefined;
    let reasoningAssistant: any;
    if (b.instructions !== undefined)
        messages.push({ role: "system", content: string(b.instructions) });
    if (!Array.isArray(b.input))
        reject("Only client-carried input arrays supported");
    for (const item of b.input) {
        if (!object(item))
            reject("Invalid history item");
        if (item.type === "message") {
            fields(item, ["type", "id", "role", "content", "phase", "status"]);
            if (!["system", "developer", "user", "assistant"].includes(item.role) || !Array.isArray(item.content) || pending.size)
                reject("Invalid message or unresolved tool calls");
            if (item.phase !== undefined && ![null, "commentary", "final_answer"].includes(item.phase))
                reject("Unsupported message phase");
            const content = item.content.map((c: any) => { if (!object(c))
                reject("Invalid content"); fields(c, ["type", "text", "annotations"]); if (!["input_text", "output_text"].includes(c.type) || c.annotations?.length)
                reject("Unsupported media or annotations"); return string(c.text); }).join("");
            if (pendingReasoning !== undefined && item.role !== "assistant")
                reject("Reasoning must belong to the next assistant output");
            const message = { role: item.role, content,
                ...(pendingReasoning === undefined ? {} : { reasoning_content: pendingReasoning }) };
            reasoningAssistant = pendingReasoning === undefined ? undefined : message;
            pendingReasoning = undefined;
            messages.push(message);
        }
        else if (item.type === "reasoning") {
            fields(item, ["type", "id", "summary", "content", "encrypted_content"]);
            if (provider.reasoning !== "mimo-plaintext" || pending.size || pendingReasoning !== undefined ||
                item.encrypted_content != null || !Array.isArray(item.summary) || item.summary.length ||
                !Array.isArray(item.content) || !item.content.length)
                reject("Unqualified reasoning history");
            if (item.id !== undefined) string(item.id);
            pendingReasoning = item.content.map((part: any) => {
                if (!object(part)) reject("Invalid plaintext reasoning");
                fields(part, ["type", "text"]);
                if (part.type !== "reasoning_text") reject("Unqualified reasoning content type");
                return string(part.text);
            }).join("");
            if (!pendingReasoning) reject("Empty reasoning history lacks a verified contract");
            reasoningAssistant = undefined;
        }
        else if (["function_call", "custom_tool_call"].includes(item.type)) {
            fields(item, ["type", "id", "call_id", "name", "namespace", "arguments", "input", "status"]);
            if (pending.size && messages.at(-1)?.role === "tool")
                reject("Interleaved new tool calls before pending results");
            const id = string(item.call_id), originalName = string(item.name), custom = item.type === "custom_tool_call";
            if (item.namespace != null && (!Object.hasOwn(NAMESPACE_TOOLS, item.namespace) || custom)) reject("Unsupported history namespace");
            const name = item.namespace == null ? originalName : `sova_ns_${item.namespace}_${originalName}`;
            if (item.namespace == null && originalName.startsWith("sova_ns_")) reject("Transport name is not a native history identity");
            if (!id || calls.has(id))
                reject("Duplicate tool call ID");
            const spec = tools.get(name);
            if (!spec || spec.custom !== custom)
                reject("Unknown history tool");
            const args = custom ? JSON.stringify({ input: string(item.input) }) : string(item.arguments);
            if (custom && spec!.grammar && !validPatch(item.input))
                reject("Invalid pinned patch grammar");
            calls.set(id, { name, custom });
            pending.add(id);
            let prior = messages.at(-1);
            if (!prior?.tool_calls) {
                if (prior && prior === reasoningAssistant) prior.tool_calls = [];
                else {
                    prior = { role: "assistant", content: null, tool_calls: [],
                        ...(pendingReasoning === undefined ? {} : { reasoning_content: pendingReasoning }) };
                    messages.push(prior);
                }
            }
            if (pendingReasoning !== undefined) reasoningAssistant = prior;
            pendingReasoning = undefined;
            prior.tool_calls.push({ id, type: "function", function: { name, arguments: args } });
        }
        else if (["function_call_output", "custom_tool_call_output"].includes(item.type)) {
            fields(item, ["type", "id", "call_id", "output", "status"]);
            const id = string(item.call_id), call = calls.get(id);
            if (pendingReasoning !== undefined) reject("Reasoning cannot precede a tool result");
            if (!pending.delete(id) || !call || call.custom !== (item.type === "custom_tool_call_output"))
                reject("Unmatched or duplicate tool result");
            let output = item.output;
            if (Array.isArray(output))
                output = output.map((c: any) => { if (!object(c))
                    reject("Invalid tool output"); fields(c, ["type", "text"]); if (c.type !== "input_text")
                    reject("Unsupported tool media"); return string(c.text); }).join("");
            messages.push({ role: "tool", tool_call_id: id, content: string(output) });
            reasoningAssistant = undefined;
        }
        else
            reject("Unsupported history item (including encrypted reasoning/response IDs)");
    }
    if (pendingReasoning !== undefined) reject("Reasoning has no assistant output");
    if (pending.size)
        reject("Missing tool results");
    if (b.model === "qwen3.8-27b") {
        // Qwen-only adaptation: this exact template accepts one initial system
        // message and no developer role, including native post-compaction policy.
        // Preserve every original role/position/text; ordinary history is not reordered.
        const policy = messages.flatMap((m, position) => ["system", "developer"].includes(m.role)
            ? [{ position, role: m.role, content: m.content }] : []);
        if (policy.length > 1 || policy[0]?.role === "developer" || (policy[0] && policy[0].position !== 0)) {
            const history = messages.filter(m => !["system", "developer"].includes(m.role));
            messages.splice(0, messages.length, { role: "system", content: "Sova Qwen policy adaptation: system instructions take priority over developer instructions; both take priority over user messages. Later instructions at the same priority resolve conflicts. The JSON below retains the original ordered instruction messages and zero-based translated-message positions. Apply their content at the stated priority; ordinary conversation history follows in its original order.\n" + JSON.stringify(policy) }, ...history);
        }
    }
    return { provider, tools, body: { model: b.model, ...(provider.reasoning === "none" ? { reasoning_effort: "none" } : {}), messages, tools: chatTools, tool_choice: b.tool_choice, parallel_tool_calls: b.parallel_tool_calls, stream: true, stream_options: { include_usage: true }, max_tokens: output } };
}
/** Bounded SSE converter. Native usage is required; no invented token counts. */
/** Static diagnostics only: never include raw provider text or malformed JSON. */
export function responsesFailureCode(error: unknown): string {
    const known = new Set(['Data after terminal','SSE frame too large','Duplicate terminal','Invalid upstream chunk','Invalid usage','Invalid token details','Expected single choice','Invalid choice index','Unqualified reasoning field','Interleaved reasoning output','Reasoning without assistant output','Data after finish','Unsupported output media','Output bound exceeded','Invalid tool deltas','Invalid tool index/type','Changed call ID','Aggregate tool bound exceeded','Tool bound exceeded','Duplicate finish','Missing finish/usage','Tool finish mismatch','Invalid tool identity','Invalid custom tool input','Truncated or repeated Responses stream']);
    if (error instanceof SyntaxError) return 'invalid_json';
    return error instanceof Error && known.has(error.message) ? error.message.toLowerCase().replaceAll(/[ /]+/g, '_') : 'unqualified_output';
}
export class ResponsesStream {
    private decoder = new StringDecoder("utf8");
    private buffer = "";
    private sequence = 0;
    private started = false;
    private ended = false;
    private finalized = false;
    private toolBytes = 0;
    private finishReason: string | undefined;
    private responseId = "resp_" + randomUUID();
    private messageId = "msg_" + randomUUID();
    private reasoningId = "rs_" + randomUUID();
    private reasoning = "";
    private reasoningStarted = false;
    private text = "";
    private textStarted = false;
    private usage: any;
    private calls = new Map<number, {
        id: string;
        name: string;
        arguments: string;
    }>();
    private output: any[] = [];
    constructor(private translation: ResponsesTranslation, private write: (data: string) => void,
        private onDiagnostic?: (event: ResponsesDiagnostic) => void) { }
    private diagnose(event: ResponsesDiagnostic) {
        try { this.onDiagnostic?.(event); } catch { /* Observers cannot affect stream or owned settlement. */ }
    }
    private get messageIndex() { return this.reasoningStarted ? 1 : 0; }
    private emit(type: string, fields: Record<string, any> = {}) { this.write(`event: ${type}\ndata: ${JSON.stringify({ type, sequence_number: this.sequence++, ...fields })}\n\n`); }
    private response(status: string) { return { id: this.responseId, object: "response", status, output: this.output, model: this.translation.body.model }; }
    push(chunk: Buffer) { if (this.ended) {
        if (chunk.toString("utf8").trim())
            throw Error("Data after terminal");
        return;
    } this.buffer += this.decoder.write(chunk); if (this.buffer.length > 1024 * 1024)
        throw Error("SSE frame too large"); let end; while ((end = this.buffer.indexOf("\n")) >= 0) {
        const line = this.buffer.slice(0, end).trim();
        this.buffer = this.buffer.slice(end + 1);
        if (line.startsWith("data:"))
            this.data(line.slice(5).trim());
    } }
    private data(data: string) {
        if (this.ended)
            throw Error("Duplicate terminal");
        if (data === "[DONE]") {
            this.ended = true;
            return;
        }
        const v = JSON.parse(data);
        if (!object(v) || v.error)
            throw Error("Invalid upstream chunk");
        if (!this.started) {
            this.started = true;
            this.emit("response.created", { response: this.response("in_progress") });
            this.emit("response.in_progress", { response: this.response("in_progress") });
        }
        if (v.usage) {
            const u = v.usage;
            if (!uint(u.prompt_tokens) || !uint(u.completion_tokens))
                throw Error("Invalid usage");
            const cached = u.prompt_tokens_details?.cached_tokens, reasoning = u.completion_tokens_details?.reasoning_tokens;
            if ((cached !== undefined && (!uint(cached) || cached > u.prompt_tokens)) || (reasoning !== undefined && (!uint(reasoning) || reasoning > u.completion_tokens)))
                throw Error("Invalid token details");
            this.usage = { input_tokens: u.prompt_tokens, output_tokens: u.completion_tokens, total_tokens: u.prompt_tokens + u.completion_tokens, ...(cached === undefined ? {} : {input_tokens_details: {cached_tokens: cached}}), ...(reasoning === undefined ? {} : {output_tokens_details: {reasoning_tokens: reasoning}}) };
        }
        if (!Array.isArray(v.choices) || v.choices.length > 1)
            throw Error("Expected single choice");
        for (const c of v.choices) {
            if (c.index !== 0 && c.index !== undefined)
                throw Error("Invalid choice index");
            const d = c.delta ?? {};
            if (d.reasoning !== undefined && d.reasoning !== null && d.reasoning !== "")
                throw Error("Unqualified reasoning field");
            if (this.finishReason && (d.content || d.tool_calls?.length || d.reasoning_content))
                throw Error("Data after finish");
            if (d.reasoning_content !== undefined && d.reasoning_content !== null && d.reasoning_content !== "") {
                if (this.translation.provider.reasoning !== "mimo-plaintext" || typeof d.reasoning_content !== "string")
                    throw Error("Unqualified reasoning field");
                if (this.textStarted || this.calls.size) throw Error("Interleaved reasoning output");
                if (!this.reasoningStarted) {
                    this.reasoningStarted = true;
                    this.emit("response.output_item.added", { output_index: 0, item: {
                        id: this.reasoningId, type: "reasoning", summary: [], content: [], encrypted_content: null,
                    } });
                }
                this.reasoning += d.reasoning_content;
                if (this.reasoning.length > 4 * 1024 * 1024) throw Error("Output bound exceeded");
                this.emit("response.reasoning_text.delta", { item_id: this.reasoningId, output_index: 0,
                    content_index: 0, delta: d.reasoning_content });
            }
            if (d.content !== undefined && d.content !== null) {
                if (typeof d.content !== "string")
                    throw Error("Unsupported output media");
                if (d.content) {
                    if (!this.textStarted) {
                        this.textStarted = true;
                        this.emit("response.output_item.added", { output_index: this.messageIndex, item: { id: this.messageId, type: "message", role: "assistant", status: "in_progress", content: [] } });
                        this.emit("response.content_part.added", { item_id: this.messageId, output_index: this.messageIndex, content_index: 0, part: { type: "output_text", text: "", annotations: [] } });
                    }
                    this.text += d.content;
                    if (this.text.length > 4 * 1024 * 1024)
                        throw Error("Output bound exceeded");
                    this.emit("response.output_text.delta", { item_id: this.messageId, output_index: this.messageIndex, content_index: 0, delta: d.content });
                }
            }
            if (d.tool_calls) {
                if (!Array.isArray(d.tool_calls))
                    throw Error("Invalid tool deltas");
                for (const t of d.tool_calls) {
                    if (!uint(t.index) || t.index > 127 || t.type !== undefined && t.type !== "function")
                        throw Error("Invalid tool index/type");
                    if (!this.translation.provider.parallelToolCalls && t.index !== 0)
                        throw Error("Invalid tool index/type");
                    const old = this.calls.get(t.index) ?? { id: "", name: "", arguments: "" };
                    if (t.id) {
                        if (old.id && old.id !== t.id)
                            throw Error("Changed call ID");
                        old.id = string(t.id);
                    }
                    if (t.function?.name)
                        old.name += string(t.function.name);
                    if (t.function?.arguments) {
                        const delta = string(t.function.arguments);
                        this.toolBytes += Buffer.byteLength(delta);
                        if (this.toolBytes > 4 * 1024 * 1024) throw Error("Aggregate tool bound exceeded");
                        old.arguments += delta;
                    }
                    if (old.arguments.length > 1024 * 1024)
                        throw Error("Tool bound exceeded");
                    this.calls.set(t.index, old);
                }
            }
            if (c.finish_reason) {
                if (this.finishReason)
                    throw Error("Duplicate finish");
                this.finishReason = c.finish_reason;
                if (this.onDiagnostic) this.diagnose({ type: "provider_finish", responseId: this.responseId,
                    model: this.translation.body.model,
                    finishReason: ["stop", "tool_calls", "length"].includes(c.finish_reason) ? c.finish_reason : "unsupported",
                    finishReasonSha256: fingerprint(JSON.stringify(c.finish_reason)).sha256 });
            }
        }
    }
    private complete() {
        if (!this.started || !this.usage || !["stop", "tool_calls", "length"].includes(this.finishReason ?? ""))
            throw Error("Missing finish/usage");
        if ((this.finishReason === "tool_calls") !== !!this.calls.size)
            throw Error("Tool finish mismatch");
        if (this.reasoningStarted && !this.textStarted && !this.calls.size && this.finishReason === "stop")
            throw Error("Reasoning without assistant output");
        if (this.reasoningStarted) {
            const item = { id: this.reasoningId, type: "reasoning", summary: [],
                content: [{ type: "reasoning_text", text: this.reasoning }], encrypted_content: null };
            this.emit("response.reasoning_text.done", { item_id: this.reasoningId, output_index: 0, content_index: 0, text: this.reasoning });
            this.emit("response.output_item.done", { output_index: 0, item });
            this.output.push(item);
        }
        if (this.textStarted) {
            const part = { type: "output_text", text: this.text, annotations: [] };
            const item = { id: this.messageId, type: "message", role: "assistant", status: "completed", content: [part] };
            this.emit("response.output_text.done", { item_id: this.messageId, output_index: this.messageIndex, content_index: 0, text: this.text });
            this.emit("response.content_part.done", { item_id: this.messageId, output_index: this.messageIndex, content_index: 0, part });
            this.emit("response.output_item.done", { output_index: this.messageIndex, item });
            this.output.push(item);
        }
        const ids = new Set<string>();
        const diagnosticTools: ResponsesToolDiagnostic[] = [];
        let expected = 0;
        for (const [index, c] of [...this.calls].sort((a, b) => a[0] - b[0])) {
            const spec = this.translation.tools.get(c.name);
            if (index !== expected++ || !c.id || ids.has(c.id) || !spec)
                throw Error("Invalid tool identity");
            ids.add(c.id);
            let args = c.arguments;
            if (spec.custom) {
                const wrapper = JSON.parse(args);
                if (!object(wrapper) || Object.keys(wrapper).join() !== "input" || typeof wrapper.input !== "string" || (spec.grammar && !validPatch(wrapper.input)))
                    throw Error("Invalid custom tool input");
                args = wrapper.input;
            }
            const output_index = this.output.length, id = "fc_" + randomUUID(), type = spec.custom ? "custom_tool_call" : "function_call", key = spec.custom ? "input" : "arguments", item = { id, type, call_id: c.id, name: spec.originalName ?? c.name, ...(spec.namespace ? { namespace: spec.namespace } : {}), status: "completed", [key]: args };
            this.emit("response.output_item.added", { output_index, item: { ...item, status: "in_progress", [key]: "" } });
            this.emit(spec.custom ? "response.custom_tool_call_input.delta" : "response.function_call_arguments.delta", { output_index, item_id: id, delta: args });
            this.emit(spec.custom ? "response.custom_tool_call_input.done" : "response.function_call_arguments.done", { output_index, item_id: id, [key]: args });
            this.emit("response.output_item.done", { output_index, item });
            this.output.push(item);
            if (this.onDiagnostic) {
                let argumentShape: ResponsesToolDiagnostic["argumentShape"] = "invalid_json", keys: string[] = [];
                try {
                    const parsed: unknown = JSON.parse(c.arguments);
                    argumentShape = object(parsed) ? "object" : Array.isArray(parsed) ? "array" : "scalar";
                    if (object(parsed)) keys = Object.keys(parsed);
                } catch { /* Raw invalid arguments remain unchanged for native tool validation. */ }
                const schema = this.translation.body.tools.find((tool: any) => tool.function.name === c.name)?.function.parameters;
                const declared = object(schema?.properties) ? Object.keys(schema.properties) : [];
                const allowed = new Set([...declared, "__ns", "ns", "__v"]);
                const argumentKeys = keys.filter(key => allowed.has(key) && /^[A-Za-z0-9_-]{1,64}$/.test(key)).slice(0, 64);
                diagnosticTools.push({ callId: diagnosticId(c.id), callIdSha256: fingerprint(c.id).sha256,
                    transportName: c.name, name: spec.originalName ?? c.name, ...(spec.namespace ? { namespace: spec.namespace } : {}),
                    providerArguments: fingerprint(c.arguments), responseArguments: fingerprint(args),
                    argumentShape, argumentKeys, otherKeyCount: keys.length - argumentKeys.length });
            }
        }
        this.ended = true;
        const incomplete = this.finishReason === "length";
        this.emit(incomplete ? "response.incomplete" : "response.completed", { response: { ...this.response(incomplete ? "incomplete" : "completed"), usage: this.usage, ...(incomplete ? { incomplete_details: { reason: "max_output_tokens" } } : {}) } });
        if (this.onDiagnostic) this.diagnose({ type: "response_terminal", responseId: this.responseId,
            model: this.translation.body.model, finishReason: this.finishReason as "stop" | "tool_calls" | "length",
            status: incomplete ? "incomplete" : "completed", ...(this.textStarted ? { messageId: this.messageId } : {}),
            text: fingerprint(this.text), ...(this.reasoningStarted ? { reasoning: fingerprint(this.reasoning) } : {}), tools: diagnosticTools,
            usage: { input_tokens: this.usage.input_tokens, output_tokens: this.usage.output_tokens, total_tokens: this.usage.total_tokens } });
    }
    end() {
        this.buffer += this.decoder.end();
        if (this.buffer.trim() || !this.ended || this.finalized) throw Error("Truncated or repeated Responses stream");
        this.finalized = true;
        // Gateway calls this only after HTTP completion and native permit settlement.
        this.complete();
    }
}
