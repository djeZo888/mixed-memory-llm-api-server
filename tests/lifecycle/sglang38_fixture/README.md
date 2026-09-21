# Q38B actual-image authentication and cache fixture

**Source worker status: NOT_TESTED in the actual image.** The local control tests
exercise driver/refusal/I/O behavior with synthetic collaborators. They cannot
establish this image's authentication capability or live model readiness.

Worker1 runs the following only after source review and separately approved
runtime acquisition. The image must already exist; this command never pulls it.
Run the current storage guards before and after the gate. The coordinator must
admit `EVIDENCE_DIRECTORY` through L1's registered data-root binding. Use a new
receipt filename in a protected directory on that verified filesystem.

```bash
python3 tests/lifecycle/sglang38_fixture/run_fixture.py \
  --repo "$PWD" --output "$EVIDENCE_DIRECTORY/q38b-auth.json"
```

The reviewed config-image ID remains
`sha256:e6238090791a938ab86dd21a9a6394192dad15237e815df557cf83524d54b813`,
with the exact platform-manifest relationship in
[the OCI contract](../../../docs/q38b-oci-contract.md). Docker's actual observed
ID/domain, Linux/amd64 platform, default entrypoint and source are verified. It runs
the exact digest reference, not a tag. Both 131072 and 262144 contexts must pass
before it publishes one mode-0600 receipt. The anchored output writer checks
directory identity before and after publication and removes its file if the
directory is rebound. Runtime evidence import belongs to L2's canonical L1
binding and anchored storage writer, not to this fixture helper.

Docker runs with `--pull=never`, `--runtime nvidia`, `--network none`, no published
ports, no GPU requests, explicit `NVIDIA_VISIBLE_DEVICES=none`,
`NVIDIA_DRIVER_CAPABILITIES=compute,utility`, and empty
`CUDA_VISIBLE_DEVICES`, read-only root/repository, dropped capabilities and no
Docker log driver. The model directory, secret directory and cache/workspaces
are private tmpfs. Only a random synthetic sentinel and a small synthetic model
configuration are created. The pinned public 8952-byte chat template is fixture
source, not acquired tokenizer/model data. HOME is unchanged.

Before synthetic files or CUDA discovery stubs, `cache_probe.py` imports genuine
installed resolvers, verifies paths/writes under `/cache`, loads driver libraries
and requires zero GPU devices. It permits only reviewed global control/UVM nodes.
See [the exact source research](../../../docs/q38b-cache-research.md). Actual
library/import/resolver success remains NOT_TESTED until this image gate runs.

Each context uses a unique disposable name and ownership token; create captures
the immutable container ID before start. Host inspect verifies the runtime,
devices, mounts, process and resource limits. Completion, timeout, cancellation
and CLI death enter bounded ID-only stop/quiescence/removal checks. A reused name
or identity mismatch is never a deletion target. Failed creation without known
identity, unavailable daemon, or unconfirmed removal emits sanitized failure
evidence and cannot produce PASS. SIGKILL, host loss and daemon loss cannot be
made recoverable by killing a Docker CLI; Worker1 must reconcile an unverified
container before proceeding. Native output capture is bounded.

The inner runner has no AST/replacement-framework fallback. It imports the
installed parser, raw/resolved ServerArgs and native runtime publication, actual
FastAPI/Starlette HTTP application, native auth middleware and native routes.
Only GPU discovery and engine/model/worker execution are synthetic. Uvicorn's
run call is captured, so native lifespan model initialization remains untested.
Any unexpected native import/configuration behavior fails the gate.

Checks include missing/wrong/correct HTTP auth, native models listing while
health remains Starting/503, authenticated server_info with empty raw/resolved
key fields, worker-argument serialization, captured logs, SSE and disconnect,
WebSocket denial, unsupported launch modes and spawn-import inertness. Native
health/metrics prefix and OPTIONS exemptions are tested explicitly. ADMIN_FORCE
has no configured admin key and is denied. The launcher's bounded authenticated
warmup must succeed before Up, while false warmup stays Starting and separate
actual-process auth-failure/timeout cases must terminate without a surviving
listener. Native post-warmup freeze_gc has no ServerArgs key, receives 401, and
cannot disclose the sentinel.

The actual installed `qwen3_coder` parser additionally parses a synthetic
structured tool call both whole and in seven-character fragments. The actual
`qwen3` reasoning parser must remove an empty think wrapper from final content.
Jinja renders the exact checkpoint template with a synthetic assistant tool
call/tool response and `enable_thinking=false`; it must avoid the xhigh default.
These parser/template checks are **not model/client tool-continuation proof**.

The schema2 `q38b_actual_image_auth` receipt binds both distinct container lifetimes,
host runtime inspection, cache/device proof, exact image identities, pinned source revision and source-file
hashes, current launcher hash, and executable/template fixture hashes. It labels
model execution, GPU work, native model-serving lifespan and live agent
acceptance `NOT_TESTED`. The lifecycle adapter must validate those exact bindings
before importing the receipt into its generic runtime evidence registry.

Local source control verification:

```bash
python3 -m unittest discover -s tests/lifecycle -p 'test_qwen38_image_fixture.py' -v
python3 tests/lifecycle/sglang38_fixture/run_fixture.py --help
python3 tests/lifecycle/sglang38_fixture/run_pinned_image.py --help
python3 tests/lifecycle/verify_qwen38_git_source.py --commit HEAD
```

### Q38NEXT launch failure capture and independent scenarios

The fixture retains `launcher.main`'s exact result, captured-Uvicorn count and
completed-engine-hook count when launch setup fails. Its existing safe-log hook
records the first swallowed exception before a later cleanup error can replace
it. Public failure JSON contains only bounded operands and an allowlisted class;
the original stderr carries a bounded, source-hash-bound private exception/frame
record with synthetic-key redaction. Worker1 must retain raw streams privately
(directory0700/files0600), outside Git and reports. Diagnostic capture or parser
failure still returns CLI2 and cannot publish a receipt.

Native resolution changes environment variables, including
`SGLANG_MAMBA_SSM_DTYPE`. Q38FIN captures the entry environment immediately after
strict validation, before genuine imports. Pinned FlashInfer's import-time
Blackwell patch can add `TRITON_PTXAS_BLACKWELL_PATH` for CUDA13; revalidating that
post-import state does not match production's validate-before-import order.
Both launcher calls reenter the validated snapshot and keep subsequent real
resolution changes during execution. The outer scenario restores its entry
environment before independent failure children. Production launcher validation
and native imports are unchanged. Import-cached fixture execution is auth/source
proof only, never model/compiler acceptance. The pinned mutation is reproduced
synthetically; the historical Q38VERIFY offending name remains unconfirmed.

Additional source-worker regressions require an explicit external copy of the
exact pinned upstream files; they validate hashes before exercising selected
native definitions with synthetic collaborators. This test-only extraction is
never an actual-fixture fallback or native acceptance proof:

```bash
Q38NEXT_UPSTREAM_ROOT=/path/to/pinned/python/sglang \
Q38FIN_FLASHINFER_ROOT=/path/to/flashinfer-69ff11fc/flashinfer python3 -B -m unittest \
  tests.lifecycle.test_qwen38_native_launch \
  tests.lifecycle.test_qwen38_launch_diagnostics -v
```
