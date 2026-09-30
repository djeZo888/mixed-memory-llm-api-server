import test from "node:test";
import assert from "node:assert/strict";
import { ResponsesStream, translateResponses } from "../src/codex-responses.js";
import { codexFunctionStrict, codexProvider } from "../src/codex-provider.js";

// Synthetic declarations and payloads only; no retained user prompt or live capture.
const capabilityAlias = "sova_ns_mcp__image_image_capabilities";
const emptySchema = { type: "object", properties: {}, additionalProperties: false };
const querySchema = {
  type: "object",
  properties: { query: { type: "string", enum: ["capabilities"] } },
  required: ["query"],
  additionalProperties: false,
};
// Selected public descriptor fields from W2-IMAGE-CAPABILITIES-DESCRIPTOR.json.
// Keep the actual MCP serializer's dialect metadata; the native function retains it.
const serializedCapabilityDescriptor = {
  name: "image_capabilities",
  description: 'Read only the resident Qwen-Image-2.1 service operation, size and reference-count metadata. Call with {"query":"capabilities"}. This does not generate or edit images. Only advertised qualified edit profiles are available; no creative fallback.',
  inputSchema: {
    type: "object",
    properties: { query: { type: "string", enum: ["capabilities"] } },
    required: ["query"],
    $schema: "http://json-schema.org/draft-07/schema#",
    additionalProperties: false,
  },
};
const request = (model = "qwen3.8-27b", strict = false): any => ({
  model, tool_choice: "auto", parallel_tool_calls: true, store: false, stream: true,
  max_output_tokens: 256,
  tools: [{
    type: "namespace", name: "mcp__image", description: "Synthetic discovery fixture.",
    tools: [{
      type: "function", name: "image_capabilities", description: "Read capabilities.",
      strict, parameters: structuredClone(emptySchema),
    }],
  }, {
    type: "function", name: "fixture_query", description: "Synthetic parameterized query.",
    strict, parameters: structuredClone(querySchema),
  }],
  input: [{ type: "message", role: "user", content: [{ type: "input_text", text: "Read capabilities." }] }],
});
function queryRequest(model = "qwen3.8-27b", strict = false) {
  const body = request(model, strict);
  body.tools[0].tools[0].parameters = structuredClone(querySchema);
  return body;
}
const events = (wire: string): any[] => wire.split("\n")
  .filter(line => line.startsWith("data: ")).map(line => JSON.parse(line.slice(6)));
const frame = (value: unknown) => Buffer.from(`data: ${JSON.stringify(value)}\n\n`);
function finish(stream: ResponsesStream, reason: string, outputTokens = 22) {
  stream.push(frame({ choices: [{ index: 0, delta: {}, finish_reason: reason }] }));
  stream.push(frame({ choices: [], usage: { prompt_tokens: 32, completion_tokens: outputTokens } }));
  stream.push(Buffer.from("data: [DONE]\n\n"));
}
function toolDelta(argumentsText: string | undefined) {
  return { choices: [{ index: 0, delta: { tool_calls: [{
    index: 0, id: "call_fixture_capability", type: "function",
    function: { name: capabilityAlias, ...(argumentsText === undefined ? {} : { arguments: argumentsText }) },
  }] }, finish_reason: null }] };
}

test("Qwen and MiMo preserve explicit empty and parameterized contracts without promoting strictness", () => {
  for (const model of ["qwen3.8-27b", "mimo-v2.6-pro-rl"]) {
    for (const strict of [false, true]) {
      const body = request(model, strict), original = structuredClone(body);
      const translated = translateResponses(body);
      const declarations = translated.body.tools.map((tool: any) => tool.function);
      assert.deepEqual(declarations.map((tool: any) => tool.parameters), [emptySchema, querySchema]);
      assert.deepEqual(declarations.map((tool: any) => tool.strict), [strict, strict]);
      assert.deepEqual(declarations.map((tool: any) => tool.name), [capabilityAlias, "fixture_query"]);
      assert.equal(translated.body.tool_choice, "auto");
      assert.equal(translated.body.max_tokens, 256);
      assert.deepEqual(body, original);
    }
    for (const missing of ["strict", "parameters"]) {
      const body = request(model);
      delete body.tools[0].tools[0][missing];
      assert.throws(() => translateResponses(body), /Invalid function schema/);
    }
  }
});

test("only the exact Qwen namespaced capability query contract gains strict enforcement", () => {
  for (const model of ["qwen3.8-27b", "mimo-v2.6-pro-rl"]) {
    for (const strict of [false, true]) {
      const body = queryRequest(model, strict), original = structuredClone(body);
      const translated = translateResponses(body);
      const capability = translated.body.tools[0].function;
      assert.equal(capability.strict, model === "qwen3.8-27b" || strict);
      assert.deepEqual(capability.parameters, querySchema);
      assert.equal(capability.name, capabilityAlias);
      assert.deepEqual(translated.tools.get(capabilityAlias), {
        custom: false, grammar: false, namespace: "mcp__image", originalName: "image_capabilities",
      });
      assert.equal(translated.body.tools[1].function.strict, strict);
      assert.equal(translated.body.tool_choice, "auto");
      assert.equal(translated.body.parallel_tool_calls, model === "qwen3.8-27b");
      assert.deepEqual(body, original);
    }
  }
});

