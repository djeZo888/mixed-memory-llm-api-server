import assert from "node:assert/strict";
import test from "node:test";
import { DatabaseSync } from "node:sqlite";
import { readFileSync } from "node:fs";
import { AdminActions, type AdminFreeze } from "../src/admin-actions.js";
import type { NodeAction } from "../src/node-contract.js";
import type { NodeBackend } from "../src/node-client.js";
import { ApiError } from "../src/errors.js";
const fixture = (name: string) =>
  JSON.parse(
    readFileSync(
      new URL(`./fixtures/h005/${name}.json`, import.meta.url),
      "utf8",
    ),
  );
const metadata = {
  state: "ok",
  freshness: "fresh",
  observed_at: new Date().toISOString(),
  age_ms: 0,
  reason: null,
};
const base: NodeAction = {
  ...fixture("node-action-v1"),
  expected_generation: 3,
};
const turn = () => new Promise((resolve) => setImmediate(resolve));
function rig() {
  const db = new DatabaseSync(":memory:");
  const node = fixture("node-status-v1");
  Object.assign(node, metadata, {
    boot_id: base.expected_boot_id,
    generation: 3,
  });
  for (const service of node.services)
    Object.assign(service, metadata, {
      generation: 3,
      ready: true,
      availability: "available",
      hardware_latched: false,
    });
  const held = new Map<string, string[]>(),
    seen: NodeAction[] = [],
    settled: NodeAction[] = [];
  let ownerState = "succeeded",
    transportFailure = false,
    ackFailure = false,
    changeAfterAck = false;
  const freeze: AdminFreeze = {
    hold: (a, scope) => {
      held.set(a.idempotency_key, scope ?? []);
    },
    acknowledge: async () => {
      if (changeAfterAck) node.services[0].generation++;
      if (ackFailure) throw Error("unreachable");
    },
    release: (a) => {
      held.delete(a.idempotency_key);
    },
    settle: async (a) => {
      settled.push(a);
    },
    inspect: async () => ({
      frozen: held.size > 0,
      ready: true,
      activity: "unknown",
      active_requests: null,
      queue_depth: null,
    }),
  };
  const receipt = (action: NodeAction) => ({
    ...fixture("node-operation-v1"),
    operation_id: `owner-${action.idempotency_key}`,
    action: action.action,
    service_id: action.service_id ?? null,
    gpu_uuid: action.gpu_uuid ?? null,
    expected_boot_id: action.expected_boot_id,
    expected_generation: action.expected_generation,
    status: ownerState,
  });
  const backend: NodeBackend = {
    status: async () => structuredClone(node),
    action: async (a) => {
      seen.push(a);
      if (a.action !== "service.start")
        assert.ok(
          held.has(a.idempotency_key),
          "protected freeze precedes owner POST",
        );
      if (transportFailure)
        throw new ApiError(503, "node_transport_error", "unknown");
      return receipt(a);
    },
    operation: async (id) =>
      receipt(seen.find((a) => `owner-${a.idempotency_key}` === id)!),
    passiveReady: async () => true,
  };
  const backends = { "ai-vm": backend, "ai-harness": backend };
  let actions = new AdminActions({ db, freeze, backends, autoPoll: false });
  return {
    db,
    node,
    held,
    seen,
    settled,
    freeze,
    backends,
    get actions() {
      return actions;
    },
    set ownerState(v: string) {
      ownerState = v;
    },
    set transportFailure(v: boolean) {
      transportFailure = v;
    },
    set ackFailure(v: boolean) {
      ackFailure = v;
    },
    set changeAfterAck(v: boolean) {
      changeAfterAck = v;
    },
    get: (receipt: any) =>
      actions.get(receipt.operation_id.split("~")[1], receipt.node_id),
    restart: () => {
      actions.close();
      actions = new AdminActions({ db, freeze, backends, autoPoll: false });
    },
    close: () => {
      actions.close();
      db.close();
    },
  };
}
test("destructive relay freezes before owner dispatch and exact repeats precede stale CAS", async () => {
  const r = rig();
  try {
    r.ownerState = "accepted";
    const operation = await r.actions.submit(base);
    await turn();
    assert.deepEqual(r.held.get(base.idempotency_key), ["qwen-gpu0"]);
    assert.equal(r.seen.length, 1);
    r.node.boot_id = "new-boot";
    r.node.services[0].generation++;
    assert.equal(
      (await r.actions.submit(base)).operation_id,
      operation.operation_id,
    );
    assert.equal(r.seen.length, 1);
    await assert.rejects(
      r.actions.submit({ ...base, allow_interrupt: false }),
      (e: any) => e.statusCode === 409,
    );
    await assert.rejects(
      r.actions.submit({ ...base, idempotency_key: "another-action-key" }),
      (e: any) => e.statusCode === 409,
    );
  } finally {
    r.close();
  }
});
test("missing interruption confirmation, failed freeze and post-freeze CAS never dispatch", async () => {
  const r = rig();
  try {
    await assert.rejects(
      r.actions.submit({ ...base, allow_interrupt: false }),
      (e: any) => e.code === "interrupt_required",
    );
    r.ackFailure = true;
    const failed = await r.actions.submit(base);
    await turn();
    assert.equal(r.get(failed).status, "failed");
    assert.equal(r.seen.length, 0);
    assert.equal(r.held.size, 0);
    r.ackFailure = false;
    r.changeAfterAck = true;
    const changed = await r.actions.submit({
      ...base,
      idempotency_key: "changed-after-freeze",
    });
    await turn();
    assert.equal(r.get(changed).status, "failed");
    assert.equal(r.seen.length, 0);
    assert.equal(r.held.size, 0);
  } finally {
    r.close();
  }
});
test("lost owner response survives daemon restart, preserves hold and never replays; guarded recovery settles it", async () => {
  const r = rig();
  try {
    r.transportFailure = true;
    const lost = await r.actions.submit(base);
    await turn();
    assert.equal(r.get(lost).status, "unknown");
    assert.equal(r.held.size, 1);
    r.restart();
    assert.equal((await r.actions.submit(base)).status, "unknown");
    assert.equal(r.seen.length, 1);
    // Fresh ready telemetry by itself cannot reconcile the ambiguous invocation.
    await r.actions.refresh();
    assert.equal(r.held.size, 1);
    assert.equal(r.settled.length, 0);
    await assert.rejects(
      r.actions.submit({
        ...base,
        action: "service.start",
        idempotency_key: "unsafe-start-key",
      }),
      (e: any) => e.code === "target_admission_busy",
    );
    r.transportFailure = false;
    await assert.rejects(
      r.actions.reconcile(lost.operation_id.split("~")[1]!, "ai-vm", {
        allow_interrupt: true,
        expected_boot_id: "stale-recovery-boot",
        expected_generation: 3,
        idempotency_key: "stale-recovery-key",
      }),
      (error: any) => error.statusCode === 409,
    );
    assert.equal(r.seen.length, 1);
    const recovery = await r.actions.reconcile(
      lost.operation_id.split("~")[1]!,
      "ai-vm",
      {
        allow_interrupt: true,
        expected_boot_id: base.expected_boot_id,
        expected_generation: 3,
        idempotency_key: "explicit-recovery-key",
      },
    );
    await turn();
    assert.equal(r.seen.length, 2);
    assert.equal(r.seen[1]!.action, "service.restart");
    assert.notEqual(r.seen[1]!.idempotency_key, base.idempotency_key);
    assert.equal(r.get(recovery).status, "succeeded");
    assert.equal(r.get(lost).status, "unknown");
    assert.equal(r.settled.length, 1);
    assert.equal(r.held.size, 0);
  } finally {
    r.close();
  }
});
test("uncertain target does not prevent a disjoint healthy peer action", async () => {
  const r = rig();
  try {
    r.transportFailure = true;
    await r.actions.submit(base);
    await turn();
    r.transportFailure = false;
    const peer = await r.actions.submit({
      ...base,
      service_id: "qwen-gpu1",
      idempotency_key: "healthy-peer-action",
    });
    await turn();
    assert.equal(r.get(peer).status, "succeeded");
    assert.equal(r.seen.length, 2);
    assert.deepEqual([...r.held.values()], [["qwen-gpu0"]]);
  } finally {
    r.close();
  }
});
test("successful stop stays held until validated start, preserving peer scope", async () => {
  const r = rig();
  try {
    const stopped = await r.actions.submit({ ...base, action: "service.stop" });
    await turn();
    assert.equal(r.get(stopped).status, "succeeded");
    assert.deepEqual([...r.held.values()], [["qwen-gpu0"]]);
    r.node.services[0].ready = false;
    const started = await r.actions.submit({
      ...base,
      action: "service.start",
      idempotency_key: "restart-stopped-lane",
    });
    await turn();
    assert.equal(r.get(started).status, "succeeded");
    assert.equal(r.held.size, 1);
    r.node.services[0].ready = true;
    await r.actions.refresh();
    assert.equal(r.held.size, 0);
    assert.equal(r.settled.length, 1);
  } finally {
    r.close();
  }
});
test("accepted owner receipt polls without repost and readiness cannot become idle proof", async () => {
  const r = rig();
  try {
    r.ownerState = "accepted";
    const operation = await r.actions.submit(base);
    await turn();
    r.ownerState = "succeeded";
    r.node.services[0].ready = false;
    await r.actions.refresh();
    assert.equal(r.get(operation).status, "succeeded");
    assert.equal(r.held.size, 1);
    r.node.services[0].ready = true;
    r.node.services[0].activity = "busy";
    await r.actions.refresh();
    assert.equal(r.held.size, 0);
    assert.equal(r.seen.length, 1);
    assert.equal(r.settled.length, 1);
  } finally {
    r.close();
  }
});
test("GPU reset scope uses exact current affected services including unassigned empty scope", async () => {
  const r = rig();
  try {
    r.ownerState = "accepted";
    const uuid = "GPU-00000000-0000-0000-0000-000000000001";
    r.node.gpus = [{ ...metadata, uuid, generation: 3, affected_services: [] }];
    const { service_id: _, ...action } = base;
    await r.actions.submit({ ...action, action: "gpu.reset", gpu_uuid: uuid });
    await turn();
    assert.deepEqual(r.held.get(base.idempotency_key), []);
    assert.equal(r.seen.length, 1);
    r.ownerState = "succeeded";
    await r.actions.refresh();
    assert.equal(r.held.size, 0);
  } finally {
    r.close();
  }
});
test("reboot readiness release requires changed boot plus canonical settlement", async () => {
  const r = rig();
  try {
    const { service_id: _, ...request } = base;
    const receipt = await r.actions.submit({
      ...request,
      action: "node.reboot",
    });
    await turn();
    assert.equal(r.get(receipt).status, "succeeded");
    assert.equal(r.held.size, 1);
    assert.deepEqual(
      [...r.held.values()],
      [["qwen-gpu0", "qwen-gpu1", "image"]],
    );
    r.node.boot_id = "changed-boot";
    Object.assign(r.node.services[1], {
      availability: "unavailable",
      hardware_latched: true,
      ready: false,
    });
    await r.actions.refresh();
    assert.equal(r.held.size, 0);
    assert.equal(r.settled.length, 1);
  } finally {
    r.close();
  }
});
test("mismatched owner target or confirmation cannot become settlement proof", async () => {
  const r = rig();
  try {
    const original = r.backends["ai-vm"].action;
    r.backends["ai-vm"].action = async (action, signal) => ({
      ...((await original(action, signal)) as Record<string, unknown>),
      service_id: "qwen-gpu1",
    });
    const operation = await r.actions.submit(base);
    await turn();
    assert.equal(r.get(operation).status, "unknown");
    assert.equal(r.held.size, 1);
    assert.equal(r.settled.length, 0);
  } finally {
    r.close();
  }
});
test("failed readiness reconciliation never erases canonical succeeded receipt or releases hold", async () => {
  const r = rig();
  try {
    r.freeze.settle = async () => {
      throw Error("active request retains ownership");
    };
    const operation = await r.actions.submit(base);
    await turn();
    assert.equal(r.get(operation).status, "succeeded");
    assert.equal(r.held.size, 1);
    await r.actions.refresh();
    assert.equal(r.get(operation).status, "succeeded");
    assert.equal(r.held.size, 1);
    assert.equal(r.seen.length, 1);
  } finally {
    r.close();
  }
});

