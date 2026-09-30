import { randomUUID } from "node:crypto";
import type { DatabaseSync } from "node:sqlite";
import { verifiedPhysicalReleaseRequests } from "./recovery-snapshot.js";
export type RequestOwnershipState = "queued" | "counting" | "accepted" | "draining" | "uncertain" | "settled";
export interface RequestOwnership {
    id: string;
    sessionId: string;
    state: RequestOwnershipState;
    lane?: string;
    updatedAt: string;
    accounting?: { inputTokens?: number; reservedOutputTokens?: number; promptTokens?: number; completionTokens?: number };
}
export interface SettlementQuery {
    sessionId: string;
    nativeThreadId?: string;
    activeTurnId?: string | null;
}
export interface OwnershipOptions {
    /** True only after a durable ledger has been opened and all prior records loaded. */
    recoveryReady: boolean;
    initialRequests?: readonly RequestOwnership[];
    /** Sessions with a committed physical-release disposition, retaining unknown outcome. */
    physicallyReleasedSessions?: readonly string[];
    /** Synchronous durable commit. No token or credentials are recorded. */
    onRequestState: (record: RequestOwnership) => void;
}
/** Session lineage outlives token revocation and socket/native lifetimes. */
export class GatewayOwnership {
    private records = new Map<string, RequestOwnership>();
    private knownSessions = new Set<string>();
    private failed = false;
    private settlementObservers = new Set<() => void>();
    constructor(private options?: OwnershipOptions) { for (const id of options?.physicallyReleasedSessions ?? []) this.knownSessions.add(id); for (const r of options?.initialRequests ?? []) {
        if (!r.id || !r.sessionId || !["queued", "counting", "accepted", "draining", "uncertain", "settled"].includes(r.state))
            throw Error("Invalid ownership ledger");
        this.knownSessions.add(r.sessionId);
        if (r.state !== "settled")
            this.records.set(r.id, { ...r, state: "uncertain" });
    } }
    registerSession(sessionId: string) { this.knownSessions.add(sessionId); }
    begin(sessionId: string): RequestOwnership { this.registerSession(sessionId); const r: RequestOwnership = { id: randomUUID(), sessionId, state: "queued", updatedAt: new Date().toISOString() }; this.records.set(r.id, r); this.write(r); return r; }
    transition(r: RequestOwnership, state: RequestOwnershipState, lane?: string) { r.state = state; if (lane)
        r.lane = lane; r.updatedAt = new Date().toISOString(); this.write(r); if (state === "settled")
        this.records.delete(r.id);
        for (const observe of this.settlementObservers) observe(); }
    account(r: RequestOwnership, value: NonNullable<RequestOwnership['accounting']>) {
        r.accounting = { ...r.accounting, ...value }; this.write(r);
    }
    private write(r: RequestOwnership) { try {
        this.options?.onRequestState({ ...r });
    }
    catch {
        r.state = "uncertain";
        this.failed = true;
        for (const observe of this.settlementObservers) observe();
        throw Error("Gateway ownership ledger unavailable");
    } }
    confirm(query: SettlementQuery): boolean { return this.options?.recoveryReady === true && !this.failed && this.knownSessions.has(query.sessionId) && ![...this.records.values()].some(r => r.sessionId === query.sessionId); }
    /** Observe durable drain only; caller must first stop native producers and revoke admission.
     * Numeric budgets preserve the bounded proof API; a host signal observes the
     * existing request lifecycle and stops false on shutdown. Neither releases work.
     * No request replay, lane release or uncertain-record reconciliation happens here.
     */
    waitForSettlement(query: SettlementQuery, budget: number | AbortSignal): Promise<boolean> {
        const waitMs = typeof budget === "number" ? budget : undefined;
        const signal = typeof budget === "number" ? undefined : budget;
        if (waitMs !== undefined && (!Number.isSafeInteger(waitMs) || waitMs < 0 || waitMs > 15000))
            throw Error("Invalid settlement observation budget");
        const unavailable = () => this.options?.recoveryReady !== true || this.failed ||
            !this.knownSessions.has(query.sessionId) ||
            [...this.records.values()].some(r => r.sessionId === query.sessionId && r.state === "uncertain");
        if (signal?.aborted || unavailable()) return Promise.resolve(false);
        if (this.confirm(query)) return Promise.resolve(true);
        if (waitMs === 0) return Promise.resolve(false);
        return new Promise(resolve => {
            const finish = (settled: boolean) => {
                clearTimeout(timer);
                signal?.removeEventListener("abort", stopped);
                this.settlementObservers.delete(observe);
                resolve(settled);
            };
            const observe = () => {
                if (this.confirm(query)) finish(true);
                else if (unavailable()) finish(false);
            };
            const stopped = () => finish(false);
            // Signal-bound Codex observation uses existing request/queue deadlines.
            // Those owners publish uncertain on expiry; observation has no second timer.
            const timer = waitMs === undefined ? undefined : setTimeout(stopped, waitMs);
            this.settlementObservers.add(observe);
            signal?.addEventListener("abort", stopped, { once: true });
        });
    }
    snapshot(sessionId: string) { return [...this.records.values()].filter(r => r.sessionId === sessionId).map(r => ({ ...r })); }
}
/** Additive table; old releases and existing lane/frontier ledgers remain intact. */
export class GatewayOwnershipLedger {
    constructor(private db: DatabaseSync) { db.exec("CREATE TABLE IF NOT EXISTS h021_gateway_requests(id TEXT PRIMARY KEY, session_id TEXT NOT NULL, state TEXT NOT NULL, record TEXT NOT NULL)"); }
    options(): OwnershipOptions {
        const released = verifiedPhysicalReleaseRequests(this.db);
        // Preserve historical settled rows as opaque retained evidence, exactly
        // as before recovery support. Only unresolved owners enter this ledger.
        const requests = this.db.prepare("SELECT * FROM h021_gateway_requests WHERE state!='settled'").all().map(row => {
            const record = JSON.parse(String(row.record)) as RequestOwnership;
            if (record.id !== row.id || record.sessionId !== row.session_id || record.state !== row.state ||
                !["queued", "counting", "accepted", "draining", "uncertain", "settled"].includes(record.state))
                throw Error("Invalid ownership ledger row binding");
            return record;
        });
        return {
            recoveryReady: true,
            physicallyReleasedSessions: [...new Set(released.values())],
            initialRequests: requests.filter(record => !released.has(record.id)),
            onRequestState: (record) => {
                // A released request is immutable historical evidence. A new
                // explicit turn receives a new request ID through begin().
                if (released.has(record.id)) throw Error("Released provider request cannot be rewritten");
                this.db.prepare("INSERT OR REPLACE INTO h021_gateway_requests VALUES(?,?,?,?)").run(record.id, record.sessionId, record.state, JSON.stringify(record));
            },
        };
    }
}
