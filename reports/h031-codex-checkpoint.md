# H031 Codex integration checkpoint

September 29, 2026, execution window **08:46–10:46 UTC**. Public Sova remains in
maintenance as requested. This is not a completed Codex release.

Both workers' native CLI sessions closed cleanly by **10:35:26 UTC**. No new
execution window, model reload or baseline restoration was started afterward.

## Verified progress

- The reviewed node hardware-proof refresh and metadata corrections are deployed.
  Both 480K Qwen instances passed the ordinary deployed admission verifier.
- A retained Codex conversation resumed on its original native thread, executed
  its Python test and returned the exact saved follow-up. All three project files
  were unchanged and the new inference requests settled. This did not perform a
  new application restart; it is the continuation previously blocked in H030.
- Image startup no longer holds the shared lifecycle lock through slow native
  startup and warm-up. The deployed correction retains separate image ownership.
- A subsequent image failure exposed a second bug: a saved GPU telemetry tuple
  becomes a JSON list, so comparing it with the original Python value falsely
  reports a state change. The focused repair passed 85 affected tests, including
  the failing original representation and real-change rejection. This second
  repair is committed but **not deployed**.
- MiMo's intentional stop timed out at the client, although its native process
  subsequently stopped. A reviewed source transition now preserves both the
  original error and independent physical settlement. It is deployed.

### Actual workflow acceptance

| Case | Result and practical limit |
|---|---|
| Retained Codex continuation | PASS: real Python test, exact follow-up and unchanged files; no new app restart induced. |
| Codex to MiniMax handoff | PASS: fresh MiniMax native history, shared files and actual test execution; original history retained. |
| Both 480K Qwen instances | PASS for small normal requests on each; overlapping token-count ownership observed. No simultaneous-decode or capacity benchmark claim. |
| Shared workspace and queued Stop | PASS: queued Codex waited behind active MiniMax and cancelled before provider dispatch. |
| Active Stop | PASS for MiniMax continuation cancellation and settlement. Its shell sleep had already finished, so native process interruption remains untested. |
| Reconnect | PASS for API event-cursor replay without resubmission; browser reload remains untested. |
| PDF | FAIL: extraction and rendering worked, but the numeric answer and summary PDF were not produced. |

All six new runs settled. Final app checks recorded no active runs, pending
inference requests, task containers or temporary acceptance tickets. Existing
uncertain owners and quarantines were preserved. Earlier ordinary coding,
follow-up, deduplication, small compaction and recall passes were reused.

## Current blockers

**MiMo remains stopped.** Two normal successor starts refused `lifecycle_busy`
before creating a new owner or consuming the transition. The old settled state,
failure history and unconsumed receipt remain intact. No competing lock holder
was captured, so the historical holder is unknown. A source fixture reproduced
immediate startup refusal under a temporary lock holder. The reviewed correction
waits up to two seconds only before admission, rechecks current state and never
retries an acquired action. Review caught and corrected an initial missing-lock
regression. The final correction passed 62 affected tests and remains
**undeployed**. Exact deployed external preparation-helper bytes remain unverified.

**Image service remains unavailable.** The native model warmed successfully, but
the false state-change check left unresolved operation/recovery ownership after
the parent exited. Warm native weights do not establish API readiness. The
reconciliation proposal preserves the exact failed attempt and settles only its
owned native generation. It has not been implemented or executed.

These lifecycle failures consumed most of this window and delayed the specialist
Codex acceptance cases. They are service admission/recovery defects; this work has
not established an inference-model or GPU performance regression.

**PDF completion remains unresolved.** Eight provider requests carried all tool
results correctly. Native image viewing reported unsupported input. The final
provider response stopped with an 83-byte planning statement; byte comparison
shows it reached Responses, native history and Sova unchanged. No answer was lost
in the adapter. That establishes incomplete termination, not the model's internal
reason for stopping. The original PDF was preserved; the missing answer and
summary keep this case failed.

Root independently viewed the retained rendered PNG after the worker reports:
the page visibly reads 3.3 V and 250 mA without clipping. This new render-only
check does not qualify the model's image understanding or missing final artifact.
An earlier unsupported reviewer attribution was corrected before publication.

Image generation/edit/child and MiMo delegation remain unqualified and their
capability gates remain closed. Healthy-lane fallback, queue saturation, fresh
restart, browser reconnect, remaining child/lifecycle combinations and unified
provider-profile work remain. See [next execution](h031-next-execution.md).

## Preserved boundaries

App source remains `2b40610`; Codex version, model weights/runtimes, context limits,
GPU placement, cooling and power policy are unchanged. All three Qwen processes,
user histories/files, two old uncertain owners and three quarantines are retained.
Image/frontier Codex capabilities remain closed. MiniMax remains the configured
default. No 950K benchmark, baseline restoration or main-branch merge occurred.

## Evidence

- [Initial source and transition review](h031-source01-20260929/REPORT.md).
- [Image ownership correction](h031-imagelock01-20260929/REPORT.md).
- [Stop and physical settlement](h031-activate01-20260929/REPORT.md).
- [Preserved timeout transition](h031-source02-20260929/REPORT.md).
- [Deployed activation and actual failures](h031-activate02-20260929/REPORT.md).
- [Serialization correction and final refused start](h031-source03-20260929/REPORT.md).
- [Proposed exact image reconciliation](h031-source03-20260929/PROPOSAL.md).
- [Final startup correction](h031-source05-20260929/REPORT.md).
- [Live workflow results and limits](h031-flow01-20260929/SUMMARY.md).
- [Machine-readable checkpoint](h031-codex-results.json).

Source fixtures, deployed changes and live user-workflow results are distinct.
Original failed attempts remain evidence even when a later affected case passes.
