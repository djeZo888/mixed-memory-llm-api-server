# M8B SGLang Smoke Deployment Report

- Milestone ID: M8B
- Timestamp: `2026-07-04T17:17:02Z`
- Branch: `milestone/m8b-sglang-smoke-deploy`
- Base branch: `main`
- Repository: `git@github.com:djeZo888/mixed-memory-llm-api-server.git`
- Repo path: `/data/services/mixed-memory-llm-api-server`
- Conclusion: STOP. The reviewed image tag and smoke model were prepared, but the SGLang container exited during Python import before readiness.

## Baseline

- Latest base commit before M8B branch: `c7ede29f8a84ef6cbaf035b13abd3f3b85d5737a`
- Git identity: `CodexAIagent <133749519+djeZo888@users.noreply.github.com>`
- `/data`: mounted from `/dev/sdb1`, ext4, label `AI_DATA`, UUID `8daf56f1-5649-4163-9d87-919c2d271875`
- Docker Root Dir: `/data/docker`
- Docker storage driver: `overlayfs` through `io.containerd.snapshotter.v1`
- Docker runtimes: `runc`, `io.containerd.runc.v2`, `nvidia`
- Docker default runtime: `runc`
- containerd root/state: `/data/containerd/root` / `/run/containerd`
- NVIDIA driver: `595.71.05`
- GPUs: 2 x NVIDIA RTX PRO 6000 Blackwell Workstation Edition, `97887 MiB` each
- Active model/backend before deployment: `active: none`
- Manager state before deployment: `planning_only`
- Port `30000` before deployment: not listening

## Scope

- Smoke model: `Qwen/Qwen3-0.6B`
- Model profile: `qwen3-0.6b-smoke`
- Runtime profile: `sglang`
- Planned local model path: `/data/models/qwen3-0.6b-smoke`
- Planned endpoint: `http://127.0.0.1:30000/v1`
- Planned chat endpoint: `http://127.0.0.1:30000/v1/chat/completions`
- Planned host bind: `127.0.0.1:30000`
- No public API exposure was configured.
- M8B did not install host SGLang, PyTorch, CUDA Toolkit, KTransformers, vLLM, ik_llama, or other host backend software.
- M8B did not modify Docker/containerd daemon configuration and did not restart Docker/containerd.
- M8B did not create systemd services, reverse proxy, front door, firewall rules, or API auth.

## Image Digest Verification

- Image tag: `lmsysorg/sglang:v0.5.14-cu130-runtime`
- M8A recorded linux/amd64 digest: `sha256:344f361284ba3514d0c93fb7c810f4cdbf89c789117cb51ebea8497d2c8ed101`
- M8B verification method: `sudo -n docker buildx imagetools inspect lmsysorg/sglang:v0.5.14-cu130-runtime`
- M8B observed linux/amd64 digest: `sha256:344f361284ba3514d0c93fb7c810f4cdbf89c789117cb51ebea8497d2c8ed101`
- Result: PASS. The linux/amd64 digest matched before pull/run.

## Image Pull

- Command: `sudo -n docker pull --platform linux/amd64 lmsysorg/sglang:v0.5.14-cu130-runtime`
- Result: pulled successfully.
- Pulled tag/index digest reported by Docker: `sha256:9e436f44523e9f53519c6175fefd1e0d373322bf54b8154bb331a2f5e4840ad2`
- Image ID: `sha256:9e436f44523e9f53519c6175fefd1e0d373322bf54b8154bb331a2f5e4840ad2`
- Repo digest: `lmsysorg/sglang@sha256:9e436f44523e9f53519c6175fefd1e0d373322bf54b8154bb331a2f5e4840ad2`
- Architecture/OS: `amd64` / `linux`
- Created: `2026-06-26T03:09:14.515561204Z`
- Size: `12177739292` bytes

## Model Download

- Method: helper container using the already-pulled SGLang image.
- Host packages installed: none.
- Token usage: no `HF_TOKEN` used.
- Environment/cache roots:
  - `HOME=/data/hf-cache/home`
  - `HF_HOME=/data/hf-cache`
  - `HF_HUB_CACHE=/data/hf-cache/hub`
  - `HF_XET_CACHE=/data/hf-cache/xet`
  - `HF_ASSETS_CACHE=/data/hf-cache/assets`
  - `HF_DATASETS_CACHE=/data/hf-cache/datasets`
  - `TRANSFORMERS_CACHE=/data/hf-cache/transformers`
  - `XDG_CACHE_HOME=/data/hf-cache/xdg`
- Download target: `/data/models/qwen3-0.6b-smoke`
- Download result: PASS.
- Downloaded size: `1.5G`
- Root cache check after download: `/home/user/.cache` was `4.0K`; `/root/.cache`, `/var/lib/docker`, and `/var/lib/containerd` did not appear in the disk-usage output.

Downloaded top-level files:

```text
.gitattributes
LICENSE
README.md
config.json
generation_config.json
merges.txt
model.safetensors
tokenizer.json
tokenizer_config.json
vocab.json
```

## Compose Runtime File

- Runtime compose file: `/data/services/llm-manager/compose/sglang-smoke.compose.yml`
- Git-tracked: no.
- Image: `lmsysorg/sglang:v0.5.14-cu130-runtime`
- Container name: `sglang-smoke-qwen3-0.6b`
- Restart policy: `no`
- Host bind: `127.0.0.1:30000:30000`
- Public host bind check: PASS, no `0.0.0.0:30000:30000` host bind.
- Rendered Compose config showed `host_ip: 127.0.0.1`.
- Model mount: `/data/models:/data/models:ro`
- Cache mount: `/data/hf-cache:/data/hf-cache`
- Log mount: `/data/logs:/data/logs`
- GPU access: Compose device reservation with `driver: nvidia`, `count: all`, `capabilities: [gpu]`

