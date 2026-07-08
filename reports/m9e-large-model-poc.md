# M9E MiniMax-M3 Large-Model Proof Of Life

- Timestamp: `2026-07-07T03:11:04Z`
- Branch: `milestone/m9e-large-model-poc`
- Base branch: `main`
- Repository path: `/data/services/mixed-memory-llm-api-server`
- Selected large model: `MiniMaxAI/MiniMax-M3-MXFP8`
- Runtime path: KTransformers / KT-Kernel plus SGLang-KT heterogeneous CPU/GPU serving
- Expected storage reservation: 500-650 GB on `/data`
- Conclusion: STOP. M9E built the initial runtime and downloaded the MiniMax model successfully, but the first container exited before readiness because `sgl_kernel` could not load `common_ops`; the log included missing `libnuma.so.1` and SM120-specific `common_ops` lookup failure context. M9E-R1 recovered the post-reboot 30B service, rebuilt the isolated runtime as `local/minimax-m3-ktransformers:0.6.3-post1-r1`, fixed `libnuma.so.1` and `sgl_kernel/common_ops` import loading, then retried MiniMax. The R1 relaunch still stopped before `/v1/models` because the SGLang MXFP8 path asserts SM90 or SM100 support and this VM is SM120. The prior 30B backend was restored and verified healthy again.

## Explicit STOP Gates

- STOP before model download if KTransformers, KT-Kernel, SGLang-KT, `sglang.launch_server`, or required MiniMax/KT launch flags cannot be built or imported cleanly.
- STOP before model download if the runtime verifier shows required KT launch flags are missing.
- STOP if the GPU architecture is clearly unsupported by the built runtime.
- STOP if root-disk guard, Docker storage verification, or `/data` mount verification fails.
- STOP if `/data` free space falls below 650 GB before model download.
- STOP if model access requires a token strategy not approved by the human.
- No fallback model download in M9E.
- No `Qwen/Qwen3-235B-A22B-Instruct-2507-FP8` download in M9E.
- No host global Python install.
- No host CUDA Toolkit install.
- No host apt install without separate human approval.
- No Docker/containerd daemon configuration change.
- No Docker/containerd daemon restart.
- No public API exposure, public host bind, firewall change, reverse proxy, API auth/front-door, Caddy, systemd service, or Docker restart policy.
- No model deletion, Docker image deletion, or Docker prune.

## Context-Sync Result

PASS before branch creation.

- Hostname: `llmserver`.
- Initial shell path before repo entry: `/home/user`.
- Repository path after `cd`: `/data/services/mixed-memory-llm-api-server`.
- `main` synced from `origin/main` and was already up to date.
- Latest `main` commit at context-sync: `7171167 document M9D merge and pre-M9E handoff`.
- Git identity matched the required attribution: `CodexAIagent <133749519+djeZo888@users.noreply.github.com>`.
- Source-of-truth files were read: `AGENTS.md`, `ROADMAP.md`, `docs/current-state.md`, `docs/pre-m9e-large-model-poc-handoff.md`, `docs/large-model-feasibility.md`, `docs/model-matrix.md`, `docs/model-runtime-manager.md`, `reports/m9d-main-merge.md`, `reports/m9d-large-model-feasibility-plan.md`, and `reports/m9c-main-merge.md`.
- `/data` mount guard passed.
- Root-disk guard passed with report written to `/tmp/root-disk-guard-before-m9e.md`.
- Docker storage verifier passed.
- GPU container verifier passed with `nvidia/cuda:13.2.1-base-ubuntu24.04`.
- Current 30B live verifier passed before transition.
- `scripts/llmctl active` and `scripts/llmctl status` reported the current 30B backend active and healthy.
- `/data` had about `1.8T` available, above the 650 GB gate.
- Known guard side effects on `reports/m3-root-disk-guard.md` and `reports/m4b-docker-containerd-install.md` were restored before branch creation.
- Branch `milestone/m9e-large-model-poc` was created only after context-sync passed.

## Current 30B Active State Before Transition

- Model profile: `qwen3-30b-a3b-instruct-2507`.
- Model ID: `Qwen/Qwen3-30B-A3B-Instruct-2507`.
- Runtime profile: `sglang`.
- Container: `sglang-qwen3-30b-a3b-instruct-2507`.
- Image: `lmsysorg/sglang:v0.5.14-cu130`.
- Endpoint: `http://127.0.0.1:30001/v1`.
- Bind: `127.0.0.1:30001` only.
- Launch args: `--tp 2 --context-length 32768 --mem-fraction-static 0.75`.
- Model path: `/data/models/qwen3-30b-a3b-instruct-2507`.
- State: active and healthy before M9E runtime preflight.

## System Baseline At Context-Sync

- `/`: `15G` total, `9.0G` used, `4.5G` free.
- `/data`: `2.0T` total, `124G` used, `1.8T` free before M9E build/download work.
- `/data/models`: `59G` before MiniMax download.
- `/data/hf-cache`: `13M` before MiniMax download.
- `/data/docker`: `27G`.
- `/data/containerd`: `66G` before runtime image build; later `106G` after build layers.
- `/data/build`: `4.0K` before M9E runtime directories were created.
- GPUs: two `NVIDIA RTX PRO 6000 Blackwell Workstation Edition` GPUs, each `97887 MiB`, driver `595.71.05`, compute capability `12.0` / SM120.
- CPU/NUMA: `112` CPUs, `1` thread per core, `7` sockets, `7` NUMA nodes.
- Host CUDA Toolkit and `nvcc`: absent by project baseline; not installed in M9E.

