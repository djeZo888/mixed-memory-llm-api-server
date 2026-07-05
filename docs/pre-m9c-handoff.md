# Pre-M9C Handoff

- Timestamp: `2026-07-05T17:28:07Z`
- Repository: `git@github.com:djeZo888/mixed-memory-llm-api-server.git`
- Repo path on VM: `/data/services/mixed-memory-llm-api-server`
- Latest `main` commit after M9B merge: `c33d09d31bba66f6a0af2bb4c8b9b451887adbe0`
- M9B source commit: `4fb333a649d5e0169d616fd3b1c1980b7b0ac15d`
- M9B main merge report: `reports/m9b-main-merge.md`
- M9B deployment report: `reports/m9b-first-real-fast-model-deploy.md`

## Active Real-Model State

- Active model/backend: `Qwen/Qwen3-30B-A3B-Instruct-2507` on SGLang.
- Served model name: `qwen3-30b-a3b-instruct-2507`.
- Container: `sglang-qwen3-30b-a3b-instruct-2507`, running and healthy at merge validation.
- Endpoint: `http://127.0.0.1:30001/v1`.
- Bind: `127.0.0.1:30001` only.
- Model path: `/data/models/qwen3-30b-a3b-instruct-2507`.
- Model size: `57G`.
- Runtime image: `lmsysorg/sglang:v0.5.14-cu130`.
- Compose file outside Git: `/data/services/llm-manager/compose/sglang-qwen3-30b.compose.yml`.
- Active state outside Git: `/data/services/llm-manager/active/active.json`.
- Launch args: `--tp 2 --context-length 32768 --mem-fraction-static 0.75`.

## Smoke Model State

- Smoke backend was stopped cleanly during M9B through `scripts/llmctl stop --yes`.
- Smoke endpoint `http://127.0.0.1:30000/v1` should not be listening during M9C unless intentionally restored in a later approved task.
- Smoke model files remain preserved at `/data/models/qwen3-0.6b-smoke` (`1.5G`).
- Do not delete smoke model files or Docker images.

## Quick Manual Checks

```bash
cd /data/services/mixed-memory-llm-api-server
scripts/llmctl active
scripts/llmctl status
scripts/llmctl logs --dry-run
scripts/sglang/verify-sglang-real-fast-live.sh
curl -fsS http://127.0.0.1:30001/v1/models
ss -tulpn | grep ':30001'
```

Manual non-streaming chat check:

```bash
curl -fsS http://127.0.0.1:30001/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"qwen3-30b-a3b-instruct-2507","messages":[{"role":"user","content":"Reply with one short sentence confirming the first real model is working."}],"max_tokens":128,"temperature":0}'
```

Manual streaming check:

```bash
curl -fsS http://127.0.0.1:30001/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"qwen3-30b-a3b-instruct-2507","messages":[{"role":"user","content":"Stream one short confirmation sentence."}],"max_tokens":128,"temperature":0,"stream":true}'
```

## M9C Scope

M9C should be benchmark/lifecycle/resource review for the active first real model.

Recommended scope:

- Benchmark latency, throughput, streaming behavior, and practical context behavior for the 30B model.
- Review GPU memory, root/data disk usage, logs, and warning patterns after sustained use.
- Review lifecycle semantics for the real model, especially whether `restart --yes` should become supported.
- Inspect SGLang warnings, including missing optimized MoE kernel config for RTX PRO 6000 Blackwell.
- Keep all model/cache/log/runtime data under `/data`.

M9C must not:

- Expose a public API.
- Bind host services to `0.0.0.0`.
- Download a new model.
- Download the fallback coder model.
- Install host backend packages.
- Install CUDA Toolkit.
- Modify or restart Docker/containerd daemons unless a later human-approved task explicitly allows it.

## Carry-Forward Proxmox Notes

- Correctable PCIe AER warnings were observed during passthrough reset/start activity.
- VFIO reset done lines were observed.
- Avoid live snapshots with VFIO GPUs because previous logs showed VFIO migration unsupported.
- QGA currently works based on human `qm agent 120 ping` verification.
