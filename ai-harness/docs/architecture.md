# ai-harness v0.0.1 architecture

This is the current design under the [approved plan](../PLAN-v0.0.1.md).
Live evidence spans initial `10dea3e`, Delete/lifecycle `d58020c` and V2 Stop
`7659955`, including final follow-up/health. The docs base remains `d58020c`.
The [acceptance report](acceptance-v0.0.1.md) pins each release and separates
bounded live results, fixtures, failures and unexecuted cases.

## Request path and storage

```text
LAN browser -> nginx HTTP :80 -> React UI / Fastify server (127.0.0.1:8080)
                                      | SQLite metadata + file storage
                                      | ACP
                              rootless MiniMax engines
                                |                 |
                   internal Qwen gateway     local Chromium / PDF / code tools
                     (127.0.0.1:8081)        private SearXNG via MCP adapter
                         |       |
                      GPU0 Qwen  GPU1 Qwen
```

The active browser origin is `http://10.156.100.61/` (initial live readiness).
React/Vite serves the shared chat interface; the Node/TypeScript server persists
chats, original messages, run state, events, context observations and file metadata
in SQLite. Project files, uploads and downloadable artifact snapshots use filesystem
storage. Reconnect combines a consistent saved snapshot with later stream events
to avoid duplicated replies. Browser disconnection does not cancel a run.

The existing ordinary user runs the server and rootless containers. Each engine
mounts its profile and intended workspace; backend credentials and host management
sockets remain outside task containers. Host/origin checks are retained, but
there is no login or per-person access separation. Everyone with LAN access shares
conversations and task access; the operator owns access restriction. HTTP is
unencrypted. The [runtime](../deploy/RUNTIME.md) defines the reviewed transport.

## Inference and context

Pinned MiniMax Code (`ae65651df5f97ae1085ab4e19964f4b78c769a4e`) uses one logical
Qwen provider through the internal gateway. The existing endpoints are:

| Endpoint | Upstream model alias | Shared request slots |
| --- | --- | --- |
| `http://10.156.100.60:30002/v1` | `qwen3.8-27b-gpu0` | 1 |
| `http://10.156.100.60:30004/v1` | `qwen3.8-27b` | 1 |

Exactly two request slots are shared globally across chats, native background
children, compression and auxiliary calls. Slots belong to inference requests
and are released between requests; a parent waiting for a child holds no slot.
Queueing is bounded and cancellable. Ambiguous upstream completion retains or
quarantines its slot until settlement; an aborted socket does not prove idleness.
Partially emitted responses and tool side effects are not automatically replayed.
Weights, placement and runtimes remain unchanged; GLM is outside this integration.

Each main/child session has 480,000 context tokens, with at most 65,536 output
tokens per inference request, including reasoning where counted. Input and output
share that window. Normal native compression begins near 412,416 input tokens
under the production output reservation; archiving can start earlier. Compression
preserves original visible history, native snapshots and archived tool results.
The UI reports estimated occupied context after replies/compression, marks old
observations stale and absent observations unavailable, and never substitutes
cumulative inference usage. Fixed configuration does not prove measured capacity.

## Task ownership, Stop and recovery

Runs in one chat serialize. Separate workspaces can run concurrently; handoff
chats share project files and therefore serialize. Continue in new chat asks the
engine for a summary, seeds the new conversation and retains old history/files.

The original ACP prompt remains attached through child-triggered root
continuations and their text delivery. Children appear as progress; final
assistant output comes from root turns. Before releasing a workspace, the server
requires prompt completion, drained output and a fresh authoritative proof that
the full native task tree has settled. Cancellation acknowledgment alone, elapsed
idle time or missing proof cannot establish completion.

Persisted clean-settled and clean-cancelled checkpoints are distinct from
interrupted/unknown state and are revalidated on load. After proven Stop, the
next explicit prompt starts a new run in the same native root session, preserving
history, context and workspace. Per-task cancellation suppression remains durable
so old tasks and late callbacks cannot revive. Native CLI slash commands
(`/status`, `/context`, `/compact`, etc.) are rejected before ACP dispatch;
automatic native compression remains part of supported normal prompts.

Unknown work retains partial history and blocks workspace reuse pending cleanup.
Verified shutdown of the exact owned container can prove process cleanup, but
cannot turn an unknown run into successful completion. Stop cleanup does not end
already dispatched upstream inference: it may drain while retaining a gateway
lane. V2 suppresses tagged cancellation failures only after verified cleanup;
the tiny live Stop and explicit same-chat follow-up passed. Clean restart
and one controlled crash/no-replay case passed on `d58020c`: interrupted work was
quarantined, counter unchanged, old container absent. Active Delete and preservation
also passed there, with the older spurious cancellation error recorded separately.
See [server recovery details](../server/README.md).

## Tools and operations

Private SearXNG and local Chromium support public research, JavaScript pages and
source links; logged-in actions and publishing are excluded. Local PDF tools cover
text, rendering, OCR and basic generation; Python/C++/Node tools cover code work.
Image upload, recognition and follow-up passed a bounded synthetic-image live case.
Office, CAD and simulators are outside scope. See [tooling](../tools/runtime/README.md),
[deployment](../deploy/README.md) and [service commands/licenses](../README.md).
SearXNG is a separate AGPL-3.0-or-later service; its
[notice](../tools/searxng/NOTICE.md) remains separate from first-party MIT additions.
