# NVIDIA Container Toolkit Plan

This document defines the M6 Docker-only NVIDIA Container Toolkit path. The toolkit allows Docker containers to access the already-installed host NVIDIA driver and GPUs. It does not install the CUDA Toolkit on the host, install backend frameworks, download models, or expose an API.

## Current State

- Host GPUs: 2 x NVIDIA RTX PRO 6000 Blackwell Workstation Edition.
- Host NVIDIA driver: `595.71.05`.
- Host `nvidia-smi`: working; reports CUDA compatibility `13.2`.
- Docker: `29.6.1`.
- Docker Root Dir: `/data/docker`.
- containerd: `v2.2.5`.
- containerd root: `/data/containerd/root`.
- containerd state: `/run/containerd`.
- NVIDIA Container Toolkit: not installed.
- `nvidia-ctk`: absent.
- CUDA Toolkit and `nvcc`: absent.

## Prerequisites

Run these checks before any M6B install or configuration:

```bash
scripts/common/require-data-mounted.sh
scripts/common/root-disk-guard.sh
scripts/docker/verify-docker-storage.sh
nvidia-smi
sudo -n docker info | egrep 'Docker Root Dir|Storage Driver|containerd'
```

M6B must stop unless `/data` is mounted, the root-disk guard passes, Docker storage verifies, host `nvidia-smi` sees exactly two expected GPUs, Docker Root Dir is `/data/docker`, and containerd root/state remain `/data/containerd/root` and `/run/containerd`.

## Official Apt Repository Plan

Use the NVIDIA Container Toolkit apt instructions from NVIDIA documentation:

- Install the NVIDIA Container Toolkit apt signing key into `/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg`.
- Write `/etc/apt/sources.list.d/nvidia-container-toolkit.list` from `https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list`.
- Install only these packages:
  - `nvidia-container-toolkit`
  - `nvidia-container-toolkit-base`
  - `libnvidia-container-tools`
  - `libnvidia-container1`

Do not install host CUDA Toolkit packages in M6. Do not install PyTorch, KTransformers, ik_llama, models, or API services.

## Why M6A Is Dry-Run Only

M6A records the exact installation, configuration, verification, and rollback path before any host changes. It creates the future M6B scripts and runs only static checks, read-only system inventory, and script dry-runs. Actual apt repository creation, package installation, Docker runtime configuration, Docker restart, image pull, and `docker run --gpus all` are reserved for M6B after human review.

## Docker Runtime Configuration

For M6B, configure Docker with:

```bash
sudo nvidia-ctk runtime configure --runtime=docker
```

That command modifies `/etc/docker/daemon.json` so Docker can use the NVIDIA runtime. M6B must back up `/etc/docker/daemon.json` before running the command and must verify the file still contains:

```json
"data-root": "/data/docker"
```

Docker must be restarted after the configuration change because the daemon reads runtime configuration at startup:

```bash
sudo systemctl restart docker
```

The restart is allowed only in M6B after config verification and root-disk guard checks. M6A must not restart Docker.

## Storage Preservation Policy

Docker persistent storage must remain at `/data/docker`. M6B must verify this before configuration, after `nvidia-ctk runtime configure`, after Docker restart, and after the GPU container test.

containerd persistent root must remain `/data/containerd/root` and state must remain `/run/containerd`. M6 is Docker-only. Do not configure the containerd NVIDIA runtime and do not modify `/etc/containerd/config.toml` unless a later milestone explicitly reviews and approves that path.

Docker must not expose TCP sockets. M6B must check `/etc/docker/daemon.json` and Docker systemd units for `tcp://`, `2375`, `2376`, or wildcard listener patterns before and after runtime configuration.

## Proposed CUDA Test Image Policy

Use an explicit official NVIDIA CUDA image tag, never `latest`. M6A proposes:

```text
nvidia/cuda:13.2.1-base-ubuntu24.04
```

Rationale:

- It is an official `nvidia/cuda` tag listed by Docker Hub for linux/amd64. Source: `https://hub.docker.com/r/nvidia/cuda/tags` and Docker Hub tag API query `https://hub.docker.com/v2/repositories/nvidia/cuda/tags?page_size=100&name=13.2.1-base`.
- It is a base image, smaller than runtime/devel/cuDNN/TensorRT images, and sufficient for an `nvidia-smi` runtime smoke test.
- The VM host driver is `595.71.05`; NVIDIA CUDA release notes at `https://docs.nvidia.com/cuda/cuda-toolkit-release-notes/index.html` list CUDA 13.2 GA as requiring Linux driver `>=595.45.04` and CUDA 13.2 Update 1 as requiring `>=595.58.03`, so this driver is compatible with CUDA 13.2 images.

Do not pull or run this image in M6A.

## Verification Commands

M6A dry-run:

```bash
scripts/nvidia/install-nvidia-container-toolkit.sh --dry-run
scripts/nvidia/verify-gpu-containers.sh || true
```

Expected M6B install/configuration sequence after human approval:

```bash
scripts/common/require-data-mounted.sh
scripts/common/root-disk-guard.sh
scripts/docker/verify-docker-storage.sh
nvidia-smi
scripts/nvidia/install-nvidia-container-toolkit.sh --yes-install-nvidia-container-toolkit
```

Expected M6B GPU container test after installation and Docker restart:

```bash
scripts/nvidia/verify-gpu-containers.sh \
  --approved-cuda-test-image nvidia/cuda:13.2.1-base-ubuntu24.04 \
  --yes-run-cuda-test
```

The container test command inside that verifier is:

```bash
sudo docker run --rm --gpus all nvidia/cuda:13.2.1-base-ubuntu24.04 nvidia-smi
```

M6B must confirm the container sees exactly two GPUs matching the host GPU names and expected VRAM, and must rerun the root-disk guard afterward.

## Rollback Notes

If Docker runtime configuration fails or breaks storage policy in M6B:

1. Restore the `/etc/docker/daemon.json` backup made immediately before `nvidia-ctk runtime configure`.
2. Restart Docker.
3. Verify Docker Root Dir is `/data/docker`.
4. Verify containerd root/state remain `/data/containerd/root` and `/run/containerd`.
5. Rerun:

```bash
scripts/common/require-data-mounted.sh
scripts/common/root-disk-guard.sh
scripts/docker/verify-docker-storage.sh
```

Do not change disks, fstab, mountpoints, systemd storage policy, model storage, backend installs, or API exposure as part of M6 rollback.
