#!/usr/bin/env bash
set -euo pipefail

DOCKER_DATA_ROOT="/data/docker"
CONTAINERD_ROOT="/data/containerd/root"
CONTAINERD_STATE="/run/containerd"
DOCKER_DAEMON_JSON="/etc/docker/daemon.json"
CONTAINERD_CONFIG="/etc/containerd/config.toml"
NVIDIA_KEYRING="/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg"
NVIDIA_SOURCE_LIST="/etc/apt/sources.list.d/nvidia-container-toolkit.list"
NVIDIA_STABLE_LIST_URL="https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list"
NVIDIA_GPGKEY_URL="https://nvidia.github.io/libnvidia-container/gpgkey"
NVIDIA_PACKAGES=(
  nvidia-container-toolkit
  nvidia-container-toolkit-base
  libnvidia-container-tools
  libnvidia-container1
)
FORBIDDEN_PACKAGE_PATTERN='(^|[^[:alnum:]_.+-])(cuda|cuda-toolkit|cuda-drivers|nvidia-cuda-toolkit|pytorch|torch|ktransformers|ik_llama|vllm|sglang)([^[:alnum:]_.+-]|$)'

usage() {
  cat <<'EOF'
Usage: scripts/nvidia/install-nvidia-container-toolkit.sh [--help] [--dry-run] [--yes-install-nvidia-container-toolkit]

Plan or perform the future M6B NVIDIA Container Toolkit install for the Docker
runtime only.

Modes:
  --help                                  Show this help text.
  --dry-run                               Print the planned M6B commands only.
  --yes-install-nvidia-container-toolkit  Perform the future M6B install and Docker runtime configuration.

M6A rule:
  Run this script with --dry-run only. Actual package installation, apt source
  creation, nvidia-ctk runtime configuration, and Docker restart are reserved
  for M6B after human review.
EOF
}

mode=""
case "${1:-}" in
  --help)
    usage
    exit 0
    ;;
  --dry-run)
    mode="dry-run"
    ;;
  --yes-install-nvidia-container-toolkit)
    mode="install"
    ;;
  "")
    usage >&2
    echo "STOP: refusing NVIDIA Container Toolkit installation without --yes-install-nvidia-container-toolkit" >&2
    exit 2
    ;;
  *)
    usage >&2
    echo "STOP: unknown option: $1" >&2
    exit 2
    ;;
esac

repo_root() {
  git rev-parse --show-toplevel 2>/dev/null || pwd
}

require_command() {
  local command_name="$1"
  command -v "$command_name" >/dev/null 2>&1 || {
    echo "STOP: required command missing: $command_name" >&2
    exit 1
  }
}

verify_storage_policy() {
  scripts/common/require-data-mounted.sh
  scripts/common/root-disk-guard.sh
  scripts/docker/verify-docker-storage.sh

  local docker_root
  docker_root=$(sudo -n docker info --format '{{.DockerRootDir}}' 2>/dev/null || true)
  [[ "$docker_root" == "$DOCKER_DATA_ROOT" ]] || {
    echo "STOP: Docker Root Dir is ${docker_root:-unknown}, expected $DOCKER_DATA_ROOT" >&2
    exit 1
  }

  sudo -n grep -Fq "\"data-root\": \"$DOCKER_DATA_ROOT\"" "$DOCKER_DAEMON_JSON" || {
    echo "STOP: $DOCKER_DAEMON_JSON does not preserve data-root $DOCKER_DATA_ROOT" >&2
    exit 1
  }
  sudo -n grep -Fxq "root = \"$CONTAINERD_ROOT\"" "$CONTAINERD_CONFIG" || {
    echo "STOP: $CONTAINERD_CONFIG does not preserve containerd root $CONTAINERD_ROOT" >&2
    exit 1
  }
  sudo -n grep -Fxq "state = \"$CONTAINERD_STATE\"" "$CONTAINERD_CONFIG" || {
    echo "STOP: $CONTAINERD_CONFIG does not preserve containerd state $CONTAINERD_STATE" >&2
    exit 1
  }
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
    echo "STOP: Docker TCP socket exposure detected" >&2
    exit 1
  fi
}

validate_docker_daemon_json() {
  sudo -n cat "$DOCKER_DAEMON_JSON" | python3 -m json.tool >/dev/null
}

check_apt_simulation_scope() {
  local simulation_output
  simulation_output=$(mktemp)
  sudo -n apt-get -s install "${NVIDIA_PACKAGES[@]}" >"$simulation_output"
  cat "$simulation_output"

  if grep -Ei "$FORBIDDEN_PACKAGE_PATTERN" "$simulation_output"; then
    echo "STOP: apt simulation proposed out-of-scope package names" >&2
    exit 1
  fi
}

