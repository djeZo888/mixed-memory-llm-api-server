# MiMo Pro-RL qualification — 27 September 2026

Original window: **10:48:08–13:48:08 UTC**. Two two-hour extensions and a further45minutes for4/conditional2-thread tests
make the current final deadline **18:33:08 UTC /20:33Ljubljana**. The optimized eight-thread profile passed native4K/16K and tool continuation at
1,000,000 usable context. Ordinary production startup subsequently failed, so
MiMo is **not yet enabled in Sova**. The unchanged GLM-backed Sova
release was restored at18:21:23UTC, with health/status checks and preserved chats/files. Optimized64K and near1M have not started.

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

## Historical ladder before the output-speed correction

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
cgroup counters are not process RSS. The 64K rung's sampled cgroup maximum was
680.006 GiB: anonymous memory reached 497.265 GiB, file cache 181.142 GiB and
kernel memory 1.599 GiB. Host available memory stayed above 356.016 GiB.
Device-used VRAM stayed at 46,482 MiB; maximum frontier temperature was 51°C.
No owned swap or OOM was observed. Exact 16K/64K request boundaries show zero
storage-I/O and major-fault growth; the 4K request lacks exact I/O boundaries.

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
averaged about 58 sampled CPU cores, so a single active CPU thread does not
explain the result. A live mapping confirms `libggml-cpu-zen4.so`; generic CPU
fallback is unsupported by the evidence. Sampled GPU utilization was 0–4%.
The guest exposes no AMD memory-controller PMU. The user has now enabled the
host's existing `amd_uncore` module and installed `perf` 6.12.107. All eight
host UMCs and their read/write CAS events are visible; a measurement aligned
with decode is still pending. Utilization percentages, logical weight bytes
and measured bandwidth must remain distinct.

R5 settled at 13:40:11 and original GLM readiness was restored at 13:42:07.
R6 completed two short output fixtures after a discarded warm-up. Both used
83 input tokens and produced 128 output tokens, with the same 131K allocation:

| Sample | Output tokens/s | TTFT | Complete request |
|---|---:|---:|---:|
| Unprofiled baseline | 0.9352 | 3.445 s | 139.241 s |
| CPU-profiled request | 0.9823 | 3.394 s | 132.683 s |

Raw stream arrivals agree with native decode timing within 3 milliseconds.
This rules out a client-side pacing explanation for these samples. The second
sample ran after additional warming and produced different text; its 5% higher
rate is not a demonstrated profiler benefit or an optimization result.

**94.56% of sampled CPU time was in two OpenMP spin-wait loops**, resolved
against the actual mapped `libgomp` binary and disassembly. Another 4.28% was
in the repacked MXFP4 CPU GEMV kernel. The profile consumed 59.11 CPU-core
equivalents at IPC 0.13. This proves that the high CPU utilization largely
represents waiting, but does not mean 94.56% of wall time is recoverable or
identify the underlying reason for each wait. GPU SM activity averaged 2.89%.
The available PCIe traffic and GPU activity counters are not VRAM bandwidth.

R6 settled normally and GLM readiness was restored at 14:25:33. R7 started at
14:28:05 with exactly one runtime change: `GOMP_SPINCOUNT=0`. It retains the
same 64 threads, NUMA placement, weights, kernels, GPU and fixtures. Startup
guards and the actual environment passed readback. The completed unprofiled
128-token sample reached **5.885 output tokens/s**, versus 0.935 before the change.
A longer, unprofiled 512-token sample reached **6.005 output tokens/s** in
87.48 seconds overall. These capped responses measure throughput, not quality.
The profiled 128-token sample reached 3.364 tokens/s; instrumentation and run
order affect that comparison, so it is not the production-speed estimate.
The paid launcher session exited at 14:32:20 while the bounded native owner
continued. Admission closes at 15:15 and settlement begins by 15:35.

The R7 CPU profile averaged 8.59 core equivalents at IPC 2.53. The earlier
spin loops no longer dominated; scheduler transitions and MXFP4 matrix work
became the largest sampled costs. Whole-container lifetime memory peaked at
611.33 GiB, including reclaimable file cache; the latest split was approximately
497.25 GiB anonymous memory, 112.81 GiB file cache and 0.98 GiB kernel memory.
Owned swap remained zero and the frontier GPU reached at most 46°C.

