# M7A - Model Runtime Research And Shortlist

Timestamp: 2026-07-03T20:31:49+02:00

Branch: `milestone/m7a-model-runtime-research`

Base commit at research start: `a0868b8`

Conclusion: PASS for M7A research and shortlist. STOP for model downloads, backend installs, runtime builds, service creation, Docker/containerd changes, and API exposure until human review approves M7B.

## Scope Confirmation

M7A was research/report-only. No model weights were downloaded, no backend software was installed, no CUDA Toolkit/PyTorch/KTransformers/ik_llama/vLLM/SGLang package was installed, no Docker or containerd configuration was changed, Docker/containerd were not restarted, no inference service was created, and no API was exposed.

Lightweight Hugging Face model metadata was queried for file-size estimates only; model weight files were not downloaded.

## Hardware Summary

- Host: `llmserver`
- VM user: `user`
- OS: Ubuntu 24.04.4 LTS
- Kernel: `6.8.0-134-generic`
- GPUs: 2 x NVIDIA RTX PRO 6000 Blackwell Workstation Edition
- GPU PCI IDs:
  - GPU 0: `00000000:01:00.0`
  - GPU 1: `00000000:02:00.0`
- VRAM reported by `nvidia-smi`: `97887 MiB` per GPU, about 192 GB total before overhead
- System RAM target from project context: 1 TB
- Root filesystem: about 15 GB total, 4.5 GB free at research time
- `/data`: 2.0 TB filesystem, about 1.9 TB free at research time
- Required data roots exist: `/data/models`, `/data/hf-cache`, `/data/build`, `/data/logs`, `/data/services`

## Software Baseline

- NVIDIA host driver: `595.71.05`
- `nvidia-smi` reports CUDA compatibility: `13.2`
- Host CUDA Toolkit: absent
- `nvcc`: absent
- Docker: `29.6.1`
- Docker Root Dir: `/data/docker`
- containerd: `2.2.5`
- containerd root: `/data/containerd/root`
- containerd state: `/run/containerd`
- NVIDIA Container Toolkit: `1.19.1`
- Docker runtimes include `nvidia`; default runtime remains `runc`
- GPU container verifier passed with `nvidia/cuda:13.2.1-base-ubuntu24.04`

## Source List

Access date for all sources: 2026-07-03.

- `zai-org/GLM-5.2` Hugging Face model card: <https://huggingface.co/zai-org/GLM-5.2>
- GLM-5 paper page: <https://huggingface.co/papers/2602.15763>
- `MiniMaxAI/MiniMax-M3` Hugging Face model card: <https://huggingface.co/MiniMaxAI/MiniMax-M3>
- MiniMax Sparse Attention paper/source links from MiniMax-M3 card: <https://arxiv.org/abs/2606.13392> and <https://github.com/MiniMax-AI/MSA>
- `Qwen/Qwen3-235B-A22B-Instruct-2507` Hugging Face model card: <https://huggingface.co/Qwen/Qwen3-235B-A22B-Instruct-2507>
- `Qwen/Qwen3.6-35B-A3B` Hugging Face model card: <https://huggingface.co/Qwen/Qwen3.6-35B-A3B>
- `Qwen/Qwen3-30B-A3B-Instruct-2507` Hugging Face model card: <https://huggingface.co/Qwen/Qwen3-30B-A3B-Instruct-2507>
- `Qwen/Qwen3-30B-A3B-Thinking-2507` Hugging Face model card: <https://huggingface.co/Qwen/Qwen3-30B-A3B-Thinking-2507>
- `Qwen/Qwen3-Coder-30B-A3B-Instruct` Hugging Face model card: <https://huggingface.co/Qwen/Qwen3-Coder-30B-A3B-Instruct>
- `Qwen/Qwen3-0.6B` Hugging Face model card for smoke-test candidate: <https://huggingface.co/Qwen/Qwen3-0.6B>
- `deepseek-ai/DeepSeek-V4-Flash` Hugging Face model card: <https://huggingface.co/deepseek-ai/DeepSeek-V4-Flash>
- Hugging Face model metadata API for repository file-size estimates: `https://huggingface.co/api/models/<repo>?blobs=true`
- KTransformers repository and docs: <https://github.com/kvcache-ai/ktransformers> and <https://kvcache-ai.github.io/ktransformers/>
- SGLang repository and docs: <https://github.com/sgl-project/sglang> and <https://docs.sglang.io/>
- vLLM repository and docs: <https://github.com/vllm-project/vllm> and <https://docs.vllm.ai/>
- ik_llama.cpp repository and build docs: <https://github.com/ikawrakow/ik_llama.cpp> and <https://github.com/ikawrakow/ik_llama.cpp/blob/main/docs/build.md>
- llama.cpp repository and build docs: <https://github.com/ggml-org/llama.cpp> and <https://github.com/ggml-org/llama.cpp/blob/master/docs/build.md>
- NVIDIA CUDA release notes for driver/CUDA baseline cross-check: <https://docs.nvidia.com/cuda/cuda-toolkit-release-notes/index.html>

