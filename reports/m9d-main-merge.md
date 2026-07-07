# M9D Main Merge Report

- Timestamp: `2026-07-07T00:52:31Z`
- Source branch: `milestone/m9d-large-model-feasibility-plan`
- Target branch: `main`
- Merge commit: `3ae263395fe1c5bca260a0136ab77a6f18110bcb`
- M9D source commit: `c3131db02ace63ffca6a8180d9d3ddea5094d2ae`
- Result: PASS. M9D is merged into `main`; STOP for M9E download/deploy actions until human review.

## Large-Model Decision

- Recommended first large proof-of-life model: `MiniMaxAI/MiniMax-M3-MXFP8`.
- Recommended runtime path: KTransformers / KT-Kernel plus SGLang heterogeneous CPU/GPU serving.
- Fallback model: `Qwen/Qwen3-235B-A22B-Instruct-2507-FP8`.
- Expected storage impact: about 443.75 GB / 413.27 GiB for MiniMax-M3-MXFP8 model files; reserve 500-650 GB on `/data` for model, cache, build artifacts, logs, and rollback room.
- Expected VRAM/RAM risk: high. Do not run concurrently with the current 30B backend. CPU/GPU offload is required. RTX PRO 6000 Blackwell Workstation support still needs proof in M9E.

## Current Active 30B Model State

Validation before merge confirmed the current backend remained active and healthy:

- Active model/backend: `Qwen/Qwen3-30B-A3B-Instruct-2507` on SGLang.
- Served model name: `qwen3-30b-a3b-instruct-2507`.
- Endpoint: `http://127.0.0.1:30001/v1`.
- Bind: `127.0.0.1:30001` only.
- Container: `sglang-qwen3-30b-a3b-instruct-2507`.
- Runtime image: `lmsysorg/sglang:v0.5.14-cu130`.
- Model path: `/data/models/qwen3-30b-a3b-instruct-2507`.
- Launch args: `--tp 2 --context-length 32768 --mem-fraction-static 0.75`.
- Live status: `running` / `healthy`; `/v1/models` returned OK.

## Tests And Checks Run

Source branch validation ran before the merge:

```bash
scripts/common/require-data-mounted.sh
scripts/common/root-disk-guard.sh --report reports/m3-root-disk-guard.md
scripts/docker/verify-docker-storage.sh
scripts/nvidia/verify-gpu-containers.sh
scripts/sglang/verify-sglang-real-fast-live.sh
scripts/llmctl active
scripts/llmctl status
scripts/large-models/plan-large-model.sh --dry-run
scripts/large-models/verify-large-model-plan.sh
bash -n scripts/large-models/plan-large-model.sh
bash -n scripts/large-models/verify-large-model-plan.sh
bash -n tests/shell/test-large-model-plan-static.sh
tests/shell/test-large-model-plan-static.sh
nvidia-smi
df -hT / /data
sudo -n docker system df
sudo -n du -sh /data/models /data/hf-cache /data/docker /data/containerd 2>/dev/null || true
git diff --check
```

Results:

- `/data` mount guard passed.
- Root-disk guard passed.
- Docker storage verifier passed.
- GPU container verifier passed with the standard short CUDA verifier container.
- SGLang real-fast live verifier passed.
- `scripts/llmctl active` and `scripts/llmctl status` reported the current 30B backend active and healthy.
- Large-model plan dry-run and verifier passed.
- Shell syntax/static checks passed.
- Static large-model test passed.
- `nvidia-smi` reported both RTX PRO 6000 Blackwell Workstation Edition GPUs.
- `/data` had about 1.8T free; `/data/models` was about 59G.
- `git diff --check` passed.

## Secret Scan Result

The required broad grep-based scan matched only intentional docs, tests, scanner patterns, safety strings, and historical report text. A narrower value-shaped scan over the changed M9D files found no real secret-shaped values. No real secret, token, password, private key, auth file, local sudo helper, or local Codex memory content was identified.

## No Runtime Mutation Confirmation

M9D and this merge did not download a large model, pull a Docker image, install packages, install or build KTransformers/SGLang/vLLM/PyTorch/CUDA Toolkit/ik_llama, stop or restart the current 30B backend, start a model/backend container, expose a public API, bind to `0.0.0.0`, delete model files, delete Docker images, prune Docker, change Docker/containerd daemon config, or touch disks/fstab/mountpoints/partitioning/Proxmox host.

The only container run during validation was the standard short CUDA verifier container from `scripts/nvidia/verify-gpu-containers.sh`.

## Next Recommended Milestone

M9E actual large-model proof-of-life, in a fresh Codex context after human review.
