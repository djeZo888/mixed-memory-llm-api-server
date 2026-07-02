# M5A - CUDA/NVIDIA Compatibility Research

- Milestone ID: M5A
- Milestone name: CUDA/NVIDIA compatibility research
- Timestamp: 2026-07-02T21:19:03+00:00
- Hostname: llmserver
- User: user
- Branch: milestone/m5a-cuda-nvidia-compatibility-research
- Base commit before M5A branch: eade4c4939d1da7e61fe091e36301c0272db20dd
- Research mode: read-only inventory and documentation only
- Conclusion: STOP for GPU/CUDA/backend installation until human review approves the selected matrix and M5B starts explicitly.

## Safety Confirmation

No packages, NVIDIA drivers, CUDA Toolkit, PyTorch wheels, KTransformers components, ik_llama builds, NVIDIA Container Toolkit packages, models, inference backends, API exposure, disks, fstab, mountpoints, partitioning, systemd services, history rewrites, or force-pushes were installed or configured during M5A.

## Stale Branch Cleanup Result

Only the two requested stale branches were inspected and deleted.

| Branch | Before cleanup | Cleanup action | After cleanup |
| --- | --- | --- | --- |
| `milestone/m4b-docker-containerd-install` | Present at `4ac53dd390f61b923fb8d4c5db30212a75c51d69` | `git push origin --delete milestone/m4b-docker-containerd-install`; matching local branch deleted if present | Deleted remotely and locally |
| `test/git-attribution-fix` | Present at `6a11e2649ceacbd3ad82663dbef3bb5b4b8242f9` | `git push origin --delete test/git-attribution-fix`; matching local branch deleted if present | Deleted remotely and locally |

No other local or remote branch was deleted. `main` was not deleted. History was not rewritten and no force-push was used.

## Local System Inventory

| Item | Value |
| --- | --- |
| Hostname | `llmserver` |
| User | `user` |
| OS | Ubuntu 24.04.4 LTS, Noble |
| Kernel | `Linux llmserver 6.8.0-134-generic #134-Ubuntu SMP PREEMPT_DYNAMIC Fri Jun 26 18:43:11 UTC 2026 x86_64` |
| Docker | Docker Engine Community `29.6.1` |
| containerd | `v2.2.5` through Docker, git commit `e53c7c1516c3b2bff98eb76f1f4117477e6f4e66` |
| Docker storage driver | `overlayfs`, `io.containerd.snapshotter.v1` |
| Docker Root Dir | `/data/docker` |
| containerd root | `/data/containerd/root` |
| containerd state | `/run/containerd` |
| `nvidia-smi` | not installed / not in PATH |
| `nvcc` | not installed / not in PATH |
| Loaded GPU-related modules | `nouveau` loaded; no proprietary `nvidia` module loaded |
| `/data` guard | PASS |
| root-disk guard | PASS |
| Docker/containerd storage verifier | PASS |

## Detected GPU Inventory From VM

Read-only PCI inventory currently sees two NVIDIA display functions, both with the same PCI device and subsystem IDs. The host does not yet have an NVIDIA proprietary driver, so marketing names, VRAM totals, driver version, MIG state, and compute capability cannot be confirmed with `nvidia-smi` yet.

```console
00:01.0 VGA compatible controller [0300]: Device [1234:1111] (rev 02)
01:00.0 VGA compatible controller [0300]: NVIDIA Corporation Device [10de:2bb1] (rev a1)
01:00.1 Audio device [0403]: NVIDIA Corporation Device [10de:22e8] (rev a1)
02:00.0 VGA compatible controller [0300]: NVIDIA Corporation Device [10de:2bb1] (rev a1)
02:00.1 Audio device [0403]: NVIDIA Corporation Device [10de:22e8] (rev a1)
```