## Official Source Refresh

Sources refreshed on 2026-07-07 before runtime changes:

| Source | URL | M9E notes |
| --- | --- | --- |
| `Running MiniMax-M3 with SGLang and KT-Kernel` | `https://github.com/kvcache-ai/ktransformers/blob/main/doc/en/kt-kernel/MiniMax-M3-Tutorial.md` | Uses public model ID `MiniMaxAI/MiniMax-M3-MXFP8`; requires KT-Kernel install from `kvcache-ai/ktransformers`, SGLang-KT through `./install.sh` or `pip install sglang-kt`, and launch flags including `--kt-weight-path`, `--kt-method MXFP8`, `--kt-cpuinfer`, `--kt-threadpool-count`, `--kt-num-gpu-experts`, `--kt-gpu-prefill-token-threshold`, `--tp-size`, `--quantization mxfp8`, `--moe-runner-backend triton`, `--trust-remote-code`, `--mem-fraction-static`, `--chunked-prefill-size`, `--cuda-graph-max-bs`, `--tool-call-parser minimax-m3`, `--reasoning-parser minimax-m3`, and `--served-model-name`. |
| `KTransformers` introduction | `https://kvcache-ai.github.io/ktransformers/` | Describes KTransformers as CPU-GPU heterogeneous computing for large language model inference. The page lists MiniMax-M3 day-zero support on June 21, 2026 and identifies inference as `kt-kernel` serving. |
| `KT-Kernel` README / Inference docs | `https://github.com/kvcache-ai/ktransformers/blob/main/kt-kernel/README.md` | Documents KT-Kernel installation through `pip install kt-kernel` or source `./install.sh`, SGLang integration, and KT-specific launch parameters. PyPI metadata for `kt-kernel 0.6.3.post1` states no CUDA Toolkit installation is needed for wheels, but its explicit CUDA architecture examples list SM80/SM86/SM89/SM90. |
| `sglang-kt` PyPI | `https://pypi.org/project/sglang-kt/` | Observed package: `0.6.3.post1`, released June 25, 2026, Python >=3.10. |
| `kt-kernel` PyPI | `https://pypi.org/project/kt-kernel/` | Observed package: `0.6.3.post1`, released June 25, 2026, Python >=3.10. GPU support text says compute capability 8.0+ but the explicit matrix lists Ampere, Ada, and Hopper; it does not explicitly list SM120 workstation Blackwell. |
| `MiniMaxAI/MiniMax-M3-MXFP8` Hugging Face model card | `https://huggingface.co/MiniMaxAI/MiniMax-M3-MXFP8` | Exact model ID is `MiniMaxAI/MiniMax-M3-MXFP8`; card tags include safetensors, custom code, MoE, multimodal, agent, coding, conversational, and `mxfp8`; license is `minimax-community`; examples include `trust_remote_code=True`, SGLang, vLLM, and Docker snippets. |
| SGLang server arguments | `https://docs.sglang.io/docs/advanced_features/server_arguments` | Current docs list `--tp-size` as an alias for tensor parallelism, `--served-model-name`, cache/memory controls such as `--max-total-tokens` and `--chunked-prefill-size`, and OpenAI-compatible server arguments. The installed SGLang-KT `--help` output remains the source of truth for KT-specific flags. |
| Hugging Face Hub download guide | `https://huggingface.co/docs/huggingface_hub/guides/download` | `snapshot_download()` downloads an entire repository, supports `cache_dir`, and `local_dir` preserves original file structure. `HF_HOME` can set a custom cache location. |

Current source limitation summary:

- The MiniMax tutorial explicitly lists supported GPUs as SM90 Hopper and says upstream SGLang targets SM100 datacenter Blackwell so far.
- This VM has RTX PRO 6000 Blackwell Workstation GPUs with compute capability 12.0 / SM120.
- Current public docs and package metadata do not explicitly confirm RTX PRO 6000 Blackwell Workstation / SM120 support.
- M9E confirmed imports/help flags, but the actual launch still failed before model serving because `sgl_kernel` could not load the required common ops.

## Runtime Isolation Strategy

Selected strategy: dedicated Docker image based on `nvidia/cuda:13.2.1-base-ubuntu24.04`, with Python and runtime packages installed only inside the image virtual environment. The first attempt based on `lmsysorg/sglang:v0.5.14-cu130` exposed package-version conflicts after `sglang-kt` changed the base SGLang dependency stack, so the runtime preflight switched to a cleaner CUDA base before any model download.

Rationale:

- Keeps KTransformers/KT-Kernel/SGLang-KT out of host system Python.
- Avoids host CUDA Toolkit installation.
- Keeps Docker image layers under Docker Root Dir `/data/docker` and containerd root `/data/containerd/root`.
- Avoids package conflicts with the existing SGLang 0.5.14 image by installing `sglang-kt` into a clean image-local virtual environment.
- Does not modify Docker/containerd daemon configuration and does not restart daemons.

Artifacts added for the Docker strategy:

