# H030 Codex completion — second bounded window

September 29, 2026. Authorized **06:53–08:53 UTC**; updated08:33 UTC.
Integration is **incomplete**. Public Sova chat routes remain in maintenance
(HTTP503); the status page remains available. The newest deployed changes stay
in place, as requested. Chats, files and historical uncertain owners are preserved.

## Completed and verified

| Change or workflow | Evidence |
|---|---|
| Control publication scheduling | A live pre-fix capture identified node-observer contention. Entry now waits cancellably within the existing one-second budget; collection/body/mutations are not replayed.21 focused checks and a post-deploy readiness read passed; that single read did not encounter publication contention. |
| Ordinary Codex coding and follow-up | Real application task, three native commands/four inference requests, independent Python/artifact assertions; follow-up on the same native thread with three requests. No inference retry. |
| Durable submission handling | Active and completed same-ID replay returned existing work; conflicting text, attachments and image references each returned409. |
| Compaction repair | Native compaction sends completed tool history with tools:[]. Adapter now validates matched historical calls separately from current new-tool authorization.35 focused checks and the original captured request passed. |
| Live compaction and recall | Corrected small manual compaction, active/completed action deduplication, same-thread four-fact recall and unchanged files passed. No large-context capacity claim. The summary misstated an incidental file size as18 rather than22bytes; exact file content remained intact. |
| Cross-engine handoff implementation | New target-engine selection transfers a summary and references into fresh native context, retaining old history/shared workspace serialization.61 affected server checks,34 web checks, build/typecheck and synthetic visual review passed. Live handoff remains NOT_TESTED. |
| Specialist qualification | Protected retained-live evidence now controls host gates and capability metadata together. Missing/invalid evidence keeps ordinary image/frontier gates closed. No artificial PASS record was installed. |
| Diagnostic visibility | Failed admission records the actual latch value, GPU identity, ages and phase. The new cold-resume failure is now distinguishable from a GPU identity mismatch. |

The combined app source `2b40610e937ad6256450e055ffd1d5647997f4c5` deployed
08:15:31.959, appPID118087; separate statusPID14480 unchanged. Native Codex
0.158.0, its image, web assets, model weights/runtimes and protected configuration
are unchanged in this deployment. MiniMax remains the default; Codex is preview.

## Remaining blockers

### Qwen admission can report unknown hardware proof

The replacement PDF workflow ran two successful provider/tool turns, then its
third generation was blocked at count/node_before. Its exact historical node
fields were not retained. No unchanged PDF retry was made.

Cold resume on the original native thread failed08:22:36 before inference.
The actual correlated rejection was count/node_after with `hardwareLatched=null`,
the exact expected GPU UUID, node age4315ms and service age3955ms. Control/native
checks passed. No model output or native Python command ran. Independent assertions
on unchanged files do not qualify this native workflow.

Public node output omits underlying proof-age/validated-boot fields, so those
new diagnostic fields are null. The exact producer-side cause is not established
by that omission or by a later healthy snapshot. Worker1 is examining a finite
contention/refresh path; the15-second proof requirement remains unchanged.

### Image startup holds the common lifecycle lock too long

Source inspection proves image startup retains the common lease through native
load and warm-up. This can starve MiMo's mandatory hardware guard. MiMo entered
HELD during the image recovery window; timing supports this explanation, but no
sample captured the historical competing lock holder. Image error recovery can
enter the same path. Avoiding another restart contains the issue; it is not a fix.

The original failure and one Docker-stop client timeout were preserved. The
daemon subsequently stopped the exact old container. A reviewed changed-state
reconciliation used the existing owner without a second stop, proved physical
release, then started the model normally. No guard or timeout was weakened.

At08:28:28, the new MiMo owner/native/proxy/canonical readback passed: RUNNING,
950000 configured capacity,65536 output ceiling, one idle slot and current
hardware guard. No inference or occupied950K test was run. Candidate flags and
ordinary specialist gates remain closed pending actual workflow qualification.

## Work still needed before release

1. Resolve intermittent Qwen admission and repeat the affected cold/PDF cases
   only after a demonstrated correction. Qualify both480K lanes and healthy-lane
   fallback without replaying already-passed ordinary coding.
2. Move slow image load/warm-up outside the common lifecycle lease while retaining
   exclusive image ownership, exact before/after identity and hardware guards.
   Test that model recovery cannot starve another service's watchdog.
3. Complete actual Codex image generation/edit/child tasks and MiMo child/tool
   continuation, plus MiniMax MiMo delegation. Open capabilities only on actual PASS.
4. Run live cross-engine handoff and the remaining shared queue, cancellation,
   reconnect, restart and offline acceptance cases.
5. Finish reviewed provider-profile unification and release documentation. The
   Ada200K instance must remain separate from480K chat routing until qualified.

Much of this window addressed infrastructure admission, source-pinned lifecycle
recovery and exact state settlement rather than model generation. No model
benchmark,950K request, hardware/fan/power/ECC tuning or driver/runtime upgrade
was performed. Worker2 closed08:29 after settling all owned work; the remaining
worker has a hard08:43 deadline, leaving publication time inside the two-hour limit.

## Evidence

- [Machine-readable checkpoint](h030-codex-results.json).
- [FLOW03 actual outcomes](h030-flow03-20260929/SUMMARY.md) and
  [correlated cold failure](h030-flow03-20260929/COLD-HARDWARE-FAILURE.json).
- [Frontier lifecycle handoff](h030-frontier-20260929/REPORT.md) and
  [unresolved image critical section](h030-frontier-20260929/IMAGE-MIMO-LIFECYCLE-BLOCKER.md).
- Earlier failed attempts and source receipts remain in the H030/H029 reports.
  Bulky raw traces, credentials and private workflow captures remain outside Git.
