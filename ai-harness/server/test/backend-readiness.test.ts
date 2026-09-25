import assert from "node:assert/strict";
import test, { type TestContext } from "node:test";
import {
  createServer,
  type IncomingMessage,
  type ServerResponse,
} from "node:http";
import { setTimeout as delay } from "node:timers/promises";
import { createBackendReadiness } from "../src/backend-readiness.js";

type Service = "qwen-gpu0" | "qwen-gpu1" | "image";
const KEY = "fixture-inference-key-never-public";
const aliases = { "qwen-gpu0": "qwen3.8-27b-gpu0", "qwen-gpu1": "qwen3.8-27b" };
const textBody = (service: "qwen-gpu0" | "qwen-gpu1", changes = {}) => ({
  schema_version: 1,
  model_alias: aliases[service],
  ready: true,
  state: "up",
  admitting: null,
  ...changes,
});
const imageBody = (changes = {}) => ({
  model: "qwen-image-2.1",
  ready: true,
  admitting: true,
  busy: false,
  ...changes,
});
const signal = () => AbortSignal.timeout(3000);
async function fixture(
  t: TestContext,
  service: Service,
  handler: (req: IncomingMessage, res: ServerResponse) => void,
) {
  const server = createServer(handler);
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  t.after(
    () =>
      new Promise<void>((resolve) => {
        server.closeAllConnections();
        server.close(() => resolve());
      }),
  );
  const origin = `http://127.0.0.1:${(server.address() as { port: number }).port}`;
  return {
    probe: createBackendReadiness(KEY, {
      fixtureOrigins: { [service]: origin },
    })[service],
    origin,
  };
}
function unavailable(error: unknown) {
  assert.ok(error instanceof Error);
  assert.equal(error.message, "Passive backend readiness unavailable");
  assert.ok(!String(error).includes(KEY));
  assert.ok(!String(error).includes("private-fixture"));
  return true;
}

test("only fixed passive GET paths consume the server-side inference credential; no work body or idle claim", async (t) => {
  for (const service of ["qwen-gpu0", "qwen-gpu1", "image"] as const) {
    let calls = 0;
    const { probe } = await fixture(t, service, (req, res) => {
      calls++;
      assert.equal(req.method, "GET");
      assert.equal(
        req.url,
        service === "image" ? "/v1/image-capabilities" : "/v1/readiness",
      );
      assert.equal(req.headers.authorization, `Bearer ${KEY}`);
      assert.equal(req.headers["content-length"], undefined);
      assert.equal(req.headers["transfer-encoding"], undefined);
      res.setHeader("Content-Type", "application/json");
      res.end(
        JSON.stringify(service === "image" ? imageBody() : textBody(service)),
      );
    });
    const value = await probe(signal());
    assert.deepEqual(value, { ready: true });
    assert.deepEqual(Object.keys(value), ["ready"]);
    assert.equal(calls, 1);
  }
});

test("text readiness requires matching model and consistent strict ready/up/status/admitting contract", async (t) => {
  let status = 200;
  let body: unknown = textBody("qwen-gpu0");
  const { probe } = await fixture(t, "qwen-gpu0", (_req, res) => {
    res.writeHead(status);
    res.end(JSON.stringify(body));
  });
  for (const [state, expected] of [
    ["starting", false],
    ["unhealthy", false],
    ["unknown", null],
  ] as const) {
    status = 503;
    body = textBody("qwen-gpu0", { state, ready: false });
    assert.deepEqual(await probe(signal()), { ready: expected });
  }
  for (const [code, value] of [
    [200, textBody("qwen-gpu1")],
    [200, textBody("qwen-gpu0", { schema_version: 2 })],
    [200, textBody("qwen-gpu0", { ready: "true" })],
    [200, textBody("qwen-gpu0", { admitting: true })],
    [200, textBody("qwen-gpu0", { state: "starting" })],
    [503, textBody("qwen-gpu0")],
    [200, textBody("qwen-gpu0", { ready: false, state: "unhealthy" })],
    [503, textBody("qwen-gpu0", { ready: false, state: "ready" })],
  ] as const) {
    status = code;
    body = value;
    await assert.rejects(probe(signal()), unavailable);
  }
});

