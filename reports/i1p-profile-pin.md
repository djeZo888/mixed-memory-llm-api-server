# I1P reviewed installer profile pin

Status: **PASS_SOURCE**. Source-only Mac-Worker2 task; actual fresh installation
remains **NOT_TESTED**. Base: `228c57ee64e520cd9b6bb172be6ee631c70d40d1`;
branch: `milestone/i1p-profile-pin`.
Session: `01a0a282-e06c-7cd3-bc38-4259f335fa68`.

## Exact reconciliation

F1S commit `4c56b4668efcfc89494d6c789818dea331305eb3`, compared with parent
`35e02ba6d1b781812c7e54628222660de4328e2e`, adds only top-level
`"backend": "llama_cpp"` and its preceding comma to
`configs/runtimes/llama-cpp-v0.4.1-d1.json`. Current reviewed bytes exactly match
that F1S commit. The profile itself is unchanged by I1P.

- Old profile: 3071 bytes, SHA256
  `adc636db00bb092fe33dfab20302ab954a7796600f7b829163a8e685af0db1a7`.
- Reviewed profile: 3097 bytes, SHA256
  `cf313fe24894cc640c91b77fa8432cf31224e69fad17050ea58d1ae73139e4bd`.
- Only `runtimes.glm.profile_sha256` in `scripts/install/versions.lock.json`
  changes. Strict `runtime_release_input_drift` rejection remains unchanged;
  no calculated replacement, skip or fallback was added to the installer.

Before mutation, independent audit verified all six other local pinned files:

| Input | Matching SHA256 |
| --- | --- |
| `reports/d1-runtime-proof.json` | `93f5ac6c302e10eef8408350d27090c917e150879702d9bfbad1adb803abb760` |
| `containers/llama-cpp/Dockerfile` | `c79e2e63ab7085a6f0835d9810b855e58f4a57745912c819b2142116ec68d8a9` |
| `containers/llama-cpp/Dockerfile.dockerignore` | `50628099759da59c4faa5452f63173533f31bfa39b89d64de35ee08910abd5dc` |
| `reports/f1a-sglang-proof.json` | `04c6258840f3811eb938c341e52d4426a33a7b2d76051ad63d64e3861b4e1953` |
| `reports/r2-flagship-artifact.json` | `8e7cb419a9dea83f1978f936455cedace1b964cbbb3580f7be191998f6a999d3` |
| `reports/f1a-qwen-manifest.json` | `022674d4daf63fa57c2798a30fea80c6dde7b1b2e73630ae3c3aa94e45debb9e` |

All 25 runtime structural/semantic checks passed. All three runtime registry
records and the duplicate GPU-gate record exactly match checked-in I1b registry
evidence. This verifies source evidence equivalence, not fresh registry pulls.

## Source validation

Darwin arm64, Python 3.14.7; no Docker/VM/package/service/disk operations.

| Check | Result |
| --- | --- |
| Baseline actual fixture CLI plan | Exit 1, `runtime_release_input_drift` reproduced |
| Installer suite after correction | 197 run: 193 passed, 4 skipped, 0 failures/errors |
| Actual fixture CLI plan after correction | Exit 0; `SYNTHETIC_FIXTURE`, `ready: false`, `INCOMPLETE_I1C_REQUIRED`; service/acceptance pending |
| Five existing runtime drift tests, explicitly rerun | 5 passed: recipe, image platform/repository digest, durable evidence, installed SGLang source, llama image source |
| Direct in-memory negative checks through unchanged `runtime_inputs()` | 3 passed: stale profile pin and altered D1/F1A proof digests each reject with `runtime_release_input_drift` |
| Shell syntax and installer help | Passed |

Commands: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests/install -p 'test_*.py' -v`;
`./install.sh plan --profile flagship-hybrid --model-set glm,qwen --fixture-host tests/install/fixtures/ubuntu-host.json`;
`bash -n install.sh scripts/common/require-data-mounted.sh scripts/common/root-disk-guard.sh`;
`./install.sh --help`.
The five negative cases are existing `test_runtime.RuntimeTest` methods; their
exact invocation/output is retained in taskroot `negative-drift-tests.log`.

Three Linux `/proc` process-group/FD tests and one Linux private-mount-namespace
detach test were skipped on macOS. Synthetic runtime/HTTP/filesystem evidence
does not establish Linux execution, GPU inference or fresh-install acceptance.

## Hosted evidence and handoff

[Prior hosted installer run 34914046842](https://github.com/djeZo888/mixed-memory-llm-api-server/actions/runs/34914046842)
at `d7a2373908d6c5b09fdd63a045405527d25c4932` was independently observed failed:
197 tests, 1 failure, 23 errors, 1 skip; log confirms runtime release drift.
This historical run is separate from corrected-feature validation.

Taskroot `progress.md` and `final.md` record the delivered commit, clean branch,
full `I1P.bundle`, filename-only secret/whitespace/scope/remote/identity gates,
and exact feature-hosted SHA/run URL/result. No report-only CI churn is required.
Next action: Root reviews/merges the two-file correction and triggers integrated
hosted installer validation. Actual fresh installation remains **NOT_TESTED**.
