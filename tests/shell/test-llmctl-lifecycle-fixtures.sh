#!/usr/bin/env bash
set -euo pipefail

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

mkdir -p "$tmp/active" "$tmp/data" "$tmp/configs/models/profiles" "$tmp/configs/runtimes"

cat >"$tmp/smoke.compose.yml" <<'YAML'
services:
  sglang-smoke:
    image: lmsysorg/sglang:v0.5.14-cu130
    container_name: sglang-smoke-qwen3-0.6b
    profiles: ["sglang-smoke"]
    restart: "no"
    ports:
      - "127.0.0.1:30000:30000"
YAML

write_active() {
  local status="$1"
  cat >"$tmp/active/active.json" <<YAML
{
  "model_profile": "qwen3-0.6b-smoke",
  "runtime_profile": "sglang",
  "compose_file": "$tmp/smoke.compose.yml",
  "container_name": "sglang-smoke-qwen3-0.6b",
  "bind": "127.0.0.1",
  "port": 30000,
  "endpoint": "http://127.0.0.1:30000/v1",
  "model_path": "/data/models/qwen3-0.6b-smoke",
  "image": "lmsysorg/sglang:v0.5.14-cu130",
  "status": "$status"
}
YAML
}

fixture_env=(
  LLMCTL_SKIP_HOST_CHECKS=1
  LLMCTL_SKIP_DOCKER=1
  LLMCTL_ACTIVE_DIR="$tmp/active"
  LLMCTL_SMOKE_COMPOSE_FILE="$tmp/smoke.compose.yml"
)

write_active active

env "${fixture_env[@]}" scripts/llmctl active >/tmp/llmctl-lifecycle-active.out || fail "active parsing failed"
grep -q 'model_profile: qwen3-0.6b-smoke' /tmp/llmctl-lifecycle-active.out || fail "active output missing model"
grep -q 'WARN: active_state_stale' /tmp/llmctl-lifecycle-active.out || fail "stale active state warning missing"

env "${fixture_env[@]}" scripts/llmctl status >/tmp/llmctl-lifecycle-status.out || fail "status parsing failed"
grep -q 'manager_status: stale' /tmp/llmctl-lifecycle-status.out || fail "status did not report stale"

for command in start stop restart deactivate; do
  env "${fixture_env[@]}" scripts/llmctl "$command" --dry-run >/tmp/llmctl-lifecycle-"$command"-dry.out || fail "$command dry-run failed"
  grep -q 'DRY-RUN' /tmp/llmctl-lifecycle-"$command"-dry.out || fail "$command dry-run missing DRY-RUN"
done

rm -f "$tmp/active/active.json"
if env "${fixture_env[@]}" scripts/llmctl stop --dry-run >/tmp/llmctl-lifecycle-missing-stop.out 2>/tmp/llmctl-lifecycle-missing-stop.err; then
  fail "stop dry-run succeeded without active.json"
fi
grep -q 'active state missing' /tmp/llmctl-lifecycle-missing-stop.err || fail "missing active.json failure was not specific"

env "${fixture_env[@]}" scripts/llmctl start --dry-run >/tmp/llmctl-lifecycle-missing-start.out || fail "start dry-run fallback failed"
grep -q 'active.json missing' /tmp/llmctl-lifecycle-missing-start.out || fail "start fallback did not explain missing active.json"

write_active stopped
env "${fixture_env[@]}" scripts/llmctl active >/tmp/llmctl-lifecycle-stopped-active.out || fail "stopped active parsing failed"
grep -q 'active: stopped' /tmp/llmctl-lifecycle-stopped-active.out || fail "stopped active output missing"

env "${fixture_env[@]}" scripts/llmctl deactivate --yes >/tmp/llmctl-lifecycle-deactivate.out || fail "fixture deactivate failed"
grep -q 'archived_active_state:' /tmp/llmctl-lifecycle-deactivate.out || fail "deactivate did not report archive"
[[ ! -e "$tmp/active/active.json" ]] || fail "active.json still present after deactivate"
find "$tmp/active/history" -type f -name 'active-*.json' | grep -q . || fail "active history archive missing"

if [[ -e /data/services/llm-manager/active/history ]]; then
  echo "INFO: real active history directory exists; fixture test did not inspect or modify it"
fi

echo "PASS: llmctl lifecycle fixture checks"
