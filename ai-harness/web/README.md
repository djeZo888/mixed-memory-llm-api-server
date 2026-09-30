# ai-harness web 0.0.2

React/Vite frontend for the additive H002 UI/server contract v1. Single shared
workspace, same-origin `/api`; no credential, model selector or inference budget
setting is embedded. This source task changes only `ai-harness/web/**`.

## Build and verification

Use Node 24 or newer. From this directory:

```sh
npm ci
npm test
npm run typecheck
npm run build
```

The backend serves `dist/`. Build assets use absolute root paths. Local dev binds
`127.0.0.1:5193`; preview binds `127.0.0.1:4193`, both strict. These commands do not
supply an API. No server/deploy/native source is included here.

```sh
PLAYWRIGHT_CHANNEL=chrome npm run test:browser
```

Browser tests use installed Chrome and an isolated local HTTP/SSE fixture at
`127.0.0.1:4193`. They refuse an existing server. Fixture data is under `tests/`,
never imported by application code. Set `H001_WEB_EVIDENCE` to the desired external
evidence directory. Screenshots, DOM tests and builds are fixture/source evidence;
they do not establish live inference, deployment, native lifecycle or server file
safety acceptance. No browser installation is required by the source checks.

## Exact additive contract

Older snapshots can omit every new field. Current snapshots add `runs`,
`activities`, `attachments` and `environment`. SSE adds `run: {run}`,
`activity: {activity}`, and `subagents: {runId, summary}`.

- Message `phase` is `intermediate | thinking | final | unclassified` and
  `streamState` is `streaming | completed`. `nativeMessageId` and `nativeTurnId`
  are optional. A completion message upserts the same application message ID.
  Progress stays expanded until a completed final for its run exists; it remains
  expandable afterward. Only emitted `thinking` is labeled Reasoning. Missing
  metadata remains a neutral Legacy response; text is never split by heuristics.
- Runs carry `id`, `kind`, `status`, timestamps, `finalMessageId`, `artifactIds`,
  optional `zipUrl`, and `subagents`. Run status is queued/running/cancelling or
  completed/cancelled/interrupted/failed. The composer accepts follow-ups through
  the existing workspace queue, with multiple pending IDs; it promises no live
  steering. Stop all uses the existing cancel endpoint for active and queued work.
- Canonical activities upsert by `(runId,id)`. They retain typed lifecycle status,
  name, summary, command, URL, details and emitted timestamps. Duration uses only
  emitted start/finish bounds. A main lifecycle row updates in place. When typed
  activity exists, generic compatibility tool/subagent rows for that run/kind are
  folded into Legacy events; they are retained without guessing individual IDs.
  Other legacy/error/cleanup records remain visible. Main activity is paged in
  groups of 100; the reducer never discards old activities. Tool details are
  bounded at 6,000 characters without truncating assistant message history.
- `Summary {known,active,completed,failed,cancelled,updatedAt?}` is authoritative.
  Unknown counts stay unknown, and prose/tool rows never become active agents.
  A zero count is not evidence that the parent/final answer has settled.
- Artifacts carry optional nullable `runId`, `messageId` and `previewUrl`.
  Exact IDs associate messages, activities and files to a reply. Queued user turns
  cannot steal a late response from the previous run. Conflicting or unknown
  associations remain in a clearly labeled history section.
- Snapshot attachments resolve each USER message's `attachmentIds`, displaying
  its uploaded filename and authoritative download link. Legacy missing metadata
  is explicit. Successful local uploads preserve metadata immediately.

Reviewed same-origin file routes:

```text
GET /api/artifacts/:id/download
GET /api/attachments/:id/download
GET /api/files/:id/preview
GET /api/sessions/:id/runs/:runId/artifacts.zip
```

Preview/upload/ZIP URLs must exactly equal their encoded-ID route, with no query,
fragment, credentials or arbitrary origin. Artifact download uses its registered
ID, ignoring arbitrary old `downloadUrl` values. More than one associated file and
an authoritative run `zipUrl` are required for Download all ZIP. Previews use `img`
with failure fallback and preserved individual downloads; SVG/HTML is never
injected into the page. Markdown raw HTML is disabled and Markdown images remain
inert placeholders. Tool text/commands are escaped; tool links require explicit
public HTTP(S) hostnames without credentials, local names or address literals.
This link check is not DNS verification and causes no automatic URL fetch.

## History, context and input

