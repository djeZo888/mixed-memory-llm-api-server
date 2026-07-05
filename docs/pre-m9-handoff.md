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

Use this only when the human explicitly decides to stop the smoke backend:

```bash
sudo -n docker compose -f /data/services/llm-manager/compose/sglang-smoke.compose.yml --profile sglang-smoke down
```

Warning: manual stop may make `/data/services/llm-manager/active/active.json` stale until M8C implements a reviewed real deactivate workflow.

## Next Decision

Choose one:

- M8C lifecycle/deactivate policy, if the smoke backend should have reviewed stop/status semantics.
- M9A first real fast-model planning, after human review confirms M8B should remain merged and the smoke state is acceptable.
