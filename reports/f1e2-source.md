# F1E2 — actual-image helper coverage completion

Status: **PASS_SOURCE; exact actual-image execution NOT_TESTED.**
Base: `516e4cb52aa2672cf140b687d237b8fa832f6899` (F1E).
Branch: `milestone/f1e2-auth-fixture-coverage`.
Worker: Mac-Worker1, Darwin arm64, Python 3.14.7.

This follow-up supplies the three helper coverage gaps in the root-provided
`../blocker.md`. It does not run or pass Phase A, set `auth_gate_passed`, or
establish inference readiness. Parent reviews F1E and F1E2 together before the
Root/F1Db isolated image retry. Native full lifespan/model initialization remains
separate F1D live proof.

## Changed coverage

1. **Native `/model_info` in the final ASGI chain.** Require one GET route whose
   endpoint and FastAPI dependency both reference the installed `model_info`.
   Missing/wrong Bearer must return exactly 401 with no model collaborator access;
   correct Bearer must access it once and return the native response fields.
   The handler, routing and auth middleware are not replaced. Only model data is
   synthetic. Existing native server-info, repr/asdict/pickle/worker args, logs,
   environment and argv sentinel checks remain.
2. **Actual SIGINT through a disposable launcher process.** The new internal
   scenario runs installed Uvicorn with `lifespan="off"`, installed native HTTP
   setup, the real launcher and installed `kill_process_tree`. Synthetic engine
   startup creates a child and grandchild. A delegating startup observer verifies
   that the installed Uvicorn instance owns SIGINT, then emits a fixed readiness
   marker. The controller sends SIGINT to the launcher PID, requires native
   captured-signal/shutdown state, exact completion output, worker SIGKILL from
   launcher cleanup, and no surviving process-group members. The existing Docker
   command makes the controller PID1, allowing it to reap adopted descendants.
   These checks happen before emergency cleanup; emergency group cleanup cannot
   create a PASS. Child startup is bounded at 180 seconds, signal completion at
   15 seconds, and group reaping at 5 seconds. Abort/timeout children now share
   bounded pipe draining (64 KiB), owned sessions and emergency cleanup.
3. **Negative key files and launch boundaries.** Fourteen filesystem cases:
   missing, symlink, directory, FIFO, modes 0644/0400/0000, empty, LF, CRLF, space,
   NUL, non-ASCII and 4097-byte oversized content. Each executed case runs the
   installed parser/ServerArgs normalization and real key reader through guarded
   `main`. Nineteen CLI rejection cases must stop before normalization/key reads.
   Eighteen post-normalization mode faults modify actual native ServerArgs and
   must stop before key reads. These are explicitly injected invalid normalized
   fields, not an assertion that stock normalization naturally produces them.
   Delegating observers require completed normalization and expected read counts;
   unexpected key acceptance or auth/engine/listener entry fails the fixture.
   Launcher errors must be exactly `sglang_file_auth_launch_failed`; all backend
   output remains privately captured and checked for the generated sentinel.

The key cases park and restore only the exclusively created synthetic key, retain
its inode, and never overwrite an unexpected replacement. Wrong-owner coverage
attempts real `fchown`: if unavailable under the unchanged `--cap-drop ALL` Docker
command, output explicitly records `NOT_TESTED_CAPABILITY_UNAVAILABLE`; there is
no fabricated ownership or mocked-stat PASS. Root must assess this applicability
when reviewing image results. There is no capability expansion.

## Provenance and limits

[Fixture provenance](../tests/lifecycle/sglang_fixture/provenance.json) records the
exact helper digest and coverage. The existing AST fixture provenance remains
historical and separate. `--actual-image` still requires Linux, installed package
versions and exact SGLang source hashes, launcher hash and guarded environment
validation. No AST/mock-framework fallback is available. Actual success output
also records helper/launcher SHA256 and installed FastAPI/Starlette/Uvicorn versions;
those HTTP package versions are observed, not independently pinned by this source
session. Exact host-verified image identity remains required:
`sha256:5027e95bf6ec536856b1b52a91d1f35ff5c564ab83e8a94758a169ff09bb8df3`.

An independent source review compared official commit
[`49e384ce9d304648e9959666ecb8ce8cd98d0deb`](https://github.com/sgl-project/sglang/tree/49e384ce9d304648e9959666ecb8ce8cd98d0deb)
HTTP server, engine, cleanup utilities and ServerArgs bytes/hashes with the
existing installed-static evidence. This was source review, not VM verification.

CUDA discovery remains explicitly stubbed and CUDA initialization refused.
Model/engine/worker collaborators remain synthetic; real inference, GPU work,
full native lifespan, SIGTERM and SIGQUIT are **NOT_TESTED**. The native signal
case uses real Uvicorn; route cases still capture Uvicorn. Worker tests use
explicit doubles for native dependencies and do not establish installed-image
behavior. No VM access/mutation, Docker execution, packages, keys, models,
services, installer, manager, backend adapter or L1 lease changes occurred.
D3/GLM was not accessed. The F1E metadata allowlist and launcher bytes are unchanged.

## Verification and next action

| Check | Result |
| --- | --- |
| Focused helper controls, synthetic route/normalization and native POSIX processes | PASS: 38 tests, 0.550 s |
| Focused run with ResourceWarnings as errors | PASS: 38 tests, 0.552 s |
| Existing focused launcher suite | PASS: 21 tests, 0.607 s |
| Full lifecycle discovery | PASS: 231 tests, 6.669 s |
| Lifecycle static and CLI shell fixtures | PASS |
| Independent source/process review and diff whitespace check | PASS |
| Exact installed image, real inference and native model lifespan | NOT_TESTED |

Helper SHA256: `c08ae64da3b04abcebdf241920adb40fbfaf8a93daa075dffd64d5f86013cfc7`.
Unchanged F1E launcher SHA256:
`b47a334466e32ca8384478721d77e00352003c5809bdeccf2a0553dc496210a7`.

Worker regression work caught and fixed an obsolete subprocess interception, a
normalization-observer false-pass path, and a macOS zombie-only group cleanup
error. Final checks above passed after these corrections. Native-POSIX tests
assert the owned PIDs are gone; they use synthetic native dependencies and do not
claim installed Uvicorn or SGLang execution.

```bash
python3 -m unittest discover -s tests/lifecycle -p 'test_pinned_image*.py' -v
python3 -m unittest discover -s tests/lifecycle -p 'test_sglang_file_auth.py' -q
python3 -m unittest discover -s tests/lifecycle -p 'test_*.py' -q
bash tests/shell/test-llmctl-lifecycle-static.sh
bash tests/shell/test-llmctl-lifecycle-fixtures.sh
git diff --check
```

The actual-image command is unchanged in
[the existing isolated Docker fixture instructions](../docs/lifecycle/f1s-handoff.md#shipped-actual-image-auth-fixture).
Use the reviewed merged checkout and existing pre/post data-mount/root guards;
mount no host key/model directories and retain all isolation flags. The helper
entrypoint remains:

```bash
python3 /fixture/tests/lifecycle/sglang_fixture/run_pinned_image.py --actual-image --repo /fixture
```

Root/F1Db runs that command only after review/merge and records actual per-case
results and hashes. Source tests do not set the auth gate. Bundle/commit identity,
secret scan and delivery verification are recorded in taskroot `../handoff.md`.
