# M5A Main Merge And Pre-M5B Handoff

- Timestamp: 2026-07-03T01:11:08+00:00
- Source branch: `milestone/m5a-cuda-nvidia-compatibility-research`
- Target branch: `main`
- Merge commit hash: `3be1f1c564923b3249c9db8266362859d661102c`
- M5A source commit hash: `3b82f8ff3524b69815b42491edc4a5fbdbd170bd`
- M5A result: `STOP` for installation until human approval
- Conflicts: none

## Corrected GPU Inventory

Human review confirmed the expected VM hardware profile:

- Expected GPUs after driver installation: 2 x RTX PRO 6000 Blackwell Workstation Edition 96 GB.
- No RTX 6000 Ada is expected in this VM.
- Current pre-driver PCI inventory sees two NVIDIA display devices:
  - `01:00.0 VGA compatible controller [0300]: NVIDIA Corporation Device [10de:2bb1] (rev a1)`
  - `02:00.0 VGA compatible controller [0300]: NVIDIA Corporation Device [10de:2bb1] (rev a1)`
- Current related audio functions:
  - `01:00.1 Audio device [0403]: NVIDIA Corporation Device [10de:22e8] (rev a1)`
  - `02:00.1 Audio device [0403]: NVIDIA Corporation Device [10de:22e8] (rev a1)`
- `nvidia-smi` is absent.
- `nvcc` is absent.
- `nouveau` is loaded.

Because the NVIDIA driver is not installed, PCI visibility is not proof of exact GPU name, VRAM, driver binding, compute readiness, or passthrough reliability. M5B must prove those facts after driver installation and after reboot.

## Version Matrix Handoff

- Recommended driver branch: R595 production via Ubuntu `nvidia-driver-595-open`, pending human approval; R580 LTS remains the documented fallback.
- Recommended CUDA Toolkit approach: do not install host CUDA Toolkit in M5B. If a host toolkit is later needed for native builds, start with CUDA 12.8 unless a backend requirement changes that decision.
- PyTorch recommendation: use the `cu128` wheel family first after PyTorch installation is explicitly approved.
- KTransformers conclusion: Blackwell RTX PRO 6000 support is not proven by current prebuilt kt-kernel wheels; prebuilt kt-kernel lists SM 80/86/89/90, not SM_120. Keep GPU KTransformers blocked until source-build proof exists.
- ik_llama conclusion: CUDA support appears plausible for Blackwell with CUDA 12.8+ and explicit SM_120 build handling, but remains unverified until a later source-build smoke test.
- NVIDIA Container Toolkit conclusion: do not install until M6, and only after host `nvidia-smi` passes in M5B.

## Required M5B Tests

M5B must be host NVIDIA driver installation only unless the human explicitly expands scope. Required post-driver tests:

```bash
scripts/common/require-data-mounted.sh
scripts/common/root-disk-guard.sh
lspci -nnk | egrep -A4 -i 'nvidia|vga|3d|display'
lsmod | egrep 'nvidia|nouveau|vfio'
nvidia-smi
nvidia-smi -L
nvidia-smi --query-gpu=index,name,pci.bus_id,driver_version,memory.total,power.limit --format=csv
nvidia-smi topo -m
nvidia-smi -q -d MEMORY,PCI,POWER
scripts/docker/verify-docker-storage.sh
scripts/common/root-disk-guard.sh
sudo -n reboot
nvidia-smi
nvidia-smi -L
nvidia-smi --query-gpu=index,name,pci.bus_id,driver_version,memory.total,power.limit --format=csv
scripts/docker/verify-docker-storage.sh
scripts/common/root-disk-guard.sh
```

M5B must verify:

- Exactly two GPUs are visible.
- Each GPU name is RTX PRO 6000 Blackwell or the equivalent official driver name for RTX PRO 6000 Blackwell Workstation Edition.
- Each GPU reports about 96 GB VRAM.
- `nouveau` is not bound to either GPU after driver install.
- GPU PCI bus IDs match the passed-through VM devices.
- No GPU is missing after VM reboot.
- No persistent Xorg/display stack is required for compute use.
- Docker Root Dir remains `/data/docker`.
- containerd root remains `/data/containerd/root`.
- Root-disk guard passes before and after driver work.
- NVIDIA Container Toolkit is not installed until M6.

## Passthrough Validation Checks

The VM has passed-through Blackwell GPUs, and historical logs showed VFIO reset activity and correctable PCIe AER events. Do not assume passthrough is reliable only because `lspci` sees devices.

Manual Proxmox host checks after M5B:

```bash
journalctl -b -k | egrep -i 'vfio|nvidia|nouveau|pcie|aer|reset|120'
journalctl -b -p warning --no-pager | egrep -i 'vfio|pcie|aer|nvidia|nouveau|120'
qm config 120
qm status 120
```

Manual validation must confirm VM start/stop/reboot does not trigger unrecovered GPU reset failures. Do not use live snapshots with VFIO GPUs unless explicitly tested and supported. Codex did not access the Proxmox host during this merge task.

## Checks Run

- `git config --show-origin --get-regexp '^user\.(name|email)$' || true`
- `git config --global --show-origin --get-regexp '^user\.(name|email)$' || true`
- `git fetch origin`
- `git checkout milestone/m5a-cuda-nvidia-compatibility-research`
- `git pull --ff-only origin milestone/m5a-cuda-nvidia-compatibility-research`
- `scripts/common/require-data-mounted.sh`
- `scripts/common/root-disk-guard.sh --report reports/m3-root-disk-guard.md`
- `scripts/docker/verify-docker-storage.sh`
- `lspci -nn | egrep -i 'nvidia|vga|3d|display' || true`
- `lsmod | egrep 'nvidia|nouveau|vfio' || true`
- `command -v nvidia-smi || true`
- `command -v nvcc || true`
- `git diff --check`
- Grep-based secret scan
- `git checkout main`
- `git pull --ff-only origin main`
- `git merge --no-ff milestone/m5a-cuda-nvidia-compatibility-research -m "merge M5A CUDA NVIDIA compatibility research"`
- Merge commit attribution verification
- `git push origin main`
- Final root-disk guard refresh on `main`

## Secret Scan Result

The grep-based secret scan matched only intentional documentation, test, sanitizer, `.gitignore`, CI, and prior report strings. No real secrets, tokens, passwords, private keys, auth files, real `.env` files, `MEMORY.md`, or local Codex memory files were detected.

## Safety Confirmation

No packages, NVIDIA drivers, CUDA Toolkit, PyTorch wheels, KTransformers components, ik_llama builds, NVIDIA Container Toolkit packages, models, inference backends, API exposure, Docker/containerd configuration, disks, fstab, mountpoints, partitioning, systemd services, history rewrites, force-pushes, or branch deletions were performed during this merge and handoff task.

## Conclusion

PASS. Corrected M5A is merged into `main`, and the final pre-M5B handoff is recorded.

## Next Recommended Task

Start a fresh ChatGPT/Codex context before M5B host NVIDIA driver installation. M5B must remain host-driver-only unless the human explicitly approves additional scope.
