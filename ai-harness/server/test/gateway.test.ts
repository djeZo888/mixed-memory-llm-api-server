import test from "node:test";
import assert from "node:assert/strict";
import {
  createServer,
  type IncomingHttpHeaders,
  type ServerResponse,
} from "node:http";
import { setTimeout as delay } from "node:timers/promises";
import { createGateway, type GatewayOptions } from "../src/gateway.js";
import type { GatewayUsage } from "../src/contracts.js";

interface Captured {
  lane: number;
  body: Record<string, unknown>;
  headers: IncomingHttpHeaders;
  response: ServerResponse;
}
async function until(check: () => boolean, timeout = 2500) {
  const started = Date.now();
  while (!check()) {
    if (Date.now() - started > timeout)
      throw new Error("Fixture condition timed out");
    await delay(5);
  }
}
async function fixture(options: Partial<GatewayOptions> = {}) {
  const seen: Captured[] = [];
  const running = [0, 0];
  const maximum = [0, 0];
  const upstream = createServer(async (request, response) => {
    const chunks: Buffer[] = [];
    for await (const chunk of request) chunks.push(chunk as Buffer);
    const lane = Number(request.url!.split("/")[1]);
    running[lane]!++;
    maximum[lane] = Math.max(maximum[lane]!, running[lane]!);
    response.once("close", () => running[lane]!--);
    seen.push({
      lane,
      body: JSON.parse(Buffer.concat(chunks).toString()),
      headers: request.headers,
      response,
    });
  });
  await new Promise<void>((resolve) =>
    upstream.listen(0, "127.0.0.1", resolve),
  );
  const port = (upstream.address() as { port: number }).port;
  const usages: GatewayUsage[] = [];
  const gateway = createGateway({
    upstreamKey: "fixture-upstream-key",
    upstreams: [
      { url: `http://127.0.0.1:${port}/0/v1`, alias: "qwen3.8-27b-gpu0" },
      { url: `http://127.0.0.1:${port}/1/v1`, alias: "qwen3.8-27b" },
    ],
    onUsage: (usage) => usages.push(usage),
    ...options,
  });
  const url = await gateway.app.listen({ host: "127.0.0.1", port: 0 });
  const token = gateway.issueToken("fixture-session");
  const send = (
    body: Record<string, unknown> = {},
    signal?: AbortSignal,
    runnerToken = token,
  ) =>
    fetch(`${url}/v1/chat/completions`, {
      method: "POST",
      headers: {
        authorization: `Bearer ${runnerToken}`,
        "content-type": "application/json",
      },
      body: JSON.stringify({ model: "qwen3.8-27b", messages: [], ...body }),
      signal,
    });
  const complete = (index: number, extra: Record<string, unknown> = {}) => {
    const text = JSON.stringify({
      id: `response-${index}`,
      choices: [{ message: { content: "fixture" }, finish_reason: "stop" }],
      usage: { prompt_tokens: 123, completion_tokens: 4 },
      ...extra,
    });
    seen[index]!.response.setHeader("content-type", "application/json");
    seen[index]!.response.end(text);
    return text;
  };
  const close = async () => {
    await gateway.close();
    upstream.closeAllConnections();
    await new Promise<void>((resolve) => upstream.close(() => resolve()));
  };
  return { gateway, url, token, send, complete, close, seen, usages, maximum };
}