- `configs/docker/Dockerfile.ktransformers-minimax-m3`
- `configs/compose/compose.minimax-m3-poc.template.yml`
- `scripts/large-models/build-ktransformers-minimax-runtime.sh`
- `scripts/large-models/verify-ktransformers-minimax-runtime.sh`
- `scripts/large-models/verify-minimax-m3-poc-live.sh`

Pinned/current build inputs:

- Base image: `nvidia/cuda:13.2.1-base-ubuntu24.04`
- KTransformers source URL: `https://github.com/kvcache-ai/ktransformers.git`
- KTransformers main commit observed before build: `cb9f47d142a507cac5d74450b30463d2e8d1cf58`
- SGLang main commit observed for reference: `3cbb7568bd47da8ecde305557583c15fc8f58c22`
- `kt-kernel`: `0.6.3.post1`
- `sglang-kt`: `0.6.3.post1`
- Built image: `local/minimax-m3-ktransformers:0.6.3-post1`

## Build/Import Preflight Result

PASS before model download.

Commands run:

```bash
scripts/large-models/build-ktransformers-minimax-runtime.sh --dry-run
scripts/large-models/build-ktransformers-minimax-runtime.sh --yes-build-runtime
scripts/large-models/verify-ktransformers-minimax-runtime.sh
```

Results:

- Docker dry-run printed the expected no-model-download, no-fallback, no-host-install, no-daemon-change plan.
- Runtime image `local/minimax-m3-ktransformers:0.6.3-post1` built successfully.
- Python in image: `3.12.3`.
- `kt-kernel=0.6.3.post1` imported.
- `sglang-kt=0.6.3.post1` imported.
- `sglang.launch_server` imported.
- `python3 -m sglang.launch_server --help` succeeded.
- Required flags were present: `--kt-weight-path`, `--kt-method`, `--kt-cpuinfer`, `--kt-threadpool-count`, `--kt-num-gpu-experts`, `--quantization`, and tensor parallel flag `--tp-size`.
- Optional planned flags were present: `--kt-gpu-prefill-token-threshold`, `--moe-runner-backend`, `--chunked-prefill-size`, `--cuda-graph-max-bs`, `--tool-call-parser`, `--reasoning-parser`, `--served-model-name`, `--mem-fraction-static`, and `--context-length`.
- Runtime verification warning: SGLang-KT printed `Triton is not supported on current platform, roll back to CPU.`
- Runtime verification warning: SM120 workstation Blackwell is not explicitly documented as supported by the current MiniMax/KTransformers sources.
- Runtime verification record: `/data/build/ktransformers-minimax-m3/runtime-verify-latest.md`.
- Build record: `/data/build/ktransformers-minimax-m3/runtime-build-latest.md`.

## Model Download Result

PASS.

- Download method: `huggingface_hub.snapshot_download()` inside the isolated runtime image.
- `repo_id`: `MiniMaxAI/MiniMax-M3-MXFP8`.
- `local_dir`: `/data/models/minimax-m3-mxfp8`.
- `cache_dir`: `/data/hf-cache/hub`.
- HF cache environment variables were set to `/data/hf-cache` paths.
- No HF token was used; public unauthenticated access worked.
- No fallback model was downloaded.
- `Qwen/Qwen3-235B-A22B-Instruct-2507-FP8` was not downloaded.
- Download completed after 52 files.
- Model size: `414G` at `/data/models/minimax-m3-mxfp8`.
- Key files verified: `config.json`, `chat_template.jinja`, `tokenizer.json`, `tokenizer_config.json`, `model.safetensors.index.json`, and `model-00001-of-00031.safetensors` through `model-00031-of-00031.safetensors`.
- `/root/.cache`: absent after download.
- `/home/user/.cache`: only `/home/user/.cache/motd.legal-displayed`; no Hugging Face, Torch, pip, or model cache spill.
- Post-download root-disk guard passed.
- Post-download Docker storage verifier passed.

## Storage After Download And Restore

- `/`: `15G` total, `9.0G` used, `4.5G` free.
- `/data`: `2.0T` total, `577G` used, `1.4T` free.
- `/data/models/minimax-m3-mxfp8`: `414G`.
- `/data/models/qwen3-30b-a3b-instruct-2507`: `57G`.
- `/data/hf-cache`: `29M`.
- `/data/docker`: `27G`.
- `/data/containerd`: `106G`.
- `/data/build`: `300K`.
- Docker images: `86.31GB` total.
- Docker build cache: `44.91GB` total; no prune was run.

## 30B Stop Result

PASS.

- Stop dry-run completed first.
- `scripts/llmctl stop --yes` stopped `sglang-qwen3-30b-a3b-instruct-2507`.
- Port `30001` was verified not listening after stop.
- 30B model files were preserved at `/data/models/qwen3-30b-a3b-instruct-2507` with size `57G`.
- No 30B model deletion, image deletion, Docker prune, restart policy, or systemd service change occurred.

## MiniMax Compose And Launch

Runtime compose path:

- `/data/services/llm-manager/compose/minimax-m3-poc.compose.yml`

Repo template path:

- `configs/compose/compose.minimax-m3-poc.template.yml`

Launch command:

```bash
sudo -n docker compose -f /data/services/llm-manager/compose/minimax-m3-poc.compose.yml up -d
```

Actual launch args:

