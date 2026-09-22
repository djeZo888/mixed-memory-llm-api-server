# ai-harness server 0.0.1

Node 24 / TypeScript / Fastify / SQLite control plane and two-lane inference
gateway for the approved ai-harness plan. This directory owns the server only;
PREP owns the engine container/launcher and WEB owns the frontend. First-party
source is MIT under this directory's LICENSE. No hosted MiniMax account is used.

## Build and local verification

```sh
npm ci --ignore-scripts
npm run typecheck
npm run build
npm test
npm audit
```

Dependencies are exact-pinned in package.json/package-lock.json, including the
official `@agentclientprotocol/sdk` **1.3.0**. Engine interoperability is based on
MiniMax source **ae65651df5f97ae1085ab4e19964f4b78c769a4e**, inspected in a separate
reference checkout. Tests use synthetic credentials and local HTTP / official
ACP SDK subprocess fixtures. They do not start MiniMax, contact VMs, use a real
inference key, prove tokenizer accuracy, or constitute live acceptance.

## Launch contract

After PREP deployment and root review, supply these protected host settings:

| Variable | Meaning |
| --- | --- |
| `AI_HARNESS_DATA_DIR` | Absolute private mode-0700 data directory, outside served web assets and engine mounts except individual profile/workspace mounts |
| `AI_HARNESS_ENGINE_LAUNCHER` | Absolute path to PREP `deploy/run-engine.sh` |
| `AI_HARNESS_INFERENCE_KEY_FILE` | Existing host-only, owner-readable, regular, unlinked inference credential; never mounted into engines |
| `AI_HARNESS_GATEWAY_URL` | Engine/container-reachable URL ending `/v1`; default `http://127.0.0.1:8081/v1` for local transport |
| `AI_HARNESS_ALLOWED_ORIGINS` | Comma-separated exact browser origins; defaults `http://10.156.100.61,http://127.0.0.1:8080,http://localhost:8080` |
| `AI_HARNESS_VISION_AVAILABLE` | Fixed deployment defaults enabled following root's separate backend probe; set `false` to disable. UI/end-to-end vision remains NOT_TESTED |
| `AI_HARNESS_WEB_DIST` | Optional static directory; default sibling `web/dist` |
| `AI_HARNESS_PORT` | Public app loopback port; default 8080 |
| `AI_HARNESS_GATEWAY_PORT` | Internal gateway loopback port; default 8081 |

Run `npm start` after building. Both listeners bind **127.0.0.1**. Nginx exposes
only the public application on the reviewed LAN HTTP80 origin and must preserve
Host. Forwarded host/protocol headers are not trusted. The API is intentionally
single-user LAN access: no login, arbitrary CORS, model selector, context selector,
settings or lifecycle API. Host, Origin and Fetch Metadata checks apply to API,
SSE, downloads and static assets. The gateway rejects browser Origin and uses a
separate inference-only bearer credential; bearer credentials are rejected on
the public application. DNS rebinding to arbitrary hostnames is rejected.

The server directly executes the launcher (no shell) with
`--profile-dir ABS --workspace ABS`, passing only a minimal environment and:

- `AI_HARNESS_GATEWAY_URL`
- `AI_HARNESS_GATEWAY_TOKEN`: random per-process token; PREP may persist it only
  in protected native profile config; server registry is in memory and revokes
  it when the engine closes/exits
- `AI_HARNESS_SESSION_ID`: public chat identifier

The container must mount profile/workspace at the **same absolute paths**.
PREP must verify container reachability (candidate `http://10.0.2.2:8081/v1`)
and terminate descendants on launcher shutdown. The server allows 5 seconds for
ACP settlement, then 45 seconds after SIGTERM for PREP's bounded exact-container
cleanup (up to 40 seconds), followed by a bounded final kill. Nonzero/uncertain
launcher settlement quarantines the workspace. Runner shutdown is parallel and
does not wait on a stuck prompt before signaling its launcher; the overall
process shutdown ceiling is 70 seconds, below PREP's 90-second unit deadline. Profiles isolate native session
storage; they are not security sandboxes. Engine stdout is ACP JSONL; stderr is
written to private per-chat logs with gateway-token redaction. Host credentials,
auth sockets, proxy variables and Node injection options are not inherited.
PREP must configure fixed **480000** context, maximum **65536** output, native
background subagents enabled, and every main/child/compression request through
the gateway. No direct upstream key is exposed to the engine.

