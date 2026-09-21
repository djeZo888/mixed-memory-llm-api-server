# Concurrent GLM G1 + Qwen Q1 — 20 September 2026

**Recommendation: retain one VM with two fixed GPU slots as the direction supported by observed practical concurrency.** Evidence is limited to one measured long concurrent pair and one idle-peer reference; future capacity and production acceptance remain separate. **Benchmark completed; production pair not deployed.** [Machine results and SHA256 provenance](concurrent-g1q1-20260920.json).

Practical concurrency was observed once: GLM at 65,008 input / 65,072 occupied tokens completed in **935.400652 s**, close to the historical diagnostic replay **934.818440 s** (+0.062%). Qwen near 700K completed in **507.213325 s** concurrently versus **508.731414 s** with GLM resident but idle (−0.298%). These observations do not establish multiple-run equivalence, a causal fix, or production readiness.

The short G16/Q256 round produced **four strict and semantic PASS** results. Across short, long and idle-reference retrievals, **12/12 semantic exact-object PASS; 10/12 strict PASS**. Long Q0 and Q3 each had one enclosing JSON fence: their strict **HARNESS_FAILURE** remains visible alongside semantic PASS under the reviewed optional-one-fence policy. GLM strict retrieval JSON correctness passed. The separate scientific decode pair is capped, timing-only and UNSCORED, not scientific-quality PASS.

**Configuration and measurement conventions.** GLM5.3 UD-Q4_K_XL used GPU0 (UUID suffix1488237), N76 host experts, F16 KV, batch2048/ubatch512, 96 threads and guest CPUs0–95. Qwen3.8-27B FP8 used GPU1 (suffix2c163cc), TP1, BF16 compute/KV, YaRN4, chunk2048, guest CPUs96–111, static allocation fraction0.8, one request, disabled radix cache, CUDA graphs and overlap scheduler. Host caps were640/32 GiB with model swap disabled. Guest CPU partitioning does not prove physical isolation. Exact model revisions, image pins, request samplers and source hashes are in the JSON; source manifests alone are not live proof.

Configured capacity is the allocated total window; occupied total is actual input plus actual output. Retrieval output limit was256, not an output count. GLM native input rate is input/(prompt_ms/1000); native decode rate is **(decode_tokens−1)/(decode_ms/1000)**. Qwen columns are **client** input/TTFT and (completion_tokens−1)/(last−first output arrival) estimates, not native prefill/decode measurements. Qwen native evaluated/cache/decode counters remain null. SSE events are not token counts. TTFT below is first output of any type; short GLM content TTFT was249.839692 s, versus227.566091 s first reasoning/output.

| Request | Configured | Input / output / occupied | Elapsed s | Client TTFT s | Input t/s¹ | Output t/s¹ | Strict / semantic |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| short-G1 | 16,384 | 15,830 / 202 / 16,032 | 259.249 | 227.566 | 69.590 | 6.344 | PASS / PASS |
| short-Q1-0 | 262,144 | 261,622 / 82 / 261,704 | 87.310 | 84.732 | 3087.651 | 31.852 | PASS / PASS |
| short-Q1-1 | 262,144 | 261,622 / 82 / 261,704 | 90.619 | 88.043 | 2971.514 | 31.850 | PASS / PASS |
| short-Q1-2 | 262,144 | 261,622 / 82 / 261,704 | 90.976 | 88.396 | 2959.662 | 31.794 | PASS / PASS |
| long-G1 | 65,536 | 65,008 / 64 / 65,072 | 935.401 | 929.734 | 70.056 | 8.579 | PASS / PASS |
| long-Q1-0 | 700,160 | 699,583 / 78 / 699,661 | 507.213 | 503.391 | 1389.740 | 20.418 | HARNESS_FAILURE / PASS |
| long-Q1-1 | 700,160 | 261,622 / 82 / 261,704 | 90.838 | 88.255 | 2964.396 | 31.795 | PASS / PASS |
| long-Q1-2 | 700,160 | 261,622 / 82 / 261,704 | 90.924 | 88.346 | 2961.323 | 31.823 | PASS / PASS |
| long-Q1-3 | 700,160 | 261,622 / 87 / 261,709 | 91.212 | 88.474 | 2957.035 | 31.795 | HARNESS_FAILURE / PASS |
| long-Q1-4 | 700,160 | 261,622 / 82 / 261,704 | 91.015 | 88.434 | 2958.371 | 31.799 | PASS / PASS |
| long-Q1-5 | 700,160 | 261,622 / 82 / 261,704 | 90.996 | 88.418 | 2958.912 | 31.826 | PASS / PASS |
| Q-idle reference | 700,160 | 699,583 / 82 / 699,665 | 508.731 | 504.711 | 1386.105 | 20.407 | PASS / PASS |

