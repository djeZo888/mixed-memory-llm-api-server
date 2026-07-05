# M9A Main Merge Report

- Timestamp: `2026-07-05T14:41:54Z`
- Source branch: `milestone/m9a-first-real-fast-model-plan`
- Target branch: `main`
- Merge commit hash: `e04385fe096ee3d2ed0e41e28f8c3feaf11312b2`
- M9A source commit hash: `670e1349e18f33cd004a8f49fe63ddb16bd987ca`
- Result: PASS. M9A was merged into `main`; the smoke backend remained active, healthy, and localhost-only.

## Context-Sync Result

PASS. M9A context-sync passed on `llmserver` at `/data/services/mixed-memory-llm-api-server` before branch creation, and this merge task revalidated the pushed M9A branch before merging.

## M9A Recommendation

- Recommended first real model: `Qwen/Qwen3-30B-A3B-Instruct-2507`
- Fallback model: `Qwen/Qwen3-Coder-30B-A3B-Instruct`
- Planned model path: `/data/models/qwen3-30b-a3b-instruct-2507`
- Planned bind/port: `127.0.0.1:30001:30000`
- Planned runtime: SGLang through `configs/compose/compose.sglang-qwen3-30b.template.yml`
- Planned env template: `configs/sglang/qwen3-30b.env.example`

## Current Smoke State

- Active model/backend: `qwen3-0.6b-smoke` on SGLang.
- Endpoint: `http://127.0.0.1:30000/v1`.
- Bind: `127.0.0.1:30000` only.
- Container: `sglang-smoke-qwen3-0.6b`.
- Image: `lmsysorg/sglang:v0.5.14-cu130`.
- Validation result: active and healthy during M9A merge validation.

## M9B Planned Transition

1. Start in a fresh Codex context and run context-sync first.
2. Stop smoke through `scripts/llmctl stop --yes` only after explicit human approval.
3. Download `Qwen/Qwen3-30B-A3B-Instruct-2507` to `/data/models/qwen3-30b-a3b-instruct-2507` only.
4. Keep Hugging Face cache under `/data/hf-cache` and logs under `/data/logs`.
5. Start the real SGLang profile on a localhost-only bind.
6. Run `/v1/models`, non-streaming chat, streaming chat, and health checks.
7. Validate root-disk guard, GPU container support, Docker storage, and active manager state.
8. Keep public API exposure blocked.

## Tests And Checks Run

Pre-merge validation on the M9A branch:

- `scripts/common/require-data-mounted.sh`: PASS.
- `scripts/common/root-disk-guard.sh --report reports/m3-root-disk-guard.md`: PASS.
- `scripts/docker/verify-docker-storage.sh`: PASS.
- `scripts/nvidia/verify-gpu-containers.sh`: PASS with `nvidia/cuda:13.2.1-base-ubuntu24.04`.
- `scripts/llmctl doctor`: PASS.
- `scripts/llmctl validate`: PASS with 7 model profiles and 4 runtime profiles.
- `scripts/llmctl active`: PASS; smoke active and healthy.
- `scripts/llmctl status`: PASS; manager active.
- `scripts/sglang/verify-sglang-lifecycle.sh`: PASS.
- `scripts/api/smoke-openai-chat.sh --yes-run-smoke-api`: PASS.
- `scripts/sglang/plan-sglang-real-fast.sh --dry-run`: PASS and printed dry-run-only M9B sequence.
- `scripts/sglang/verify-sglang-real-fast-plan.sh`: PASS.
- `bash -n scripts/sglang/plan-sglang-real-fast.sh`: PASS.
- `bash -n scripts/sglang/verify-sglang-real-fast-plan.sh`: PASS.
- `bash -n tests/shell/test-sglang-real-fast-static.sh`: PASS.
- `tests/shell/test-sglang-real-fast-static.sh`: PASS.
- `sudo -n docker ps`: PASS; only the smoke SGLang container was running.
- `sudo -n docker system df`: PASS.
- `df -hT / /data`: PASS; root and `/data` layout remained as expected.
- `git diff --check`: PASS.

## Secret Scan Result

The grep-based scan matched only intentional documentation, static-test scanner patterns, safety strings, sanitizer code, prior report text, and env-example comments. A narrower changed-file scan for value-shaped tokens, private keys, and password assignments returned no matches. No real secret, token, password, private key, auth file, real `.env`, local sudo helper, `MEMORY.md`, or local Codex memory content was identified.

## No-Action Confirmations

- No real model was downloaded.
- `Qwen/Qwen3-30B-A3B-Instruct-2507` was not downloaded.
- No Docker image was pulled.
- No real-model/backend container was run.
- The smoke container was not stopped.
- Docker/containerd daemon configuration was not modified.
- Docker/containerd was not restarted.
- No package, SGLang, PyTorch, KTransformers, vLLM, ik_llama, or CUDA Toolkit install/build occurred.
- No public API exposure was configured.
- No host `0.0.0.0` bind was configured.
- No model files or Docker images were deleted.
- Docker prune was not run.
- No disk, fstab, mountpoint, partitioning, or Proxmox host change occurred.
- Only the existing GPU verifier ephemeral CUDA `nvidia-smi` checks ran.

## Next Recommended Milestone

M9B actual first real fast-model deployment in a fresh Codex context.