`lspci -nnk -d 10de:` reported `Kernel modules: nvidiafb, nouveau` for both `10de:2bb1` display devices and `snd_hda_intel` for both audio functions. It did not report a proprietary NVIDIA kernel driver in use.

## Expected GPU Inventory If Passthrough Devices Are Visible

The project research target includes RTX PRO 6000 Blackwell Workstation class hardware and RTX 6000 Ada class compatibility. The current VM PCI output shows two identical NVIDIA `10de:2bb1` display devices and does not show a separately identifiable RTX 6000 Ada device. Treat the following as expected compatibility targets, not confirmed installed names, until `nvidia-smi -L` and `nvidia-smi --query-gpu=name,driver_version,memory.total,compute_cap --format=csv` pass after M5B.

| Expected GPU | Expected architecture | Compute capability | Source status |
| --- | --- | ---: | --- |
| NVIDIA RTX PRO 6000 Blackwell Workstation Edition | Blackwell | 12.0 | NVIDIA CUDA GPU compute capability table lists this GPU under compute capability 12.0. |
| NVIDIA RTX 6000 Ada | Ada Lovelace | 8.9 | NVIDIA CUDA GPU compute capability table lists this GPU under compute capability 8.9. |

## Official Sources Consulted

Access date for web sources: 2026-07-02.

| Topic | Source |
| --- | --- |
| CUDA GPU compute capability | https://developer.nvidia.com/cuda/gpus |
| CUDA Toolkit current release notes and minimum driver tables | https://docs.nvidia.com/cuda/cuda-toolkit-release-notes/index.html |
| CUDA 12.8 release notes and Blackwell compiler support | https://docs.nvidia.com/cuda/archive/12.8.0/cuda-toolkit-release-notes/index.html |
| CUDA minor-version compatibility | https://docs.nvidia.com/deploy/cuda-compatibility/minor-version-compatibility.html |
| CUDA forward compatibility | https://docs.nvidia.com/deploy/cuda-compatibility/forward-compatibility.html |
| NVIDIA driver lifecycle and branch matrix | https://docs.nvidia.com/datacenter/tesla/drivers/latest/driver-lifecycle.html and https://docs.nvidia.com/datacenter/tesla/drivers/latest/supported-drivers-and-cuda-toolkit-versions.html |
| CUDA Toolkit, driver, and architecture matrix | https://docs.nvidia.com/datacenter/tesla/drivers/latest/cuda-toolkit-driver-and-architecture-matrix.html |
| PyTorch install/version docs | https://pytorch.org/get-started/locally/ and https://pytorch.org/get-started/previous-versions/ |
| KTransformers / kt-kernel | https://github.com/kvcache-ai/ktransformers and https://raw.githubusercontent.com/kvcache-ai/ktransformers/main/kt-kernel/README.md |
| ik_llama | https://github.com/ikawrakow/ik_llama.cpp and https://raw.githubusercontent.com/ikawrakow/ik_llama.cpp/main/docs/build.md |
| NVIDIA Container Toolkit | https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html and https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/docker-specialized.html |

## Compute Capability Table

| GPU / architecture | Compute capability | Practical meaning for this project |
| --- | ---: | --- |
| RTX PRO 6000 Blackwell Workstation Edition | 12.0 | Requires backend/kernel support for `sm_120`; CUDA 12.8 release notes added compiler support for SM_120. |
| RTX 6000 Ada | 8.9 | Supported by current KTransformers kt-kernel prebuilt GPU matrix and by CUDA 11.8+ era software. |
| Blackwell architecture in NVIDIA data-center architecture matrix | 10.0 and 12.0 | Blackwell support is ongoing, but the exact workstation Blackwell target here is `sm_120`. |

## Local Ubuntu Driver Availability

Read-only `apt-cache policy` and `ubuntu-drivers devices` were run without installing anything.

