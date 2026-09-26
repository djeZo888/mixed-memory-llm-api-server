import test from "node:test";
import assert from "node:assert/strict";
import { createServer, type ServerResponse } from "node:http";
import { setTimeout as delay } from "node:timers/promises";
import { readFileSync } from "node:fs";
import type { AvailabilityProvider } from "../src/service-availability.js";
import { createGateway, type LaneState } from "../src/gateway.js";
import {
  FRONTIER_MODEL,
  FRONTIER_REVISION,
  type FrontierRecord,
  type FrontierOptions,
} from "../src/frontier.js";
const revision = FRONTIER_REVISION,
  template = FRONTIER_REVISION;
async function until(fn: () => boolean) {
  for (let i = 0; i < 500; i++) {
    if (fn()) return;
    await delay(5);
  }
  throw Error("fixture timeout");
}
async function fixture(
  overrides: Partial<FrontierOptions> = {},
  initial: Record<string, LaneState> = {},
  availability?: AvailabilityProvider,
) {
  const counts: Record<string, unknown>[] = [];
  const requests: {
    url: string;
    body: any;
    response: ServerResponse;
    auth: string | undefined;
  }[] = [];
  const records = new Map<string, FrontierRecord>();
  const states = { ...initial };
  let holdCounts = false;
  const pendingCounts: ServerResponse[] = [];
  let countResponse: any = {
    count: 100,
    context_limit: 128000,
    tokenizer_revision: revision,
    template_revision: template,
  };
  const backend = createServer(async (req, res) => {
    const chunks = [];
    for await (const c of req) chunks.push(c);
    const body = JSON.parse(Buffer.concat(chunks).toString());
    if (req.url === "/frontier/v1/tokenize") {
      counts.push(body);
      if (holdCounts) {
        pendingCounts.push(res);
        return;
      }
      res.setHeader("content-type", "application/json");
      res.end(JSON.stringify(countResponse));
      return;
    }
    requests.push({
      url: req.url!,
      body,
      response: res,
      auth: req.headers.authorization,
    });
  });
  await new Promise<void>((r) => backend.listen(0, "127.0.0.1", r));
  const origin = `http://127.0.0.1:${(backend.address() as any).port}`;
  const gateway = createGateway({
    upstreamKey: "qwen-host-fixture",
    availability:
      availability ?? (() => ({ state: "available", dispatch: "allow" })),
    upstreams: [
      { url: origin + "/q0/v1", alias: "qwen3.8-27b-gpu0" },
      { url: origin + "/q1/v1", alias: "qwen3.8-27b" },
    ],
    initialLaneStates: states,
    onLaneState: (a, s) => {
      states[a] = s;
    },
    frontier: {
      contextWindow: 128000,
      tokenizerRevision: revision,
      templateRevision: template,
      upstreamKey: "frontier-host-fixture",
      fixtureUrl: origin + "/frontier/v1",
      onRequestState: (r) => records.set(r.id, r),
      ...overrides,
    },
  });
  const url = await gateway.app.listen({ host: "127.0.0.1", port: 0 });
  const token = gateway.issueToken("owned-session");
  const send = (body: any = {}, signal?: AbortSignal, qwen = false) =>
    fetch(url + (qwen ? "/v1" : "/frontier/v1") + "/chat/completions", {
      method: "POST",
      headers: {
        authorization: `Bearer ${token}`,
        "content-type": "application/json",
      },
      body: JSON.stringify({
        model: qwen ? "qwen3.8-27b" : FRONTIER_MODEL,
        messages: [],
        ...body,
      }),
      signal,
    });
  const complete = (i: number, status = 200) => {
    requests[i]!.response.writeHead(status, {
      "content-type": "application/json",
    });
    requests[i]!.response.end(
      JSON.stringify({
        choices: [{ message: { content: "fixture" }, finish_reason: "stop" }],
        usage: { count: 100, completion_tokens: 10 },
      }),
    );
  };
  const close = async () => {
    await gateway.close();
    backend.closeAllConnections();
    await new Promise<void>((r) => backend.close(() => r()));
  };
  return {
    gateway,
    url,
    token,
    send,
    requests,
    counts,
    records,
    states,
    complete,
    close,
    holdCounts: (value: boolean) => {
      holdCounts = value;
    },
    releaseCounts: () => {
      for (const res of pendingCounts.splice(0))
        res.end(JSON.stringify(countResponse));
    },
    setCount: (v: any) => {
      countResponse = v;
    },
    countResponse,
  };
}
test("exact rendered-token contract, fixed identity/high thinking, unchanged reserved output and protected key", async (t) => {
  const f = await fixture();
  t.after(f.close);
  f.setCount({ ...f.countResponse, count: 127988 });
  const body = {
    messages: [{ role: "user", content: "中文 résumé <|tool|>" }],
    tools: [
      {
        type: "function",
        function: { name: "read", parameters: { type: "object" } },
      },
    ],
    max_tokens: 10,
  };
  const p = f.send(body);
  await until(() => f.requests.length === 1);
  assert.deepEqual(f.counts[0]!.messages, body.messages);
  assert.deepEqual(f.counts[0]!.tools, body.tools);
  assert.equal(f.counts[0]!.add_generation_prompt, undefined);
  assert.deepEqual(f.counts[0], f.requests[0]!.body);
  assert.equal(f.requests[0]!.body.max_tokens, 10);
  assert.equal(f.requests[0]!.body.reasoning_effort, "high");
  assert.deepEqual(f.requests[0]!.body.chat_template_kwargs, {
    clear_thinking: true,
  });
  assert.equal(f.requests[0]!.auth, "Bearer frontier-host-fixture");
  f.complete(0);
  assert.equal((await p).status, 200);
  await until(() => f.gateway.frontierSnapshot().state === "idle");
  assert.equal([...f.records.values()][0]!.state, "settled");
  assert.equal([...f.records.values()][0]!.promptTokens, 127988);
});
test("independent frontier queue never consumes parent Qwen lanes; per-HTTP release and queue cap eight", async (t) => {
  const f = await fixture();
  t.after(f.close);
  const parent = f.send({}, undefined, true);
  await until(() => f.requests.length === 1);
  f.complete(0);
  await parent;
  const first = f.send();
  await until(() => f.requests.length === 2);
  const cancellations = Array.from({ length: 8 }, () => new AbortController());
  const pending = cancellations.map((c) =>
    f.send({}, c.signal).catch(() => null),
  );
  await until(() => f.gateway.frontierSnapshot().queued === 8);
  assert.equal((await f.send()).status, 429);
  const qwen = f.send({}, undefined, true);
  await until(() => f.requests.length === 3);
  assert.match(f.requests[2]!.url, /q[01]/);
  f.complete(2);
  assert.equal((await qwen).status, 200);
  cancellations.forEach((c) => c.abort());
  await Promise.all(pending);
  await until(() => f.gateway.frontierSnapshot().queued === 0);
  assert.equal(f.gateway.frontierSnapshot().state, "active");
  f.complete(1);
  await first;
  await until(() => f.gateway.frontierSnapshot().state === "idle");
  const next = f.send();
  await until(() => f.requests.length === 4);
  f.complete(3);
  assert.equal((await next).status, 200);
});
test("dispatched disconnect drains; ambiguous response quarantines and reconnect never replays", async (t) => {
  const f = await fixture();
  t.after(f.close);
  const cancel = new AbortController();
  const p = f.send({}, cancel.signal).catch(() => null);
  await until(() => f.requests.length === 1);
  cancel.abort();
  await p;
  await delay(20);
  assert.equal(f.gateway.frontierSnapshot().state, "active");
  f.complete(0, 500);
  await until(() => f.gateway.frontierSnapshot().state === "quarantined");
  assert.equal((await f.send()).status, 503);
  assert.equal(f.requests.length, 1);
  const qwen = f.send({}, undefined, true);
  await until(() => f.requests.length === 2);
  f.complete(1);
  assert.equal((await qwen).status, 200);
  const recovered = await fixture({}, f.states);
  t.after(recovered.close);
  assert.equal(recovered.gateway.frontierSnapshot().state, "quarantined");
  assert.equal((await recovered.send()).status, 503);
  assert.equal(recovered.requests.length, 0);
});
test("tokenizer identity/count/endpoint errors fail isolated frontier with zero inference", async (t) => {
  const f = await fixture();
  t.after(f.close);
  for (const change of [
    { tokenizer_revision: "wrong" },
    { template_revision: "wrong" },
    { context_limit: 480000 },
    { count: -1 },
    { count: 1.5 },
    { count: 128000 },
  ]) {
    f.setCount({ ...f.countResponse, ...change });
    assert([413, 503].includes((await f.send()).status));
    assert.equal(f.requests.length, 0);
    assert.equal(f.gateway.frontierSnapshot().state, "idle");
  }
  const qwen = f.send({}, undefined, true);
  await until(() => f.requests.length === 1);
  f.complete(0);
  assert.equal((await qwen).status, 200);
});
test("body cannot inject endpoint/model/template, errors reserve no inference; missing frontier is isolated", async (t) => {
  const f = await fixture();
  t.after(f.close);
  for (const body of [
    { model: "qwen3.8-27b" },
    { base_url: "http://bad" },
    { chat_template_kwargs: { clear_thinking: false } },
    { max_tokens: 0 },
    { max_tokens: 2, max_completion_tokens: 3 },
  ])
    assert.equal((await f.send(body)).status, 400);
  assert.equal(f.counts.length, 0);
  assert.equal(f.requests.length, 0);
  const g = createGateway({ upstreamKey: "fixture" });
  t.after(() => g.close());
  const token = g.issueToken("fixture");
  const r = await g.app.inject({
    method: "POST",
    url: "/frontier/v1/chat/completions",
    headers: { authorization: `Bearer ${token}` },
    payload: { model: FRONTIER_MODEL, messages: [] },
  });
  assert.equal(r.statusCode, 503);
  assert.equal(g.snapshot().lanes.length, 2);
  assert.equal(g.frontierSnapshot().state, "unavailable");
});
test("unqualified tokenizer and unavailable protected key never start inference or affect Qwen", async (t) => {
  for (const options of [
    { tokenizerRevision: "" },
    {
      upstreamKey: async () => {
        throw Error("missing credential");
      },
    },
  ]) {
    const f = await fixture(options);
    t.after(f.close);
    assert.equal((await f.send()).status, 503);
    assert.equal(f.requests.length, 0);
    assert.equal(f.gateway.frontierSnapshot().state, "idle");
  }
});

