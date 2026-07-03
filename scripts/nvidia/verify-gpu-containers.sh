#!/usr/bin/env bash
set -euo pipefail

EXPECTED_GPU_COUNT=2
EXPECTED_GPU_NAME="NVIDIA RTX PRO 6000 Blackwell Workstation Edition"
EXPECTED_DOCKER_ROOT="/data/docker"
EXPECTED_CONTAINERD_ROOT="/data/containerd/root"
EXPECTED_CONTAINERD_STATE="/run/containerd"
DOCKER_DAEMON_JSON="/etc/docker/daemon.json"
CONTAINERD_CONFIG="/etc/containerd/config.toml"
DEFAULT_CUDA_TEST_IMAGE="nvidia/cuda:13.2.0-base-ubuntu24.04"
TOOLKIT_PACKAGES=(
  nvidia-container-toolkit
  nvidia-container-toolkit-base
  libnvidia-container-tools
  libnvidia-container1
)

cuda_test_image="$DEFAULT_CUDA_TEST_IMAGE"
run_cuda_test=0

usage() {
  cat <<'EOF'
Usage: scripts/nvidia/verify-gpu-containers.sh [--help] [--approved-cuda-test-image IMAGE] [--yes-run-cuda-test]

Verify host GPU/container runtime readiness.

M6A behavior:
  The script is read-only and is expected to report STOP while NVIDIA Container
  Toolkit is not installed.

M6B behavior:
  After human approval and toolkit installation, pass an explicit approved CUDA
  image and --yes-run-cuda-test to run the GPU container nvidia-smi test.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --help)
      usage
      exit 0
      ;;
    --approved-cuda-test-image)
      [[ $# -ge 2 ]] || { echo "STOP: --approved-cuda-test-image requires a value" >&2; exit 2; }
      cuda_test_image="$2"
      shift 2
      ;;
    --yes-run-cuda-test)
      run_cuda_test=1
      shift
      ;;
    *)
      usage >&2
      echo "STOP: unknown option: $1" >&2
      exit 2
      ;;
  esac
done

repo_root() {
  git rev-parse --show-toplevel 2>/dev/null || pwd
}

stop() {
  echo "STOP: $*" >&2
  exit 1
}

require_command() {
  local command_name="$1"
  command -v "$command_name" >/dev/null 2>&1 || stop "required command missing: $command_name"
}

check_no_latest_image() {
  if [[ "$cuda_test_image" == *:latest || "$cuda_test_image" != *:* ]]; then
    stop "approved CUDA test image must use an explicit non-latest tag"
  fi
}

check_no_docker_tcp_exposure() {
  local hits
  hits=$(
    {
      sudo -n grep -RInE 'tcp://|0\.0\.0\.0:[0-9]+|2375|2376' "$DOCKER_DAEMON_JSON" /etc/systemd/system/docker.service.d /etc/systemd/system/docker.socket.d 2>/dev/null || true
      sudo -n systemctl cat docker docker.socket 2>/dev/null | grep -nE 'tcp://|0\.0\.0\.0:[0-9]+|2375|2376' || true
    } | grep -v 'Documentation=' || true
  )
  if [[ -n "$hits" ]]; then
    echo "$hits" >&2
    stop "Docker TCP socket exposure detected"
  fi
}

package_installed() {
  dpkg-query -W -f='${Status}' "$1" 2>/dev/null | grep -qx 'install ok installed'
}

cd "$(repo_root)"
check_no_latest_image

require_command nvidia-smi
require_command docker
require_command dpkg-query

scripts/common/require-data-mounted.sh
scripts/common/root-disk-guard.sh
scripts/docker/verify-docker-storage.sh

nvidia-smi >/dev/null
host_gpu_count=$(nvidia-smi -L | grep -c '^GPU ')
[[ "$host_gpu_count" == "$EXPECTED_GPU_COUNT" ]] || stop "host GPU count is $host_gpu_count, expected $EXPECTED_GPU_COUNT"