```text
python3 -m sglang.launch_server
  --model-path /data/models/minimax-m3-mxfp8
  --kt-weight-path /data/models/minimax-m3-mxfp8
  --kt-method MXFP8
  --kt-cpuinfer 64
  --kt-threadpool-count 7
  --kt-num-gpu-experts 8
  --kt-gpu-prefill-token-threshold 500
  --tp-size 2
  --quantization mxfp8
  --moe-runner-backend triton
  --trust-remote-code
  --host 0.0.0.0
  --port 30000
  --served-model-name minimax-m3-mxfp8-poc
  --context-length 8192
  --mem-fraction-static 0.55
  --chunked-prefill-size 4096
  --cuda-graph-max-bs 1
  --tool-call-parser minimax-m3
  --reasoning-parser minimax-m3
  --max-running-requests 1
```

Localhost-only verification before launch:

- Compose config published `127.0.0.1:30002:30000`.
- Public host bind check for `0.0.0.0:30002:30000` passed.
- `docker compose config` showed `host_ip: 127.0.0.1`, target `30000`, published `30002`.

Container status:

- Container name: `minimax-m3-mxfp8-poc`.
- Started, then exited with status `Exited (1)` before readiness.
- Endpoint `http://127.0.0.1:30002/v1` did not become available.
- `/v1/models` result: not reached; `curl` failed to connect after container exit.
- Short chat proof: not run because `/v1/models` never passed.
- Optional technical prompt: not run.

## MiniMax Failure Diagnostics

Diagnostics captured under:

- `/data/logs/minimax-m3-poc/m9e-failure-20260707T030539Z`

Files captured:

- `docker-inspect.json`
- `docker.log`
- `nvidia-smi.txt`
- `nvidia-smi-query.csv`
- `ss-tulpn.txt`

Primary failure from logs:

```text
ImportError:
[sgl_kernel] CRITICAL: Could not load any common_ops library!
...
GPU Info:
- Compute capability: 120
- Expected variant: SM120 (precise math for compatibility)
...
Error details from previous import attempts:
- ImportError: libnuma.so.1: cannot open shared object file: No such file or directory
- ModuleNotFoundError: No module named 'common_ops'
```

Additional warning before failure:

```text
Triton is not supported on current platform, roll back to CPU.
```

M9E stopped at this failure boundary rather than rebuilding or retrying. A later remediation should add the missing image runtime dependency and explicitly re-verify `sgl_kernel` common ops loading on SM120 before relaunch.

## 30B Restore Result

PASS.

- Failed MiniMax compose service was stopped; the container remains present for diagnostics and was not removed.
- `scripts/llmctl start --yes` restored `sglang-qwen3-30b-a3b-instruct-2507`.
- Startup waited until `/v1/models` was ready and health was `healthy`.
- `scripts/sglang/verify-sglang-real-fast-live.sh` passed.
- Direct `curl -fsS http://127.0.0.1:30001/v1/models` passed and returned `qwen3-30b-a3b-instruct-2507`.
- Current active endpoint after recovery: `http://127.0.0.1:30001/v1`.
- Current host bind after recovery: `127.0.0.1:30001` only.

## GPU/RAM Summary After Restore

- System RAM: `881Gi` total, `858Gi` available after restore sample.
- GPU 0: `NVIDIA RTX PRO 6000 Blackwell Workstation Edition`, compute capability `12.0`, `76294 MiB / 97887 MiB` used after 30B restore.
- GPU 1: `NVIDIA RTX PRO 6000 Blackwell Workstation Edition`, compute capability `12.0`, `76326 MiB / 97887 MiB` used after 30B restore.
- GPU verifier passed after restore using `nvidia/cuda:13.2.1-base-ubuntu24.04`.

## Guard Results

- `/data` mount guard: PASS before build, before download, and during final checks.
- Root-disk guard: PASS before build, after build, before download, after download, and during final checks.
- Docker storage verifier: PASS before build, after build, after download, and during final checks.
- GPU container verifier: PASS during context-sync and after 30B restore.
- `reports/m3-root-disk-guard.md` was refreshed as the committed root-disk guard report for M9E.

## Scope Confirmations

- Public API exposure: not configured.
- Public host bind: not used. MiniMax compose used `127.0.0.1:30002:30000`; restored 30B uses `127.0.0.1:30001` only.
- Fallback model download: not performed.
- `Qwen/Qwen3-235B-A22B-Instruct-2507-FP8` download: not performed.
- Docker/containerd daemon configuration change: not performed.
- Docker/containerd daemon restart: not performed.
- Host CUDA Toolkit install: not performed.
- Host global Python install: not performed.
- Host apt install: not performed.
- Docker prune: not performed.
- Docker image deletion: not performed.
- Model file deletion: not performed.
- Systemd service creation: not performed.
- Docker restart policy: not added.
- Firewall, Caddy, reverse proxy, and API auth/front-door: not configured.
- Proxmox snapshots: not used.

## M9E-R1 MiniMax runtime remediation

- Timestamp: `2026-07-08T20:35:00Z`
- Branch: `milestone/m9e-r1-minimax-runtime-remediation`
- Base branch: `milestone/m9e-large-model-poc`
- Result: STOP. R1 fixed the missing NUMA dependency and proved `sgl_kernel/common_ops` can import in the remediated image, but MiniMax still did not reach `/v1/models` on SM120.

### 30B recovery gate at task start