test("gateway authenticates inference-only routes, logical model and declared output limits", async (t) => {
  const f = await fixture();
  t.after(f.close);
  const auth = { authorization: `Bearer ${f.token}` };
  assert.equal((await fetch(`${f.url}/v1/models`)).status, 401);
  assert.equal(
    (await fetch(`${f.url}/api/sessions`, { headers: auth })).status,
    404,
  );
  assert.equal(
    (await fetch(`${f.url}/v1/completions`, { headers: auth })).status,
    404,
  );
  assert.equal(
    (
      await fetch(`${f.url}/v1/models`, {
        headers: { ...auth, origin: "http://evil.invalid" },
      })
    ).status,
    403,
  );
  const models = (await (
    await fetch(`${f.url}/v1/models`, { headers: auth })
  ).json()) as { data: { id: string }[] };
  assert.deepEqual(
    models.data.map((item) => item.id),
    ["qwen3.8-27b"],
  );
  for (const invalid of [
    { model: "glm" },
    { model: "qwen3.8-27b-gpu0" },
    { max_tokens: 0 },
    { max_tokens: 1.1 },
    { max_completion_tokens: "65536" },
    { max_tokens: 65536, max_completion_tokens: 400 },
    { stream: "true" },
    { messages: "text" },
  ])
    assert.equal((await f.send(invalid)).status, 400);
  assert.equal(f.seen.length, 0);
  f.gateway.revokeToken(f.token);
  assert.equal((await f.send()).status, 401);
});

test("gateway translates only request alias/cap, preserves payload and real usage, has no 16K clamp", async (t) => {
  const f = await fixture();
  t.after(f.close);
  const body = {
    messages: [{ role: "user", content: "x".repeat(1024 * 1024 + 1) }],
    tools: [
      {
        type: "function",
        function: {
          name: "local",
          parameters: {
            type: "object",
            properties: { code: { type: "string" } },
          },
        },
      },
    ],
    tool_choice: "auto",
    temperature: 0.3,
    max_tokens: 65536,
  };
  const a = f.send(body);
  await until(() => f.seen.length === 1);
  const b = f.send({
    max_completion_tokens: 13107,
    messages: [{ role: "user", content: "compress" }],
  });
  await until(() => f.seen.length === 2);
  assert.equal(f.seen[0]!.body.model, "qwen3.8-27b-gpu0");
  assert.equal(f.seen[1]!.body.model, "qwen3.8-27b");
  assert.deepEqual(f.seen[0]!.body, { ...body, model: "qwen3.8-27b-gpu0" });
  assert.equal(f.seen[1]!.body.max_completion_tokens, 13107);
  assert.equal(f.seen[1]!.body.max_tokens, undefined);
  assert.equal(f.seen[0]!.headers.authorization, "Bearer fixture-upstream-key");
  const response = f.complete(0, {
    usage: { prompt_tokens: 31415, completion_tokens: 27 },
  });
  f.complete(1);
  assert.equal(await (await a).text(), response);
  await (await b).text();
  assert.equal(f.usages[0]!.promptTokens, 31415);
  assert.equal(f.usages[0]!.sessionId, "fixture-session");
  assert.match(f.usages[0]!.source, /attribution unknown/);
  const capped = f.send({ max_tokens: 100000 });
  await until(() => f.seen.length === 3);
  assert.equal(f.seen[2]!.body.max_tokens, 65536);
  f.complete(2);
  await (await capped).text();
  const defaulted = f.send();
  await until(() => f.seen.length === 4);
  assert.equal(f.seen[3]!.body.max_tokens, 65536);
  f.complete(3);
  await (await defaulted).text();
});

test("two global request permits enforce endpoint cap and FIFO across runner tokens", async (t) => {
  const f = await fixture();
  t.after(f.close);
  const requests: Promise<Response>[] = [];
  const otherToken = f.gateway.issueToken("other-runner");
  for (let index = 0; index < 5; index++) {
    requests.push(
      f.send(
        { user: `request-${index}` },
        undefined,
        index % 2 ? otherToken : f.token,
      ),
    );
    await until(
      () => f.seen.length + f.gateway.snapshot().queued === index + 1,
    );
  }
  assert.equal(f.seen.length, 2);
  assert.equal(f.gateway.snapshot().queued, 3);
  f.complete(0);
  await until(() => f.seen.length === 3);
  assert.equal(f.seen[2]!.body.user, "request-2");
  assert.equal(f.seen[2]!.lane, 0);
  f.complete(1);
  await until(() => f.seen.length === 4);
  assert.equal(f.seen[3]!.body.user, "request-3");
  assert.equal(f.seen[3]!.lane, 1);
  f.complete(2);
  await until(() => f.seen.length === 5);
  assert.equal(f.seen[4]!.body.user, "request-4");
  f.complete(3);
  f.complete(4);
  await Promise.all(requests.map(async (response) => (await response).text()));
  assert.deepEqual(f.maximum, [1, 1]);
  assert.deepEqual(
    f.gateway.snapshot().lanes.map((lane) => lane.state),
    ["idle", "idle"],
  );
});

