# M9A First Real Fast-Model Plan

- Timestamp: `2026-07-05T14:00:13Z`
- Branch: `milestone/m9a-first-real-fast-model-plan`
- Repository: `git@github.com:djeZo888/mixed-memory-llm-api-server.git`
- Repo path: `/data/services/mixed-memory-llm-api-server`
- Conclusion: PASS for planning only. STOP for actual download/deployment until human review.

## Context-Sync Result

PASS.

- Hostname gate: PASS, remote hostname is `llmserver`.
- Repo path gate: PASS, path is `/data/services/mixed-memory-llm-api-server`.
- Base branch sync: PASS, `main` was fast-forward current at `5431aee` before branching.
- Git identity: PASS, `CodexAIagent <133749519+djeZo888@users.noreply.github.com>`.
- Repo cleanliness: PASS after restoring known verifier side effects from `reports/m3-root-disk-guard.md` and `reports/m4b-docker-containerd-install.md` before creating the M9A branch.
- `/data` guard: PASS.
- Root-disk guard: PASS.
- Docker storage verifier: PASS.
- GPU container verifier: PASS with `nvidia/cuda:13.2.1-base-ubuntu24.04`.
- `scripts/llmctl doctor`: PASS.
- `scripts/llmctl validate`: PASS before M9A changes.
- `scripts/llmctl active`: PASS, smoke active.
- `scripts/llmctl status`: PASS, manager active.
- `scripts/sglang/verify-sglang-lifecycle.sh`: PASS.
- `scripts/api/smoke-openai-chat.sh --yes-run-smoke-api`: PASS.
- No first real model download, image pull, or new backend container start occurred during context-sync.

## Current Active Smoke State

- Model/backend: `qwen3-0.6b-smoke` on SGLang.
- Container: `sglang-smoke-qwen3-0.6b`.
- Status: running and healthy during context-sync.
- Endpoint: `http://127.0.0.1:30000/v1`.
- Bind: `127.0.0.1:30000` only.
- Image: `lmsysorg/sglang:v0.5.14-cu130`.
- Model path: `/data/models/qwen3-0.6b-smoke`.
- `/v1/models`: PASS and returned the smoke model.
- Chat smoke: PASS with non-empty content.

## Hardware And Software Baseline

- Host: `llmserver`.
- OS: Ubuntu 24.04.4 LTS.
- GPUs: 2 x NVIDIA RTX PRO 6000 Blackwell Workstation Edition.
- VRAM: `97887 MiB` per GPU, about 192 GB aggregate before runtime overhead.
- Driver: `595.71.05`.
- CUDA compatibility reported by `nvidia-smi`: `13.2`.
- Docker: `29.6.1`.
- Docker Root Dir: `/data/docker`.
- containerd: `v2.2.5` with root `/data/containerd/root` and state `/run/containerd`.
- NVIDIA Container Toolkit: installed and verified for Docker GPU containers.
- Host CUDA Toolkit and `nvcc`: absent by policy.
- Root filesystem: about 15G total, 4.5G free during context-sync.
- `/data`: about 2.0T total, 1.9T free during context-sync.

## Current Research Sources

Access date: 2026-07-05.