PASS before MiniMax remediation.

- After the VM reboot, `active.json` still identified `qwen3-30b-a3b-instruct-2507` as active, but the Docker container was exited, port `127.0.0.1:30001` was not listening, and `/v1/models` was not OK.
- `scripts/llmctl start --dry-run` and `scripts/llmctl start --yes` recovered the existing 30B service without downloading models or changing runtime policy.
- `scripts/sglang/verify-sglang-real-fast-live.sh`, `scripts/llmctl active`, `scripts/llmctl status`, and direct `/v1/models` all passed before R1 MiniMax work continued.

### Existing image diagnosis

- Existing image: `local/minimax-m3-ktransformers:0.6.3-post1`.
- Failed container inspected: `minimax-m3-mxfp8-poc`, originally `Exited (1)` before readiness.
- Diagnostic logs: `/data/logs/minimax-m3-poc/m9e-r1-existing-image-diagnostic.log`, `/data/logs/minimax-m3-poc/m9e-r1-existing-image-ldd.log`, `/data/logs/minimax-m3-poc/m9e-r1-existing-container-tail500.log`.
- Existing image `ldconfig`/`find` found no `libnuma.so.1`.
- Existing image `sgl_kernel` import failed with the prior `common_ops` loader error. The package contained `sgl_kernel/sm90/common_ops.abi3.so` and `sgl_kernel/sm100/common_ops.abi3.so`, but no explicit `sm120` common ops file.
- Existing image ldd showed `libnuma.so.1 => not found` for both `sm90` and `sm100` common ops. Other Torch/CUDA libraries required the runtime library path used by Python, so the actionable missing OS dependency was `libnuma.so.1`.

### R1 image build and runtime verification

- R1 Dockerfile change: added only container-isolated apt packages `libnuma1`, `libnuma-dev`, and `numactl`.
- R1 image tag: `local/minimax-m3-ktransformers:0.6.3-post1-r1`.
- Build log: `/data/logs/minimax-m3-poc/m9e-r1-build.log`.
- Build record: `/data/build/ktransformers-minimax-m3/runtime-build-latest.md`.
- Verification record: `/data/build/ktransformers-minimax-m3/runtime-verify-latest.md`.
- `libnuma.so.1` verified present through `ldconfig` and filesystem lookup.
- `kt-kernel=0.6.3.post1`, `sglang-kt=0.6.3.post1`, `kt_kernel`, `sglang`, and `sglang.launch_server` imported.
- The image does not install a separate `ktransformers` Python module; the active runtime path is the `sglang-kt` plus `kt-kernel` wheel path used in M9E.
- `sgl_kernel` imported successfully with GPUs visible, and `common_ops` ldd resolved `libnuma.so.1` plus Torch/CUDA dependencies.
- `python3 -m sglang.launch_server --help` passed. Required flags were present: `--kt-weight-path`, `--kt-method`, `--kt-cpuinfer`, `--kt-threadpool-count`, `--kt-num-gpu-experts`, `--quantization`, and tensor-parallel flag `--tp-size`.
- SM120/common_ops status: no native `sm120` common ops file was present. The wheel contained `sm90` and `sm100`; `sgl_kernel` import succeeded through the package loader's SM100 compatibility/fallback path, not native SM120 coverage.
- Runtime warnings still included `Triton is not supported on current platform, roll back to CPU` and NUMA bind warnings from the containerized `kt_kernel_ext` probe, but they did not block import verification.

### MiniMax R1 relaunch result

STOP after launch attempt.

- 30B was stopped through `scripts/llmctl stop --dry-run` and `scripts/llmctl stop --yes` only after the R1 runtime verification passed.
- 30B model files remained preserved at `/data/models/qwen3-30b-a3b-instruct-2507` (`57G`).
- Previous failed MiniMax container was removed; no image or model files were removed.
- Runtime compose path: `/data/services/llm-manager/compose/minimax-m3-poc.compose.yml`.
- Compose image: `local/minimax-m3-ktransformers:0.6.3-post1-r1`.
- Compose rendered `host_ip: 127.0.0.1`, published `127.0.0.1:30002:30000`, and kept `restart: "no"`.
- MiniMax container started and port `127.0.0.1:30002` listened, but `/v1/models` repeatedly reset the connection and never returned a model list.
- Diagnostics: `/data/logs/minimax-m3-poc/m9e-r1-failure-20260708T203230Z`.
- Primary R1 launch blocker from logs: `AssertionError` at the SGLang MXFP8 quantization path, `assert is_sm100_supported() or is_sm90_supported()`, followed by `Received sigquit from a child process`.
- Interpretation: `libnuma` was a real blocker and is fixed, but it was not the only blocker. MiniMax MXFP8 serving remains unresolved on RTX PRO 6000 Blackwell Workstation / SM120 because the current SGLang MXFP8 code path requires SM90 or SM100.
- MiniMax `/v1/models` did not pass and no chat proof was run.

### R1 recovery and final guards

