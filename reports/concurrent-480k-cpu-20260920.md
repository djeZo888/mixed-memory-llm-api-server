# Both configured 480K: CPU comparison — 20 September 2026

**Four measurements completed; B-GLM is partial.** A-GLM completed65008 input/64 output in **941.819 s**. Matched near480K Qwen took **253.166 s in A /253.829 s in B** (+0.262%). B-GLM hit the captured transport cutoff before final counters, so the pair's no-penalty comparison remains unresolved. **The96 production target is superseded by the user-selected future72-vCPU plan; this benchmark validates neither a72 layout nor no-penalty operation.** A-GLM's sampled output phase used95.261 mean/95.981 p95 core-equivalents; low whole-request averages hide that demand. [Exact rows, CPU/memory summaries and evidence hashes](concurrent-480k-cpu-20260920.json).

The current goal is **both480K models resident, one GPU each, with15% required-working-set estimate headroom**. The latest root-relayed user plan selects a **72-vCPU VM** after user reconfiguration/restart, with host affinity`0-63,72-79`, described as64 physical cores plus8 additional SMT threads on GPU host node6. Model CPU sharing is not yet defined. This is a future plan: the unchanged112-vCPU guest tested neither that host placement nor an actual72-vCPU VM. **All further reduced-CPU tests and activation are deferred until the user's actual72 reconfiguration/restart.** CPU-independent PREP remains source-only; unreviewed resident96 WIP is excluded. Original Qwen TP2/1M restoration is a necessary intermediate because the immutable runner has no supported warm hold/handoff. No concurrent pair is deployed, and this report does not wait for new PREP or a later proposal.

| Case | Configured | Input / output / occupied | Elapsed s | TTFT s | Input t/s¹ | Output t/s¹ | Strict / semantic |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| A-G65008 | 480,000 | 65,008 /64 /65,072 | 941.819 | 930.411 | 70.053 | 4.593 | PASS /PASS |
| A-Qnear480K | 480,000 | 479,487 /87 /479,574 | 253.166 | 249.665 | 1920.520 | 24.855 | HARNESS_FAILURE /PASS |
| A-Q256K | 480,000 | 261,622 /82 /261,704 | 90.952 | 88.377 | 2960.301 | 31.786 | PASS /PASS |
| B-G65008 | 480,000 | 65,008 preflight² /unavailable /unavailable | 605.850 to cutoff² | unavailable | unavailable | unavailable | UNSCORED /UNSCORED |
| B-Qnear480K | 480,000 | 479,487 /87 /479,574 | 253.829 | 250.321 | 1915.486 | 24.812 | HARNESS_FAILURE /PASS |

¹ GLM rates are native: evaluated input/native prompt seconds and **(decode_tokens−1)/native decode seconds**. Qwen rates are **client estimates**: input/first-any-output TTFT and (completion−1)/(last−first output arrival); native prefill/decode/cache counters remain **UNAVAILABLE**. SSE events are not tokens. A-G native prompt927.980198 s/decode13.718008 s, cached0; its client output interval11.324218 s is a different measure. First-any-output and content TTFT are separately retained in JSON.

² B-G's native preflight count65008 is not a final response/evaluated count. Saved status is **STOP_NATIVE_OR_TRANSPORT /TRANSPORT_FAILURE**, zero observed output events, no done marker and empty native counters. Its605.850 s is observation to transport termination, not completed throughput. Completion count, occupied total, native cache/timings/rates and correctness remain unavailable/unscored; no final counts are inferred. The runner's five-item `completed` list means **five saved records**, comprising four complete measurements and one partial record.

Both near-Q rows returned one enclosing JSON fence: retain strict HARNESS_FAILURE alongside semantic exact-object PASS. Complete rows total **4 semantic PASS,2 strict PASS,2 strict framing failures**; B-G adds one unscored partial, not a correctness failure. Completed outputs ended naturally below max256, without retry.

**Protocol clock versus user authorization.** Original start **10:14:56.052823 UTC** is unchanged. Root extended the internal75-minute protocol once to120 minutes, fixing the runtime cutoff at **12:14:56.052823 UTC**. Later, the user explicitly authorized the current B pair through **12:40:00 UTC**, recorded in `user-duration-amendment.json` at12:11:57.296672. The immutable transport had captured a scalar deadline/socket timer at dispatch and had no supported live amendment hook. The extension was recorded but not applied; B-G was cut at the old timer. This was **not a user refusal or budget choice**. No new cases, requests, clock reset or runtime patch were introduced. Canonical restoration remains outside benchmark timing.

