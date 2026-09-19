# GLM G1 saved-data verification — 2026-09-19

**One measured 4K request completed at about 0.46 output tokens/s, but strict retrieval acceptance failed:** `HARNESS_FAILURE / invalid_answer_json_unscored`. Native input was **3,546 tokens** in a **4,096-token configured window**, with **231 output tokens**. **16K and 64K were NOT_TESTED because this response-contract failure stopped the ladder, not because the deadline expired.** No larger-context performance or occupied-context correctness is established.

## Measured result

| Measured G1-4096-retrieval metric | Result |
| --- | ---: |
| Native evaluated prompt / cached tokens | 3,546 / 0 |
| Native prompt interval / rate | 51.954221 s / 68.252395 tokens/s |
| Native decode interval / emitted `predicted_per_second` | 505.195535 s / 0.455269 tokens/s |
| Completion count / decode interval | 0.457249 tokens/s |
| First reasoning / first content arrival | 52.119385 / 320.347308 s |
| Client dispatch-to-drain / completion delivery rate | 557.260121 s / 0.414528 tokens/s |
| Output / requested output cap | 231 / 256 tokens |
| Assigned GPU sampled used peak / minimum reported free | 34.853516 / 60.118164 GiB |
| Known-process RSS / cgroup `memory.current` sampled peaks | 400.397598 / 401.937172 GiB |

Native prompt rate is `3546 / (51954.221/1000)`. The pinned native decode convention is `(231−1) / (505195.535/1000)`, exactly matching saved SSE `predicted_per_second`; the simple count rate uses 231 instead. Completion accounting includes reasoning; no visible-content-only rate is established. Input occupied 86.57% of the window; input plus output occupied 92.21%. Trial orchestration took 597.869827 s, including 38.873495 s fixture preparation; this is separate from inference latency.

## Strict response outcome

Transport was `COMPLETE`, with `finish_reason=stop`, `[DONE]` and observer `OK`. Exact wire content is a JSON object, literal `</think>`, then a duplicate JSON object, not one harmless fence. Both separately decoded objects match the expected START/MIDDLE/END fixture strings, but this offline comparison **does not normalize or reclassify the unscored strict failure**. The [JSON report](benchg1-verified-20260919.json) preserves exact safe answer content, expected/actual fields, row and response hashes. The single accepted 4K warmup is discarded from the measured table: 2,391 evaluated input, zero cached, 235 output tokens and 552.517216 s transport.

The reasoning/content boundary cause remains undetermined; the saved template/parser metadata does not establish responsibility for this response.

## Memory and fixed placement

Request memory comes from **516 saved samples** inside worker-monotonic interval `312892.716608083–313449.976728708`. Estimated coverage was 92.48%, maximum gap 1.194 s; these are sampled peaks, not continuous observation. Collection wall time was 30.468 s (5.47%); its causal performance cost is unknown and is not subtracted. Owned process/cgroup swap and OOM events were zero; host swap remained 81,788,928 bytes without increased swap-out. Host swap is separate from model swap. Minimum host `MemAvailable` was 464.106392 GiB. Cgroup lifetime peak observed during the request was 401.937416 GiB; it is not a request-only peak. Readiness/warm-idle PSS checkpoints were 400.078587/400.157059 GiB, distinct from RSS. Final-attempt and earlier-load peaks remain separately labeled in JSON; conservative mapped-file plus shmem receipts can overlap and do not establish exact required RAM or make all file memory reclaimable.

The accepted load used GLM5.3 UD-Q4_K_XL, fixed N76 (**76 MoE expert layers placed in host RAM**), one slot, F16 K/V, batch 2048 / ubatch 512, 96 guest CPUs, and CUDA0 only on `GPU-88058d9d-08e5-cb1e-a77a-04cbc1488237`. Native proof reported 80/80 offload, 78 main / 21 indexer nodes, host weights **409,012.22 MiB (399.426 GiB)**, GPU weights **30,754.20 MiB (30.033 GiB)**, cache **390,070,272 bytes**, GPU compute **3,124,832,256 bytes (2.910 GiB)** and host compute 33,632,288 bytes. Load elapsed was 182.276093 s. Image, model revision, cap and per-attempt allocation evidence are in JSON.

