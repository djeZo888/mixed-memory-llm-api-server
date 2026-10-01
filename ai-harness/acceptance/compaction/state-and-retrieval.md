# Smallest authoritative state and retrieval successor

Read-only source inspection in this isolated checkout found useful durable
foundations, not an implemented authoritative project-memory service:

| Existing support | Source-backed scope |
| --- | --- |
| Original messages, runs, events and files | `server/src/store.ts:96` tables; `messages(sessionId)` at 603 and `replay(sessionId,after,limit)` at 904 retain addressable data. |
| Engine/native ownership | Store native identity at 379 and state cursor/ownership at 389 bind sessions to their engines. |
| Compaction idempotency | `h024_compaction_actions` at Store 115 and Broker 123–154 retain action/run binding and reject duplicate pending work. |
| Original visible records and settlement | Broker 467–513 records compaction progress and marks usage stale; 650–732 checks cleanup, settlement and quarantine. This does not prove native summary rollback. |
| Session retrieval routes | `server/src/app.ts:355` exposes a full session snapshot; 459 exposes ordinary manual compaction. The full snapshot contains more than a scoped fact retrieval tool should expose. |
| Tool policy boundary | `server/src/policy.ts:51` lists `memory` among disallowed tools. No project-memory permission follows from the presence of a durable database. |

The smallest next source change is exact original-record retrieval before a new
schema or embeddings. B proposes the following changes to their owners; B did
not edit these files:

1. Add `Store.readOriginalMessage(sessionId,messageId,{offsetBytes,maxBytes})` in
   `server/src/store.ts`, with the session predicate in the SQL lookup itself.
   Return message ID, role, run ID, timestamp, full-content SHA, safe UTF-8 byte
   interval and bounded excerpt. Validate ownership before reading. Fail closed
   for missing, deleted or foreign-session records. Do not expose profile/auth,
   arbitrary paths or the full `snapshot().environment`.
2. Add literal text search scoped by session, using `instr(content,?)>0` and a
   bounded result count; return original IDs/offsets/hashes rather than an
   answer-bearing synthetic memory file. Exact retrieval is sufficient for the
   first successor. FTS, embeddings and project/organization sharing can follow
   a separate ownership/authorization design.
3. Have the broker/tool owner expose ONLY `scoped.read_original_records` to a
   reviewed session-bound host adapter. Bind each read to current run/session and
   record tool-call ID plus requested/returned source hashes. Add the exact
   allowlist entry in `policy.ts`; do not turn on the broad blocked `memory`
   tool. Root reviews this narrow contract before source integration.
4. After exact retrieval works, store a versioned project-state artifact through
   the existing owned file machinery. Each fact has key, exact typed value/unit,
   authority, version, explicit superseded version, source ID/hash and check
   receipt or pending status. Accepted user requirements and actual check
   receipts survive independently of generated narrative summaries. A user
   correction supersedes an old decision without deleting the old source.
   Model assertions and untrusted document instructions cannot become test
   receipts or new authorization. A content hash/version compare protects
   promotion against concurrent edits.

The initial state artifact needs no database migration. It should be an owned
append-only versioned source artifact plus an explicitly reviewed current
pointer. A future project namespace needs its own cross-session authority rules;
this proposal remains session-scoped. Lifecycle hooks into native pre-commit,
staged promotion or documented recovery checkpoints remain A/root decisions
after auditing actual Codex persistence. Post-replacement grading cannot be
called atomic rollback.

Independent acceptance should verify foreign-session denial, exact provenance,
old/new decision coexistence, pending check preservation, literal search limits,
UTF-8 boundaries, deleted records and cold retrieval. The present synthetic suite
tests the proposed receipt/answer contract; it does not prove these future store
methods or native tools already exist.

H040 read-only inspection still finds the broad `memory` tool blocked and no
original-record read API in this B base. Root's A source proposal supplies a
different, explicitly branded fresh `read_original` probe: an immutable
checkpoint-bound set of copied original byte slices, exact native
`item/tool/call` handling and default-absent trusted launch/settlement receipts.
That can pilot the session-scoped successor before a store schema change.

The exact next B/E interface proposal is a separate reviewed native retrieval
representation. Preserve the synthetic `scoped.read_original_records` contract;
validate `read_original` wire name, owned native thread/turn/call/item IDs,
reference/offset/limit, immutable checkpoint ID, exact returned original bytes
and current citations from captured native requests and canonical completion.
Use E's preserved original-to-message byte references as the source authority,
never the ground-truth file. A host response write alone is not consumption or
settlement. This proposal is not implemented or native-qualified by B; the
full-profile retrieval gate remains closed until the owners' coherent source
and actual trusted Linux transport pass root review.
