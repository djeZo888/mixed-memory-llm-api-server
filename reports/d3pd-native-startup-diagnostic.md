# D3PD native GLM startup diagnostic

2026-09-15. **PASS_SOURCE_AND_FOCUSED_WORKER_CHECKS**. Base:
`9ffa2bae2ecfaad9e497861bd363bdba34889fb1` (reviewed D3P).
Source handoff only; no VM build, deployment or inference acceptance.

## Change and parser contract

The combined [patch](../containers/llama-cpp/strict-model-chat.patch) retains the
original strict-alias patch section byte-for-byte and adds **28 lines only** to
upstream `src/llama-context.cpp`, `llama_context::sched_reserve()`.
Every added block is restricted to `model.arch == LLM_ARCH_GLM_DSA`.
No original native line, allocation/fusion choice or error path changes.

After the final successful prompt graph reserve, warning-level records report
actual selected context/batch/sequence parameters, flags and counted fused-node
entries. The existing backend loop reports exact returned compute bytes including
zero; the existing const memory-breakdown API supplies cache bytes per buffer
type. Both sizes are estimates when `no_alloc=1`; D3T must reject that mode as
allocation evidence. No requests, payloads, tensors, keys or environment are logged.

The early `../diagnostic-contract.md` was frozen after coordinator ACK in
coordination Revision2. Its [checked-in exact copy](d3pd-evidence/diagnostic-contract.md)
defines graph -> compute records -> cache records -> `D3T_NATIVE_V1 kind=end`.
The constant end warning delimits completion without new state or a framework.
Each new graph resets the candidate; a later incomplete group cannot reuse older
allocations. D3T owns parser/runner and Manager implementation; consumer changes
were neither made nor tested here. This is a producer contract handoff.

## Source identities and recipe

The existing fixed filename now explicitly denotes **ONE combined D3P + D3PD
patch**, applied once against clean upstream. It is not an additional patch to
stack on an already patched source. The [manifest](../containers/llama-cpp/d3p-source.json)
updates only the combined patch SHA256 and derived tree. The fixed prepare helper,
Dockerfile.d3p and build runner remain byte-identical to reviewed D3P; their
existing checks verify clean pin, ancestry, patch hash and prospective/applied
tree before compilation. No generic patch registry or unpublished commit fetch.

| Identity | Value |
| --- | --- |
| Official upstream | `https://github.com/ggml-org/llama.cpp` |
| Upstream commit | `b29c606e28a01b1bc8c1351026a0fa6e616bf6c4` |
| Upstream tree | `950999fe62b7fe55f44ab5b7394e3c8542f37f12` |
| Original D3P strict-alias patch SHA256 | `f803f6fe8cd91aaff232f1ca2ebb9ec2ed30269ab524637f744f5fe454558a78` |
| Original D3P guard-only tree | `aa029cce1a5648ac3673c872518414169a505666` |
| Combined patch SHA256 | `43e4aeb5b63dbb82d7457526000391ba52d49a408040ec736fb302092e734f3b` |
| Combined derived tree | `0075e6f2ca5b8a3f13c0725e35f60a0ceb2b2b5e` |
| Final llama-context.cpp SHA256 | `1d0b5b495dadd57d9068efd9a98252a7ce2c57d686d6073a50d18e40e4897418` |

[Provenance](d3pd-evidence/provenance.json) distinguishes both approved changes,
hashes final recipe/source/test evidence, and preserves original D1 rollback
identities. Historical D3P report/provenance describe the guard-only revision;
this report supplies the combined successor. Derived upstream commit is null.
No new image, binary version, active profile or installer pin is invented.

## Pinned API verification

Read the exact pinned source and compiled the affected translation unit on CPU:

- `llama-cparams.h`: five fields are `uint32_t`; `PRIu32` is already available
  through `<cinttypes>`; flags and hparams.no_alloc are bool, explicitly cast to int.
- `llama-graph.h`: `get_fused_nodes()` returns const vector of nodes with `op`.
  Graph reset clears the vector; the counted entries are from the final prompt
  graph, not accumulated probe/token-generation graphs. Counts use `size_t`.
- `models/glm-dsa.cpp` registers LIGHTNING_INDEXER only on the selected fused path;
  `llama-graph.cpp` registers FLASH_ATTN only on the selected attention path.
- `llama-memory.h`: const `memory_breakdown()` returns
  `map<ggml_backend_buffer_type_t, size_t>`; GLM cache components aggregate by
  buffer type. With real allocation, KV implementation sums backend buffer sizes.

