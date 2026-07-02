# ROADMAP.md

Each milestone must produce a report under `reports/`, run applicable checks, run a secret scan, commit to a feature branch, and push the branch.

## M0 repository bootstrap

Create public repository skeleton, durable project instructions, documentation, CI metadata, issue templates, and `reports/m0-repo-bootstrap.md`.

## M1 VM preflight

Record host identity, OS, Codex availability, sudo behavior, disks, `/data` state, GPU inventory, network, firewall, failed services, and boot errors without modifying the system.

## M2 data disk dry-run and /data preparation

Perform a dry-run proving the intended 2 TB data disk is unused, unmounted, non-root, and safe. After approval, prepare `/data`, mount by UUID, create required data directories, and verify persistence after reboot.

## M3 root-disk guard

Create reusable checks that fail when model weights, Hugging Face cache, Docker data, containerd snapshots, builds, logs, or service data appear on the root disk. M3 produces `scripts/common/require-data-mounted.sh`, `scripts/common/root-disk-guard.sh`, fixture/static tests, documentation, and `reports/m3-root-disk-guard.md`.

## M4A Docker/containerd storage planning

Create Docker/containerd installation and storage scripts, static tests, dry-run output, and `reports/m4a-docker-containerd-plan.md` without installing packages or editing system configuration. M4A must document Docker's official Ubuntu apt repository method, Docker `data-root` policy, containerd persistent root policy, current `/var/lib/docker` and `/var/lib/containerd` state, and the checks required before actual installation.

## M4B Docker/containerd storage installation

Install and configure Docker only after M4A review, `/data` is mounted, and M3 root-disk guard passes. Docker root must be `/data/docker`; containerd persistent storage must be under `/data/containerd` or explicitly documented as safe. M4B must verify storage before any image pull or container run.

## M5A CUDA/NVIDIA compatibility research

Before any NVIDIA driver, CUDA Toolkit, PyTorch CUDA wheel, KTransformers GPU component, ik_llama CUDA build, or NVIDIA Container Toolkit installation, produce `reports/m5a-cuda-nvidia-compatibility.md` from official sources where possible. The report must inventory the GPUs, compute capability, Ubuntu/kernel versions, available Ubuntu and NVIDIA driver branches, CUDA Toolkit versions, CUDA minimum driver requirements, PyTorch CUDA wheel support, KTransformers and kt-kernel requirements, ik_llama CUDA build requirements, Docker/NVIDIA Container Toolkit requirements, and the exact verification tests for the chosen stack.

M5A must explicitly answer whether to use R580 LTS, R595 production, or another driver branch; whether host CUDA Toolkit should be installed; whether CUDA 12.8, CUDA 13.0, or another Toolkit should be used; which PyTorch CUDA wheel should be used; whether KTransformers supports Blackwell RTX PRO 6000 through wheels, source builds, or not yet; whether ik_llama compiles and runs for Blackwell compute capability; and what tests prove the selected stack works. Human approval of the selected version matrix is required before M5B, M6, M7 GPU build work, or any GPU backend installation. The first M5A execution report concludes `STOP` for installation until human review; the recommended next task is matrix review before any host driver installation.

## M5B NVIDIA host driver

Install the approved Ubuntu/NVIDIA host driver path after M5A passes and a VM checkpoint has been requested. Verify all expected GPUs with `nvidia-smi` before and after reboot.

## M6 NVIDIA Container Toolkit

Install and configure the approved NVIDIA Container Toolkit path after M5A and M5B pass. Verify `docker run --gpus all ... nvidia-smi` works while Docker storage remains on `/data`.

## M7 backend runtime abstraction

Add runtime environment examples, backend profiles, and common start/stop/status/benchmark scripts for KTransformers and ik_llama.

## M8 small model API smoke service

Select a small open model, download only to `/data/models`, start a localhost backend, expose OpenAI-compatible chat completions, test auth, streaming, health, logs, restart, and reboot behavior.

## M9 fast technical/coding model

Deploy and benchmark Qwen/Qwen3.6-35B-A3B through the API, recording throughput, context stability, RAM, VRAM, startup time, and failure modes.

## M10 larger model benchmarks

Benchmark Qwen/Qwen3.5-122B-A10B, Qwen/Qwen3.5-397B-A17B, and zai-org/GLM-5.2 one model at a time, with storage and memory estimates before downloads.

## M11 authenticated API exposure

Choose LAN-only, VPN-only, or public TLS exposure. Keep backends local by default, require API keys, configure firewall policy, and verify unauthorized access fails.

## M12 observability and operations

Add health scripts, model memory reports, log rotation, restart policies, backup/restore docs for configs and secrets, upgrade procedure, and troubleshooting docs.
