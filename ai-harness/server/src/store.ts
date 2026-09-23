import { DatabaseSync } from "node:sqlite";
import { randomUUID } from "node:crypto";
import { EventEmitter } from "node:events";
import type {
  Session,
  Status,
  Context,
  Message,
  Event,
  Artifact,
  Attachment,
  MessagePhase,
  Activity,
  RunSnapshot,
  SubagentSummary,
} from "./contracts.js";
import { CONTEXT_LIMIT, unknownSubagents } from "./contracts.js";
import { environment } from "./locale.js";
import { imageMime, safeStorageName, displayName } from "./file-metadata.js";
import { ApiError } from "./errors.js";

export interface StoredSession extends Session {
  workspaceId: string;
  nativeSessionId?: string;
  deleted: boolean;
  deleteRequested: boolean;
}
export interface Run {
  id: string;
  sessionId: string;
  workspaceId: string;
  kind: "message" | "handoff";
  text: string;
  attachmentIds: string[];
  status: string;
}
export interface FileRecord {
  image?: import("./image-contracts.js").ImageMetadata;
  id: string;
  sessionId: string;
  kind: "attachment" | "artifact";
  path: string;
  name: string;
  mimeType: string;
  size: number;
  runId?: string | null;
  messageId?: string | null;
}
const now = () => new Date().toISOString();
const decode = <T>(v: unknown): T => JSON.parse(String(v));
export class Store {
  readonly db: DatabaseSync;
  readonly events = new EventEmitter();
  constructor(path: string) {
    this.events.setMaxListeners(0);
    this.db = new DatabaseSync(path);
    this.db
      .exec(`PRAGMA journal_mode=WAL; PRAGMA foreign_keys=ON; PRAGMA busy_timeout=5000;
   CREATE TABLE IF NOT EXISTS handoffs(session_id TEXT PRIMARY KEY,summary TEXT NOT NULL,delivered INTEGER NOT NULL DEFAULT 0);
   CREATE TABLE IF NOT EXISTS quarantined_workspaces(id TEXT PRIMARY KEY, reason TEXT NOT NULL);
   CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY,title TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,status TEXT NOT NULL,context TEXT NOT NULL,workspace_id TEXT NOT NULL,native_session_id TEXT,deleted INTEGER NOT NULL DEFAULT 0,delete_requested INTEGER NOT NULL DEFAULT 0);
   CREATE TABLE IF NOT EXISTS messages(id TEXT PRIMARY KEY,session_id TEXT NOT NULL REFERENCES sessions(id),role TEXT NOT NULL,content TEXT NOT NULL,created_at TEXT NOT NULL,run_id TEXT,attachment_ids TEXT NOT NULL);
   CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY,session_id TEXT NOT NULL REFERENCES sessions(id),workspace_id TEXT NOT NULL,kind TEXT NOT NULL,text TEXT NOT NULL,attachment_ids TEXT NOT NULL,status TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
   CREATE TABLE IF NOT EXISTS events(session_id TEXT NOT NULL REFERENCES sessions(id),id INTEGER NOT NULL,type TEXT NOT NULL,run_id TEXT,created_at TEXT NOT NULL,data TEXT NOT NULL,PRIMARY KEY(session_id,id));
   CREATE TABLE IF NOT EXISTS files(id TEXT PRIMARY KEY,session_id TEXT NOT NULL REFERENCES sessions(id),kind TEXT NOT NULL,path TEXT NOT NULL,name TEXT NOT NULL,mime_type TEXT NOT NULL,size INTEGER NOT NULL,UNIQUE(session_id,kind,path));
   CREATE INDEX IF NOT EXISTS messages_session ON messages(session_id,created_at);
   CREATE INDEX IF NOT EXISTS events_session ON events(session_id,id);`);
    // Companion tables preserve old release positional INSERT compatibility on rollback.
    this.db.exec(`
      CREATE TABLE IF NOT EXISTS h003_image_outputs(workspace_id TEXT NOT NULL,path TEXT NOT NULL,job_id TEXT NOT NULL,PRIMARY KEY(workspace_id,path));
      CREATE TABLE IF NOT EXISTS h003_image_file_meta(file_id TEXT PRIMARY KEY REFERENCES files(id) ON DELETE CASCADE,data TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS h003_run_image_refs(run_id TEXT PRIMARY KEY REFERENCES runs(id),data TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS h002_message_meta(message_id TEXT PRIMARY KEY REFERENCES messages(id) ON DELETE CASCADE,data TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS h002_file_refs(file_id TEXT PRIMARY KEY REFERENCES files(id) ON DELETE CASCADE,run_id TEXT,message_id TEXT);
      CREATE TABLE IF NOT EXISTS h002_file_names(file_id TEXT PRIMARY KEY REFERENCES files(id) ON DELETE CASCADE,display_name TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS h002_activities(session_id TEXT NOT NULL,run_id TEXT NOT NULL,id TEXT NOT NULL,data TEXT NOT NULL,PRIMARY KEY(run_id,id));
      CREATE TABLE IF NOT EXISTS h002_subagents(run_id TEXT PRIMARY KEY,data TEXT NOT NULL);
    `);
    this.recoverLegacyFiles();
    this.recoverLegacyActivities();
    // A process restart never replays a queued prompt or a tool effect.
    this.db.exec("BEGIN IMMEDIATE");
    try {
      const interrupted = this.db
        .prepare(
          "SELECT DISTINCT session_id FROM runs WHERE status IN ('queued','running','cancelling')",
        )
        .all() as { session_id: string }[];
      const interruptedRuns = this.db
        .prepare(
          "SELECT id FROM runs WHERE status IN ('queued','running','cancelling')",
        )
        .all();
      this.db
        .prepare(
          "UPDATE runs SET status='interrupted',updated_at=? WHERE status IN ('queued','running','cancelling')",
        )
        .run(now());
      for (const run of interruptedRuns) this.emitRun(String(run.id));
      for (const r of interrupted) {
        this.quarantine(
          this.getSession(r.session_id, true).workspaceId,
          "restart_during_run",
        );
        this.setStatus(r.session_id, "interrupted");
        this.markContextStale(r.session_id);
        this.emit(r.session_id, "error", {
          code: "interrupted",
          message:
            "Server restarted; the run was interrupted and was not replayed",
        });
      }
      this.db.exec("COMMIT");
    } catch (error) {
      this.db.exec("ROLLBACK");
      throw error;
    }
    // A restarted server cannot prove that an external launcher/container settled.
    // Keep pending deletions visible until a fresh explicit cancel confirms settlement.
  }
  quarantine(workspaceId: string, reason: string) {
    this.db
      .prepare("INSERT OR REPLACE INTO quarantined_workspaces VALUES(?,?)")
      .run(workspaceId, reason);
  }
  releaseQuarantineAfterVerifiedCleanup(workspaceId: string) {
    this.db
      .prepare("DELETE FROM quarantined_workspaces WHERE id=?")
      .run(workspaceId);
  }
  isQuarantined(workspaceId: string) {
    return !!this.db
      .prepare("SELECT id FROM quarantined_workspaces WHERE id=?")
      .get(workspaceId);
  }
  close() {
    this.db.close();
    this.events.removeAllListeners();
  }
  createSession(workspaceId: string = randomUUID()): StoredSession {
    const id = randomUUID(),
      time = now();
    const context: Context = {
      used: 0,
      limit: CONTEXT_LIMIT,
      estimated: false,
      stale: false,
      source: "empty",
      updatedAt: time,
    };
    this.db
      .prepare(
        "INSERT INTO sessions(id,title,created_at,updated_at,status,context,workspace_id) VALUES(?,?,?,?,?,?,?)",
      )
      .run(
        id,
        "New chat",
        time,
        time,
        "idle",
        JSON.stringify(context),
        workspaceId,
      );
    return this.getSession(id);
  }
  getSession(id: string, includeDeleted = false): StoredSession {
    const r = this.db.prepare("SELECT * FROM sessions WHERE id=?").get(id) as
      | Record<string, unknown>
      | undefined;
    if (!r || (r.deleted && !includeDeleted))
      throw new ApiError(404, "not_found", "Session not found");
    return {
      id: String(r.id),
      title: String(r.title),
      createdAt: String(r.created_at),
      updatedAt: String(r.updated_at),
      status: r.status as Status,
      context: decode(r.context),
      workspaceId: String(r.workspace_id),
      nativeSessionId: r.native_session_id
        ? String(r.native_session_id)
        : undefined,
      deleted: !!r.deleted,
      deleteRequested: !!r.delete_requested,
    };
  }
  publicSession(s: StoredSession): Session {
    const {
      workspaceId,
      nativeSessionId,
      deleted,
      deleteRequested,
      ...result
    } = s;
    return result;
  }
  listSessions(): Session[] {
    return (
      this.db
        .prepare(
          "SELECT id FROM sessions WHERE deleted=0 ORDER BY updated_at DESC,rowid DESC",
        )
        .all() as { id: string }[]
    ).map((r) => this.publicSession(this.getSession(r.id)));
  }
  snapshot(id: string) {
    this.db.exec("BEGIN");
    try {
      const result = {
        session: this.publicSession(this.getSession(id)),
        messages: this.messages(id),
        events: this.allEvents(id),
        artifacts: this.files(id, "artifact").map((f) => this.publicFile(f)),
        attachments: this.files(id, "attachment").map((f) =>
          this.publicFile(f),
        ),
        runs: this.runs(id),
        watermark: Number(
          this.db
            .prepare(
              "SELECT COALESCE(MAX(id),0) AS value FROM events WHERE session_id=?",
            )
            .get(id)!.value,
        ),
        environment: environment(),
        activities: this.activities(id),
      };
      this.db.exec("COMMIT");
      return result;
    } catch (error) {
      this.db.exec("ROLLBACK");
      throw error;
    }
  }
  setNative(id: string, nativeId: string) {
    this.db
      .prepare("UPDATE sessions SET native_session_id=? WHERE id=?")
      .run(nativeId, id);
  }
  setTitle(id: string, title: string) {
    this.db
      .prepare("UPDATE sessions SET title=? WHERE id=?")
      .run(title.slice(0, 100), id);
  }
  setStatus(id: string, status: Status, runId?: string) {
    this.db
      .prepare("UPDATE sessions SET status=?,updated_at=? WHERE id=?")
      .run(status, now(), id);
    this.emit(id, "state", { status }, runId);
  }
  setContext(id: string, context: Context, runId?: string) {
    this.db
      .prepare("UPDATE sessions SET context=?,updated_at=? WHERE id=?")
      .run(JSON.stringify(context), now(), id);
    this.emit(id, "context", { context }, runId);
  }
  touchContext(id: string, runId?: string) {
    const c = this.getSession(id, true).context!;
    if (c.source === "empty")
      this.setContext(
        id,
        {
          ...c,
          used: null,
          stale: true,
          source: "unmeasured",
          updatedAt: now(),
        },
        runId,
      );
  }
  markContextStale(id: string, runId?: string) {
    const c = this.getSession(id, true).context!;
    this.setContext(id, { ...c, stale: true }, runId);
  }
  requestDelete(id: string) {
    this.db
      .prepare("UPDATE sessions SET delete_requested=1 WHERE id=?")
      .run(id);
    this.setStatus(id, "deleting");
  }
  finishDelete(id: string) {
    this.db
      .prepare(
        "UPDATE sessions SET deleted=1,status='idle',updated_at=? WHERE id=?",
      )
      .run(now(), id);
  }
  addMessage(
    sessionId: string,
    role: Message["role"],
    content: string,
    runId?: string,
    attachmentIds: string[] = [],
    id: string = randomUUID(),
    phase: MessagePhase = { phase: "unclassified" },
  ): Message {
    const m: Message = {
      id,
      ...phase,
      role,
      content,
      createdAt: now(),
      ...(runId ? { runId } : {}),
      ...(attachmentIds.length ? { attachmentIds } : {}),
    };
    this.db
      .prepare(
        "INSERT INTO messages(id,session_id,role,content,created_at,run_id,attachment_ids) VALUES(?,?,?,?,?,?,?)",
      )
      .run(
        id,
        sessionId,
        role,
        content,
        m.createdAt,
        runId ?? null,
        JSON.stringify(attachmentIds),
      );
    this.db
      .prepare("UPDATE sessions SET updated_at=? WHERE id=?")
      .run(m.createdAt, sessionId);
    this.db
      .prepare("INSERT INTO h002_message_meta VALUES(?,?)")
      .run(id, JSON.stringify(phase));
    return this.message(m.id);
  }
  appendMessage(id: string, text: string) {
    this.db
      .prepare("UPDATE messages SET content=content || ? WHERE id=?")
      .run(text, id);
  }
  message(id: string): Message {
    const r = this.db
      .prepare("SELECT * FROM messages WHERE id=?")
      .get(id) as Record<string, unknown>;
    return {
      id: String(r.id),
      ...this.messagePhase(id),
      attachments: decode<string[]>(r.attachment_ids).flatMap((id) => {
        const f = this.db
          .prepare(
            "SELECT id FROM files WHERE id=? AND session_id=? AND kind='attachment'",
          )
          .get(id, r.session_id as string);
        return f ? [this.publicFile(this.file(id))] : [];
      }),
      role: r.role as Message["role"],
      content: String(r.content),
      createdAt: String(r.created_at),
      ...(r.run_id ? { runId: String(r.run_id) } : {}),
      ...(decode<string[]>(r.attachment_ids).length
        ? { attachmentIds: decode<string[]>(r.attachment_ids) }
        : {}),
    };
  }
  messages(id: string): Message[] {
    return (
      this.db
        .prepare("SELECT id FROM messages WHERE session_id=? ORDER BY rowid")
        .all(id) as { id: string }[]
    ).map((r) => this.message(r.id));
  }
  private writeEvent(
    sessionId: string,
    type: string,
    data: Record<string, unknown>,
    runId?: string,
  ): Event {
    const createdAt = now();
    const row = this.db
      .prepare(
        "INSERT INTO events(session_id,id,type,run_id,created_at,data) SELECT ?,COALESCE(MAX(id),0)+1,?,?,?,? FROM events WHERE session_id=? RETURNING id",
      )
      .get(
        sessionId,
        type,
        runId ?? null,
        createdAt,
        JSON.stringify(data),
        sessionId,
      ) as { id: number };
    const event: Event = {
      id: row.id,
      type,
      sessionId,
      ...(runId ? { runId } : {}),
      createdAt,
      data,
    };
    return event;
  }
  emit(
    sessionId: string,
    type: string,
    data: Record<string, unknown>,
    runId?: string,
  ): Event {
    const event = this.writeEvent(sessionId, type, data, runId);
    this.events.emit(sessionId, event);
    return event;
  }
  appendDelta(
    sessionId: string,
    messageId: string,
    text: string,
    runId: string,
    phase?: MessagePhase,
  ): Event {
    let event: Event;
    this.db.exec("BEGIN IMMEDIATE");
    try {
      const existing = this.db
        .prepare("SELECT session_id,run_id FROM messages WHERE id=?")
        .get(messageId);
      if (!existing)
        this.addMessage(
          sessionId,
          "assistant",
          "",
          runId,
          [],
          messageId,
          phase,
        );
      else if (existing.session_id !== sessionId || existing.run_id !== runId)
        throw new Error("Message ownership mismatch");
      this.appendMessage(messageId, text);
      event = this.writeEvent(
        sessionId,
        "assistant_delta",
        { messageId, text, ...(phase ?? {}) },
        runId,
      );
      this.db.exec("COMMIT");
    } catch (error) {
      this.db.exec("ROLLBACK");
      throw error;
    }
    // Live subscribers may read a snapshot: notify only after committed text+event.
    this.events.emit(sessionId, event);
    return event;
  }
  setMessagePhase(
    sessionId: string,
    messageId: string,
    runId: string,
    phase: MessagePhase,
  ) {
    let event: Event;
    this.db.exec("BEGIN IMMEDIATE");
    try {
      const row = this.db
        .prepare(
          "SELECT id FROM messages WHERE id=? AND session_id=? AND run_id=?",
        )
        .get(messageId, sessionId, runId);
      if (!row) {
        this.db.exec("COMMIT");
        return;
      }
      this.db
        .prepare("INSERT OR REPLACE INTO h002_message_meta VALUES(?,?)")
        .run(messageId, JSON.stringify(phase));
      event = this.writeEvent(
        sessionId,
        "message",
        { message: this.message(messageId) },
        runId,
      );
      this.db.exec("COMMIT");
    } catch (error) {
      this.db.exec("ROLLBACK");
      throw error;
    }
    this.events.emit(sessionId, event);
  }
  messagePhase(id: string): MessagePhase {
    const meta = this.db
      .prepare("SELECT data FROM h002_message_meta WHERE message_id=?")
      .get(id);
    return meta ? decode<MessagePhase>(meta.data) : { phase: "unclassified" };
  }
  runs(sessionId: string): RunSnapshot[] {
    return this.db
      .prepare("SELECT id FROM runs WHERE session_id=? ORDER BY rowid")
      .all(sessionId)
      .map((r) => this.runSnapshot(String(r.id)));
  }
  runSnapshot(id: string): RunSnapshot {
    const r = this.db.prepare("SELECT * FROM runs WHERE id=?").get(id)!;
    const artifactIds = this.files(String(r.session_id), "artifact")
      .filter((f) => f.runId === id)
      .map((f) => f.id);
    const finalMessageId =
      this.messages(String(r.session_id)).findLast(
        (m) => m.runId === id && m.phase === "final",
      )?.id ?? null;
    const summary = this.db
      .prepare("SELECT data FROM h002_subagents WHERE run_id=?")
      .get(id);
    return {
      id,
      kind: r.kind as RunSnapshot["kind"],
      status: r.status as RunSnapshot["status"],
      createdAt: String(r.created_at),
      updatedAt: String(r.updated_at),
      finalMessageId,
      artifactIds,
      ...(artifactIds.length > 1
        ? { zipUrl: `/api/sessions/${r.session_id}/runs/${id}/artifacts.zip` }
        : {}),
      subagents: summary
        ? decode<SubagentSummary>(summary.data)
        : unknownSubagents(),
    };
  }
  emitRun(id: string) {
    const r = this.db.prepare("SELECT session_id FROM runs WHERE id=?").get(id);
    if (r)
      this.emit(String(r.session_id), "run", { run: this.runSnapshot(id) }, id);
  }
  activities(sessionId: string): Activity[] {
    return this.db
      .prepare(
        "SELECT data FROM h002_activities WHERE session_id=? ORDER BY rowid",
      )
      .all(sessionId)
      .map((r) => decode<Activity>(r.data));
  }
  upsertActivity(sessionId: string, activity: Activity) {
    this.db.exec("BEGIN IMMEDIATE");
    let event: Event;
    try {
      const old = this.db
        .prepare("SELECT data FROM h002_activities WHERE run_id=? AND id=?")
        .get(activity.runId, activity.id);
      const merged = {
        ...(old ? decode<Activity>(old.data) : {}),
        ...activity,
      };
      this.db
        .prepare("INSERT OR REPLACE INTO h002_activities VALUES(?,?,?,?)")
        .run(sessionId, activity.runId, activity.id, JSON.stringify(merged));
      event = this.writeEvent(
        sessionId,
        "activity",
        { activity: merged },
        activity.runId,
      );
      this.db.exec("COMMIT");
    } catch (error) {
      this.db.exec("ROLLBACK");
      throw error;
    }
    this.events.emit(sessionId, event);
  }
  setSubagents(sessionId: string, runId: string, summary: SubagentSummary) {
    this.db.exec("BEGIN IMMEDIATE");
    let event: Event;
    try {
      this.db
        .prepare("INSERT OR REPLACE INTO h002_subagents VALUES(?,?)")
        .run(runId, JSON.stringify(summary));
      event = this.writeEvent(
        sessionId,
        "subagents",
        { runId, summary },
        runId,
      );
      this.db.exec("COMMIT");
    } catch (error) {
      this.db.exec("ROLLBACK");
      throw error;
    }
    this.events.emit(sessionId, event);
    this.emitRun(runId);
  }
  private recoverLegacyFiles() {
    // Only unambiguous existing artifact event envelopes establish historical run ownership.
    this.db
      .prepare(
        `INSERT OR IGNORE INTO h002_file_refs(file_id,run_id,message_id)
      SELECT f.id,MIN(e.run_id),NULL FROM files f JOIN events e
        ON e.session_id=f.session_id AND e.type='artifact' AND json_valid(e.data)
        AND json_extract(e.data,'$.artifact.id')=f.id
      JOIN runs r ON r.id=e.run_id AND r.session_id=f.session_id
      WHERE f.kind='artifact' GROUP BY f.id HAVING COUNT(DISTINCT e.run_id)=1`,
      )
      .run();
  }
  private recoverLegacyActivities() {
    const projected = new Map<
      string,
      { sessionId: string; activity: Activity }
    >();
    const rows = this.db
      .prepare(
        `SELECT e.* FROM events e JOIN runs r ON r.id=e.run_id AND r.session_id=e.session_id
      WHERE e.type='progress' AND json_valid(e.data) AND json_extract(e.data,'$.kind') IN ('tool','subagent')
      AND json_type(e.data,'$.taskId')='text' ORDER BY e.session_id,e.id`,
      )
      .iterate();
    for (const row of rows) {
      const data = decode<Record<string, unknown>>(row.data);
      const nativeId = String(data.taskId);
      if (!nativeId || nativeId.length > 512 || /[\x00-\x1f]/.test(nativeId))
        continue;
      const kind = data.kind as Activity["kind"],
        runId = String(row.run_id),
        id = `${kind}:${nativeId}`;
      const key = `${runId}:${id}`;
      const old = projected.get(key)?.activity;
      projected.set(key, {
        sessionId: String(row.session_id),
        activity: {
          ...old,
          id,
          runId,
          kind,
          name: kind === "tool" ? "Tool" : "Subagent",
          status: "unknown",
          updatedAt: String(row.created_at),
          startedAt: old?.startedAt ?? String(row.created_at),
          ...(typeof data.label === "string"
            ? { summary: data.label.slice(0, 300) }
            : {}),
          ...(typeof data.detail === "string"
            ? { detail: data.detail.slice(0, 2048) }
            : {}),
          ...(kind === "tool"
            ? { toolCallId: nativeId }
            : { childSessionId: nativeId }),
        },
      });
    }
    const insert = this.db.prepare(
      "INSERT OR IGNORE INTO h002_activities VALUES(?,?,?,?)",
    );
    for (const { sessionId, activity } of projected.values())
      insert.run(
        sessionId,
        activity.runId,
        activity.id,
        JSON.stringify(activity),
      );
  }
  replay(sessionId: string, after = 0, limit = 1000): Event[] {
    return (
      this.db
        .prepare(
          "SELECT * FROM events WHERE session_id=? AND id>? ORDER BY id LIMIT ?",
        )
        .all(sessionId, after, limit) as Record<string, unknown>[]
    ).map((r) => ({
      id: Number(r.id),
      type: String(r.type),
      sessionId,
      ...(r.run_id ? { runId: String(r.run_id) } : {}),
      createdAt: String(r.created_at),
      data: decode(r.data),
    }));
  }
  allEvents(id: string): Event[] {
    const out: Event[] = [];
    let after = 0;
    for (;;) {
      const next = this.replay(id, after);
      out.push(...next);
      if (next.length < 1000) return out;
      after = next.at(-1)!.id;
    }
  }
  createRun(
    s: StoredSession,
    kind: Run["kind"],
    text: string,
    attachmentIds: string[],
  ): Run {
    const id = randomUUID(),
      time = now();
    this.db
      .prepare("INSERT INTO runs VALUES(?,?,?,?,?,?,?,?,?)")
      .run(
        id,
        s.id,
        s.workspaceId,
        kind,
        text,
        JSON.stringify(attachmentIds),
        "queued",
        time,
        time,
      );
    this.touchContext(s.id, id);
    this.emitRun(id);
    return {
      id,
      sessionId: s.id,
      workspaceId: s.workspaceId,
      kind,
      text,
      attachmentIds,
      status: "queued",
    };
  }
  updateRun(id: string, status: string) {
    this.db
      .prepare("UPDATE runs SET status=?,updated_at=? WHERE id=?")
      .run(status, now(), id);
    this.emitRun(id);
  }
  settleRun(
    id: string,
    status: "completed" | "cancelled",
    final?: { messageId: string; phase: MessagePhase },
  ) {
    const events: Event[] = [];
    const run = this.db
      .prepare("SELECT session_id FROM runs WHERE id=?")
      .get(id)!;
    const sessionId = String(run.session_id);
    this.db.exec("BEGIN IMMEDIATE");
    try {
      if (status === "completed" && final) {
        const message = this.db
          .prepare(
            "SELECT content FROM messages WHERE id=? AND session_id=? AND run_id=? AND role='assistant'",
          )
          .get(final.messageId, sessionId, id);
        if (message && String(message.content).trim()) {
          this.db
            .prepare("INSERT OR REPLACE INTO h002_message_meta VALUES(?,?)")
            .run(final.messageId, JSON.stringify(final.phase));
          events.push(
            this.writeEvent(
              sessionId,
              "message",
              { message: this.message(final.messageId) },
              id,
            ),
          );
          this.db
            .prepare("UPDATE h002_file_refs SET message_id=? WHERE run_id=?")
            .run(final.messageId, id);
          for (const f of this.files(sessionId, "artifact").filter(
            (f) => f.runId === id,
          ))
            events.push(
              this.writeEvent(
                sessionId,
                "artifact",
                { artifact: this.publicFile(f) },
                id,
              ),
            );
        }
      }
      this.db
        .prepare("UPDATE runs SET status=?,updated_at=? WHERE id=?")
        .run(status, now(), id);
      events.push(
        this.writeEvent(sessionId, "run", { run: this.runSnapshot(id) }, id),
      );
      this.db.exec("COMMIT");
    } catch (error) {
      this.db.exec("ROLLBACK");
      throw error;
    }
    for (const event of events) this.events.emit(sessionId, event);
  }
  saveFile(f: FileRecord): FileRecord {
    // A savepoint also preserves an enclosing caller transaction on failure.
    this.db.exec("SAVEPOINT save_file");
    try {
      const old = this.db
        .prepare(
          "SELECT id FROM files WHERE session_id=? AND kind=? AND path=?",
        )
        .get(f.sessionId, f.kind, f.path) as { id: string } | undefined;
      if (old) {
        this.db
          .prepare("UPDATE files SET name=?,mime_type=?,size=? WHERE id=?")
          .run(safeStorageName(f.name), f.mimeType, f.size, old.id);
        this.db
          .prepare("INSERT OR REPLACE INTO h002_file_names VALUES(?,?)")
          .run(old.id, displayName(f.name));
        const saved = this.file(old.id);
        this.db.exec("RELEASE SAVEPOINT save_file");
        return saved;
      }
      this.db
        .prepare(
          "INSERT INTO files(id,session_id,kind,path,name,mime_type,size) VALUES(?,?,?,?,?,?,?)",
        )
        .run(
          f.id,
          f.sessionId,
          f.kind,
          f.path,
          safeStorageName(f.name),
          f.mimeType,
          f.size,
        );
      this.db
        .prepare("INSERT INTO h002_file_names VALUES(?,?)")
        .run(f.id, displayName(f.name));
      this.db
        .prepare("INSERT INTO h002_file_refs VALUES(?,?,?)")
        .run(f.id, f.runId ?? null, f.messageId ?? null);
      if (f.image)
        this.db
          .prepare("INSERT OR REPLACE INTO h003_image_file_meta VALUES(?,?)")
          .run(f.id, JSON.stringify(f.image));
      this.db.exec("RELEASE SAVEPOINT save_file");
      return f;
    } catch (error) {
      this.db.exec(
        "ROLLBACK TO SAVEPOINT save_file; RELEASE SAVEPOINT save_file",
      );
      throw error;
    }
  }

