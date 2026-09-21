# Current model and deployment matrix

**Live production acceptance PASS — 2026-09-21, 03:21 UTC**, source
`04143b18cca7aca724d9a4a4bcf943fe86c040db`. The [dated proof](../reports/dualq-480k-20260921.md#dated-production-acceptance--2026-09-21)
records both Qwen instances warm/ready, running/resume, native 480,000 each,
72 guest CPUs and shared 0–7 masks. There are two model identities and three
reviewed pair deployment choices; catalog retains two historical native1M/TP2
entries. Hardware boot, cold-boot replay and live full rollback remain NOT_TESTED.

| Model / placement | Deployment ID = public `instance_id` | API target | Alias / port | Guest CPUs / RAM cap |
| --- | --- | --- | --- | --- |
| Qwen3.8-27B FP8 / GPU0 | `qwen38-27b-q0-480000-yarn4-bf16kv` | `glm` | `qwen3.8-27b-gpu0` / 30002 | 0–7 / 32 GiB |
| Qwen3.8-27B FP8 / GPU1 | `qwen38-27b-q1-480000-yarn4-bf16kv` | `qwen` | `qwen3.8-27b` / 30004 | 0–7 / 32 GiB |
| GLM5.3 UD-Q4_K_XL / GPU0 | `glm-5.3-ud-q4-k-xl-g1-480000` | `glm` | `glm-5.3` / 30002 | 0–71 / 640 GiB |

Default `dual-qwen` selects both Qwen instances. Optional `glm-qwen` replaces
GPU0 only; returning to default explicitly restores GPU0 Qwen. Target `glm`
is a historical name for GPU0, not a requirement to run GLM. Public instance
IDs identify deployment choices; they are not immutable container identities
or the opaque `active_identity` used for mutation compare-and-swap.

Every deployment configures **480,000 tokens**. The existing guest has **72
vCPUs** and two GPUs. Q/Q shares CPUs 0–7: union 8, exclusive 0. G/Q shares
Qwen's eight CPUs with GLM's 72. No physical host pinning or minimum-core claim
follows from these masks. Caps permit no swap and retain the reviewed 15%
sampled working-set margin policy.

Qwen uses pinned `sglang-qwen38-0.5.19`, FP8 weights, TP1, BF16 KV, YaRN 4 and
chunk size 2,048. GLM uses pinned `llama-cpp-v0.4.1-d3br`, one GPU plus system
RAM, N76 CPU offload and F16 KV. Exact model/runtime/profile pins remain in
[deployment profiles](../configs/deployments/) and the protected acceptance
contract; this documentation changes none of them.

## Capacity evidence

| Saved workload | Configured tokens | Native input / actual output / occupied | Boundary |
| --- | ---: | ---: | --- |
| Dual-Q Q0 | 480,000 | 479,408 / 82 / 479,490 | Strict and semantic PASS |
| Dual-Q Q1 | 480,000 | 479,408 / 87 / 479,495 | Strict outer-fence failure; semantic exact object PASS |
| Historical REAL72 B3 GLM | 480,000 | 65,008 / 68 / 65,076 | Historical G/Q workload; not maximum occupied capacity |

The [dual-Q report](../reports/dualq-480k-20260921.md) covers one measured pair,
512-token output caps, separate actual outputs, sampled resources and no
output-window overlap. [REAL72 B3](../reports/postrestart72-three-case-followup-20260920.md)
is historical comparison evidence. Neither proves a general throughput limit.
The later production GLM native 480K proof and one correct `42`/`stop` smoke
(6.799028 s) are allocation/function evidence, not a new occupied-context
benchmark. Q0 schema and Q1 real tool/result continuation also passed.

Qwen admission requires native pool 480,000 and input limit 479,994. Optional
native request limit must be 479,999 when present; absence remains unknown,
with input plus output bounded by the pinned 479,999 policy. GLM resolved native
context must equal 480,000. Allocation is distinct from occupied retrieval.
Catalog configured, accepted and verified occupied capacities remain separate;
a protected reviewed receipt is required for accepted values. A Ready probe,
source test or model declaration cannot supply that receipt.

## Historical alternatives

TP2/1M profiles, earlier 700160-token G/Q candidates, older models and research
shortlists remain historical/deferred. They are not automatic download or
activation choices for this pair. See the preserved
[stage-one status](../reports/stage1-ai-vm-status.md) and
[M7 research](../reports/m7a-model-runtime-research.md). Installer work is paused;
this matrix authorizes no downloads or host changes.