host_gpu_summary=$(nvidia-smi --query-gpu=index,name,pci.bus_id,driver_version,memory.total,power.limit --format=csv,noheader)
echo "Host GPU summary:"
echo "$host_gpu_summary"
if [[ "$(printf '%s\n' "$host_gpu_summary" | grep -c "$EXPECTED_GPU_NAME")" != "$EXPECTED_GPU_COUNT" ]]; then
  stop "host GPU names do not all match $EXPECTED_GPU_NAME"
fi

docker_root=$(sudo -n docker info --format '{{.DockerRootDir}}' 2>/dev/null || true)
[[ "$docker_root" == "$EXPECTED_DOCKER_ROOT" ]] || stop "Docker Root Dir is ${docker_root:-unknown}, expected $EXPECTED_DOCKER_ROOT"
sudo -n grep -Fxq "root = \"$EXPECTED_CONTAINERD_ROOT\"" "$CONTAINERD_CONFIG" || stop "containerd root is not $EXPECTED_CONTAINERD_ROOT"
sudo -n grep -Fxq "state = \"$EXPECTED_CONTAINERD_STATE\"" "$CONTAINERD_CONFIG" || stop "containerd state is not $EXPECTED_CONTAINERD_STATE"

missing_packages=()
for package in "${TOOLKIT_PACKAGES[@]}"; do
  if ! package_installed "$package"; then
    missing_packages+=("$package")
  fi
done
if [[ "${#missing_packages[@]}" -gt 0 ]]; then
  echo "NVIDIA Container Toolkit packages missing: ${missing_packages[*]}" >&2
  stop "NVIDIA Container Toolkit is not installed yet; expected STOP during M6A"
fi

command -v nvidia-ctk >/dev/null 2>&1 || stop "nvidia-ctk is not available"

runtime_json=$(sudo -n docker info --format '{{json .Runtimes}}' 2>/dev/null || true)
echo "$runtime_json" | grep -q '"nvidia"' || stop "Docker nvidia runtime is not available"
sudo -n grep -Fq "\"data-root\": \"$EXPECTED_DOCKER_ROOT\"" "$DOCKER_DAEMON_JSON" || stop "$DOCKER_DAEMON_JSON does not preserve data-root $EXPECTED_DOCKER_ROOT"
sudo -n grep -q '"nvidia"' "$DOCKER_DAEMON_JSON" || stop "$DOCKER_DAEMON_JSON does not contain nvidia runtime configuration"
check_no_docker_tcp_exposure

if [[ "$run_cuda_test" != "1" ]]; then
  stop "M6B CUDA container test requires --yes-run-cuda-test after human approval"
fi

container_output=$(mktemp)
sudo -n docker run --rm --gpus all "$cuda_test_image" nvidia-smi | tee "$container_output"
container_query=$(sudo -n docker run --rm --gpus all "$cuda_test_image" nvidia-smi --query-gpu=index,name,pci.bus_id,driver_version,memory.total,power.limit --format=csv,noheader)
echo "Container GPU summary:"
echo "$container_query"
container_gpu_count=$(printf '%s\n' "$container_query" | grep -c "$EXPECTED_GPU_NAME" || true)
[[ "$container_gpu_count" == "$EXPECTED_GPU_COUNT" ]] || stop "container GPU count/name check failed"
[[ "$(printf '%s\n' "$container_query" | grep -c '97887 MiB')" == "$EXPECTED_GPU_COUNT" ]] || stop "container VRAM check did not find expected 97887 MiB GPUs"

scripts/common/root-disk-guard.sh
sudo -n du -sh /var/lib/docker /var/lib/containerd "$EXPECTED_DOCKER_ROOT" /data/containerd "$EXPECTED_CONTAINERD_ROOT" 2>/dev/null || true
scripts/docker/verify-docker-storage.sh

echo "PASS: GPU container verification passed with $cuda_test_image"
