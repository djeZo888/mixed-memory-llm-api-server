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

## M4A Docker/containerd storage planning

Create Docker/containerd installation and storage scripts, static tests, dry-run output, and `reports/m4a-docker-containerd-plan.md` without installing packages or editing system configuration. M4A must document Docker's official Ubuntu apt repository method, Docker `data-root` policy, containerd persistent root policy, current `/var/lib/docker` and `/var/lib/containerd` state, and the checks required before actual installation.

## M4B Docker/containerd storage installation

Install and configure Docker only after M4A review, `/data` is mounted, and M3 root-disk guard passes. Docker root must be `/data/docker`; containerd persistent storage must be under `/data/containerd` or explicitly documented as safe. M4B must verify storage before any image pull or container run.

## M5A CUDA/NVIDIA compatibility research

Before any NVIDIA driver, CUDA Toolkit, PyTorch CUDA wheel, KTransformers GPU component, ik_llama CUDA build, or NVIDIA Container Toolkit installation, produce `reports/m5a-cuda-nvidia-compatibility.md` from official sources where possible. The report must inventory the GPUs, compute capability, Ubuntu/kernel versions, available Ubuntu and NVIDIA driver branches, CUDA Toolkit versions, CUDA minimum driver requirements, PyTorch CUDA wheel support, KTransformers and kt-kernel requirements, ik_llama CUDA build requirements, Docker/NVIDIA Container Toolkit requirements, and the exact verification tests for the chosen stack.

M5A must explicitly answer whether to use R580 LTS, R595 production, or another driver branch; whether host CUDA Toolkit should be installed; whether CUDA 12.8, CUDA 13.0, or another Toolkit should be used; which PyTorch CUDA wheel should be used; whether KTransformers supports Blackwell RTX PRO 6000 through wheels, source builds, or not yet; whether ik_llama compiles and runs for Blackwell compute capability; and what tests prove the selected stack works. Human approval of the selected version matrix is required before M5B, M6, M7 GPU build work, or any GPU backend installation. The first M5A execution report concludes `STOP` for installation until human review; the recommended next task is matrix review before any host driver installation.

## M5B NVIDIA host driver

Install the approved Ubuntu/NVIDIA host driver path after M5A passes and a VM checkpoint has been requested. Verify all expected GPUs with `nvidia-smi` before and after reboot.

## M5C QEMU Guest Agent status review

Guest management was reviewed after M5B. Human Proxmox host verification ran `qm agent 120 ping`; it returned no output and produced no new guest-ping warning, so QEMU Guest Agent currently works. Older guest-ping timeouts are historical/temporary and not a current blocker. If QGA warnings recur, repair guest agent behavior in a focused maintenance task with no NVIDIA/CUDA/container-toolkit/model/API changes.

## M6A NVIDIA Container Toolkit planning/dry-run

Plan and dry-run the approved NVIDIA Container Toolkit path after M5B. M6A must preserve Docker Root Dir `/data/docker` and containerd root `/data/containerd/root`, document package/configuration changes before install, define rollback and verification commands, and keep any image pulls or `docker run --gpus all ... nvidia-smi` execution for the approved install milestone. M6A must not install NVIDIA Container Toolkit, configure Docker NVIDIA runtime, download models, configure inference backends, or expose API unless explicitly expanded.

## M6B NVIDIA Container Toolkit

Completed. Installed and configured the approved NVIDIA Container Toolkit Docker path after M6A human review. M6B added the NVIDIA Container Toolkit apt repository, installed the approved toolkit packages, backed up and modified `/etc/docker/daemon.json` through `sudo nvidia-ctk runtime configure --runtime=docker`, restarted Docker after config verification, and verified `docker run --gpus all ... nvidia-smi` works while Docker storage remains on `/data`. M6B did not configure the containerd NVIDIA runtime.

## M7A model/runtime research and shortlist

Research current model and runtime options using official/current web sources where possible. M7A must be research-only: no model downloads, no backend installs, no runtime builds, no inference service configuration, and no API exposure. Produce a shortlist of three large/high-quality model candidates, three smaller/faster model candidates, and a runtime/backend recommendation matrix for human review.

Completed and merged into `main`. M7A produced `reports/m7a-model-runtime-research.md` on branch `milestone/m7a-model-runtime-research`; `reports/m7a-main-merge.md` records the main merge. Its conclusion is PASS for research and shortlist, STOP for downloads/installs/builds/services/API exposure until a later approved milestone. Human review decided not to lock a final model yet; the project should support several model/runtime profiles and allow only one active model/backend at a time.

## M7B model/runtime manager abstraction

Add a model/runtime manager abstraction with profile definitions, runtime environment examples, and common start/stop/status/benchmark script skeletons for SGLang, vLLM, KTransformers/KT-Kernel, ik_llama, or other approved backend paths. M7B must keep backends bound to `127.0.0.1` by default, pin versions/images, keep model/cache/build/log paths under `/data`, make new model profiles easy to add, and ensure only one model/backend is active at a time. M7B must not download models, install backends, build runtimes, modify Docker/containerd config, restart Docker/containerd, create services, or expose API unless explicitly expanded.