Snapshots are canonical at their highest returned event ID. Snapshot text does not
replay old deltas; only events after that watermark append text. Buffered SSE and
reconnect resync are idempotent, and stale responses cannot replace newer state.
Local storage holds only the selected opaque session ID. Browser cleanup aborts
GETs and closes EventSource; it never cancels server work. Original conversation
history stays available after handoff/compression.

A fresh server `source: "empty"` context displays `0 / 480,000 tokens · 0%`.
Missing old/interrupted context never becomes zero. Once a turn exists, an old
empty-source zero waits for a new estimate. Measured, estimated and stale context
remain distinct; input/output share the fixed 480,000-token window. The UI imposes
no inference output cap. All visible timestamps use `Europe/Ljubljana` via Intl,
including automatic CET/CEST, while preserving original ISO `dateTime` attributes.

Enter inserts a newline. Ctrl+Enter and Cmd+Enter send, with IME composition
protected. Attach and drag/drop share serialized validation/upload handling,
per-file feedback, duplicate guards and the existing 50 MiB server limit. PDF and
source/text files are accepted; images require explicit health or qualified image-reference capability. The
server owns content validation. Drafts survive failed sends, but switching chats
still discards local unsent text; completed uploads stay with their session.

First-party source is MIT licensed. Third-party packages retain their licenses.

## H003 image workflow (source/offline)

Image cards remain attached to their stored `runId`, including when approval or
completion happens after the assistant turn ends. The browser loads
`GET /api/sessions/:id/image-jobs` on initial selection and reconnection, and
upserts persisted `image_job: {job}` SSE events. Failed image-status reads preserve
ordinary chat and last known cards with a visible refresh notice. Current state,
queue position, elapsed time, dimensions, seed/model, source fingerprints and
concise errors are displayed without invented percent progress.

Canvas approval shows each source's original dimensions, the proposed canvas and
the reason, including exact working dimensions and all four padding values. Only
an explicit browser click fetches `/api/sessions/:id/image-jobs/:jobId/approval-token`
and then posts `{decision:'approve'|'reject',approvalToken}` to the approval route.
The token is an ephemeral request-local value and is never cached in application
state or exposed to model records. Failed decisions are not automatically replayed;
each explicit retry fetches a fresh token. The browser does not send new
sizes, references, prompts or an approval boolean. Cancelling an active image
shows its saved running/saving state with draining intent until the host settles;
closing the browser or ending a text turn does not cancel image work.

Generated images retain existing preview, download and reply ZIP links. Use for
next edit selects the current session's artifact ID in a separate composer list;
message submission adds `imageReferences` without changing upload `attachmentIds`.
Successful sends clear only the submitted selections, and originals remain in
reply files. Missing or disabled edit capability profiles disable reuse. The
client never substitutes generation for an unavailable edit. Image uploads are
also enabled when the image service advertises qualified reference profiles.

`GET /api/image-capabilities` returns the unchanged reviewed upstream JSON. The
browser reads `profiles` entries with `operation`, `size`, `references`,
`transparent`, `evidence_sha256`, `native_size` and `crop_bottom`; unknown,
malformed or transparent profiles do not enable editing. Availability follows
qualified operation/reference counts, while `ready`, `admitting` and `busy` are
separate service states. The upstream `defaults.size` does not change the harness
1920x1080 generation default.

Job size fields use `WIDTHxHEIGHT`. Sources carry
`{referenceId,fileId?,name,sha256,width,height}` and adjustment sources add exact
`workingWidth`, `workingHeight` and `padding:{top,right,bottom,left}`. Every job
has a positive integer `revision`. GET, SSE and action responses share revision
ordering: lower/equal revisions cannot overwrite a newer card, while a newer
running-to-queued revision is a valid known-non-admission retry. Browser
approval/cancel responses use the exact `{job}` envelope. Internal `outputPath`
is omitted from browser records; preview/download uses the saved artifact ID.

Focused source checks:

```sh
npm run typecheck
npm run test -- tests/image-jobs.test.ts tests/store.test.ts tests/api.test.ts tests/composer.test.tsx
npm run build
PLAYWRIGHT_CHANNEL=chrome npm run test:browser -- tests/image.browser.ts
```

These local fixtures do not establish deployed image generation/editing,
resident-model behavior, GPU cancellation or backend geometry qualification.

Browser approval-token fixtures cover click sequencing and errors only. Worker1
owns protected token issuance and proxy/origin policy; deployed security remains
NOT_TESTED by this source task.
