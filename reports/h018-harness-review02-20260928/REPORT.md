# H018 REVIEW02 — independent source review

**PASS for the frozen W1 source and supplied tiny reload proof; no blocking
finding.** EARLY-VERDICT was delivered at 2026-09-27T23:57:33.937220Z, 67 seconds
after the native wrapper start. This is not production deployment approval or
950K model qualification. Only new review records are changed by this task.

Exact reviewed hashes are in `EARLY-VERDICT.json` and `INPUT-SHA256.json`.
Owner `dbb54dd9`, service `367b5ca3`, slice `7a656fbb` match the requested pins.
The complete supplied REPRO704 proof hashes to
`40ff96a051332f4baed4e7a930767cb9920f95c9327fff72714883f80b5e2af7`.

| Review boundary | Result |
| --- | --- |
| Native ancestry | `sample_guard` requires `/sys/fs/cgroup/llmmimo.slice/docker-<exact container ID>.scope`; Docker creation and inspect also require this slice. |
| Parent ownership and effective limits | Before creation the parent has no child; afterward exactly the owned child and no direct parent processes. Raw parent memory cap is exactly 755914244096 (704 GiB), swap max/current both exactly `0`. Child memory cap/current and owned swap/OOM checks remain. |
| Child unlimited swap literal | Only raw `0` or `max` is allowed, with the proven covering zero-swap parent. Empty, malformed and finite-positive swap limits fail. `max` is never converted to zero. |
| Durable ordering and source closure | Both `Requires` and `After` include `llmmimo.slice`, so the parent exists before the pre-create check. `source_preflight` requires and verifies service and slice hashes; `memory_policy` additionally checks exact slice text and live values. Actual installed manifest/drop-ins/loaded unit state were not supplied or remotely inspected. |
| Earlier evidence-loss finding | Fixed: parent-value refusal attaches bounded classification before re-raising, outside the later validation handler. `max`, empty and bounded numeric literals are retained; arbitrary invalid content is omitted. |
| Unrelated policy and recovery | GPU 7%, host 15%, lower-of-85C/hardware limit, zero owned swap/OOM, storage identity, native identity, selection, exact PID/cgroup/GPU release, proxy ambiguity and separate primary/cleanup failures remain. No Qwen/image policy or scope changed. |

The only owner functions changed versus PREP01 are `source_preflight`,
`validate_sample`, `sample_guard`, `create_argv`, `exact_container`, `supervise`,
and the two new helpers `limit_value`/`memory_policy`. The other function ASTs,
including native readiness and settlement, are identical. Whole-host swap stays
telemetry under the previously reviewed policy; no new host-swap relaxation.

The supplied proof records a no-GPU 64 MiB child under the real 704 GiB parent:
child swap limit `0 -> max -> 0 -> max` across initial state, daemon reload,
container restart and another reload. Parent cap and zero swap persisted at all
four stages, as did zero child swap/OOM. The plain-container control also records
`0 -> max`. Resident before/after/final snapshots are identical and owned
container/prototype cleanup is reported complete. `TINY-PROOF-REVIEW.json`
retains the compact facts and the original proof hash. W2 checked the supplied
evidence offline; W2 did not run or observe this live reproduction. The historical
H017 failing literal remains unknown; this reproduces the reset mechanism,
not historical causality or real-model behavior.

Four genuinely missing local regression groups passed: parent topology,
integrated exact ancestry/literal-max handling, parent diagnostic propagation
through `sample_guard`, and service/slice source-pin omission. See
`focused-regressions.py` and `FOCUSED-RESULT.json`. These use temporary local
fixtures and mocked GPU/process inputs; they are not runtime qualification.
W1 reports owner 41 run/1 skip, LAST 30 and short 7. Those suites were not
independently rerun; no broad suite, fuzzing, framework or production gate added.

The retained preparation is suitable for its existing receipt-gated next step.
All 479 source-manifest entries were reconstructed and verified offline: 66 from
the retained packet and 413 from exact Git objects at
`3760c615ec4c4785d1a3e5f5ca4781066782ad66`. Manifest
`054c7cf73f69740e739d18af05c55402603a68839ebacb80eb461b60886bf724`
matches the earlier staging receipt. All 23 helper delta hashes also match.
No ai-harness contact was made and later remote drift was not checked. The
preserved H017 SOURCE-COMMIT metadata discrepancy is not the H018 stage identity.
No source/profile/context bug requiring an edit was demonstrated.

`NEXT-STEPS.md` gives the minimal continuation using the accepted base and retained
host. Original Sova 7143/9ef pause and data/quarantine preservation are inherited
PREP01 evidence, not newly checked host state. This task performed no VM contact,
build, inference, activation, reload, dependency/model download, push or subagent
work. Root owns publication and subsequent dispatch decisions. This worker exits
after handing back records, without waiting for qualification.