- Failed MiniMax container was stopped for recovery and left available for diagnostics; no images were removed and no Docker prune was run.
- `scripts/llmctl start --yes` restored the previous 30B service.
- `scripts/sglang/verify-sglang-real-fast-live.sh` passed after restore, including `/v1/models`, non-streaming chat, and streaming checks.
- Current active backend after R1: `Qwen/Qwen3-30B-A3B-Instruct-2507` on SGLang at `http://127.0.0.1:30001/v1`, bound to `127.0.0.1` only.
- Final `/data` mount guard, root-disk guard, Docker storage verifier, GPU container verifier, and `scripts/llmctl active/status` passed.
- Final MiniMax container state after recovery: `minimax-m3-mxfp8-poc` is exited; it is not active.

### R1 scope confirmations

- No public API exposure was configured.
- No public host bind was used.
- No fallback model was downloaded.
- No Docker/containerd daemon configuration was changed.
- No Docker/containerd daemon was restarted.
- No Docker restart policy, systemd service, firewall, reverse proxy, Caddy, or API auth/front-door was created.
- No model files were deleted.
- No Docker images were deleted.
- No Docker prune was run.
- No host CUDA Toolkit, host SGLang/KTransformers, host Python package, or host system package install was performed.

### R1 next recommended task

R1 recommendation, superseded by R2: SM120-specific remediation was investigated in M9E-R2. R2 found no clean released/source-level SM120 gate, so the next task is upstream/release-level support follow-up or an explicitly approved alternate runtime/model decision. Do not download the fallback model unless separately approved.

## M9E-R2 SM120 compatibility remediation

- Timestamp: `2026-07-08T21:35:35Z`
- Branch: `milestone/m9e-r2-sm120-minimax-remediation`
- Base branch: `milestone/m9e-r1-minimax-runtime-remediation`
- Result: STOP. R2 identified no clean released/source-level SM120 remediation path for MiniMax-M3-MXFP8 in the current SGLang-KT / `sgl-kernel` / KT-Kernel stack, so it did not build an R2 image and did not relaunch MiniMax.
- Current active backend after R2: `Qwen/Qwen3-30B-A3B-Instruct-2507` on SGLang at `http://127.0.0.1:30001/v1`, bound to `127.0.0.1` only. R2 never stopped the 30B service.

### R1 result summary

- R1 image: `local/minimax-m3-ktransformers:0.6.3-post1-r1`.
- R1 fixed missing container runtime dependencies: `libnuma.so.1` is present, `sgl_kernel` imports, and `common_ops` ldd resolves.
- R1 remaining blocker: MiniMax launch reached SGLang MXFP8 initialization and failed with `assert is_sm100_supported() or is_sm90_supported()` on RTX PRO 6000 Blackwell Workstation / compute capability 12.0 / SM120.

### R2 baseline gates

- VM and repo path: PASS (`hostname=llmserver`, repo path `/data/services/mixed-memory-llm-api-server`).
- Branch sync: PASS; R2 branch was created from `milestone/m9e-r1-minimax-runtime-remediation` at R1 commit `1f90c3a`.
- Git identity: PASS (`CodexAIagent <133749519+djeZo888@users.noreply.github.com>`).
- `/data` mount guard: PASS.
- Root-disk guard: PASS with report `/tmp/root-disk-guard-before-m9e-r2.md`.
- Docker storage verifier: PASS.
- GPU container verifier: PASS with `nvidia/cuda:13.2.1-base-ubuntu24.04`.
- Hardware: 2 x `NVIDIA RTX PRO 6000 Blackwell Workstation Edition`, driver `595.71.05`, `97887 MiB` each, compute capability `12.0`.
- Storage sample: `/` had `4.5G` available; `/data` had `1.3T` available; MiniMax model remained `414G`; 30B model remained `57G`.
- 30B active gate: PASS. `scripts/llmctl active`, `scripts/llmctl status`, and `scripts/sglang/verify-sglang-real-fast-live.sh` passed before R2 diagnostics.
- Known verifier report side effects on `reports/m3-root-disk-guard.md` and `reports/m4b-docker-containerd-install.md` were restored before R2 documentation changes.

### Official/upstream source refresh

