#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/large-models/verify-qwen35-mixed-memory-plan.sh [--dry-run] [--help]

Read-only verification for the M9F Qwen3.5 mixed-memory architecture plan. The
verifier checks docs, report, and planning scripts. It does not download models,
pull images, install packages, build runtimes, start containers, stop the active
model, or change active state.
USAGE
}

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

DRY_RUN=0
for arg in "$@"; do
  case "$arg" in
    --help|-h)
      usage
      exit 0
      ;;
    --dry-run)
      DRY_RUN=1
      ;;
    *)
      fail "unknown argument: $arg"
      ;;
  esac
done

EXPECTED_REPO="/data/services/mixed-memory-llm-api-server"
EXPECTED_HOSTNAME="llmserver"
PLAN_SCRIPT="scripts/large-models/plan-qwen35-mixed-memory.sh"
VERIFY_SCRIPT="scripts/large-models/verify-qwen35-mixed-memory-plan.sh"
TEST_SCRIPT="tests/shell/test-qwen35-mixed-memory-plan-static.sh"
REPORT="reports/m9f-offline-resilience-mixed-memory-plan.md"

required_files=(
  docs/offline-resilience-goals.md
  docs/mixed-memory-large-model-strategy.md
  docs/memory-rag-architecture.md
  docs/model-roles.md
  docs/current-state.md
  docs/model-matrix.md
  ROADMAP.md
  "$PLAN_SCRIPT"
  "$VERIFY_SCRIPT"
  "$TEST_SCRIPT"
  "$REPORT"
)

for path in "${required_files[@]}"; do
  [[ -f "$path" ]] || fail "$path missing"
  echo "PASS: exists: $path"
done

[[ -x "$PLAN_SCRIPT" ]] || fail "$PLAN_SCRIPT is not executable"
[[ -x "$VERIFY_SCRIPT" ]] || fail "$VERIFY_SCRIPT is not executable"
[[ -x "$TEST_SCRIPT" ]] || fail "$TEST_SCRIPT is not executable"

grep -q 'set -euo pipefail' "$PLAN_SCRIPT" || fail "$PLAN_SCRIPT missing strict shell mode"
grep -q 'set -euo pipefail' "$VERIFY_SCRIPT" || fail "$VERIFY_SCRIPT missing strict shell mode"
grep -q 'set -euo pipefail' "$TEST_SCRIPT" || fail "$TEST_SCRIPT missing strict shell mode"

for text in \
  'offline/local AI resilience' \
  'Qwen/Qwen3.5-397B-A17B-FP8' \
  'mixed RAM/VRAM' \
  'local memory/RAG' \
  'model-role' \
  'public API exposure remains deferred'; do
  grep -RInF "$text" docs ROADMAP.md "$REPORT" >/dev/null || fail "missing required planning text: $text"
done

if grep -RInE '^[[:space:]]*(sudo -n[[:space:]]+)?docker[[:space:]]+(pull|run|compose[[:space:]]+up)|^[[:space:]]*(huggingface-cli|hf)[[:space:]]+download|snapshot_download|pip[[:space:]]+install|apt(-get)?[[:space:]]+install' "$PLAN_SCRIPT" "$VERIFY_SCRIPT" "$TEST_SCRIPT" | grep -v 'grep -RInE'; then
  fail "M9F scripts/tests contain executable download, image pull, container start, or install command"
fi

if grep -RInE '(^|[[:space:]])0\.0\.0\.0(:[0-9]+)?|[0-9]+:30000:30000' "$PLAN_SCRIPT" "$VERIFY_SCRIPT" "$TEST_SCRIPT" | grep -v 'grep -RInE'; then
  fail "M9F scripts/tests contain public bind pattern"
fi

secret_matches="$(grep -RInE '(HF_TOKEN=[A-Za-z0-9_./+:-]{8,}|OPENAI_API_KEY=[A-Za-z0-9_./+:-]{8,}|GITHUB_TOKEN=[A-Za-z0-9_./+:-]{8,}|BEGIN OPENSSH|BEGIN RSA|PRIVATE KEY)' "$PLAN_SCRIPT" "$VERIFY_SCRIPT" "$TEST_SCRIPT" docs/offline-resilience-goals.md docs/mixed-memory-large-model-strategy.md docs/memory-rag-architecture.md docs/model-roles.md "$REPORT" | grep -v 'grep -RInE' || true)"
if [[ -n "$secret_matches" ]]; then
  echo "$secret_matches" >&2
  fail "secret-like content found"
fi

if [[ "${M9F_PLAN_SKIP_HOST_CHECKS:-0}" == "1" ]]; then
  echo "SKIP: host checks skipped by M9F_PLAN_SKIP_HOST_CHECKS=1 for static tests only"
else
  [[ "$(hostname)" == "$EXPECTED_HOSTNAME" ]] || fail "unexpected hostname: $(hostname)"
  [[ "$(pwd)" == "$EXPECTED_REPO" ]] || fail "unexpected repo path: $(pwd)"
  scripts/common/require-data-mounted.sh
  scripts/common/root-disk-guard.sh --report /tmp/root-disk-guard-m9f-qwen35-verify.md
  M4_REPORT_PATH=/tmp/m9f-docker-storage-verify.md scripts/docker/verify-docker-storage.sh
  nvidia-smi --query-gpu=index,name,compute_cap,memory.total,driver_version --format=csv,noheader | grep -q 'NVIDIA RTX PRO 6000 Blackwell Workstation Edition' || fail "GPU inventory check failed"
  active="$(scripts/llmctl active)"
  echo "$active"
  grep -q '^active: active$' <<<"$active" || fail "active model is not active"
  grep -q '^model_profile: qwen3-30b-a3b-instruct-2507$' <<<"$active" || fail "unexpected active model"
  grep -q '^endpoint: http://127\.0\.0\.1:30001/v1$' <<<"$active" || fail "unexpected active endpoint"
  grep -q '^live_endpoint_models: ok$' <<<"$active" || fail "active endpoint is not ok"
  scripts/llmctl status | grep -q '^manager_status: active$' || fail "manager status is not active"
fi

echo "PASS: Qwen3.5 mixed-memory plan verification passed"
