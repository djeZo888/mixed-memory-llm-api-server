import assert from "node:assert/strict";
import test, { type TestContext } from "node:test";
import { mkdtemp, rm, readFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { PassThrough } from "node:stream";
import { DatabaseSync } from "node:sqlite";
import { createApp } from "../src/app.js";
import { composeCodexHost } from "../src/codex-host.js";
import { codexDeployment } from "../src/codex-deployment.js";
import { GatewayOwnership, GatewayOwnershipLedger, type RequestOwnership } from "../src/gateway-ownership.js";
import type { Gateway } from "../src/gateway.js";

function deferred<T = void>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(yes => { resolve = yes; });
  return { promise, resolve };
}
const tick = () => new Promise<void>(resolve => setImmediate(resolve));

// Native stdio and owned inference are controlled fixtures. Real engine, host,
// broker, store and durable ownership observer run together; no model is called.
async function fixture(t: TestContext, interrupt: "interrupted" | "failed" = "interrupted", nativeProof: boolean | "reject" = true) {
  const dir = await mkdtemp(join(tmpdir(), "h021-stop08-"));
  const db = new DatabaseSync(":memory:");
  const ledger = new GatewayOwnershipLedger(db).options();
  let failWrites = false;
  const owners = new GatewayOwnership({ ...ledger, onRequestState(record) {
    if (failWrites) throw Error("fixture disk unavailable");
    ledger.onRequestState(record);
  } });
  const started = deferred(), observing = deferred();
  let owned!: RequestOwnership;
  let turns = 0, cleanupCalls = 0, observations = 0;
  let finish!: (status: string) => void;
  // Read actual trusted resume policy; launchRootless below still replaces all native execution.
  const host = composeCodexHost(fileURLToPath(new URL("../../deploy/run-codex.sh", import.meta.url)), () => ({
    revokeSession() {},
    observeSettlement(query, signal) {
      observations++;
      const result = owners.waitForSettlement(query, signal);
      observing.resolve();
      return result;
    },
  } as Gateway), {
    protocolQualified: true, rootlessQualified: true,
    verifyLane: async () => { throw Error("No live verification in fixture"); },
  });
  host.runtime.launchRootless = async input => {
    const stdin = new PassThrough(), stdout = new PassThrough();
    const emit = (value: unknown) => stdout.write(JSON.stringify(value) + "\n");
    const threadId = "fixture-thread";
    stdin.on("data", data => {
      const r = JSON.parse(data.toString());
      const reply = (result: unknown) => emit({ id: r.id, result });
      if (r.method === "initialize") reply({ userAgent: "codex/0.158.0", codexHome: input.codexHome, platformOs: "linux", platformFamily: "unix" });
      if (r.method === "thread/start" || r.method === "thread/resume") reply({ thread: { id: threadId }, model: "qwen3.8-27b", modelProvider: "sova", cwd: input.workspace, approvalPolicy: "never" });
      if (r.method === "turn/start") {
        const turnId = `turn-${++turns}`;
        reply({ turn: { id: turnId } });
        finish = status => emit({ method: "turn/completed", params: { threadId, turn: { id: turnId, status } } });
        if (turns === 1) {
          owned = owners.begin(input.sessionId);
          owners.transition(owned, "accepted", "fixture-qwen");
          started.resolve();
        } else finish("completed");
      }
      if (r.method === "turn/interrupt") {
        reply({});
        owners.transition(owned, "draining");
        finish(interrupt);
      }
    });
    return { stdin, stdout, exited: new Promise<void>(() => {}), async terminateAndConfirm() { cleanupCalls++; if (nativeProof === "reject") throw Error("private launcher detail must not escape"); return nativeProof; } };
  };
  const app = await createApp({ newChatEngine: "minimax",
    dataDir: dir, launcher: "/never", gatewayUrl: "http://127.0.0.1:1/v1",
    allowedOrigins: ["http://localhost"],
    engineFactory: () => { throw Error("Wrong engine"); },
    issueToken: id => { owners.registerSession(id); return "fixture-token"; },
    revokeToken() {}, ...codexDeployment({ enablePreview: true, runtime: host.runtime }),
  });
  t.after(async () => {
    t.mock.timers.reset();
    host.stopSettlementObservation();
    await app.app.close();
    db.close();
    await rm(dir, { recursive: true, force: true });
  });
  const session = await app.broker.createSession(undefined, "codex");
  const run = app.broker.enqueue(session.id, "message", "Stop fixture");
  await started.promise;
  return { ...app, host, owners, db, session, run, observing, failLedger: () => { failWrites = true; }, get owned() { return owned; }, get turns() { return turns; }, get cleanupCalls() { return cleanupCalls; }, get observations() { return observations; }, finish: (status: string) => finish(status) };
}

