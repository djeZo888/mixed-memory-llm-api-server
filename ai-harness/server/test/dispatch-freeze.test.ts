import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, rm, stat } from "node:fs/promises";
import path from "node:path";
import { tmpdir } from "node:os";
import {
  DispatchFreeze,
  serveDispatchFreeze,
  actionFingerprint,
  actionScope,
} from "../src/dispatch-freeze.js";
import type { NodeAction } from "../src/node-contract.js";
const action: NodeAction = {
  schema_version: 1,
  node_id: "ai-vm",
  action: "service.restart",
  service_id: "qwen-gpu0",
  idempotency_key: "fixture-restart-001",
  expected_boot_id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
  expected_generation: 2,
  allow_interrupt: true,
};
async function fixture(t: test.TestContext) {
  const dir = await mkdtemp(path.join(tmpdir(), "freeze-"));
  const database = path.join(dir, "state.sqlite"),
    socket = path.join(dir, "app.sock");
  const gate = new DispatchFreeze(database, socket);
  t.after(async () => {
    gate.close();
    await rm(dir, { recursive: true, force: true });
  });
  return { gate, database, socket };
}
test("durable exact per-target hold and protected UDS acknowledgement preserve peer dispatch across reopen", async (t) => {
  const { gate, database, socket } = await fixture(t);
  let observed = false;
  const app = await serveDispatchFreeze(
    gate,
    () => ({
      frozen: gate.held(),
      ready: true,
      activity: "unknown",
      active_requests: 1,
      queue_depth: 3,
    }),
    () => {
      observed = gate.held("qwen3.8-27b-gpu0");
    },
  );
  t.after(() => app.close());
  gate.hold(action);
  assert.equal(gate.held("qwen3.8-27b-gpu0"), true);
  assert.equal(gate.held("qwen3.8-27b"), false);
  assert.equal(gate.held("image"), false);
  assert.equal(gate.held("harness"), false);
  assert.equal((await gate.acknowledge(action)).app_state, "acknowledged");
  assert.equal(observed, true);
  assert.equal((await stat(socket)).mode & 0o777, 0o600);
  assert.equal((await gate.inspect()).queue_depth, 3);
  const reopened = new DispatchFreeze(database, socket);
  assert.equal(reopened.held("qwen-gpu0"), true);
  assert.throws(
    () => reopened.hold({ ...action, expected_generation: 3 }),
    /already belongs/,
  );
  reopened.release(action);
  reopened.close();
  assert.equal(gate.held(), false);
});
test("unreachable app is unknown; only confirmed whole app/node or no-inference scope can acknowledge", async (t) => {
  const { gate } = await fixture(t);
  gate.hold(action);
  await assert.rejects(gate.acknowledge(action), /acknowledgement required/);
  assert.equal((await gate.inspect()).activity, "unknown");
  const reboot = {
    ...action,
    action: "node.reboot",
    service_id: undefined,
    idempotency_key: "whole-reboot-001",
  } as NodeAction;
  delete reboot.service_id;
  gate.hold(reboot);
  assert.equal(
    (await gate.acknowledge(reboot)).app_state,
    "unreachable_confirmed",
  );
  const status = {
    ...action,
    node_id: "ai-harness",
    service_id: "status",
    idempotency_key: "status-restart-001",
  } as NodeAction;
  gate.hold(status);
  assert.equal((await gate.acknowledge(status)).app_state, "not_affected");
  assert.deepEqual(
    actionScope(
      { ...reboot, action: "gpu.reset", gpu_uuid: "GPU-unassigned" },
      [],
    ),
    [],
  );
  assert.throws(
    () =>
      actionScope({
        ...reboot,
        action: "gpu.reset",
        gpu_uuid: "GPU-unassigned",
      }),
    /affected services/,
  );
});
test("request quarantine settlement requires exact completed canonical receipt; readiness alone cannot clear", async (t) => {
  const { gate } = await fixture(t);
  let reconciled = 0;
  const app = await serveDispatchFreeze(
    gate,
    () => ({
      frozen: true,
      ready: true,
      activity: "unknown",
      active_requests: null,
      queue_depth: null,
    }),
    () => {},
    (scope) => {
      assert.deepEqual(scope, ["qwen-gpu0"]);
      reconciled++;
      return true;
    },
  );
  t.after(() => app.close());
  gate.hold(action);
  gate.db.exec(
    "CREATE TABLE admin_relay_operations(request_key TEXT,request TEXT,receipt TEXT,owner_id TEXT,dispatched INTEGER)",
  );
  gate.db
    .prepare("INSERT INTO admin_relay_operations VALUES(?,?,?,?,1)")
    .run(
      "ai-vm:" + action.idempotency_key,
      JSON.stringify(action),
      JSON.stringify({ status: "unknown" }),
      "owner-fixture",
    );
  await assert.rejects(gate.settle(action));
  assert.equal(reconciled, 0);
  gate.db
    .prepare("UPDATE admin_relay_operations SET receipt=?")
    .run(JSON.stringify({ status: "succeeded" }));
  await gate.settle(action);
  assert.equal(reconciled, 1);
  assert.equal(
    gate.held("qwen-gpu0"),
    true,
    "settlement does not itself release admission",
  );
  assert.equal(
    actionFingerprint(action),
    actionFingerprint(
      Object.fromEntries(Object.entries(action).reverse()) as NodeAction,
    ),
  );
});

