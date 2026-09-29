import assert from "node:assert/strict";
import test from "node:test";
import { CODEX_SCHEMA_ERROR_BOUND, CodexSchemaErrorGuard } from "../src/codex-schema-errors.js";

// H033 corrected original: exact first three call IDs and MCP error text from
// CORRECTED-NONPROGRESS.json. App-server projection is mcpToolCall/result.content
// with error:null; the native rollout's isError field is not in that projection.
const ids = ["call_2e7a7080aeb742609801873d", "call_062e691437b24784be6584e5", "call_c7acb0809c214dadb84b1865"];
const error = 'MCP error -32602: Input validation error: Invalid arguments for tool image_capabilities: Unrecognized key: "prompt"';
const started = (id: string, args: Record<string, unknown> = { prompt: "1024x576" }) => ({
  type: "mcpToolCall", id, server: "image", tool: "image_capabilities", arguments: args,
  status: "inProgress", result: null, error: null,
});
const completed = (id: string, changes: Record<string, unknown> = {}) => ({
  ...started(id), status: "failed", result: { content: [{ type: "text", text: error }] }, ...changes,
});
function fail(guard: CodexSchemaErrorGuard, id: string, changes: Record<string, unknown> = {}) {
  guard.observe(started(id, changes.arguments as Record<string, unknown> | undefined), false);
  return guard.observe(completed(id, changes), true);
}

test("three exact captured schema errors return full trace once without rewriting arguments", () => {
  const guard = new CodexSchemaErrorGuard();
  assert.equal(CODEX_SCHEMA_ERROR_BOUND, 3);
  assert.equal(fail(guard, ids[0]!), undefined);
  guard.observe({ type: "agentMessage", id: "commentary" }, true);
  guard.observe({ type: "reasoning", id: "reason" }, false);
  assert.equal(fail(guard, ids[1]!), undefined);
  const final = completed(ids[2]!); const before = structuredClone(final);
  guard.observe(started(ids[2]!), false);
  assert.deepEqual(guard.observe(final, true), { tool: "image_capabilities", server: "image", callIds: ids, error,
    attempts: ids.map(id => completed(id)) });
  assert.deepEqual(final, before);
  assert.equal(fail(guard, "later"), undefined);
});

test("canonical nested argument order matches but changed values start a new streak", () => {
  const guard = new CodexSchemaErrorGuard();
  fail(guard, "a", { arguments: { prompt: "x", nested: { z: [1, 2], a: true } } });
  fail(guard, "b", { arguments: { nested: { a: true, z: [1, 2] }, prompt: "x" } });
  assert.deepEqual(fail(guard, "c", { arguments: { prompt: "x", nested: { z: [1, 2], a: true } } })?.callIds, ["a", "b", "c"]);
  const changed = new CodexSchemaErrorGuard();
  fail(changed, "old");
  assert.equal(fail(changed, "new-a", { arguments: { prompt: "different" } }), undefined);
  assert.equal(fail(changed, "new-b", { arguments: { prompt: "different" } }), undefined);
  assert.deepEqual(fail(changed, "new-c", { arguments: { prompt: "different" } })?.callIds, ["new-a", "new-b", "new-c"]);
});

test("changed error detail cannot combine otherwise identical calls", () => {
  const guard = new CodexSchemaErrorGuard();
  fail(guard, "a"); fail(guard, "b");
  const detail = `${error} (different detail)`;
  assert.equal(fail(guard, "changed", { result: { content: [{ type: "text", text: detail }] } }), undefined);
  assert.equal(fail(guard, "again"), undefined);
});

test("duplicate starts/completions never count twice", () => {
  const guard = new CodexSchemaErrorGuard();
  guard.observe(started("a"), false); guard.observe(started("a"), false);
  guard.observe(completed("a"), true); guard.observe(completed("a"), true);
  fail(guard, "a");
  assert.equal(fail(guard, "b"), undefined);
  assert.deepEqual(fail(guard, "c")?.callIds, ["a", "b", "c"]);
});

