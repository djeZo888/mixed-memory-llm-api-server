# M9F Offline Resilience And Mixed-Memory Large-Model Plan

- Timestamp: `2026-07-09T00:37:27Z`
- Branch: `milestone/m9f-offline-resilience-mixed-memory-plan`
- Base branch: `milestone/m9e-r2-sm120-minimax-remediation`
- Repository path: `/data/services/mixed-memory-llm-api-server`
- Conclusion: PASS for planning only. STOP for download/build/deploy until human review.

## Context-Sync Result

PASS.

- Hostname verified as `llmserver`.
- Repository path verified as `/data/services/mixed-memory-llm-api-server`.
- Source branch `milestone/m9e-r2-sm120-minimax-remediation` was fetched and fast-forward checked.
- Work branch `milestone/m9f-offline-resilience-mixed-memory-plan` was created.
- Git identity matched `CodexAIagent <133749519+djeZo888@users.noreply.github.com>`.
- Source-of-truth files were read: `AGENTS.md`, `ROADMAP.md`, `docs/current-state.md`, `docs/model-matrix.md`, `docs/model-runtime-manager.md`, `docs/large-model-poc.md`, `reports/m9e-large-model-poc.md`, `reports/m9d-large-model-feasibility-plan.md`, and `docs/minimax-sm120-upstream-repro.md`.

Read-only guards passed before planning edits:

- `/data` mount guard: PASS.
- Root-disk guard: PASS with `/tmp/root-disk-guard-before-m9f.md`.
- Docker storage verifier: PASS.
- GPU container verifier: PASS with the already-present `nvidia/cuda:13.2.1-base-ubuntu24.04` verifier image.
- 30B SGLang live verifier: PASS.
- `scripts/llmctl active` and `scripts/llmctl status`: active and healthy.

Guard side effects on `reports/m3-root-disk-guard.md` and `reports/m4b-docker-containerd-install.md` were restored before M9F edits.

## Current Active Model State

- Active model/backend: `Qwen/Qwen3-30B-A3B-Instruct-2507` on SGLang.
- Endpoint: `http://127.0.0.1:30001/v1`.
- Bind: `127.0.0.1` only.
- Container: `sglang-qwen3-30b-a3b-instruct-2507`.
- Live status: `running` / `healthy`.
- `/v1/models`: OK.
- M9F did not stop, restart, or modify the active backend.

## Human Mission Statement

The system is an offline/local AI resilience system, not primarily a cost-saving system. It should remain useful when the internet is unavailable or degraded. The workstation's large system RAM is an asset and should be used through mixed RAM/VRAM inference. Lower speed is acceptable if answer quality and offline independence improve.

## Official And Upstream Source Refresh

Qwen3.5 sources:

- `https://huggingface.co/Qwen/Qwen3.5-397B-A17B`: official model card lists 397B total parameters, 17B activated, 512 routed experts, 10 routed plus 1 shared expert per token, Apache-2.0 license, multimodal input, 262,144 native context, and extension to about 1,010,000 tokens.
- `https://huggingface.co/Qwen/Qwen3.5-397B-A17B-FP8`: official FP8 card states fine-grained FP8 block quantization with block size 128 and compatibility with Transformers, vLLM, SGLang, KTransformers, and related runtimes.
- Hugging Face metadata API observed storage estimates: BF16 `806.80 GB / 751.39 GiB`; FP8 `406.15 GB / 378.26 GiB`; NVIDIA NVFP4 `251.19 GB / 233.93 GiB`.
- `https://docs.sglang.io/cookbook/autoregressive/Qwen/Qwen3.5`: SGLang has a dedicated Qwen3.5 page, says main-branch SGLang is required, documents the 397B/17B architecture, and lists memory guidance for BF16, FP8, and FP4.
- `https://docs.vllm.ai/projects/recipes/en/latest/Qwen/Qwen3.5.html`: vLLM recipe requires current/nightly path and documents Qwen3.5 serving, long context, and Qwen thinking controls.

