# CUDA/NVIDIA Compatibility Gate

M5A is a mandatory research-only milestone before GPU stack installation. It exists to prevent an accidental mismatch between the NVIDIA host driver, CUDA Toolkit, PyTorch CUDA wheels, KTransformers GPU components, ik_llama CUDA builds, and NVIDIA Container Toolkit on a mixed system-RAM plus NVIDIA-VRAM workstation.

Until `reports/m5a-cuda-nvidia-compatibility.md` passes and the human approves the selected version matrix, do not install or configure:

- NVIDIA host drivers.
- CUDA Toolkit or host CUDA packages.
- PyTorch CUDA wheels.
- KTransformers GPU components or kt-kernel builds.
- ik_llama CUDA builds.
- NVIDIA Container Toolkit.
- GPU-enabled inference backends.

M5A is documentation and read-only inventory only. It must not install packages, mutate system configuration, build software, download models, or configure Docker/NVIDIA services.


## Corrected Expected Hardware

Human review corrected the expected VM hardware profile:

- Expected hardware: 2 x RTX PRO 6000 Blackwell Workstation Edition 96 GB.
- No RTX 6000 Ada is expected in this VM.
- RTX PRO 6000 Blackwell Workstation Edition is Blackwell compute capability 12.0.
- RTX 6000 Ada is Ada compute capability 8.9 and is only a contrast/reference point, not the VM profile.
- M5B must validate exact GPU names, PCI bus IDs, driver binding, and memory totals through `nvidia-smi` after driver installation and after reboot.
- M5B must include passthrough reliability checks; `lspci` visibility alone is not sufficient proof of stable VFIO passthrough.

## Current M5A Execution Result

The current M5A execution report is `reports/m5a-cuda-nvidia-compatibility.md`. Its conclusion is `STOP` for installation until human review approves the selected version matrix. It recommends host-driver-only M5B with Ubuntu `nvidia-driver-595-open` as the candidate branch, documents R580 LTS as the longer-support fallback, recommends no host CUDA Toolkit for M5B, and keeps KTransformers Blackwell GPU support blocked until SM_120 source-build proof exists.

## Required Report

The milestone report path is:

```text
reports/m5a-cuda-nvidia-compatibility.md
```

The report must include:

- Milestone ID and name: `M5A - CUDA/NVIDIA compatibility research`.
- Timestamp, hostname, user, branch, and git commit hash.
- Confirmation that the work was research-only and made no driver/CUDA/Docker/model/API changes.
- Commands run for read-only inventory.
- Official source URLs and access dates for each compatibility claim.
- PASS/STOP conclusion.
- Human approval requirement for the selected version matrix.

## Read-Only Inventory

Collect the VM facts needed to evaluate GPU compatibility:

- GPU inventory from `lspci`.
- Exact GPU names from all available read-only sources.
- Compute capability for each GPU, including whether `nvidia-smi --query-gpu=compute_cap` is supported after driver installation.
- Ubuntu version.
- Kernel version.
- Installed compiler and CMake versions if already present.
- Available Ubuntu NVIDIA driver packages from read-only package-cache commands.
- Available NVIDIA official driver branches.
- Available CUDA Toolkit versions.
- CUDA Toolkit minimum driver versions.
- PyTorch CUDA wheel support matrix.
- KTransformers branch, release, and install requirements.
- KTransformers kt-kernel GPU architecture support.
- ik_llama CUDA build requirements.
- Docker and NVIDIA Container Toolkit requirements.

Do not treat `lspci` visibility as proof that CUDA works. CUDA readiness requires a compatible kernel driver, user-space libraries, runtime, and backend-specific smoke tests.

## Required Compatibility Questions

The report must explicitly answer all of these questions before any install milestone starts:

- Should this VM use R580 LTS, R595 production, or another NVIDIA driver branch?
- Should host CUDA Toolkit be installed at all?
- If host CUDA Toolkit is required, should it be CUDA 12.8, CUDA 13.0, or another version?
- Should PyTorch use CUDA 12.8, CUDA 13.0, or another wheel?
- Does KTransformers support Blackwell RTX PRO 6000 through prebuilt wheels, source build, or not yet?
- Does KTransformers kt-kernel support the required Blackwell GPU architecture for this hardware?
- Does ik_llama compile and run with the Blackwell compute capability present in this VM?
- Should native host builds be used, or should GPU backends be built in Docker build containers with build output under `/data/build`?
- What exact tests prove the selected stack works?

If any answer is uncertain, the report conclusion must be `STOP` and no GPU installation milestone may proceed.

## Official Source Checklist

Prefer official vendor and upstream project sources. The report should include links, access dates, and the exact table or release notes consulted.

- NVIDIA CUDA Toolkit Release Notes: <https://docs.nvidia.com/cuda/cuda-toolkit-release-notes/index.html>
- NVIDIA CUDA 12.8 Release Notes: <https://docs.nvidia.com/cuda/archive/12.8.0/cuda-toolkit-release-notes/index.html>
- NVIDIA CUDA Compatibility Guide: <https://docs.nvidia.com/deploy/cuda-compatibility/latest/index.html>
- NVIDIA CUDA Installation Guide for Linux: <https://docs.nvidia.com/cuda/cuda-installation-guide-linux/index.html>
- NVIDIA CUDA GPU compute capability list: <https://developer.nvidia.com/cuda/gpus>
- NVIDIA Data Center Driver documentation: <https://docs.nvidia.com/datacenter/tesla/drivers/latest/index.html>
- NVIDIA official driver download and branch pages: <https://www.nvidia.com/Download/index.aspx>
- NVIDIA Container Toolkit installation guide: <https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html>
- PyTorch local install selector: <https://pytorch.org/get-started/locally/>
- PyTorch previous versions matrix: <https://pytorch.org/get-started/previous-versions/>
- KTransformers repository: <https://github.com/kvcache-ai/ktransformers>
- KTransformers documentation: <https://kvcache-ai.github.io/ktransformers/>
- ik_llama repository: <https://github.com/ikawrakow/ik_llama.cpp>
- ik_llama build documentation: <https://github.com/ikawrakow/ik_llama.cpp/blob/main/docs/build.md>

