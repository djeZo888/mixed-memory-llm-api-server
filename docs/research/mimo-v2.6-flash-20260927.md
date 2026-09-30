# MiMo-V2.6-Flash as a possible GLM Flash replacement

**Selection update:** the quality-first trial now selects Pro first; see the
[current plan](../h014-mimo-trial-plan.md) and [pinned source review](../../reports/h014-mimo-selection-20260927/REPORT.md).
The 155.875 GiB Flash artifact discussed below retains native expert MXFP4 but
also quantizes nonexpert matrices to Q8. It is not a full-native-precision
artifact. A separate MXFP4/BF16 Flash candidate is 162.896 GiB. The original
research below is retained with this correction; no model has yet been run.

Research only, 27 September 2026. The user proposes replacing GLM-5.3-Flash,
reusing its system RAM and one fast Blackwell. Both Qwen instances and the Ada
image service remain separate. No MiMo download, runtime installation or model
replacement was performed.

## Recommendation

MiMo-V2.6-Flash-RL merits the next bounded comparison after the current Flash and
ECC tests. RAM capacity is unlikely to be the limiting factor. The important
unknowns are CPU/GPU runtime efficiency, long-context allocation and reliable
tool continuation on our exact RTX PRO 6000 SM120 hardware. No local speed or
quality result exists for MiMo yet; GLM's measured speed cannot be transferred
to a different architecture.

Xiaomi describes Flash as a 309B-total / 15B-active MoE with a 1M context and
multimodal inputs. It is MIT licensed. These are model capabilities, not proof
that every modality works in a selected local runtime.
[Official model card](https://huggingface.co/XiaomiMiMo/MiMo-V2.6-Flash-RL).

## Weight size and memory

The approximately 310B parameter count is distinct from bytes. Selected MXFP4
GGUF base weights total **167.369 GB / 155.875 GiB**. The publisher says the routed
experts retain the source model's native MXFP4 precision. Avoid downloading all
variants: this GGUF repository totals 310.535 GB across MXFP4, Q2_K and sidecars;
that is not the requirement for a single selected model.
[GGUF files and notes](https://huggingface.co/ggml-org/MiMo-V2.6-Flash-RL-GGUF/tree/a5d1269fdcf9c3346934411f700038e9cd9d5102).

The official checkpoint's main shards are 171.743 GB, or 172.933 GB with its MTP
file; all safetensors including audio/draft files total 177.741 GB. Metadata was
read at revision `5711b268169967567844e1e560e8a3966da959b1` without downloading
weights. Stored MXFP4 and FP8 execution are distinct; runtime expansion/repacking
can increase the live footprint.
[Official files](https://huggingface.co/XiaomiMiMo/MiMo-V2.6-Flash-RL/tree/5711b268169967567844e1e560e8a3966da959b1),
[vLLM storage/execution recipe](https://recipes.vllm.ai/XiaomiMiMo/MiMo-V2.6-Flash-RL).

It cannot fit wholly in one 96 GB GPU. A CPU-expert/GPU-attention deployment is
plausible within 896 GiB host RAM, but must account for caches, staging buffers,
allocator overhead and the other resident services. As an architecture-only
estimate, nine global layers × four KV heads × (192 key + 128 value dimensions)
× two bytes gives 22.5 GiB global KV at 1,048,576 tokens, before sliding-window state, draft model,
workspace and allocation overhead. An FP8 equivalent would halve that term,
only if the exact runtime supports it correctly. This is not a measured peak
or a guaranteed 1M configuration.
[Model configuration](https://huggingface.co/XiaomiMiMo/MiMo-V2.6-Flash-RL/blob/5711b268169967567844e1e560e8a3966da959b1/config.json).

## Published benchmark signals

These are publisher-reported results with different harnesses/settings, not our
controlled comparison. They justify testing; the small MiMo/GLM gaps do not
establish a universal winner.

| Benchmark | MiMo-V2.6-Flash | GLM-5.3-Flash | Qwen3.8-27B |
| --- | ---: | ---: | ---: |
| DeepSWE v1.1 | 67.9 | 63.4 | 42.2 |
| Terminal-Bench 2.1 | 87.6 | 84.3 | 73.0 |

Sources: [MiMo](https://huggingface.co/XiaomiMiMo/MiMo-V2.6-Flash-RL),
[GLM evaluation record](https://huggingface.co/zai-org/GLM-5.3-Flash/blob/main/.eval_results/GLM-5.3-Flash.yaml),
[Qwen](https://huggingface.co/Qwen/Qwen3.8-27B).
For example, GLM's DeepSWE uses mini-swe-agent/400K while Qwen's uses Claude
Code/256K. A faster default Qwen remains useful even if a frontier model solves
more difficult tasks.

## Runtime choice and proposed bounded trial

Start with a recent pinned **llama.cpp** and the native-MXFP4 GGUF. MiMo-V2.6
conversion support, including a tool-parser correction, merged on 22 September;
upstream reports loading with vision. This provides a concrete mixed-memory
candidate, but not a local SM120 performance certification.
[Merged implementation](https://github.com/ggml-org/llama.cpp/pull/29257).

Keep KTransformers as an alternative only after confirming the exact 2.6 loader,
MXFP4 CPU kernels and CUDA/SM120 paths. Older MiMo support alone is insufficient.
The current vLLM recipe needs a recent/nightly 2.6-capable build and describes
multi-GPU deployment; copying it does not establish a one-GPU CPU-expert setup.
[KTransformers releases](https://github.com/kvcache-ai/ktransformers/releases),
[vLLM recipe](https://recipes.vllm.ai/XiaomiMiMo/MiMo-V2.6-Flash-RL).

For a separately authorized trial: preserve qualified GLM rollback, reuse its
GPU slot, warm MiMo, then run identical 4K/16K retrieval/reasoning fixtures and
bounded coding/tool-continuation cases. Measure prefill, decode, total task time
and memory; check configured large capacity separately. Start without speculative
decoding, then add its draft model only if correctness and basic performance pass.
Validate tool-loop limits: upstream issue reports describe repeated tool-call
batches in MiMo Code; those reports do not prove the same problem in Sova.
[Reported agent failure](https://github.com/XiaomiMiMo/MiMo-Code/issues/2482).

Choose on completed task quality, latency and reliable tool use, retaining GLM
until MiMo has passed that comparison. No claim of a guaranteed speed increase.
