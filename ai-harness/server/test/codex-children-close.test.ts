import assert from "node:assert/strict";
import test from "node:test";
import { CodexChildren } from "../src/codex-children.js";
import type { EngineUpdate } from "../src/contracts.js";

const parent = "01a0edc1-1b35-7860-93a2-3d2c563d06a8";
const historical = "01a0ede6-0fad-7191-9e87-bcad69beb761";
const call = "call_c6b86a86548d4b99953770e9";
// Terminal identity/status derive from retained EDIT Core item ordinal 130.
// Start is reconstructed from pinned 064c6b8 event_mapping.rs CloseBegin;
// this is not an archived AppServer notification or host-exception receipt.
const close = (complete = false): Record<string, unknown> => ({
  type: "collabAgentToolCall", id: call, tool: "closeAgent",
  status: complete ? "failed" : "inProgress", senderThreadId: parent,
  receiverThreadIds: [historical], prompt: null, model: null, reasoningEffort: null,
  agentsStates: complete ? { [historical]: { status: "notFound", message: null } } : {},
});
function fixture(max = 4) {
  const updates: EngineUpdate[] = [];
  const children = new CodexChildren(() => parent, update => updates.push(update), max);
  return { children, updates };
}
const empty = { known: true, active: 0, completed: 0, failed: 0, cancelled: 0 };
function unowned(f: ReturnType<typeof fixture>) {
  assert.equal(f.children.owns(historical), false);
  assert.deepEqual(f.children.summary(), empty);
  assert.deepEqual(f.updates, []);
}

test("retained failed/notFound close pair settles only call bookkeeping and permits a real new child", () => {
  const f = fixture();
  const start = close(), end = close(true), snapshot = JSON.stringify([start, end]);
  f.children.item(start, false);
  unowned(f); assert.equal(f.children.unfinished, true);
  f.children.item(end, true);
  unowned(f); assert.equal(f.children.unfinished, false);
  assert.equal(JSON.stringify([start, end]), snapshot);
  f.children.item({ type: "collabAgentToolCall", id: "new-spawn", tool: "spawnAgent",
    status: "completed", senderThreadId: parent, receiverThreadIds: ["new-child"],
    model: "qwen3.8-27b", agentsStates: { "new-child": { status: "running", message: null } } }, true);
  assert.equal(f.children.owns("new-child"), true);
  assert.equal(f.children.owns(historical), false);
  assert.equal(f.children.summary().active, 1);
  assert.equal(f.updates.some(update => update.type === "progress" && update.subagentId === historical), false);
});

test("unknown active collaboration and unknown activity remain fail closed", () => {
  for (const tool of ["sendInput", "wait", "resumeAgent", "sendMessage", "followupTask", "interruptAgent"]) {
    for (const complete of [false, true]) {
      const f = fixture();
      assert.throws(() => f.children.item({ ...close(complete), tool,
        agentsStates: { [historical]: { status: "running", message: null } } }, complete), /Unknown native child/);
      unowned(f);
    }
  }
  const f = fixture(); f.children.item(close(), false);
  assert.throws(() => f.children.activity({ agentThreadId: historical, agentPath: "child", kind: "started" }), /Unowned/);
  assert.throws(() => f.children.notification("turn/started", { threadId: historical, turn: { id: "foreign-turn" } }), /Unowned/);
  unowned(f); assert.equal(f.children.unfinished, true);
});

test("unknown close requires the matching provisional call and exact failed/notFound terminal", () => {
  const changes: Record<string, unknown>[] = [
    { status: "completed" }, { status: "interrupted" }, { status: "inProgress" },
    { agentsStates: {} },
    ...["running", "pendingInit", "completed", "shutdown", "errored", "interrupted", "not_found"].map(status =>
      ({ agentsStates: { [historical]: { status, message: null } } })),
    { agentsStates: { [historical]: { status: "notFound" } } },
    { agentsStates: { [historical]: { status: "notFound", message: "not found" } } },
    { agentsStates: { [historical]: { status: "notFound", message: {} } } },
    { agentsStates: { [historical]: { status: "notFound", message: null, error: "extra" } } },
    { agentsStates: { [historical]: null } },
    { agentsStates: { [historical]: { status: "notFound", message: null }, other: { status: "notFound", message: null } } },
    { error: { message: "not found" } }, { result: { error: "not found" } },
  ];
  for (const change of changes) {
    const f = fixture(); f.children.item(close(), false);
    assert.throws(() => f.children.item({ ...close(true), ...change }, true));
    unowned(f); assert.equal(f.children.unfinished, true);
  }
  const f = fixture();
  assert.throws(() => f.children.item(close(true), true), /Unconfirmed/);
  unowned(f); assert.equal(f.children.unfinished, false);
});

