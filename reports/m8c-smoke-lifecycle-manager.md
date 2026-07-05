# M8C Smoke Lifecycle Manager Report

- Milestone ID: M8C
- Timestamp: `2026-07-05T07:18:40Z`
- Branch: `milestone/m8c-smoke-lifecycle-manager`
- Base commit: `892f65c8619205ff33c1c30db593d65a7f228958`
- Repository: `git@github.com:djeZo888/mixed-memory-llm-api-server.git`
- Repo path: `/data/services/mixed-memory-llm-api-server`
- Conclusion: PASS. The SGLang smoke lifecycle manager was implemented, validated through stop/start/restart, and left active and localhost-only.

## Baseline Smoke State

- Container: `sglang-smoke-qwen3-0.6b`
- Baseline status: running and healthy.
- Endpoint: `http://127.0.0.1:30000/v1`
- Bind: `127.0.0.1:30000` only.
- Model/backend: `qwen3-0.6b-smoke` on SGLang.
- Model path: `/data/models/qwen3-0.6b-smoke`
- Model size: `1.5G`
- Image: `lmsysorg/sglang:v0.5.14-cu130`
- Active state: `/data/services/llm-manager/active/active.json`

## Lifecycle Commands Implemented

- `scripts/llmctl active`
- `scripts/llmctl status`
- `scripts/llmctl logs --dry-run`
- `scripts/llmctl logs --yes`
- `scripts/llmctl stop --dry-run`
- `scripts/llmctl stop --yes`
- `scripts/llmctl start --dry-run`
- `scripts/llmctl start --yes`
- `scripts/llmctl restart --dry-run`
- `scripts/llmctl restart --yes`
- `scripts/llmctl deactivate --dry-run`
- `scripts/llmctl deactivate --yes`

Mutating lifecycle commands require `--yes`. Without `--yes`, they stop and print the matching dry-run command. New model activation remains guarded; `start --yes` is the path for the already deployed smoke profile.

## Active State Policy

- `start --yes`: writes `status: active`, `started_at`, and `last_checked_at`.
- `stop --yes`: writes `status: stopped`, `stopped_at`, and `last_checked_at`.
- `restart --yes`: writes `status: active`, `restarted_at`, and `last_checked_at`.
- `deactivate --yes`: moves `active.json` to `/data/services/llm-manager/active/history/active-YYYYMMDD-HHMMSS.json` and leaves no active model.
- `active` and `status` warn when `active.json` is stale, including active state with no running container or stopped state while port `30000` is listening.

## Preflight And Safety Guards

Lifecycle commands validate:

- `/data` is mounted.
- Docker Root Dir is `/data/docker`.
- Docker/containerd storage verifier passes.
- GPU container verifier passes before start/restart.
- Compose file exists.
- Rendered compose config is localhost-only.
- Port `30000` is either free or owned by the expected smoke container.
- Active state matches the M8B smoke deployment.
- Model path still exists.

The lifecycle manager never deletes model files, removes Docker images, or runs Docker prune.

## Controlled Lifecycle Validation

### A. Active Before Cycle

- `scripts/llmctl active`: reported `status: active`, model `qwen3-0.6b-smoke`, runtime `sglang`, endpoint `http://127.0.0.1:30000/v1`.
- `scripts/llmctl status`: reported active manager state and healthy endpoint.
- `scripts/sglang/verify-sglang-lifecycle.sh`: PASS with active state, `/v1/models`, chat completion, localhost-only bind, root-disk guard, Docker storage verifier, and GPU verifier.

### B. Stop

- `scripts/llmctl stop --dry-run`: PASS; printed stop plan and no-delete policy.
- `scripts/llmctl stop --yes`: PASS.
- Container after stop: `Exited (0)`.
- Port `30000`: not listening.
- `active.json`: `status: stopped`, `stopped_at: 2026-07-05T07:15:42Z`.
- Model path after stop: `/data/models/qwen3-0.6b-smoke` still exists.
- Docker image after stop: `lmsysorg/sglang:v0.5.14-cu130` still exists.
- `scripts/sglang/verify-sglang-lifecycle.sh`: PASS in stopped state.

### C. Start

