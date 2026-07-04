#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/sglang/plan-sglang-smoke.sh --dry-run

Plan the M8B SGLang + Qwen/Qwen3-0.6B smoke deployment without downloading
models, pulling images, starting containers, modifying Docker/containerd, or
exposing an API. M8A only supports --dry-run.
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

[[ "$DRY_RUN" == "1" ]] || fail "M8A supports dry-run planning only; pass --dry-run"

run_check() {
  echo "+ $*"
  "$@"
}

require_dir() {
  local path="$1"
  [[ -d "$path" ]] || fail "required directory missing: $path"
  echo "PASS: required directory exists: $path"
}

check_port() {
  local port="${SGLANG_PORT:-30000}"
  if command -v ss >/dev/null 2>&1; then
    if ss -H -ltn | awk '{print $4}' | grep -Eq "(^|[:.])${port}$"; then
      fail "port ${port} is already listening; M8B must choose a free localhost port before start"
    fi
    echo "PASS: port ${port} is not currently listening"
  else
    echo "WARN: ss not available; port ${port} conflict check not run"
  fi
}

check_no_active_model() {
  local active status
  active="$(scripts/llmctl active)"
  echo "$active"
  [[ "$active" == "active: none" ]] || fail "llmctl reports an active model/backend"
  status="$(scripts/llmctl status)"
  echo "$status"
  grep -q '^manager_status: planning_only$' <<<"$status" || fail "manager is not in planning_only state"
  grep -q '^active: none$' <<<"$status" || fail "manager status reports an active model/backend"
}

check_docker_runtime() {
  local info
  info="$(sudo -n docker info 2>/dev/null)" || fail "sudo -n docker info failed"
  grep -q 'Docker Root Dir: /data/docker' <<<"$info" || fail "Docker Root Dir is not /data/docker"
  grep -q 'Runtimes:.*nvidia' <<<"$info" || fail "Docker nvidia runtime is not available"
  echo "PASS: Docker Root Dir is /data/docker and nvidia runtime is available"
}

if [[ "${SGLANG_SMOKE_PLAN_SKIP_HOST_CHECKS:-0}" == "1" ]]; then
  echo "SKIP: host checks skipped by SGLANG_SMOKE_PLAN_SKIP_HOST_CHECKS=1 for static tests only"
else
  run_check scripts/common/require-data-mounted.sh
  run_check scripts/common/root-disk-guard.sh
  run_check scripts/docker/verify-docker-storage.sh
  run_check scripts/nvidia/verify-gpu-containers.sh
  run_check scripts/llmctl validate
  require_dir /data/models
  require_dir /data/hf-cache
  require_dir /data/logs
  check_docker_runtime
  check_no_active_model
  check_port
fi

cat <<'PLAN'
PLAN: M8B SGLang smoke deployment sequence, not executed in M8A
model_profile: qwen3-0.6b-smoke
runtime_profile: sglang
hf_repo: Qwen/Qwen3-0.6B
local_model_path: /data/models/qwen3-0.6b-smoke
hf_cache_root: /data/hf-cache
log_dir: /data/logs/sglang-smoke
bind_address: 127.0.0.1
container_host: 0.0.0.0 inside container only
port: 30000
compose_template: configs/compose/compose.sglang-smoke.template.yml
proposed_sglang_image: lmsysorg/sglang:v0.5.14-cu130-runtime

planned_m8b_steps:
  1. create /data/models/qwen3-0.6b-smoke
  2. download Qwen/Qwen3-0.6B to the local model path only
  3. pull the human-approved pinned SGLang Docker image
  4. start Docker Compose profile sglang-smoke on 127.0.0.1:30000
  5. wait for readiness and verify /health or documented readiness output
  6. run OpenAI-compatible smoke requests at /v1/chat/completions
  7. record logs under /data/logs/sglang-smoke
  8. stop/deactivate cleanly and leave only approved state

m8a_execution: dry_run_only
model_download_performed: false
image_pull_performed: false
container_started: false
api_exposed: false
PLAN