  file(id: string): FileRecord {
    const r = this.db.prepare("SELECT * FROM files WHERE id=?").get(id) as
      | Record<string, unknown>
      | undefined;
    if (!r) throw new ApiError(404, "not_found", "File not found");
    const ref = this.db
      .prepare("SELECT run_id,message_id FROM h002_file_refs WHERE file_id=?")
      .get(id);
    const image = this.db
      .prepare("SELECT data FROM h003_image_file_meta WHERE file_id=?")
      .get(id)?.data;
    return {
      ...(image
        ? { image: decode<import("./image-contracts.js").ImageMetadata>(image) }
        : {}),
      id: String(r.id),
      sessionId: String(r.session_id),
      kind: r.kind as FileRecord["kind"],
      path: String(r.path),
      name: String(
        this.db
          .prepare("SELECT display_name FROM h002_file_names WHERE file_id=?")
          .get(id)?.display_name ?? r.name,
      ),
      mimeType: String(r.mime_type),
      size: Number(r.size),
      runId: ref?.run_id ? String(ref.run_id) : null,
      messageId: ref?.message_id ? String(ref.message_id) : null,
    };
  }
  files(sessionId: string, kind: FileRecord["kind"]): FileRecord[] {
    return (
      this.db
        .prepare(
          "SELECT id FROM files WHERE session_id=? AND kind=? ORDER BY rowid",
        )
        .all(sessionId, kind) as { id: string }[]
    ).map((r) => this.file(r.id));
  }
  publicFile(f: FileRecord): Attachment | Artifact {
    const value = {
      id: f.id,
      name: f.name,
      mimeType: f.mimeType,
      size: f.size,
      ...(imageMime(f.name)
        ? { previewUrl: `/api/files/${f.id}/preview` }
        : {}),
    };
    return f.kind === "artifact"
      ? {
          ...value,
          downloadUrl: `/api/artifacts/${f.id}/download`,
          ...(f.image ? { image: f.image } : {}),
          runId: f.runId ?? null,
          messageId: f.messageId ?? null,
        }
      : { ...value, downloadUrl: `/api/attachments/${f.id}/download` };
  }
}
