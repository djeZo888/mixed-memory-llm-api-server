# D3T native startup diagnostic — one small D3P-owned patch

**Observed 2026-09-15, bounded read-only Worker1 SSH; no generation, reload,
build, GPU allocation or installed-file edit.**

Current container `bb77b764cb9677f3c04c1e60359d287a15abb304ba289f38703e58b5a6fc0d55`
still uses old D1 image
`sha256:6866856c573d69d504f82265321b182f631a7b3912a1ed1b4efbf893729d4e62`.
Its complete bounded Docker JSON log was 52,632 bytes, SHA256
`473d35975224b148fa6d756651b62ec9094a642333bdf6b23602714691ba8eac`.
It proves one slot / actual `n_ctx_slot = 32768` at line 35. It contains **no
selected Flash Attention / Lightning Indexer or allocated compute/cache buffer
lines**. Source capability and absence of warnings do not establish selection.

Installed source `/data/build/d1-glm53-20260915/source` is pinned at
`b29c606e28a01b1bc8c1351026a0fa6e616bf6c4`.

| File | SHA256 | Exact useful seam |
|---|---|---|
| `src/llama-context.cpp` | `6429ebec7c926945987e6fe037317af0f99265490bc14b0606d9487a62a76453` | `resolve_fused_ops` 505–580 resolves actual backend support; `sched_reserve` 582–714 builds/reserves full-memory pp/tg graphs and obtains actual allocated sizes |
| `src/models/glm-dsa.cpp` | `51eb8e82df5d607eae137c7fbf358410c0f992c4842b8df9d5ca68da7f7ee3f3` | 317–320 selects `cparams.fused_lid` / `ggml_lightning_indexer`; 322–354 is the unfused score path |
| `src/llama-graph.cpp` | `90f5c6f082790599124630680ba1293d702b369e9ce9088680d210b69905c8d3` | `build_attn_mha` 2615–2638 selects the actual Flash Attention graph node |
| `src/llama-kv-cache.cpp` | `16b40ff274e5aed3827f0d1c13a04f4f44c4d800c4eecbb5294b04127ab213c3` | 276–294 allocates real cache buffers; existing INFO output uses rounded MiB |

## Exact minimal patch proposal

D3P owns implementation and integration with its separate strict-alias patch.
Change **only `src/llama-context.cpp`, `llama_context::sched_reserve()`**.
No new public API, configuration, inference operation, profiler or framework.
Emit fixed numeric/backend-name diagnostic lines using `LLAMA_LOG_WARN` (the
current server retains warning output while these INFO lines are absent).
Restrict emission to `model.arch == LLM_ARCH_GLM_DSA`.

After the final pp reserve succeeds (immediately after current line 683), count
`LLM_FUSED_OP_LIGHTNING_INDEXER` and `LLM_FUSED_OP_FLASH_ATTN` entries from
`get_gf_res_reserve()->get_fused_nodes()`. Emit:

```
D3T_NATIVE_V1 kind=graph n_ctx=1048576 n_ctx_seq=1048576 n_seq_max=1 n_batch=2048 n_ubatch=512 flash_attn=1 fused_lid=1 lid_nodes=21 fa_nodes=78 no_alloc=0
```

Values above illustrate the expected native case; **print actual values** from
`cparams`, counted graph entries and `model.hparams.no_alloc`. The one-slot 32K
sanity load uses the same record with its actual context. This proves a selected
reserved graph, not an executed CUDA kernel or instantaneous allocation peak.

Inside the existing backend loop (685–696), after actual
`ggml_backend_sched_get_buffer_size(sched.get(), backend)` has populated the
size, emit one exact-byte record per backend:

```
D3T_NATIVE_V1 kind=compute backend=CUDA0 bytes=<actual size_t>
D3T_NATIVE_V1 kind=compute backend=CUDA1 bytes=<actual size_t>
```

Use `ggml_backend_buft_name(buft)` and `backend_buf_exp_size[i]`, `%zu`.
Then iterate existing `memory->memory_breakdown()` (declared at
`src/llama-memory.h:119`) and print exact bytes per returned buffer type:

```
D3T_NATIVE_V1 kind=cache backend=CUDA0 bytes=<actual size_t>
D3T_NATIVE_V1 kind=cache backend=CUDA1 bytes=<actual size_t>
```

Use `ggml_backend_buft_name(buft)` and the returned size. Do not print tensors,
prompts, tokens, request bodies, environment, keys or model payload. Re-reserve
may emit another tiny group; the probe consumes the latest complete group and
stops on explicit fusion disable/error lines. Do not suppress allocation errors.

## Acceptance and dependency

D3P/root review and combine both patches into **one separately authorized VM
build**. Record patch/source/binary/image identities. The final live source
profile must bind that measured image; D1 remains old baseline only.
The concrete D3T telemetry parser recognizes exactly these records and requires
actual 1,048,576 context, one slot, fused indexer and FA node counts, real
allocation (`no_alloc=0`) and positive CUDA0/CUDA1 compute/cache byte records
before native occupancy. Later 32K and native-load sanity still need separate
authorization. No inference or native-capacity acceptance is claimed here.

Fresh-host storage registration `/etc/local-ai-server/storage.json` is absent on
this historical VM. Current exact ext4 mount UUIDs were rechecked:
`/data=8daf56f1-5649-4163-9d87-919c2d271875`;
`/data/models-large=a6d4ab58-84e1-4e48-9a67-13ad1c6f6e0a`.
The task-specific telemetry pins these existing D3 identities only; it does not
change installer registration or turn them into defaults for another host.