The further single-variable trial selected **16 decode threads**, retaining
64 input-processing threads and all other inference settings. On the identical
83-input/128-output fixture, R8 reached **7.763 output tokens/s**, 31.9% faster
than R7. Prefill took 2.140 seconds, decode 16.359 seconds, TTFT 2.457 seconds
and the complete request 18.816 seconds. Cached input was zero, and terminal
stream evidence and subsequent native-idle readback passed. The response hit
the output ceiling, so this remains throughput evidence rather than a quality test.

The request boundary averaged 9.25 CPU-core equivalents, with no major faults,
storage-read growth, owned swap or OOM. The frontier GPU reached 42°C and
23% utilization in the available samples. Thread affinity observations do not
by themselves identify which workers were active, and activity is not bandwidth.

The user next requested two eight-thread trials: one decode CPU per guest NUMA
node versus eight on guest node0. Both retain 64 batch threads and external
memory interleave; GGML's NUMA affinity override is disabled so distinct strict
decode masks can take effect. Their actual thread placement must be checked.
Guest node0 is not proof of physical GPU-local execution because Proxmox's
aggregate CPU mask does not establish individual vCPU pinning. The spread-eight trial completed at16:38UTC with **9.210 output tokens/s**,
18.64% above the16-thread result. The identical83-input/128-output fixture had
2.125s prefill,2.443s TTFT and16.232s total duration, with zero cached input,
DONE/full HTTP drain and native-idle confirmation. This is a whole-profile
comparison because GGML NUMA affinity also changed. It is a length-capped
throughput sample, not a quality evaluation;10tokens/s remains unproven.

The affinity classifier reported INCONCLUSIVE because the initial snapshot
straddled the batch-to-decode transition and several unrelated threads exited.
Four later saved snapshots show eight substantially active threads pinned to
singleton guest CPUs0,16,24,32,40,48,56,64. These observations do not establish
physical-host vCPU pinning. The guest-node0-only trial was not admitted within
its remaining time budget. The user subsequently requested four decode threads
and two only if four beats eight. The four-thread result is now complete, as recorded below.

A new 4K/16K/64K ladder will use the selected settings and final allocated context.
The first allocation target is decimal 1,000,000 tokens; 917,504 is the fallback
if actual allocation or workspace fails the 7% GPU reserve. Native cache padding
to 256-cell blocks may make the physical pool 1,000,192 positions. Usable slot
capacity and physical pool size will be reported separately.

The user-supplied 20-second Proxmox capture began at 14:54:34 UTC, after MiMo
had stopped generating. Its four intervals estimated 1.61, 1.66, 4.84 and
1.63 GB/s across the whole host. This is an **idle baseline, not MiMo bandwidth**.
All eight controllers supplied read/write counters without multiplexing.
The conversion follows Linux's Zen5 estimate of 64 bytes per CAS command.
A coordinated decode capture is deferred until the user returns.

See the [resolved profile and launch evidence](../reports/h016-20260927/worker1/profile8/HANDOFF.md).
No repeated large-context benchmark, GPU-profiler injection or unreviewed
settings sweep was used for this A/B test.

The [pinned-source review](../reports/h016-mimo-decode-research-20260927/REPORT.md)
found no inspected token-rate limiter. `OMP_NUM_THREADS=1` also does not prove a
single-thread graph: the OpenMP graph requests its thread count explicitly.
The closest published Pro result uses a GB300 with coherent Grace memory;
its approximately 30 tokens/s cannot serve as a target for PCIe CPU-expert
execution. A reported 18.6 tokens/s result is MiMo Flash with eight GPUs and
most expert layers GPU-resident, also a different workload and architecture.

## Integration and capacity limits

An initial native request using the full MiniMax 17-tool roster and the 65,536
output ceiling generated a response, but the session-bound receiver was
interrupted before saving the complete stream. Tool execution and continuation
did not run. This is an orchestration failure and **does not qualify integration**.
Future clients run as independent Linux services with durable receipts. The
full check will run at the selected final settings, followed by real harness
delegation and independent parent verification.

