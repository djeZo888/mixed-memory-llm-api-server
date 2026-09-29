# H031 SOURCE01 source validation

Authoritative final run: **99 tests PASS, 0 failed, 0 skipped**, 1.027 seconds, exit 0. This is one command/run; interim counts are not added. All VM/Docker/systemd/GPU boundaries are offline fixtures. No inference, model lifecycle, SSH or deployment occurred.

```sh
python3 -m unittest tests.test_mimo_same_boot_source tests.test_mimo_settled_source_recovery tests.test_mimo_new_boot_recovery tests.test_mimo_owner_settlement tests.test_mimo_owner tests.test_mimo_guard_contention.GuardContentionTests.test_transient_contention_refreshes_under_same_canonical_inode tests.test_mimo_guard_contention.GuardContentionTests.test_continuous_contention_expires_original_cycle_without_write tests.test_mimo_guard_contention.GuardContentionTests.test_positive_latch_missing_identity_and_stale_sample_never_wait tests.test_mimo_guard_contention.GuardContentionTests.test_canonical_inode_replacement_during_contention_fails_closed tests.test_mimo_guard_contention.GuardContentionTests.test_fault_appearing_during_contention_is_not_cleared -v > ../output/TESTS.log 2>&1
python3 -m py_compile scripts/runtime/mimo/owner.py tests/test_mimo_same_boot_source.py
git diff --check
```

Syntax and diff checks exit 0. Final TESTS.log SHA256: `01ec03ac769b7787a3346f997184dd03d00137d425f1f2b846b3d54eb8c0af08`.

The 17 new methods cover clean pre-stop prepare/normal idle stop, exact state/manifest/selection/delta bindings, runtime/context/config/source drift, prepared-intent and receipt tampering/reuse, positive/unknown hardware refusal, unchanged fault history, strict terminal proxy identity and active/unknown/quarantined work, old native/proxy/supervisor processes, unit jobs/invocation, service/native cgroup descendants, GPU compute and listeners, exact successor-only service cgroup, and failed launch preflight preserving history/receipt followed by one consumption and predecessor rename. Existing new-boot, settlement, owner and real canonical-latch fixtures remain included.

An earlier exploratory command yielded 122 invocations / 111 distinct test IDs with 1 optional private R9 replay skipped, because the contention module imports and subclasses the latch tests. It passed but is **not** the authoritative count; retained in TESTS.initial-overlapping.log for honesty. The final command names only the five contention-specific methods and does not request the private R9 replay. Prior H030 private replay evidence is retained, not re-run.

W1's retained 08:53 inventory was checked offline with the actual strict guard and idle-proxy helpers; schema/identity comparisons matched. This checks compatibility with captured metadata, not fresh host state, physical release, historical failure cause or live acceptance.