test("queued cancellation never contacts upstream and bounded queue rejects excess requests", async (t) => {
  const f = await fixture({ queueLimit: 1 });
  t.after(f.close);
  const a = f.send();
  const b = f.send();
  await until(() => f.seen.length === 2);
  const cancel = new AbortController();
  const queued = f
    .send({ user: "cancelled" }, cancel.signal)
    .catch((error) => error as Error);
  await until(() => f.gateway.snapshot().queued === 1);
  assert.equal((await f.send()).status, 429);
  cancel.abort();
  assert.ok((await queued) instanceof Error);
  await until(() => f.gateway.snapshot().queued === 0);
  f.complete(0);
  f.complete(1);
  await (await a).text();
  await (await b).text();
  assert.equal(f.seen.length, 2);
});

test("aggregate queued JSON byte budget rejects excess, releases on cancel, and preserves FIFO", async (t) => {
  const aBody = { user: "queue-α" };
  const bBody = { user: "queue-b" };
  const bytes = (body: Record<string, unknown>) =>
    Buffer.byteLength(
      JSON.stringify({
        model: "qwen3.8-27b",
        messages: [],
        ...body,
        max_tokens: 65536,
      }),
    );
  const f = await fixture({ queueByteLimit: bytes(aBody) + bytes(bBody) });
  t.after(f.close);
  // Immediate dispatch uses the two active request slots, not queued-byte budget.
  const activeBody = {
    messages: [{ role: "user", content: "active".repeat(100) }],
  };
  const x = f.send(activeBody);
  const y = f.send(activeBody);
  await until(() => f.seen.length === 2);
  const cancel = new AbortController();
  const a = f.send(aBody, cancel.signal).catch((error) => error as Error);
  await until(() => f.gateway.snapshot().queued === 1);
  const b = f.send(bBody);
  await until(() => f.gateway.snapshot().queued === 2);
  assert.equal(f.gateway.snapshot().queuedBytes, bytes(aBody) + bytes(bBody));
  const rejected = await f.send({ user: "queue-c" });
  assert.equal(rejected.status, 429);
  assert.equal(
    ((await rejected.json()) as { error: { code: string } }).error.code,
    "queue_bytes_full",
  );
  assert.equal(f.gateway.snapshot().queued, 2);
  cancel.abort();
  assert.ok((await a) instanceof Error);
  await until(() => f.gateway.snapshot().queued === 1);
  assert.equal(f.gateway.snapshot().queuedBytes, bytes(bBody));
  const c = f.send({ user: "queue-c" });
  await until(() => f.gateway.snapshot().queued === 2);
  f.complete(0);
  await until(() => f.seen.length === 3);
  assert.equal(f.seen[2]!.body.user, "queue-b");
  assert.equal(f.gateway.snapshot().queuedBytes, bytes({ user: "queue-c" }));
  f.complete(1);
  await until(() => f.seen.length === 4);
  assert.equal(f.seen[3]!.body.user, "queue-c");
  assert.equal(f.gateway.snapshot().queuedBytes, 0);
  f.complete(2);
  f.complete(3);
  await Promise.all(
    [x, y, b, c].map(async (response) => (await response).text()),
  );
  assert.deepEqual(f.maximum, [1, 1]);
});

