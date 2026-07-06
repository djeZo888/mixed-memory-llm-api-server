# M9C Main Merge Report

- Timestamp: `2026-07-06T22:53:51Z`
- Source branch: `milestone/m9c-real-model-benchmark-review`
- Target branch: `main`
- Merge commit: `db9afcd5a1f29f6daed5f82bda7afc6791fbd89a`
- M9C benchmark source commit: `9e299ccf1cde028a2d89538b85b2cc2b5c4b7d96`
- M9C readiness fix commit: `be560dd6e1772205848fde8385ddfa8261b4e3e8`
- Raw benchmark JSONL: `/data/logs/benchmarks/m9c/m9c-results.jsonl`
- Benchmark run dir: `/data/logs/benchmarks/m9c/run-20260706T042917Z`
- Conclusion: PASS. M9C benchmark review and post-reboot readiness semantics are merged into `main`.

## Active Runtime State

- Active model/backend: `Qwen/Qwen3-30B-A3B-Instruct-2507` on SGLang.
- Served model name: `qwen3-30b-a3b-instruct-2507`.
- Endpoint: `http://127.0.0.1:30001/v1`.
- Bind: `127.0.0.1:30001` only.
- Container: `sglang-qwen3-30b-a3b-instruct-2507`.
- Container status at merge: `running` / Docker health `healthy`.
- Launch args: `--tp 2 --context-length 32768 --mem-fraction-static 0.75`.
- `/v1/models`: PASS; returned `qwen3-30b-a3b-instruct-2507` with `max_model_len: 32768`.
- Public API exposure remains absent.

## Benchmark Summary

| Case | Status | Elapsed | Prompt size | Prompt tokens | Output tokens | Output tok/s |
| --- | --- | --- | --- | --- | --- | --- |
| tiny_health | PASS | 0.076s | 81 chars | 36 | 12 | 158.264 |
| technical_short | PASS | 0.473s | 72 chars | 37 | 118 | 249.255 |
| coding_short | PASS | 0.468s | 144 chars | 47 | 115 | 245.643 |
| streaming_short | PASS | 0.614s | 118 chars | n/a | n/a | n/a |
| context_4k | PASS | 0.868s | 4,254 chars | 921 | 209 | 240.831 |
| context_8k | PASS | 1.606s | 8,375 chars | 1,798 | 396 | 246.545 |
| context_16k | PASS | 1.997s | 16,581 chars | 3,518 | 486 | 243.395 |

- Streaming TTFT: `0.033s`.
- Streaming chunks: `155`.
- Largest context tested: `16,581` prompt characters / `3,518` prompt tokens.
- Correction: M9C did not test a true 16K-token context. True 8K/16K/24K token context testing remains future work.

## Resource Summary

- Benchmark GPU memory range: GPU0 `76360-76360 MiB`, GPU1 `76392-76392 MiB`.
- Benchmark GPU utilization range: `0-100%`.
- Benchmark memory utilization range: GPU0 `0-70%`, GPU1 `0-58%`.
- Benchmark power range: GPU0 `79-287 W`, GPU1 `93-310 W`.
- Post-merge warm state: GPU0 `76294 MiB`, GPU1 `76326 MiB`; GPU utilization `0%`; power about `83 W` and `89 W`.
- Disk state at merge: `/` `15G` total, `9.0G` used, `4.5G` free; `/data` `2.0T` total, `124G` used, `1.8T` free.
- Docker system df at merge: images `69.75GB`, containers `351.3MB`; no prune was run.

## Lifecycle And Recovery

- Lifecycle dry-runs from M9C passed: `status`, `logs --dry-run`, `stop --dry-run`, and `restart --dry-run`.
- A VM reboot later left the real-model container stopped because no Docker restart policy or systemd auto-start service exists by design.
- First post-reboot diagnostic state was `exited`/`unhealthy` with exit code `137`; logs showed `SIGTERM` and graceful SGLang shutdown.
- Human ran `scripts/llmctl start --yes`; the container was then running with Docker health `starting`, port `127.0.0.1:30001` listening, and `/v1/models` not ready yet with connection reset during cold start.
- This intermediate state was startup readiness, not a confirmed model failure.
- `scripts/llmctl` now reports running plus `health=starting` as `manager_status: starting`, not stale. Exited containers remain `stale`; `health=unhealthy` reports `unhealthy`; healthy container plus `/v1/models` reports `active`.
- `scripts/llmctl start --yes` now waits up to 20 minutes for readiness by default and prints periodic startup status lines.
- Final recovery state at merge: `manager_status: active`, container `running`/`healthy`, localhost port listening, `/v1/models` and chat completion passing.
- Auto-start/boot policy is deferred to a later milestone.

## Guard Results

- `/data` mount guard: PASS.
- Root-disk guard: PASS.
- Docker storage verifier: PASS.
- GPU verifier: PASS with existing `nvidia/cuda:13.2.1-base-ubuntu24.04`.
- SGLang real-fast live verifier: PASS after recovery.
- Secret scan: broad scan matched only intentional docs, tests, scanner patterns, safety strings, and historical report text; changed-file value-shaped scan matched only the static test scanner regex. No real secret was identified.

## No-Action Confirmations

- No model download occurred.
- No Docker image pull occurred.
- No package install occurred.
- No Docker/containerd daemon config was modified.
- Docker/containerd daemons were not restarted.
- No Docker restart policy was added.
- No systemd service was created.
- No public API exposure, firewall change, reverse proxy, Caddy, TLS, or auth front door was created.
- No model files or Docker images were deleted, and Docker prune was not run.
- The active model launch args were not changed.

## Next Milestone

Human decision after M9C: large-model testing should happen before API/front-door/auth work. Next recommended milestone is M9D large-model feasibility and selection planning/dry-run.
