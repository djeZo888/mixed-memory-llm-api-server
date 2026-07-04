# Model Matrix

Do not download models before the relevant milestone explicitly approves the download path, cache path, backend, and verification sequence. M7A is research-only.

## Hardware Profile

`llmserver-vm120-2x-rtx-pro-6000-blackwell-96gb`

- Current GPU inventory: 2 x NVIDIA RTX PRO 6000 Blackwell Workstation Edition.
- Current VRAM: `97887 MiB` per GPU, about 192 GB total before overhead.
- No RTX 6000 Ada is expected in this VM.
- System RAM target: 1 TB.
- `/data` is mounted and has the required model/cache/build/log/service roots.
- Docker Root Dir is `/data/docker`.
- containerd root is `/data/containerd/root`.
- Host NVIDIA driver `595.71.05` works.
- NVIDIA Container Toolkit works for Docker GPU containers.
- Host CUDA Toolkit and `nvcc` remain absent.

## Runtime Gate

M7A produced `reports/m7a-model-runtime-research.md` as a source-cited shortlist. Its conclusion is PASS for research and STOP for downloads, backend installs, builds, service creation, Docker/containerd changes, and API exposure until human review approves M7B.

KTransformers/KT-Kernel remains the most important heterogeneous RAM+VRAM path for very large MoE models, but SGLang is the recommended first backend to implement for the smoke and 30B-class API path because current model cards list SGLang support and OpenAI-compatible serving. vLLM is the main cross-check backend. ik_llama and llama.cpp are GGUF/quantized fallback paths.

M7B adds a model/runtime manager abstraction. Model choices remain profile-based rather than final. Use `configs/models/catalog.yaml`, `configs/models/profiles/*.yaml`, `configs/runtimes/*.yaml`, and `scripts/llmctl` to validate and plan future activation. Only one model/backend should be active at a time.

## Shortlist

| Priority | Model | Role | First backend | Status | Gate |
| --- | --- | --- | --- | --- | --- |
| 0 | `Qwen/Qwen3-0.6B` | Small smoke-test model | SGLang first, vLLM optional | Recommended first download after M8 approval | M7B backend abstraction, M8 download approval, `/data/models` and `/data/hf-cache` guard checks |
| 1 | `Qwen/Qwen3-30B-A3B-Instruct-2507` | First real fast technical/general model | SGLang first, vLLM cross-check | Recommended first real model after smoke | M7B runtime profile, M9 benchmark approval, reduced context first |
| 2 | `Qwen/Qwen3.6-35B-A3B` | Higher-quality fast coding/agentic model | SGLang or vLLM text-only first | Top smaller/faster candidate | Use text-only mode first; prove runtime supports `qwen3_5_moe` on this VM |
| 3 | `Qwen/Qwen3-30B-A3B-Thinking-2507` | Smaller reasoning model | SGLang first, vLLM cross-check | Top smaller/faster candidate | Limit output/context initially because thinking mode increases KV/cache pressure |
| 4 | `Qwen/Qwen3-Coder-30B-A3B-Instruct` | Coding-specific alternate | vLLM or SGLang, ik_llama if GGUF chosen | Alternate | Use if M9 focuses on code repair/generation over general technical chat |
| 5 | `Qwen/Qwen3-235B-A22B-Instruct-2507` | Large/high-quality general model | KTransformers or SGLang/vLLM after memory plan | Top large candidate | Native BF16 footprint is about 438 GiB; 1M context is not viable on this VM without far more GPU memory |
| 6 | `MiniMaxAI/MiniMax-M3` | Large agentic/coding/multimodal model | KTransformers or SGLang/vLLM after license/runtime review | Top large candidate | Native footprint is about 796 GiB; review MiniMax Community license and custom-code/runtime path |
| 7 | `zai-org/GLM-5.2` | Frontier large coding/agentic model | KTransformers or SGLang/vLLM after memory plan | Top large candidate | Native footprint is about 1403 GiB; not a first download |
| 8 | `deepseek-ai/DeepSeek-V4-Flash` | Large feasibility comparator | SGLang or KTransformers after memory plan | Alternate/comparator | Official FP4+FP8 footprint is about 149 GiB; strongest first large-quality experiment if feasibility outranks top-list purity |

## Current Backend Notes

- Recommended first M7B backend profile: pinned SGLang Docker profile, localhost-only, all model/cache/log/build mounts under `/data`.
- Recommended cross-check backend: vLLM pinned version/profile for the same small and 30B-class models.
- Recommended large-MoE experimental path: KTransformers/KT-Kernel after M7B proves Blackwell behavior on this host.
- Recommended quantized/GGUF fallback: ik_llama first, llama.cpp as reference.
- M7B manager state root: `/data/services/llm-manager/state`.
- M7B is dry-run/planning only; real downloads and activation remain blocked.
- Do not use `latest` images or unpinned commits in implementation milestones.
- Do not attempt 1M context first on any model. Start at 4K/32K for smoke, then 128K, and only then 262K if memory is stable.
