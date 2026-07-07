#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/large-models/verify-large-model-plan.sh [--dry-run] [--help]

Read-only verification for the M9D large-model feasibility plan. The verifier
checks planning artifacts and, unless skipped for static tests, verifies the
current active real model without downloading models, pulling images, installing
packages, building runtimes, starting containers, or changing active state.
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

REPORT="reports/m9d-large-model-feasibility-plan.md"
DOC="docs/large-model-feasibility.md"
PLAN_SCRIPT="scripts/large-models/plan-large-model.sh"
EXPECTED_REPO="/data/services/mixed-memory-llm-api-server"
EXPECTED_HOSTNAME="llmserver"

required_files=(
  "$REPORT"
  "$DOC"
  docs/model-matrix.md
  docs/current-state.md
  ROADMAP.md
  "$PLAN_SCRIPT"
)

for path in "${required_files[@]}"; do
  [[ -f "$path" ]] || fail "$path missing"
  echo "PASS: exists: $path"
done

[[ -x "$PLAN_SCRIPT" ]] || fail "$PLAN_SCRIPT is not executable"
grep -q 'set -euo pipefail' "$PLAN_SCRIPT" || fail "$PLAN_SCRIPT missing strict shell mode"

for text in \
  'MiniMaxAI/MiniMax-M3-MXFP8' \
  'KTransformers/KT-Kernel plus SGLang' \
  'Qwen/Qwen3-235B-A22B-Instruct-2507-FP8' \
  'M9E' \
  'M10 API/front-door/auth'; do
  grep -Fq "$text" "$REPORT" "$DOC" docs/model-matrix.md docs/current-state.md ROADMAP.md || fail "missing required planning text: $text"
done

grep -Fq 'No large model is downloaded in M9D' "$DOC" || fail "large-model doc must state no download in M9D"
grep -Fq 'no backend/runtime is installed or built' "$DOC" || fail "large-model doc must state no runtime install/build in M9D"
grep -Fq '16,581` prompt characters / `3,518` prompt tokens' "$DOC" || fail "large-model doc missing M9C context correction"
grep -Fq 'Boot persistence remains a later milestone' "$REPORT" || fail "report missing boot persistence note"
grep -Fq 'PASS for planning' "$REPORT" || fail "report missing PASS for planning"
grep -Fq 'STOP for actual download/deploy until human review' "$REPORT" || fail "report missing STOP for deployment"

if grep -RInE '^[[:space:]]*(sudo -n[[:space:]]+)?docker[[:space:]]+(pull|run|compose[[:space:]]+up)|^[[:space:]]*(huggingface-cli|hf)[[:space:]]+download|snapshot_download|pip[[:space:]]+install|apt(-get)?[[:space:]]+install' scripts/large-models tests/shell/test-large-model-plan-static.sh | grep -v 'grep -RInE'; then
  fail "large-model scripts/tests contain executable download, image pull, container start, or install command"
fi

if grep -RInE '(^|[[:space:]])0\.0\.0\.0(:[0-9]+)?|[0-9]+:30000:30000' scripts/large-models; then
  fail "large-model scripts contain public bind pattern"
fi

secret_matches="$(grep -RInE '(HF_TOKEN=[A-Za-z0-9_./+:-]{8,}|OPENAI_API_KEY=[A-Za-z0-9_./+:-]{8,}|GITHUB_TOKEN=[A-Za-z0-9_./+:-]{8,}|BEGIN OPENSSH|BEGIN RSA|PRIVATE KEY)' scripts/large-models "$DOC" "$REPORT" | grep -v 'grep -RInE' || true)"
if [[ -n "$secret_matches" ]]; then
  echo "$secret_matches" >&2
  fail "secret-like content found"
fi

if [[ "${LARGE_MODEL_PLAN_SKIP_HOST_CHECKS:-0}" == "1" ]]; then
  echo "SKIP: host checks skipped by LARGE_MODEL_PLAN_SKIP_HOST_CHECKS=1 for static tests only"
else
  [[ "$(hostname)" == "$EXPECTED_HOSTNAME" ]] || fail "unexpected hostname: $(hostname)"
  [[ "$(pwd)" == "$EXPECTED_REPO" ]] || fail "unexpected repo path: $(pwd)"
  scripts/common/require-data-mounted.sh
  scripts/common/root-disk-guard.sh --report /tmp/root-disk-guard-m9d-large-model-verify.md
  M4_REPORT_PATH=/tmp/m9d-docker-storage-verify.md scripts/docker/verify-docker-storage.sh
  nvidia-smi --query-gpu=index,name,memory.total,driver_version --format=csv,noheader | grep -q 'NVIDIA RTX PRO 6000 Blackwell Workstation Edition' || fail "GPU inventory check failed"
  active="$(scripts/llmctl active)"
  echo "$active"
  grep -q '^active: active$' <<<"$active" || fail "active model is not active"
  grep -q '^model_profile: qwen3-30b-a3b-instruct-2507$' <<<"$active" || fail "unexpected active model"
  grep -q '^endpoint: http://127.0.0.1:30001/v1$' <<<"$active" || fail "unexpected active endpoint"
  grep -q '^live_endpoint_models: ok$' <<<"$active" || fail "active endpoint is not ok"
  scripts/llmctl status | grep -q '^manager_status: active$' || fail "manager status is not active"
fi

echo "PASS: large-model plan verification passed"
