#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/sglang/plan-sglang-real-fast.sh --dry-run

Plan the M9B first real SGLang fast-model deployment without downloading
models, pulling images, starting containers, stopping smoke, modifying
Docker/containerd, or exposing an API. M9A only supports --dry-run.
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

[[ "$DRY_RUN" == "1" ]] || fail "M9A supports planning only; pass --dry-run"

run_check() {
  echo "+ $*"
  "$@"
}

require_dir() {
  local path="$1"
  [[ -d "$path" ]] || fail "required directory missing: $path"
  echo "PASS: required directory exists: $path"
}

check_active_smoke() {
  local active status
  active="$(scripts/llmctl active)"
  echo "$active"
  grep -q '^active: active$' <<<"$active" || fail "smoke deployment is not active"
  grep -q '^model_profile: qwen3-0.6b-smoke$' <<<"$active" || fail "unexpected active model"
  grep -q '^runtime_profile: sglang$' <<<"$active" || fail "unexpected active runtime"
  grep -q '^bind: 127.0.0.1$' <<<"$active" || fail "active smoke bind is not localhost-only"
  grep -q '^port: 30000$' <<<"$active" || fail "active smoke is not on port 30000"
  grep -q '^live_container_health: healthy$' <<<"$active" || fail "active smoke container is not healthy"
  grep -q '^live_endpoint_models: ok$' <<<"$active" || fail "active smoke /v1/models check is not ok"

  status="$(scripts/llmctl status)"
  echo "$status"
  grep -q '^manager_status: active$' <<<"$status" || fail "manager is not active"
  grep -q '^active_status: active$' <<<"$status" || fail "active status is not active"
}

check_real_model_absent() {
  local model_path="/data/models/qwen3-30b-a3b-instruct-2507"
  if [[ -e "$model_path" ]]; then
    fail "first real model path already exists: $model_path"
  fi
  echo "PASS: first real model path is not present: $model_path"
}

check_plan_files() {
  local required=(
    configs/models/profiles/qwen3-30b-a3b-instruct-2507.yaml
    configs/models/profiles/qwen3.6-35b-a3b.yaml
    configs/models/profiles/qwen3-30b-a3b-thinking-2507.yaml
    configs/compose/compose.sglang-qwen3-30b.template.yml
    configs/sglang/qwen3-30b.env.example
    docs/sglang-first-real-model.md
    reports/m9a-first-real-fast-model-plan.md
  )
  local path
  for path in "${required[@]}"; do
    [[ -f "$path" ]] || fail "required plan artifact missing: $path"
    echo "PASS: plan artifact exists: $path"
  done
}

if [[ "${SGLANG_REAL_FAST_PLAN_SKIP_HOST_CHECKS:-0}" == "1" ]]; then
  echo "SKIP: host checks skipped by SGLANG_REAL_FAST_PLAN_SKIP_HOST_CHECKS=1 for static tests only"
else
  run_check scripts/common/require-data-mounted.sh
  run_check scripts/common/root-disk-guard.sh --report /tmp/root-disk-guard-m9a-real-fast-plan.md
  echo "+ M4_REPORT_PATH=/tmp/m9a-docker-storage-plan.md scripts/docker/verify-docker-storage.sh"
  M4_REPORT_PATH=/tmp/m9a-docker-storage-plan.md scripts/docker/verify-docker-storage.sh
  run_check scripts/llmctl validate
  require_dir /data/models
  require_dir /data/hf-cache
  require_dir /data/logs
  check_active_smoke
  check_real_model_absent
fi

check_plan_files

cat <<'PLAN'
PLAN: M9B first real fast-model deployment sequence, not executed in M9A
primary_model_profile: qwen3-30b-a3b-instruct-2507
primary_hf_repo: Qwen/Qwen3-30B-A3B-Instruct-2507
fallback_model: Qwen/Qwen3-Coder-30B-A3B-Instruct for coding-specific fallback after human review
runtime_profile: sglang
local_model_path: /data/models/qwen3-30b-a3b-instruct-2507
hf_cache_root: /data/hf-cache
log_dir: /data/logs/sglang-qwen3-30b-a3b-instruct-2507
planned_bind: 127.0.0.1
planned_host_port: 30001
container_port: 30000
endpoint: http://127.0.0.1:30001/v1
compose_template: configs/compose/compose.sglang-qwen3-30b.template.yml
planned_sglang_image: lmsysorg/sglang:v0.5.14-cu130
initial_context_length: 32768
initial_max_running_requests: 1
initial_mem_fraction_static: 0.70

planned_m9b_steps:
  1. rerun storage, Docker, GPU, llmctl, and smoke health guards
  2. stop smoke through scripts/llmctl stop --yes only after human approval
  3. download Qwen/Qwen3-30B-A3B-Instruct-2507 to /data/models/qwen3-30b-a3b-instruct-2507 only
  4. use /data/hf-cache for Hugging Face cache and /data/logs for logs
  5. verify or pull the approved pinned SGLang image only after human approval
  6. start the real SGLang profile on 127.0.0.1:30001
  7. run /v1/models and non-streaming and streaming chat tests
  8. validate root disk, Docker storage, GPU container support, and active manager state
  9. if startup or health fails, stop the real profile, keep model files for review, and either restart smoke or leave no active backend based on human instruction

m9a_execution: dry_run_only
smoke_stop_performed: false
model_download_performed: false
image_pull_performed: false
container_started: false
api_exposed: false
PLAN
