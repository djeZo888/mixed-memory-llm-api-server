import assert from "node:assert/strict";
import test, { type TestContext } from "node:test";
import {
  createServer,
  type IncomingMessage,
  type ServerResponse,
} from "node:http";
import sharp from "sharp";
import { ImageUpstream, IMAGE_ORIGIN } from "../src/image-upstream.js";

const caps = {
  model: "qwen-image-2.1",
  ready: true,
  busy: false,
  admitting: true,
  profiles: [
    {
      operation: "generation",
      references: 0,
      size: "1920x1080",
      transparent: false,
      evidence_sha256: "a".repeat(64),
      native_size: "1920x1088",
      crop_bottom: 8,
    },
  ],
  extension: { preserved: 1 },
};
async function fixture(
  t: TestContext,
  handle: (req: IncomingMessage, res: ServerResponse) => void,
) {
  const server = createServer(handle);
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  t.after(
    () =>
      new Promise<void>((resolve) => {
        server.closeAllConnections();
        server.close(() => resolve());
      }),
  );
  return new ImageUpstream({
    key: "fixture-host-only-key",
    fixtureOrigin: `http://127.0.0.1:${(server.address() as { port: number }).port}`,
    requestMs: 100,
    responseMs: 100,
  });
}
const signal = () => AbortSignal.timeout(2000);
const input = {
  operation: "generation" as const,
  prompt: "fixture",
  seed: 42,
  size: "1920x1080",
  model: "qwen-image-2.1",
  references: [] as Buffer[],
};

test("fixed private origin; authenticated unchanged capabilities and strict readiness+idle", async (t) => {
  assert.equal(IMAGE_ORIGIN, "http://10.156.100.60:30006");
  assert.throws(
    () =>
      new ImageUpstream({ key: "fake", fixtureOrigin: "http://example.com" }),
    /loopback/,
  );
  let health = { ready: true, admitting: true, busy: false };
  const upstream = await fixture(t, (req, res) => {
    assert.equal(req.headers.authorization, "Bearer fixture-host-only-key");
    res.setHeader("content-type", "application/json");
    res.end(
      JSON.stringify(req.url === "/v1/image-capabilities" ? caps : health),
    );
  });
  assert.deepEqual(await upstream.capabilities(signal()), caps);
  assert.deepEqual(
    upstream.profiles(caps).map((p) => p.operation),
    ["generation"],
  );
  assert.deepEqual(await upstream.readiness(signal()), {
    ready: true,
    idle: true,
  });
  health = { ready: true, admitting: false, busy: true };
  assert.deepEqual(await upstream.readiness(signal()), {
    ready: false,
    idle: false,
  });
  assert.deepEqual(upstream.profiles({ ...caps, profiles: [] }), []);
});

test("generation sends n1 opaque persisted seed; only b64 data is consumed host-side, FHD remains public1080", async (t) => {
  const png = await sharp({
    create: { width: 1920, height: 1080, channels: 3, background: "#223355" },
  })
    .png()
    .toBuffer();
  let body: Record<string, unknown> = {};
  const upstream = await fixture(t, async (req, res) => {
    assert.equal(req.url, "/v1/images/generations");
    const chunks = [];
    for await (const c of req) chunks.push(c);
    body = JSON.parse(Buffer.concat(chunks).toString());
    res.end(
      JSON.stringify({
        created: 1,
        data: [
          {
            b64_json: png.toString("base64"),
            revised_prompt: "ignored",
            url: "http://must-not-fetch/",
          },
        ],
      }),
    );
  });
  const result = await upstream.execute(input, signal());
  assert.deepEqual(body, {
    model: "qwen-image-2.1",
    prompt: "fixture",
    size: "1920x1080",
    seed: 42,
    n: 1,
    response_format: "b64_json",
    background: "opaque",
  });
  assert.equal(result.kind, "output");
  if (result.kind === "output") assert.deepEqual(result.png, png);
});

