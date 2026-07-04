# Current State

This file is the compact source-of-truth handoff for future Codex and ChatGPT sessions.

## Project

- Repo SSH URL: `git@github.com:djeZo888/mixed-memory-llm-api-server.git`
- Public URL: `https://github.com/djeZo888/mixed-memory-llm-api-server`
- Repo path on VM: `/data/services/mixed-memory-llm-api-server`
- Target VM: `ai-vm / 10.156.100.60`
- Hostname: `llmserver`
- User: `user`
- OS: Ubuntu 24.04.4 LTS
- Project state: M0-M7B merged into `main`; M8A planning branch in progress

## Git Attribution

Future commits must use:

```text
CodexAIagent <133749519+djeZo888@users.noreply.github.com>
```

Old commits were previously attributed incorrectly due to this placeholder email:

```text
12345678+djeZo888@users.noreply.github.com
```

Old history was not rewritten. Do not create new commits unless Git config uses the correct email. M4B was squash-merged into `main` after attribution was fixed.

## Completed Milestones

- M0 repo bootstrap: merged
- M1 VM preflight: merged
- M2 data disk setup: merged
- M3 root-disk guard: merged
- M4A Docker/containerd plan: merged
- M5A CUDA/NVIDIA compatibility gate: merged
- M4B Docker/containerd install: squash-merged by this task
- M5A CUDA/NVIDIA compatibility research: merged into main
- M5B NVIDIA host driver: passed and merged into main
- M6A NVIDIA Container Toolkit planning/dry-run: merged into `main` with corrected future test image `nvidia/cuda:13.2.1-base-ubuntu24.04`
- M6B NVIDIA Container Toolkit install: merged into `main`; pre-reboot install, GPU container test, guest reboot, and post-reboot verification passed
- M7A model/runtime research: merged into `main`; research-only report is `reports/m7a-model-runtime-research.md`
- M7A main merge report: `reports/m7a-main-merge.md`
- M7B model/runtime manager abstraction: merged into `main`; dry-run/planning report is `reports/m7b-model-runtime-manager.md`
- M7B main merge report: `reports/m7b-main-merge.md`

## Current Storage

- Root filesystem: ext4 on `/dev/mapper/ubuntu--vg-ubuntu--lv`, about 15G
- `/data`: `/dev/sdb1`, ext4, label `AI_DATA`, UUID `8daf56f1-5649-4163-9d87-919c2d271875`
- `/data` is mounted by UUID in `/etc/fstab`
- Required `/data` directories exist:
  - `/data/models`
  - `/data/hf-cache`
  - `/data/docker`
  - `/data/containerd`
  - `/data/services`
  - `/data/build`
  - `/data/logs`
  - `/data/backups`
  - `/data/services/secrets`

## Current Docker/Containerd

- Docker: `29.6.1`
- containerd: `v2.2.5`
- Docker Compose: `v5.3.0`
- Docker Root Dir: `/data/docker`
- containerd root: `/data/containerd/root`
- containerd state: `/run/containerd`
- `/var/lib/docker`: absent
- `/var/lib/containerd`: absent
- `/data/docker` may be mode `0710` and is Docker-managed
- `/data/containerd` root/state policy is documented
- `hello-world`: passed
- `user` was not added to the `docker` group
- NVIDIA Container Toolkit is installed:
  - `nvidia-container-toolkit 1.19.1-1`
  - `nvidia-container-toolkit-base 1.19.1-1`
  - `libnvidia-container-tools 1.19.1-1`
  - `libnvidia-container1 1.19.1-1`
- `nvidia-ctk`: `/usr/bin/nvidia-ctk`, `NVIDIA Container Toolkit CLI version 1.19.1`
- Docker runtimes include `nvidia`; default runtime remains `runc`
- Docker daemon config backup from M6B: `/etc/docker/daemon.json.pre-m6b-nvidia-container-toolkit.20260703T162043Z.bak`
- M6A confirms Docker Root Dir remains `/data/docker`
- M6A confirms containerd root remains `/data/containerd/root`


## Current GPU Driver State

- M5A is merged into `main`.
- M5A execution report: `reports/m5a-cuda-nvidia-compatibility.md`.
- M5A main merge and pre-M5B handoff report: `reports/m5a-main-merge.md`.
- M5B host NVIDIA driver installation passed with Ubuntu `nvidia-driver-595-open` / `nvidia-utils-595`.
- M5B execution report: `reports/m5b-nvidia-host-driver.md`.
- M5B main merge report: `reports/m5b-main-merge.md`.
- Installed NVIDIA driver version: `595.71.05`.
- `nvidia-smi -L` reports exactly two GPUs:
  - GPU 0: NVIDIA RTX PRO 6000 Blackwell Workstation Edition, PCI `00000000:01:00.0`, memory `97887 MiB`.
  - GPU 1: NVIDIA RTX PRO 6000 Blackwell Workstation Edition, PCI `00000000:02:00.0`, memory `97887 MiB`.