## Model Comparison

Storage footprint is the sum of official `.safetensors` files reported by the Hugging Face model metadata API at research time. It excludes local cache duplication, temporary download space, tokenizer/config files, logs, and any external quantization artifacts.

| Model | Provider | License | Total params | Active params | Context length | Native precision / quantization | Expected storage footprint | Expected VRAM/RAM requirement | Runtime support | Blackwell support risk | Speed tier | Quality tier | Recommendation status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `zai-org/GLM-5.2` | Z.ai | MIT | 753B | Not explicitly published on the card; config routes 8 experts per token | 1M | BF16/F32 safetensors; third-party GGUF/quantizations exist but are not the primary source | About 1403 GiB BF16/F32 safetensors | Does not fit in 192 GB VRAM as native weights. Requires CPU/RAM offload, quantization, or a specialized MoE runtime. 1M context is not realistic on this VM without aggressive memory planning. | Card lists SGLang, vLLM, KTransformers, Transformers, and Unsloth paths | Medium. Official cards list support, but this VM has only 2 Blackwell GPUs and KTransformers/kt-kernel Blackwell proof still needs M7B smoke tests. | Slow on this VM unless quantized/offloaded efficiently | Very high | Top 3 large/high-quality candidate, but not first download due 1.4 TiB footprint and memory risk |
| `MiniMaxAI/MiniMax-M3` | MiniMax AI | MiniMax Community | 427B | Not clearly published on the card; config uses 4 experts per token | 1M | BF16/F32 safetensors; MSA sparse attention; quantizations listed by HF | About 796 GiB safetensors | Native weights exceed VRAM; feasible only with CPU/RAM offload, quantization, or specialized serving. 1M context remains high risk on 2 GPUs. | Card recommends SGLang, vLLM, Transformers, KTransformers, Unsloth | Medium to high. Model-specific MSA kernels and custom code add compatibility risk on Blackwell until tested. | Slow to medium if MSA/runtime path works; slow otherwise | Very high, especially agentic/coding/multimodal | Top 3 large/high-quality candidate; review license and custom-code risk before download |
| `Qwen/Qwen3-235B-A22B-Instruct-2507` | Qwen | Apache-2.0 | 235B | 22B | 262,144 native; 1,010,000 with DCA/MInference config | BF16 safetensors; external quantizations listed | About 438 GiB safetensors | Native BF16 exceeds VRAM but fits system RAM. 1M context note says about 1000 GB total GPU memory, so this VM should target reduced context first. | Card lists SGLang, vLLM, llama.cpp, and KTransformers support paths | Medium. Qwen support is broad, but official long-context examples assume more aggregate GPU memory than this VM has. | Medium if quantized/offloaded; slow at high context | High | Top 3 large/high-quality candidate and best license/quality balance |
| `deepseek-ai/DeepSeek-V4-Flash` | DeepSeek | MIT | 284B | 13B | 1M | Official FP4 + FP8 mixed; expert params FP4 and most other params FP8 | About 149 GiB safetensors | Best large-model fit for 192 GB aggregate VRAM, but long-context KV cache can still exceed practical memory. | Card shows SGLang, Docker, Docker Model Runner, and quantization paths; KTransformers repo lists DeepSeek-V4-Flash support | Medium. Official mixed precision improves fit, but DeepSeek architecture/runtime support still needs Blackwell smoke tests. | Medium for a large model | High | Alternate/comparator; best first large-quality experiment if human prioritizes feasibility over the three frontier shortlist models |
| `Qwen/Qwen3.6-35B-A3B` | Qwen | Apache-2.0 | 35B | 3B | 262,144 native; 1,010,000 with YaRN | BF16 safetensors; multimodal/VLM model; text-only serving option documented | About 67 GiB safetensors | Fits within one 96 GB GPU for weights, but 128K-262K context needs careful KV cache sizing. 1M context should be deferred. | Card recommends SGLang, vLLM, and KTransformers guide paths; examples expose OpenAI-compatible endpoint | Low to medium. Newer `qwen3_5_moe` and VLM architecture may need latest runtime; use text-only mode first. | Fast to medium | High for coding/agentic work | Top 3 smaller/faster candidate; best quality among fast shortlist |
| `Qwen/Qwen3-30B-A3B-Instruct-2507` | Qwen | Apache-2.0 | 30.5B | 3.3B | 262,144 native | BF16 safetensors; external quantizations listed | About 56.9 GiB safetensors | Fits comfortably for weights on one GPU; context length and concurrency still require memory limits. | Card lists SGLang, vLLM, OpenAI-compatible API, llama.cpp, and KTransformers support paths | Low. Mature Qwen3 MoE support and modest weight size. | Fast | Medium-high | Top 3 smaller/faster candidate; recommended first real technical model |
| `Qwen/Qwen3-30B-A3B-Thinking-2507` | Qwen | Apache-2.0 | 30.5B | 3.3B | 262,144 native | BF16 safetensors; external quantizations listed | About 56.9 GiB safetensors | Fits comfortably for weights on one GPU; thinking-mode long outputs increase KV/cache pressure. | Card lists SGLang, vLLM, OpenAI-compatible API, llama.cpp, and KTransformers support paths | Low. Same base runtime profile as Instruct variant, but longer outputs need stricter limits. | Fast to medium | High reasoning for its size | Top 3 smaller/faster candidate for reasoning |
| `Qwen/Qwen3-Coder-30B-A3B-Instruct` | Qwen | Apache-2.0 | 30.5B | 3.3B | 262,144 native | BF16 safetensors; external quantizations listed | About 56.9 GiB safetensors | Fits comfortably for weights on one GPU; repository-scale prompts need reduced context first. | Card lists vLLM, Transformers, llama.cpp and KTransformers support for Qwen3 | Low to medium. Good coding fit, but older than Qwen3.6 and the 2507 variants. | Fast | High for coding-specific tasks | Coding-specific alternate; consider if M9 is primarily code generation/repair |
| `Qwen/Qwen3-0.6B` | Qwen | Apache-2.0 | 0.6B | Dense | 32,768 | BF16 safetensors; external quantizations listed | About 1.4 GiB safetensors | Fits trivially. Suitable for backend/API smoke only, not quality benchmarking. | Card lists SGLang, vLLM, Transformers, llama.cpp, KTransformers | Low | Very fast | Low | Recommended first download for smoke test only |

