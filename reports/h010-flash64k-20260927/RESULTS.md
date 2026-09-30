# H010 Flash occupied 64K — primary PASS

The single fresh measured request completed at **2026-09-26 23:35:37 UTC** with
**65,536 actual rendered input tokens and 150 output tokens**, normal `stop`, and
correct retrieval of all three codes plus the bounded arithmetic result. Native
context and the physical token pool remain **480,000**. This qualifies this one
varied synthetic technical fixture at occupied 64K; it does not establish broad
reasoning quality or occupied 480K acceptance. [Machine results](RESULTS.json).

| Request | Actual input / output | Client TTFT | Client elapsed | Result |
|---|---:|---:|---:|---|
| Separate varied warmup |8,192 / 128|32.654 s|41.957 s|`length`; correctness unproven at cap|
| Fresh measured fixture |65,536 / 150|246.468 s|257.332 s|`stop`; all checks PASS|

Warm output cap was 128; measured cap was 256, both including reasoning. The
warmup retrieved facts and computed the result in its reasoning but truncated
its final JSON, so it remains **UNPROVEN_OUTPUT_CAP**. There was no retry, extra
ladder, cache change or model reload. High reasoning and `clear_thinking=true`
were used. Native usage reports `reasoning_tokens=0` despite reasoning deltas;
that field is preserved, not used as an authoritative separate reasoning total.

The fixture generator uses distinct seeds and varied records across 20 technical
subjects. Both inputs passed the exact pinned backend tokenizer/template with
generation prefix. Measured code starts were tokens **1,319**, **32,776** and
**64,232** (2.01%, 50.01%, 98.01%). Expected/result codes were
`H10E-8FXOLPL0`, `H10M-VOWN62OO`, `H10E-T9CFDYYZ`; rounding
`88 * 131 + 95 = 11623` upward to 64 bytes gives **11648**. The complete final
JSON matched. Source, payload, rendered token-ID hashes and exact spans are in
[RESULTS.json](RESULTS.json); full prompts/output/deltas remain in the retained
[raw manifest](evidence/RAW-MANIFEST.json), outside Git.

TTFT is client request start to the first nonempty reasoning/content delta.
First visible final-answer content arrived at **254.118 s**. Native logs show
32 prefill chunks of 2,048 tokens, each with cached-token count zero; first and
last logged chunk completions were **23:31:30.037577391** and
**23:35:26.729219321 UTC**. The first client-observed native delta followed at
23:35:26.730551. These logs locate actual prompt processing separately from
waiting for final-answer content. API cache detail is null; native chunk logs,
not that null field, provide zero-cached-token evidence. The runtime still
forcibly disables cross-request radix reuse for this GLM path.

| Rate and its basis | Measured result |
|---|---:|
| Effective input / client TTFT, not isolated prefill kernels |265.900 tokens/s|
| Incremental native usage observed on client clock, tokens 1→150 |13.715 tokens/s|
| Full-request output average, 150 / 257.332 s including prefill |0.582904 tokens/s|
| Native scheduler 40-token window, 23:35:29.192306069→32.080512163 |13.85 tokens/s|
| Native scheduler 40-token window, 23:35:32.080512163→35.018974619 |13.61 tokens/s|

The first native decode statistics window includes prior idle/prefill and is
excluded. The two valid windows have one running request and zero queued; they
use the pinned scheduler's generated count/perf_counter formula. Their Docker
log spans are 2.888206094 and 2.938462456 s, an independent approximate check of
the rounded native rates. Pool-aligned `#token` changes are not output counts.
A full-request native decode average and exact per-token server-side timestamps
are unavailable; client arrival timestamps and native windows remain separate.

| Memory during measured 64K, sampled every 5 s | Observed |
|---|---:|
| Flash peak GPU used / minimum free |31,532 / 65,718 MiB (30.793 / 64.178 GiB)|
| Minimum GPU free fraction / maximum temperature |67.14% / 59°C|
| Minimum host MemAvailable |607,499,669,504 bytes (565.778 GiB)|
| Cgroup sampled current maximum / lifetime peak counter |624,982,945,792 / 640,462,966,784 bytes|
| Cgroup anonymous / file-cache sampled maxima |311,495,360,512 / 311,973,298,176 bytes|
| Maximum sum of process RSS |326,037,905,408 bytes; shared pages can double-count|
| Owned cgroup swap / measured host swap-in/out delta |0 bytes / 0 / 0 pages|
| CPU temperature |Not exposed by guest sensors|

