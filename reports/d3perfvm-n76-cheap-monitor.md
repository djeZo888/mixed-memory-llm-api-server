# D3PERFVM — one unchanged N76 short comparison

## Result and release

**COMPLETED_ONE_COMPARISON.** One exact frozen request returned HTTP 200 / finish_reason `stop`. Native decode was **6.607434 s for 64 tokens**, versus **117.054310 s for 64 tokens** in the prior N76 full-monitor sample. Decode rates using the same actual-token convention are **9.686060 vs 0.546755 tokens/s** (observed ratio **17.716×**). This is a large single-sample association with the monitoring change; it does not establish PSS causality or sustained throughput. The variant also narrows Docker inspect output and adds explicit process-start/state checks, so it does not isolate PSS collection as the only changed cost.

Sole request lease released **2026-09-15T04:32:17.515611+00:00**, after native slot release, zero API connections, exact owned request/sampler/tunnel cleanup, full final PSS, and registered guards. `../result.json` and `../lease-release.md` were written before report packaging. No VM reads or mutations followed release. Existing N76 backend remains running; installer STOPPED.

**Not occupied-context or D3T full-sample PASS.** `highest_proven_window=null`; configured capacity remains 32768. No second request, tuning, cache flush, model reload or context/config/thread/NUMA change.

## Exact comparison

| Measurement | D3N32 full monitoring | D3PERFVM cheap monitoring |
|---|---:|---:|
| Worker request UTC | 04:15:31.632344–04:18:05.849382 | 04:31:48.112009–04:32:15.601556 |
| Input tokens | 1370 | 1370 |
| Cached / evaluated | 0 / 1370 | 173 / 1197 |
| Decoded / completion tokens | 64 / 64 | 64 / 64 |
| Native prompt ms | 37115.145 | 20857.048 |
| Native decode ms | 117054.310 | 6607.434 |
| Worker wall s | 154.219367 | 27.488748 |
| Finish reason | stop | stop |

Cache/order differ: D3N32 performed three protocol/tool generations after its matched request; this replay reused the resulting native cache without alteration. Both matched requests sent identical body bytes and yielded 64 decoded tokens. Raw response hashes differ; output-text equivalence was not established. Counts were accepted as returned, with no retry for desired counts. Earlier all-CPU D3BASE (50 cached / 1320 evaluated, prompt22135.537 ms, decode112294.399 ms) is context only; the closest comparison here is N76 full versus N76 cheap monitoring.

Same container `7cde6a376f58a1dee7ad425fbd104bbd7337effa6d6943a5bfc0dbeed4bbee78`; image `sha256:86feba4c82a8ec083d8da31fb8d1648f7b221b724a48eca571f5dd277a0caab9`. PID243279, start ticks2367582, container start `2026-09-15T04:09:20.746242473Z`, restart count0, args hash `64c4ec488787da4703bc1505ff0c0955b71f05d4e1080d71b791547e669d3b95` unchanged. Deployment `glm-5.3-ud-q4-k-xl-n76-32k`;112 threads, N76, split1:1,32768/one slot, alias `glm-5.3`, existing localhost30002 publication and private LAN transport; control inactive/disabled.

Exact body SHA256 `6682c1aaae6491aaa900da3297c05e17a63bc35adbceaef310bc8ded47b1f89d`; token SHA256 `469dd72637c5825cf9cd3b936e7c7033ab0d99ed1dfb14ca94ce4db92bbe455c`. Native `/props`, `/apply-template`, `/tokenize` accounting before generation also matched frozen rendered-prompt and template hashes (see result JSON). Settings: reasoning_effort low, temperature0, max_tokens256, nonstream. Original protected body bytes were read directly, checkpoint unchanged; secret exact bytes matched in memory and stayed outside Git.

## PSS boundary measurements and live cadence

| Full existing sample, VM clock | PSS KiB | Precise RSS KiB | Swap / VmSwap KiB | Whole sample duration s |
|---|---:|---:|---:|---:|
| Before: 2026-09-15T04:31:47.940266+00:00 | 419911524 | 419911528 | 0 / 0 | 0.726186 |
| After: 2026-09-15T04:32:17.677817+00:00 | 419918208 | 419918212 | 0 / 0 | 0.720508 |

These are full helper durations, not isolated PSS timings. No PSS/smaps/rollup read occurs in the emitted live sampler. All29 cheap rows’ process-memory fields contain only status-derived `Rss` (Linux VmRSS, approximate) and `VmSwap`, and explicitly mark PSS absent during the request.

29 rows = one pre-dispatch seed, **27 while the request was active**, one post-response release observation. Active rows: first VM timestamp 2026-09-15T04:31:49.311884+00:00, last 2026-09-15T04:32:15.340057+00:00. Target1Hz; actual **0.998918 Hz**; mean interval **1.001084 s**, max **1.029116 s**. Collection min/median/mean/max **0.036077/0.039220/0.044830/0.069475 s**. No sampled pause, stale-sample failure, or >2s gap.