test("changed-boot reboot releases prior stopped lane while unrelated peers are latched or unknown", async (t) => {
  const r = rig();
  try {
    const stopped = await r.actions.submit({ ...base, action: "service.stop" });
    await turn();
    assert.equal(r.get(stopped).status, "succeeded");
    assert.deepEqual([...r.held.values()], [["qwen-gpu0"]]);
    const { service_id: _, ...request } = base;
    const reboot = await r.actions.submit({
      ...request,
      action: "node.reboot",
      idempotency_key: "reboot-stopped-node",
    });
    await turn();
    assert.equal(r.get(reboot).status, "succeeded");
    assert.equal(r.held.size, 2);
    Object.assign(r.node.services[1], {
      availability: "unavailable",
      hardware_latched: true,
      ready: false,
    });
    Object.assign(r.node.services[2], {
      state: "timeout",
      reason: "observer_timeout",
      freshness: "unknown",
      age_ms: null,
      availability: "unknown",
      ready: null,
    });
    await r.actions.refresh();
    assert.equal(r.held.size, 2); // Readiness alone cannot prove old ownership settled.
    r.node.boot_id = "new-boot-with-partial-telemetry";
    await r.actions.refresh();
    assert.equal(r.held.size, 0);
    assert.equal(r.settled.length, 1);
    assert.equal(r.get(stopped).status, "succeeded");
    assert.equal(r.seen.length, 2);
    const audit = r.db
      .prepare(
        "SELECT release_reason,released_by FROM admin_relay_operations WHERE request_key=?",
      )
      .get(`ai-vm:${base.idempotency_key}`)!;
    assert.equal(audit.release_reason, "changed_boot_reconciled_stop_intent");
    assert.equal(audit.released_by, reboot.operation_id.split("~")[1]);
    // Actual production NodeAvailability -> gateway after reboot: the hung
    // image observer and latched GPU1 cannot retain GPU0 maintenance admission.
    const { NodeAvailability } = await import("../src/node-availability.js");
    const { createGateway } = await import("../src/gateway.js");
    const { createServer } = await import("node:http");
    const observer = new NodeAvailability({
      backend: r.backends["ai-vm"],
      onLatch: () => {},
    });
    await observer.poll();
    t.after(() => observer.stop());
    assert.equal(observer.get("qwen3.8-27b-gpu0").dispatch, "allow");
    assert.equal(observer.get("qwen3.8-27b").dispatch, "reject");
    assert.equal(observer.get("image").dispatch, "hold");
    const seen: string[] = [];
    const upstream = createServer(async (req, res) => {
      const bytes: Buffer[] = [];
      for await (const chunk of req) bytes.push(chunk as Buffer);
      seen.push(JSON.parse(Buffer.concat(bytes).toString()).model);
      res.setHeader("content-type", "application/json");
      res.end(
        JSON.stringify({
          choices: [
            {
              message: { role: "assistant", content: "synthetic" },
              finish_reason: "stop",
            },
          ],
        }),
      );
    });
    await new Promise<void>((resolve) =>
      upstream.listen(0, "127.0.0.1", resolve),
    );
    t.after(
      () => new Promise<void>((resolve) => upstream.close(() => resolve())),
    );
    const url = `http://127.0.0.1:${(upstream.address() as { port: number }).port}/v1`;
    const gateway = createGateway({
      upstreamKey: "fixture-only",
      availability: (id) => observer.get(id),
      upstreams: [
        { url, alias: "qwen3.8-27b-gpu0" },
        { url, alias: "qwen3.8-27b" },
      ],
    });
    t.after(() => gateway.close());
    const response = await gateway.app.inject({
      method: "POST",
      url: "/v1/chat/completions",
      headers: {
        authorization: `Bearer ${gateway.issueToken("fixture-reboot-client")}`,
      },
      payload: { model: "qwen3.8-27b", messages: [] },
    });
    assert.equal(response.statusCode, 200);
    assert.deepEqual(seen, ["qwen3.8-27b-gpu0"]);
  } finally {
    r.close();
  }
});

test("validated start settles only its exact retained canonical stop, never ordinary readiness alone", async () => {
  const r = rig();
  try {
    await r.actions.submit({ ...base, action: "service.stop" });
    await turn();
    await r.actions.submit({
      ...base,
      action: "service.stop",
      service_id: "qwen-gpu1",
      idempotency_key: "stop-other-lane-key",
    });
    await turn();
    assert.equal(r.held.size, 2);
    await r.actions.submit({
      ...base,
      action: "service.start",
      idempotency_key: "start-matched-stop",
    });
    await turn();
    assert.equal(r.settled.length, 1);
    assert.equal(r.settled[0]!.action, "service.start");
    assert.deepEqual([...r.held.values()], [["qwen-gpu1"]]);
    await r.actions.submit({
      ...base,
      action: "service.start",
      idempotency_key: "ordinary-start-key",
    });
    await turn();
    assert.equal(r.settled.length, 1);
    assert.deepEqual([...r.held.values()], [["qwen-gpu1"]]);
  } finally {
    r.close();
  }
});
