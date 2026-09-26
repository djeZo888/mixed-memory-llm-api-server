# Conditional context estimate, unchanged production480K

The pinned model declares **1,048,576 positions**. That is a plausible
memory-only candidate ceiling for a future trial, conditional on larger-context
workspaces, host charges and runtime limits. The considered range is
**480000 < configured tokens <= 1048576**; it is not an accepted operating range.
No larger allocation or inference was performed. Production context and physical
pool remain480000; actual occupied qualification is reported separately.

The current FP8E4M3 token-indexed cache uses11 DSA layers. Per token:

`11 * (512 latent bytes + 16 FP32 latent-scale bytes + 128 index bytes + 4 index-scale bytes) = 7260 bytes`.

At page-aligned N, the tensor allocation is `(N+64)*7260 + 22528` bytes,
including fixed BF16 KPool live tails. Index allocation uses physical token
slots; algorithmic KPool compression does not divide that allocation by four.

| Cache component | 480000 pool | 1048576 candidate |
|---|---:|---:|
| Base latent/index allocation |3.167217GiB|6.918391GiB|
| FP32 latent-scale sidecars |0.078689GiB|0.171885GiB|
| BF16 live tails |0.000021GiB|0.000021GiB|
| Combined |**3.245927GiB**|**7.090297GiB**|
| Increment |—|**3.844371GiB**|

The native3.17GB log covers the base tensors before sidecar allocation; its
calculation uses1024³ bytes. Separate recurrent/linear states are about0.28GiB
(0.01conv+0.27temporal). With one active request and no speculation, their
persistent shapes do not scale with context. Request maps, metadata, allocator
reservations and transient workspace remain separate; one int32 request map adds
about0.00212GiB across this range, not a complete overhead inventory.

The model config SHA256 is
`bb8f01c42cb92a52ca72e65afb4d5bd8d11aef083cd210e8de25dfb904f23e9f`.
[Official pinned config](https://huggingface.co/zai-org/GLM-5.3-Flash/resolve/eb9eb208eb0d988989d07a6a12d0fdeb5f52574a/config.json)
contains max_position_embeddings1048576,11 DSA layers, latent width512,
index width128 and KPool4. The actual installed model/config and three source
files matched the pinned hashes at23:28:46UTC; see
[evidence](evidence/CAPACITY-SOURCE-IDLE.json).

Source pin `541ddc37cbc92c60dc748db5ff1a2aad0b069a80`:

- [GLM pool](https://github.com/kvcache-ai/sglang/blob/541ddc37cbc92c60dc748db5ff1a2aad0b069a80/python/sglang/srt/mem_cache/glm5_next_memory_pool.py#L153-L201), lines153–201 and320–328; SHA256 `394724b8186eb2c95bf8195e0854d98a07ee1b20d11f9a967295dd84d23db0e3`.
- [Shared pool](https://github.com/kvcache-ai/sglang/blob/541ddc37cbc92c60dc748db5ff1a2aad0b069a80/python/sglang/srt/mem_cache/memory_pool.py#L1792-L1819), lines144–146,244–263,1730–1733,1792–1819; SHA256 `c1efc23f0f10673d19295a5903aa8a1ca76214f5d1b0b84b6b9e167c713a862e`.
- [Pool sizing](https://github.com/kvcache-ai/sglang/blob/541ddc37cbc92c60dc748db5ff1a2aad0b069a80/python/sglang/srt/model_executor/model_runner_kv_cache_mixin.py), functions get_cell_size_per_token/profile_max_num_token/handle_max_mamba_cache/init_memory_pool; SHA256 `c05c1a3c5b9c35c9126f755aca305337a43eb6cee4bb2b3c1a914356d8d3c8e7`.

Use actual sampled free memory, not total minus used: driver-reserved memory is
separate. For candidateN, the conditional GPU inequality is:

`(N-480000)*7260/2^30 + extra_metadata_GiB + extra_workspace_GiB <= measured_min_free_GiB - 0.07*total_GPU_GiB`.

The final H010 load envelope and resulting reserve allowance are in RESULTS.md.
The650GiB Flash cgroup limit is an independent, nearer host constraint even when
host MemAvailable greatly exceeds its15% reserve. File cache is reclaimable in
principle but not proof that a future allocation will be admitted. Higher-context
host charges are unmeasured. No host-memory-per-token fit is justified.

Unknowns include high-occupancy attention/index/top-k scratch space, allocator
fragmentation, expert workspace behavior and peaks between5s samples. The2048
prefill chunk bounds chunk work but does not prove every allocation independent
of occupied context. No speed, quality or supported maximum is extrapolated.

Native pool480000 is distinct from usable input/output bounds: the preserved
wrapper accepts input<=479993 and input+requested output<=479998; native allocation
reports max_req_len479999/max_req_input_len479994. Production output ceiling65536
is unchanged. No tested480K or1M occupied-context claim is made.