¹ GLM native rates; Qwen client estimates, as defined above. All retrievals completed naturally below256, without request retry. The five Q256 fillers retained the **700,160 configured pool**; they did not occupy700K. Native tokenizer metadata262,144 is kept separate from the accepted Qwen runtime pool700,160.

**Comparison limits and cache evidence.** The near-Q pair used the same logical fixture, template and exact699,583 input count with fresh leading nonces and different body/token-ID hashes; inputs were not byte-identical. GLM remained allocated in both. Concurrent Qwen TTFT503.391169 s versus504.711375 s was0.262% lower; output-event intervals were3.771218/3.969319 s with78/82 actual outputs. This is one matched idle-resident-peer comparison, not an unloaded-peer baseline.

GLM65K native input70.056 t/s compares with69.763 in the ladder and70.006 in the later replay. Current native decode8.579 t/s lies between the ladder0.455 and replay10.249 (16.3% below replay). Replay instrumentation and fresh prefixes differ; intermittent GLM variability remains unexplained. Short GLM input69.590 t/s is within0.15% of historical69.650/69.489, but output6.344 compares with10.785/10.319 using202 versus176/64 outputs. Historical Q256 used a different fixture261,525/89; its84.330 s TTFT compares approximately with84.732–88.396 s here (+0.48–4.82%). Its historical strict framing failure and separate semantic PASS remain unchanged. See [GLM ladder](glm-g1-ladder-20260920.md), [diagnostic replay](glm-decode-diagnostics-20260920.md) and [Qwen reference](benchq1-verified-20260919.md).

Distinct warmups were discarded: GLM short/long warmups2389/2391 input, each32/32 output; each Qwen2342 input,86/256 output. GLM native cached_tokens=0 and evaluated-input counters supply cache proof. Qwen warmup proof derives from current server arguments plus validated disabled-radix-cache argv, not a measured zero cached-token counter. JSON retains that provenance and each request's hashes.

**Overlap and output limits.** Short round275.192 s: summed pairwise request overlap254.787 s, no observed decode/decode overlap; final Q continued14.117 s after GLM transport drain. Long round973.780 s: request overlap925.549 s, no observed decode/decode overlap; GLM output overlapped5.591 s of final-Q prefill proxy, with36.649 s Q tail. Sequential Q intervals make the summed pairwise request overlaps nonduplicative. All prefill/decode phase labels use client dispatch and output-arrival proxies; JSON preserves every aggregate phase duration.

The optional scientific pair explicitly observed **26.016137 s simultaneous output intervals** (request overlap26.137908 s). This demonstrates overlapping output, not GPU-kernel saturation or scientific correctness. Both hit512-token output limits and are **TIMING_ONLY / UNSCORED**:

| Request | Configured | Input / output / occupied | Limit | Elapsed s | TTFT any / content s | Native G decode or Q output-event estimate t/s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| decode-G1 | 65,536 | 78 / 512 / 590 | 512 | 54.530696 | 6.552212 / 8.493698 | 10.631680 |
| decode-Q1 | 700,160 | 89 / 512 / 601 | 512 | 26.137908 | 0.121335 / 0.121335 | 19.641656 |

**Memory tiers (binary GiB).** These are independent sampled extrema, not a simultaneous additive breakdown. RSS may double-count shared pages; cgroup current and lifetime peak include charged file memory. File/mapped/shmem overlap. Neither the caps nor their sum are a minimum host-RAM requirement.

| Scope / model | GPU used peak / free min | Process RSS peak | Inclusive current peak | Cgroup lifetime peak |
| --- | ---: | ---: | ---: | ---: |
| short requests / G1 | 35.965 / 59.007 | 400.420 | 401.957 | 401.957 |
| short requests / Q1 | 46.770 / 48.201 | 6.069 | 4.457 | 12.429 |
| long requests / G1 | 40.473 / 54.499 | 400.549 | 402.084 | 402.084 |
| long requests / Q1 | 73.557 / 21.414 | 6.221 | 4.521 | 12.394 |
| LONG2 load through optional decode / G1 | 40.473 / 54.499 | 406.322 | 407.870 | 407.870 |
| LONG2 load through optional decode / Q1 | 73.557 / 21.414 | 13.726 | 12.287 | 12.394 |

| LONG2 all-stage component peaks | anon | file | mapped | shmem | kernel |
| --- | ---: | ---: | ---: | ---: | ---: |
| G1 | 6.557907 | 399.591045 | 399.591057 | 399.586231 | 1.722378 |
| Q1 | 11.828667 | 0.366318 | 0.055962 | 0.361652 | 0.090931 |