| Source | URL | R2 support notes |
| --- | --- | --- |
| KTransformers MiniMax-M3 tutorial | `https://github.com/kvcache-ai/ktransformers/blob/main/doc/en/kt-kernel/MiniMax-M3-Tutorial.md` | Uses `MiniMaxAI/MiniMax-M3-MXFP8` with SGLang plus KT-Kernel for CPU/GPU heterogeneous inference. The tutorial lists supported GPUs as SM90 Hopper and says upstream SGLang targets SM100 datacenter Blackwell so far; it does not list SM120 workstation Blackwell. It recommends CUDA 12.0+ and CUDA 12.8+ for FP8/MXFP8. |
| KT-Kernel README / PyPI | `https://github.com/kvcache-ai/ktransformers/blob/main/kt-kernel/README.md`, `https://pypi.org/project/kt-kernel/` | Current `kt-kernel 0.6.3.post1` docs say prebuilt CUDA wheel support covers SM80/86/89/90 and list Ampere/Ada/Hopper in the explicit matrix. They do not explicitly list SM120. |
| KTransformers issue #2058 | `https://github.com/kvcache-ai/ktransformers/issues/2058` | Same MiniMax-M3-MXFP8 + RTX PRO 6000 Blackwell / SM120 assertion was reported upstream. A maintainer response points to the MiniMax tutorial and states SM120 is not supported. |
| KTransformers issue #2081 | `https://github.com/kvcache-ai/ktransformers/issues/2081` | New open MiniMax-M3-MXFP8 report on RTX PRO 4500 / SM120 hits the same `assert is_sm100_supported() or is_sm90_supported()` boundary and asks whether SGLang support is required. |
| KTransformers issue #1680 | `https://github.com/kvcache-ai/ktransformers/issues/1680` | Older SM120 sparse-attention question notes RTX Blackwell uncertainty. A maintainer response says that behavior follows SGLang support. |
| SGLang MiniMax-M3 feature issue / PR | `https://github.com/sgl-project/sglang/issues/27536`, `https://github.com/sgl-project/sglang/pull/29107` | SGLang has open MiniMax-M3 support work. The open PR explicitly targets MiniMax-M3 W4A paths on Hopper, not confirmed MiniMax-M3-MXFP8 on SM120. |
| SGLang / sgl-kernel SM120 issue #29900 and PR #29902 | `https://github.com/sgl-project/sglang/issues/29900`, `https://github.com/sgl-project/sglang/pull/29902` | Current sgl-kernel testing on RTX PRO 6000 / SM120 records expected-unsupported failures for DeepGEMM UE8M0, FlashMLA, and fp8 blockwise MoE. This confirms SM120 support gaps in adjacent common kernel paths. |
| SGLang PR #28125 | `https://github.com/sgl-project/sglang/pull/28125` | Open source-level PR adds SM120/SM121 dispatch for `fp8_blockwise_scaled_grouped_mm`, validated on RTX PRO 6000 with CUDA 12.8 and torch 2.11. It is open, not a released/merged wheel path, and does not by itself prove MiniMax-M3-MXFP8 works end-to-end. |
| NVIDIA CUDA GPU compute capability table | `https://developer.nvidia.com/cuda/gpus` | NVIDIA lists `NVIDIA RTX PRO 6000 Blackwell Workstation Edition` under compute capability 12.0. |
| NVIDIA Blackwell Compatibility Guide | `https://docs.nvidia.com/cuda/blackwell-compatibility-guide/index.html` | NVIDIA documents that CUDA binaries need compatible cubin or forward-compatible PTX; if neither compatible cubin nor PTX is present, kernel launch fails. PTX/native coverage is therefore a real gate for SM120. |

### R2 R1-image diagnostics

Diagnostics were saved under `/data/logs/minimax-m3-poc/`:

- Runtime diagnostic: `m9e-r2-r1-runtime-diagnostic.log`.
- Assertion/source search: `m9e-r2-assert-source-search.log`.
- Common-ops coverage: `m9e-r2-common-ops-coverage.log`.

R1 runtime facts:

- Image: `local/minimax-m3-ktransformers:0.6.3-post1-r1`.
- OS in image: Ubuntu 24.04.4 LTS.
- Python: `3.12.3`.
- Torch: `2.9.1+cu128`; torch CUDA runtime: `12.8`.
- Packages: `sglang-kt 0.6.3.post1`, `sgl-kernel 0.3.21`, `kt-kernel 0.6.3.post1`, `flashinfer-python 0.6.3`, `flashinfer-cubin 0.6.3`, `transformers 5.13.0`.
- Torch sees both GPUs and reports device 0 capability `(12, 0)`.
- `sglang.launch_server --help` still exposes required KT/MiniMax flags, including `--kt-weight-path`, `--kt-method`, `--kt-cpuinfer`, `--kt-threadpool-count`, `--kt-num-gpu-experts`, `--quantization`, and `--tp-size` / `--tensor-parallel-size`.

Exact source paths found in the installed R1 image:

- `/opt/minimax-m3-runtime/lib/python3.12/site-packages/sglang/srt/layers/quantization/fp8.py:788`: `assert is_sm100_supported() or is_sm90_supported()`.
- `/opt/minimax-m3-runtime/lib/python3.12/site-packages/sglang/srt/layers/moe/cutlass_moe.py:147`: `assert is_sm100_supported(), "MXFP8 requires SM100"`.
- `/opt/minimax-m3-runtime/lib/python3.12/site-packages/sglang/srt/server_args.py:2538`: `mxfp8 quantization forces --moe-runner-backend=cutlass` for the CUDA/native MXFP8 branch used here.
- `/opt/minimax-m3-runtime/lib/python3.12/site-packages/sglang/srt/server_args.py:2034`: MiniMax-M3 has an SM100-specific backend branch, but no SM120 branch.
- `/opt/minimax-m3-runtime/lib/python3.12/site-packages/sglang/srt/utils/common.py:253`: `is_sm120_supported()` exists and returns true on this host, but `mxfp8_block_convert_required()` returns false for compute capability major >= 10, so the launch stays on the native CUDA MXFP8/Cutlass path rather than a safer conversion path.

Common-ops coverage result:

- `sgl_kernel` contains `sm90/common_ops.abi3.so` and `sm100/common_ops.abi3.so` only.
- No `sgl_kernel/sm120/` directory or native SM120 `common_ops` file is present in `sgl-kernel 0.3.21` inside R1.
- On the SM120 host, `sgl_kernel.load_utils` selects the `sm100` common_ops path for any non-SM90 GPU; Python import loads `/opt/minimax-m3-runtime/lib/python3.12/site-packages/sgl_kernel/sm100/common_ops.abi3.so`.
- With the image runtime library path set to torch/NVIDIA wheel library directories, ldd resolves both `sm90` and `sm100` common ops, including `libnuma.so.1`.
- The R1 image does not include `file`, `strings`, `cuobjdump`, or `nvdisasm`, so deeper fatbin/PTX inspection was not available inside the image.

