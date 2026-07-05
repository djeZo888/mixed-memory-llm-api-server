# M8C Main Merge Report

- Timestamp: `2026-07-05T09:54:30Z`
- Source branch: `milestone/m8c-smoke-lifecycle-manager`
- Target branch: `main`
- Merge commit hash: `88ce5abd478a15a4cb40acbec4268ed2c5745618`
- M8C source commit hash: `fe4e196d21dc5a0bd73fe875f885959bd7a49468`
- Result: PASS. M8C was merged into `main`, and the live SGLang smoke backend remained active, healthy, and localhost-only during validation.

## Lifecycle Commands Implemented

- `scripts/llmctl status`
- `scripts/llmctl active`
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

Mutating lifecycle commands require `--yes`. New model activation remains guarded; `start --yes` is the supported start path for the already deployed smoke profile.

## Final Active Smoke State

- Active model/backend: `qwen3-0.6b-smoke` on SGLang.
- Container: `sglang-smoke-qwen3-0.6b`
- Container status during validation: `Up 3 hours (healthy)`.
- Endpoint: `http://127.0.0.1:30000/v1`
- Bind: `127.0.0.1:30000` only.
- Image: `lmsysorg/sglang:v0.5.14-cu130`
- Model path: `/data/models/qwen3-0.6b-smoke`
- `/v1/models`: PASS and returned `qwen3-0.6b-smoke`.
- Chat smoke: PASS with non-empty response content.

## Validation Summary

- Stop/start/restart lifecycle validation: PASS in M8C branch report.
- Live deactivate: dry-run only during M8C live validation.
- Fixture deactivate: PASS; real deactivate was tested only in temporary fixture state.
- `scripts/common/require-data-mounted.sh`: PASS.
- `scripts/common/root-disk-guard.sh --report reports/m3-root-disk-guard.md`: PASS.
- `scripts/docker/verify-docker-storage.sh`: PASS.
- `scripts/nvidia/verify-gpu-containers.sh`: PASS with `nvidia/cuda:13.2.1-base-ubuntu24.04`.
- `scripts/llmctl validate`: PASS.
- `scripts/llmctl active`: PASS and reported active smoke backend.
- `scripts/llmctl status`: PASS and reported `manager_status: active`.
- `scripts/llmctl logs --dry-run`: PASS and printed the intended `docker logs` command.
- `scripts/sglang/verify-sglang-lifecycle.sh`: PASS.
- `scripts/api/smoke-openai-chat.sh --yes-run-smoke-api`: PASS.
- Lifecycle shell tests: PASS for static and fixture tests.
- `git diff --check`: PASS before merge.

## Secret Scan

The grep-based secret scan matched only intentional documentation, static-test scanner patterns, report text, `.gitignore`/CI safety strings, and historical report strings. No real secrets, tokens, passwords, private keys, auth files, real `.env`, `MEMORY.md`, local Codex memory file, or sudo helper content was identified.

## No-Action Confirmations

- No model was downloaded.
- No Docker image was pulled.
- No package or backend software was installed.
- No Docker/containerd daemon configuration was modified.
- Docker/containerd was not restarted.
- No public API exposure was configured.
- No host `0.0.0.0` bind was configured.
- No systemd service was created.
- No model files were deleted.
- No Docker images were deleted.
- No Docker prune was run.
- No disk, fstab, mountpoint, partitioning, or Proxmox host change occurred.

## Conclusion

PASS. M8C is merged into `main`; the active smoke backend remains `qwen3-0.6b-smoke` on SGLang at `http://127.0.0.1:30000/v1`, bound only to `127.0.0.1`.

Next recommended milestone: M9A first real fast-model planning/dry-run.
