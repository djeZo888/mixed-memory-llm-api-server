# Model Matrix

Do not download models before the relevant milestone explicitly approves the download path, cache path, backend, and verification sequence. M9E downloaded only `MiniMaxAI/MiniMax-M3-MXFP8`; M9F downloads no models and selects `Qwen/Qwen3.5-397B-A17B-FP8` for planning/preflight only. Fallback downloads remain blocked unless a separate human-approved task says so.

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



## M9F Offline-Resilience Role Matrix

M9F classifies models by system role instead of treating a single model as final. The primary mission is offline/local AI resilience, with public API exposure deferred.

| Model | Role classification | Parameters | Context | Quantization | Expected storage | Expected RAM/VRAM | Runtime path | SM120 risk | M9F recommendation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `Qwen/Qwen3-30B-A3B-Instruct-2507` | Current technical/general local model | 30.5B total / 3.3B active | 262K model card; deployed at 32K | native current checkpoint | Downloaded `57G` | Runs on 2 x 96 GB with current SGLang config | SGLang `lmsysorg/sglang:v0.5.14-cu130` | Low; already proven | Keep active and healthy as fallback/resilience baseline. |
| `MiniMaxAI/MiniMax-M3-MXFP8` | Parked large mixed-memory candidate | about 428B total / 23B active | 1M | MXFP8 | Downloaded `414G` | Fits RAM/storage but not pure VRAM | KTransformers/SGLang-KT | Proven blocker: released path is SM90/SM100-oriented | Park until upstream SM120 support changes. |
| `Qwen/Qwen3.5-397B-A17B` | Source/reference for future large expert/worker | 397B total / 17B active | 262K native; about 1.01M extensible | BF16 | 806.80 GB / 751.39 GiB | Too large for VRAM; high RAM/storage pressure | SGLang/vLLM/KTransformers claimed by card | Unknown on 2 x RTX PRO SM120 | Do not download first; use as reference. |
| `Qwen/Qwen3.5-397B-A17B-FP8` | Next large mixed-memory proof candidate; general expert and long-context worker | 397B total / 17B active | 262K native; about 1.01M extensible | FP8 block size 128 | 406.15 GB / 378.26 GiB | Fits RAM/storage; exceeds aggregate VRAM before KV/cache | SGLang main branch, vLLM current/nightly, possible KTransformers | Unknown; official examples are datacenter/multi-GPU shapes | Select for M9G runtime preflight only, no download in M9F. |
| `nvidia/Qwen3.5-397B-A17B-NVFP4` | Quantized comparison candidate | 397B total / 17B active | up to 262K | NVFP4 | 251.19 GB / 233.93 GiB | Smaller but still above 2 x 96 GB before KV/cache | SGLang/vLLM; NVIDIA ModelOpt | Blackwell-positive, but B200-oriented; SM120 workstation unproven | Track as comparison, not first target. |
| `Qwen/Qwen3-235B-A22B-Instruct-2507-FP8` | Lower-storage fallback/general expert candidate | 235B total / 22B active | 262K native | FP8 | 236.43 GB / 220.19 GiB | Still above aggregate VRAM before overhead | SGLang/vLLM/KTransformers references | Unknown but likely lower model-specific risk than MiniMax | Keep fallback only after separate review. |
| `zai-org/GLM-5.2` / `zai-org/GLM-5.2-FP8` | Later long-context/agentic large candidate | large MoE | 1M class | BF16 / FP8 | 1506.67 GB BF16; 755.63 GB FP8 | High storage/RAM risk | KTransformers/SGLang docs exist | Unknown | Later candidate, not next proof. |
| `deepseek-ai/DeepSeek-V4-Flash` | Feasibility comparator | large MoE | model-specific | FP4/FP8 mix | 159.62 GB / 148.66 GiB | Better fit than Qwen3.5, lower mission quality target | SGLang/KTransformers comparator | Unknown | Use only if feasibility outranks large expert quality. |

M9G must verify SM120 runtime gates before any Qwen3.5 download. M9H is the earliest possible Qwen3.5 proof-of-life milestone after M9G passes and human review approves download/runtime scope.

## M9D Large-Model Feasibility Update

M9D refreshes the large-model matrix using current Hugging Face metadata and current runtime docs. No model is downloaded and no runtime is installed in M9D.

| Candidate | Current M9D status | Storage estimate | First-runtime view | Feasibility note |
| --- | --- | --- | --- | --- |
| `Qwen/Qwen3-235B-A22B-Instruct-2507` | Defer native BF16 | 470.19 GB / 437.90 GiB | SGLang/vLLM/KTransformers references exist | Exceeds 2 x 96 GB VRAM; system RAM fit only with offload. |
| `Qwen/Qwen3-235B-A22B-Instruct-2507-FP8` | Fallback after review | 236.43 GB / 220.19 GiB | SGLang/vLLM listed by model card | Still exceeds aggregate VRAM before KV/cache overhead; needs proven offload or a larger GPU plan. |
| `zai-org/GLM-5.2` | Defer BF16; possible later FP8 KT path | 1506.67 GB / 1403.19 GiB BF16; FP8 metadata about 755.63 GB / 703.74 GiB | KTransformers/KT-Kernel plus SGLang tutorial exists | Too large for first download; high storage and RAM risk. |
| `MiniMaxAI/MiniMax-M3` | Defer native BF16 | 854.18 GB / 795.51 GiB | SGLang/vLLM/KTransformers references exist | Use the MXFP8 variant first if MiniMax is selected. |
| `MiniMaxAI/MiniMax-M3-MXFP8` | M9E-R2 STOP | Downloaded size `414G` at `/data/models/minimax-m3-mxfp8` | KTransformers/KT-Kernel plus SGLang-KT hybrid | R1 fixed missing `libnuma.so.1`; R2 found the released MiniMax MXFP8 CUDA path expects SM100 datacenter Blackwell for native MXFP8/Cutlass and lacks native SM120 `common_ops`, so no R2 image was built and MiniMax was not relaunched. |
| `nvidia/MiniMax-M3-NVFP4` | Relevant comparison only | 250.10 GB / 232.93 GiB | vLLM nightly per NVIDIA model card | Relevant for Blackwell, but current card points to nightly vLLM support and TP8, not a proven 2-GPU path. |

M9E attempted the recommended `MiniMaxAI/MiniMax-M3-MXFP8` path through KTransformers/KT-Kernel plus SGLang-KT. The model downloaded successfully. M9E-R1 fixed the missing `libnuma.so.1` dependency and verified `sgl_kernel/common_ops` loading, but the relaunch stopped before `/v1/models` because SGLang MXFP8 asserts SM90 or SM100 support and this VM is SM120. M9E-R2 classified the current released stack as SM100-oriented for MiniMax native MXFP8/Cutlass, with no native SM120 common_ops and no clean released/source build gate, so no R2 image was built and MiniMax was not relaunched. The current active backend is the restored 30B SGLang service. `Qwen/Qwen3-235B-A22B-Instruct-2507-FP8` remains a fallback only after separate human approval; it was not downloaded in M9E, M9E-R1, or M9E-R2. M10 API/front-door/auth remains deferred.

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