### SM120 support classification

Classification: D, with C-adjacent kernel coverage risk.

- D: The active MiniMax-M3-MXFP8 runtime path expects SM100 datacenter Blackwell for CUDA native MXFP8/Cutlass, not SM120 workstation Blackwell. The path hard-requires SM90/SM100 at FP8 MoE initialization and hard-requires SM100 in the Cutlass MXFP8 kernel wrapper.
- C-adjacent: the installed `sgl-kernel` wheel lacks native SM120 `common_ops` and current upstream SGLang issues show SM120 gaps in related common kernel paths. R2 did not identify a released wheel, documented build flag, or clean source-build recipe that makes this stack SM120-compatible end-to-end.
- The open SGLang SM120 PR #28125 is relevant but not sufficient for this task: it is open/unreleased, targets `fp8_blockwise_scaled_grouped_mm`, and would still need integration with the SGLang-KT MiniMax-M3-MXFP8 branch plus the SM100-only Python/Cutlass guards before a safe MiniMax launch gate could pass.

### R2 build and relaunch decision

- R2 image built: no.
- R2 image tag: not created.
- MiniMax relaunched: no.
- MiniMax endpoint/chat result: not run; STOP occurred before relaunch by design.
- 30B restore result: restore was not needed because R2 never stopped 30B. The 30B backend remained healthy during R2 diagnostics.
- Fallback model download: not performed.
- Public API exposure: not configured.
- Docker/containerd daemon changes: not performed.
- Docker/containerd daemon restart: not performed.
- Docker prune, image deletion, model deletion: not performed.
- Upstream repro doc: `docs/minimax-sm120-upstream-repro.md`.

### R2 final validation

- Shell syntax checks passed for `scripts/large-models/build-ktransformers-minimax-runtime.sh`, `scripts/large-models/verify-ktransformers-minimax-runtime.sh`, and `scripts/large-models/verify-minimax-m3-poc-live.sh` when present.
- `/data` mount guard: PASS.
- Root-disk guard: PASS with committed report `reports/m3-root-disk-guard.md`.
- Docker storage verifier: PASS.
- GPU container verifier: PASS with `nvidia/cuda:13.2.1-base-ubuntu24.04`.
- STOP-state live verifier: `scripts/sglang/verify-sglang-real-fast-live.sh` passed for the active 30B service.
- `scripts/llmctl active` and `scripts/llmctl status` reported the 30B backend running, healthy, listening on `127.0.0.1:30001`, and `/v1/models` OK.
- `git diff --check`: PASS.

### R2 next recommended task

Prepare an upstream report or track upstream releases for MiniMax-M3-MXFP8 on SM120. A future local remediation should start only after upstream provides a merged/released SM120 path for the relevant SGLang-KT MiniMax branch and `sgl-kernel` common ops, or after the human explicitly approves a different runtime, quantization, or model path. Do not download the fallback model unless separately approved.


## Secret Scan

- Broad grep-based scan matched only intentional docs, tests, scanner patterns, safety strings, historical report text, and env-example comments.
- Changed-file value-shaped scan over the M9E files returned no matches for real-looking HF, OpenAI, or GitHub tokens and no private key blocks.
- No real secret, token, password, private key, auth file, local sudo helper, real `.env`, `MEMORY.md`, or local Codex memory content was identified in the M9E changes.
- M9E-R1 broad grep scan matched only intentional docs, tests, scanner patterns, safety strings, and historical report text. A narrower changed-file value-shaped scan over the R1 files returned no matches for real tokens, private key blocks, or password assignments.
- M9E-R2 broad grep scan matched only intentional docs, tests, scanner patterns, safety strings, env-example comments, and historical report text. A narrower changed-file value-shaped scan over the R2 files returned no matches for real tokens, private key blocks, or password/passwd assignments.

## Final Conclusion

STOP.

M9E proved the gated preflight and download path but did not achieve MiniMax-M3 API proof-of-life. M9E-R1 proved the missing `libnuma.so.1` dependency was real and fixed it inside the isolated image, and `sgl_kernel/common_ops` now import successfully. The R1 relaunch still stopped before `/v1/models` because the current SGLang MXFP8 path asserts SM90 or SM100 support while this VM is RTX PRO 6000 Blackwell Workstation / SM120. M9E-R2 investigated the SM120 boundary and stopped before build/relaunch because the released MiniMax-M3-MXFP8 CUDA path expects SM100 datacenter Blackwell for native MXFP8/Cutlass, the installed `sgl-kernel` wheel has no native SM120 common ops, and no clean released/source-level SM120 gate was identified. The MiniMax model files remain downloaded and preserved at `/data/models/minimax-m3-mxfp8`. The previous 30B SGLang backend remained healthy and active on `http://127.0.0.1:30001/v1`.

## Recommended Next Task

Human review, then upstream/release-level SM120 support follow-up for MiniMax-M3-MXFP8 or an explicitly approved alternate runtime, quantization, or model decision. R2 found no clean released/source-level SM120 gate for the current SGLang-KT/MXFP8 stack. Do not download fallback models unless a separate human-approved task explicitly says so.
