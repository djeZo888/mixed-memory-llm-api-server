import assert from "node:assert/strict";
import test from "node:test";
import { CodexChildren } from "../src/codex-children.js";
const spawn = (id: string, status = "running", model = "qwen3.8-27b") => ({
  tool: "spawnAgent",
  status: "completed",
  senderThreadId: "parent",
  receiverThreadIds: [id],
  model,
  agentsStates: { [id]: { status, message: null } },
});
test("child bounds, missing model, unknown status, and foreign ancestry fail closed", () => {
  const children = new CodexChildren(
    () => "parent",
    () => {},
    2,
  );
  assert.throws(() => children.item(spawn("c", "running", ""), true), /model/);
  assert.throws(
    () =>
      children.thread({
        id: "foreign",
        parentThreadId: "other",
        model: "qwen3.8-27b",
        modelProvider: "sova",
      }),
    /Unowned/,
  );
  children.item(spawn("c", "notFound"), true);
  assert.equal(children.unfinished, true);
  children.item(spawn("d", "completed"), true);
  assert.equal(children.summary().completed, 1);
  assert.throws(() => children.item(spawn("e"), true), /bound/);
  assert.throws(
    () =>
      children.item(
        { ...spawn("c"), agentsStates: { foreign: { status: "completed" } } },
        true,
      ),
    /Unowned/,
  );
});
test("late previous child terminal cannot settle a newer turn and nested work is unavailable", () => {
  const c = new CodexChildren(
    () => "parent",
    () => {},
  );
  c.item(spawn("child"), true);
  c.notification("turn/started", { threadId: "child", turn: { id: "a" } });
  c.notification("turn/completed", {
    threadId: "child",
    turn: { id: "a", status: "completed" },
  });
  c.notification("turn/started", { threadId: "child", turn: { id: "b" } });
  assert.throws(
    () =>
      c.notification("turn/completed", {
        threadId: "child",
        turn: { id: "a", status: "completed" },
      }),
    /terminal/,
  );
  assert.equal(c.unfinished, true);
  assert.throws(
    () =>
      c.notification("item/started", {
        threadId: "child",
        turnId: "b",
        item: { id: "grandchild", type: "collabAgentToolCall" },
      }),
    /Nested/,
  );
});
test("collaboration completed state cannot settle an observed active child turn; conflicting terminal rejected", () => {
  const c = new CodexChildren(
    () => "parent",
    () => {},
  );
  c.item(spawn("child"), true);
  c.notification("turn/started", { threadId: "child", turn: { id: "active" } });
  c.item({ ...spawn("child", "completed"), tool: "wait", model: null }, true);
  assert.equal(c.unfinished, true);
  assert.equal(c.summary().active, 1);
  assert.equal(c.summary().completed, 0);
  c.notification("turn/completed", {
    threadId: "child",
    turn: { id: "active", status: "failed" },
  });
  assert.equal(c.summary().failed, 1);
  assert.throws(
    () =>
      c.notification("turn/completed", {
        threadId: "child",
        turn: { id: "active", status: "completed" },
      }),
    /Conflicting/,
  );
  assert.equal(c.summary().failed, 1);
});