The candidate harness shares the existing frontier queue with GLM. Qwen remains
the coordinator and usual coding worker. This first MiMo integration buffers
frontier response text until stream validation completes; progressive MiMo text
display is not implemented. Ambiguous requests are held without automatic replay.

Published model context, configured allocation and largest completed input are
reported separately. A configured 131K window and completed 4K/16K/64K inputs do not
prove 1M capacity or long-context correctness. The latest user instruction
authorizes a near-1M-input test as the final independent background task after
native and Sova qualification. To avoid paid observation of another long prefill,
the final job runs the optimized64K rung first, and near-1M only if64K passes.
Foreground qualification records the actual4K/16K results and native tools;
64K and near-1M remain explicitly pending until their saved results exist. Its prompt must reserve answer/template space
inside the actual usable window. After startup is verified, paid sessions and
automated checks will stop; results await the user's later nudge. The existing
GLM 1M test will not be repeated.

The planned production MiMo budget is eight hours per active inference request,
with a separate 30-minute queue and an eight-hour-31-minute provider limit.
Qwen and GLM keep their existing limits. This requires changes through stream
drain as well as connection setup; long context must not fail solely because a
shorter transport timer remained in place.

At fixed placement, the source-derived global F16 cache grows by 51,200 bytes
per configured token; compact sliding-window storage is a separate fixed
component. Holding other allocations constant predicts 86,162 MiB device-used
at 943,718 tokens, 88,910 MiB at decimal 1,000,000, and 91,282 MiB at 1,048,576.
The last misses the required 7% free-VRAM reserve by approximately 883 MiB,
before any additional workspace growth. Decimal 1M has only about 1.45 GiB
remaining above that reserve. These are allocation estimates, not tested
capacities or speed/correctness predictions.

Sova was paused during the attempted integration and is restored at the final
checkpoint below. User histories and files are preserved. No new
four-way stress test, BMC/fan/ECC change, driver change or reboot was performed.

## Evidence

- [Execution plan](h016-mimo-integration-window.md)
- [Native attempts and correction](../reports/h016-20260927/worker1/phase3/PHASE3-CHRONOLOGY.md)
- [Ordinary allocation snapshot](../reports/h016-20260927/worker1/phase4/STATUS.json)
- [Harness integration source](../reports/h016-mimo-integration-20260927/REPORT.md)
- [Single-owner source and test limits](../reports/h016-production-owner-20260927/REPORT.md)
- [R7 output-speed correction and receiver incident](../reports/h016-20260927/worker1/profile9/HANDOFF.md)
- [Staged harness and held activation](../reports/h016-final-integration-20260927/REPORT.md)

Credentials, model shards and bulky traces remain outside Git.

## Final allocation checkpoint — 16:57:43 UTC

The R9 experimental process loaded with **1,000,000 usable tokens**, confirmed
by both native props and its single slot. VRAM was 89,770 MiB used and 7,481 MiB
free out of 97,887 MiB (7.6425% free), at 41 C. Owned swap and OOM events were
zero, and registered storage guards passed. Short-context and native tool checks
were still running. This snapshot proves allocation, not long-context correctness
or production readiness. The 1,000,192 physical cache cells remain a source
calculation; no component-byte readback has been established.

## Optimized 8-thread qualification — completed17:07:33UTC

The same1,000,000 usable-token allocation passed a discarded representative
warm-up, fresh4K/16K retrieval/arithmetic requests and a native tool continuation.

| Actual input | Output | Input tokens/s | Output tokens/s | First token | Total |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 4,096 | 47 | 71.49 | 9.58 | 57.62s | 62.42s |
| 16,384 | 45 | 69.56 | 9.41 | 235.88s | 240.55s |

Both requests used fresh prefixes/cache0 and passed correctness, terminal-stream,
full-drain and authenticated-idle checks. The tool check advertised all17 schemas,
executed one actual read and consumed its result in the second turn. Both requests
accepted a65,536-token output ceiling; actual outputs were60 and53 tokens. This
proves the tested continuation, not execution of every tool or a full65K output.

