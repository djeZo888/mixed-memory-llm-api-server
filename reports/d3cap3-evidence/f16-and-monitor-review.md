# D3CAP3 — F16 and loading-monitor source review

2026-09-15. Task-local review only. **CAP3 live results PENDING**; the parent owns
all VM operations and final packaging. This reviewer made no host contact and
performed no allocation, generation, build, or profile change.

## Pinned source and patch boundary

The VM source root reported by the parent,
`/data/build/d3p-d3b2-20260915/source`, is clean upstream
`b29c606e28a01b1bc8c1351026a0fa6e616bf6c4` (tree
`950999fe62b7fe55f44ab5b7394e3c8542f37f12`). It is **not** the patched tree;
the derived-tree object is absent there. Local review used matching upstream
blobs and the retained patched copy under sibling
`../D3PD-20260915/llama-upstream`, relative to this task directory.

Repository patch: `repo/containers/llama-cpp/strict-model-chat.patch`.
SHA256: `43e4aeb5b63dbb82d7457526000391ba52d49a408040ec736fb302092e734f3b`.
Declared derived tree: `0075e6f2ca5b8a3f13c0725e35f60a0ceb2b2b5e`.
The patch adds 28 diagnostic lines in `llama_context::sched_reserve()`, adds
`tools/server/server-chat-model.h`, and changes chat route registration in
`tools/server/server.cpp`. It does not change cache types/defaults, type
propagation, cache construction, or log filtering. Bind clean upstream plus
this exact checked patch to the installed runtime/image provenance; do not
claim the host checkout itself is the derived tree.

SHA256 values checked locally:

| Source file | SHA256 |
| --- | --- |
| Clean upstream `src/llama-context.cpp` | `6429ebec7c926945987e6fe037317af0f99265490bc14b0606d9487a62a76453` |
| Patched `src/llama-context.cpp` | `1d0b5b495dadd57d9068efd9a98252a7ce2c57d686d6073a50d18e40e4897418` |
| `src/llama-kv-cache-dsa.cpp` | `85d76ec2cf3f796aaed04557bdccc9fa151b84128046d48ba1017696e7801eef` |
| `src/llama-kv-cache.cpp` | `16b40ff274e5aed3827f0d1c13a04f4f44c4d800c4eecbb5294b04127ab213c3` |
| `common/common.h` | `7cfcc6a57122702ea35d04ed20861aef162bd94f55cfbbf9fd23ee3127fe6cb4` |

## Why the combined dtype line is not a readiness gate

Upstream `src/llama-kv-cache.cpp:301-304` contains a combined K/V dtype summary,
but emits it at library INFO. `common/common.cpp:394` installs the callback;
`common/log.cpp:529-546` maps library INFO to TRACE and filters by verbosity.
`common/log.h:25` defines TRACE=4, while `common/common.h:534` defaults to 3.
Thus the unchanged default suppresses that summary. The retained GLM logs do
not demonstrate its emission. Missing `K (f16)` and `V (f16)` on one line is
not a model failure. The added D3T records use WARN and contain no dtype fields.

## Effective F16 proof contract

Require all of the following, bound to the current attempt:

1. Verified immutable image, binary, upstream source, and checked patch.
2. Actual protected container contract and PID argv agree, including entrypoint
   and exact reviewed model/context/placement. No unreviewed CLI overrides.
3. Actual process environment has no dtype override. The relevant upstream
   options are `-ctk`/`--cache-type-k` and `-ctv`/`--cache-type-v`, with environment
   names `LLAMA_ARG_CACHE_TYPE_K` and `LLAMA_ARG_CACHE_TYPE_V`
   (`common/arg.cpp:2433-2458`). Do not dump unrelated environment or secrets.
4. Fresh complete native diagnostic group, bound to the current container
   `StartedAt` and process lifetime: actual context 1048576, one slot,
   `no_alloc=0`, required fused graph, and exact observed cache allocations.

Upstream source chain: `common/common.h:587-588` defaults main K/V to F16;
`common/common.cpp:1751-1752` copies types; `src/llama-context.cpp:385-395`
passes types into memory; its **upstream** lines `3699-3702` reject unequal
MLA K/V types (patched lines `3727-3730`). Upstream context defaults are
`3644-3645` (patched `3672-3673`). `src/llama-model.cpp:2294-2347` selects the
GLM_DSA memory path; `src/llama-kv-cache-dsa.cpp:29-53` passes those types to
main and indexer caches. `src/llama-kv-cache.cpp:230-234` creates K tensors
using `type_k` and no separate V tensor for MLA.

Report this as effective F16 cache construction established by source/defaults
and protected actual launch state, corroborated by real allocation. It is not
a directly emitted dtype observation. **Independent V allocation is
inapplicable**: the main MLA and indexer caches are key-only storage. Bytes
alone cannot distinguish F16 from another 16-bit type; missing launch/default
provenance leaves that exact proof gap open.

## Allocation cross-check

Retained exact model metadata in `repo/reports/d3m-metadata.json`,
`native_context_plan`, gives main width 576, indexer width 128, and GPU layer
counts 40/12 and 38/9. At one stream and 1048576 cells:

- CUDA0: `(40*576 + 12*128) * 2 * 1048576 = 51539607552` bytes (48 GiB).
- CUDA1: `(38*576 + 9*128) * 2 * 1048576 = 48318382080` bytes (45 GiB).

`src/llama-kv-cache.cpp:685-699` returns actual allocated buffer sizes when
`no_alloc=0`; `src/llama-kv-cache-dsa.cpp:98-103` sums main and indexer sizes.
Patch lines `40-47` emit those sums and the end marker (derived context lines
`716-723`). Capacity/allocation does not establish occupied 1M context,
executed-kernel profiling, instantaneous peaks, client acceptance, or boot.

## Task-local monitor review

Reviewed `transition.py`, `cheap-core.py`, `common.py`, and `run-operator.py`.
The initial 1.5-second metric timeout and 2-second inspect timeout could have
stopped healthy slow sampling before the authorized 10-second freshness bound.
The reviewed correction makes loading identity inspection and subprocess
metrics consume the remaining shared `heartbeat + 10s` deadline. Watchdog and
producer duration/gap predicates use 10 seconds; values above 2 seconds are
recorded as slow sampling. Call durations/budgets and rejected-observation
evidence are retained. The loading deadline is cleared before idle checks.

The controller drains producer output without synchronous remote polls and
records controller receipt timestamps separately. Native logs are filtered by
current `StartedAt`, including reuse of the same stopped container. Cheap load
sampling contains no PSS; full PSS remains at idle boundaries. No further
concrete defect was found in this bounded review. This is code inspection,
not independent execution of the parent's offline tests or live acceptance.

## Preserve earlier evidence

D3CAP2 remains **FAIL** with one allocation attempt and zero generations.
Its late actual 1048576 / one-slot / fused / real-allocation records appeared after
monitor stop; they do not establish accepted readiness or retroactive dtype
acceptance. Preserve its `actual_f16_kv_types` unestablished status. Target
exit 137 / OOMKilled false and shutdown host deltas 13 pages in / 3114 pages out
remain cause-unknown; no such deltas occurred in its 58 retained load samples.
CAP3 must use fresh counters and refuse new unsafe swap/OOM/resource conditions.