| Source | URL | Notes |
| --- | --- | --- |
| Hugging Face model card: Qwen/Qwen3-30B-A3B-Instruct-2507 | https://huggingface.co/Qwen/Qwen3-30B-A3B-Instruct-2507 | License, parameters, context, SGLang/vLLM serving notes, OOM guidance. |
| Hugging Face model card: Qwen/Qwen3.6-35B-A3B | https://huggingface.co/Qwen/Qwen3.6-35B-A3B | License, multimodal/hybrid behavior, SGLang deployment examples. |
| Hugging Face model card: Qwen/Qwen3-30B-A3B-Thinking-2507 | https://huggingface.co/Qwen/Qwen3-30B-A3B-Thinking-2507 | Thinking-only behavior, parameters, context, reasoning risk. |
| Hugging Face model card: Qwen/Qwen3-Coder-30B-A3B-Instruct | https://huggingface.co/Qwen/Qwen3-Coder-30B-A3B-Instruct | Optional coding-specific fallback availability and model facts. |
| Qwen SGLang deployment docs | https://qwen.readthedocs.io/en/latest/deployment/sglang.html | OpenAI-compatible SGLang API, default localhost service, tensor parallelism, thinking controls, context guidance. |
| SGLang installation docs | https://docs.sglang.io/docs/get-started/install | Docker image policy, CUDA 13 default, runtime image note. |
| SGLang Qwen3 cookbook | https://docs.sglang.io/cookbook/autoregressive/Qwen/Qwen3 | Qwen3 memory/context guidance and expert parallelism notes. |
| SGLang Qwen3.6 cookbook | https://docs.sglang.io/cookbook/autoregressive/Qwen/Qwen3.6 | Qwen3.6 SGLang `>=0.5.10`, hardware, context, MTP, tool/parser notes. |
| SGLang server arguments | https://docs.sglang.io/docs/advanced_features/server_arguments | Memory, context, tensor/data/expert parallelism, scheduling flags. |
| Hugging Face metadata API | `https://huggingface.co/api/models/<repo>?blobs=true` | Used only for safetensors size metadata; no weights downloaded. |

## Candidate Comparison

Storage is current Hugging Face metadata for `.safetensors` files only. It excludes cache duplication, tokenizer/config files, logs, and temporary download space.

| Model | License | Total params | Active params | Context length | File/storage estimate | Expected VRAM/RAM need | Expected SGLang compatibility | Expected first-run risk | Coding/technical chat | Reasoning |
| --- | --- | ---: | ---: | ---: | --- | --- | --- | --- | --- | --- |
| `Qwen/Qwen3-30B-A3B-Instruct-2507` | Apache-2.0 | 30.5B | 3.3B | 262,144 native | 16 safetensors, 61.07 GB / 56.87 GiB | Weights fit on one 96 GB GPU, but KV/cache requires conservative 32K context, max 1 running request, and memory monitoring; system RAM 128 GB+ is enough for staging. | High. Model card lists SGLang and says `sglang>=0.4.6.post1`; current full image `v0.5.14-cu130` is already smoke-verified. | Low to medium: lowest operational risk among real candidates, but 262K context can OOM. | Strong general technical chat, tool use, coding, and instruction following; best first real target. | Medium-high but non-thinking mode is not the reasoning-specialized path. |
| `Qwen/Qwen3.6-35B-A3B` | Apache-2.0 | 35B | 3B | 262,144 native, extensible beyond 1M in docs | 26 safetensors, 71.90 GB / 66.97 GiB | BF16 weights about 70 GB; fits one supported 96 GB GPU for weights, but multimodal/hybrid state and long context need stricter memory headroom; system RAM 192 GB+ recommended. | Medium-high. SGLang cookbook requires `sglang>=0.5.10`; current image likely meets this but M9B must verify image package version before deploy. | Medium: newer `qwen3_5_moe`, VLM/multimodal interface, MTP and thinking-preservation features add complexity. | Potentially best coding/agentic quality of fast shortlist, especially repo-level work. | High, with thinking mode default and preservation features. |
| `Qwen/Qwen3-30B-A3B-Thinking-2507` | Apache-2.0 | 30.5B | 3.3B | 262,144 native | 16 safetensors, 61.07 GB / 56.87 GiB | Similar weight fit to primary, but thinking-only mode can drive much longer outputs and KV/cache pressure; system RAM 192 GB+ recommended for safer long tests. | High for base architecture. Model card lists SGLang/vLLM and same Qwen3-MoE family. | Medium: output length and reasoning traces increase latency and memory risk. | Strong, but not ideal as first low-risk technical chat model because responses may be long. | Strongest reasoning candidate among 30B-class options. |
| `Qwen/Qwen3-Coder-30B-A3B-Instruct` | Apache-2.0 | 30.5B | 3.3B | 262,144 native | 16 safetensors, 61.07 GB / 56.87 GiB | Similar to primary; start at 32K context for repository-scale prompts and keep max 1 request first. | Medium-high. Qwen/SGLang docs include Qwen3-Coder deployment guidance; M9B would need a separate profile/template if selected. | Medium: coding-specific templates/tool calling need focused parser validation. | Best coding-specific fallback if primary quality is insufficient for code tasks. | Medium; not the first reasoning target. |

