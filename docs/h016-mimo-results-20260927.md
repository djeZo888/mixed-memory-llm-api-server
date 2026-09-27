# MiMo Pro-RL qualification — 27 September 2026

Original window: **10:48:08–13:48:08 UTC**. The user extended it by two hours
to **15:48:08 UTC** to investigate slow decode. This report is an intermediate
checkpoint; the full 4K/16K/64K ladder is complete, while profiling is in progress.

## Candidate and completed work

- `AesSedai/MiMo-V2.6-Pro-RL-GGUF`, revision
  `ba4eabb78b6c51ffd873ec73b9e12b0f64aced5d`.
- All **13 shards / 577,669,438,240 bytes** verified. The last retained partial
  file passed its hash; no replacement download was necessary.
- Native MXFP4 experts, BF16/F32 nonexperts: 207 MXFP4, 163 BF16 and 357 F32
  tensors. This is not a full-BF16 checkpoint or a new lower-bit conversion.
- Reused the pinned llama.cpp `7ac59a6` / CUDA 13.2.1 / SM120a image. One fast
  Blackwell holds eligible nonexpert layers; CPU experts use ordinary RAM across
  the eight guest NUMA nodes. The CPU set has 64 guest threads.
- The corrected load completed at **12:48:55 UTC**. Basic thinking/nonthinking
  text, a native tool call and its result continuation passed.
- The harness engine overlay is built. The single production owner and node
  status changes passed **68 offline tests**; live lifecycle and application
  acceptance are still separate requirements.

## Benchmarks

All measured rungs use the same **131,072-token configured window**, F16 KV
cache with compact sliding-window storage, CPU-MoE placement, batch/ubatch
2048/512, thinking disabled and a 256-token output ceiling. A varied 4K warm-up
was discarded, and measured fixtures have fresh prefixes. Inputs contain
early/middle/end retrieval codes and verifiable arithmetic.

| Actual input | Actual output | Input tokens/s | Output tokens/s | TTFT | Complete request | Result |
|---:|---:|---:|---:|---:|---:|---|
| 4,096 | 41 | 61.08 | 0.914 | 67.35 s | 111.13 s | PASS |
| 16,384 | 55 | 60.76 | 0.913 | 269.96 s | 329.10 s | PASS |
| 65,536 | 45 | 61.06 | 0.913 | 1,073.56 s | 1,121.75 s | PASS |

The 4K native prefill was 67.062604 s; native decode was 43.776971 s. The
native output rate counts 40 decode intervals for 41 reported output tokens.
Cached input was zero. The response ended normally, with usage, DONE and the
entire HTTP response received. This throughput does not establish superiority
over GLM Flash or quality on general engineering tasks.

During the measured 4K interval, 22 telemetry samples covered 106.51 seconds.
CPU use averaged **54.8 cores**. Major faults, page scans/steals and file refaults
did not increase. This supports resident execution without the earlier paging
stalls; it does not identify why decode remains slow.

The 16K run finished at 13:05:38 UTC. Its prefill took 269.654 seconds and
decode 59.140 seconds, with zero cached input. A thin benchmark runner initially
refused 64K because it treated any cache reclamation as a stall. The observed
272 MiB of clean file-cache reclamation caused no major faults, refaults or
storage reads, and throughput was unchanged. The gate was narrowed using those
measurements; the completed 16K test was not repeated. A separate 64K-only job
was dispatched at 13:10:12 UTC and completed at **13:28:56 UTC**. Native
prefill took 1,073.242495 seconds and decode 48.187979 seconds, with zero
cached input and normal stop/DONE/full HTTP drain. Basic retrieval/arithmetic
checks passed. The native client then settled while the original R5 model
remained loaded. Decode is consistently slow across all three input sizes.

After warm-up, a sample showed **46,482 MiB (45.39 GiB) device-used VRAM**,
approximately **533.89 GB anonymous host allocation**, and **194.79 GB file
cache**. Total cgroup memory was approximately 730.39 GB. File cache is
reclaimable and is not another copy of resident anonymous model demand;
cgroup counters are not process RSS. Per-rung peaks and larger-context
estimates remain pending. No owned swap or OOM was observed in these samples.

## Issues that consumed the window

1. The first load's identity check compared the raw template with the runtime's
   normalized template. The pinned lexer removes one final newline. Raw and
   effective identities are now recorded separately.
2. NUMA mmap loading disabled prefetch and used random access. Model pages were
   repeatedly reclaimed and read from storage. The cold timings are retained,
   but are not reported as warmed model performance.
3. Explicit loading exposed a monitor defect: a synchronous `numa_maps` read
   blocked mandatory checks. Expensive placement inspection now runs separately
   with a short bound; mandatory monitoring uses cheap counters.
4. The next explicit load selected a huge CUDA-host buffer. The pinned source
   routes CPU-MoE tensors through `cudaMallocHost` unless `--no-host` excludes
   that preference. A driver-query timeout stopped the attempt. Adding only
   `--no-host` produced ordinary anonymous allocation, completed loading and
   successful inference. No weights, quantization or driver were changed.

Each failed attempt's exact native process was settled before retrying; original
GLM recovery evidence is retained. The source-supported CUDA allocation cause
is stronger than the observed timeout alone, but the failed attempt did not
reach its final buffer-name log.

## Extended decode investigation

The user requested actual CPU/GPU utilization, host DRAM and GPU memory
bandwidth, source comparisons and targeted runtime optimizations. Decode
averaged about58 sampled CPU cores, so a single active CPU thread does not
explain the result. Selected optimized CPU backend/ISA is not yet proven by
the captured logs. Sampled GPU utilization is low; hardware-counter profiling
is needed before assigning a cause. Utilization percentages, theoretical
bandwidth and measured GB/s must remain distinct.

The existing R5 owner still settles at13:40; changing source files cannot extend
its already-imported deadlines. A fresh reviewed profiling owner may follow,
with15:15 admission and15:35 settlement boundaries. No repeated large-context
benchmarks or unreviewed settings sweep is planned.

## Integration and capacity limits

The actual MiniMax 17-tool schema was counted at 9,461 input tokens. That is
**count-only** evidence; native generation with the complete roster and the
65,536 output setting, plus real harness delegation, are still pending.

The candidate harness shares the existing frontier queue with GLM. Qwen remains
the coordinator and usual coding worker. This first MiMo integration buffers
frontier response text until stream validation completes; progressive MiMo text
display is not implemented. Ambiguous requests are held without automatic replay.

Published model context, configured allocation and largest completed input are
reported separately. A configured 131K window and completed 4K/16K/64K inputs do not
prove 1M capacity or long-context correctness. No occupied 1M test is authorized
in this window. The existing GLM 1M test will not be repeated.

Sova's application is paused while this work runs. User histories and files are
preserved; the original GLM and harness release remain the rollback. No new
four-way stress test, BMC/fan/ECC change, driver change or reboot was performed.

## Evidence

- [Execution plan](h016-mimo-integration-window.md)
- [Native attempts and correction](../reports/h016-20260927/worker1/phase3/PHASE3-CHRONOLOGY.md)
- [Ordinary allocation snapshot](../reports/h016-20260927/worker1/phase4/STATUS.json)
- [Harness integration source](../reports/h016-mimo-integration-20260927/REPORT.md)
- [Single-owner source and test limits](../reports/h016-production-owner-20260927/REPORT.md)

Credentials, model shards and bulky traces remain outside Git.