Across264 roughly5-second samples, VRAM use peaked at89,770MiB, free VRAM stayed
at least7,481MiB and the frontier GPU reached47C. Sampled cgroup memory peaked at
573.37GiB; anonymous memory peaked at497.28GiB. File cache peaked at225.98GiB at
a different time, so those maxima must not be added. Host available RAM remained
at least356.43GiB; owned swap/OOM/guard failures were zero. These are sampled
values, not a recovered kernel memory.peak counter.

The exact native process, cgroup and GPU allocation settled at17:07:45UTC; the
original GLM was ready at17:09:27. The experimental systemd unit reports
failed/exit-code despite ExecMainStatus0, an unresolved wrapper-status discrepancy.
Actual model settlement and restoration were independently verified. The later four-thread result is recorded below. Production/Sova
acceptance and the final64K→near1M job remain incomplete.


## Four-thread comparison and selected profile

The requested four-thread trial completed the same 83-input/128-output fixture
with **6.764 output tokens/s**, compared with **9.210** for eight threads. Prefill
was 2.019 s, first token 2.335 s and total duration 21.111 s. Cached input was
zero; terminal stream, full response drain and native idle passed. This is
length-capped throughput evidence, not a quality evaluation.

Eight spread decode threads and 64 batch threads are the selected production
profile. Four threads were approximately 26.6% slower. The conditional two-thread
test was therefore not run. Eight is the best measured configuration, not a
proof of a global optimum. The guest-node0-only eight-thread comparison was not
admitted within its earlier time budget. The aggregate four-thread affinity
diagnostic remains inconclusive; configured masks and observed thread activity
do not prove physical-host pinning.

The unchanged eight-thread R9 profile already passed native qualification at
1,000,000 usable capacity. Production deployment and real Sova delegation remain
separate checks. See the [four-thread evidence](../reports/h016-production-prep16-20260927/AFFINITY14-FIRST-RESULT.json) and
[qualification provenance](../reports/h016-production-prep16-20260927/QUALIFICATION-PROVENANCE.md).


## Persistent service startup — integration blocked

The final Sova image and paired host release passed packaging checks and remain
staged. They were never applied, and no live Sova-to-MiMo request was sent.

The first ordinary MiMo launch stopped before readiness; its original exception
was lost because the unit discarded diagnostics. A separately reproduced source
defect treated a socket readiness timeout as a fatal mandatory-monitor timeout.
The narrow correction passed19 focused tests, and unit diagnostics now go to
the journal. This does not establish that defect as the first launch's cause.

The corrected launch began17:54:58UTC. Its last healthy guard was18:04:40;
at18:04:45 it reported LeaseBusy, followed by an ExecStopPost timeout. The
service had not started its API proxy or admitted inference. Because cleanup
runs in a finally block, the cleanup exception may hide the original failure.
The underlying cause remains unproven until the retained evidence is reviewed.

A third approximately11-minute load would leave insufficient time for the
required live application test within the authorized window. Exact settlement
and restoration of the unchanged GLM-backed Sova release are complete.
The successful native benchmark evidence remains valid; production reliability
and actual harness delegation are separate, unfinished checks.


## Final handback — 18:21:23 UTC

- GLM authenticated readiness passed at18:17:36UTC with1,048,576 context.
  Both Qwen480K instances and the image model retained their identities and were ready.
- Sova's unchanged7143/9ef885 release started normally at18:21. Health, status
  page and system-status API returned HTTP200. The26sessions,133messages,62file
  records and17,597 non-database files matched their preserved records.
- MiMo is stopped and fully settled. Its final image remains staged; real Sova
  delegation was not attempted. Optimized64K and near1M were never dispatched.
- Paid worker sessions are closed. No further load or stress test is authorized
  by this handback. Follow-up monitoring is paused at the end of this window.

The next bounded integration task should first repair failure reporting and
settlement contention, keeping the primary error visible. Then reuse the existing
weights, runtime, successful native qualification and final application image for
one clean production load and actual Sova delegation. Only after those pass
should the prepared independent64K→near1M job start. No completed benchmark
needs repeating merely because production integration is unfinished.

[Exact backend recovery](../reports/h016-recovery18-20260927/README.md) ·
[Original Sova recovery and preservation checks](../reports/h016-original-recovery-20260927/REPORT.md) ·
[Supervisor findings and narrow proposed correction](../reports/h016-recovery18-20260927/offline-lease-proposal.md).
