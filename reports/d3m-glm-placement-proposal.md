# D3M — partial experts with a native-context plan

2026-09-15 · reviewed base `4ab862f829a560e00ae3f40d9358456db0a4c0e9` · coordination revisions 2–3.
**PASS: bounded metadata/source inspection and conditional fit arithmetic. NOT_TESTED: candidate load, occupied long context, peak allocation or performance. V1G2 lease is released per revision 3; D3 GLM32K remains held unchanged.**

## One candidate; native context is the priority

Replace `--cpu-moe` with **`--n-cpu-moe 76`**. Retain **`--tensor-split 1,1`**, F16 caches and one slot. This is the largest late-prefix GPU-expert variant that fits the native-context arithmetic below with a **24 GiB per-card reserve**. It offloads only main blocks 76–77 to GPU1. No profile/source implementation or live change occurred; preserve the baseline profile.

First compare at the existing **32,768** context. After separate review and lease release, use the same placement through **65,536 → 131,072 → 262,144 → 524,288 → 1,048,576**, advancing only after each occupied-context proof. The last value is the native target, not a RoPE extrapolation or a claim already tested. Unsloth gives the exact maximum; the downloaded metadata and prior live `n_ctx_train` agree. Z.ai also documents 1M context. [Unsloth](https://unsloth.ai/docs/models/glm-5.3.md), [Z.ai](https://docs.z.ai/guides/llm/glm-5.3), [D3 live metadata](d3-evidence/32k-probe.json).

Keep all other baseline settings: `--parallel 1 --n-gpu-layers 999 --split-mode layer --device CUDA0,CUDA1 --load-mode none --jinja --no-webui --chat-template-kwargs {"clear_thinking":true}`, model/shards, alias `glm-5.3`, native API-key-file, authenticated VM-loopback publication on port 30002, manual boot/restart-no and default 112 inference threads. Retain default batch 2048 / ubatch 512, Flash Attention auto, F16 K/V, no speculative/MTP or NUMA change. Requests explicitly use `reasoning_effort:"low"`, no reasoning-budget override or replayed reasoning. Embedded template SHA256 remains `15d2a7176beb599de0a59af8314b4869011e416cff7f65748b314940d3379b0e`.

Runtime source **`b29c606e28a01b1bc8c1351026a0fa6e616bf6c4`**, image **`sha256:6866856c573d69d504f82265321b182f631a7b3912a1ed1b4efbf893729d4e62`** matched existing source/container. Captured help was read; no runtime/help/GPU helper was launched. A scoped container-environment check found no cache/context/placement/batch overrides. Native-window progression changes only context after separate approval; no RoPE settings are proposed.

## Metadata evidence and access bound

[Compact metadata](d3m-metadata.json) records all 1,809 descriptors losslessly as 36 tensor families plus member layer/shard/offset, dimensions, quant type and bytes; it includes exact 79 per-layer totals and 11 shard identities. [Pinned source citations](d3m-source-citations.json) give paths, line ranges and findings.

Only the 11 protected shards under `/data/models-large/glm-5.3-ud-q4-k-xl/UD-Q4_K_XL` were opened. Exact ext4 mount UUIDs matched D3: `/data` `8daf56f1-5649-4163-9d87-919c2d271875`; `/data/models-large` `a6d4ab58-84e1-4e48-9a67-13ad1c6f6e0a`. Receipt hash `bcd8d9f85baa9bd1fe54dc65b9022487307190cf11583580ab66af845b53f48b` and every sealed device/inode/size/mtime/ctime/owner/mode/link identity matched before/after; receipt and mounts were rechecked. No payload integrity rehash is claimed.

The temporary stdin-only Python parser used `O_RDONLY|O_NOFOLLOW|O_NOATIME`, exact unbuffered reads and seeks past variable metadata. Limits: 16 MiB metadata span/shard,4 MiB actual reads/shard/parser invocation,64 KiB/read,10,000 tensors/shard,1,024 keys/shard, bounded arrays,256 MiB process address space and 60 CPU seconds. **Initial descriptor pass: 3,932,946 bytes**, ending at each descriptor boundary; no padding/weight-body reads, mmap, weight allocation, full-file scan, rehash, download or VM file/package installation. Existing D3's shard 1 helper informed the format; its tokenizer-array materialization was replaced with bounded skips. A supplemental bounded shard 1 read inspected architecture arrays: `glm-dsa.attention.indexer.types` is absent, so the pinned native-context default applies. It read another 3,814,771 metadata bytes; total model metadata reads were **7,747,717 bytes**. Both parser hashes are recorded in JSON.

Byte formula: `product(dimensions) / block_elements × block_bytes`, requiring whole quant blocks in each row. Pinned `gguf-py/gguf/constants.py:5655–5693,5848–5887` and matching C structs define **F32=1/4, Q8_0=32/34, Q4_K=256/144, Q5_K=256/176, Q6_K=256/210** (elements/bytes). No average bits-per-weight estimate was used.

| Stored block(s), zero-based | Routed expert bytes **per block** | Other bytes **per block** | Routed down / gate / up types |
| --- | ---: | ---: | --- |
| 0–2, dense | 0 | 426,576,896 | none |
| 3–7,9–74 | 5,838,471,168 | 232,329,216 | Q5_K / Q4_K / Q4_K |
| 8 | 7,071,596,544 | 232,329,216 | Q6_K / Q5_K / Q5_K |
| 75–77 | 6,266,290,176 | 232,329,216 | Q6_K / Q4_K / Q4_K |
| 78, MTP | 5,838,471,168 | 312,619,008 | Q5_K / Q4_K / Q4_K |

Other tensors use Q8_0/F32 and include **40,108,032 bytes of shared experts per MoE block**. Separate input/output matrices each contain 1,011,056,640 bytes (Q8_0); output norm 24,576 bytes (F32). Routed expert dimensions are down `[2048,6144,256]`, gate/up `[6144,2048,256]`:256 experts,8 selected/token.

Total protected files **467,289,116,837 bytes(435.196903 GiB)** = **467,279,569,920 tensor bytes** + **9,546,917 metadata/padding bytes**. Shard 1 has zero tensors; shards 2–11 exactly reconcile descriptor-aligned data starts plus nonoverlapping tensor spans to file sizes, without reading bodies. Metadata 79 blocks = 78 main +1 NextN/MTP. The loader skips 26 MTP tensors totaling6,151,089,152 bytes; its 1,024-byte router bias lacks the skip flag and is conservatively counted on GPU1. Thus stored payload and loaded main weights must not be conflated.

## Exact placement and cache layout

[`common.h:1131–1149`](https://github.com/ggml-org/llama.cpp/blob/b29c606e28a01b1bc8c1351026a0fa6e616bf6c4/common/common.h#L1131-L1149) generates CPU overrides for the initial N blocks' routed `ffn_*_exps`; shared `_shexp` stays with its layer. Remove global `--cpu-moe`: loader first-match semantics would otherwise defeat N.

[`llama-model.cpp:1463–1521`](https://github.com/ggml-org/llama.cpp/blob/b29c606e28a01b1bc8c1351026a0fa6e616bf6c4/src/llama-model.cpp#L1463-L1521) uses cumulative normalized ratios and `upper_bound(split, layer/80)` here: 79 stored blocks plus output, start 0 under ngl999. The retained 1:1 split assigns blocks 0–39 to CUDA0 and 40–78/output79 to CUDA1. Input stays CPU. MTP skipping does not change that denominator. Combined free VRAM cannot be assigned equally to the late experts.

| Planned destination | Routed blocks | Routed expert bytes (GiB) | Other tensor bytes, including shared |
| --- | --- | ---: | ---: |
| CPU | 3–75 | 427,869,339,648(398.484375) | 1,011,056,640 |
| CUDA0 | none | 0 | 9,875,911,680 |
| CUDA1 | 76–77 | 12,532,580,352(11.671875) | 9,839,592,448 |

Baseline main routed experts are 440,401,920,000 bytes (410.156250 GiB), all CPU. Shared main experts total 3,008,102,400 bytes, already included in other tensors. CUDA source supports the observed expert quant types; ordinary allocation retains stored bytes, with no extra expert row padding/alignment here. Loader fallback and actual PSS changes remain untested.

**Pinned DSA/MLA cache, one stream:** main blocks 0–77 each store a combined **K-only width 576** (`kv_lora_rank 512 + rope 64`), with V derived from the latent cache; there is no additional generic 64-head V cache. Only **21 full-indexer blocks** store a separate K-only width 128:0,1,2,6,10,…,74. Native metadata has no indexer-types override, so `glm-dsa.cpp` selects that exact GLM5.2 default at `n_ctx_train≥1048576`. Thus F16 cache is **95,232 bytes per token of configured capacity**: `(78×576 +21×128)×2`. Allocation reserves the full selected window, not just current occupancy. CUDA0 has 40 main/12 indexer blocks, CUDA1 has 38/9: **49,152 /46,080 bytes per token**. Dimensions and the selected windows satisfy cache/quant alignment. See [cache and graph source citations](d3m-source-citations.json).

Retain **F16 K/V**; native static fit does not require quantized KV. Pinned MLA requires equal K/V types. Q8_0 support exists, but its MLA Flash Attention path can need temporary F16 conversion. Unsloth's generic q4_1 recipe does not establish this pinned graph's memory/quality behavior; no KV-quantization variant or factor is assumed. [Unsloth KV guidance](https://unsloth.ai/docs/models/glm-5.3.md).

## Native fit and workspace uncertainty

Inventory: two RTX PRO 6000 Blackwell GPUs, each **97,887 MiB =95.592773 GiB**, PHB interconnect; guest KVM 112 vCPUs / 7 NUMA nodes, MemTotal881.782658 GiB. **400 GB/s RAM bandwidth is unmeasured.**

D3's final short-request sample: PSS411.992577 GiB, MemAvailable450.023319 GiB, VRAM16,804/12,940 MiB, process swap 0. At **01:35:57 UTC**, D3M sampled the same running container/PID 149976/image at **16,808/12,940 MiB =16.414063/12.636719 GiB**. Neither is a V1/full-context peak. Bounded existing-log inspection read 28,086 bytes within a 192 KiB cap and reconfirmed 32768 slot context and 112 threads; only selected placement/context lines were retained.

Unchanged split means nonexpert/shared placement stays fixed. Charge each card its **entire observed 32K device-wide allocation**, plus exact F16 cache growth above 32K, plus promoted experts, plus **24 GiB**: 8 GiB for additional workspace and 16 GiB safety floor.

| Native 1,048,576 budget, GiB | CUDA0 | CUDA1 |
| --- | ---: | ---: |
| Observed32K allocation, including nonexperts/context/workspace | 16.414063 | 12.636719 |
| Native F16 cache (reference total) | 48.000000 | 45.000000 |
| Cache growth charged (subtract existing 1.5/1.40625) | 46.500000 | 43.593750 |
| Added routed experts | 0 | 11.671875 |
| Additional workspace/safety reserve | 24.000000 | 24.000000 |
| Planning total | **86.914063** | **91.902344** |
| Capacity less total | **8.678711** | **3.690430** |

The next extra late block would add 5.8359375 GiB to GPU1, exceeding capacity with that reserve; therefore N76 is the conservative single-card choice. No changed tensor-split ratio is needed for this native-first candidate.

This is **conditional arithmetic, not a peak guarantee**. At native capacity/ubatch512, the fused indexer alone produces a 2 GiB F32 score; two F16 masks take 1 GiB each, with additional sparse-mask/graph temporaries. Top-k 2048 does not eliminate the full cache/masks. The unfused 32-head indexer can form a 64 GiB score tensor and is **outside this budget**. Later acceptance must confirm the supported fused indexer and Flash Attention path and measure graph/load workspace; stop if they fall back or exceed reserves. Source support does not prove actual runtime selection/peak.

RAM takes **no credit for expert removal**: retain 411.992577 GiB PSS plus 128 GiB transient allowance =539.992577 GiB, below881.782658 GiB total; historical available memory less 128 leaves 322.023319 GiB. Native F16 cache remains GPU-resident in this plan. Host temporary copies/cache/allocator growth still require observation; refresh memory before testing. Expected benefit is less CPU routed-expert work for two main blocks only; no guessed throughput or speedup.

## Bounded sequential proof after root review

Root must first review this proposal/reserves and separately authorize implementation/lifecycle work. Verify exact mounts/receipts and run both common storage/root guards before/after deployment. Preserve baseline and rollback assets; keep one user/task/slot. No such operation occurred in D3M.

**Fair 32K comparison:** freeze one worker-side fixture using the actual V1 tool schema and body hashes. For baseline and candidate, use equivalent fresh prompt caches, temperature 0, explicit low effort and identical output caps: one uncached ordinary request plus warm repeat(256 each), then one tool call/continuation pair(512 each):4 requests/configuration,8 total. Bound 600 s/request / 40 min generation total, no retry/grid/cache flush. Record actual cached/evaluated/completion counts and compare matched cache conditions and output lengths.

**Then one ascending context sequence, unchanged N76/F16/split:**

| Context | F16 cache CUDA0/CUDA1 GiB | Planning total including 24 GiB reserve CUDA0/CUDA1 | Initial templated-input ceiling |
| --- | --- | --- | ---: |
| 65,536 | 3 /2.8125 | 41.914063 /49.714844 | 57,344 |
| 131,072 | 6 /5.625 | 44.914063 /52.527344 | 122,880 |
| 262,144 | 12 /11.25 | 50.914063 /58.152344 | 253,952 |
| 524,288 | 24 /22.5 | 62.914063 /69.402344 | 516,096 |
| **1,048,576 native** | **48 /45** | **86.914063 /91.902344** | **1,040,384** |

Reserve **8,192 tokens inside each window** for bounded generation, tool results and continuation/template overhead; published output capacity is not extra room outside the window. For each stage, use at most three sequential requests: a cold occupied-context retrieval (128 output tokens), a follow-up tool call (256), then its real worker-side tool-result continuation (256). Measure input with the pinned tokenizer/template including tools/special tokens and require occupancy near the listed ceiling, without truncation/shift. Verify early/middle/late content, valid tool IDs/results and useful cached-token reuse of the stable prefix. Allocation/window size alone is not acceptance.

Keep system/tool definitions and previous text stable; default prompt caching reuses the longest matching token prefix. Retain default no context shift and cache-reuse 0; no new shifted-chunk/persistent-cache policy. The template removes replayed reasoning consistently. Readiness, actual occupancy, correctness, prefix reuse and bounded sampled peaks must pass before advancing; successful 128K is not native completion. Proposed operational time caps are 2/4/8/12/24 hours for the five stages, including prefill and continuations; these are stop budgets, **not performance estimates**. At most 15 progression requests, no retries; timeout is NOT_TESTED at that stage, not proof of model incapacity.

Record per-request prefill/decode/end-to-end timing, all token/cache counts, correctness, bounded 1 Hz per-card VRAM/PSS/available-memory samples and error counts. Label sampled maxima honestly. Stop on CUDA/OOM errors, swapping, guard failure, fallback outside the budget or less than 16 GiB free on either card. Restore 32K baseline after the trial unless root explicitly selects another final state. This proves only the measured workload; long-agent behavior and instantaneous peaks remain broader questions.

## Existing V1G2 throughput — numeric log evidence only

Revision3 authorized this extraction after request-lease release. Matched Docker completion timestamps to coordinator windows: A1 normal **01:35:19.014655–01:36:19.252810 UTC**; A1 stream **01:37:05.643998–01:37:58.843355**; OpenCode **01:38:53.087037–01:41:24.243778**, all 2026-09-15. OpenCode end is coordinator-derived from 151.156741 seconds monotonic elapsed. Alignment is by completion time in these exclusive windows; no request bodies were inspected.

The reader refused logs over 512 KiB and emitted only timestamp/slot/task IDs, token counts and numeric prompt/decode timings. All **38 rows/19 completed task pairs** are in `existing_request_timings` in [metadata JSON](d3m-metadata.json). No raw/unmatched lines, prompts, bodies, headers or keys were emitted/saved. No new generation or benchmark ran.

| OpenCode task, slot 0 | Evaluated prompt tokens | Prompt ms; tokens/s | Decode tokens | Decode ms; tokens/s |
| --- | ---: | --- | ---: | --- |
| 473 | 633 | 13,853.83;45.69 | 11 | 3,237.05;3.09 |
| 474 | 5,058 | 73,828.18;68.51 | 59 | 8,311.18;6.98 |
| 547 | 271 | 7,531.98;35.98 | 74 | 6,851.60;10.65 |
| 622 | 352 | 8,016.72;43.91 | 55 | 4,799.33;11.25 |
| 678 | 106 | 6,177.82;17.16 | 43 | 3,818.67;11.00 |

These are individual real client requests, **not sustained decode benchmarks**. Task 474 supplies a larger 5,058-token prefill observation; the longest listed decode is only 74 tokens. A1 normal tasks 135/148/160/194/202/228/259 and stream tasks 311/323/336/362/370/396/427 yielded 6–33 decode tokens at 2.75–14.13 logged tokens/s; many evaluated only 1–4 prompt tokens. Those tiny/cache-sensitive samples must not be treated as sustained throughput. Timing rows do not expose total prompt/cached counts, so exact cache reuse cannot be reconstructed here. Decode rates use the server's `(tokens−1)/seconds` convention. No average or speedup is inferred.

## Checks and next action

**PASS:** parser syntax/limits and skip-bound tests; exact receipt/stat/mount checks; all 1,809 byte formulas and lossless compact descriptor reconstruction;79 per-layer totals;11-shard offset/alignment/count/payload reconciliation; source pin/scoped cleanliness; captured help/defaults; independent placement/cache arithmetic review. Final diff/secret/attribution/bundle checks are in task-root `handoff.md`.

**NOT_TESTED:** candidate load/inference, actual fusion selection at larger windows, V1 peaks, native occupied context and performance. No protected-state writes, model/API requests, GPU allocations, lifecycle operations, downloads, installs or NUMA tuning occurred. Completed V1G2 numeric timing rows were read under revision 3 authorization. Next: root reviews **one N76/F16/1:1 proposal and native progression**; source implementation and live proof remain separate tasks; request-lease release alone authorizes neither.
