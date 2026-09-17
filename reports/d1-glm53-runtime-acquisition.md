# D1 — pinned GLM-5.3 acquisition and CUDA runtime proof

## Result

**Runtime build/identity/CUDA enumeration/CLI gates PASS. Acquisition is RUNNING; final download acceptance is PENDING. GLM inference and tool calling are NOT_TESTED.** This report authorizes no D3 activation.

- Operator: Mac-Worker1 via SSH `ai-vm` (`llmserver`), 2026-09-15 Europe/Ljubljana (UTC evidence starts September 14).
- Base: reviewed integration `241783a9e054e32e64b99431a0d3c46a8dfbd807`; branch `milestone/d1-glm53-runtime-acquisition`. No push.
- Isolated VM run: `/data/build/d1-glm53-20260915`; project source under `repo/`, upstream under `source/`, logs/state alongside `evidence/`.
- [Machine-readable runtime proof](d1-runtime-proof.json), [actual selected CLI help](d1-cli-selected.txt), [D1b continuation](d1-continuation.md).
- No lifecycle/profile/client edits, inference activation, public listener, host driver/toolkit/daemon changes, disk changes, model/image deletion or reboot. Historical dirty deployment checkout and its boot unit were not modified.

## Storage and acquisition

The runtime source/build started on verified existing `/data` before D0B readiness. Acquisition began only after reading D0B's final PASS handoff at `/Users/agent/CodexProjects/llm-orchestration/tasks/D0B-20260915/storage-ready.md`, copying its exact bytes into `evidence/d0b-storage-ready.md`, and independently verifying:

| Mount | UUID | Device / independent evidence |
| --- | --- | --- |
| `/data` | `8daf56f1-5649-4163-9d87-919c2d271875` | `/dev/sdb1`, actual ext4 rw mount |
| `/data/models-large` | `a6d4ab58-84e1-4e48-9a67-13ad1c6f6e0a` | `/dev/sdc1`, ext4 rw, label AI_MODELS; stable by-id partition resolves here; PARTUUID `e2b5ae5c-7050-4913-bcda-1741ab6f8252` |

Root, existing data and model filesystem device IDs were distinct (`64512`, `2065`, `2081`). Source/container writes use existing `/data`; model writes and partial files use the new filesystem. New model destination is **`/data/models-large/glm-5.3-ud-q4-k-xl/UD-Q4_K_XL/`**, superseding R2's old destination/cache fields without rewriting R2 history.

The downloader validates the reviewed D0B handoff SHA, exact pinned metadata, path set, sizes and published LFS SHA256s before fetching weights. It selects only the 11 R2 shards from `unsloth/GLM-5.3-GGUF@346b3591c7f28d1a23716f97a065ecf12ec14771`, total **467289116837 bytes**. `evidence/hf-pinned-metadata.json` matched R2 exactly. No other quant/repository download occurs.

`acquire.py` uses one HTTPS stream, at most six attempts per shard, checked byte ranges on resume, 16 MiB writes, periodic atomic status and exact computed SHA256 before atomic final rename. `.partial` stays beside its final shard; no duplicate HF/Xet cache or checkpoint copy. It revalidates exact mountpoints/UUIDs and root's exact 4 GiB minimum before every write/resume, rejects nested devices/symlinks, unexpected files, ambiguous final+partial, oversized partials and corruption. It reserves an additional 20 GiB. A file lock and launcher active-unit check prevent competing acquisition. On resume all completed files are rehashed; prior status is not trusted as integrity proof.

- Durable unit: `d1-glm53-acquire-20260915.service`; initial/current launch PID `34781`; 36-hour maximum, 2 GiB memory bound, nice 10.
- Authoritative state: `/data/build/d1-glm53-20260915/evidence/acquisition-status.json`; file log `acquisition.log`.
- First shard, 9428677 bytes, completed and computed SHA256 matched `02a3e367e8b5f5ee3341d556211faa2cc956c3e77ad0e298c6805323bfaeb02d`.
- Exact moving progress is recorded below and in `../progress.md` / `../acquisition-state.md`. It is not completion evidence.

