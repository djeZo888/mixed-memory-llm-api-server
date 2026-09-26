/** Trusted release configuration. Inventory never confers execution/action authority. */
import { isIPv4 } from "node:net";
import { readFileSync } from "node:fs";
import { NODE_IDS, SERVICE_IDS, type NodeId } from "./node-contract.js";

export type RegistryNode = {
  id: string;
  display_name: string;
  observation: { adapter: "node-v1" | "unsupported"; transport: string | null };
};
export type RegistryService = {
  id: string;
  node_id: string;
  display_name: string;
  observation_key: string;
  owner: string;
  capabilities: string[];
  endpoint_ref: string | null;
};
export type RegistryComponent = {
  id: string;
  node_id: string;
  display_name: string;
  type: "support" | "capability" | "task-capability";
  owner: string;
  parent_id: string | null;
  independently_restartable: boolean;
  observation: { source: "node_manager" | "support" | "none"; key: string | null };
};
export type RegistryTransport = {
  id: string;
  kind: "private-http" | "local-helper";
  host: string | null;
  port: number | null;
  socket_path: string | null;
  credential_ref: string | null;
};
export type RegistryCredential = { id: string; systemd_credential: string };
export type SystemRegistry = {
  schema_version: 1;
  credentials: RegistryCredential[];
  transports: RegistryTransport[];
  nodes: RegistryNode[];
  services: RegistryService[];
  components: RegistryComponent[];
};
export const isActionNode = (id: string): id is NodeId =>
  (NODE_IDS as readonly string[]).includes(id);