| Package | Candidate observed |
| --- | --- |
| `nvidia-driver-570` | `570.211.01-0ubuntu1.24.04.1` |
| `nvidia-driver-575` | `575.64.03-0ubuntu0.24.04.3` |
| `nvidia-driver-580` | `580.159.03-0ubuntu0.24.04.1` |
| `nvidia-driver-590` | `590.48.01-0ubuntu0.24.04.5` |
| `nvidia-driver-595` | `595.71.05-0ubuntu0.24.04.1` |

`ubuntu-drivers devices` recognized modalias `pci:v000010DEd00002BB1sv000010DEsd0000204Bbc03sc00i00` and marked `nvidia-driver-595-open` as recommended. It also listed R580 server/open, R580, R595 server/open, and nouveau choices.

## Driver Branch Comparison

| Branch | NVIDIA lifecycle status | CUDA major without forward-compat package | Local Ubuntu relevance | Decision | Risk |
| --- | --- | --- | --- | --- | --- |
| R580 | Long Term Support Branch, EOL June 2028 | CUDA 13 | Available locally as `nvidia-driver-580` and server/open variants | Good LTS fallback, but not the local resolver recommendation for `10de:2bb1` | May be less aligned with Ubuntu's exact device recommendation for this workstation Blackwell ID. |
| R595 | Production Branch, EOL March 2027 | CUDA 13 | Available locally as `nvidia-driver-595`; `nvidia-driver-595-open` is recommended by `ubuntu-drivers devices` for the detected PCI ID | Recommended M5B candidate for host-driver-first validation | Shorter support window than R580; must be human-approved. |
| R610 | New Feature Branch, EOL August 2026 | CUDA 13 | Not observed in local apt-cache command | Avoid for first install | New feature branch, shorter lifecycle, not locally exposed by checked packages. |

Recommendation: use Ubuntu's recommended `nvidia-driver-595-open` branch for the M5B host-driver-only trial if the human approves. Keep R580 LTS as the documented fallback if the human prioritizes LTS and confirms it binds the RTX PRO Blackwell device cleanly. Do not use R610 for the first install.

## CUDA Toolkit Comparison

| Toolkit family | NVIDIA source fact | Decision |
| --- | --- | --- |
| CUDA 12.8 | CUDA 12.8 release notes add compiler support for Blackwell SM_100, SM_101, and SM_120. CUDA 12.8 GA corresponds to Linux driver >=570.26 in the release notes. | Preferred toolkit family if a host compiler is later required for native Blackwell builds. |
| CUDA 13.x | Current CUDA release notes show CUDA 13.3 Update 1 and a CUDA 13.x minor compatibility driver floor of >=580. Per-release toolkit driver rows go higher for 13.1, 13.2, and 13.3. | Do not use as the first host toolkit unless a backend explicitly requires it. CUDA 13.0/13.x can be revisited after host driver and backend source support are proven. |
| No host toolkit | PyTorch wheels and some prebuilt components can carry runtime libraries; NVIDIA Container Toolkit can run CUDA containers after the host driver is installed. | Recommended for M5B: install host driver only first. Host CUDA Toolkit should wait until M7/backend build strategy is approved. |

## PyTorch Wheel Compatibility

PyTorch's official install selector lists CUDA 12.8 among current Linux pip compute platforms. The previous versions matrix also lists CUDA 12.8 and CUDA 13.0 wheel families for recent releases such as 2.9.x, 2.10.x, and 2.11.x.

Recommendation: use the `cu128` PyTorch wheel family first when PyTorch installation is later approved. CUDA 12.8 is the first toolkit release explicitly adding SM_120 compiler support in NVIDIA release notes and avoids making CUDA 13.x the first variable. Use `cu130` only if a selected backend requires it and the chosen host driver branch is validated against that wheel family.

## KTransformers Compatibility

KTransformers remains a strategic target for large MoE, CPU/GPU heterogeneous inference, and Hugging Face-format model workflows. However, its current kt-kernel README says the prebuilt wheel GPU acceleration supports SM 80, 86, 89, and 90, with examples for Ampere, Ada, and Hopper. It does not list SM 120 or RTX PRO 6000 Blackwell Workstation in the prebuilt wheel matrix.

