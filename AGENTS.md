# AGENTS.md

These instructions are durable project rules for agents and operators working in this repository.

## Project Scope

- This VM is API-only.
- This VM runs inference backends and exposes model inference APIs.
- This VM must not implement web browsing, scraping, browser automation, or the human chat UI.
- Another VM will handle browser, scraper, and chat UI work later.
- Build around an OpenAI-compatible API contract.
- Support backend profiles for both KTransformers and ik_llama.
- Use official sources where possible when researching implementation details.

## Storage Rules

- M0 must not touch `/dev/sdb` or `/data`.
- Do not touch `/dev/sdb` except during the approved M2 data-disk milestone.
- After M2 completes, use `/data` for all large AI-server data.
- The root disk must not store models, Hugging Face cache, Docker layers, containerd snapshots, builds, logs, or service data.
- Do not download model weights until `/data` is mounted and verified.
- Before and after any milestone that installs Docker/containerd, downloads models, builds inference software, writes logs, or deploys services, run `scripts/common/require-data-mounted.sh` and `scripts/common/root-disk-guard.sh`. Stop if either fails.
- Expected future data roots include `/data/models`, `/data/hf-cache`, `/data/docker`, `/data/containerd`, `/data/build`, `/data/logs`, `/data/services`, and `/data/services/secrets`.

## Git Rules

- Use feature branches.
- Do not push directly to `main`.
- Use one milestone branch per milestone.
- Do not commit secrets.
- Do not commit `MEMORY.md` or local Codex memory files.
- Do not commit real `.env` files, tokens, passwords, private keys, API keys, Hugging Face tokens, GitHub tokens, SSH keys, sudo files, auth files, model weights, or service secrets.
- Confirm `git remote -v` does not contain credentials before pushing.
- Run a local grep-based secret check before every push.

## Milestone Rules

- Every milestone must create a report under `reports/`.
- Every script or config must have tests or documented verification commands.
- Every milestone must record checks run, warnings, pass/fail status, and next recommended action.
- Do not install packages, configure system services, or mutate disks outside the approved milestone scope.
- Do not install NVIDIA drivers, CUDA Toolkit, PyTorch CUDA wheels, KTransformers GPU components, ik_llama CUDA builds, or NVIDIA Container Toolkit until M5A CUDA/NVIDIA compatibility research has passed and the human has approved the selected version matrix.

## Script Rules

- Shell scripts must use `set -euo pipefail`.
- Shell scripts must support `--help`.
- Destructive scripts must support `--dry-run`.
- Destructive scripts must refuse unsafe or ambiguous states.
- Disk operations require a dry-run/report step before actual changes.

## Backend Strategy

- Do not hard-code one model, quantization, host, port, or backend.
- Backends should bind to `127.0.0.1` by default.
- Any API exposure beyond localhost must require API-key authentication and documented firewall/TLS policy.
- KTransformers is preferred first for Hugging Face-format large MoE models and heterogeneous CPU/GPU experiments.
- ik_llama is preferred for GGUF or hybrid CPU/GPU experiments where appropriate.

## Initial Model Strategy

1. Small smoke-test model.
2. Qwen/Qwen3.6-35B-A3B.
3. Qwen/Qwen3.5-122B-A10B.
4. Qwen/Qwen3.5-397B-A17B.
5. zai-org/GLM-5.2.
