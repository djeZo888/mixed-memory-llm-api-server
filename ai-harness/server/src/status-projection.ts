import { observation, sanitizeNode, type NodeSnapshot } from "./node-contract.js";
import type { RegistryNode, SystemRegistry } from "./system-registry.js";

const current = (o: { state: string; freshness: string }) => o.state === "ok" && o.freshness === "fresh";
/** Join expectations after sanitizing and aging native facts. No parent health inheritance. */
export function projectNode(node: NodeSnapshot, config: RegistryNode, registry: SystemRegistry) {
  const services = registry.services.filter(s => s.node_id === node.node_id).map(s => {
    const native = node.services.find(n => n.service_id === s.observation_key) ??
      sanitizeNode({ schema_version: 1, node_id: node.node_id, services: [{ service_id: s.observation_key, reason: "not_observed" }] }, node.node_id, [s.observation_key]).services[0]!;
    return {
      ...native, service_id: s.id, node_id: s.node_id, display_name: s.display_name,
      type: "service" as const, owner: s.owner,
      configured_capabilities: s.capabilities,
      endpoint_ref: s.endpoint_ref,
      evidence_source: "native-service" as const,
      current_state: current(native) ? native.availability : "unknown",
      health: current(native) ? native.ready === true ? "ready" : native.ready === false ? "not_ready" : "unknown" : "unknown",
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
  return { ...node, display_name: config.display_name, services, components };
}
