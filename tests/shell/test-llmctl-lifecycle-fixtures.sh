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

write_real_active() {
  local status="$1"
  cat >"$tmp/active/active.json" <<YAML
{
  "model_profile": "qwen3-30b-a3b-instruct-2507",
  "runtime_profile": "sglang",
  "compose_file": "/data/services/llm-manager/compose/sglang-qwen3-30b.compose.yml",
  "container_name": "sglang-qwen3-30b-a3b-instruct-2507",
  "bind": "127.0.0.1",
  "port": 30001,
  "endpoint": "http://127.0.0.1:30001/v1",
  "model_path": "/data/models/qwen3-30b-a3b-instruct-2507",
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

run_status_case() {
  local name="$1"
  local container_status="$2"
  local health="$3"
  local endpoint_ok="$4"
  local port_lines="$5"
  local expected="$6"
  local out="/tmp/llmctl-lifecycle-status-$name.out"

  env "${fixture_env[@]}" \
    LLMCTL_FAKE_CONTAINER_STATUS="$container_status" \
    LLMCTL_FAKE_CONTAINER_HEALTH="$health" \
    LLMCTL_FAKE_ENDPOINT_OK="$endpoint_ok" \
    LLMCTL_FAKE_PORT_LINES="$port_lines" \
    scripts/llmctl status >"$out" || fail "status case failed: $name"
  grep -q "manager_status: $expected" "$out" || fail "status case $name did not report $expected"
}

smoke_port_line='LISTEN 0 4096 127.0.0.1:30000 0.0.0.0:*'
real_port_line='LISTEN 0 4096 127.0.0.1:30001 0.0.0.0:*'

write_active active

env "${fixture_env[@]}" scripts/llmctl active >/tmp/llmctl-lifecycle-active.out || fail "active parsing failed"
grep -q 'model_profile: qwen3-0.6b-smoke' /tmp/llmctl-lifecycle-active.out || fail "active output missing model"
grep -q 'WARN: active_state_stale' /tmp/llmctl-lifecycle-active.out || fail "stale active state warning missing"

env "${fixture_env[@]}" scripts/llmctl status >/tmp/llmctl-lifecycle-status.out || fail "status parsing failed"
grep -q 'manager_status: stale' /tmp/llmctl-lifecycle-status.out || fail "status did not report stale"

run_status_case starting running starting 0 "$smoke_port_line" starting
if grep -q 'manager_status: stale' /tmp/llmctl-lifecycle-status-starting.out; then
  fail "starting case was incorrectly reported stale"
fi
grep -q 'active_state_starting' /tmp/llmctl-lifecycle-status-starting.out || fail "starting case did not explain readiness"

run_status_case exited exited unhealthy 0 '' stale
run_status_case unhealthy running unhealthy 0 "$smoke_port_line" unhealthy
run_status_case active running healthy 1 "$smoke_port_line" active

write_real_active active
run_status_case real-active running healthy 1 "$real_port_line" active
grep -q 'real_activation: active_m9b_real_fast' /tmp/llmctl-lifecycle-status-real-active.out || fail "real model status missing activation marker"

env "${fixture_env[@]}" scripts/llmctl start --dry-run >/tmp/llmctl-lifecycle-real-start-dry.out || fail "real start dry-run failed"
grep -q 'model_profile: qwen3-30b-a3b-instruct-2507' /tmp/llmctl-lifecycle-real-start-dry.out || fail "real start dry-run did not use active real model"

write_active active
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
