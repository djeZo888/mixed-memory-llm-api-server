# H034 — remaining Codex integration work

H034 is closed. This is a continuation plan, not authorization to start another
window. Preserve the current deployment and completed evidence. Do not rerun
GPU/model benchmarks, repeat bootstrap, replace Qwen, or restore an old baseline.

## Priority 1: finish the image workflow

Worker1: trace the existing image job state through approval, tool return, native
child completion and parent final. Add an authoritative read-only status/wait or
completion handoff using the existing job identity. Preserve original messages;
show a later result as a new durable event/result instead of silently rewriting
history. A completed approved job must not require another image submission.
Keep restart, rejection, cancellation and uncertain-completion handling bounded.
Use deterministic state fixtures before any live inference.

Worker2 in parallel: make operation-specific capabilities unmistakable in the
tool/skill contract (generation capacity is not editing capacity). Keep actual
arguments and errors; no hidden repair, relaxed size limits or replacement of
the original regression. Independently review the PDF result-honesty failure:
prior extraction/numeric/PDF creation passed, but the final incorrectly denied
observed tool failures. Fix reporting from observed tool results and test it.

Root reviews interfaces before activation. One worker alone owns shared
activation and acceptance. Reuse the actual completed edit for a read-only
handoff check first. Then run at most one unchanged guarded-edit regression with
one fresh child and normal user approval, preserving input and job identity.
Keep the exactly-one-tool-attempt oracle separate from exactly-one-GPU-job.
Do not claim a later successful follow-up repaired an earlier final.

## Priority 2: bounded release acceptance

Reuse existing Python/C++/Node, research, follow-up, two-lane admission, Stop,
small compression, cold continuation and MiMo delegation evidence when the
changed paths do not invalidate it. Complete only the remaining relevant
browser reconnect, service restart, queue/failover, child cancellation and
local/offline checks. Record PASS, FAIL or NOT_TESTED for each; avoid duplicating
representative passed fixtures merely to fill a checklist.

Full image support requires correct generation, guarded edit, approval/rejection,
original preservation, accurate current status, final image/download delivery,
and physical job settlement. Turn off public maintenance only after reviewed
release acceptance. MiniMax remains available/default unless the user changes
that decision. Native image/audio/video recognition, Ada200K routing and occupied
950K-context qualification remain separately deferred.

## Suggested two-hour budget

- First 55 minutes: parallel source fixes and deterministic checks.
- Next 40 minutes: one coordinated deployment and bounded actual regressions.
- Last 25 minutes: settle work, review, publish and write a precise checkpoint.

No new long workflow after minute 95. Stop adding tests when the remaining time
cannot cover execution plus settlement. Keep actual native session/exit receipts
and resumable evidence; do not leave paid worker sessions waiting.
