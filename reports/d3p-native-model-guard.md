# D3P — native strict-model chat guard

Date: 2026-09-15. **PASS_SOURCE_AND_FOCUSED_WORKER_TESTS.**
Source and focused worker tests only; future build/deploy awaits root review. Project base:
`6cffccb` on `milestone/d3p-native-model-guard`. Approved policy input was the
attached `d3c-model-alias-diagnosis.md`, absent from this project's base reports;
coordination Revision1 confirms approval and the installer STOP.

## Change

The checked-in [patch](../containers/llama-cpp/strict-model-chat.patch) modifies
exactly two upstream files: new `tools/server/server-chat-model.h` and the shared
chat registration in `tools/server/server.cpp`. It applies only to standalone
(non-router, non-child) POST `/chat/completions` and `/v1/chat/completions`.
The two native helpers own the guard and route registration and are called by
both the shipped server and the focused tests. The existing exception wrapper
remains outside the guard; readiness/auth and other route implementations are
unchanged. Child detection uses existing startup process state, not a request
header.

| Top-level model/body | Result |
| --- | --- |
| Object, model omitted | Delegate original request unchanged |
| Exact cached declared canonical ID or native alias | Delegate original request unchanged |
| Other nonempty string, including case/whitespace/undeclared path variants | HTTP 400, model_not_found string code, model param |
| Empty string, null, boolean, number, array or object model | HTTP 400, null code, model param |
| Invalid JSON or non-object body | HTTP 400, null code and param |

All rejections have an object envelope containing `error.message`,
`error.type="invalid_request_error"`, `error.param`, and `error.code`. An ordinary
`server_http_res` sets numeric status 400 independently and retains the JSON
content type with no streaming callback. Fixed messages never echo the supplied
ID. No generic numeric-code error formatter or HTTP 404 rewrite is changed.
A supplied exact alias resolves to the existing canonical response identity;
secondary aliases are deliberately accepted without an echo guarantee.

`routes.get_model_info()` reads cached metadata initialized before HTTP readiness;
it does not create a response generator or access a sleeping inference context.
The guard runs before the original handler's `create_response()`, template/media
processing, task/queue setup and resumable session registration. Accepted requests
pay for a second JSON parse to keep the existing generation handler intact.
The existing auth order remains OPTIONS, readiness (503), then key check (401),
then route/guard. Rejected stream requests stay ordinary JSON responses.

Router/child chat, completions, Responses, embeddings, rerank, control, token
counting and all other endpoints retain their upstream contracts. This is not an
all-endpoint strictness claim. No model ID or deployment setting is hard-coded.
Final project model choices remain GLM5.3 and Qwen3.8; no Coder-Next work occurred.

## Source and recipe provenance

The source was cloned on Mac-Worker1 from the official upstream repository.
The exact upstream commit is `b29c606e28a01b1bc8c1351026a0fa6e616bf6c4`;
its tree is `950999fe62b7fe55f44ab5b7394e3c8542f37f12`.
The [source manifest](../containers/llama-cpp/d3p-source.json) records:

- Patch SHA256: `f803f6fe8cd91aaff232f1ca2ebb9ec2ed30269ab524637f744f5fe454558a78`.
- Derived Git tree: `aa029cce1a5648ac3673c872518414169a505666`.
- Derived upstream commit: none (base plus checked-in patch, verified staged tree).

The [provenance record](d3p-evidence/provenance.json) separately hashes the recipe,
tests, policy attachment and captured evidence. The patch does not require an unpublished upstream commit.
The generated binary's upstream version stamp is not proof of an unmodified
source tree; patch/tree/recipe evidence must accompany it.

The new D3P recipe is separate from the original `containers/llama-cpp/Dockerfile`
and `scripts/d1/build-runtime.sh`. D1 build/proof/runtime rollback files remain
byte-for-byte unchanged. Verification commands, recipe identities and focused results follow.

## Scope and remaining approval boundary

No SSH, ai-vm access, VM build/restart/load/request, GPU work, model weights,
protected state, service activation, installer edits, Manager/control/Q38 edits
or deployment changes occurred. The worker CPU build is an explicitly authorized
exception to VM-only data-disk build paths; no VM storage guards were invoked on
this Mac. The future VM recipe must enforce its storage guards before and after.
Root reviews this source before a separately authorized build. There is no new
image ID in D3P and no installed-runtime acceptance claim.

## Later build/deploy seams (recorded only)