test("unmatched completions and changed start-to-complete arguments do not count", () => {
  for (const change of ["missing", "arguments", "server", "tool"]) {
    const guard = new CodexSchemaErrorGuard(); fail(guard, "a"); fail(guard, "b");
    if (change !== "missing") guard.observe(started("bad"), false);
    guard.observe(completed("bad", change === "arguments" ? { arguments: {} }
      : change === "server" ? { server: "other" } : change === "tool" ? { tool: "other" } : {}), true);
    assert.equal(fail(guard, "new"), undefined, change);
  }
});

test("success, transient, declined, cancellation, malformed results and generic prose reset", () => {
  const cases: Record<string, unknown>[] = [
    { status: "completed" }, { status: "declined" }, { status: "cancelled" }, { status: "inProgress" },
    { error: { message: error } }, { error: undefined }, { result: null },
    { result: { content: [{ type: "text", text: "MCP error -32000: timeout" }] } },
    { result: { content: [{ type: "text", text: `The tool said ${error}` }] } },
    { result: { content: [{ type: "text", text: error.replace("image_capabilities", "image_edit") }] } },
    { result: { content: [{ type: "text", text: error }, { type: "text", text: "extra" }] } },
    { result: { content: [{ type: "image", text: error }] } },
    { result: { content: [{ type: "text", text: "MCP error -32602: Input validation error: Invalid arguments for tool image_capabilities: " }] } },
  ];
  for (const changes of cases) {
    const guard = new CodexSchemaErrorGuard(); fail(guard, "a"); fail(guard, "b");
    assert.equal(fail(guard, "different", changes), undefined);
    assert.equal(fail(guard, "new"), undefined, JSON.stringify(changes));
  }
});

test("other actions and overlapping incomplete calls reset and invalidate affected starts", () => {
  for (const type of ["commandExecution", "fileChange", "collabAgentToolCall", "unknown"]) {
    const guard = new CodexSchemaErrorGuard(); fail(guard, "a"); fail(guard, "b");
    guard.observe(started("incomplete"), false);
    guard.observe({ id: "action", type }, false);
    assert.equal(guard.observe(completed("incomplete"), true), undefined);
    assert.equal(fail(guard, "new"), undefined);
  }
  const guard = new CodexSchemaErrorGuard(); fail(guard, "a"); fail(guard, "b");
  guard.observe(started("overlap-a"), false); guard.observe(started("overlap-b"), false);
  assert.equal(guard.observe(completed("overlap-a"), true), undefined);
  assert.equal(guard.observe(completed("overlap-b"), true), undefined);
  assert.equal(fail(guard, "new-a"), undefined); assert.equal(fail(guard, "new-b"), undefined);
  assert.deepEqual(fail(guard, "new-c")?.callIds, ["new-a", "new-b", "new-c"]);
});

test("separate child/turn instances cannot pool failures", () => {
  const parent = new CodexSchemaErrorGuard(), child = new CodexSchemaErrorGuard(), nextTurn = new CodexSchemaErrorGuard();
  fail(parent, "parent-a"); fail(parent, "parent-b");
  assert.equal(fail(child, "child-a"), undefined);
  assert.equal(fail(nextTurn, "next-a"), undefined);
  assert.deepEqual(fail(parent, "parent-c")?.callIds, ["parent-a", "parent-b", "parent-c"]);
});

test("long identical errors still trigger and retain their complete text and items", () => {
  const guard = new CodexSchemaErrorGuard(), long = error + "x".repeat(8192);
  const changes = { result: { content: [{ type: "text", text: long }] } };
  assert.equal(fail(guard, "a", changes), undefined);
  assert.equal(fail(guard, "b", changes), undefined);
  const failure = fail(guard, "c", changes);
  assert.equal(failure?.error, long);
  assert.deepEqual(failure?.attempts, ["a", "b", "c"].map(id => completed(id, changes)));
});

test("non-JSON arguments reset safely without being silently normalized", () => {
  const cycle: Record<string, unknown> = {}; cycle.self = cycle;
  for (const value of [undefined, NaN, Infinity, BigInt(1), () => 1, new Date(), cycle, { x: undefined }]) {
    const guard = new CodexSchemaErrorGuard(); fail(guard, "a"); fail(guard, "b");
    const input = { ...started("invalid"), arguments: value };
    assert.doesNotThrow(() => guard.observe(input, false));
    assert.equal(guard.observe({ ...completed("invalid"), arguments: value }, true), undefined);
    assert.equal(fail(guard, "new"), undefined);
  }
});
