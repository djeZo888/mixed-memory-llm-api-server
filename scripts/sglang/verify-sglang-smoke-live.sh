#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/sglang/verify-sglang-smoke-live.sh [--help]

Read-only live verification for the M8B localhost-only SGLang smoke service.
USAGE
}

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

for arg in "$@"; do
  case "$arg" in
    --help|-h)
      usage
      exit 0
      ;;
    *)
      fail "unknown argument: $arg"
      ;;
  esac
done

container="sglang-smoke-qwen3-0.6b"
active_json="/data/services/llm-manager/active/active.json"
endpoint="http://127.0.0.1:30000/v1"

status="$(sudo -n docker inspect -f '{{.State.Status}}' "$container" 2>/dev/null || true)"
[[ "$status" == "running" ]] || fail "container is not running: ${status:-missing}"

bind_lines="$(ss -H -ltnp | grep ':30000' || true)"
[[ -n "$bind_lines" ]] || fail "port 30000 is not listening"
echo "$bind_lines"
if grep -Eq '(^|[[:space:]])0\.0\.0\.0:30000([[:space:]]|$)|(^|[[:space:]])\[::\]:30000([[:space:]]|$)' <<<"$bind_lines"; then
  fail "public host bind detected"
fi
grep -Eq '127\.0\.0\.1:30000' <<<"$bind_lines" || fail "localhost bind not found"

models_json="$(curl -fsS "$endpoint/models")" || fail "/v1/models request failed"
MODELS_JSON="$models_json" python3 - <<'PY'
import json
import os

data = json.loads(os.environ["MODELS_JSON"])
ids = [item.get("id") for item in data.get("data", [])]
if "qwen3-0.6b-smoke" not in ids:
    raise SystemExit(f"FAIL: qwen3-0.6b-smoke not found in /v1/models: {ids}")
print("PASS: /v1/models includes qwen3-0.6b-smoke")
PY

chat_payload='{"model":"qwen3-0.6b-smoke","messages":[{"role":"system","content":"You are a smoke test assistant."},{"role":"user","content":"Reply with a short confirmation that the smoke test works."}],"max_tokens":64,"temperature":0}'
chat_json="$(curl -fsS -X POST "$endpoint/chat/completions" -H 'Content-Type: application/json' --data "$chat_payload")" || fail "chat completion request failed"
CHAT_JSON="$chat_json" python3 - <<'PY'
import json
import os

data = json.loads(os.environ["CHAT_JSON"])
content = data["choices"][0]["message"]["content"]
if not isinstance(content, str) or not content.strip():
    raise SystemExit("FAIL: empty chat completion content")
print("PASS: chat completion returned non-empty content")
PY

stream_payload='{"model":"qwen3-0.6b-smoke","messages":[{"role":"system","content":"You are a smoke test assistant."},{"role":"user","content":"Reply with a short confirmation that the streaming smoke test works."}],"max_tokens":64,"temperature":0,"stream":true}'
stream_out="$(mktemp)"
trap 'rm -f "$stream_out"' EXIT
curl -fsS -N -X POST "$endpoint/chat/completions" -H 'Content-Type: application/json' --data "$stream_payload" >"$stream_out" || fail "streaming chat request failed"
grep -q '^data: ' "$stream_out" || fail "no SSE data chunks received"
if ! grep -q '^data: \[DONE\]' "$stream_out"; then
  echo "WARN: streaming response did not include explicit [DONE], but curl closed cleanly"
fi
echo "PASS: streaming chat produced SSE data"

[[ -f "$active_json" ]] || fail "active.json missing"
python3 - <<'PY'
import json
from pathlib import Path

path = Path("/data/services/llm-manager/active/active.json")
state = json.loads(path.read_text(encoding="utf-8"))
expected = {
    "model_profile": "qwen3-0.6b-smoke",
    "runtime_profile": "sglang",
    "container_name": "sglang-smoke-qwen3-0.6b",
    "bind": "127.0.0.1",
    "port": 30000,
    "endpoint": "http://127.0.0.1:30000/v1",
    "model_path": "/data/models/qwen3-0.6b-smoke",
    "image": "lmsysorg/sglang:v0.5.14-cu130",
    "status": "active",
}
for key, value in expected.items():
    if state.get(key) != value:
        raise SystemExit(f"FAIL: active.json {key} mismatch: {state.get(key)!r} != {value!r}")
print("PASS: active.json matches SGLang smoke deployment")
PY

scripts/common/root-disk-guard.sh --report /tmp/root-disk-guard-sglang-live.md
scripts/docker/verify-docker-storage.sh

echo "PASS: SGLang smoke live verification passed"
