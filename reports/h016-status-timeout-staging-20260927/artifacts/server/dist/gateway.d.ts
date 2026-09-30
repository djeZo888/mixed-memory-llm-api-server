import { MIMO_MODEL } from "./mimo.js";
import { type MimoFrontierOptions } from "./mimo-frontier.js";
import { FRONTIER_MODEL, type FrontierOptions } from "./frontier.js";
import type { ImageBroker } from "./image-broker.js";
import { type AvailabilityProvider, type ServiceAvailability } from "./service-availability.js";
import { type FastifyInstance } from "fastify";
import { type GatewayUsage } from "./contracts.js";
/** Per-dispatched-request elapsed budget; queue/count retain their own limits. */
export declare function activeRequestTimeoutMs(model: string, override?: number): number;
export interface GatewayUpstream {
    url: string;
    alias: string;
}
export interface GatewayOptions {
    frontier?: FrontierOptions | MimoFrontierOptions;
    /** Actual selected identity even when qualification fails; never fallback. */
    selectedFrontierModel?: typeof FRONTIER_MODEL | typeof MIMO_MODEL;
    /** Latest unresolved durable request owner, retained across profile changes. */
    initialFrontierOwnerModel?: string;
    images?: ImageBroker;
    dispatchHeld?: (alias: string) => boolean;
    /** Local cached observation only; unknown preserves existing admission behavior. */
    availability?: AvailabilityProvider;
    /** The protected credential is supplied by the host. This module never reads files. */
    upstreamKey: string | (() => string | Promise<string>);
    /** Deployment uses the fixed defaults; overrides permit local protocol fixtures. */
    upstreams?: readonly [GatewayUpstream, GatewayUpstream];
    onUsage?: (usage: GatewayUsage) => void;
    queueLimit?: number;
    /** Aggregate serialized request-body bytes waiting for a lane; default 128 MiB. */
    queueByteLimit?: number;
    queueTimeoutMs?: number;
    activeTimeoutMs?: number;
    /** Durable host ledger; previous active requests recover quarantined. */
    initialLaneStates?: Readonly<Record<string, LaneState>>;
    /** Must durably commit synchronously. Admission records active before dispatch. */
    onLaneState?: (alias: string, state: LaneState) => void;
}
export type LaneState = "idle" | "active" | "quarantined";
export interface Gateway {
    app: FastifyInstance;
    issueToken(sessionId: string): string;
    revokeToken(token: string): void;
    snapshot(): {
        queued: number;
        queuedBytes: number;
        lanes: {
            alias: string;
            state: LaneState;
            availability: ServiceAvailability;
        }[];
    };
    frontierSnapshot(): {
        model: string;
        contextWindow: number | null;
        configured: boolean;
        provider: "glm" | "mimo";
        maxOutputTokens: number | null;
        capacity: {
            published: number;
            configured: number | null;
            allocated: number | null;
            occupiedTested: number | null;
        };
        queued: number;
        state: LaneState | "unavailable";
        availability: ServiceAvailability;
    };
    /** Publish cache changes promptly without touching active request settlement. */
    notifyAvailabilityChanged(): void;
    reconcileAfterOwnerSettlement(aliases: string[]): boolean;
    close(): Promise<void>;
}
export declare function createGateway(options: GatewayOptions): Gateway;
