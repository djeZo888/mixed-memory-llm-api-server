# M6A - NVIDIA Container Toolkit Planning/Dry-Run

- Milestone ID: M6A
- Milestone name: NVIDIA Container Toolkit planning/dry-run
- Timestamp: 2026-07-03T09:35:51+00:00
- Branch: `milestone/m6a-nvidia-container-toolkit-plan`
- Base branch: `main`
- Base commit: `32e14fe update QGA status after M5B merge`
- Repo path: `/data/services/mixed-memory-llm-api-server`
- Result: PASS for planning/dry-run; STOP for actual install until human M6A review approves M6B.

## Scope

M6A is planning and dry-run only. No NVIDIA Container Toolkit package was installed, no NVIDIA apt repository was added, no `nvidia-ctk runtime configure` command was run, no Docker or containerd config was modified, no Docker/containerd daemon was restarted, no CUDA container image was pulled or run, no CUDA Toolkit or backend framework was installed, no model was downloaded, no API was exposed, no disk/fstab/mountpoint/systemd changes were made, and Codex did not access the Proxmox host.

## Current Driver And GPU State

`nvidia-smi` works on the host with NVIDIA driver `595.71.05` and reports CUDA compatibility `13.2`.

Host GPUs:

| Index | Name | PCI bus ID | Driver | VRAM | Power limit |
| ---: | --- | --- | --- | ---: | ---: |
| 0 | NVIDIA RTX PRO 6000 Blackwell Workstation Edition | `00000000:01:00.0` | `595.71.05` | `97887 MiB` | `600.00 W` |
| 1 | NVIDIA RTX PRO 6000 Blackwell Workstation Edition | `00000000:02:00.0` | `595.71.05` | `97887 MiB` | `600.00 W` |

## Docker And Containerd Storage State

- Docker: `29.6.1`
- Docker Root Dir: `/data/docker`
- Docker storage driver: `overlayfs`
- Docker containerd snapshotter driver type: `io.containerd.snapshotter.v1`
- containerd: `v2.2.5`
- containerd root: `/data/containerd/root`
- containerd state: `/run/containerd`
- Docker Compose: `v5.3.0`
- Docker Buildx: `v0.35.0`
- `/var/lib/docker`: absent or small enough that `du` reported no entry.
- `/var/lib/containerd`: absent or small enough that `du` reported no entry.
- `/data/docker`: `236K`
- `/data/containerd`: `336K`

Baseline storage checks:

- `scripts/common/require-data-mounted.sh`: PASS.
- `scripts/common/root-disk-guard.sh --report reports/m3-root-disk-guard.md`: PASS.
- `scripts/docker/verify-docker-storage.sh`: PASS.

## Current Package And Tool State

Installed NVIDIA/CUDA-related packages found by the baseline query:

```text
nvidia-driver-595-open 595.71.05-0ubuntu0.24.04.1
nvidia-utils-595 595.71.05-0ubuntu0.24.04.1
```

- NVIDIA Container Toolkit packages: absent.
- `nvidia-ctk`: absent.
- CUDA Toolkit: absent.
- `nvcc`: absent.

## Proposed Packages

Future M6B should install only the NVIDIA Container Toolkit package set documented by NVIDIA:

- `nvidia-container-toolkit`
- `nvidia-container-toolkit-base`
- `libnvidia-container-tools`
- `libnvidia-container1`

M6B must not install CUDA Toolkit, PyTorch, KTransformers, ik_llama, models, or API services.

## Proposed Apt Repository Configuration

Use NVIDIA's official apt repository method for Debian-derived distributions:

- Signing key URL: `https://nvidia.github.io/libnvidia-container/gpgkey`
- Keyring path: `/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg`
- Source list URL: `https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list`
- Source list path: `/etc/apt/sources.list.d/nvidia-container-toolkit.list`

M6A did not create the keyring or source list.

## Proposed M6B Runtime Configuration

After package installation in M6B:

```bash
sudo nvidia-ctk runtime configure --runtime=docker
```

This command modifies `/etc/docker/daemon.json`. M6B must back up `/etc/docker/daemon.json` before running it and verify afterward that the file still contains:

```json
"data-root": "/data/docker"
```

M6B must also verify Docker has no TCP socket exposure before and after the configuration.

Docker must be restarted after runtime configuration:

```bash
sudo systemctl restart docker
```

The restart is an M6B action only and must happen after config verification and root-disk guard checks.

## Storage Preservation Plan

Docker data-root must stay `/data/docker` before install, after `nvidia-ctk`, after Docker restart, and after the container test.

containerd root/state must stay `/data/containerd/root` and `/run/containerd`. M6 is Docker-only. Do not run `nvidia-ctk runtime configure --runtime=containerd`, do not restart containerd, and do not modify `/etc/containerd/config.toml` unless a later reviewed milestone explicitly authorizes containerd runtime work.

Run the root-disk guard before package work, before Docker restart, and after the GPU container test.

## Proposed CUDA Test Image Tag

Proposed explicit official NVIDIA CUDA image:

```text
nvidia/cuda:13.2.1-base-ubuntu24.04
```

Source and compatibility:

