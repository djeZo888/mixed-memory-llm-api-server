# R2 — current models and agentic readiness

Date: 2026-09-15. Branch: `milestone/r2-model-refresh`. Research/read-only audit only.
**Research complete; runtime and agent acceptance remain unexecuted.** Root owns downloads, runtime approval and implementation.

## Decision

- **Flagship:** GLM-5.3, community Unsloth `UD-Q4_K_XL`, on pinned llama.cpp CUDA with CPU-resident experts.
- **Practical fast model:** official `Qwen/Qwen3-Coder-Next-FP8`, on SGLang with `qwen3_coder` tool parser.
- One model/backend active at a time. Preserve existing Qwen30B and MiniMax artifacts for rollback/comparison.
- [Exact machine-readable flagship manifest](r2-flagship-artifact.json) records all eleven paths, sizes, SHA-256 identifiers and runtime commit.

## Current candidates and primary evidence

| Candidate | Verified publication and deployment judgment |
| --- | --- |
| **GLM-5.3** | Official 744B/40B-active family, 1,048,576 context. HF repository created August 25; surviving FP8 initial commit August 27, 2026. Independent announcement date not established. [Official card](https://huggingface.co/zai-org/GLM-5.3-BF16), [publication history](https://huggingface.co/api/models/zai-org/GLM-5.3/commits/main). Official BF16 is 1,506,667,387,408 bytes; official FP8 755,632,050,320 bytes. Select smaller community GGUF below. |
| **Qwen3-Coder-Next** | Dedicated coding-agent model, 80B/3B active, non-thinking, 262,144 context, Apache-2.0; published by February 3, 2026, repository created February 1. Official FP8: 80,381,394,600 bytes / 74.86 GiB, 40 safetensors, revision `da6e2ed27304dd39abadd9c82ef50e8de67bdd4c`. [Official FP8 card](https://huggingface.co/Qwen/Qwen3-Coder-Next-FP8), [metadata](https://huggingface.co/api/models/Qwen/Qwen3-Coder-Next-FP8?blobs=true). |
| **DeepSeek-V4.1-Flash** | Official September 10, 2026 release; new architecture, mixed FP8/FP4 weights, 510,296,708,312 bytes, revision `dba1be0a40aa45a94ad051997016db3960a90277`. [Card](https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash). SGLang requires `dev-dsv41`; vLLM requires a special image, not a released wheel. Defer first deployment. [SGLang cookbook](https://github.com/sgl-project/sglang/blob/main/docs/cookbook/autoregressive/DeepSeek/DeepSeek-V4_1.mdx), [vLLM recipe](https://github.com/vllm-project/recipes/blob/main/models/deepseek-ai/DeepSeek-V4.1-Flash.yaml). |
| **MiniMax-M3-MXFP8** | Real June 2026 model, not a speculative name. Official 443,749,077,256-byte / 413.27 GiB checkpoint, revision `c5454eb03678d8710e54a4e0fc681b9f3b4a3dba`; existing local alternative. [Card](https://huggingface.co/MiniMaxAI/MiniMax-M3-MXFP8), [June 12 runtime announcement](https://vllm-project.github.io/2026/06/12/minimax-m3-vllm.html). Its previous KT recommendation is historical, not current successful-service evidence. |

**License:** GLM-5.3 is open-weight under a custom license, not MIT or an unqualified OSI-open-source claim. A licensee/affiliate operating a MaaS business with aggregate revenue exceeding US$10B over any consecutive twelve months must pass Z.ai security review before commercial use. The described private local deployment has no evident obstacle under that clause; retain notices. [Official license](https://huggingface.co/zai-org/GLM-5.3-BF16/blob/9d2398f478cab2de883137db3a36ad2c96205e24/LICENSE).

## Exact flagship handoff

- Repository: **`unsloth/GLM-5.3-GGUF`**, revision **`346b3591c7f28d1a23716f97a065ecf12ec14771`**.
- Include **`UD-Q4_K_XL/*.gguf`**, all **11 shards**, totaling **467,289,116,837 bytes = 467.289 GB = 435.197 GiB**.
- Destination: `/data/models/glm-5.3-ud-q4-k-xl`; cache: `/data/hf-cache`; no duplicate BF16/FP8 download.
- Load `UD-Q4_K_XL/GLM-5.3-UD-Q4_K_XL-00001-of-00011.gguf`; all siblings must exist.
- First shard is only **9,428,677 bytes**, confirmed in both HF tree and blob metadata. This is not the entire checkpoint.
- [Immutable files](https://huggingface.co/unsloth/GLM-5.3-GGUF/tree/346b3591c7f28d1a23716f97a065ecf12ec14771/UD-Q4_K_XL), [pinned size/hash metadata](https://huggingface.co/api/models/unsloth/GLM-5.3-GGUF/tree/346b3591c7f28d1a23716f97a065ecf12ec14771/UD-Q4_K_XL).
- Manifest SHA-256 values are published LFS identifiers; **no downloaded file was hashed or verified in R2**.

**Runtime pin:** upstream llama.cpp **v0.4.1**, released September 14, 2026, commit **`b29c606e28a01b1bc8c1351026a0fa6e616bf6c4`**. This is R2's conservative minimum/pin; the earliest historical compatible version remains unknown. [Stable release](https://github.com/ggml-org/llama.cpp/releases/tag/v0.4.1).

The tag includes GLM-DSA/MLA support and Jinja integer-property fix `ae9afff8d2c012ca760eb9c2adf41961cf6f6232`, merged September 12. Unsloth also documents GLM template fixes. [Tagged model source](https://github.com/ggml-org/llama.cpp/blob/v0.4.1/src/models/glm-dsa.cpp), [Jinja fix](https://github.com/ggml-org/llama.cpp/pull/28817), [quantizer guide](https://unsloth.ai/docs/models/glm-5.3).

Use the embedded Jinja template and automatic parser; there is no verified named `glm5.3` CLI parser. Keep tool/reasoning parsing enabled. Verify emitted `tool_calls` and `reasoning_content`; pin any necessary template override after inspecting the artifact. [Tagged parser selection](https://github.com/ggml-org/llama.cpp/blob/v0.4.1/common/chat.cpp).

Initial proof shape: approved CUDA build/container under `/data`, local artifact path, localhost-only `llama-server`, `--no-webui`, `--jinja`, one slot, 8,192 total tokens, layer split across GPUs, `--cpu-moe` initially. Tune `--n-cpu-moe` only after observing allocation/latency. Do not assume 1M context, experimental tensor split or speculative decoding. [Tagged server options](https://github.com/ggml-org/llama.cpp/blob/v0.4.1/tools/server/README.md).

## Live hardware and stale installation state

Read first: [AGENTS](../AGENTS.md), [current state](../docs/current-state.md), [pre-M9E handoff](../docs/pre-m9e-large-model-poc-handoff.md), [M9D report](m9d-large-model-feasibility-plan.md). Read-only SSH snapshot: approximately September 14, 22:15 UTC / September 15 locally.

| Observed | Implication |
| --- | --- |
| Two RTX PRO 6000 Blackwell Workstation GPUs, 97,887 MiB each; driver 595.71.05; nearly idle | 191.19 GiB nominal aggregate VRAM, separate pools. PHB interconnect, no NVLink shown. |
| RAM 946,806,919,168 bytes / 881.78 GiB; available 940,343,717,888 bytes | Flagship RAM weight capacity is feasible; runtime allocations remain unmeasured. |
| Threadripper PRO 9985WX CPU string, 112 guest vCPUs, seven guest NUMA nodes | Virtual topology does not prove physical sockets/channels. Worker1 owns detailed hardware verification. |
| `/data` mounted ext4, 1,406,234,140,672 bytes free | Capacity for selected artifact and staging; preserve root-disk policy. |
| MiniMax weights `414G`, Qwen30B `57G`, smoke `1.5G`; KT image `0.6.3-post1-r1` exists | “No large model downloaded” in old handoff is stale; directory size does not prove integrity. |
| MiniMax container exited 137 July 8, `OOMKilled=false`; Qwen30B exited 0 July 9; both `restart=no` | MiniMax cause unknown, not proven OOM. No restart attempted. |
| Stored `active.json` says Qwen30B active, but port 30001 health/model GETs refuse connection | No healthy API was observed; stored state and handoff are stale. |

## Fit, context and runtime tradeoffs

GLM's 435.20 GiB weights exceed nominal VRAM by 244.01 GiB before buffers. A provisional 160 GiB GPU weight budget leaves at least 275.20 GiB in RAM; the entire checkpoint can fit RAM with about 446.59 GiB nominal room before runtime allocations. CPU-resident experts execute on CPU; NUMA placement, memory bandwidth, prefill and PCIe traffic determine latency. The user's eight-channel DDR5-6400 / up-to-400-GB/s claim is **unmeasured** here. No speed promise is justified.

GLM's compressed FP16 latent-only illustration is about 0.69 GiB at 8K, 2.74 GiB at 32K and 87.75 GiB at 1M, derived from 78 layers × (512+64) × two bytes/token. This excludes index caches, workspace, concurrency and expanded layouts; **not a runtime KV forecast**. Start 8K and measure. [Pinned config](https://huggingface.co/zai-org/GLM-5.3-BF16/blob/9d2398f478cab2de883137db3a36ad2c96205e24/config.json).

Qwen FP8 leaves about 116.32 GiB nominal aggregate headroom, versus 20.73 GiB on one GPU. Start SGLang TP2 at 32K, one request. Full-attention FP16 KV is approximately 0.75 GiB at 32K and 6 GiB at 256K, excluding recurrent state and buffers. Its BF16 benchmark scores do not certify this FP8 deployment. [Pinned config](https://huggingface.co/Qwen/Qwen3-Coder-Next-FP8/blob/da6e2ed27304dd39abadd9c82ef50e8de67bdd4c/config.json).

Qwen's official minimum is SGLang **>=0.5.8**, parser `qwen3_coder`, or vLLM **>=0.15.0** with automatic tool choice and the same parser. Existing SGLang `v0.5.14-cu130` meets the version floor but has no Qwen-Next FP8 validation here. No reasoning parser is needed for this non-thinking model. [SGLang release](https://github.com/sgl-project/sglang/releases/tag/v0.5.8), [vLLM release](https://github.com/vllm-project/vllm/releases/tag/v0.15.0).

Official GLM SGLang/vLLM recipes do not prove two-workstation-GPU RAM offload or support for this GGUF. The vLLM recipe gives inconsistent minima (0.29.0+ versus 0.28.0); do not turn it into a verified pin. Retain KTransformers/ik_llama profiles, but do not assume they inherit current llama.cpp architecture/template support. [GLM vLLM recipe](https://recipes.vllm.ai/zai-org/GLM-5.3).

## Missing implementation and bounded acceptance

The [manager](../scripts/llmctl) only implements deployment handling for existing smoke/Qwen30B paths; adding metadata alone is insufficient. Real-model restart remains explicitly refused, activation is dry-run-only, compose lacks the new parser settings, and historical text/SSE checks submit no tools. Add pinned runtime/model/template/preset profiles and a llama.cpp adapter, reconcile state, enforce single-model readiness, and preserve rollback. [Compose](../configs/compose/compose.sglang-qwen3-30b.template.yml), [existing verifier](../scripts/sglang/verify-sglang-real-fast-live.sh).

Use **Qwen Code on the client worker/VM**: its documented `modelProviders.openai[]` supports self-hosted Chat Completions with served-model ID, `/v1` base URL and environment-referenced credential. This is a supported configuration route, **not a passed integration**. [Client documentation](https://qwenlm.github.io/qwen-code-docs/en/users/configuration/model-providers/). The client owns tools, edits, tests, browser work and history; `ai-vm` exposes inference only, with no unrestricted server-shell API or chat UI.

| Gate / owner | Required evidence — ALL UNEXECUTED in R2 |
| --- | --- |
| Artifact/runtime / Root + worker1 | Before/after heavy work run data-mount and root-disk guards; verify manifest sizes/hashes, approved CUDA matrix, pinned build/image, both GPUs, allocations and no root-disk data growth. |
| API / runtime worker | Correct `/health` and `/v1/models`, one active model, bounded nonstream/SSE replies, tool IDs/schemas and reasoning separation. Record actual token counts, RAM/VRAM, first-token and total latency. |
| Streaming / A1 client harness | Reassemble fragmented tool calls by index/ID, validate completed JSON, execute exactly once, return matching tool results. Cover Unicode/escaping, sequential tools, supported parallel calls, one error, cancellation and disconnect. |
| REAL agent loop / A1 | Disposable client repository with seeded bug: model chooses **read → edit → test → result**, consumes a failing test and repairs, then reports actual results. Preserve diff, test exit status and redacted wire/tool transcript. Three bounded tasks/model, at most twelve tool turns/task; no pre-scripted tool sequence. |
| Recovery / runtime + client owners | Separately authorized restart and, if approved, reboot. Mount guards first, selected model restored, readiness verified, no competing model. Resume client history without duplicated edits/tool execution; prove rollback. |

GLM presets must choose `reasoning_effort=low|high|max` and reasoning-history handling; official chat guidance recommends explicit `clear_thinking=true`. [Usage](https://huggingface.co/zai-org/GLM-5.3-BF16). Authentication plus documented firewall/TLS policy is required before exposure beyond localhost; operator-approved tunneling can support initial client tests.

## Checks and next action

**Executed:** repository/handoff review; official model/runtime source and metadata inspection; read-only CPU/RAM/GPU/storage/container/model/state/listener inventory and GET health/model-list attempts. No authentication files, full container environment or raw server logs inspected. No installs, model downloads, inference, service changes or local project tests.

**Passed:** research, exact artifact metadata and hardware capacity inventory. **Failed live:** documented API reachability. **Unknown/unexecuted:** file integrity, Blackwell runtime execution, exact GGUF template/streamed tools, sustained RAM bandwidth, offload latency, agent success and persistence. Final packaging uses `git diff --check`, required attribution and bundle verification.

**Next:** Root/worker1 own approved artifact download and runtime proof; worker1 owns hardware follow-up; fresh **A1** owns the real client harness. Root decides operational presets and subsequent persistence/API exposure. No further research is required before those bounded tasks.
