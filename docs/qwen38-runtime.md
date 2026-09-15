# Qwen3.8 bounded runtime source contract

Q38B corrects the Q38S adapter and two declarative native-context variants.
**Actual-image execution, acquisition, model load, live generation, client tool
continuation and occupied-context performance are NOT_TESTED.** The narrow
Manager dispatch seam uses frozen L1B `9cb93959105468ea0e140598b51493ee0d13ce9e`,
under the explicit incoming ownership handoff; final root review remains pending.
Installer work is stopped. The protected control closure is refreshed in Q38B;
L2 separately owns publication/read checks for the current two-model roster:
GLM5.3 and Qwen3.8-27B FP8. Historical Coder-Next source remains deferred.

## Immutable identities

| Item | Contract |
| --- | --- |
| Model ID | `qwen38-27b-fp8` |
| Repository / revision | `Qwen/Qwen3.8-27B-FP8@017b9c7af6b5689d5dd426a76e0bc077eb5ca20a` |
| Runtime ID | `sglang-qwen38-0.5.19` |
| Backend dispatch identity | `sglang_qwen38` |
| Deployments | `qwen38-27b-128k`, `qwen38-27b-256k` |
| Served alias / host API | `qwen3.8-27b`, `http://127.0.0.1:30004/v1` |
| SGLang source | `0bcd822377da7b5718e674eaf9c870d349424dd1`, release `v0.5.19` |
| Human-readable image tag | `lmsysorg/sglang:v0.5.19-cu130` |
| Exact create/run reference | `lmsysorg/sglang@sha256:37bbbd3444732a464bbc68dee4fb0164e0ce9e18e2f027f3fc967f1152d3c262` |
| Expected Docker config-image ID | `sha256:e6238090791a938ab86dd21a9a6394192dad15237e815df557cf83524d54b813` |

Public OCI manifest and configuration bytes were independently SHA256 checked;
configuration metadata identifies Linux/amd64 and the pinned source revision.
The manifest digest identifies the platform manifest; the config digest identifies
its configuration blob. Docker's observed `.Id` domain is explicit and must
match the exact relationship in the [OCI contract](q38b-oci-contract.md).
Creation uses the immutable digest reference with `--pull=never`; source,
platform, entrypoint, inherited environment and receipt identity must agree.
No layer was fetched.
See [source provenance](../reports/q38s-provenance.json) and
[reviewed research](../reports/q38r-qwen38-evaluation.md).

Both deployments use TP1/GPU0, one request, native BF16 KV, FP32 linear state,
max Mamba cache 1, `no_buffer`, disabled radix retention and overlap scheduling,
disabled decode/prefill CUDA graphs, chunked prefill 2048, memory fraction 0.80,
FlashInfer attention, Triton linear attention and CUTLASS FP8 GEMM. Context and
max-total-tokens are respectively 131072 or 262144. No remote code, MTP,
speculation, ReplaySSM, RoPE extension or million-token option is exposed.
These conservative settings are a test configuration, not measured memory fit.

