import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { codexProvider } from "../src/codex-provider.js";
import { translateResponses, ResponsesStream } from "../src/codex-responses.js";

const captured = JSON.parse(readFileSync(new URL("./fixtures/codex/native-requests.json", import.meta.url), "utf8"));
const request = () => ({ ...structuredClone(captured[0].body), model: "mimo-v2.6-pro-rl", parallel_tool_calls: false });
const reason = (text = "Fixture plaintext; not encrypted.") => ({ type: "reasoning", id: "rs_fixture", summary: [], content: [{ type: "reasoning_text", text }], encrypted_content: null });
const message = (text: string, role = "assistant") => ({ type: "message", role, content: [{ type: role === "assistant" ? "output_text" : "input_text", text }] });
const call = (id: string) => ({ type: "function_call", call_id: id, name: "get_goal", arguments: "{}" });
const result = (id: string) => ({ type: "function_call_output", call_id: id, output: `result-${id}` });
const parse = (wire: string) => wire.split("\n").filter(line => line.startsWith("data: ")).map(line => JSON.parse(line.slice(6)));

test("reviewed providers keep distinct budgets, selected-model identity and serial-tool semantics", () => {
  const b = request();
  const selected = codexProvider(b.model);
  const translated = translateResponses(b, 65536, selected);
  assert.equal(translated.provider.contextWindow, 950000);
  assert.equal(translated.provider.autoCompactTokenLimit, 880000);
  assert.equal(translated.body.max_tokens, 65536);
  assert.equal(translated.body.reasoning_effort, undefined);
  assert.equal(translated.body.parallel_tool_calls, false);
  const qwen = translateResponses(captured[0].body);
  assert.equal(qwen.provider.contextWindow, 480000);
  assert.equal(qwen.provider.autoCompactTokenLimit, 400000);
  assert.equal(qwen.body.reasoning_effort, "none");
  assert.throws(() => translateResponses(b, 65536, codexProvider("qwen3.8-27b")), /mismatched provider/);
  assert.throws(() => translateResponses(b, 65536, { ...selected, contextWindow: 480000 }), /mismatched provider/);
  assert.throws(() => translateResponses(b, 65536, { ...selected, parallelToolCalls: true }), /mismatched provider/);
  assert.throws(() => translateResponses({ ...b, parallel_tool_calls: true }), /serial auto/);
  assert.throws(() => translateResponses({ ...b, tool_choice: "none" }), /serial auto/);
});

test("verified plaintext reasoning belongs to its assistant content and parallel call IDs/results, never a later message", () => {
  for (const withText of [false, true]) {
    const b = request();
    b.input.push(reason(), ...(withText ? [message("Calling the tools.")] : []), call("a"), call("b"), result("a"), result("b"), message("next", "user"), message("ordinary answer"));
    const history = translateResponses(b).body.messages;
    const assistant = history.find((item: any) => item.reasoning_content);
    assert.equal(assistant.reasoning_content, "Fixture plaintext; not encrypted.");
    assert.equal(assistant.content, withText ? "Calling the tools." : null);
    assert.deepEqual(assistant.tool_calls.map((item: any) => item.id), ["a", "b"]);
    assert.deepEqual(history.filter((item: any) => item.role === "tool").map((item: any) => [item.tool_call_id, item.content]), [["a", "result-a"], ["b", "result-b"]]);
    assert.equal(history.at(-1).reasoning_content, undefined);
  }
});

