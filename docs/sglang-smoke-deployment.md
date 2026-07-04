# SGLang Smoke Deployment Plan

## M8B Attempt Result

M8B was attempted on branch `milestone/m8b-sglang-smoke-deploy` and stopped before readiness. The linux/amd64 digest for `lmsysorg/sglang:v0.5.14-cu130-runtime` was re-verified as `sha256:344f361284ba3514d0c93fb7c810f4cdbf89c789117cb51ebea8497d2c8ed101`, the image was pulled, and `Qwen/Qwen3-0.6B` was downloaded to `/data/models/qwen3-0.6b-smoke`.

The container `sglang-smoke-qwen3-0.6b` exited during startup with `ModuleNotFoundError: No module named 'distro'` from the pinned image Python environment. No active manager state was written, no API smoke request was sent, and no public or localhost API endpoint remained running. The failed container is left exited for diagnostics; the model files remain under `/data/models/qwen3-0.6b-smoke`.

Human review is required before retrying M8B with a reviewed remediation path, such as a different pinned SGLang image digest or a reviewed derivative image. Do not hot-patch the running container or install host packages as an unreviewed workaround.

M8A defines the planned SGLang smoke deployment for `Qwen/Qwen3-0.6B`. It is planning and dry-run only. It does not download model weights, pull Docker images, start containers, install backend software, expose an API, create services, restart Docker/containerd, or change Docker/containerd configuration.

## Purpose

The smoke deployment proves the manager, storage policy, Docker GPU runtime, local-only binding, logs, and OpenAI-compatible chat endpoint before any larger model work. It is not a quality benchmark.

## Model Choice

`Qwen/Qwen3-0.6B` is the first smoke model because it is small enough to validate the path with low storage and memory risk while still using the Qwen3 chat template and reasoning/non-thinking behavior that later Qwen profiles will need. The M7B profile name is `qwen3-0.6b-smoke` and the planned local path is `/data/models/qwen3-0.6b-smoke`.

The Hugging Face model card identifies the model as Apache-2.0 licensed, a causal language model, 0.6B parameters with 0.44B non-embedding parameters, 28 layers, BF16 safetensors, and 32,768 context length. The card also documents SGLang serving with `python3 -m sglang.launch_server`, port `30000`, and OpenAI-compatible chat completions.

## Runtime Choice

SGLang is the first backend because M7A/M7B selected it as the preferred smoke and 30B-class OpenAI-compatible runtime. It supports Docker deployment and an OpenAI-compatible API. KTransformers remains the later heterogeneous RAM/VRAM path for large MoE experiments; vLLM remains the cross-check runtime; ik_llama remains a quantized/GGUF fallback.

## API Endpoint Plan

M8B should expose only the local backend endpoint:

```text
http://127.0.0.1:30000/v1/chat/completions
```

No public, LAN, or wildcard API exposure is part of M8A or M8B. A later milestone must review authentication, firewall, and TLS policy before external exposure.

## Binding Policy

The host-side Compose port binding must stay:

```text
127.0.0.1:30000:30000
```

The SGLang process may use `--host 0.0.0.0` inside the container so Docker can forward traffic from the localhost-only host binding. The host must not publish `0.0.0.0:30000` or bare `30000:30000`.

## Storage Policy

Model weights must be downloaded only after M8B approval and only to:

```text
/data/models/qwen3-0.6b-smoke
```

SGLang must use that local path at runtime. M8B must not rely on SGLang auto-downloading from Hugging Face on first launch.

Hugging Face and application caches stay under `/data/hf-cache`:

```text
HF_HOME=/data/hf-cache
HF_HUB_CACHE=/data/hf-cache/hub
HF_XET_CACHE=/data/hf-cache/xet
HF_ASSETS_CACHE=/data/hf-cache/assets
HF_DATASETS_CACHE=/data/hf-cache/datasets
TRANSFORMERS_CACHE=/data/hf-cache/transformers
XDG_CACHE_HOME=/data/hf-cache/xdg
```

Logs stay under `/data/logs/sglang-smoke`. Docker persistent storage must remain `/data/docker`; containerd persistent root must remain `/data/containerd/root`.

## Prerequisites

Before M8B performs any real action, rerun:

```bash
scripts/common/require-data-mounted.sh
scripts/common/root-disk-guard.sh
scripts/docker/verify-docker-storage.sh
scripts/nvidia/verify-gpu-containers.sh
scripts/llmctl validate
scripts/llmctl active
scripts/sglang/plan-sglang-smoke.sh --dry-run
scripts/sglang/verify-sglang-smoke-plan.sh
```

