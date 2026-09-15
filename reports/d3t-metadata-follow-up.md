# D3T — exact read-only planning follow-up

No tuning or new live probes were performed. **No --n-cpu-moe N value is proposed yet.** D3's existing GGUF evidence covers metadata/template from shard1, whose tensor count is0; it does not contain per-layer expert tensor byte sizes.

At the final D3 short-request32K snapshot, each GPU reports97,887MiB total; used16,804/12,940MiB, leaving **81,083/84,947MiB unallocated**. This is not a safe expert-offload allowance: V1's real schema/prompt/workspace peak and a reviewed margin must be subtracted. Aggregate free VRAM is not interchangeable between GPUs.

After V1 evidence and explicit lease release, a bounded read-only planning task should:

1. Reverify the exact two mount UUIDs and protected11-shard receipt/stat identities. Do not download, copy or reread/hash tensor payloads.
2. Read only GGUF headers/metadata/tensor descriptors from all11 immutable shards, seeking past variable metadata as needed. Use pinned llama.cpp/GGUF type/block-size definitions to compute actual stored bytes for each expert tensor; record name, layer index, quantization type, dimensions and bytes. Account for mixed quantization and distinguish tensor bytes from file padding.
3. Verify the pinned implementation of --n-cpu-moe N: firstN layers' experts stay onCPU. Match its actual expert-tensor override patterns; do not infer membership solely from a guessed name or divide467GB by79 layers.
4. Derive the actual layer-to-GPU assignment for the existing layer split, CUDA0/CUDA1 and1:1 tensor split from pinned placement logic/evidence. Later GPU-offloaded expert layers may concentrate onGPU1; do not split their bytes equally between GPUs.
5. Combine cumulative per-GPU expert bytes for candidateN with the measured V1 32K peak/workspace allowance and a root-reviewed reserve. Submit **one** reversible candidate profile/seam, exact predicted per-GPU allocation, same prompt/output-token measurement plan and rollback to the retained baseline.

No N choice, placement prediction, speedup claim or profile change is authorized by current total VRAM alone. Root must review the single variant before any reload; no NUMA tuning or concurrent model activation.
