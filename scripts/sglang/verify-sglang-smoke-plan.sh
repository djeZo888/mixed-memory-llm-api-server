#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/sglang/verify-sglang-smoke-plan.sh [--instance PATH] [--llmctl PATH] [--help]

Offline verification of the retained SGLang smoke plan and templates.
Run from the repository root. Requires bash, grep, Python 3 and llmctl source;
Docker, mounted model storage and installed inference software are unnecessary.

--instance PATH  Pass an explicit deployment-instance file to status --offline.
--llmctl PATH    Use an explicit llmctl executable dependency (default scripts/llmctl).

Saved selection may name any deployment. Saved readiness is not live evidence.
Live host checks and model readiness remain NOT_TESTED by this planning command.
USAGE
}

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

LLMCTL="scripts/llmctl"
llmctl_args=(status --offline)
while [[ $# -gt 0 ]]; do
  case "$1" in
    --help|-h)
      usage
      exit 0
      ;;
    --instance)
      [[ $# -ge 2 && -n "$2" ]] || fail "--instance requires a path"
      llmctl_args=(status --offline --instance "$2")
      shift 2
      ;;
    --llmctl)
      [[ $# -ge 2 && -n "$2" ]] || fail "--llmctl requires an executable path"
      LLMCTL="$2"
      shift 2
      ;;
    *)
      fail "unknown argument; use --help"
      ;;
  esac
done

COMPOSE="configs/compose/compose.sglang-smoke.template.yml"
ENV_EXAMPLE="configs/sglang/smoke.env.example"
REPORT="reports/m8a-sglang-smoke-plan.md"
M8B_REPORT="reports/m8b-sglang-smoke-deploy.md"
DOC="docs/sglang-smoke-deployment.md"
PROPOSED_IMAGE="lmsysorg/sglang:v0.5.14-cu130"

[[ -f "$COMPOSE" ]] || fail "$COMPOSE missing"
[[ -f "$ENV_EXAMPLE" ]] || fail "$ENV_EXAMPLE missing"
[[ -f "$REPORT" ]] || fail "$REPORT missing"
[[ -f "$M8B_REPORT" ]] || fail "$M8B_REPORT missing"
[[ -f "$DOC" ]] || fail "$DOC missing"

grep -Fq 'image: ${SGLANG_IMAGE_TAG}' "$COMPOSE" || fail "compose template must use SGLANG_IMAGE_TAG placeholder"
grep -Fq 'profiles: ["sglang-smoke"]' "$COMPOSE" || fail "compose template must use sglang-smoke profile"
grep -Fq '127.0.0.1:30000:30000' "$COMPOSE" || fail "compose template must bind externally to 127.0.0.1:30000"
if grep -En '"(0\.0\.0\.0:)?30000:30000"|-[[:space:]]*"30000:30000"' "$COMPOSE"; then
  fail "compose template publishes port without explicit 127.0.0.1 binding"
fi
for path in /data/models /data/hf-cache /data/logs /data/models/qwen3-0.6b-smoke; do
  grep -Fq "$path" "$COMPOSE" "$ENV_EXAMPLE" "$REPORT" "$DOC" || fail "missing planned path reference: $path"
done

grep -Fq "$PROPOSED_IMAGE" "$M8B_REPORT" "$DOC" "$ENV_EXAMPLE" || fail "M8B docs/config do not record remediation pinned SGLang image"
grep -Fq "$PROPOSED_IMAGE" "$DOC" || fail "deployment doc does not record proposed pinned SGLang image"
if grep -En 'lmsysorg/sglang:(latest|latest-runtime)$|SGLANG_IMAGE_TAG=.*latest' "$COMPOSE" "$ENV_EXAMPLE" "$REPORT" "$DOC"; then
  fail "latest SGLang image tag found where a pinned tag is required"
fi

secret_matches="$(grep -RInE '(HF_TOKEN=[A-Za-z0-9_./+:-]{8,}|OPENAI_API_KEY=[A-Za-z0-9_./+:-]{8,}|GITHUB_TOKEN=[A-Za-z0-9_./+:-]{8,}|BEGIN OPENSSH|BEGIN RSA|PRIVATE KEY)' "$COMPOSE" "$ENV_EXAMPLE" "$REPORT" "$DOC" scripts/sglang scripts/api tests/shell/test-sglang-smoke-static.sh | grep -v 'grep -RInE' || true)"
if [[ -n "$secret_matches" ]]; then
  fail "secret-like content found"
fi

python3 - "$LLMCTL" "${llmctl_args[@]}" <<'PY'
import json
import re
import subprocess
import sys

def fail(code):
    print("FAIL: " + code, file=sys.stderr)
    raise SystemExit(1)

# Capture diagnostics without relaying arbitrary status data, key-like values,
# subprocess stderr, command lines or exception messages.
try:
    result = subprocess.run([sys.argv[1], *sys.argv[2:]],
                            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, timeout=15, check=False)
except (OSError, ValueError, subprocess.TimeoutExpired):
    fail("offline_status_command_failed")
if result.returncode != 0:
    fail("offline_status_command_failed")
if len(result.stdout) > 1024 * 1024:
    fail("offline_status_schema_invalid")
try:
    state = json.loads(result.stdout)
except (ValueError, UnicodeError):
    fail("offline_status_schema_invalid")
required = {"schema_version", "configured", "selected", "desired", "boot_policy",
            "recorded_observed", "observed", "container_running", "observation"}
if not isinstance(state, dict) or not required.issubset(state):
    fail("offline_status_schema_invalid")
selected = state["selected"]
if (type(state["schema_version"]) is not int or state["schema_version"] != 2
        or type(state["configured"]) is not bool
        or (selected is not None and (not isinstance(selected, str)
            or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}", selected)))
        or state["desired"] not in ("running", "stopped")
        or state["boot_policy"] not in ("manual", "resume")
        or state["recorded_observed"] not in (None, "stopped", "starting", "ready", "unhealthy", "failed")
        or state["observed"] is not None or state["container_running"] is not None
        or state["observation"] != "not_performed_offline"
        or (selected is None and state["desired"] != "stopped")
        or (not state["configured"] and (selected is not None or state["desired"] != "stopped"
            or state["boot_policy"] != "manual" or state["recorded_observed"] is not None))):
    fail("offline_status_schema_invalid")
print("offline_lifecycle_contract: PASS")
PY

echo "live_host_checks: NOT_TESTED"
echo "readiness: NOT_TESTED"
echo "PASS: SGLang smoke plan verification passed"
