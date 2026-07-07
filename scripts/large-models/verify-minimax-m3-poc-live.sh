#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/large-models/verify-minimax-m3-poc-live.sh [--help]

Read-only live verification for the M9E MiniMax-M3 MXFP8 proof of life.
It verifies active manager state, localhost-only Docker bind, OpenAI-compatible
/v1/models and chat completions, and storage/GPU guards. It does not start,
stop, pull, download, prune, or mutate active state.
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
compose_file="/data/services/llm-manager/compose/minimax-m3-poc.compose.yml"
container="minimax-m3-mxfp8-poc"
model="minimax-m3-mxfp8-poc"
endpoint="http://127.0.0.1:30002/v1"

[[ "$(hostname)" == "llmserver" ]] || fail "hostname is $(hostname), expected llmserver"
[[ "$(pwd)" == "/data/services/mixed-memory-llm-api-server" ]] || fail "unexpected repo path: $(pwd)"
[[ -f "$active_json" ]] || fail "active.json missing: $active_json"
[[ -f "$compose_file" ]] || fail "compose file missing: $compose_file"

python3 - <<'PY'
import json
from pathlib import Path
path = Path('/data/services/llm-manager/active/active.json')
state = json.loads(path.read_text())
expected = {
    'model_profile': 'minimax-m3-mxfp8-poc',
    'runtime_profile': 'ktransformers-sglang-kt',
    'compose_file': '/data/services/llm-manager/compose/minimax-m3-poc.compose.yml',
    'container_name': 'minimax-m3-mxfp8-poc',
    'bind': '127.0.0.1',
    'port': 30002,
    'endpoint': 'http://127.0.0.1:30002/v1',
    'model_path': '/data/models/minimax-m3-mxfp8',
    'status': 'active',
}
for key, value in expected.items():
    if state.get(key) != value:
        raise SystemExit(f'FAIL: active.json {key}={state.get(key)!r}, expected {value!r}')
image = state.get('image')
if not image or not image.startswith('local/minimax-m3-ktransformers:'):
    raise SystemExit(f'FAIL: unexpected image in active.json: {image!r}')
args = state.get('launch_args', {})
required = {
    '--model-path': '/data/models/minimax-m3-mxfp8',
    '--kt-weight-path': '/data/models/minimax-m3-mxfp8',
    '--kt-method': 'MXFP8',
    '--tp-size': '2',
    '--quantization': 'mxfp8',
    '--served-model-name': 'minimax-m3-mxfp8-poc',
}
for key, value in required.items():
    if str(args.get(key)) != value:
        raise SystemExit(f'FAIL: launch arg {key}={args.get(key)!r}, expected {value!r}')
print('PASS: active.json matches MiniMax-M3 POC')
PY

status="$(sudo -n docker inspect -f '{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$container" 2>/dev/null || true)"
[[ "$status" == running* ]] || fail "container is not running: ${status:-missing}"
echo "PASS: container running: $status"

bind_lines="$(ss -tulpn | grep ':30002' || true)"
[[ -n "$bind_lines" ]] || fail "port 30002 is not listening"
echo "$bind_lines"
if grep -E '0\.0\.0\.0:30002|\[::\]:30002' <<<"$bind_lines"; then
  fail "public host bind detected on 30002"
fi
grep -q '127.0.0.1:30002' <<<"$bind_lines" || fail "localhost bind missing on 30002"
echo "PASS: localhost-only bind verified"

if grep -nE '(^|[^0-9])0\.0\.0\.0:30002:30000' "$compose_file"; then
  fail "public host bind detected in compose file"
fi
grep -n '127.0.0.1:30002:30000' "$compose_file" >/dev/null || fail "localhost compose bind missing"
echo "PASS: compose bind is localhost-only"

curl -fsS "$endpoint/models" >/tmp/m9e-minimax-live-models.json
python3 - <<'PY'
import json
with open('/tmp/m9e-minimax-live-models.json') as f:
    data = json.load(f)
ids = [item.get('id') for item in data.get('data', [])]
if 'minimax-m3-mxfp8-poc' not in ids:
    raise SystemExit(f'FAIL: expected model missing from /v1/models: {ids}')
print('PASS: /v1/models includes minimax-m3-mxfp8-poc')
PY

python3 - <<'PY'
import json, urllib.request
endpoint='http://127.0.0.1:30002/v1'
model='minimax-m3-mxfp8-poc'
payload={
  'model': model,
  'messages': [
    {'role': 'user', 'content': 'Reply with one short sentence confirming MiniMax-M3 proof of life works.'},
  ],
  'max_tokens': 64,
  'temperature': 1.0,
  'top_p': 0.95,
}
req=urllib.request.Request(endpoint + '/chat/completions', data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'}, method='POST')
with urllib.request.urlopen(req, timeout=600) as resp:
    body=resp.read().decode()
    status=resp.status
obj=json.loads(body)
content=obj.get('choices', [{}])[0].get('message', {}).get('content', '')
if status != 200 or not content.strip():
    raise SystemExit('FAIL: chat completion did not return non-empty content')
print('PASS: chat completion returned non-empty content')
print(content.strip()[:500])
PY

scripts/common/require-data-mounted.sh
scripts/common/root-disk-guard.sh --report /tmp/m9e-minimax-live-root-disk-guard.md
M4_REPORT_PATH=/tmp/m9e-minimax-live-docker-storage.md scripts/docker/verify-docker-storage.sh

tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT
mkdir -p "$tmpdir/scripts" "$tmpdir/reports"
cp -R scripts/common scripts/docker scripts/nvidia "$tmpdir/scripts/"
(
  cd "$tmpdir"
  M4_REPORT_PATH="$tmpdir/reports/docker-storage.md" scripts/nvidia/verify-gpu-containers.sh
)

echo "PASS: MiniMax-M3 POC live verification passed"
