# H026 quick Qwen power-cap comparison

Both Qwen cards completed one 600 W warm-up and the measured **600/550/500/600 W** sequence, sequentially, between **21:14:36 and 21:18:54 UTC on 2026-09-28**. All ten accepted requests reached terminal SSE, full HTTP EOF and unchanged native owner/readiness settlement. No telemetry/thermal guard fault occurred. Both original configured/enforced limits were restored to **600 W** before shutdown.

Native W1 session `01a0e9d7-255c-7153-907a-b9136e22c032`; base `776a135`. Successful unit `h026-caps02.service`, PID2845647, invocation `0ae9605eebdf4ffd94e9e598c82da777`. No GitHub push.

## Measurements

| GPU | Cap W | Prompt/output | TTFT s | Prefill proxy tok/s | Decode proxy tok/s | Mean/peak board W | Peak C |
|---|---:|---:|---:|---:|---:|---:|---:|
| qwen0 | 600 | 63978/512 | 9.637 | 6638.5 | 36.58 | 445.0/600.3 | 63 |
| qwen0 | 550 | 63979/512 | 10.358 | 6176.5 | 37.02 | 421.4/550.5 | 68 |
| qwen0 | 500 | 63974/512 | 11.233 | 5695.4 | 36.73 | 416.8/500.0 | 70 |
| qwen0 | 600 | 63977/512 | 10.014 | 6388.7 | 36.97 | 454.6/610.1 | 74 |
| qwen1 | 600 | 63975/512 | 8.839 | 7237.5 | 38.02 | 410.0/606.5 | 67 |
| qwen1 | 550 | 63979/512 | 9.154 | 6989.6 | 37.70 | 400.6/553.9 | 71 |
| qwen1 | 500 | 63977/512 | 9.532 | 6711.7 | 37.59 | 384.0/513.4 | 69 |
| qwen1 | 600 | 63981/512 | 8.909 | 7182.0 | 37.62 | 403.7/603.6 | 73 |

The second 600 W row is the final drift anchor. Warm-ups are excluded above and retained in RESULTS.json. Actual inputs were 63,974–63,981 native tokens; all ten outputs were exactly 512 tokens with native finish reason `length`. Temperature peaked at 74 C across the run. No hardware/software thermal or hardware power-brake slowdown was sampled. Software cap flags on Qwen0 are retained in RESULTS.json; Qwen1 did not report that flag in these samples.

Relative to each card's first measured600 W:

| GPU/cap | Prefill proxy change | Decode proxy change | Mean board-power change |
|---|---:|---:|---:|
| Qwen0 550 W | -6.96% | +1.22% | -5.31% |
| Qwen0 500 W | -14.21% | +0.41% | -6.35% |
| Qwen0 600 W anchor | -3.76% | +1.07% | +2.14% |
| Qwen1 550 W | -3.43% | -0.83% | -2.29% |
| Qwen1 500 W | -7.26% | -1.13% | -6.33% |
| Qwen1 600 W anchor | -0.77% | -1.03% | -1.54% |

500 W looks usable for this short workload when lower board power matters more than prompt latency.550 W offers a smaller prompt-latency penalty. The decode differences are comparable to anchor drift and do not establish a cap-related decode effect. Qwen0's3.76% prefill-proxy anchor drift also limits precision. This single sequence supports a tradeoff discussion, not a permanent cap recommendation or statistical performance qualification. No reruns or permanent power policy were applied.

## Definitions and limits

No native prompt/decode timing fields were supplied. **Prefill proxy** = actual prompt tokens / dispatch-to-first-nonempty-output seconds; this includes upload, admission, native prefill, first decode and client overhead. **Decode proxy** = (actual completion tokens -1) / (last minus first nonempty-output arrival). Stream chunk batching and buffering affect it; neither column is native stage throughput. Dispatch, send-start, body-sent, headers, first/last output and full EOF times are retained privately and compact transport clocks are public in RESULTS.json.

Power is the arithmetic mean/peak of approximately1 Hz same-request GPU **board** readings. It excludes CPU, wall/PSU losses, transients and simultaneous multi-GPU workload qualification. Readback caps were correct; observed sample peaks can exceed the configured number, as the table records. This is not a hard instantaneous electrical ceiling or whole-PSU qualification.

