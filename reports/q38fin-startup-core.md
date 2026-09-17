# Q38FIN — source ready; native verification pending

Worker2 source-only change from `adb1fd60ab15759c6e0959b660b1de504eada0a8`,
branch `milestone/q38fin-startup-core`. No VM/SSH, model, container, lifecycle,
frontend or installer actions. Singleton Manager/control API is preserved.

## First cause and correction

Q38VERIFY's retained `launch_environment_invalid` frame is the cache-prefix
branch, after successful entry validation and genuine imports. Its offending
variable name was not retained; historical failures remain unchanged.

Pinned FlashInfer commit `69ff11fc4954396d98326656dc85debd2223f637`
[`triton/__init__.py`, lines 7–25](https://github.com/flashinfer-ai/flashinfer/blob/69ff11fc4954396d98326656dc85debd2223f637/flashinfer/triton/__init__.py#L7)
adds `TRITON_PTXAS_BLACKWELL_PATH` at import when discovered ptxas reports CUDA
release >=13. File SHA256:
`ae0d97f7ca56c142787f0bfd127e2bdb45d21613c033beea2ab0c70dd14ed4b2`.
The pinned server import reaches it through disaggregation/model_config,
quantization/fp8/fp8_utils, FlashInfer/mamba/ssd_combined. Reviewed image metadata
declares CUDA13.0.3. Exact pinned-function tests with synthetic ptxas responses
reproduce the refused-prefix failure for CUDA13, while CUDA12 adds no variable.
**This establishes the source defect, not the observed VM offender's identity.**

The fixture now captures entry state immediately after strict validation,
before genuine imports. Both launcher invocations reenter that snapshot, keeping
real resolution changes during each call; outer scenario exit restores entry
state before failure children. Initial/explicit invalid inputs still fail actual
validation. Production launcher bytes, allowlist, native imports, auth checks,
synthetic sentinel handling and first-cause/independent-result diagnostics remain
unchanged. Cached native imports mean this isolation proves an auth-fixture
boundary, not production model/compiler behavior. SGLANG_MAMBA is a distinct
later resolution side effect, not the leading explanation of the historical frame.

## Managed crash containment

Only Qwen creation adds one `--ulimit core=1:1` pair before the image. Reuse
requires exactly one core entry with exact integer Soft1/Hard1, rejecting
missing/duplicate/wrong/bool/string entries while preserving unrelated daemon
limits. The already-reviewed Linux6.8 piped-core rationale addresses the fixture
crash/root-fill hazard; no global host policy changes. Both Qwen profiles are
covered; representative GLM/deferred argv remain byte-identical.

## Verification and evidence limits

Final composed run: **144 focused tests PASS** (seven existing suites: launcher,
Qwen adapter/Manager, pinned native-source contracts, launch diagnostics,
actual-image fixture controls, final-source drift). Source definitions and host
collaborators are synthetic; no installed native execution or receipt is claimed.
All 67 L2 inventory entries, closure hash, fixture/support/launcher pins and
changed-source syntax verify. Only affected fixture/provenance/adapter/Manager
hashes changed; closure manifest and all profiles/production launchers are
byte-identical to base. No installer, broad archive or imported test reruns.
Task-root test log: `../final-focused-tests.txt`; integrity:
`../final-source-integrity.json`. Source review and whitespace checks passed.

Worker1 still owes the actual 131072/262144 pair, managed-container core inspect,
real Qwen model loading/inference and context acceptance. Root's incoming note
reports root-space/NVML recovery prerequisites; Worker1 must refresh those facts
and current installed guard identities before execution.

## Worker1 next native pair — commands only, not executed here

After coordinator review, exact-source staging and the current protected
registered-storage/root guards and ownership admission, run the existing bounded
driver once. It runs 131072 then 262144 and publishes only if both pass:

```sh
python3 "$REVIEWED_SOURCE/tests/lifecycle/sglang38_fixture/run_fixture.py" \
  --repo "$REVIEWED_SOURCE" --output "$EVIDENCE_DIRECTORY/q38fin-auth.json"
```

Use a new protected receipt path and the reviewed private stdout/stderr capture
wrapper. Retain current pre/postguard and exact cleanup evidence. On failure,
retain the first cause and individual operands; no repeated retries are proposed.
If identifying an environment rejection is still necessary, capture only its
bounded variable name, never its value or environment/locals. Native success,
real model readiness and production crash containment remain separate live gates.