Prior full-monitor timestamps inside the matched window:131 rows, **0.849568 Hz**, duration median/mean **1.245199/1.082558 s**, max gap **1.535892 s**. Its first collection began before dispatch;130 inferred wholly-contained samples give0.848543Hz. The collection-duration totals are not CPU use or model-blocking time.

Every cheap row freshly checks narrowed Docker identity/args/state/ports, `/proc/PID/stat` start/state, status RSS/VmSwap, host MemAvailable/SwapFree, vmstat swap/OOM counters, GPU UUID/index/free, both exact registered ext4 mount UUIDs, root available bytes, bounded numeric container-log and kernel-error counters. Numeric startup thread/slot/graph facts are parsed from startup logs and bound to unchanged process identity; they are not remeasured kernel/thread-layout facts. Sampling is serial; each row's duration bounds its internal field-age spread. Commands retain10s child timeouts, with worker freshness and sample-gap aborts at2s; request deadline600s. Completion is polled every20ms between telemetry handling; measured wall includes polling and scheduling overhead.

Worker and VM clocks are distinct. Paired receipts suggest VM approximately0.20s ahead; no dedicated clock calibration was run. VM final PSS timestamp therefore appears slightly later than worker release timestamp despite collection/closure completing before release. Durations and cadence use within-host clocks; sample roles follow controller flow.

## Safety, interference, and ownership

- Registered guard/dependency hashes from `VM-GUARDS.json` verified with protected ownership; installed wrapper hashes matched reviewed source. Both installed `require-data-mounted.sh` and `root-disk-guard.sh --json` passed before/after. Actual registered mount identities verified; no legacy fallback.
- Minimum root free **5208326144 bytes (4.851 GiB)**: PASS above4GiB STOP, WARN below6GiB. Minimum MemAvailable **481911572 KiB**. Status RSS ranged **419911552–419918212 KiB**.
- Minimum GPU free bytes **84356890624 / 75892785152** (both above16GiB). Target VmSwap0. Host swap use stayed14080KiB; pswpin19045/pswpout35822/oom_kill0 unchanged. All numeric CUDA/OOM/storage/runtime/fusion errors0; container never sampled paused/restarting.
- D3N32 explicit request release04:20:37.752Z; final full read ended04:23:01.711Z. Final live handoff04:26:50.570Z and packaging completion04:29:24.647Z confirmed closure before admission. Requested `d3n32-lease-release.md` was absent; copied D3BASE `lease-release.md` was not used as D3N32 evidence. Distinct D3N32 `final.md`, live status and cleanup JSON were used.
- Q38DEV noGPU/device-stat container04:25:06.838309–04:25:07.177105Z, cleanup complete04:25:07.491195Z: **no request overlap**. Inner inventory04:25:07.139106121–04:25:07.139166211Z. No overlapping owned inference. Other host CPU use/steal/run queue/NUMA placement were not measured, so absence of all host interference is not established.
- Owned worker PID35013; sampler SSH35022 / VM263422; tunnel35021, port55344, isolated task `trial/ssh-control`. Request thread stopped, sampler SSH reaped and VM PID absent, tunnel reaped, port unbound, ControlPath removed. Native slot-release/stop-processing marker **04:32:15.806020433Z (VM)** and zero final API established sockets. Identity, state/recovery, instance, registry, control/network hashes and key metadata unchanged.

## Checks, preparation corrections, and handoff

Reviewed base `3acd2741635a05e42474f1b19664e477b510cf78`; branch `milestone/d3perfvm-cheap-monitor`. Task-local measurement reused existing `Transfer`, native accounting, full telemetry helpers and owned SSH cleanup; live sampler alone uses a separate cheap validator. No production source/library changes or reusable harness.

Source review caught and corrected a Docker-format quoting error before execution. All three initial task sources parsed successfully through worker SSH ai-vm; the final corrected sources then executed successfully in the actual bounded run. Initial admission stopped before any request because the newly created report directory inherited setgid mode2700; a diagnostic rerun encountered the already-created parent. The known task-owned directory was corrected to exact root0700, then admission passed. Temporary preparation STOP/result placeholders were superseded by the actual completed result. Exactly one dispatch marker and one generation exist. No general test suite, install, service/registry/closure writes, disk mutation, boot/API changes, or model operations.

Checks PASS: frozen native accounting; final immutable identity and registered guards; all cheap safety rows; full before/after samples; exact child/connection cleanup; static independent review of emitted sampler confirming no smaps/Pss/HTTP; local numeric reconciliation. These validate this bounded observation only. Source copies under `operator-code/` are historical task evidence; do not rerun this consumed one-shot task. Raw response, token arrays, original body and key remain private outside Git; sanitized hashes/numbers only are published.

**Next action:** Root chooses the next separately authorized Qwen/native-context stage using the released lease. Stop this experiment here. The result supports investigating sampler overhead, but one ordered sample with different cache history and unmeasured host scheduling does not isolate PSS as the cause.
