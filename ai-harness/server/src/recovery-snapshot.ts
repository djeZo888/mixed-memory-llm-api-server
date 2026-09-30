import { createHash } from "node:crypto";
import type { DatabaseSync } from "node:sqlite";

/** A single named interrupted owner. There is intentionally no bulk selector. */
export interface RecoveryTarget {
  sessionId: string;
  runId: string;
  workspaceId: string;
  threadId: string;
  turnId: string;
  requestIds: string[];
}
const hashPattern = /^[a-f0-9]{64}$/;
export const PHYSICAL_RELEASE_CLEANUP_LABEL = "Owned engine container cleanup confirmed; interrupted work was not replayed";
const identifier = (s: string) => `"${s.replaceAll('"', '""')}"`;
export function hasRecoveryTable(db: DatabaseSync, name: string): boolean {
  return !!db.prepare("SELECT name FROM sqlite_schema WHERE type='table' AND name=?").get(name);
}
function canonical(value: unknown): string {
  if (typeof value === "bigint") return JSON.stringify({ bigint: String(value) });
  if (value instanceof Uint8Array) return JSON.stringify({ blob: Buffer.from(value).toString("base64") });
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value && typeof value === "object") return `{${Object.entries(value).sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0).map(([k, v]) => `${JSON.stringify(k)}:${canonical(v)}`).join(",")}}`;
  return JSON.stringify(value);
}
/** Hash every logical row and schema object, without exporting private DB contents.
 * Caller must hold a read transaction (preflight) or BEGIN IMMEDIATE (apply).
 */
export function recoveryDatabaseSha256(db: DatabaseSync): string {
  const hash = createHash("sha256");
  const schema = db.prepare("SELECT type,name,tbl_name,sql FROM sqlite_schema ORDER BY type,name").all();
  hash.update(canonical(schema));
  for (const table of schema.filter(row => row.type === "table")) {
    const query = db.prepare(`SELECT * FROM ${identifier(String(table.name))}`);
    query.setReadBigInts(true);
    const rows = query.all().map(canonical).sort();
    hash.update(canonical({ table: table.name, rows }));
  }
  return hash.digest("hex");
}
export function validateRecoveryTarget(target: RecoveryTarget): void {
  if (!target || Object.keys(target).sort().join(",") !== "requestIds,runId,sessionId,threadId,turnId,workspaceId" ||
      ![target.sessionId, target.runId, target.workspaceId, target.threadId, target.turnId].every(id => typeof id === "string" && /^[A-Za-z0-9][A-Za-z0-9-]{0,127}$/.test(id)) ||
      !Array.isArray(target.requestIds) || !target.requestIds.length || target.requestIds.length > 32 ||
      !target.requestIds.every(id => typeof id === "string" && /^[A-Za-z0-9][A-Za-z0-9-]{0,127}$/.test(id)) ||
      new Set(target.requestIds).size !== target.requestIds.length)
    throw Error("Invalid exact recovery target");
}
export function recoverySnapshot(db: DatabaseSync, target: RecoveryTarget) {
  validateRecoveryTarget(target);
  const session = db.prepare("SELECT * FROM sessions WHERE id=?").get(target.sessionId);
  const run = db.prepare("SELECT * FROM runs WHERE id=?").get(target.runId);
  const owner = db.prepare("SELECT * FROM h021_session_engines WHERE session_id=?").get(target.sessionId);
  const quarantine = db.prepare("SELECT * FROM quarantined_workspaces WHERE id=?").get(target.workspaceId);
  if (!session || session.workspace_id !== target.workspaceId || session.native_session_id !== target.threadId ||
      session.status !== "interrupted" || session.deleted !== 0 || session.delete_requested !== 0 ||
      !run || run.session_id !== target.sessionId || run.workspace_id !== target.workspaceId || run.status !== "interrupted" ||
      !owner || owner.engine_kind !== "codex" || owner.workspace_id !== target.workspaceId || owner.ownership !== "uncertain" ||
      owner.active_turn_id !== target.turnId || !Number.isSafeInteger(owner.event_cursor) || Number(owner.event_cursor) < 0 || !quarantine)
    throw Error("Interrupted recovery identity/state mismatch");
  if (db.prepare("SELECT id FROM runs WHERE (session_id=? OR workspace_id=?) AND status IN ('queued','running','cancelling') LIMIT 1").get(target.sessionId, target.workspaceId) ||
      db.prepare("SELECT session_id FROM h021_session_engines WHERE workspace_id=? AND session_id!=? AND ownership!='idle' LIMIT 1").get(target.workspaceId, target.sessionId))
    throw Error("Another active owner blocks recovery");
  if (hasRecoveryTable(db, "h003_image_jobs")) {
    for (const row of db.prepare(`SELECT jobs.* FROM h003_image_jobs jobs
      LEFT JOIN sessions ON sessions.id=jobs.session_id
      WHERE jobs.session_id=? OR sessions.workspace_id=?`).all(target.sessionId, target.workspaceId)) {
      const job = JSON.parse(String(row.data))?.job;
      if (!job || job.id !== row.id || job.sessionId !== row.session_id || job.requestId !== row.request_id ||
          !["completed", "failed", "cancelled"].includes(job.state) ||
          ["image_completion_unknown", "server_stopped", "server_restarted"].includes(job.error?.code))
        throw Error("Pending or uncertain image work blocks recovery");
    }
  }
  const requests = db.prepare("SELECT * FROM h021_gateway_requests WHERE session_id=? AND state!='settled' ORDER BY id").all(target.sessionId);
  if (requests.map(r => r.id).sort().join("\0") !== [...target.requestIds].sort().join("\0"))
    throw Error("Exact affected provider request set mismatch");
  for (const row of requests) {
    const request = JSON.parse(String(row.record));
    if (!request || request.id !== row.id || request.sessionId !== row.session_id || request.state !== row.state ||
        !["accepted", "draining", "uncertain"].includes(String(row.state)) ||
        typeof request.lane !== "string" || !request.lane || !Number.isFinite(Date.parse(request.updatedAt)))
      throw Error("Provider request record mismatch");
    if (hasRecoveryTable(db, "h036_released_requests") && db.prepare("SELECT request_id FROM h036_released_requests WHERE request_id=?").get(String(row.id)))
      throw Error("Provider request already has a recovery disposition");
  }
  if (db.prepare("SELECT id FROM events WHERE session_id=? AND run_id=? AND type='done' LIMIT 1").get(target.sessionId, target.runId))
    throw Error("Interrupted run already has a completion disposition");
  return { sha256: recoveryDatabaseSha256(db), target, session, run, owner, quarantine, requests };
}

