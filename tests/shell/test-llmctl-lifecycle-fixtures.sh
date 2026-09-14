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

for command in start restart; do
  if "$LLMCTL" "$command" --instance "$INSTANCE" --dry-run >"$tmp/$command.out" 2>"$tmp/$command.err"; then
    fail "$command unexpectedly selected a model from absent state"
  fi
  grep -q '^FAIL: no_deployment_selected_use_select$' "$tmp/$command.err" || fail "$command missing-selection refusal was not specific"
  [[ ! -s "$tmp/$command.out" ]] || fail "$command emitted a misleading fallback plan"
done

for command in stop deactivate; do
  "$LLMCTL" "$command" --instance "$INSTANCE" --dry-run >"$tmp/$command.json" || fail "$command dry-run failed"
  python3 - "$tmp/$command.json" "$command" <<'PY_CHECK'
import json
import sys
value = json.load(open(sys.argv[1]))
assert value["dry_run"] is True and value["action"] == sys.argv[2]
assert value["selected"] is None and value["writes"] is False
assert value["model_file_deletion"] == value["image_deletion"] == "none"
PY_CHECK
done

for deployment in glm-5.3-ud-q4-k-xl-8k glm-5.3-ud-q4-k-xl-32k qwen3-30b-a3b-instruct-2507 qwen3-0.6b-smoke; do
  "$LLMCTL" select "$deployment" --instance "$INSTANCE" --dry-run >"$tmp/select.json" || fail "explicit select dry-run failed: $deployment"
  python3 - "$tmp/select.json" "$deployment" <<'PY_CHECK'
import json
import sys
value = json.load(open(sys.argv[1]))
assert value["selected"] == sys.argv[2]
assert value["dry_run"] is True and value["writes"] is False
assert value["wait_for_readiness"] is True
assert value["model_file_deletion"] == value["image_deletion"] == "none"
PY_CHECK
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
grep -q '^FAIL: invalid_or_missing_json$' "$tmp/invalid.err" || fail "invalid instance diagnostic was not sanitized"
if grep -q 'invalid-synthetic-fixture-content' "$tmp/invalid.out" "$tmp/invalid.err"; then
  fail "invalid instance data leaked into output"
fi

for path in /data/services/llm-manager/active/active.json /data/services/llm-manager/state/active.json /run/llmctl/recovery.json; do
  [[ ! -e "$path" && ! -L "$path" ]] || fail "read-only CLI fixtures wrote lifecycle state"
done

echo "PASS: llmctl lifecycle CLI fixtures; transition/API fixtures are tests/lifecycle"
