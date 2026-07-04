# M8A SGLang Smoke-Model Deployment Plan

- Milestone ID: M8A
- Timestamp: 2026-07-04T14:45:00Z
- Branch: `milestone/m8a-sglang-smoke-plan`
- Base branch: `main`
- Repository: `git@github.com:djeZo888/mixed-memory-llm-api-server.git`
- Repo path: `/data/services/mixed-memory-llm-api-server`
- Conclusion: PASS for planning/dry-run; STOP for runtime action until human review approves M8B.

## System Baseline

- VM: `ai-vm / 10.156.100.60`
- Hostname: `llmserver`
- `/data`: mounted from `/dev/sdb1`, ext4, label `AI_DATA`, UUID `8daf56f1-5649-4163-9d87-919c2d271875`
- Docker Root Dir: `/data/docker`
- containerd root/state: `/data/containerd/root` / `/run/containerd`
- NVIDIA driver: `595.71.05`
- NVIDIA Container Toolkit: installed; Docker runtimes include `nvidia`; default runtime remains `runc`
- GPUs: 2 x NVIDIA RTX PRO 6000 Blackwell Workstation Edition, `97887 MiB` each
- Host CUDA Toolkit/nvcc: absent
- Model manager state: `planning_only`, `active: none`

## Baseline Checks

| Check | Result |
| --- | --- |
| `scripts/common/require-data-mounted.sh` | PASS |
| `scripts/common/root-disk-guard.sh --report reports/m3-root-disk-guard.md` | PASS |
| `scripts/docker/verify-docker-storage.sh` | PASS |
| `scripts/nvidia/verify-gpu-containers.sh` | PASS with `nvidia/cuda:13.2.1-base-ubuntu24.04` |
| `scripts/llmctl doctor` | PASS |
| `scripts/llmctl validate` | PASS: 5 model profiles, 4 runtime profiles |
| `scripts/llmctl active` | `active: none` |
| `scripts/llmctl show-model qwen3-0.6b-smoke` | PASS |
| `scripts/llmctl show-runtime sglang` | PASS |
| `scripts/llmctl plan-download qwen3-0.6b-smoke` | planned only, no download |
| `scripts/llmctl plan-activate qwen3-0.6b-smoke --runtime sglang` | planned only |
| `scripts/llmctl activate qwen3-0.6b-smoke --runtime sglang --dry-run` | dry-run only, no state written |
| `sudo -n docker info` storage/runtime summary | PASS: Docker Root Dir `/data/docker`, runtimes include `nvidia` |
| `nvidia-smi -L` | PASS: exactly two expected Blackwell GPUs |

## Qwen/Qwen3-0.6B Facts

Source: https://huggingface.co/Qwen/Qwen3-0.6B

- License: Apache-2.0.
- Model type: causal language model.
- Parameters: 0.6B listed in the model overview; Hugging Face file metadata reports 0.8B params for stored weights.
- Non-embedding parameters: 0.44B.
- Layers: 28.
- Attention heads: 16 Q heads and 8 KV heads.
- Context length: 32,768.
- Tensor type: BF16 safetensors.
- Qwen3 supports thinking and non-thinking behavior; smoke prompts should be short and deterministic, and M8B should record whether thinking markup appears.
- The card documents SGLang serving with `python3 -m sglang.launch_server`, `--model-path Qwen/Qwen3-0.6B`, `--host 0.0.0.0`, `--port 30000`, and `/v1/chat/completions`.

## SGLang Deployment Facts

Sources:

- https://docs.sglang.io/docs/get-started/install
- https://docs.sglang.io/docs/get-started/quickstart
- https://qwen.readthedocs.io/en/latest/deployment/sglang.html

Findings:

- SGLang publishes Docker images under `lmsysorg/sglang`.
- Official docs show `python3 -m sglang.launch_server --model-path ... --host 0.0.0.0 --port 30000`.
- SGLang is OpenAI API-compatible and supports `/v1/chat/completions` on the selected host/port.
- Qwen docs state the API service defaults to `http://localhost:30000` and can be configured with `--host` and `--port`.
- Qwen docs warn that if `--model-path` is not a valid local directory, SGLang downloads from Hugging Face. M8B must therefore launch from `/data/models/qwen3-0.6b-smoke` after an explicit approved download.

## Docker Compose Profile Facts

Source: https://docs.docker.com/compose/how-tos/profiles/

Docker Compose profiles allow services to be activated selectively. The smoke template uses profile `sglang-smoke` so M8B can start only this backend profile after review.

## SGLang Image Tag Decision

Proposed pinned M8B image:

```text
lmsysorg/sglang:v0.5.14-cu130-runtime
```

Source: Docker Hub SGLang tags page and Docker Hub tag API query on 2026-07-04.