kt-kernel source metadata shows a CUDA build path controlled by `CPUINFER_USE_CUDA`, `CPUINFER_CUDA_ARCHS`, and CMake arguments, and notes that it no longer sets `CMAKE_CUDA_ARCHITECTURES` by default. That means a source build might be possible for SM_120 with a suitable CUDA Toolkit, but upstream documentation does not prove it.

Conclusion: KTransformers prebuilt wheels do not currently prove Blackwell RTX PRO 6000 support. KTransformers source build support for SM_120 is possible but unproven. Do not install KTransformers GPU components or rely on KTransformers GPU acceleration until an M7 backend build task compiles and smoke-tests it after M5B/M6.

## ik_llama Compatibility

The ik_llama repository states that the fully functional and performant compute backends are CPU and CUDA, and says CUDA is for Turing or newer NVIDIA GPUs. Its build documentation requires NVIDIA drivers and CUDA Toolkit for CUDA builds, and shows `cmake -B build -DGGML_CUDA=ON` for CUDA. The docs do not explicitly list Blackwell SM_120, but Turing-or-newer wording plus CMake CUDA architecture selection suggests Blackwell should be buildable with a CUDA Toolkit that supports SM_120.

Conclusion: ik_llama appears buildable for Blackwell in principle, but M5A did not compile it and upstream docs do not explicitly prove SM_120. Treat ik_llama CUDA on RTX PRO 6000 Blackwell as plausible but unverified until a later build task uses CUDA 12.8+ and records the exact `CMAKE_CUDA_ARCHITECTURES=120` or equivalent behavior.

## NVIDIA Container Toolkit Compatibility

NVIDIA Container Toolkit requires the NVIDIA GPU driver to be installed first. Its Docker configuration path uses `nvidia-ctk runtime configure --runtime=docker`, which modifies `/etc/docker/daemon.json`, followed by a Docker daemon restart. That is intentionally out of scope for M5A and must wait for M6.

M6 must preserve the existing M4B Docker storage policy. After toolkit configuration, Docker Root Dir must remain `/data/docker`, containerd persistent root must remain `/data/containerd/root`, and `docker run --rm --gpus all ... nvidia-smi` must pass.

## Docker/Containerd Status

| Check | Result |
| --- | --- |
| `scripts/common/require-data-mounted.sh` | PASS |
| `scripts/common/root-disk-guard.sh --report reports/m3-root-disk-guard.md` | PASS |
| `scripts/docker/verify-docker-storage.sh` | PASS |
| Docker Root Dir | `/data/docker` |
| Docker storage driver | `overlayfs` |
| containerd configured root | `/data/containerd/root` |
| containerd configured state | `/run/containerd` |

## Exact Risks And Uncertainties

- `nvidia-smi` is unavailable before M5B, so exact marketing names, VRAM totals, and compute capabilities are not yet confirmed from the host driver.
- Current PCI inventory shows two identical NVIDIA `10de:2bb1` display devices and no separately named RTX 6000 Ada device.
- `nouveau` is loaded. M5B must account for proprietary/open NVIDIA driver module handling through the Ubuntu package path, not ad hoc module changes in M5A.
- NVIDIA's lifecycle source favors R580 for long support, while local Ubuntu device resolution recommends R595-open for the exact detected `10de:2bb1` modalias.
- CUDA 13.x is current, but CUDA 12.8 is the first release note explicitly adding SM_120 compiler support and is the lower-change first toolkit choice if native builds become necessary.
- KTransformers kt-kernel prebuilt wheels do not list SM_120. Blackwell source-build support is unproven.
- ik_llama CUDA support likely covers Blackwell through Turing-or-newer CUDA support plus CUDA 12.8+ compiler support, but this remains unproven without a build and smoke test.