test("provisional close rejects receiver, call, sender, type, tool and metadata drift", () => {
  const changes: Record<string, unknown>[] = [
    { id: "other-call" }, { id: "" }, { senderThreadId: "other-parent" },
    { receiverThreadIds: ["other-child"] }, { receiverThreadIds: [parent] },
    { receiverThreadIds: [] }, { receiverThreadIds: [historical, "other-child"] },
    { type: "mcpToolCall" }, { tool: "spawnAgent", model: "qwen3.8-27b" },
    { tool: "sendInput" }, { tool: "wait" }, { tool: "resumeAgent" },
    { model: "qwen3.8-27b" }, { model: undefined }, { prompt: "unexpected" },
    { reasoningEffort: "high" },
    { agentsStates: { other: { status: "notFound", message: null } } },
  ];
  for (const change of changes) {
    const f = fixture(); f.children.item(close(), false);
    assert.throws(() => f.children.item({ ...close(true), ...change }, true));
    unowned(f); assert.equal(f.children.unfinished, true);
    assert.equal(f.children.owns("other-child"), false);
  }
});

test("provisional starts are bounded, reject premature state and do not imply terminal absence", () => {
  for (const change of [
    { status: "failed" }, { agentsStates: { [historical]: { status: "notFound", message: null } } },
    { agentsStates: { [historical]: { status: "running", message: null } } },
    { receiverThreadIds: [parent] }, { prompt: undefined }, { error: null },
  ]) {
    const f = fixture(); assert.throws(() => f.children.item({ ...close(), ...change }, false));
    unowned(f); assert.equal(f.children.unfinished, false);
  }
  const f = fixture(1); f.children.item(close(), false);
  f.children.item(close(), false); // Exact duplicate does not consume another slot.
  assert.throws(() => f.children.item({ ...close(), id: "second-call" }, false), /bound/);
  assert.throws(() => f.children.item({ ...close(), receiverThreadIds: ["changed"] }, false), /binding/);
  unowned(f); assert.equal(f.children.unfinished, true);
  f.children.interruptedAfterCleanup();
  unowned(f); assert.equal(f.children.unfinished, false);
  assert.throws(() => f.children.item(close(true), true), /Unconfirmed/);
});

test("tracked child close and confirmed cleanup retain genuine ownership and active-turn semantics", () => {
  const f = fixture();
  f.children.thread({ id: "owned", parentThreadId: parent, modelProvider: "sova", model: "qwen3.8-27b" });
  f.children.notification("turn/started", { threadId: "owned", turn: { id: "active" } });
  f.children.item({ ...close(), id: "owned-close", receiverThreadIds: ["owned"] }, false);
  f.children.item({ ...close(true), id: "owned-close", receiverThreadIds: ["owned"], status: "completed",
    agentsStates: { owned: { status: "shutdown", message: null } } }, true);
  assert.equal(f.children.owns("owned"), true);
  assert.equal(f.children.unfinished, true); // Observed active turn still requires settlement.
  f.children.item(close(), false);
  f.children.interruptedAfterCleanup();
  assert.equal(f.children.unfinished, false);
  assert.equal(f.children.summary().cancelled, 1);
  assert.equal(f.children.owns(historical), false);
  assert.equal(f.updates.some(update => update.type === "progress" && update.subagentId === historical), false);
  assert.ok(f.updates.some(update => update.type === "progress" && update.subagentId === "owned" && update.detail?.includes("cleanup")));
});

test("a provisional target becoming owned cannot reuse the unowned-close exception", () => {
  const f = fixture(); f.children.item(close(), false);
  f.children.thread({ id: historical, parentThreadId: parent, modelProvider: "sova", model: "qwen3.8-27b" });
  assert.throws(() => f.children.item(close(true), true), /binding/);
  assert.equal(f.children.owns(historical), true);
  assert.equal(f.children.unfinished, true);
  assert.equal(f.children.summary().active, 1);
});
