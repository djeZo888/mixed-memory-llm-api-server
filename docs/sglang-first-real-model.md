# SGLang First Real Fast Model Plan

M9A planned the first real fast-model deployment after the live SGLang smoke service. M9B has now deployed `Qwen/Qwen3-30B-A3B-Instruct-2507` locally on SGLang while keeping public exposure absent.

## M9B Actual Result

M9B deployed the first real fast model successfully on branch `milestone/m9b-first-real-fast-model-deploy`.

- Active model: `Qwen/Qwen3-30B-A3B-Instruct-2507`.
- Served model name: `qwen3-30b-a3b-instruct-2507`.
- Runtime: SGLang in Docker image `lmsysorg/sglang:v0.5.14-cu130`.
- Local model path: `/data/models/qwen3-30b-a3b-instruct-2507`.
- Endpoint: `http://127.0.0.1:30001/v1`.
- Host bind: `127.0.0.1:30001` only.
- Runtime compose file: `/data/services/llm-manager/compose/sglang-qwen3-30b.compose.yml`.
- Active state file: `/data/services/llm-manager/active/active.json`.
- Launch args: `--tp 2 --context-length 32768 --mem-fraction-static 0.75`.
- Smoke model was stopped but preserved at `/data/models/qwen3-0.6b-smoke`.
- `/v1/models`, non-streaming chat, streaming chat, and a technical PCIe passthrough prompt passed.
- Public API exposure remains absent; no firewall, Caddy, reverse proxy, TLS, auth, or front-door service was added.

Query the local endpoint:

```bash
curl -fsS http://127.0.0.1:30001/v1/models
curl -fsS http://127.0.0.1:30001/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"qwen3-30b-a3b-instruct-2507","messages":[{"role":"user","content":"Reply with one short sentence."}],"max_tokens":64,"temperature":0}'
```

Inspect logs and state:

```bash
scripts/llmctl active
scripts/llmctl status
scripts/llmctl logs --dry-run
scripts/llmctl logs --yes
sudo -n docker logs --tail 200 sglang-qwen3-30b-a3b-instruct-2507
```

Lifecycle support after M9B:

```bash
scripts/llmctl stop --dry-run
scripts/llmctl stop --yes
scripts/llmctl restart --dry-run
```

`restart --dry-run` documents the intended refusal for the real model. `restart --yes` remains unsupported for the real model until M9C lifecycle/benchmark review. Use `stop --yes` only when a human explicitly wants to stop the active real backend.

Run live verification:

```bash
scripts/sglang/verify-sglang-real-fast-live.sh
```

## Current Baseline

- Active real model: `qwen3-30b-a3b-instruct-2507`
- Runtime: SGLang
- Active endpoint: `http://127.0.0.1:30001/v1`
- Bind: `127.0.0.1:30001` only
- Active image: `lmsysorg/sglang:v0.5.14-cu130`
- Active model path: `/data/models/qwen3-30b-a3b-instruct-2507`
- M9B result: PASS on branch `milestone/m9b-first-real-fast-model-deploy`

The smoke service is stopped but its model files and image are preserved.

## Recommendation

M9B primary model:

```text
Qwen/Qwen3-30B-A3B-Instruct-2507
```

Actual local path:

```text
/data/models/qwen3-30b-a3b-instruct-2507
```

Actual first real endpoint:

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

M9B actual conservative launch settings:

```text
image: lmsysorg/sglang:v0.5.14-cu130
host bind: 127.0.0.1:30001:30000
model path: /data/models/qwen3-30b-a3b-instruct-2507
tensor parallelism: --tp 2
context length: --context-length 32768
memory fraction: --mem-fraction-static 0.75
```

M9B used the full SGLang image already verified by M8B/M8C. SGLang docs publish Docker images under `lmsysorg/sglang` and state CUDA 13 is the default environment. The smaller runtime image is not selected here because M8B found the pinned runtime variant missing the `distro` dependency in this environment.

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

M9A was planning-only. M9B has now completed the approved actual download/deployment on the milestone branch and should be reviewed before merge.
