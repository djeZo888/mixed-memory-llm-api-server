# SGLang First Real Fast Model Plan

M9A plans the first real fast-model deployment after the live SGLang smoke service. It is planning/dry-run only. It does not download `Qwen/Qwen3-30B-A3B-Instruct-2507`, pull Docker images, stop smoke, start containers, expose an API, install packages, or modify Docker/containerd.

## Current Baseline

- Active smoke model: `qwen3-0.6b-smoke`
- Runtime: SGLang
- Active endpoint: `http://127.0.0.1:30000/v1`
- Bind: `127.0.0.1:30000` only
- Active image: `lmsysorg/sglang:v0.5.14-cu130`
- Active model path: `/data/models/qwen3-0.6b-smoke`
- M9A context-sync result: PASS

The smoke service remains running during M9A. M9B must stop it through `scripts/llmctl stop --yes` only after human approval.

## Recommendation

Recommended M9B primary model:

```text
Qwen/Qwen3-30B-A3B-Instruct-2507
```

Planned local path:

```text
/data/models/qwen3-30b-a3b-instruct-2507
```

Planned first real endpoint:

```text
http://127.0.0.1:30001/v1
```

The M9A template uses `127.0.0.1:30001:30000` so the real-model plan cannot collide with the active smoke endpoint during review. Reusing host port `30000` after stopping smoke is a valid alternate M9B decision if the human wants localhost API continuity, but the safer first benchmark path is `30001` because it makes smoke-vs-real state explicit.

## Candidate Summary

| Model | First-use decision | Reason |
| --- | --- | --- |
| `Qwen/Qwen3-30B-A3B-Instruct-2507` | Primary | Lowest-risk first real model: Apache-2.0, 30.5B total / 3.3B active, 262K native context, non-thinking mode, SGLang-supported, about 61.1 GB decimal / 56.9 GiB safetensors. |
| `Qwen/Qwen3.6-35B-A3B` | Defer | Stronger agentic coding and multimodal candidate, but newer hybrid GDN/VLM behavior and SGLang `>=0.5.10` requirement make it a second-run target. |
| `Qwen/Qwen3-30B-A3B-Thinking-2507` | Defer | Strong reasoning candidate with same footprint as primary, but thinking-only outputs increase KV/cache, latency, and max-token pressure. |
| `Qwen/Qwen3-Coder-30B-A3B-Instruct` | Coding fallback | Available and relevant for coding-specific quality fallback, but not the lowest-risk first real deployment target. |

## SGLang Runtime Plan

Template:

```text
configs/compose/compose.sglang-qwen3-30b.template.yml
```

Initial conservative launch settings:

```text
image: lmsysorg/sglang:v0.5.14-cu130
host bind: 127.0.0.1:30001:30000
model path: /data/models/qwen3-30b-a3b-instruct-2507
context length: 32768
max running requests: 1
mem fraction static: 0.70
```

M9A keeps the full SGLang image used successfully by M8B/M8C. SGLang docs publish Docker images under `lmsysorg/sglang` and state CUDA 13 is the default environment. The smaller runtime image is not selected here because M8B found the pinned runtime variant missing the `distro` dependency in this environment.

## M9B Sequence

1. Confirm hostname `llmserver` and repo path `/data/services/mixed-memory-llm-api-server`.
2. Rerun `/data`, root-disk, Docker storage, GPU container, `llmctl`, smoke lifecycle, and smoke API checks.
3. Stop smoke through `scripts/llmctl stop --yes`.
4. Download `Qwen/Qwen3-30B-A3B-Instruct-2507` only to `/data/models/qwen3-30b-a3b-instruct-2507` with Hugging Face cache under `/data/hf-cache`.
5. Verify or pull only the human-approved pinned SGLang image.
6. Start the real SGLang profile on `127.0.0.1:30001`.
7. Verify `/health`, `/v1/models`, non-streaming chat, and streaming chat.
8. Record startup time, throughput, latency, VRAM, RAM, context stability, and failure modes.
9. Rerun root-disk, Docker storage, GPU container, and manager-state checks.
10. If real startup fails, stop the real profile, keep model files for review, and either restart smoke or leave no active backend based on human instruction.

## Risks

- VRAM: 30B BF16 weights are about 56.9 GiB, leaving limited room for long-context KV cache on one 96 GB GPU. Start at 32K context.
- Long context: official cards support 262K context, but M9B should scale 32K, then 128K, then 262K only after memory checks pass.
- MoE behavior: active parameters are small, but expert routing, KV cache, and prefill can still reserve large GPU memory.
- SGLang image compatibility: `lmsysorg/sglang:v0.5.14-cu130` is already verified for smoke on this VM. Do not switch tags without digest/import verification.
- Smoke staleness: stopping smoke for M9B makes smoke inactive. If real deployment fails, restart smoke through reviewed `llmctl` commands or document no-active-backend state.

## Sources

- Hugging Face model card: https://huggingface.co/Qwen/Qwen3-30B-A3B-Instruct-2507
- Hugging Face model card: https://huggingface.co/Qwen/Qwen3.6-35B-A3B
- Hugging Face model card: https://huggingface.co/Qwen/Qwen3-30B-A3B-Thinking-2507
- Hugging Face model card: https://huggingface.co/Qwen/Qwen3-Coder-30B-A3B-Instruct
- Qwen SGLang deployment docs: https://qwen.readthedocs.io/en/latest/deployment/sglang.html
- SGLang installation docs: https://docs.sglang.io/docs/get-started/install
- SGLang Qwen3 cookbook: https://docs.sglang.io/cookbook/autoregressive/Qwen/Qwen3
- SGLang Qwen3.6 cookbook: https://docs.sglang.io/cookbook/autoregressive/Qwen/Qwen3.6
- SGLang server arguments: https://docs.sglang.io/docs/advanced_features/server_arguments

## M9A Boundary

PASS for planning only. STOP for actual download/deployment until human review.
