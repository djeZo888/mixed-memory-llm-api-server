import assert from "node:assert/strict";
import test from "node:test";
import http from "node:http";
import { mkdtemp, readFile, realpath, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createApp, type AppOptions } from "../src/app.js";
import { createEngine } from "../src/engine.js";
import { createGateway } from "../src/gateway.js";
import type { Event, GatewayUsage } from "../src/contracts.js";

test(
  "real app + official SDK subprocess + gateway fixtures preserve history across restart and revoke exit credentials",
  { timeout: 15000 },
  async (t) => {
    const root = await realpath(
      await mkdtemp(path.join(tmpdir(), "h001-integration-")),
    );
    const upstreamRequests: {
      model: string;
      max_tokens: number;
      stream: boolean;
      messages: unknown[];
    }[] = [];
    const upstreams = [0, 1].map(() =>
      http.createServer(async (req, res) => {
        assert.equal(req.socket.remoteAddress, "127.0.0.1");
        assert.equal(req.url, "/v1/chat/completions");
        assert.equal(
          req.headers.authorization,
          "Bearer integration-fixture-upstream",
        );
        let body = "";
        for await (const chunk of req) body += chunk;
        upstreamRequests.push(JSON.parse(body));
        res.writeHead(200, { "content-type": "application/json" });
        res.end(
          JSON.stringify({
            id: "fixture-generation",
            object: "chat.completion",
            choices: [
              {
                index: 0,
                message: {
                  role: "assistant",
                  content: "Gateway fixture visible answer. ",
                },
                finish_reason: "stop",
              },
            ],
            usage: {
              prompt_tokens: 111,
              completion_tokens: 7,
              total_tokens: 118,
            },
          }),
        );
      }),
    );
    await Promise.all(
      upstreams.map(
        (server) =>
          new Promise<void>((resolve) =>
            server.listen(0, "127.0.0.1", resolve),
          ),
      ),
    );
    const port = (server: http.Server) => {
      const addr = server.address();
      assert.ok(addr && typeof addr === "object");
      return addr.port;
    };
    const usages: GatewayUsage[] = [];
    const gateway = createGateway({
      upstreamKey: "integration-fixture-upstream",
      onUsage: (usage) => {
        usages.push(usage);
      },
      upstreams: [
        {
          url: `http://127.0.0.1:${port(upstreams[0]!)}/v1`,
          alias: "qwen3.8-27b-gpu0",
        },
        {
          url: `http://127.0.0.1:${port(upstreams[1]!)}/v1`,
          alias: "qwen3.8-27b",
        },
      ],
    });
    await gateway.app.listen({ host: "127.0.0.1", port: 0 });
    const issued: string[] = [],
      revoked: string[] = [];
    const options: AppOptions = {
      dataDir: root,
      allowedOrigins: ["http://localhost"],
      heartbeatMs: 20,
      launcher: fileURLToPath(
        new URL("./fixtures/engine-agent.mjs", import.meta.url),
      ),
      engineFactory: createEngine,
      gatewayUrl: `http://127.0.0.1:${port(gateway.app.server)}/v1`,
      issueToken(id) {
        const token = gateway.issueToken(id);
        issued.push(token);
        return token;
      },
      revokeToken(token) {
        revoked.push(token);
        gateway.revokeToken(token);
      },
    };
    let application: Awaited<ReturnType<typeof createApp>> | undefined;
    let eventRequest: http.ClientRequest | undefined,
      eventResponse: http.IncomingMessage | undefined;
    t.after(async () => {
      eventResponse?.destroy();
      eventRequest?.destroy();
      await application?.app.close();
      await gateway.close();
      await Promise.all(
        upstreams.map(
          (server) =>
            new Promise<void>((resolve, reject) =>
              server.close((error) => (error ? reject(error) : resolve())),
            ),
        ),
      );
      await rm(root, { recursive: true, force: true });
    });
    application = await createApp(options);
    await application.app.listen({ host: "127.0.0.1", port: 0 });
    const created = await application.app.inject({
      method: "POST",
      url: "/api/sessions",
      headers: { host: "localhost" },
      payload: {},
    });
    assert.equal(created.statusCode, 200);
    const sessionId = created.json().session.id as string;
    await writeFile(
      path.join(application.files.profile(sessionId), "fixture.json"),
      "{}",
    );
    let eventBody = "";
    eventRequest = http.get({
      hostname: "127.0.0.1",
      port: port(application.app.server),
      path: `/api/sessions/${sessionId}/events`,
      headers: { host: "localhost" },
    });
    eventResponse = await new Promise<http.IncomingMessage>(
      (resolve, reject) => {
        eventRequest!.once("response", resolve);
        eventRequest!.once("error", reject);
      },
    );
    assert.equal(eventResponse.statusCode, 200);
    eventResponse.setEncoding("utf8");
    eventResponse.on("data", (text) => {
      eventBody += text;
    });
    eventResponse.on("error", () => {});
    const prompt = () =>
      application!.app.inject({
        method: "POST",
        url: `/api/sessions/${sessionId}/messages`,
        headers: { host: "localhost" },
        payload: { text: "gateway" },
      });
    const run = await prompt();
    assert.equal(run.statusCode, 202);
    await application.broker.idle();
    const deadline = Date.now() + 3000;
    while (!eventBody.includes("event: done")) {
      assert.ok(Date.now() < deadline, "SSE delivers durable completion");
      await new Promise((resolve) => setTimeout(resolve, 5));
    }
    const events: Event[] = eventBody
      .split("\n\n")
      .filter((frame) => frame.startsWith("id:"))
      .map((frame) =>
        JSON.parse(
          frame
            .split("\n")
            .find((line) => line.startsWith("data: "))!
            .slice(6),
        ),
      );
    assert.ok(
      events.some(
        (event) => event.type === "state" && event.data.status === "running",
      ),
    );
    assert.ok(events.some((event) => event.type === "assistant_delta"));
    assert.ok(
      events.some(
        (event) => event.type === "done" && event.runId === run.json().runId,
      ),
    );
    assert.equal(
      application.store.getSession(sessionId).nativeSessionId,
      "native-fixture-session",
    );
    assert.equal(application.store.getSession(sessionId).status, "idle");
    const firstHistory = application.store.messages(sessionId);
    assert.deepEqual(
      firstHistory
        .filter((m) => m.phase !== "thinking")
        .map((message) => message.content),
      ["gateway", "Gateway fixture visible answer. fixture response"],
    );
    assert.equal(
      application.store.getSession(sessionId).context?.used,
      12345,
      "native context occupancy is distinct from per-request gateway usage",
    );
    assert.equal(usages[0]?.sessionId, sessionId);
    assert.equal(usages[0]?.promptTokens, 111);
    assert.deepEqual(
      upstreamRequests.map((request) => [
        request.model,
        request.max_tokens,
        request.stream,
      ]),
      [["qwen3.8-27b-gpu0", 17, false]],
    );
    assert.equal(
      (
        await gateway.app.inject({
          url: "/v1/models",
          headers: { authorization: `Bearer ${issued[0]}` },
        })
      ).statusCode,
      200,
    );
    eventResponse.destroy();
    eventRequest.destroy();
    await application.app.close();
    assert.ok(revoked.includes(issued[0]!));
    assert.equal(
      (
        await gateway.app.inject({
          url: "/v1/models",
          headers: { authorization: `Bearer ${issued[0]}` },
        })
      ).statusCode,
      401,
    );

    application = await createApp(options);
    assert.deepEqual(application.store.messages(sessionId), firstHistory);
    assert.equal((await prompt()).statusCode, 202);
    await application.broker.idle();
    const restoredCalls = JSON.parse(
      await readFile(
        path.join(application.files.profile(sessionId), "calls.json"),
        "utf8",
      ),
    ) as { method: string; params?: { sessionId?: string } }[];
    assert.ok(
      restoredCalls.some(
        (call) =>
          call.method === "resume" &&
          call.params?.sessionId === "native-fixture-session",
      ),
    );
    assert.equal(
      restoredCalls.some((call) => call.method === "new"),
      false,
    );
    assert.equal(application.store.messages(sessionId).length, 6);
    assert.deepEqual(
      application.store.messages(sessionId).slice(0, firstHistory.length),
      firstHistory,
    );
    assert.equal(upstreamRequests.length, 2);
    assert.equal(issued.length, 2);
    assert.notEqual(issued[0], issued[1]);
    const currentToken = issued[1]!;
    assert.equal(
      (
        await gateway.app.inject({
          url: "/v1/models",
          headers: { authorization: `Bearer ${currentToken}` },
        })
      ).statusCode,
      200,
    );
    const crash = await application.app.inject({
      method: "POST",
      url: `/api/sessions/${sessionId}/messages`,
      headers: { host: "localhost" },
      payload: { text: "crash" },
    });
    assert.equal(crash.statusCode, 202);
    await application.broker.idle();
    assert.equal(application.store.getSession(sessionId).status, "failed");
    assert.ok(
      application.store.isQuarantined(
        application.store.getSession(sessionId).workspaceId,
      ),
    );
    assert.ok(revoked.includes(currentToken));
    assert.equal(
      (
        await gateway.app.inject({
          url: "/v1/models",
          headers: { authorization: `Bearer ${currentToken}` },
        })
      ).statusCode,
      401,
      "actual subprocess transport exit revokes inference access",
    );
    assert.equal(
      upstreamRequests.length,
      2,
      "crashed prompt is never replayed through gateway",
    );
  },
);
