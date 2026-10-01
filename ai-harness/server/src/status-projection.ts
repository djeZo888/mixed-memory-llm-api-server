import { observation, sanitizeNode, type NodeSnapshot } from "./node-contract.js";
import type { RegistryNode, SystemRegistry } from "./system-registry.js";
import { codexProvider } from "./codex-provider.js";
import { QWEN_REVIEWED_LANES } from "./codex-production.js";
import { MIMO_GPU_UUID } from "./mimo-current-owner.js";

const current = (o: { state: string; freshness: string }) => o.state === "ok" && o.freshness === "fresh";
/** Join expectations after sanitizing and aging native facts. No parent health inheritance. */
export function projectNode(node: NodeSnapshot, config: RegistryNode, registry: SystemRegistry) {
  const services = registry.services.filter(s => s.node_id === node.node_id).map(s => {
    const observed = node.services.find(n => n.service_id === s.observation_key);
    const native = observed ??
      sanitizeNode({ schema_version: 1, node_id: node.node_id, services: [{ service_id: s.observation_key, reason: "not_observed" }] }, node.node_id, [s.observation_key]).services[0]!;
    const selection = s.model?.selection_group === "frontier"
      ? registry.selected_frontier === undefined ? "unknown"
        : s.model.expected_alias === registry.selected_frontier ? "selected" : "dormant"
      : "not_applicable";
    const profile = s.id === "qwen-gpu0" || s.id === "qwen-gpu1" ? codexProvider("qwen3.8-27b")
      : s.id === "mimo-v2.6-pro-rl" ? codexProvider(s.id) : null;
    const capacity = !profile ? "not_applicable" : native.configured_context_tokens === null || native.max_output_tokens === null ? "unknown"
      : native.configured_context_tokens === profile.contextWindow && native.max_output_tokens === profile.maxOutputTokens ? "matched" : "mismatch";
    const capacityReason = capacity !== "unknown" ? null
      : native.configured_context_tokens === null ? "native_context_not_observed" : "native_output_ceiling_not_observed";
    const qwenLane = Object.values(QWEN_REVIEWED_LANES).find(l => l.serviceId === s.id);
    const configuredGpuUuids = s.placement ? [s.placement.gpu_uuid] : qwenLane ? [qwenLane.gpuUuid]
      : s.id === "mimo-v2.6-pro-rl" ? [MIMO_GPU_UUID] : null;
    const gpuIdentity = configuredGpuUuids === null ? "not_applicable" : native.required_gpu_uuids.length === 0 ? "unknown"
      : JSON.stringify(native.required_gpu_uuids) === JSON.stringify(configuredGpuUuids) ? "matched" : "mismatch";
    const placement = !s.placement ? "not_applicable"
      : !current(node) || node.imageGPU.bootId !== node.boot_id || !node.boot_id ||
        !node.imageGPU.uuid || !node.imageGPU.selectionConfigSha256 || !s.placement.selection_config_sha256 ? "unknown"
      : node.imageGPU.uuid !== s.placement.gpu_uuid || native.required_gpu_uuids.length !== 1 ||
        native.required_gpu_uuids[0] !== s.placement.gpu_uuid || node.imageGPU.selectionConfigSha256 !== s.placement.selection_config_sha256 ? "mismatch" : "matched";
    const retired = s.retirement_key === "retired200K" && current(node) &&
      node.retired200K.retired === true && node.retired200K.ready === false && node.retired200K.present !== null &&
      !(current(native) && native.ready === true);
    const identity = !s.model ? "not_applicable"
      : native.freshness === "stale" || node.freshness === "stale" ? "stale"
      : !current(node) || !current(native) ? "unavailable"
      : native.model_alias === null ? "unknown"
      : native.model_alias === s.model.expected_alias ? "matched" : "mismatch";
    const usable = !retired && current(node) && current(native) &&
      (identity === "matched" || identity === "not_applicable") &&
      (placement === "matched" || placement === "not_applicable") &&
      (capacity === "matched" || capacity === "not_applicable") &&
      (gpuIdentity === "matched" || gpuIdentity === "not_applicable") &&
      (!s.placement || (node.image.ready !== null && node.image.admitting !== null &&
        node.image.ready === native.ready && node.image.admitting === native.admitting)) &&
      selection !== "dormant" && selection !== "unknown";
    const mismatchReason = !current(node) || !current(native) || selection === "dormant" ? null
      : identity === "mismatch" ? "model_identity_mismatch"
      : placement === "mismatch" ? "image_placement_mismatch"
      : capacity === "mismatch" ? "model_capacity_mismatch"
      : gpuIdentity === "mismatch" ? "gpu_identity_mismatch"
      : s.placement && node.image.ready !== null && node.image.admitting !== null && native.ready !== null && native.admitting !== null &&
        (node.image.ready !== native.ready || node.image.admitting !== native.admitting) ? "image_status_mismatch" : null;
    return {
      ...native, service_id: s.id, node_id: s.node_id, display_name: s.display_name,
      configured_model: s.model ?? null, selection, identity_status: identity,
      configured_placement: s.placement ?? null, placement_status: placement,
      configured_profile: profile, capacity_status: capacity, capacity_reason: capacityReason,
      configured_gpu_uuids: configuredGpuUuids, gpu_identity_status: gpuIdentity,
      observed_placement: s.placement ? node.imageGPU : null,
      observed_image_capabilities: s.placement ? node.image.capabilities : null,
      retirement_status: s.retirement_key ? retired ? "retired" : "unconfirmed" : "not_applicable",
      active_roster: selection !== "dormant" && selection !== "unknown" && !retired,
      selection_conflict: selection === "dormant" && identity === "matched" && native.ready === true,
      observed_model: {
        node_id: observed ? node.node_id : null, service_id: observed?.service_id ?? null,
        model_alias: native.model_alias, deployment_id: native.deployment_id,
        required_gpu_uuids: native.required_gpu_uuids,
        ...observation(native), ready: native.ready,
        admitting: native.admitting, availability: native.availability, functional_qualified: native.functional_qualified,
      },
      type: "service" as const, owner: s.owner,
      configured_capabilities: s.capabilities,
      endpoint_ref: s.endpoint_ref,
      evidence_source: "native-service" as const,
      availability: mismatchReason ? "unavailable" : usable ? native.availability : "unknown",
      reason: mismatchReason ?? native.reason,
      ready: mismatchReason ? false : usable ? s.placement ? native.ready === true && node.image.ready === true : native.ready : null,
      admitting: mismatchReason ? false : usable ? s.placement ? native.admitting === true && node.image.admitting === true : native.admitting : null,
      functional_qualified: usable ? native.functional_qualified : null,
      current_state: retired ? "retired" : selection === "dormant" ? "dormant" : mismatchReason ? "mismatch" : usable ? native.availability : "unknown",
      health: mismatchReason ? "not_ready" : usable ? s.placement ? native.ready === true && node.image.ready === true ? "ready" : "not_ready" : native.ready === true ? "ready" : native.ready === false ? "not_ready" : "unknown" : "unknown",
    };
  });
  const components = registry.components.filter(c => c.node_id === node.node_id).map(c => {
    const facts = c.observation.source === "node_manager" ? node.node_manager :
      c.observation.source === "support" ? node.support.find(s => s.component_id === c.observation.key) : undefined;
    const meta = facts ?? { ...observation(null), reason: "not_observed" };
    let state = "unknown";
    if (facts && current(facts)) {
      if ("running" in facts) state = facts.running === true ? "running" : facts.running === false ? "stopped" : "unknown";
      if ("active_state" in facts) state = facts.active_state === "unknown" ? "unknown" : `${facts.active_state}/${facts.sub_state}`;
    }
    return {
      component_id: c.id, node_id: c.node_id, display_name: c.display_name,
      type: c.type, owner: c.owner, parent_id: c.parent_id,
      independently_restartable: c.independently_restartable,
      ...observation(meta), reason: meta.reason,
      evidence_source: c.observation.source,
      current_state: state,
      // Unit/process state is not a passive API readiness proof, including active/exited oneshots.
      health: state.startsWith("failed/") ? "failed" : "unknown",
      ready: null, actions: [] as string[],
    };
  });
  const gpus = node.gpus.map(gpu => ({
    ...gpu,
    // affected_services is the owner's action impact scope, not a running-model assignment.
    // A dependency join requires fresh matching service/model and measured GPU presence.
    // The node reports required UUIDs, not per-process occupancy. Never rewrite impact IDs.
    observed_ready_dependents: current(node) && current(gpu) ? services.filter(s =>
      s.identity_status === "matched" && s.ready === true &&
      s.observed_model.required_gpu_uuids.includes(gpu.uuid)).map(s => ({
        service_id: s.service_id, node_id: s.node_id, display_name: s.display_name,
        instance_name: s.configured_model!.instance_name,
        model_alias: s.observed_model.model_alias, selection: s.selection,
      })) : [],
  }));
  return { ...node, display_name: config.display_name, selected_frontier: registry.selected_frontier ?? null, services, components, gpus };
}
