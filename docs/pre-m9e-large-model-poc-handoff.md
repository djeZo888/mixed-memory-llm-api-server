# Pre-M9E Large-Model Proof-Of-Life Handoff

- Timestamp: `2026-07-07T00:52:31Z`
- Latest `main` commit after M9D merge: `3ae263395fe1c5bca260a0136ab77a6f18110bcb`
- M9D source commit: `c3131db02ace63ffca6a8180d9d3ddea5094d2ae`
- Repo path on VM: `/data/services/mixed-memory-llm-api-server`
- Repo SSH URL: `git@github.com:djeZo888/mixed-memory-llm-api-server.git`
- Git identity required for future commits: `CodexAIagent <133749519+djeZo888@users.noreply.github.com>`
- M9D merge report: `reports/m9d-main-merge.md`
- M9D feasibility report: `reports/m9d-large-model-feasibility-plan.md`
- Result: M9D is merged. Stop before M9E actual large-model proof-of-life until human review.

## Current Active 30B State

- Active model/backend: `Qwen/Qwen3-30B-A3B-Instruct-2507` on SGLang.
- Served model name: `qwen3-30b-a3b-instruct-2507`.
- Endpoint: `http://127.0.0.1:30001/v1`.
- Bind: `127.0.0.1:30001` only.
- Container: `sglang-qwen3-30b-a3b-instruct-2507`.
- Runtime image: `lmsysorg/sglang:v0.5.14-cu130`.
- Model path: `/data/models/qwen3-30b-a3b-instruct-2507`.
- Launch args: `--tp 2 --context-length 32768 --mem-fraction-static 0.75`.
- Last merge validation: `running` / `healthy`, `/v1/models` OK, localhost-only.
- Public API exposure remains absent.
- No boot auto-start policy exists yet; boot persistence remains a later milestone.

## M9D Recommendation

- Primary M9E proof-of-life model: `MiniMaxAI/MiniMax-M3-MXFP8`.
- Runtime path: KTransformers / KT-Kernel plus SGLang heterogeneous CPU/GPU serving.
- Fallback model: `Qwen/Qwen3-235B-A22B-Instruct-2507-FP8`.
- Expected primary model files: about 443.75 GB / 413.27 GiB.
- Expected `/data` reservation: 500-650 GB for model files, cache, build artifacts, logs, and rollback room.
- VRAM/RAM risk: high. The large proof must not run concurrently with the current 30B backend, requires CPU/GPU offload, and Blackwell workstation support still needs proof.
- Recommended first context: 8192 tokens or less; do not attempt 1M context first.
- M9C correction carries forward: the largest M9C context was 16,581 prompt characters / 3,518 prompt tokens, not a true 16K-token context test.

## Recommended M9E Scope

M9E should be the actual large-model proof-of-life for one reviewed model/runtime path. It should prove minimal serving only:

- Sync clean `main` in `/data/services/mixed-memory-llm-api-server`.
- Verify hostname `llmserver`, Git identity, `/data`, root-disk guard, Docker storage, GPU visibility, and current active 30B health.
- Stop the current 30B backend through `scripts/llmctl` only after explicit human approval.
- Download only `MiniMaxAI/MiniMax-M3-MXFP8` to `/data/models`, with cache under `/data/hf-cache`.
- Install or build only the reviewed KTransformers / KT-Kernel / SGLang path required for proof-of-life, preferably under `/data/build` or an approved container strategy.
- Start one localhost-only large-model service on a distinct proof port.
- Run minimal `/v1/models`, one short non-streaming chat, one short streaming chat, and resource snapshots.
- Stop and document uncertainty if runtime compatibility, CUDA/KT-Kernel support, memory fit, or health is unclear.

## M9E Forbidden Actions

- No public API exposure.
- No host bind to `0.0.0.0`.
- No fallback model download unless the primary is explicitly rejected by the human.
- No Docker/containerd daemon config changes unless separately reviewed.
- No Proxmox host access.
- No live snapshots with VFIO GPUs.
- No model file deletion, Docker image deletion, Docker prune, disk/fstab/mountpoint/partition changes, or unrelated package installs.
- No M10 API/front-door/auth work in M9E unless the human explicitly changes sequencing.

## Carry-Forward Proxmox Notes

- Correctable PCIe AER warnings have been observed during passthrough reset/start activity.
- VFIO reset done lines have been observed.
- Avoid live snapshots with VFIO GPUs because prior logs showed VFIO migration is unsupported.
- QGA is currently working based on human `qm agent 120 ping` verification.

## Fresh Context Start

Start the next Codex session from this file plus:

- `AGENTS.md`
- `ROADMAP.md`
- `docs/current-state.md`
- `docs/large-model-feasibility.md`
- `docs/model-matrix.md`
- `docs/model-runtime-manager.md`
- `reports/m9d-main-merge.md`
- `reports/m9d-large-model-feasibility-plan.md`

Then start M9E only after human review and explicit approval to stop the current 30B backend and perform the first large-model proof-of-life.
