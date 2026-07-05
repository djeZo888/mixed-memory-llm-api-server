# Pre-M9 / Pre-M9B Handoff

- Timestamp: `2026-07-05T14:41:54Z`
- Latest main commit after M9A merge: `e04385fe096ee3d2ed0e41e28f8c3feaf11312b2`
- M9A source commit: `670e1349e18f33cd004a8f49fe63ddb16bd987ca`
- M9A main merge report: `reports/m9a-main-merge.md`
- M9A planning report: `reports/m9a-first-real-fast-model-plan.md`
- Active model/backend: `qwen3-0.6b-smoke` on SGLang.
- Endpoint: `http://127.0.0.1:30000/v1`
- Bind: `127.0.0.1:30000` only.
- Image: `lmsysorg/sglang:v0.5.14-cu130`
- Smoke model path: `/data/models/qwen3-0.6b-smoke`
- First real model: not downloaded.
- Public API exposure: not configured.

## M9A Merge State

M9A first real fast-model planning/dry-run was accepted by human review and merged into `main`. It recommends `Qwen/Qwen3-30B-A3B-Instruct-2507` as the first real fast model, with `Qwen/Qwen3-Coder-30B-A3B-Instruct` as the coding-specific fallback after review.

M9A was planning/dry-run only. It did not download a real model, pull a SGLang image, stop smoke, start a real-model container, install packages, modify Docker/containerd, or expose an API.

## M9B Scope

M9B is the actual first real fast-model deployment milestone. It must run in a fresh Codex context and start with context-sync from `main`.

Approved M9B target:

```text
Qwen/Qwen3-30B-A3B-Instruct-2507
```

Approved local model path:

```text
/data/models/qwen3-30b-a3b-instruct-2507
```

Planned localhost bind:

```text
127.0.0.1:30001:30000
```

## M9B Allowed Actions

- Stop smoke through reviewed `scripts/llmctl stop --yes` only after explicit human approval in the M9B task.
- Download `Qwen/Qwen3-30B-A3B-Instruct-2507` to `/data/models/qwen3-30b-a3b-instruct-2507` only.
- Keep Hugging Face cache under `/data/hf-cache`.
- Start the SGLang real model on a localhost-only bind.
- Run local `/health`, `/v1/models`, non-streaming chat, streaming chat, and functional API tests.
- Validate root-disk, Docker storage, GPU container support, and active manager state before and after deployment.
- Record startup time, throughput, RAM, VRAM, context stability, and failure modes.

## M9B Forbidden Actions

- No public API exposure.
- No `0.0.0.0` host bind.
- No larger or alternate model downloads without explicit human approval.
- No Docker/containerd daemon configuration changes.
- No Docker/containerd restart unless explicitly approved in a later task.
- No unrelated backend installs or builds.
- No SGLang/PyTorch/KTransformers/vLLM/ik_llama/CUDA Toolkit host installation.
- No Docker image deletion, model deletion, or Docker prune.
- No disk, fstab, mountpoint, partitioning, or Proxmox host access.

## Smoke Operations Reference

Use the reviewed M8C lifecycle commands for smoke state:

```bash
scripts/llmctl active
scripts/llmctl status
scripts/llmctl stop --dry-run
scripts/llmctl stop --yes
scripts/llmctl start --dry-run
scripts/llmctl start --yes
scripts/sglang/verify-sglang-lifecycle.sh
```

Manual Docker commands can make `/data/services/llm-manager/active/active.json` stale. Prefer `scripts/llmctl` for smoke lifecycle actions.

## Next Decision

Start a fresh Codex context for M9B actual first real fast-model deployment. Do not start M9B from this merge/handoff context.