## Focused verification

| Check | Result |
| --- | --- |
| Clean upstream + ancestry + combined hash/tree preflight and apply | PASS |
| Final verified CPU build, including llama-context.cpp recompilation | PASS |
| Existing native guard + source integration CTests | PASS, 2/2 |
| Direct native guard/HTTP/bypass matrices | PASS, 142 direct + 142 HTTP + 426 bypass cases |
| Existing fixed source-helper/recipe checks | PASS, 20/20 |
| Diagnostic source confinement/GLM/grammar/value invariants | PASS |
| Final tree/raw source bytes and unchanged guard/recipe/D1 rollback hashes | PASS |
| Diff whitespace, owned scope and local grep secret scan | PASS |
| VM/CUDA, model loads/requests, executed kernels, D3T parser | NOT RUN |

Worker verified: macOS 26.6.2 (25G83), arm64, AppleClang 21.0.0.21000334,
CMake 4.4.3, Ninja 1.13.2; existing tools only. CPU configuration disables CUDA,
Metal, Vulkan, SYCL, HIP, RPC, BLAS, Accelerate, OpenSSL and UI. Guard tests use a
fake downstream and local ephemeral HTTP listener; they load no model.

Warnings/setup corrections: optional ccache/OpenMP absent, unsupported ARM probes
and expected disabled-UI warning. A local clone attempt from D3P's partial clone
failed, so source was cloned from official upstream. A first preservation check
rejected full-index reserialization of old patch headers; final patch keeps the
original strict-guard section exactly. A preliminary CPU build ran on the same
native bytes before combined replay; the final evidence uses the verified replay
and recompilation (13 scheduled build steps, including llama-context.cpp).
The optional direct test initially used the wrong output path; corrected `bin/`
command passed. No implementation change was needed for these setup corrections.

### Reproduce worker checks from repository root

```sh
git clone --filter=blob:none --no-checkout https://github.com/ggml-org/llama.cpp.git ../llama-upstream
git -C ../llama-upstream checkout --detach b29c606e28a01b1bc8c1351026a0fa6e616bf6c4
python3 containers/llama-cpp/prepare-d3p-source.py ../llama-upstream --check-only
python3 containers/llama-cpp/prepare-d3p-source.py ../llama-upstream
cmake -S ../llama-upstream -B ../native-build -G Ninja \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_PROJECT_INCLUDE="$PWD/containers/llama-cpp/tests/register-tests.cmake" \
  -DGGML_CPU=ON -DGGML_METAL=OFF -DGGML_CUDA=OFF -DGGML_VULKAN=OFF \
  -DGGML_SYCL=OFF -DGGML_HIP=OFF -DGGML_RPC=OFF -DGGML_NATIVE=OFF \
  -DGGML_BLAS=OFF -DGGML_ACCELERATE=OFF -DLLAMA_OPENSSL=OFF \
  -DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_EXAMPLES=OFF -DLLAMA_BUILD_APP=OFF \
  -DLLAMA_BUILD_TOOLS=ON -DLLAMA_BUILD_SERVER=ON \
  -DLLAMA_BUILD_UI=OFF -DLLAMA_USE_PREBUILT_UI=OFF
cmake --build ../native-build --target d3p-test-strict-model-chat --parallel 8
ctest --test-dir ../native-build -R '^d3p-' --no-tests=error --output-on-failure
../native-build/bin/d3p-test-strict-model-chat
PYTHONDONTWRITEBYTECODE=1 python3 containers/llama-cpp/test_d3p_source.py
python3 containers/llama-cpp/tests/test-source-integration.py ../llama-upstream
python3 containers/llama-cpp/tests/test-native-diagnostic.py ../llama-upstream
```

## Handoff boundary

No SSH/VM work, GPU allocation/profiling, models, protected-state changes,
installer edits/tests, Manager/D3T source edits or runtime/profile changes.
The authorized Mac CPU build is outside the VM-only data-disk rules, as in D3P.
Original D1 rollback and strict-alias policy/tests remain unchanged.

**Next action:** root reviews this tiny combined source, then separately
authorizes the ONE actual VM build through the unchanged guarded D3P recipe.
That build must measure image/binary/source identities before profile binding.
The parser must consume complete groups; later real 32K/native request sanity
and resource gates remain required. Reserved graph selection is not executed
kernel profiling or native-capacity acceptance. Installer remains paused.
