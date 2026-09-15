#!/usr/bin/env bash
set -euo pipefail

# CLI-only worker fixtures. Stateful transition/API/container fixtures live in
# tests/lifecycle and inject dependencies instead of production bypass variables.
fail() {
  echo "FAIL: $*" >&2
  exit 1
}

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
LLMCTL="scripts/llmctl"
INSTANCE="configs/deployments/instances/ai-vm-d0b.json"

# Refuse a live deployment host: these shell tests deliberately assume no state.
for path in /data/services/llm-manager/active/active.json /data/services/llm-manager/state/active.json /run/llmctl/recovery.json; do
  [[ ! -e "$path" && ! -L "$path" ]] || fail "worker-only fixture requires absent lifecycle state"
done

# Installed lifecycle plans also require the protected registration. In-process
# tests inject registered fixtures; shell callers have no trust-anchor bypass.
[[ ! -e /etc/local-ai-server && ! -L /etc/local-ai-server ]] || fail "worker-only fixture requires no installed registry"
for command in start restart stop deactivate select; do
  args=("$command")
  if [[ "$command" == select ]]; then args+=(glm-5.3-ud-q4-k-xl-8k); fi
  if LLMCTL_DATA_ROOT="$tmp" LLMCTL_INSTANCE="$INSTANCE" LLMCTL_SKIP_HOST_CHECKS=1 \
      "$LLMCTL" "${args[@]}" --instance "$INSTANCE" --dry-run >"$tmp/$command.out" 2>"$tmp/$command.err"; then
    fail "$command accepted an unregistered instance"
  fi
  grep -q '^FAIL: invalid_configuration_or_io_failure$' "$tmp/$command.err" || fail "$command registration refusal was not sanitized"
  [[ ! -s "$tmp/$command.out" ]] || fail "$command emitted a misleading fallback plan"
done

# An unavailable observation never becomes healthy based on missing/stale state.
if "$LLMCTL" status --instance "$tmp/missing-instance.json" >"$tmp/status.json" 2>"$tmp/status.err"; then
  fail "status with missing instance reported success"
fi
python3 - "$tmp/status.json" <<'PY_CHECK'
import json
import sys
value = json.load(open(sys.argv[1]))
assert value["selected"] is None and value["desired"] == "stopped"
assert value["observed"] == "failed" and value["container_running"] is None
assert value["failure"] == "instance_missing_observation_unavailable"
PY_CHECK

# Invalid JSON and arbitrary diagnostic text must not be echoed in exceptions.
printf '%s\n' '{invalid-synthetic-fixture-content' >"$tmp/invalid-instance.json"
if "$LLMCTL" select glm-5.3-ud-q4-k-xl-8k --instance "$tmp/invalid-instance.json" --dry-run >"$tmp/invalid.out" 2>"$tmp/invalid.err"; then
  fail "invalid instance passed"
fi
grep -q '^FAIL: invalid_configuration_or_io_failure$' "$tmp/invalid.err" || fail "invalid instance diagnostic was not sanitized"
if grep -q 'invalid-synthetic-fixture-content' "$tmp/invalid.out" "$tmp/invalid.err"; then
  fail "invalid instance data leaked into output"
fi

for path in /data/services/llm-manager/active/active.json /data/services/llm-manager/state/active.json /run/llmctl/recovery.json; do
  [[ ! -e "$path" && ! -L "$path" ]] || fail "read-only CLI fixtures wrote lifecycle state"
done

echo "PASS: llmctl lifecycle CLI fixtures; transition/API fixtures are tests/lifecycle"