## Recommendation

Primary M9B first real model:

```text
Qwen/Qwen3-30B-A3B-Instruct-2507
```

Reason: it remains the lowest-risk first real fast model. It is Apache-2.0, has 30.5B total / 3.3B active parameters, 262K native context, current official SGLang support, a manageable 61.07 GB safetensors footprint, and non-thinking default behavior suitable for technical chat and coding smoke benchmarks.

Fallback model:

```text
Qwen/Qwen3-Coder-30B-A3B-Instruct
```

Use this as a coding-specific fallback only after human review if the primary deploys but does not satisfy coding quality goals. If the primary fails because the SGLang/Qwen3-MoE runtime path itself is broken, the operational fallback is to stop the failed real profile and restart the smoke service or leave no active backend based on human instruction.

Deferred candidates:

- `Qwen/Qwen3.6-35B-A3B`: likely higher quality, but newer hybrid GDN/VLM behavior and SGLang `>=0.5.10` requirements make it a better second real test.
- `Qwen/Qwen3-30B-A3B-Thinking-2507`: useful for reasoning, but thinking-only output increases memory and latency risk for the first real deployment.

## Planned Local Model Path

```text
/data/models/qwen3-30b-a3b-instruct-2507
```

Only M9B may create and populate this path after human review. M9A verifies it is absent.

## Planned Bind And Port

```text
127.0.0.1:30001:30000
```

The real-model template uses host port `30001` to avoid accidental collision with the live smoke endpoint on `30000` during review. Reusing `30000` after stopping smoke is a valid alternate M9B choice if endpoint continuity is more important than explicit smoke/real separation.

## Planned Active-State Transition

1. M9A leaves smoke active and unchanged.
2. M9B starts only after human review.
3. M9B runs `scripts/llmctl stop --yes` to stop the smoke container while preserving smoke files and images.
4. M9B downloads the real model to `/data/models/qwen3-30b-a3b-instruct-2507` only.
5. M9B starts the real SGLang profile on `127.0.0.1:30001`.
6. M9B writes/updates manager active state only after health, `/v1/models`, and chat checks pass.
7. If real health fails, M9B must stop the failed real profile and either restart smoke through `scripts/llmctl start --yes` or document a no-active-backend state for human review.

## M9B Sequence

1. Confirm VM hostname `llmserver` and repo path `/data/services/mixed-memory-llm-api-server`.
2. Sync `main` and check Git identity.
3. Run `/data`, root-disk, Docker storage, GPU container, `llmctl`, lifecycle, and smoke API checks.
4. Stop smoke through `scripts/llmctl stop --yes`.
5. Create `/data/models/qwen3-30b-a3b-instruct-2507`.
6. Download `Qwen/Qwen3-30B-A3B-Instruct-2507` to that local path only with cache under `/data/hf-cache`.
7. Verify or pull the approved pinned SGLang image only after human review.
8. Start the real SGLang profile on `127.0.0.1:30001`.
9. Run `/health`, `/v1/models`, non-streaming chat, streaming chat, and logs checks.
10. Record startup time, throughput, latency, RAM, VRAM, context stability, and failure modes.
11. Rerun root-disk guard, Docker storage verifier, GPU verifier, `llmctl validate`, active/status, and `git diff --check`.
12. Keep public API exposure blocked.

## Risk Section

- VRAM use: 30B BF16 weights are about 56.9 GiB before runtime overhead. The active smoke service currently reserves most of GPU 0, so smoke must be stopped before M9B real launch.
- Long context memory use: 262K native context is supported by the model card, but initial M9B should use 32K, then 128K, then 262K only after memory stability passes.
- MoE behavior: only 3.3B parameters are active per token, but expert routing, prefill, and KV cache still consume substantial GPU memory.
- SGLang image compatibility: current full image `lmsysorg/sglang:v0.5.14-cu130` worked for smoke; the earlier runtime image was rejected in M8B because it lacked `distro` in this environment. M9B must verify imports and image digest before any new pull/run.
- Leaving smoke inactive/stale: after M9B stops smoke, failed real deployment could leave no healthy backend. M9B must update active state consistently and either restart smoke or explicitly document inactive state.

