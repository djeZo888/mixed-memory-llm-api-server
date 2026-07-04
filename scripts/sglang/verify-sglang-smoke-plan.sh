#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/sglang/verify-sglang-smoke-plan.sh [--help]

Read-only verification for the M8A SGLang smoke deployment plan and templates.
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

COMPOSE="configs/compose/compose.sglang-smoke.template.yml"
ENV_EXAMPLE="configs/sglang/smoke.env.example"
REPORT="reports/m8a-sglang-smoke-plan.md"
DOC="docs/sglang-smoke-deployment.md"
PROPOSED_IMAGE="lmsysorg/sglang:v0.5.14-cu130-runtime"

[[ -f "$COMPOSE" ]] || fail "$COMPOSE missing"
[[ -f "$ENV_EXAMPLE" ]] || fail "$ENV_EXAMPLE missing"
[[ -f "$REPORT" ]] || fail "$REPORT missing"
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

grep -Fq "$PROPOSED_IMAGE" "$REPORT" || fail "report does not record proposed pinned SGLang image"
grep -Fq "$PROPOSED_IMAGE" "$DOC" || fail "deployment doc does not record proposed pinned SGLang image"
if grep -En 'lmsysorg/sglang:(latest|latest-runtime)$|SGLANG_IMAGE_TAG=.*latest' "$COMPOSE" "$ENV_EXAMPLE" "$REPORT" "$DOC"; then
  fail "latest SGLang image tag found where a pinned tag is required"
fi

secret_matches="$(grep -RInE '(HF_TOKEN=[A-Za-z0-9_./+:-]{8,}|OPENAI_API_KEY=[A-Za-z0-9_./+:-]{8,}|GITHUB_TOKEN=[A-Za-z0-9_./+:-]{8,}|BEGIN OPENSSH|BEGIN RSA|PRIVATE KEY)' "$COMPOSE" "$ENV_EXAMPLE" "$REPORT" "$DOC" scripts/sglang scripts/api tests/shell/test-sglang-smoke-static.sh | grep -v 'grep -RInE' || true)"
if [[ -n "$secret_matches" ]]; then
  echo "$secret_matches" >&2
  fail "secret-like content found"
fi

active="$(scripts/llmctl active)"
echo "$active"
[[ "$active" == "active: none" ]] || fail "llmctl reports active backend"

if sudo -n docker ps --format '{{.Image}} {{.Names}} {{.Command}}' 2>/dev/null | grep -Ei 'sglang|qwen3-0\.6b-smoke'; then
  fail "SGLang or smoke-model container is already running"
fi

echo "PASS: SGLang smoke plan verification passed"
