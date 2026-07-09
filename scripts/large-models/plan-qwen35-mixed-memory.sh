#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/large-models/plan-qwen35-mixed-memory.sh --dry-run

Plan the M9G/M9H Qwen3.5 mixed-memory sequence without downloading models,
pulling images, installing packages, building runtimes, starting containers,
stopping the current active model, modifying Docker/containerd, or exposing an API.

M9F is planning only and refuses non-dry-run execution.
USAGE
}

fail() {
  echo "STOP: $*" >&2
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

[[ "$DRY_RUN" == "1" ]] || fail "M9F supports planning only; pass --dry-run"

EXPECTED_HOSTNAME="llmserver"
EXPECTED_REPO="/data/services/mixed-memory-llm-api-server"
REPORT="reports/m9f-offline-resilience-mixed-memory-plan.md"

run_check() {
  echo "+ $*"
  "$@"
}

check_identity() {
  local host repo
  host="$(hostname)"
  [[ "$host" == "$EXPECTED_HOSTNAME" ]] || fail "hostname is $host, expected $EXPECTED_HOSTNAME"
  repo="$(pwd)"
  [[ "$repo" == "$EXPECTED_REPO" ]] || fail "pwd is $repo, expected $EXPECTED_REPO"
  echo "PASS: host and repo path verified"
}

check_gpu_inventory() {
  command -v nvidia-smi >/dev/null 2>&1 || fail "nvidia-smi missing"
  local summary count
  summary="$(nvidia-smi --query-gpu=index,name,compute_cap,memory.total,driver_version --format=csv,noheader)"
  echo "$summary"
  count="$(printf '%s\n' "$summary" | grep -c 'NVIDIA RTX PRO 6000 Blackwell Workstation Edition' || true)"
  [[ "$count" == "2" ]] || fail "expected two RTX PRO 6000 Blackwell GPUs"
  grep -q ', 12\.0,' <<<"$summary" || fail "expected compute capability 12.0 / SM120"
  echo "PASS: GPU inventory verified without starting containers"
}

check_active_30b() {
  local active status
  active="$(scripts/llmctl active)"
  echo "$active"
  grep -q '^active: active$' <<<"$active" || fail "active model is not active"
  grep -q '^model_profile: qwen3-30b-a3b-instruct-2507$' <<<"$active" || fail "unexpected active model"
  grep -q '^runtime_profile: sglang$' <<<"$active" || fail "unexpected active runtime"
  grep -q '^bind: 127\.0\.0\.1$' <<<"$active" || fail "active bind is not localhost-only"
  grep -q '^port: 30001$' <<<"$active" || fail "active endpoint is not on port 30001"
  grep -q '^live_container_status: running$' <<<"$active" || fail "active container is not running"
  grep -q '^live_endpoint_models: ok$' <<<"$active" || fail "active /v1/models is not ok"

  status="$(scripts/llmctl status)"
  echo "$status"
  grep -q '^manager_status: active$' <<<"$status" || fail "manager status is not active"
  echo "PASS: current active 30B service verified"
}

check_plan_artifacts() {
  local path
  for path in \
    "$REPORT" \
    docs/offline-resilience-goals.md \
    docs/mixed-memory-large-model-strategy.md \
    docs/memory-rag-architecture.md \
    docs/model-roles.md \
    docs/current-state.md \
    docs/model-matrix.md \
    ROADMAP.md; do
    [[ -f "$path" ]] || fail "required planning artifact missing: $path"
    echo "PASS: planning artifact exists: $path"
  done
  grep -Fq 'PASS for planning only' "$REPORT" || fail "report missing PASS planning conclusion"
  grep -Fq 'STOP for download/build/deploy until human review' "$REPORT" || fail "report missing STOP deployment conclusion"
  grep -Fq 'Qwen/Qwen3.5-397B-A17B-FP8' "$REPORT" || fail "report missing Qwen3.5 FP8 candidate"
}

if [[ "${M9F_PLAN_SKIP_HOST_CHECKS:-0}" == "1" ]]; then
  echo "SKIP: host checks skipped by M9F_PLAN_SKIP_HOST_CHECKS=1 for static tests only"
else
  check_identity
  run_check scripts/common/require-data-mounted.sh
  run_check scripts/common/root-disk-guard.sh --report /tmp/root-disk-guard-m9f-qwen35-plan.md
  echo "+ M4_REPORT_PATH=/tmp/m9f-docker-storage-plan.md scripts/docker/verify-docker-storage.sh"
  M4_REPORT_PATH=/tmp/m9f-docker-storage-plan.md scripts/docker/verify-docker-storage.sh
  check_gpu_inventory
  check_active_30b
fi

check_plan_artifacts

cat <<PLAN
PLAN: M9G/M9H Qwen3.5 mixed-memory sequence, not executed in M9F
mission: offline_resilience_not_cost_saving
next_candidate: Qwen/Qwen3.5-397B-A17B-FP8
current_backend_preserved: Qwen/Qwen3-30B-A3B-Instruct-2507 at http://127.0.0.1:30001/v1
current_backend_stopped_or_restarted: false
recommended_first_context_tokens: 8192
recommended_second_context_tokens: 16384
large_proof_bind_policy: localhost_only
public_api_exposure: false

planned_m9g_preflight:
  1. refresh official Qwen3.5, SGLang, KTransformers, vLLM, and NVIDIA SM120 sources
  2. choose one isolated runtime preflight path for Qwen3.5 FP8
  3. verify SM120 import and kernel gates without Qwen3.5 weights
  4. verify launch help and required flags
  5. keep the active 30B backend running throughout M9G
  6. stop if SM120 gates fail

planned_m9h_proof_after_m9g_pass:
  1. request human approval before model download
  2. download Qwen3.5 FP8 only after runtime preflight passes
  3. keep cache and model files under /data
  4. stop 30B only after download and preflight pass
  5. launch a localhost-only proof endpoint on a distinct port
  6. run /v1/models and one short chat proof
  7. restore 30B if launch or proof fails

m9f_execution: dry_run_only
model_download_performed: false
docker_image_pull_performed: false
runtime_install_performed: false
runtime_build_performed: false
model_backend_container_started: false
current_active_model_stopped_or_restarted: false
api_exposed: false
public_bind_performed: false
PLAN