Completed and merged into `main`. M7B created `scripts/llmctl`, declarative model/runtime profiles, compose templates, manager documentation, shell tests, and `reports/m7b-model-runtime-manager.md`. M7B remained dry-run/planning only: no model downloads, backend installs, Docker image pulls, runtime containers, service creation, Docker/containerd changes, restarts, or API exposure. The next task is M8A SGLang smoke-model deployment planning/dry-run.

## M8A SGLang smoke-model deployment planning/dry-run

Completed and merged into `main`. M8A produced `reports/m8a-sglang-smoke-plan.md` on branch `milestone/m8a-sglang-smoke-plan`; `reports/m8a-main-merge.md` records the main merge. M8A planned the SGLang + `Qwen/Qwen3-0.6B` smoke path using the M7B manager/profiles. It remained planning/dry-run only: no model downloads, backend installs, Docker image pulls, backend containers, API exposure, Docker/containerd config changes, Docker/containerd restarts, or services. The reviewed plan uses `/data/models/qwen3-0.6b-smoke`, localhost bind `127.0.0.1:30000`, and proposed pinned image `lmsysorg/sglang:v0.5.14-cu130-runtime` pending M8B digest verification.

## M8B small model API smoke service

Completed and merged into `main` after remediation. The first attempt with `lmsysorg/sglang:v0.5.14-cu130-runtime` stopped before readiness because the image Python environment raised `ModuleNotFoundError: No module named 'distro'`. Human review approved switching to the full image `lmsysorg/sglang:v0.5.14-cu130`; its linux/amd64 digest was verified, the required `distro`, `openai`, and SGLang OpenAI protocol imports passed, and the smoke backend started on `127.0.0.1:30000` only. `/v1/models`, non-streaming chat, streaming chat, logs, active state, root-disk guard, Docker storage verification, and GPU container verification passed. No public API exposure was configured. `reports/m8b-main-merge.md` records the main merge. M8B is complete/merged.

## M8C smoke lifecycle/deactivate policy

Completed and merged into `main`. M8C adds reviewed `llmctl` lifecycle commands for the existing SGLang smoke deployment: status, active, logs, stop, start, restart, and deactivate. Mutating commands require `--yes`, preserve model files and Docker images, keep the backend localhost-only, and keep `active.json` consistent. M8C performs no model downloads, image pulls, host package installs, public API exposure, Docker/containerd daemon changes, or systemd service creation. `reports/m8c-main-merge.md` records the main merge.

## M9 fast technical/coding model

M9A first real fast-model planning/dry-run is complete and merged into `main`. M9A produced `reports/m9a-first-real-fast-model-plan.md`; `reports/m9a-main-merge.md` records the main merge. It recommends `Qwen/Qwen3-30B-A3B-Instruct-2507` as the M9B primary model, with `Qwen/Qwen3-Coder-30B-A3B-Instruct` as the coding-specific fallback after review. M9A remained planning-only: no real model download, Docker image pull, new runtime container, smoke stop, Docker/containerd change, package install, or public API exposure.

M9B first real fast-model deployment is complete on branch `milestone/m9b-first-real-fast-model-deploy` and should be reviewed/merged if PASS. M9B stopped smoke through `scripts/llmctl`, downloaded only `Qwen/Qwen3-30B-A3B-Instruct-2507` to `/data/models/qwen3-30b-a3b-instruct-2507`, started SGLang on localhost-only bind `127.0.0.1:30001:30000`, and passed `/v1/models`, non-streaming chat, streaming chat, local-only exposure checks, root-disk guard, Docker storage verification, and GPU container verification. No public API exposure, host backend install, CUDA Toolkit install, Docker/containerd daemon change, fallback model download, model deletion, image deletion, or prune occurred.

M9C is optional lifecycle/benchmark hardening for the first real model. It should review stop/start/restart semantics for the real model, benchmark latency/throughput and context behavior, inspect warnings such as missing optimized MoE kernel config, and decide whether `restart --yes` should become supported for the real model.

## M10 API/front-door/auth planning

After M9B passes, M10 should be API/front-door/auth planning only. It should choose LAN-only, VPN-only, or public TLS exposure strategy, define API-key handling, firewall/TLS policy, reverse proxy or gateway placement, and unauthorized-access tests. M10 must not expose a public API until a later approved implementation milestone.

## M11 larger model benchmarks

After M9B and M10 planning, benchmark `Qwen/Qwen3-235B-A22B-Instruct-2507`, `MiniMaxAI/MiniMax-M3`, and `zai-org/GLM-5.2` one model at a time, with storage and memory estimates before downloads. Use `deepseek-ai/DeepSeek-V4-Flash` as the practical large-model feasibility comparator if human review prioritizes fit and speed before the largest candidates.

## M12 authenticated API exposure and operations

Implement the reviewed API exposure plan only after approval, then add health scripts, model memory reports, log rotation, restart policies, backup/restore docs for configs and secrets, upgrade procedure, and troubleshooting docs.
