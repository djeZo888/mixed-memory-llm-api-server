# ai-harness 0.0.2 — authorized candidate and acceptance plan

Authorized on 2026-09-22. This extends the [0.0.1 plan](PLAN-v0.0.1.md) for the
requested UI and additive server/event contract. Existing infrastructure,
models, context/output limits, access policy and worker ownership remain.
The [acceptance report](docs/acceptance-v0.0.2.md) distinguishes source/fixture
observations from any later deployed/live results.

## Requested behavior

1. Separate actual emitted intermediate/thinking updates from final replies using
   native message/turn metadata. Show progress during work, collapse after a
   classified final answer, and retain its text when reopened. Do not infer
   hidden reasoning or historical phases from prose.
2. Group activity and files by reply/run. Merge tool lifecycle updates by stable
   identity, retaining available command, URL, duration and detail. Display
   validated child lifecycle counts, with unknown distinct from zero.
3. Show working, queued, compressing, cancelling and terminal states outside
   composer buttons. Active-run follow-ups queue for the next turn; no native
   mid-turn steering claim. Late events remain with the originating run.
4. Show zero context only for a genuinely untouched conversation. Preserve
   unknown/stale observations and the fixed 480,000-token context.
5. Preview generated SVG/images as image resources, with individual downloads
   and a per-reply ZIP for multiple files. Preserve proven shared membership and
   honestly label unknown legacy ownership; never execute SVG as inline markup.
6. Support composer drop/upload, visible attachment names/downloads on submitted
   user messages, Enter newline and Ctrl/Cmd+Enter submit with a visible hint.
   Preserve drafts on failed submission and protect composition event handling.
7. Use Europe/Ljubljana and Ljubljana, Slovenia metadata with a fresh current
   instant. Display timestamps with automatic CET/CEST, never a fixed offset.
8. Display version 0.0.2 and preserve v0.0.1 source, release evidence and limits.

## This bounded phase

H002-UI-FIXTURES starts from root-integrated candidate
`eb8387c9431b83a50d3c782b45ab7468f8f5a173`. Worker2 builds its static web assets
and runs a focused synthetic fixture campaign at desktop 1440 and mobile 390.
Only the task-owned, rootless Linux Chromium container and its internal
127.0.0.1 fixture server may be used. There is no production app, gateway,
inference or ai-vm access and no deployment or service change in this phase.

The fixture reuses the approved utility image
`sha256:84ea979312f7743d9ab789465aae7adde92f97d6169744ec7b63776a9482b227`
with the candidate assets, not the image's historical web build. Existing
Node/Chromium/Playwright and the approved sandbox profile are reused without
rebuilding, retagging or installing a toolchain. The container has no network,
host ports, broad mounts or sandbox bypass. Actual versions and launch controls
are recorded in task evidence. This utility image is not a release-runtime claim.

Screenshots are marked FIXTURE / NOT LIVE INFERENCE. Evidence distinguishes
browser observations, unit/source proof and unexecuted cases. Synthetic fixture
events, attachment bytes and child summaries do not prove backend/native
behavior. The fixture ZIP is an empty archive used only to check routing.
All live engine/server behavior, real archive contents, native child counts,
user-history migration and production rendering remain NOT_TESTED here.
UI defects are reported to root for source-owner coordination; this task edits
only its release-document paths and evidence drivers/fixtures.

## Later independently authorized acceptance

Root reviews the combined final source/runtime and coordinates any deployment
at an idle point, with a consistent metadata backup and prior immutable release
preserved. User conversations/files and active work must remain untouched.
Only a fresh, separately assigned live gate may permit actual browser/API work
against production; the prepared evidence driver defaults to NO_LIVE_GATE.

The later campaign uses owned new test chats to check real intermediate/final
boundaries, tools and native child counts, per-reply SVG/files and ZIP contents,
attachment round trips, queued follow-ups, refresh continuity and local time.
Existing user-history migration/rendering needs separately authorized read-only
review. Do not repeat GPU, full-context, long-output or the broad v0.0.1 suite.

Mac-Orchestrator coordinates/reviews/synchronizes. Fresh isolated worker tasks
implement/build/test; only assigned tasks contact hosts. Keep native session IDs,
source/image identities, compact receipts, screenshots and cleanup records.
No model/lifecycle changes, GLM integration, installer, new accounts, credential
changes, push or deployment are authorized by this fixture/document phase.
