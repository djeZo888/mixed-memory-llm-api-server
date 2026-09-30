# H031 SOURCE01 — source handoff

Implemented a narrow explicit same-boot source successor for an intentionally stopped, idle MiMo owner. Source proposal only: **NOT DEPLOYED; no live acceptance**.

- Exact base: `70e3e7c1e59eb846eab65f16c11215c000f79351`.
- Source commit: `9cd941cdbd9170fb56ccacbc87f3238e3bd40f0e`.
- Modified only `scripts/runtime/mimo/owner.py` and added `tests/test_mimo_same_boot_source.py`. Report/release artifacts are outside the checkout.
- Native session: `01a0ec5d-4cbc-7cf3-b414-b852c29c870c`. Actual native start observed08:52:22 UTC; source useful before09:10 checkpoint. Hard deadline09:30 remains; closing early after handoff. Actual wrapper exit is **pending** until coordinator records exit-code/finished-utc.

No prior supported path existed: the old settled-source verifier required a different boot and hardcoded REBOOT/FAILED_OR_UNKNOWN. The new staged `prepare-source-stop` records reviewed intent while validating the unchanged installed RUNNING predecessor. Normal systemd stop uses the old owner and ExecStopPost. Explicit `reconcile-settled-source --same-boot-intentional-stop` requires exact pre-stop evidence, terminal zero-work proxy, normal owner_interrupted/RUNNING history with no additional failure, full physical release, current hardware proof, and exact reviewed source-only delta. It archives all prior evidence and emits a protected one-time receipt consumed by normal start.

The original primary_failure is preserved, not relabeled as a successful request. Same-boot disposition is IDLE_INTENTIONAL_STOP / NORMAL_OWNER_STOP; new-boot recovery and FAILED_OR_UNKNOWN semantics remain. HELD recovery, positive/unknown hardware latches, source/config/runtime/context pins, candidate/specialist gates and existing histories remain guarded. Read-only preflight failure does not consume the receipt or replace predecessor state. Source list changes are restricted to the existing reviewed allowlist; this proposal's actual MiMo delta contains only owner.py/node.py/node_collectors.py.

**Validation:** final focused command ran99tests, allPASS, no failures/skips. `TESTS.md` gives exact command/count and log SHA; syntax/diff checks passed. The old new-boot/settlement/owner/latch regressions are included. Two independent source reviews completed; final review found no blocker after recursive native/service cgroup checks, exact service cgroup binding, and strict same-boot latch proof before receipt consumption. No test process or delegated work remains.

**Operational handoff:** `PROTOCOL.md` provides exact staged prepare -> normalstop -> read-only stopped verification -> exact source/manifest staging -> explicit reconcile -> normalstart commands and full reviewed hashes. `SOURCE-MANIFEST.json` records canonical versus raw manifest/state/delta pins. `source-successor-delta.json`, `reviewed-source/`, and private `private/successor-manifest.json` support that exact proposal. The candidate manifest was generated offline from W1's private retained inventory; fresh live checks and separate combined-deployment authorization are still required. Keep private metadata private. W1's separate reviewed image/control closure activation fits in the same stopped interval; image service.py is not a MiMo source pin.

`SOURCE.patch` and `SOURCE.bundle` contain only the assigned two-file source commit. Bundle prerequisite is the exact base above. Git bundle verify passed. No GitHub push, SSH/live probe, VM/model action, request admission, inference, app/config deployment, benchmark or hardware/profile change occurred. Public503/status available and all retained failures/uncertain owners/quarantines are unchanged by this task.

`ACCEPTANCE-PLAN.md` is a compact later sequence using the retained H030 inputs/evidence; no successful workflow was re-run here. Final wrapper process evidence must be appended by root/coordinator after this native session actually exits.
