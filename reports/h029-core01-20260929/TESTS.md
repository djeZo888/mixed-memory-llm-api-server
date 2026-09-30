# H029 CORE01 focused validation

- PASS 124 Python tests: test_control_refresh, test_control_core_guards, test_control_integration, test_control_slots, test_control_production_deadlines, test_control_production, test_control_receipts, test_control_restart, test_control_source_closure. Log TESTS-control-final.log.
- PASS 33 TypeScript tests: codex-admission, codex-current-owner, codex-production, codex-host, codex-qwen, codex-diagnostics, codex-provider-responses. Log TESTS-qwen-reviewed.log.
- PASS TypeScript `tsc --noEmit`; Node v24.21.0. Dependencies installed from existing lock with npm ci --ignore-scripts; no package/model setting change.
- Initial test failures retained separately: old refresh mocks returned mock objects instead of None; receipt fixture lacked new explicit refresh port; new fixture initially patched nonexistent journal.write instead of journal.save. These fixture interfaces were corrected, production assertions unchanged.
- Initial live owner preflight FAIL before any start: exact source closure mismatch; see QWEN-RECOVERY-BLOCKER.json. No inference submitted. This initial checkpoint preceded the reviewed deployment and final readiness/lease measurements in README.md.
- Supplemental affected gateway/stop-drain run: 18 PASS, 1 FAIL in an existing source regex assertion; exact base also fails because owned?.close() precedes stopSettlementObservation. Runtime drain assertions preceding that regex passed. No shutdown behavior changed. Retained TESTS-gateway.log and TESTS-gateway-known-failure.json; no broad rerun.
- After demonstrated Docker Mounts-order failure: final adapter127f1e71 passed36 affected Python refresh/production checks, preserving full entry/multiplicity/shape validation; 14 exact final-policy TS checks PASS.
- Ada coexistence extension managera6c39140: 18 affected image/new-Ada peer checks PASS, including actual conflict router and unknown peer refusal.
