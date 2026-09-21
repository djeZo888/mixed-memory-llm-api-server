# D3PD / D3T native diagnostic contract

Published early, 2026-09-15. FROZEN after coordinator ACK in coordination
Revision2. Graph/compute/cache grammar is fixed to the approved plan; the
acknowledged constant end delimiter completes each group.

## Producer ownership and exact grammar

Only upstream `src/llama-context.cpp`, `llama_context::sched_reserve()`.
Only `model.arch == LLM_ARCH_GLM_DSA`; all records use `LLAMA_LOG_WARN`.
One group after final successful prompt-graph reserve:

```text
D3T_NATIVE_V1 kind=graph n_ctx=<u32> n_ctx_seq=<u32> n_seq_max=<u32> n_batch=<u32> n_ubatch=<u32> flash_attn=<0|1> fused_lid=<0|1> lid_nodes=<size_t> fa_nodes=<size_t> no_alloc=<0|1>
D3T_NATIVE_V1 kind=compute backend=<buffer-type-name> bytes=<size_t>
D3T_NATIVE_V1 kind=cache backend=<buffer-type-name> bytes=<size_t>
D3T_NATIVE_V1 kind=end
```

Each record is one newline-terminated log call, no function prefix in payload.
Existing logger prefixes are outside this grammar. Fields/order/spaces are exact.
Compute/cache lines repeat zero or more times as described below. Names are the
actual `ggml_backend_buft_name()` value; consume bytes as the final ` bytes=`
decimal field, without assuming names are identifiers or printing other data.
No expected context, batch, slots, counts, backend names or sizes are hard-coded.

- Graph: actual `cparams` uint32 fields, bool flags promoted to int, counted
  `LLM_FUSED_OP_LIGHTNING_INDEXER` / `LLM_FUSED_OP_FLASH_ATTN` entries from
  `get_gf_res_reserve()->get_fused_nodes()`, and `model.hparams.no_alloc`.
- Compute: inside existing backend loop, after existing size assignment, one
  record per backend using `backend_buft[i]` / `backend_buf_exp_size[i]`, including
  zero bytes. For `no_alloc=1` these are estimates; never accept as allocations.
- Cache: if `memory` exists, one record per entry in its existing const
  `memory_breakdown()` API (`map<ggml_backend_buffer_type_t, size_t>`). Byte counts
  are exact returned sizes, also estimates when `no_alloc=1`. No tensor names, model payload, prompts, tokens,
  keys, environment or requests are logged.
- `kind=end`: one constant warning call after cache loop, even if no
  cache records. Delimits complete groups without new state/counters/framework.

## Parser handshake (consumer owned by D3T)

Coordinator ACK received in `../coordination-input.md` Revision2; it explicitly
instructs D3T to require end before accepting the latest group. No changes by
D3PD to D3T parser/runner or Manager bodies. D3T consumer implementation remains
its owner's responsibility and is not claimed tested by this source handoff.

For this one-active-model task stream, graph starts a fresh candidate and
invalidates prior allocation maps. Compute records precede cache records. End
commits only that complete candidate. A later incomplete group must refuse
acceptance (do not silently reuse an older complete group). Unexpected ordering,
malformed/duplicate required backend records or explicit disable/allocation/error
lines must refuse acceptance. Multiple concurrent inference contexts are outside
this diagnostic's contract; no process/context IDs or generic logging state.

This proves selected reserved graph and reported allocation sizes, not executed
kernels or peak GPU allocation. D3T still requires actual slot/thread/resource
evidence and later separately authorized real 32K/native request sanity.

## Reproducible source

One explicitly combined `containers/llama-cpp/strict-model-chat.patch` against
`b29c606e28a01b1bc8c1351026a0fa6e616bf6c4`; retains the D3P guard bytes unchanged.
Existing fixed `prepare-d3p-source.py` verifies clean pin, patch SHA256 and final
derived tree before compilation.

- Combined patch SHA256: `43e4aeb5b63dbb82d7457526000391ba52d49a408040ec736fb302092e734f3b`.
- Combined Git tree: `0075e6f2ca5b8a3f13c0725e35f60a0ceb2b2b5e`.
- Final `src/llama-context.cpp` SHA256: `1d0b5b495dadd57d9068efd9a98252a7ce2c57d686d6073a50d18e40e4897418`.

No unpublished derived commit fetch, installer changes or VM operations.