**Configuration and native proof.** A uses G96 threads/batch96 on`0-95`, Q16 allowed vCPUs on`96-111`; B uses G88/batch88 on`0-87`, Q8 allowed on`96-103`. Native allocation receipts confirm those effective cgroup CPU masks. The guest stayed112 vCPUs; B's aggregate96 model allowance is neither an actual96-vCPU VM nor physical pinning. Q8 is not eight runtime threads. B's Q96–103 mask is invalid after a literal resize to CPUs0–95, requiring a reviewed valid placement and post-resize validation.

Same weights/cache/runtime settings: GLM5.3 UD-Q4_K_XL, GPU0/N76/F16 KV, batch2048/ubatch512; Qwen3.8-27B FP8, GPU1/TP1/BF16 compute/KV, YaRN4, static0.8/chunk2048, disabled radix cache/CUDA graph backends/overlap scheduler. Exact model/image/GPU/profile hashes are in JSON. All four native allocation proofs were accepted: G `n_ctx`/`n_ctx_seq`/slot480000, one slot; Q native pool480000/input limit479994, request-limit field absent. Tokenizer metadata262144 is separate. A-G65008 at configured480000 proves approximately65K occupied operation, not occupied480K GLM. B-G preflight/allocation is not completed inference acceptance.

Actual **Mems_allowed is UNAVAILABLE** in the inspected allocation/boundary schemas. Saved B warm-idle guest NUMA page totals are G105,148,185 and Q1,546,273 across process inventories; exact node counts remain in JSON. These are guest residency pages, not bytes or physical-host NUMA/pinning proof; cross-process sums may double-count shared pages.

**Overlap and comparisons.** A's single Q256 continuation dispatched2.118956 s after near-Q drained, with G active. Actual summed G/Q request overlap344.119 s; both Q intervals fit inside G's client prefill proxy, with zero observed output/output overlap. G continued594.354 s after final Q drain. B request overlap253.829 s is observed; G remained open350.815 s after Q drain until cutoff. B-G output/phase boundaries and completed tail are unavailable, so no decode overlap or useful token progress is inferred from an open request/GPU utilization.

A/B near-Q inputs479487, outputs87 and logical fixture match. B TTFT is0.263% higher and elapsed0.262% higher in this one pair. This does not establish a completed pair's no-penalty result, an isolated CPU effect or statistical equivalence. A-G elapsed is0.686% above historical935.401 s at65008/64; native input70.053 versus70.056 t/s is close, while decode4.593 versus8.579 t/s is46.468% lower. Historical G was configured65536, not480000. Intermittent GLM slow decode, unequal peer exposure (A alone has Q256) and one ordered pair prevent causal CPU/pool claims. A common-Q TTFT88.377/elapsed90.952 s falls within historical700160-pool88.255–88.474/90.838–91.212 s; source, G pool and warm state differ. Historical strict failures and25% policy remain unchanged.

Load and discarded warmup time is excluded from request timing but included in the captured campaign window. Load G/Q: A214.179/109.754 s; B109.148/110.880 s. **Four discarded warmups** completed their32-token cap: each G2642 input, each Q3251; A G/Q112.389/5.135 s, B111.298/5.127 s. All four CPU collection gates passed. G warmups prove native cached0/evaluated2642; Q derives prefill from disabled-cache policy, not a native cached0 counter.

**CPU usage and coverage.** Mean / time-weighted interval p95 core-equivalents below are from each named request's client phase proxy. Process, cgroup and guest channels overlap and are not added. JSON retains individual process summaries, PSI, steal, thread counts and coverage.

| Window | Intervals / observed span | G cgroup mean/p95 | Q cgroup mean/p95 | Guest mean/p95 |
| --- | --- | --- | --- | --- |
| A near-Q prefill | 215 /99.924% | 1.000/1.001 | 1.007/1.005 | 2.149/2.190 |
| A near-Q output | 1 /34.114% | 1.000/1.000 | 1.015/1.015 | 2.177/2.177 |
| A Q256 prefill | 76 /99.746% | 1.000/1.001 | 1.008/1.005 | 2.148/2.176 |
| A Q256 output | 1 /45.556% | 1.000/1.000 | 1.018/1.018 | 2.188/2.188 |
| A G prefill | 797 /99.776% | 1.149/1.001 | 1.006/1.005 | 2.299/2.192 |
| A G output | 9 /96.483% | 95.261/95.981 | 1.010/1.021 | 96.437/97.346 |
| B near-Q prefill | 215 /99.602% | 1.001/1.001 | 1.008/1.005 | 2.150/2.195 |
| B near-Q output | 2 /68.113% | 1.001/1.001 | 1.014/1.015 | 2.164/2.168 |
| B G partial request | 519 /99.675% | 1.001/1.001 | 1.006/1.005 | 2.153/2.196 |