test("plaintext tool and final responses roundtrip reasoning_text without fabricating encrypted state or final phase", () => {
  for (const tool of [false, true]) {
    const b = request(); const translated = translateResponses(b); let wire = "";
    const stream = new ResponsesStream(translated, data => wire += data);
    const data = (value: unknown) => stream.push(Buffer.from(`data: ${JSON.stringify(value)}\n\n`));
    data({ choices: [{ delta: { reasoning_content: "Fixture " }, finish_reason: null }] });
    data({ choices: [{ delta: { reasoning_content: "plaintext." }, finish_reason: null }] });
    data({ choices: [{ delta: { content: "Visible text." }, finish_reason: null }] });
    if (tool) data({ choices: [{ delta: { tool_calls: [{ index: 0, id: "fixture", type: "function", function: { name: "get_goal", arguments: "{}" } }] }, finish_reason: null }] });
    data({ choices: [{ delta: {}, finish_reason: tool ? "tool_calls" : "stop" }], usage: { prompt_tokens: 20, completion_tokens: 9 } });
    stream.push(Buffer.from("data: [DONE]\n\n")); stream.end();
    const events = parse(wire); const output = events.at(-1).response.output;
    assert.equal(output[0].type, "reasoning");
    assert.deepEqual(output[0].summary, []);
    assert.deepEqual(output[0].content, [{ type: "reasoning_text", text: "Fixture plaintext." }]);
    assert.equal(output[0].encrypted_content, null);
    assert.equal(output[1].content[0].text, "Visible text.");
    assert.equal(output[1].phase, undefined);
    assert.equal(events.find(event => event.type === "response.output_text.delta").output_index, 1);
    b.input.push(...output, ...(tool ? [result("fixture")] : []));
    const history = translateResponses(b).body.messages;
    const assistant = history.find((item: any) => item.reasoning_content);
    assert.equal(assistant.reasoning_content, "Fixture plaintext.");
    assert.equal(assistant.content, "Visible text.");
    if (tool) assert.equal(assistant.tool_calls[0].id, "fixture");
  }
});

test("encrypted, summary-only, cross-provider, orphaned or interleaved reasoning fails closed", () => {
  const mutations = [
    (b: any) => b.input.push({ ...reason(), encrypted_content: "secret" }, message("answer")),
    (b: any) => b.input.push({ ...reason(), summary: [{ type: "summary_text", text: "summary" }] }, message("answer")),
    (b: any) => b.input.push({ ...reason(), content: [{ type: "text", text: "not reasoning_text" }] }, message("answer")),
    (b: any) => b.input.push(reason()),
    (b: any) => b.input.push(reason(), message("unowned", "user")),
    (b: any) => b.input.push(call("a"), reason(), result("a")),
    (b: any) => b.input.push(reason(), reason(), message("answer")),
    (b: any) => { b.model = "qwen3.8-27b"; b.input.push(reason(), message("answer")); },
  ];
  for (const mutate of mutations) { const b = request(); mutate(b); assert.throws(() => translateResponses(b)); }
  for (const mode of ["qwen", "late", "alternate-field"] as const) {
    const b = request(); if (mode === "qwen") b.model = "qwen3.8-27b";
    const stream = new ResponsesStream(translateResponses(b), () => {});
    if (mode === "late") stream.push(Buffer.from('data: {"choices":[{"delta":{"content":"already visible"}}]}\n\n'));
    assert.throws(() => stream.push(Buffer.from(`data: ${JSON.stringify({ choices: [{ delta: { [mode === "alternate-field" ? "reasoning" : "reasoning_content"]: "unverified ordering or field" } }] })}\n\n`)));
  }
});

test("reasoning-only stop cannot claim completion with history that cannot continue", () => {
  let wire = "";
  const stream = new ResponsesStream(translateResponses(request()), data => wire += data);
  stream.push(Buffer.from('data: {"choices":[{"delta":{"reasoning_content":"Only internal output"},"finish_reason":"stop"}],"usage":{"prompt_tokens":4,"completion_tokens":3}}\n\n'));
  stream.push(Buffer.from("data: [DONE]\n\n"));
  assert.throws(() => stream.end(), /Reasoning without assistant output/);
  assert.doesNotMatch(wire, /response.completed|response.output_item.done/);
});

test("serial provider rejects a second emitted tool even while old paired batches remain valid history", () => {
  const stream = new ResponsesStream(translateResponses(request()), () => {});
  const tool = (index: number) => ({ index, id: `call-${index}`, type: "function", function: { name: "get_goal", arguments: "{}" } });
  assert.throws(() => stream.push(Buffer.from(`data: ${JSON.stringify({ choices: [{ delta: { tool_calls: [tool(0), tool(1)] }, finish_reason: "tool_calls" }] })}\n\n`)), /Invalid tool index/);
});