test("gateway shutdown releases every queued-byte reservation", async (t) => {
  const f = await fixture({ queueByteLimit: 256 });
  t.after(f.close);
  const a = f.send().catch((error) => error as Error);
  const b = f.send().catch((error) => error as Error);
  await until(() => f.seen.length === 2);
  const queued = f.send().catch((error) => error as Error);
  await until(() => f.gateway.snapshot().queued === 1);
  assert.ok(f.gateway.snapshot().queuedBytes > 0);
  await f.gateway.close();
  await Promise.all([a, b, queued]);
  assert.equal(f.gateway.snapshot().queued, 0);
  assert.equal(f.gateway.snapshot().queuedBytes, 0);
});

test("revoked queued token cannot dispatch, while its existing generations still settle normally", async (t) => {
  const f = await fixture();
  t.after(f.close);
  const a = f.send();
  const b = f.send();
  await until(() => f.seen.length === 2);
  const queued = f.send();
  await until(() => f.gateway.snapshot().queued === 1);
  f.gateway.revokeToken(f.token);
  assert.deepEqual(
    f.gateway.snapshot().lanes.map((lane) => lane.state),
    ["active", "active"],
  );
  f.complete(0);
  assert.equal((await a).status, 200);
  await (await a).text();
  const denied = await queued;
  assert.equal(denied.status, 401);
  assert.equal(
    ((await denied.json()) as { error: { code: string } }).error.code,
    "unauthorized",
  );
  assert.equal(f.seen.length, 2);
  assert.equal(f.gateway.snapshot().lanes[0]!.state, "idle");
  assert.equal(f.gateway.snapshot().lanes[1]!.state, "active");
  f.complete(1);
  assert.equal((await b).status, 200);
  await (await b).text();
  assert.deepEqual(
    f.gateway.snapshot().lanes.map((lane) => lane.state),
    ["idle", "idle"],
  );
});

test("token revoked during asynchronous credential lookup cannot dispatch upstream", async (t) => {
  let releaseCredential!: (key: string) => void;
  let readingCredential = false;
  const f = await fixture({
    upstreamKey: () => {
      readingCredential = true;
      return new Promise<string>((resolve) => {
        releaseCredential = resolve;
      });
    },
  });
  t.after(f.close);
  const result = f.send();
  await until(() => readingCredential);
  f.gateway.revokeToken(f.token);
  releaseCredential("fixture-upstream-key");
  assert.equal((await result).status, 401);
  await (await result).text();
  assert.equal(f.seen.length, 0);
  assert.deepEqual(
    f.gateway.snapshot().lanes.map((lane) => lane.state),
    ["idle", "idle"],
  );
});

test("queue wait has its own timeout and never consumes active generation budget", async (t) => {
  const f = await fixture({ activeTimeoutMs: 450, queueTimeoutMs: 1500 });
  t.after(f.close);
  const a = f.send();
  const b = f.send();
  await until(() => f.seen.length === 2);
  const queued = f.send();
  await until(() => f.gateway.snapshot().queued === 1);
  await delay(275);
  f.complete(0);
  f.complete(1);
  await (await a).text();
  await (await b).text();
  await until(() => f.seen.length === 3);
  await delay(275);
  f.complete(2);
  assert.equal((await queued).status, 200);
  await (await queued).text();
  assert.equal(f.gateway.snapshot().lanes[0]!.state, "idle");
  const timed = await fixture({ queueTimeoutMs: 40, activeTimeoutMs: 1000 });
  t.after(timed.close);
  const x = timed.send();
  const y = timed.send();
  await until(() => timed.seen.length === 2);
  const waiting = await timed.send();
  assert.equal(waiting.status, 504);
  assert.equal(
    ((await waiting.json()) as { error: { code: string } }).error.code,
    "queue_timeout",
  );
  assert.equal(timed.seen.length, 2);
  assert.equal(timed.gateway.snapshot().queuedBytes, 0);
  timed.complete(0);
  timed.complete(1);
  await (await x).text();
  await (await y).text();
});