Available phase summaries remain **PARTIAL**. Four completed rows report COMPLETE counter inventory; **B-G inventory is INCOMPLETE**, with only partial-request channels available and prefill/decode summaries **UNAVAILABLE**. Short output p95 values are coarse, particularly one/two Q intervals and nine G intervals. Whole-request A-G mean2.359/p951.001 hides its brief near96-core output demand. The root numerical audit confirms CPU-time/elapsed arithmetic, with no96-fold divisor or missing known process pool. A process threads G215/Q56,1,79,35; B G207/Q32,1,55,19. These are inventories, not CPU requirements.

Owned quota is`max` with zero sampled throttling; inherited quota and guest CPU-full PSI remain unavailable. Guest steal totals A-G6.39 s/A-near-Q0.05/A-Q2560.01; B-G1.58/B-Q0.06. Sampled memory PSI0; CPU/IO pressure remains in JSON. Process tick precision0.01 s, uncorrected RPC lag, phase edges and client/native phase mismatch limit interpretation. CPU interval coverage differs from point-memory coverage; collector wall time does not prove timing perturbation or minimum cores.

**Memory, binary GiB.** Independent sampled extrema over each layout's request observations; B includes the partial G window. Lifetime peaks include loading. These tiers are nonadditive.

| Layout/model | GPU used peak / free minimum | Process RSS peak | Raw cgroup current peak | Lifetime peak |
| --- | ---: | ---: | ---: | ---: |
| A G | 77.971 /17.001 | 401.403 | 412.642 | 412.643 |
| A Q | 60.070 /34.900 | 6.020 | 4.415 | 12.394 |
| B G | 77.971 /17.001 | 401.365 | 407.640 | 409.440 |
| B Q | 60.045 /34.926 | 5.990 | 7.272 | 15.400 |

Both sampled GPU minima exceed16GiB; Q also exceeds10% of reported95.593GiB total. G margin above16GiB is only1.001GiB; unobserved minima are unbounded. Point-telemetry coverage A85.75–86.26%, B85.83–86.13%; full collection wall overhead A5.34–5.67%, B5.39–5.66%, separate from CPU-only collector overhead. Host available minima A457.816/B455.877GiB. Model swap/OOM samples were zero. A guest swap decreased262144 bytes with pswpin+3; B guest swap about0.129GiB stayed unchanged with swap-in/out deltas0. Guest activity is not model swap.

Required working-set **ESTIMATE** is sampled high-water of `max(anon+kernel+max(mapped,shmem), summed process RSS+kernel, pinned native host weights+workspace floor)`. Campaign peaks G403.118×1.15=463.586GiB and Q13.922×1.15=16.010GiB fit640/32GiB caps. Lower B estimates403.084/9.804GiB do not replace those peaks. Native floor provenance stays explicit; Q native host floor is unavailable. Raw current/lifetime/file/mapped/shmem and RSS overlap; extra charged cache is not proved wholly/instantly reclaimable. There is **no exact minimum VM RAM claim**. The old700K report retains25%; this comparison uses15% estimate headroom.

**Setup, restoration and publication.** JSON retains old source/arm identities and receipt hashes. Initial`be3a91fd` failed private0755 capture before inference; CONT1`5d02cd35` failed too-long STAGE before ownership; CONT2`0414f8fe` passed G load/warmup then failed the flat-Q-info guard (failed Q480 API payload unavailable). FLATFIX`cf755a4` failed begin UNKNOWN before loads; historical`control_not_frozen` was later canonically RESTORED without model restart. FINAL`76360ad9` begin passed without resolving that earlier UNKNOWN cause.

Fresh **FINAL cont3** evidence now records **RESTORED_WITH_MEASUREMENT_FAILURE**: original Qwen TP2/1M authenticated Worker1 verification at **12:16:57.238167 UTC**, no active requests or pending create, six owned resources REMOVED, both local tunnels CLOSED. Its owner/verification hashes match the fresh final index. This is the necessary intermediate restore, not historical substitution, benchmark completion or both480 deployment. Old G480/Q700 validation remains deferred.

Published`22cb69321dff3a96436cabcc32e620799973ec72` remains an ancestor of integration merge`3024965ea2bfaa998839ef882abdb9c9f17b5b45`; old700K reports are unchanged. Measured runtime stays`76360ad9ffb911ef3c85f4ee1fc468bd40487efe`. The only publication source correction changes the actual-STAGE guard test's hardcoded cont2 expectation to cont3; **only that one test passed**. The local report/test commit and bundle are identified in the review receipt; publication awaits root GO. No push, runtime edit, build, implementation suite, live contact or new requests from this reporting task. Raw reasoning, headers, credentials and traces remain private.
