# F1E — pinned SGLang build metadata source correction

Status: **PASS_SOURCE; actual-image auth NOT_TESTED for this revision.**
Base: `e46c788534d5b71e988c2cdf188f37f6214f7514`.
Branch: `milestone/f1e-sglang-build-metadata`.
Worker: `mac-worker1.local`, Darwin arm64, Python 3.14.7.

## Change and evidence

The reviewed launcher rejected the pinned image's three public `SGLANG_*` build
metadata entries before native startup or sentinel creation. It now permits
only the exact name/value pairs in [sanitized evidence](f1e-build-metadata-evidence.json).
Each present value must match byte-for-byte; empty, modified and all unknown
`SGLANG_*` entries still fail. No defaults are inferred or injected. All eight
absent/subset/full combinations preserve the launcher's previous absence
behavior. The unchanged manager separately pins image identity and exact inherited
environment; this does not authorize removing image metadata at deployment.

Evidence is explicitly the root-supplied F1D `../blocker.md`, SHA256
`3c65ff6a0678929b0eafc40ca68b73d7e87d60f5d351628eaa59577dc16ac4fc`.
It reports image
`sha256:5027e95bf6ec536856b1b52a91d1f35ff5c564ab83e8a94758a169ff09bb8df3`.
F1E made **one** bounded read-only SSH Docker image inspection attempt, which
exited 1 with no usable evidence. No retry was made; failure diagnostics were
suppressed and not retained, so the cause is undiagnosed. These metadata values
were **not independently reverified by F1E on the VM**. The evidence records the
exact projected command, source hash and three source lines only.

Launcher SHA256: `b47a334466e32ca8384478721d77e00352003c5809bdeccf2a0553dc496210a7`.
[Current provenance](f1s-contract-evidence/launcher-provenance.json) and
[focused handoff](../docs/lifecycle/f1s-handoff.md) record these bytes. Historical
F1S report/worker-validation hashes remain records of their original runs.

## Verification on Worker1

| Check | Result |
| --- | --- |
| Focused launcher suite | PASS: 21 tests in 0.609s |
| Full existing lifecycle discovery | PASS: 201 tests in 6.288s |
| Lifecycle shell static and fixture regressions | PASS |
| Independent source/provenance review | PASS; no must-fix findings |
| Read-only VM image inspection attempt | FAILED: exit 1; no retry, no new VM evidence |
| Actual-image auth gate / real key tests | NOT_RUN by F1E |

Commands:

```bash
python3 -m unittest discover -s tests/lifecycle -p 'test_sglang_file_auth.py' -q
python3 -m unittest discover -s tests/lifecycle -p 'test_*.py' -q
bash tests/shell/test-llmctl-lifecycle-static.sh
bash tests/shell/test-llmctl-lifecycle-fixtures.sh
git diff --check
```

Tests cover exact values, all eight metadata subsets, 55 altered/unknown/control
cases both at validation and guarded main, generic diagnostics, and refusal
before native imports/key reads. UI/version/plugin refusals remain covered.
The successful synthetic guarded-main test now exercises real environment
validation with exact metadata; existing synthetic auth, file safety, key
nonleakage, spawn, warmup, cleanup and lifecycle regressions pass. An initial
new import guard also blocked argparse's standard-library imports; the test was
corrected to guard SGLang imports and assert environment validation ran.
No production code was changed to accommodate that test.

## Scope, warnings and next action

Only launcher environment validation, focused tests, current launcher provenance
and minimal evidence/docs changed. `qwen_next.py`, `manager.py`, L1 binding,
installer modules, runtime/deployment profiles and actual-image helper are
unchanged. No packages, models, keys, services or VM state were changed by F1E.
No actual-image gate was rerun and no `auth_gate_passed` value was changed.

Root reviews/merges this commit first. Then F1D/F1Db installs the reviewed launcher
bytes under its own authorization and reruns the pinned-image auth gate, recording
this new SHA256. The blocker also leaves actual signal delivery, native
`/model_info` auth coverage, actual-image negative key-file/rejected-mode cases
and native lifespan/model initialization unproven. Synthetic source tests do not
close these gaps or establish live model/GPU/parser/agent readiness. No real-key
or activation approval follows from this report. API/V1 readiness remains unproven.

Final commit identity, grep-based secret scan and bundle verification are recorded
in taskroot `../handoff.md` after packaging.