1. Review and commit the new recipe/helper/patch/manifest together. The optional
   Linux wrapper uses a clean upstream default context plus the named BuildKit
   context `d3p=containers/llama-cpp`. BuildKit named-context support and the pinned
   Linux/CUDA build are not tested on this worker. The helper rejects wrong HEAD,
   dirty/hidden-index source, patch drift and wrong derived tree before compiling.
   D1 CUDA devel/runtime digests, Ubuntu snapshot, compiler choice, architecture,
   CMake options and 8 jobs are retained. Python3 is a new verification dependency
   from the same Ubuntu snapshot, in a separate layer so the original package
   layer can still be reused. Docker's normal cache is retained; no pruning,
   no `--no-cache`, and no claim of compiled-object cache reuse.
2. The later build must measure a new immutable image ID, binary version/help,
   CLI flags, CUDA availability, and exported source/tree/recipe/package evidence.
   `source-commit.txt` means upstream base; `source-tree.txt` means patched tree.
   OCI revision is the derived **tree**, explicitly labelled `git-tree` alongside
   upstream commit and patch SHA256; `v0.4.1+d3p` is the package label, not an
   assertion about the binary's upstream version stamp. Never fetch that tree as
   an upstream commit. The optional wrapper builds/inspects only; CLI/CUDA/protocol
   proof remains a later authorized step and it does not start a container.
3. Add a reviewed sibling of `configs/runtimes/llama-cpp-v0.4.1-d1.json` only after
   real image evidence exists: `id`, `image_tag`, `source_repository`,
   `source_revision`/revision-kind, `source_release`, separate upstream/patch/tree
   metadata, and `validation.status`, `validation.evidence`, `validation.image_id`,
   `validation.supported_flags`. Keep the D1 runtime and proof as rollback.
4. Deliberately select the new runtime in a later GLM deployment profile based on
   `configs/deployments/glm-5.3-ud-q4-k-xl-32k.json`: `runtime`, `paths.cache.suffix`
   and matching cache mount source must agree. Preserve canonical
   `endpoint.served_model="glm-5.3"`, 32K, parallel 1, launch arguments and key
   handling. Coordinate profile ownership with D3T; D3P creates no profile.
   The registered deployment instance at data-role
   `services/llm-manager/deployment-instance.json` needs measured
   `runtime_evidence.<new-runtime>.{image_id,flags_verified,evidence,supported_flags,load_mode}`.
   Existing Manager admission/image/command checks remain intact. Current direct
   Manager admission checks image evidence/ID; installer `_image_ok` owns the
   cited OCI-label check. Do not assume those are the same layer.
5. **Installer remains STOPPED.** Recorded seams only:
   `scripts/install/versions.lock.json` → `runtimes.glm` profile/proof paths and
   SHA256s, build recipe hash map, upstream/patch/tree identities, source
   repository/release/revision, image tag and observed reference image ID;
   `scripts/install/runtime.py` fixed profile/proof/recipe allowlists, source/label
   and CLI validators, and upstream fetch/Docker context assembly;
   `scripts/install/host.py` runtime-profile selection;
   `scripts/install/main.py` bundled source identity list;
   `tests/install/test_runtime.py` coordinated source/negative checks. The current
   installer conflates fetched commit, OCI revision and binary stamp; it cannot
   ingest this patch/tree contract by merely changing one pin. Do not bypass or
   weaken that validation. These files were not edited or tested in D3P.
6. After source review and a separately authorized build/deploy, the exclusive
   request owner can run exact canonical/alias, omitted and invalid model chat
   checks in nonstream/SSE forms and unchanged A1 against the measured GLM image.
   Worker fake-handler evidence does not establish live generation, performance,
   model behavior or the protocol aggregate. Qwen3.8 runtime work is separate.

Coordination Revision2 was read during focused testing: root intends one later
VM build, possibly with a separately reviewed D3T startup diagnostics patch.
D3P adds no diagnostics. Its manifest describes the strict-alias patch alone;
stacking requires a reviewed ordered patch list, combined tree/provenance and
focused tests of that exact source. No duplicate VM build is proposed.

## Worker verification and limits

Worker: macOS 26.6.2 (25G83), Darwin arm64; AppleClang
21.0.0.21000334, CMake 4.4.3, Ninja 1.13.2. Existing tools only; no packages
installed. Native full `llama-server` CPU target and the focused test target built.
The measured worker version is `0.4.1-dev (build 10964, commit b29c606e2)`;
its full-history build number differs from D1's recorded shallow-source build 62.
This is a worker binary, not a new VM image identity.