- Docker Hub tag: `v0.5.14-cu130-runtime`
- Last updated: `2026-06-26T03:22:04.294209Z`
- linux/amd64 digest: `sha256:344f361284ba3514d0c93fb7c810f4cdbf89c789117cb51ebea8497d2c8ed101`
- linux/amd64 compressed size: about 12.18 GB
- Reason: pinned version, CUDA 13.0 variant, runtime image, not `latest`.

Compatibility note: NVIDIA CUDA release notes list CUDA 13.x minor-version compatibility as driver `>= 580`, and CUDA 13.0 GA as Linux driver `>=580.65.06`. This VM has driver `595.71.05`, so the CUDA 13.0 runtime tag is compatible by published minimum-driver policy. M8B must still record the actual digest pulled.

## Compose Template Summary

File: `configs/compose/compose.sglang-smoke.template.yml`

- Template only; not run in M8A.
- Image: `${SGLANG_IMAGE_TAG}`, with documentation proposing `lmsysorg/sglang:v0.5.14-cu130-runtime` for human-approved M8B.
- Profile: `sglang-smoke`.
- Host binding: `127.0.0.1:30000:30000` only.
- Container launch host: `0.0.0.0` inside the container only, behind localhost-only Docker port publishing.
- Model path: `/data/models/qwen3-0.6b-smoke`.
- Mounts: `/data/models`, `/data/hf-cache`, `/data/logs`.
- Cache environment variables all point under `/data/hf-cache`.
- Healthcheck: `http://127.0.0.1:30000/health`, pending M8B image verification.

## Manager Integration Summary

- Model profile: `qwen3-0.6b-smoke`.
- Runtime profile: `sglang`.
- `scripts/llmctl validate` passes.
- `scripts/llmctl active` reports `active: none`.
- `scripts/llmctl plan-download qwen3-0.6b-smoke` plans `/data/models` with `/data/hf-cache` and performs no download.
- `scripts/llmctl activate qwen3-0.6b-smoke --runtime sglang --dry-run` performs no activation and writes no state.
- M8A adds `scripts/sglang/plan-sglang-smoke.sh --dry-run` for the smoke-specific 127.0.0.1:30000 plan.

## Planned M8B Steps

1. Re-run `/data`, root-disk, Docker storage, GPU container, and `llmctl` checks.
2. Confirm no active model/backend and no port `30000` listener.
3. Create `/data/models/qwen3-0.6b-smoke`.
4. Download `Qwen/Qwen3-0.6B` only to `/data/models/qwen3-0.6b-smoke` with cache under `/data/hf-cache`.
5. Pull `lmsysorg/sglang:v0.5.14-cu130-runtime` after human approval and record the pulled digest.
6. Start Docker Compose profile `sglang-smoke` with `127.0.0.1:30000:30000`.
7. Wait for readiness using `/health` if supported; otherwise record the readiness log signal.
8. Run local `/v1/chat/completions` smoke request.
9. Run streaming chat-completions smoke request if supported.
10. Record logs under `/data/logs/sglang-smoke`.
11. Stop/deactivate cleanly.
12. Rerun root-disk guard and Docker storage verification.

## Planned M8B Tests

- Docker image pull of the pinned tag.
- Model download to `/data/models/qwen3-0.6b-smoke` only.
- Backend starts on `127.0.0.1:30000` only.
- Readiness/health check.
- `/v1/chat/completions` non-streaming smoke request.
- Streaming smoke request if supported.
- Stop/deactivate and confirm `llmctl active` returns none.
- Root-disk guard after model/runtime activity.

## Risks

- SGLang image compatibility: pinned CUDA 13.0 runtime tag is compatible by driver policy, but M8B must still validate actual runtime behavior on Blackwell.
- Qwen thinking/non-thinking behavior: smoke prompt should record whether `<think>` markup appears and may use `/no_think` if deterministic concise output is needed.
- Accidental auto-download: launching SGLang with `Qwen/Qwen3-0.6B` instead of `/data/models/qwen3-0.6b-smoke` would download at startup; M8B must use the local path only.
- Port conflict: M8B must stop if `127.0.0.1:30000` is already listening.
- API not authenticated locally: M8B is localhost-only; authenticated external API exposure is a later milestone.

## No-Action Confirmation

M8A did not download models, run `huggingface-cli download`, run `git-lfs download`, pull SGLang Docker images, run SGLang/model/backend containers, install backend software, modify Docker/containerd config, restart Docker/containerd, create systemd services, or expose an API.

## Secret Scan Result

The grep-based scan matched only intentional documentation, placeholders, static-test/sanitizer patterns, historical report text, and safety strings such as `HF_TOKEN`, `password`, and private-key detection expressions. No real token, password, private key, auth file, real `.env`, local sudo helper, `MEMORY.md`, or local Codex memory file was identified.

## Result

PASS for M8A planning/dry-run.

STOP for M8B runtime actions until human review explicitly approves the actual SGLang smoke deployment.

## Next Task

Human review, then M8B actual SGLang smoke deployment.