Mixed-memory runtime sources:

- `https://kvcache-ai.github.io/ktransformers/`: KTransformers describes CPU/GPU heterogeneous inference and hot/cold expert placement.
- `https://github.com/kvcache-ai/ktransformers/blob/main/kt-kernel/README.md`: KT-Kernel documents SGLang integration for CPU-GPU heterogeneous inference and requires `sglang-kt` for that path.
- `https://raw.githubusercontent.com/kvcache-ai/ktransformers/main/doc/en/kt-kernel/experts-sched-Tutorial.md`: documents expert placement strategies and CPU/GPU expert scheduling.
- `https://raw.githubusercontent.com/kvcache-ai/ktransformers/main/doc/en/kt-kernel/Native-Precision-Tutorial.md`: lists native precision support for Qwen3/Qwen3-Next family models but M9F did not find a dedicated Qwen3.5 KTransformers tutorial.

SM120 and GPU compatibility sources:

- `https://developer.nvidia.com/cuda/gpus`: RTX PRO 6000 Blackwell Workstation Edition is compute capability 12.0.
- `https://docs.nvidia.com/cuda/blackwell-compatibility-guide/index.html`: CUDA binaries need compatible native cubin or forward-compatible PTX for Blackwell.
- The MiniMax R2 report remains relevant because it proved this VM can hit released-runtime SM120 gaps even after storage and import gates pass.

Memory/RAG sources:

- `https://qdrant.tech/documentation/manage-data/storage/`: Qdrant supports in-memory and memmap vector storage, on-disk HNSW, payload storage options, and WAL-backed recovery.
- `https://developers.llamaindex.ai/python/framework/module_guides/indexing/vector_store_index/`: LlamaIndex supports vector-store indexing and retrieval-oriented application structure.
- `https://docs.openclaw.ai/providers/sglang`: OpenClaw can connect to SGLang via an OpenAI-compatible `/v1` provider and auto-discover models from `/v1/models`.
- `https://docs.openclaw.ai/concepts/models`: OpenClaw model refs, model allowlists, fallbacks, and local provider selection can map to future local SGLang/vLLM backends.

## Qwen3.5 Candidate Analysis

| Candidate | Params | Context | Quantization | Storage estimate | Runtime path | SM120 risk | Recommendation |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `Qwen/Qwen3.5-397B-A17B` | 397B total / 17B active | 262K native; about 1.01M with long-context config | BF16 | 806.80 GB / 751.39 GiB | SGLang/vLLM/KTransformers claimed by cards | Very high memory pressure; no two-GPU workstation proof | Do not download first. Use as source model reference. |
| `Qwen/Qwen3.5-397B-A17B-FP8` | 397B total / 17B active | 262K native; about 1.01M extensible | FP8 block size 128 | 406.15 GB / 378.26 GiB | SGLang main branch, vLLM main/nightly, possible KTransformers | Medium-high; official examples target larger datacenter shapes | Select as next mixed-memory preflight target. |
| `nvidia/Qwen3.5-397B-A17B-NVFP4` | 397B total / 17B active | up to 262K per NVIDIA card | NVFP4 | 251.19 GB / 233.93 GiB | SGLang/vLLM, NVIDIA Blackwell, B200 test hardware | Blackwell-positive but datacenter B200-oriented; not proven on 2 x RTX PRO | Track as comparison, not first M9G target. |
| `Qwen/Qwen3-235B-A22B-Instruct-2507-FP8` | 235B total / 22B active | 262K native | FP8 | 236.43 GB / 220.19 GiB | SGLang/vLLM/KTransformers references | Still exceeds VRAM; less mission-aligned than Qwen3.5 397B | Keep as lower-risk fallback only after review. |
| `MiniMaxAI/MiniMax-M3-MXFP8` | about 428B total / 23B active | 1M | MXFP8 | Downloaded `414G` | KTransformers/SGLang-KT | Proven SM120 blocker in released path | Parked until upstream SM120 support lands. |
| `zai-org/GLM-5.2-FP8` | large MoE | 1M class | FP8 | 755.63 GB / 703.74 GiB | KTransformers/SGLang docs exist | High storage/runtime risk | Later candidate, not next proof. |
| `deepseek-ai/DeepSeek-V4-Flash` | large MoE comparator | model-specific | FP4/FP8 mix | 159.62 GB / 148.66 GiB | SGLang/KTransformers comparator | Lower storage, but different mission tradeoff | Useful feasibility comparator, not primary quality target. |

