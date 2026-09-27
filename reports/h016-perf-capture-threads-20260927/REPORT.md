# H016 perf capture and conditional final thread A/B

Source/planning only over `6adafffa1ba3c42d69a2c4c5c275b8a56ffaa659`. No private-host contact, live measurement, implementation, reload, build, model download, delegation or push. R7's outcome remains unknown; this report does not wait for it.

## Manual capture

Use `EARLY-COMMAND.md`, corrected to root's final instruction: private mktemp directory, Bash eight-PMU loop, 5-second intervals/four intervals, UTC brackets, retained exact runtime coverage and pasteable output. No operational action was executed here. Root sends it after W1's active-decode receipt.

The supplied host inventory establishes `amd_umc_0..7`, representative CPU0 and fields `event=config:0-7`, `rdwrmask=config:8-9`; W2 did not re-read the host. Retained Linux v7.0.14 `arch/x86/events/amd/uncore.c:351,361,379–382` independently defines those fields. The retained Zen5 memory-controller JSON:62–77 identifies event0x0a/mask1 reads/mask2 writes. AMD [PMC58550 Rev0.02](https://docs.amd.com/api/khub/documents/J16SVs7~UyY5YdjGOobZaQ/content), printed pp35–36, includes both subchannels and defines mask1 as excluding writes and mask2 as excluding reads. No direct MSR/PWM write or guessed encoding.

The [merged Linux v7.0.14 metrics](https://github.com/gregkh/linux/blob/v7.0.14/tools/perf/pmu-events/arch/x86/amdzen5/recommended.json#L305) explicitly call the CAS×64 calculation **estimated** bandwidth. Their divisor1e6 and MB/s unit are decimal; divide by1e9 for decimal GB/s. Retain raw counts and CAS/s. No subchannel multiplier, independent byte-counter claim or saturation/ceiling inference.

Primary perf **v6.12.107** manual/code were checked, beyond generic web manpages: `--no-scale` preserves unscaled counts; `-x ';'` exposes runtime and percentage; `-I 5000` reports count deltas and relative timestamps; `--interval-count 4` bounds the collection; `--no-merge` preserves separate PMUs. `builtin-stat.c:353–359` writes raw cumulative value/enabled/running to **stat_config.output**, so `-vv -o` mixes these lines with the CSV-style rows. `stat-display.c:80–87` prints runtime and rounded running/enabled percentage. Difference cumulative raw times for exact interval coverage. `builtin-stat.c:438–457` takes monotonic interval timestamps. Enabled/running units are nanoseconds under the perf read-format ABI. The installed binary is user-reported; no execution validation is claimed.

## Conditional second/final A/B

**If R7's GOMP_SPINCOUNT=0 does not improve native decode throughput, `--threads 16 --threads-batch 64` is a defensible single configuration-variable second/final comparison against R7, subject to root GO and W1 ownership.** Keep GOMP_SPINCOUNT=0 in both sides. A drop in CPU utilization alone is not a throughput improvement, and the source provides no expected TPS. The R6 retained profile has90.32%+4.24%=94.56% CPU-clock samples in libgomp loops whose disassembly includes PAUSE;4.28% is repacked `ggml_gemv_mxfp4_8x8_q8_0`, with59.110 CPU equivalents in stat. These are CPU sample fractions, not94.56% of wall time or proof that fewer threads will be faster. Waiting can reflect load imbalance, synchronization or a critical path; reduced parallel work can also hurt.

All following references are exact llama revision `7ac59a6e3ad851cd41af00f678effab0598ba9a8`, checked against the retained source manifest for the decision-bearing files (supplemental server-http.cpp is retained but lacks an older manifest entry):

| Source | Finding |
|---|---|
| `common/arg.cpp:1513–1533`; `common/common.cpp:1681–1683` | Separate generation `-t` and batch `-tb` values feed context settings. Explicitly retain batch64; do not let it inherit16. |
| `src/llama-context.cpp:1454,2566–2585` | Actual dispatch uses batch threads when microbatch token count>1, decode threads otherwise. This is not strictly a semantic prompt/decode distinction: a one-token prompt tail also uses16. |
| `common/common.cpp:1359–1361,1738–1779` | Threadpools are initialized with the context; different settings produce separate pools, each matching its count. Pool separation is a consequence of changing t, not a separately varied option. |
| `src/llama-context.cpp:1195–1200,3912–3914` | A C library context setter exists. Its presence does not expose a supported request or HTTP thread control. |
| `tools/server/server-context.cpp:1099,4816–4826`; retained server task/schema/common/queue/http files | Startup initializes from base params. `/props` POST has no property-update implementation. No request `n_threads` parsing or server call to `llama_set_n_threads` was found in the inspected server sources. Do not use ignored JSON fields, library injection or a runtime API hack. |
| `ggml/src/ggml-cpu/ggml-cpu.c:2171–2213,2713–2735,3105,3344–3350,3413–3432` | Distribute chooses node `thread_index % node_count`, then sets affinity to that node's CPUs. Strict mask is applied first; graph-time NUMA affinity supersedes that initial per-thread assignment, subject to the enclosing cpuset. OpenMP explicitly requests the configured team size and reads actual team size. |

With **eight discovered usable nodes and an actual16-thread team**, distribute assigns two thread indices per node. Keep `--numa distribute`, both strict masks `0xffffffffffffff00ff`, outer CPU cpuset `0–7,16–71`, memory nodes0–7 and `numactl --interleave=0-7`. Strict masks alone would initially choose the first16 permitted CPUs; they do **not** prove eight-node execution. Source modulo placement does, conditionally on successful affinity and the same eight-node topology. W1 should retain actual team/affinity evidence during the already-authorized sample; do not assert physical-host pinning from guest masks.

For this pinned server/current path, changing startup t requires W1's ordinary restart/context/threadpool recreation and model reload. The approximately11-minute reload is a supplied planning observation, not a source-guaranteed duration. Do not implement a new API or reload workaround. This review supplies no operational command or new execution authority.

Keep exact model/image/runtime/quantization, prompt, occupied context, sampling/seed, current stable output-token budget and workload concurrency unchanged; compare against R7's matching request, not a fresh R6 replay. One warmed fixed sample after readiness, retaining native predicted count/time and derived `(N-1)/seconds` plus client UTC timing; no sweep or automatic repeat. Prefill, load and decode stay separate. If output shape/sample conditions differ, mark the comparison inconclusive. Keep existing thermal/reserve/lease/storage guards and normal settlement. Root admits only if reload, sample and recovery fit the15:15 admission/15:35 settlement and15:48:08 overall limits; otherwise defer. If R7 succeeds, this second experiment is unnecessary.

## Validation and limitations

Local only: source hash comparison, Bash syntax of the documentation block, sixteen unique generated PMU selections, diff/whitespace and scoped secret checks. No runtime test or test suite is warranted for this docs-only packet. UTC alignment, four usable intervals, full running coverage, actual8-node placement and R7 throughput remain operational observations for root/W1/user, not results of this source review.
