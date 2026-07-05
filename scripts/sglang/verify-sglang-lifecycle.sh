#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/sglang/verify-sglang-lifecycle.sh [--help]

Read-only lifecycle verification for the localhost-only SGLang smoke service.
It validates active.json, live container/port state, local API health when
active, and storage/GPU guards. It never starts, stops, or edits state.
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

active_dir="${LLMCTL_ACTIVE_DIR:-/data/services/llm-manager/active}"
active_json="$active_dir/active.json"
container="sglang-smoke-qwen3-0.6b"
endpoint="http://127.0.0.1:30000/v1"

[[ -f "$active_json" ]] || fail "active.json missing: $active_json"

state_status="$(
  ACTIVE_JSON="$active_json" python3 - <<'PY'
import json
import os
from pathlib import Path

path = Path(os.environ["ACTIVE_JSON"])
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
}
for key, value in expected.items():
    if state.get(key) != value:
        raise SystemExit(f"FAIL: active.json {key} mismatch: {state.get(key)!r} != {value!r}")
status = state.get("status")
if status not in {"active", "stopped"}:
    raise SystemExit(f"FAIL: active.json status must be active or stopped, got {status!r}")
print(status)
PY
)"
echo "PASS: active.json matches smoke deployment with status $state_status"

container_status="$(sudo -n docker inspect -f '{{.State.Status}}' "$container" 2>/dev/null || true)"
bind_lines="$(ss -H -ltnp | grep ':30000' || true)"

if [[ "$state_status" == "stopped" ]]; then
  [[ "$container_status" != "running" ]] || fail "active.json says stopped but container is running"
  [[ -z "$bind_lines" ]] || fail "active.json says stopped but port 30000 is listening: $bind_lines"
  echo "PASS: stopped state has no running container and no listening port"
else
  [[ "$container_status" == "running" ]] || fail "container is not running: ${container_status:-missing}"
  [[ -n "$bind_lines" ]] || fail "port 30000 is not listening"
  echo "$bind_lines"
  if grep -Eq '(^|[[:space:]])0\.0\.0\.0:30000([[:space:]]|$)|(^|[[:space:]])\[::\]:30000([[:space:]]|$)' <<<"$bind_lines"; then
    fail "public host bind detected"
  fi
  grep -Eq '127\.0\.0\.1:30000' <<<"$bind_lines" || fail "localhost bind not found"
  echo "PASS: localhost-only bind verified"

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

  chat_payload='{"model":"qwen3-0.6b-smoke","messages":[{"role":"system","content":"You are a smoke test assistant."},{"role":"user","content":"Reply with a short confirmation that the lifecycle smoke test works."}],"max_tokens":64,"temperature":0}'
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
fi

scripts/common/root-disk-guard.sh --report /tmp/root-disk-guard-sglang-lifecycle.md
scripts/docker/verify-docker-storage.sh
scripts/nvidia/verify-gpu-containers.sh

echo "PASS: SGLang lifecycle verification passed"
