# ai-harness server 0.0.2

Node 24 / TypeScript / Fastify / SQLite control plane and two-lane inference
gateway for the approved ai-harness plan. This directory owns the server only;
PREP owns the engine container/launcher and WEB owns the frontend. First-party
source is MIT under this directory's LICENSE. No hosted MiniMax account is used.

## 0.0.2 source contract

Snapshots retain all prior fields and add `runs`, `activities`, `attachments`,
`environment`, and an explicit atomic `watermark`. Messages carry native
identity and `phase` (`intermediate`, `thinking`, `final`, `unclassified`). Actual
emitted thought text is a separate message/channel; no reasoning is inferred.
The native metadata bridge is `mcode/session/message_update` schema 1. A final
candidate requires a fresh exhaustive native settlement, the last root turn,
and a real final kind/terminal finish reason with visible text. Publication waits
for the app run's final cancellation check and commits final metadata, file
associations, run state and events together.

`run`, `activity` and `subagents` events restore run queues and upsert activities.
Tool inputs expose only bounded, redacted recognized fields, including native
browser `{action,input:{url}}`. Child counts require a complete native snapshot
and a per-run historical baseline; missing/truncated capability remains unknown.
Legacy merged messages remain unclassified. Historical file/activity grouping
uses existing event run IDs; historical commands and phases are not fabricated.

Original `messages`/`files` table layouts are unchanged. Additive `h002_*`
companion tables preserve old positional inserts. New file names retain an ASCII
fallback in `files.name` for old-release download headers; companion metadata
retains the sanitized original Unicode name. Existing rows are not renamed.

Downloads use `/api/attachments/:id/download` and the existing artifact route.
`/api/files/:id/preview` serves allowlisted image MIME types under sandboxed CSP
and `nosniff`; clients must use an image element, never inline SVG markup.
Per-run `/api/sessions/:id/runs/:runId/artifacts.zip` streams only registered
owned snapshots, limited to 100 files/256 MiB. Names are unique and path-free;
reads retain the same symlink/hardlink/containment guards. Downloads and previews
do not publish or register files.

An untouched chat alone has `context.source="empty"`, used 0; enqueue/handoff
invalidates that value. Environment metadata and each native request's clock
are computed freshly for IANA `Europe/Ljubljana`, Ljubljana, Slovenia. Source
passes that timezone through the real Podman argument list and ensures zoneinfo
in the image. Native Chromium inherits this process environment. Effective
Linux/browser timezone, native image build and coordinated deployment remain
separate acceptance gates; source tests do not establish them.

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

The host launcher's `HOME` is the canonical existing home from `userInfo()` for
the ordinary service account, checked for ownership; ambient `HOME` is ignored.
No host `MINIMAX_DATA_DIR` is passed. The reviewed launcher sets container-only
`HOME=ABS_PROFILE/state/home` and `MINIMAX_DATA_DIR=ABS_PROFILE/state` explicitly,
mounting only profile/workspace. The host home is never a container mount.

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

Before launch the server creates a guarded private `profile/state` directory and
atomically writes mode-0600 `profile/state/permission.json`. PREP sets
`MINIMAX_DATA_DIR=ABS_PROFILE/state` and `HOME=ABS_PROFILE/state/home`; the sole
profile mount remains `ABS_PROFILE`, leaving the native migration lock inside
that mount. PREP preserves the permission file without broad allow rules.
Native `permissionMode=default` is selected and verified through the SDK.

Native read/write/edit/grep/glob/bash requests go through ACP permission checks.
File mutations are workspace-scoped. Read-only container assets under
`/opt/ai-harness/skills` and `/opt/ai-harness/tools` are admitted without host
existence checks or host callbacks; PREP supplies read-only mounts without
escaping links. The authorized native bash schema allows autonomous scripts,
pipelines, substitutions, builds, tests, package commands and PDF helpers.
Command-string recognition is not a sandbox or a network firewall. The actual
boundary is PREP's rootless container, fixed workspace/profile mounts, read-only
image, absence of host credentials/sockets, and fresh browser. Host ACP filesystem
and terminal capabilities remain disabled.

