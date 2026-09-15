# Q38VD source handoff

Status: PASS_SOURCE_CHECKS; READY_FOR_ROOT_SOURCE_REVIEW. No actual retry authorized by this handoff. Installer paused.

- Base/prerequisite: `f17ec2c37d4c706752dd3fbe1978519983578b71`
- Branch: `milestone/q38vd-safe-attach-diagnostic`
- Commit: `de765920fb65f6e0f8b4fcc96790a563eaea4b22`
- Tree: `a256aef8bae8979e2bdaaf8042008a2e42a1bbde`
- Author and committer: CodexAIagent <133749519+djeZo888@users.noreply.github.com>
- Bundle: `Q38VD.bundle` (14935 bytes)
- Bundle SHA-256: `d0cef5f58edddf3dd65f37672321e0f3eb1afca6006ec7020b31800f22be5f65`
- Bundle verification/import: PASS; requires the reviewed base above.
- Working tree after commit: clean. Push: NOT_PERFORMED.

## Result

Failure-only bounded attach diagnostics preserve CLI status, separately observed pre-stop container exit, stream lengths/hashes, and structurally allowlisted inner fixture callsite metadata. Unknown origins remain unknown. Redaction is structural; raw messages/output/paths/locals/source/environment/header/body/secret values are never retained. Root's explicit minimal inner-extension approval is recorded in coordination-input.md after diagnostic-contract.md disclosed producer opacity.

Existing Docker commands, runtime/resources, ownership/cleanup and all native/auth/cache/device/source/PASS gates are unchanged. Inner failure exit remains 2; outer failure remains FAIL/exit 1. No fallback or retry. Post-attach verification errors retain completed attach output and identify the separate operation.

## Verification

- Working tree: 48 targeted tests PASS.
- Immutable archive of this exact final commit/tree: 48 tests PASS.
- Locally imported bundle, matching this exact commit/tree: 48 tests PASS.
- Exact source provenance happy path and outer/inner/support/provenance drift rejection: PASS in both archives, no pin override or regeneration.
- Existing lifetime cases plus malicious/invalid/truncated/overflow data, timeout/CLI/reap/inspection errors, concrete origin, synthetic-secret redaction, exact-owned cleanup, retained ID/no arbitrary deletion and failed-evidence receipt rejection: PASS.
- AST checks against base: command builder; source/runtime/native checks; receipt/run/main; inner verify/fixture-files/cache-child/actual/failure-child execution functions unchanged.
- Mechanical pin checks: only two fixture hashes and the adapter's one provenance hash changed.
- `git diff HEAD^ HEAD --check`: PASS.
- Quiet grep-based final-commit secret-pattern scan (all 8 paths including added files): PASS. Initial pre-commit grep invocation rejected a pattern beginning with dashes; corrected with `--` and scanned the exact final committed diff. No matching content was printed.
- Independent read-only source review: no remaining must-fix issue after the inspection-capture correction.
- Exact test selectors and machine-readable results: `Q38VD-verification.json`.

No SSH, Docker daemon/container/image/native fixture, model/GPU, real keys, deployment/state/guard mutation or installer suite was used. Test process helpers are bounded local Python only. No auth receipt was produced. Historical 131072 failure cause remains unknown; 262144 was not run by this task.

## Exact changed files

- `reports/q38vd-safe-attach-diagnostics.md`
- `scripts/lifecycle/qwen38.py`
- `tests/lifecycle/sglang38_fixture/provenance.json`
- `tests/lifecycle/sglang38_fixture/run_fixture.py`
- `tests/lifecycle/sglang38_fixture/run_pinned_image.py`
- `tests/lifecycle/test_qwen38_final_source.py`
- `tests/lifecycle/test_qwen38_fixture_diagnostics.py`
- `tests/lifecycle/test_qwen38_image_fixture.py`

## Final pins

- `tests/lifecycle/sglang38_fixture/run_fixture.py`: `9757a9b097c601c2201c78052bd05e81c1db6c97d140befba26b4895b1496653`
- `tests/lifecycle/sglang38_fixture/run_pinned_image.py`: `185ac9c1faf663c619ef64da84f1ac7ff1bfc4530a50a2947909ade2b14a4118`
- `tests/lifecycle/sglang38_fixture/provenance.json`: `407eae14b0433b5017ef0b66c772eb78f5d7b25ec951672d4d94e2ecfb823ee2`

## Next action

Root reviews the exact bundle commit and diagnostic-contract.md, then decides separately whether to authorize an actual fixture retry. L2 should propagate the exact updated provenance pin without touching any unchanged model/template/launcher/runtime identities. Deeper cache/launcher causes remain opaque; reported fixture callsites do not assert those causes.