## Permission boundary

Before launch the server atomically writes mode-0600 `profile/permission.json`.
**PREP must set `MINIMAX_DATA_DIR` to that exact absolute profile directory and
preserve this file**, without extra allow rules or alternate data roots. Native
`permissionMode=default` is selected and verified through the official SDK.
The pinned native default fast-allows some shell publication commands, so the
server's rules force read/write/edit/grep/glob/bash escalation to the ACP client.
Scoped regular workspace file operations and read-only container assets under
`/opt/ai-harness/skills` and `/opt/ai-harness/tools` are approved. Asset checks are
lexical container policy and do not open nonexistent host paths; PREP mounts
these reviewed image roots read-only without escaping links. Asset mutations are
denied; unsafe paths, arbitrary
shell source and external writes are denied. Recognized container-local Python/C++/Node build/test/package commands are
admitted under the coordinator-approved PREP isolation/network boundary. Explicit
publishing/send/host-management commands, unrecognized shell operations and
unsafe path arguments are denied. Arbitrary program/package script effects
cannot be proven safe by command recognition; PREP must enforce the reviewed
external-write/credential boundary. The server's own tests run on the authorized
worker; this is not live MiniMax coding-task acceptance.

Website deployment, dynamic feature/MCP configuration, code-review side execution,
memory and every pinned browser tool are currently denied as a temporary
fail-closed policy. Native browser/search/skill policy is **incomplete**, pending
the coordinator's reviewed POLICY-CONTRACT; blanket browser denial is not
accepted final behavior. Native task children
remain enabled and their permission requests use the root chat callback. PREP
must disable unreviewed profile-global MCP, Matrix and plugin tools: their native
catalog provenance can bypass the permission gate. Empty ACP `mcpServers` alone
does not disable those global discovery paths. Read-only research/browser tooling
must be integrated under the separately reviewed tools task; no browsing/sandbox
acceptance is claimed here. The server policy is not a kernel sandbox.

## Persistence and run semantics

An OS-held SQLite ownership lock prevents a second server from treating a live
data directory as a crashed instance; it releases automatically on process exit.
Session snapshots use one SQLite read transaction. Assistant content and its delta event commit in one SQLite transaction, and
live subscribers are notified only after commit; snapshots are canonical through their
maximum event ID, and clients replay buffered events only above that watermark.
SQLite WAL stores sessions, original visible messages, runs, monotonic per-chat
events, native engine session IDs, context observations and attachment/artifact
metadata. The server never replaces original visible history with a compaction
summary. ACP load replay is suppressed because the durable application history
already owns those messages. `usage_update` from the pinned engine's context
snapshot supplies occupied context, marked estimated. Missing or unsupported
measurements remain `null`; new work makes the previous measurement stale.
Gateway prompt-token observations have unknown main/child/compression attribution
and are retained as diagnostics, never presented as exact main-chat occupancy
or summed into context. No inferred thoughts are presented as work progress.
The root-reviewed PREP patch adds `mcode/session/compaction_update`. Validated,
ordered, deduplicated start/completed/failed transitions drive real progress and
compacting/running state. Completion leaves context stale until ACP usage_update;
failure emits compaction_failed without inventing the prompt outcome. Native
compaction event counters never replace occupied-context measurements.

