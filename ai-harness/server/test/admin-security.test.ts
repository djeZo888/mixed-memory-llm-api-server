import assert from "node:assert/strict";
import test from "node:test";
import Fastify from "fastify";
import { AdminSecurity } from "../src/admin-security.js";

test("anonymous LAN admin needs exact Host/Origin and signed same-origin CSRF; status alias cannot mutate", async () => {
  let now = 1700000000000;
  const security = new AdminSecurity(
    ["http://10.156.100.61"],
    ["http://status.ai-harness"],
    () => now,
  );
  const app = Fastify();
  app.get("/api/admin/session", async (req, reply) =>
    security.issue(req, reply),
  );
  app.post("/api/admin/test", async (req) => {
    security.mutation(req);
    return { ok: true };
  });
  const session = await app.inject({
    url: "/api/admin/session",
    headers: { host: "10.156.100.61" },
  });
  const cookie = String(session.headers["set-cookie"]).split(";")[0]!;
  const token = session.json().csrf;
  const headers = {
    host: "10.156.100.61",
    origin: "http://10.156.100.61",
    cookie,
    "x-csrf-token": token,
  };
  const send = (changes: Record<string, string | undefined>) =>
    app.inject({
      method: "POST",
      url: "/api/admin/test",
      headers: Object.fromEntries(
        Object.entries({ ...headers, ...changes }).filter(
          ([, v]) => v !== undefined,
        ),
      ),
      payload: {},
    });
  assert.equal((await send({})).statusCode, 200);
  for (const change of [
    { host: "attacker.test" },
    { origin: "http://attacker.test" },
    { origin: undefined },
    { "x-csrf-token": undefined },
    { cookie: "" },
    { "sec-fetch-site": "cross-site" },
    { host: "status.ai-harness", origin: "http://status.ai-harness" },
    { "x-csrf-token": "forged" },
  ])
    assert.equal((await send(change)).statusCode, 403);
  assert.equal(
    (
      await app.inject({
        url: "/api/admin/session",
        headers: { host: "status.ai-harness" },
      })
    ).statusCode,
    403,
  );
  now += 1800001;
  assert.equal((await send({})).statusCode, 403);
  await app.close();
});