M8B must stop if `/data` is not mounted, Docker Root Dir is not `/data/docker`, the NVIDIA Docker runtime is unavailable, the GPU container verifier fails, an active model/backend exists, or port `30000` is already listening.

## Image Policy

Do not use `lmsysorg/sglang:latest` or `lmsysorg/sglang:latest-runtime`.

M8A proposes this pinned image for M8B after human review:

```text
lmsysorg/sglang:v0.5.14-cu130-runtime
```

Docker Hub listed this tag on 2026-07-04 with linux/amd64 digest `sha256:344f361284ba3514d0c93fb7c810f4cdbf89c789117cb51ebea8497d2c8ed101`. SGLang documentation states Docker images are published under `lmsysorg/sglang`, runtime variants are smaller, and CUDA 13 is the default SGLang environment. NVIDIA CUDA release notes list CUDA 13.x minor-version compatibility as requiring driver `>= 580`, and CUDA 13.0 GA as requiring Linux driver `>=580.65.06`; this VM has driver `595.71.05`.

M8B must still verify the image by pulling only after human approval, then recording the digest actually pulled.

## M8A Boundary

M8A creates only templates, dry-run scripts, docs, tests, and a report. It performs no model download, SGLang image pull, SGLang container run, backend install, API exposure, service creation, Docker/containerd restart, or Docker/containerd config change.

## Planned M8B Steps

1. Re-run all guards and the M8A plan verifier.
2. Create `/data/models/qwen3-0.6b-smoke`.
3. Download `Qwen/Qwen3-0.6B` to that local model path with Hugging Face cache under `/data/hf-cache`.
4. Pull the approved pinned SGLang image.
5. Start the `sglang-smoke` Compose profile on `127.0.0.1:30000`.
6. Wait for readiness using `/health` if supported by the selected image, and confirm readiness logs otherwise.
7. Run `scripts/api/smoke-openai-chat.sh --yes-run-smoke-api` locally.
8. Run a streaming chat-completions smoke request if supported.
9. Record logs under `/data/logs/sglang-smoke`.
10. Stop/deactivate cleanly and rerun the root-disk guard.

## Rollback And Cleanup

Stop the Compose profile and remove only the smoke container. Keep downloaded model files unless the human explicitly approves deletion. Preserve `/data/models`, `/data/hf-cache`, `/data/logs`, `/data/docker`, and `/data/containerd`. After cleanup, rerun `scripts/common/root-disk-guard.sh` and `scripts/docker/verify-docker-storage.sh`.

## Security Note

M8 keeps the backend local. Public API exposure, LAN binding, API keys, TLS, firewall changes, and a front-door service are later milestones, not M8A or M8B.

## Local Operations Reference

After a successful future retry, query the local OpenAI-compatible endpoint with:

```bash
curl -fsS http://127.0.0.1:30000/v1/models
scripts/api/smoke-openai-chat.sh --yes-run-smoke-api
```

Inspect the failed or future smoke container with:

```bash
sudo -n docker ps -a --filter name=sglang-smoke-qwen3-0.6b
sudo -n docker logs --tail 200 sglang-smoke-qwen3-0.6b
```

A later reviewed stop/deactivate task can stop the runtime with:

```bash
sudo -n docker compose -f /data/services/llm-manager/compose/sglang-smoke.compose.yml --profile sglang-smoke down
```

Public exposure is still not configured. Do not add Caddy, reverse proxy, firewall changes, TLS, LAN/public binds, or API keys in M8B.

## Sources

- SGLang installation and Docker docs: https://docs.sglang.io/docs/get-started/install
- SGLang quickstart and OpenAI-compatible API: https://docs.sglang.io/docs/get-started/quickstart
- Qwen SGLang deployment docs: https://qwen.readthedocs.io/en/latest/deployment/sglang.html
- Qwen/Qwen3-0.6B model card: https://huggingface.co/Qwen/Qwen3-0.6B
- Docker Compose profiles docs: https://docs.docker.com/compose/how-tos/profiles/
- Docker Hub SGLang tags: https://hub.docker.com/r/lmsysorg/sglang/tags
- NVIDIA CUDA release notes: https://docs.nvidia.com/cuda/cuda-toolkit-release-notes/index.html
