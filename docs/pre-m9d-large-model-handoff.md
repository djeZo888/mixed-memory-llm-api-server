# Pre-M9D Large-Model Handoff

- Timestamp: `2026-07-06T22:53:51Z`
- Latest main commit immediately after M9C merge: `db9afcd5a1f29f6daed5f82bda7afc6791fbd89a`
- M9C benchmark commit: `9e299ccf1cde028a2d89538b85b2cc2b5c4b7d96`
- M9C readiness fix commit: `be560dd6e1772205848fde8385ddfa8261b4e3e8`
- M9C main merge report: `reports/m9c-main-merge.md`
- M9C benchmark report: `reports/m9c-real-model-benchmark-review.md`
- Raw benchmark JSONL: `/data/logs/benchmarks/m9c/m9c-results.jsonl`
- Benchmark run dir: `/data/logs/benchmarks/m9c/run-20260706T042917Z`

## Active Current Model State

- Active model/backend: `Qwen/Qwen3-30B-A3B-Instruct-2507` on SGLang.
- Served model name: `qwen3-30b-a3b-instruct-2507`.
- Endpoint: `http://127.0.0.1:30001/v1`.
- Bind: `127.0.0.1:30001` only.
- Container: `sglang-qwen3-30b-a3b-instruct-2507`.
- Container status at handoff creation: `running` / `healthy`.
- Model path: `/data/models/qwen3-30b-a3b-instruct-2507`.
- Launch args: `--tp 2 --context-length 32768 --mem-fraction-static 0.75`.
- Public API exposure remains absent.
- Smoke model remains stopped but preserved at `/data/models/qwen3-0.6b-smoke`.

## Quick Local Tests

```bash
curl -fsS http://127.0.0.1:30001/v1/models

curl -fsS http://127.0.0.1:30001/v1/chat/completions \
  -H "Content-Type: application/json" \
  --data-binary @- <<'JSON'
{
  "model": "qwen3-30b-a3b-instruct-2507",
  "messages": [{"role": "user", "content": "Reply with one short sentence confirming the model is working."}],
  "max_tokens": 64,
  "temperature": 0
}
JSON
```

```bash
scripts/llmctl status
scripts/sglang/verify-sglang-real-fast-live.sh
```

## M9C Benchmark Summary

- Cases passed: `tiny_health`, `technical_short`, `coding_short`, `streaming_short`, `context_4k`, `context_8k`, `context_16k`.
- Fast-path latency was stable: short non-streaming cases were under `0.5s`; generated-context cases were under `2.0s`.
- Streaming TTFT was `0.033s`.
- Output throughput where usage tokens were returned was about `240-249 tok/s` for larger non-streaming cases.
- GPU memory stayed around `76.3 GiB` per GPU under this deployment.
- Launch args remained unchanged.

## Context-Size Correction

The largest M9C context was `16,581` prompt characters / `3,518` prompt tokens. Do not describe this as a true 16K-token context test. True 8K/16K/24K token context testing remains future benchmark/tuning work.

## Reboot Recovery Note

After a VM reboot, the real-model container did not auto-start because no Docker restart policy or systemd auto-start service exists. Human ran `scripts/llmctl start --yes`; SGLang entered normal cold start with Docker health `starting`, port `127.0.0.1:30001` listening, and `/v1/models` temporarily not ready. M9C fixed `llmctl` so this state is reported as `starting`, not stale. Final state is healthy with `/v1/models` and chat completion passing. Boot persistence is intentionally deferred.

## Large-Model Candidates For M9D

Evaluate these candidates without downloading them in M9D:

- `Qwen/Qwen3-235B-A22B-Instruct-2507`
- `Qwen/Qwen3-235B-A22B-Instruct-2507-FP8`
- `zai-org/GLM-5.2`
- `MiniMaxAI/MiniMax-M3`

## M9D Scope

M9D is planning/dry-run only:

- No model download.
- No Docker image pull.
- No backend install.
- No container changes.
- No launch-arg changes to the active real model.
- No public API exposure.
- No Docker/containerd daemon config changes or restarts.

M9D should estimate storage, memory, runtime compatibility, quantization/precision choices, startup plan, smoke tests, rollback, and STOP conditions for one future large-model proof-of-life.

## M9E Future Scope

M9E is the earliest candidate for an actual large-model proof-of-life after M9D human review. It should start only one approved model, keep localhost-only exposure, preserve the current model files, and include explicit rollback and disk/root guards.

## Carry-Forward Proxmox Notes

- Correctable PCIe AER warnings have been observed historically during passthrough reset/start activity. Monitor under longer load tests.
- VFIO reset done lines have been observed during VM stop/start/reboot.
- Avoid live snapshots with VFIO GPUs; use stopped/offline snapshots unless explicitly tested and approved.
- QEMU Guest Agent is currently working based on previous human `qm agent 120 ping` verification.