## Model-Role Architecture Summary

- Technical expert model: strong coding/sysadmin/engineering model, not necessarily 1M context. Current practical local fit is the active 30B SGLang backend.
- General expert model: broad world/domain knowledge and explanations. A large Qwen3.5 model may fit if mixed-memory runtime proof passes.
- Long-context working model: 250K to 1M context preferred, used after A/B or memory/RAG prepares material. Qwen3.5 is attractive but must start at 8K/16K proof before long-context work.

## Memory/RAG Architecture Summary

M9F adds local memory/RAG as a core roadmap feature:

- Storage under `/data/memory/raw`, `/data/memory/processed`, `/data/memory/indexes`, `/data/memory/qdrant`, `/data/memory/manifests`, `/data/memory/snapshots`, and `/data/logs/memory`.
- Likely vector backend: Qdrant.
- Likely orchestration layer: LlamaIndex or a small repo-native ingestion/retrieval wrapper.
- Required capabilities: list, add/import, delete/archive, search, attach/detach, auto-select, memory pack, provenance/citations, web capture with timestamp/URL/content hash, export/backup.
- Retrieval must work offline after ingestion.
- Web-captured content is untrusted context, not system instruction material.

## MiniMax SM120 Lesson

MiniMax was the right type of experiment for the mission because it aimed to use CPU RAM and GPU VRAM together. The failure teaches that mixed-memory feasibility is not enough: every model-specific quantization/kernel path must prove SM120 support on this exact RTX PRO workstation stack.

M9G must therefore gate Qwen3.5 on runtime import, kernel, and launch-help checks before any Qwen3.5 model download.

## Recommended Next Actual Runtime Milestone

M9G: Qwen3.5-397B-A17B-FP8 mixed-memory runtime preflight.

M9G should:

1. Refresh official/current Qwen3.5, SGLang, KTransformers, vLLM, and NVIDIA SM120 sources.
2. Choose one isolated runtime preflight path.
3. Verify SM120 import/kernel gates without downloading Qwen3.5 weights.
4. Verify required launch flags and localhost-only compose shape.
5. Keep the current 30B backend running.
6. STOP if SM120 gates fail.

M9H should be the first possible model download/proof milestone, and only after M9G passes and human review approves the download.

## Scope Confirmations

- No model download occurred in M9F.
- No Docker image pull occurred in M9F.
- No runtime build or install occurred in M9F.
- No host package install occurred in M9F.
- Secret scan matched only intentional documentation, historical safety strings, and scanner regexes; changed-file value-shaped scan matched only the new verifier and test scanner regexes.
- No model/backend container was started by the planning scripts.
- The requested GPU verifier did run the standard short CUDA verifier container as a read-only guard, using the already-present verifier image.
- The active 30B backend was not stopped or restarted.
- No public API exposure was configured.
- No wildcard/public host bind was configured.
- No Docker/containerd daemon configuration was changed.
- No disk/fstab/mount/partition/Proxmox host work occurred.

## PASS/STOP Conclusion

PASS for planning only.

STOP for download/build/deploy until human review. The next recommended task is human review of M9F, then M9G Qwen3.5 mixed-memory runtime preflight.