test("SSE tool arguments and usage are byte-preserved, disconnect drains until real settlement", async (t) => {
  const f = await fixture();
  t.after(f.close);
  const cancel = new AbortController();
  const a = f.send({ stream: true }, cancel.signal);
  const b = f.send();
  await until(() => f.seen.length === 2);
  const stream = f.seen[0]!.response;
  stream.setHeader("content-type", "text/event-stream");
  const first =
    'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"{\\\"a\\\":"}}]}}]}\n\n';
  stream.write(first);
  const response = await a;
  const reader = response.body!.getReader();
  assert.equal(Buffer.from((await reader.read()).value!).toString(), first);
  cancel.abort();
  await delay(25);
  assert.equal(f.gateway.snapshot().lanes[0]!.state, "active");
  const queued = f.send({ user: "after-drain" });
  await until(() => f.gateway.snapshot().queued === 1);
  // This oversized incomplete observation line is discarded while transport
  // continues draining; it does not become an ever-growing response buffer.
  for (let i = 0; i < 40; i++) stream.write("x".repeat(64 * 1024));
  stream.write(
    '\n\ndata: {"usage":{"prompt_tokens":456,"completion_tokens":90}}\n\n',
  );
  await delay(40);
  assert.equal(f.seen.length, 2);
  assert.equal(f.gateway.snapshot().lanes[0]!.state, "active");
  stream.end("data: [DONE]\n\n");
  await until(() => f.seen.length === 3);
  assert.equal(f.seen[2]!.lane, 0);
  assert.equal(f.usages[0]!.promptTokens, 456);
  f.complete(1);
  f.complete(2);
  await (await b).text();
  await (await queued).text();
  assert.deepEqual(f.maximum, [1, 1]);
});

test("normal SSE preserves exact response chunks and reports real usage without accumulation", async (t) => {
  const f = await fixture();
  t.after(f.close);
  const result = f.send({
    stream: true,
    stream_options: { include_usage: true },
  });
  await until(() => f.seen.length === 1);
  const chunks = [
    'data: {"choices":[{"delta":{"tool_calls":[{"function":{"arguments":"{\\\"x\\\":1}"}}]}}]}\n\n',
    'data: {"usage":{"prompt_tokens":987,"completion_tokens":18}}\n\n',
    "data: [DONE]\n\n",
  ];
  f.seen[0]!.response.setHeader("content-type", "text/event-stream");
  for (const chunk of chunks) f.seen[0]!.response.write(chunk);
  f.seen[0]!.response.end();
  assert.equal(await (await result).text(), chunks.join(""));
  assert.equal(f.usages[0]!.promptTokens, 987);
  assert.equal(f.gateway.snapshot().lanes[0]!.state, "idle");
});

test("partial stream transport failure quarantines lane, never retries, and retains other lane", async (t) => {
  const f = await fixture();
  t.after(f.close);
  const a = f.send({ stream: true });
  await until(() => f.seen.length === 1);
  f.seen[0]!.response.setHeader("content-type", "text/event-stream");
  f.seen[0]!.response.write(
    'data: {"choices":[{"delta":{"content":"partial"}}]}\n\n',
  );
  const response = await a;
  const content = response.text().catch((error) => error as Error);
  f.seen[0]!.response.destroy();
  assert.ok((await content) instanceof Error);
  await until(() => f.gateway.snapshot().lanes[0]!.state === "quarantined");
  assert.equal(f.seen.length, 1);
  const b = f.send();
  await until(() => f.seen.length === 2);
  assert.equal(f.seen[1]!.lane, 1);
  f.complete(1);
  await (await b).text();
  assert.equal(f.gateway.snapshot().lanes[0]!.state, "quarantined");
});