/** Additive release is authoritative only when its exact original ledger bytes,
 * original owner, interrupted outcome and committed audit events agree. Never
 * reinterpret the original accepted record as a successful provider response.
 */
export function verifiedPhysicalReleaseRequests(db: DatabaseSync): Map<string, string> {
  const released = new Map<string, string>();
  if (!hasRecoveryTable(db, "h036_physical_releases") || !hasRecoveryTable(db, "h036_released_requests")) return released;
  const dispositions = db.prepare("SELECT * FROM h036_physical_releases").all();
  for (const row of dispositions) {
    try {
      const record = JSON.parse(String(row.record));
      const target = record.target as RecoveryTarget;
      validateRecoveryTarget(target);
      if (record.physicalRelease !== true || record.outcome !== "interrupted_unknown" ||
          row.recovery_id !== record.recoveryId || row.session_id !== target.sessionId || row.run_id !== target.runId ||
          row.proof_sha256 !== record.proofSha256 || row.snapshot_sha256 !== record.snapshotSha256 ||
          !hashPattern.test(record.proofSha256) || !hashPattern.test(record.snapshotSha256) ||
          record.priorOwnership?.session_id !== target.sessionId || record.priorOwnership?.workspace_id !== target.workspaceId ||
          record.priorOwnership?.engine_kind !== "codex" || record.priorOwnership?.ownership !== "uncertain" ||
          record.priorOwnership?.active_turn_id !== target.turnId || record.priorSession?.native_session_id !== target.threadId ||
          record.priorRun?.id !== target.runId || record.priorRun?.session_id !== target.sessionId ||
          record.priorRun?.workspace_id !== target.workspaceId || record.priorRun?.status !== "interrupted") continue;
      const run = db.prepare("SELECT status FROM runs WHERE id=? AND session_id=? AND workspace_id=?").get(target.runId, target.sessionId, target.workspaceId);
      if (run?.status !== "interrupted") continue;
      const session = db.prepare("SELECT workspace_id,native_session_id FROM sessions WHERE id=?").get(target.sessionId);
      const owner = db.prepare("SELECT engine_kind,workspace_id FROM h021_session_engines WHERE session_id=?").get(target.sessionId);
      if (session?.workspace_id !== target.workspaceId || session?.native_session_id !== target.threadId ||
          owner?.engine_kind !== "codex" || owner?.workspace_id !== target.workspaceId) continue;
      const events = db.prepare("SELECT type,data FROM events WHERE session_id=? AND run_id=? AND type IN ('done','progress')").all(target.sessionId, target.runId);
      const matching = events.filter(event => {
        const data = JSON.parse(String(event.data));
        return data.recoveryId === record.recoveryId && data.physicalRelease === true &&
          data.outcome === "interrupted_unknown" && data.proofSha256 === record.proofSha256 &&
          (event.type === "done" ? data.runId === target.runId : data.kind === "cleanup" && data.label === PHYSICAL_RELEASE_CLEANUP_LABEL);
      });
      if (!matching.some(event => event.type === "done") || !matching.some(event => event.type === "progress")) continue;
      const requests = db.prepare(`SELECT released.request_id,released.original_record,current.session_id,current.state,current.record
        FROM h036_released_requests released LEFT JOIN h021_gateway_requests current ON current.id=released.request_id
        WHERE released.recovery_id=? ORDER BY released.request_id`).all(String(row.recovery_id));
      if (requests.map(r => r.request_id).sort().join("\0") !== [...target.requestIds].sort().join("\0") ||
          requests.some(r => {
            const original = JSON.parse(String(r.original_record));
            return r.session_id !== target.sessionId || r.original_record !== r.record || original.id !== r.request_id ||
              original.sessionId !== target.sessionId || original.state !== r.state || !["accepted", "draining", "uncertain"].includes(original.state);
          })) continue;
      for (const request of requests) released.set(String(request.request_id), target.sessionId);
    } catch { /* Malformed/incomplete disposition retains original uncertainty. */ }
  }
  return released;
}