The same six-word neutral corpus and output instruction were used with a fresh leading nonce per request, temperature0, thinking off and512 output target. Every final body was independently counted through the authentic native `/v1/tokenize` route; only stream transport fields were omitted. Token-ID, body and existing template hashes were preserved. Both480K runtime profiles, weights/cache settings and exact UUID assignments stayed unchanged. Native readback confirmed radix caching already disabled; it was not changed. Request count matched native response prompt count in every row. Request IDs are the unique sample IDs in RESULTS.json.

## Source, guards and settlement

`caps.py` reuses the existing benchmark client/parser. The narrow client change records send/body/header times and distinguishes unsent cancellation from an uncertain partial send. Seventeen focused client tests passed, including those dispatch cases and full-EOF clock ordering. Parallel source review findings were fixed before inference; final caps SHA256 `af020c844633a2777351d428468ec568f057f135fbf5b9647c47dff2c1c6f9e9`, client `0a922fafc8a842c09ac4ea1a573c09546e586d4858f6cb2d32c3704b4ac4feed`.

The independent one-shot VM unit retained an85 C cutoff, one-second GPU/fan samples, a separate five-second telemetry watchdog,180-second request deadline,21:23 admission cutoff and UUID-only cap setters. The helper's nested cleanup and systemd ExecStopPost restore both600 W limits. Existing cooling controllers stayed running. External fan status used its independent private controller file, including exact UUID/source-bit/mode and freshness checks. Natural40→80→40 behavior was observed without controller writes by this helper.

Successful settlement uses the pinned adaptive-drain source contract, complete valid terminal SSE/usage/DONE/full EOF, exclusive quiet ingress and exact same owner/readiness/capacity afterward. It is **not a native global-idle claim**. No runtime stop or accepted-request replay was needed. Counter sums, positive stream intervals, observer OK, empty report errors and absence of reasoning/tool deltas were validated for all ten rows.

An initial setup attempt failed **before HTTP dispatch**, because the private raw directory inherited mode2700 and the existing client requires exactly0700. Its empty raw directory, failed intent, source, telemetry and600 W restoration receipts are preserved in `attempt01-unsent` inside the private archive. Correcting the directory mode preceded the separately identified caps02 attempt; no uncertain inference was replayed. The successful run did not overwrite this failure history.

## Preservation and authorized shutdown

Before quieting,73 runs and20 image jobs were terminal,118 gateway requests were settled, all gateway lanes were idle and image uncertainty was0. Their relevant table hashes were unchanged after measurement, as were the three historical quarantines. Normal app stop changed the image lane from idle to quarantined with uncertainty0; no manual history/hold edits occurred. App/status enabled states were preserved; search and cooling stayed active through measurement.

The later user instruction authorized shutting down both VMs for the hardware work and superseded upper-service restoration. The exact task-created upper restore timer was cancelled. At21:19:25 bothQwens retained original generations/PIDs41/2511660 and37/1844069,480K capacity and readiness; retainedGLM and image were also resident/ready. GLM readiness does not overturn H025's failed16K inference. No frontier selection, Ada, BMC, fan policy, model, profile, context, cache or persistent TDP change was made.

Full source, request/SSE bodies, telemetry and both attempts were copied to the Mac before shutdown; the coordinator acknowledged its copy. Own fan bridgePID80695 was terminated. `sudo systemctl poweroff` on ai-vm returned0 at21:20:08.656 UTC; SSH was unavailable at21:20:11.863. This proves accepted normal shutdown plus SSH disappearance, not a Proxmox/hardware power-state observation. W2 received release to shut down ai-harness only after that receipt; its shutdown is independently owned by W2.

See RESULTS.json for metrics, FINAL-VERIFY.json and RESTORE.json for pre-shutdown state, VM-SHUTDOWN.json for shutdown evidence, and PRIVATE-EVIDENCE-MANIFEST.json for retained private artifacts. All accepted requests finished by21:18:54; no additional workload is pending.