- Docker Hub `nvidia/cuda` tag metadata lists `13.2.1-base-ubuntu24.04` for linux/amd64; the amd64 compressed size is about `184406258` bytes. Source: `https://hub.docker.com/r/nvidia/cuda/tags` and Docker Hub tag API query `https://hub.docker.com/v2/repositories/nvidia/cuda/tags?page_size=100&name=13.2.1-base`.
- NVIDIA CUDA release notes at `https://docs.nvidia.com/cuda/cuda-toolkit-release-notes/index.html` list CUDA 13.x minor-version compatibility with driver branch `>= 580`.
- NVIDIA CUDA release notes list CUDA 13.2 GA as requiring Linux driver `>=595.45.04` and CUDA 13.2 Update 1 as requiring `>=595.58.03`; the host driver is `595.71.05`.

M6A did not pull or run this image. Do not use `nvidia/cuda:latest`.

Expected M6B test after human approval:

```bash
sudo docker run --rm --gpus all nvidia/cuda:13.2.1-base-ubuntu24.04 nvidia-smi
```

Expected M6B container checks:

- Container sees exactly two GPUs.
- GPU names match host: NVIDIA RTX PRO 6000 Blackwell Workstation Edition.
- VRAM matches host expectation around `97887 MiB` each.
- Docker Root Dir remains `/data/docker`.
- containerd root/state remain `/data/containerd/root` and `/run/containerd`.
- `/var/lib/docker` and `/var/lib/containerd` remain absent/empty/small.
- Root-disk guard passes after the container test.

## Rollback Plan

If M6B Docker runtime configuration fails:

1. Restore the pre-configuration `/etc/docker/daemon.json` backup.
2. Restart Docker.
3. Verify Docker Root Dir is `/data/docker`.
4. Verify containerd root/state are `/data/containerd/root` and `/run/containerd`.
5. Run:

```bash
scripts/common/require-data-mounted.sh
scripts/common/root-disk-guard.sh
scripts/docker/verify-docker-storage.sh
```

Rollback must not change disks, fstab, mountpoints, containerd storage policy, models, backend installs, or API exposure.

## Checks Run

- `git fetch origin`
- `git checkout main`
- `git pull --ff-only origin main`
- `git checkout -B milestone/m6a-nvidia-container-toolkit-plan`
- Git identity verification for `CodexAIagent <133749519+djeZo888@users.noreply.github.com>`
- `scripts/common/require-data-mounted.sh`
- `scripts/common/root-disk-guard.sh --report reports/m3-root-disk-guard.md`
- `scripts/docker/verify-docker-storage.sh`
- `nvidia-smi`
- `nvidia-smi -L`
- `nvidia-smi --query-gpu=index,name,pci.bus_id,driver_version,memory.total,power.limit --format=csv`
- `sudo -n docker info | egrep 'Docker Root Dir|Storage Driver|containerd' || true`
- `sudo -n docker version`
- `sudo -n docker compose version`
- `sudo -n docker buildx version`
- `dpkg -l | egrep 'nvidia-container|libnvidia-container|cuda|nvidia-driver|nvidia-utils' || true`
- `command -v nvidia-ctk || true`
- `command -v nvcc || true`
- `nvcc --version || true`
- `sudo -n du -sh /var/lib/docker /var/lib/containerd /data/docker /data/containerd /data/containerd/root 2>/dev/null || true`
- Docker Hub tag metadata lookup for `nvidia/cuda:13.2.1-base-ubuntu24.04` without pulling the image.
- NVIDIA CUDA release notes review for CUDA 13.2 driver compatibility.
- `chmod +x scripts/nvidia/install-nvidia-container-toolkit.sh`
- `chmod +x scripts/nvidia/verify-gpu-containers.sh`
- `chmod +x tests/shell/test-nvidia-container-toolkit-static.sh`
- `bash -n scripts/nvidia/install-nvidia-container-toolkit.sh`
- `bash -n scripts/nvidia/verify-gpu-containers.sh`
- `bash -n tests/shell/test-nvidia-container-toolkit-static.sh`
- `tests/shell/test-nvidia-container-toolkit-static.sh`: PASS.
- `scripts/nvidia/install-nvidia-container-toolkit.sh --dry-run`: PASS; printed plan only.
- `scripts/nvidia/verify-gpu-containers.sh || true`: expected M6A STOP because NVIDIA Container Toolkit packages are not installed.
- Final `scripts/common/require-data-mounted.sh`: PASS.
- Final `scripts/common/root-disk-guard.sh --report reports/m3-root-disk-guard.md`: PASS.
- Final `scripts/docker/verify-docker-storage.sh`: PASS.
- `git diff --check`: PASS.
- Grep-based secret scan: matched only intentional documentation, sanitizer/static-test code, `.gitignore`/CI patterns, prior report text, and scan pattern text. No real secrets, tokens, private keys, auth files, real `.env` files, `MEMORY.md`, or local Codex memory files were identified.

## Human Review Correction

Human review correction: use nvidia/cuda:13.2.1-base-ubuntu24.04 instead of 13.2.0-base-ubuntu24.04. CUDA 13.2 Update 1 is compatible with driver 595.71.05; CUDA 13.3 images are not selected because CUDA 13.3 requires the 610 driver branch. Do not use nvidia/cuda:latest.

## Conclusion

PASS for M6A planning and dry-run. Actual NVIDIA Container Toolkit installation, Docker runtime configuration, Docker restart, image pull, and GPU container test remain blocked until human review approves M6B.

Next task: M6B actual NVIDIA Container Toolkit install after human review.
