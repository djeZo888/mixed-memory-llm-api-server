# Architecture

## Layers

1. Host safety: preflight, disk dry-run, root-disk guard, and milestone reports.
2. Storage: `/data` for models, caches, Docker, containerd, builds, logs, services, backups, and secrets after M2.
3. GPU compatibility gate: M5A researches and freezes the approved NVIDIA driver, CUDA Toolkit, PyTorch CUDA wheel, KTransformers, ik_llama, and NVIDIA Container Toolkit matrix before any GPU stack installation.
4. Runtime profiles: backend-specific configuration for KTransformers and ik_llama.
5. API: OpenAI-compatible endpoints, local-first binding, and API-key enforcement for exposure.
6. Operations: health checks, logs, restarts, benchmark records, and troubleshooting.

## Default Network Posture

Inference backends bind to `127.0.0.1` by default. External access requires an explicit exposure milestone, API keys, and documented firewall/TLS or VPN controls.

## Data Boundary

The root disk is a control-plane disk. Large or persistent AI data belongs on `/data` only after the M2 data-disk milestone prepares it.

## GPU Compatibility Boundary

GPU enablement is intentionally split from host storage and Docker work. M5A is a documentation and research gate that must complete before M5 host driver work, M6 NVIDIA Container Toolkit work, or any GPU-enabled KTransformers or ik_llama build.

The M5A report must use official vendor and upstream project sources where possible, then produce a human-approved version matrix covering the driver branch, CUDA Toolkit choice, PyTorch CUDA wheel, KTransformers/kt-kernel support, ik_llama CUDA build support, and verification tests. Until that report passes, the project treats Blackwell support as unproven even if GPUs are visible in `lspci`.

Host CUDA Toolkit installation is not assumed. The M5A report must decide whether native host builds need a Toolkit on the VM or whether build containers with mounted `/data/build` are safer and more reproducible.

See [CUDA/NVIDIA Compatibility Gate](cuda-driver-compatibility.md) for the required research checklist.