for (const terminal of ["interrupted", "failed"] as const) {
  test(`Stop ${terminal}: cancelling beyond 15s, no terminal event or followup dispatch before durable drain`, async t => {
    const f = await fixture(t, terminal);
    t.mock.timers.enable({ apis: ["setTimeout"] });
    await f.broker.cancel(f.session.id);
    await f.observing.promise;
    t.mock.timers.tick(46_000);
    await tick();
    const pending = f.store.snapshot(f.session.id);
    assert.equal(pending.session.status, "cancelling");
    assert.equal(pending.runs[0]!.status, "cancelling");
    assert.equal(pending.events.some(e => e.type === "done" || e.type === "error"), false);
    assert.equal(f.store.isQuarantined(f.store.getSession(f.session.id).workspaceId), false);
    assert.equal(f.cleanupCalls, 1);
    assert.equal(f.owners.snapshot(f.session.id)[0]!.state, "draining");
    const followup = f.broker.enqueue(f.session.id, "message", "Explicit followup");
    await tick();
    assert.equal(f.turns, 1);
    assert.equal(f.store.runs(f.session.id).find(r => r.id === followup)!.status, "queued");
    f.owners.transition(f.owned, "settled");
    t.mock.timers.reset();
    await f.broker.idle();
    const final = f.store.snapshot(f.session.id);
    assert.equal(final.runs.find(r => r.id === f.run)!.status, "cancelled");
    assert.equal(final.runs.find(r => r.id === followup)!.status, "completed");
    assert.equal(f.store.getSession(f.session.id).nativeState?.ownership, "idle");
    assert.equal(f.turns, 2);
    assert.equal(f.store.isQuarantined(f.store.getSession(f.session.id).workspaceId), false);
    assert.equal(f.db.prepare("SELECT state FROM h021_gateway_requests WHERE id=?").get(f.owned.id)!.state, "settled");
  });
}

test("shutdown abort before broker.close ends pending and future observation false without releasing drain", async t => {
  const f = await fixture(t, "failed");
  await f.broker.cancel(f.session.id);
  await f.observing.promise;
  f.host.stopSettlementObservation();
  await f.broker.close();
  assert.equal(f.owners.snapshot(f.session.id)[0]!.state, "draining");
  assert.equal(f.store.getSession(f.session.id).nativeState!.ownership, "uncertain");
  assert.equal(f.store.isQuarantined(f.store.getSession(f.session.id).workspaceId), true);
  assert.notEqual(f.store.runs(f.session.id)[0]!.status, "completed");
  assert.equal(f.store.allEvents(f.session.id).find(e => e.type === "error" && e.data.code === "engine_cleanup_unknown")?.data.cleanupFailure, "gateway_settlement_unconfirmed");
  f.owners.transition(f.owned, "settled");
  assert.equal(await f.host.runtime.confirmGatewaySettlement({ sessionId: f.session.id, gatewayToken: "fixture", activeTurnId: null }), false);
  const main = await readFile(new URL("../src/main.ts", import.meta.url), "utf8");
  const startupFailure = main.slice(main.indexOf("  } catch (error) {"), main.indexOf("  let stopping = false;"));
  assert.ok(startupFailure.includes("codexHost.stopSettlementObservation();"));
  assert.ok(startupFailure.indexOf("codexHost.stopSettlementObservation();") < startupFailure.indexOf("await application.app.close();"));
  const shutdown = main.slice(main.indexOf("const close = async"));
  assert.ok(shutdown.indexOf("codexHost.stopSettlementObservation();") < shutdown.indexOf("application.broker.close(),"));
});