test("production has no 16K cap; exact input plus complete output reservation at limit +/-1", async (t) => {
  const f = await fixture({ contextWindow: 480000 });
  t.after(f.close);
  for (const count of [16001, 479998 - 65536 - 1, 479998 - 65536]) {
    f.setCount({ ...f.countResponse, context_limit: 480000, count });
    const index = f.requests.length;
    const p = f.send({ max_tokens: 999999 });
    await until(() => f.requests.length === index + 1);
    assert.equal(f.requests[index]!.body.max_tokens, 65536);
    assert.deepEqual(f.counts.at(-1), f.requests[index]!.body);
    f.complete(index);
    assert.equal((await p).status, 200);
  }
  f.setCount({
    ...f.countResponse,
    context_limit: 480000,
    count: 479998 - 65536 + 1,
  });
  assert.equal((await f.send()).status, 413);
  assert.equal(f.requests.length, 3);
  for (const count of [479992, 479993]) {
    f.setCount({ ...f.countResponse, context_limit: 480000, count });
    const index = f.requests.length,
      p = f.send({ max_tokens: 1 });
    await until(() => f.requests.length === index + 1);
    f.complete(index);
    assert.equal((await p).status, 200);
  }
  f.setCount({ ...f.countResponse, context_limit: 480000, count: 479994 });
  assert.equal((await f.send({ max_tokens: 1 })).status, 413);
  assert.equal(f.requests.length, 5);
});

