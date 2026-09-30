# H012 — launch the prepared Flash-only 1M trial

**Current status:** the fresh H012 attempt is processing the 1M input. See the
[launch receipt](../reports/h012-flash1m-20260927/LAUNCH-RECEIPT.md) for current
unit/path identities, the two launch repairs and the next-check commands. The
initial H011 identities and intermediate archive below are retained history.

User authorization, 27 September 2026: start the Flash 1M test now, confirm that it
is running correctly, then end the turn. The user will return after about one
hour. This explicitly permits a separate Flash-only test despite the H011
four-way cooling hold. No concurrency or Qwen/image inference is authorized.

## Execution

Mac-Orchestrator coordinates and reviews. Worker1 uses a fresh remote Codex CLI
session and an isolated copy, with a 25-minute launch-session budget. Reuse the
already reviewed H011 candidate, which passed 29 offline checks; do not rebuild
the runner or repeat completed tests. The unchanged prepared runner intentionally
uses its H011 paths and `h011-manual1m.service` name.

Initially prepared archive SHA256:
`19c2db15c8f5cd91ced676724a055787223448e21cad98053a18c5865d038088`.
Source/reproduction: [prepared runner](../reports/h011-worker2-20260927/manual/README.md).
That document's old no-launch statement is historical; this direct user request
supersedes it for this bounded, isolated trial.

### Launch correction

The first start was refused before creating an owner record, systemd job or
candidate. The start function held the lifecycle lock, then tried to acquire it
again while saving its receipt. Worker1 reproduced the failure with the real
lock. A narrow correction borrows the outer lease and clears that reference in
`finally`; all runtime and resource guards remain unchanged.

Four focused real-lock checks passed: the original failure, corrected dispatch,
cleanup after a dispatch error, and refusal of an existing owner. Root reviewed
the exact diff and source manifest before authorizing guarded restaging.

Corrected archive SHA256:
`df127011181e4bf195f10b66f0082b1d52b7de0570dffab70be779b553ab88c0`.
Corrected `manual.py` SHA256:
`94de4735a332889050abcfb142b7b4994be6fc0cb2dd125d254420cefea2d00c`.
Manifest SHA256:
`d4168973e2ac0de8ae00bd8820ada39914e22aa53142f494e03ffc819431060b`.
The original archive and refusal evidence are retained. This repair does not
constitute a repeated inference request: the first attempt never dispatched one.

### Live launch

Refresh actual Sova pause, settled native ownership, Flash 480K readiness,
hardware/cooling/latches, protected source/model/runtime pins and storage guards.
Keep the other three models loaded and idle, without inference. Stage only the
exact reviewed source using existing registered-storage protections; never
overwrite an existing candidate or owner record to force a retry.

The independent job owns original Flash halt, allocation of the temporary
1,048,576-token profile on localhost:30011, its short validation request, native
tokenizer parity and the main request: exactly 1,000,000 input tokens with a
1,024-token output ceiling. Retain the unchanged 300-second forward-progress
watchdog, two-hour main-request limit, 85°C cutoff, 7% free GPU reserve, 15% host
reserve and 650 GiB no-swap cgroup.

## Handoff

Confirm actual main request dispatch and multiple advancing native prefill
chunks, together with healthy current telemetry. A pre-send `REQUEST_RUNNING`
record, CPU activity or HTTP connection alone is insufficient. Save source/job/
container identity, exact input count, request start/deadline and status command.
Then exit the paid worker session immediately; the independent job keeps running.
Do not wait for the long inference result or claim it has passed.

Verified PASS retains 1M loaded for the already-authorized production promotion
after result review. Failure/timeout confirms exact candidate stop before the
original owner's 480K recovery. Unknown ownership means quarantine, never replay.
Sova stays paused until result review. No automatic wakeup is needed: the user
will return. No new models, runtimes, ECC/power changes, installer or unrelated
work belongs to this task.