## Recommended Version Matrix

| Layer | Candidate | Source | Decision | Rationale | Risk |
| --- | --- | --- | --- | --- | --- |
| NVIDIA driver branch | R595 production, Ubuntu `nvidia-driver-595-open` | Ubuntu `ubuntu-drivers devices`; NVIDIA driver lifecycle docs | Recommended for M5B human review | Local resolver recommends it for `10de:2bb1`; production branch supports CUDA 13 major | Shorter lifecycle than R580; requires human approval and post-reboot validation. |
| NVIDIA driver fallback | R580 LTS | NVIDIA driver lifecycle docs; local apt candidates | Documented fallback | Longer EOL and CUDA 13 major support | Not the local recommended device package in this inventory. |
| Host CUDA Toolkit | None for M5B | CUDA docs, PyTorch docs, Container Toolkit docs | Do not install in M5B | Driver-only first reduces variables and is enough to prove PCI/device/driver readiness | Native backend builds later need a toolkit or build container. |
| Host CUDA Toolkit if needed later | CUDA 12.8 | CUDA 12.8 release notes | Preferred first native build toolkit | Explicit SM_120 compiler support | Later backend docs may require CUDA 13.x. |
| PyTorch wheel | `cu128` | PyTorch install selector / previous version matrix | Recommended first PyTorch GPU wheel family after approval | Aligns with CUDA 12.8 Blackwell compiler support and avoids CUDA 13.x as first runtime variable | Backend packages may pin a specific torch version. |
| KTransformers / kt-kernel | Source build only after M5B/M6; do not use prebuilt for Blackwell | kt-kernel README and setup metadata | Blocked for Blackwell until build proof | Prebuilt wheel matrix stops at SM 90 | SM_120 support unknown. |
| ik_llama CUDA | Source build after driver/toolkit approval | ik_llama README/build docs | Plausible but unverified | CUDA backend is documented as Turing or newer; Blackwell is newer, CUDA 12.8 supports SM_120 | No M5A build proof. |
| NVIDIA Container Toolkit | Install only in M6 after host `nvidia-smi` passes | NVIDIA Container Toolkit docs | Defer | Toolkit configuration mutates Docker daemon config and restarts Docker | Must preserve `/data/docker` and `/data/containerd/root`. |

## Required Recommendation Answers

- Recommended NVIDIA driver branch: R595 production via Ubuntu `nvidia-driver-595-open`, pending human approval; R580 LTS remains the documented fallback.
- Recommended CUDA Toolkit version, if host toolkit is needed: CUDA 12.8 first, because NVIDIA 12.8 release notes explicitly add SM_120 compiler support.
- Whether host CUDA Toolkit should be installed at all: no for M5B; install only the host driver first.
- Recommended PyTorch CUDA wheel family: `cu128` first after PyTorch installation is approved.
- Whether KTransformers should use prebuilt wheels or source build: do not use prebuilt wheels for Blackwell; source build must be tested later if KTransformers is selected.
- Whether KTransformers appears to support Blackwell RTX PRO 6000: not proven. Prebuilt kt-kernel wheels list SM 80/86/89/90, not SM_120.
- Whether ik_llama appears buildable for Blackwell: plausible but unproven. Requires CUDA Toolkit 12.8+ and an explicit later build/smoke test.
- Whether M5B should install only host driver first: yes.
- Whether M6 should install NVIDIA Container Toolkit only after host `nvidia-smi` passes: yes.
- What tests prove success: the tests listed below under M5B/M6/M7 verification.

## Install Strategy Recommendation