The reviewed sampled working-set **ESTIMATE** is `max(anon + kernel + max(mapped, shmem), summed process RSS + kernel, pinned native host weights + workspace floor)`, taking the high-water over covered phases. LONG2 estimates were408.045/13.817 GiB (G/Q); adding25% gives510.056/17.271 GiB against640/32 GiB caps. JSON retains exact bytes, formula inputs and native-floor provenance; Qwen's native host floor is unavailable. This is not exact MEASURED_COMPONENTS, an exact union or an absolute peak. Raw current/lifetime charges remain separate hard-cap checks. Extra charged file maxima77,824/51,073,024 B are not proved instantly reclaimable.

Current compact load receipts record ALLOCATION_PROOF_ACCEPTED, but detailed current native KV/weight/workspace exports were unavailable in the inspected saved set and remain null. For labelled historical context only, same-pin G64 reported6,241,124,352 B CUDA KV,3,250,661,376 B CUDA compute workspace,30,754.2 MiB device weights,409,012.22 MiB host weights and159,461,408 B host workspace. Historical Q256 logs labelled K/V8.0/8.0 GB and weights28.72 GB; workspace unavailable and byte-unit semantics unverified. These are not current near700K component proof and cannot be added to device/RSS/cgroup totals.

Minimum measured free GPU memory54.499/21.414 GiB exceeds the16 GiB reserve for this G65K/Q700160 pair. Q's additional10%-physical-total comparison is9.559 GiB, leaving11.855 GiB above it. No higher capacity follows. LONG2 host available minimum was452.581 GiB across load through decode, versus459.482 GiB for long requests. The3077 samples and per-request coverage estimates (short85.3–87.7%, long86.2–87.3%, decode76.2–78.5%) leave gaps; sampled extrema do not bound spikes.

Model process/cgroup swap and sampled OOM counters were zero. Guest swap nevertheless ranged138,936,320–163,053,568 B; guest pswpin/pswpout increased3004/6176 and oom_kill stayed0. Guest activity is not model swap. The short campaign likewise had zero sampled model swap/OOM while guest swap counters changed.

**Preserved interruptions and restoration.** Original RUN stopped at warmup admission after a loading telemetry gap, without completed measured requests. CONT1 lacked task-local progress; LONG lacked the incoming-control note before its first load. These orchestration failures remain separate from model correctness. CONT1B completed the four short rows, then stopped G64 loading under its inclusive-charge headroom rule:549,898,883,072 B exceeded the549,755,813,888 B threshold under a640 GiB cap. File charge547,576,070,144 B included118,685,192,192 B above max(mapped,shmem); this was not an OOM or proof of instant cache reclaimability. It dispatched zero long requests. Recovery-wrapper errors were preserved; canonical continuation restored it at08:41:49.452569 UTC. LONG2's later success does not erase that stop or prove a causal fix.

LONG2 used source`63884aa22effeb73aab1cef69228e982e512c5c2`. Its explicit extension retained the original07:55:54.308154 UTC epoch, changing the90-minute deadline09:25:54.308154 to120-minute09:55:54.308154; restoration was outside the measurement clock. The fresh final receipt records **RESTORED/PASS at09:36:03.111974 UTC**, authenticated Worker1 LAN verification, host session closed and both tunnels closed; run outcome has no errors and execution exit0. This is a saved receipt claim. The subsequently saved auth-stage receipt supplies the canonical-state/absence supplement: original Qwen remained selected/running/resume and ready with the same container, state, process start and units; all four exact predecessor resources were absent.

**Candidate and deployment boundary.** GLM65008 input/65072 occupied proof was configured65536. The deferred G480000 candidate planned allocation plus short checks only: no occupied480K, speed or quality acceptance transfers. Qwen699583 input/699661 concurrent occupied (699665 idle) may be cross-referenced only after explicit **700160 core-configuration comparison**; production wrapper, authentication and alias proof are separate.

Accepted API source preparation is not deployment. Candidate source is`46e7f29c6edd98c156006736b999e6c858a0c9ab`, canonical arm`d4b725f537222f06eaaabecb04cb29da794e5c466e8e3dae9c7b30498a32c6aa`. Source-prep receipts historically recorded actual-image auth NOT_RUN. The later saved actual-image Q700 auth receipt is **PASS at09:43:11 UTC**, with the fixture exited and removed, the canonical lease free before execution and released afterward, and original Qwen unchanged. This is **no-model proof**: model loading, inference and700160 capacity were NOT_TESTED. Candidate G480/Q700 model validation and production activation are now **DEFERRED, not failed**; accepted production receipt and live boot proof remain absent. A separate future both-configured480000 comparison (G96/Q16 versusG88/Q8) has no results here. Its new15% system-RAM policy applies only to that future scope; this completed benchmark retains its historical25% margin.

Raw prompts, outputs/reasoning, private paths and credentials remain private. The companion JSON gives sanitized artifact names, raw-file SHA256, exact counts/timings, sampled tiers and explicit nulls; only existing public report links are used here.
