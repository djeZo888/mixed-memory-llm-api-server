# SOURCE03 independent source review

Reviewed 2026-09-29 10:09 UTC; updated with final local retry evidence at 10:11 UTC. Read-only source/evidence inspection; no tests rerun and no VM actions by this reviewer.

Verdict: PASS for the narrow source correction and focused regression evidence. No blocking source defect found in this change.

- Reviewed service SHA256 `4ebe25cf6d2c3399052e2d65c4b343b93ed00668b353e6fdb985f4528ea13496`; test SHA256 `90ea474810ec4c4cc3df24ce32c0330cb7aae9c750f3e2ec0c019e70deb90fb1`.
- `publish()` saves first, then snapshots the JSON-normalized value using `allow_nan=False`, matching `AnchoredRoot.atomic_json()` serialization semantics. Key sorting/indentation do not affect the reloaded value. It does not read an unexpected persisted change into the expected snapshot.
- Exact full-state equality remains in `critical()`. Operation-record, lock-descriptor, source closure, config, boot, recovery, native-generation and hardware guards remain unchanged. No field is omitted from the expected state.
- The logged BEFORE test uses real anchored save and operation-finally and fails with `image_operation_changed`; its pre-finally equality assertion also exposes tuple/list divergence. AFTER records 85 affected image tests passing. This review inspected the log without rerunning it.
- New mutation controls cover residency, container, native generation, run ID, warm flag and an added field, leaving the operation unresolved. Their equal-before-mutation assertion prevents the original serialization mismatch from falsely satisfying rejection. Existing source/boot/owner/config/lock controls remain present; the start/warm fixture now includes realistic residency tuples.
- The fixture establishes a source defect and correction. It does not establish the complete historical live failure chain, current image readiness, recovery success or integration acceptance.

## Initial MiMo preflight evidence boundary

Reviewed private retry script SHA256 `59054baacfa15f9aa2abc781754193ed7c8145a83b7e361281091c747ca5a595` and its retained JSONL/stderr. In this initial preflight, `common_hardware_not_negative` is raised before the sole `systemctl start` call and before `started=True`; the retained result is `startAttempts=0` at `2026-09-29T10:06:50.761863+00:00`. The script has no automatic retry loop. No start or inference was submitted during this initial attempt. This initial release was subsequently superseded only by ROOT's explicit 10:09 authorization below.

The additional five-target passive projection admits only literal `hardware_latched is False`; positive, unknown and missing values all fail closed. Its actual returned projection was not emitted before the exception. Consequently the retained evidence cannot distinguish a fault from unknown/stale/missing proof, identify a failing GPU, or establish the cause. Earlier exact-pin/physical/owner/unit/source-hardware checks were traversed according to control flow, but their detailed success payload was also not emitted. Do not describe those omitted values as independently inspectable captured proof.

## Final authorized single-start outcome

The acknowledged INBOX explicitly authorized removal only of the extraneous all-five-GPU passive projection/predicate at 10:09 UTC, fresh revalidation and the still-unsubmitted single normal start. Local diff review of `retry-corrected.py` (SHA256 `3b7d9242c0f5f445e90d586a48ee875afeb2af746a4c890be4b6bdad8cfbc21f`) confirms only that projection, its imports, predicate and emitted field were removed. Exact source/state/receipt/physical/no-writer predicates and `source_hardware(h, boot, lease)` remain unchanged. No production source or guard change was made by this script.

The retained corrected JSONL records preflight PASS at `2026-09-29T10:09:56.341487+00:00`, including current MiMo-target `hardware_latched=false`, exact boot, proof age 5650.309 ms, physical-release proof, image-owner absence, settled unit jobs and unconsumed transition. One `systemctl start --no-block` was submitted at `10:09:56.341536`, with submission return code 0. This command acceptance did not establish owner admission or LOADING.

The retained journal binds invocation `223dccb354624451ba5be9692567b780` to CLI refusal `lifecycle_busy` at `10:09:56.776569`, followed by ExecStopPost refusal `recovery_invocation_changed` at `10:09:56.844076`. No competing lock holder was captured; no holder or hardware-cause attribution follows from this evidence.

The final release at `10:09:58.389780` records exactly one start attempt, unit failed/exit 255/MainPID 0/job empty, original owner still `SETTLED`, original state raw SHA256 unchanged at `b1ba8b36d09aef570a0d90f769268a61d05a6dbb11899720a163a5bab8fa7420`, and consumption absent. No LOADING result, inference or image action is claimed. Original initial refusal and historical failures remain retained. The final receipt explicitly releases VM write ownership and permits no further start.

No further VM cleanup, start, stop, recovery or diagnostic is authorized or proposed by this review. Final phase verification used only local retained JSONL/journal/receipt and INBOX/OUTBOX evidence.
