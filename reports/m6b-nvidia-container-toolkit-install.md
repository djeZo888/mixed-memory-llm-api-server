# M6B - NVIDIA Container Toolkit Install

- Milestone ID: M6B
- Milestone name: NVIDIA Container Toolkit install and GPU-container verification
- Timestamp: 2026-07-03T16:20:09+00:00
- Branch: `milestone/m6b-nvidia-container-toolkit-install`
- Base branch: `main`
- Base commit: `bdc2544`
- Approved CUDA container test image: `nvidia/cuda:13.2.1-base-ubuntu24.04`

## Scope

M6B is limited to installing the NVIDIA Container Toolkit package set, configuring Docker's NVIDIA runtime, preserving Docker/containerd storage on `/data`, restarting Docker after configuration validation, running the approved GPU container `nvidia-smi` test, rebooting the guest, and verifying the same state after reboot.

Out of scope: CUDA Toolkit, `cuda`, `cuda-toolkit`, `cuda-drivers`, `nvidia-cuda-toolkit`, PyTorch, KTransformers, ik_llama, model downloads, API exposure, Docker group membership changes, Docker TCP socket exposure, containerd NVIDIA runtime configuration, `/etc/containerd/config.toml` modification, disk/fstab/mountpoint/partitioning changes, and Proxmox host access.

## Baseline Driver And GPU State

- NVIDIA driver version: `595.71.05`.
- `nvidia-smi` host CUDA compatibility display: `13.2`.
- GPU count: 2.
- GPU 0: NVIDIA RTX PRO 6000 Blackwell Workstation Edition, PCI `00000000:01:00.0`, memory `97887 MiB`, power limit `600.00 W`.
- GPU 1: NVIDIA RTX PRO 6000 Blackwell Workstation Edition, PCI `00000000:02:00.0`, memory `97887 MiB`, power limit `600.00 W`.

## Baseline Docker And Containerd State

- Docker: `29.6.1`.
- Docker Root Dir: `/data/docker`.
- Docker storage driver: `overlayfs`.
- Docker containerd snapshotter driver type: `io.containerd.snapshotter.v1`.
- containerd: `v2.2.5`.
- containerd root: `/data/containerd/root`.
- containerd state: `/run/containerd`.
- Docker Compose: `v5.3.0`.
- Docker Buildx: `v0.35.0`.
- `/data/docker`: `236K` before M6B install.
- `/data/containerd`: `336K` before M6B install.
- `/var/lib/docker`: absent or too small for `du` output.
- `/var/lib/containerd`: absent or too small for `du` output.

## Baseline Package And Tool State

- NVIDIA Container Toolkit packages: absent.
- `nvidia-ctk`: absent.
- CUDA Toolkit: absent.
- `nvcc`: absent.
- Installed NVIDIA packages: `nvidia-driver-595-open`, `nvidia-utils-595`.

## Baseline Checks

- `scripts/common/require-data-mounted.sh`: PASS.
- `scripts/common/root-disk-guard.sh --report reports/m3-root-disk-guard.md`: PASS.
- `scripts/docker/verify-docker-storage.sh`: PASS.
- `nvidia-smi`: PASS.
- `nvidia-smi -L`: PASS.
- `nvidia-smi --query-gpu=index,name,pci.bus_id,driver_version,memory.total,power.limit --format=csv`: PASS.
- `sudo -n docker info | egrep 'Docker Root Dir|Storage Driver|containerd' || true`: PASS.
- `sudo -n docker version`: PASS.
- `sudo -n docker compose version`: PASS.
- `sudo -n docker buildx version`: PASS.

## Installation Log Summary

- NVIDIA Container Toolkit apt repository was added with the NVIDIA official method from `https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list`.
- `sudo -n apt-get update`: PASS.
- `sudo -n apt-get -s install nvidia-container-toolkit nvidia-container-toolkit-base libnvidia-container-tools libnvidia-container1`: PASS.
- Apt simulation proposed only the four approved toolkit packages:
  - `libnvidia-container1`
  - `libnvidia-container-tools`
  - `nvidia-container-toolkit-base`
  - `nvidia-container-toolkit`
