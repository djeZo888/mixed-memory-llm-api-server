#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/api/smoke-openai-chat.sh --dry-run [--url URL] [--model MODEL]
       scripts/api/smoke-openai-chat.sh --yes-run-smoke-api [--url URL] [--model MODEL]

M8A dry-run prints the local OpenAI-compatible smoke curl command only. A real
request is reserved for M8B or later and requires --yes-run-smoke-api.
USAGE
}

fail() {
  echo "STOP: $*" >&2
  exit 1
}

URL="http://127.0.0.1:30000/v1/chat/completions"
MODEL="qwen3-0.6b-smoke"
DRY_RUN=0
YES_RUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --help|-h)
      usage
      exit 0
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --yes-run-smoke-api)
      YES_RUN=1
      shift
      ;;
    --url)
      [[ $# -ge 2 ]] || fail "--url requires a value"
      URL="$2"
      shift 2
      ;;
    --model)
      [[ $# -ge 2 ]] || fail "--model requires a value"
      MODEL="$2"
      shift 2
      ;;
    *)
      fail "unknown argument: $1"
      ;;
  esac
done

[[ "$URL" == http://127.0.0.1:* || "$URL" == http://localhost:* ]] || fail "smoke API target must be local only"

payload=$(printf '{"model":"%s","messages":[{"role":"system","content":"You are a smoke test assistant."},{"role":"user","content":"Reply with a short confirmation that the smoke test works."}],"temperature":0,"max_tokens":64}' "$MODEL")

if [[ "$DRY_RUN" == "1" ]]; then
  cat <<EOF
DRY-RUN: no API request sent
curl -sS -X POST '$URL' \\
  -H 'Content-Type: application/json' \\
  --data '$payload'
EOF
  exit 0
fi

[[ "$YES_RUN" == "1" ]] || fail "real API smoke request is reserved for M8B; pass --dry-run in M8A"

response="$(curl -fsS -X POST "$URL" \
  -H 'Content-Type: application/json' \
  --data "$payload")"

SMOKE_RESPONSE="$response" python3 - <<'PY'
import json
import os
import sys

raw = os.environ["SMOKE_RESPONSE"]
try:
    data = json.loads(raw)
except json.JSONDecodeError as exc:
    print(raw)
    raise SystemExit(f"STOP: response was not valid JSON: {exc}")

try:
    content = data["choices"][0]["message"]["content"]
except (KeyError, IndexError, TypeError) as exc:
    print(json.dumps(data, indent=2, sort_keys=True))
    raise SystemExit(f"STOP: missing choices[0].message.content: {exc}")

if not isinstance(content, str) or not content.strip():
    print(json.dumps(data, indent=2, sort_keys=True))
    raise SystemExit("STOP: empty chat completion content")

print("PASS: chat completion content received")
print("content:")
print(content.strip())
PY