test("the actual serialized MCP capability descriptor promotes without dropping draft-07 metadata", () => {
  const body = queryRequest();
  body.tools[0].tools[0] = {
    type: "function", name: serializedCapabilityDescriptor.name,
    description: serializedCapabilityDescriptor.description, strict: false,
    parameters: structuredClone(serializedCapabilityDescriptor.inputSchema),
  };
  const original = structuredClone(body);
  const translated = translateResponses(body);
  const capability = translated.body.tools[0].function;
  assert.equal(capability.strict, true);
  assert.deepEqual(capability.parameters, serializedCapabilityDescriptor.inputSchema);
  assert.ok(capability.description.endsWith(serializedCapabilityDescriptor.description));
  assert.deepEqual(body, original);
  body.model = "mimo-v2.6-pro-rl";
  assert.equal(translateResponses(body).body.tools[0].function.strict, false);
});

test("strict promotion excludes changed, omitted, open and extended capability schemas", () => {
  const changes: [string, (schema: any) => void][] = [
    ...["type", "properties", "required", "additionalProperties"].map(key =>
      [`missing ${key}`, (schema: any) => { delete schema[key]; }] as [string, (schema: any) => void]),
    ["nullable root", schema => { schema.type = ["object", "null"]; }],
    ["open root", schema => { schema.additionalProperties = true; }],
    ["schema-valued extras", schema => { schema.additionalProperties = {}; }],
    ["missing query", schema => { schema.properties = {}; }],
    ["null properties", schema => { schema.properties = null; }],
    ["array properties", schema => { schema.properties = []; }],
    ["extra property", schema => { schema.properties.prompt = { type: "string" }; }],
    ["null query", schema => { schema.properties.query = null; }],
    ["array query", schema => { schema.properties.query = []; }],
    ["missing query type", schema => { delete schema.properties.query.type; }],
    ["changed query type", schema => { schema.properties.query.type = "number"; }],
    ["missing enum", schema => { delete schema.properties.query.enum; }],
    ["non-array enum", schema => { schema.properties.query.enum = "capabilities"; }],
    ["changed enum", schema => { schema.properties.query.enum = ["other"]; }],
    ["extended enum", schema => { schema.properties.query.enum.push("other"); }],
    ["duplicate enum", schema => { schema.properties.query.enum.push("capabilities"); }],
    ["const substitution", schema => { delete schema.properties.query.enum; schema.properties.query.const = "capabilities"; }],
    ["extra query constraint", schema => { schema.properties.query.minLength = 1; }],
    ["optional query", schema => { schema.required = []; }],
    ["non-array required", schema => { schema.required = "query"; }],
    ["different required", schema => { schema.required = ["other"]; }],
    ["duplicate required", schema => { schema.required.push("query"); }],
    ["extra root constraint", schema => { schema.maxProperties = 1; }],
    ["root composition", schema => { schema.allOf = []; }],
    ["unreviewed dialect", schema => { schema.$schema = "https://json-schema.org/draft/2020-12/schema"; }],
    ["non-string dialect", schema => { schema.$schema = {}; }],
  ];
  for (const [label, change] of changes) {
    const body = queryRequest();
    change(body.tools[0].tools[0].parameters);
    const original = structuredClone(body);
    const declaration = translateResponses(body).body.tools[0].function;
    assert.equal(declaration.strict, false, label);
    assert.deepEqual(declaration.parameters, original.tools[0].tools[0].parameters, label);
    assert.deepEqual(body, original, label);
  }
});

test("strict promotion requires qualified namespace identity and a function declaration", () => {
  const provider = codexProvider("qwen3.8-27b");
  for (const identity of [
    {}, { originalName: "image_capabilities" }, { namespace: "mcp__image" },
    { namespace: "mcp__search", originalName: "image_capabilities" },
    { namespace: "mcp__image", originalName: "image_generate" },
  ]) assert.equal(codexFunctionStrict(provider, identity, querySchema, false), false);

  const topLevel = queryRequest();
  topLevel.tools[0] = topLevel.tools[0].tools[0];
  assert.equal(translateResponses(topLevel).body.tools[0].function.strict, false);
  const differentName = queryRequest();
  differentName.tools[0].tools[0].name = "image_generate";
  assert.equal(translateResponses(differentName).body.tools[0].function.strict, false);
  const custom = queryRequest();
  custom.tools[0].tools[0].type = "custom";
  assert.throws(() => translateResponses(custom), /Unsupported namespace tool/);
  const reservedAlias = queryRequest();
  reservedAlias.tools[0] = { ...reservedAlias.tools[0].tools[0], name: capabilityAlias };
  assert.throws(() => translateResponses(reservedAlias), /Reserved namespace transport name/);
});

