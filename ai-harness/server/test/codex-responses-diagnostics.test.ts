import test from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { ResponsesStream, translateResponses, type ResponsesDiagnostic } from "../src/codex-responses.js";

const request = () => JSON.parse(readFileSync(new URL("./fixtures/codex/native-mcp-namespaces.json", import.meta.url), "utf8"));
const chunk = (value: unknown) => Buffer.from(`data: ${JSON.stringify(value)}\n\n`);
const sha = (value: string) => createHash("sha256").update(value).digest("hex");
const parse = (wire: string) => wire.split("\n").filter(line => line.startsWith("data: ")).map(line => JSON.parse(line.slice(6)));

// Text, call ID and token counts are retained ACCEPT06 facts. Upstream finish
// choices below are SYNTHETIC: the historical raw Chat wire was not retained.
const pdfPromise = "Text extracted successfully. Now rendering page 1.";
test("PDF-shaped final text is preserved; raw finish observation and canonical terminal are separate evidence", () => {
  for (const finish of ["stop", "length"] as const) {
    const events: ResponsesDiagnostic[] = [];
    let wire = "";
    const stream = new ResponsesStream(translateResponses(request()), data => wire += data, event => events.push(event));
    stream.push(chunk({ choices: [{ index: 0, delta: { content: pdfPromise }, finish_reason: finish }] }));
    stream.push(chunk({ choices: [], usage: { prompt_tokens: 16120, completion_tokens: 11 } }));
    stream.push(Buffer.from("data: [DONE]\n\n"));
    assert.deepEqual(events.map(event => event.type), ["provider_finish"]);
    assert.doesNotMatch(wire, /response.completed|response.incomplete/);
    stream.end(); // Called only after HTTP/native drain by the gateway.
    const terminal = events[1];
    assert.equal(terminal?.type, "response_terminal");
    if (terminal?.type !== "response_terminal") throw Error("missing terminal diagnostic");
    assert.equal(terminal.finishReason, finish);
    assert.equal(terminal.status, finish === "length" ? "incomplete" : "completed");
    assert.deepEqual(terminal.text, { bytes: Buffer.byteLength(pdfPromise), sha256: sha(pdfPromise) });
    assert.deepEqual(terminal.tools, []); // No promised render call is invented.
    assert.deepEqual(terminal.usage, { input_tokens: 16120, output_tokens: 11, total_tokens: 16131 });
    const final = parse(wire).at(-1);
    assert.equal(final.type, finish === "length" ? "response.incomplete" : "response.completed");
    assert.equal(final.response.output[0].content[0].text, pdfPromise);
    assert.equal(final.response.output[0].phase, undefined);
    assert.equal(terminal.messageId, final.response.output[0].id);
    assert.equal(terminal.responseId, final.response.id);
    assert.equal(JSON.stringify(events).includes(pdfPromise), false);
  }
});

test("diagnostic metadata retains malformed image argument evidence without changing strict schema or raw bytes", () => {
  const b = request();
  const translated = translateResponses(b);
  const alias = "sova_ns_mcp__image_image_capabilities";
  assert.deepEqual(translated.body.tools.find((tool: any) => tool.function.name === alias).function.parameters,
    { type: "object", properties: {}, additionalProperties: false });
  for (const args of ['{}', '{"__v":"0"}', ' { "__ns" : "10" }\n', '{"ns":"10"}', '{"do-not-log-this-private-key":"private-value"}', '{broken']) {
    const events: ResponsesDiagnostic[] = [];
    let wire = "";
    const stream = new ResponsesStream(translated, data => wire += data, event => events.push(event));
    stream.push(chunk({ choices: [{ delta: { tool_calls: [{ index: 0, id: "call-retained-shape", type: "function", function: { name: alias, arguments: args } }] }, finish_reason: "tool_calls" }] }));
    stream.push(chunk({ choices: [], usage: { prompt_tokens: 10, completion_tokens: 4 } }));
    stream.push(Buffer.from("data: [DONE]\n\n"));
    stream.end();
    const terminal = events.find(event => event.type === "response_terminal");
    if (terminal?.type !== "response_terminal") throw Error("missing terminal diagnostic");
    const tool = terminal.tools[0]!;
    assert.equal(tool.name, "image_capabilities");
    assert.equal(tool.namespace, "mcp__image");
    assert.equal(tool.callId, "call-retained-shape");
    assert.deepEqual(tool.providerArguments, { bytes: Buffer.byteLength(args), sha256: sha(args) });
    assert.deepEqual(tool.responseArguments, tool.providerArguments);
    assert.equal(JSON.stringify(events).includes("private-key"), false);
    assert.equal(JSON.stringify(events).includes("private-value"), false);
    if (args.includes("__v")) assert.deepEqual(tool.argumentKeys, ["__v"]);
    if (args === "{broken") assert.equal(tool.argumentShape, "invalid_json");
    const item = parse(wire).at(-1).response.output[0];
    assert.equal(item.arguments, args);
    const next = structuredClone(b);
    next.input.push(item, { type: "function_call_output", call_id: item.call_id, output: "MCP strict validation failure retained" });
    const history = translateResponses(next).body.messages;
    assert.equal(history.at(-2).tool_calls[0].function.arguments, args);
    assert.equal(history.at(-1).tool_call_id, item.call_id);
    assert.equal(history.at(-1).content, "MCP strict validation failure retained");
  }
});

test("observer exceptions do not change completed output and invalid streams never get a terminal diagnostic", () => {
  let wire = "";
  const good = new ResponsesStream(translateResponses(request()), data => wire += data, () => { throw Error("observer unavailable"); });
  good.push(chunk({ choices: [{ delta: { content: "ok" }, finish_reason: "stop" }], usage: { prompt_tokens: 1, completion_tokens: 1 } }));
  good.push(Buffer.from("data: [DONE]\n\n"));
  assert.doesNotThrow(() => good.end());
  assert.equal(parse(wire).at(-1).response.output[0].content[0].text, "ok");
  for (const value of [
    { choices: [{ delta: { content: pdfPromise }, finish_reason: "stop" }] }, // missing usage
    { choices: [{ delta: { content: pdfPromise } }], usage: { prompt_tokens: 1, completion_tokens: 1 } }, // missing finish
    { choices: [{ delta: { reasoning_content: "unqualified" }, finish_reason: "stop" }], usage: { prompt_tokens: 1, completion_tokens: 1 } },
    { choices: [{ delta: { tool_calls: [{ index: 0, id: "call", type: "function", function: { name: "sova_ns_mcp__image_image_capabilities", arguments: "{}" } }] }, finish_reason: "stop" }], usage: { prompt_tokens: 1, completion_tokens: 1 } },
  ]) {
    const events: ResponsesDiagnostic[] = [];
    const stream = new ResponsesStream(translateResponses(request()), () => {}, event => events.push(event));
    assert.throws(() => { stream.push(chunk(value)); stream.push(Buffer.from("data: [DONE]\n\n")); stream.end(); });
    assert.equal(events.some(event => event.type === "response_terminal"), false);
  }
});
