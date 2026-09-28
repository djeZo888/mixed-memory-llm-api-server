import { observation, sanitizeNode, type NodeSnapshot } from "./node-contract.js";
import type { RegistryNode, SystemRegistry } from "./system-registry.js";

const current = (o: { state: string; freshness: string }) => o.state === "ok" && o.freshness === "fresh";
/** Join expectations after sanitizing and aging native facts. No parent health inheritance. */
export function projectNode(node: NodeSnapshot, config: RegistryNode, registry: SystemRegistry) {
  const services = registry.services.filter(s => s.node_id === node.node_id).map(s => {
    const native = node.services.find(n => n.service_id === s.observation_key) ??
      sanitizeNode({ schema_version: 1, node_id: node.node_id, services: [{ service_id: s.observation_key, reason: "not_observed" }] }, node.node_id, [s.observation_key]).services[0]!;
    const selection = s.model?.selection_group === "frontier"
      ? registry.selected_frontier === undefined ? "unknown"
        : s.model.expected_alias === registry.selected_frontier ? "selected" : "dormant"
      : "not_applicable";
    const identity = !s.model ? "not_applicable"
      : native.freshness === "stale" || node.freshness === "stale" ? "stale"
      : !current(node) || !current(native) ? "unavailable"
      : native.model_alias === null ? "unknown"
      : native.model_alias === s.model.expected_alias ? "matched" : "mismatch";
    const usable = current(node) && current(native) &&
      (identity === "matched" || identity === "not_applicable") &&
      selection !== "dormant" && selection !== "unknown";
    return {
      ...native, service_id: s.id, node_id: s.node_id, display_name: s.display_name,
      configured_model: s.model ?? null, selection, identity_status: identity,
      observed_model: {
        node_id: node.node_id, service_id: native.service_id,
        model_alias: native.model_alias, deployment_id: native.deployment_id,
        required_gpu_uuids: native.required_gpu_uuids,
        ...observation(native), ready: native.ready,
      },
      type: "service" as const, owner: s.owner,
      configured_capabilities: s.capabilities,
      endpoint_ref: s.endpoint_ref,
      evidence_source: "native-service" as const,
      ready: usable ? native.ready : null,
      admitting: usable ? native.admitting : null,
      current_state: selection === "dormant" ? "dormant" : identity === "mismatch" ? "mismatch" : usable ? native.availability : "unknown",
      health: usable ? native.ready === true ? "ready" : native.ready === false ? "not_ready" : "unknown" : "unknown",
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
      s.identity_status === "matched" && s.observed_model.ready === true &&
      s.observed_model.required_gpu_uuids.includes(gpu.uuid)).map(s => ({
        service_id: s.service_id, node_id: s.node_id, display_name: s.display_name,
        instance_name: s.configured_model!.instance_name,
        model_alias: s.observed_model.model_alias, selection: s.selection,
      })) : [],
  }));
  return { ...node, display_name: config.display_name, selected_frontier: registry.selected_frontier ?? null, services, components, gpus };
}
