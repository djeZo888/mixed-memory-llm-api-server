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


## M8A Smoke Path

M8A keeps `Qwen/Qwen3-0.6B` as the first smoke-test model and SGLang as the first smoke runtime. The planned local model path is `/data/models/qwen3-0.6b-smoke`; M8B must download to that path before launch and must not rely on SGLang auto-downloading from Hugging Face.

The planned localhost endpoint is `http://127.0.0.1:30000/v1/chat/completions`. The host binding must remain `127.0.0.1:30000:30000`; public or LAN exposure is out of scope for M8.

M8A proposes the pinned runtime image `lmsysorg/sglang:v0.5.14-cu130-runtime` for human review. M8A does not download the model, pull the image, start a backend, or select any final large model.

## Current Backend Notes

- Recommended first M7B backend profile: pinned SGLang Docker profile, localhost-only, all model/cache/log/build mounts under `/data`.
- Recommended cross-check backend: vLLM pinned version/profile for the same small and 30B-class models.
- Recommended large-MoE experimental path: KTransformers/KT-Kernel after M7B proves Blackwell behavior on this host.
- Recommended quantized/GGUF fallback: ik_llama first, llama.cpp as reference.
- M7B manager state root: `/data/services/llm-manager/state`.
- M7B is dry-run/planning only; real downloads and activation remain blocked.
- Do not use `latest` images or unpinned commits in implementation milestones.
- Do not attempt 1M context first on any model. Start at 4K/32K for smoke, then 128K, and only then 262K if memory is stable.


## M9A First Real Fast-Model Plan

M9A keeps `Qwen/Qwen3-30B-A3B-Instruct-2507` as the recommended first real fast model. Current Hugging Face metadata reports 16 safetensors totaling 61.07 GB decimal / 56.87 GiB. The model card lists Apache-2.0 license, 30.5B total parameters, 3.3B active parameters, 262,144 native context, non-thinking-only behavior, and SGLang/vLLM deployment guidance.

`Qwen/Qwen3.6-35B-A3B` is now tracked as a higher-quality fast follow-up profile. It is Apache-2.0, 35B total / 3B active, about 71.90 GB decimal / 66.97 GiB safetensors, multimodal/hybrid GDN, and should be tested text-only first because SGLang docs require `sglang>=0.5.10` and recommend careful memory/context settings.

`Qwen/Qwen3-30B-A3B-Thinking-2507` is now tracked as a reasoning follow-up profile. It shares the primary model footprint but is thinking-only, so M9B should not use it as the first low-risk real deployment.

`Qwen/Qwen3-Coder-30B-A3B-Instruct` remains the coding-specific fallback candidate if human review decides coding quality is more important than the lowest-risk first real path.

Planned M9B primary path: download `Qwen/Qwen3-30B-A3B-Instruct-2507` only to `/data/models/qwen3-30b-a3b-instruct-2507`, keep cache under `/data/hf-cache`, use the verified full SGLang image `lmsysorg/sglang:v0.5.14-cu130`, bind only to `127.0.0.1:30001`, start at 32K context and one running request, then scale context only after VRAM/RAM checks pass. M9A remains planning-only and does not approve downloads, image pulls, container starts, smoke stop, or API exposure.