const fail = (): never => { throw Error("Invalid system registry"); };
function object(value: unknown, keys: string[]): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) return fail();
  const v = value as Record<string, unknown>;
  if (Object.keys(v).length !== keys.length || keys.some(k => !Object.hasOwn(v, k))) return fail();
  return v;
}
const id = (v: unknown): string => typeof v === "string" && /^[a-z][a-z0-9_.-]{0,63}$/.test(v) && !["constructor", "prototype", "__proto__"].includes(v) ? v : fail();
const label = (v: unknown): string => typeof v === "string" && /^[\x20-\x7e]{1,120}$/.test(v) ? v : fail();
function list<T>(v: unknown, max: number, parse: (x: unknown) => T): T[] {
  if (!Array.isArray(v) || v.length > max) return fail();
  return v.map(parse);
}
function unique(values: string[]) { if (new Set(values).size !== values.length) fail(); }
const endpointRefs = ["frontier-private", "qwen-gpu0-private", "qwen-gpu1-private", "image-private", "control-private", "harness-local", "search-local", "status-uds"];
export function validateSystemRegistry(raw: unknown): SystemRegistry {
  const v = object(raw, ["schema_version", "credentials", "transports", "nodes", "services", "components"]);
  if (v.schema_version !== 1) fail();
  const credentials = list(v.credentials, 16, entry => {
    const c = object(entry, ["id", "systemd_credential"]);
    const credentialId = id(c.id);
    if (credentialId === "control-api-key") {
      if (c.systemd_credential !== "control-api-key") fail();
    } else if (typeof c.systemd_credential !== "string" || !/^node-[a-z0-9][a-z0-9-]{0,55}$/.test(c.systemd_credential)) fail();
    return { id: credentialId, systemd_credential: c.systemd_credential as string };
  });
  unique(credentials.map(c => c.id)); unique(credentials.map(c => c.systemd_credential));
  const transports = list(v.transports, 16, entry => {
    const t = object(entry, ["id", "kind", "host", "port", "socket_path", "credential_ref"]);
    const transportId = id(t.id);
    if (t.kind === "private-http") {
      if (typeof t.host !== "string" || !isIPv4(t.host)) fail();
      const parts = (t.host as string).split(".").map(Number);
      const privateHost = parts[0] === 10 || (parts[0] === 172 && parts[1] >= 16 && parts[1] <= 31) || (parts[0] === 192 && parts[1] === 168) || t.host === "127.0.0.1";
      if (!privateHost || !Number.isInteger(t.port) || Number(t.port) < 1 || Number(t.port) > 65535 || t.socket_path !== null || !credentials.some(c => c.id === t.credential_ref)) fail();
      if (t.credential_ref === "control-api-key" && (transportId !== "ai-vm-private" || t.host !== "10.156.100.60" || t.port !== 30008)) fail();
    } else if (t.kind !== "local-helper" || transportId !== "local-helper" || t.host !== null || t.port !== null || t.socket_path !== "/run/ai-harness-admin/helper.sock" || t.credential_ref !== null) fail();
    return { id: transportId, kind: t.kind, host: t.host, port: t.port, socket_path: t.socket_path, credential_ref: t.credential_ref } as RegistryTransport;
  });
  unique(transports.map(t => t.id));
  unique(transports.filter(t => t.credential_ref !== null).map(t => t.credential_ref!));
  const nodes = list(v.nodes, 16, entry => {
    const n = object(entry, ["id", "display_name", "observation"]);
    const o = object(n.observation, ["adapter", "transport"]);
    const nodeId = id(n.id);
    if (o.adapter === "unsupported") { if (o.transport !== null) fail(); }
    else {
      if (o.adapter !== "node-v1") fail();
      const transport = transports.find(t => t.id === o.transport);
      if (!transport || (transport.kind === "local-helper" && nodeId !== "ai-harness")) return fail();
      // Existing action clients remain pinned to these exact reviewed owners.
      // A generic node can never receive the existing administration credential.
      if (transport.credential_ref === "control-api-key" && nodeId !== "ai-vm") fail();
      if (nodeId === "ai-vm" && (transport.kind !== "private-http" || transport.host !== "10.156.100.60" || transport.port !== 30008 || transport.credential_ref !== "control-api-key")) fail();
      if (nodeId === "ai-harness" && transport.kind !== "local-helper") fail();
    }
    return { id: nodeId, display_name: label(n.display_name), observation: { adapter: o.adapter, transport: o.transport } } as RegistryNode;
  });
  if (!nodes.length) fail();
  unique(nodes.map(n => n.id));
  const services = list(v.services, 128, entry => {
    const s = object(entry, ["id", "node_id", "display_name", "observation_key", "owner", "capabilities", "endpoint_ref"]);
    if (s.endpoint_ref !== null && !endpointRefs.includes(s.endpoint_ref as string)) fail();
    const capabilities = list(s.capabilities, 32, id); unique(capabilities);
    return { id: id(s.id), node_id: id(s.node_id), display_name: label(s.display_name), observation_key: id(s.observation_key), owner: label(s.owner), capabilities, endpoint_ref: s.endpoint_ref } as RegistryService;
  });
  const components = list(v.components, 128, entry => {
    const c = object(entry, ["id", "node_id", "display_name", "type", "owner", "parent_id", "independently_restartable", "observation"]);
    const o = object(c.observation, ["source", "key"]);
    if (!["support", "capability", "task-capability"].includes(c.type as string) || typeof c.independently_restartable !== "boolean") fail();
    if (c.type !== "support" && (c.independently_restartable !== false || c.parent_id === null)) fail();
    if (o.source === "none" || o.source === "node_manager") { if (o.key !== null) fail(); }
    else if (o.source !== "support" || !["nginx", "admin", "egress", "task-slice"].includes(o.key as string)) fail();
    if ((o.source === "support" && c.node_id !== "ai-harness") || (o.source === "node_manager" && c.node_id !== "ai-vm") || (c.type !== "support" && o.source !== "none")) fail();
    return { id: id(c.id), node_id: id(c.node_id), display_name: label(c.display_name), type: c.type, owner: label(c.owner), parent_id: c.parent_id === null ? null : id(c.parent_id), independently_restartable: c.independently_restartable, observation: { source: o.source, key: o.key } } as RegistryComponent;
  });
  unique([...services, ...components].map(s => s.id));
  for (const entry of [...services, ...components]) if (!nodes.some(n => n.id === entry.node_id)) fail();
  for (const n of nodes) {
    unique(services.filter(s => s.node_id === n.id).map(s => s.observation_key));
    unique(components.filter(c => c.node_id === n.id && c.observation.source !== "none").map(c => `${c.observation.source}:${c.observation.key}`));
  }
  for (const c of components) {
    const visited = new Set([c.id]); let parent = c.parent_id;
    while (parent !== null) {
      if (visited.has(parent)) fail(); visited.add(parent);
      const p = [...services, ...components].find(s => s.id === parent && s.node_id === c.node_id);
      if (!p) return fail();
      parent = "parent_id" in p ? p.parent_id : null;
    }
  }
  // The seven existing action identities cannot be relabelled onto another owner.
  for (const nodeId of NODE_IDS) for (const serviceId of SERVICE_IDS[nodeId]) {
    const s = services.find(s => s.id === serviceId);
    if (s && (s.node_id !== nodeId || s.observation_key !== serviceId)) fail();
    if (services.some(s => s.id !== serviceId && s.node_id === nodeId && s.observation_key === serviceId)) fail();
  }
  return { schema_version: 1, credentials, transports, nodes, services, components };
}
export function loadSystemRegistry(): SystemRegistry {
  // Fixed path relative to source/dist, shipped and reviewed with the release.
  // No request parameter, browser endpoint, environment URL or credential path.
  const text = readFileSync(new URL("../../config/system-registry.json", import.meta.url), "utf8");
  if (Buffer.byteLength(text) > 128 * 1024) fail();
  return validateSystemRegistry(JSON.parse(text));
}