The pinned release moved graph controls to `--cuda-graph-backend-decode disabled`
and `--cuda-graph-backend-prefill disabled`; the older `--disable-cuda-graph` is
not this launch contract. Complete exact flags live in the new launcher and
runtime profile; source tests ensure they agree. [Pinned server arguments](https://github.com/sgl-project/sglang/blob/0bcd822377da7b5718e674eaf9c870d349424dd1/python/sglang/srt/server_args.py).

## Authentication and actual startup path

`scripts/runtime/sglang38_file_auth.py` is a standalone, guarded launcher. Spawn
imports are inert. It validates its finite argv and environment, prepares the
native **raw** arguments, invokes `resolve_once()`, checks the raw record and
resolved view/dictionary, and only then reads the protected file. Both inference
and admin key fields remain `None` in raw/resolved ServerArgs and worker
serialization. The key is held separately and passed only to native middleware
on the retained module-global FastAPI app and authenticated warmup requests.
There is no key in argv, environment or configuration.

It calls `http_server.launch_server` directly, preserving that app and the custom
warmup. Native setup can layer its empty-key admin-force middleware; the fixture
exercises the final chain. Warmup authenticates `/model_info` and a one-token
`/generate` call within a 600-second budget and marks Up only after success.
Failure terminates descendants and the launcher; a 7200-second launcher watchdog
bounds serving startup after preflight. Manager's own startup deadline and
ownership recovery remain required. Native post-warmup `/freeze_gc` has no key
and can receive a harmless 401; it does not justify an authentication bypass.

Native policy is explicit:

- Ordinary routes, including `/v1/models`, `/v1/chat/completions`, `/model_info`,
  `/generate`, `/server_info` and `/get_server_info`, require the correct Bearer key.
- The upstream auth layer exempts **all paths starting `/health` or `/metrics`
  and all OPTIONS requests**. Handler availability/status still applies; metrics
  collection is disabled in this profile. `/health` returns 503 while Starting.
- Admin-force routes are denied without an admin key. No admin key is supplied.
- Every WebSocket scope is denied, including `/v1/realtime`. HTTP SSE and disconnect
  signals pass through native middleware.
- Extra tokenizer workers, Ray, gRPC/sidecar, encoder-only, HTTP2/TLS-refresh,
  remote code, plugin entry points and unreviewed endpoint/launch modes are refused.
  OpenAPI/Swagger/ReDoc routes are disabled before app import.

The launcher allows only exact pinned SGLang build metadata and reviewed cache
variables in their relevant override families. The adapter additionally checks
the complete inherited OCI environment and exact overrides during image/reuse
validation. Model/cache/scratch destinations are `/models`, `/cache`, `/logs`
and `/service`; downloads, CUDA, FlashInfer, HF, Triton and TorchInductor caches
stay under mounted `/cache`. HOME is unchanged. The root filesystem is read-only;
`/tmp` is bounded tmpfs, private shared memory is 8 GiB, and Docker logs rotate
20 MB × 3 under the registered Docker root.

Source evidence: [native HTTP setup](https://github.com/sgl-project/sglang/blob/0bcd822377da7b5718e674eaf9c870d349424dd1/python/sglang/srt/entrypoints/http_server.py),
[native auth](https://github.com/sgl-project/sglang/blob/0bcd822377da7b5718e674eaf9c870d349424dd1/python/sglang/srt/utils/auth.py),
[raw/resolved machinery](https://github.com/sgl-project/sglang/blob/0bcd822377da7b5718e674eaf9c870d349424dd1/python/sglang/srt/arg_groups/overrides.py).

## Fast no-thinking request and continuation

The actual architecture is `Qwen3_5ForConditionalGeneration`. Pinned 0.5.19
registers `qwen3_coder` structured tools and `qwen3` reasoning. The checkpoint's
pinned template supports assistant tool calls, tool results and absent
`reasoning_content`. Q38C's observed pinned client wire selects:

```json
{"reasoning_effort":"none"}
```

The request omits `chat_template_kwargs`. Pinned native request normalization
inserts `thinking:false` and `enable_thinking:false` for `none` before the
reviewed false server default is merged. The declarations' false template
setting remains unchanged; no additional client field is required.
The server default is `enable_thinking:false`. Native per-request effort can
override defaults: top-level `xhigh` or `low` can enable thinking. The explicit
preset must be present in actual fast-agent requests; source defaults alone do
not bound an existing client that sends `xhigh`. The pinned template otherwise
defaults omitted effort to xhigh. The actual-image fixture checks the exact
ordinary and tool-continuation wire shape through native request normalization
and prompt preparation, renders synthetic no-thinking history, parses structured calls in whole/fragmented form and
checks empty-think stripping. It does **not** establish model or client continuation.
[Pinned template](https://huggingface.co/Qwen/Qwen3.8-27B-FP8/blob/017b9c7af6b5689d5dd426a76e0bc077eb5ca20a/chat_template.jinja),
[request normalization](https://github.com/sgl-project/sglang/blob/0bcd822377da7b5718e674eaf9c870d349424dd1/python/sglang/srt/entrypoints/openai/protocol.py),
[chat serving](https://github.com/sgl-project/sglang/blob/0bcd822377da7b5718e674eaf9c870d349424dd1/python/sglang/srt/entrypoints/openai/serving_chat.py).

A1 records but does not replay reasoning content. It is unchanged here. The
no-thinking continuation gate replays assistant content/tool_calls and matching
tool results. If future evaluation enables thinking, a separate bounded A1
followup must preserve `reasoning_content` on assistant replay (including tool-call
turns), maintain call IDs/arguments and verify streamed reasoning/tool fragments
through an actual second-turn generation. If the current client cannot send the
explicit preset, add that request-config support in separately owned client work
before fast-agent acceptance. Do not infer compatibility from registration alone.

## Narrow L1B / Manager dispatch seam

The public adapter is `lifecycle.qwen38`:

| API | Required caller context |
| --- | --- |
| `declared_profile(id)`, `expected_manifest()`, `launcher_hash()` | Read-only exact source/catalog metadata; never installed/ready evidence |
| `validate(d)`, `command(d)` | Canonical L1 bound deployment and mounted path verification |
| `check_completion(d, instance)` | Protected generic acquisition seal; caller also stats all 81 artifacts |
| `evidence(d, instance)` | Protected actual-image receipt with exact source/image/launcher/fixture identity |
| `validate_launcher(d, evidence)` | Root-owned mode0644 installed launcher, exact reviewed bytes |
| `image_environment(image, d)` | Actual Docker inspect of exact digest/config-image/platform/source/env |
| `verify_runtime_image(image, d, evidence)` | Exact observed OCI identity block agrees with protected auth/runtime binding evidence |
| `validate_reused(container, d, evidence, image)` | Exact command/context/GPU/mount/cache/security/network identity |
| `probe(endpoint, alias, key_file, ...)` | Existing SGLang health-Up + authenticated alias + missing/wrong-key denial |

Profiles use `{role: data|models, suffix: ...}`. L1 resolves model_root, paths,
auth.key_file and mount sources, then injects `_storage_binding`. This adapter
consumes `path(role,suffix)`, `verify(roles=...)`, `validate_path(role,path)` and
`read_json(role,path,maximum=...)`. It supplies no storage registration, writer,
lease or environment override. A fixture duck type is only a unit-test dependency;
it is not lifecycle authorization. L1B's canonical guards remain in force.

The source integration after the explicit L1B freeze handoff:

1. Dispatches exactly this backend/runtime to these functions; discovers only the
   declared model/runtime/deployments. Existing ID rules already accept the runtime
   version; no regex expansion is needed.
2. Permits this launcher target/source role in the existing six-mount SGLang
   contract and retain the common readonly-root/tmpfs/GPU/security renderer.
3. Inspects/creates by the digest reference, binds observed `.Id` and its OCI
   domain to the exact protected auth receipt, and validates image environment
   before creation as well as reuse.
4. Routes readiness through the existing SGLang health/auth probe. Model listing
   while Starting cannot become Ready.
5. Keeps the same canonical minted lease and package admission, one active backend,
   expected-active switch intent, all preflight checks **before stopping the current
   backend**, and existing safe stop/recovery semantics. Never accept an arbitrary
   lock FD or duplicate lock owner.

Manager changes are limited to this backend dispatch. Shared runtime_io,
qwen_next/0.5.14 launcher/cache, installer, common storage/lease and clients are
unchanged by Q38B. The incorporated L1B changes retain their original ownership.
After the separate U1B702e147 handoff, Q38B also updates only the control closure
manifest, matching normal-file constants and focused protection/import tests.
Recovery stays minimal; normal Q38 dependencies are protected before imports.
The reserved D3T llama validation and command bodies remain unchanged.

## Protected acquisition / L2 runtime evidence publication

See [exact acquisition mapping](../reports/q38s-i1c-mapping.md). The new normalized
manifest SHA256 is `726012378a40f648a104230d3f5ed5d6bc505cbd09b32918fc29aa81c0f075f2`.
It contains all 81 artifacts (66 weights), 30,890,049,597 total bytes and
30,866,866,928 weight bytes. Original revision, size, payload hash, pointer/payload
Git identity and evidence status are retained; unknown metadata cannot be filled
with a made-up hash. A generic registry selects this manifest and registered
model destination. No per-model downloader branch is appropriate.

Lifecycle completion is a separate protected seal at
`binding.path('data','services/llm-manager/acquisition/qwen38-27b-fp8.complete.json')`.
Runtime auth proof is at
`binding.path('data','services/llm-manager/evidence/sglang-qwen38-0.5.19.auth.json')`.
L2 runtime binding publishes receipts/instance evidence with its anchored writer under the same
lease after validating exact acquired files or exact actual-image results.
Source/mock test success must never set `verified`, `auth_gate_passed`, installed
or ready flags in a real instance.

## Runnable future actual-image gate

After source review and separately authorized exact-image acquisition, worker1
runs from a protected reviewed checkout. `Q38_AUTH_OUTPUT` below is a **new** file
in a protected directory validated against registered data by the L1 caller;
it is not a launcher environment override. The helper refuses root-filesystem
output, symlink/unprotected parents and replacement files. L2 validates and
publishes the resulting receipt using its registered anchored writer.

```sh
scripts/common/require-data-mounted.sh
scripts/common/root-disk-guard.sh
sudo -n python3 tests/lifecycle/sglang38_fixture/run_fixture.py \
  --repo "$PWD" --output "$Q38_AUTH_OUTPUT"
scripts/common/require-data-mounted.sh
scripts/common/root-disk-guard.sh
```

The helper uses `--pull=never`, exact digest, Linux/amd64, NVIDIA runtime with
`NVIDIA_VISIBLE_DEVICES=none`, no Docker logs, no GPU device requests, network
none, readonly root and bounded private tmpfs. [Pinned NVIDIA behavior and cache
resolver proof](q38b-cache-research.md) require real driver libraries, zero
native torch devices and no GPU nodes before creating synthetic fixture files.
Global control/UVM nodes may exist and are bounded/reported. Only the
checkout is mounted read-only. Each native-context case creates its own synthetic
sentinel and tiny synthetic config; no real key/model is mounted. It imports
the installed native app/auth/ServerArgs/resolution and stubs only model/engine
collaborators and GPU discovery. Uvicorn is captured; native serving lifespan and
GPU/model execution remain NOT_TESTED. The 18 receipt checks cover cache/device
proof and native auth,
ordinary/server_info routes, raw/resolved/worker serialization, logs, streaming,
disconnect, WebSocket denial, warmup failure/nonready and synthetic parser/template
behavior. The adapter rejects proof with different image/source/launcher/fixture
hashes, missing checks or either missing context. Schema2
`q38b_actual_image_auth` also requires both distinct container identities,
host runtime inspection, verified zero exit, quiescence and removal. Timeout,
signal and CLI failure cleanup targets only each verified immutable ID.
Unverifiable cleanup fails closed and returns bounded safe failure evidence.

## Required worker1 / V1 gates

1. Exact-image fixture above before any real key/model; actual native imports,
   source hashes and final auth chain must pass. A mismatch needs review.
2. Generic complete acquisition seal, exact model load coverage, actual SM120
   generation and memory allocation. No full-model success inferred from metadata.
3. Nonstream/stream/auth/cancel, generic tool loop, then actual OpenCode read/edit/
   requested-test task with independent final tests and explicit fast request preset.
4. After GLM priority, one bounded occupied-context run near each cap, retaining
   **at least 8192 tokens inside the cap** for tools/reasoning/output. Count the actual
   tokenizer's system/tools/template/history tokens. Record actual input/output/
   remaining tokens, per-GPU peak allocation, TTFT, prefill/decode throughput and
   end-to-end latency, plus safe beyond-cap rejection and a normal-sized edit/test
   latency case. Unknown usage stays unknown. A short prompt at 256K proves only
   configuration/allocation; arithmetic establishes no speed or quality claim.

Source checks are documented in the [Q38B report](../reports/q38b-runtime-gates.md).
The [original pin finalization trace](../reports/q38b-pin-finalization.md)
distinguishes historical Q38S test claims from its final committed-source defect.
