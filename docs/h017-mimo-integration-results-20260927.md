# MiMo production integration — 27 September 2026

## Current state

**MiMo integration remains incomplete; the working GLM-backed Sova service was
restored.** The two-hour foreground window is 19:07:11–21:07:11 UTC
(21:07–23:07 Ljubljana). GLM authenticated readiness passed at 20:45:14;
the original Sova application was restored at 20:48:10. Its health, status and
system endpoints returned HTTP 200, and the existing observer reported GLM,
both Qwens and image ready. Chats and files were preserved.

MiMo loaded successfully with 950,000 usable tokens twice, and each attempt
returned a correct tiny text response. Its supervisor then failed during a
swap-limit check. The diagnostic attempt identified `ValueError` at
`int(cg['memory.swap.max'])`; the exact nonnumeric value was not retained.
No current 950K tool continuation or Sova delegation acceptance passed.
**Neither the optimized 64K test nor the near-950K test was launched.** There
is no background benchmark for the user to wait for. No further model load or
live investigation is included in this window.

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

## Located failure and next repair

The last diagnostic load started at 20:23:57 and reached READY at 20:35:08.
The tiny 14-input/two-output response fully drained at 20:35:22.995940.
At 20:35:24.460174 the owner raised `ValueError` on line 455, converting
`memory.swap.max` to an integer. Numeric-only diagnostics omitted the offending
value. The model's captured swap usage and OOM counts were zero; available host
memory was 358.19 GiB. This was not a demonstrated model OOM or inference failure.
A separate cleanup timeout was retained; subsequent exact process, cgroup,
GPU and proxy release passed, with no uncertain request left active.

Both short-test launch helpers run `systemctl daemon-reload` after model
readiness. An upstream [Moby issue](https://github.com/moby/moby/issues/51446)
documents that operation changing Docker's `memory.swap.max` from `0` to `max`
with the systemd cgroup driver. This is a strong explanation to test, **not a
locally proven cause**: our failing raw value was not captured and no controlled
reproduction was performed. A literal `max` is a valid Linux cgroup value but
would violate this model's intended zero-swap policy.

The next bounded task should reproduce the limit transition with a disposable,
small container before paying for another model load. Preserve zero-swap
enforcement across systemd reloads, classify `0`, `max`, empty and invalid
values without an uncaught conversion, and preinstall test units before loading
MiMo. Do not treat `max` as zero or weaken the limit simply to avoid the crash.
This repair and its deployment remain pending.

Repeated loading of the roughly 578 GB checkpoint took about eleven minutes
per full load. The window was spent on supervisor/settlement corrections and
diagnosing service failures; no model download, runtime rebuild, new thread
sweep or long benchmark consumed this window. Small native responses alone do
not establish a reliable persistent service.

## Recovery and remaining acceptance

Original GLM selection generation 8 and source/configuration were restored.
GLM remains at 1,048,576 tokens; both Qwens remain at 480,000. Sova retains
release `7143c17` / image `9ef8859`. The two Qwen and image containers were not
recreated. Normal Sova startup reconciled the idle image lane; it did not clear
historical quarantines. The preserved data includes 26 chats, 133 messages,
62 file records and 17,597 non-database files. Restoration used readiness and
preservation checks, with no new inference requests.

Remaining work is: the swap-limit lifecycle repair, current 950K native tool
continuation, and actual Qwen parent → MiMo child → Qwen verification using the
prepared Sova release. Only after these pass should a new final independent job
run optimized 64K followed by near 950K. The prepared target is 948,975 input
tokens with a 1,024-token output allowance and one spare slot, within one total
eight-hour background cap. Its dispatch authority is inactive and must be
renewed for a new execution window; old expired acceptance clocks are not valid.

Paid worker sessions close after recovery/publication, and the existing
automation stays paused. Credentials, complete streams and bulky traces remain
private. Exact sanitized failure and GLM recovery evidence is in
[`reports/h017-final-receipt05-20260927`](../reports/h017-final-receipt05-20260927).
The [Sova recovery receipt](../reports/h017-final-integration04-20260927/ORIGINAL-RECOVERY.json)
records health, all four model instances, preserved data and zero recovery
inference. Worker1's final CLI stopped at its 20:46 cap after backend recovery;
Worker2's final recovery CLI exited successfully at 20:51:24. No paid worker
session remains waiting for a model or benchmark.