- No out-of-scope package names were proposed by the simulation.
- Installed package versions:
  - `libnvidia-container-tools 1.19.1-1`
  - `libnvidia-container1 1.19.1-1`
  - `nvidia-container-toolkit 1.19.1-1`
  - `nvidia-container-toolkit-base 1.19.1-1`
- Existing host driver packages remained:
  - `nvidia-driver-595-open 595.71.05-0ubuntu0.24.04.1`
  - `nvidia-utils-595 595.71.05-0ubuntu0.24.04.1`
- `nvidia-ctk`: `/usr/bin/nvidia-ctk`.
- `nvidia-ctk --version`: `NVIDIA Container Toolkit CLI version 1.19.1`.
- Docker daemon config backup: `/etc/docker/daemon.json.pre-m6b-nvidia-container-toolkit.20260703T162043Z.bak`.
- `sudo -n nvidia-ctk runtime configure --runtime=docker`: PASS.
- Docker daemon config after `nvidia-ctk`: valid JSON, preserved `"data-root": "/data/docker"`, and added `runtimes.nvidia.path = "nvidia-container-runtime"`.
- Docker TCP socket exposure check: PASS; no `tcp://`, `2375`, `2376`, or wildcard listener pattern found in Docker daemon/systemd config checks.
- `/etc/containerd/config.toml`: unchanged by the Docker-only M6B path; root remains `/data/containerd/root`, state remains `/run/containerd`.
- `sudo -n systemctl restart docker`: PASS.
- `sudo -n systemctl is-active docker`: `active`.
- `sudo -n systemctl is-active containerd`: `active`.
- Docker runtime summary after restart:
  - Runtimes: `io.containerd.runc.v2 nvidia runc`
  - Default Runtime: `runc`
  - Docker Root Dir: `/data/docker`

## GPU Container Verification

- Approved image used: `nvidia/cuda:13.2.1-base-ubuntu24.04`.
- `sudo -n docker run --rm --gpus all nvidia/cuda:13.2.1-base-ubuntu24.04 nvidia-smi`: PASS.
- Docker pulled digest `sha256:7be56e69d8ae7c3648b8fca009fa35980ecd9c6eefaafbff3ee8c224e0043eb5` for the approved image.
- Exact container GPU query:

```text
0, NVIDIA RTX PRO 6000 Blackwell Workstation Edition, 00000000:01:00.0, 595.71.05, 97887 MiB, 600.00 W
1, NVIDIA RTX PRO 6000 Blackwell Workstation Edition, 00000000:02:00.0, 595.71.05, 97887 MiB, 600.00 W
```

- Container GPU count/name/VRAM check: PASS.
- `sudo -n docker system df`: images `717MB`, containers `0B`, volumes `0B`, build cache `0B`.
- `sudo -n docker image ls`: `hello-world:latest` and `nvidia/cuda:13.2.1-base-ubuntu24.04`.
- `sudo -n docker container ls -a`: no containers.
- Post-test `/data/docker`: `236K`.
- Post-test `/data/containerd`: `685M`.
- `/var/lib/docker`: absent or too small for `du` output.
- `/var/lib/containerd`: absent or too small for `du` output.
- Post-test `scripts/docker/verify-docker-storage.sh`: PASS.
- Post-test `scripts/common/root-disk-guard.sh --report reports/m3-root-disk-guard.md`: PASS.

## Post-Reboot Verification

Pending.

## Pre-Reboot Checks And Commit Gate

- `bash -n scripts/nvidia/install-nvidia-container-toolkit.sh`: PASS.
- `bash -n scripts/nvidia/verify-gpu-containers.sh`: PASS.
- `bash -n tests/shell/test-nvidia-container-toolkit-static.sh`: PASS.
- `bash -n /data/services/m6b-post-reboot/m6b-post-reboot-verify.sh`: PASS.
- `tests/shell/test-nvidia-container-toolkit-static.sh`: PASS.
- `scripts/nvidia/verify-gpu-containers.sh`: PASS.
- `git diff --check`: PASS.
- Grep-based secret scan: matched only intentional documentation, sanitizer/static-test code, `.gitignore`/CI patterns, prior report text, and scan pattern text. No real secrets, tokens, passwords, private keys, auth files, real `.env` files, `MEMORY.md`, or local Codex memory files were identified.

## Conclusion

Pre-reboot PASS. Post-reboot verification is pending.
