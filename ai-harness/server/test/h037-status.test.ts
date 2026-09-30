import assert from "node:assert/strict";
import test from "node:test";
import { loadSystemRegistry, selectRegistryFrontier } from "../src/system-registry.js";
import { sanitizeNode } from "../src/node-contract.js";
import { projectNode } from "../src/status-projection.js";
import { QWEN_REVIEWED_LANES } from "../src/codex-production.js";
import { MIMO_GPU_UUID } from "../src/mimo-current-owner.js";

const meta = { state: "ok", freshness: "fresh", age_ms: 0, observed_at: "2026-09-30T11:00:00Z" };
const boot = "93baf79c-e3a1-4473-8c56-19d7c2b600ba", digest = "a".repeat(64);
function fixture() {
  const registry = selectRegistryFrontier(loadSystemRegistry(), "mimo-v2.6-pro-rl");
  const image = registry.services.find(s => s.id === "image")!;
  image.placement!.selection_config_sha256 = digest;
  const services = registry.services.filter(s => s.node_id === "ai-vm").map(s => ({ ...meta,
    service_id: s.id, model_alias: s.model?.expected_alias, deployment_id: "SOURCE_FIXTURE", ready: true, admitting: true,
    functional_qualified: s.id !== "qwen-ada200k", availability: "available", configured_context_tokens: 480000, max_output_tokens: 65536,
    required_gpu_uuids: s.id === "image" ? [image.placement!.gpu_uuid]
      : s.id === "mimo-v2.6-pro-rl" ? [MIMO_GPU_UUID]
      : Object.values(QWEN_REVIEWED_LANES).filter(l => l.serviceId === s.id).map(l => l.gpuUuid),
  }));
  const raw: any = { schema_version: 1, node_id: "ai-vm", ...meta, boot_id: boot, services,
    imageGPU: { uuid: image.placement!.gpu_uuid, selectionConfigSha256: digest, bootId: boot },
    image: { ready: true, admitting: true, capabilities: ["images.generations", "images.edits"] },
    retired200K: { present: true, ready: true, retired: false },
  };
  const project = () => projectNode(sanitizeNode(raw, "ai-vm", services.map(s => s.service_id)), registry.nodes[0]!, registry);
  return { raw, registry, project };
}
test("SOURCE_FIXTURE three active text profiles, dormant GLM and receipt-dependent Ada retirement remain distinct", () => {
  const f = fixture(); let result = f.project();
  for (const id of ["qwen-gpu0", "qwen-gpu1", "mimo-v2.6-pro-rl"]) {
    const row = result.services.find(s => s.service_id === id)!;
    assert.equal(row.ready, true); assert.equal(row.configured_profile!.autoCompactTokenLimit, 400000);
    assert.equal(row.capacity_status, "matched"); assert.equal(row.gpu_identity_status, "matched");
  }
  assert.equal(result.services.find(s => s.service_id === "glm-5.3-flash")!.active_roster, false);
  assert.equal(result.services.find(s => s.service_id === "qwen-ada200k")!.active_roster, true);
  f.raw.retired200K = { present: true, ready: false, retired: true };
  assert.equal(f.project().services.find(s => s.service_id === "qwen-ada200k")!.active_roster, true);
  f.raw.services.find((s: any) => s.service_id === "qwen-ada200k").ready = false;
  result = f.project();
  const retained = result.services.find(s => s.service_id === "qwen-ada200k")!;
  assert.equal(retained.active_roster, false); assert.equal(retained.current_state, "retired"); assert.equal(retained.ready, null);
  assert.ok(result.services.some(s => s.service_id === "qwen-ada200k"));
  f.raw.freshness = "stale"; assert.equal(f.project().services.find(s => s.service_id === "qwen-ada200k")!.active_roster, true);
});
for (const change of ["uuid", "sha", "boot", "unknown", "not-ready"] as const) {
  test(`SOURCE_FIXTURE image ${change} only closes image and never borrows text availability`, () => {
    const f = fixture(); assert.equal(f.project().services.find(s => s.service_id === "image")!.ready, true);
    if (change === "uuid") f.raw.imageGPU.uuid = MIMO_GPU_UUID;
    if (change === "sha") f.raw.imageGPU.selectionConfigSha256 = "b".repeat(64);
    if (change === "boot") f.raw.imageGPU.bootId = "older-boot";
    if (change === "unknown") delete f.raw.imageGPU;
    if (change === "not-ready") { f.raw.image.ready = false; f.raw.image.admitting = false; }
    const result = f.project(); assert.notEqual(result.services.find(s => s.service_id === "image")!.ready, true);
    if (change === "not-ready") assert.equal(result.services.find(s => s.service_id === "image")!.reason, "image_status_mismatch");
    for (const id of ["qwen-gpu0", "qwen-gpu1", "mimo-v2.6-pro-rl"]) assert.equal(result.services.find(s => s.service_id === id)!.ready, true);
  });
}
test("SOURCE_FIXTURE unknown configured image digest and mismatched text profile/UUID fail only the dependent service", () => {
  const f = fixture(); f.registry.services.find(s => s.id === "image")!.placement!.selection_config_sha256 = null;
  const qwen = f.raw.services.find((s: any) => s.service_id === "qwen-gpu0"); qwen.configured_context_tokens = 200000;
  const result = f.project(); assert.equal(result.services.find(s => s.service_id === "image")!.ready, null);
  assert.equal(result.services.find(s => s.service_id === "qwen-gpu0")!.current_state, "mismatch");
  const mismatched = result.services.find(s => s.service_id === "qwen-gpu0")!;
  assert.equal(mismatched.availability, "unavailable"); assert.equal(mismatched.ready, false); assert.equal(mismatched.admitting, false);
  assert.equal(mismatched.reason, "model_capacity_mismatch"); assert.equal(mismatched.observed_model.ready, true);
  assert.equal(mismatched.observed_model.availability, "available");
  assert.equal(result.services.find(s => s.service_id === "qwen-gpu1")!.ready, true);
});
