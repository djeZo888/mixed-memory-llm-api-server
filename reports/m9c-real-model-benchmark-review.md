# M9C Real Model Benchmark Review

- Timestamp: `2026-07-06T04:33:33Z`
- Branch: `milestone/m9c-real-model-benchmark-review`
- Base commit: `a3fafe5dd31c11e0e122794c93d1ea506428d743`
- Run ID: `20260706T042917Z`
- Raw benchmark JSONL: `/data/logs/benchmarks/m9c/m9c-results.jsonl`
- Conclusion: PASS. The modest local benchmark suite passed against the active first real model.

## Context-Sync Result

PASS. The M9C context-sync gate started from clean `main`, verified Git identity, restored known verifier report side effects, and created the milestone branch only after the active localhost-only SGLang real model passed live verification.

## Active Model State

- Active model/backend: `Qwen/Qwen3-30B-A3B-Instruct-2507` on SGLang.
- Served model name: `qwen3-30b-a3b-instruct-2507`.
- Endpoint: `http://127.0.0.1:30001/v1`.
- Bind: `127.0.0.1:30001` only.
- Container: `sglang-qwen3-30b-a3b-instruct-2507`.
- Model path: `/data/models/qwen3-30b-a3b-instruct-2507`.
- Launch args: `--tp 2 --context-length 32768 --mem-fraction-static 0.75`.
- Public API exposure remains unconfigured.

## Benchmark Cases

| Case | Status | HTTP | Elapsed | TTFT | Prompt Chars | Output Chars | Prompt Tokens | Output Tokens | Output tok/s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| tiny_health | PASS | 200 | 0.076s | n/a | 81 | 55 | 36 | 12 | 158.264 |
| technical_short | PASS | 200 | 0.473s | n/a | 72 | 587 | 37 | 118 | 249.255 |
| coding_short | PASS | 200 | 0.468s | n/a | 144 | 520 | 47 | 115 | 245.643 |
| streaming_short | PASS | 200 | 0.614s | 0.033s | 118 | 604 | n/a | n/a | n/a |
| context_4k | PASS | 200 | 0.868s | n/a | 4254 | 1062 | 921 | 209 | 240.831 |
| context_8k | PASS | 200 | 1.606s | n/a | 8375 | 1783 | 1798 | 396 | 246.545 |
| context_16k | PASS | 200 | 1.997s | n/a | 16581 | 2515 | 3518 | 486 | 243.395 |

## Latency And Throughput Summary

- Largest context tested successfully: `context_16k` with `16,581` prompt characters and `3,518` prompt tokens.
- Correction: M9C did not test a true 16K-token context; true 8K/16K/24K token context testing remains future work.
- Streaming TTFT: `0.033s`.
- Streaming total elapsed: `0.614s`.
- Streaming chunks: `155`.
- Output token throughput is reported only when SGLang returns OpenAI `usage.completion_tokens`.

## Sanitized Response Excerpts

- `tiny_health`: The M9C benchmark health check is functioning properly.
- `technical_short`: PCIe passthrough allows a virtual machine (VM) to directly access and use a physical GPU as if it were connected directly to the VM, bypassing the host operating system's GPU driver stack. This enables the VM to leverage the full performance and capabilities of the GPU for tasks like gaming, machine learning, or 3D rendering, with near-native efficiency. The...
- `coding_short`: ```python def chunked(lst, size): for i in range(0, len(lst), size): yield lst[i:i + size] ``` - **Splits a list into fixed-size sublists**: The function divides the input list into chunks of a specified size, maintaining order. - **Uses generator for memory efficiency**: It yields each chunk one at a time, avoiding memory overhead from storing all chunks in...
- `streaming_short`: 1. **Verify Server is Running**: Confirm the local server process is active (e.g., `curl http://localhost:8080/health` returns 200). 2. **Test Basic Endpoint**: Send a simple request to `/v1/models` to ensure the endpoint responds with model metadata. 3. **Validate API Compatibility**: Make a minimal `/v1/chat/completions` request with a basic prompt and che...
- `context_4k`: - The SGLang backend operates exclusively over localhost; no public API exposure or 0.0.0.0 binds are permitted. - Model weights, cache files, Docker data, containerd data, logs, and benchmark artifacts must reside under the /data directory. - Model downloads, Docker image pulls, package installations, and daemon restarts are out of scope and must not be per...
- `context_8k`: **Storage Constraints & Risks:** - All model weights, cache files, Docker data, containerd data, logs, and benchmark artifacts **must reside under `/data`**. - No external storage or temporary directories may be used; strict adherence to `/data` is required. - Risk of storage exhaustion due to large model sizes or unbounded log/cache growth during long-runni...
- `context_16k`: **Benchmark Risks:** - **PCIe AER Warnings:** Correctable PCIe Advanced Error Reporting (AER) warnings during passthrough reset/start activity pose a risk to stability, especially under prolonged or high-load testing. These may indicate underlying hardware or virtualization layer issues affecting GPU reliability. - **GPU Memory Exhaustion:** With two RTX PRO...

## GPU Resource Summary