The reviewed native browser uses ask rules plus actual tool-name/action/input
validation. Public navigation, read/query, screenshot, scroll, hover, wait and
research clicks are admitted; form entry, uploads, arbitrary keys, unknown
operations and managed publishing/login/deployment tools are denied. A separate
trusted engine instruction limits clicks to public research/navigation/downloads
and prohibits login, forms, publish/send/delete/purchase. Lexical URL checks do
not establish DNS/network isolation. The pinned screenshot schema is inline-only;
unsupported file fields are not invented.

The `skill` tool admits exactly technical-research, code-investigation,
calculations, technical-testing, pdf, code-review and control-in-app-browser.
Only the direct `mcp__searxng__searxng_search` adapter is admitted. PREP/RUNTIME
sets `mcpToolSearch:{enabled:false}` to expose it inline; `tool_search` and
`mcp_invoke` wrappers are denied. Unreviewed global MCP, Matrix and plugin
catalogs must stay disabled: an empty ACP mcpServers list alone does not disable
all native discovery. Native task children remain enabled and use the root
chat permission callback. SDK fixtures establish admission behavior, not actual
browser downloads, helpers, container isolation or research acceptance.

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
Separate workspaces can run concurrently. The native bridge must advertise
`mcode/session/settlement/get`. The original prompt remains attached through
background root continuations and output drain, then supplies the versioned
`minimax-code/settlement` receipt. The server strictly validates native instance,
root session, initial run and ordered root-turn identities, exhaustive status,
and a fresh get using the expected instance/run before releasing the workspace.
An exhaustive cancelled receipt may have a unique non-null run ID and no root
turn IDs only when Stop precedes initial native root-turn admission. This is
cancellation, never successful settlement: settled receipts still require the
first real root turn to equal the run ID. Fresh identity and stale-run checks
also apply to early cancellation, allowing a later ordinary prompt safely.
Children are progress only. Background-task presence alone does not quarantine a
valid settled run. Missing/stale/foreign/malformed/non-exhaustive receipts, unknown
state or pending projection cannot authorize success. No timer-idle inference is
used. Cancellation requests root/child stop and requires settlement proof; a
notification ACK alone is insufficient. Browser SSE disconnect never cancels.

Unknown native completion retains partial history and interrupts the run.
Requested launcher SIGTERM followed by exit **0** is PREP's verified exact-container
cleanup proof and may release a live workspace quarantine; it cannot turn that
run into successful prompt completion. Cancelled work stays cancelled; ordinary
errors stay failed. Exit143, cleanup-failure125, a closed ACP pipe, unrequested
parent exit and final SIGKILL do not prove cleanup. Restarted unfinished runs
quarantine their workspace and never replay prompts/tool effects. Native load
must suppress interrupted delivery or report unknown before admitting a new
prompt. Durable restart quarantine has no public bypass: an operator must
independently verify descendants settled before a reviewed offline repair.
Deletion first cancels work and waits for confirmed settlement before hiding
metadata; project files remain. Uncertain deletion stays visible. Handoff asks
the real engine for a summary, creates a new chat sharing the workspace, retains
the old chat/history, and seeds the new engine's first prompt with that summary.

## Public API

JSON errors are `{error:{code,message}}`. IDs are opaque; timestamps are UTC ISO.
The shapes match the task's `COORDINATION.md` v1 contract.

Native CLI slash commands are unsupported in v0.0.1. Message submission returns
400 `unsupported_slash_command` before enqueue or any stored/engine mutation for
`/help`, `/new`, `/model`, `/status`, `/doctor`, `/context`, `/skills`, `/mcp`,
`/usage`, `/compact` and the direct slash aliases of `REVIEWED_SKILLS`. Recognition
matches the pinned ACP parser: a case-sensitive complete first token at the
start of the text, with optional whitespace-separated arguments. Absolute file
paths and prose remain ordinary tasks. Phrase a normal task to use a skill;
automatic native compression remains enabled.

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

The SERVER halves of the reviewed settlement, compaction and native-tool policy
contracts are implemented and tested with the official SDK. PREP/RUNTIME must
integrate the matching native settlement/compaction patches, profile layout,
fixed inline search roster, verified launcher cleanup and >=151-minute SDK plus
Undici gateway transport. Engine retries after admission/compression failure are
an integration dependency; the server/gateway does not replay or retry requests.