test("edit uses ordered PNG multipart and exact scalar allowlist, no backend transport crop/pad at host", async (t) => {
  const references = await Promise.all(
    ["#111111", "#cccccc"].map((background) =>
      sharp({ create: { width: 32, height: 32, channels: 3, background } })
        .png()
        .toBuffer(),
    ),
  );
  let body = Buffer.alloc(0);
  const upstream = await fixture(t, async (req, res) => {
    assert.equal(req.url, "/v1/images/edits");
    assert.match(
      req.headers["content-type"]!,
      /^multipart\/form-data; boundary=image-/,
    );
    const chunks = [];
    for await (const c of req) chunks.push(c);
    body = Buffer.concat(chunks);
    res.end(
      JSON.stringify({
        data: [{ b64_json: references[0].toString("base64") }],
      }),
    );
  });
  await upstream.execute(
    { ...input, operation: "edit", size: "32x32", references },
    signal(),
  );
  assert.ok(
    body.indexOf(references[0]) >= 0 &&
      body.indexOf(references[1]) > body.indexOf(references[0]),
  );
  const text = body.toString("latin1");
  assert.equal((text.match(/name="image\[\]"/g) ?? []).length, 2);
  assert.ok(text.includes('name="seed"\r\n\r\n42'));
  assert.ok(!text.includes("guidance"));
  assert.ok(!text.includes("fixture-host-only-key"));
});

test("only reviewed busy429 retries; unknown errors, malformed output, redirects and transport loss never do", async (t) => {
  let mode = "busy";
  const upstream = await fixture(t, (req, res) => {
    req.resume();
    if (mode === "disconnect") {
      req.socket.destroy();
      return;
    }
    if (mode === "busy" || mode === "unknown429") {
      res.statusCode = 429;
      res.setHeader("Retry-After", "3");
      res.end(
        JSON.stringify({
          error: { code: mode === "busy" ? "busy" : "unknown" },
        }),
      );
    } else if (mode === "redirect") {
      res.statusCode = 302;
      res.setHeader("Location", "http://must-not-fetch/");
      res.end();
    } else if (mode === "malformed")
      res.end('{"data":[{"b64_json":"not-valid-base64"}]}');
    else {
      res.statusCode = 504;
      res.end('{"secret":"must not escape"}');
    }
  });
  assert.deepEqual(await upstream.execute(input, signal()), {
    kind: "not_admitted",
    retryAfterMs: 3000,
  });
  for (mode of ["unknown429", "redirect", "malformed", "timeout", "disconnect"])
    await assert.rejects(
      upstream.execute(input, signal()),
      (e) =>
        e instanceof Error && e.message === "Image upstream is unavailable",
    );
});

test("native/header and response-body budgets are bounded, credential errors sanitized", async (t) => {
  let headers = false;
  const upstream = await fixture(t, (req, res) => {
    req.resume();
    if (headers) {
      res.writeHead(200);
      res.write("{");
    }
  });
  await assert.rejects(upstream.execute(input, signal()), /unavailable/);
  headers = true;
  await assert.rejects(upstream.execute(input, signal()), /unavailable/);
  const invalid = new ImageUpstream({
    key: () => {
      throw new Error("secret path");
    },
  });
  await assert.rejects(
    invalid.capabilities(signal()),
    (e) => e instanceof Error && !e.message.includes("secret"),
  );
});

test("optional upstream effective seed is retained for broker cross-check and never silently overwritten", async (t) => {
  const png = await sharp({
    create: { width: 64, height: 64, channels: 3, background: "#345678" },
  })
    .png()
    .toBuffer();
  let seed: unknown = 43;
  const upstream = await fixture(t, (req, res) => {
    req.resume();
    res.end(
      JSON.stringify({ data: [{ b64_json: png.toString("base64"), seed }] }),
    );
  });
  const result = await upstream.execute({ ...input, size: "64x64" }, signal());
  assert.equal(result.kind, "output");
  if (result.kind === "output") assert.equal(result.seed, 43);
  seed = null;
  await assert.rejects(
    upstream.execute({ ...input, size: "64x64" }, signal()),
    /unavailable/,
  );
});