When official sources conflict, prefer the newer official release note over older project examples, record the conflict, and conclude `STOP` unless the human approves a risk-managed path.

## Version Matrix Template

The M5A report must fill a table like this:

| Layer | Candidate | Source | Decision | Rationale | Risk |
| --- | --- | --- | --- | --- | --- |
| NVIDIA driver branch | R580 LTS / R595 production / other | NVIDIA driver docs | TBD | TBD | TBD |
| CUDA Toolkit | none / 12.8 / 13.0 / other | CUDA release notes | TBD | TBD | TBD |
| PyTorch wheel | CPU / CUDA 12.8 / CUDA 13.0 / other | PyTorch install matrix | TBD | TBD | TBD |
| KTransformers | release / branch / source build | KTransformers docs | TBD | TBD | TBD |
| kt-kernel GPU arch | supported / source patch / unsupported | kt-kernel docs/source | TBD | TBD | TBD |
| ik_llama CUDA | supported / source patch / unsupported | ik_llama docs/source | TBD | TBD | TBD |
| Container runtime | host Docker runtime / build containers | NVIDIA Container Toolkit docs | TBD | TBD | TBD |

## M5B Install Tests To Document But Not Run In M5A

M5A must document the exact tests that M5/M6/M7 will run later. Do not run these tests during M5A unless they are read-only and already available.

Required post-install tests:

```bash
nvidia-smi
nvidia-smi -L
nvidia-smi --query-gpu=name,driver_version,memory.total,compute_cap --format=csv
nvidia-smi --query-gpu=index,name,pci.bus_id,driver_version,memory.total,power.limit --format=csv
nvidia-smi topo -m
nvidia-smi -q -d MEMORY,PCI,POWER
nvcc --version
python3 - <<'PY'
import torch
print(torch.cuda.is_available())
print(torch.zeros(1, device="cuda"))
PY
```

Additional required checks after the relevant install milestones:

- Detect exactly two RTX PRO 6000 Blackwell Workstation Edition GPUs; no RTX 6000 Ada is expected in this VM.
- Compile and run a tiny CUDA sample if CUDA Toolkit is installed.
- Build and test the ik_llama CUDA backend.
- Run a KTransformers small-model smoke test.
- After M6, run `docker run --rm --gpus all ... nvidia-smi`.
- Confirm Docker storage remains on `/data/docker`.
- Confirm build trees remain under `/data/build`.
- Confirm logs remain under `/data/logs`.
- Run the root-disk guard before and after GPU stack installation.
- Manual Proxmox passthrough checks after M5B: `journalctl` VFIO/PCIe/AER/reset scans, `qm config 120`, `qm status 120`, and confirmation that VM start/stop/reboot does not trigger unrecovered GPU reset failures.
- Do not use live snapshots with VFIO GPUs unless explicitly tested and supported.

If `nvcc` is intentionally absent because host CUDA Toolkit is not installed, the report must say so and define the equivalent container-build verification.

## PASS Criteria

M5A can pass only if:

- The exact GPUs and compute capabilities are identified.
- Ubuntu and kernel compatibility risks are documented.
- The selected NVIDIA driver branch is justified against official NVIDIA sources.
- CUDA Toolkit installation is either explicitly required or explicitly avoided.
- PyTorch CUDA wheel selection matches both the driver and backend needs.
- KTransformers and kt-kernel support status is proven for the target GPU architecture or marked unsupported.
- ik_llama CUDA build support is proven for the target GPU architecture or marked unsupported.
- Docker/NVIDIA Container Toolkit requirements are compatible with M4 storage policy.
- The selected native-host-build versus Docker-build-container strategy keeps build output under `/data/build`.
- Verification commands are listed for M5, M6, and backend GPU smoke tests.
- A human approves the selected version matrix before installation begins.

## STOP Conditions

The report must stop GPU work if:

- More than one official source gives incompatible requirements and the conflict is unresolved.
- The selected driver branch does not support all attached GPUs.
- CUDA Toolkit minimum driver requirements exceed the selected driver branch.
- PyTorch wheels do not exist for the selected CUDA runtime.
- KTransformers or kt-kernel support for Blackwell is unknown.
- ik_llama CUDA support for Blackwell compute capability is unknown.
- Required build output, cache, or logs would land on the root disk.
- Any step requires package installation, driver installation, Docker configuration, model download, or API exposure during M5A.

## Relationship To Later Milestones

- M5B uses the M5A-approved host driver branch only.
- M6 uses the M5A-approved NVIDIA Container Toolkit path only after M5B passes.
- M7 GPU-capable runtime profiles must reference the M5A-approved CUDA/PyTorch/backend matrix.
- M8 small-model API smoke testing may remain CPU-only if GPU compatibility is still blocked.
- M9 and M10 model benchmarks must not use GPU acceleration until the relevant M5/M6/M7 verification tests pass.