- `scripts/llmctl start --dry-run`: PASS; printed start plan and no-delete policy.
- `scripts/llmctl start --yes`: PASS.
- Container after start: running; Docker health became healthy after the healthcheck settled.
- Port: `127.0.0.1:30000` only.
- `/v1/models`: PASS and returned `qwen3-0.6b-smoke`.
- `scripts/api/smoke-openai-chat.sh --yes-run-smoke-api`: PASS with non-empty chat content.
- `active.json`: `status: active`, `started_at: 2026-07-05T07:16:46Z`.

### D. Restart

- `scripts/llmctl restart --dry-run`: PASS; printed stop/start plan and no-delete policy.
- `scripts/llmctl restart --yes`: PASS.
- Container after restart: running; Docker health became healthy after the healthcheck settled.
- `/v1/models`: PASS and returned `qwen3-0.6b-smoke`.
- `scripts/api/smoke-openai-chat.sh --yes-run-smoke-api`: PASS with non-empty chat content.
- `active.json`: `status: active`, `restarted_at: 2026-07-05T07:17:55Z`.

### E. Deactivate

- Live `scripts/llmctl deactivate --dry-run`: PASS.
- Live real deactivate: not run by design; the smoke service was left active.
- Fixture real deactivate: PASS in `tests/shell/test-llmctl-lifecycle-fixtures.sh`; it archived fake active state under a temporary fixture directory only.

## Final Smoke State

- Container: `sglang-smoke-qwen3-0.6b`
- Final status: running and healthy.
- Final endpoint: `http://127.0.0.1:30000/v1`
- Final bind: `127.0.0.1:30000` only.
- Final active model/backend: `qwen3-0.6b-smoke` on SGLang.
- Final active state: `status: active`.
- `scripts/llmctl logs --yes --tail 20`: PASS and printed recent SGLang logs.

## Guard Results

- `scripts/common/require-data-mounted.sh`: PASS.
- `scripts/common/root-disk-guard.sh --report reports/m3-root-disk-guard.md`: PASS.
- `scripts/docker/verify-docker-storage.sh`: PASS.
- `scripts/nvidia/verify-gpu-containers.sh`: PASS with `nvidia/cuda:13.2.1-base-ubuntu24.04`.
- Docker Root Dir: `/data/docker`.
- containerd root/state: `/data/containerd/root` / `/run/containerd`.

## Tests And Checks

- `bash -n scripts/sglang/verify-sglang-lifecycle.sh`: PASS.
- `bash -n tests/shell/test-llmctl-lifecycle-static.sh`: PASS.
- `bash -n tests/shell/test-llmctl-lifecycle-fixtures.sh`: PASS.
- `tests/shell/test-llmctl-static.sh`: PASS.
- `tests/shell/test-llmctl-fixtures.sh`: PASS.
- `tests/shell/test-llmctl-lifecycle-static.sh`: PASS.
- `tests/shell/test-llmctl-lifecycle-fixtures.sh`: PASS.
- `scripts/llmctl validate`: PASS.
- `scripts/llmctl active`: PASS.
- `scripts/llmctl status`: PASS.
- `scripts/llmctl logs --dry-run`: PASS.
- `scripts/sglang/verify-sglang-lifecycle.sh`: PASS.
- `scripts/api/smoke-openai-chat.sh --yes-run-smoke-api`: PASS.
- `git diff --check`: PASS before commit.

## Secret Scan

The grep-based secret scan matched only intentional docs, tests, report text, safety strings, and scanner patterns. No real secret, token, password, private key, auth file, real `.env`, `MEMORY.md`, local Codex memory file, or sudo helper content was identified.

## No-Action Confirmations

- No model was downloaded.
- No Docker image was pulled.
- No host package was installed.
- No host SGLang, PyTorch, CUDA Toolkit, KTransformers, vLLM, ik_llama, or unrelated backend install occurred.
- No Docker/containerd daemon configuration was modified.
- Docker/containerd was not restarted.
- No public API exposure was configured.
- No host `0.0.0.0` bind was configured.
- No systemd service was created.
- No model files were deleted.
- No Docker images were deleted.
- No Docker prune was run.

## Conclusion

PASS. M8C implemented safe lifecycle management for the already deployed SGLang smoke backend, validated stop/start/restart, verified deactivate dry-run, and left the smoke service active and healthy.

Next recommended milestone: human review and merge M8C into `main`, then M9A first real fast-model planning/dry-run.
