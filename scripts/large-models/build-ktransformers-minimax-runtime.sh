#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/large-models/build-ktransformers-minimax-runtime.sh --dry-run
       scripts/large-models/build-ktransformers-minimax-runtime.sh --yes-build-runtime

Build the isolated M9E MiniMax-M3 runtime image. The real build is intentionally
gated behind --yes-build-runtime. This script does not install host packages,
does not install into system Python, does not download model weights, does not
modify Docker/containerd daemon configuration, and does not start a model
backend service.

Environment overrides:
  MINIMAX_RUNTIME_IMAGE          image tag to build
  MINIMAX_RUNTIME_BASE_IMAGE     pinned base image
  KT_KERNEL_VERSION              kt-kernel package version
  SGLANG_KT_VERSION              sglang-kt package version
  KTRANSFORMERS_COMMIT           ktransformers main commit recorded in image
USAGE
}

fail() {
  echo "STOP: $*" >&2
  exit 1
}

repo_root() {
  git rev-parse --show-toplevel 2>/dev/null || pwd
}

mode=""
for arg in "$@"; do
  case "$arg" in
    --help|-h)
      usage
      exit 0
      ;;
    --dry-run)
      [[ -z "$mode" ]] || fail "choose only one mode"
      mode="dry-run"
      ;;
    --yes-build-runtime)
      [[ -z "$mode" ]] || fail "choose only one mode"
      mode="build"
      ;;
    *)
      fail "unknown argument: $arg"
      ;;
  esac
done

[[ -n "$mode" ]] || fail "pass --dry-run or --yes-build-runtime"

cd "$(repo_root)"

dockerfile="configs/docker/Dockerfile.ktransformers-minimax-m3"
[[ -f "$dockerfile" ]] || fail "missing Dockerfile: $dockerfile"

image_tag="${MINIMAX_RUNTIME_IMAGE:-local/minimax-m3-ktransformers:0.6.3-post1}"
base_image="${MINIMAX_RUNTIME_BASE_IMAGE:-nvidia/cuda:13.2.1-base-ubuntu24.04}"
kt_kernel_version="${KT_KERNEL_VERSION:-0.6.3.post1}"
sglang_kt_version="${SGLANG_KT_VERSION:-0.6.3.post1}"
ktransformers_source_url="${KTRANSFORMERS_SOURCE_URL:-https://github.com/kvcache-ai/ktransformers.git}"
ktransformers_commit="${KTRANSFORMERS_COMMIT:-cb9f47d142a507cac5d74450b30463d2e8d1cf58}"
build_root="${MINIMAX_BUILD_ROOT:-/data/build/ktransformers-minimax-m3}"
record_file="$build_root/runtime-build-latest.md"

cat_plan() {
  cat <<PLAN
M9E MiniMax-M3 runtime build plan
mode: $mode
image: $image_tag
base_image: $base_image
dockerfile: $dockerfile
ktransformers_source_url: $ktransformers_source_url
ktransformers_commit: $ktransformers_commit
kt_kernel_version: $kt_kernel_version
sglang_kt_version: $sglang_kt_version
build_root: $build_root
pip_cache_root: /data/build/pip-cache
model_download_performed: false
fallback_model_download_performed: false
host_python_install_performed: false
host_cuda_toolkit_install_performed: false
docker_daemon_change_performed: false
docker_prune_performed: false
backend_container_started: false
PLAN
}

cat_plan

if [[ "$mode" == "dry-run" ]]; then
  exit 0
fi

[[ "$(hostname)" == "llmserver" ]] || fail "hostname is $(hostname), expected llmserver"
[[ "$(pwd)" == "/data/services/mixed-memory-llm-api-server" ]] || fail "unexpected repo path: $(pwd)"
command -v sudo >/dev/null 2>&1 || fail "sudo missing"
sudo -n true || fail "sudo -n is not available"
command -v docker >/dev/null 2>&1 || fail "docker missing"