- No RTX 6000 Ada is expected or reported.
- `nouveau` is not loaded or bound to the GPUs; the NVIDIA driver is bound.
- `nvcc` is absent.
- CUDA Toolkit is absent.
- NVIDIA Container Toolkit is installed and Docker runtime configuration is present.
- `nvidia-ctk` is installed.
- Approved CUDA container test image `nvidia/cuda:13.2.1-base-ubuntu24.04` passed.
- The CUDA container saw exactly two NVIDIA RTX PRO 6000 Blackwell Workstation Edition GPUs with `97887 MiB` each.
- M6B pulled and ran `nvidia/cuda:13.2.1-base-ubuntu24.04` for `nvidia-smi` only.
- Host CUDA Toolkit and `nvcc` remain absent.
- PyTorch, KTransformers, ik_llama, models, and API exposure remain blocked until their approved milestones.
- M7A did not install PyTorch, KTransformers, ik_llama, vLLM, SGLang, CUDA Toolkit, model weights, backend services, or API exposure.
- Human Proxmox review: VM 120 has `hostpci0: 0000:c1:00,pcie=1,rombar=1` and `hostpci1: 0000:e1:00,pcie=1,rombar=1`, with parent snapshot `before-m5b-nvidia-driver-595-open`; `qm status 120` reports running.
- Proxmox host logs show VFIO reset activity with reset-done lines during VM stop/start/reboot.
- Proxmox host logs show correctable PCIe AER Data Link Layer events around GPU reset/start activity, especially root port `0000:e0:01.1`; human decision: monitor after M6/M7/load tests, but not a blocker for M6.
- QEMU Guest Agent status after M5B merge: human Proxmox host check `qm agent 120 ping` returned no output and produced no new guest-ping warning, so QGA currently works. Older guest-ping timeouts are documented as historical/temporary, not a current blocker.
- Live snapshots with VFIO GPUs remain disallowed because prior logs showed `VFIO migration is not supported in kernel`; use stopped/offline snapshots unless explicitly tested and approved.

## Guardrails

- Run `scripts/common/require-data-mounted.sh` before heavy work.
- Run `scripts/common/root-disk-guard.sh` before and after Docker, model, build, log, or service work.
- Run `scripts/docker/verify-docker-storage.sh` after Docker/containerd changes.
- Do not install NVIDIA/CUDA/PyTorch GPU/KTransformers GPU/ik_llama CUDA/NVIDIA Container Toolkit before M5A compatibility research passes and the human approves the selected version matrix.
- Do not download models before M5/M6/M7/M8 readiness.
- Do not expose API without authentication/firewall review.
- Do not commit secrets.
- M7A is a research gate only. It does not approve model downloads, backend installs/builds, service creation, Docker/containerd changes, restarts, or API exposure.
- M7B is a dry-run/planning manager gate only. It added profiles, templates, docs, and tests, but does not approve model downloads, backend installs/builds, Docker image pulls, runtime containers, service creation, Docker/containerd changes, restarts, or API exposure.

## Current M7A Result

- M7A report: `reports/m7a-model-runtime-research.md`.
- M7A was merged into `main` with merge commit `e4f5dbf6ad2680d3a96965bd7083c03bdc2e5081`.
- M7A main merge report: `reports/m7a-main-merge.md`.
- PASS for research and shortlist.
- STOP for downloads, backend installs/builds, service creation, Docker/containerd changes, restarts, and API exposure until a later approved milestone explicitly expands scope.
- Human decision: model choice is intentionally not final. The system should support several model/runtime profiles and allow only one active model/backend at a time.
- M7B must build a model/runtime manager abstraction, not a single hard-coded model path.
- Top large/high-quality candidates:
  - `Qwen/Qwen3-235B-A22B-Instruct-2507`
  - `MiniMaxAI/MiniMax-M3`
  - `zai-org/GLM-5.2`
- Large feasibility comparator:
  - `deepseek-ai/DeepSeek-V4-Flash`
- Top smaller/faster candidates:
  - `Qwen/Qwen3-30B-A3B-Instruct-2507`
  - `Qwen/Qwen3.6-35B-A3B`
  - `Qwen/Qwen3-30B-A3B-Thinking-2507`
- Coding-specific alternate:
  - `Qwen/Qwen3-Coder-30B-A3B-Instruct`
- Recommended first download after approval: `Qwen/Qwen3-0.6B` for smoke testing only.
- Recommended first real model after smoke: `Qwen/Qwen3-30B-A3B-Instruct-2507`.
- Recommended first backend to implement in M7B: pinned, localhost-only SGLang Docker profile with all model/cache/log/build paths under `/data`.
- KTransformers/KT-Kernel remains the large-MoE heterogeneous RAM+VRAM path to prototype after SGLang smoke is defined.
- The manager should make new model profiles easy to add without changing the API contract or hard-coding one backend/model into scripts.
- QGA is currently working based on human Proxmox host verification with `qm agent 120 ping`; older guest-ping timeouts are historical/temporary and not a current blocker.
- Future work must not configure containerd NVIDIA runtime, install CUDA Toolkit, install PyTorch, install KTransformers, install ik_llama, download models, configure inference backends, or expose API unless explicitly expanded by the relevant milestone.

## Current M7B Result

