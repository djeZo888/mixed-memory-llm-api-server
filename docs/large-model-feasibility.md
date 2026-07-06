# Large-Model Feasibility

M9D is a planning/dry-run milestone for the first large-model proof-of-life. No large model is downloaded in M9D, no backend/runtime is installed or built, no Docker image is pulled, no model/backend container is started, and the active 30B SGLang model remains running.

## Current Baseline

- Active model: `Qwen/Qwen3-30B-A3B-Instruct-2507`.
- Runtime: SGLang in `lmsysorg/sglang:v0.5.14-cu130`.
- Endpoint: `http://127.0.0.1:30001/v1`.
- Bind: `127.0.0.1:30001` only.
- Launch args: `--tp 2 --context-length 32768 --mem-fraction-static 0.75`.
- M9C benchmark passed, but its largest context case was `16,581` prompt characters / `3,518` prompt tokens, not a true 16K-token context test.
- Current services do not auto-start after reboot; boot persistence remains deferred.

## M9D Recommendation

- First large proof-of-life candidate: `MiniMaxAI/MiniMax-M3-MXFP8`.
- Runtime path: KTransformers/KT-Kernel plus SGLang heterogeneous CPU/GPU serving.
- Fallback candidate: `Qwen/Qwen3-235B-A22B-Instruct-2507-FP8` only if human review prioritizes Apache-2.0 and M9E first proves a current two-GPU/offload path.
- Comparison-only candidate: `nvidia/MiniMax-M3-NVFP4`; relevant, but not first because the current card points to vLLM nightly support and TP8.

## Why This Is High Risk

The VM has 2 x 96 GB VRAM, about 192 GB total before overhead. The required large candidates exceed that when served as normal full-GPU weights:

| Model | Current `.safetensors` estimate | Practical note |
| --- | --- | --- |
| `Qwen/Qwen3-235B-A22B-Instruct-2507` | 437.90 GiB | BF16 does not fit VRAM. |
| `Qwen/Qwen3-235B-A22B-Instruct-2507-FP8` | 220.19 GiB | Still above aggregate VRAM before KV/cache overhead. |
| `zai-org/GLM-5.2` | 1403.19 GiB | Too large for first download. |
| `MiniMaxAI/MiniMax-M3` | 795.51 GiB | Use MXFP8 variant instead. |
| `MiniMaxAI/MiniMax-M3-MXFP8` | 413.27 GiB | Fits `/data` and RAM; needs CPU/GPU offload. |
| `nvidia/MiniMax-M3-NVFP4` | 232.93 GiB | Relevant but not a proven two-GPU fit. |

## M9E Shape After Human Review

M9E should run only one approved large-model proof-of-life at a time:

1. Start from clean `main`, verify hostname `llmserver` and repo path `/data/services/mixed-memory-llm-api-server`.
2. Run `/data`, root-disk, Docker, GPU, and active-model guards.
3. Stop the current 30B backend only after explicit human approval.
4. Download exactly one approved model to `/data/models` with cache under `/data/hf-cache`.
5. Install/build only the approved runtime path under `/data/build` or in an approved container strategy.
6. Bind only to localhost, preferably a distinct proof port such as `127.0.0.1:30002`.
7. Start with text-only, one request, 8192 tokens or less, and reduced server token/cache settings.
8. Verify `/v1/models`, non-streaming chat, streaming chat, storage guards, GPU/RAM snapshots, and rollback.
9. If runtime compatibility is unclear, STOP and document the uncertainty instead of guessing.

M10 API/front-door/auth planning remains deferred until after M9E or an explicit human sequencing change.

## Report

The detailed source-cited report is:

```text
reports/m9d-large-model-feasibility-plan.md
```