Runs sharing one workspace execute sequentially, including across a handoff.
Separate workspaces can run concurrently. Parent prompt completion is followed
by native delegation-state checks; queued/running/unknown children retain the
workspace. Foreground delegation can settle normally. **Native background
delegation is enabled but has a source acceptance hold:** completion can steer a
new parent turn, while this pinned ACP revision exposes only child status and
its close response does not await parent termination. When `backgroundTaskId` is
observed, the bridge waits for children, stops/closes the launcher, then reports
`engine_settlement_unknown` and durably quarantines the workspace. It never
admits a next writer based on an inferred idle parent. Full background continuation
needs a reviewed native settlement extension and live acceptance. Cancellation requests both root cancellation and
native child stop. Browser SSE disconnection never cancels a run. Follow-ups
queue durably but a server restart marks unfinished/queued work interrupted;
no tool effect or prompt is automatically replayed.

Engine failures of uncertain settlement quarantine the workspace. Restarted
unfinished runs also quarantine their workspace. These blocks are durable and
have no public bypass. An operator must verify every engine/container descendant
has settled before an offline, reviewed repair of the corresponding
`quarantined_workspaces` row. Do not clear this merely because a socket closed.
Deletion first cancels work and waits for confirmed settlement before hiding
metadata; project files remain. Uncertain deletion stays visible. Handoff asks
the real engine for a summary, creates a new chat sharing the workspace, retains
the old chat/history, and seeds the new engine's first prompt with that summary.

## Public API

JSON errors are `{error:{code,message}}`. IDs are opaque; timestamps are UTC ISO.
The shapes match the task's `COORDINATION.md` v1 contract.

| Method and path | Result |
| --- | --- |
| `GET /api/health` | `{version:"0.0.1",status:"ok",visionAvailable:boolean}; fixed deployment defaults true` |
| `GET /api/sessions` | `{sessions}` recent first |
| `POST /api/sessions` body `{}` | `{session}` |
| `GET /api/sessions/:id` | `{session,messages,events,artifacts}` |
| `DELETE /api/sessions/:id` | 202 deleting, or 200 deleted after settlement |
| `POST /api/sessions/:id/messages` | 202 `{runId}`; body `{text,attachmentIds?}` |
| `POST /api/sessions/:id/cancel` body `{}` | 202 `{status:"cancelling"}` |
| `POST /api/sessions/:id/handoff` body `{}` | 202 `{runId}`; later `handoff` event with `newSessionId` |
| `POST /api/sessions/:id/uploads` | One multipart file; 201 `{attachment}` |
| `GET /api/sessions/:id/artifacts` | `{artifacts}` |
| `GET /api/artifacts/:id/download` | Registered snapshot by ID only; no path query |
| `GET /api/sessions/:id/events?after=N` | SSE replay; alternatively `Last-Event-ID` |

SSE events have per-session increasing numeric `id`, `type`, `sessionId`, optional
`runId`, `createdAt`, and `data`; event names are message, assistant_delta,
progress, context, state, artifact, error, done and handoff. Replay is incremental
with backpressure and a 15-second heartbeat. Reconnect clients should resync the
session to deduplicate partial assistant deltas versus the final message.

Public JSON bodies are bounded at 1 MiB; text at 250000 characters; each message
has at most 10 attachment IDs. Uploads are separately bounded at **50 MiB**, one
file, sanitized display names and generated storage IDs. Image inputs are enabled only by the explicit reviewed capability setting.
Root's separate probe accepted backend image inputs; inline ACP image blocks
remain unsupported, so attachments use scoped workspace references. This task
has not accepted the UI/end-to-end vision path. Attachment IDs cannot
cross session ownership. Original uploads stay outside engine mounts; only
validated copies are placed in the task workspace. Artifact registration checks
lexical/canonical scope, symlinks, hard links, file identity and regular-file
type, then snapshots into server-only storage. Downloads use the snapshot ID,
never an engine-supplied path. Artifact size is bounded at 64 MiB. After each
run, bounded discovery registers changed regular workspace files (up to 1000
entries / 8 directory levels, excluding hidden files and dependency/build caches).
Large or excluded files remain in the workspace; they are not exposed as downloads.

