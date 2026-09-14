#!/usr/bin/env bash
set -euo pipefail

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

LLMCTL="scripts/llmctl"
LIFECYCLE="scripts/lifecycle"
INSTANCE="configs/deployments/instances/ai-vm-d0b.json"
[[ -x "$LLMCTL" ]] || fail "$LLMCTL missing or not executable"
[[ -f "$LIFECYCLE/manager.py" && -f "$LIFECYCLE/runtime_io.py" ]] || fail "lifecycle source missing"
[[ -f "$INSTANCE" ]] || fail "explicit deployment instance missing"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
"$LLMCTL" --help >"$tmp/help" || fail "llmctl --help failed"
for command in select activate start stop restart deactivate boot-start boot-stop recover-stop logs; do
  "$LLMCTL" "$command" --help >"$tmp/$command-help" || fail "$command --help failed"
  grep -q -- '--instance' "$tmp/$command-help" || fail "$command help missing explicit instance"
  grep -q -- '--dry-run' "$tmp/$command-help" || fail "$command help missing --dry-run"
  grep -q -- '--yes' "$tmp/$command-help" || fail "$command help missing --yes"
  args=("$command")
  if [[ "$command" == select || "$command" == activate ]]; then
    args+=(glm-5.3-ud-q4-k-xl-8k)
  fi
  if "$LLMCTL" "${args[@]}" --instance "$INSTANCE" >"$tmp/$command.out" 2>"$tmp/$command.err"; then
    fail "$command without --yes or --dry-run succeeded"
  fi
  grep -q -- '--yes or --dry-run' "$tmp/$command.err" || fail "$command refusal missing confirmation/dry-run guidance"
done

grep -q -- '--no-wait' "$tmp/start-help" || fail "deprecated no-wait help missing"
if "$LLMCTL" start --instance "$INSTANCE" --yes --no-wait >"$tmp/no-wait.out" 2>"$tmp/no-wait.err"; then
  fail "unbounded no-wait start was accepted"
fi
grep -q 'no_wait_refused_use_bounded_start' "$tmp/no-wait.err" || fail "no-wait refusal not specific"

"$LLMCTL" logs --dry-run >"$tmp/logs-dry" || fail "logs --dry-run failed"
grep -q 'DRY-RUN.*bounded Docker logs' "$tmp/logs-dry" || fail "logs dry-run missing bounded log policy"
if "$LLMCTL" logs --yes >"$tmp/logs.out" 2>"$tmp/logs.err"; then
  fail "raw runtime logs were relayed without reviewed redaction"
fi
grep -q 'raw_logs_disabled' "$tmp/logs.err" || fail "raw log refusal missing"

# Keep destructive-download-secret checks alongside executable behavior tests.
if grep -RInE 'docker[[:space:]]+prune|system[[:space:]]+prune|docker[[:space:]]+(rmi|image[[:space:]]+rm)|shutil\.rmtree|rm[[:space:]-].*/data/models|docker[[:space:]]+(image[[:space:]]+)?pull' "$LLMCTL" "$LIFECYCLE" --include='*.py'; then
  fail "dangerous lifecycle deletion/pull pattern found"
fi
if grep -RInE '(BEGIN OPENSSH|BEGIN RSA|PRIVATE KEY|HF_TOKEN=[A-Za-z0-9_./+:-]{8,}|OPENAI_API_KEY=[A-Za-z0-9_./+:-]{8,}|GITHUB_TOKEN=[A-Za-z0-9_./+:-]{8,})' "$LLMCTL" "$LIFECYCLE" --include='*.py'; then
  fail "hard-coded secret-like content found"
fi
python3 - <<'PY_CHECK'
from pathlib import Path
source = Path("scripts/lifecycle/runtime_io.py").read_text()
assert '["container", "create", "--pull", "never", *argv]' in source
assert "stderr=subprocess.DEVNULL" in source
assert "os.O_NOFOLLOW" in source
assert "LLMCTL_SKIP_DOCKER" not in Path("scripts/lifecycle/manager.py").read_text()
assert "LLMCTL_SKIP_HOST_CHECKS" not in Path("scripts/lifecycle/manager.py").read_text()
PY_CHECK

echo "PASS: llmctl lifecycle help, refusals, and safety source checks"