## Runtime Comparison

| Backend | Model support | Blackwell/CUDA requirement | Heterogeneous RAM+VRAM support | OpenAI-compatible API support | Docker suitability | Expected complexity | Risks |
| --- | --- | --- | --- | --- | --- | --- | --- |
| SGLang | Broad support for Qwen, DeepSeek, GLM, MiniMax and multimodal models; model cards list SGLang for all primary candidates | Uses CUDA/PyTorch stack inside runtime image or environment; official docs list NVIDIA hardware support including Blackwell-class systems | Primarily GPU-serving oriented; can use tensor/expert parallelism but not the main RAM+VRAM offload tool | Yes, model cards and docs show OpenAI-compatible endpoints | Good, but M7B must pin image/version and mount `/data/models`, `/data/hf-cache`, and `/data/logs`; do not use `latest` | Medium | Official examples often bind `0.0.0.0`; this repo must bind `127.0.0.1`. Long-context examples may assume more GPUs than this VM has. |
| vLLM | Broad Hugging Face model support; Qwen and GLM cards list vLLM versions; strong quantization/kernel ecosystem | Uses CUDA/PyTorch stack; Blackwell support depends on selected wheel/image and kernels | Primarily GPU-serving oriented; not the preferred path for huge CPU-offloaded MoE on this host | Yes, official docs list OpenAI-compatible server, Anthropic Messages API, and gRPC | Good, but M7B must pin image/version and avoid host package installs | Medium | Some model cards require very new/nightly versions for 1M context or newer architectures; avoid 1M context first. |
| KTransformers / KT-Kernel | Official repo lists recent support for GLM-5.2, MiniMax-M3, DeepSeek-V4-Flash, Qwen3-Next/Qwen3.5 MoE, and CPU-GPU expert scheduling | Build/runtime path must prove SM_120/Blackwell behavior in M7B; host CUDA Toolkit remains absent unless a container build path is approved | Yes. This is its main reason to exist for this VM: CPU/GPU heterogeneous MoE inference with hot experts on GPU and cold experts in RAM | Partial/direct server path is less mature than SGLang/vLLM; SGLang integration is a safer API route | Possible, but likely needs custom build container and `/data/build`; no install/build in M7A | High | Most important large-model backend, but also the highest implementation risk. Requires pinned commit, source-build plan, and Blackwell smoke proof before any recommendation to deploy. |
| ik_llama.cpp | GGUF/quantized path; repo lists Qwen3, GLM-5, Qwen3.5-MoE and many quant improvements | CUDA build requires NVIDIA driver and CUDA Toolkit in build environment; can be containerized later | Yes for GGUF hybrid CPU/GPU offload and tensor overrides | Yes through `llama-server`; repo also lists OpenAI `/v1/responses` endpoint support | Good for self-built container after M7B build plan; not for M7A | Medium-high | Depends on high-quality GGUF availability and model conversion/quantization compatibility. Not the first path for official HF safetensors. |
| llama.cpp | Mainline GGUF/quantized path, broad community support | CUDA builds use `-DGGML_CUDA=ON`; build docs support explicit CUDA architecture lists | Yes for GGUF CPU/GPU offload, but less specialized than ik_llama for some MoE quant paths | Yes through `llama-server` | Good for small smoke or GGUF fallback | Medium | Use mainly as fallback/reference for GGUF. It is not the primary path for the official HF-format large MoE shortlist. |