- M7B report: `reports/m7b-model-runtime-manager.md`.
- M7B was merged into `main` with merge commit `dc32c8239baf1bcf9cd38c1e57939bb268364969`.
- M7B main merge report: `reports/m7b-main-merge.md`.
- `scripts/llmctl` exists and supports metadata, validation, planning, dry-run activation, dry-run deactivation, status, logs dry-run, download planning, and environment inspection commands.
- Model profiles exist under `configs/models/profiles/`:
  - `qwen3-0.6b-smoke`
  - `qwen3-30b-a3b-instruct-2507`
  - `qwen3-235b-a22b-instruct-2507`
  - `minimax-m3`
  - `glm-5.2`
- Runtime profiles exist under `configs/runtimes/`:
  - `sglang`
  - `ktransformers`
  - `ik-llama`
  - `vllm`
- Only one model/backend should be active at once.
- Model choice is intentionally not final.
- New models should be added as declarative profiles instead of hard-coding model-specific behavior into deployment logic.
- M7B did not download models, install backends, pull backend Docker images, run model/backend containers, expose API, modify Docker/containerd config, restart Docker/containerd, or create services.


## Current M8A Branch Result

- Branch: `milestone/m8a-sglang-smoke-plan`.
- M8A status: planning/dry-run only until merged and reviewed.
- M8A report: `reports/m8a-sglang-smoke-plan.md`.
- SGLang smoke deployment doc: `docs/sglang-smoke-deployment.md`.
- Smoke model profile remains `qwen3-0.6b-smoke` for `Qwen/Qwen3-0.6B`.
- Preferred smoke runtime remains `sglang`.
- Proposed pinned SGLang image for M8B review: `lmsysorg/sglang:v0.5.14-cu130-runtime`.
- Planned local model path: `/data/models/qwen3-0.6b-smoke`.
- Planned local endpoint: `http://127.0.0.1:30000/v1/chat/completions`.
- Active model remains none.
- No model has been downloaded by M8A.
- No SGLang image has been pulled by M8A.
- No backend is running from M8A.
- No API has been exposed by M8A.
- Next after human review: M8B actual localhost-only SGLang smoke deployment.

## Next Recommended Milestone

- M8A SGLang smoke-model deployment planning/dry-run.
- Current M8A work branch: `milestone/m8a-sglang-smoke-plan`.
- M8A must be planning/dry-run only unless explicitly expanded after human review.
- M8A should plan the SGLang + `Qwen/Qwen3-0.6B` smoke path.
- M8A should not download `Qwen/Qwen3-0.6B` yet.
- M8A should not pull an SGLang Docker image yet.
- M8A should not run backend containers yet.
- M8A should not expose API yet.
- M8A should preserve localhost-only backend binding.
- M8A should use the manager and profiles created in M7B.
- M8B or later should perform any actual smoke-model deploy/run only after human review and explicit approval.
- M9 remains the first real fast-model path after smoke.

## Carry-Forward Operational Warnings

- Correctable PCIe AER warnings have been observed during passthrough reset/start activity and should be monitored during future load tests.
- VFIO reset activity has shown reset-done lines.
- Avoid live snapshots with VFIO GPUs because live snapshot previously failed with VFIO migration unsupported.
- QGA is currently working based on human `qm agent 120 ping` verification.

## Known Future Model Candidates

- `Qwen/Qwen3-0.6B` for small smoke-test model first
- `Qwen/Qwen3-30B-A3B-Instruct-2507`
- `Qwen/Qwen3.6-35B-A3B`
- `Qwen/Qwen3-30B-A3B-Thinking-2507`
- `Qwen/Qwen3-Coder-30B-A3B-Instruct`
- `Qwen/Qwen3-235B-A22B-Instruct-2507`
- `MiniMaxAI/MiniMax-M3`
- `zai-org/GLM-5.2`
- `deepseek-ai/DeepSeek-V4-Flash` as large feasibility comparator

## New-chat Instruction

Future sessions should read:

- `AGENTS.md`
- `ROADMAP.md`
- `docs/current-state.md`
- `docs/cuda-driver-compatibility.md`
- `docs/root-disk-guard.md`
- `docs/docker-containerd-storage.md`
- `reports/m5a-cuda-nvidia-compatibility.md`
- `reports/m5a-main-merge.md`
- `reports/m5b-nvidia-host-driver.md`
- `reports/m5b-main-merge.md` if present
- `docs/nvidia-container-toolkit.md` if present
- `reports/m6a-nvidia-container-toolkit-plan.md` if present
- `reports/m6a-main-merge.md` if present
- `reports/m6b-main-merge.md` if present
- `reports/m6b-nvidia-container-toolkit-install.md` if present
- `reports/m7a-model-runtime-research.md` if present
- `reports/m7a-main-merge.md` if present
- `docs/model-runtime-manager.md` if present
- `docs/model-matrix.md` if present
- `reports/m7b-model-runtime-manager.md` if present
- `reports/m7b-main-merge.md` if present
- `docs/pre-m8-handoff.md` if present
- `reports/m4b-main-merge.md`
- Latest reports

Then continue with M8A SGLang smoke-model deployment planning/dry-run only.
