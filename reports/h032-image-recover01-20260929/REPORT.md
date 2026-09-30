# H032 IMAGE-RECOVER01 — source complete, undeployed

The exact abandoned H031 image generation now has a fixed root-only cleanup
helper and one-use handoff into ordinary API-owned recovery. Source was tested
in isolated mac-worker1 copy based on `5cc21bafa7ecda85bb20e50e45bee86a826ded76`.
No VM mutation, API pause, native stop/start, inference, or deployment occurred.
Application acceptance and image readiness remain untested by this task.

## Current evidence

One read-only ai-vm preflight completed at **11:23:02 UTC September 29, 2026**.
Boot `992bf979-efae-495b-9ab2-26e75ed5c5d0`, retained image native `d66478c5…`,
original operation/recovery hashes and absent recorded image owner PIDs matched.
Backend had MainPID/ControlPID0, no job, failed invocation `6e8aa276…`; API was
closed, not ready/admitting/busy. Three Qwen native generations remained present.
MiMo was physically stopped with SETTLED state and unconsumed transition.

Exact deployed PREP `/data/build/h014-pro-7ac59a6-20260927/prep.py` was captured
privately; SHA256 `03c0933c194c79a6aca5e98e26bd1682f99927c0f9dbfe53f25d9938caf3724c`
matches the expected helper. Root specifically requested one additional known
MiMo timeout supplement read; its hash is `8a9597d5…`. Both private packets were
exported for W2. No repeated inventory or GPU workload ran. Node request counts
were unknown/null; they are not evidence of globally absent active requests.
Configured source maps and directly verified source leaves are distinguished in
BASELINE.json; map capture alone is not a full closure verification.

## Protocol and validation

The helper verifies this exact boot/source/config/record/native tuple, paused API,
settled backend invocation, absent original owners and target hardware policy.
It archives raw records/source/config, original failure receipts/journals,
telemetry, exact bind-mounted native log and generation files before exclusive
consumed intent. Docker LogConfig is exactly `none`; no Docker log call is made.

A distinct active cleanup owner performs only the first exact stop/remove.
Lost acknowledgement remains consumed/unresolved. Physical Docker/PID/cgroup,
selected GPU compute and listener absence precede source/config CAS. Active
ownership and held descriptors span installation. The API remains paused until
exact handoff publication; its one ordinary startup consumes that handoff and
replaces active ownership without an inactive gap. No direct backend warm or old
warm replay occurs. New failures use existing immutable Attempt receipts;
original failures and uncertain markers remain archived.

**124 affected image-runtime tests passed** on the final source, including23
new cleanup/archive tests and16 handoff tests. Real anchored files/flocks,
records and lifecycle methods were exercised with fake native/system boundaries.
The exact captured deployed `26f7b17d…` Runtime class and exact `c0cfd3fa…` state
also passed offline cleanup: saved residency stayed JSON lists, only stop/remove
were dispatched, and the old warm marker stayed dispatched. The persisted-JSON
serialization correction already present in the base remains included.

Tests cover identity/source/boot/owner/successor refusals; archive-before-effect;
log-driver-none and real fd evidence; partial installation; lost acknowledgement;
concurrent recovery; expiry before admission; continuation after admission; and
selected GPU policy without requiring all-five-GPU negative proof. Original
ordinary dead-parent refusals remain unchanged. Failed fixture attempts and later
passes are retained separately. `git diff --check` passed.

## Review and handoff

Final source/plan hashes are in RESULT.json and external SOURCE-PINS.json;
DEPLOY-PROPOSAL.md/json specifies exclusive staging, exact two-leaf CAS, backups,
pause/ownership interval, one API start and failure policy. W2 MiMo source is not
incorporated in this image-only package. No owner.py, node/API/app code, model,
weights/runtime, GPU placement, power/hardware policy, or capability gates changed.

Root's explicit activation-start cutoff is **12:45 UTC** (`1790685900`). Admitted
cleanup keeps its independent120-second monotonic budget through installation;
ordinary admitted API recovery retains its existing840/900-second deadline.
The source CLI deadline remains12:05 and global native settlement13:07. This
packet is not activation authorization. Do not replay, clear ownership, restore
an old baseline, or reuse the expired activation plan.

Native source session `01a0ece5-f7fa-7e50-9fdc-a362a6d6c071` closes after export;
no VM writer was launched or remains owned by this task. Root reviews/publishes;
this branch is committed locally only, with bundle prerequisite `5cc21baf…`.
Raw protected evidence, native output and config remain outside Git.
