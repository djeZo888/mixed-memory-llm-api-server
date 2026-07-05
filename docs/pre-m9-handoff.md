# Pre-M9 Handoff

- Timestamp: `2026-07-05T06:36:37Z`
- Latest main commit after M8B merge: `2330b8b432243cea6ddc6effc1fb60065d7d1759`
- M8B source commit: `e204955f9268a2124f0590c80a30e1f0ad8b6fa2`
- Active model/backend: `qwen3-0.6b-smoke` on SGLang.
- Endpoint: `http://127.0.0.1:30000/v1`
- Bind: `127.0.0.1:30000` only.
- Image: `lmsysorg/sglang:v0.5.14-cu130`
- Verified linux/amd64 manifest digest: `sha256:9611bd4c5624b0e9e17829506188a12f17205f2083de0dd44d6c521733553a50`
- Model path: `/data/models/qwen3-0.6b-smoke`
- Model size: `1.5G`
- Container: `sglang-smoke-qwen3-0.6b` (`healthy` during merge validation).
- Public API exposure: not configured.
- First real model: not downloaded.
- M8C lifecycle manager: merged into `main` with merge commit `88ce5abd478a15a4cb40acbec4268ed2c5745618`.
- M8C main merge report: `reports/m8c-main-merge.md`.
- Final lifecycle state after M8C validation: active and healthy.

## Active Smoke Deployment Summary

M8B deployed the small `Qwen/Qwen3-0.6B` smoke model behind a localhost-only SGLang OpenAI-compatible endpoint. The first runtime-image attempt failed with `ModuleNotFoundError: No module named 'distro'`; human review approved switching to the full `lmsysorg/sglang:v0.5.14-cu130` image, whose required import gate and live API smoke tests passed.

## Manual Local Tests

List models:

```bash
curl -fsS http://127.0.0.1:30000/v1/models
```

Run a non-streaming chat smoke request:

```bash
curl -fsS http://127.0.0.1:30000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"qwen3-0.6b-smoke","messages":[{"role":"system","content":"You are a smoke test assistant."},{"role":"user","content":"Reply with a short confirmation that the smoke test works."}],"max_tokens":64,"temperature":0}'
```

Inspect the container:

```bash
sudo -n docker ps --filter name=sglang-smoke-qwen3-0.6b
sudo -n docker logs --tail 200 sglang-smoke-qwen3-0.6b
```

## Manual Stop Command

Prefer the reviewed M8C lifecycle commands:

```bash
scripts/llmctl status
scripts/llmctl active
scripts/llmctl logs --dry-run
scripts/llmctl logs --yes
scripts/llmctl stop --dry-run
scripts/llmctl stop --yes
scripts/llmctl start --dry-run
scripts/llmctl start --yes
scripts/llmctl restart --dry-run
scripts/llmctl restart --yes
scripts/llmctl deactivate --dry-run
```

`stop --yes` stops the smoke container but keeps the smoke deployment selected in `active.json`. `start --yes` starts that existing deployment again. `restart --yes` performs a guarded stop/start cycle. `deactivate --yes` archives `active.json` and leaves no active backend; test it only when the service should no longer be active.

Manual Docker commands can make `/data/services/llm-manager/active/active.json` stale. Use `scripts/llmctl status` or `scripts/sglang/verify-sglang-lifecycle.sh` to detect stale state.

## Next Decision

Proceed to M9A first real fast-model planning/dry-run. M9A should compare first real fast-model candidates, define storage/runtime/image/digest/download/benchmark/rollback plans, and keep all actual model downloads and backend image pulls blocked. Do not download the first real model in M9A.
