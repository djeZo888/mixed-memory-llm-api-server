# H021 — optional Codex preview

## Current checkpoint

September 28, 2026, 10:11 UTC. Codex 0.158.0 is deployed as an optional
new-chat engine. MiniMax remains default; existing conversations retain their
engine, history and files. Coding, public research, native child delegation,
cold resume, real Stop and same-chat follow-up have passed bounded live checks.
**Codex image tools are disabled after the unchanged image test failed again.**
Use MiniMax for images and the tested PDF workflow. This is a controlled preview,
not full feature parity or production acceptance.

Open Sova, choose **Harness: Codex (preview)** and then **New chat**. Existing
chats keep their original engine. Inference uses local Qwen, with no OpenAI
model login or hosted inference fallback.

The independent MiMo near-950K test was neither inspected nor changed. MiMo
dispatch remains held in Sova to avoid competing with it. Its previous
MiniMax HTTP400 issue remains separate unresolved work.

## Completed real-task comparison

Identical fixtures, Qwen0, 480,000 configured context and a temporary 1,024
output-token ceiling per request. Cases ran sequentially through the existing
shared queue; no automatic provider retries or manual prompt corrections.
Engine instructions and tool catalogs differ. These are single functional
runs, not throughput or model-quality benchmarks.

| Task | MiniMax completion | Codex completion | Independent result |
|---|---:|---:|---|
| Python boundary fix | 47.5 s | 157.2 s | Both passed original tests |
| C++ bounds fix | 88.8 s | 171.7 s | Both compiled with warnings as errors and passed original tests |
| Node.js async validation | 49.9 s | 165.5 s | Both passed original tests |
| Public research | 41.1 s | 67.4 s | Both used search and read the linked primary source |
| PDF extraction/creation | 84.8 s | 144.9 s | MiniMax passed; Codex failed to produce the requested summary PDF and numeric answer |

All six coding artifacts were downloaded and executed against the unchanged
regressions in a separate rootless Linux container with networking disabled.
The container was removed after verification. Expected pre-fix test failures
remain in the evidence. MiniMax's research task encountered a `web_fetch`
failure and completed using its existing browser within the same turn.

The first Codex PDF attempt recovered from two relative-workspace argument
errors and successfully extracted and rendered the source. It then ended with
“Both operations succeeded. Let me visually verify the rendered page.” The last
response used 13 tokens; no request reached the 1,024-token cap. The native
runtime reported task completion, without a retained decoder error. The raw
upstream finish reason was not retained, so model-versus-provider cause is not
proved. The installed instructions now require absolute workspace paths and
text/metadata checks, and avoid asking the preview to perform unsupported native
vision. One unchanged-fixture repeat on the corrected release also failed: it
extracted text, announced rendering, and ended without the numeric answer or
summary PDF. That repeat used the normal 65,536-token ceiling, a changed
condition from the matched table. No third attempt or prompt rescue was made.
PDF helpers work directly, but this complete Codex workflow is not qualified.
Use MiniMax for the tested PDF workflow.

Completion times end at the application's terminal task state. Separately
recorded confirmations establish that all native work and upstream requests
settled. Their observation delays include operator scheduling and must not be
treated as measured GPU drain latency. Input/output totals in the
[machine-readable results](h021-matched-cases.json) sum all requests in a task;
they are not occupied context.

## Other completed checks

- Real pinned Linux Codex read/edit/test and resumed follow-up on Qwen0.
- Actual desktop and mobile new-chat selection, immutable engine on follow-up,
  attachment upload/download byte identity, reload/history and running-state UI.
- Direct rootless Linux search, Chromium rendering and PDF extract/render/create.
- Native fixtures for child agents and compaction; bounded context admission,
  cancellation, uncertain ownership and restart behavior have fixture coverage.
- Image tool catalog, trusted enable flag, existing broker integration and
  3,300-second queue/execution timeout passed native configuration and focused
  tests. MiniMax generated one correct 1024×576 blue-mug image in 37.2 seconds;
  inline preview, downloaded PNG, independent settlement and visual review passed.
  Codex repeatedly supplied invalid `__ns`/`ns` arguments to the no-argument
  capabilities tool. Sixteen calls failed schema validation, with zero image
  jobs dispatched. There were no operator retries or provider fallbacks.
- The actual UI Stop was exercised once on that Codex tool loop. The task became
  interrupted and inference drained. Exact container kill/removal events and
  `podman exists` exit 1 prove physical removal. The application nevertheless
  retained uncertain native ownership and quarantined that workspace. This
  historical cancellation attempt remains FAIL; the later repaired acceptance
  below passed without manually clearing stored uncertainty. An earlier Stop fixture used an
  incorrect accessible-button locator and never clicked; its naturally completed
  task and successful follow-up are not cancellation acceptance.

See the [focused results](h021-codex-focused-cases.json) for distinct outcomes.

### Cancellation repair

