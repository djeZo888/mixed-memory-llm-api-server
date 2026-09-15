# mixed-memory-llm-api-server

`mixed-memory-llm-api-server` is an open-source deployment framework for running large local LLMs on mixed system-RAM plus NVIDIA-VRAM workstations and exposing an authenticated OpenAI-compatible API.

## Intended Hardware Class

The target host class is a headless Linux workstation or VM with large system RAM, many CPU cores, and one or more NVIDIA GPUs with substantial VRAM. The initial deployment target is a mixed-memory workstation where models may use both system RAM and GPU VRAM.

## Scope

This repository is API-only. It is intended to run inference backends, expose model inference APIs, and provide repeatable operational checks. It does not implement web browsing, scraping, browser automation, or a human chat UI.

## Current installer status

The fresh-Linux installer is **incomplete: final integration required**. I1/I1b
provide storage/prerequisite, container/toolkit, pinned runtime and GLM/Qwen
acquisition source stages. Package execution remains pending the reviewed
I1R/L1 ownership interface; blank-disk provisioning is handed to I1S. Full
`apply` refuses before mutation until I1c service/control/client/acceptance passes.
This revision does not leave a fresh machine ready for inference.

```sh
./install.sh --help
./install.sh plan --profile flagship-hybrid --model-set glm --data-dir /data
```

See [installation and partial-boundary commands](docs/installation.md),
[I1b test evidence](reports/i1b-runtime-acquisition.md), and
[remaining integration checklist](reports/i1c-installer-checklist.md). Ubuntu24.04 amd64 is the supported
source target. Full fresh GPU installation/reboot is **NOT_TESTED**.

The roadmap below is historical. Current D1/D1b/F1A artifact acquisition,
D2 lifecycle and V0 client interfaces are separate reviewed components;
their reports do not establish whole-installer or live-model acceptance.

## High-Level Install Roadmap

1. M0 repository bootstrap.
2. M1 VM preflight.
3. M2 data disk dry-run and `/data` preparation.
4. M3 root-disk guard.
5. M4 Docker/containerd storage.
6. M5 NVIDIA host driver.
7. M6 NVIDIA Container Toolkit.
8. M7 backend runtime abstraction.
9. M8 small model API smoke service.
10. M9 fast technical/coding model.
11. M10 larger model benchmarks.
12. M11 authenticated API exposure.
13. M12 observability and operations.

## License

Apache-2.0 is intended. The full license text is not added in M0 unless a trusted local copy is available. See `LICENSE.todo.md`.
