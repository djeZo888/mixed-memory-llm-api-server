# M9E MiniMax-M3 Large-Model Proof Of Life

- Timestamp: `2026-07-07T03:11:04Z`
- Branch: `milestone/m9e-large-model-poc`
- Base branch: `main`
- Repository path: `/data/services/mixed-memory-llm-api-server`
- Selected large model: `MiniMaxAI/MiniMax-M3-MXFP8`
- Runtime path: KTransformers / KT-Kernel plus SGLang-KT heterogeneous CPU/GPU serving
- Expected storage reservation: 500-650 GB on `/data`
- Conclusion: STOP. The runtime built and imported, and the MiniMax model downloaded successfully, but the MiniMax container exited before readiness because `sgl_kernel` could not load `common_ops`; the log includes `ImportError: libnuma.so.1: cannot open shared object file: No such file or directory` and SM120-specific `common_ops` lookup failure context. The prior 30B backend was restored and verified healthy.

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

## Secret Scan

- Broad grep-based scan matched only intentional docs, tests, scanner patterns, safety strings, historical report text, and env-example comments.
- Changed-file value-shaped scan over the M9E files returned no matches for real-looking HF, OpenAI, or GitHub tokens and no private key blocks.
- No real secret, token, password, private key, auth file, local sudo helper, real `.env`, `MEMORY.md`, or local Codex memory content was identified in the M9E changes.

## Final Conclusion

STOP.

M9E proved the gated preflight and download path but did not achieve MiniMax-M3 API proof-of-life. The immediate blocker is the isolated runtime image failing to load SGLang kernel common ops on SM120 due to missing `libnuma.so.1` and no successful `common_ops` fallback. The MiniMax model files remain downloaded and preserved at `/data/models/minimax-m3-mxfp8`. The previous 30B SGLang backend is restored healthy and active on `http://127.0.0.1:30001/v1`.

## Recommended Next Task

Human review, then M9E remediation planning. The next remediation should be narrowly scoped to the MiniMax runtime image and should verify `sgl_kernel` common ops loading, `libnuma.so.1`, SM120 behavior, and the `Triton is not supported` warning before any relaunch. Do not download fallback models unless a separate human-approved task explicitly says so.
