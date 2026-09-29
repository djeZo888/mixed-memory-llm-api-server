# H030 FRONTIER01 final handoff

Source and immediate lifecycle work are complete. Worker closes early; the new MiMo load is independently owned by `llm-frontier-mimo.service` and explicitly handed to the coordinator for fresh acceptance near08:26. No user inference is pending under W1. No further mutations or paid readiness polling are scheduled by this worker.

## Source and checks

Base `a4b73725`. Hardware diagnostic commit `69293e8`; protected specialist production commit `7139978`; additive test-only commit `b73ec3b`. Working tree clean; no GitHub push or W1 app deployment. `SOURCE.bundle`, `SOURCE.patch`, `SOURCE-MANIFEST.json`, and separate `TEST-ONLY.bundle` are exported for root/W2.

Typecheck and build PASS. Focused checks passed:50 combined admission/qualification checks,42 specialist/scoped acceptance checks,24 final stronger qualification checks. These sets overlap. The initial stronger missing-backend assertion exposed a fixture using a blocked route; corrected actual Codex `/v1/responses` fixture now asserts exact503/codex_frontier_unqualified. No production correction was needed for that test issue.

The original `hardware_state` predicate is unchanged. Safe diagnostics distinguish false/true/null/missing/invalid latch values and expected/actual GPU UUID mismatch, with bounded schema/age/generation fields. Unexposed proof fields remain null. Protected root-owned specialist receipts now drive host gates and capability metadata together; missing/invalid evidence remains closed. Engine/policy/model pins, existing tickets, Qwen profiles and all output budgets remain. No fake live PASS record was installed.

## Diagnostics and image recovery

The original07:43 hardware predicate remains uncaptured. One snapshot and one55-second passive Qwen0 sample found hardwarefalse and the expectedUUID throughout:55samples/no errors; maximum retained negative-proof age9812ms. Outcome NOT_REPRODUCED; no unsupported stale-proof diagnosis or cutoff relaxation.

Image had a warm backend but closed API admission. Root and W2 authorized one supported API restart, including its normal backend reload and deterministic warm. API ready/admitting/idle was accepted07:57:50; image container `88c5e402`, native3080569. Three Qwen native identities stayed unchanged. No independent image workflow was generated.

## MiMo failure, settlement and new owner

MiMo's unchanged native identity did not imply unchanged health. Its owner entered HELD following mandatory_guard_timeout07:56:17 and settlement_lease_deadline07:56:38. The image start source holds the canonical lease through native loading and warming. Timing supports it as the likely competitor, but the historical holder was not sampled. This remains an unresolved production blocker; image error recovery can repeat that path. Avoiding image lifecycle writes during this window is containment, not a fix. See `IMAGE-MIMO-LIFECYCLE-BLOCKER.md`.

Root-approved helper5102 dispatched one exact stop. The fixed7-second Docker client budget expired; the daemon later completed the stop. Readback proved exited native, oldPID absent, cgroup absent, dedicatedGPU empty and final exact proxy absent/idle. No second stop was issued. Root then approved helper6a83 to reconcile this changed, already-stopped state through the unchanged owner.

Existing owner settlement published SETTLED08:14:17.524, with PID released/cgroup empty/GPU empty, request_holdfalse and historical failures preserved. Protected archives:

- Original guard/lease failure: `h030-held-image-contention-3c6fde3cca7443b098b04e42c7179df7.json`, SHA256 `5cd2def22c964571a5811826899849bf0e31992eae82e20eb498b23c78aa31aa`.
- Stop-client timeout: `h030-held-command-timeout-3c6fde3cca7443b098b04e42c7179df7.json`, SHA256 `2ecc52c7a0f6d76541c0d3161c8f5949419b8bd8c697332a72efc46b47f7fb54`.

One normal start returned0 at08:14:17.638. Owned LOADING was confirmed08:14:51:

- Source `1cc1ee45`, manifest `5c364e58`, boot `992bf979-efae-495b-9ab2-26e75ed5c5d0` unchanged.
- Launch `fbfd46357f0d4e3482aa1c7da14f5147`; container `87d2b6f131b9e6e98249f5ba148c0191c6a58fb17b58cf7f792ec27b14ef6d57`.
- Native3442849/startticks3384546, StartedAt `2026-09-29T08:14:19.131765939Z`.
- Supervisor3442364, invocation `a1aed8cfbc0046c8a247922dfbe11e70`, unit active/running.
- Proxy not yet started; request_holdfalse; no current failure. Image and all three Qwen peer identities unchanged.

This is an ownership handoff, not readiness. Candidate remains closed; actual Codex MiMo child/tool continuation and MiniMax delegation remain NOT_TESTED. `CANDIDATE-ACTIVATION-PROPOSAL.md` and `SPECIALIST-ACCEPTANCE-REQUEST.md` contain the conditional two-flag proposal and minimal prompts. W2 alone deploys/configures the app. Root's08:14 instruction assigns a fresh worker near08:26 to validate current readiness and schedule any remaining short acceptance. Do not reuse the earlier07:50 ready capsule.

No model/runtime/driver/GPU/fan/power/ECC tuning,950K occupied request, guard bypass, blanket retry or old-baseline restoration. Keep external maintenance and newest deployed state. No further image lifecycle writes while MiMo loads or runs; the unresolved critical-section blocker must remain visible in final qualification.