scripts/common/require-data-mounted.sh
scripts/common/root-disk-guard.sh --report /tmp/root-disk-guard-before-minimax-runtime-build.md
M4_REPORT_PATH=/tmp/minimax-runtime-build-docker-storage.md scripts/docker/verify-docker-storage.sh

mkdir -p "$build_root" /data/build/pip-cache /data/logs/minimax-m3-poc

timestamp="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
tmp_record="$(mktemp)"
trap 'rm -f "$tmp_record"' EXIT

{
  echo "# M9E MiniMax-M3 Runtime Build Record"
  echo
  echo "- Timestamp: \`$timestamp\`"
  echo "- Image: \`$image_tag\`"
  echo "- Base image: \`$base_image\`"
  echo "- Dockerfile: \`$dockerfile\`"
  echo "- KTransformers source URL: \`$ktransformers_source_url\`"
  echo "- KTransformers commit: \`$ktransformers_commit\`"
  echo "- kt-kernel package: \`$kt_kernel_version\`"
  echo "- sglang-kt package: \`$sglang_kt_version\`"
  echo "- Build root: \`$build_root\`"
  echo
  echo "## Host GPU Compatibility Snapshot"
  nvidia-smi --query-gpu=index,name,compute_cap,memory.total,driver_version --format=csv,noheader || true
  echo
  echo "## CPU/NUMA Snapshot"
  lscpu | grep -E '^(CPU\(s\)|Thread\(s\) per core|Core\(s\) per socket|Socket\(s\)|NUMA node\(s\))' || true
  echo
  echo "## Docker Build Output"
} >"$tmp_record"

build_log="$build_root/docker-build-$(date -u +%Y%m%dT%H%M%SZ).log"
sudo -n docker build \
  --pull=false \
  --progress=plain \
  --label "org.mixed-memory.milestone=M9E" \
  --label "org.mixed-memory.model=MiniMaxAI/MiniMax-M3-MXFP8" \
  --build-arg "BASE_IMAGE=$base_image" \
  --build-arg "KTRANSFORMERS_SOURCE_URL=$ktransformers_source_url" \
  --build-arg "KTRANSFORMERS_COMMIT=$ktransformers_commit" \
  --build-arg "KT_KERNEL_VERSION=$kt_kernel_version" \
  --build-arg "SGLANG_KT_VERSION=$sglang_kt_version" \
  -f "$dockerfile" \
  -t "$image_tag" \
  . 2>&1 | tee "$build_log"

probe_script="$(cat <<'PROBE'
set -euo pipefail
python3 --version
python3 - <<"PY"
import importlib.metadata as metadata
for dist in ("kt-kernel", "sglang-kt"):
    print(f"{dist}={metadata.version(dist)}")
import kt_kernel
print(f"kt_kernel_module={getattr(kt_kernel, '__file__', 'unknown')}")
print(f"kt_kernel_version={getattr(kt_kernel, '__version__', 'unknown')}")
import sglang
print(f"sglang_module={getattr(sglang, '__file__', 'unknown')}")
import sglang.launch_server
print("sglang.launch_server=import-ok")
PY
nvidia-smi --query-gpu=index,name,compute_cap,memory.total,driver_version --format=csv,noheader
PROBE
)"

{
  sed -n '1,220p' "$build_log"
  echo
  echo "## Image Inspection"
  sudo -n docker image inspect "$image_tag" \
    --format 'id={{.Id}} size={{.Size}} created={{.Created}}' || true
  echo
  echo "## Runtime Metadata Probe"
  sudo -n docker run --rm --gpus all --entrypoint bash "$image_tag" -lc "$probe_script"
} >>"$tmp_record"

mv "$tmp_record" "$record_file"
chmod 0644 "$record_file"

scripts/common/root-disk-guard.sh --report /tmp/root-disk-guard-after-minimax-runtime-build.md
M4_REPORT_PATH=/tmp/minimax-runtime-build-docker-storage-after.md scripts/docker/verify-docker-storage.sh

echo "PASS: runtime image built: $image_tag"
echo "PASS: build record written: $record_file"