| Check | Result |
| --- | --- |
| Exact upstream/Jinja ancestry and patch SHA/tree verification | PASS |
| Check-only on separate clean checkout, then exact apply | PASS; unchanged checkout after check-only; derived tree matches |
| Full patched native CPU `llama-server` build | PASS, 214 build steps |
| Direct shipped guard/routes | PASS, 142 matrix cases plus alternate metadata canonical |
| Actual pinned loopback HTTP serialization | PASS, 142 matrix cases plus auth/readiness/OPTIONS/stock404 |
| Router/child/both bypass | PASS, 426 matrix cases plus router-valid/child-unknown alias |
| CTest focused native + exact source integration | PASS, 2/2, `--no-tests=error` |
| Source helper/recipe negative and preservation checks | PASS, 20 tests |
| Native/server and project diff whitespace; local grep secret scan | PASS |
| Original D1 recipe/helper/proof/profile bytes and owned file scope | PASS, unchanged |
| Docker/CUDA build, image/CLI/CUDA proof, live-model/A1 checks | NOT RUN; later approval/evidence required |

The full 71-input matrix runs on each chat path in direct and HTTP tests. Object
cases cover stream omitted/false/true. A non-object cannot carry a top-level
stream field; nested stream fields are included. Tests preserve request/response
object delegation, successful JSON/SSE behavior and completion callbacks. Fake
counters cover generator/wake/template/session/queue/stream/completion; rejected
requests leave all counters and an existing fake conversation session unchanged.
The native fixture compiles/links the actual server implementation and calls the
shipped guard/registration, without initializing the real model-owning main.
An exact-source check verifies main's guard arguments/getter/exception wrapper
and unchanged route position, HTTP/router/session/model implementation.

Warnings and resolved test setup issues: missing optional ccache/OpenMP, unsupported
ARM feature probes, and expected no-embedded-UI warning. No packages were added
to resolve them. Initial CMake test registration used an unsupported deferred
subdirectory and then discovered zero tests; both harness setup issues were fixed
before the final 2/2 run, with `--no-tests=error` enforced. Neither required a
native patch change. No unrelated upstream suites were run.

Portability limits: CPU arm64 HTTP without TLS is tested. Linux amd64/CUDA,
BuildKit image build/cache, TLS, real native sleep/wake, templates/tokenizers,
real resumable session storage, child processes and live model generation are
not tested. Fake downstream counts prove no handler entry; unchanged pinned
source establishes where that entry leads. No real inference claim follows.
The optional `build-d3p-runtime.sh` is explicitly **legacy ai-vm layout only**:
it retains D1's UUID/storage guard and refuses `/etc/local-ai-server` registered
hosts. Registered-host integration must use its authoritative storage/report
contracts in a later approved task; no common/installer guard was edited.
Only help, syntax and focused static runner contract checks ran here.

### Reproduce the bounded worker checks

From the project root, source/build directories are worker artifacts outside Git:

```sh
git clone --filter=blob:none --no-checkout https://github.com/ggml-org/llama.cpp.git ../llama-upstream
git -C ../llama-upstream checkout --detach b29c606e28a01b1bc8c1351026a0fa6e616bf6c4
python3 containers/llama-cpp/prepare-d3p-source.py ../llama-upstream --check-only
python3 containers/llama-cpp/prepare-d3p-source.py ../llama-upstream
cmake -S ../llama-upstream -B ../native-build -G Ninja \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_PROJECT_INCLUDE="$PWD/containers/llama-cpp/tests/register-tests.cmake" \
  -DGGML_METAL=OFF -DGGML_CUDA=OFF -DGGML_VULKAN=OFF \
  -DGGML_NATIVE=OFF -DGGML_BLAS=OFF -DGGML_ACCELERATE=OFF \
  -DLLAMA_OPENSSL=OFF -DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_EXAMPLES=OFF \
  -DLLAMA_BUILD_APP=OFF -DLLAMA_BUILD_TOOLS=ON -DLLAMA_BUILD_SERVER=ON \
  -DLLAMA_BUILD_UI=OFF -DLLAMA_USE_PREBUILT_UI=OFF
cmake --build ../native-build --target llama-server d3p-test-strict-model-chat --parallel 8
ctest --test-dir ../native-build -R '^d3p-' --no-tests=error --output-on-failure
PYTHONDONTWRITEBYTECODE=1 python3 containers/llama-cpp/test_d3p_source.py
```

The actual first CPU build preceded CMake test-hook configuration; the final
reconfigure reused its CPU objects. A second clean checkout (`../llama-clean`)
proved the checked-in patch replay independently; both resulting trees and the
post-build source match. Sources/builds stay outside the committed project.
Evidence outputs are in [d3p-evidence](d3p-evidence/).

**Next recommended action:** review this source and coordinate any separately
approved D3T patch into one measured source tree for the single later VM build.
Then obtain real image/build proof before reviewing runtime/deployment identity
changes. D3P stops here; installer remains STOPPED. No push.