1. Human reviews this M5A matrix.
2. If approved, M5B installs only the selected Ubuntu NVIDIA host driver branch, with a VM checkpoint requested before installation.
3. M5B does not install CUDA Toolkit, PyTorch, KTransformers, ik_llama, NVIDIA Container Toolkit, models, or API services.
4. M5B validates both GPUs with `nvidia-smi` before and after reboot.
5. M6 installs and configures NVIDIA Container Toolkit only after M5B passes and must re-verify Docker Root Dir `/data/docker`.
6. M7 chooses backend build strategy. Prefer Docker build containers with source and build output under `/data/build` unless a native host build has a documented advantage.

## Verification Tests Required For M5B/M6/M7

M5B host-driver tests:

```bash
scripts/common/require-data-mounted.sh
scripts/common/root-disk-guard.sh
lspci -nn | egrep -i 'nvidia|vga|3d|display' || true
lsmod | egrep 'nvidia|nouveau|vfio' || true
nvidia-smi
nvidia-smi -L
nvidia-smi --query-gpu=name,driver_version,memory.total,compute_cap --format=csv
sudo -n reboot
nvidia-smi
nvidia-smi -L
nvidia-smi --query-gpu=name,driver_version,memory.total,compute_cap --format=csv
scripts/common/root-disk-guard.sh
```

M6 NVIDIA Container Toolkit tests:

```bash
scripts/common/require-data-mounted.sh
scripts/common/root-disk-guard.sh
scripts/docker/verify-docker-storage.sh
sudo -n docker info | egrep 'Docker Root Dir|Storage Driver|containerd|Runtimes'
sudo -n docker run --rm --gpus all nvidia/cuda:12.8.1-base-ubuntu24.04 nvidia-smi
scripts/docker/verify-docker-storage.sh
scripts/common/root-disk-guard.sh
```

M7 backend tests after explicit approval:

```bash
# PyTorch GPU smoke after approved install only
python3 - <<'PY'
import torch
print(torch.__version__)
print(torch.version.cuda)
print(torch.cuda.is_available())
print(torch.cuda.get_device_name(0))
print(torch.zeros(1, device="cuda"))
PY

# CUDA compiler smoke only if host CUDA Toolkit is intentionally installed
nvcc --version
# Compile and run a tiny deviceQuery or vector-add sample targeting sm_120.

# ik_llama after source build only
cmake -B /data/build/ik_llama -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=120
cmake --build /data/build/ik_llama --config Release -j$(nproc)
/data/build/ik_llama/bin/llama-cli --help

# KTransformers/kt-kernel after source build only
# Build with explicit SM_120 architecture handling, then verify kt-kernel imports and CUDA path.
```

## Checks Run

- `git fetch origin --prune`
- `git checkout main`
- `git pull --ff-only origin main`
- Git identity checks for repo and global `user.name` / `user.email`
- M4B handoff file and content checks
- `git ls-remote --heads origin main`
- Stale branch inspect/delete/verify commands for the two requested branches
- `git checkout -B milestone/m5a-cuda-nvidia-compatibility-research`
- `scripts/common/require-data-mounted.sh`
- `scripts/common/root-disk-guard.sh --report reports/m3-root-disk-guard.md`
- `scripts/docker/verify-docker-storage.sh`
- Read-only inventory commands listed in the task
- `apt-cache policy` for NVIDIA driver package candidates
- `ubuntu-drivers devices || true`
- Official-source web research listed above
- `git diff --check`
- Grep-based secret scan

The grep-based secret scan matched only intentional documentation, safety rules, examples, and scan pattern text. No real secrets, tokens, passwords, private keys, auth files, real `.env` files, `MEMORY.md`, or local Codex memory files were found.

## PASS/STOP Conclusion

STOP for installation. The branch cleanup and M5A research report are complete, but the VM must not proceed to NVIDIA/CUDA/backend installation automatically. Human review is required before M5B. The recommended next install milestone, if approved, is host-driver-only M5B using Ubuntu `nvidia-driver-595-open`, followed by `nvidia-smi` validation. KTransformers Blackwell GPU support remains unproven and must stay blocked until a later source-build smoke test proves SM_120 support.
