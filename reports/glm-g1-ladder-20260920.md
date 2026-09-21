# G1 16K/64K ladder — saved results

Measured cases: 3 successful, 0 failed/stopped, 0 missing. Final restoration receipt: PASS; saved phase: RESTORED.

Source `4063ef3581f0c4c41d2c134203b60bd47b272c29`; session `01a0bc02-cfe2-7c50-b6ae-d5765a02af62`. The new three-hour clock includes preparation, loading, warmup, fitting and requests; restoration is outside that budget.

Serious observed performance variability: the 64K measured decode rate returned to about 0.455 tok/s, versus 10.32–10.79 tok/s in the two 16K samples. The short discarded warmup on the 64K load was already slow. Cause is UNPROVEN; context size, schema, sampling and GPU count are not established causes.

Exactly two planned loads (16,384 then 65,536 configured tokens), one discarded 32-token-cap warmup per load, and three measured streaming schema requests. UD-Q4_K_XL/N76/F16, GPU0 only, 96 threads/cpuset 0–95, batch 2048/ubatch 512, split/load none and original poll50 remain pinned. Profiles and observed limits are retained in companion JSON.

## Measured cases

| Case | Saved result | Records | Input | Evaluated | Cached | Output | Occupied | Cap | Finish |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| G1-16384-primary | PASS | 495 | 15,831 | 15,831 | 0 | 176 | 16,007 | 256 | stop |
| G1-16384-repeat | PASS | 495 | 15,831 | 15,831 | 0 | 64 | 15,895 | 256 | stop |
| G1-65536-primary | PASS | 2,028 | 65,008 | 65,008 | 0 | 64 | 65,072 | 256 | stop |

All three retrieval keys are scored jointly by exact semantic JSON equality; fences, duplication and wrong values remain failures. Output content hashes, strict scorer status, native counts and exact request/response hashes are in JSON. Separate reasoning/content token counts are unavailable in the saved public counters.

| Case | Prefill ms | Input tok/s | Decode ms | (n−1) tok/s | TTFT any s | TTFT reasoning s | TTFT content s | Total s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| G1-16384-primary | 227,294.212 | 69.650 | 16,225.561 | 10.785 | 227.380 | 227.380 | 239.170 | 243.606 |
| G1-16384-repeat | 227,821.604 | 69.489 | 6,105.370 | 10.319 | 228.939 | — | 228.939 | 234.288 |
| G1-65536-primary | 931,845.713 | 69.763 | 138,526.124 | 0.455 | 934.214 | — | 934.214 | 1,070.484 |

The 16K primary and repeat are independent measurements. Their match proof, fresh request hashes and recount evidence are in JSON; short output lengths may vary. Client TTFT is event arrival time and includes chunk batching/transport overhead.

Historical performance cause: **UNPROVEN**. No claim that schema, sampling or GPU count caused a speed change. The saved 4K baseline is a different occupied window and fixture, not a rerun or matched 16K sample.

Saved 4K baseline: 3,546 input / 145 output tokens; prefill 68.521 tok/s; native (n−1) decode 12.641 tok/s. Full saved provenance is retained.

## Per-load allocation and warmup

| Context | GPU weights MiB label | Host weights MiB label | Native KV bytes | GPU compute bytes | Host compute bytes | Main/indexer nodes | Warm input | Warm evaluated |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 16384 | 30,754.20 | 409,012.22 | 1,560,281,088 | 3,149,998,080 | 58,798,112 | 78/21 | 2,389 | 2,389 |
| 65536 | 30,754.20 | 409,012.22 | 6,241,124,352 | 3,250,661,376 | 159,461,408 | 78/21 | 2,391 | 2,391 |

Weights preserve rounded native MiB labels. Cache/compute values are exact logged bytes with source log hashes and line references in JSON. Full context, slot, no_alloc, graph, CPU/cgroup/GPU-UUID and allocation proofs remain attached. Warmup timings are discarded; each warmup requires a fresh uncached full native 2048-token batch.

Discarded warmup variability (excluded from the three measured cases):

| Context | Input | Evaluated | Cached | Output | Cap | Prefill ms | Decode ms | Client total s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 16384 | 2,389 | 2,389 | 0 | 32 | 32 | 36,857.859 | 5,301.159 | 42.214 |
| 65536 | 2,391 | 2,391 | 0 | 32 | 32 | 37,105.137 | 68,134.398 | 105.266 |

