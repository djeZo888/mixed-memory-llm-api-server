# Actual native startup evidence

One read-only snapshot at 2026-09-27T13:17:49.447621+00:00. Docker logs were filtered for CPU/ISA/backend, buffer, context and timing lines. The retained result contains no CPU tensor-buffer size/name or selected optimized CPU variant. These remain UNAVAILABLE, not disproved. No new profiling, process-map scan, runtime invocation, rebuild or load was performed.

The retained load_model line proves one slot and n_ctx_slot=131072 at12:48:55.305845552Z. Launch source requests --cpu-moe, --no-host, --load-mode none; source buffer-selection preference is not actual buffer or ISA selection evidence. CPU capability symbols likewise are not selection evidence.

Latest64K progress: 2026-09-27T13:17:27.290464430Z 39.49.978.301 I slot print_timing: id  0 | task 249 | prompt processing, n_tokens =  26624, progress = 0.41, t = 432.20 s / 61.60 tokens per second
