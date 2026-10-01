import assert from "node:assert/strict";
import test from "node:test";
import { PassThrough } from "node:stream";
import { CodexConnection } from "../src/codex-connection.js";
function fixture(timeout = 1000) {
  const input = new PassThrough(),
    output = new PassThrough();
  const sent: any[] = [],
    events: any[] = [],
    errors: Error[] = [];
  output.on("data", (data) => sent.push(JSON.parse(data.toString())));
  const connection = new CodexConnection(
    input,
    output,
    (method, params) => events.push({ method, params }),
    (error) => errors.push(error),
    timeout,
  );
  const receive = (value: unknown) => input.write(JSON.stringify(value) + "\n");
  return { input, output, sent, events, errors, connection, receive };
}
test("JSONL framing accepts split records; exact duplicate responses are harmless", async () => {
  const f = fixture();
  const result = f.connection.request("initialize", {
    clientInfo: { name: "sova", version: "fixture" },
  });
  f.input.write('{"id":1,"result":');
  f.input.write('{"userAgent":"fixture"}}\n');
  assert.deepEqual(await result, { userAgent: "fixture" });
  f.receive({ id: 1, result: { userAgent: "fixture" } });
  f.connection.initialized();
  f.receive({ method: "thread/started", params: { thread: { id: "t" } } });
  assert.equal(f.events.length, 1);
  assert.equal(f.errors.length, 0);
  assert.equal(f.sent.length, 2);
});
test("invalid/truncated/process-death and conflicting responses reject without retries", async () => {
  for (const failure of [
    "invalid",
    "truncated",
    "death",
    "wrong-id",
    "conflict",
  ]) {
    const f = fixture();
    if (failure === "conflict") {
      const first = f.connection.request("initialize", {});
      f.receive({ id: 1, result: {} });
      await first;
    }
    const pending = f.connection.request("turn/start", { threadId: "thread" });
    const rejected = assert.rejects(pending);
    if (failure === "invalid") f.input.write("not-json\n");
    if (failure === "truncated") {
      f.input.write('{"result":');
      f.input.end();
    }
    if (failure === "death") f.input.end();
    if (failure === "wrong-id") f.receive({ id: 99, result: {} });
    if (failure === "conflict")
      f.receive({ id: 1, result: { different: true } });
    await rejected;
    assert.equal(f.sent.filter((v) => v.method === "turn/start").length, 1);
    await assert.rejects(f.connection.request("turn/start", {}));
  }
});
test("unsupported server requests get an explicit denial and no browser/host execution", async () => {
  const f = fixture();
  const pending = f.connection.request("turn/start", {});
  const rejected = assert.rejects(pending);
  f.receive({
    id: "approval",
    method: "item/commandExecution/requestApproval",
    params: { command: "untrusted" },
  });
  await rejected;
  assert.equal(f.sent[1].error.code, -32601);
  assert.equal(f.events[0].method, "sova/unsupportedRequest");
  await assert.rejects(f.connection.request("command/exec" as never, {}));
});
test("timeout and late response never dispatch a second prompt", async () => {
  const f = fixture(10);
  const pending = f.connection.request("turn/start", {});
  await assert.rejects(pending, /will not be replayed/);
  f.receive({ id: 1, result: { turn: { id: "late" } } });
  assert.equal(f.sent.length, 1);
  assert.equal(f.errors.length, 1);
});

test("coalesced frames preserve retained history when the transport chunk exceeds the frame limit", async () => {
  const f = fixture();
  const history = [{ role: "user", text: "old requirement " + "ž".repeat(1250000) }];
  const result = { thread: { id: "retained-thread", turns: [{ items: history }] } };
  const pending = f.connection.request("thread/resume", { threadId: "retained-thread" });
  const event = { method: "thread/started", params: { thread: { id: "retained-thread", turns: [{ items: history }] } } };
  const responseFrame = JSON.stringify({ id: 1, result });
  const eventFrame = JSON.stringify(event);
  assert.ok(Buffer.byteLength(responseFrame) < 4 * 1024 * 1024);
  assert.ok(Buffer.byteLength(eventFrame) < 4 * 1024 * 1024);
  assert.ok(Buffer.byteLength(responseFrame + eventFrame) > 4 * 1024 * 1024);
  f.input.write(responseFrame + "\n" + eventFrame + "\n");
  assert.deepEqual(await pending, result);
  assert.deepEqual(f.events, [event]);
  assert.deepEqual(result.thread.turns[0].items, history);
  assert.equal(f.errors.length, 0);
  assert.equal(f.sent.length, 1, "history receipt must not replay resume");
});

test("individual oversized frames still fail closed, including split and unterminated frames", async () => {
  for (const ending of ["\n", ""]) {
    const f = fixture();
    const pending = f.connection.request("thread/resume", { threadId: "retained-thread" });
    const rejected = assert.rejects(pending, /frame exceeds limit/);
    const frame = JSON.stringify({ id: 1, result: { history: "ž".repeat(2200000) } });
    f.input.write(frame.slice(0, 1100000));
    assert.equal(f.errors.length, 0);
    f.input.write(frame.slice(1100000) + ending);
    await rejected;
    assert.equal(f.errors.length, 1);
    assert.equal(f.events.length, 0);
    assert.equal(f.sent.length, 1);
    await assert.rejects(f.connection.request("thread/resume", {}));
  }
});

test("compaction ACK is not a terminal event; a missing ACK times out without replay", async () => {
  const f = fixture(10);
  const acknowledged = f.connection.request("thread/compact/start", { threadId: "thread" });
  f.receive({ id: 1, result: {} });
  assert.deepEqual(await acknowledged, {});
  assert.equal(f.events.length, 0, "RPC response must not fabricate completion");
  const pending = f.connection.request("thread/compact/start", { threadId: "thread" });
  await assert.rejects(pending, /will not be replayed/);
  f.receive({ id: 2, result: {} });
  assert.equal(f.sent.length, 2, "exactly the two explicitly requested operations");
  assert.equal(f.errors.length, 1);
});