The warmup rows retain their actual native counts and durations even where timing varies substantially. They are discarded warmups, not extra measured cases. The cause of the warmup timing variation is **UNPROVEN**.

## Memory by phase

Memory columns are GiB. Checkpoints are after load/warmup; request rows show sampled used/RSS/cgroup peaks and minimum free/available values, which need not be simultaneous. GPU0 is `GPU-88058d9d-08e5-cb1e-a77a-04cbc1488237`; GPU1 is the other observed GPU.

| Phase | GPU0 used | GPU0 free | GPU1 used | GPU1 free | Host available | RSS | PSS | Cgroup charge |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 16384 after load | 35.939 | 59.032 | 0.033 | 94.938 | 463.545 | 400.103 | 400.103 | 401.639 |
| 16384 after warmup | 35.965 | 59.007 | 0.033 | 94.938 | 463.720 | 400.182 | 400.182 | 401.712 |
| G1-16384-primary request peaks | 35.965 | 59.007 | 0.033 | 94.938 | 463.283 | 400.455 | — | 401.985 |
| G1-16384-repeat request peaks | 35.965 | 59.007 | 0.033 | 94.938 | 461.864 | 401.890 | — | 403.422 |
| 65536 after load | 40.393 | 54.579 | 0.033 | 94.938 | 463.449 | 400.202 | 400.202 | 401.739 |
| 65536 after warmup | 40.418 | 54.554 | 0.033 | 94.938 | 464.031 | 400.301 | 400.301 | 401.832 |
| G1-65536-primary request peaks | 40.473 | 54.499 | 0.033 | 94.938 | 462.943 | 400.662 | — | 402.194 |

| Phase | Anon | File | Mapped | Shmem | Kernel | Owned swap | Host swap |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 16384 after load | 0.437 | 399.493 | 399.494 | 399.492 | 1.710 | 0.000 | 0.073 |
| 16384 after warmup | 0.509 | 399.493 | 399.494 | 399.492 | 1.710 | 0.000 | 0.073 |
| G1-16384-primary request peaks | 0.781 | 399.493 | 399.495 | 399.492 | 1.711 | 0.000 | 0.073 |
| G1-16384-repeat request peaks | 2.216 | 399.493 | 399.495 | 399.492 | 1.714 | 0.000 | 0.073 |
| 65536 after load | 0.442 | 399.586 | 399.588 | 399.586 | 1.710 | 0.000 | 0.073 |
| 65536 after warmup | 0.534 | 399.586 | 399.588 | 399.586 | 1.711 | 0.000 | 0.073 |
| G1-65536-primary request peaks | 0.895 | 399.586 | 399.588 | 399.586 | 1.712 | 0.000 | 0.073 |

**Cgroup charge is not exact model RAM.** File/mapped/shmem overlap; they are not added. Native host workspace is already included in observed process/cgroup totals. No assumption treats all cache as reclaimable. RSS may double-count shared pages, and request PSS is unavailable between quiescent checkpoints.

The existing required-host-demand helper may report UNAVAILABLE where file_mapped is slightly larger than file. Raw components remain visible. The capacity analysis below defines a conservative conditional component bound without changing the live helper. Pre-existing host swap is distinguished from owned model swap and host swap I/O.

| Case | Samples | Coverage est. | Max gap s | Cgroup faults Δ | Major faults Δ | OOM Δ | OOM kill Δ | Host OOM kill Δ | Swap-in Δ | Swap-out Δ |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| G1-16384-primary | 228 | 0.934 | 1.146 | 698,737 | 1 | 0 | 0 | 0 | 0 | 0 |
| G1-16384-repeat | 220 | 0.935 | 1.143 | 1,010,215 | 0 | 0 | 0 | 0 | 0 | 0 |
| G1-65536-primary | 1,000 | 0.934 | 1.370 | 1,691,005 | 0 | 0 | 0 | 0 | 0 | 0 |

Coverage is an estimate from half-interval sample windows, not continuous observation. Leading/trailing gaps, collection duration/overhead, absolute counters and per-metric availability are preserved in JSON. Lifetime memory.peak is separate from request-only sampled peaks.