test("bounded queue expiry and session-token revoke cancel queued ownership immediately", async (t) => {
  const f = await fixture({ fixtureQueueTimeoutMs: 40 });
  t.after(f.close);
  const first = f.send();
  await until(() => f.requests.length === 1);
  assert.equal((await f.send()).status, 504);
  assert.equal(f.gateway.frontierSnapshot().queued, 0);
  const queued = f.send();
  await until(() => f.gateway.frontierSnapshot().queued === 1);
  f.gateway.revokeToken(f.token);
  assert.equal((await queued).status, 499);
  assert.equal(f.gateway.frontierSnapshot().queued, 0);
  assert.equal(f.gateway.frontierSnapshot().state, "active");
  f.complete(0);
  await first;
  await until(() => f.gateway.frontierSnapshot().state === "idle");
  const values = [...f.records.values()];
  assert(values.some((r) => r.state === "rejected"));
  assert(values.some((r) => r.state === "cancelled"));
  assert(values.some((r) => r.state === "settled"));
});

test("count endpoint timeout, connection failure, malformed and oversized responses cannot start inference", async (t) => {
  const f = await fixture({ countTimeoutMs: 25 });
  t.after(f.close);
  f.holdCounts(true);
  assert.equal((await f.send()).status, 503);
  f.holdCounts(false);
  for (const value of [
    undefined,
    { ...f.countResponse, unexpected: "x".repeat(20000) },
  ]) {
    f.setCount(value);
    assert.equal((await f.send()).status, 503);
  }
  assert.equal(f.requests.length, 0);
  assert.equal(f.gateway.frontierSnapshot().state, "idle");
  const missing = await fixture({ fixtureUrl: "http://127.0.0.1:1/v1" });
  t.after(missing.close);
  assert.equal((await missing.send()).status, 503);
  assert.equal(missing.requests.length, 0);
  const qwen = missing.send({}, undefined, true);
  await until(() => missing.requests.length === 1);
  missing.complete(0);
  assert.equal((await qwen).status, 200);
});

