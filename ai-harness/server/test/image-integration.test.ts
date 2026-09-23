import assert from "node:assert/strict";
import test, { type TestContext } from "node:test";
import { mkdtemp, readFile, realpath, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { createServer, type ServerResponse } from "node:http";
import { Readable } from "node:stream";
import sharp from "sharp";
import { Store } from "../src/store.js";
import { createApp } from "../src/app.js";
import { createGateway } from "../src/gateway.js";
import { ImageUpstream } from "../src/image-upstream.js";
import type { EngineOptions } from "../src/contracts.js";
import type { ImageJob } from "../src/image-contracts.js";
const delay = (ms = 5) => new Promise((r) => setTimeout(r, ms));
async function until(f: () => boolean) {
  const end = Date.now() + 4000;
  while (!f()) {
    if (Date.now() >= end) throw new Error("Condition timed out");
    await delay();
  }
}
const png = (width = 64, height = 64) =>
  sharp({ create: { width, height, channels: 3, background: "#728344" } })
    .png()
    .toBuffer();
async function fixture(t: TestContext) {
  const dir = await realpath(
    await mkdtemp(path.join(tmpdir(), "h003-integration-")),
  );
  const requests: {
    response: ServerResponse;
    data: Record<string, unknown>;
  }[] = [];
  let busy = false;
  const capabilities = {
    model: "qwen-image-2.1",
    profiles: [
      {
        operation: "generation",
        references: 0,
        size: "64x64",
        transparent: false,
        evidence_sha256: "a".repeat(64),
        native_size: "64x64",
        crop_bottom: 0,
      },
      {
        operation: "edit",
        references: 1,
        size: "64x64",
        transparent: false,
        evidence_sha256: "b".repeat(64),
        native_size: "64x64",
        crop_bottom: 0,
      },
    ],
    fixture: true,
  };
  const upstream = createServer(async (req, res) => {
    assert.equal(req.headers.authorization, "Bearer offline-secret");
    if (req.url === "/v1/chat/completions") {
      req.resume();
      res.setHeader("content-type", "application/json");
      return res.end(
        JSON.stringify({
          choices: [
            {
              message: {
                role: "assistant",
                content: "Text answered during image work",
              },
            },
          ],
          usage: { prompt_tokens: 1, completion_tokens: 1 },
        }),
      );
    }
    if (req.url === "/health/ready")
      return res.end(JSON.stringify({ ready: true, busy, admitting: !busy }));
    if (req.url === "/v1/image-capabilities")
      return res.end(JSON.stringify(capabilities));
    const chunks = [];
    for await (const chunk of req) chunks.push(chunk);
    busy = true;
    requests.push({
      response: res,
      data: req.url?.endsWith("generations")
        ? JSON.parse(Buffer.concat(chunks).toString())
        : {},
    });
  });
  await new Promise<void>((r) => upstream.listen(0, "127.0.0.1", r));
  const tokens = new Map<string, string>();
  const turns: {
    options: EngineOptions;
    text: string;
    attachments: unknown[];
    finish(): void;
  }[] = [];
  let gateway: ReturnType<typeof createGateway>;
  const application = await createApp({
    dataDir: dir,
    launcher: "/offline/fake",
    gatewayUrl: "http://127.0.0.1:1/v1",
    allowedOrigins: ["http://localhost"],
    issueToken: (id) => {
      const token = gateway.issueToken(id);
      tokens.set(id, token);
      return token;
    },
    revokeToken: (token) => gateway.revokeToken(token),
    approvalProxyKey: "fixture-proxy-capability",
    imageBackend: new ImageUpstream({
      key: "offline-secret",
      fixtureOrigin: `http://127.0.0.1:${(upstream.address() as { port: number }).port}`,
    }),
    engineFactory: (options) => {
      let settle = () => {};
      return {
        async start() {},
        async prompt(text, attachments = []) {
          await new Promise<void>((resolve) => {
            settle = resolve;
            turns.push({
              options,
              text,
              attachments,
              finish() {
                options.onUpdate({
                  type: "text",
                  text: "Final fixture reply",
                  nativeMessageId: "reply",
                  channel: "final",
                });
                options.onUpdate({
                  type: "phase",
                  nativeMessageId: "reply",
                  channel: "final",
                  streamState: "completed",
                });
                resolve();
              },
            });
          });
        },
        async cancel() {
          settle();
        },
        async close() {
          settle();
        },
      };
    },
  });
  // Text requests use the same local fixture listener, never production.
  gateway = createGateway({
    upstreamKey: "offline-secret",
    images: application.images,
    upstreams: [
      {
        url: `http://127.0.0.1:${(upstream.address() as { port: number }).port}/v1`,
        alias: "qwen3.8-27b-gpu0",
      },
      {
        url: `http://127.0.0.1:${(upstream.address() as { port: number }).port}/v1`,
        alias: "qwen3.8-27b",
      },
    ],
  });
  const session = await application.broker.createSession();
  const runId = application.broker.enqueue(session.id, "message", "make image");
  await until(() => turns.length === 1);
  t.after(async () => {
    await gateway.close();
    await application.app.close();
    upstream.closeAllConnections();
    await new Promise<void>((r) => upstream.close(() => r()));
    await rm(dir, { recursive: true, force: true });
  });
  const internal = (
    method: "GET" | "POST",
    url: string,
    payload?: unknown,
    token = tokens.get(session.id),
  ) =>
    gateway.app.inject({
      method,
      url,
      headers: { authorization: `Bearer ${token}` },
      ...(payload ? { payload } : {}),
    });
  const browser = (
    method: "GET" | "POST" | "DELETE",
    url: string,
    payload?: unknown,
  ) =>
    application.app.inject({
      method,
      url,
      headers: { host: "localhost", origin: "http://localhost" },
      ...(payload ? { payload } : {}),
    });
  async function complete(index = requests.length - 1) {
    busy = false;
    requests[index].response.end(
      JSON.stringify({
        created: 1,
        data: [{ b64_json: (await png()).toString("base64") }],
      }),
    );
  }
  return {
    ...application,
    dir,
    gateway,
    session,
    runId,
    tokens,
    turns,
    requests,
    internal,
    browser,
    capabilities,
    complete,
  };
}

test("gateway token/session binding, browser origin enforcement, exact capability pass-through and no MCP approval", async (t) => {
  const f = await fixture(t);
  assert.equal(
    (await f.gateway.app.inject("/v1/image-capabilities")).statusCode,
    401,
  );
  assert.equal(
    (await f.internal("GET", "/v1/image-capabilities", undefined, "wrong"))
      .statusCode,
    401,
  );
  const cap = await f.internal("GET", "/v1/image-capabilities");
  assert.deepEqual(cap.json(), f.capabilities);
  assert.deepEqual(
    (await f.browser("GET", "/api/image-capabilities")).json(),
    f.capabilities,
  );
  const b = {
    requestId: "one",
    operation: "generation",
    prompt: "fixture",
    size: "64x64",
  };
  for (const invalid of [
    { ...b, approved: true },
    { ...b, sessionId: f.session.id },
    { ...b, runId: f.runId },
  ])
    assert.equal(
      (await f.internal("POST", "/v1/image-jobs", invalid)).statusCode,
      400,
    );
  const response = await f.internal("POST", "/v1/image-jobs", b);
  assert.equal(response.statusCode, 200);
  const job = response.json().job as ImageJob;
  assert.equal(job.runId, f.runId);
  await until(() => f.requests.length === 1);
  const other = await f.broker.createSession(),
    otherToken = f.gateway.issueToken(other.id);
  for (const [method, suffix, payload] of [
    ["GET", "", undefined],
    ["POST", "/cancel", {}],
  ] as const)
    assert.equal(
      (
        await f.internal(
          method,
          `/v1/image-jobs/${job.id}${suffix}`,
          payload,
          otherToken,
        )
      ).statusCode,
      404,
    );
  assert.equal(
    (
      await f.internal("POST", `/v1/image-jobs/${job.id}/approval`, {
        decision: "approve",
      })
    ).statusCode,
    404,
  );
  const cross = await f.app.inject({
    method: "POST",
    url: `/api/sessions/${f.session.id}/image-jobs/${job.id}/cancel`,
    headers: { host: "localhost", origin: "http://evil.test" },
    payload: {},
  });
  assert.equal(cross.statusCode, 403);
  assert.deepEqual(
    f.gateway.snapshot().lanes.map((l) => l.state),
    ["idle", "idle"],
  );
  const text = await f.internal("POST", "/v1/chat/completions", {
    model: "qwen3.8-27b",
    messages: [{ role: "user", content: "text while image is active" }],
  });
  assert.equal(text.statusCode, 200);
  assert.match(text.body, /Text answered during image work/);
  assert.equal(f.images!.snapshot().lane, "active");
  await f.complete();
  await until(() => f.images!.get(f.session.id, job.id).state === "completed");
  const internalJob = (
    await f.internal("GET", `/v1/image-jobs/${job.id}`)
  ).json().job;
  assert.match(internalJob.outputPath, /^image-[a-f0-9-]+\.png$/);
  const browserJob = (
    await f.browser("GET", `/api/sessions/${f.session.id}/image-jobs`)
  ).json().jobs[0];
  assert.ok(!("outputPath" in browserJob));
  assert.ok(!JSON.stringify(browserJob).includes("offline-secret"));
  assert.ok(!JSON.stringify(browserJob).includes("b64_json"));
});

test("normal text turn end preserves image job; late artifact belongs to original final reply and next edit receives owned copy", async (t) => {
  const f = await fixture(t);
  const submitted = await f.internal("POST", "/v1/image-jobs", {
    requestId: "late",
    operation: "generation",
    prompt: "fixture",
    size: "64x64",
    seed: 42,
  });
  const job = submitted.json().job as ImageJob;
  await until(() => f.requests.length === 1);
  f.turns[0].finish();
  await f.broker.idle();
  assert.equal(f.images!.get(f.session.id, job.id).state, "running");
  await f.complete();
  await until(() => f.images!.get(f.session.id, job.id).state === "completed");
  const completed = f.images!.get(f.session.id, job.id),
    artifact = f.store.file(completed.artifactId!);
  assert.equal(artifact.runId, f.runId);
  assert.equal(artifact.image?.width, 64);
  assert.equal(artifact.image?.height, 64);
  assert.equal(artifact.image?.actualSize, "64x64");
  const rawMetadata = JSON.parse(
    String(
      f.store.db
        .prepare("SELECT data FROM h003_image_file_meta WHERE file_id=?")
        .get(artifact.id)!.data,
    ),
  );
  assert.equal(rawMetadata.width, 64);
  assert.equal(rawMetadata.height, 64);
  // Existing actualSize-only rows still hydrate numeric dimensions on refresh.
  delete rawMetadata.width;
  delete rawMetadata.height;
  f.store.db
    .prepare("UPDATE h003_image_file_meta SET data=? WHERE file_id=?")
    .run(JSON.stringify(rawMetadata), artifact.id);
  assert.equal(f.store.file(artifact.id).image?.width, 64);
  assert.equal(f.store.file(artifact.id).image?.height, 64);
  assert.equal(artifact.messageId, f.store.runSnapshot(f.runId).finalMessageId);
  assert.ok(artifact.messageId);
  assert.equal(
    (await f.browser("GET", `/api/artifacts/${artifact.id}/download`))
      .statusCode,
    200,
  );
  const followup = await f.browser(
    "POST",
    `/api/sessions/${f.session.id}/messages`,
    { text: "edit this", imageReferences: [artifact.id], attachmentIds: [] },
  );
  assert.equal(followup.statusCode, 202);
  const followupRun = followup.json().runId;
  const selectedMessage = f.store
    .messages(f.session.id)
    .find(
      (message) => message.role === "user" && message.runId === followupRun,
    )!;
  assert.deepEqual(selectedMessage.imageReferences, [artifact.id]);
  assert.equal(selectedMessage.attachmentIds, undefined);
  const emitted = f.store
    .allEvents(f.session.id)
    .find((event) => event.type === "message" && event.runId === followupRun)!;
  assert.deepEqual(
    (emitted.data.message as { imageReferences: string[] }).imageReferences,
    [artifact.id],
  );
  const refreshed = (
    await f.browser("GET", `/api/sessions/${f.session.id}`)
  ).json();
  assert.deepEqual(
    refreshed.messages.find(
      (message: { id: string }) => message.id === selectedMessage.id,
    ).imageReferences,
    [artifact.id],
  );
  assert.equal(
    refreshed.artifacts.find((file: { id: string }) => file.id === artifact.id)
      .image.width,
    64,
  );
  await until(() => f.turns.length === 2);
  assert.match(f.turns[1].text, /\.image-references\//);
  assert.equal(f.turns[1].attachments.length, 0);
  const relative = JSON.parse(
    f.turns[1].text
      .split("\n")
      .find((line) => line.startsWith('".image-references/'))!,
  );
  const session = f.store.getSession(f.session.id);
  assert.deepEqual(
    await readFile(path.join(f.files.workspace(session.workspaceId), relative)),
    await readFile(path.join(f.dir, "artifacts", artifact.path)),
  );
  f.turns[1].finish();
  await f.broker.idle();
  assert.equal(f.store.files(f.session.id, "artifact").length, 1);
  assert.equal(f.store.file(artifact.id).runId, f.runId);
  const reopenedPath = path.join(f.dir, "projection-refresh.sqlite");
  f.store.db.prepare("VACUUM INTO ?").run(reopenedPath);
  const reopened = new Store(reopenedPath);
  try {
    assert.deepEqual(reopened.message(selectedMessage.id).imageReferences, [
      artifact.id,
    ]);
    assert.equal(reopened.file(artifact.id).image?.height, 64);
    assert.equal(
      reopened
        .messages(f.session.id)
        .filter((message) => message.role === "assistant")
        .some((message) => message.imageReferences),
      false,
    );
  } finally {
    reopened.close();
  }
  const other = await f.broker.createSession();
  assert.equal(
    (
      await f.browser("POST", `/api/sessions/${other.id}/messages`, {
        text: "edit",
        imageReferences: [artifact.id],
      })
    ).statusCode,
    400,
  );
  const alien = f.store.saveFile({
    id: "foreign-image",
    sessionId: other.id,
    kind: "artifact",
    path: "foreign-image",
    name: "foreign.png",
    mimeType: "image/png",
    size: 1,
  });
  f.store.db
    .prepare("UPDATE h003_run_image_refs SET data=? WHERE run_id=?")
    .run(JSON.stringify([artifact.id, alien.id]), followupRun);
  assert.deepEqual(f.store.message(selectedMessage.id).imageReferences, [
    artifact.id,
  ]);
});

test("approval after text completion binds original run; Stop while idle removes approval and Delete drains active output", async (t) => {
  const f = await fixture(t),
    upload = await f.files.upload(
      f.session.id,
      "r.png",
      "image/png",
      Readable.from(await png(120, 60)),
    );
  const submit = async (requestId: string) =>
    (
      await f.internal("POST", "/v1/image-jobs", {
        requestId,
        operation: "edit",
        prompt: "fixture",
        references: [{ fileId: upload.id }],
      })
    ).json().job as ImageJob;
  const approved = await submit("approve"),
    stopped = await submit("stop");
  f.turns[0].finish();
  await f.broker.idle();
  const tokenResponse = await f.app.inject({
    url: `/api/sessions/${f.session.id}/image-jobs/${approved.id}/approval-token`,
    headers: {
      host: "localhost",
      "x-ai-harness-approval-proxy": "fixture-proxy-capability",
    },
  });
  assert.equal(tokenResponse.statusCode, 200);
  const approvedResponse = await f.browser(
    "POST",
    `/api/sessions/${f.session.id}/image-jobs/${approved.id}/approval`,
    { decision: "approve", approvalToken: tokenResponse.json().approvalToken },
  );
  assert.equal(approvedResponse.statusCode, 200);
  assert.equal(approvedResponse.json().job.runId, f.runId);
  await until(() => f.requests.length === 1);
  await f.browser("POST", `/api/sessions/${f.session.id}/cancel`, {});
  assert.equal(f.images!.get(f.session.id, stopped.id).state, "cancelled");
  assert.equal(f.images!.get(f.session.id, approved.id).cancelRequested, true);
  assert.equal(f.images!.snapshot().lane, "active");
  assert.equal(
    (await f.browser("DELETE", `/api/sessions/${f.session.id}`)).statusCode,
    200,
  );
  await f.complete();
  await until(() => f.images!.snapshot().lane === "idle");
  const record = JSON.parse(
    String(
      f.store.db
        .prepare("SELECT data FROM h003_image_jobs WHERE id=?")
        .get(approved.id)!.data,
    ),
  );
  assert.equal(record.job.state, "cancelled");
  assert.equal(f.store.file(record.job.artifactId).messageId, null);
  assert.equal(
    (await f.browser("GET", `/api/sessions/${f.session.id}/image-jobs`))
      .statusCode,
    404,
  );
});

test("approval token route refuses direct requests/forged forwarding/bearer and accepts only protected proxy capability", async (t) => {
  const f = await fixture(t),
    file = await f.files.upload(
      f.session.id,
      "r.png",
      "image/png",
      Readable.from(await png(120, 60)),
    );
  const submitted = await f.internal("POST", "/v1/image-jobs", {
    requestId: "secure",
    operation: "edit",
    prompt: "fixture",
    references: [{ fileId: file.id }],
  });
  const job = submitted.json().job as ImageJob,
    url = `/api/sessions/${f.session.id}/image-jobs/${job.id}/approval-token`;
  for (const extra of [
    {},
    { "x-ai-harness-approval-proxy": "forged" },
    { "x-forwarded-for": "10.156.100.9", "x-real-ip": "10.156.100.9" },
    { authorization: `Bearer ${f.tokens.get(f.session.id)}` },
  ]) {
    const denied = await f.app.inject({
      url,
      headers: { host: "localhost", origin: "http://localhost", ...extra },
    });
    assert.equal(denied.statusCode, 403);
  }
  const missing = await f.browser(
    "POST",
    url.replace("approval-token", "approval"),
    { decision: "approve" },
  );
  assert.equal(missing.statusCode, 403);
  const token = await f.app.inject({
    url,
    headers: {
      host: "localhost",
      "x-ai-harness-approval-proxy": "fixture-proxy-capability",
    },
  });
  assert.equal(token.statusCode, 200);
  const { approvalToken } = token.json();
  assert.match(approvalToken, /^[a-f0-9]{64}$/);
  const rejected = await f.browser(
    "POST",
    url.replace("approval-token", "approval"),
    { decision: "reject", approvalToken },
  );
  assert.equal(rejected.statusCode, 200);
  assert.equal(rejected.json().job.state, "cancelled");
  assert.ok(
    !JSON.stringify(f.images!.list(f.session.id)).includes(approvalToken),
  );
  assert.equal(f.requests.length, 0);
  const nginx = await readFile(
    new URL("../../deploy/nginx/ai-harness.conf", import.meta.url),
    "utf8",
  );
  const [specific, generic] = nginx.split("    location / {");
  assert.match(specific, /deny 127\.0\.0\.0\/8;/);
  assert.match(specific, /deny 10\.156\.100\.61;/);
  assert.match(specific, /allow all;/);
  assert.ok(!specific.includes("allow 10.156.100.0/24"));
  assert.match(specific, /deny 10\.156\.100\.61;[\s\S]*allow all;/);
  assert.match(
    specific,
    /include \/etc\/ai-harness\/image-approval-proxy.conf;/,
  );
  assert.match(generic, /proxy_set_header X-AI-Harness-Approval-Proxy "";/);
  assert.ok(!generic.includes("image-approval-proxy.conf"));
});