## Gateway and settlement

The only supported routes are `/v1/models` and `/v1/chat/completions`; logical model
`qwen3.8-27b`. Fixed production upstreams are:

- `http://10.156.100.60:30002/v1`, alias `qwen3.8-27b-gpu0`
- `http://10.156.100.60:30004/v1`, alias `qwen3.8-27b`

Each endpoint has one global generation permit across all runners and child or
compression calls. Permits belong to actual requests, never a parent turn. A
shared FIFO allows 128 queued requests with a 128 MiB aggregate queued JSON budget,
with a separate 30-minute queue deadline.
Active generation gets two hours; queue waiting consumes none of it. PREP owns
a gateway-origin-specific MiniMax/OpenAI transport patch of at least 151 minutes
(queue30 + generation120 + overhead), including Undici headers/body deadlines
and agentStop maxActiveSpan=0. SDK fetch-abort timeout alone does not override
Undici's 300-second transport default. Short title deadlines remain intentional.
The server gateway uses node:http/https with its own active timer, no synthetic
stream heartbeats, and no hidden fetch timeout workaround. JSON input
is bounded at 64 MiB. Request content/tools/messages are preserved; only the
model alias and declared output cap change. Smaller requested limits, including
compression's 13107, survive; missing limits default to 65536, larger valid
limits clamp to 65536, conflicting/invalid limits fail. There is no hidden 16K cap.

Responses and SSE tool arguments are forwarded byte-for-byte. Disconnect detaches
the consumer and drains the upstream with bounded observation buffers, retaining
the permit until terminal settlement. A successful SSE response needs `[DONE]`.
Transport failure, active timeout, ambiguous upstream server failure or missing
terminal completion quarantines a lane. There is no automatic retry or lane
recovery. Durable lane state is written before dispatch; an active lane recovered
after restart becomes quarantined. An operator must confirm actual upstream GPU
settlement before reviewed offline recovery of `gateway_lanes`. Socket abortion
is never treated as proof of GPU idleness. Usage parsing is bounded at 256 KiB;
oversized observations become unavailable without modifying transport.

### Operator reconciliation

There is no public recovery endpoint. Stop the server using the reviewed PREP
service procedure, independently establish actual upstream settlement for the
specific quarantined alias, then use an offline SQLite transaction to change
only that reviewed row from `quarantined` to `idle`. For example, for GPU0 only:

```sql
BEGIN IMMEDIATE;
SELECT alias,state FROM gateway_lanes WHERE alias='qwen3.8-27b-gpu0';
UPDATE gateway_lanes SET state='idle'
 WHERE alias='qwen3.8-27b-gpu0' AND state='quarantined';
COMMIT;
```

Use the protected data directory and obtain an exclusive transaction on
`owner.sqlite` first so a running server makes reconciliation fail. Record the
upstream settlement evidence and changed row before restarting. Do not clear
workspace quarantine as part of lane recovery, do not clear all aliases, and do
not use health/ready responses or aborted sockets as settlement evidence. No
reconciliation or VM operation was performed in this source task.

## Acceptance boundary

Two features remain **incomplete**: authoritative native background
parent/delivery settlement (awaiting SETTLEMENT-CONTRACT), and approved native
browser/search/skill tool admission (awaiting POLICY-CONTRACT). The current
quarantine/deny fallbacks are safe temporary behavior, not feature acceptance. PREP's permission/network/container boundary and the
new compaction patch still need integrated acceptance. The fail-closed behavior
and approved command admission are fixture-tested; successful native background
continuation, coding/browsing and UI vision are not claimed.


Local fixtures/builds validate source behavior, not deployed MiniMax, container
isolation, gateway reachability, live Qwen context occupancy, vision, browser
research, PDF/OCR tools, actual coding tasks, or production cancellation. Those
require root-reviewed integration and separately dispatched live acceptance.
No ai-vm services, models, credentials, lifecycle, installer, deploy or web source
are changed by this package.
