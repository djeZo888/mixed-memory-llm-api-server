# H029 — Codex completion checkpoint

September 29, 2026. Authorized window: **01:25–03:25 UTC**
(03:25–05:25 Ljubljana). Root coordinated and reviewed; fresh bounded native
Codex CLI sessions on both Mac workers performed implementation, builds, tests
and VM operations. This was the first window of the approved completion plan.
Both final native worker sessions exited cleanly by **03:05:51 UTC**. No worker
remains running or waiting on a model job. Root completed the report/publication
within the original window.

**Outcome: infrastructure and retry fixes are deployed; complete Codex workflow
qualification is still blocked.** MiniMax remains the default and Codex remains
an optional preview. This report separates the final deployed source from the
earlier failed attempts. The feature branch is not ready to merge into main.

## Completed changes

- Slow model-status collection runs outside the shared lifecycle lock. Before
  publishing a result, the service rechecks boot, source, configuration, runtime
  identity and ownership. Model starts and stops remain serialized.
- Docker mount lists are compared independently of their return order while
  preserving every entry and duplicate. Malformed or changed mounts still fail.
- The existing dedicated Ada Qwen is recognized as an independently validated
  peer. Its presence no longer blocks recovery of the two Blackwell Qwens.
- Admission diagnostics now retain bounded failure categories, HTTP status,
  safe control error codes and phase timings, without prompts or credentials.
- Targeted control reads preserve the original observation error instead of
  replacing it with a misleading `target_unavailable` response.
- Ordinary user submissions have durable IDs. Retrying the same ID and payload
  returns the original run; a changed payload conflicts. The browser retains an
  uncertain submission for explicit retry. Intentional repeated prompts get new
  IDs. This does not promise exactly-once execution across external tools.

The application is source `2662bd08e65c3fca5ce399761f4e672fb5d8f824`, activated
at 02:42:06 UTC. Its pinned Codex binary/image and web assets were retained from
the earlier combined deployment. H028 status remains independently deployed.
The final control error-preservation patch was activated at **03:00:38 UTC**;
all 82 protected source files matched in each of three installed source roots,
and all three Qwen container identities were preserved. An earlier attempt
rolled back after a full launch-hash mismatch. Its helper compared unordered
mount lists by wire order; the revised helper avoids that false difference.
The original component-level mismatch was not retained, so its exact cause
remains unproved. Original failed evidence remains intact.

## Verification

Test counts below describe separate focused runs and overlap; do not add them.

| Check | Result and evidence |
| --- | --- |
| Control behavior | 124 focused Python checks passed; affected mount/peer checks also passed. |
| Admission source | 33 focused TypeScript checks and typecheck passed. |
| Safe transport diagnostics | 11 focused checks and typecheck passed. |
| Targeted control errors | 24 focused checks passed, including original safe error/status retention. |
| Deployment helper | 16 finite checks passed for order independence, changed fields and malformed mounts. |
| Durable submissions | 76 focused server and 56 browser checks passed; builds passed. |
| Actual lifecycle-lock occupancy | One warm status refresh took 9.086 s overall; the complete observed lock hold was **39.7 ms**, sampled every 2 ms. |
| Model readiness | Two Blackwell Qwens recovered at **480,000** configured/allocated tokens each; Ada Qwen remained ready at **200,000**. |
| Live submission retries | Two actual interrupted runs: active and terminal same-ID replay returned the original; changed text, attachment IDs and image references each returned 409. No duplicate dispatch. |
| Completed-run replay | Covered by fixtures; **not tested live** because neither new tool task completed. |
| Ordinary Codex tool task | **Failed before generation** in both attempts described below. |
| Follow-up, PDF and compaction | **Not tested** in this window because the prerequisite tool task failed. |

One supplemental gateway run retained an unchanged baseline failure in a textual
source-order assertion; its runtime drain assertions passed. This is not reported
as an entirely passing suite.

## Remaining failure

The first ordinary coding request passed both initial lane checks, then failed
on a control read before tokenization. Old records classified it only as
`transport`; its exact subtype cannot be recovered.

