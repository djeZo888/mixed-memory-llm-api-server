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

## M4 Docker/containerd storage

Install and configure Docker only after `/data` is mounted and M3 root-disk guard passes. Docker root must be `/data/docker`; containerd storage must be relocated or explicitly documented as safe.

## M5 NVIDIA host driver

Install the appropriate Ubuntu/NVIDIA host driver path after requesting a VM checkpoint. Verify all expected GPUs with `nvidia-smi` before and after reboot.

## M6 NVIDIA Container Toolkit

Install and configure NVIDIA Container Toolkit. Verify `docker run --gpus all ... nvidia-smi` works while Docker storage remains on `/data`.

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
