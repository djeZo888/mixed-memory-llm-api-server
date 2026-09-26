import type { DatabaseSync } from "node:sqlite";
import type { FrontierRecord } from "./frontier.js";
/** Content-free ownership journal in the existing protected harness database. */
export class FrontierLedger {
  constructor(private db: DatabaseSync) {
    db.exec(`CREATE TABLE IF NOT EXISTS frontier_requests(
      id TEXT PRIMARY KEY, session_id TEXT NOT NULL, state TEXT NOT NULL,
      updated_at TEXT NOT NULL, value TEXT NOT NULL);
      CREATE INDEX IF NOT EXISTS frontier_requests_by_session ON frontier_requests(session_id,updated_at DESC);
      UPDATE frontier_requests SET state='quarantined', value=json_set(value,'$.state','quarantined') WHERE state='active';
      UPDATE frontier_requests SET state='cancelled', value=json_set(value,'$.state','cancelled') WHERE state='queued';`);
    // Recovery never dispatches a request. The separate durable lane ledger
    // also restores active/quarantined frontier ownership as quarantined.
  }
  record(record: FrontierRecord): void {
    this.db
      .prepare("INSERT OR REPLACE INTO frontier_requests VALUES(?,?,?,?,?)")
      .run(
        record.id,
        record.sessionId,
        record.state,
        record.updatedAt,
        JSON.stringify(record),
      );
  }
  latest(sessionId: string): FrontierRecord[] {
    return this.db
      .prepare(
        "SELECT value FROM frontier_requests WHERE session_id=? ORDER BY updated_at DESC LIMIT 8",
      )
      .all(sessionId)
      .map((row) => JSON.parse(String(row.value)) as FrontierRecord);
  }
}
