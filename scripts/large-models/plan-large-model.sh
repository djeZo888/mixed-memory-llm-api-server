#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/large-models/plan-large-model.sh --dry-run

Plan the M9E large-model proof-of-life sequence without downloading models,
pulling images, installing/building runtimes, starting containers, stopping the
current active model, modifying Docker/containerd, or exposing an API.

M9D supports planning only and refuses non-dry-run execution.
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

[[ "$DRY_RUN" == "1" ]] || fail "M9D supports planning only; pass --dry-run"

REPORT="reports/m9d-large-model-feasibility-plan.md"
DOC="docs/large-model-feasibility.md"
EXPECTED_HOSTNAME="llmserver"
EXPECTED_REPO="/data/services/mixed-memory-llm-api-server"

run_check() {
  echo "+ $*"
  "$@"
}

report_value() {
  local label="$1"
  grep -E "^- ${label}:" "$REPORT" | head -n 1 | sed "s/^- ${label}: //" | sed -E 's/^`//; s/`[.]?$//; s/[.]$//'
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
  summary="$(nvidia-smi --query-gpu=index,name,memory.total,driver_version --format=csv,noheader)"
  echo "$summary"
  count="$(printf '%s\n' "$summary" | grep -c 'NVIDIA RTX PRO 6000 Blackwell Workstation Edition' || true)"
  [[ "$count" == "2" ]] || fail "expected two RTX PRO 6000 Blackwell GPUs"
  echo "PASS: GPU inventory verified without starting containers"
}

check_active_real_model() {
  local active status models
  active="$(scripts/llmctl active)"
  echo "$active"
  grep -q '^active: active$' <<<"$active" || fail "active model is not active"
  grep -q '^model_profile: qwen3-30b-a3b-instruct-2507$' <<<"$active" || fail "unexpected active model"
  grep -q '^runtime_profile: sglang$' <<<"$active" || fail "unexpected active runtime"
  grep -q '^bind: 127.0.0.1$' <<<"$active" || fail "active bind is not localhost-only"
  grep -q '^port: 30001$' <<<"$active" || fail "active endpoint is not on port 30001"
  grep -q '^live_container_status: running$' <<<"$active" || fail "active container is not running"
  grep -q '^live_endpoint_models: ok$' <<<"$active" || fail "active /v1/models is not ok"

  status="$(scripts/llmctl status)"
  echo "$status"
  grep -q '^manager_status: active$' <<<"$status" || fail "manager status is not active"

  models="$(curl -fsS http://127.0.0.1:30001/v1/models)"
  grep -q 'qwen3-30b-a3b-instruct-2507' <<<"$models" || fail "current endpoint did not return served model"
  echo "PASS: current active real model status verified"
}

check_plan_artifacts() {
  local path
  for path in "$REPORT" "$DOC" docs/model-matrix.md docs/current-state.md ROADMAP.md; do
    [[ -f "$path" ]] || fail "required planning artifact missing: $path"
    echo "PASS: planning artifact exists: $path"
  done
  grep -Fq 'STOP for actual download/deploy until human review' "$REPORT" || fail "report missing STOP conclusion"
  grep -Fq 'MiniMaxAI/MiniMax-M3-MXFP8' "$REPORT" || fail "report missing recommended candidate"
  grep -Fq 'Qwen/Qwen3-235B-A22B-Instruct-2507-FP8' "$REPORT" || fail "report missing fallback candidate"
}

if [[ "${LARGE_MODEL_PLAN_SKIP_HOST_CHECKS:-0}" == "1" ]]; then
  echo "SKIP: host checks skipped by LARGE_MODEL_PLAN_SKIP_HOST_CHECKS=1 for static tests only"
else
  check_identity
  run_check scripts/common/require-data-mounted.sh
  run_check scripts/common/root-disk-guard.sh --report /tmp/root-disk-guard-m9d-large-model-plan.md
  echo "+ M4_REPORT_PATH=/tmp/m9d-docker-storage-plan.md scripts/docker/verify-docker-storage.sh"
  M4_REPORT_PATH=/tmp/m9d-docker-storage-plan.md scripts/docker/verify-docker-storage.sh
  check_gpu_inventory
  check_active_real_model
fi

check_plan_artifacts

recommended="$(report_value 'Recommended first large proof-of-life model')"
runtime="$(report_value 'Recommended runtime path')"
fallback="$(report_value 'Fallback candidate')"

cat <<PLAN
PLAN: M9E large-model proof-of-life sequence, not executed in M9D
recommended_first_large_model: ${recommended:-MiniMaxAI/MiniMax-M3-MXFP8}
recommended_runtime_path: ${runtime:-KTransformers/KT-Kernel plus SGLang heterogeneous CPU/GPU serving}
fallback_model: ${fallback:-Qwen/Qwen3-235B-A22B-Instruct-2507-FP8}
current_model_kept_running_until_m9e: true
current_endpoint_preserved: http://127.0.0.1:30001/v1
recommended_first_context_tokens: 8192
recommended_large_proof_bind: 127.0.0.1
recommended_large_proof_port: 30002
expected_model_storage: about 443.75 GB decimal / 413.27 GiB for MiniMaxAI/MiniMax-M3-MXFP8
expected_data_reserve: 500-650 GB on /data for model, cache, build artifacts, and logs
expected_vram_ram_risk: high; requires CPU/GPU expert offload and cannot run concurrently with current 30B

planned_m9e_steps:
  1. human reviews reports/m9d-large-model-feasibility-plan.md
  2. sync clean main and verify llmserver plus /data/services/mixed-memory-llm-api-server
  3. run storage, root-disk, Docker, GPU, and active-model guards
  4. stop the current 30B backend only after explicit human approval
  5. download exactly one approved large model to /data/models with cache under /data/hf-cache
  6. install or build only the approved runtime path under /data/build or an approved container strategy
  7. start one localhost-only large proof backend on a distinct proof port
  8. run /v1/models, non-streaming chat, streaming chat, and resource snapshots
  9. if compatibility is unclear or health fails, stop and document uncertainty before further action
  10. rollback by stopping the large proof backend and restarting the 30B backend only with human approval

m9d_execution: dry_run_only
large_model_download_performed: false
docker_image_pull_performed: false
runtime_install_performed: false
runtime_build_performed: false
model_backend_container_started: false
current_active_model_stopped_or_restarted: false
api_exposed: false
public_bind_performed: false
PLAN