## Artifacts Added Or Updated

- `configs/models/profiles/qwen3-30b-a3b-instruct-2507.yaml`
- `configs/models/profiles/qwen3.6-35b-a3b.yaml`
- `configs/models/profiles/qwen3-30b-a3b-thinking-2507.yaml`
- `configs/models/catalog.yaml`
- `configs/compose/compose.sglang-qwen3-30b.template.yml`
- `configs/sglang/qwen3-30b.env.example`
- `scripts/sglang/plan-sglang-real-fast.sh`
- `scripts/sglang/verify-sglang-real-fast-plan.sh`
- `tests/shell/test-sglang-real-fast-static.sh`
- `docs/sglang-first-real-model.md`
- `docs/current-state.md`
- `docs/model-matrix.md`
- `ROADMAP.md`

## No-Action Confirmations

- No real model was downloaded.
- No Docker image was pulled.
- No new model/backend container was started.
- The smoke model was not stopped.
- Docker/containerd daemon configuration was not modified.
- Docker/containerd was not restarted.
- No package was installed.
- No SGLang/PyTorch/KTransformers/vLLM/ik_llama/CUDA Toolkit build or install occurred.
- No public API exposure was configured.
- No model files, Docker images, or Docker data were deleted.
- No Docker prune was run.
- No disk, fstab, mountpoint, partitioning, or Proxmox host change occurred.


## M9A Validation Run

Checks run after implementation:

- `chmod +x scripts/sglang/plan-sglang-real-fast.sh scripts/sglang/verify-sglang-real-fast-plan.sh tests/shell/test-sglang-real-fast-static.sh`: PASS.
- `bash -n scripts/sglang/plan-sglang-real-fast.sh`: PASS.
- `bash -n scripts/sglang/verify-sglang-real-fast-plan.sh`: PASS.
- `bash -n tests/shell/test-sglang-real-fast-static.sh`: PASS.
- `tests/shell/test-sglang-real-fast-static.sh`: PASS.
- `scripts/sglang/plan-sglang-real-fast.sh --dry-run`: PASS; printed M9B sequence and confirmed no smoke stop, model download, image pull, container start, or API exposure.
- `scripts/sglang/verify-sglang-real-fast-plan.sh`: PASS.
- `scripts/common/require-data-mounted.sh`: PASS.
- `scripts/common/root-disk-guard.sh --report reports/m3-root-disk-guard.md`: PASS.
- `scripts/docker/verify-docker-storage.sh`: PASS; known `reports/m4b-docker-containerd-install.md` side effect was restored.
- `scripts/nvidia/verify-gpu-containers.sh`: PASS with `nvidia/cuda:13.2.1-base-ubuntu24.04`.
- `scripts/llmctl validate`: PASS with 7 model profiles and 4 runtime profiles.
- `scripts/llmctl active`: PASS; smoke active and healthy.
- `scripts/llmctl status`: PASS; manager active.
- `scripts/sglang/verify-sglang-lifecycle.sh`: PASS.
- `git diff --check`: PASS.

Secret scan:

- Broad grep matched intentional documentation, static-test scanner patterns, safety strings, prior report text, and env-example comments.
- Changed-file strict scan matched only the new scanner expressions in `scripts/sglang/verify-sglang-real-fast-plan.sh` and `tests/shell/test-sglang-real-fast-static.sh`.
- No real secret, token, password, private key, auth file, real `.env`, local sudo helper, `MEMORY.md`, or local Codex memory content was identified.

## PASS/STOP Conclusion

PASS for planning only.

STOP for actual download/deployment until human review.

Next recommended task: human review, then M9B actual first real fast-model deployment.
