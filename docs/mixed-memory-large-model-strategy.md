# Mixed-Memory Large-Model Strategy

This VM has two 96 GB-class RTX PRO 6000 Blackwell Workstation GPUs and roughly 900 GiB of usable system RAM. M9F makes that RAM a first-class inference resource. The project should not require every target model to fit fully in VRAM before it is considered useful.

## Why System RAM Matters

Very large MoE models have many total parameters but far fewer active parameters per token. When the runtime can keep hot experts on GPU and cold experts in CPU RAM, a workstation with large RAM can run models that are impossible as pure full-GPU deployments on two GPUs.

This changes the project goal:

- Full VRAM fit is not mandatory for every target.
- Reduced speed is acceptable for hard tasks if quality improves.
- Initial proof-of-life should use small context, one request, and conservative expert placement.
- Long-context growth comes after runtime stability, not before it.

## Runtime Classes

KTransformers / SGLang-KT heterogeneous expert offload:

- Best conceptual fit for large Hugging Face MoE checkpoints with CPU/GPU expert placement.
- KT-Kernel documentation describes hot experts on GPU and cold experts on CPU through SGLang integration.
- MiniMax proved the concept and exposed the current risk: model-specific GPU kernels can still block on SM120.

ik_llama / llama.cpp GGUF CPU+GPU offload:

- Best for GGUF or other quantized checkpoints with mature CPU+GPU layer offload.
- Useful when a high-quality quantized model exists and quality loss is acceptable.
- Often easier to make use of RAM, but model availability and exact quantization quality are model-specific.

vLLM / SGLang CPU offload:

- Strong OpenAI-compatible serving ecosystems.
- Good comparison path for Qwen-family models.
- Official Qwen3.5 examples assume high GPU memory and large tensor parallel shapes; CPU offload on this exact two-GPU SM120 workstation must be proven, not assumed.

## MiniMax Lesson

`MiniMaxAI/MiniMax-M3-MXFP8` was a correct architectural experiment because it matched the mixed RAM/VRAM goal and fit storage/RAM better than BF16. It stopped because the released MiniMax SGLang-KT MXFP8 path is SM90/SM100-oriented and does not currently support this VM's SM120 workstation GPUs cleanly. R1 fixed `libnuma.so.1` and `sgl_kernel` import loading; R2 proved the remaining blocker is source/runtime support, not model storage.

MiniMax is parked, not deleted. The downloaded model remains at `/data/models/minimax-m3-mxfp8`.

## Qwen3.5 Next Candidate

The next large mixed-memory investigation target is:

```text
Qwen/Qwen3.5-397B-A17B-FP8
```

Why it is attractive:

- Apache-2.0 license.
- Official model card reports 397B total parameters and 17B activated.
- Official context is 262,144 native tokens, extensible to about 1,010,000 tokens.
- Official model card says the FP8 artifacts are compatible with Transformers, vLLM, SGLang, KTransformers, and related runtimes.
- SGLang has a dedicated Qwen3.5 cookbook page.
- It is a strong candidate for technical/general expert and long-context worker roles if runtime support is proven.

Current caution:

- Official SGLang examples use tensor parallel 8 for the full 262K context shape.
- SGLang's Qwen3.5 memory table says FP8 weights require about 400 GB and lists B200/B300 datacenter shapes, not this exact two-GPU RTX PRO SM120 workstation shape.
- KTransformers docs currently show native precision support for Qwen3 and Qwen3-Next families, but M9F did not find a dedicated Qwen3.5 KTransformers tutorial equivalent to the MiniMax tutorial.
- SM120 support must be verified before any Qwen3.5 model download.

## First-Run Strategy

M9G should perform runtime preflight only:

1. Refresh official sources and upstream issues.
2. Identify a Qwen3.5-compatible SGLang/KTransformers/vLLM runtime candidate.
3. Build or verify the runtime only after human approval in M9G scope.
4. Prove SM120 import/kernel gates without Qwen3.5 weights.
5. Confirm no MiniMax-style SM90/SM100-only guards block Qwen3.5.
6. Keep the 30B service running throughout M9G.

M9H, only after M9G passes, may request approval for model download and proof-of-life.

Expected first proof context:

- Start at 8192 tokens.
- If stable, try 16384 tokens.
- Do not attempt 128K, 262K, or 1M context first.

Expected speed:

- Several tokens/sec is acceptable if answer quality is high.
- Startup and first-token latency may be high because weights may reside mostly in RAM.

Stop condition:

- Do not download Qwen3.5 if SM120 runtime gates fail.
- Do not stop the 30B service until download, runtime, and localhost proof plan are approved.
- Do not proceed if the runtime requires public bind, Docker daemon changes, host package installs, or global CUDA Toolkit installation.