## Top 3 Large/High-Quality Candidates

1. `Qwen/Qwen3-235B-A22B-Instruct-2507`
   - Best balance of open license, official runtime support, active-parameter efficiency, and storage size among the primary large candidates.
   - Do not attempt 1M context on this VM first; the model card states about 1000 GB total GPU memory is needed for 1M context.

2. `MiniMaxAI/MiniMax-M3`
   - Strong agentic/coding/multimodal candidate with official SGLang/vLLM/KTransformers paths and MSA for long context.
   - Requires license review and custom-code/runtime validation before download.

3. `zai-org/GLM-5.2`
   - Strong frontier-style open model with MIT license and official SGLang/vLLM/KTransformers support notes.
   - Not a first download because native files are about 1.4 TiB and active-parameter count is not explicitly published in the model card.

Alternate/comparator: `deepseek-ai/DeepSeek-V4-Flash` is the most feasible large-quality first experiment because its official FP4+FP8 mixed safetensors are about 149 GiB and should fit the aggregate VRAM budget with reduced context. Keep it as a comparator unless human review decides feasibility should outrank maximum quality.

## Top 3 Smaller/Faster Candidates

1. `Qwen/Qwen3-30B-A3B-Instruct-2507`
   - Recommended first real technical model after smoke testing.
   - General, non-thinking mode, Apache-2.0, about 56.9 GiB storage, 3.3B active parameters.

2. `Qwen/Qwen3.6-35B-A3B`
   - Best quality/agentic-coding candidate in the smaller set.
   - Use text-only serving first to reduce VLM memory complexity.

3. `Qwen/Qwen3-30B-A3B-Thinking-2507`
   - Best smaller reasoning candidate.
   - Start with conservative output and context limits because thinking mode increases KV/cache pressure.

Coding-specific alternate: `Qwen/Qwen3-Coder-30B-A3B-Instruct` remains useful if the human wants the M9 benchmark to emphasize code repair/generation over general technical chat.

