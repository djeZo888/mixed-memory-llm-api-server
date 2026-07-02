#!/usr/bin/env bash
set -euo pipefail

REPORT_PATH="${M4_REPORT_PATH:-reports/m4-docker-containerd-storage.md}"
DOCKER_DATA_ROOT="/data/docker"
CONTAINERD_DATA_ROOT="/data/containerd"
DOCKER_PACKAGES=(
  docker-ce
  docker-ce-cli
  containerd.io
  docker-buildx-plugin
  docker-compose-plugin
)

usage() {
  cat <<'EOF'
Usage: scripts/docker/install-docker.sh [--help] [--dry-run] [--yes-install-docker]

Plan or perform Docker Engine installation using Docker's official Ubuntu apt
repository method.

Modes:
  --help                 Show this help text.
  --dry-run              Print the planned commands and safety checks only.
  --yes-install-docker   Perform the install. Refuses to run without this flag.

Safety:
  Actual installation requires /data to be mounted and the root-disk guard to
  pass before any package or repository work. This script does not add the user
  to the docker group and does not configure GPU container runtime support.
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
  --yes-install-docker)
    mode="install"
    ;;
  "")
    usage >&2
    echo "STOP: refusing Docker installation without --yes-install-docker" >&2
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

print_plan() {
  cat <<EOF
M4 Docker install plan

This is the planned M4B installation path. No commands are executed in dry-run mode.

Official method:
- Use Docker's official Ubuntu apt repository.
- Install packages: ${DOCKER_PACKAGES[*]}
- Do not use shortcut installer scripts.
- Do not add user accounts to the docker group by default.
- Do not configure GPU container runtime support in M4.
- Planned Docker data-root after configuration: $DOCKER_DATA_ROOT
- Planned containerd persistent root after configuration: $CONTAINERD_DATA_ROOT/root

Pre-install required checks:
- scripts/common/require-data-mounted.sh
- scripts/common/root-disk-guard.sh

Planned repository and install steps:
1. Verify /data mount and root-disk guard.
2. Verify base tools exist: apt-get, curl, gpg, dpkg, install, tee.
3. Create /etc/apt/keyrings if needed.
4. Install Docker apt signing key from https://download.docker.com/linux/ubuntu/gpg.
5. Write Docker apt source for the detected Ubuntu codename and architecture.
6. apt-get update.
7. apt-get install: ${DOCKER_PACKAGES[*]}
8. Run scripts/docker/configure-docker-data-root.sh before using Docker for images.

Report path for actual install: $REPORT_PATH
EOF
}

append_report_header() {
  mkdir -p "$(dirname "$REPORT_PATH")"
  cat >> "$REPORT_PATH" <<EOF

## Docker Engine Install

- Timestamp: $(date -Is)
- Hostname: $(hostname 2>/dev/null || printf unknown)
- User: $(whoami 2>/dev/null || printf unknown)
- Branch: $(git branch --show-current 2>/dev/null || printf unknown)
EOF
}

run_logged() {
  local label="$1"
  shift
  {
    printf '\n### %s\n\n' "$label"
    printf '```console\n'
    printf '$'
    printf ' %q' "$@"
    printf '\n'
    set +e
    "$@" 2>&1
    local status=$?
    set -e
    printf '\n[exit=%s]\n' "$status"
    printf '```\n'
    return "$status"
  } >> "$REPORT_PATH"
}

if [[ "$mode" == "dry-run" ]]; then
  print_plan
  exit 0
fi

cd "$(repo_root)"

scripts/common/require-data-mounted.sh
scripts/common/root-disk-guard.sh

for command_name in apt-get curl gpg dpkg install tee; do
  require_command "$command_name"
done

source /etc/os-release
codename="${VERSION_CODENAME:-}"
[[ -n "$codename" ]] || {
  echo "STOP: could not determine Ubuntu VERSION_CODENAME" >&2
  exit 1
}
arch=$(dpkg --print-architecture)

append_report_header
run_logged "pre-install root-disk guard" scripts/common/root-disk-guard.sh
run_logged "create Docker apt keyring directory" sudo -n install -m 0755 -d /etc/apt/keyrings
run_logged "install Docker apt signing key" sudo -n bash -c 'curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg'
run_logged "set Docker apt key permissions" sudo -n chmod a+r /etc/apt/keyrings/docker.gpg
run_logged "write Docker apt source" sudo -n bash -c "printf '%s\n' 'deb [arch=${arch} signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu ${codename} stable' > /etc/apt/sources.list.d/docker.list"
run_logged "apt update for Docker repository" sudo -n apt-get update
run_logged "install Docker Engine packages" sudo -n apt-get install -y "${DOCKER_PACKAGES[@]}"
run_logged "post-install root-disk guard" scripts/common/root-disk-guard.sh

cat <<EOF
PASS: Docker Engine packages installed. Configure /data storage before pulling images or running containers.
EOF
