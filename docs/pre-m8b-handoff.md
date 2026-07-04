# Pre-M8B Handoff

- Timestamp: `2026-07-04T15:16:24Z`
- Latest main commit after M8A merge: `a43c9a6d00c7bc1115a609809c2a417b637115f4`
- Repo path: `/data/services/mixed-memory-llm-api-server`
- Repository: `git@github.com:djeZo888/mixed-memory-llm-api-server.git`
- Git identity: `CodexAIagent <133749519+djeZo888@users.noreply.github.com>`
- Next task: M8B actual localhost-only SGLang smoke deployment

## System Baseline

- VM: `ai-vm / 10.156.100.60`
- Hostname: `llmserver`
- `/data` is mounted from `/dev/sdb1`, ext4, label `AI_DATA`.
- Docker Root Dir is `/data/docker`.
- containerd root/state are `/data/containerd/root` and `/run/containerd`.
- NVIDIA driver `595.71.05` is installed.
- NVIDIA Container Toolkit `1.19.1` is installed.
- Docker runtimes include `nvidia`; default runtime remains `runc`.
- CUDA Toolkit and `nvcc` are absent on the host.
- GPU container verification passed with `nvidia/cuda:13.2.1-base-ubuntu24.04`.
- 2 x NVIDIA RTX PRO 6000 Blackwell Workstation Edition GPUs are visible, `97887 MiB` each.
- `scripts/llmctl status` remains `planning_only`.
- Active model/backend remains none.

## M8A Result

- M8A source branch: `milestone/m8a-sglang-smoke-plan`.
- M8A source commit: `fda5e3c7a910e064fa2b34b76a5711fb56d3b1fa`.
- M8A merge commit: `a43c9a6d00c7bc1115a609809c2a417b637115f4`.
- M8A was planning/dry-run only.
- M8A report: `reports/m8a-sglang-smoke-plan.md`.
- M8A main merge report: `reports/m8a-main-merge.md`.
- SGLang smoke deployment doc: `docs/sglang-smoke-deployment.md`.
- Proposed SGLang image tag: `lmsysorg/sglang:v0.5.14-cu130-runtime`.
- linux/amd64 digest recorded by M8A: `sha256:344f361284ba3514d0c93fb7c810f4cdbf89c789117cb51ebea8497d2c8ed101`.
- M8B must verify the linux/amd64 digest again before pulling or running.
- Smoke model: `Qwen/Qwen3-0.6B`.
- License: Apache-2.0.
- Context length: `32768`.
- Model profile: `qwen3-0.6b-smoke`.
- Runtime profile: `sglang`.
- Planned local model path: `/data/models/qwen3-0.6b-smoke`.
- Planned bind/port: `127.0.0.1:30000`.
- Planned endpoint: `http://127.0.0.1:30000/v1/chat/completions`.

## M8B Scope

M8B is the first actual localhost-only SGLang smoke deployment. It should prove download placement, cache placement, pinned image behavior, localhost binding, readiness, local OpenAI-compatible chat completions, logs, stop/deactivate behavior, and post-run root-disk guard status.

## M8B Allowed Actions

- Download `Qwen/Qwen3-0.6B` to `/data/models/qwen3-0.6b-smoke` only.
- Keep Hugging Face cache under `/data/hf-cache`.
- Pull `lmsysorg/sglang:v0.5.14-cu130-runtime` only after verifying the linux/amd64 digest.
- Start the SGLang smoke container bound on the host only to `127.0.0.1:30000`.
- Run local API smoke tests against `http://127.0.0.1:30000/v1/chat/completions`.
- Record logs under `/data/logs/sglang-smoke`.
- Stop/deactivate the smoke runtime if requested by the reviewed plan.
- Rerun root-disk and Docker storage guards after runtime activity.

## M8B Forbidden Actions

- No public API exposure.
- No `0.0.0.0` host bind.
- No first real model download.
- No KTransformers, vLLM, or ik_llama installs.
- No unrelated backend installs.
- No CUDA Toolkit install.
- No Docker/containerd config changes.
- No Docker/containerd restart unless a later approved plan explicitly requires it.
- No systemd service creation.
- No Proxmox host access.
- No branch deletion, force push, or history rewrite.

## Files Future Session Should Read

- `AGENTS.md`
- `ROADMAP.md`
- `docs/current-state.md`
- `docs/pre-m8b-handoff.md`
- `docs/sglang-smoke-deployment.md`
- `docs/model-runtime-manager.md`
- `reports/m8a-sglang-smoke-plan.md`
- `reports/m8a-main-merge.md`
- `configs/compose/compose.sglang-smoke.template.yml`
- `configs/sglang/smoke.env.example`
- `scripts/sglang/plan-sglang-smoke.sh`
- `scripts/sglang/verify-sglang-smoke-plan.sh`
- `scripts/api/smoke-openai-chat.sh`

## Carry-Forward Warnings

- Correctable PCIe AER warnings have been observed during passthrough reset/start activity and should be monitored during future load tests.
- VFIO reset activity has shown reset-done lines.
- Avoid live snapshots with VFIO GPUs because live snapshot previously failed with VFIO migration unsupported.
- QGA is currently working based on human `qm agent 120 ping` verification.