## Startup Result

- Start command: `sudo -n docker compose -f /data/services/llm-manager/compose/sglang-smoke.compose.yml --profile sglang-smoke up -d`
- Container creation/start: completed.
- Readiness result: STOP.
- Container status after start: `Exited (1)`
- Port `30000` after failure: not listening.
- `/health`: not reached.
- `/v1/models`: not reached.

Failure log excerpt:

```text
Traceback (most recent call last):
  File "<frozen runpy>", line 198, in _run_module_as_main
  File "<frozen runpy>", line 88, in _run_code
  File "/sgl-workspace/sglang/python/sglang/launch_server.py", line 8, in <module>
    from sglang.srt.server_args import prepare_server_args
  File "/sgl-workspace/sglang/python/sglang/srt/server_args.py", line 49, in <module>
    from sglang.srt.function_call.function_call_parser import FunctionCallParser
  File "/sgl-workspace/sglang/python/sglang/srt/function_call/function_call_parser.py", line 4, in <module>
    from sglang.srt.entrypoints.openai.protocol import (
  File "/sgl-workspace/sglang/python/sglang/srt/entrypoints/openai/protocol.py", line 36, in <module>
    from openai.types.responses import (
  File "/usr/local/lib/python3.12/dist-packages/openai/__init__.py", line 12, in <module>
    from ._client import Client, OpenAI, Stream, Timeout, Transport, AsyncClient, AsyncOpenAI, AsyncStream, RequestOptions
  File "/usr/local/lib/python3.12/dist-packages/openai/_client.py", line 32, in <module>
    from ._base_client import (
  File "/usr/local/lib/python3.12/dist-packages/openai/_base_client.py", line 36, in <module>
    import distro
ModuleNotFoundError: No module named 'distro'
```

## API Smoke Tests

- Non-streaming chat smoke: NOT RUN because startup hit the STOP condition.
- Streaming chat smoke: NOT RUN because startup hit the STOP condition.
- `scripts/api/smoke-openai-chat.sh --yes-run-smoke-api`: NOT RUN after STOP.
- No API request was sent to a live backend.

## Active State

- `/data/services/llm-manager/active/active.json`: not created or updated.
- `scripts/llmctl active`: `active: none`
- Active model/backend after STOP: none.

## Guard Results After STOP

- `scripts/common/require-data-mounted.sh`: PASS
- `scripts/common/root-disk-guard.sh --report reports/m3-root-disk-guard.md`: PASS
- `scripts/docker/verify-docker-storage.sh`: PASS
- `scripts/nvidia/verify-gpu-containers.sh`: PASS with `nvidia/cuda:13.2.1-base-ubuntu24.04`

Disk usage after STOP:

```text
Images: 38.93GB
Containers: 99.35MB
/data/docker: 296K
/data/containerd: 37G
/data/models/qwen3-0.6b-smoke: 1.5G
/data/hf-cache: 208K
/data/logs/sglang-smoke: 4.0K
```

## Warnings

- The selected pinned SGLang image starts far enough to import SGLang, but exits because the Python dependency `distro` is missing from the image environment.
- The failed container is left exited as diagnostic evidence. It did not bind a live host port.
- The smoke model files remain under `/data/models/qwen3-0.6b-smoke`.
- A future retry should use a reviewed remediation path, such as a different pinned SGLang image digest or a reviewed derivative image. Do not hot-patch the running container or install host packages as an unreviewed workaround.

## Checks And Secret Scan

- Shell syntax/static checks: PASS for `scripts/sglang/plan-sglang-smoke.sh`, `scripts/sglang/verify-sglang-smoke-plan.sh`, `scripts/api/smoke-openai-chat.sh`, and `tests/shell/test-sglang-smoke-static.sh`.
- `tests/shell/test-sglang-smoke-static.sh`: PASS.
- `scripts/sglang/plan-sglang-smoke.sh --dry-run`: PASS.
- `scripts/sglang/verify-sglang-smoke-plan.sh`: PASS.
- `scripts/api/smoke-openai-chat.sh --dry-run`: PASS; no API request sent.
- `scripts/llmctl validate`: PASS.
- `scripts/llmctl active`: `active: none`.
- `scripts/llmctl status`: `planning_only`, `active: none`.
- `git diff --check`: PASS.
- Grep-based secret scan: the broad scan matched only intentional docs, tests, sanitizer patterns, prior reports, and safety strings. The changed-file scan matched only the intentional report statement that no `HF_TOKEN` was used. No real secrets, tokens, passwords, private keys, auth files, real `.env`, `MEMORY.md`, local Codex memory file, or sudo helper content was identified.

## No-Action Confirmations

- No public API exposure was configured.
- No `0.0.0.0` host bind was configured.
- No first real model was downloaded.
- No Qwen3-30B or larger model was downloaded.
- No unrelated backend image was pulled.
- No host SGLang, PyTorch, CUDA Toolkit, KTransformers, vLLM, ik_llama, or other backend install occurred.
- No Docker/containerd daemon configuration was modified.
- Docker/containerd was not restarted.
- No systemd service was created.
- No Proxmox host, disk partition, fstab, or mountpoint change occurred.

## Result

STOP.

M8B did not complete the live localhost API smoke deployment. Human review is required before retrying with a remediated runtime image/dependency path.
