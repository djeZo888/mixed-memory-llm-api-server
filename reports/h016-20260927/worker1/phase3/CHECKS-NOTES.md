# R3 focused verification

Reviewed launch source is782bd29; r3 is a separate scripts/h016/r3 namespace. Existing source-only adoption/node/proxy drafts remain unchanged.

Passed exact byte comparison of benchmark.py, private_proxy.py, telemetry.py, native_identity.py against782bd29; inspect_gguf.py hash matches frozen staged receipt. LAUNCH native argv equals both reviewed r2 after reverting none to mmap and exact root-approved proposal after stripping the interleave/executable prefix. Python AST parse passed for all packet Python source. git diff --check passed.

Focused command: python3 -B -m unittest discover -s scripts/h016/r3 -p 'test_*.py'. Final result:12tests,11PASS,1SKIP for absent historical private legacy fixture; current production17 fixture test PASSED using retained private SHA2fb03c... The first local run found relocation paths and oldnamespace assertions in copied tests; corrected test-only relative roots/namespace and reran. No VM runtime was staged before this correction.

Owner readiness cap is1200seconds capped by13:25 admission. systemd runtime is computed against13:40 and keeps420seconds settlement allowance, before13:48:08globalend. No16K/64K admission in this initial owner; first4K leaves guardedhold for root review. No adoption logic included.