## Runtime identity and build

Upstream [v0.4.1 release](https://github.com/ggml-org/llama.cpp/releases/tag/v0.4.1) resolved to **`b29c606e28a01b1bc8c1351026a0fa6e616bf6c4`**. A clean checkout was checked on host and inside the build. Git ancestry confirmed Jinja fix `ae9afff8d2c012ca760eb9c2adf41961cf6f6232` (#28817).

| Build input/result | Exact value |
| --- | --- |
| CUDA development base, amd64 | `nvidia/cuda:13.2.1-devel-ubuntu24.04@sha256:0e1f7b8e96fa9ec5e36d4709a38c62df7b5665977446081811c12b8234d874bf` |
| CUDA runtime base, amd64 | `nvidia/cuda:13.2.1-runtime-ubuntu24.04@sha256:285c50be684df76df5cd0e3162687e74b7b67add47134ff55075e3a9cfa94044` |
| Ubuntu dependency snapshot | `20260914T000000Z`; installed package list retained in `evidence/build-packages.tsv` |
| Architecture / parallelism | `CMAKE_CUDA_ARCHITECTURES=120a-real`, eight compile jobs |
| Compiler | GNU 13.3.0; nvcc 13.2.78 |
| Local image tag | `local/llama-cpp:v0.4.1-b29c606-cu132-sm120-d1` |
| Immutable built image ID | `sha256:6866856c573d69d504f82265321b182f631a7b3912a1ed1b4efbf893729d4e62` |
| Actual binary version | `0.4.1-dev (build 62, commit b29c606)` |

The `-dev` suffix comes from upstream's default `LLAMA_BUILD_IS_DEV=ON`; the source remains the exact released commit. Build number 62 reflects the shallow source history. These are recorded faithfully rather than presenting this custom build as an upstream distributed binary. Inputs are pinned for rebuilding; a second bit-for-bit reproducibility build was not performed.

Inspected upstream [CUDA CMake](https://github.com/ggml-org/llama.cpp/blob/b29c606e28a01b1bc8c1351026a0fa6e616bf6c4/ggml/src/ggml-cuda/CMakeLists.txt) explicitly supports SM120, uses `120a-real` for architecture-specific Blackwell instructions, and requires CUDA >=12.8. [NVIDIA's driver table](https://docs.nvidia.com/cuda/cuda-toolkit-release-notes/index.html) associates CUDA 13.2 with R595. Installed driver stayed **595.71.05**. No host CUDA Toolkit installation was made.

CMake used Release, CUDA ON, native CPU OFF, dynamic backends ON, all CPU variants ON, tests/examples/app OFF, UI build and prebuilt UI OFF. Only `llama-server` was compiled as a target. Compiler/CMake/package records and llama license remain inside the image. Upstream's Docker ignore excluded tracked files, so attempt 1 correctly stopped at source cleanliness. A Dockerfile-specific ignore override includes the whole checkout; attempt 2 passed. Both attempt logs remain on `/data`.

The finished transient build unit is `d1-llama-build-20260915-r2.service` (initial PID 30604); `build.exit=0`, `build.state=PASS_BUILD_CUDA_CLI_ONLY`. Its MemoryMax applies to the job/client, not Docker daemon compilation; eight compiler jobs bound build parallelism. Concurrent observation showed about 861 GiB available RAM, no swap use, and ample data storage.

## Actual CLI/CUDA proof and D3 handoff

The resulting image ID was run with `--version`, `--help`, and `--list-devices`, each bounded to 120 seconds, network disabled, read-only rootfs, no published ports, no model mount and file-backed/no Docker logs. Both `CUDA0` and `CUDA1` reported RTX PRO 6000 Blackwell Workstation Edition. This proves backend initialization/enumeration; it does not establish model allocation, CUDA inference kernels or tool-call correctness.

Actual help supports:

| Purpose | Supported syntax / relevant behavior |
| --- | --- |
| CPU experts | `--cpu-moe`; `--n-cpu-moe N` |
| GPU selection | `--device CUDA0,CUDA1`; `--n-gpu-layers N` accepts integer, `auto`, `all` |
| Distribution | `--split-mode {none,layer,row,tensor}`; layer splits layers/KV and is default; tensor mode is experimental; `--tensor-split N0,N1,...` |
| Loading | `--load-mode auto|none|mmap|mlock|mmap+mlock|dio`; no legacy standalone mmap/mlock/direct-io flags |
| Initial shape, for D3 | `--ctx-size 8192 --parallel 1`; no inference configuration activated here |
| API identity / binding | `--alias STRING` (comma-separated aliases), `--host HOST` (127.0.0.1 default), `--port PORT` |
| Authentication | `--api-key-file FNAME` (one key per line, hash-prefixed comments); `--api-key KEY` also exists, but file avoids credentials in process arguments |
| UI / template | `--no-webui`, `--jinja`, `--chat-template-kwargs JSON`; embedded model template is default per tagged source |
| Reasoning | `--reasoning on|off|auto`, `--reasoning-effort LEVEL`, `--reasoning-format`, `--reasoning-preserve` / inverse |
| Monitoring | `--metrics`, `--slots` / inverse, `--timeout N` |

Readiness is an HTTP contract, not a tested live D1 endpoint. Tagged [server documentation](https://github.com/ggml-org/llama.cpp/blob/b29c606e28a01b1bc8c1351026a0fa6e616bf6c4/tools/server/README.md) documents `/health` and `/v1/health`: 503 during loading and 200 with status ok when ready; the health endpoint is public. `/v1/models` uses the alias. D3 must verify authenticated API behavior and actual model readiness. No API key or auth file was read/created here.

## Checks, warnings and next action

**PASS:** required common guards before/after build and before acquisition, strict mount/byte checks, clean pinned source and fix ancestry, exact metadata comparison, build, binary version/help, two CUDA devices, five offline helper tests, live wrong-UUID rejection before report creation, duplicate active launch rejection, and live pinned HTTP Range test (16 returned bytes matched verified first-shard tail). The fixture tests cover metadata identity/count/size/hash rejection, Range status/offset/total/length rejection, symlink refusal, hashing, unknown/wrong/ancestor mounts, shared root device and exact below-4-GiB refusal. Shell syntax and help checked on ai-vm.

**Warnings/limits:** root remains approximately 4.84 GiB free, within accepted <6 GiB warning. The unchanged common guard writes two tiny hardcoded `/tmp/root-disk-guard-require-data-mounted.*` files; its report uses `/data`. Other task temps, build/source/container data, partials, logs and cache paths use `/data` or the new model mount. Existing small bootstrap/old-root-backup warnings remain. No historical tracked report was rewritten. Actual interrupted-process resume and complete 11-shard hashes remain pending; successful Range transport alone is not an interrupted-download recovery test.

**Next action:** D1b should read the continuation and current unit/status metadata, allow the current acquisition to finish, then confirm all exact sizes and computed hashes plus final guards. D3 deploy, GLM load/inference/tool calls, latency/VRAM allocation, authenticated readiness, recovery and client integration remain separate **NOT_TESTED** gates.

## Handoff snapshot

At **2026-09-14T22:51:51.232495+00:00**, acquisition was `DOWNLOADING` with **36919303877 bytes present**, **1/11 shards verified**, session mean **78261393 B/s**. Unit MainPID remained **34781**. This is an in-progress snapshot; no full-download PASS is claimed. Final handoff strict/common storage guards passed, root free **5197258752 bytes**.

Final source validation: five helper tests passed again on ai-vm, shell syntax passed, duplicate launch and wrong UUID refusal passed. Local staged diff/credential checks are required at commit handoff; the raw CLI help is retained on ai-vm while the selected excerpt removes trailing spaces.

Final local packaging checks **PASS**: staged `git diff --check`, review of the staged changes, and grep-based value-shaped credential scan over all eleven new files; remote URLs contained no embedded credentials. A token-boundary refinement removed a false positive on the literal `disk-guard-require-data-mounted` filename. No credential values were exposed and no push occurred.