There were 52 samples within the measured request; maximum sample gap was
5.000411 s. Shorter peaks cannot be excluded. The GPU 7% and host 15% reserves
passed, with no OOM/thermal/resource cancellation. The cgroup's lifetime peak
predates this request and is not a 64K peak. Across warmup plus measurement,
host swap occupancy increased from 44,564,480 to 46,923,776 bytes, with one page
in and 553 pages out during warmup. This was not sustained across three sample
intervals; owned cgroup swap stayed zero. Historical occupied swap is not zero.

Loaded Flash GPU use was 23,624 MiB; post-warm 31,530 MiB; measured peak/final
31,532 MiB. The first varied warmup lazily allocated a documented 7,249,526,784-
byte GPU expert workspace and 50,343,936-byte host buffer, while the 480K token
pool was already allocated. No linear fit of used VRAM against occupied tokens
is justified. Separate phase snapshots and per-NUMA anonymous/file distribution
are retained in the machine results.

All 64 expert threads on guest CPUs 0–7 and 16–71 accumulated CPU time. Across
the 261.835 s bracketing interval, individual CPU time was 253.10–253.70 s;
summed time was 16,225.87 s, equivalent to 61.97 busy guest CPUs. This proves
guest coverage across eight pools/nodes, not host physical-core pinning or
memory-channel saturation. A separate natural idle observation found zero
expert CPU ticks over 376.07 s before warmup, with the last current-boot native
startup prefill at 21:21:34. It is not a controlled 600-second idle/wake campaign.

The verified source formula gives **3.245927 GiB** for the current FP8 cache
(including latent-scale sidecars/live tails), plus approximately 0.28 GiB of
recurrent states. At the published model limit **1,048,576 positions**, the
cache estimate is **7.090297 GiB**, an increment of **3.844371 GiB**. Using the
actual 64K minimum free memory, hypothetical pool growth leaves **53.642 GiB**
for additional workspace/metadata after the 7% reserve. The 650 GiB cgroup is an
independent host constraint; higher-context host charges/workspace behavior are
unknown. The range above 480K through the published limit is only a conditional
memory candidate, not an accepted operating range or tested maximum. No speed
or quality extrapolation is made. [Formula and source references](CAPACITY.md).

At **23:48:25 UTC**, final registered-storage/root guards and all 21 installed
identities matched, boot was unchanged, both Qwens and Flash retained actual
480K pools, and all four original containers were ready/resident. ECC stayed on
for the three Blackwells and off for Ada; original Full HD/nine image profiles
were retained. The primary job was inactive/MainPID0 with success, its SSE/body
was drained, and no established Flash connection was observed. This is not an
atomic native-drain claim. [Handback](evidence/PRIMARY-HANDBACK.json),
[final identity](evidence/FINAL-IDENTITY.json), [readiness](evidence/FINAL-READY.json).

Worker2/root reported true CPU-only operation unsupported in the exact pinned
architecture; Worker1 made no CPU-only trial or runtime change. Optional four-instance overlap was **not established**: the Flash task was
rejected before launch by a late staging check for the coordinated 23:44:00 UTC
window. That first attempt created no unit/path and ran no inference. Root then
explicitly authorized one corrected 23:49 window. Worker1 was actually armed at
23:47:08, but root aborted because Worker2 was not armed; the owned timer stopped
at 23:48:02 before inference. **Zero Flash smoke requests ran**, and no third
attempt occurred. These are coordination failures, not backend failures.
Worker2 owns its other smoke outcomes. [First failure](evidence/OVERLAP-NOT-RUN.json),
[actual corrected owner](evidence/OVERLAP-OWNER.json), [abort](evidence/OVERLAP-ABORT.json). Worker2 owns Sova restoration; this report does not claim Sova is
running without its receipt. The installer and all model/hardware changes
remained outside this task.

The stream defect was addressed only in the task driver: prompt draining with
bounded memory, independent 5 s telemetry, and guarded batches every 15 s outside
the hot reader. Ten offline stream/error/deadline tests and the fixture
construction self-test passed. Clean handoff preserves the independent job;
abrupt process death could lose the most recent buffered checkpoint interval.
Source commit `a9d3034`, executed job SHA256
`0ac1bc7987c7e798607f31570ca441f6c2e10d149feb9b30b984891bcaf345d6`.
No Git push was performed.
