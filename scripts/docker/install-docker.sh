#!/usr/bin/env bash
set -euo pipefail

REPORT_PATH="${M4_REPORT_PATH:-reports/m4b-docker-containerd-install.md}"
DOCKER_KEYRING="/etc/apt/keyrings/docker.asc"
DOCKER_SOURCE="/etc/apt/sources.list.d/docker.sources"
POLICY_RC_D="/usr/sbin/policy-rc.d"
DOCKER_PACKAGES=(
  docker-ce
  docker-ce-cli
  containerd.io
  docker-buildx-plugin
  docker-compose-plugin
)
CONFLICT_PACKAGES=(
  docker.io
  docker-compose
  docker-compose-v2
  docker-doc
  podman-docker
  containerd
  runc
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
  pass before package or repository work. Service auto-start is blocked during
  package installation with a temporary policy-rc.d file, then removed before
  deliberate service start in the storage configuration step. This script does
  not add users to the docker group and does not configure GPU container runtime
  support.
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

installed_package() {
  dpkg-query -W -f='${Status}' "$1" 2>/dev/null | grep -qx 'install ok installed'
}

check_conflicts() {
  local package conflicts=()
  for package in "${CONFLICT_PACKAGES[@]}"; do
    if installed_package "$package"; then
      conflicts+=("$package")
    fi
  done
  if [[ "${#conflicts[@]}" -gt 0 ]]; then
    echo "STOP: conflicting distro packages installed: ${conflicts[*]}" >&2
    return 1
  fi
}

print_plan() {
  cat <<EOF
M4B Docker install plan

No commands are executed in dry-run mode.

Official method:
- Use Docker's official Ubuntu apt repository.
- Key path: $DOCKER_KEYRING
- Source path: $DOCKER_SOURCE
- Install packages: ${DOCKER_PACKAGES[*]}
- Do not use shortcut installer scripts.
- Do not add user accounts to the docker group.
- Do not configure GPU container runtime support in M4B.
- Planned Docker data-root after configuration: /data/docker
- Planned containerd persistent root after configuration: /data/containerd/root

Pre-install required checks:
- sudo -n true
- scripts/common/require-data-mounted.sh
- scripts/common/root-disk-guard.sh
- no conflicting distro Docker/containerd packages
- no existing $POLICY_RC_D

Service auto-start handling:
- Create temporary $POLICY_RC_D that exits 101 before apt install.
- Remove temporary $POLICY_RC_D after apt install.
- Start services deliberately after storage configuration.
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

run_shell_logged() {
  local label="$1"
  local command="$2"
  {
    printf '\n### %s\n\n' "$label"
    printf '```console\n'
    printf '$ %s\n' "$command"
    set +e
    bash -o pipefail -c "$command" 2>&1
    local status=$?
    set -e
    printf '\n[exit=%s]\n' "$status"
    printf '```\n'
    return "$status"
  } >> "$REPORT_PATH"
}

cleanup_policy_rc_d() {
  if [[ "${CREATED_POLICY_RC_D:-0}" == "1" ]]; then
    sudo -n rm -f "$POLICY_RC_D" || true
  fi
}

if [[ "$mode" == "dry-run" ]]; then
  print_plan
  exit 0
fi

cd "$(repo_root)"

sudo -k
sudo -n true
scripts/common/require-data-mounted.sh
scripts/common/root-disk-guard.sh
check_conflicts

if [[ -e "$POLICY_RC_D" ]]; then
  echo "STOP: $POLICY_RC_D already exists; refusing to overwrite it" >&2
  exit 1
fi

for command_name in apt-get curl dpkg install tee chmod; do
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
run_shell_logged "conflicting package check" "dpkg -l | grep -E 'docker|containerd|runc' || true"

trap cleanup_policy_rc_d EXIT
run_logged "create temporary service auto-start blocker" sudo -n tee "$POLICY_RC_D" >/dev/null <<'EOF'
#!/bin/sh
exit 101
EOF
CREATED_POLICY_RC_D=1
run_logged "set temporary service auto-start blocker mode" sudo -n chmod 0755 "$POLICY_RC_D"

run_logged "create Docker apt keyring directory" sudo -n install -m 0755 -d /etc/apt/keyrings
run_shell_logged "install Docker apt signing key" "curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo -n tee '$DOCKER_KEYRING' >/dev/null"
run_logged "set Docker apt signing key permissions" sudo -n chmod a+r "$DOCKER_KEYRING"
run_logged "write Docker apt source" sudo -n tee "$DOCKER_SOURCE" >/dev/null <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: $codename
Components: stable
Signed-By: $DOCKER_KEYRING
Architectures: $arch
EOF
run_logged "apt update for Docker repository" sudo -n apt-get update
run_logged "install Docker Engine packages" sudo -n apt-get install -y "${DOCKER_PACKAGES[@]}"
run_logged "remove temporary service auto-start blocker" sudo -n rm -f "$POLICY_RC_D"
CREATED_POLICY_RC_D=0
trap - EXIT

run_shell_logged "installed Docker package versions" "dpkg-query -W docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin"
run_logged "post-install root-disk guard" scripts/common/root-disk-guard.sh

echo "PASS: Docker Engine packages installed. Configure /data storage before pulling images or running containers."