test("healthy busy image remains ready; readiness never asserts that image worker is idle", async (t) => {
  let body: unknown = imageBody();
  const { probe } = await fixture(t, "image", (_req, res) =>
    res.end(JSON.stringify(body)),
  );
  for (const [changes, expected] of [
    [{ ready: true, admitting: false, busy: true }, true],
    [{ ready: true, admitting: true, busy: false }, true],
    [{ ready: false, admitting: false, busy: false }, false],
    [{ ready: true, admitting: false, busy: false }, false],
  ] as const) {
    body = imageBody(changes);
    assert.deepEqual(await probe(signal()), { ready: expected });
  }
  for (const changes of [
    { model: "unexpected-model" },
    { ready: "true" },
    { admitting: null },
    { busy: undefined },
  ]) {
    body = imageBody(changes);
    await assert.rejects(probe(signal()), unavailable);
  }
});

test("redirects never follow a target or transmit credentials to it", async (t) => {
  let destinationCalls = 0;
  const target = await fixture(t, "image", (_req, res) => {
    destinationCalls++;
    res.end(JSON.stringify(imageBody()));
  });
  const source = await fixture(t, "image", (_req, res) => {
    res.writeHead(302, { Location: target.origin + "/admin" });
    res.end("private-fixture redirect body");
  });
  await assert.rejects(source.probe(signal()), unavailable);
  assert.equal(destinationCalls, 0);
});

test("malformed, oversized and upstream failure details remain unknown without leaking backend bytes", async (t) => {
  let body = "private-fixture invalid-json";
  let status = 200;
  const { probe } = await fixture(t, "image", (_req, res) => {
    res.writeHead(status);
    res.end(body);
  });
  for (const value of [
    "private-fixture invalid-json",
    "null",
    "[]",
    JSON.stringify({ ...imageBody(), padding: "x".repeat(128 * 1024) }),
  ]) {
    body = value;
    await assert.rejects(probe(signal()), unavailable);
  }
  body = "private-fixture backend trace " + KEY;
  for (const code of [401, 404, 500, 503]) {
    status = code;
    await assert.rejects(probe(signal()), unavailable);
  }
});

test("transport errors and cancellation are bounded and use fixed errors", async (t) => {
  const closed = await fixture(t, "qwen-gpu1", (req) => req.socket.destroy());
  await assert.rejects(closed.probe(signal()), unavailable);
  let entered = false;
  const hanging = await fixture(t, "image", () => {
    entered = true;
  });
  const controller = new AbortController();
  const result = assert.rejects(hanging.probe(controller.signal), unavailable);
  for (let i = 0; !entered && i < 50; i++) await delay(2);
  assert.equal(entered, true);
  const started = performance.now();
  controller.abort();
  await result;
  assert.ok(performance.now() - started < 500);
  const internalDeadline = performance.now();
  await assert.rejects(
    hanging.probe(new AbortController().signal),
    unavailable,
  );
  const elapsed = performance.now() - internalDeadline;
  assert.ok(
    elapsed >= 1500 && elapsed < 3000,
    `expected internal 2s cap, observed ${elapsed}ms`,
  );
});

test("fixture overrides cannot route privileged probes to external hosts, userinfo, paths, or alternate protocols", () => {
  for (const origin of [
    "http://example.com",
    "http://10.156.100.60:30008",
    "https://127.0.0.1:12345",
    "http://localhost:12345",
    "http://[::1]:12345",
    "http://user:pass@127.0.0.1:12345",
    "http://127.0.0.1:12345/health",
    "http://127.0.0.1:12345?secret=private-fixture",
    "http://127.0.0.1:12345#fragment",
  ]) {
    assert.throws(() =>
      createBackendReadiness(KEY, { fixtureOrigins: { image: origin } }),
    );
  }
});
