#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/sglang/verify-sglang-real-fast-live.sh [--help]

Read-only live verification for the M9B SGLang first real fast model.
It verifies active manager state, localhost-only Docker bind, OpenAI-compatible
/v1/models and chat completions, streaming responses, and storage/GPU guards.
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

repo_root() {
  git rev-parse --show-toplevel 2>/dev/null || pwd
}

cd "$(repo_root)"

active_json="/data/services/llm-manager/active/active.json"
compose_file="/data/services/llm-manager/compose/sglang-qwen3-30b.compose.yml"
container="sglang-qwen3-30b-a3b-instruct-2507"
model="qwen3-30b-a3b-instruct-2507"
endpoint="http://127.0.0.1:30001/v1"

[[ -f "$active_json" ]] || fail "active.json missing: $active_json"
[[ -f "$compose_file" ]] || fail "compose file missing: $compose_file"

python3 - <<'PY'
import json
from pathlib import Path
path = Path('/data/services/llm-manager/active/active.json')
state = json.loads(path.read_text())
expected = {
    'model_profile': 'qwen3-30b-a3b-instruct-2507',
    'runtime_profile': 'sglang',
    'compose_file': '/data/services/llm-manager/compose/sglang-qwen3-30b.compose.yml',
    'container_name': 'sglang-qwen3-30b-a3b-instruct-2507',
    'bind': '127.0.0.1',
    'port': 30001,
    'endpoint': 'http://127.0.0.1:30001/v1',
    'model_path': '/data/models/qwen3-30b-a3b-instruct-2507',
    'image': 'lmsysorg/sglang:v0.5.14-cu130',
    'status': 'active',
}
for key, value in expected.items():
    if state.get(key) != value:
        raise SystemExit(f'FAIL: active.json {key}={state.get(key)!r}, expected {value!r}')
args = state.get('launch_args', {})
for key, value in {'--tp': '2', '--context-length': '32768', '--mem-fraction-static': '0.75'}.items():
    if str(args.get(key)) != value:
        raise SystemExit(f'FAIL: launch arg {key}={args.get(key)!r}, expected {value!r}')
print('PASS: active.json matches M9B real fast model')
PY

status="$(sudo -n docker inspect -f '{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$container" 2>/dev/null || true)"
[[ "$status" == running* ]] || fail "container is not running: ${status:-missing}"
echo "PASS: container running: $status"

bind_lines="$(ss -tulpn | grep ':30001' || true)"
[[ -n "$bind_lines" ]] || fail "port 30001 is not listening"
echo "$bind_lines"
if grep -E '0\.0\.0\.0:30001|\[::\]:30001' <<<"$bind_lines"; then
  fail "public host bind detected on 30001"
fi
grep -q '127.0.0.1:30001' <<<"$bind_lines" || fail "localhost bind missing on 30001"
echo "PASS: localhost-only bind verified"

if ss -tulpn | grep ':30000'; then
  fail "smoke port 30000 is unexpectedly listening"
fi
echo "PASS: smoke port 30000 is not listening"

curl -fsS "$endpoint/models" >/tmp/m9b-live-models.json
python3 - <<'PY'
import json
with open('/tmp/m9b-live-models.json') as f:
    data = json.load(f)
ids = [item.get('id') for item in data.get('data', [])]
if 'qwen3-30b-a3b-instruct-2507' not in ids:
    raise SystemExit(f'FAIL: expected model missing from /v1/models: {ids}')
print('PASS: /v1/models includes qwen3-30b-a3b-instruct-2507')
PY

python3 - <<'PY'
import json, urllib.request
endpoint='http://127.0.0.1:30001/v1'
model='qwen3-30b-a3b-instruct-2507'
payload={
  'model': model,
  'messages': [
    {'role': 'system', 'content': 'You are a concise technical assistant.'},
    {'role': 'user', 'content': 'Reply with one short sentence confirming live verification works.'},
  ],
  'max_tokens': 96,
  'temperature': 0,
}
req=urllib.request.Request(endpoint + '/chat/completions', data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'}, method='POST')
with urllib.request.urlopen(req, timeout=300) as resp:
    body=resp.read().decode()
    status=resp.status
obj=json.loads(body)
content=obj.get('choices', [{}])[0].get('message', {}).get('content', '')
if status != 200 or not content.strip():
    raise SystemExit('FAIL: chat completion did not return non-empty content')
print('PASS: chat completion returned non-empty content')

stream_payload=dict(payload)
stream_payload['stream']=True
req=urllib.request.Request(endpoint + '/chat/completions', data=json.dumps(stream_payload).encode(), headers={'Content-Type': 'application/json'}, method='POST')
chunks=0
done=False
with urllib.request.urlopen(req, timeout=300) as resp:
    if resp.status != 200:
        raise SystemExit(f'FAIL: streaming status {resp.status}')
    for raw in resp:
        line=raw.decode(errors='replace').strip()
        if not line.startswith('data: '):
            continue
        chunks += 1
        if line == 'data: [DONE]':
            done=True
            break
if chunks < 1:
    raise SystemExit('FAIL: streaming produced no SSE data chunks')
print(f'PASS: streaming returned SSE chunks; done={done}')
PY

scripts/common/require-data-mounted.sh
scripts/common/root-disk-guard.sh --report /tmp/m9b-real-fast-live-root-disk-guard.md
M4_REPORT_PATH=/tmp/m9b-real-fast-live-docker-storage.md scripts/docker/verify-docker-storage.sh

tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT
mkdir -p "$tmpdir/scripts" "$tmpdir/reports"
cp -R scripts/common scripts/docker scripts/nvidia "$tmpdir/scripts/"
(
  cd "$tmpdir"
  M4_REPORT_PATH="$tmpdir/reports/docker-storage.md" scripts/nvidia/verify-gpu-containers.sh
)

echo "PASS: SGLang real fast live verification passed"
