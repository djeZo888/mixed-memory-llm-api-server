import { type NodeId } from "./node-contract.js";
export type RegistryNode = {
    id: string;
    display_name: string;
    observation: {
        adapter: "node-v1" | "unsupported";
        transport: string | null;
    };
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
    observation: {
        source: "node_manager" | "support" | "none";
        key: string | null;
    };
};
export type RegistryTransport = {
    id: string;
    kind: "private-http" | "local-helper";
    host: string | null;
    port: number | null;
    socket_path: string | null;
    credential_ref: string | null;
};
export type RegistryCredential = {
    id: string;
    systemd_credential: string;
};
export type SystemRegistry = {
    schema_version: 1;
    credentials: RegistryCredential[];
    transports: RegistryTransport[];
    nodes: RegistryNode[];
    services: RegistryService[];
    components: RegistryComponent[];
};
export declare const isActionNode: (id: string) => id is NodeId;
export declare function validateSystemRegistry(raw: unknown): SystemRegistry;
/** Inventory retains both identities; selection never creates another queue or readiness. */
export declare function selectRegistryFrontier(registry: SystemRegistry, model: string): SystemRegistry;
export declare function loadSystemRegistry(): SystemRegistry;