Local fixtures/builds validate source behavior, not deployed MiniMax, Linux,
container isolation, gateway reachability, live context occupancy, UI vision,
browser research/downloads, PDF/OCR helpers, actual coding workloads or production
cancellation. Configuration and the separate bounded capability probe establish
480000/65536 settings/acceptance, not actual occupied480K or full64K generation.
Those require root-reviewed integration and separately dispatched acceptance.
No ai-vm services, models, real credentials, lifecycle, installer, deploy or web
source are changed by this package.

## v0.0.3 host image broker (source candidate)

`main.ts` loads the existing protected inference key once and constructs the fixed
private image adapter. `image-broker.ts` persists jobs, revisions, canonical request
hashes, source/ancestor seed provenance, immutable reference hashes and admission
before dispatch. SQLite companion tables preserve existing chat/file schemas.
The broker owns one image lane with eight waiting jobs and a30-minute queue
deadline. Native transport has900 seconds to headers and30 seconds to consume the
bounded response; host preparation/codecs and saving have bounded deadlines.
Only reviewed busy429 can retry, honoring Retry-After and the original deadline.
If all eight waiters are occupied on429, the non-admitted job fails explicitly
with `image_queue_full`; it is never automatically resubmitted. Ambiguous errors
are never replayed, and the lane stays quarantined until authenticated readiness
proves ready, admitting and not busy. Restart interrupts every unresolved job.

The backend's capability JSON passes through unchanged. Missing operation/refcount
profiles mean unavailable. Generation defaults to1920x1080; edits use exact source
geometry when qualified, otherwise stage aspect-preserving downsize/padding for
browser approval. The backend exclusively owns any FHD bottom8 transport mapping.
Sharp0.35.4 is pinned with integrity-locked native dependencies; PNG/JPEG are fully
decoded, oriented, converted to sRGB and flattened on white. Originals and normalized
copies are separate host-only snapshots. Output must decode as one opaque PNG at
exact public dimensions; no native URLs, errors or encoded pixels leave the host.

Image gateway routes reuse the existing session token; current run/workspace come
from the text broker. `outputPath` is relative and appears only in internal job
results. Browser/SSE records omit it and identify owned artifacts by id. Optional
artifact `image` metadata records jobId, dimensions, model, seed and output hash.
Model provenance records the exact capability-selected model. If upstream returns
its optional effective seed, it must equal the persisted submitted seed; mismatch
fails and never silently replaces the requested seed. Known source/ancestor seeds are excluded from random
seed selection; explicit collisions fail with `source_seed_collision`. Imported
images without retained provenance cannot guarantee collision detection.

Approval capabilities are browser-only and bound to immutable job/input/adjustment;
see [runtime setup](../deploy/RUNTIME.md#v003-host-image-broker-and-browser-approval-capability).
The separate proxy secret is never passed to an engine. Main and ordinary worker
image tools supplement native permission checks; native explore/verifier ceilings
remain owned by engine packaging. No model-supplied approval flag is recognized.

Normal turn completion and client disconnect leave image work alive. Stop also
checks detached jobs while text is idle. Dispatched cancellation retains ownership
until settled. Late cancelled/deleted-session output is saved internally with its
original run and no revived assistant text. Managed workspace output paths are
excluded from later text artifact discovery. A failed workspace copy still retains
the authoritative artifact and provenance. Workspace-selected next-edit copies
preserve attachmentIds semantics and expose explicit relative paths to the engine.

Focused offline checks (no startup, credentials, service contact or inference):

```sh
npm run typecheck
node_modules/.bin/tsx --test --test-timeout=15000 test/image-broker.test.ts test/image-upstream.test.ts test/image-integration.test.ts test/policy.test.ts
```

Fixtures use a real local codec and fake IPv4-loopback HTTP upstream. They do not
qualify editing fidelity, deployed geometry profiles, Linux codec installation,
nginx runtime ACLs or actual engine/browser reachability. Those remain separate
root-reviewed activation/acceptance work.