Actual Docker memory and memory-swap limits both equaled **687,194,767,360 bytes (640 GiB)**; cgroup `memory.max` matched and `memory.swap.max` was zero. This is a bounded validation cap, not minimum VM RAM. Earlier whole-host unavailable-plus-host-swap bounds with a **25% host reserve** were 521.908/521.520 GiB, supporting the chosen cap; these include unrelated host demand and sampled accounting uncertainty. Final settings added observer logging, CUDA_Host recognition, immediate loading resource stops and the exact loading GPU-timeout gap rule with fresh reserve proof. Three earlier setup failures remain in the JSON attempt history.

## Larger-context memory projections

All contexts above 4K below are **NOT_TESTED**. Projections assume unchanged non-cache workspace.

The primary memory projection uses `delta_cache = 95232 × (target_tokens−4096)`, then `projected_free = measured_min_free−delta_cache`; headroom is projected free minus the **16 GiB GPU reserve**. The source-derived F16 slope is `(78×576 + 21×128)×2 = 95,232 bytes/configured token`; only the 4K allocation was observed. The measured-free baseline includes existing 4K runtime overhead and preserves the **666,894,336-byte (0.621094 GiB)** difference between device total, reported free and reported used, without assigning that difference to a specific cause.

| NOT_TESTED configured context | F16 cache GiB | Projected used GiB | Projected reported free GiB | Headroom after 16 GiB reserve |
| --- | ---: | ---: | ---: | ---: |
| 16K — 16,384 tokens | 1.453 | 35.943 | 59.028 | 43.028 |
| 64K — 65,536 tokens | 5.812 | 40.303 | 54.669 | 38.669 |
| 128K — 131,072 tokens | 11.625 | 46.115 | 48.856 | 32.856 |
| 256K — 262,144 tokens | 23.250 | 57.740 | 37.231 | 21.231 |
| 512K — 524,288 tokens | 46.500 | 80.990 | 13.981 | -2.019 |
| 1M — 1,048,576 tokens | 93.000 | 127.490 | -32.519 | -48.519 |

These conditional calculations assume unchanged placement and non-cache workspace; larger contexts can increase workspace and other allocations. The separate component floor, `GPU weights + cache + measured 4K compute + 16 GiB`, leaves only **0.149 GiB at 512K**, excluding other overhead: it is neither a safe nor validated fit. The measured-free projection already misses the reserve at 512K. At 1M, GPU weights plus cache alone total **123.033 GiB**, exceeding the 95.593 GiB device. Extra host RAM does not change this fixed GPU cache placement. Host weight storage stays about 399.426 GiB; weight-only plus 25% is 499.282 GiB, excluding workspace, OS and transient demand. Larger-context host RAM, throughput, latency and quality remain unknown.

## Campaign outcome and provenance

The immutable campaign epoch/deadline stayed `1789826207.34127 / 1789847807.34127` (13:56:47.341270 / 19:56:47.341270 UTC), without budget reset or repeated completed requests. Saved final receipts record original production restoration and authenticated Worker1 private-LAN control/inference, with no owned containers, benchmark host/listeners or held canonical lease; supervisor exit was **19:27:45.068002 UTC**, independently confirmed by root. This verification used saved local data only: no VM contact, runtime changes, inference, new tests or benchmark source edits.

Source is `14764639915f427e01a74eab51004d5e6ead7ad1`, descended from the reviewed Qwen report commit `47a29cf391776a3806af2ac04123f2bf79caf831`. Detailed formulas, exact native timings, safe content, source/evidence SHA256 provenance and retained failed-attempt receipts are in the JSON report. Raw prompts, reasoning and SSE remain private.
