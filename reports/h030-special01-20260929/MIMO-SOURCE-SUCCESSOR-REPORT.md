# MiMo settled source successor — offline implementation

Frozen source: `scripts/runtime/mimo/owner.py` SHA256 `1cc1ee45eca7c578d9b84411d75c1cfd37c914edd7b5097389ee2f19fae23098`.
New fixture: `tests/test_mimo_settled_source_recovery.py` SHA256 `80e04ef884bfed971a551f2e198bda829967d4fef740118440b08a30f60f74ff`.
Combined patch: `MIMO-OWNER-FINAL.patch` SHA256 `d15314ce4515801ad2237396b28b8b417a53c2c468ddf1bd77c53d91bbdb9548`.
Independent read-only review found no blocking safety issue at those hashes. No VM contact, deployment, inference, or ownership mutation occurred in this subtask.

## Interface

Stage new `manifest.json`, exact old `source-successor-prior-manifest.json`, exact old `source-successor-prior-owner.py`, and separately reviewed `source-successor-delta.json` (absolute path keys with exactly `{old: SHA256, new: SHA256}`). Leave selection/state/history unchanged until owner reconciliation. The delta is restricted to the 12 captured control/lifecycle leaves and owner.py; no other manifest field/key changes are accepted.

Run the owner action `reconcile-settled-source --expected-state-sha256 RAW_STATE --expected-boot-id CURRENT_BOOT --expected-manifest-sha256 CANONICAL_NEW_MANIFEST --expected-delta-sha256 RAW_REVIEWED_DELTA`. Root must authorize the exact new owner source and renewed W2 lifecycle gap before VM mutation.

The action requires exact prior SETTLED state, request_hold=false, all settlement proofs true, prior selected manifest/generation binding, a different current boot, zero proxy active requests and quarantined=false. Under the canonical lease it validates exact retained container identity and stopped state, native/supervisor/proxy PID absence, cgroup/target GPU/listener absence, source pins, protected storage, and current inactive owner unit. It exclusively archives old state/proxy/guard/selection/manifest/owner/delta, writes a boot+manifest scoped receipt, and only then CAS-advances selection's manifest hash. Prior FAILED_OR_UNKNOWN outcome and original failure records remain unchanged.

Normal `supervise` revalidates that receipt, exact predecessor state, source amendment, and live absence under the canonical lease. After normal hardware/memory/latch checks pass, it persists successor ownership, exclusively consumes the receipt, renames the stopped predecessor to retain logs, and performs the ordinary create/start. Existing HELD/new-boot semantics remain strict and distinct.

## Verification

- `python3 -m unittest discover -s tests -p 'test_mimo*recovery.py'`: 25 PASS (14 existing, 11 new); `MIMO-OWNER-RECOVERY-TESTS.log`.
- `PYTHONPATH=scripts python3 -m unittest tests.test_mimo_owner tests.test_mimo_owner_settlement tests.test_mimo_guard_contention tests.test_mimo_new_boot_recovery tests.test_mimo_settled_source_recovery`: 104 PASS; `MIMO-OWNER-FOCUSED-TESTS.log`.
- `git diff --check`: PASS. Python compile: PASS.
- Initial broad discovery without PYTHONPATH hit 12 import/path errors plus an unrelated proxy deadline source-closure fixture failure. Correct module invocation resolves the import errors. The proxy fixture's `reviewed_file_changed` expectation fails earlier on missing systemd source leaves; independently reproduced using unmodified HEAD owner in an isolated temporary tree (3 PASS, 1 FAIL), recorded in `MIMO-PROXY-BASELINE-TESTS.log`. No unrelated fixture was changed.

New fixtures cover changed profile/unreviewed delta/unknown leaf refusal, exact archive and generation preservation, old owner bytes, state/delta drift, active/quarantined proxy refusal, archive tamper, physical absence refusal matrix, prelaunch guard failure without consumption, and one successor consume/rename. Native operational validation remains for root-authorized execution; tests are offline fixtures only.