test("stale socket cleanup rejects live/foreign paths and removes only dead exact owned socket", async (t) => {
  const { socket } = await fixture(t);
  const { createServer } = await import("node:net");
  const { chmod, writeFile } = await import("node:fs/promises");
  const { spawn } = await import("node:child_process");
  const { once } = await import("node:events");
  const { removeStaleDispatchSocket } =
    await import("../src/dispatch-freeze.js");
  const live = createServer();
  await new Promise<void>((resolve) => live.listen(socket, resolve));
  await chmod(socket, 0o600);
  await assert.rejects(removeStaleDispatchSocket(socket), /live or unknown/);
  await new Promise<void>((resolve) => live.close(() => resolve()));
  const child = spawn(
    process.execPath,
    [
      "-e",
      "require('node:net').createServer().listen(process.argv[1],()=>process.exit(0))",
      socket,
    ],
    { stdio: "ignore" },
  );
  await once(child, "exit");
  await chmod(socket, 0o600);
  await removeStaleDispatchSocket(socket);
  await assert.rejects(stat(socket), { code: "ENOENT" });
  await writeFile(socket, "not a socket", { mode: 0o600 });
  await assert.rejects(
    removeStaleDispatchSocket(socket),
    /Unsafe dispatch socket/,
  );
});

test("production private stop/start adapter clears actual gateway quarantine only with canonical outstanding stop", async (t) => {
  const { gate } = await fixture(t);
  const { createGateway } = await import("../src/gateway.js");
  const gateway = createGateway({
    upstreamKey: "fixture-not-used",
    initialLaneStates: { "qwen3.8-27b-gpu0": "quarantined" },
    availability: (id) => ({
      state: "available",
      dispatch: gate.held(id) ? "hold" : "allow",
    }),
  });
  t.after(() => gateway.close());
  const app = await serveDispatchFreeze(
    gate,
    () => ({
      frozen: gate.held(),
      ready: true,
      activity: "unknown",
      active_requests: null,
      queue_depth: null,
    }),
    () => gateway.notifyAvailabilityChanged(),
    (scope) =>
      gateway.reconcileAfterOwnerSettlement(
        scope.filter((id) => id === "qwen-gpu0").map(() => "qwen3.8-27b-gpu0"),
      ),
  );
  t.after(() => app.close());
  gate.db.exec(
    "CREATE TABLE admin_relay_operations(request_key TEXT,request TEXT,receipt TEXT,owner_id TEXT,dispatched INTEGER,released INTEGER)",
  );
  const start = {
    ...action,
    action: "service.start",
    idempotency_key: "fixture-start-proof-001",
  } as NodeAction;
  const insert = (a: NodeAction, status: string) =>
    gate.db
      .prepare("INSERT INTO admin_relay_operations VALUES(?,?,?,?,1,0)")
      .run(
        `${a.node_id}:${a.idempotency_key}`,
        JSON.stringify(a),
        JSON.stringify({ status }),
        "owner-" + a.idempotency_key,
      );
  insert(start, "succeeded");
  await assert.rejects(gate.settle(start));
  assert.equal(gateway.snapshot().lanes[0].state, "quarantined");
  const stop = {
    ...action,
    action: "service.stop",
    idempotency_key: "fixture-stop-proof-001",
  } as NodeAction;
  gate.hold(stop);
  insert(stop, "succeeded");
  await gate.acknowledge(stop);
  await gate.settle(start);
  assert.equal(gateway.snapshot().lanes[0].state, "idle");
  assert.equal(
    gate.held("qwen-gpu0"),
    true,
    "settled ownership remains frozen until readiness coordinator releases",
  );
  assert.equal(gateway.snapshot().queuedBytes, 0);
  gate.release(stop);
  const local = {
    ...action,
    node_id: "ai-harness",
    service_id: "harness",
    idempotency_key: "fixture-local-restart",
  } as NodeAction;
  insert(local, "succeeded");
  gate.hold(local);
  const before = gateway.snapshot();
  await gate.settle(local);
  assert.deepEqual(
    gateway.snapshot(),
    before,
    "local harness restart cannot settle remote lanes",
  );
});