After the safe diagnostic update, a new run of the unchanged fixture again
passed both initial lane checks. It reached the tokenizer and locally validated
its response, then the final control check returned **HTTP 409,
`target_unavailable`**, after 9.357 s. The tokenizer reachability is established
by the exact source path; its raw count was not retained. No model generation,
tool call or artifact edit began. Both failed runs settled and remain preserved.

The final control patch removes the demonstrated error-masking defect. It does
not, by itself, repair or explain the underlying intermittent observation failure.
The final bounded diagnostic sequence is recorded separately below; it cannot
retroactively turn either failed application workflow into a pass.

### Final diagnostic sequence

At 03:02:49 UTC, the final read-only verifier sequence captured **HTTP 409,
`lifecycle_busy`** for Qwen0's initial control read after 9.547 s. The parallel
Qwen1 qualification passed. The sequence then stopped; both planned count
brackets were not reached. It made six GETs, no tokenizer or generation request,
and no retry. The sequence settled at 03:02:58 UTC.

This exposes a current lifecycle-lock rejection. The code attempts a
nonblocking publication lock after completing status collection; a busy lock
is projected as this safe error. The competing holder was not captured. This
does not prove which error caused the earlier masked response, nor establish
that all intermittent admission failures share one cause.

## Time spent and next work

Most of this window went into the shared prerequisites: repairing lock occupancy,
recovering Qwen services alongside the new Ada, deploying reviewed source with
identity checks, and tracing the intermittent admission failure. One deployment
was rolled back after a launch-hash mismatch; its helper's order-sensitive mount
comparison was then corrected.
New diagnostics now distinguish transport failures from rejected control state.
No time was spent repeating GPU benchmarks or the 950K context test.

The next bounded task should first capture the competing lifecycle-lock holder
and implement bounded publication scheduling that tolerates brief contention
while retaining current identity checks and hardware-guard access. Keep slow
collection outside the lock; do not substitute stale readiness or a blanket
timeout increase. Then pass the same ordinary coding task plus follow-up through
the actual app. Only after that:

1. Complete the retained PDF extraction/summary-PDF workflow and small
   compaction, recall and cold-resume case.
2. Recover MiMo and the image service, then qualify delegation, image generation
   and guarded editing through normal chats before opening Codex capability gates.
3. Finish shared provider profiles, with an explicit 200K budget for Ada child
   tasks and the existing 480K profile for main Qwen chats.
4. Complete cross-engine handoff and the remaining queue, cancellation,
   reconnect and restart acceptance.

## Preserved state and limits

- Histories, files, existing native sessions and historical uncertain owners and
  quarantines were preserved. Worker2 checked 36,613 prior rows across 25 tables,
  with separately documented startup reconciliation exceptions.
- All new accepted work settled; no new generation or image job remains running.
- MiniMax remains default. Codex image and frontier capability gates remain closed.
- MiMo remains selected but unavailable; the image service remains stopped.
  They were not recovered in this window. Three Qwen services are resident.
- The added Ada is not yet part of normal harness routing.
- Model weights, runtime pins, GPU placement, fan, power and ECC policies were
  preserved. No capacity/stress test, driver update or full-context test ran.

## Evidence

- [Machine-readable checkpoint](h029-codex-results.json).
- [Control deployment and readiness](h029-core01-20260929/README.md).
- [Control tests](h029-core01-20260929/TESTS.md).
- [Diagnostic investigation](h029-admission02-20260929/README.md).
- [Initial control update rollback](h029-controldeploy02-20260929/README.md).
- [Final control deployment and exposed lock rejection](h029-finalcontrol03-20260929/README.md).
- [Worker2 deployment and live acceptance](h029-worker2-20260929/README.md).
- [Approved work order](../ai-harness/PLAN-CODEX-COMPLETION-20260929.md).
- Durable task/session records and private traces remain under
  `orchestration/tasks/H029-20260929` on Mac-Orchestrator and the corresponding
  isolated task directories on the workers. Credentials and raw private
  application traces are excluded from Git.
