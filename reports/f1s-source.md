# F1S bounded Qwen3-Coder-Next SGLang source

Status: PASS_SOURCE; STOP for activation until F1D gates pass. Reviewed base
`35e02ba6d1b781812c7e54628222660de4328e2e`; feature branch
`milestone/f1s-qwen-next-adapter`. Host `mac-worker2`, Darwin arm64,
Python 3.14.7. Final commit/bundle identity is recorded in taskroot `final.md`.

## Result and scope

Adds explicit SGLang dispatch to D2 validation/create/launch/reuse while retaining
GLM checks and the shared one-active mutex, atomic state, ownership, readiness,
boot intent and safe stop. An explicit SGLang readiness probe requires health 200
plus missing/wrong-key denial and exact authenticated model identity within one
shared deadline; GLM retains its existing behavior. New deployment `qwen3-coder-next` serves only
`127.0.0.1:30003/v1`, pinned official FP8 revision, image and F1A 48-file manifest.
No VM access, service change, package installation, model download or inference
was performed. A1/V0/D1, common installer/guards, README/current-state and D2CI
workflow remain outside F1S edits.

Authentication is a mandatory pre-activation gate. A separately mounted protected
launcher injects native middleware into the retained global app, with both secret
ServerArgs fields None. Custom authenticated tiny warmup, explicit WebSocket
rejection and bounded cleanup cover the reviewed path. The checked-in instance
requires F1D actual pinned-image sentinel proof and complete artifact integrity;
both remain false. Existing protected keys are never overwritten or rotated;
the actual-image test creates its own sentinel exclusively in private tmpfs.

## Supplied evidence

- Full F1A auth review and installed source fixtures were read before implementation.
  The full review supersedes the early contract's protected-YAML suggestion;
  a ServerArgs secret would still leak through repr and server_info.
  Source hashes and extracted test functions document exact provenance.
- Immutable expected manifest SHA256:
  `022674d4daf63fa57c2798a30fea80c6dde7b1b2e73630ae3c3aa94e45debb9e`.
  48 artifacts, 40 weights + 8 assets, 80407722953 bytes total;
  80381394600 weight bytes. Expected identity is not acquisition completion.
- SGLang image `sha256:5027e95bf6ec536856b1b52a91d1f35ff5c564ab83e8a94758a169ff09bb8df3`;
  installed SGLang 0.5.14, torch 2.11.0+cu130, Transformers 5.8.1,
  FlashInfer 0.6.12. Those are supplied F1A installed-source facts, not local
  Mac container observations.
- Early I1 handshake persisted in taskroot `installer-handshake.md` before
  substantial tests. [Final interface and live sequence](../docs/lifecycle/f1s-handoff.md).

## Checks

| Check on mac-worker2 | Result |
| --- | --- |
| Exact base, feature branch and initial clean checkout | PASS |
| Retained D2 deterministic suite (command below) | PASS: 116 tests |
| Five retained shell suites and functional offline verifier | PASS |
| Final discovery, retained and F1S tests together | PASS: 198 tests in 8.445s |
| Whitespace, grep-based changed-file secret scan, credential-free remote and required identity config | PASS; final publication recorded in taskroot final.md |
| Shipped actual-image fixture worker control tests | PASS: 8 included above; native image still NOT_TESTED |
| Actual pinned-container setup/launcher with sentinel | NOT_TESTED: Docker executable unavailable on this worker |
| Live Qwen generation, FP8/GPU fit, parser/tools/agent, reboot | NOT_TESTED; Worker1 F1D |

Exact final commands passed on mac-worker2:

```bash
python3 -m unittest discover -s tests/lifecycle -p 'test_*.py' -q
bash tests/shell/test-llmctl-static.sh
bash tests/shell/test-llmctl-fixtures.sh
bash tests/shell/test-llmctl-lifecycle-static.sh
bash tests/shell/test-llmctl-lifecycle-fixtures.sh
bash tests/shell/test-sglang-smoke-static.sh
bash scripts/sglang/verify-sglang-smoke-plan.sh
```

An initial full discovery while parallel implementation was writing the new test
module reported three missing-new-profile errors; retained 116 tests passed.
Final discovery above passed after all implementation files were present.
No retained assertion or verifier was reduced to syntax-only testing.


The 82 new tests cover 39 backend cases, 18 auth cases, 17 functional readiness
cases and 8 actual-image-helper control cases. In particular, real local HTTP
fixtures serve models200 while health503 and remain not-ready. The actual custom
warmup sends authenticated tiny generation, moves Starting to Up, and then the
health/auth/model readiness chain succeeds; auth/generation/timeout failures
remain not-ready. Redirects, malformed/oversized responses and trickling across
the shared deadline fail safely. Existing GLM probe behavior is unchanged.

The shipped `tests/lifecycle/sglang_fixture/run_pinned_image.py --actual-image`
imports the installed pinned source and real FastAPI/Starlette, refuses missing
or mismatched dependencies, and never falls back to copied mocks. It captures
actual native setup/Uvicorn and preserves real models/chat/server-info/health
handlers; CUDA discovery and model/worker responses are synthetic. It checks
native health Starting503/Up200, both native auth layers, probe exemptions,
admin/WebSocket denial, SSE/disconnect, serialization/log absence and actual
failure-child cleanup. Native lifespan model-serving initialization is explicitly
NOT_TESTED. The exact isolated Docker command is in the handoff.

Final launcher SHA256:
`1bf781b83d1a6bf25b63b948550cf2926e16247f48d6f977188954e9a10d212a`.
[Launcher provenance](f1s-contract-evidence/launcher-provenance.json) and
[worker validation](f1s-contract-evidence/worker-validation.json).

## Warnings and next action

Source mocks/AST-extracted functions prove bounded code behavior only. They do
not certify real FastAPI/Starlette dependency integration, native worker launch,
CUDA/FP8 correctness, capacity, throughput, parser quality or real agent behavior.
Worker1 must run pinned-image sentinel tests on reviewed merged code before a
real key, complete all artifact hashes and perform the multi-step acceptance in
the handoff. Current D2 two-mount storage scope is preserved. Arbitrary data-root portability
is a separate L1 task; no such portability is claimed by F1S.
