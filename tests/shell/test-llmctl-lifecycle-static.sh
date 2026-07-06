#!/usr/bin/env bash
set -euo pipefail

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

LLMCTL="scripts/llmctl"
VERIFY="scripts/sglang/verify-sglang-lifecycle.sh"

[[ -x "$LLMCTL" ]] || fail "$LLMCTL missing or not executable"
[[ -f "$VERIFY" ]] || fail "$VERIFY missing"

"$LLMCTL" --help >/dev/null || fail "llmctl --help failed"
for command in start stop restart deactivate logs; do
  "$LLMCTL" "$command" --help >/tmp/llmctl-"$command"-help.out || fail "$command --help failed"
done

grep -q 'start' /tmp/llmctl-start-help.out || fail "start help missing command text"
grep -q -- '--dry-run' /tmp/llmctl-start-help.out || fail "start help missing --dry-run"
grep -q -- '--yes' /tmp/llmctl-start-help.out || fail "start help missing --yes"
grep -q -- '--no-wait' /tmp/llmctl-start-help.out || fail "start help missing --no-wait"
grep -q -- '--yes' /tmp/llmctl-stop-help.out || fail "stop help missing --yes"
grep -q -- '--yes' /tmp/llmctl-restart-help.out || fail "restart help missing --yes"
grep -q -- '--yes' /tmp/llmctl-deactivate-help.out || fail "deactivate help missing --yes"
grep -q -- '--yes' /tmp/llmctl-logs-help.out || fail "logs help missing --yes"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
mkdir -p "$tmp/active"
cat >"$tmp/smoke.compose.yml" <<'YAML'
services:
  sglang-smoke:
    image: lmsysorg/sglang:v0.5.14-cu130
    container_name: sglang-smoke-qwen3-0.6b
    profiles: ["sglang-smoke"]
    ports:
      - "127.0.0.1:30000:30000"
YAML
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
  "status": "active"
}
YAML

fixture_env=(
  LLMCTL_SKIP_HOST_CHECKS=1
  LLMCTL_SKIP_DOCKER=1
  LLMCTL_ACTIVE_DIR="$tmp/active"
  LLMCTL_SMOKE_COMPOSE_FILE="$tmp/smoke.compose.yml"
)

for command in start stop restart deactivate; do
  if env "${fixture_env[@]}" "$LLMCTL" "$command" >/tmp/llmctl-"$command".out 2>/tmp/llmctl-"$command".err; then
    fail "$command without --yes or --dry-run succeeded"
  fi
  grep -q -- '--yes' /tmp/llmctl-"$command".err || fail "$command refusal did not mention --yes"
  grep -q -- '--dry-run' /tmp/llmctl-"$command".err || fail "$command refusal did not show dry-run command"
done

for command in start stop restart deactivate; do
  env "${fixture_env[@]}" "$LLMCTL" "$command" --dry-run >/tmp/llmctl-"$command"-dry-run.out || fail "$command --dry-run failed"
  grep -q 'DRY-RUN' /tmp/llmctl-"$command"-dry-run.out || fail "$command dry-run did not report DRY-RUN"
  grep -q 'model_file_deletion: none' /tmp/llmctl-"$command"-dry-run.out || fail "$command dry-run missing model deletion policy"
  grep -q 'image_deletion: none' /tmp/llmctl-"$command"-dry-run.out || fail "$command dry-run missing image deletion policy"
  if [[ "$command" == "start" ]]; then
    grep -q 'wait_for_readiness: yes by default' /tmp/llmctl-start-dry-run.out || fail "start dry-run missing readiness wait policy"
  fi
done

env "${fixture_env[@]}" "$LLMCTL" logs --dry-run >/tmp/llmctl-logs-dry-run.out || fail "logs --dry-run failed"
grep -q 'log_command:' /tmp/llmctl-logs-dry-run.out || fail "logs dry-run missing log command"

if grep -RInE 'docker[[:space:]]+prune|system[[:space:]]+prune|docker[[:space:]]+(rmi|image[[:space:]]+rm)|shutil\.rmtree|rm[[:space:]-].*/data/models|0\.0\.0\.0:30000:30000' "$LLMCTL" "$VERIFY"; then
  fail "dangerous lifecycle pattern found"
fi

if grep -RInE 'known M8B smoke deployment|existing M8B smoke deployment|run start --yes only for the known smoke deployment' "$LLMCTL"; then
  fail "old smoke-only lifecycle failure string found"
fi

if grep -RInE '(BEGIN OPENSSH|BEGIN RSA|PRIVATE KEY|HF_TOKEN=[A-Za-z0-9_./+:-]{8,}|OPENAI_API_KEY=[A-Za-z0-9_./+:-]{8,}|GITHUB_TOKEN=[A-Za-z0-9_./+:-]{8,})' "$LLMCTL" "$VERIFY"; then
  fail "hard-coded secret-like content found"
fi

echo "PASS: llmctl lifecycle static checks"