for (const nativeProof of [false, "reject"] as const)
test(`native cleanup ${nativeProof} fails promptly without entering gateway observation or releasing followup`, async t => {
  const f = await fixture(t, "interrupted", nativeProof);
  await f.broker.cancel(f.session.id);
  await f.broker.idle();
  assert.equal(f.observations, 0);
  assert.equal(f.owners.snapshot(f.session.id)[0]!.state, "draining");
  assert.equal(f.store.isQuarantined(f.store.getSession(f.session.id).workspaceId), true);
  assert.throws(() => f.broker.enqueue(f.session.id, "message", "blocked"), /settlement review/);
  assert.equal(f.store.allEvents(f.session.id).find(e => e.type === "error" && e.data.code === "engine_cleanup_unknown")?.data.cleanupFailure, "native_cleanup_unconfirmed");
  assert.doesNotMatch(JSON.stringify(f.store.allEvents(f.session.id)), /private launcher detail/);
});

for (const lateStop of [false, true])
test(`independent failed turn, late Stop ${lateStop}: retains failure evidence and never becomes successful`, async t => {
  const f = await fixture(t);
  f.finish("failed");
  await f.observing.promise;
  assert.equal(f.store.isQuarantined(f.store.getSession(f.session.id).workspaceId), true);
  assert.ok(["failed", "interrupted"].includes(f.store.runs(f.session.id)[0]!.status));
  assert.ok(f.store.allEvents(f.session.id).some(e => e.type === "error"));
  if (lateStop) await f.broker.cancel(f.session.id);
  f.owners.transition(f.owned, "settled");
  await f.broker.idle();
  assert.ok((lateStop ? ["failed", "interrupted", "cancelled"] : ["failed", "interrupted"]).includes(f.store.runs(f.session.id)[0]!.status));
  assert.ok(f.store.allEvents(f.session.id).some(e => e.type === "error"));
  assert.equal(f.store.getSession(f.session.id).nativeState!.ownership, "idle");
});

for (const failure of ["uncertain", "ledger"] as const)
test(`Codex Stop ${failure} fails closed and cannot admit a followup or become success on a late settled record`, async t => {
  const f = await fixture(t);
  await f.broker.cancel(f.session.id);
  await f.observing.promise;
  if (failure === "ledger") {
    f.failLedger();
    assert.throws(() => f.owners.transition(f.owned, "settled"), /ledger/);
  } else f.owners.transition(f.owned, "uncertain");
  await f.broker.idle();
  assert.equal(f.store.isQuarantined(f.store.getSession(f.session.id).workspaceId), true);
  assert.throws(() => f.broker.enqueue(f.session.id, "message", "blocked"), /settlement review/);
  assert.ok(["failed", "interrupted"].includes(f.store.runs(f.session.id)[0]!.status));
  assert.equal(f.store.allEvents(f.session.id).find(e => e.type === "error" && e.data.code === "engine_cleanup_unknown")?.data.cleanupFailure, "gateway_settlement_unconfirmed");
  if (failure === "uncertain") f.owners.transition(f.owned, "settled");
  await tick();
  assert.equal(f.store.getSession(f.session.id).nativeState!.ownership, "uncertain");
  assert.equal(f.store.isQuarantined(f.store.getSession(f.session.id).workspaceId), true);
});
