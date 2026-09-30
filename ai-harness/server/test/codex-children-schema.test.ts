import assert from "node:assert/strict";
import test from "node:test";
import { CodexChildren } from "../src/codex-children.js";
import type { CodexSchemaErrorFailure } from "../src/codex-schema-errors.js";
import type { EngineUpdate } from "../src/contracts.js";

// Native H033 error shape; synthetic arguments and identities isolate child scope.
const schemaError = 'MCP error -32602: Input validation error: Invalid arguments for tool image_capabilities: Unrecognized key: "prompt"';
const mcp = (id: string, complete = false, args: Record<string, unknown> = { prompt: "fixture" }) => ({
  id, type: "mcpToolCall", server: "image", tool: "image_capabilities", arguments: args,
  status: complete ? "failed" : "inProgress", error: null,
  result: complete ? { content: [{ type: "text", text: schemaError }] } : null,
});
function fixture() {
  const failures: { failure: CodexSchemaErrorFailure; threadId: string; turnId: string }[] = [];
  const updates: EngineUpdate[] = [];
  const children = new CodexChildren(() => "parent", update => updates.push(update), 4,
    ["qwen3.8-27b"], (failure, threadId, turnId) => failures.push({ failure, threadId, turnId }));
  const own = (threadId: string) => children.thread({ id: threadId, parentThreadId: "parent", modelProvider: "sova", model: "qwen3.8-27b" });
  const start = (threadId: string, turnId: string) => children.notification("turn/started", { threadId, turn: { id: turnId } });
  const event = (threadId: string, turnId: string, item: Record<string, unknown>, complete = false) =>
    children.notification(complete ? "item/completed" : "item/started", { threadId, turnId, item });
  const attempt = (threadId: string, turnId: string, id: string, args?: Record<string, unknown>) => {
    event(threadId, turnId, mcp(id, false, args));
    event(threadId, turnId, mcp(id, true, args), true);
  };
  return { children, failures, updates, own, start, event, attempt };
}

test("three owned child schema errors report exact scope and trace without settling or exposing child prose", () => {
  const f = fixture(); f.own("child"); f.start("child", "turn");
  f.attempt("child", "turn", "a"); f.attempt("child", "turn", "b");
  f.event("child", "turn", { id: "message", type: "agentMessage", text: "private child prose" });
  f.event("child", "turn", { id: "message", type: "agentMessage", text: "private child prose" }, true);
  assert.equal(f.failures.length, 0);
  f.attempt("child", "turn", "c");
  assert.equal(f.failures.length, 1);
  assert.equal(f.failures[0].threadId, "child"); assert.equal(f.failures[0].turnId, "turn");
  assert.deepEqual(f.failures[0].failure.callIds, ["a", "b", "c"]);
  assert.equal(f.failures[0].failure.error, schemaError);
  assert.equal(f.failures[0].failure.tool, "image_capabilities");
  assert.deepEqual(f.failures[0].failure.attempts, [mcp("a", true), mcp("b", true), mcp("c", true)]);
  assert.doesNotMatch(JSON.stringify(f.failures), /private child prose/);
  assert.doesNotMatch(JSON.stringify(f.updates), /private child prose/);
  assert.equal(f.children.unfinished, true);
  f.children.interruptedAfterCleanup();
  assert.equal(f.children.unfinished, false); assert.equal(f.children.summary().cancelled, 1);
});

test("identical child errors do not combine across children or later turns", () => {
  const f = fixture();
  for (const child of ["one", "two"]) { f.own(child); f.start(child, "old"); }
  f.attempt("one", "old", "a"); f.attempt("one", "old", "b");
  f.attempt("two", "old", "a"); f.attempt("two", "old", "b");
  assert.equal(f.failures.length, 0);
  f.children.notification("turn/completed", { threadId: "one", turn: { id: "old", status: "completed" } });
  f.start("one", "new"); f.attempt("one", "new", "a");
  assert.equal(f.failures.length, 0);
  f.attempt("two", "old", "c");
  assert.equal(f.failures.length, 1); assert.equal(f.failures[0].threadId, "two");
  f.attempt("one", "new", "b"); assert.equal(f.failures.length, 1);
  f.attempt("one", "new", "c");
  assert.equal(f.failures.length, 2); assert.equal(f.failures[1].turnId, "new");
});

test("duplicate completion cannot increment a child schema-error streak", () => {
  const f = fixture(); f.own("child"); f.start("child", "turn");
  f.attempt("child", "turn", "a");
  for (let n = 0; n < 4; n++) f.event("child", "turn", mcp("a", true), true);
  assert.equal(f.failures.length, 0);
  f.attempt("child", "turn", "b"); assert.equal(f.failures.length, 0);
  f.attempt("child", "turn", "c"); assert.equal(f.failures.length, 1);
  f.event("child", "turn", mcp("c", true), true); assert.equal(f.failures.length, 1);
});

test("unowned, stale, missing-start and invalid child events never reach the guard", () => {
  const f = fixture(); f.own("child"); f.start("child", "turn");
  f.attempt("child", "turn", "a"); f.attempt("child", "turn", "b");
  assert.throws(() => f.event("foreign", "turn", mcp("c", true), true), /Unowned/);
  assert.throws(() => f.event("child", "previous", mcp("c", true), true), /Out-of-order/);
  assert.throws(() => f.event("child", "turn", mcp("missing", true), true), /lifecycle/);
  f.event("child", "turn", mcp("c"));
  assert.throws(() => f.event("child", "turn", { ...mcp("c", true), status: "inProgress" }, true), /not terminal/);
  assert.equal(f.failures.length, 0);
  f.event("child", "turn", mcp("c", true), true); assert.equal(f.failures.length, 1);
});

test("changed child call arguments and overlapping calls reset the schema-error streak", () => {
  const f = fixture(); f.own("child"); f.start("child", "turn");
  f.attempt("child", "turn", "a"); f.attempt("child", "turn", "b");
  f.event("child", "turn", mcp("changed"));
  f.event("child", "turn", mcp("changed", true, { prompt: "different" }), true);
  f.attempt("child", "turn", "c"); f.attempt("child", "turn", "d");
  assert.equal(f.failures.length, 0);
  f.event("child", "turn", mcp("overlap-one"));
  f.event("child", "turn", mcp("overlap-two"));
  f.event("child", "turn", mcp("overlap-one", true), true);
  f.event("child", "turn", mcp("overlap-two", true), true);
  f.attempt("child", "turn", "e"); f.attempt("child", "turn", "f");
  assert.equal(f.failures.length, 0);
  f.attempt("child", "turn", "g");
  assert.equal(f.failures.length, 1); assert.deepEqual(f.failures[0].failure.callIds, ["e", "f", "g"]);
});