test("SSE EOF without terminal marker and active timeout quarantine, no automatic reuse", async (t) => {
  const f = await fixture({ activeTimeoutMs: 65 });
  t.after(f.close);
  const a = f.send({ stream: true });
  await until(() => f.seen.length === 1);
  f.seen[0]!.response.end(
    'data: {"choices":[{"delta":{"content":"incomplete"}}]}\n\n',
  );
  await (await a).text();
  assert.equal(f.gateway.snapshot().lanes[0]!.state, "quarantined");
  const b = f.send();
  await until(() => f.seen.length === 2);
  const pending = f.send();
  await until(() => f.gateway.snapshot().queued === 1);
  const result = await b;
  assert.equal(result.status, 504);
  assert.equal(
    ((await result.json()) as { error: { code: string } }).error.code,
    "active_timeout",
  );
  assert.deepEqual(
    f.gateway.snapshot().lanes.map((lane) => lane.state),
    ["quarantined", "quarantined"],
  );
  assert.equal((await pending).status, 503);
  await (await pending).text();
  assert.equal(f.gateway.snapshot().queuedBytes, 0);
  assert.equal((await f.send()).status, 503);
  assert.equal(f.seen.length, 2);
});

test("missing upstream credential never sends request or consumes permit", async (t) => {
  const f = await fixture({
    upstreamKey: () => {
      throw new Error("fixture unavailable");
    },
  });
  t.after(f.close);
  assert.equal((await f.send()).status, 503);
  assert.equal(f.seen.length, 0);
  assert.deepEqual(
    f.gateway.snapshot().lanes.map((lane) => lane.state),
    ["idle", "idle"],
  );
});

test("durable admission records active before dispatch and recovers interrupted lanes quarantined", async (t) => {
  const ledger: Record<string, "idle" | "active" | "quarantined"> = {
    "qwen3.8-27b-gpu0": "active",
  };
  const writes: { alias: string; state: string }[] = [];
  const f = await fixture({
    initialLaneStates: { ...ledger },
    onLaneState: (alias, state) => {
      ledger[alias] = state;
      writes.push({ alias, state });
    },
  });
  t.after(f.close);
  assert.deepEqual(
    f.gateway.snapshot().lanes.map((lane) => lane.state),
    ["quarantined", "idle"],
  );
  assert.equal(ledger["qwen3.8-27b-gpu0"], "quarantined");
  const result = f.send();
  await until(() => f.seen.length === 1);
  assert.equal(f.seen[0]!.lane, 1);
  assert.equal(ledger["qwen3.8-27b"], "active");
  f.complete(0);
  await (await result).text();
  assert.equal(ledger["qwen3.8-27b"], "idle");
  assert.deepEqual(
    writes
      .filter((write) => write.alias === "qwen3.8-27b")
      .map((write) => write.state),
    ["idle", "active", "idle"],
  );
});

test("failed durable admission write prevents upstream dispatch and fails closed", async (t) => {
  const f = await fixture({
    onLaneState: (_alias, state) => {
      if (state === "active") throw new Error("fixture full disk");
    },
  });
  t.after(f.close);
  const result = await f.send();
  assert.equal(result.status, 503);
  assert.equal(
    ((await result.json()) as { error: { code: string } }).error.code,
    "lane_ledger_unavailable",
  );
  assert.equal(f.seen.length, 0);
  assert.equal(f.gateway.snapshot().lanes[0]!.state, "quarantined");
});

test("complete proxy errors remain ambiguous; definite admission rejection releases its lane", async (t) => {
  const f = await fixture();
  t.after(f.close);
  const a = f.send();
  await until(() => f.seen.length === 1);
  f.seen[0]!.response.statusCode = 502;
  f.seen[0]!.response.end('{"error":{"message":"proxy lost backend"}}');
  assert.equal((await a).status, 502);
  await (await a).text();
  assert.equal(f.gateway.snapshot().lanes[0]!.state, "quarantined");
  const b = f.send({ stream: true });
  await until(() => f.seen.length === 2);
  f.seen[1]!.response.statusCode = 429;
  f.seen[1]!.response.end('{"error":{"message":"capacity rejected"}}');
  assert.equal((await b).status, 429);
  await (await b).text();
  assert.equal(f.gateway.snapshot().lanes[1]!.state, "idle");
  assert.equal(f.seen.length, 2);
});
