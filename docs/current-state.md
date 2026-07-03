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

## Next Recommended Milestone

- M7A model/runtime research is next.
- M7A must be research-only: no model downloads, no backend installation, no inference backend configuration, and no API service changes.
- M7A must use current official/current web sources where possible.
- M7A should produce:
  - 3 large/high-quality model candidates.
  - 3 smaller/faster model candidates.
  - A runtime/backend recommendation matrix for human review.
- QGA is currently working based on human Proxmox host verification with `qm agent 120 ping`; older guest-ping timeouts are historical/temporary and not a current blocker.
- Future work must not configure containerd NVIDIA runtime, install CUDA Toolkit, install PyTorch, install KTransformers, install ik_llama, download models, configure inference backends, or expose API unless explicitly expanded by the relevant milestone.

## Known Future Model Candidates

- Small smoke-test model first
- `Qwen/Qwen3.6-35B-A3B`
- `Qwen/Qwen3.5-122B-A10B`
- `Qwen/Qwen3.5-397B-A17B`
- `zai-org/GLM-5.2`

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
- `reports/m4b-main-merge.md`
- Latest reports

Then continue with M7A model/runtime research only.
