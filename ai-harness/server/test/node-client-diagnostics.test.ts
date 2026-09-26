import assert from "node:assert/strict";
import test from "node:test";
import { NodeResponseError, nodeResponseError } from "../src/node-client.js";
import { ApiError, publicError } from "../src/errors.js";

test("allowlisted producer diagnostics preserve existing public error mappings", () => {
  for (const [upstream, status, code, message] of [
    [400, 400, "node_unavailable", "Node request unavailable; retain action key and inspect operation status"],
    [404, 404, "node_unavailable", "Node request unavailable; retain action key and inspect operation status"],
    [409, 409, "node_action_conflict", "Target changed or interruption confirmation required; refresh targets"],
    [422, 422, "node_action_unsupported", "Action unsupported by the guarded node owner"],
    [503, 503, "node_unavailable", "Node request unavailable; retain action key and inspect operation status"],
    [500, 503, "node_unavailable", "Node request unavailable; retain action key and inspect operation status"],
  ] as const) {
    const error = nodeResponseError(upstream, Buffer.from('{"error":{"code":"stale_state"}}'));
    assert.ok(error instanceof ApiError);
    assert.ok(error instanceof NodeResponseError);
    assert.equal(error.statusCode, status);
    assert.deepEqual(publicError(error), { code, message });
    assert.equal(error.upstreamStatus, upstream);
    assert.equal(error.upstreamCode, "stale_state");
  }
});

test("constructor itself rejects arbitrary diagnostic values", () => {
  for (const status of [null, undefined, "409", 99, 600, 409.5, NaN, Infinity]) {
    const error = new NodeResponseError(status, "PRIVATE_UPSTREAM_VALUE");
    assert.equal(error.upstreamStatus, null);
    assert.equal(error.upstreamCode, null);
    assert.equal(error.statusCode, 503);
    assert.ok(!JSON.stringify(error).includes("PRIVATE_UPSTREAM_VALUE"));
  }
  for (const status of [100, 409, 599])
    assert.equal(new NodeResponseError(status, "lifecycle_busy").upstreamStatus, status);
  for (const code of [null, 409, ["stale_state"], { code: "stale_state" }, "constructor", "__proto__", "stale_state\nSECRET"])
    assert.equal(new NodeResponseError(409, code).upstreamCode, null);
});

test("bounded parser retains no arbitrary upstream body or message", () => {
  const secret = "UNTRUSTED_SECRET_BODY";
  const error = nodeResponseError(409, Buffer.from(JSON.stringify({
    error: { code: "stale_state", message: secret, stack: secret, credentials: secret },
    message: secret,
  })));
  assert.equal(error.upstreamCode, "stale_state");
  assert.deepEqual(Object.keys(error).sort(), ["code", "statusCode", "upstreamCode", "upstreamStatus"]);
  assert.ok(!JSON.stringify(error).includes(secret));
  assert.ok(!error.message.includes(secret));
  assert.ok(!error.stack?.includes(secret));
  for (const body of [
    "not-json", "null", "[]", '{"error":[]}', '{"error":"stale_state"}',
    '{"error":{"code":"UNTRUSTED_SECRET_BODY"}}',
    '{"error":{"code":{"value":"stale_state"}}}',
    JSON.stringify({ error: { code: "stale_state" }, padding: "x".repeat(512 * 1024) }),
  ]) {
    const rejected = nodeResponseError(409, Buffer.from(body));
    assert.equal(rejected.upstreamCode, null);
    assert.equal(rejected.code, "node_action_conflict");
  }
});