print_plan() {
  cat <<EOF
M6A NVIDIA Container Toolkit dry-run plan

No package installation, apt repository creation, Docker config write, Docker
restart, image pull, or container run is executed in dry-run mode.

Current storage policy to preserve:
- Docker data-root: $DOCKER_DATA_ROOT
- containerd root: $CONTAINERD_ROOT
- containerd state: $CONTAINERD_STATE

Future M6B required pre-checks:
- sudo -n true
- scripts/common/require-data-mounted.sh
- scripts/common/root-disk-guard.sh
- scripts/docker/verify-docker-storage.sh
- nvidia-smi
- sudo -n apt-get -s install ${NVIDIA_PACKAGES[*]}
- STOP if apt simulation proposes CUDA Toolkit, CUDA drivers, PyTorch, KTransformers, ik_llama, vLLM, or SGLang packages.
- Docker Root Dir remains $DOCKER_DATA_ROOT
- containerd root remains $CONTAINERD_ROOT
- Docker has no TCP socket exposure

Future M6B official NVIDIA apt repository method:
- Install key from: $NVIDIA_GPGKEY_URL
- Write keyring: $NVIDIA_KEYRING
- Write source list from: $NVIDIA_STABLE_LIST_URL
- Install packages: ${NVIDIA_PACKAGES[*]}

Future M6B Docker runtime configuration:
- Back up $DOCKER_DAEMON_JSON before runtime configuration.
- Run: sudo nvidia-ctk runtime configure --runtime=docker
- Verify $DOCKER_DAEMON_JSON still contains "data-root": "$DOCKER_DATA_ROOT".
- Verify Docker has no TCP socket exposure.
- Run root-disk guard before and after Docker restart.
- Restart Docker only after config verification.
- Do not configure containerd NVIDIA runtime in M6.

Out of scope for M6A and this script:
- CUDA Toolkit installation.
- PyTorch, KTransformers, or ik_llama installation.
- Model downloads.
- API exposure.
- /etc/containerd/config.toml changes.
EOF
}

if [[ "$mode" == "dry-run" ]]; then
  print_plan
  exit 0
fi

cd "$(repo_root)"

sudo -n true
verify_storage_policy
nvidia-smi >/dev/null
check_no_docker_tcp_exposure

for command_name in apt-get curl gpg sed tee cp date install grep nvidia-smi docker python3 sha256sum; do
  require_command "$command_name"
done

backup_path="${DOCKER_DAEMON_JSON}.pre-m6b-nvidia-container-toolkit.$(date -u +%Y%m%dT%H%M%SZ).bak"
containerd_config_before=$(sudo -n sha256sum "$CONTAINERD_CONFIG" | awk '{print $1}')
sudo -n cp -a "$DOCKER_DAEMON_JSON" "$backup_path"

sudo -n install -m 0755 -d /usr/share/keyrings
curl -fsSL "$NVIDIA_GPGKEY_URL" | sudo -n gpg --dearmor -o "$NVIDIA_KEYRING"
curl -s -L "$NVIDIA_STABLE_LIST_URL" \
  | sed "s#deb https://#deb [signed-by=$NVIDIA_KEYRING] https://#g" \
  | sudo -n tee "$NVIDIA_SOURCE_LIST" >/dev/null

sudo -n apt-get update
check_apt_simulation_scope
sudo -n apt-get install -y "${NVIDIA_PACKAGES[@]}"

command -v nvidia-ctk >/dev/null 2>&1 || {
  echo "STOP: nvidia-ctk is not available after package installation" >&2
  exit 1
}

sudo -n nvidia-ctk runtime configure --runtime=docker

validate_docker_daemon_json
sudo -n grep -Fq "\"data-root\": \"$DOCKER_DATA_ROOT\"" "$DOCKER_DAEMON_JSON" || {
  echo "STOP: $DOCKER_DAEMON_JSON lost data-root $DOCKER_DATA_ROOT after nvidia-ctk configuration" >&2
  echo "Rollback: restore $backup_path, restart Docker, and rerun storage checks." >&2
  exit 1
}
sudo -n grep -q '"nvidia"' "$DOCKER_DAEMON_JSON" || {
  echo "STOP: $DOCKER_DAEMON_JSON does not contain NVIDIA runtime configuration" >&2
  exit 1
}
containerd_config_after=$(sudo -n sha256sum "$CONTAINERD_CONFIG" | awk '{print $1}')
[[ "$containerd_config_before" == "$containerd_config_after" ]] || {
  echo "STOP: $CONTAINERD_CONFIG changed during Docker-only M6B path" >&2
  exit 1
}
check_no_docker_tcp_exposure
scripts/common/root-disk-guard.sh

sudo -n systemctl restart docker

scripts/common/root-disk-guard.sh
scripts/docker/verify-docker-storage.sh
check_no_docker_tcp_exposure

echo "PASS: NVIDIA Container Toolkit installed and Docker runtime configured for future M6B."
echo "Docker daemon.json backup: $backup_path"
