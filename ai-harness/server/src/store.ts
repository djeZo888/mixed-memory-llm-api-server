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
} from "./contracts.js";
import { CONTEXT_LIMIT } from "./contracts.js";
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
  id: string;
  sessionId: string;
  kind: "attachment" | "artifact";
  path: string;
  name: string;
  mimeType: string;
  size: number;
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
    // A process restart never replays a queued prompt or a tool effect.
    this.db.exec("BEGIN IMMEDIATE");
    try {
      const interrupted = this.db
        .prepare(
          "SELECT DISTINCT session_id FROM runs WHERE status IN ('queued','running','cancelling')",
        )
        .all() as { session_id: string }[];
      this.db
        .prepare(
          "UPDATE runs SET status='interrupted',updated_at=? WHERE status IN ('queued','running','cancelling')",
        )
        .run(now());
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
      used: null,
      limit: CONTEXT_LIMIT,
      estimated: false,
      stale: true,
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
    id = randomUUID(),
  ): Message {
    const m: Message = {
      id,
      role,
      content,
      createdAt: now(),
      ...(runId ? { runId } : {}),
      ...(attachmentIds.length ? { attachmentIds } : {}),
    };
    this.db
      .prepare("INSERT INTO messages VALUES(?,?,?,?,?,?,?)")
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
    return m;
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
  ): Event {
    let event: Event;
    this.db.exec("BEGIN IMMEDIATE");
    try {
      this.appendMessage(messageId, text);
      event = this.writeEvent(
        sessionId,
        "assistant_delta",
        { messageId, text },
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
  }
  saveFile(f: FileRecord): FileRecord {
    const old = this.db
      .prepare("SELECT id FROM files WHERE session_id=? AND kind=? AND path=?")
      .get(f.sessionId, f.kind, f.path) as { id: string } | undefined;
    if (old) {
      this.db
        .prepare("UPDATE files SET name=?,mime_type=?,size=? WHERE id=?")
        .run(f.name, f.mimeType, f.size, old.id);
      return this.file(old.id);
    }
    this.db
      .prepare("INSERT INTO files VALUES(?,?,?,?,?,?,?)")
      .run(f.id, f.sessionId, f.kind, f.path, f.name, f.mimeType, f.size);
    return f;
  }
  file(id: string): FileRecord {
    const r = this.db.prepare("SELECT * FROM files WHERE id=?").get(id) as
      | Record<string, unknown>
      | undefined;
    if (!r) throw new ApiError(404, "not_found", "File not found");
    return {
      id: String(r.id),
      sessionId: String(r.session_id),
      kind: r.kind as FileRecord["kind"],
      path: String(r.path),
      name: String(r.name),
      mimeType: String(r.mime_type),
      size: Number(r.size),
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
    };
    return f.kind === "artifact"
      ? { ...value, downloadUrl: `/api/artifacts/${f.id}/download` }
      : value;
  }
}