## Capacity estimates

**Conditional memory estimates only; none of these larger sizes was allocated or inferred.**

| Configured tokens | Native KV GiB | Estimated total used VRAM GiB | Projected free GiB | Cushion above 16 GiB | Current-ladder host demand +25% GiB |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 131,072 | 11.625 | 46.410 | 48.562 | 32.562 | 504.777 |
| 262,144 | 23.250 | 58.285 | 36.687 | 20.687 | 505.090 |
| 393,216 | 34.875 | 70.160 | 24.812 | 8.812 | 505.402 |
| 524,288 | 46.500 | 82.035 | 12.937 | -3.063 | 505.715 |
| 1,048,576 | 93.000 | 129.535 | -34.563 | -50.563 | 506.965 |

The used-VRAM column is an estimate with the observed **0.621094 GiB unavailable/unclassified total − used − free gap held fixed**. That gap is excluded from estimated USED but remains unavailable. Do not substitute total minus free for reported USED. Native weight/cache/compute components and unreported residuals remain separate in JSON.

**384K (393,216 total tokens)** is a practical conditional memory candidate, leaving **24.8115 GiB free**, or **8.8115 GiB above the 16 GiB reserve**. 256K offers more cushion. The algebraic ceiling of **490,474 tokens** (490,240 rounded down to 256) has essentially no uncertainty cushion and is not validated. 512K fails the reserve; native 1M exceeds this fixed single-GPU physical capacity.

Measured-basis formulas, with C in configured tokens:

- KV(C) = 95,232 × C bytes.
- Native device compute(C) = 3,250,661,376 + 2,048 × (C − 65,536) bytes.
- Native host workspace(C) = 159,461,408 + 2,048 × (C − 65,536) bytes.
- Conditional free(C) = 58,517,880,832 − 97,280 × (C − 65,536) bytes, less any unmodelled growth.
- Current-ladder host anchor retains max(file, mapped, shmem) once plus anon/kernel, compares inclusive RSS/PSS/native alternatives without adding them together, projects only native workspace growth, then applies ×1.25.

The compute slopes are measured allocation relationships, not guaranteed peak bounds beyond 64K. Weights retain rounded native labels: GPU 30,754.20 MiB and host 409,012.22 MiB. Bytes and binary GiB are distinguished in JSON; native 1M is 1,048,576 tokens.

**Historical host provision remains relevant.** The accepted 4K run had about **70.639 GiB additional charged file**, not extra weights or proved entirely reclaimable. Retaining those historical components gives about **590.708 GiB including 25% headroom**, or about **591.636 GiB projected to 384K**, before unrelated host demand and unmodelled growth. This is distinct from the current-ladder ~505 GiB conditional projections above. The existing **640 GiB tested container cap is a conservative planning provision, not a proved minimum VM allocation or verified future fit**; OS and other services also need capacity.

The live required-demand helper remains UNAVAILABLE where mapped slightly exceeds file. This descriptive conditional bound does not repair it into exact model RAM. Native host workspace is shown separately; its exact anon/file subdivision was not isolated, and it is not added again to inclusive cgroup totals. Sampled peaks are not absolute. Memory fit establishes neither speed nor retrieval correctness above 64K.


No context above 64K was allocated or inferred by this ladder. Capacity ceilings do not validate performance or correctness at 128K/256K/512K/native 1M. Any projection must preserve 16 GiB GPU reserve and 25% headroom above defensible host demand.

## Restoration and evidence limits

Final receipt: **PASS**; phase `RESTORED`; host session closed `True`; tunnel ports `{"31002": "CLOSED", "31004": "CLOSED"}`.

Canonical restoration verified the original Qwen 1M TP2 running intent and matched the captured manager and control/boot service states. Authenticated Worker1 LAN control status was ready and the restoration-only inference check passed. No campaign container or listener remained, the lifecycle lease was released, and the supervisor exited 0 after waiting for the host session and confirming both tunnel ports closed. Production code/configuration was unchanged. Restoration evidence is separate from measurement success.

Raw private requests/responses, reasoning and token IDs remain in the original private evidence. This report uses saved sanitized evidence; report preparation made no VM contact. SHA-256 identities for every report input are in companion JSON.