test("invalid capability arguments remain exact through response and call-ID-matched error feedback", () => {
  // Wrong types and extra fields must remain evidence, including original spacing.
  const argumentsText = ' { "prompt" : "fixture", "action" : "read", "references" : "[]" }\n';
  const body = queryRequest();
  assert.equal(translateResponses(body).body.tools[0].function.strict, true);
  let wire = "";
  const stream = new ResponsesStream(translateResponses(body), value => wire += value);
  stream.push(frame(toolDelta(argumentsText)));
  finish(stream, "tool_calls");
  stream.end();
  const completed = events(wire).find(event => event.type === "response.completed");
  const call = completed.response.output[0];
  assert.equal(call.arguments, argumentsText);
  assert.equal(call.namespace, "mcp__image");
  assert.equal(call.name, "image_capabilities");
  assert.equal(call.call_id, "call_fixture_capability");

  const failure = "MCP error -32602: synthetic capability schema rejection";
  body.input.push(call, { type: "function_call_output", call_id: call.call_id, output: failure });
  const next = translateResponses(body).body.messages;
  assert.equal(next.at(-2).tool_calls[0].function.arguments, argumentsText);
  assert.equal(next.at(-2).tool_calls[0].function.name, capabilityAlias);
  assert.equal(next.at(-2).tool_calls[0].id, call.call_id);
  assert.deepEqual(next.at(-1), { role: "tool", tool_call_id: call.call_id, content: failure });
  body.input.at(-1).call_id = "different_call";
  assert.throws(() => translateResponses(body), /Unmatched or duplicate tool result/);
});

test("promoted declarations do not fill omitted or malformed generated query arguments", () => {
  for (const argumentsText of [undefined, "", "{}", "{broken"]) {
    let wire = "";
    const stream = new ResponsesStream(translateResponses(queryRequest()), value => wire += value);
    stream.push(frame(toolDelta(argumentsText)));
    finish(stream, "tool_calls");
    stream.end();
    assert.equal(events(wire).at(-1).response.output[0].arguments, argumentsText ?? "");
  }
});

test("256-token function-name-only truncation never becomes a completed empty call", () => {
  // Both omitted and explicitly empty argument deltas are incomplete evidence.
  for (const argumentsText of [undefined, ""]) {
    let wire = "";
    const stream = new ResponsesStream(translateResponses(queryRequest()), value => wire += value);
    stream.push(frame(toolDelta(argumentsText)));
    finish(stream, "length", 256);
    assert.throws(() => stream.end(), /Tool finish mismatch/);
    assert.deepEqual(events(wire).map(event => event.type), ["response.created", "response.in_progress"]);
    assert.doesNotMatch(wire, /response\.completed|response\.output_item\.done|"arguments":"\{\}"/);
  }
});

test("AUTO still permits ordinary text without synthesizing a capability call", () => {
  let wire = "";
  const stream = new ResponsesStream(translateResponses(queryRequest()), value => wire += value);
  stream.push(frame({ choices: [{ index: 0, delta: { content: "Synthetic ordinary answer." } }] }));
  finish(stream, "stop");
  stream.end();
  const completed = events(wire).at(-1);
  assert.equal(completed.type, "response.completed");
  assert.equal(completed.response.output.length, 1);
  assert.equal(completed.response.output[0].type, "message");
  assert.equal(completed.response.output[0].content[0].text, "Synthetic ordinary answer.");
});

test("a completed valid empty capability call remains distinct from a truncated call", () => {
  let wire = "";
  const stream = new ResponsesStream(translateResponses(request()), value => wire += value);
  stream.push(frame(toolDelta("{}")));
  finish(stream, "tool_calls");
  assert.doesNotMatch(wire, /response\.completed|response\.output_item\.done/);
  stream.end();
  const completed = events(wire).at(-1);
  assert.equal(completed.type, "response.completed");
  assert.equal(completed.response.output[0].arguments, "{}");
  assert.equal(completed.response.output[0].call_id, "call_fixture_capability");
  assert.equal(completed.response.usage.output_tokens, 22);
});

test("the promoted query contract preserves a completed valid query and its declared schema", () => {
  const body = queryRequest();
  const translated = translateResponses(body);
  let wire = "";
  const stream = new ResponsesStream(translated, value => wire += value);
  const argumentsText = '{"query":"capabilities"}';
  stream.push(frame(toolDelta(argumentsText)));
  finish(stream, "tool_calls");
  stream.end();
  const completed = events(wire).at(-1);
  assert.equal(completed.type, "response.completed");
  assert.equal(completed.response.output[0].arguments, argumentsText);
  assert.deepEqual(translated.body.tools[0].function.parameters, querySchema);
});
