# H012 — launch the prepared Flash-only 1M trial

User authorization, 27 September2026: start the Flash1M test now, confirm that it
is running correctly, then end the turn. The user will return after about one
hour. This explicitly permits a separate Flash-only test despite the H011
four-way cooling hold. No concurrency or Qwen/image inference is authorized.

## Execution

Mac-Orchestrator coordinates and reviews. Worker1 uses a fresh remote Codex CLI
session and an isolated copy, with a25-minute launch-session budget. Reuse the
already reviewed H011 candidate, which passed29 offline checks; do not rebuild
the runner or repeat completed tests. The unchanged prepared runner intentionally
uses its H011 paths and `h011-manual1m.service` name.

Candidate archive SHA256:
`19c2db15c8f5cd91ced676724a055787223448e21cad98053a18c5865d038088`.
Source/reproduction: [prepared runner](../reports/h011-worker2-20260927/manual/README.md).
That document's old no-launch statement is historical; this direct user request
supersedes it for this bounded, isolated trial.

Refresh actual Sova pause, settled native ownership, Flash480K readiness,
hardware/cooling/latches, protected source/model/runtime pins and storage guards.
Keep the other three models loaded and idle, without inference. Stage only the
exact reviewed source using existing registered-storage protections; never
overwrite an existing candidate or owner record to force a retry.

The independent job owns original Flash halt, allocation of the temporary
1,048,576-token profile on localhost30011, its short validation request, native
tokenizer parity and the main request: exactly1,000,000 input tokens with a
1,024-token output ceiling. Retain the unchanged300-second forward-progress
watchdog, two-hour main-request limit,85°C cutoff,7% free GPU reserve,15% host
reserve and650GiB no-swap cgroup.

## Handoff

Confirm actual main request dispatch and multiple advancing native prefill
chunks, together with healthy current telemetry. A pre-send `REQUEST_RUNNING`
record, CPU activity or HTTP connection alone is insufficient. Save source/job/
container identity, exact input count, request start/deadline and status command.
Then exit the paid worker session immediately; the independent job keeps running.
Do not wait for the long inference result or claim it has passed.

VerifiedPASS retains1M loaded for the already-authorized production promotion
after result review. Failure/timeout confirms exact candidate stop before the
original owner's480K recovery. Unknown ownership means quarantine, never replay.
Sova stays paused until result review. No automatic wakeup is needed: the user
will return. No new models, runtimes, ECC/power changes, installer or unrelated
work belongs to this task.
