# H021 — optional Codex preview

## Current checkpoint

September 28, 2026, 07:50 UTC. Codex 0.158.0 is deployed as an optional
new-chat engine. MiniMax remains default; existing conversations retain their
engine, history and files. Final tool/lifecycle acceptance and central engine
status integration are in progress.

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
| Public research | 41.1 s | Pending | MiniMax used search and read the linked primary source |
| PDF extraction/creation | Pending | Pending | Acceptance in progress |

All six coding artifacts were downloaded and executed against the unchanged
regressions in a separate rootless Linux container with networking disabled.
The container was removed after verification. Expected pre-fix test failures
remain in the evidence. MiniMax's research task encountered a `web_fetch`
failure and completed using its existing browser within the same turn.

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
  tests. The live Codex image workflow is still pending.

## Known limits

- Codex currently uses the qualified Qwen0 lane. Qwen1 has stale control-generation
  metadata; it has not been accepted by bypassing that check. MiniMax's existing
  pool is separate from this Codex qualification limit.
- Native image/audio/video recognition is unavailable in the Codex preview.
  Specialist image generation/editing is a separate tool capability.
- MiMo live Codex acceptance is deferred while the independent test owns it.
- Local-model recall after compaction and a real child-agent workflow are still
  pending. Scripted/native mock evidence is not substituted for those checks.
- An early real-Qwen stream decoding failure remains unproven in cause. Later
  successful cases do not erase it. The new protected diagnostics record only
  bounded, static error codes and ownership IDs, without prompts or credentials.

## Release and recovery

Codex executable, source and generated schemas are pinned to 0.158.0 /
`064c6b8c737f5b41d171fdda80bd9ef10ad06eb3`. Existing rootless isolation,
task-scoped gateway credentials and global inference admission are reused.
No hosted OpenAI inference, login or search fallback is configured.

The final release will restore the normal 65,536-token output ceiling on both
engines, retain Qwen's 480,000 context and Codex's 400,000 compaction threshold,
and expose current engine metadata in central status. Old releases, service
configuration backups, a consistent database backup and private evidence remain
available. No automatic rollback or replay is performed when task settlement is
uncertain. Publication remains on the feature branch and draft PR10.
