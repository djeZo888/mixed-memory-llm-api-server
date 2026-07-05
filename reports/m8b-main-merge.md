# M8B Main Merge Report

- Timestamp: `2026-07-05T06:36:37Z`
- Source branch: `milestone/m8b-sglang-smoke-deploy`
- Target branch: `main`
- Merge commit hash: `2330b8b432243cea6ddc6effc1fb60065d7d1759`
- M8B source commit hash: `e204955f9268a2124f0590c80a30e1f0ad8b6fa2`
- Result: PASS. M8B was merged into `main`, and the live localhost-only SGLang smoke deployment remained healthy during validation.

## Runtime Image Failure And Remediation

- Initial runtime image: `lmsysorg/sglang:v0.5.14-cu130-runtime`
- Initial failure: `ModuleNotFoundError: No module named 'distro'` during SGLang startup through the OpenAI protocol import path.
- Reviewed remediation: switch the smoke deployment to the full CUDA 13.0 image `lmsysorg/sglang:v0.5.14-cu130`.
- Working image: `lmsysorg/sglang:v0.5.14-cu130`
- Verified linux/amd64 manifest digest: `sha256:9611bd4c5624b0e9e17829506188a12f17205f2083de0dd44d6c521733553a50`
- Import/dependency gate on the full image: PASS for `distro`, `openai`, and `sglang.srt.entrypoints.openai.protocol`.
- The runtime image remains rejected for this smoke path until the missing dependency issue is fixed upstream and re-verified.

## Active Smoke Deployment

- Model/backend: `qwen3-0.6b-smoke` on SGLang.
- Model path: `/data/models/qwen3-0.6b-smoke`
- Model size: `1.5G`
- Container: `sglang-smoke-qwen3-0.6b`
- Container status during merge validation: `Up 10 hours (healthy)`.
- Endpoint: `http://127.0.0.1:30000/v1`
- Host bind: `127.0.0.1:30000` only.
- Runtime compose file: `/data/services/llm-manager/compose/sglang-smoke.compose.yml`
- Active state file: `/data/services/llm-manager/active/active.json`

## Live Validation Results

- `scripts/common/require-data-mounted.sh`: PASS.
- `scripts/common/root-disk-guard.sh --report reports/m3-root-disk-guard.md`: PASS.
- `scripts/docker/verify-docker-storage.sh`: PASS.
- `scripts/nvidia/verify-gpu-containers.sh`: PASS with `nvidia/cuda:13.2.1-base-ubuntu24.04`.
- `scripts/llmctl validate`: PASS during pre-merge validation.
- `scripts/llmctl active`: active smoke backend reported.
- `scripts/llmctl status`: `manager_status: active`.
- `scripts/llmctl logs --dry-run`: PASS during pre-merge validation.
- `scripts/sglang/verify-sglang-smoke-live.sh`: PASS.
- `scripts/api/smoke-openai-chat.sh --yes-run-smoke-api`: PASS.
- Direct `/v1/models`: PASS; returned model id `qwen3-0.6b-smoke` with `max_model_len` `40960`.
- Direct bind check: PASS; `ss` showed `127.0.0.1:30000` listening and no public host bind.
- Non-streaming chat smoke: PASS; HTTP 200, JSON parsed, and `choices[0].message.content` was non-empty.
- Streaming chat smoke: PASS; HTTP 200, SSE chunks received, and stream completed with `[DONE]`.
- `git diff --check`: PASS before merge.
- Grep-based secret scan: PASS. Matches were limited to intentional docs, tests, report text, safety strings, and scanner patterns; no real secret, token, password, private key, auth file, real `.env`, `MEMORY.md`, local Codex memory file, or sudo helper content was identified.

## Storage And GPU State

- `/data`: mounted from `/dev/sdb1`, ext4, label `AI_DATA`, UUID `8daf56f1-5649-4163-9d87-919c2d271875`.
- Docker Root Dir: `/data/docker`.
- Docker storage driver: `overlayfs`.
- Docker default runtime: `runc`; NVIDIA runtime is available.
- containerd root/state: `/data/containerd/root` / `/run/containerd`.
- `/var/lib/docker`: absent from disk-usage output.
- `/var/lib/containerd`: absent from disk-usage output.
- Docker system df after validation: images `69.75GB`, containers `170.3MB`, local volumes `0B`, build cache `0B`.
- Disk usage after validation:
  - `/data/docker`: `27G`
  - `/data/containerd`: `66G`
  - `/data/models/qwen3-0.6b-smoke`: `1.5G`
  - `/data/hf-cache`: `208K`
  - `/data/logs/sglang-smoke`: `4.0K`
- GPU verifier summary: two NVIDIA RTX PRO 6000 Blackwell Workstation Edition GPUs, driver `595.71.05`, `97887 MiB` each.

## No-Action Confirmations

- No public API exposure was configured.
- No `0.0.0.0` host bind was configured.
- No first real model was downloaded.
- No additional model was downloaded during merge validation.
- No additional backend image was pulled during merge validation.
- No host SGLang, PyTorch, CUDA Toolkit, KTransformers, vLLM, ik_llama, or unrelated backend install occurred.
- No Docker/containerd daemon configuration was modified.
- Docker/containerd was not restarted.
- No systemd service was created.
- No model files were deleted.

## Warnings

- Manual `docker compose down` will stop the smoke container, but `active.json` may remain stale until M8C implements a reviewed real deactivate flow.
- Keep `lmsysorg/sglang:v0.5.14-cu130-runtime` rejected for smoke until the upstream missing `distro` dependency is fixed and verified.
- Public API exposure, reverse proxy, firewall opening, and authentication remain future work and were not configured in M8B.

## Conclusion

PASS. M8B is merged into `main`; the current active backend is the localhost-only SGLang smoke deployment using `qwen3-0.6b-smoke` and `lmsysorg/sglang:v0.5.14-cu130`.

Next recommended milestone: M8C smoke lifecycle/stop-deactivate policy, or M9A first real fast-model planning after human review.