## First-Download Recommendation

Do not download anything in M7A.

After M7B creates a guarded backend abstraction and M8 authorizes a smoke service, download `Qwen/Qwen3-0.6B` first to `/data/models` with Hugging Face cache redirected to `/data/hf-cache`. It is about 1.4 GiB, Apache-2.0, and is sufficient to validate storage, cache placement, localhost API behavior, logs, auth checks, streaming, and restart/reboot handling.

After smoke passes, the first real model should be `Qwen/Qwen3-30B-A3B-Instruct-2507`.

## First Backend Recommendation

Implement SGLang first in M7B as a pinned, localhost-only Docker backend profile, with all mounts under `/data` and no API exposure beyond `127.0.0.1`.

Rationale:

- It is listed by the current official cards for Qwen, GLM, MiniMax, and DeepSeek candidates.
- It exposes OpenAI-compatible endpoints.
- It is lower complexity than KTransformers for the first smoke and 30B-class tests.
- It keeps KTransformers available as the second, large-MoE heterogeneous profile instead of blocking the first API smoke on source-build uncertainty.

M7B should also define, but not necessarily run first, KTransformers/KT-Kernel and ik_llama profiles:

- KTransformers/KT-Kernel for GLM-5.2, MiniMax-M3, DeepSeek-V4-Flash, and future very large MoE CPU/GPU experiments.
- ik_llama for GGUF quantized fallback where official or high-quality quantizations are selected later.

## Recommended Test Sequence

1. Small smoke model:
   - Model: `Qwen/Qwen3-0.6B`
   - Backend: SGLang first, vLLM optional cross-check
   - Context target: 4K then 32K
   - Goal: storage/cache/log placement, localhost OpenAI-compatible chat completions, streaming, auth handling, stop/start/status scripts, root-disk guard before and after

2. Fast technical model:
   - Model: `Qwen/Qwen3-30B-A3B-Instruct-2507`
   - Backend: SGLang first, vLLM cross-check if time allows
   - Context target: 32K, then 128K, then 262K only if memory allows
   - Goal: throughput, latency, GPU memory, RAM use, long-context stability, tool/function-call parser compatibility

3. Large quality model:
   - Primary model for quality shortlist: `Qwen/Qwen3-235B-A22B-Instruct-2507`
   - Practical comparator: `deepseek-ai/DeepSeek-V4-Flash`
   - Backend: KTransformers/KT-Kernel or SGLang/vLLM only after M7B proves the selected path; use reduced context first
   - Goal: prove memory plan before download, avoid 1M context initially, compare quality/speed/storage against smaller models

## Guard Checks Run

```bash
scripts/common/require-data-mounted.sh
scripts/common/root-disk-guard.sh --report reports/m3-root-disk-guard.md
scripts/docker/verify-docker-storage.sh
scripts/nvidia/verify-gpu-containers.sh
```

Result: all passed. The GPU container verifier saw both RTX PRO 6000 Blackwell GPUs and passed with `nvidia/cuda:13.2.1-base-ubuntu24.04`.

## Biggest Risks

- Official long-context examples for larger Qwen models assume far more aggregate GPU memory than this VM has; start with reduced context.
- Native safetensors for GLM-5.2 and MiniMax-M3 exceed practical VRAM and consume a large fraction of `/data`.
- KTransformers/KT-Kernel is the key heterogeneous MoE path, but Blackwell SM_120 behavior must be proven by M7B smoke tests before use.
- MiniMax-M3 uses a community license and custom/model-specific code paths; review license and runtime trust settings before download.
- ik_llama/llama.cpp paths depend on GGUF/quantization quality and compatibility; do not treat community quantizations as equivalent to official model cards without review.
- Any backend image or wheel must be pinned. Do not use floating `latest` images in implementation milestones.

## PASS/STOP

PASS:

- M7A research and shortlist are complete.
- Current source-cited candidates and runtime matrix are documented.
- Required guard checks passed.
- The recommended next task is human review, then M7B backend runtime abstraction.

STOP:

- No model download is approved by M7A.
- No backend installation/build is approved by M7A.
- No Docker/containerd change or restart is approved by M7A.
- No model service or API exposure is approved by M7A.
