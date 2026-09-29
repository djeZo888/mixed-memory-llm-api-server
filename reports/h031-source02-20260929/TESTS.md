Focused final command (54 tests PASS, zero skipped; no inherited test class duplication):

```sh
H031_ACTUAL_EVIDENCE_DIR="$PWD/../input/exact" PYTHONPATH=tests python3 -m unittest -v test_mimo_stop_timeout_source test_mimo_same_boot_source test_mimo_settled_source_recovery test_mimo_new_boot_recovery
python3 -m py_compile scripts/runtime/mimo/owner.py tests/test_mimo_stop_timeout_source.py
git diff --check
```

Private replay uses raw intent/state/proxy/guard/manifest/delta and actual failure records. Filesystem protection, current source preflight and operating-system boundaries are mocked; separate bounded physical fixtures exercise the real physical verifier. This is offline source validation, not live hardware proof. Initial failure exposed a missing independent SETTLED tuple check in the timeout evidence validator; corrected and final suite passed. Earlier logs retained.
