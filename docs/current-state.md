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
- NVIDIA Container Toolkit is not installed


## Current M5A Research Snapshot

- M5A is merged into `main`.
- M5A execution report: `reports/m5a-cuda-nvidia-compatibility.md`
- M5A main merge and pre-M5B handoff report: `reports/m5a-main-merge.md`
- M5A result: research-only `STOP` for installation until human approval.
- Expected GPU inventory after driver installation: 2 x RTX PRO 6000 Blackwell Workstation Edition 96 GB.
- No RTX 6000 Ada is expected in this VM.
- Current pre-driver state: `lspci` sees two NVIDIA PCI display devices with device ID `10de:2bb1`, subsystem `10de:204b`; `nvidia-smi` is absent; `nvcc` is absent; `nouveau` is loaded.
- M5B must validate exact GPU names, VRAM, PCI bus IDs, driver binding, and passthrough stability before M6/M7/M8.
- Current recommendation for human review: M5B should install only the selected host NVIDIA driver first, with Ubuntu `nvidia-driver-595-open` as the recommended candidate and R580 LTS documented as the longer-support fallback.
- M5B must not install CUDA Toolkit unless explicitly approved.
- M6 NVIDIA Container Toolkit must wait until host `nvidia-smi` passes in M5B.
- Host CUDA Toolkit, PyTorch, KTransformers, ik_llama, NVIDIA Container Toolkit, models, and API exposure remain blocked until their approved milestones.

## Guardrails

- Run `scripts/common/require-data-mounted.sh` before heavy work.
- Run `scripts/common/root-disk-guard.sh` before and after Docker, model, build, log, or service work.
- Run `scripts/docker/verify-docker-storage.sh` after Docker/containerd changes.
- Do not install NVIDIA/CUDA/PyTorch GPU/KTransformers GPU/ik_llama CUDA/NVIDIA Container Toolkit before M5A compatibility research passes and the human approves the selected version matrix.
- Do not download models before M5/M6/M7/M8 readiness.
- Do not expose API without authentication/firewall review.
- Do not commit secrets.

## Next Recommended Milestone

- Start a fresh ChatGPT/Codex context before M5B.
- M5B host NVIDIA driver installation may start only after human approval.
- M5B should install only the approved host NVIDIA driver, followed by `nvidia-smi` validation before and after reboot.
- M5B must not install CUDA Toolkit unless explicitly approved.
- M5B must not install PyTorch, KTransformers, ik_llama, NVIDIA Container Toolkit, models, or API services.
- M6 NVIDIA Container Toolkit may start only after host `nvidia-smi` passes.

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
- `reports/m4b-main-merge.md`
- Latest reports

Then continue with M5B only after human approval, keeping M5B host-driver-only unless explicitly expanded.
