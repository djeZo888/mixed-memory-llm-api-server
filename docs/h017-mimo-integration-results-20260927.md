# MiMo production integration — 27 September 2026

## Current state

**In progress.** The authorized foreground window is 19:07:11–21:07:11 UTC
(21:07–23:07 Ljubljana). A 950K ordinary-service load stopped at 19:44 UTC
because an aggregate host-swap guard fired. After exact settlement and a
reviewed correction, the ordinary service restarted at 19:58:45 UTC. It reached
READY at 20:10:08 with an actual usable 950,000-token slot. The independent
short qualification started at 20:10:18 and returned the correct two-token
answer with full stream completion. At 20:10:22 the ordinary supervisor failed
in its resource-validation stage, before the tool-call request was submitted.
Its exact process/cgroup/GPU allocation was released. One final diagnostic
attempt started at 20:23:57 with unchanged resource checks and additional safe
exception detail. The cause remains unknown; this is not a demonstrated repair.
Sova is paused and the long-context job has not started.

Worker1 operates ai-vm; Worker2 operates ai-harness and independently reviews
the service changes. Root coordinates, reviews and publishes. Original chats,
files, quarantines and the GLM/Sova rollback pair are preserved.

## Selected model and settings

- MiMo V2.6 **Pro-RL**, `AesSedai/MiMo-V2.6-Pro-RL-GGUF`, revision
  `ba4eabb78b6c51ffd873ec73b9e12b0f64aced5d`; all 13 shards previously verified.
- Native MXFP4 experts and BF16/F32 nonexpert tensors. No additional
  quantization or replacement download in this window.
- Existing llama.cpp `7ac59a6` / CUDA 13.2.1 / SM120a runtime, one fast Blackwell
  plus system RAM, eight decode threads, 64 batch threads and `GOMP_SPINCOUNT=0`.
- F16 attention cache and eight-node host interleave remain unchanged.
- Capacity reduced from 1,000,000 to **950,000**, confirmed by native props and
  the private slot response. Calculated physical cache padding is 950,016;
  that padding is not additional usable context.
- Qwen remains the coordinator and normal coding model. MiMo is intended for
  selective difficult tasks. Both Qwen instances retain 480K contexts; image
  generation remains on Ada. GLM is retained for explicit rollback.

## Existing performance evidence

These completed tests used the selected eight-thread settings with a
**1,000,000-token configured window**, before H017. They are not new 950K or
long-context measurements.

| Actual input | Actual output | Input tokens/s | Output tokens/s | Total time |
| ---: | ---: | ---: | ---: | ---: |
| 4,096 | 47 | 71.49 | 9.58 | 62.42 s |
| 16,384 | 45 | 69.56 | 9.41 | 240.55 s |

Warm-up was discarded, measured prefixes were fresh, and retrieval/arithmetic,
terminal streaming and native idle checks passed. A native tool call and its
result continuation also passed. The separate fixed-output comparison measured
9.210 output tokens/s with eight threads versus 6.764 with four threads.

At the old 1M allocation, sampled device VRAM peaked at **89,770 MiB**, leaving
7,481 MiB free. That exceeded the agreed 7% free reserve by only 628.91 MiB.
The reduced capacity was projected to save about **2.39 GiB** of cache allocation.
At actual 950K readiness, GPU memory was **87,160 MiB used**, 638 MiB reserved
and **10,091 MiB free (10.31%)**, at 36°C. This is an idle allocation observation,
not an occupied near-950K inference peak. Cgroup memory was 634.02 GiB including
file cache, host available memory was 358.26 GiB, and owned swap/OOM were zero.
Historical cgroup memory peaked at
573.37 GiB including reclaimable file cache, with anonymous memory peaking at
497.28 GiB at its own observation time. These different maxima must not be added.

See the [historical benchmark report](h016-mimo-results-20260927.md) for full
conditions, memory definitions and the incomplete earlier integration attempt.

## Service work in this window

The earlier supervisor could lose its original exception when cleanup raised
another exception. Cleanup contention could also invent a sticky request hold
even when no proxy or request had existed. The reviewed correction preserves
the original and cleanup diagnostics separately, bounds acquisition of the
existing lifecycle lock, and preserves genuine request uncertainty.

Proxy disposition is now checked after the exact child stops; an earlier idle
snapshot cannot prove that no request arrived before termination. Repeated
cleanup preserves prior same-launch, same-manifest settlement evidence only as
history when a fresh lock acquisition times out. A failed recheck still raises;
rollback continues to require fresh physical release evidence.

Both workers replayed ordinary readiness against genuine saved native responses.
Those checks pass, but do not identify the earlier hidden primary error. The
source corrections passed focused regressions and independent review.

The first H017 start refused before creating a model process because the stored
GPU health proof was unavailable. A subsequent legitimate fresh proof passed,
and the corrected start loaded with unchanged reviewed source. The transient
refusal is retained; no hardware latch was cleared or guard disabled. It is not
established as the cause of the older H016 failure.

The new error reporting then exposed the loading failure at 19:44:02:
`added_host_swap`. That comparison watches whole-host swap, independently of
MiMo's cgroup. The last healthy sample five seconds earlier showed **zero owned
swap**, approximately **652 GiB host available**, and a 35°C frontier GPU.
Existing host swap was 97.5 MiB; the later observation was only **768 KiB**
higher, with current memory-pressure averages zero. The exact failing sample
and process attribution were not retained, so these facts do not attribute
swapping to MiMo. The deployment prohibited owned swap (`memory.swap.max=0`)
and the last healthy sample confirmed none in use.

The narrow correction keeps aggregate host swap as numeric telemetry while
retaining zero owned swap/OOM, unchanged swap configuration and the host/GPU
reserves. It also saves the numeric sample on future resource-check failures.
Focused regressions pass. No kernel, swappiness or host-swap settings changed.
The failed process, cgroup and GPU allocation were fully released before the
corrected start; no inference had been admitted.

The subsequent 20:10 failure had code `unexpected_error` in resource validation.
It preceded the qualification client's failure. The client had fully received
the correct tiny text answer and had not submitted its next tool-call request.
Saved allocation and last-good samples all pass offline replay. No failing
sample or exception class was retained, so its cause cannot be inferred from
those healthy snapshots. The diagnostic-only revision records an allowlisted
exception class, the owner source line and bounded numeric fields, without
exception text, credentials or locals. Its resource predicates are unchanged.

Sova was paused normally at 19:29 UTC. Its 26 chats, 133 messages, 62 file records
and 17,597 non-database files matched their preserved records. Worker2 closed
its preparation CLI while waiting for native qualification. No dependency or
native runtime rebuild is planned.

## Remaining acceptance and final job

1. Actual 950K props/slot, memory reserve and short native tool continuation.
2. Minimal Sova profile/configuration layer over the existing accepted image.
3. Real Qwen parent → MiMo child/tool result → Qwen verification, followed by
   ordinary Sova activation and preservation/health checks.
4. As the last task, one independent Linux systemd client runs optimized 64K,
   then near 950K only after correctness, terminal/drain, idle and resource
   checks pass. At 950,000 usable capacity the near-limit input target is
   948,975 tokens with a 1,024-token answer allowance and one spare slot.

The final job has one total eight-hour deadline and no automatic replay. After
startup is verified, paid worker sessions close and the automation stays paused.
The user will request a later result check. Allocation and small-context success
do not establish near-maximum speed or correctness.