| GPU | Memory Used | GPU Util | Memory Util | Power | Temp |
| --- | --- | --- | --- | --- | --- |
| 0 | 76360-76360 MiB | 0-100% | 0-70% | 79-287 W | 37-44 C |
| 1 | 76392-76392 MiB | 0-100% | 0-58% | 93-310 W | 42-49 C |

## Guard Results

| Guard | Status | Details |
| --- | --- | --- |
| require_data | PASS | /data/logs/benchmarks/m9c/run-20260706T042917Z/guard-require_data.txt |
| root_disk | PASS | /data/logs/benchmarks/m9c/run-20260706T042917Z/guard-root_disk.txt |
| docker_storage | PASS | /data/logs/benchmarks/m9c/run-20260706T042917Z/guard-docker_storage.txt |
| gpu_container | PASS | /data/logs/benchmarks/m9c/run-20260706T042917Z/guard-gpu_container.txt |
| real_fast_live | PASS | /data/logs/benchmarks/m9c/run-20260706T042917Z/guard-real_fast_live.txt |

## Lifecycle Dry-Run Results

| Command | Status | Details |
| --- | --- | --- |
| status | PASS | /data/logs/benchmarks/m9c/run-20260706T042917Z/lifecycle-status.txt |
| logs_dry_run | PASS | /data/logs/benchmarks/m9c/run-20260706T042917Z/lifecycle-logs_dry_run.txt |
| stop_dry_run | PASS | /data/logs/benchmarks/m9c/run-20260706T042917Z/lifecycle-stop_dry_run.txt |
| restart_dry_run | PASS | /data/logs/benchmarks/m9c/run-20260706T042917Z/lifecycle-restart_dry_run.txt |

No real stop or restart was executed in M9C.

## SGLang Log Warning/Error Summary

- No warning/error lines matched in the captured SGLang log tail.

## Resource And Passthrough Notes

- Root/Docker/GPU guards passed before benchmark execution.
- Resource snapshots were collected before and after each benchmark case with `nvidia-smi`, `docker stats --no-stream`, `df -hT / /data`, and `docker system df`.
- Correctable PCIe AER warnings have been observed historically during passthrough reset/start activity and should be monitored under longer load tests.

## Recommendations

- Keep the current launch args for now: `--tp 2 --context-length 32768 --mem-fraction-static 0.75`.
- Run a later dry-run-only tuning review before changing memory fraction, context length, CUDA graph, or MoE kernel-related flags.
- Benchmark a 24K generated-context case later before trying anything near the configured 32K context limit.
- Do not attempt full 262K context on this deployment; that belongs to a later tuning milestone with explicit memory planning.
- Human decision after M9C: add a large-model feasibility path before API/front-door/auth work. Proceed next to M9D large-model feasibility and selection planning/dry-run, then M9E proof-of-life only after human review.

## Post-Benchmark Reboot Recovery Note

- Timestamp: `2026-07-06T22:45:43Z`.
- A VM reboot terminated the real-model container; no Docker restart policy, systemd service, or boot persistence policy is intentionally configured yet.
- First post-reboot state observed before this recovery was `exited`/`unhealthy` with exit code `137`; prior logs showed `SIGTERM` followed by graceful SGLang shutdown.
- Human then ran `scripts/llmctl start --yes`. During cold start the container was `running`, Docker health was `starting`, port `127.0.0.1:30001` was listening, and `/v1/models` returned connection-reset/not-ready responses. This was a startup readiness window, not a confirmed runtime failure.
- `scripts/llmctl` readiness semantics were fixed so active state plus a running container with `health=starting` is reported as `manager_status: starting`, not stale, while exited containers remain `stale` and unhealthy containers report `unhealthy`.
- `scripts/llmctl start --yes` now waits up to 20 minutes for readiness by default and prints periodic container/health/port/models status lines; `--no-wait` is available when an operator explicitly wants to skip waiting.
- Final recovered state: container `sglang-qwen3-30b-a3b-instruct-2507` is `running`/`healthy`, `127.0.0.1:30001` is listening, `/v1/models` passes, and a chat completion returned non-empty content.
- Auto-start, Docker restart policy, and systemd boot policy remain deferred to a later approved milestone.

## Secret Scan

- Broad grep scan matched only intentional documentation, tests, scanner patterns, safety strings, and prior report text.
- Changed-file value-shaped scan returned no matches for real tokens, private key blocks, or password assignments.
- No real secret, token, password, private key, auth file, real `.env`, local sudo helper, `MEMORY.md`, or local Codex memory content was identified.

## No-Action Confirmations

- No model download was performed.
- No Docker image pull was performed.
- No package install was performed.
- No Docker/containerd daemon configuration was changed.
- Docker/containerd daemons were not restarted.
- The SGLang model container was not stopped or restarted.
- No public API exposure, firewall change, reverse proxy, Caddy, TLS, or auth front door was created.
- No model files or Docker images were deleted, and Docker prune was not run.

## PASS/STOP Conclusion

PASS. M9C benchmark/lifecycle/resource review completed successfully on the active local first real model.
