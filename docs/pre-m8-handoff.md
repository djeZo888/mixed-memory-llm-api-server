# Pre-M8 Handoff

- Timestamp: `2026-07-04T11:15:53Z`
- Repo path: `/data/services/mixed-memory-llm-api-server`
- M7B merge commit on `main`: `dc32c8239baf1bcf9cd38c1e57939bb268364969`
- M7B source commit: `d7a31be06888180da45e5fd430b6dd8db30c0b8a`
- Branch merged: `milestone/m7b-model-runtime-manager`
- Next task: M8A SGLang smoke-model deployment planning/dry-run

## System State Summary

- `/data` is mounted from `/dev/sdb1`, ext4, label `AI_DATA`.
- Docker Root Dir is `/data/docker`.
- containerd root/state are `/data/containerd/root` and `/run/containerd`.
- NVIDIA driver `595.71.05` is installed.
- NVIDIA Container Toolkit `1.19.1` is installed.
- `nvidia-ctk` is installed.
- CUDA Toolkit and `nvcc` are absent on the host.
- Docker GPU container test passed with `nvidia/cuda:13.2.1-base-ubuntu24.04`.
- 2 x NVIDIA RTX PRO 6000 Blackwell Workstation Edition GPUs are visible.

## M7B Manager Summary

- `scripts/llmctl` exists and supports metadata, validation, planning, dry-run activation, dry-run deactivation, status, logs dry-run, download planning, and environment inspection.
- Model catalog and profiles exist under `configs/models/`.
- Runtime profiles exist under `configs/runtimes/`.
- Compose templates exist under `configs/compose/`.
- Model/runtime choice is intentionally not final.
- New models should be added as profiles.
- Only one model/backend should be active at once.
- Backends should bind to localhost by default.
- M7B did not download models, install backends, pull backend Docker images, run backend containers, expose API, modify Docker/containerd config, restart Docker/containerd, or create services.

## M8A Scope

M8A should plan and dry-run the SGLang + `Qwen/Qwen3-0.6B` smoke path using the manager/profiles created in M7B. It should verify exact planned paths, templates, ports, localhost binding, environment variables, state handling, safety checks, and the review gates required before M8B or later performs any real deploy/run action.

## Strict M8A Exclusions

- No model download.
- No backend install.
- No Docker image pull.
- No container run.
- No API exposure.
- No Docker/containerd config change.
- No Docker/containerd restart.
- No service creation.

## Required Files For Future Sessions

- `AGENTS.md`
- `ROADMAP.md`
- `docs/current-state.md`
- `docs/model-runtime-manager.md`
- `docs/model-matrix.md`
- `docs/nvidia-container-toolkit.md`
- `docs/docker-containerd-storage.md`
- `reports/m7b-model-runtime-manager.md`
- `reports/m7b-main-merge.md`

## Proxmox Passthrough Warning Summary

Correctable PCIe AER warnings have been observed during passthrough reset/start activity and should be monitored during future load tests. VFIO reset activity has shown reset-done lines. Avoid live snapshots with VFIO GPUs because a prior live snapshot failed with VFIO migration unsupported. Use stopped/offline snapshots unless live snapshot behavior is explicitly tested and approved.

## QGA Status

QGA is currently working based on human Proxmox host verification with `qm agent 120 ping`. Older guest-ping timeouts are historical/temporary and not a current blocker.

## Next Recommended Action

Start M8A in a fresh Codex context and keep it to SGLang smoke-model deployment planning/dry-run only.