test("Flash rejects malformed or multimodal messages before count and inference without echoing input", async (t) => {
  const f = await fixture();
  t.after(f.close);
  for (const messages of [
    [null],
    [{ role: { toString: null }, content: "private-fixture-content" }],
    ["private-fixture-content"],
    [{ role: "user", content: { text: "private-fixture-content" } }],
    ...[
      "image_url",
      "image",
      "input_image",
      "video_url",
      "video",
      "audio",
      "input_audio",
      "file",
    ].map((type) => [
      {
        role: "user",
        content: [{ type, [type]: { url: "private-fixture-content" } }],
      },
    ]),
    [
      {
        role: "user",
        content: [
          { type: "text", text: { nested: "private-fixture-content" } },
        ],
      },
    ],
    [
      {
        role: "user",
        content: [[{ type: "text", text: "private-fixture-content" }]],
      },
    ],
    [{ role: "user", content: "ok", images: ["private-fixture-content"] }],
    [
      {
        role: "assistant",
        content: null,
        audio: { data: "private-fixture-content" },
      },
    ],
    [{ role: "assistant", content: null, tool_calls: [null] }],
  ]) {
    const response = await f.send({ messages });
    assert.equal(response.status, 400);
    assert(!(await response.text()).includes("private-fixture-content"));
  }
  assert.equal(f.counts.length, 0);
  assert.equal(f.requests.length, 0);
  const p = f.send({
    messages: [
      { role: "user", content: [{ type: "text", text: "OCR or PDF text" }] },
    ],
  });
  await until(() => f.requests.length === 1);
  f.complete(0);
  assert.equal((await p).status, 200);
});
test("pure-text user and tool arrays remain identical for count and inference", async t => {
  const f=await fixture(); t.after(f.close);
  const messages=[{role:"user",content:[{type:"text",text:"one"},{type:"text",text:" two"}]},
    {role:"assistant",content:null,tool_calls:[{id:"call_text",type:"function",function:{name:"read",arguments:"{}"}}]},
    {role:"tool",tool_call_id:"call_text",content:[{type:"text",text:"PDF"},{type:"text",text:" text"}]}];
  const p=f.send({messages}); await until(()=>f.requests.length===1);
  assert.deepEqual(f.counts[0]!.messages,messages); assert.deepEqual(f.requests[0]!.body,f.counts[0]);
  f.complete(0); assert.equal((await p).status,200);
});
test("actual pinned offline tokenizer responses satisfy the frozen gateway contract", async (t) => {
  const fixtures = JSON.parse(
    readFileSync(
      new URL("./fixtures/h008/tokenizer-fixtures.json", import.meta.url),
      "utf8",
    ),
  );
  const f = await fixture({ contextWindow: 480000 });
  t.after(f.close);
  for (const sample of fixtures.fixtures) {
    f.setCount(sample.response);
    const index = f.requests.length,
      p = f.send(sample.request);
    await until(() => f.requests.length === index + 1);
    assert.deepEqual(f.counts.at(-1), f.requests[index]!.body);
    f.complete(index);
    assert.equal((await p).status, 200);
    assert.equal(
      [...f.records.values()].at(-1)!.promptTokens,
      sample.response.count,
    );
  }
});
test("frontier availability is independent of durable idle and wakes queued admission", async (t) => {
  let ready = false;
  const f = await fixture({}, {}, (alias) => ({
    state: alias === FRONTIER_MODEL && !ready ? "unknown" : "available",
  }));
  t.after(f.close);
  const p = f.send();
  await until(() => f.gateway.frontierSnapshot().queued === 1);
  assert.equal(f.gateway.frontierSnapshot().state, "idle");
  assert.equal(f.gateway.frontierSnapshot().availability.state, "unknown");
  assert.equal(f.counts.length, 0);
  const q = f.send({}, undefined, true);
  await until(() => f.requests.length === 1);
  f.complete(0);
  assert.equal((await q).status, 200);
  ready = true;
  f.gateway.notifyAvailabilityChanged();
  await until(() => f.requests.length === 2);
  f.complete(1);
  assert.equal((await p).status, 200);
});
test("service disappearance while exact count is outstanding sends zero generation bytes", async (t) => {
  let ready = true;
  const f = await fixture({}, {}, (alias) => ({
    state: alias === FRONTIER_MODEL && !ready ? "unknown" : "available",
  }));
  t.after(f.close);
  f.holdCounts(true);
  const p = f.send();
  await until(() => f.counts.length === 1);
  ready = false;
  f.gateway.notifyAvailabilityChanged();
  f.releaseCounts();
  assert.equal((await p).status, 503);
  assert.equal(f.requests.length, 0);
  assert.equal(f.gateway.frontierSnapshot().state, "idle");
  assert.equal([...f.records.values()][0]!.state, "rejected");
});
test("only exact confirmed frontier-owner alias clears frontier quarantine; passive readiness never does", async (t) => {
  const f = await fixture({}, { [FRONTIER_MODEL]: "quarantined" });
  t.after(f.close);
  f.gateway.notifyAvailabilityChanged();
  f.gateway.reconcileAfterOwnerSettlement([
    "qwen3.8-27b",
    "qwen3.8-27b-gpu0",
    "image",
    "frontier",
    "harness",
  ]);
  assert.equal(f.gateway.frontierSnapshot().state, "quarantined");
  assert.equal(f.gateway.reconcileAfterOwnerSettlement([FRONTIER_MODEL]), true);
  assert.equal(f.gateway.frontierSnapshot().state, "idle");
  const p = f.send();
  await until(() => f.requests.length === 1);
  f.complete(0);
  assert.equal((await p).status, 200);
});

test("unconfigured availability observer cannot dispatch Flash from an idle lane", async (t) => {
  const gateway = createGateway({
    upstreamKey: "synthetic-qwen-key",
    frontier: {
      contextWindow: 480000,
      tokenizerRevision: revision,
      templateRevision: template,
      fixtureUrl: "http://127.0.0.1:1/v1",
      fixtureQueueTimeoutMs: 20,
      upstreamKey: "synthetic-flash-key",
      onRequestState: () => {},
    },
  });
  t.after(() => gateway.close());
  const token = gateway.issueToken("synthetic-session");
  assert.equal(gateway.frontierSnapshot().state, "idle");
  assert.equal(gateway.frontierSnapshot().availability.dispatch, "hold");
  const response = await gateway.app.inject({
    method: "POST",
    url: "/frontier/v1/chat/completions",
    headers: { authorization: `Bearer ${token}` },
    payload: { model: FRONTIER_MODEL, messages: [] },
  });
  assert.equal(response.statusCode, 504);
});
