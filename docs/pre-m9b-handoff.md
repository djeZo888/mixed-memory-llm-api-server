# Pre-M9B Handoff

- Timestamp: `2026-07-05T14:41:54Z`
- Latest main commit after M9A merge: `e04385fe096ee3d2ed0e41e28f8c3feaf11312b2`
- Repository: `git@github.com:djeZo888/mixed-memory-llm-api-server.git`
- Repo path: `/data/services/mixed-memory-llm-api-server`
- Git identity for future commits: `CodexAIagent <133749519+djeZo888@users.noreply.github.com>`
- M9A merge report: `reports/m9a-main-merge.md`
- M9A plan report: `reports/m9a-first-real-fast-model-plan.md`

## System Baseline

- Hostname: `llmserver`
- OS: Ubuntu 24.04.4 LTS
- GPUs: 2 x NVIDIA RTX PRO 6000 Blackwell Workstation Edition
- VRAM: `97887 MiB` per GPU
- NVIDIA driver: `595.71.05`
- Docker Root Dir: `/data/docker`
- containerd root: `/data/containerd/root`
- containerd state: `/run/containerd`
- `/data`: ext4 on `/dev/sdb1`, label `AI_DATA`, mounted at `/data`
- Host CUDA Toolkit and `nvcc`: absent by policy
- NVIDIA Container Toolkit: installed and verified for Docker GPU containers

## Active Smoke State

- Model/backend: `qwen3-0.6b-smoke` on SGLang
- Endpoint: `http://127.0.0.1:30000/v1`
- Bind: `127.0.0.1:30000` only
- Container: `sglang-smoke-qwen3-0.6b`
- Image: `lmsysorg/sglang:v0.5.14-cu130`
- Model path: `/data/models/qwen3-0.6b-smoke`
- Status during M9A merge validation: active and healthy

## M9A Recommendation

- Recommended first real model: `Qwen/Qwen3-30B-A3B-Instruct-2507`
- Fallback model: `Qwen/Qwen3-Coder-30B-A3B-Instruct`
- Planned model path: `/data/models/qwen3-30b-a3b-instruct-2507`
- Planned bind/port: `127.0.0.1:30001:30000`
- Planned SGLang image: `lmsysorg/sglang:v0.5.14-cu130`

## M9B Approved Target

```text
Qwen/Qwen3-30B-A3B-Instruct-2507
```

Only this model is approved for M9B download. Do not download `Qwen/Qwen3-Coder-30B-A3B-Instruct`, `Qwen/Qwen3.6-35B-A3B`, `Qwen/Qwen3-30B-A3B-Thinking-2507`, larger models, or alternate models without explicit human approval.

## M9B Files To Use

- Compose template: `configs/compose/compose.sglang-qwen3-30b.template.yml`
- Env template: `configs/sglang/qwen3-30b.env.example`
- Planning script: `scripts/sglang/plan-sglang-real-fast.sh`
- Plan verifier: `scripts/sglang/verify-sglang-real-fast-plan.sh`
- Manager/lifecycle script: `scripts/llmctl`
- Smoke lifecycle verifier: `scripts/sglang/verify-sglang-lifecycle.sh`
- Smoke API helper: `scripts/api/smoke-openai-chat.sh`

## M9B Context-Sync Requirement

M9B must start with context-sync from `main`:

```bash
hostname
cd /data/services/mixed-memory-llm-api-server
git fetch origin
git checkout main
git pull --ff-only origin main
git status
scripts/common/require-data-mounted.sh
scripts/common/root-disk-guard.sh --report reports/m3-root-disk-guard.md
scripts/docker/verify-docker-storage.sh
scripts/nvidia/verify-gpu-containers.sh
scripts/llmctl doctor
scripts/llmctl validate
scripts/llmctl active
scripts/llmctl status
scripts/sglang/verify-sglang-lifecycle.sh
scripts/api/smoke-openai-chat.sh --yes-run-smoke-api
scripts/sglang/plan-sglang-real-fast.sh --dry-run
scripts/sglang/verify-sglang-real-fast-plan.sh
```

Stop if smoke is not active and healthy, if `/data` or storage guards fail, or if the repo is not clean after restoring known verifier side effects.

## M9B Allowed Deployment Sequence

1. Stop smoke through `scripts/llmctl stop --yes` only after explicit human approval.
2. Create `/data/models/qwen3-30b-a3b-instruct-2507`.
3. Download `Qwen/Qwen3-30B-A3B-Instruct-2507` to `/data/models/qwen3-30b-a3b-instruct-2507` only, with Hugging Face cache under `/data/hf-cache`.
4. Verify or use the approved pinned SGLang image only.
5. Start SGLang real model on localhost-only bind `127.0.0.1:30001:30000`.
6. Run `/health`, `/v1/models`, non-streaming chat, streaming chat, and logs checks.
7. Record startup time, throughput, RAM, VRAM, context behavior, and failure modes.
8. Rerun root-disk, Docker storage, GPU container, and manager-state checks.

## M9B Hard Stops

- Do not expose public API.
- Do not bind host to `0.0.0.0`.
- Do not download any model except `Qwen/Qwen3-30B-A3B-Instruct-2507`.
- Do not modify Docker/containerd daemon config.
- Do not restart Docker/containerd unless a later human instruction explicitly expands scope.
- Do not install host packages or backend stacks.
- Do not delete model files or Docker images.
- Do not prune Docker.
- Do not touch disks, fstab, mountpoints, partitioning, or Proxmox host.

## Carry-Forward Proxmox Notes

- Correctable PCIe AER warnings have been observed during passthrough reset/start activity.
- VFIO reset-done lines have been observed.
- Avoid live snapshots with VFIO GPUs because prior logs showed VFIO migration is unsupported.
- QEMU Guest Agent currently works based on human `qm agent 120 ping` verification.

## Next Task

Start a fresh Codex context for M9B actual first real fast-model deployment.