A later real Stop on the 15-second repair reproduced the logical failure. The
native container was removed promptly, but the single accepted Qwen request
finished 45.6 seconds after Stop. The gateway intentionally lets accepted model
work drain, so a separate 15-second cleanup deadline was incompatible with its
ownership policy. No follow-up or image request was admitted after that failure.

The next repair keeps the task in **cancelling** and its workspace occupied until
all owned inference requests settle durably. Existing request deadlines still
apply. Unconfirmed native cleanup fails immediately; shutdown stops observation
and retains uncertainty. It does not cancel native GPU work or release capacity
early. The repair passed 37 focused fixtures, type checking and a cached server
build. A new real Stop passed: cancellation remained pending for the accepted
request's 38.5-second drain, then reached cancelled with native ownership idle,
no remaining request and no new quarantine. A distinct same-native-thread
follow-up answered correctly in 19.6 seconds and survived browser reload.
See the [cancellation evidence](h021-codex-cancellation.json) and
[final live cases](h021-codex-final-cases.json). Original failed runs and their
quarantines remain recorded.

The final unchanged image test still failed, this time with two invalid
`image_capabilities` calls containing `{"__v":"0"}`. Four model requests ran;
no image job was submitted. The same turn was stopped and all ownership settled.
The simpler alias did not qualify this workflow. Only Codex's image enable flag
was then removed; strict tool argument validation and MiniMax's image service
were preserved. No further parameter sweep or prompt rescue was performed.

## Known limits

- Codex currently uses the qualified Qwen0 lane. Qwen1 failed its current-generation
  check during qualification; that guard was not bypassed. MiniMax's existing
  pool is separate from this Codex qualification limit.
- Native image/audio/video recognition is unavailable in the Codex preview.
  Specialist image generation/editing is separate and is currently disabled
  for Codex after failed workflow acceptance; MiniMax retains it.
- MiMo live Codex acceptance is deferred while the independent test owns it.
- A real native child completed successfully and reconnect preserved history.
  Its next follow-up was interrupted before new inference. A reproduced native
  resume event-ordering defect is now repaired: historical token-usage updates
  cannot claim ownership of a new turn. Seven new boundary fixtures passed;
  a distinct live cold-resume follow-up passed in 34.3 seconds, using the same
  native thread and one fresh authorized inference request. History and final
  native/gateway settlement were verified. The original failure remains recorded.
  Local-model recall after compaction is still unqualified.
- Some fresh Codex messages lack reliable phase metadata and remain unclassified.
  The current renderer labels those messages “Legacy response”; this does not
  mean the new conversation is using an old engine. Improving that label and
  qualifying reliable final/progress separation remain follow-up work.
- An early real-Qwen stream decoding failure remains unproven in cause. Later
  successful cases do not erase it. The new protected diagnostics record only
  bounded, static error codes and ownership IDs, without prompts or credentials.

## Release and recovery

Codex executable, source and generated schemas are pinned to 0.158.0 /
`064c6b8c737f5b41d171fdda80bd9ef10ad06eb3`. Existing rootless isolation,
task-scoped gateway credentials and global inference admission are reused.
No hosted OpenAI inference, login or search fallback is configured.

The final release restores the normal 65,536-token output ceiling on both
engines and retains Qwen's 480,000 context and Codex's 400,000 compaction
threshold. Central status now reads the configured engine catalog and observed
app policy, with separate version, freshness and unavailable states. It does
not infer engine readiness from a model being loaded. Old releases, service
configuration backups, a consistent database backup and private evidence remain
available. No automatic rollback or replay is performed when task settlement is
uncertain. Publication remains on the feature branch and draft PR10.

Deployed application source: `bbeec44d44c29d1b50ce8374c5d26170bc844f5a`.
The rootless Codex image and read-only policy are pinned in the deployment
receipt. Both output ceilings were verified from the reviewed source and active
unit; this did not require generating a 64K answer. The final image-flag change preserved 46 sessions, 215 messages, 70 runs and
107 file rows, image history, active selector and holds. Normal startup
reconciliation marked the two already interrupted test sessions stale, retained
their quarantines and appended six lifecycle events. Original events, failed
runs, native ownership, messages and files remained unchanged. The first
post-start check ran before those events had been appended; a later read-only
check of the same deployment passed without another restart or helper change.
Saved pre-update state retains the original failure reasons; no uncertainty
was manually cleared. The prior source-bound reader intentionally rejects the
changed unit; its positive pre-switch proofs remain retained.

The temporary Qwen1 acceptance hold was removed at 10:12 UTC after all three
new runs settled. The separate MiMo benchmark hold and all three historical
workspace quarantines remain. No model runtime, GPU or benchmark was inspected
or changed by this work.

Both final worker CLI sessions exited successfully (Worker1 10:03 UTC, Worker2
10:15 UTC). The small comparison favored MiniMax for completion time and tool
workflow reliability. Keep it as default while evaluating the explicit Codex
preview; these single cases do not justify a general model-quality claim.
