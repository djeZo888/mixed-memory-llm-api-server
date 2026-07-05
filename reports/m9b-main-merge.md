# M9B Main Merge Report

- Timestamp: `2026-07-05T17:28:07Z`
- Source branch: `milestone/m9b-first-real-fast-model-deploy`
- Target branch: `main`
- Merge commit hash: `c33d09d31bba66f6a0af2bb4c8b9b451887adbe0`
- M9B source commit hash: `4fb333a649d5e0169d616fd3b1c1980b7b0ac15d`
- Result: PASS. M9B was merged into `main`; the first real fast model remains active, healthy, and localhost-only.

## Live Validation Summary

- `/data` mounted guard: PASS.
- Root-disk guard: PASS.
- Docker storage verifier: PASS; Docker Root Dir is `/data/docker`.
- GPU verifier: PASS with `nvidia/cuda:13.2.1-base-ubuntu24.04`.
- `scripts/llmctl validate`: PASS.
- `scripts/llmctl active`: PASS, active model is `qwen3-30b-a3b-instruct-2507` on SGLang.
- `scripts/llmctl status`: PASS, manager status is active and the container is healthy.
- `scripts/llmctl logs --dry-run`: PASS.
- `scripts/sglang/verify-sglang-real-fast-live.sh`: PASS.
- `git diff --check`: PASS before merge.
- Secret scan: matched only intentional documentation, test, report, and scanner strings; no real secret was identified.

## Active Model State

- Active model/backend: `Qwen/Qwen3-30B-A3B-Instruct-2507` on SGLang.
- Served model name: `qwen3-30b-a3b-instruct-2507`.
- Model path and size: `/data/models/qwen3-30b-a3b-instruct-2507`, `57G`.
- Runtime image: `lmsysorg/sglang:v0.5.14-cu130`.
- Container: `sglang-qwen3-30b-a3b-instruct-2507`, running and healthy.
- Endpoint: `http://127.0.0.1:30001/v1`.
- Bind verification: `127.0.0.1:30001` only; no `0.0.0.0` host bind was observed.
- Runtime compose file outside Git: `/data/services/llm-manager/compose/sglang-qwen3-30b.compose.yml`.
- Active state outside Git: `/data/services/llm-manager/active/active.json`.

## Launch Args Used

```text
--tp 2 --context-length 32768 --mem-fraction-static 0.75
```

Container-internal SGLang listens on `0.0.0.0:30000`, but host publishing remains `127.0.0.1:30001:30000` only.

## API Results

- `/v1/models`: PASS, HTTP 200, returned `qwen3-30b-a3b-instruct-2507` with `max_model_len=32768`.
- Chat smoke: PASS, HTTP 200 with non-empty answer confirming the first real model is working.
- Streaming: PASS, HTTP 200 with SSE chunks and clean completion.
- Technical prompt: PASS, HTTP 200 with a non-empty PCIe passthrough explanation.

## Smoke Model State

- Smoke stop result: PASS; smoke was stopped cleanly through `scripts/llmctl stop --yes` during M9B.
- Smoke port `30000`: not listening during merge validation.
- Smoke model preserved: `/data/models/qwen3-0.6b-smoke`, `1.5G`.
- Smoke Docker image preserved; no image deletion or prune was run.

## Storage And Runtime Evidence

- Docker Root Dir: `/data/docker`.
- containerd root/state: `/data/containerd/root` / `/run/containerd`.
- Root filesystem: `/` total `15G`, used `9.0G`, free `4.5G`.
- Data filesystem: `/data` total `2.0T`, used `124G`, free `1.8T`.
- Docker system df: images `69.75GB`, containers `351.2MB`, no local volumes, no build cache.
- Directory sizes: `/data/docker` `27G`; `/data/containerd` `66G`; real model `57G`; smoke model `1.5G`; `/data/hf-cache` `7.4M`; `/data/logs/sglang-qwen3-30b` `4.0K`.
- Runtime VRAM after warmup: about `76294 MiB` on GPU 0 and `76326 MiB` on GPU 1.

## No-Action Confirmations

- No public API exposure was configured.
- No host bind to `0.0.0.0` was configured.
- No firewall, reverse proxy, Caddy, TLS, API auth, or front-door service was created.
- No fallback, larger, coder, or alternate model was downloaded.
- No host backend, SGLang, PyTorch, CUDA Toolkit, KTransformers, vLLM, or ik_llama install occurred.
- Docker/containerd daemon configuration was not modified and Docker/containerd was not restarted.
- No model files or Docker images were deleted.
- Docker prune was not run.
- No disk, fstab, mountpoint, partitioning, or Proxmox host change occurred.

## Next Recommended Milestone

M9C benchmark/lifecycle/resource review for the active first real model before M10 API/front-door/auth planning.
