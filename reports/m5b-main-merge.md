# M5B Main Merge And GPU Driver State

- Timestamp: 2026-07-03T08:34:06+00:00
- Source branch: `milestone/m5b-nvidia-host-driver`
- Target branch: `main`
- Merge commit hash: `b8aa4ae902a3f13c56ffc437c08a4a319be1a66f`
- M5B source branch latest commit hash: `25e3ea2c654b46c27ff7ec7439364a001aa85757`
- M5B result: PASS

## Driver And GPU State

- Installed driver packages: `nvidia-driver-595-open` / `nvidia-utils-595` through Ubuntu apt packages only.
- NVIDIA driver version from `nvidia-smi`: `595.71.05`.
- GPU count: 2.
- GPU 0: NVIDIA RTX PRO 6000 Blackwell Workstation Edition, PCI `00000000:01:00.0`, memory `97887 MiB`.
- GPU 1: NVIDIA RTX PRO 6000 Blackwell Workstation Edition, PCI `00000000:02:00.0`, memory `97887 MiB`.
- No RTX 6000 Ada is expected or reported.
- `nouveau`: not loaded and not bound to the GPUs.
- `nvcc`: absent.
- CUDA Toolkit: absent.
- NVIDIA Container Toolkit: absent.
- PyTorch, KTransformers, ik_llama, models, Docker NVIDIA runtime, Docker/containerd configuration, and API exposure: not installed or configured by M5B.

## Storage And Guard State

- `/data` guard: PASS.
- Root-disk guard: PASS.
- Docker storage verifier: PASS.
- Docker Root Dir remains `/data/docker`.
- containerd root remains `/data/containerd/root`.
- containerd state remains `/run/containerd`.

## Human Proxmox Passthrough Review Summary

Codex did not access the Proxmox host. This section records the human-supplied host review.

- VM 120 config includes `hostpci0: 0000:c1:00,pcie=1,rombar=1` and `hostpci1: 0000:e1:00,pcie=1,rombar=1`.
- Snapshot parent noted by human review: `before-m5b-nvidia-driver-595-open`.
- `qm status 120`: running.
- Host logs show VFIO reset activity during VM stop/start/reboot, with reset-done lines.
- Host logs show correctable PCIe AER Data Link Layer events around GPU reset/start activity, especially on root port `0000:e0:01.1`.
- Correctable AER warning policy: not a blocker for M6, but monitor after M6/M7 and later GPU load tests.
- Host logs still show QEMU Guest Agent guest-ping timeouts.
- QGA follow-up policy: not a GPU-driver blocker, but repair as M5C before M6.
- Prior logs showed live snapshot failure with `VFIO migration is not supported in kernel`.
- VFIO snapshot policy: avoid live snapshots with VFIO GPUs; use stopped/offline snapshots unless live snapshots are explicitly tested and approved.

## Checks Run

- Git identity verification for repo/global `user.name` and `user.email`.
- `git fetch origin`.
- `git checkout milestone/m5b-nvidia-host-driver`.
- `git pull --ff-only origin milestone/m5b-nvidia-host-driver`.
- `scripts/common/require-data-mounted.sh`.
- `scripts/common/root-disk-guard.sh --report reports/m3-root-disk-guard.md`.
- `scripts/docker/verify-docker-storage.sh` with report output routed to M5B/M5B-merge reports.
- `nvidia-smi`.
- `nvidia-smi -L`.
- `nvidia-smi --query-gpu=index,name,pci.bus_id,driver_version,memory.total,power.limit --format=csv`.
- `command -v nvcc || true`.
- `dpkg -l | egrep 'nvidia|cuda|container-toolkit' || true`.
- `git diff --check`.
- Grep-based secret scan.
- `git checkout main`.
- `git pull --ff-only origin main`.
- `git merge --no-ff milestone/m5b-nvidia-host-driver -m "merge M5B NVIDIA host driver"`.
- Merge commit attribution verification.
- `git push origin main`.

## Secret Scan Result

The grep-based secret scan matched only intentional documentation, safety rules, sanitizer/static-test code, previous report text, and scan pattern text. No real secrets, tokens, passwords, private keys, auth files, real `.env` files, `MEMORY.md`, or local Codex memory files were identified.

## Safety Confirmation

No packages, NVIDIA/CUDA changes beyond the already-completed M5B driver install, NVIDIA Container Toolkit, PyTorch, KTransformers, ik_llama, models, Docker NVIDIA runtime configuration, Docker/containerd configuration, disks, fstab, mountpoints, partitioning, inference backend configuration, API exposure, history rewrite, force-push, branch deletion, or Proxmox host access were performed during this documentation and merge task.

## Conclusion

PASS. M5B is merged into `main`. The next recommended task is M5C QEMU Guest Agent repair and Proxmox guest-operations verification before M6 NVIDIA Container Toolkit.
